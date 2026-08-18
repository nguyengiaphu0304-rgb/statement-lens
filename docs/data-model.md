# Data model

## Source document

`locator`, lowercase SHA-256, timezone-aware retrieval timestamp and license are mandatory. The digest is evidence of byte identity, not publisher authenticity.

## Entity and filing

An entity has an identifier scheme, identifier and legal name. A filing has an accession, form, filing timestamp and report date. The report date cannot follow the filing timestamp, and the filing timestamp cannot follow retrieval. Accessions are preserved so later restatements cannot silently overwrite earlier filings.

## Taxonomy policy

Each concept declares exactly one `instant` or `duration` period type, a non-empty unit allowlist and a non-empty allowed-scale list. This local manifest is validation policy, not authoritative GAAP or IFRS semantics.

## Fact

A fact contains concept, decimal string, unit, scale, period, dimensions and source locator. Scale is applied with decimal arithmetic and then removed from normalized output. Identity is concept + period + unit + sorted dimensions; filing accession remains in the report envelope.

Identical facts with the same identity collapse. If any other field differs for the same identity, normalization fails rather than choosing a value.

## Lineage

The semantic input digest covers normalized source/entity/filing fields, sorted taxonomy policies and sorted deduplicated facts. The report digest covers the report before the digest field is attached. Both use canonical UTF-8 JSON and SHA-256.

## Filing history and availability

A history contains independently normalized reports for exactly one entity. Accession is the history key. Identical duplicate accessions collapse; conflicting content for one accession fails. `filed_at` captures publisher filing time, while `source.retrieved_at` is the local availability boundary. Both selected filings must have been retrieved by the caller's timezone-aware `as_of` timestamp.

The base and comparison accessions are mandatory and distinct. The engine does not select a latest filing. Base filing and retrieval times cannot follow the comparison filing in availability order.

## Restatement change

Facts join on concept + period + unit + sorted dimensions. A fact only in the comparison is `added`; only in the base is `removed`; equal full payloads are `unchanged`; and the same identity with any payload difference is `changed`. Before and after values and source locators remain intact. Different units, periods or dimensions remain different identities and are never coerced.

The restatement report separately hashes ordered input reports, filing-history summaries, the comparison policy and the final report.

## Accounting mapping policy

Every mapping has a unique rule ID, source concept, canonical concept, statement, role, expected period type and unit. A source concept maps at most once. Multiple sources may feed one canonical concept only when a unique aggregation rule names exactly those inputs and declares Decimal summation.

Mapped facts preserve every source concept, mapping rule ID, source locator and original value. Unmapped facts remain explicit evidence rather than being silently dropped. Dimensional or multi-context facts fail until a selector policy exists.

## Reconciliation

A reconciliation names one left-hand canonical concept, one or more unique right-hand concepts and a non-negative absolute tolerance. Complete, compatible evidence produces `pass` or `fail` plus the exact Decimal difference. Missing concepts produce `insufficient_evidence` and `difference: null`; missing values are never treated as zero. Units and canonical periods must match.

The accounting report independently hashes the verified normalized report, normalized policy, mapped facts and final report.
