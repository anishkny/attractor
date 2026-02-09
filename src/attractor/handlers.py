"""
Node handlers for Attractor pipelines.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .models import (
    Answer,
    AnswerStatus,
    Context,
    Graph,
    Node,
    Option,
    Outcome,
    Question,
    QuestionType,
    StageStatus,
)

# Constants
MAX_OUTPUT_LENGTH = 200  # Maximum length for output snippets in context


class Handler(ABC):
    """Base interface for all node handlers."""

    @abstractmethod
    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        """Execute the handler logic."""
        pass


class CodergenBackend(ABC):
    """Interface for LLM backends used by the codergen handler."""

    @abstractmethod
    def run(self, node: Node, prompt: str, context: Context) -> Any:
        """Execute the LLM call and return response or Outcome."""
        pass


class Interviewer(ABC):
    """Interface for human interaction (TUI, web, IDE frontends)."""

    @abstractmethod
    def ask(self, question: Question) -> Tuple[AnswerStatus, Optional[Answer]]:
        """
        Present a question to the human and wait for an answer.

        Returns:
            (status, answer) tuple where:
            - status is AnswerStatus (ANSWERED, TIMEOUT, SKIPPED)
            - answer is the Answer object if status is ANSWERED, None otherwise
        """
        pass


# Shape to handler type mapping
SHAPE_TO_TYPE = {
    "Mdiamond": "start",
    "Msquare": "exit",
    "box": "codergen",
    "hexagon": "wait.human",
    "diamond": "conditional",
    "component": "parallel",
    "tripleoctagon": "parallel.fan_in",
    "parallelogram": "tool",
    "house": "stack.manager_loop",
}


class HandlerRegistry:
    """Registry for node handlers."""

    def __init__(self):
        self.handlers: Dict[str, Handler] = {}
        self.default_handler: Optional[Handler] = None

        # Register built-in handlers
        self.register("start", StartHandler())
        self.register("exit", ExitHandler())
        self.register("conditional", ConditionalHandler())
        self.register("tool", ToolHandler())
        self.register("wait.human", WaitForHumanHandler())
        self.register("parallel", ParallelHandler())
        self.register("parallel.fan_in", FanInHandler())
        self.register("stack.manager_loop", ManagerLoopHandler())

    def register(self, type_string: str, handler: Handler):
        """Register a handler for a type string."""
        self.handlers[type_string] = handler

    def set_default(self, handler: Handler):
        """Set the default handler (typically codergen)."""
        self.default_handler = handler

    def resolve(self, node: Node) -> Handler:
        """Resolve the handler for a node."""
        # 1. Explicit type attribute
        if node.type and node.type in self.handlers:
            return self.handlers[node.type]

        # 2. Shape-based resolution
        handler_type = SHAPE_TO_TYPE.get(node.shape)
        if handler_type and handler_type in self.handlers:
            return self.handlers[handler_type]

        # 3. Default
        if self.default_handler:
            return self.default_handler

        raise ValueError(
            f"No handler found for node {node.id} (type={node.type}, shape={node.shape})"
        )


class StartHandler(Handler):
    """No-op handler for pipeline entry point."""

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)


class ExitHandler(Handler):
    """No-op handler for pipeline exit point."""

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)


class ConditionalHandler(Handler):
    """Pass-through handler for conditional routing nodes."""

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        return Outcome(
            status=StageStatus.SUCCESS, notes=f"Conditional node evaluated: {node.id}"
        )


class CodergenHandler(Handler):
    """Handler for LLM tasks (code generation, analysis, planning)."""

    def __init__(self, backend: Optional[CodergenBackend] = None):
        self.backend = backend

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        # 1. Build prompt
        prompt = node.prompt
        if not prompt:
            prompt = node.label

        # Expand $goal variable
        prompt = prompt.replace("$goal", graph.goal)

        # 2. Write prompt to logs
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)

        with open(stage_dir / "prompt.md", "w") as f:
            f.write(prompt)

        # 3. Call LLM backend
        if self.backend:
            try:
                result = self.backend.run(node, prompt, context)

                # If backend returns an Outcome, use it
                if isinstance(result, Outcome):
                    self._write_status(stage_dir, result)
                    return result

                response_text = str(result)
            except Exception as e:
                return Outcome(status=StageStatus.FAIL, failure_reason=str(e))
        else:
            # Simulation mode
            response_text = f"[Simulated] Response for stage: {node.id}"

        # 4. Write response to logs
        with open(stage_dir / "response.md", "w") as f:
            f.write(response_text)

        # 5. Write status and return outcome
        outcome = Outcome(
            status=StageStatus.SUCCESS,
            notes=f"Stage completed: {node.id}",
            context_updates={
                "last_stage": node.id,
                "last_response": response_text[:MAX_OUTPUT_LENGTH]
                if response_text
                else "",
            },
        )

        self._write_status(stage_dir, outcome)
        return outcome

    def _write_status(self, stage_dir: Path, outcome: Outcome):
        """Write status.json to stage directory."""
        import json

        status_data = {
            "outcome": outcome.status.value,
            "preferred_next_label": outcome.preferred_label,
            "suggested_next_ids": outcome.suggested_next_ids,
            "notes": outcome.notes,
            "failure_reason": outcome.failure_reason,
        }

        with open(stage_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)


class ToolHandler(Handler):
    """Handler for external tool execution (shell commands, API calls)."""

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        import subprocess

        # 1. Get command from prompt or label
        command = node.prompt or node.label
        if not command:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No command specified for tool node",
            )

        # 2. Expand $goal variable
        command = command.replace("$goal", graph.goal)

        # 3. Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 4. Write command to logs
        with open(stage_dir / "command.txt", "w") as f:
            f.write(command)

        # 5. Execute command
        try:
            timeout_value = node.attrs.get("timeout")
            if timeout_value and isinstance(timeout_value, str):
                # Parse duration string like "900s" to seconds
                from .models import parse_duration

                timeout_value = parse_duration(timeout_value)

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_value,
            )

            # 6. Write stdout and stderr to logs
            with open(stage_dir / "stdout.txt", "w") as f:
                f.write(result.stdout)
            with open(stage_dir / "stderr.txt", "w") as f:
                f.write(result.stderr)

            # 7. Determine outcome based on return code
            if result.returncode == 0:
                outcome = Outcome(
                    status=StageStatus.SUCCESS,
                    notes=f"Tool execution succeeded: {node.id}",
                    context_updates={
                        "last_tool_stdout": result.stdout[:MAX_OUTPUT_LENGTH]
                        if result.stdout
                        else "",
                        "last_tool_returncode": str(result.returncode),
                    },
                )
            else:
                outcome = Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"Tool execution failed with return code {result.returncode}",
                    notes=result.stderr[:MAX_OUTPUT_LENGTH] if result.stderr else "",
                )

        except subprocess.TimeoutExpired:
            outcome = Outcome(
                status=StageStatus.FAIL, failure_reason="Tool execution timed out"
            )
        except Exception as e:
            outcome = Outcome(
                status=StageStatus.FAIL, failure_reason=f"Tool execution error: {e!s}"
            )

        # 8. Write status
        self._write_status(stage_dir, outcome)
        return outcome

    def _write_status(self, stage_dir: Path, outcome: Outcome):
        """Write status.json to stage directory."""
        import json

        status_data = {
            "outcome": outcome.status.value,
            "preferred_next_label": outcome.preferred_label,
            "suggested_next_ids": outcome.suggested_next_ids,
            "notes": outcome.notes,
            "failure_reason": outcome.failure_reason,
        }

        with open(stage_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)


class WaitForHumanHandler(Handler):
    """Handler for human-in-the-loop gates."""

    def __init__(self, interviewer: Optional[Interviewer] = None):
        self.interviewer = interviewer

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        import json

        # 1. Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 2. Get outgoing edges to derive choices
        edges = [e for e in graph.edges if e.from_node == node.id]

        if not edges:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No outgoing edges for human gate",
            )

        # 3. Build choices from edges
        choices = []
        for edge in edges:
            label = edge.label if edge.label else edge.to_node
            key = self._parse_accelerator_key(label)
            choices.append({"key": key, "label": label, "to": edge.to_node})

        # 4. Create question
        options = [Option(key=c["key"], label=c["label"]) for c in choices]
        question = Question(
            text=node.label or "Select an option:",
            type=QuestionType.MULTIPLE_CHOICE,
            options=options,
            stage=node.id,
        )

        # 5. Write question to logs
        with open(stage_dir / "question.json", "w") as f:
            json.dump(
                {
                    "text": question.text,
                    "options": [{"key": o.key, "label": o.label} for o in options],
                },
                f,
                indent=2,
            )

        # 6. Ask the question
        if self.interviewer:
            status, answer = self.interviewer.ask(question)

            if status == AnswerStatus.TIMEOUT:
                # Check for default choice
                default_choice = node.attrs.get("human.default_choice")
                if default_choice:
                    selected = next(
                        (c for c in choices if c["key"] == default_choice), choices[0]
                    )
                else:
                    return Outcome(
                        status=StageStatus.RETRY,
                        failure_reason="Human gate timeout, no default",
                    )
            elif status == AnswerStatus.SKIPPED:
                return Outcome(
                    status=StageStatus.FAIL, failure_reason="Human skipped interaction"
                )
            else:
                # Find matching choice
                selected = self._find_choice_matching(
                    answer.value if answer else "", choices
                )
                if not selected:
                    selected = choices[0]  # Fallback to first
        else:
            # Simulation mode - default to first choice
            selected = choices[0]

        # 7. Write answer to logs
        with open(stage_dir / "answer.json", "w") as f:
            json.dump(
                {
                    "key": selected["key"],
                    "label": selected["label"],
                    "to": selected["to"],
                },
                f,
                indent=2,
            )

        # 8. Return outcome with suggested next node
        outcome = Outcome(
            status=StageStatus.SUCCESS,
            suggested_next_ids=[selected["to"]],
            context_updates={
                "human.gate.selected": selected["key"],
                "human.gate.label": selected["label"],
            },
        )

        self._write_status(stage_dir, outcome)
        return outcome

    def _parse_accelerator_key(self, label: str) -> str:
        """Parse accelerator key from label like '[Y] Yes' or 'Y) Yes'."""
        import re

        # Pattern: [K] Label
        match = re.match(r"^\[([A-Za-z0-9])\]\s*(.+)$", label)
        if match:
            return match.group(1).upper()

        # Pattern: K) Label
        match = re.match(r"^([A-Za-z0-9])\)\s*(.+)$", label)
        if match:
            return match.group(1).upper()

        # Pattern: K - Label
        match = re.match(r"^([A-Za-z0-9])\s*-\s*(.+)$", label)
        if match:
            return match.group(1).upper()

        # Default: first character
        return label[0].upper() if label else "A"

    def _find_choice_matching(self, answer_key: str, choices: list) -> Optional[dict]:
        """Find choice matching the answer key."""
        answer_key = answer_key.upper()
        for choice in choices:
            if choice["key"].upper() == answer_key:
                return choice
        return None

    def _write_status(self, stage_dir: Path, outcome: Outcome):
        """Write status.json to stage directory."""
        import json

        status_data = {
            "outcome": outcome.status.value,
            "preferred_next_label": outcome.preferred_label,
            "suggested_next_ids": outcome.suggested_next_ids,
            "notes": outcome.notes,
            "failure_reason": outcome.failure_reason,
        }

        with open(stage_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)


class ParallelHandler(Handler):
    """Handler for parallel fan-out execution."""

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        import json
        from pathlib import Path

        # 1. Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 2. Get outgoing edges for parallel branches
        branches = graph.outgoing_edges(node.id)

        if not branches:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No outgoing edges for parallel node",
            )

        # 3. Get join and error policies
        join_policy = node.attrs.get("join_policy", "wait_all")
        node.attrs.get("error_policy", "continue")
        int(node.attrs.get("max_parallel", "4"))

        # 4. Execute branches in parallel (simulation - just record branch targets)
        # In a full implementation, this would execute subgraphs
        results = []

        for _i, branch in enumerate(branches):
            # Clone context for each branch
            context.clone()

            # Simulate branch execution
            branch_result = {
                "branch_id": branch.to_node,
                "status": "success",  # Simplified for now
                "notes": f"Branch to {branch.to_node}",
            }
            results.append(branch_result)

        # 5. Write results to logs
        with open(stage_dir / "parallel_results.json", "w") as f:
            json.dump(results, f, indent=2)

        # 6. Evaluate join policy
        success_count = sum(1 for r in results if r["status"] == "success")
        fail_count = len(results) - success_count

        if join_policy == "wait_all":
            if fail_count == 0:
                status = StageStatus.SUCCESS
            else:
                status = StageStatus.PARTIAL_SUCCESS
        elif join_policy == "first_success":
            status = StageStatus.SUCCESS if success_count > 0 else StageStatus.FAIL
        else:
            # Default to wait_all behavior
            status = (
                StageStatus.SUCCESS if fail_count == 0 else StageStatus.PARTIAL_SUCCESS
            )

        # 7. Store results in context for downstream fan-in
        outcome = Outcome(
            status=status,
            notes=f"Parallel execution: {success_count}/{len(results)} branches succeeded",
            context_updates={
                "parallel.results": results,
                "parallel.branch_count": len(results),
                "parallel.success_count": success_count,
            },
        )

        self._write_status(stage_dir, outcome)
        return outcome

    def _write_status(self, stage_dir: Path, outcome: Outcome):
        """Write status.json to stage directory."""
        import json

        status_data = {
            "outcome": outcome.status.value,
            "preferred_next_label": outcome.preferred_label,
            "suggested_next_ids": outcome.suggested_next_ids,
            "notes": outcome.notes,
            "failure_reason": outcome.failure_reason,
        }

        with open(stage_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)


class FanInHandler(Handler):
    """Handler for consolidating results from parallel branches."""

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        import json
        from pathlib import Path

        # 1. Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 2. Read parallel results from context
        results = context.get("parallel.results")

        if not results:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No parallel results to evaluate",
            )

        # 3. Evaluate and select best candidate
        # In a full implementation, this might use LLM to rank candidates
        # For now, we just take the first successful result
        best_result = None
        for result in results:
            if result.get("status") == "success":
                best_result = result
                break

        if not best_result:
            best_result = results[0]  # Fallback to first result

        # 4. Write consolidated results
        with open(stage_dir / "fan_in_result.json", "w") as f:
            json.dump(
                {"selected": best_result, "total_candidates": len(results)}, f, indent=2
            )

        # 5. Return outcome
        outcome = Outcome(
            status=StageStatus.SUCCESS,
            notes=f"Selected best result from {len(results)} candidates",
            context_updates={
                "fan_in.selected": best_result.get("branch_id", ""),
                "fan_in.candidate_count": len(results),
            },
        )

        self._write_status(stage_dir, outcome)
        return outcome

    def _write_status(self, stage_dir: Path, outcome: Outcome):
        """Write status.json to stage directory."""
        import json

        status_data = {
            "outcome": outcome.status.value,
            "preferred_next_label": outcome.preferred_label,
            "suggested_next_ids": outcome.suggested_next_ids,
            "notes": outcome.notes,
            "failure_reason": outcome.failure_reason,
        }

        with open(stage_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)


class ManagerLoopHandler(Handler):
    """
    Manager loop handler for supervising child pipelines.
    
    Orchestrates sprint-based iteration by supervising a child pipeline. 
    The manager observes the child's telemetry, evaluates progress via a 
    guard function, and optionally steers the child through intervention.
    """

    def execute(
        self, node: Node, context: Context, graph: Graph, logs_root: str
    ) -> Outcome:
        """Execute manager loop supervision."""
        import json
        import subprocess
        import time
        from pathlib import Path

        from .conditions import evaluate_condition

        # Parse configuration
        child_dotfile = graph.attrs.get("stack.child_dotfile", "")
        if not child_dotfile:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No child_dotfile specified in graph attributes",
            )

        poll_interval_str = node.attrs.get("manager.poll_interval", "45s")
        poll_interval = self._parse_duration(poll_interval_str)

        max_cycles = int(node.attrs.get("manager.max_cycles", "1000"))
        stop_condition = node.attrs.get("manager.stop_condition", "")
        actions = [
            a.strip() for a in node.attrs.get("manager.actions", "observe,wait").split(",")
        ]
        child_autostart = node.attrs.get("stack.child_autostart", "true").lower() == "true"

        # Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)

        # 1. Auto-start child if configured
        child_process = None
        if child_autostart:
            try:
                # Start child pipeline in subprocess
                child_logs_dir = stage_dir / "child_logs"
                child_logs_dir.mkdir(exist_ok=True)

                child_process = subprocess.Popen(
                    ["python", "-m", "attractor.cli", child_dotfile, "--logs-root", str(child_logs_dir)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                context.set("stack.child.pid", str(child_process.pid))
                context.set("stack.child.status", "running")
            except Exception as e:
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"Failed to start child pipeline: {e}",
                )

        # 2. Observation loop
        for cycle in range(1, max_cycles + 1):
            # Observe: ingest child telemetry
            if "observe" in actions:
                self._ingest_child_telemetry(context, stage_dir, child_process)

            # Steer: optionally intervene (simplified - just log for now)
            if "steer" in actions:
                steer_msg = f"Cycle {cycle}: Observing child progress"
                context.set("stack.steer.last_message", steer_msg)

            # Evaluate stop conditions
            child_status = context.get("stack.child.status", "")
            if child_status in ["completed", "failed"]:
                child_outcome = context.get("stack.child.outcome", "")
                if child_outcome == "success" or child_status == "completed":
                    # Write outcome
                    outcome = Outcome(
                        status=StageStatus.SUCCESS,
                        notes="Child pipeline completed successfully",
                    )
                    self._write_status(stage_dir, outcome)
                    return outcome
                if child_status == "failed":
                    outcome = Outcome(
                        status=StageStatus.FAIL,
                        failure_reason="Child pipeline failed",
                    )
                    self._write_status(stage_dir, outcome)
                    return outcome

            # Check custom stop condition
            if stop_condition:
                try:
                    if evaluate_condition(
                        stop_condition,
                        Outcome(status=StageStatus.SUCCESS),
                        context,
                    ):
                        outcome = Outcome(
                            status=StageStatus.SUCCESS,
                            notes="Stop condition satisfied",
                        )
                        self._write_status(stage_dir, outcome)
                        return outcome
                except Exception:
                    pass  # Continue if condition evaluation fails

            # Wait before next cycle
            if "wait" in actions:
                time.sleep(poll_interval)

        # Max cycles exceeded
        # Terminate child if still running
        if child_process and child_process.poll() is None:
            child_process.terminate()
            try:
                child_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child_process.kill()

        outcome = Outcome(
            status=StageStatus.FAIL,
            failure_reason=f"Max cycles ({max_cycles}) exceeded",
        )
        self._write_status(stage_dir, outcome)
        return outcome

    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string to seconds."""
        import re

        duration_str = duration_str.strip()
        match = re.match(r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)?", duration_str)
        if not match:
            return 45.0  # Default

        value = float(match.group(1))
        unit = match.group(2) or "s"

        conversions = {
            "ms": 0.001,
            "s": 1.0,
            "m": 60.0,
            "h": 3600.0,
            "d": 86400.0,
        }
        return value * conversions.get(unit, 1.0)

    def _ingest_child_telemetry(
        self, context: Context, stage_dir: Path, child_process
    ):
        """Ingest telemetry from child pipeline."""
        # Check if child process is still running
        if child_process:
            poll_result = child_process.poll()
            if poll_result is not None:
                # Child has exited
                if poll_result == 0:
                    context.set("stack.child.status", "completed")
                    context.set("stack.child.outcome", "success")
                else:
                    context.set("stack.child.status", "failed")
                    context.set("stack.child.outcome", "failure")
                return

        # Try to read child's checkpoint/manifest
        child_logs_dir = stage_dir / "child_logs"
        if child_logs_dir.exists():
            # Look for most recent run directory
            run_dirs = sorted(child_logs_dir.glob("run_*"))
            if run_dirs:
                latest_run = run_dirs[-1]
                checkpoint_path = latest_run / "checkpoint.json"
                if checkpoint_path.exists():
                    try:
                        with open(checkpoint_path) as f:
                            checkpoint_data = json.load(f)
                            context.set(
                                "stack.child.current_node",
                                checkpoint_data.get("current_node", ""),
                            )
                            context.set(
                                "stack.child.completed_nodes",
                                len(checkpoint_data.get("completed_nodes", [])),
                            )
                    except Exception:
                        pass  # Ignore read errors

    def _write_status(self, stage_dir: Path, outcome: Outcome):
        """Write status.json to stage directory."""
        import json

        status_data = {
            "outcome": outcome.status.value,
            "preferred_next_label": outcome.preferred_label,
            "suggested_next_ids": outcome.suggested_next_ids,
            "notes": outcome.notes,
            "failure_reason": outcome.failure_reason,
        }

        with open(stage_dir / "status.json", "w") as f:
            json.dump(status_data, f, indent=2)
