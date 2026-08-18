# Reproducible release demo

This demo is offline and uses only project-owned CC0 synthetic fixtures. It exercises normalization,
filing-history comparison, exact-policy ratios and accounting reconciliation. It is correctness evidence,
not a real filing analysis, accounting opinion, financial advice or investment result.

```bash
uv sync --frozen --python 3.12
uv run python scripts/release_evidence.py --output-dir evidence/v1.0.0 --verify
rm -rf release-artifacts
uv run python scripts/release_verify.py --output-dir release-artifacts
uv run python scripts/release_verify.py --output-dir release-artifacts --verify-existing
```

`evidence/v1.0.0/manifest.json` binds each report to its source fixture, generator and package version.
The artifact verifier builds twice, inspects archives without extraction, canonicalizes the sdist,
installs the wheel offline, runs an isolated import and CLI smoke check, and validates the exact asset set.
