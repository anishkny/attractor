"""
Condition expression evaluation for edge routing.
"""

from typing import Any
from .models import Outcome, Context


def evaluate_condition(condition: str, outcome: Outcome, context: Context) -> bool:
    """Evaluate a condition expression against outcome and context."""
    if not condition or condition.strip() == "":
        return True  # Empty condition = always eligible
    
    # Split by && for AND clauses
    clauses = condition.split("&&")
    
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        
        if not evaluate_clause(clause, outcome, context):
            return False
    
    return True


def evaluate_clause(clause: str, outcome: Outcome, context: Context) -> bool:
    """Evaluate a single condition clause."""
    # Check for != operator
    if "!=" in clause:
        parts = clause.split("!=", 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            return resolve_key(key, outcome, context) != value
    
    # Check for = operator
    if "=" in clause:
        parts = clause.split("=", 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            return resolve_key(key, outcome, context) == value
    
    # Bare key: check if truthy
    return bool(resolve_key(clause.strip(), outcome, context))


def resolve_key(key: str, outcome: Outcome, context: Context) -> str:
    """Resolve a key to its value from outcome or context."""
    if key == "outcome":
        return outcome.status.value
    
    if key == "preferred_label":
        return outcome.preferred_label
    
    # Try context with and without "context." prefix
    if key.startswith("context."):
        # Try with prefix
        value = context.get(key)
        if value is not None:
            return str(value)
        
        # Try without prefix
        key_without_prefix = key[8:]  # Remove "context."
        value = context.get(key_without_prefix)
        if value is not None:
            return str(value)
        
        return ""
    
    # Direct context lookup
    value = context.get(key)
    if value is not None:
        return str(value)
    
    return ""
