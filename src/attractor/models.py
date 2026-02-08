"""
Core data models for Attractor.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from threading import RLock
import json
import copy


class StageStatus(Enum):
    """Status of a stage execution."""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    RETRY = "retry"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass
class Outcome:
    """Result of executing a node handler."""
    status: StageStatus
    preferred_label: str = ""
    suggested_next_ids: List[str] = field(default_factory=list)
    context_updates: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    failure_reason: str = ""


@dataclass
class Node:
    """A node in the pipeline graph."""
    id: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def label(self) -> str:
        return self.attrs.get("label", self.id)
    
    @property
    def shape(self) -> str:
        return self.attrs.get("shape", "box")
    
    @property
    def type(self) -> str:
        return self.attrs.get("type", "")
    
    @property
    def prompt(self) -> str:
        return self.attrs.get("prompt", "")
    
    @property
    def max_retries(self) -> int:
        return int(self.attrs.get("max_retries", 0))
    
    @property
    def goal_gate(self) -> bool:
        return self.attrs.get("goal_gate", False) in [True, "true", "True"]
    
    @property
    def retry_target(self) -> str:
        return self.attrs.get("retry_target", "")
    
    @property
    def fallback_retry_target(self) -> str:
        return self.attrs.get("fallback_retry_target", "")
    
    @property
    def timeout(self) -> Optional[float]:
        """Timeout in seconds, or None if not set."""
        timeout_val = self.attrs.get("timeout")
        if timeout_val:
            return parse_duration(str(timeout_val))
        return None
    
    @property
    def allow_partial(self) -> bool:
        return self.attrs.get("allow_partial", False) in [True, "true", "True"]


@dataclass
class Edge:
    """An edge in the pipeline graph."""
    from_node: str
    to_node: str
    attrs: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def label(self) -> str:
        return self.attrs.get("label", "")
    
    @property
    def condition(self) -> str:
        return self.attrs.get("condition", "")
    
    @property
    def weight(self) -> int:
        return int(self.attrs.get("weight", 0))


@dataclass
class Graph:
    """A pipeline graph."""
    name: str
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: List[Edge] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def goal(self) -> str:
        return self.attrs.get("goal", "")
    
    @property
    def label(self) -> str:
        return self.attrs.get("label", "")
    
    @property
    def model_stylesheet(self) -> str:
        return self.attrs.get("model_stylesheet", "")
    
    @property
    def default_max_retry(self) -> int:
        return int(self.attrs.get("default_max_retry", 50))
    
    @property
    def retry_target(self) -> str:
        return self.attrs.get("retry_target", "")
    
    @property
    def fallback_retry_target(self) -> str:
        return self.attrs.get("fallback_retry_target", "")
    
    def outgoing_edges(self, node_id: str) -> List[Edge]:
        """Get all edges leaving a node."""
        return [e for e in self.edges if e.from_node == node_id]
    
    def incoming_edges(self, node_id: str) -> List[Edge]:
        """Get all edges entering a node."""
        return [e for e in self.edges if e.to_node == node_id]


class Context:
    """Thread-safe key-value store for pipeline state."""
    
    def __init__(self):
        self.values: Dict[str, Any] = {}
        self.logs: List[str] = []
        self.lock = RLock()
    
    def set(self, key: str, value: Any):
        """Set a context value."""
        with self.lock:
            self.values[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        with self.lock:
            return self.values.get(key, default)
    
    def get_string(self, key: str, default: str = "") -> str:
        """Get a context value as a string."""
        value = self.get(key)
        if value is None:
            return default
        return str(value)
    
    def append_log(self, entry: str):
        """Append to the run log."""
        with self.lock:
            self.logs.append(entry)
    
    def snapshot(self) -> Dict[str, Any]:
        """Get a serializable snapshot of all values."""
        with self.lock:
            return copy.copy(self.values)
    
    def clone(self) -> 'Context':
        """Create a deep copy for parallel branch isolation."""
        with self.lock:
            new_context = Context()
            new_context.values = copy.copy(self.values)
            new_context.logs = copy.copy(self.logs)
            return new_context
    
    def apply_updates(self, updates: Dict[str, Any]):
        """Merge updates into the context."""
        with self.lock:
            for key, value in updates.items():
                self.values[key] = value


@dataclass
class Checkpoint:
    """Serializable snapshot of execution state."""
    timestamp: str
    current_node: str
    completed_nodes: List[str]
    node_retries: Dict[str, int]
    context_values: Dict[str, Any]
    logs: List[str]
    
    def save(self, path: str):
        """Serialize to JSON and write to filesystem."""
        data = {
            "timestamp": self.timestamp,
            "current_node": self.current_node,
            "completed_nodes": self.completed_nodes,
            "node_retries": self.node_retries,
            "context": self.context_values,
            "logs": self.logs
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> 'Checkpoint':
        """Deserialize from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(
            timestamp=data["timestamp"],
            current_node=data["current_node"],
            completed_nodes=data["completed_nodes"],
            node_retries=data["node_retries"],
            context_values=data["context"],
            logs=data["logs"]
        )


def parse_duration(duration_str: str) -> float:
    """Parse a duration string like '900s', '15m', '2h' to seconds."""
    duration_str = duration_str.strip()
    
    if duration_str.endswith('ms'):
        return float(duration_str[:-2]) / 1000
    elif duration_str.endswith('s'):
        return float(duration_str[:-1])
    elif duration_str.endswith('m'):
        return float(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return float(duration_str[:-1]) * 3600
    elif duration_str.endswith('d'):
        return float(duration_str[:-1]) * 86400
    else:
        # Try to parse as a plain number (assume seconds)
        return float(duration_str)
