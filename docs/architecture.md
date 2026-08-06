# Architecture

Statement Lens v0.1 is a small offline boundary around untrusted JSON.

1. `normalize_json` parses JSON and rejects malformed or non-object roots.
2. Schema validation requires a supported version and complete source, entity, filing, taxonomy and fact fields.
3. Policies bind each concept to one period type and explicit unit/scale allowlists.
4. Decimal strings are scaled with `Decimal`; binary floating point is never introduced.
5. A fact identity is the canonical tuple of concept, period, unit and dimensions. Identical facts collapse; a conflicting payload fails the whole document.
6. Facts and taxonomy declarations are sorted before semantic input hashing.
7. The report records the semantic input digest, ordered transformations and its own payload digest.

The CLI is an adapter only. Core normalization has no file, clock, environment or network dependency, so replay is deterministic.

## Module boundaries

- `normalizer.py`: validation, canonicalization and lineage.
- `cli.py`: filesystem/stdout/stderr behavior and exit codes.
- `fixtures/`: offline, permissively licensed correctness evidence.
- `tests/`: invariants, failure paths, boundaries and replay.

Live acquisition, XBRL interpretation, reconciliation and analytical layers remain outside this boundary until separate milestones define their trust and data models.

