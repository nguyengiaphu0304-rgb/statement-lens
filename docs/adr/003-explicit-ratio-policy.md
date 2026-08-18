# ADR 003: Require explicit, exact ratio policies

## Status

Accepted for the v0.3 alpha.

## Context

Computing a financial ratio is mechanically simple but semantically risky. A
tool can silently combine different periods, units, dimensional members, or
concept meanings; drop a missing denominator; divide by zero; or round with an
unstated rule. A numeric result produced under those conditions looks more
certain than its evidence supports.

## Decision

Ratio evaluation consumes a verified normalized report and a separately
versioned policy. Every rule names the exact numerator and denominator concepts,
period, unit, dimensions, decimal precision, missingness behavior, and
zero-denominator behavior.

Facts are selected only by their complete normalized identity. The engine does
not coerce concepts, periods, units, or dimensions. Missing inputs and zero
denominators either raise a validation error or produce an explicit
`insufficient_evidence` result according to the declared policy. Successful
division uses `Decimal` and `ROUND_HALF_EVEN` at the declared precision.

The canonical output binds the normalized input report and normalized policy by
SHA-256, records the transformation sequence, sorts ratio rules by name, and
hashes the complete ratio report.

## Consequences

- Results are reproducible and the assumptions needed to obtain them are
  reviewable.
- A policy must be more verbose than an ad hoc formula.
- Versioned concept mapping and accounting reconciliation remain separate
  prerequisites for broader ratio libraries.
- SHA-256 detects changed bytes but does not authenticate the publisher.
