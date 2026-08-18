# Support and recovery matrix

| Area | Verified scope | Recovery or failure behavior |
| --- | --- | --- |
| Python | CPython 3.11, 3.12, 3.13 on GitHub-hosted Ubuntu | Reinstall the verified wheel offline; unsupported runtimes fail metadata constraints. |
| Input | Bounded UTF-8 JSON and project-owned synthetic fixtures | Invalid, ambiguous, oversized or temporally inconsistent input fails closed. |
| Evidence | Canonical JSON, SHA-256 lineage and independent replay | Regenerate from bound fixtures; unexpected files or byte drift fail verification. |
| Package | Pure-Python wheel and canonical sdist | Verify the exact asset set, checksums and archives before offline wheel installation. |
| Network | No network at runtime or in the release demo | Provider availability, corrections and rate limits remain out of scope. |
| Storage | Caller-controlled local input/output paths | Preserve source documents and governance externally; this package is not a warehouse. |

Windows, macOS, alternate Python implementations, distributed storage and production recovery are not
verified support claims.
