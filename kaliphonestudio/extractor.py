"""Fail-closed adapter for externally built OTA partition extractors.

The adapter never downloads tools. A caller must provide a local extractor binary
and its expected SHA-256. Source provenance is pinned separately so release/build
pipelines can reproduce the executable before allowing extraction.
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

PAYLOAD_DUMPER_GO_SOURCE = "https://github.com/ssut/payload-dumper-go"
PAYLOAD_DUMPER_GO_COMMIT = "05fe59e21c9f271fba38398c7c040993313ecd04"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractorLock:
    executable: Path
    sha256: str
    source_url: str = PAYLOAD_DUMPER_GO_SOURCE
    source_commit: str = PAYLOAD_DUMPER_GO_COMMIT


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


def verify_extractor(lock: ExtractorLock) -> str:
    if not lock.executable.is_file():
        raise ExtractionError("extractor executable does not exist")
    expected = lock.sha256.lower()
    if not _SHA256_RE.fullmatch(expected):
        raise ExtractionError("extractor lock requires a lowercase/hex SHA-256")
    if not re.fullmatch(r"[0-9a-f]{40}", lock.source_commit):
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
