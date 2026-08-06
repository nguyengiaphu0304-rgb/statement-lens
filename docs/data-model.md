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

