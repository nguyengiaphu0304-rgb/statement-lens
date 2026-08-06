# Threat model

## Protected properties

- No silent loss of source provenance or filing identity.
- No floating-point drift in statement values.
- No survivor-style averaging or investment-performance claim.
- Deterministic replay for the same semantic input.
- Fail-closed behavior for ambiguous duplicates, concepts, periods, units and scales.

## Untrusted inputs

JSON structure, timestamps, identifiers, taxonomy policies, fact values, source locators and digests are untrusted. The normalizer bounds them by schema and invariant checks but does not authenticate a publisher or verify that a supplied digest matches remote bytes.

## Current mitigations

- Offline core with no URL fetching, shell execution, dynamic imports or templating.
- Version gate rejects unknown schemas.
- Timezone-aware filing/retrieval boundaries.
- Decimal finite-value checks reject NaN and infinity.
- Canonical identity and report hashes expose semantic changes.
- Conflicting duplicates abort the document.
- CI exercises supported Python versions, strict typing, lint, tests, build, replay and dependency audit.

## Residual risks

Input sizes are not yet bounded for hostile bulk ingestion. SHA-256 proves equality, not authenticity. Taxonomy policies may be wrong. Unicode confusables, identifier registry checks, signed provenance, resource limits and parser fuzzing remain future work. Do not use this release as an accounting, regulatory or trading control.

