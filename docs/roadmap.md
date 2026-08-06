# Roadmap

## v0.1 — provenance-first ingestion foundation

- Versioned offline schema and canonical report.
- Explicit filing/source lineage and decimal/period/unit invariants.
- Deterministic fixture, CLI, tests, CI and package build.

## v0.2 — filing history and restatement change detection

- [x] Multi-filing entity history keyed by accession and availability timestamp.
- [x] Fact-level added, removed, changed and unchanged classifications.
- [x] Reproducible restatement reports without silently selecting a “latest” filing.
- [x] Normalized-report lineage verification, look-ahead cutoff and bounded history.

## v0.3 — accounting normalization and ratios

- Versioned concept mappings with traceable transformation rules.
- Balance-sheet and cash-flow reconciliation gates.
- Ratio computation with denominator, unit, period and missingness policies.

## v1.0 release candidate

- Optional respectful public-data adapter with source licensing and retrieval evidence.
- Bounded inputs, signed release artifacts and documented recovery/support matrix.
- Independent replay of release evidence and residual-risk review.

Each milestone requires its own issue, acceptance criteria, failure-path tests and reviewable pull request. Live data will not be added before provenance and availability semantics are testable.
