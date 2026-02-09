"""
Additional tests for engine internals.
"""

import random
from pathlib import Path

import pytest

import attractor.engine as engine_module
from attractor.engine import PipelineEngine, RetryPolicy
from attractor.handlers import Handler, HandlerRegistry
from attractor.models import Context, Edge, Graph, Node, Outcome, StageStatus


class SequenceHandler(Handler):
    def __init__(self, outcomes=None, exceptions=None):
        self.outcomes = outcomes or []
        self.exceptions = exceptions or []
        self.calls = 0

    def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        if self.calls < len(self.exceptions) and self.exceptions[self.calls] is not None:
            exc = self.exceptions[self.calls]
            self.calls += 1
            raise exc

        if self.calls < len(self.outcomes):
            outcome = self.outcomes[self.calls]
        else:
            outcome = self.outcomes[-1]

        self.calls += 1
        return outcome


def _build_graph() -> Graph:
    nodes = {
        "start": Node(id="start", attrs={"shape": "Mdiamond"}),
        "task": Node(id="task", attrs={"shape": "box"}),
        "exit": Node(id="exit", attrs={"shape": "Msquare"}),
    }
    edges = [
        Edge(from_node="start", to_node="task", attrs={}),
        Edge(from_node="task", to_node="exit", attrs={}),
    ]
    return Graph(name="g", nodes=nodes, edges=edges, attrs={})


def test_retry_policy_delay_jitter(monkeypatch):
    monkeypatch.setattr(random, "uniform", lambda _a, _b: 1.0)
    policy = RetryPolicy(
        max_attempts=3,
        initial_delay_ms=100,
        backoff_factor=2.0,
        max_delay_ms=1000,
        jitter=True,
    )
    assert policy.delay_for_attempt(2) == pytest.approx(0.2)

    policy_no_jitter = RetryPolicy(
        max_attempts=1,
        initial_delay_ms=100,
        backoff_factor=2.0,
        max_delay_ms=1000,
        jitter=False,
    )
    assert policy_no_jitter.delay_for_attempt(1) == pytest.approx(0.1)


def test_create_logs_root_creates_dir(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    graph = _build_graph()
    engine = PipelineEngine(graph, logs_root=None)
    assert Path(engine.logs_root).exists()


def test_find_start_node_missing(monkeypatch, tmp_path: Path):
    graph = Graph(name="no_start", nodes={"task": Node(id="task", attrs={})})
    monkeypatch.setattr(engine_module, "validate_or_raise", lambda *_a, **_k: [])

    engine = PipelineEngine(graph, logs_root=str(tmp_path))
    with pytest.raises(ValueError, match="No start node"):
        engine._find_start_node()


def test_get_retry_target_resolution(tmp_path: Path):
    graph = _build_graph()
    graph.attrs.update({"retry_target": "g_retry", "fallback_retry_target": "g_fallback"})

    engine = PipelineEngine(graph, logs_root=str(tmp_path))

    node = Node(id="task", attrs={"retry_target": "n_retry"})
    assert engine._get_retry_target(node) == "n_retry"

    node = Node(id="task", attrs={"fallback_retry_target": "n_fallback"})
    assert engine._get_retry_target(node) == "n_fallback"

    node = Node(id="task", attrs={})
    assert engine._get_retry_target(node) == "g_retry"

    graph.attrs["retry_target"] = ""
    assert engine._get_retry_target(node) == "g_fallback"

    graph.attrs["fallback_retry_target"] = ""
    assert engine._get_retry_target(node) is None


def test_check_goal_gates(tmp_path: Path):
    graph = _build_graph()
    graph.nodes["task"].attrs["goal_gate"] = True
    engine = PipelineEngine(graph, logs_root=str(tmp_path))

    ok, failed = engine._check_goal_gates({"task": Outcome(status=StageStatus.FAIL)})
    assert ok is False
    assert failed == graph.nodes["task"]

    ok, failed = engine._check_goal_gates(
        {"task": Outcome(status=StageStatus.SUCCESS)}
    )
    assert ok is True
    assert failed is None


def test_select_edge_priority_and_normalization(monkeypatch, tmp_path: Path):
    graph = _build_graph()
    graph.edges = [
        Edge(
            from_node="task",
            to_node="a",
            attrs={"condition": "outcome=success", "weight": 1},
        ),
        Edge(from_node="task", to_node="b", attrs={"label": "[Y] Yes"}),
        Edge(from_node="task", to_node="c", attrs={"weight": 5}),
    ]

    monkeypatch.setattr(engine_module, "validate_or_raise", lambda *_a, **_k: [])
    engine = PipelineEngine(graph, logs_root=str(tmp_path))
    context = Context()

    outcome = Outcome(status=StageStatus.SUCCESS)
    assert engine._select_edge(graph.nodes["task"], outcome, context).to_node == "a"

    outcome = Outcome(status=StageStatus.FAIL, preferred_label="Yes")
    assert engine._select_edge(graph.nodes["task"], outcome, context).to_node == "b"

    outcome = Outcome(status=StageStatus.FAIL, suggested_next_ids=["c"])
    assert engine._select_edge(graph.nodes["task"], outcome, context).to_node == "c"

    assert engine._normalize_label("[Y] Yes") == "yes"

    best = engine._best_by_weight_then_lexical(
        [
            Edge(from_node="task", to_node="b", attrs={"weight": 1}),
            Edge(from_node="task", to_node="a", attrs={"weight": 1}),
        ]
    )
    assert best.to_node == "a"
    assert engine._best_by_weight_then_lexical([]) is None


def test_execute_with_retry_exception_then_success(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    graph = _build_graph()
    registry = HandlerRegistry()
    handler = SequenceHandler(
        outcomes=[Outcome(status=StageStatus.SUCCESS)],
        exceptions=[RuntimeError("boom")],
    )
    registry.register("custom", handler)
    graph.nodes["task"].attrs["type"] = "custom"

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))

    policy = RetryPolicy(max_attempts=2, jitter=False)
    outcome = engine._execute_with_retry(
        graph.nodes["task"], Context(), policy, {}, 0
    )

    assert outcome.status == StageStatus.SUCCESS
    assert handler.calls == 2


