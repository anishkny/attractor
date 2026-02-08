"""
Command-line interface for Attractor.
"""

import argparse
import sys
from pathlib import Path

from .engine import run_pipeline
from .models import Context
from .parser import parse_dot


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Attractor: DOT-based pipeline runner for AI workflows"
    )

    parser.add_argument("dotfile", help="Path to the DOT pipeline file")

    parser.add_argument(
        "--logs-root",
        help="Directory for logs and artifacts (default: auto-generated)",
        default=None,
    )

    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate the pipeline without executing",
    )

    args = parser.parse_args()

    # Check if file exists
    if not Path(args.dotfile).exists():
        print(f"Error: File '{args.dotfile}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        # Parse the DOT file
        print(f"Parsing {args.dotfile}...")
        graph = parse_dot(args.dotfile)

        print(f"  Graph: {graph.name}")
        print(f"  Goal: {graph.goal}")
        print(f"  Nodes: {len(graph.nodes)}")
        print(f"  Edges: {len(graph.edges)}")

        if args.validate_only:
            from .validation import Severity, validate

            print("\nValidating pipeline...")
            diagnostics = validate(graph)

            errors = [d for d in diagnostics if d.severity == Severity.ERROR]
            warnings = [d for d in diagnostics if d.severity == Severity.WARNING]

            if errors:
                print(f"\n{len(errors)} error(s):")
                for diag in errors:
                    print(f"  [ERROR] {diag.rule}: {diag.message}")
                sys.exit(1)

            if warnings:
                print(f"\n{len(warnings)} warning(s):")
                for diag in warnings:
                    print(f"  [WARN] {diag.rule}: {diag.message}")

            if not errors and not warnings:
                print("✓ Pipeline is valid")

            sys.exit(0)

        # Execute the pipeline
        print("\nExecuting pipeline...")

        context = Context()
        outcome = run_pipeline(graph, context=context, logs_root=args.logs_root)

        print(f"\nPipeline completed with status: {outcome.status.value}")
        if outcome.notes:
            print(f"Notes: {outcome.notes}")

        if outcome.status.value == "success":
            sys.exit(0)
        else:
            if outcome.failure_reason:
                print(f"Failure reason: {outcome.failure_reason}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
