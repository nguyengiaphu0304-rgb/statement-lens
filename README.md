# Statement Lens

Statement Lens is a provenance-first toolkit for normalizing financial-statement facts, comparing filing history and evaluating explicitly declared ratios through deterministic, auditable reports. The current `v0.3.0a1` milestone works entirely offline with synthetic data and fails closed when provenance, availability, identity, period, unit, scale, missingness or ratio policy is ambiguous.

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
- Explicit base/comparison accession selection with timezone-aware `as_of` cutoffs.
- Multi-filing history that rejects mixed entities, tampered reports and conflicting accessions.
- Fact-level `added`, `removed`, `changed` and `unchanged` classifications retaining both sides' provenance.
- Canonical history, policy, input and report SHA-256 lineage independent of input order.\n- Exact-identity ratio selection with explicit period, unit, dimensions, precision, missingness and zero-denominator policies.\n- Decimal-only ratio arithmetic with declared `ROUND_HALF_EVEN` rounding and policy/input/output lineage.

## Quick start

Requirements: Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
uv run statement-lens fixtures/synthetic_statement.json --output report.json
uv run statement-lens fixtures/synthetic_restatement.json \
  --base-accession 0000000000-25-000001 \
  --comparison-accession 0000000000-25-000002 \
  --as-of 2025-03-02T00:00:00Z \
  --output restatement.json
```

The fixtures are CC0 and deliberately synthetic. Their source digests are documented synthetic markers, not downloaded filings.

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

Input JSON flows through schema validation, provenance checks, explicit decimal scaling, period/unit policy, identity-aware deduplication, canonical ordering and lineage hashing. Ratio evaluation separately verifies that normalized lineage, selects facts only by exact identity and applies a versioned policy. Neither path makes a network request. See [architecture](docs/architecture.md), [data model](docs/data-model.md), [threat model](docs/threat-model.md), [ADR-001](docs/adr/001-provenance-first-offline-core.md) and [ADR-003](docs/adr/003-explicit-ratio-policy.md).

## Limits

- No live SEC/EDGAR adapter, Inline XBRL rendering, taxonomy package resolver, or source-digest downloader.
- No authoritative concept mapping, accounting reconciliation, currency conversion, audit opinion, market data, forecasting, or investment recommendation.\n- The ratio engine evaluates exact declared identities only; it does not decide whether a ratio is financially meaningful or comparable across entities.
- Taxonomy policies are explicit input manifests; they are not authoritative GAAP/IFRS validation.
- SHA-256 lineage detects changed bytes but does not authenticate who supplied them.
- History is bounded to 100 filings and 10,000 facts per filing, but individual text-field lengths are not yet bounded.
- A restatement classification is a structural diff, not a judgment about accounting materiality or correctness.

See the [roadmap](docs/roadmap.md) for deliberately staged follow-up work and the [interview guide](docs/interview-guide.md) for design trade-offs.

## License

Code is MIT licensed. The included synthetic fixture is CC0-1.0.
