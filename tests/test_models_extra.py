"""
Additional tests for models and utilities.
"""

from pathlib import Path

import pytest

from attractor.models import Checkpoint, Context, Node, parse_duration


def test_node_retry_targets_timeout_and_allow_partial():
    node = Node(
        id="task",
        attrs={
            "retry_target": "retry_node",
            "fallback_retry_target": "fallback_node",
            "timeout": "1.5s",
            "allow_partial": "true",
        },
    )

    assert node.retry_target == "retry_node"
    assert node.fallback_retry_target == "fallback_node"
    assert node.timeout == pytest.approx(1.5)
    assert node.allow_partial is True

    empty_node = Node(id="empty", attrs={})
    assert empty_node.timeout is None
    assert empty_node.allow_partial is False


def test_context_string_clone_and_updates():
    context = Context()

    assert context.get_string("missing", "fallback") == "fallback"

    context.set("count", 123)
    assert context.get_string("count") == "123"

    context.append_log("entry-1")
    clone = context.clone()
    clone.set("count", 999)

    assert context.get("count") == 123
    assert clone.get("count") == 999
    assert clone.logs == ["entry-1"]

    context.apply_updates({"new": "value"})
    assert context.get("new") == "value"


def test_checkpoint_load_round_trip(tmp_path: Path):
    checkpoint = Checkpoint(
        timestamp="2026-02-08T00:00:00",
        current_node="task",
        completed_nodes=["start", "task"],
        node_retries={"task": 1},
        context_values={"key": "value"},
        logs=["log-1"],
    )

    path = tmp_path / "checkpoint.json"
    checkpoint.save(str(path))

    loaded = Checkpoint.load(str(path))
    assert loaded.current_node == "task"
    assert loaded.node_retries == {"task": 1}
    assert loaded.context_values["key"] == "value"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1500ms", 1.5),
        ("2s", 2.0),
        ("3m", 180.0),
        ("1h", 3600.0),
        ("1d", 86400.0),
        ("4.2", 4.2),
    ],
)
def test_parse_duration_units(value: str, expected: float):
    assert parse_duration(value) == pytest.approx(expected)
