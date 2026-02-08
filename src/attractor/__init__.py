"""
Attractor: A DOT-based pipeline runner for AI workflows.
"""

__version__ = "0.1.0"

from .parser import parse_dot, parse_dot_string
from .models import Graph, Node, Edge, Context, Outcome, StageStatus
from .engine import run_pipeline
from .handlers import HandlerRegistry, CodergenBackend

__all__ = [
    "parse_dot",
    "parse_dot_string",
    "Graph",
    "Node",
    "Edge",
    "Context",
    "Outcome",
    "StageStatus",
    "run_pipeline",
    "HandlerRegistry",
    "CodergenBackend",
]
