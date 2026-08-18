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

- [x] Versioned concept mappings with traceable transformation rules.
- [x] Balance-sheet and cash-flow reconciliation gates.
- [x] Exact-identity ratio computation with denominator, unit, period, dimensions, precision, missingness and zero-denominator policies.
- [x] Deterministic ratio CLI, synthetic fixtures, failure-path tests and policy/input/output lineage.

The ratio policy landed in `v0.3.0a1`; mapping and reconciliation form `v0.3.0a2`. Both alphas are verified together in the v1.0 release candidate.

## v1.0 — reproducible portfolio release

- [x] Bounded inputs and deterministic, independently replayed synthetic evidence.
- [x] Reproducible wheel and canonical sdist with strict offline archive verification.
- [x] Checksums, publication procedure, support/recovery matrix and residual-risk review.
- [ ] Annotated public tag, non-prerelease GitHub Release and independently re-downloaded assets.

Artifact signing and a respectful public-data adapter remain explicitly deferred. SHA-256 proves byte
integrity but not publisher identity; a live adapter requires source-specific licensing, rate-limit,
availability and correction semantics before it can enter scope.

Each milestone requires its own issue, acceptance criteria, failure-path tests and reviewable pull request. Live data will not be added before provenance and availability semantics are testable.
