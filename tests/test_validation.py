"""
Tests for validation.
"""

import pytest

from attractor.parser import parse_dot_string
from attractor.validation import Severity, validate, validate_or_raise


def test_valid_pipeline():
    """Test that a valid pipeline passes validation."""
    dot = """
    digraph Valid {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task  [label="Do work"]

        start -> task -> exit
    }
    """

    graph = parse_dot_string(dot)
    diagnostics = validate(graph)

    errors = [d for d in diagnostics if d.severity == Severity.ERROR]
    assert len(errors) == 0


def test_missing_start_node():
    """Test that missing start node is an error."""
    dot = """
    digraph NoStart {
        exit [shape=Msquare]
        task [label="Do work"]

        task -> exit
    }
    """

    graph = parse_dot_string(dot)
    diagnostics = validate(graph)

    errors = [d for d in diagnostics if d.rule == "start_node"]
    assert len(errors) == 1
    assert errors[0].severity == Severity.ERROR


def test_missing_exit_node():
    """Test that missing exit node is an error."""
    dot = """
    digraph NoExit {
        start [shape=Mdiamond]
        task  [label="Do work"]

        start -> task
    }
    """

    graph = parse_dot_string(dot)
    diagnostics = validate(graph)

    errors = [d for d in diagnostics if d.rule == "terminal_node"]
    assert len(errors) == 1


def test_unreachable_node():
    """Test that unreachable nodes are detected."""
    dot = """
    digraph Unreachable {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task  [label="Do work"]
        orphan [label="Orphan"]

        start -> task -> exit
    }
    """

    graph = parse_dot_string(dot)
    diagnostics = validate(graph)

    errors = [d for d in diagnostics if d.rule == "reachability"]
    assert len(errors) == 1
    assert "orphan" in errors[0].message.lower()


def test_start_with_incoming_edge():
    """Test that start node with incoming edge is an error."""
    dot = """
    digraph BadStart {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task  [label="Task"]

        start -> task -> exit
        task -> start
    }
    """

    graph = parse_dot_string(dot)
    diagnostics = validate(graph)

    errors = [d for d in diagnostics if d.rule == "start_no_incoming"]
    assert len(errors) == 1


def test_exit_with_outgoing_edge():
    """Test that exit node with outgoing edge is an error."""
    dot = """
    digraph BadExit {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task  [label="Task"]

        start -> task -> exit -> task
    }
    """

    graph = parse_dot_string(dot)
    diagnostics = validate(graph)

    errors = [d for d in diagnostics if d.rule == "exit_no_outgoing"]
    assert len(errors) == 1


def test_validate_or_raise():
    """Test that validate_or_raise raises on errors."""
    dot = """
    digraph Invalid {
        task [label="Task"]
    }
    """

    graph = parse_dot_string(dot)

    with pytest.raises(ValueError, match="Validation failed"):
        validate_or_raise(graph)
