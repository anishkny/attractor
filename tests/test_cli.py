"""
Tests for CLI entry points.
"""

import sys
from pathlib import Path

import pytest
import runpy

from attractor import cli
from attractor.models import Graph, Node, Outcome, StageStatus
from attractor.validation import Diagnostic, Severity


def _basic_graph() -> Graph:
    nodes = {
        "start": Node(id="start", attrs={"shape": "Mdiamond"}),
        "exit": Node(id="exit", attrs={"shape": "Msquare"}),
    }
    return Graph(name="g", nodes=nodes, edges=[], attrs={"goal": "g"})


def test_cli_missing_file(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "missing.dot"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1


def test_cli_validate_only_with_errors(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path), "--validate-only"])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: graph)

    diagnostics = [
        Diagnostic(
            rule="start_node",
            severity=Severity.ERROR,
            message="error",
        )
    ]
    import attractor.validation as validation

    monkeypatch.setattr(validation, "validate", lambda _g: diagnostics)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1


def test_cli_validate_only_with_warnings(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path), "--validate-only"])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: graph)

    diagnostics = [
        Diagnostic(
            rule="warn",
            severity=Severity.WARNING,
            message="warning",
        )
    ]
    import attractor.validation as validation

    monkeypatch.setattr(validation, "validate", lambda _g: diagnostics)

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0


def test_cli_validate_only_no_diagnostics(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path), "--validate-only"])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: graph)

    import attractor.validation as validation

    monkeypatch.setattr(validation, "validate", lambda _g: [])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0


def test_cli_execute_success(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path)])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: graph)
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda _g, context=None, logs_root=None: Outcome(
            status=StageStatus.SUCCESS
        ),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0


def test_cli_execute_success_with_notes(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path)])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: graph)
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda _g, context=None, logs_root=None: Outcome(
            status=StageStatus.SUCCESS,
            notes="extra",
        ),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0


def test_cli_execute_failure(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path)])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: graph)
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda _g, context=None, logs_root=None: Outcome(
            status=StageStatus.FAIL, failure_reason="boom"
        ),
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1


def test_cli_exception_handler(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path)])
    monkeypatch.setattr(cli, "parse_dot", lambda _p: (_ for _ in ()).throw(ValueError("boom")))

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1


def test_cli_main_guard(monkeypatch, tmp_path: Path):
    dot_path = tmp_path / "pipeline.dot"
    dot_path.write_text("digraph g { start [shape=Mdiamond]; exit [shape=Msquare]; }")

    graph = _basic_graph()

    monkeypatch.setattr(sys, "argv", ["prog", str(dot_path)])
    import attractor.parser as parser
    import attractor.engine as engine

    monkeypatch.setattr(parser, "parse_dot", lambda _p: graph)
    monkeypatch.setattr(
        engine,
        "run_pipeline",
        lambda _g, context=None, logs_root=None: Outcome(
            status=StageStatus.SUCCESS
        ),
    )

    sys.modules.pop("attractor.cli", None)

    with pytest.raises(SystemExit):
        runpy.run_module("attractor.cli", run_name="__main__")
