from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from statement_lens.cli import main
from statement_lens.normalizer import (
    ValidationError,
    canonical_json,
    normalize_document,
    normalize_json,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synthetic_statement.json"


@pytest.fixture
def document() -> dict[str, object]:
    loaded: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def nested(document: dict[str, object], *keys: str) -> dict[str, object]:
    current = document
    for key in keys:
        value = current[key]
        assert isinstance(value, dict)
        current = value
    return current


def facts(document: dict[str, object]) -> list[dict[str, object]]:
    value = document["facts"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def concepts(document: dict[str, object]) -> list[dict[str, object]]:
    taxonomy = nested(document, "taxonomy")
    value = taxonomy["concepts"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return value


def mutations(document: dict[str, object]) -> Iterator[tuple[str, dict[str, object]]]:
    unknown = copy.deepcopy(document)
    facts(unknown)[0]["concept"] = "us-gaap:Unknown"
    yield "not declared", unknown

    unit = copy.deepcopy(document)
    facts(unit)[0]["unit"] = "shares"
    yield "not allowed", unit

    scale = copy.deepcopy(document)
    facts(scale)[0]["scale"] = 2
    yield "not allowed", scale

    locator = copy.deepcopy(document)
    facts(locator)[0]["source_locator"] = ""
    yield "non-empty string", locator


def test_normalizes_provenance_and_decimal_values(document: dict[str, object]) -> None:
    report = normalize_document(document)
    assert report["schema_version"] == "statement-lens.normalized.v1"
    assert report["source"] == document["source"]
    normalized_facts = report["facts"]
    assert isinstance(normalized_facts, list)
    values = {item["concept"]: item["value"] for item in normalized_facts}
    assert values == {"us-gaap:Assets": "1250000", "us-gaap:Revenue": "2500000"}
    lineage = report["lineage"]
    assert isinstance(lineage, dict)
    assert len(lineage["input_sha256"]) == 64
    assert len(lineage["report_sha256"]) == 64


def test_identical_duplicate_collapses(document: dict[str, object]) -> None:
    facts(document).append(copy.deepcopy(facts(document)[0]))
    report = normalize_document(document)
    normalized_facts = report["facts"]
    assert isinstance(normalized_facts, list)
    assert len(normalized_facts) == 2


def test_conflicting_duplicate_fails_closed(document: dict[str, object]) -> None:
    conflicting = copy.deepcopy(facts(document)[0])
    conflicting["value"] = "999"
    facts(document).append(conflicting)
    with pytest.raises(ValidationError, match="conflicting duplicate"):
        normalize_document(document)


@pytest.mark.parametrize(("value", "expected"), [("1.25E3", "1250000"), ("-0", "0")])
def test_decimal_canonicalization(document: dict[str, object], value: str, expected: str) -> None:
    facts(document)[0]["value"] = value
    report = normalize_document(document)
    normalized = report["facts"]
    assert isinstance(normalized, list)
    assets = next(item for item in normalized if item["concept"] == "us-gaap:Assets")
    assert assets["value"] == expected


@pytest.mark.parametrize("value", ["not-a-number", "NaN", "Infinity"])
def test_invalid_decimals_fail(document: dict[str, object], value: str) -> None:
    facts(document)[0]["value"] = value
    with pytest.raises(ValidationError, match="finite decimal"):
        normalize_document(document)


def test_period_type_mismatch_fails(document: dict[str, object]) -> None:
    facts(document)[0]["period"] = {
        "kind": "duration",
        "start": "2024-01-01",
        "end": "2024-12-31",
    }
    with pytest.raises(ValidationError, match="must be 'instant'"):
        normalize_document(document)


def test_duration_requires_both_endpoints(document: dict[str, object]) -> None:
    facts(document)[1]["period"] = {"kind": "duration", "start": "2024-01-01"}
    with pytest.raises(ValidationError, match="non-empty string"):
        normalize_document(document)


def test_duration_end_cannot_precede_start(document: dict[str, object]) -> None:
    facts(document)[1]["period"] = {
        "kind": "duration",
        "start": "2024-12-31",
        "end": "2024-01-01",
    }
    with pytest.raises(ValidationError, match="cannot precede"):
        normalize_document(document)


def test_filing_time_boundary_is_valid(document: dict[str, object]) -> None:
    report = normalize_document(document)
    assert report["filing"] == document["filing"]


def test_future_filing_timestamp_fails(document: dict[str, object]) -> None:
    nested(document, "filing")["filed_at"] = "2025-02-02T00:00:01Z"
    with pytest.raises(ValidationError, match=r"later than source\.retrieved_at"):
        normalize_document(document)


def test_taxonomy_unit_scale_concept_and_locator_failures(document: dict[str, object]) -> None:
    for expected, invalid in mutations(document):
        with pytest.raises(ValidationError, match=expected):
            normalize_document(invalid)


def test_distinct_accessions_preserve_restatement_identity(document: dict[str, object]) -> None:
    first = normalize_document(document)
    revised = copy.deepcopy(document)
    nested(revised, "filing")["accession"] = "0000000000-25-000002"
    second = normalize_document(revised)
    assert first["filing"] != second["filing"]
    assert first["lineage"] != second["lineage"]


def test_order_independent_output_and_digest(document: dict[str, object]) -> None:
    first = normalize_document(document)
    facts(document).reverse()
    concepts(document).reverse()
    second = normalize_document(document)
    assert canonical_json(first) == canonical_json(second)


def test_unsupported_schema_and_malformed_json_fail(document: dict[str, object]) -> None:
    document["schema_version"] = "statement-lens.ingest.v2"
    with pytest.raises(ValidationError, match="unsupported schema_version"):
        normalize_document(document)
    with pytest.raises(ValidationError, match="malformed JSON"):
        normalize_json("{")


def test_cli_writes_canonical_output(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    assert main([str(FIXTURE), "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8").endswith("\n")
    parsed = json.loads(output.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == "statement-lens.normalized.v1"


def test_cli_returns_nonzero_for_invalid_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert main([str(invalid)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"]["type"] == "validation_error"
