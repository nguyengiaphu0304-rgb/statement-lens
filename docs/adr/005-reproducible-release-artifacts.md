# ADR-005: Rebuild and verify release artifacts offline

## Status

Accepted for the v1.0.0 release candidate.

## Context

A successful package build does not prove that the intended files were included, that the wheel can be
installed without dependency resolution, or that another build produces the same bytes. Source archives
can also carry nondeterministic or unsafe tar and gzip metadata.

## Decision

Build the wheel and sdist twice with a fixed source epoch. Wheels must be byte-identical. Validate each
sdist without extraction, then repack regular allowlisted files in sorted order with fixed metadata and
require byte-identical canonical archives. Reject absolute, traversal or backslash paths; duplicate,
link or special members; group/world-writable members; identity/version drift; forbidden paths; and
resource-budget violations. Install the wheel in a clean environment using `--no-index --no-deps`,
verify versioned import and CLI startup, and publish only the verified wheel, canonical sdist and
canonical checksum file.

## Consequences

The candidate is reproducible and has a bounded archive attack surface. SHA-256 is integrity evidence,
not publisher authentication. Signing and trusted build attestations remain future work and must not
replace the independent offline path.
