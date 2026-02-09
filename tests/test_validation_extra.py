"""
Additional tests for validation rules.
"""

import pytest

from attractor.models import Edge, Graph, Node
from attractor.validation import Diagnostic, LintRule, Severity, validate


def test_lint_rule_base_raises():
    rule = LintRule("base")
    with pytest.raises(NotImplementedError):
        rule.apply(Graph(name="g"))


def test_multiple_start_nodes_detected():
    dot = """
    digraph MultiStart {
        start [shape=Mdiamond]
        Start [shape=Mdiamond]
        exit [shape=Msquare]
        start -> exit
        Start -> exit
    }
    """

    graph = Graph(
        name="MultiStart",
        nodes={
            "start": Node(id="start", attrs={"shape": "Mdiamond"}),
            "Start": Node(id="Start", attrs={"shape": "Mdiamond"}),
            "exit": Node(id="exit", attrs={"shape": "Msquare"}),
        },
        edges=[
            Edge(from_node="start", to_node="exit", attrs={}),
            Edge(from_node="Start", to_node="exit", attrs={}),
        ],
        attrs={},
    )

    diagnostics = validate(graph)
    errors = [d for d in diagnostics if d.rule == "start_node"]
    assert len(errors) == 1
    assert errors[0].severity == Severity.ERROR


def test_edge_target_exists_rule_reports_missing_nodes():
    graph = Graph(
        name="MissingNodes",
        nodes={
            "start": Node(id="start", attrs={"shape": "Mdiamond"}),
            "exit": Node(id="exit", attrs={"shape": "Msquare"}),
        },
        edges=[
            Edge(from_node="start", to_node="missing", attrs={}),
            Edge(from_node="ghost", to_node="exit", attrs={}),
        ],
        attrs={},
    )

    diagnostics = validate(graph)
    errors = [d for d in diagnostics if d.rule == "edge_target_exists"]
    assert len(errors) == 2


def test_prompt_on_llm_nodes_warning():
    graph = Graph(
        name="PromptWarning",
        nodes={
            "node1": Node(
                id="node1",
                attrs={"shape": "box", "label": "", "prompt": ""},
            )
        },
        edges=[],
        attrs={},
    )

    diagnostics = validate(graph)
    warnings = [d for d in diagnostics if d.severity == Severity.WARNING]
    assert warnings


def test_validate_with_extra_rules():
    class ExtraRule(LintRule):
        def __init__(self):
            super().__init__("extra")

        def apply(self, graph: Graph):
            return [
                Diagnostic(
                    rule=self.name,
                    severity=Severity.INFO,
                    message="extra rule",
                )
            ]

    graph = Graph(name="g")
    diagnostics = validate(graph, extra_rules=[ExtraRule()])

    assert any(d.rule == "extra" for d in diagnostics)
