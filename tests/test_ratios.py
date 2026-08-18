from __future__ import annotations

import copy
import json

import pytest
from statement_lens.normalizer import (
    REPORT_SCHEMA,
    ValidationError,
    canonical_json,
    sha256_json,
)
from statement_lens.ratios import evaluate_ratio_json, evaluate_ratio_policy


def fact(concept: str, value: str, *, unit: str = "USD") -> dict[str, object]:
    return {
        "concept": concept,
        "dimensions": {},
        "period": {"instant": "2024-12-31", "kind": "instant"},
        "source_locator": f"statement/{concept}",
        "unit": unit,
        "value": value,
    }


def normalized_report(*facts: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "entity": {"identifier": "SYNTH-1"},
        "facts": list(facts),
        "filing": {"accession": "SYNTH-2024"},
        "lineage": {"normalizer": "statement-lens/0.2.0"},
        "schema_version": REPORT_SCHEMA,
        "source": {"locator": "fixture://ratio-test"},
    }
    lineage = report["lineage"]
    assert isinstance(lineage, dict)
    lineage["report_sha256"] = sha256_json(report)
    return report


def ratio(
    name: str = "asset_coverage",
    *,
    numerator: str = "us-gaap:Assets",
    denominator: str = "us-gaap:Liabilities",
    on_missing: str = "report",
    on_zero: str = "report",
) -> dict[str, object]:
    return {
        "decimal_places": 4,
        "denominator_concept": denominator,
        "dimensions": {},
        "name": name,
        "numerator_concept": numerator,
        "on_missing": on_missing,
        "on_zero_denominator": on_zero,
        "period": {"instant": "2024-12-31", "kind": "instant"},
        "unit": "USD",
    }


def policy(*rules: dict[str, object]) -> dict[str, object]:
    return {"ratios": list(rules), "schema_version": "statement-lens.ratio-policy.v1"}


def test_computes_ratio_with_explicit_rounding_and_lineage() -> None:
    report = normalized_report(
        fact("us-gaap:Assets", "1250000"), fact("us-gaap:Liabilities", "500000")
    )
    result = evaluate_ratio_policy(report, policy(ratio()))
    assert result["schema_version"] == "statement-lens.ratio-report.v1"
    assert result["counts"] == {"computed": 1, "insufficient_evidence": 0}
    ratios = result["ratios"]
    assert isinstance(ratios, list)
    assert ratios[0]["value"] == "2.5000"
    assert ratios[0]["rounding"] == "ROUND_HALF_EVEN"
    lineage = result["lineage"]
    assert isinstance(lineage, dict)
    expected = lineage["report_sha256"]
    unsigned = copy.deepcopy(result)
    unsigned_lineage = unsigned["lineage"]
    assert isinstance(unsigned_lineage, dict)
    unsigned_lineage.pop("report_sha256")
    assert sha256_json(unsigned) == expected


def test_output_is_independent_of_rule_order() -> None:
    assets = fact("us-gaap:Assets", "1250000")
    liabilities = fact("us-gaap:Liabilities", "500000")
    cash = fact("us-gaap:Cash", "250000")
    first = evaluate_ratio_policy(
        normalized_report(assets, liabilities, cash),
        policy(
            ratio(),
            ratio("cash_coverage", numerator="us-gaap:Cash"),
        ),
    )
    second = evaluate_ratio_policy(
        normalized_report(assets, liabilities, cash),
        policy(
            ratio("cash_coverage", numerator="us-gaap:Cash"),
            ratio(),
        ),
    )
    assert canonical_json(first) == canonical_json(second)


@pytest.mark.parametrize(
    ("facts", "reason"),
    [
        ([fact("us-gaap:Liabilities", "5")], "missing_numerator"),
        ([fact("us-gaap:Assets", "5")], "missing_denominator"),
        ([], "missing_numerator_and_denominator"),
    ],
)
def test_missingness_is_reported_explicitly(
    facts: list[dict[str, object]], reason: str
) -> None:
    placeholder = fact("us-gaap:Placeholder", "1")
    result = evaluate_ratio_policy(
        normalized_report(*facts, placeholder), policy(ratio())
    )
    ratios = result["ratios"]
    assert isinstance(ratios, list)
    assert ratios[0] == {
        "name": "asset_coverage",
        "reason": reason,
        "status": "insufficient_evidence",
    }


