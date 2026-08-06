# ADR-002: Explicit filing selection and availability-aware restatement diffs

Status: accepted

## Context

A report date can have multiple original and amended filings. Filing time alone does not prove when a research system obtained the data, and choosing a latest record can overwrite evidence or introduce look-ahead.

## Decision

The history engine accepts independently normalized reports, verifies their lineage, and requires explicit base accession, comparison accession and timezone-aware `as_of`. Retrieval time is the availability boundary. Facts join only on canonical concept, period, unit and dimensions; complete payload equality determines `unchanged`.

## Consequences

Comparisons are reproducible and cannot silently drift when another filing arrives. Callers must make selection policy explicit. The engine reports structural changes but does not infer accounting materiality, map concepts, convert units or decide which filing is authoritative.
