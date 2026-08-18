# ADR-004: Explicit, fail-closed accounting mapping

Status: accepted

## Context

Raw taxonomy concepts do not automatically have one canonical accounting meaning. Many-to-one mappings can hide detail, and missing facts can be mistaken for zero during reconciliation.

## Decision

Accounting transformations use a versioned input policy. Every mapping declares a rule ID, source concept, canonical concept, statement, role, period type and unit. A source maps once. Many sources can map to one canonical concept only when an aggregation names the exact inputs and uses Decimal summation. Dimensional or multi-context facts fail until a selector is explicit.

Reconciliations require a left concept, right-hand concepts and non-negative tolerance. Missing inputs yield `insufficient_evidence`, while complete inputs yield `pass` or `fail`. Units and periods must match. Normalized input, policy, mapped facts and output are hashed separately. Ratio evaluation remains a separate exact-identity policy boundary under ADR-003.

## Consequences

Every output number can be traced to source locators and policy rules, and incomplete evidence cannot silently become a successful control. Callers must maintain correct mapping policy. The engine is intentionally not a taxonomy authority, dimensional selector, audit opinion or open-ended formula language.
