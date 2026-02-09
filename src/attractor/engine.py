"""
Pipeline execution engine.
"""

import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .conditions import evaluate_condition
from .events import (
    CheckpointSavedEvent,
    EventEmitter,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStartedEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageRetryingEvent,
    StageStartedEvent,
)
from .handlers import CodergenHandler, HandlerRegistry
from .models import Checkpoint, Context, Graph, Node, Outcome, StageStatus
from .validation import validate_or_raise


class RetryPolicy:
    """Retry policy configuration."""

    def __init__(
        self,
        max_attempts: int = 1,
        initial_delay_ms: int = 200,
        backoff_factor: float = 2.0,
        max_delay_ms: int = 60000,
        jitter: bool = True,
    ):
        self.max_attempts = max(1, max_attempts)
        self.initial_delay_ms = initial_delay_ms
        self.backoff_factor = backoff_factor
        self.max_delay_ms = max_delay_ms
        self.jitter = jitter

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay in seconds for a given attempt (1-indexed)."""
        delay_ms = self.initial_delay_ms * (self.backoff_factor ** (attempt - 1))
        delay_ms = min(delay_ms, self.max_delay_ms)

        if self.jitter:
            delay_ms = delay_ms * random.uniform(0.5, 1.5)

        return delay_ms / 1000.0  # Convert to seconds


class PipelineEngine:
    """Execution engine for Attractor pipelines."""

    def __init__(
        self,
        graph: Graph,
        handler_registry: Optional[HandlerRegistry] = None,
        logs_root: Optional[str] = None,
        event_emitter: Optional[EventEmitter] = None,
    ):
        self.graph = graph
        self.handler_registry = handler_registry or self._create_default_registry()
        self.logs_root = logs_root or self._create_logs_root()
        self.event_emitter = event_emitter or EventEmitter()

        # Validate the graph
        validate_or_raise(graph)

    def _create_default_registry(self) -> HandlerRegistry:
        """Create a default handler registry."""
        registry = HandlerRegistry()
        # Set codergen as default (simulation mode)
        registry.set_default(CodergenHandler(backend=None))
        return registry

    def _create_logs_root(self) -> str:
        """Create a timestamped logs directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logs_dir = Path("logs") / f"run_{timestamp}"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return str(logs_dir)

    def run(self, context: Optional[Context] = None) -> Outcome:
        """Run the pipeline from start to finish."""
        start_time = time.time()
        pipeline_id = Path(self.logs_root).name

        if context is None:
            context = Context()

        # Emit pipeline started event
        self.event_emitter.emit(
            PipelineStartedEvent(self.graph.name or "unnamed", pipeline_id)
        )

        # Mirror graph attributes into context
        context.set("graph.goal", self.graph.goal)

        # Write manifest
        self._write_manifest()

        # Initialize tracking
        completed_nodes = []
        node_outcomes = {}
        node_retries = {}
        stage_index = 0

        # Find start node
        current_node = self._find_start_node()

        try:
            # Main execution loop
            while True:
                node = self.graph.nodes[current_node.id]

                # Step 1: Check for terminal node
                if self._is_terminal(node):
                    gate_ok, failed_gate = self._check_goal_gates(node_outcomes)
                    if not gate_ok and failed_gate:
                        retry_target = self._get_retry_target(failed_gate)
                        if retry_target:
                            current_node = self.graph.nodes[retry_target]
                            continue
                        else:
                            failure_outcome = Outcome(
                                status=StageStatus.FAIL,
                                failure_reason="Goal gate unsatisfied and no retry target",
                            )
                            # Emit pipeline failed event
                            self.event_emitter.emit(
                                PipelineFailedEvent(
                                    failure_outcome.failure_reason or "Unknown error",
                                    time.time() - start_time,
                                )
                            )
                            return failure_outcome
                    # Pipeline complete
                    break

                # Step 2: Execute node with retry
                retry_policy = self._build_retry_policy(node)
                outcome = self._execute_with_retry(
                    node, context, retry_policy, node_retries, stage_index
                )

                stage_index += 1

                # Step 3: Record completion
                completed_nodes.append(node.id)
                node_outcomes[node.id] = outcome

                # Step 4: Apply context updates
                for key, value in outcome.context_updates.items():
                    context.set(key, value)
                context.set("outcome", outcome.status.value)
                if outcome.preferred_label:
                    context.set("preferred_label", outcome.preferred_label)

                # Step 5: Save checkpoint
                self._save_checkpoint(
                    context, current_node.id, completed_nodes, node_retries
                )

                # Step 6: Select next edge
                next_edge = self._select_edge(node, outcome, context)
                if next_edge is None:
                    if outcome.status == StageStatus.FAIL:
                        failure_outcome = Outcome(
                            status=StageStatus.FAIL,
                            failure_reason="Stage failed with no outgoing fail edge",
                        )
                        # Emit pipeline failed event
                        self.event_emitter.emit(
                            PipelineFailedEvent(
                                failure_outcome.failure_reason or "Unknown error",
                                time.time() - start_time,
                            )
                        )
                        return failure_outcome
                    break

                # Step 7: Advance to next node
                current_node = self.graph.nodes[next_edge.to_node]
        except Exception as e:
            # Emit pipeline failed event
            self.event_emitter.emit(
                PipelineFailedEvent(str(e), time.time() - start_time)
            )
            raise

        # Emit pipeline completed event
        duration = time.time() - start_time
        artifact_count = len(completed_nodes)
        self.event_emitter.emit(PipelineCompletedEvent(duration, artifact_count))

        # Return final outcome
        return Outcome(
            status=StageStatus.SUCCESS, notes="Pipeline completed successfully"
        )

    def _find_start_node(self) -> Node:
        """Find the start node."""
        for node in self.graph.nodes.values():
            if node.shape == "Mdiamond" or node.id.lower() in ["start", "Start"]:
                return node
        raise ValueError("No start node found")

    def _is_terminal(self, node: Node) -> bool:
        """Check if node is a terminal/exit node."""
        return node.shape == "Msquare" or node.id.lower() in ["exit", "end", "done"]

    def _check_goal_gates(self, node_outcomes: dict) -> Tuple[bool, Optional[Node]]:
        """Check if all goal gate nodes have succeeded."""
        for node_id, outcome in node_outcomes.items():
            node = self.graph.nodes[node_id]
            if node.goal_gate and outcome.status not in [
                StageStatus.SUCCESS,
                StageStatus.PARTIAL_SUCCESS,
            ]:
                return False, node
        return True, None

    def _get_retry_target(self, node: Node) -> Optional[str]:
        """Get retry target for a node."""
        if node.retry_target:
            return node.retry_target
        if node.fallback_retry_target:
            return node.fallback_retry_target
        if self.graph.retry_target:
            return self.graph.retry_target
        if self.graph.fallback_retry_target:
            return self.graph.fallback_retry_target
        return None

    def _build_retry_policy(self, node: Node) -> RetryPolicy:
        """Build retry policy for a node."""
        max_retries = node.max_retries
        if max_retries == 0:
            max_retries = self.graph.default_max_retry

        return RetryPolicy(max_attempts=max_retries + 1)

    def _execute_with_retry(
        self,
        node: Node,
        context: Context,
        retry_policy: RetryPolicy,
        node_retries: dict,
        stage_index: int,
    ) -> Outcome:
        """Execute a node with retry logic."""
        try:
            handler = self.handler_registry.resolve(node)
        except ValueError as e:
            # No handler found for this node
            return Outcome(status=StageStatus.FAIL, failure_reason=str(e))
        
        stage_start_time = time.time()

        # Emit stage started event
        self.event_emitter.emit(StageStartedEvent(node.label or node.id, stage_index))

        for attempt in range(1, retry_policy.max_attempts + 1):
            try:
                outcome = handler.execute(node, context, self.graph, self.logs_root)
            except Exception as e:
                if attempt < retry_policy.max_attempts:
                    delay = retry_policy.delay_for_attempt(attempt)
                    # Emit stage retrying event
                    self.event_emitter.emit(
                        StageRetryingEvent(
                            node.label or node.id, stage_index, attempt + 1, delay
                        )
                    )
                    time.sleep(delay)
                    continue
                else:
                    # Emit stage failed event
                    duration = time.time() - stage_start_time
                    self.event_emitter.emit(
                        StageFailedEvent(
                            node.label or node.id,
                            stage_index,
                            f"Exception: {e!s}",
                            False,
                        )
                    )
                    return Outcome(
                        status=StageStatus.FAIL, failure_reason=f"Exception: {e!s}"
                    )

            # Check outcome
            if outcome.status in [StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS]:
                # Reset retry counter
                if node.id in node_retries:
                    del node_retries[node.id]
                # Emit stage completed event
                duration = time.time() - stage_start_time
                self.event_emitter.emit(
                    StageCompletedEvent(node.label or node.id, stage_index, duration)
                )
                return outcome

            if outcome.status == StageStatus.RETRY:
                if attempt < retry_policy.max_attempts:
                    # Increment retry counter
                    node_retries[node.id] = node_retries.get(node.id, 0) + 1
                    delay = retry_policy.delay_for_attempt(attempt)
                    # Emit stage retrying event
                    self.event_emitter.emit(
                        StageRetryingEvent(
                            node.label or node.id, stage_index, attempt + 1, delay
                        )
                    )
                    time.sleep(delay)
                    continue
                else:
                    # Retries exhausted
                    duration = time.time() - stage_start_time
                    if node.allow_partial:
                        self.event_emitter.emit(
                            StageCompletedEvent(
                                node.label or node.id, stage_index, duration
                            )
                        )
                        return Outcome(
                            status=StageStatus.PARTIAL_SUCCESS,
                            notes="retries exhausted, partial accepted",
                        )
                    # Emit stage failed event
                    self.event_emitter.emit(
                        StageFailedEvent(
                            node.label or node.id,
                            stage_index,
                            "max retries exceeded",
                            False,
                        )
                    )
                    return Outcome(
                        status=StageStatus.FAIL, failure_reason="max retries exceeded"
                    )

            if outcome.status == StageStatus.FAIL:
                # Emit stage failed event
                duration = time.time() - stage_start_time
                self.event_emitter.emit(
                    StageFailedEvent(
                        node.label or node.id,
                        stage_index,
                        outcome.failure_reason or "Unknown failure",
                        False,
                    )
                )
                return outcome

        # Emit stage failed event (shouldn't reach here)
        duration = time.time() - stage_start_time
        self.event_emitter.emit(
            StageFailedEvent(
                node.label or node.id,
                stage_index,
                "max retries exceeded",
                False,
            )
        )
        return Outcome(status=StageStatus.FAIL, failure_reason="max retries exceeded")

    def _select_edge(self, node: Node, outcome: Outcome, context: Context):
        """Select the next edge using the 5-step priority algorithm."""
        edges = self.graph.outgoing_edges(node.id)

        if not edges:
            return None

        # Step 1: Condition matching
        condition_matched = []
        for edge in edges:
            if edge.condition and evaluate_condition(edge.condition, outcome, context):
                condition_matched.append(edge)

        if condition_matched:
            return self._best_by_weight_then_lexical(condition_matched)

        # Step 2: Preferred label
        if outcome.preferred_label:
            pref_label = self._normalize_label(outcome.preferred_label)
            for edge in edges:
                if self._normalize_label(edge.label) == pref_label:
                    return edge

        # Step 3: Suggested next IDs
        if outcome.suggested_next_ids:
            for suggested_id in outcome.suggested_next_ids:
                for edge in edges:
                    if edge.to_node == suggested_id:
                        return edge

        # Step 4 & 5: Weight with lexical tiebreak (unconditional edges only)
        unconditional = [e for e in edges if not e.condition]
        if unconditional:
            return self._best_by_weight_then_lexical(unconditional)

        # Fallback: If outcome is not FAIL and there are conditional edges that didn't match,
        # select any edge as a fallback to keep the pipeline moving
        if outcome.status != StageStatus.FAIL:
            return self._best_by_weight_then_lexical(edges)

        # No matching edge found for FAIL outcome
        return None

    def _normalize_label(self, label: str) -> str:
        """Normalize a label for matching."""
        label = label.lower().strip()

        # Strip accelerator prefixes like [Y], Y), Y -
        import re

        label = re.sub(r"^\[?\w+[\])\-]\s*", "", label)

        return label

    def _best_by_weight_then_lexical(self, edges: List):
        """Select best edge by weight, then lexical tiebreak."""
        if not edges:
            return None

        # Sort by weight descending, then to_node ascending
        sorted_edges = sorted(edges, key=lambda e: (-e.weight, e.to_node))
        return sorted_edges[0]

    def _save_checkpoint(
        self,
        context: Context,
        current_node: str,
        completed_nodes: List[str],
        node_retries: dict,
    ):
        """Save a checkpoint."""
        checkpoint = Checkpoint(
            timestamp=datetime.now().isoformat(),
            current_node=current_node,
            completed_nodes=completed_nodes.copy(),
            node_retries=node_retries.copy(),
            context_values=context.snapshot(),
            logs=context.logs.copy(),
        )

        checkpoint_path = Path(self.logs_root) / "checkpoint.json"
        checkpoint.save(str(checkpoint_path))

        # Emit checkpoint saved event
        self.event_emitter.emit(CheckpointSavedEvent(current_node))

    def _write_manifest(self):
        """Write pipeline manifest."""
        manifest = {
            "name": self.graph.name,
            "goal": self.graph.goal,
            "start_time": datetime.now().isoformat(),
        }

        # Ensure logs directory exists
        logs_path = Path(self.logs_root)
        logs_path.mkdir(parents=True, exist_ok=True)

        manifest_path = logs_path / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)


def run_pipeline(
    graph: Graph,
    context: Optional[Context] = None,
    handler_registry: Optional[HandlerRegistry] = None,
    logs_root: Optional[str] = None,
    event_emitter: Optional[EventEmitter] = None,
) -> Outcome:
    """Run a pipeline and return the final outcome."""
    engine = PipelineEngine(graph, handler_registry, logs_root, event_emitter)
    return engine.run(context)
