"""Command-line interface for offline Statement Lens normalization."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from statement_lens.normalizer import ValidationError, canonical_json, normalize_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="statement-lens",
        description="Normalize a provenance-bearing financial-statement fixture.",
    )
    parser.add_argument("input", type=Path, help="path to an ingestion JSON document")
    parser.add_argument("--output", type=Path, help="write canonical report to this path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = _parser().parse_args(argv)
    try:
        text = args.input.read_text(encoding="utf-8")
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
