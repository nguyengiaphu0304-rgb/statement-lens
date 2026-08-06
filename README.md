# Statement Lens

Statement Lens is a provenance-first toolkit for normalizing financial-statement facts into deterministic, auditable reports. The current `v0.1` foundation works entirely offline with synthetic data and fails closed when provenance, periods, concepts, units, scale, or duplicate identities are ambiguous.

> **Educational software only.** Statement Lens is not financial advice, accounting assurance, an SEC filing parser, or a production reporting control. The included evidence is synthetic and makes no performance or investability claim.

## What works

- Versioned ingestion and normalized-report schemas.
- Explicit source locator, SHA-256 digest, retrieval timestamp, license, filing accession, entity, period, unit, scale and transformation lineage.
- Decimal parsing without binary floating-point conversion.
- Separate instant and duration periods with filing-time boundaries.
- Taxonomy-declared units and allowed scales.
- Deterministic fact identity, identical-duplicate collapse and fail-closed conflict detection.
- Canonical JSON plus input/report SHA-256 lineage independent of fact or taxonomy input order.
- Machine-readable CLI errors and deterministic offline replay.

## Quick start

Requirements: Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
uv run statement-lens fixtures/synthetic_statement.json --output report.json
```

The fixture is CC0 and deliberately synthetic. Its source digest is the SHA-256 of the documented synthetic source marker, not a downloaded filing.

## Verification

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
uv run statement-lens fixtures/synthetic_statement.json --output report.json
uv run statement-lens fixtures/synthetic_statement.json --output report-replay.json
cmp report.json report-replay.json
uv build
uv pip check
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file runtime-requirements.txt
uv run pip-audit --requirement runtime-requirements.txt --strict
```

## Architecture and trust boundaries

Input JSON flows through schema validation, provenance checks, explicit decimal scaling, period/unit policy, identity-aware deduplication, canonical ordering and lineage hashing. It never makes a network request. See [architecture](docs/architecture.md), [data model](docs/data-model.md), [threat model](docs/threat-model.md) and [ADR-001](docs/adr/001-provenance-first-offline-core.md).

## Limits

- No live SEC/EDGAR adapter, Inline XBRL rendering, taxonomy package resolver, or source-digest downloader.
- No ratio computation, accounting reconciliation, restatement diff, currency conversion, audit opinion, market data, forecasting, or investment recommendation.
- Taxonomy policies are explicit input manifests; they are not authoritative GAAP/IFRS validation.
- SHA-256 lineage detects changed bytes but does not authenticate who supplied them.
- The first milestone supports one filing per ingestion document. Distinct accessions remain distinct when independently normalized.

See the [roadmap](docs/roadmap.md) for deliberately staged follow-up work and the [interview guide](docs/interview-guide.md) for design trade-offs.

## License

Code is MIT licensed. The included synthetic fixture is CC0-1.0.

