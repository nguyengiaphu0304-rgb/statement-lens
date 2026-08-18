"""Deterministic accounting mappings and reconciliation gates."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, localcontext
from typing import cast

from statement_lens.normalizer import (
    REPORT_SCHEMA,
    ValidationError,
    canonical_json,
    normalize_document,
    sha256_json,
)

ACCOUNTING_INPUT_SCHEMA = "statement-lens.accounting-input.v1"
ACCOUNTING_POLICY_SCHEMA = "statement-lens.accounting-policy.v1"
ACCOUNTING_REPORT_SCHEMA = "statement-lens.accounting-report.v1"
MAX_POLICY_RULES = 100
MAX_TEXT_LENGTH = 256
MAX_DECIMAL_LENGTH = 600
MAX_ABSOLUTE_ADJUSTED_EXPONENT = 256


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
    text = value.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise ValidationError(f"{field} exceeds {MAX_TEXT_LENGTH} characters")
    return text


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty decimal string")
    text = value.strip()
    if len(text) > MAX_DECIMAL_LENGTH:
        raise ValidationError(f"{field} exceeds {MAX_DECIMAL_LENGTH} characters")
    try:
        result = Decimal(text)
    except InvalidOperation as error:
        raise ValidationError(f"{field} must be a finite decimal string") from error
    if not result.is_finite():
        raise ValidationError(f"{field} must be a finite decimal string")
    if abs(result.adjusted()) > MAX_ABSOLUTE_ADJUSTED_EXPONENT:
        raise ValidationError(f"{field} adjusted exponent exceeds {MAX_ABSOLUTE_ADJUSTED_EXPONENT}")
    return result


def _decimal_text(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _sum_decimals(values: list[Decimal]) -> Decimal:
    integer_places = max(max(value.adjusted() + 1, 0) for value in values)
    fractional_places = max(max(-cast(int, value.as_tuple().exponent), 0) for value in values)
    precision = max(
        28,
        integer_places + fractional_places + len(str(len(values))) + 2,
        max(len(value.as_tuple().digits) for value in values) + len(str(len(values))) + 2,
    )
    with localcontext() as context:
        context.prec = precision
        return sum(values, Decimal(0))


def _require_keys(value: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise ValidationError(f"{field} contains missing or unknown fields")


def _verify_report(report: Mapping[str, object]) -> None:
    if report.get("schema_version") != REPORT_SCHEMA:
        raise ValidationError("unsupported normalized report schema_version")
    lineage = _mapping(report.get("lineage"), "report.lineage")
    expected = _string(lineage.get("report_sha256"), "report.lineage.report_sha256")
    unsigned = copy.deepcopy(dict(report))
    unsigned_lineage = _mapping(unsigned.get("lineage"), "report.lineage")
    unsigned_lineage.pop("report_sha256", None)
    if sha256_json(unsigned) != expected:
        raise ValidationError("normalized report_sha256 does not match report content")


def _period_type(fact: Mapping[str, object]) -> str:
    period = _mapping(fact.get("period"), "fact.period")
    return _string(period.get("kind"), "fact.period.kind")


def _parse_policy(policy: Mapping[str, object]) -> dict[str, object]:
    if policy.get("schema_version") != ACCOUNTING_POLICY_SCHEMA:
        raise ValidationError("unsupported accounting policy schema_version")
    expected_policy_keys = {"aggregations", "mappings", "reconciliations", "schema_version"}
    if set(policy) != expected_policy_keys:
        raise ValidationError("accounting policy contains missing or unknown fields")

    mappings: list[dict[str, object]] = []
    source_seen: set[str] = set()
    rule_seen: set[str] = set()
    canonical_sources: dict[str, set[str]] = {}
    raw_mappings = _list(policy.get("mappings"), "policy.mappings")
    if not 1 <= len(raw_mappings) <= MAX_POLICY_RULES:
        raise ValidationError(f"policy.mappings must contain 1 to {MAX_POLICY_RULES} rules")
    for index, raw in enumerate(raw_mappings):
        item = _mapping(raw, f"policy.mappings[{index}]")
        _require_keys(
            item,
            {
                "canonical_concept",
                "period_type",
                "role",
                "rule_id",
                "source_concept",
                "statement",
                "unit",
            },
            f"policy.mappings[{index}]",
        )
        rule_id = _string(item.get("rule_id"), f"policy.mappings[{index}].rule_id")
        source = _string(item.get("source_concept"), f"policy.mappings[{index}].source_concept")
        canonical = _string(
            item.get("canonical_concept"), f"policy.mappings[{index}].canonical_concept"
        )
        period_type = _string(item.get("period_type"), f"policy.mappings[{index}].period_type")
        if period_type not in {"instant", "duration"}:
            raise ValidationError(f"mapping {rule_id!r} has unsupported period_type")
        role = _string(item.get("role"), f"policy.mappings[{index}].role")
        if role not in {"primary", "component"}:
            raise ValidationError(f"mapping {rule_id!r} has unsupported role")
        if source in source_seen:
            raise ValidationError(f"source concept {source!r} is mapped more than once")
        if rule_id in rule_seen:
            raise ValidationError(f"mapping rule_id {rule_id!r} is duplicated")
        source_seen.add(source)
        rule_seen.add(rule_id)
        canonical_sources.setdefault(canonical, set()).add(source)
        mappings.append(
            {
                "canonical_concept": canonical,
                "period_type": period_type,
                "role": role,
                "rule_id": rule_id,
                "source_concept": source,
                "statement": _string(item.get("statement"), f"policy.mappings[{index}].statement"),
                "unit": _string(item.get("unit"), f"policy.mappings[{index}].unit"),
            }
        )
    aggregations: list[dict[str, object]] = []
    aggregation_by_canonical: dict[str, set[str]] = {}
    raw_aggregations = _list(policy.get("aggregations", []), "policy.aggregations")
    if len(raw_aggregations) > MAX_POLICY_RULES:
        raise ValidationError(f"policy.aggregations exceeds {MAX_POLICY_RULES} rules")
    for index, raw in enumerate(raw_aggregations):
        item = _mapping(raw, f"policy.aggregations[{index}]")
        _require_keys(
            item,
            {"canonical_concept", "operation", "rule_id", "source_concepts"},
            f"policy.aggregations[{index}]",
        )
        canonical = _string(
            item.get("canonical_concept"), f"policy.aggregations[{index}].canonical_concept"
        )
        aggregation_sources = tuple(
            sorted(
                _string(value, f"policy.aggregations[{index}].source_concepts")
                for value in _list(
                    item.get("source_concepts"),
                    f"policy.aggregations[{index}].source_concepts",
                )
            )
        )
        if len(aggregation_sources) < 2 or len(aggregation_sources) != len(
            set(aggregation_sources)
        ):
            raise ValidationError("aggregation source_concepts must contain unique inputs")
        if canonical in aggregation_by_canonical:
            raise ValidationError(f"canonical concept {canonical!r} has multiple aggregations")
        operation = _string(item.get("operation"), f"policy.aggregations[{index}].operation")
        if operation != "sum":
            raise ValidationError(f"aggregation {canonical!r} has unsupported operation")
        rule_id = _string(item.get("rule_id"), f"policy.aggregations[{index}].rule_id")
        if rule_id in rule_seen:
            raise ValidationError(f"transformation rule_id {rule_id!r} is duplicated")
        rule_seen.add(rule_id)
        aggregation_by_canonical[canonical] = set(aggregation_sources)
        aggregations.append(
            {
                "canonical_concept": canonical,
                "operation": operation,
                "rule_id": rule_id,
                "source_concepts": list(aggregation_sources),
            }
        )

    for canonical, sources in canonical_sources.items():
        if len(sources) > 1 and aggregation_by_canonical.get(canonical) != sources:
            raise ValidationError(
                f"many-to-one mapping for {canonical!r} requires an exact aggregation declaration"
            )
    for canonical, sources in aggregation_by_canonical.items():
        if canonical_sources.get(canonical) != sources:
            raise ValidationError(
                f"aggregation for {canonical!r} must name exactly its mapped source concepts"
            )

    reconciliations: list[dict[str, object]] = []
    reconciliation_names: set[str] = set()
    raw_reconciliations = _list(policy.get("reconciliations"), "policy.reconciliations")
    if not 1 <= len(raw_reconciliations) <= MAX_POLICY_RULES:
        raise ValidationError(f"policy.reconciliations must contain 1 to {MAX_POLICY_RULES} rules")
    for index, raw in enumerate(raw_reconciliations):
        item = _mapping(raw, f"policy.reconciliations[{index}]")
        _require_keys(
            item,
            {"left", "name", "right", "tolerance"},
            f"policy.reconciliations[{index}]",
        )
        name = _string(item.get("name"), f"policy.reconciliations[{index}].name")
        if name in reconciliation_names:
            raise ValidationError(f"reconciliation {name!r} is duplicated")
        reconciliation_names.add(name)
        right = sorted(
            _string(value, f"policy.reconciliations[{index}].right")
            for value in _list(item.get("right"), f"policy.reconciliations[{index}].right")
        )
        left = _string(item.get("left"), f"policy.reconciliations[{index}].left")
        if not right or len(right) != len(set(right)) or left in right:
            raise ValidationError(f"reconciliation {name!r} must have unique right-hand concepts")
        tolerance = _decimal(item.get("tolerance"), f"policy.reconciliations[{index}].tolerance")
        if tolerance < 0:
            raise ValidationError(f"reconciliation {name!r} tolerance cannot be negative")
        reconciliations.append(
            {
                "left": left,
                "name": name,
                "right": right,
                "tolerance": _decimal_text(tolerance),
            }
        )

    return {
        "aggregations": sorted(aggregations, key=lambda item: cast(str, item["canonical_concept"])),
        "mappings": sorted(mappings, key=lambda item: cast(str, item["source_concept"])),
        "reconciliations": sorted(reconciliations, key=lambda item: cast(str, item["name"])),
        "schema_version": ACCOUNTING_POLICY_SCHEMA,
    }


def _map_facts(
    report: Mapping[str, object], policy: Mapping[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    facts_by_source: dict[str, dict[str, object]] = {}
    for raw in _list(report.get("facts"), "report.facts"):
        fact = _mapping(raw, "report.fact")
        concept = _string(fact.get("concept"), "report.fact.concept")
        if concept in facts_by_source:
            raise ValidationError(
                f"source concept {concept!r} has multiple contexts and cannot be mapped "
                "unambiguously"
            )
        facts_by_source[concept] = fact

    rules = {
        cast(str, item["source_concept"]): item
        for item in cast(list[dict[str, object]], policy["mappings"])
    }
    grouped: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = {}
    unmapped: list[dict[str, object]] = []
    for source, fact in sorted(facts_by_source.items()):
        rule = rules.get(source)
        if rule is None:
            unmapped.append(
                {
                    "source_concept": source,
                    "source_locator": fact["source_locator"],
                }
            )
            continue
        if fact.get("unit") != rule["unit"]:
            raise ValidationError(f"mapped fact {source!r} does not match declared unit")
        if _period_type(fact) != rule["period_type"]:
            raise ValidationError(f"mapped fact {source!r} does not match declared period_type")
        dimensions = _mapping(fact.get("dimensions"), "fact.dimensions")
        if dimensions:
            raise ValidationError(f"mapped fact {source!r} has dimensions that require a selector")
        grouped.setdefault(cast(str, rule["canonical_concept"]), []).append((rule, fact))

    aggregation_by_canonical = {
        cast(str, item["canonical_concept"]): item
        for item in cast(list[dict[str, object]], policy["aggregations"])
    }
    mapped: list[dict[str, object]] = []
    for canonical, members in sorted(grouped.items()):
        first_fact = members[0][1]
        if len(members) > 1:
            aggregation = aggregation_by_canonical.get(canonical)
            if aggregation is None:
                raise ValidationError(f"canonical concept {canonical!r} is ambiguous")
            for _, fact in members[1:]:
                if fact["unit"] != first_fact["unit"] or canonical_json(
                    fact["period"]
                ) != canonical_json(first_fact["period"]):
                    raise ValidationError(f"aggregation {canonical!r} mixes units or periods")
        value = _sum_decimals([_decimal(fact["value"], "fact.value") for _, fact in members])
        sources = [
            {
                "rule_id": rule["rule_id"],
                "source_concept": rule["source_concept"],
                "source_locator": fact["source_locator"],
                "value": fact["value"],
            }
            for rule, fact in sorted(members, key=lambda item: cast(str, item[0]["source_concept"]))
        ]
        mapped.append(
            {
                "aggregation_rule_id": (
                    aggregation_by_canonical[canonical]["rule_id"] if len(members) > 1 else None
                ),
                "canonical_concept": canonical,
                "period": first_fact["period"],
                "sources": sources,
                "unit": first_fact["unit"],
                "value": _decimal_text(value),
            }
        )
    return mapped, unmapped


def _reconcile(
    definitions: list[dict[str, object]], facts: Mapping[str, dict[str, object]]
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for definition in definitions:
        left_name = cast(str, definition["left"])
        right_names = cast(list[str], definition["right"])
        required = [left_name, *right_names]
        missing = sorted(name for name in required if name not in facts)
        base: dict[str, object] = {
            "left": left_name,
            "name": definition["name"],
            "right": right_names,
            "tolerance": definition["tolerance"],
        }
        if missing:
            base.update({"difference": None, "missing": missing, "status": "insufficient_evidence"})
            results.append(base)
            continue
        selected = [facts[name] for name in required]
        if len({cast(str, fact["unit"]) for fact in selected}) != 1:
            raise ValidationError(f"reconciliation {definition['name']!r} mixes units")
        if len({canonical_json(fact["period"]) for fact in selected}) != 1:
            raise ValidationError(f"reconciliation {definition['name']!r} mixes periods")
        left = _decimal(facts[left_name]["value"], "reconciliation.left")
        right_values = [
            _decimal(facts[name]["value"], "reconciliation.right") for name in right_names
        ]
        right = _sum_decimals(right_values)
        difference = _sum_decimals([left, -right])
        tolerance = _decimal(definition["tolerance"], "reconciliation.tolerance")
        base.update(
            {
                "difference": _decimal_text(difference),
                "missing": [],
                "status": "pass" if abs(difference) <= tolerance else "fail",
            }
        )
        results.append(base)
    return results


def analyze_report(report: Mapping[str, object], policy: Mapping[str, object]) -> dict[str, object]:
    """Apply a bounded accounting policy to a verified normalized report."""

    _verify_report(report)
    normalized_policy = _parse_policy(policy)
    mapped, unmapped = _map_facts(report, normalized_policy)
    by_canonical = {cast(str, fact["canonical_concept"]): fact for fact in mapped}
    reconciliations = _reconcile(
        cast(list[dict[str, object]], normalized_policy["reconciliations"]), by_canonical
    )
    report_lineage = _mapping(report.get("lineage"), "report.lineage")
    result: dict[str, object] = {
        "entity": report["entity"],
        "filing": report["filing"],
        "lineage": {
            "accounting_engine": "statement-lens/0.3.0a2",
            "mapped_facts_sha256": sha256_json(mapped),
            "normalized_report_sha256": report_lineage["report_sha256"],
            "policy_sha256": sha256_json(normalized_policy),
        },
        "mapped_facts": mapped,
        "reconciliations": reconciliations,
        "schema_version": ACCOUNTING_REPORT_SCHEMA,
        "unmapped_facts": unmapped,
    }
    lineage = _mapping(result["lineage"], "lineage")
    lineage["report_sha256"] = sha256_json(result)
    return result


def analyze_document(value: Mapping[str, object]) -> dict[str, object]:
    """Normalize an ingestion document and apply its explicit accounting policy."""

    if value.get("schema_version") != ACCOUNTING_INPUT_SCHEMA:
        raise ValidationError("unsupported accounting input schema_version")
    if set(value) != {"document", "policy", "schema_version"}:
        raise ValidationError("accounting input contains missing or unknown fields")
    document = _mapping(value.get("document"), "document")
    policy = _mapping(value.get("policy"), "policy")
    return analyze_report(normalize_document(document), policy)


def analyze_json(text: str) -> dict[str, object]:
    """Parse and analyze an accounting input document."""

    try:
        parsed: object = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ValidationError(
            f"malformed JSON at line {error.lineno}, column {error.colno}"
        ) from error
    return analyze_document(_mapping(parsed, "accounting input"))
