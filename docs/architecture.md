# Architecture

Statement Lens v0.3 alpha is an offline pipeline with four explicit trust boundaries.

1. `normalize_json` parses JSON and rejects malformed or non-object roots.
2. Schema validation requires a supported version and complete source, entity, filing, taxonomy and fact fields.
3. Policies bind each concept to one period type and explicit unit/scale allowlists.
4. Decimal strings are scaled with `Decimal`; binary floating point is never introduced.
5. A fact identity is the canonical tuple of concept, period, unit and dimensions. Identical facts collapse; a conflicting payload fails the whole document.
6. Facts and taxonomy declarations are sorted before semantic input hashing.
7. The normalized report records the semantic input digest, ordered transformations and its own payload digest.
8. `compare_history` verifies every normalized report digest, enforces one entity and deduplicates only byte-equivalent accessions.
9. The caller selects base/comparison accessions and an explicit `as_of`; the engine never infers “latest”.
10. Facts are joined by canonical identity and classified as added, removed, changed or unchanged while preserving before/after payloads.
11. History, policy, input and output lineage are hashed independently of input order.
12. `evaluate_ratio_policy` verifies the normalized report digest before reading facts.
13. A versioned policy selects numerator and denominator only by exact concept, period, unit and dimensions.
14. Missing facts and zero denominators follow explicit `error` or `report` behavior; reporting produces `insufficient_evidence`, never a fabricated number.
15. Successful division uses bounded `Decimal` inputs and declared `ROUND_HALF_EVEN` precision.
16. Ratio rules are sorted by name and the input report, normalized policy and output receive independent SHA-256 lineage.
17. `analyze_report` reverifies normalized-report lineage before reading facts.
18. A versioned accounting policy maps one source concept to one canonical concept with an explicit rule ID, statement, role, period type and unit.
19. Many-to-one mappings require an exact `sum` aggregation; ambiguous contexts, dimensions, units or periods fail closed.
20. Reconciliation never substitutes zero for missing concepts. It emits `pass`, `fail` or `insufficient_evidence` using bounded `Decimal` tolerances.
21. Mapping rules, source concepts, source locators, mapped facts, normalized policy and the final report retain canonical SHA-256 lineage.

The CLI is an adapter only. The normalization, history, ratio and accounting engines have no file, clock, environment or network dependency, so replay is deterministic.

## Module boundaries

- `normalizer.py`: validation, canonicalization and lineage.
- `history.py`: normalized-report verification, availability policy and restatement diff.
- `ratios.py`: exact fact selection, missingness policy, decimal division and ratio lineage.
- `accounting.py`: versioned mapping, explicit aggregation, reconciliation gates and accounting lineage.
- `cli.py`: filesystem/stdout/stderr behavior and exit codes.
- `fixtures/`: offline, permissively licensed correctness evidence.
- `tests/`: invariants, failure paths, boundaries and replay.

Live acquisition, XBRL interpretation, authoritative taxonomy resolution, dimensional selectors and broader analytical layers remain outside this boundary.
