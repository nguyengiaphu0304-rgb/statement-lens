from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from statement_lens.accounting import analyze_document, analyze_json, analyze_report
from statement_lens.cli import main
from statement_lens.normalizer import ValidationError, canonical_json, normalize_document

FIXTURE = Path(__file__).parents[1] / "fixtures" / "synthetic_accounting.json"


@pytest.fixture
def accounting_input() -> dict[str, object]:
    loaded: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def document(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], value["document"])


def policy(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], value["policy"])


def facts(value: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], document(value)["facts"])


def mappings(value: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], policy(value)["mappings"])


def reconciliations(value: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], policy(value)["reconciliations"])


def test_computes_reconciliations_and_preserves_provenance(
    accounting_input: dict[str, object],
) -> None:
    report = analyze_document(accounting_input)
    assert report["schema_version"] == "statement-lens.accounting-report.v1"
    checks = cast(list[dict[str, object]], report["reconciliations"])
    assert [(item["name"], item["status"], item["difference"]) for item in checks] == [
        ("balance_sheet", "pass", "0"),
        ("cash_flow", "pass", "0"),
    ]
    mapped = cast(list[dict[str, object]], report["mapped_facts"])
    assets = next(item for item in mapped if item["canonical_concept"] == "assets")
    assert assets["sources"] == [
        {
            "rule_id": "map-assets-v1",
            "source_concept": "us-gaap:Assets",
            "source_locator": "balance-sheet/assets",
            "value": "1000",
        }
    ]
    assert report["unmapped_facts"] == [
        {
            "source_concept": "synthetic:DisclosureCount",
            "source_locator": "notes/disclosures",
        }
    ]


def test_lineage_is_complete_and_detects_tampering(accounting_input: dict[str, object]) -> None:
    normalized = normalize_document(document(accounting_input))
    report = analyze_report(normalized, policy(accounting_input))
    lineage = cast(dict[str, object], report["lineage"])
    assert all(
        len(cast(str, lineage[key])) == 64
        for key in (
            "mapped_facts_sha256",
            "normalized_report_sha256",
            "policy_sha256",
            "report_sha256",
        )
    )
    normalized_facts = cast(list[dict[str, object]], normalized["facts"])
    normalized_facts[0]["value"] = "999"
    with pytest.raises(ValidationError, match="report_sha256"):
        analyze_report(normalized, policy(accounting_input))


def test_reconciliation_exact_tolerance_and_failure(accounting_input: dict[str, object]) -> None:
    assets = next(item for item in facts(accounting_input) if item["concept"] == "us-gaap:Assets")
    assets["value"] = "1001"
    balance = next(
        item for item in reconciliations(accounting_input) if item["name"] == "balance_sheet"
    )
    balance["tolerance"] = "1"
    report = analyze_document(accounting_input)
    check = next(
        item
        for item in cast(list[dict[str, object]], report["reconciliations"])
        if item["name"] == "balance_sheet"
    )
    assert (check["difference"], check["status"]) == ("1", "pass")
    assets["value"] = "1002"
    report = analyze_document(accounting_input)
    check = next(
        item
        for item in cast(list[dict[str, object]], report["reconciliations"])
        if item["name"] == "balance_sheet"
    )
    assert (check["difference"], check["status"]) == ("2", "fail")


def test_missing_fact_is_insufficient_evidence_not_zero(
    accounting_input: dict[str, object],
) -> None:
    mappings(accounting_input)[:] = [
        item for item in mappings(accounting_input) if item["canonical_concept"] != "equity"
    ]
    report = analyze_document(accounting_input)
    check = next(
        item
        for item in cast(list[dict[str, object]], report["reconciliations"])
        if item["name"] == "balance_sheet"
    )
    assert check["status"] == "insufficient_evidence"
    assert check["difference"] is None
    assert check["missing"] == ["equity"]


def test_duplicate_source_and_rule_ids_fail(accounting_input: dict[str, object]) -> None:
    duplicate = copy.deepcopy(mappings(accounting_input)[0])
    duplicate["rule_id"] = "another-rule"
    mappings(accounting_input).append(duplicate)
    with pytest.raises(ValidationError, match="mapped more than once"):
        analyze_document(accounting_input)
    mappings(accounting_input).pop()
    duplicate = copy.deepcopy(mappings(accounting_input)[0])
    duplicate["source_concept"] = "synthetic:AnotherConcept"
    mappings(accounting_input).append(duplicate)
    with pytest.raises(ValidationError, match=r"rule_id.*duplicated"):
        analyze_document(accounting_input)


def test_many_to_one_requires_exact_aggregation(accounting_input: dict[str, object]) -> None:
    liabilities = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "liabilities"
    )
    liabilities["canonical_concept"] = "assets"
    with pytest.raises(ValidationError, match="requires an exact aggregation"):
        analyze_document(accounting_input)


def test_declared_aggregation_sums_compatible_inputs(accounting_input: dict[str, object]) -> None:
    liabilities = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "liabilities"
    )
    equity = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "equity"
    )
    liabilities["canonical_concept"] = "capital"
    equity["canonical_concept"] = "capital"
    policy(accounting_input)["aggregations"] = [
        {
            "canonical_concept": "capital",
            "operation": "sum",
            "rule_id": "sum-capital-v1",
            "source_concepts": ["us-gaap:Liabilities", "us-gaap:StockholdersEquity"],
        }
    ]
    report = analyze_document(accounting_input)
    capital = next(
        item
        for item in cast(list[dict[str, object]], report["mapped_facts"])
        if item["canonical_concept"] == "capital"
    )
    assert capital["value"] == "1000"
    assert capital["aggregation_rule_id"] == "sum-capital-v1"
    assert len(cast(list[object], capital["sources"])) == 2


