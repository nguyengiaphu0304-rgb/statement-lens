"""Build and independently replay the complete offline v1.0 evidence set."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

from statement_lens import __version__

ROOT: Final = Path(__file__).resolve().parents[1]
REPORTS: Final = (
    "normalized-report.json",
    "history-report.json",
    "ratio-report.json",
    "accounting-report.json",
)
SOURCES: Final = (
    "fixtures/synthetic_accounting.json",
    "fixtures/synthetic_ratio_policy.json",
    "fixtures/synthetic_ratio_statement.json",
    "fixtures/synthetic_restatement.json",
    "fixtures/synthetic_statement.json",
)
GENERATORS: Final = ("scripts/release_evidence.py",)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _run(arguments: tuple[str, ...], output: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "statement_lens.cli", *arguments, "--output", str(output)],
        cwd=ROOT,
        check=True,
    )


def generate(output_dir: Path) -> None:
    """Generate a canonical evidence set and a manifest binding every input."""
    output_dir.mkdir(parents=True, exist_ok=True)
    commands = (
        (("fixtures/synthetic_statement.json",), "normalized-report.json"),
        (
            (
                "fixtures/synthetic_restatement.json",
                "--base-accession",
                "0000000000-25-000001",
                "--comparison-accession",
                "0000000000-25-000002",
                "--as-of",
                "2025-03-02T00:00:00Z",
            ),
            "history-report.json",
        ),
        (
            (
                "fixtures/synthetic_ratio_statement.json",
                "--ratio-policy",
                "fixtures/synthetic_ratio_policy.json",
            ),
            "ratio-report.json",
        ),
        (("fixtures/synthetic_accounting.json", "--accounting"), "accounting-report.json"),
    )
    for arguments, name in commands:
        _run(arguments, output_dir / name)

    manifest = {
        "artifact_schema": "statement-lens.release-evidence.v1",
        "generators": {path: _sha256((ROOT / path).read_bytes()) for path in sorted(GENERATORS)},
        "package_version": __version__,
        "reports": {name: _sha256((output_dir / name).read_bytes()) for name in REPORTS},
        "sources": {path: _sha256((ROOT / path).read_bytes()) for path in sorted(SOURCES)},
        "synthetic_only": True,
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    (output_dir / "manifest.json").write_text(f"{encoded}\n", encoding="utf-8", newline="\n")


def verify(output_dir: Path) -> None:
    """Regenerate evidence and require the exact expected file set and bytes."""
    with tempfile.TemporaryDirectory(prefix="statement-lens-evidence-") as temporary:
        regenerated = Path(temporary)
        generate(regenerated)
        expected = tuple(sorted((*REPORTS, "manifest.json")))
        actual = tuple(sorted(path.name for path in output_dir.iterdir() if path.is_file()))
        if actual != expected:
            raise ValueError("release evidence file set is not exact")
        for name in expected:
            if (output_dir / name).read_bytes() != (regenerated / name).read_bytes():
                raise ValueError(f"release evidence drift: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or verify Statement Lens v1.0 evidence")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify:
        verify(arguments.output_dir)
    else:
        generate(arguments.output_dir)


if __name__ == "__main__":
    main()
