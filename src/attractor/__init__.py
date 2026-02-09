"""
Attractor: A DOT-based pipeline runner for AI workflows.
"""

__version__ = "0.1.0"

from .engine import run_pipeline
from .events import Event, EventEmitter, EventType
from .handlers import CodergenBackend, HandlerRegistry
from .models import Context, Edge, Graph, Node, Outcome, StageStatus
from .parser import parse_dot, parse_dot_string

__all__ = [
    "CodergenBackend",
    "Context",
    "Edge",
    "Event",
    "EventEmitter",
    "EventType",
    "Graph",
    "HandlerRegistry",
    "Node",
    "Outcome",
    "StageStatus",
    "parse_dot",
    "parse_dot_string",
    "run_pipeline",
]
