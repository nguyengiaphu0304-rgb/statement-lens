"""Create and verify the bounded, reproducible Statement Lens v1.0 artifacts."""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Final

IMPORT_PACKAGE: Final = "statement_lens"
DIST_NAME: Final = "statement-lens"
ARCHIVE_NAME: Final = "statement_lens"
VERSION: Final = "1.0.0"
EPOCH: Final = 1_787_011_200
WHEEL_NAME: Final = "statement_lens-1.0.0-py3-none-any.whl"
SDIST_NAME: Final = "statement_lens-1.0.0.tar.gz"
WHEEL_TIMESTAMP: Final = (2026, 8, 18, 0, 0, 0)
EXPECTED_ASSETS: Final = (WHEEL_NAME, SDIST_NAME, "SHA256SUMS")
MAX_ARCHIVE_BYTES: Final = 2_097_152
MAX_MEMBER_BYTES: Final = 524_288
MAX_WHEEL_FILES: Final = 64
MAX_SDIST_FILES: Final = 160
FORBIDDEN_PARTS: Final = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "release-artifacts",
}
ALLOWED_SDIST_TOP_LEVEL: Final = {
    ".github",
    ".gitignore",
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "docs",
    "evidence",
    "fixtures",
    "pyproject.toml",
    "scripts",
    "src",
    "tests",
    "uv.lock",
}
CHECKSUM_LINE: Final = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(name: str) -> PurePosixPath:
    if "\\" in name:
        raise ValueError("archive member contains a backslash")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise ValueError("archive member path is unsafe")
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        raise ValueError("archive contains a forbidden path")
    return path


def inspect_wheel(path: Path) -> None:
    """Fail closed on malformed, unexpected, or oversized wheels."""
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("wheel exceeds size budget")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len(names) > MAX_WHEEL_FILES:
            raise ValueError("wheel member count or uniqueness policy failed")
        prefixes = (f"{IMPORT_PACKAGE}/", f"{ARCHIVE_NAME}-{VERSION}.dist-info/")
        for info in infos:
            member_path = _safe_name(info.filename)
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("wheel member exceeds size budget")
            if not str(member_path).startswith(prefixes):
                raise ValueError("wheel contains a file outside the package allowlist")
            mode = info.external_attr >> 16
            if mode and (mode & 0o170000) not in {0, 0o100000}:
                raise ValueError("wheel contains a non-regular member")
            if mode and mode & 0o022:
                raise ValueError("wheel contains a group/world-writable member")
            if info.date_time != WHEEL_TIMESTAMP or info.compress_type != zipfile.ZIP_DEFLATED:
                raise ValueError("wheel member metadata drifted")
        metadata_name = f"{ARCHIVE_NAME}-{VERSION}.dist-info/METADATA"
        if metadata_name not in names:
            raise ValueError("wheel metadata is missing")
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        if metadata["Name"] != DIST_NAME or metadata["Version"] != VERSION:
            raise ValueError("wheel metadata identity is wrong")
        record_name = f"{ARCHIVE_NAME}-{VERSION}.dist-info/RECORD"
        if record_name not in names:
            raise ValueError("wheel RECORD is missing")
        rows = list(csv.reader(archive.read(record_name).decode("utf-8").splitlines()))
        if any(len(row) != 3 for row in rows):
            raise ValueError("wheel RECORD format is invalid")
        records = {row[0]: (row[1], row[2]) for row in rows}
        if len(records) != len(rows) or set(records) != set(names):
            raise ValueError("wheel RECORD file set is wrong")
        for member_name in names:
            encoded_digest, encoded_size = records[member_name]
            if member_name == record_name:
                if encoded_digest or encoded_size:
                    raise ValueError("wheel RECORD self-entry is not canonical")
                continue
            content = archive.read(member_name)
            digest = (
                base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            )
            if encoded_digest != f"sha256={digest}" or encoded_size != str(len(content)):
                raise ValueError("wheel RECORD integrity check failed")


