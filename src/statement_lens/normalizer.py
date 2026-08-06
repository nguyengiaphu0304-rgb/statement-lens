"""Deterministic, fail-closed normalization for synthetic statement facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import cast

INGEST_SCHEMA = "statement-lens.ingest.v1"
REPORT_SCHEMA = "statement-lens.normalized.v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class ValidationError(ValueError):
    """Raised when input cannot be normalized without ambiguity."""


@dataclass(frozen=True)
class ConceptPolicy:
    """Validation policy declared by the input taxonomy manifest."""

    name: str
    period_type: str
    units: tuple[str, ...]
    scales: tuple[int, ...]


def canonical_json(value: object) -> str:
    """Serialize JSON-compatible data deterministically."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_json(value: object) -> str:
    """Hash canonical JSON bytes."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


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


def _string_list(value: object, field: str) -> tuple[str, ...]:
    items = tuple(_string(item, field) for item in _list(value, field))
    if not items or len(items) != len(set(items)):
        raise ValidationError(f"{field} must contain unique values")
    return tuple(sorted(items))


def _integer_list(value: object, field: str) -> tuple[int, ...]:
    raw_items = _list(value, field)
    items: list[int] = []
    for item in raw_items:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValidationError(f"{field} must contain integers")
        items.append(item)
    if not items or len(items) != len(set(items)):
        raise ValidationError(f"{field} must contain unique values")
    return tuple(sorted(items))


def _date(value: object, field: str) -> date:
    text = _string(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValidationError(f"{field} must be an ISO-8601 calendar date") from error


def _timestamp(value: object, field: str) -> datetime:
    text = _string(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _decimal(value: object, scale: int, field: str) -> str:
    text = _string(value, field)
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValidationError(f"{field} must be a finite decimal string") from error
    if not parsed.is_finite():
        raise ValidationError(f"{field} must be a finite decimal string")
    scaled = parsed.scaleb(scale)
    if scaled.is_zero():
        return "0"
    return format(scaled.normalize(), "f")


def _parse_source(document: Mapping[str, object]) -> tuple[dict[str, object], datetime]:
    source = _mapping(document.get("source"), "source")
    digest = _string(source.get("sha256"), "source.sha256").lower()
    if not _DIGEST.fullmatch(digest):
        raise ValidationError("source.sha256 must be 64 lowercase hexadecimal characters")
    retrieved_at = _timestamp(source.get("retrieved_at"), "source.retrieved_at")
    normalized: dict[str, object] = {
        "license": _string(source.get("license"), "source.license"),
        "locator": _string(source.get("locator"), "source.locator"),
        "retrieved_at": _timestamp_text(retrieved_at),
        "sha256": digest,
    }
    return normalized, retrieved_at


def _parse_entity(document: Mapping[str, object]) -> dict[str, object]:
    entity = _mapping(document.get("entity"), "entity")
    return {
        "identifier": _string(entity.get("identifier"), "entity.identifier"),
        "identifier_scheme": _string(entity.get("identifier_scheme"), "entity.identifier_scheme"),
        "legal_name": _string(entity.get("legal_name"), "entity.legal_name"),
    }


def _parse_filing(
    document: Mapping[str, object], retrieved_at: datetime
) -> tuple[dict[str, object], date]:
    filing = _mapping(document.get("filing"), "filing")
    filed_at = _timestamp(filing.get("filed_at"), "filing.filed_at")
    report_date = _date(filing.get("report_date"), "filing.report_date")
    if filed_at > retrieved_at:
        raise ValidationError("filing.filed_at cannot be later than source.retrieved_at")
    if report_date > filed_at.date():
        raise ValidationError("filing.report_date cannot be later than filing.filed_at")
    normalized: dict[str, object] = {
        "accession": _string(filing.get("accession"), "filing.accession"),
        "filed_at": _timestamp_text(filed_at),
        "form": _string(filing.get("form"), "filing.form"),
        "report_date": report_date.isoformat(),
    }
    return normalized, report_date


def _parse_taxonomy(document: Mapping[str, object]) -> dict[str, ConceptPolicy]:
    taxonomy = _mapping(document.get("taxonomy"), "taxonomy")
    concepts: dict[str, ConceptPolicy] = {}
    for index, raw in enumerate(_list(taxonomy.get("concepts"), "taxonomy.concepts")):
        item = _mapping(raw, f"taxonomy.concepts[{index}]")
        name = _string(item.get("name"), f"taxonomy.concepts[{index}].name")
        period_type = _string(item.get("period_type"), f"taxonomy.concepts[{index}].period_type")
        if period_type not in {"instant", "duration"}:
            raise ValidationError(f"taxonomy concept {name!r} has unsupported period_type")
        if name in concepts:
            raise ValidationError(f"taxonomy concept {name!r} is declared more than once")
        concepts[name] = ConceptPolicy(
            name=name,
            period_type=period_type,
            units=_string_list(item.get("units"), f"taxonomy.concepts[{index}].units"),
            scales=_integer_list(
                item.get("allowed_scales"),
                f"taxonomy.concepts[{index}].allowed_scales",
            ),
        )
    if not concepts:
        raise ValidationError("taxonomy.concepts must not be empty")
    return concepts


def _parse_period(value: object, expected_type: str, field: str) -> dict[str, object]:
    period = _mapping(value, field)
    kind = _string(period.get("kind"), f"{field}.kind")
    if kind != expected_type:
        raise ValidationError(f"{field}.kind must be {expected_type!r} for this concept")
    if kind == "instant":
        if period.get("start") is not None or period.get("end") is not None:
            raise ValidationError(f"{field} instant cannot include start or end")
        return {
            "instant": _date(period.get("instant"), f"{field}.instant").isoformat(),
            "kind": kind,
        }
    if period.get("instant") is not None:
        raise ValidationError(f"{field} duration cannot include instant")
    start = _date(period.get("start"), f"{field}.start")
    end = _date(period.get("end"), f"{field}.end")
    if end < start:
        raise ValidationError(f"{field}.end cannot precede {field}.start")
    return {"end": end.isoformat(), "kind": kind, "start": start.isoformat()}


def _parse_dimensions(value: object, field: str) -> dict[str, str]:
    if value is None:
        return {}
    raw = _mapping(value, field)
    normalized: dict[str, str] = {}
    for axis, member in raw.items():
        normalized[_string(axis, f"{field}.axis")] = _string(member, f"{field}.{axis}")
    return dict(sorted(normalized.items()))


def _parse_fact(
    raw: object,
    index: int,
    concepts: Mapping[str, ConceptPolicy],
    report_date: date,
) -> tuple[str, dict[str, object]]:
    field = f"facts[{index}]"
    fact = _mapping(raw, field)
    concept_name = _string(fact.get("concept"), f"{field}.concept")
    policy = concepts.get(concept_name)
    if policy is None:
        raise ValidationError(f"{field}.concept {concept_name!r} is not declared by taxonomy")
    unit = _string(fact.get("unit"), f"{field}.unit")
    if unit not in policy.units:
        raise ValidationError(f"{field}.unit {unit!r} is not allowed for {concept_name!r}")
    scale_value = fact.get("scale")
    if isinstance(scale_value, bool) or not isinstance(scale_value, int):
        raise ValidationError(f"{field}.scale must be an integer")
    if scale_value not in policy.scales:
        raise ValidationError(f"{field}.scale {scale_value!r} is not allowed for {concept_name!r}")
    period = _parse_period(fact.get("period"), policy.period_type, f"{field}.period")
    period_end_text = cast(str, period.get("instant", period.get("end")))
    if date.fromisoformat(period_end_text) > report_date:
        raise ValidationError(f"{field}.period cannot end after filing.report_date")
    normalized: dict[str, object] = {
        "concept": concept_name,
        "dimensions": _parse_dimensions(fact.get("dimensions"), f"{field}.dimensions"),
        "period": period,
        "source_locator": _string(fact.get("source_locator"), f"{field}.source_locator"),
        "unit": unit,
        "value": _decimal(fact.get("value"), scale_value, f"{field}.value"),
    }
    identity = canonical_json(
        {
            "concept": normalized["concept"],
            "dimensions": normalized["dimensions"],
            "period": normalized["period"],
            "unit": normalized["unit"],
        }
    )
    return identity, normalized


def normalize_document(document: Mapping[str, object]) -> dict[str, object]:
    """Validate and normalize an ingestion document into a deterministic report."""

    schema_version = _string(document.get("schema_version"), "schema_version")
    if schema_version != INGEST_SCHEMA:
        raise ValidationError(f"unsupported schema_version {schema_version!r}")

    source, retrieved_at = _parse_source(document)
    entity = _parse_entity(document)
    filing, report_date = _parse_filing(document, retrieved_at)
    concepts = _parse_taxonomy(document)

    facts_by_identity: dict[str, dict[str, object]] = {}
    facts_input = _list(document.get("facts"), "facts")
    if not facts_input:
        raise ValidationError("facts must not be empty")
    for index, raw in enumerate(facts_input):
        identity, normalized = _parse_fact(raw, index, concepts, report_date)
        existing = facts_by_identity.get(identity)
        if existing is not None:
            if canonical_json(existing) == canonical_json(normalized):
                continue
            raise ValidationError(f"conflicting duplicate fact identity at facts[{index}]")
        facts_by_identity[identity] = normalized

    normalized_facts = [facts_by_identity[key] for key in sorted(facts_by_identity)]
    taxonomy_manifest = [
        {
            "allowed_scales": list(policy.scales),
            "name": policy.name,
            "period_type": policy.period_type,
            "units": list(policy.units),
        }
        for policy in sorted(concepts.values(), key=lambda item: item.name)
    ]
    semantic_input: dict[str, object] = {
        "entity": entity,
        "facts": normalized_facts,
        "filing": filing,
        "schema_version": schema_version,
        "source": source,
        "taxonomy": taxonomy_manifest,
    }
    report: dict[str, object] = {
        "entity": entity,
        "facts": normalized_facts,
        "filing": filing,
        "lineage": {
            "input_sha256": sha256_json(semantic_input),
            "normalizer": "statement-lens/0.1.0",
            "transformations": [
                "validate-v1-schema",
                "apply-explicit-decimal-scale",
                "canonicalize-periods-and-dimensions",
                "deduplicate-identical-facts",
                "sort-facts-by-identity",
            ],
        },
        "schema_version": REPORT_SCHEMA,
        "source": source,
    }
    lineage = cast(dict[str, object], report["lineage"])
    lineage["report_sha256"] = sha256_json(report)
    return report


def normalize_json(text: str) -> dict[str, object]:
    """Parse JSON and normalize it, returning a machine-readable report."""

    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValidationError(
            f"malformed JSON at line {error.lineno}, column {error.colno}"
        ) from error
    return normalize_document(_mapping(parsed, "document"))