def test_execute_with_retry_exception_final_attempt(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    graph = _build_graph()
    registry = HandlerRegistry()
    handler = SequenceHandler(exceptions=[RuntimeError("boom")])
    registry.register("custom", handler)
    graph.nodes["task"].attrs["type"] = "custom"

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))

    policy = RetryPolicy(max_attempts=1, jitter=False)
    outcome = engine._execute_with_retry(
        graph.nodes["task"], Context(), policy, {}, 0
    )

    assert outcome.status == StageStatus.FAIL
    assert "Exception: boom" in outcome.failure_reason


def test_execute_with_retry_retries_and_partial(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    graph = _build_graph()
    registry = HandlerRegistry()

    handler_retry_then_success = SequenceHandler(
        outcomes=[
            Outcome(status=StageStatus.RETRY),
            Outcome(status=StageStatus.SUCCESS),
        ]
    )
    registry.register("custom", handler_retry_then_success)
    graph.nodes["task"].attrs["type"] = "custom"

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))

    policy = RetryPolicy(max_attempts=2, jitter=False)
    node_retries = {}
    outcome = engine._execute_with_retry(
        graph.nodes["task"], Context(), policy, node_retries, 0
    )

    assert outcome.status == StageStatus.SUCCESS
    assert graph.nodes["task"].id not in node_retries

    handler_retry_exhausted = SequenceHandler(outcomes=[Outcome(status=StageStatus.RETRY)])
    registry.register("custom2", handler_retry_exhausted)

    node_partial = Node(
        id="partial",
        attrs={"type": "custom2", "allow_partial": True},
    )

    outcome = engine._execute_with_retry(
        node_partial,
        Context(),
        RetryPolicy(max_attempts=1, jitter=False),
        {},
        1,
    )

    assert outcome.status == StageStatus.PARTIAL_SUCCESS


def test_execute_with_retry_fail_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    graph = _build_graph()
    registry = HandlerRegistry()

    handler_retry_exhausted = SequenceHandler(outcomes=[Outcome(status=StageStatus.RETRY)])
    handler_fail = SequenceHandler(
        outcomes=[Outcome(status=StageStatus.FAIL, failure_reason="bad")]
    )

    registry.register("retry", handler_retry_exhausted)
    registry.register("fail", handler_fail)

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))

    node_retry = Node(id="retry", attrs={"type": "retry"})
    outcome = engine._execute_with_retry(
        node_retry, Context(), RetryPolicy(max_attempts=1, jitter=False), {}, 0
    )
    assert outcome.status == StageStatus.FAIL


def test_execute_with_retry_zero_attempts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    graph = _build_graph()
    registry = HandlerRegistry()
    handler = SequenceHandler(outcomes=[Outcome(status=StageStatus.SUCCESS)])
    registry.register("custom", handler)
    graph.nodes["task"].attrs["type"] = "custom"

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))

    policy = RetryPolicy(max_attempts=1, jitter=False)
    policy.max_attempts = 0

    outcome = engine._execute_with_retry(
        graph.nodes["task"], Context(), policy, {}, 0
    )

    assert outcome.status == StageStatus.FAIL

    node_fail = Node(id="fail", attrs={"type": "fail"})
    outcome = engine._execute_with_retry(
        node_fail, Context(), RetryPolicy(max_attempts=1, jitter=False), {}, 0
    )
    assert outcome.status == StageStatus.FAIL


