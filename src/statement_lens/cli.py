"""Command-line interface for offline Statement Lens analysis."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from statement_lens.accounting import analyze_json
from statement_lens.history import compare_json
from statement_lens.normalizer import ValidationError, canonical_json, normalize_json
from statement_lens.ratios import evaluate_ratio_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="statement-lens",
        description="Normalize or analyze a provenance-bearing financial-statement fixture.",
    )
    parser.add_argument("input", type=Path, help="path to an ingestion JSON document")
    parser.add_argument("--output", type=Path, help="write canonical report to this path")
    parser.add_argument("--base-accession", help="explicit base accession for history comparison")
    parser.add_argument(
        "--comparison-accession", help="explicit comparison accession for history comparison"
    )
    parser.add_argument("--as-of", help="timezone-aware availability cutoff for history comparison")
    parser.add_argument(
        "--accounting",
        action="store_true",
        help="apply the versioned mapping and reconciliation policy embedded in the input",
    )
    parser.add_argument(
        "--ratio-policy",
        type=Path,
        help="evaluate a versioned ratio policy against the normalized input",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        text = args.input.read_text(encoding="utf-8")
        history_values = (args.base_accession, args.comparison_accession, args.as_of)
        if args.accounting:
            if args.ratio_policy is not None or any(value is not None for value in history_values):
                raise ValidationError(
                    "--accounting cannot be combined with ratio or history comparison options"
                )
            report = analyze_json(text)
        elif args.ratio_policy is not None:
            if any(value is not None for value in history_values):
                raise ValidationError(
                    "--ratio-policy cannot be combined with history comparison options"
                )
            normalized = normalize_json(text)
            policy_text = args.ratio_policy.read_text(encoding="utf-8")
            report = evaluate_ratio_json(normalized, policy_text)
        elif any(value is not None for value in history_values):
            if not all(value is not None for value in history_values):
                raise ValidationError(
                    "--base-accession, --comparison-accession and --as-of must be provided together"
                )
            report = compare_json(
                text,
                base_accession=args.base_accession,
                comparison_accession=args.comparison_accession,
                as_of=args.as_of,
            )
        else:
            report = normalize_json(text)
        output = canonical_json(report) + "\n"
        if args.output is None:
            sys.stdout.write(output)
        else:
            args.output.write_text(output, encoding="utf-8", newline="\n")
    except (OSError, ValidationError) as error:
        sys.stderr.write(
            json.dumps(
                {"error": {"message": str(error), "type": "validation_error"}},
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