def canonical_sdist(path: Path) -> bytes:
    """Validate without extraction and deterministically repack an sdist."""
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("sdist exceeds size budget")
    prefix = f"{ARCHIVE_NAME}-{VERSION}/"
    files: dict[str, bytes] = {}
    total_bytes = 0
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or len(names) > MAX_SDIST_FILES:
            raise ValueError("sdist member count or uniqueness policy failed")
        for member in members:
            name = str(_safe_name(member.name))
            if not name.startswith(prefix):
                raise ValueError("sdist root is wrong")
            relative = PurePosixPath(name).relative_to(PurePosixPath(prefix))
            if not relative.parts or relative.parts[0] not in ALLOWED_SDIST_TOP_LEVEL:
                raise ValueError("sdist contains a file outside the source allowlist")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("sdist contains a non-regular member")
            if member.mode & 0o022:
                raise ValueError("sdist contains a group/world-writable member")
            if member.size > MAX_MEMBER_BYTES:
                raise ValueError("sdist member exceeds size budget")
            total_bytes += member.size
            if total_bytes > MAX_ARCHIVE_BYTES:
                raise ValueError("sdist expanded size budget exceeded")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("sdist member could not be read")
            files[name] = stream.read()
    pkg_info = f"{prefix}PKG-INFO"
    if pkg_info not in files:
        raise ValueError("sdist metadata is missing")
    metadata = BytesParser().parsebytes(files[pkg_info])
    if metadata["Name"] != DIST_NAME or metadata["Version"] != VERSION:
        raise ValueError("sdist metadata identity is wrong")

    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as output:
        for name in sorted(files):
            content = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mtime = EPOCH
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            output.addfile(info, io.BytesIO(content))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=EPOCH) as gzip_stream:
        gzip_stream.write(tar_buffer.getvalue())
    return compressed.getvalue()


def _build(output: Path) -> tuple[Path, Path]:
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(EPOCH)
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output)],
        check=True,
        env=environment,
    )
    wheels = tuple(output.glob("*.whl"))
    sdists = tuple(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("build did not produce exactly one wheel and one sdist")
    return wheels[0], sdists[0]


def _isolated_smoke(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="statement-lens-wheel-") as temporary:
        virtualenv = Path(temporary) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(virtualenv)], check=True)
        bindir = "Scripts" if os.name == "nt" else "bin"
        python = virtualenv / bindir / ("python.exe" if os.name == "nt" else "python")
        cli = virtualenv / bindir / ("statement-lens.exe" if os.name == "nt" else "statement-lens")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import statement_lens; assert statement_lens.__version__ == '1.0.0'",
            ],
            check=True,
        )
        subprocess.run([str(cli), "--help"], check=True, stdout=subprocess.DEVNULL)


def verify_artifact_set(output: Path) -> None:
    """Verify an existing downloaded artifact set without trusting filenames or checksums."""
    actual = tuple(sorted(path.name for path in output.iterdir() if path.is_file()))
    if actual != tuple(sorted(EXPECTED_ASSETS)):
        raise ValueError("release artifact file set is not exact")
    raw = (output / "SHA256SUMS").read_bytes()
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("checksum file must be ASCII") from error
    matches = CHECKSUM_LINE.findall(text)
    if "".join(f"{digest}  {name}\n" for digest, name in matches) != text:
        raise ValueError("checksum file format is not canonical")
    expected_names = (SDIST_NAME, WHEEL_NAME)
    if tuple(name for _, name in matches) != expected_names:
        raise ValueError("checksum file names or ordering are wrong")
    for digest, name in matches:
        if sha256(output / name) != digest:
            raise ValueError(f"checksum mismatch: {name}")
    inspect_wheel(output / WHEEL_NAME)
    sdist = output / SDIST_NAME
    if canonical_sdist(sdist) != sdist.read_bytes():
        raise ValueError("sdist is not canonical")
    _isolated_smoke(output / WHEEL_NAME)


def build_release(output: Path) -> None:
    """Build twice, verify reproducibility, and emit one checked artifact set."""
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("release output directory must be empty")
    with tempfile.TemporaryDirectory(prefix="statement-lens-build-") as temporary:
        root = Path(temporary)
        first_wheel, first_sdist = _build(root / "first")
        second_wheel, second_sdist = _build(root / "second")
        inspect_wheel(first_wheel)
        inspect_wheel(second_wheel)
        if first_wheel.read_bytes() != second_wheel.read_bytes():
            raise ValueError("wheel builds are not byte-identical")
        first_canonical = canonical_sdist(first_sdist)
        second_canonical = canonical_sdist(second_sdist)
        if first_canonical != second_canonical:
            raise ValueError("canonical sdist builds are not byte-identical")
        (output / WHEEL_NAME).write_bytes(first_wheel.read_bytes())
        (output / SDIST_NAME).write_bytes(first_canonical)
        sums = "".join(f"{sha256(output / name)}  {name}\n" for name in (SDIST_NAME, WHEEL_NAME))
        (output / "SHA256SUMS").write_text(sums, encoding="ascii", newline="\n")
    verify_artifact_set(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or verify Statement Lens v1.0 artifacts")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-existing", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify_existing:
        verify_artifact_set(arguments.output_dir)
    else:
        build_release(arguments.output_dir)


if __name__ == "__main__":
    main()
