# ADR-001: Start with a provenance-first offline core

- Status: accepted
- Date: 2026-08-06

## Context

Financial-statement tools can accidentally mix acquisition time, filing time, report periods, taxonomy interpretation and analytical claims. Starting with live EDGAR or ratio features would make it harder to determine whether failures came from the network, source bytes, schema policy or transformation logic.

## Decision

Build a standard-library runtime that accepts one versioned JSON document, validates explicit provenance and accounting-shape invariants, and emits canonical JSON with semantic lineage. Use only CC0 synthetic evidence. Reject ambiguity rather than guessing.

## Consequences

The core is easy to replay, audit and package, and it has no runtime dependency supply chain. At the time of this decision it could not acquire or interpret real filings, reconcile statements, detect restatements across a history, or compute ratios. ADR-002 subsequently added the bounded restatement-history layer; acquisition, accounting reconciliation and ratios remain separate milestones.