def test_missingness_can_fail_closed() -> None:
    with pytest.raises(ValidationError, match="missing_denominator"):
        evaluate_ratio_policy(
            normalized_report(fact("us-gaap:Assets", "5")),
            policy(ratio(on_missing="error")),
        )


def test_zero_denominator_is_never_divided() -> None:
    report = normalized_report(
        fact("us-gaap:Assets", "5"), fact("us-gaap:Liabilities", "0")
    )
    result = evaluate_ratio_policy(report, policy(ratio()))
    ratios = result["ratios"]
    assert isinstance(ratios, list)
    assert ratios[0]["reason"] == "zero_denominator"
    with pytest.raises(ValidationError, match="zero_denominator"):
        evaluate_ratio_policy(report, policy(ratio(on_zero="error")))


def test_exact_identity_does_not_coerce_unit_period_or_dimensions() -> None:
    wrong_unit = fact("us-gaap:Liabilities", "5", unit="shares")
    result = evaluate_ratio_policy(
        normalized_report(fact("us-gaap:Assets", "10"), wrong_unit), policy(ratio())
    )
    ratios = result["ratios"]
    assert isinstance(ratios, list)
    assert ratios[0]["reason"] == "missing_denominator"


def test_tampered_report_fails_lineage_verification() -> None:
    report = normalized_report(
        fact("us-gaap:Assets", "10"), fact("us-gaap:Liabilities", "5")
    )
    facts = report["facts"]
    assert isinstance(facts, list)
    facts[0]["value"] = "999"
    with pytest.raises(ValidationError, match="does not match"):
        evaluate_ratio_policy(report, policy(ratio()))


def test_policy_rejects_duplicate_names_unknown_fields_and_invalid_precision() -> None:
    with pytest.raises(ValidationError, match="duplicate ratio name"):
        evaluate_ratio_policy(
            normalized_report(fact("us-gaap:Assets", "1")), policy(ratio(), ratio())
        )
    unknown = ratio()
    unknown["surprise"] = True
    with pytest.raises(ValidationError, match="missing or unknown"):
        evaluate_ratio_policy(
            normalized_report(fact("us-gaap:Assets", "1")), policy(unknown)
        )
    invalid_precision = ratio()
    invalid_precision["decimal_places"] = 13
    with pytest.raises(ValidationError, match="0 to 12"):
        evaluate_ratio_policy(
            normalized_report(fact("us-gaap:Assets", "1")), policy(invalid_precision)
        )

    invalid_period = ratio()
    invalid_period["period"] = {"instant": "not-a-date", "kind": "instant"}
    with pytest.raises(ValidationError, match="ISO-8601 calendar date"):
        evaluate_ratio_policy(
            normalized_report(fact("us-gaap:Assets", "1")), policy(invalid_period)
        )


def test_rejects_unbounded_decimal_exponents() -> None:
    report = normalized_report(
        fact("us-gaap:Assets", "1e999999"),
        fact("us-gaap:Liabilities", "1"),
    )
    with pytest.raises(ValidationError, match="adjusted exponent exceeds"):
        evaluate_ratio_policy(report, policy(ratio()))


def test_policy_json_rejects_malformed_and_duplicate_keys() -> None:
    report = normalized_report(fact("us-gaap:Assets", "1"))
    with pytest.raises(ValidationError, match="malformed ratio policy"):
        evaluate_ratio_json(report, "{")
    duplicate = (
        '{"schema_version":"statement-lens.ratio-policy.v1","ratios":[],"ratios":[]}'
    )
    with pytest.raises(ValidationError, match="duplicate JSON key"):
        evaluate_ratio_json(report, duplicate)


def test_ratio_policy_json_round_trip() -> None:
    report = normalized_report(
        fact("us-gaap:Assets", "1"), fact("us-gaap:Liabilities", "8")
    )
    result = evaluate_ratio_json(report, json.dumps(policy(ratio())))
    ratios = result["ratios"]
    assert isinstance(ratios, list)
    assert ratios[0]["value"] == "0.1250"
