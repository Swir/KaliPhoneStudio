"""Safe one-command stock OTA -> payload.bin -> boot.img -> provenance pipeline.

This module is host-side only. It never downloads tools, talks to a phone,
flashes partitions, boots a device, or grants hardware/Beta credit. The caller
must provide an exact local OTA ZIP and a local extractor binary whose SHA-256
is authorized by the repository's versioned extractor lock manifest.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Sequence
from zipfile import BadZipFile, ZipFile

from .boot_image import BootImageError
from .extractor import ExtractionError, extract_stock_boot, lock_from_manifest
from .ota_import import OTAImportError, OTAPackageReport, inspect_ota_zip, require_firmware_hint
from .payload import PayloadFormatError
from .profiles import ProfileError, get_profile
from .provenance import ProvenanceError, StockBootProvenance, write_immutable_provenance
from .stock_baseline_ingress import StockBaselineIngressError, prepare_stock_provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICES_ROOT = REPO_ROOT / "devices"
DEFAULT_EXTRACTOR_MANIFEST = REPO_ROOT / "tools" / "extractor-locks.json"
_HASH_CHUNK_SIZE = 1024 * 1024


class StockOTAPipelineError(ValueError):
    """Raised when the local stock extraction pipeline fails closed."""


@dataclass(frozen=True)
class StockOTAExtractionReport:
    schema_version: int
    profile_id: str
    ota_sha256: str
    ota_size: int
    payload_sha256: str
    payload_size: int
    boot_sha256: str
    boot_size: int
    extractor_sha256: str
    extractor_platform: str
    extractor_manifest_sha256: str
    extractor_source_url: str
    extractor_source_commit: str
    stock_provenance_sha256: str
    payload_relpath: str
    boot_relpath: str
    provenance_relpath: str
    phone_queried: bool
    phone_storage_written: bool
    temporary_boot_authorized: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"


def _hash_regular_file(path: Path, label: str) -> str:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise StockOTAPipelineError(f"{label} must be a regular non-symlink file: {candidate}")
    before = candidate.stat()
    digest = sha256()
    try:
        with candidate.open("rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise StockOTAPipelineError(f"cannot read {label}: {candidate}") from exc
    after = candidate.stat()
    if not _same_stat(before, after):
        raise StockOTAPipelineError(f"{label} changed while being hashed: {candidate}")
    return digest.hexdigest()


def _same_stat(before: object, after: object) -> bool:
    return (
        getattr(before, "st_size", None) == getattr(after, "st_size", None)
        and getattr(before, "st_mtime_ns", None) == getattr(after, "st_mtime_ns", None)
        and getattr(before, "st_ino", None) == getattr(after, "st_ino", None)
    )


def _materialize_exact_payload(
    ota_path: Path,
    report: OTAPackageReport,
    destination: Path,
) -> tuple[str, int]:
    """Extract exactly the already-inspected payload.bin and re-check source stability."""
    source = Path(ota_path)
    destination = Path(destination)
    if source.is_symlink() or not source.is_file():
        raise StockOTAPipelineError(f"OTA package must be a regular non-symlink file: {source}")
    if destination.exists() or destination.is_symlink():
        raise StockOTAPipelineError(f"refusing to overwrite payload output: {destination}")

    before = source.stat()
    digest = sha256()
    seen = 0
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(source) as zf:
            candidates = [
                info for info in zf.infolist()
                if info.filename == report.payload_member and not info.is_dir()
            ]
            if len(candidates) != 1:
                raise StockOTAPipelineError("inspected payload member is missing or ambiguous")
            info = candidates[0]
            if info.file_size != report.payload_size:
                raise StockOTAPipelineError("OTA payload size drifted after inspection")
            with zf.open(info, "r") as src, destination.open("xb") as dst:
                while chunk := src.read(_HASH_CHUNK_SIZE):
                    seen += len(chunk)
                    if seen > report.payload_size:
                        raise StockOTAPipelineError("payload.bin expanded beyond inspected size")
                    digest.update(chunk)
                    dst.write(chunk)
    except (BadZipFile, OSError) as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise StockOTAPipelineError(f"cannot materialize exact OTA payload: {exc}") from exc
    except StockOTAPipelineError:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    after = source.stat()
    actual_sha = digest.hexdigest()
    if not _same_stat(before, after):
        destination.unlink(missing_ok=True)
        raise StockOTAPipelineError("OTA package changed while payload.bin was materialized")
    if seen != report.payload_size:
        destination.unlink(missing_ok=True)
        raise StockOTAPipelineError("materialized payload size does not match inspected OTA")
    if actual_sha != report.payload_sha256:
        destination.unlink(missing_ok=True)
        raise StockOTAPipelineError("materialized payload SHA-256 does not match inspected OTA")
    return actual_sha, seen


def _write_report(report: StockOTAExtractionReport, path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise StockOTAPipelineError(f"refusing to overwrite extraction report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as fh:
            fh.write(report.canonical_json())
    except OSError as exc:
        raise StockOTAPipelineError(f"cannot write extraction report: {exc}") from exc


def prepare_stock_from_ota(
    *,
    devices_root: Path,
    profile_id: str,
    ota_path: Path,
    extractor_path: Path,
    extractor_manifest_path: Path,
    extractor_platform: str,
    output_dir: Path,
) -> tuple[StockOTAExtractionReport, StockBootProvenance]:
    """Build a create-only local stock evidence bundle from one exact OTA."""
    output_dir = Path(output_dir)
    if output_dir.exists() or output_dir.is_symlink():
        raise StockOTAPipelineError(f"refusing existing output directory: {output_dir}")
    if not isinstance(extractor_platform, str) or not extractor_platform.strip():
        raise StockOTAPipelineError("extractor platform must be a non-empty manifest key")

    profile = get_profile(Path(devices_root), profile_id)
    ota_report = inspect_ota_zip(Path(ota_path))
    require_firmware_hint(ota_report, list(profile.data["firmware_hints"]))
    extractor_manifest_sha256 = _hash_regular_file(Path(extractor_manifest_path), "extractor lock manifest")
    lock = lock_from_manifest(Path(extractor_path), Path(extractor_manifest_path), extractor_platform)
    if _hash_regular_file(Path(extractor_manifest_path), "extractor lock manifest") != extractor_manifest_sha256:
        raise StockOTAPipelineError("extractor lock manifest changed while being loaded")

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise StockOTAPipelineError(f"output parent must be a real directory: {parent}")

    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=str(parent)))
    committed = False
    try:
        payload_path = stage / "payload.bin"
        payload_sha, payload_size = _materialize_exact_payload(Path(ota_path), ota_report, payload_path)

        partitions_dir = stage / "partitions"
        extraction = extract_stock_boot(payload_path, partitions_dir, profile, lock)
        boot_path = partitions_dir / "boot.img"

        provenance, ota_sha, ota_size, boot_sha, boot_size = prepare_stock_provenance(
            devices_root=Path(devices_root),
            profile_id=profile_id,
            ota_path=Path(ota_path),
            payload_path=payload_path,
            stock_boot_path=boot_path,
        )
        if ota_sha != ota_report.sha256 or ota_size != ota_report.size:
            raise StockOTAPipelineError("OTA identity drifted between extraction and provenance")
        if provenance.payload_sha256 != payload_sha or provenance.payload_size != payload_size:
            raise StockOTAPipelineError("payload identity drifted between extraction and provenance")
        if extraction.boot.sha256 != boot_sha or extraction.boot.size != boot_size:
            raise StockOTAPipelineError("boot identity drifted between extraction and provenance")

        provenance_path = stage / "stock-provenance.json"
        write_immutable_provenance(provenance, provenance_path)

        report = StockOTAExtractionReport(
            schema_version=1,
            profile_id=profile_id,
            ota_sha256=ota_sha,
            ota_size=ota_size,
            payload_sha256=payload_sha,
            payload_size=payload_size,
            boot_sha256=boot_sha,
            boot_size=boot_size,
            extractor_sha256=extraction.extractor_sha256,
            extractor_platform=extractor_platform,
            extractor_manifest_sha256=extractor_manifest_sha256,
            extractor_source_url=lock.source_url,
            extractor_source_commit=lock.source_commit,
            stock_provenance_sha256=provenance.evidence_sha256(),
            payload_relpath="payload.bin",
            boot_relpath="partitions/boot.img",
            provenance_relpath="stock-provenance.json",
            phone_queried=False,
            phone_storage_written=False,
            temporary_boot_authorized=False,
            hardware_verified=False,
            beta_gate_credit=False,
        )
        _write_report(report, stage / "stock-extraction-report.json")

        if output_dir.exists() or output_dir.is_symlink():
            raise StockOTAPipelineError(f"output directory appeared during extraction: {output_dir}")
        stage.rename(output_dir)
        committed = True
        return report, provenance
    finally:
        if not committed:
            shutil.rmtree(stage, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio extract-stock-boot-from-ota",
        description=(
            "Host-only: validate one exact local OTA, materialize its exact payload.bin, "
            "run a SHA-256-authorized local payload-dumper-go binary for boot.img only, "
            "validate the boot image against the selected device profile, and emit "
            "create-only stock provenance. No phone I/O, boot or flash is performed."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--devices-root", type=Path, default=DEFAULT_DEVICES_ROOT)
    parser.add_argument("--ota", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, required=True)
    parser.add_argument("--extractor-manifest", type=Path, default=DEFAULT_EXTRACTOR_MANIFEST)
    parser.add_argument("--extractor-platform", required=True, help="Exact key from tools/extractor-locks.json.")
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        report, _ = prepare_stock_from_ota(
            devices_root=args.devices_root,
            profile_id=args.profile_id,
            ota_path=args.ota,
            extractor_path=args.extractor,
            extractor_manifest_path=args.extractor_manifest,
            extractor_platform=args.extractor_platform,
            output_dir=args.out_dir,
        )
    except (
        StockOTAPipelineError,
        StockBaselineIngressError,
        ProfileError,
        OTAImportError,
        PayloadFormatError,
        BootImageError,
        ExtractionError,
        ProvenanceError,
        OSError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(report.canonical_json(), end="")
    return 0
