"""
Node handlers for Attractor pipelines.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import os
from pathlib import Path

from .models import (
    Node, Context, Graph, Outcome, StageStatus,
    Question, QuestionType, Option, Answer, AnswerStatus
)


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


class Interviewer(ABC):
    """Interface for human interaction (TUI, web, IDE frontends)."""
    
    @abstractmethod
    def ask(self, question: Question) -> tuple[AnswerStatus, Optional[Answer]]:
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


class ToolHandler(Handler):
    """Handler for external tool execution (shell commands, API calls)."""
    
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        import subprocess
        import shlex
        
        # 1. Get command from prompt or label
        command = node.prompt or node.label
        if not command:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No command specified for tool node"
            )
        
        # 2. Expand $goal variable
        command = command.replace("$goal", graph.goal)
        
        # 3. Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)
        
        # 4. Write command to logs
        with open(stage_dir / "command.txt", 'w') as f:
            f.write(command)
        
        # 5. Execute command
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=node.timeout if hasattr(node, 'timeout') and node.timeout else None
            )
            
            # 6. Write stdout and stderr to logs
            with open(stage_dir / "stdout.txt", 'w') as f:
                f.write(result.stdout)
            with open(stage_dir / "stderr.txt", 'w') as f:
                f.write(result.stderr)
            
            # 7. Determine outcome based on return code
            if result.returncode == 0:
                outcome = Outcome(
                    status=StageStatus.SUCCESS,
                    notes=f"Tool execution succeeded: {node.id}",
                    context_updates={
                        "last_tool_stdout": result.stdout[:200] if result.stdout else "",
                        "last_tool_returncode": str(result.returncode)
                    }
                )
            else:
                outcome = Outcome(
                    status=StageStatus.FAIL,
                    failure_reason=f"Tool execution failed with return code {result.returncode}",
                    notes=result.stderr[:200] if result.stderr else ""
                )
        
        except subprocess.TimeoutExpired:
            outcome = Outcome(
                status=StageStatus.FAIL,
                failure_reason="Tool execution timed out"
            )
        except Exception as e:
            outcome = Outcome(
                status=StageStatus.FAIL,
                failure_reason=f"Tool execution error: {str(e)}"
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
            "failure_reason": outcome.failure_reason
        }
        
        with open(stage_dir / "status.json", 'w') as f:
            json.dump(status_data, f, indent=2)


class WaitForHumanHandler(Handler):
    """Handler for human-in-the-loop gates."""
    
    def __init__(self, interviewer: Optional[Interviewer] = None):
        self.interviewer = interviewer
    
    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        import json
        import re
        
        # 1. Create stage directory
        stage_dir = Path(logs_root) / node.id
        stage_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Get outgoing edges to derive choices
        edges = [e for e in graph.edges if e.from_node == node.id]
        
        if not edges:
            return Outcome(
                status=StageStatus.FAIL,
                failure_reason="No outgoing edges for human gate"
            )
        
        # 3. Build choices from edges
        choices = []
        for edge in edges:
            label = edge.label if edge.label else edge.to_node
            key = self._parse_accelerator_key(label)
            choices.append({
                "key": key,
                "label": label,
                "to": edge.to_node
            })
        
        # 4. Create question
        options = [Option(key=c["key"], label=c["label"]) for c in choices]
        question = Question(
            text=node.label or "Select an option:",
            type=QuestionType.MULTIPLE_CHOICE,
            options=options,
            stage=node.id
        )
        
        # 5. Write question to logs
        with open(stage_dir / "question.json", 'w') as f:
            json.dump({
                "text": question.text,
                "options": [{"key": o.key, "label": o.label} for o in options]
            }, f, indent=2)
        
        # 6. Ask the question
        if self.interviewer:
            status, answer = self.interviewer.ask(question)
            
            if status == AnswerStatus.TIMEOUT:
                # Check for default choice
                default_choice = node.attrs.get("human.default_choice")
                if default_choice:
                    selected = next((c for c in choices if c["key"] == default_choice), choices[0])
                else:
                    return Outcome(
                        status=StageStatus.RETRY,
                        failure_reason="Human gate timeout, no default"
                    )
            elif status == AnswerStatus.SKIPPED:
                return Outcome(
                    status=StageStatus.FAIL,
                    failure_reason="Human skipped interaction"
                )
            else:
                # Find matching choice
                selected = self._find_choice_matching(answer.value if answer else "", choices)
                if not selected:
                    selected = choices[0]  # Fallback to first
        else:
            # Simulation mode - default to first choice
            selected = choices[0]
        
        # 7. Write answer to logs
        with open(stage_dir / "answer.json", 'w') as f:
            json.dump({
                "key": selected["key"],
                "label": selected["label"],
                "to": selected["to"]
            }, f, indent=2)
        
        # 8. Return outcome with suggested next node
        outcome = Outcome(
            status=StageStatus.SUCCESS,
            suggested_next_ids=[selected["to"]],
            context_updates={
                "human.gate.selected": selected["key"],
                "human.gate.label": selected["label"]
            }
        )
        
        self._write_status(stage_dir, outcome)
        return outcome
    
    def _parse_accelerator_key(self, label: str) -> str:
        """Parse accelerator key from label like '[Y] Yes' or 'Y) Yes'."""
        import re
        
        # Pattern: [K] Label
        match = re.match(r'^\[([A-Za-z0-9])\]\s*(.+)$', label)
        if match:
            return match.group(1).upper()
        
        # Pattern: K) Label
        match = re.match(r'^([A-Za-z0-9])\)\s*(.+)$', label)
        if match:
            return match.group(1).upper()
        
        # Pattern: K - Label
        match = re.match(r'^([A-Za-z0-9])\s*-\s*(.+)$', label)
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
            "failure_reason": outcome.failure_reason
        }
        
        with open(stage_dir / "status.json", 'w') as f:
            json.dump(status_data, f, indent=2)
