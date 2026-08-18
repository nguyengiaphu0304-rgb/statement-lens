from __future__ import annotations

import json
from pathlib import Path

from statement_lens.cli import main

ROOT = Path(__file__).parents[1]
INPUT = ROOT / "fixtures" / "synthetic_ratio_statement.json"
POLICY = ROOT / "fixtures" / "synthetic_ratio_policy.json"


def test_cli_writes_canonical_ratio_report(tmp_path: Path) -> None:
    output = tmp_path / "ratios.json"
    assert (
        main(
            [
                str(INPUT),
                "--ratio-policy",
                str(POLICY),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    parsed = json.loads(text)
    assert parsed["schema_version"] == "statement-lens.ratio-report.v1"
    assert parsed["counts"] == {"computed": 1, "insufficient_evidence": 0}
    assert parsed["ratios"][0]["value"] == "2.5000"


def test_cli_rejects_ratio_and_history_modes_together() -> None:
    assert (
        main(
            [
                str(INPUT),
                "--ratio-policy",
                str(POLICY),
                "--base-accession",
                "a",
                "--comparison-accession",
                "b",
                "--as-of",
                "2025-01-01T00:00:00Z",
            ]
        )
        == 2
    )
