# Threat model

## Protected properties

- No silent loss of source provenance or filing identity.
- No floating-point drift in statement values.
- No survivor-style averaging or investment-performance claim.
- Deterministic replay for the same semantic input.
- Fail-closed behavior for ambiguous duplicates, concepts, periods, units and scales.
- No look-ahead through filings retrieved after an explicit availability cutoff.
- No silent “latest filing” choice or overwrite of conflicting accessions.
- No silent concept merge, missing-as-zero reconciliation or untraceable transformation.

## Untrusted inputs

JSON structure, timestamps, identifiers, taxonomy and mapping policies, fact values, source locators and digests are untrusted. The normalizer bounds them by schema and invariant checks but does not authenticate a publisher or verify that a supplied digest matches remote bytes.

## Current mitigations

- Offline core with no URL fetching, shell execution, dynamic imports or templating.
- Version gate rejects unknown schemas.
- Timezone-aware filing/retrieval boundaries.
- Decimal finite-value checks reject NaN and infinity.
- Canonical identity and report hashes expose semantic changes.
- Conflicting duplicates abort the document.
- Normalized-report digests are reverified before history comparison.
- Filing histories are limited to 100 reports and 10,000 facts per report.
- Accounting policy collections are limited to 100 rules, text and decimal inputs are bounded, and extreme decimal exponents are rejected.
- Many-to-one mappings require an exact aggregation declaration; dimensional and multi-context mappings fail closed.
- Missing reconciliation inputs remain `insufficient_evidence`; compatible complete inputs alone can pass or fail.
- Mixed entities, invalid availability order and future-retrieved comparisons abort.
- CI exercises supported Python versions, strict typing, lint, tests, build, replay and dependency audit.

## Residual risks

Top-level JSON byte size is not bounded before parsing. SHA-256 proves equality, not authenticity. Taxonomy and caller-supplied mapping policies may be wrong. Reconciliation is arithmetic rather than accounting assurance, and a structural fact change is not a materiality opinion. Unicode confusables, identifier registry checks, signed provenance, tighter parser limits and fuzzing remain future work. Do not use this release as an accounting, regulatory or trading control.
