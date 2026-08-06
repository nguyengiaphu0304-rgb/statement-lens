"""Deterministic filing history and restatement comparison."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import cast

from statement_lens.normalizer import (
    REPORT_SCHEMA,
    ValidationError,
    canonical_json,
    normalize_document,
    sha256_json,
)

HISTORY_INPUT_SCHEMA = "statement-lens.history-input.v1"
RESTATEMENT_SCHEMA = "statement-lens.restatement.v1"
MAX_FILINGS = 100
MAX_FACTS_PER_FILING = 10_000


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


def _verify_report(value: object, index: int) -> dict[str, object]:
    field = f"reports[{index}]"
    report = _mapping(value, field)
    if report.get("schema_version") != REPORT_SCHEMA:
        raise ValidationError(f"{field} has unsupported schema_version")
    filing = _mapping(report.get("filing"), f"{field}.filing")
    source = _mapping(report.get("source"), f"{field}.source")
    facts = _list(report.get("facts"), f"{field}.facts")
    if not facts:
        raise ValidationError(f"{field}.facts must not be empty")
    if len(facts) > MAX_FACTS_PER_FILING:
        raise ValidationError(f"{field}.facts exceeds the {MAX_FACTS_PER_FILING} fact limit")
    filed_at = _timestamp(filing.get("filed_at"), f"{field}.filing.filed_at")
    retrieved_at = _timestamp(source.get("retrieved_at"), f"{field}.source.retrieved_at")
    if filed_at > retrieved_at:
        raise ValidationError(f"{field} filing cannot be available before it was filed")

    lineage = _mapping(report.get("lineage"), f"{field}.lineage")
    expected_digest = _string(lineage.get("report_sha256"), f"{field}.lineage.report_sha256")
    unsigned = copy.deepcopy(report)
    unsigned_lineage = _mapping(unsigned.get("lineage"), f"{field}.lineage")
    unsigned_lineage.pop("report_sha256", None)
    if sha256_json(unsigned) != expected_digest:
        raise ValidationError(f"{field} report_sha256 does not match report content")
    return copy.deepcopy(report)


def _fact_identity(fact: Mapping[str, object]) -> str:
    return canonical_json(
        {
            "concept": fact.get("concept"),
            "dimensions": fact.get("dimensions"),
            "period": fact.get("period"),
            "unit": fact.get("unit"),
        }
    )


def _facts_by_identity(report: Mapping[str, object], field: str) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for index, raw in enumerate(_list(report.get("facts"), f"{field}.facts")):
        fact = _mapping(raw, f"{field}.facts[{index}]")
        identity = _fact_identity(fact)
        if identity in indexed:
            raise ValidationError(f"{field} contains duplicate normalized fact identity")
        indexed[identity] = fact
    return indexed


def _filing_summary(report: Mapping[str, object]) -> dict[str, object]:
    filing = _mapping(report.get("filing"), "filing")
    source = _mapping(report.get("source"), "source")
    lineage = _mapping(report.get("lineage"), "lineage")
    facts = _list(report.get("facts"), "facts")
    return {
        "accession": filing["accession"],
        "fact_count": len(facts),
        "filed_at": filing["filed_at"],
        "form": filing["form"],
        "report_date": filing["report_date"],
        "report_sha256": lineage["report_sha256"],
        "retrieved_at": source["retrieved_at"],
        "source_sha256": source["sha256"],
    }


def compare_history(
    reports: Sequence[object],
    *,
    base_accession: str,
    comparison_accession: str,
    as_of: str,
) -> dict[str, object]:
    """Validate filing history and compare two explicitly selected accessions."""

    if not reports:
        raise ValidationError("reports must not be empty")
    if len(reports) > MAX_FILINGS:
        raise ValidationError(f"reports exceeds the {MAX_FILINGS} filing limit")
    base_accession = _string(base_accession, "base_accession")
    comparison_accession = _string(comparison_accession, "comparison_accession")
    if base_accession == comparison_accession:
        raise ValidationError("base_accession and comparison_accession must differ")
    as_of_timestamp = _timestamp(as_of, "as_of")

    reports_by_accession: dict[str, dict[str, object]] = {}
    entity_identity: str | None = None
    for index, value in enumerate(reports):
        report = _verify_report(value, index)
        entity = _mapping(report.get("entity"), f"reports[{index}].entity")
        current_entity = canonical_json(entity)
        if entity_identity is None:
            entity_identity = current_entity
        elif current_entity != entity_identity:
            raise ValidationError("reports must belong to exactly one entity")
        filing = _mapping(report.get("filing"), f"reports[{index}].filing")
        accession = _string(filing.get("accession"), f"reports[{index}].filing.accession")
        existing = reports_by_accession.get(accession)
        if existing is not None:
            if canonical_json(existing) == canonical_json(report):
                continue
            raise ValidationError(f"conflicting duplicate accession {accession!r}")
        reports_by_accession[accession] = report

    base = reports_by_accession.get(base_accession)
    comparison = reports_by_accession.get(comparison_accession)
    if base is None:
        raise ValidationError(f"base_accession {base_accession!r} is not in history")
    if comparison is None:
        raise ValidationError(f"comparison_accession {comparison_accession!r} is not in history")

    base_filing = _mapping(base["filing"], "base.filing")
    comparison_filing = _mapping(comparison["filing"], "comparison.filing")
    base_source = _mapping(base["source"], "base.source")
    comparison_source = _mapping(comparison["source"], "comparison.source")
    base_filed = _timestamp(base_filing["filed_at"], "base.filing.filed_at")
    comparison_filed = _timestamp(comparison_filing["filed_at"], "comparison.filing.filed_at")
    base_retrieved = _timestamp(base_source["retrieved_at"], "base.source.retrieved_at")
    comparison_retrieved = _timestamp(
        comparison_source["retrieved_at"], "comparison.source.retrieved_at"
    )
    if base_filed > comparison_filed or base_retrieved > comparison_retrieved:
        raise ValidationError("base filing cannot follow comparison filing in availability order")
    if base_retrieved > as_of_timestamp or comparison_retrieved > as_of_timestamp:
        raise ValidationError("selected filing was not available at as_of")

    base_facts = _facts_by_identity(base, "base")
    comparison_facts = _facts_by_identity(comparison, "comparison")
    changes: list[dict[str, object]] = []
    counts = {"added": 0, "changed": 0, "removed": 0, "unchanged": 0}
    for identity in sorted(set(base_facts) | set(comparison_facts)):
        before = base_facts.get(identity)
        after = comparison_facts.get(identity)
        if before is None:
            classification = "added"
        elif after is None:
            classification = "removed"
        elif canonical_json(before) == canonical_json(after):
            classification = "unchanged"
        else:
            classification = "changed"
        counts[classification] += 1
        changes.append(
            {
                "after": after,
                "before": before,
                "classification": classification,
                "identity": json.loads(identity),
            }
        )

    ordered_reports = [reports_by_accession[key] for key in sorted(reports_by_accession)]
    history = [_filing_summary(item) for item in ordered_reports]
    policy = {
        "availability_cutoff": "source.retrieved_at <= as_of",
        "classifications": ["added", "changed", "removed", "unchanged"],
        "fact_identity": ["concept", "period", "unit", "dimensions"],
        "selection": "explicit-accessions-only",
    }
    result: dict[str, object] = {
        "as_of": _timestamp_text(as_of_timestamp),
        "base": _filing_summary(base),
        "changes": changes,
        "comparison": _filing_summary(comparison),
        "counts": counts,
        "entity": json.loads(cast(str, entity_identity)),
        "history": history,
        "lineage": {
            "history_sha256": sha256_json(history),
            "input_sha256": sha256_json(ordered_reports),
            "policy_sha256": sha256_json(policy),
            "processor": "statement-lens/0.2.0",
            "transformations": [
                "verify-normalized-report-lineage",
                "enforce-explicit-availability-cutoff",
                "deduplicate-identical-accessions",
                "classify-facts-by-canonical-identity",
                "sort-history-and-changes",
            ],
        },
        "policy": policy,
        "schema_version": RESTATEMENT_SCHEMA,
    }
    lineage = cast(dict[str, object], result["lineage"])
    lineage["report_sha256"] = sha256_json(result)
    return result


def compare_documents(
    documents: Sequence[object],
    *,
    base_accession: str,
    comparison_accession: str,
    as_of: str,
) -> dict[str, object]:
    """Normalize ingestion documents independently before history comparison."""

    normalized = [
        normalize_document(_mapping(item, f"documents[{index}]"))
        for index, item in enumerate(documents)
    ]
    return compare_history(
        normalized,
        base_accession=base_accession,
        comparison_accession=comparison_accession,
        as_of=as_of,
    )


def compare_json(
    text: str,
    *,
    base_accession: str,
    comparison_accession: str,
    as_of: str,
) -> dict[str, object]:
    """Parse a versioned history input and produce a restatement report."""

    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValidationError(
            f"malformed JSON at line {error.lineno}, column {error.colno}"
        ) from error
    document = _mapping(parsed, "document")
    if document.get("schema_version") != HISTORY_INPUT_SCHEMA:
        raise ValidationError("unsupported history schema_version")
    documents = _list(document.get("documents"), "documents")
    return compare_documents(
        documents,
        base_accession=base_accession,
        comparison_accession=comparison_accession,
        as_of=as_of,
    )