def test_aggregation_preserves_wide_decimal_exponents(
    accounting_input: dict[str, object],
) -> None:
    liabilities_rule = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "liabilities"
    )
    equity_rule = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "equity"
    )
    liabilities_rule["canonical_concept"] = "capital"
    equity_rule["canonical_concept"] = "capital"
    policy(accounting_input)["aggregations"] = [
        {
            "canonical_concept": "capital",
            "operation": "sum",
            "rule_id": "sum-capital-v1",
            "source_concepts": ["us-gaap:Liabilities", "us-gaap:StockholdersEquity"],
        }
    ]
    liabilities = next(
        item for item in facts(accounting_input) if item["concept"] == "us-gaap:Liabilities"
    )
    equity = next(
        item for item in facts(accounting_input) if item["concept"] == "us-gaap:StockholdersEquity"
    )
    liabilities["value"] = "1e256"
    equity["value"] = "1e-256"
    report = analyze_document(accounting_input)
    capital = next(
        item
        for item in cast(list[dict[str, object]], report["mapped_facts"])
        if item["canonical_concept"] == "capital"
    )
    assert capital["value"] == f"1{'0' * 256}.{'0' * 255}1"


def test_unsupported_aggregation_and_empty_mapping_fail(
    accounting_input: dict[str, object],
) -> None:
    liabilities = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "liabilities"
    )
    equity = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "equity"
    )
    liabilities["canonical_concept"] = "capital"
    equity["canonical_concept"] = "capital"
    policy(accounting_input)["aggregations"] = [
        {
            "canonical_concept": "capital",
            "operation": "average",
            "rule_id": "average-capital-v1",
            "source_concepts": ["us-gaap:Liabilities", "us-gaap:StockholdersEquity"],
        }
    ]
    with pytest.raises(ValidationError, match="unsupported operation"):
        analyze_document(accounting_input)
    mappings(accounting_input).clear()
    with pytest.raises(ValidationError, match="must contain"):
        analyze_document(accounting_input)


def test_mapping_rejects_unit_period_and_dimension_mismatch(
    accounting_input: dict[str, object],
) -> None:
    current_assets = next(
        item for item in mappings(accounting_input) if item["canonical_concept"] == "current_assets"
    )
    current_assets["unit"] = "EUR"
    with pytest.raises(ValidationError, match="declared unit"):
        analyze_document(accounting_input)
    current_assets["unit"] = "USD"
    current_assets["period_type"] = "duration"
    with pytest.raises(ValidationError, match="declared period_type"):
        analyze_document(accounting_input)
    current_assets["period_type"] = "instant"
    fact = next(
        item for item in facts(accounting_input) if item["concept"] == "us-gaap:CurrentAssets"
    )
    fact["dimensions"] = {"synthetic:SegmentAxis": "synthetic:ConsumerMember"}
    with pytest.raises(ValidationError, match="require a selector"):
        analyze_document(accounting_input)


def test_reconciliation_rejects_mixed_periods(accounting_input: dict[str, object]) -> None:
    equity = next(
        item for item in facts(accounting_input) if item["concept"] == "us-gaap:StockholdersEquity"
    )
    equity["period"] = {"kind": "instant", "instant": "2024-12-30"}
    with pytest.raises(ValidationError, match="mixes periods"):
        analyze_document(accounting_input)


def test_negative_or_unbounded_tolerance_fails(
    accounting_input: dict[str, object],
) -> None:
    reconciliations(accounting_input)[0]["tolerance"] = "-0.01"
    with pytest.raises(ValidationError, match="tolerance cannot be negative"):
        analyze_document(accounting_input)
    reconciliations(accounting_input)[0]["tolerance"] = "1e999999"
    with pytest.raises(ValidationError, match="adjusted exponent"):
        analyze_document(accounting_input)


def test_unknown_fields_and_duplicate_json_keys_fail(
    accounting_input: dict[str, object],
) -> None:
    policy(accounting_input)["unexpected"] = True
    with pytest.raises(ValidationError, match="missing or unknown"):
        analyze_document(accounting_input)
    with pytest.raises(ValidationError, match="duplicate JSON key"):
        analyze_json('{"schema_version":"x","schema_version":"y"}')


def test_rule_shapes_and_reconciliation_identity_fail_closed(
    accounting_input: dict[str, object],
) -> None:
    mappings(accounting_input)[0]["unexpected"] = True
    with pytest.raises(ValidationError, match="missing or unknown"):
        analyze_document(accounting_input)
    mappings(accounting_input)[0].pop("unexpected")
    reconciliation = reconciliations(accounting_input)[0]
    reconciliation["right"] = [reconciliation["left"]]
    with pytest.raises(ValidationError, match="unique right-hand"):
        analyze_document(accounting_input)


def test_order_independent_policy_facts_and_lineage(accounting_input: dict[str, object]) -> None:
    first = analyze_document(accounting_input)
    facts(accounting_input).reverse()
    mappings(accounting_input).reverse()
    reconciliations(accounting_input).reverse()
    second = analyze_document(accounting_input)
    assert canonical_json(first) == canonical_json(second)


def test_cli_writes_canonical_accounting_report(tmp_path: Path) -> None:
    output = tmp_path / "accounting.json"
    assert main([str(FIXTURE), "--accounting", "--output", str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["schema_version"] == "statement-lens.accounting-report.v1"


def test_cli_rejects_accounting_history_combination(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(FIXTURE), "--accounting", "--as-of", "2025-01-01T00:00:00Z"]) == 2
    assert "cannot be combined" in capsys.readouterr().err
