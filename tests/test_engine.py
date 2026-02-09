"""
Tests for the execution engine.
"""

import tempfile
from pathlib import Path

from attractor.engine import run_pipeline
from attractor.models import Context, StageStatus
from attractor.parser import parse_dot_string


def test_simple_linear_execution():
    """Test execution of a simple linear pipeline."""
    dot = """
    digraph Simple {
        graph [goal="Run tests"]

        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task1 [label="Task 1", prompt="Do task 1"]
        task2 [label="Task 2", prompt="Do task 2"]

        start -> task1 -> task2 -> exit
    }
    """

    graph = parse_dot_string(dot)

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = run_pipeline(graph, logs_root=tmpdir)

        assert outcome.status == StageStatus.SUCCESS

        # Check that stage directories were created
        assert (Path(tmpdir) / "task1").exists()
        assert (Path(tmpdir) / "task2").exists()
        assert (Path(tmpdir) / "task1" / "prompt.md").exists()
        assert (Path(tmpdir) / "task1" / "response.md").exists()


def test_conditional_routing():
    """Test conditional edge routing."""
    dot = """
    digraph Branch {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        check [shape=diamond, label="Check"]
        success_path [label="Success"]

        start -> check
        check -> success_path [condition="outcome=success"]
        check -> exit [condition="outcome=fail"]
        success_path -> exit
    }
    """

    graph = parse_dot_string(dot)

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = run_pipeline(graph, logs_root=tmpdir)

        # Since conditional handler returns SUCCESS, should go to success_path
        assert outcome.status == StageStatus.SUCCESS
        assert (Path(tmpdir) / "success_path").exists()


def test_context_updates():
    """Test that context updates are applied."""
    dot = """
    digraph Context {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task  [label="Task"]

        start -> task -> exit
    }
    """

    graph = parse_dot_string(dot)
    context = Context()

    with tempfile.TemporaryDirectory() as tmpdir:
        run_pipeline(graph, context=context, logs_root=tmpdir)

        # Check that context was updated
        assert context.get("last_stage") == "task"
        assert context.get("graph.goal") == ""


def test_checkpoint_saved():
    """Test that checkpoints are saved."""
    dot = """
    digraph Checkpoint {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        task  [label="Task"]

        start -> task -> exit
    }
    """

    graph = parse_dot_string(dot)

    with tempfile.TemporaryDirectory() as tmpdir:
        run_pipeline(graph, logs_root=tmpdir)

        # Check that checkpoint exists
        checkpoint_path = Path(tmpdir) / "checkpoint.json"
        assert checkpoint_path.exists()

        # Load and verify checkpoint
        import json
        with open(checkpoint_path) as f:
            checkpoint_data = json.load(f)

        assert "task" in checkpoint_data["completed_nodes"]


def test_goal_gate_enforcement():
    """Test that goal gates are enforced."""
    dot = """
    digraph GoalGate {
        start [shape=Mdiamond]
        exit  [shape=Msquare]
        critical [label="Critical", goal_gate=true]
        optional [label="Optional"]

        start -> critical -> optional -> exit
    }
    """

    graph = parse_dot_string(dot)

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = run_pipeline(graph, logs_root=tmpdir)

        # Since critical has goal_gate=true and succeeds, pipeline should complete
        assert outcome.status == StageStatus.SUCCESS
