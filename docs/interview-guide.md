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

