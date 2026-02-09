"""
Integration test based on the specification's Definition of Done (Section 11.13).
"""

import json
import tempfile
from pathlib import Path

from attractor.engine import run_pipeline
from attractor.models import Context, StageStatus
from attractor.parser import parse_dot_string
from attractor.validation import Severity, validate


def test_integration_smoke_test():
    """End-to-end smoke test from the specification."""

    # Test pipeline: plan -> implement -> review -> done
    dot = """
    digraph test_pipeline {
        graph [goal="Create a hello world Python script"]

        start       [shape=Mdiamond]
        plan        [shape=box, prompt="Plan how to create a hello world script for: $goal"]
        implement   [shape=box, prompt="Write the code based on the plan", goal_gate=true]
        review      [shape=box, prompt="Review the code for correctness"]
        done        [shape=Msquare]

        start -> plan
        plan -> implement
        implement -> review [condition="outcome=success"]
        implement -> plan   [condition="outcome=fail", label="Retry"]
        review -> done      [condition="outcome=success"]
        review -> implement [condition="outcome=fail", label="Fix"]
    }
    """

    # 1. Parse
    graph = parse_dot_string(dot)
    assert graph.goal == "Create a hello world Python script"
    assert len(graph.nodes) == 5
    # Count total edges
    assert len(graph.edges) == 6

    # 2. Validate
    lint_results = validate(graph)
    errors = [d for d in lint_results if d.severity == Severity.ERROR]
    assert len(errors) == 0, f"Validation failed with errors: {errors}"

    # 3. Execute with simulation backend
    context = Context()

    with tempfile.TemporaryDirectory() as tmpdir:
        outcome = run_pipeline(graph, context, logs_root=tmpdir)

        # 4. Verify
        assert outcome.status == StageStatus.SUCCESS

        # Check completed nodes (start doesn't create a directory in simulation)
        logs_path = Path(tmpdir)

        # Verify artifacts exist
        assert (logs_path / "plan" / "prompt.md").exists()
        assert (logs_path / "plan" / "response.md").exists()
        assert (logs_path / "plan" / "status.json").exists()

        assert (logs_path / "implement" / "prompt.md").exists()
        assert (logs_path / "implement" / "response.md").exists()
        assert (logs_path / "implement" / "status.json").exists()

        assert (logs_path / "review" / "prompt.md").exists()
        assert (logs_path / "review" / "response.md").exists()
        assert (logs_path / "review" / "status.json").exists()

        # 5. Verify goal gate
        # implement has goal_gate=true and should have succeeded
        implement_status_path = logs_path / "implement" / "status.json"
        with open(implement_status_path) as f:
            implement_status = json.load(f)
        assert implement_status["outcome"] in ["success", "partial_success"]

        # 6. Verify checkpoint
        checkpoint_path = logs_path / "checkpoint.json"
        assert checkpoint_path.exists()

        with open(checkpoint_path) as f:
            checkpoint = json.load(f)

        # The checkpoint records the last node that completed execution
        # In this case, 'review' is the last node before exit
        assert checkpoint["current_node"] in ["review", "done"]

        # Check that key nodes were completed
        assert "plan" in checkpoint["completed_nodes"]
        assert "implement" in checkpoint["completed_nodes"]
        assert "review" in checkpoint["completed_nodes"]

        # 7. Verify prompt variable expansion
        plan_prompt_path = logs_path / "plan" / "prompt.md"
        with open(plan_prompt_path) as f:
            plan_prompt = f.read()

        # $goal should have been expanded
        assert "Create a hello world Python script" in plan_prompt
        assert "$goal" not in plan_prompt


def test_definition_of_done_checklist():
    """Verify key items from the Definition of Done checklist."""

    # Test: Parse a simple linear pipeline (start -> A -> B -> done)
    dot1 = """
    digraph Test {
        start [shape=Mdiamond]
        A [label="Task A"]
        B [label="Task B"]
        done [shape=Msquare]
        start -> A -> B -> done
    }
    """
    graph1 = parse_dot_string(dot1)
    assert len(graph1.nodes) == 4
    assert len(graph1.edges) == 3

    # Test: Parse a pipeline with graph-level attributes (goal, label)
    dot2 = """
    digraph Test {
        graph [goal="Test goal", label="Test label"]
        start [shape=Mdiamond]
        done [shape=Msquare]
        start -> done
    }
    """
    graph2 = parse_dot_string(dot2)
    assert graph2.goal == "Test goal"
    assert graph2.label == "Test label"

    # Test: Validate - missing start node -> error
    dot3 = """
    digraph Test {
        done [shape=Msquare]
    }
    """
    graph3 = parse_dot_string(dot3)
    diagnostics3 = validate(graph3)
    errors3 = [d for d in diagnostics3 if d.severity == Severity.ERROR and d.rule == "start_node"]
    assert len(errors3) == 1

    # Test: Validate - missing exit node -> error
    dot4 = """
    digraph Test {
        start [shape=Mdiamond]
    }
    """
    graph4 = parse_dot_string(dot4)
    diagnostics4 = validate(graph4)
    errors4 = [d for d in diagnostics4 if d.severity == Severity.ERROR and d.rule == "terminal_node"]
    assert len(errors4) == 1

    # Test: Execute a linear 3-node pipeline end-to-end
    dot5 = """
    digraph Test {
        start [shape=Mdiamond]
        A [label="Task A"]
        B [label="Task B"]
        C [label="Task C"]
        done [shape=Msquare]
        start -> A -> B -> C -> done
    }
    """
    graph5 = parse_dot_string(dot5)
    with tempfile.TemporaryDirectory() as tmpdir:
        outcome5 = run_pipeline(graph5, logs_root=tmpdir)
        assert outcome5.status == StageStatus.SUCCESS

        # Verify all tasks completed
        assert (Path(tmpdir) / "A" / "status.json").exists()
        assert (Path(tmpdir) / "B" / "status.json").exists()
        assert (Path(tmpdir) / "C" / "status.json").exists()

    # Test: Execute with conditional branching (success/fail paths)
    dot6 = """
    digraph Test {
        start [shape=Mdiamond]
        check [shape=diamond]
        success_path [label="Success"]
        done [shape=Msquare]

        start -> check
        check -> success_path [condition="outcome=success"]
        check -> done [condition="outcome=fail"]
        success_path -> done
    }
    """
    graph6 = parse_dot_string(dot6)
    with tempfile.TemporaryDirectory() as tmpdir:
        outcome6 = run_pipeline(graph6, logs_root=tmpdir)
        assert outcome6.status == StageStatus.SUCCESS

        # Since conditional returns SUCCESS, should take success path
        assert (Path(tmpdir) / "success_path" / "status.json").exists()

    # Test: Context updates from one node are visible to the next
    dot7 = """
    digraph Test {
        start [shape=Mdiamond]
        task [label="Task"]
        done [shape=Msquare]
        start -> task -> done
    }
    """
    graph7 = parse_dot_string(dot7)
    context7 = Context()
    with tempfile.TemporaryDirectory() as tmpdir:
        run_pipeline(graph7, context=context7, logs_root=tmpdir)
        # Verify context was updated
        assert context7.get("last_stage") == "task"
        assert context7.get("outcome") is not None