def test_run_goal_gate_failure(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    nodes = {
        "start": Node(id="start", attrs={"shape": "Mdiamond"}),
        "gate": Node(id="gate", attrs={"goal_gate": True, "type": "custom"}),
        "exit": Node(id="exit", attrs={"shape": "Msquare"}),
    }
    edges = [
        Edge(from_node="start", to_node="gate", attrs={}),
        Edge(from_node="gate", to_node="exit", attrs={}),
    ]
    graph = Graph(name="g", nodes=nodes, edges=edges, attrs={})

    registry = HandlerRegistry()
    registry.register(
        "custom", SequenceHandler(outcomes=[Outcome(status=StageStatus.FAIL)])
    )

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))
    outcome = engine.run(Context())

    assert outcome.status == StageStatus.FAIL
    assert "Goal gate" in outcome.failure_reason


def test_run_goal_gate_retry_target(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    nodes = {
        "start": Node(id="start", attrs={"shape": "Mdiamond"}),
        "gate": Node(
            id="gate",
            attrs={"goal_gate": True, "type": "custom", "retry_target": "gate"},
        ),
        "exit": Node(id="exit", attrs={"shape": "Msquare"}),
    }
    edges = [
        Edge(from_node="start", to_node="gate", attrs={}),
        Edge(from_node="gate", to_node="exit", attrs={}),
    ]
    graph = Graph(name="g", nodes=nodes, edges=edges, attrs={})

    registry = HandlerRegistry()
    registry.register(
        "custom",
        SequenceHandler(
            outcomes=[Outcome(status=StageStatus.FAIL), Outcome(status=StageStatus.SUCCESS)]
        ),
    )

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))
    outcome = engine.run(Context())

    assert outcome.status == StageStatus.SUCCESS


def test_run_sets_preferred_label(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    graph = _build_graph()
    registry = HandlerRegistry()
    registry.register(
        "custom",
        SequenceHandler(outcomes=[Outcome(status=StageStatus.SUCCESS, preferred_label="Next")]),
    )
    graph.nodes["task"].attrs["type"] = "custom"

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))
    context = Context()
    engine.run(context)

    assert context.get("preferred_label") == "Next"


def test_run_fail_with_no_outgoing_edge(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _s: None)

    nodes = {
        "start": Node(id="start", attrs={"shape": "Mdiamond"}),
        "task": Node(id="task", attrs={"type": "custom"}),
        "exit": Node(id="exit", attrs={"shape": "Msquare"}),
    }
    edges = [
        Edge(from_node="start", to_node="task", attrs={}),
        Edge(from_node="task", to_node="exit", attrs={"condition": "outcome=success"}),
    ]
    graph = Graph(name="g", nodes=nodes, edges=edges, attrs={})

    registry = HandlerRegistry()
    registry.register(
        "custom",
        SequenceHandler(outcomes=[Outcome(status=StageStatus.FAIL, failure_reason="bad")]),
    )

    engine = PipelineEngine(graph, handler_registry=registry, logs_root=str(tmp_path))
    outcome = engine.run(Context())

    assert outcome.status == StageStatus.FAIL
    assert "no outgoing" in outcome.failure_reason.lower()


def test_run_exception_emits_failure(monkeypatch, tmp_path: Path):
    graph = _build_graph()
    engine = PipelineEngine(graph, logs_root=str(tmp_path))

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_select_edge", boom)

    with pytest.raises(RuntimeError, match="boom"):
        engine.run(Context())


def test_select_edge_no_edges_and_fallback(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(engine_module, "validate_or_raise", lambda *_a, **_k: [])

    graph = _build_graph()
    engine = PipelineEngine(graph, logs_root=str(tmp_path))
    node = graph.nodes["task"]

    graph.edges = []
    assert engine._select_edge(node, Outcome(status=StageStatus.SUCCESS), Context()) is None

    graph.edges = [
        Edge(from_node="task", to_node="a", attrs={"condition": "outcome=fail"}),
        Edge(from_node="task", to_node="b", attrs={"condition": "outcome=fail"}),
    ]
    outcome = Outcome(status=StageStatus.SUCCESS)
    assert engine._select_edge(node, outcome, Context()).to_node in ["a", "b"]
