# v1.0.0 publication checklist

## Automated candidate gates

- [ ] Final merge-commit CI passes on Python 3.11, 3.12 and 3.13.
- [ ] All four evidence reports regenerate byte-for-byte and the manifest verifies.
- [ ] Wheel and canonical sdist build twice byte-identically.
- [ ] Archive policy, isolated offline installation, dependency and vulnerability checks pass.
- [ ] Downloaded CI artifact contains exactly one wheel, canonical sdist and `SHA256SUMS`.

## Publication gates

- [ ] Create annotated tag `v1.0.0` at exactly the verified merge commit.
- [ ] Publish a non-prerelease GitHub Release using `docs/releases/v1.0.0.md`.
- [ ] Attach the exact three files from the Python 3.12 CI release-candidate artifact.
- [ ] Download the public attachments into an otherwise empty directory.
- [ ] Run `python scripts/release_verify.py --output-dir <download-dir> --verify-existing`.
- [ ] Confirm the public tag peels to the verified commit before calling the project released.

Never move the public tag. Correct defects through a new reviewed version.
