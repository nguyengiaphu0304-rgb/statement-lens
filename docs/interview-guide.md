# Design and trade-off guide

## Why an offline core first?

Acquisition failures and accounting interpretation are different risks. A pure normalizer makes provenance and schema behavior reproducible before network caching, rate limits or vendor formats complicate evidence.

## Why require decimal strings?

JSON numbers are often decoded through binary floating point. Requiring strings lets the package reject ambiguous types and apply scale using decimal arithmetic.

## Why fail on conflicting duplicates?

Choosing first, last or maximum would hide source disagreement. A conflict is evidence that identity policy or upstream data needs review, so the document is rejected.

## Why is the taxonomy supplied by the input?

The first milestone proves the policy boundary without pretending to ship authoritative GAAP/IFRS packages. Later versions can add versioned, licensed taxonomy resolvers behind the same explicit contract.

## What does the hash prove?

It proves that canonical semantic content is unchanged. It does not prove publisher identity, accounting correctness or investment usefulness. Authentication and signed provenance remain residual risks.

## Why require explicit base and comparison accessions?

“Latest” depends on both filing time and when data became available. Automatic selection can introduce look-ahead or silently replace prior evidence. Explicit accessions plus `as_of` make the research question reproducible.

## Why classify source-locator-only changes as changed?

The source locator is provenance, not decoration. Even when the numeric value is equal, different supporting evidence matters to an audit trail, so full payload equality is required for `unchanged`.

## Why are different units or dimensions added/removed instead of changed?

Unit, period and dimensions define fact identity. Coercing them would require an accounting transformation policy that v0.2 deliberately does not claim. Later mapping and reconciliation layers can make those rules explicit and versioned.
