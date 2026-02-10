"""
Additional tests for condition evaluation.
"""

from attractor.conditions import evaluate_condition
from attractor.models import Context, Outcome, StageStatus


def test_condition_with_empty_clause_and_bare_key():
    outcome = Outcome(status=StageStatus.SUCCESS, preferred_label="ok")
    context = Context()
    context.set("flag", "true")

    assert evaluate_condition("outcome=success &&  && flag", outcome, context)


def test_context_prefix_fallback_and_missing():
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()
    context.set("foo", "bar")
    context.set("context.baz", "qux")

    assert evaluate_condition("context.foo=bar", outcome, context)
    assert evaluate_condition("context.baz=qux", outcome, context)
    assert evaluate_condition("context.missing!=value", outcome, context)
    assert not evaluate_condition("context.missing=value", outcome, context)


def test_missing_bare_key_resolves_empty():
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()

    assert not evaluate_condition("missing_key", outcome, context)
