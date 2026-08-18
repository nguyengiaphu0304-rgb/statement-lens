from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.release_evidence import generate, verify
from scripts.release_verify import (
    SDIST_NAME,
    WHEEL_NAME,
    WHEEL_TIMESTAMP,
    canonical_sdist,
    inspect_wheel,
    verify_artifact_set,
)


def _metadata(name: str = "statement-lens", version: str = "1.0.0") -> bytes:
    return f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n\n".encode()


def _sdist(path: Path, members: list[tuple[str, bytes, str, int]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, content, kind, mode in members:
            info = tarfile.TarInfo(name)
            info.mode = mode
            if kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = "README.md"
                archive.addfile(info)
            elif kind == "hardlink":
                info.type = tarfile.LNKTYPE
                info.linkname = "README.md"
                archive.addfile(info)
            else:
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))


def _wheel(
    path: Path,
    metadata: bytes | None = None,
    *,
    duplicate: bool = False,
    timestamp: tuple[int, int, int, int, int, int] = WHEEL_TIMESTAMP,
) -> None:
    files = {
        "statement_lens/__init__.py": b"__version__ = '1.0.0'\n",
        "statement_lens-1.0.0.dist-info/METADATA": metadata or _metadata(),
    }
    record_name = "statement_lens-1.0.0.dist-info/RECORD"
    rows = []
    for name, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
        rows.append((name, f"sha256={digest.rstrip(b'=').decode()}", str(len(content))))
    rows.append((record_name, "", ""))
    record = io.StringIO(newline="")
    csv.writer(record, lineterminator="\n").writerows(rows)
    files[record_name] = record.getvalue().encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(name, timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
        if duplicate:
            info = zipfile.ZipInfo("statement_lens/__init__.py", timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, b"tampered\n")


def test_release_evidence_is_deterministic_and_exact(tmp_path: Path) -> None:
    checked = tmp_path / "checked"
    generated = tmp_path / "generated"
    generate(checked)
    generate(generated)
    assert {path.name: path.read_bytes() for path in checked.iterdir()} == {
        path.name: path.read_bytes() for path in generated.iterdir()
    }
    verify(checked)


def test_release_evidence_rejects_drift_and_extra_file(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    generate(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    manifest["synthetic_only"] = False
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="drift"):
        verify(output)
    generate(output)
    (output / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="file set"):
        verify(output)


@pytest.mark.parametrize(
    "name",
    [
        "/statement_lens-1.0.0/PKG-INFO",
        "statement_lens-1.0.0/../PKG-INFO",
        "statement_lens-1.0.0\\PKG-INFO",
    ],
)
def test_sdist_rejects_unsafe_paths(tmp_path: Path, name: str) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    _sdist(archive, [(name, _metadata(), "file", 0o644)])
    with pytest.raises(ValueError):
        canonical_sdist(archive)


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_sdist_rejects_links(tmp_path: Path, kind: str) -> None:
    archive = tmp_path / f"{kind}.tar.gz"
    prefix = "statement_lens-1.0.0/"
    _sdist(
        archive,
        [
            (f"{prefix}PKG-INFO", _metadata(), "file", 0o644),
            (f"{prefix}README.md", b"", kind, 0o644),
        ],
    )
    with pytest.raises(ValueError, match="non-regular"):
        canonical_sdist(archive)


def test_sdist_rejects_duplicate_members_and_unsafe_mode(tmp_path: Path) -> None:
    prefix = "statement_lens-1.0.0/"
    duplicate = tmp_path / "duplicate.tar.gz"
    _sdist(
        duplicate,
        [
            (f"{prefix}PKG-INFO", _metadata(), "file", 0o644),
            (f"{prefix}PKG-INFO", _metadata(), "file", 0o644),
        ],
    )
    with pytest.raises(ValueError, match="uniqueness"):
        canonical_sdist(duplicate)

    writable = tmp_path / "writable.tar.gz"
    _sdist(writable, [(f"{prefix}PKG-INFO", _metadata(), "file", 0o666)])
    with pytest.raises(ValueError, match="writable"):
        canonical_sdist(writable)


def test_wheel_rejects_duplicate_and_wrong_identity(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.whl"
    with pytest.warns(UserWarning, match="Duplicate name"):
        _wheel(duplicate, duplicate=True)
    with pytest.raises(ValueError, match="uniqueness"):
        inspect_wheel(duplicate)

    wrong = tmp_path / "wrong.whl"
    _wheel(wrong, _metadata(version="9.9.9"))
    with pytest.raises(ValueError, match="identity"):
        inspect_wheel(wrong)

    drifted = tmp_path / "drifted.whl"
    _wheel(drifted, timestamp=(2026, 8, 18, 0, 0, 2))
    with pytest.raises(ValueError, match="metadata drifted"):
        inspect_wheel(drifted)


def _artifact_stub(path: Path) -> None:
    path.mkdir()
    (path / WHEEL_NAME).write_bytes(b"wheel")
    (path / SDIST_NAME).write_bytes(b"sdist")
    (path / "SHA256SUMS").write_text(
        f"{'0' * 64}  {SDIST_NAME}\n{'1' * 64}  {WHEEL_NAME}\n", encoding="ascii"
    )


@pytest.mark.parametrize("missing", [WHEEL_NAME, SDIST_NAME, "SHA256SUMS"])
def test_downloaded_set_rejects_missing_or_renamed_asset(tmp_path: Path, missing: str) -> None:
    _artifact_stub(tmp_path / "assets")
    asset = tmp_path / "assets" / missing
    asset.rename(asset.with_name(f"renamed-{missing}"))
    with pytest.raises(ValueError, match="file set"):
        verify_artifact_set(tmp_path / "assets")


def test_downloaded_set_rejects_extra_corrupt_and_noncanonical_checksums(
    tmp_path: Path,
) -> None:
    assets = tmp_path / "assets"
    _artifact_stub(assets)
    (assets / "unexpected").write_bytes(b"")
    with pytest.raises(ValueError, match="file set"):
        verify_artifact_set(assets)
    (assets / "unexpected").unlink()
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_artifact_set(assets)
    checksum = (assets / "SHA256SUMS").read_text(encoding="ascii")
    (assets / "SHA256SUMS").write_text(checksum.upper(), encoding="ascii")
    with pytest.raises(ValueError, match=r"format|names"):
        verify_artifact_set(assets)
