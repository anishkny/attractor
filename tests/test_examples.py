"""
Tests for example DOT pipelines.
"""

from pathlib import Path

import pytest

from attractor.parser import parse_dot
from attractor.validation import Severity, validate

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.dot"))


def test_example_files_present():
    """Ensure example DOT files are available."""
    assert EXAMPLE_FILES, f"No example .dot files found in {EXAMPLES_DIR}"


@pytest.mark.parametrize("dot_file", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_pipelines_validate(dot_file: Path):
    """Validate each example pipeline has no errors."""
    graph = parse_dot(str(dot_file))
    diagnostics = validate(graph)
    errors = [d for d in diagnostics if d.severity == Severity.ERROR]
    assert not errors, f"Validation errors for {dot_file.name}: {errors}"
