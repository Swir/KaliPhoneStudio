"""Fail-closed adapter for externally built OTA partition extractors.

The adapter never downloads tools. Release-oriented callers should construct an
ExtractorLock from the repository's versioned tool-lock manifest so a local
binary is authorized only for the declared host platform and exact SHA-256.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import subprocess

from .boot_image import BootImageReport, inspect_boot_image, require_candidate_compatible
from .payload import PayloadHeaderReport, inspect_payload
from .profiles import DeviceProfile
from .tool_locks import ToolLockError, load_tool_lock

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractorLock:
    executable: Path
    sha256: str
    source_url: str
    source_commit: str
    platform: str | None = None


@dataclass(frozen=True)
class StockBootExtractionReport:
    payload: PayloadHeaderReport
    extractor_sha256: str
    boot: BootImageReport


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def lock_from_manifest(executable: Path, manifest_path: Path, platform: str) -> ExtractorLock:
    """Authorize *executable* only if the manifest has an exact platform lock.

    An empty artifacts map therefore remains deliberately unusable. This keeps
    release extraction fail-closed until a reproducibly built host binary has
    been reviewed and its SHA-256 committed to the repository.
    """
    try:
        manifest = load_tool_lock(manifest_path)
        artifact = manifest.require_artifact(platform)
    except ToolLockError as exc:
        raise ExtractionError(f"extractor is not authorized: {exc}") from exc
    return ExtractorLock(
        executable=executable,
        sha256=artifact.sha256,
        source_url=manifest.source_url,
        source_commit=manifest.source_commit,
        platform=platform,
    )


def verify_extractor(lock: ExtractorLock) -> str:
    if not lock.executable.is_file():
        raise ExtractionError("extractor executable does not exist")
    expected = lock.sha256.lower()
    if not _SHA256_RE.fullmatch(expected):
        raise ExtractionError("extractor lock requires a lowercase/hex SHA-256")
    if not isinstance(lock.source_url, str) or not lock.source_url.startswith("https://github.com/"):
        raise ExtractionError("extractor source must be an HTTPS GitHub URL")
    if not _COMMIT_RE.fullmatch(lock.source_commit):
        raise ExtractionError("extractor source must be pinned to a full commit")
    actual = _hash_file(lock.executable)
    if actual != expected:
        raise ExtractionError("extractor SHA-256 mismatch")
    return actual


def extract_stock_boot(payload_path: Path, output_dir: Path, profile: DeviceProfile, lock: ExtractorLock) -> StockBootExtractionReport:
    """Extract only boot.img after payload/tool verification, then run boot preflight.

    No shell is used and the output directory must be empty, preventing stale
    boot.img files from being mistaken for extractor output.
    """
    payload = inspect_payload(payload_path)
    extractor_hash = verify_extractor(lock)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ExtractionError("extractor output directory must be empty")

    command = [str(lock.executable), "-p", "boot", "-o", str(output_dir), str(payload_path)]
    try:
        completed = subprocess.run(command, shell=False, check=False, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExtractionError(f"extractor execution failed: {exc}") from exc
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()[-1000:]
        raise ExtractionError(f"extractor returned {completed.returncode}: {tail}")

    boot_path = output_dir / "boot.img"
    if not boot_path.is_file():
        raise ExtractionError("extractor did not produce boot.img")
    boot = inspect_boot_image(boot_path, profile)
    require_candidate_compatible(boot, profile)
    return StockBootExtractionReport(payload=payload, extractor_sha256=extractor_hash, boot=boot)
