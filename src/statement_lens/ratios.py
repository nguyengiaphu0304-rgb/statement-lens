"""Deterministic, policy-bound ratio evaluation for normalized statements."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import cast

from statement_lens.normalizer import (
    REPORT_SCHEMA,
    ValidationError,
    canonical_json,
    sha256_json,
)

RATIO_POLICY_SCHEMA = "statement-lens.ratio-policy.v1"
RATIO_REPORT_SCHEMA = "statement-lens.ratio-report.v1"
MAX_RATIO_RULES = 100
MAX_DECIMAL_CHARACTERS = 128
MAX_ABSOLUTE_ADJUSTED_EXPONENT = 256


@dataclass(frozen=True)
class RatioRule:
    """A normalized, exact-selection ratio rule."""

    decimal_places: int
    denominator_concept: str
    dimensions: tuple[tuple[str, str], ...]
    name: str
    numerator_concept: str
    on_missing: str
    on_zero_denominator: str
    period: str
    unit: str


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValidationError(f"{field} must be an object with string keys")
    return cast(dict[str, object], value)


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValidationError(f"{field} must be an array")
    return cast(list[object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _choice(value: object, field: str) -> str:
    selected = _string(value, field)
    if selected not in {"error", "report"}:
        raise ValidationError(f"{field} must be 'error' or 'report'")
    return selected


def _decimal(value: object, field: str) -> Decimal:
    text = _string(value, field)
    if len(text) > MAX_DECIMAL_CHARACTERS:
        raise ValidationError(
            f"{field} exceeds the {MAX_DECIMAL_CHARACTERS} character decimal limit"
        )
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValidationError(f"{field} must be a finite decimal string") from error
    if not parsed.is_finite():
        raise ValidationError(f"{field} must be a finite decimal string")
    if abs(parsed.adjusted()) > MAX_ABSOLUTE_ADJUSTED_EXPONENT:
        raise ValidationError(
            f"{field} adjusted exponent exceeds {MAX_ABSOLUTE_ADJUSTED_EXPONENT}"
        )
    return parsed


def _date(value: object, field: str) -> str:
    text = _string(value, field)
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ValidationError(f"{field} must be an ISO-8601 calendar date") from error


def _period(value: object, field: str) -> dict[str, object]:
    period = _mapping(value, field)
    kind = _string(period.get("kind"), f"{field}.kind")
    if kind == "instant":
        if set(period) != {"instant", "kind"}:
            raise ValidationError(f"{field} instant must contain only kind and instant")
        return {
            "instant": _date(period.get("instant"), f"{field}.instant"),
            "kind": kind,
        }
    if kind == "duration":
        if set(period) != {"end", "kind", "start"}:
            raise ValidationError(
                f"{field} duration must contain only kind, start and end"
            )
        start = _date(period.get("start"), f"{field}.start")
        end = _date(period.get("end"), f"{field}.end")
        if end < start:
            raise ValidationError(f"{field}.end cannot precede {field}.start")
        return {"end": end, "kind": kind, "start": start}
    raise ValidationError(f"{field}.kind must be 'instant' or 'duration'")


def _dimensions(value: object, field: str) -> tuple[tuple[str, str], ...]:
    raw = _mapping(value, field)
    normalized = [
        (_string(axis, f"{field}.axis"), _string(member, f"{field}.{axis}"))
        for axis, member in raw.items()
    ]
    return tuple(sorted(normalized))


def _verify_report(value: Mapping[str, object]) -> dict[str, object]:
    report = copy.deepcopy(_mapping(dict(value), "report"))
    if report.get("schema_version") != REPORT_SCHEMA:
        raise ValidationError("report has unsupported schema_version")
    facts = _list(report.get("facts"), "report.facts")
    if not facts:
        raise ValidationError("report.facts must not be empty")
    lineage = _mapping(report.get("lineage"), "report.lineage")
    expected = _string(lineage.get("report_sha256"), "report.lineage.report_sha256")
    unsigned = copy.deepcopy(report)
    unsigned_lineage = _mapping(unsigned.get("lineage"), "report.lineage")
    unsigned_lineage.pop("report_sha256", None)
    if sha256_json(unsigned) != expected:
        raise ValidationError(
            "report.lineage.report_sha256 does not match report content"
        )
    return report


def _parse_rules(
    policy: Mapping[str, object],
) -> tuple[list[RatioRule], dict[str, object]]:
    document = _mapping(dict(policy), "policy")
    if set(document) != {"ratios", "schema_version"}:
        raise ValidationError("policy must contain only ratios and schema_version")
    if document.get("schema_version") != RATIO_POLICY_SCHEMA:
        raise ValidationError("policy has unsupported schema_version")
    items = _list(document.get("ratios"), "policy.ratios")
    if not items:
        raise ValidationError("policy.ratios must not be empty")
    if len(items) > MAX_RATIO_RULES:
        raise ValidationError(f"policy.ratios exceeds the {MAX_RATIO_RULES} rule limit")

    expected_fields = {
        "decimal_places",
        "denominator_concept",
        "dimensions",
        "name",
        "numerator_concept",
        "on_missing",
        "on_zero_denominator",
        "period",
        "unit",
    }
    rules: list[RatioRule] = []
    names: set[str] = set()
    manifests: list[dict[str, object]] = []
    for index, value in enumerate(items):
        field = f"policy.ratios[{index}]"
        item = _mapping(value, field)
        if set(item) != expected_fields:
            raise ValidationError(f"{field} has missing or unknown fields")
        name = _string(item.get("name"), f"{field}.name")
        if name in names:
            raise ValidationError(f"duplicate ratio name {name!r}")
        names.add(name)
        decimal_places = item.get("decimal_places")
        if (
            isinstance(decimal_places, bool)
            or not isinstance(decimal_places, int)
            or not 0 <= decimal_places <= 12
        ):
            raise ValidationError(
                f"{field}.decimal_places must be an integer from 0 to 12"
            )
        period = _period(item.get("period"), f"{field}.period")
        dimensions = _dimensions(item.get("dimensions"), f"{field}.dimensions")
        rule = RatioRule(
            decimal_places=decimal_places,
            denominator_concept=_string(
                item.get("denominator_concept"), f"{field}.denominator_concept"
            ),
            dimensions=dimensions,
            name=name,
            numerator_concept=_string(
                item.get("numerator_concept"), f"{field}.numerator_concept"
            ),
            on_missing=_choice(item.get("on_missing"), f"{field}.on_missing"),
            on_zero_denominator=_choice(
                item.get("on_zero_denominator"), f"{field}.on_zero_denominator"
            ),
            period=canonical_json(period),
            unit=_string(item.get("unit"), f"{field}.unit"),
        )
        rules.append(rule)
        manifests.append(
            {
                "decimal_places": rule.decimal_places,
                "denominator_concept": rule.denominator_concept,
                "dimensions": dict(rule.dimensions),
                "name": rule.name,
                "numerator_concept": rule.numerator_concept,
                "on_missing": rule.on_missing,
                "on_zero_denominator": rule.on_zero_denominator,
                "period": json.loads(rule.period),
                "unit": rule.unit,
            }
        )
    rules.sort(key=lambda item: item.name)
    manifests.sort(key=lambda item: cast(str, item["name"]))
    return rules, {"ratios": manifests, "schema_version": RATIO_POLICY_SCHEMA}


def _fact_key(
    concept: str, period: str, unit: str, dimensions: Sequence[tuple[str, str]]
) -> str:
    return canonical_json(
        {
            "concept": concept,
            "dimensions": dict(dimensions),
            "period": json.loads(period),
            "unit": unit,
        }
    )


def _index_facts(report: Mapping[str, object]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for index, value in enumerate(_list(report.get("facts"), "report.facts")):
        field = f"report.facts[{index}]"
        fact = _mapping(value, field)
        period = canonical_json(_period(fact.get("period"), f"{field}.period"))
        dimensions = _dimensions(fact.get("dimensions"), f"{field}.dimensions")
        concept = _string(fact.get("concept"), f"{field}.concept")
        unit = _string(fact.get("unit"), f"{field}.unit")
        _decimal(fact.get("value"), f"{field}.value")
        _string(fact.get("source_locator"), f"{field}.source_locator")
        key = _fact_key(concept, period, unit, dimensions)
        if key in indexed:
            raise ValidationError("report contains duplicate normalized fact identity")
        indexed[key] = copy.deepcopy(fact)
    return indexed


def _fact_reference(fact: Mapping[str, object]) -> dict[str, object]:
    return {
        "concept": fact["concept"],
        "source_locator": fact["source_locator"],
        "value": fact["value"],
    }


def _missing_reason(numerator: object | None, denominator: object | None) -> str:
    if numerator is None and denominator is None:
        return "missing_numerator_and_denominator"
    if numerator is None:
        return "missing_numerator"
    return "missing_denominator"


def evaluate_ratio_policy(
    report: Mapping[str, object], policy: Mapping[str, object]
) -> dict[str, object]:
    """Evaluate exact, explicit ratio rules against a verified normalized report."""

    verified = _verify_report(report)
    rules, policy_manifest = _parse_rules(policy)
    facts = _index_facts(verified)
    results: list[dict[str, object]] = []
    counts = {"computed": 0, "insufficient_evidence": 0}

    for rule in rules:
        numerator = facts.get(
            _fact_key(rule.numerator_concept, rule.period, rule.unit, rule.dimensions)
        )
        denominator = facts.get(
            _fact_key(rule.denominator_concept, rule.period, rule.unit, rule.dimensions)
        )
        if numerator is None or denominator is None:
            reason = _missing_reason(numerator, denominator)
            if rule.on_missing == "error":
                raise ValidationError(
                    f"ratio {rule.name!r} cannot be computed: {reason}"
                )
            counts["insufficient_evidence"] += 1
            results.append(
                {"name": rule.name, "reason": reason, "status": "insufficient_evidence"}
            )
            continue

        numerator_value = _decimal(
            numerator.get("value"), f"ratio {rule.name}.numerator"
        )
        denominator_value = _decimal(
            denominator.get("value"), f"ratio {rule.name}.denominator"
        )
        if denominator_value.is_zero():
            if rule.on_zero_denominator == "error":
                raise ValidationError(
                    f"ratio {rule.name!r} cannot be computed: zero_denominator"
                )
            counts["insufficient_evidence"] += 1
            results.append(
                {
                    "denominator": _fact_reference(denominator),
                    "name": rule.name,
                    "numerator": _fact_reference(numerator),
                    "reason": "zero_denominator",
                    "status": "insufficient_evidence",
                }
            )
            continue

        integer_places = max(
            1,
            numerator_value.adjusted() - denominator_value.adjusted() + 1,
        )
        precision = min(
            768,
            max(
                64,
                len(numerator_value.as_tuple().digits)
                + len(denominator_value.as_tuple().digits)
                + rule.decimal_places
                + 10,
                integer_places + rule.decimal_places + 10,
            ),
        )
        try:
            with localcontext() as context:
                context.prec = precision
                quantum = Decimal(1).scaleb(-rule.decimal_places)
                value = (numerator_value / denominator_value).quantize(
                    quantum, rounding=ROUND_HALF_EVEN
                )
        except InvalidOperation as error:
            raise ValidationError(
                f"ratio {rule.name!r} exceeds supported decimal precision"
            ) from error
        counts["computed"] += 1
        results.append(
            {
                "decimal_places": rule.decimal_places,
                "denominator": _fact_reference(denominator),
                "name": rule.name,
                "numerator": _fact_reference(numerator),
                "rounding": "ROUND_HALF_EVEN",
                "status": "computed",
                "value": format(value, "f"),
            }
        )

    source_lineage = _mapping(verified.get("lineage"), "report.lineage")
    result: dict[str, object] = {
        "counts": counts,
        "lineage": {
            "input_report_sha256": source_lineage["report_sha256"],
            "policy_sha256": sha256_json(policy_manifest),
            "processor": "statement-lens/0.3.0a1",
            "transformations": [
                "verify-normalized-report-lineage",
                "select-facts-by-exact-identity",
                "apply-explicit-missingness-policy",
                "divide-decimals-with-half-even-rounding",
                "sort-ratios-by-name",
            ],
        },
        "policy": policy_manifest,
        "ratios": results,
        "schema_version": RATIO_REPORT_SCHEMA,
    }
    lineage = cast(dict[str, object], result["lineage"])
    lineage["report_sha256"] = sha256_json(result)
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def evaluate_ratio_json(
    report: Mapping[str, object], policy_text: str
) -> dict[str, object]:
    """Parse a ratio policy with duplicate-key rejection and evaluate it."""

    try:
        parsed: object = json.loads(
            policy_text, object_pairs_hook=_reject_duplicate_keys
        )
    except json.JSONDecodeError as error:
        raise ValidationError(
            f"malformed ratio policy JSON at line {error.lineno}, column {error.colno}"
        ) from error
    return evaluate_ratio_policy(report, _mapping(parsed, "policy"))
