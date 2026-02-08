"""
Node handlers for Attractor pipelines.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import os
from pathlib import Path

from .models import Node, Context, Graph, Outcome, StageStatus


class Handler(ABC):
    """Base interface for all node handlers."""
    
    @abstractmethod
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        """Execute the handler logic."""
        pass


class CodergenBackend(ABC):
    """Interface for LLM backends used by the codergen handler."""
    
    @abstractmethod
    def run(self, node: Node, prompt: str, context: Context) -> Any:
        """Execute the LLM call and return response or Outcome."""
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
        
        raise ValueError(f"No handler found for node {node.id} (type={node.type}, shape={node.shape})")


class StartHandler(Handler):
    """No-op handler for pipeline entry point."""
    
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)


class ExitHandler(Handler):
    """No-op handler for pipeline exit point."""
    
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)


class ConditionalHandler(Handler):
    """Pass-through handler for conditional routing nodes."""
    
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        return Outcome(
            status=StageStatus.SUCCESS,
            notes=f"Conditional node evaluated: {node.id}"
        )


class CodergenHandler(Handler):
    """Handler for LLM tasks (code generation, analysis, planning)."""
    
    def __init__(self, backend: Optional[CodergenBackend] = None):
        self.backend = backend
    
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        # 1. Build prompt
        prompt = node.prompt
        if not prompt:
            prompt = node.label
        
        # Expand $goal variable
        prompt = prompt.replace("$goal", graph.goal)
        
        # 2. Write prompt to logs
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)
        
        with open(stage_dir / "prompt.md", 'w') as f:
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
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=str(e)
                )
        else:
            # Simulation mode
            response_text = f"[Simulated] Response for stage: {node.id}"
        
        # 4. Write response to logs
        with open(stage_dir / "response.md", 'w') as f:
            f.write(response_text)
        
        # 5. Write status and return outcome
        outcome = Outcome(
            status=StageStatus.SUCCESS,
            notes=f"Stage completed: {node.id}",
            context_updates={
                "last_stage": node.id,
                "last_response": response_text[:200] if response_text else ""
            }
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
            "failure_reason": outcome.failure_reason
        }
        
        with open(stage_dir / "status.json", 'w') as f:
            json.dump(status_data, f, indent=2)
