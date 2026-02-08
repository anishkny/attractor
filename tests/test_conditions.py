"""
Tests for condition evaluation.
"""

import pytest
from attractor.conditions import evaluate_condition, evaluate_clause, resolve_key
from attractor.models import Outcome, StageStatus, Context


def test_empty_condition():
    """Test that empty condition always evaluates to true."""
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()
    
    assert evaluate_condition("", outcome, context) == True
    assert evaluate_condition("  ", outcome, context) == True


def test_equals_operator():
    """Test equals operator."""
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()
    
    assert evaluate_condition("outcome=success", outcome, context) == True
    assert evaluate_condition("outcome=fail", outcome, context) == False


def test_not_equals_operator():
    """Test not-equals operator."""
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()
    
    assert evaluate_condition("outcome!=fail", outcome, context) == True
    assert evaluate_condition("outcome!=success", outcome, context) == False


def test_and_operator():
    """Test AND (&&) operator."""
    outcome = Outcome(status=StageStatus.SUCCESS, preferred_label="approve")
    context = Context()
    
    assert evaluate_condition("outcome=success && preferred_label=approve", outcome, context) == True
    assert evaluate_condition("outcome=success && preferred_label=reject", outcome, context) == False


def test_context_variable():
    """Test context variable resolution."""
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()
    context.set("tests_passed", "true")
    
    assert evaluate_condition("context.tests_passed=true", outcome, context) == True
    assert evaluate_condition("tests_passed=true", outcome, context) == True
    assert evaluate_condition("context.tests_passed=false", outcome, context) == False


def test_preferred_label():
    """Test preferred_label resolution."""
    outcome = Outcome(status=StageStatus.SUCCESS, preferred_label="next")
    context = Context()
    
    assert evaluate_condition("preferred_label=next", outcome, context) == True
    assert evaluate_condition("preferred_label=other", outcome, context) == False


def test_missing_context_key():
    """Test that missing context keys resolve to empty string."""
    outcome = Outcome(status=StageStatus.SUCCESS)
    context = Context()
    
    # Missing key should not equal non-empty value
    assert evaluate_condition("context.missing=value", outcome, context) == False
    
    # Missing key should equal empty string
    assert evaluate_condition("context.missing=", outcome, context) == True
