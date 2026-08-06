from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from statement_lens.cli import main
from statement_lens.history import compare_documents, compare_history, compare_json
from statement_lens.normalizer import ValidationError, canonical_json, normalize_document

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synthetic_restatement.json"
BASE = "0000000000-25-000001"
COMPARISON = "0000000000-25-000002"
AS_OF = "2025-03-02T00:00:00Z"


@pytest.fixture
def history_input() -> dict[str, object]:
    loaded: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def documents(value: dict[str, object]) -> list[dict[str, object]]:
    result = value["documents"]
    assert isinstance(result, list)
    assert all(isinstance(item, dict) for item in result)
    return result


def normalized(value: dict[str, object]) -> list[dict[str, object]]:
    return [normalize_document(item) for item in documents(value)]


def compare(value: dict[str, object]) -> dict[str, object]:
    return compare_documents(
        documents(value),
        base_accession=BASE,
        comparison_accession=COMPARISON,
        as_of=AS_OF,
    )


def test_classifies_all_change_types_with_provenance(history_input: dict[str, object]) -> None:
    report = compare(history_input)
    assert report["schema_version"] == "statement-lens.restatement.v1"
    assert report["counts"] == {"added": 1, "changed": 1, "removed": 1, "unchanged": 1}
    changes = report["changes"]
    assert isinstance(changes, list)
    changed = next(item for item in changes if item["classification"] == "changed")
    assert changed["before"]["value"] == "2500000"
    assert changed["before"]["source_locator"] == "original/revenue"
    assert changed["after"]["value"] == "2600000"
    assert changed["after"]["source_locator"] == "restated/revenue"


def test_requires_explicit_accessions(history_input: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="base_accession"):
        compare_documents(
            documents(history_input),
            base_accession="missing",
            comparison_accession=COMPARISON,
            as_of=AS_OF,
        )
    with pytest.raises(ValidationError, match="must differ"):
        compare_documents(
            documents(history_input),
            base_accession=BASE,
            comparison_accession=BASE,
            as_of=AS_OF,
        )


def test_availability_cutoff_blocks_look_ahead(history_input: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="not available at as_of"):
        compare_documents(
            documents(history_input),
            base_accession=BASE,
            comparison_accession=COMPARISON,
            as_of="2025-03-01T23:59:59Z",
        )
    with pytest.raises(ValidationError, match="include a timezone"):
        compare_documents(
            documents(history_input),
            base_accession=BASE,
            comparison_accession=COMPARISON,
            as_of="2025-03-02T00:00:00",
        )


def test_base_cannot_follow_comparison(history_input: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="availability order"):
        compare_documents(
            documents(history_input),
            base_accession=COMPARISON,
            comparison_accession=BASE,
            as_of=AS_OF,
        )


def test_mixed_entities_fail(history_input: dict[str, object]) -> None:
    second = documents(history_input)[1]
    entity = second["entity"]
    assert isinstance(entity, dict)
    entity["identifier"] = "OTHER"
    with pytest.raises(ValidationError, match="exactly one entity"):
        compare(history_input)


def test_identical_accession_collapses_but_conflict_fails(
    history_input: dict[str, object],
) -> None:
    reports = normalized(history_input)
    duplicate = copy.deepcopy(reports[0])
    result = compare_history(
        [*reports, duplicate],
        base_accession=BASE,
        comparison_accession=COMPARISON,
        as_of=AS_OF,
    )
    assert len(result["history"]) == 2

    conflicting = copy.deepcopy(reports[0])
    source = conflicting["source"]
    assert isinstance(source, dict)
    source["locator"] = "tampered"
    lineage = conflicting["lineage"]
    assert isinstance(lineage, dict)
    unsigned = copy.deepcopy(conflicting)
    unsigned_lineage = unsigned["lineage"]
    assert isinstance(unsigned_lineage, dict)
    unsigned_lineage.pop("report_sha256")
    from statement_lens.normalizer import sha256_json

    lineage["report_sha256"] = sha256_json(unsigned)
    with pytest.raises(ValidationError, match="conflicting duplicate accession"):
        compare_history(
            [*reports, conflicting],
            base_accession=BASE,
            comparison_accession=COMPARISON,
            as_of=AS_OF,
        )


def test_tampered_normalized_report_fails_lineage(history_input: dict[str, object]) -> None:
    reports = normalized(history_input)
    facts = reports[0]["facts"]
    assert isinstance(facts, list)
    fact = facts[0]
    assert isinstance(fact, dict)
    fact["value"] = "999"
    with pytest.raises(ValidationError, match="report_sha256"):
        compare_history(
            reports,
            base_accession=BASE,
            comparison_accession=COMPARISON,
            as_of=AS_OF,
        )


def test_order_independent_history_and_lineage(history_input: dict[str, object]) -> None:
    first = compare(history_input)
    documents(history_input).reverse()
    for document in documents(history_input):
        facts = document["facts"]
        assert isinstance(facts, list)
        facts.reverse()
    second = compare(history_input)
    assert canonical_json(first) == canonical_json(second)


def test_identity_does_not_coerce_units_or_dimensions(history_input: dict[str, object]) -> None:
    revised = documents(history_input)[1]
    facts = revised["facts"]
    assert isinstance(facts, list)
    revenue = next(item for item in facts if item["concept"] == "us-gaap:Revenue")
    assert isinstance(revenue, dict)
    revenue["dimensions"] = {"synthetic:RegionAxis": "synthetic:GlobalMember"}
    report = compare(history_input)
    counts = report["counts"]
    assert isinstance(counts, dict)
    assert counts == {"added": 2, "changed": 0, "removed": 2, "unchanged": 1}


def test_source_locator_only_difference_is_changed(history_input: dict[str, object]) -> None:
    revised = documents(history_input)[1]
    facts = revised["facts"]
    assert isinstance(facts, list)
    revenue = next(item for item in facts if item["concept"] == "us-gaap:Revenue")
    assert isinstance(revenue, dict)
    revenue["value"] = "2500"
    report = compare(history_input)
    changes = report["changes"]
    assert isinstance(changes, list)
    revenue_change = next(
        item for item in changes if item["identity"]["concept"] == "us-gaap:Revenue"
    )
    assert revenue_change["classification"] == "changed"


def test_empty_and_unsupported_history_fail(history_input: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        compare_history([], base_accession=BASE, comparison_accession=COMPARISON, as_of=AS_OF)
    history_input["schema_version"] = "statement-lens.history-input.v2"
    with pytest.raises(ValidationError, match="unsupported history schema_version"):
        compare_json(
            json.dumps(history_input),
            base_accession=BASE,
            comparison_accession=COMPARISON,
            as_of=AS_OF,
        )


def test_cli_writes_canonical_restatement_report(tmp_path: Path) -> None:
    output = tmp_path / "restatement.json"
    assert (
        main(
            [
                str(FIXTURE),
                "--base-accession",
                BASE,
                "--comparison-accession",
                COMPARISON,
                "--as-of",
                AS_OF,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["counts"]["changed"] == 1


def test_cli_requires_complete_history_selection(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(FIXTURE), "--base-accession", BASE]) == 2
    assert "must be provided together" in capsys.readouterr().err
