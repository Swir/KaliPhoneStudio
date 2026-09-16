"""Fail-closed structural verification and boot-plan binding for DTB/DTBO artifacts.

This module is intentionally device-independent. Layout policy comes from a validated
``DeviceProfile`` and exact artifact bytes are bound to the approved ``BootBuildPlan``.
The evidence produced here is host-side only and never claims physical hardware success.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
from typing import Any

from .boot_builder import BootBuildPlan
from .profiles import DeviceProfile


FDT_MAGIC = 0xD00DFEED
DT_TABLE_MAGIC = 0xD7B7AB1E
_FDT_HEADER_SIZE = 40
_DT_TABLE_HEADER_SIZE = 32
_DT_TABLE_ENTRY_MIN_SIZE = 32
_MAX_DTB_BYTES = 128 * 1024 * 1024
_MAX_DTBO_BYTES = 128 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class DeviceTreeError(ValueError):
    pass


@dataclass(frozen=True)
class DtbArtifactEvidence:
    schema_version: int
    artifact_sha256: str
    artifact_size: int
    tree_count: int
    fdt_versions: tuple[int, ...]

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DtboArtifactEvidence:
    schema_version: int
    artifact_sha256: str
    artifact_size: int
    total_size: int
    entry_count: int
    page_size: int
    table_version: int
    overlay_sha256: tuple[str, ...]

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeviceTreeCandidateEvidence:
    schema_version: int
    profile_id: str
    boot_plan_sha256: str
    format_lock_sha256: str
    dtb_evidence_sha256: str | None
    dtb_sha256: str | None
    dtb_size: int | None
    dtb_tree_count: int | None
    dtbo_evidence_sha256: str | None
    dtbo_sha256: str | None
    dtbo_size: int | None
    dtbo_entry_count: int | None

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _regular_file_bytes(path: Path, *, limit: int, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise DeviceTreeError(f"{label} must be a regular non-symlink file")
    size = path.stat().st_size
    if size <= 0 or size > limit:
        raise DeviceTreeError(f"{label} size is outside the safety bound")
    payload = path.read_bytes()
    if len(payload) != size or path.stat().st_size != size:
        raise DeviceTreeError(f"{label} changed while being verified")
    return payload


def _sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _validate_fdt(payload: bytes, offset: int, *, container_end: int, label: str) -> tuple[int, int]:
    if offset < 0 or container_end > len(payload) or offset + _FDT_HEADER_SIZE > container_end:
        raise DeviceTreeError(f"{label} has a truncated FDT header")
    fields = struct.unpack_from(">10I", payload, offset)
    (
        magic,
        total_size,
        off_dt_struct,
        off_dt_strings,
        off_mem_rsvmap,
        version,
        last_comp_version,
        _boot_cpuid_phys,
        size_dt_strings,
        size_dt_struct,
    ) = fields
    if magic != FDT_MAGIC:
        raise DeviceTreeError(f"{label} does not begin with FDT magic")
    if total_size < _FDT_HEADER_SIZE or offset + total_size > container_end:
        raise DeviceTreeError(f"{label} FDT total size is outside the containing artifact")
    if version < 17 or last_comp_version > 17 or last_comp_version > version:
        raise DeviceTreeError(f"{label} uses an unsupported FDT version contract")
    if off_mem_rsvmap < _FDT_HEADER_SIZE or off_mem_rsvmap >= total_size or off_mem_rsvmap % 8:
        raise DeviceTreeError(f"{label} has an invalid memory-reservation offset")
    for name, block_offset, block_size in (
        ("structure", off_dt_struct, size_dt_struct),
        ("strings", off_dt_strings, size_dt_strings),
    ):
        if block_offset < _FDT_HEADER_SIZE or block_offset % 4:
            raise DeviceTreeError(f"{label} has an invalid {name} block offset")
        if block_size <= 0 or block_offset + block_size > total_size:
            raise DeviceTreeError(f"{label} has an invalid {name} block range")
    return total_size, version


def inspect_dtb_artifact(path: Path) -> DtbArtifactEvidence:
    """Verify one or more concatenated flattened DTBs with zero-only trailing padding."""
    payload = _regular_file_bytes(path, limit=_MAX_DTB_BYTES, label="DTB artifact")
    cursor = 0
    versions: list[int] = []
    while cursor < len(payload):
        while cursor < len(payload) and payload[cursor] == 0:
            cursor += 1
        if cursor == len(payload):
            break
        if cursor % 4:
            raise DeviceTreeError("DTB bundle contains non-aligned concatenated data")
        total_size, version = _validate_fdt(
            payload, cursor, container_end=len(payload), label=f"DTB[{len(versions)}]"
        )
        versions.append(version)
        cursor += total_size
    if not versions:
        raise DeviceTreeError("DTB artifact contains no flattened device tree")
    return DtbArtifactEvidence(
        schema_version=1,
        artifact_sha256=_sha256_bytes(payload),
        artifact_size=len(payload),
        tree_count=len(versions),
        fdt_versions=tuple(versions),
    )


def inspect_dtbo_artifact(path: Path) -> DtboArtifactEvidence:
    """Verify an Android DT table image and each embedded FDT payload."""
    payload = _regular_file_bytes(path, limit=_MAX_DTBO_BYTES, label="DTBO artifact")
    if len(payload) < _DT_TABLE_HEADER_SIZE:
        raise DeviceTreeError("DTBO artifact is smaller than the DT table header")
    (
        magic,
        total_size,
        header_size,
        entry_size,
        entry_count,
        entries_offset,
        page_size,
        table_version,
    ) = struct.unpack_from(">8I", payload, 0)
    if magic != DT_TABLE_MAGIC:
        raise DeviceTreeError("DTBO artifact has invalid DT table magic")
    if total_size < _DT_TABLE_HEADER_SIZE or total_size > len(payload):
        raise DeviceTreeError("DTBO total_size is outside the artifact")
    if header_size < _DT_TABLE_HEADER_SIZE or header_size > total_size:
        raise DeviceTreeError("DTBO header_size is invalid")
    if entry_size < _DT_TABLE_ENTRY_MIN_SIZE or entry_size % 4:
        raise DeviceTreeError("DTBO entry_size is invalid")
    if entry_count <= 0:
        raise DeviceTreeError("DTBO image contains no entries")
    if entries_offset < header_size or entries_offset % 4:
        raise DeviceTreeError("DTBO entries offset is invalid")
    entries_end = entries_offset + entry_size * entry_count
    if entries_end > total_size:
        raise DeviceTreeError("DTBO entry table exceeds total_size")
    if page_size < 512 or page_size & (page_size - 1):
        raise DeviceTreeError("DTBO page size must be a power of two >= 512")
    if table_version != 0:
        raise DeviceTreeError("unsupported DTBO table version")

    occupied: list[tuple[int, int]] = []
    overlay_hashes: list[str] = []
    for index in range(entry_count):
        entry_at = entries_offset + index * entry_size
        dt_size, dt_offset, _ident, _rev, *_custom = struct.unpack_from(">8I", payload, entry_at)
        if dt_size < _FDT_HEADER_SIZE:
            raise DeviceTreeError(f"DTBO entry {index} is too small for an FDT")
        if dt_offset < entries_end or dt_offset + dt_size > total_size:
            raise DeviceTreeError(f"DTBO entry {index} payload range is invalid")
        for start, end in occupied:
            if dt_offset < end and dt_offset + dt_size > start:
                raise DeviceTreeError("DTBO entries overlap")
        occupied.append((dt_offset, dt_offset + dt_size))
        fdt_total_size, _version = _validate_fdt(
            payload,
            dt_offset,
            container_end=dt_offset + dt_size,
            label=f"DTBO entry {index}",
        )
        if fdt_total_size > dt_size:
            raise DeviceTreeError(f"DTBO entry {index} FDT exceeds declared payload size")
        padding = payload[dt_offset + fdt_total_size : dt_offset + dt_size]
        if any(padding):
            raise DeviceTreeError(f"DTBO entry {index} contains non-zero bytes after FDT totalsize")
        overlay_hashes.append(_sha256_bytes(payload[dt_offset : dt_offset + dt_size]))

    if any(payload[total_size:]):
        raise DeviceTreeError("DTBO artifact has non-zero trailing bytes after total_size")
    return DtboArtifactEvidence(
        schema_version=1,
        artifact_sha256=_sha256_bytes(payload),
        artifact_size=len(payload),
        total_size=total_size,
        entry_count=entry_count,
        page_size=page_size,
        table_version=table_version,
        overlay_sha256=tuple(overlay_hashes),
    )


def _canonical_lock_payload(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_device_tree_format_locks(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeviceTreeError(f"cannot load device-tree format lock: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise DeviceTreeError("unsupported device-tree format lock schema")
    references = data.get("references")
    if not isinstance(references, list) or len(references) < 2:
        raise DeviceTreeError("device-tree format lock requires DTB and DTBO references")
    kinds: set[str] = set()
    for reference in references:
        if not isinstance(reference, dict):
            raise DeviceTreeError("device-tree format reference must be an object")
        kind = reference.get("kind")
        url = reference.get("url")
        commit = reference.get("commit")
        path_value = reference.get("path")
        if kind not in {"dtb", "dtbo"}:
            raise DeviceTreeError("device-tree format reference has invalid kind")
        if kind in kinds:
            raise DeviceTreeError("device-tree format lock contains duplicate reference kind")
        kinds.add(kind)
        if not isinstance(url, str) or not url.startswith("https://"):
            raise DeviceTreeError("device-tree format reference URL must use HTTPS")
        if not isinstance(commit, str) or not _FULL_COMMIT_RE.fullmatch(commit):
            raise DeviceTreeError("device-tree format reference must pin a full commit")
        if not isinstance(path_value, str) or not path_value or path_value.startswith("/") or ".." in Path(path_value).parts:
            raise DeviceTreeError("device-tree format reference path is unsafe")
    if kinds != {"dtb", "dtbo"}:
        raise DeviceTreeError("device-tree format lock must contain exactly DTB and DTBO references")
    return data, sha256(_canonical_lock_payload(data)).hexdigest()


def _planned_input(plan: BootBuildPlan, name: str, *, required: bool) -> Any | None:
    matches = [item for item in plan.inputs if item.name == name]
    if required and len(matches) != 1:
        raise DeviceTreeError(f"boot build plan must contain exactly one {name} input")
    if not required and matches:
        raise DeviceTreeError(f"boot build plan unexpectedly contains a {name} input")
    return matches[0] if matches else None


def bind_device_tree_candidate_evidence(
    profile: DeviceProfile,
    plan: BootBuildPlan,
    *,
    format_lock: Path,
    dtb: Path | None = None,
    dtbo: Path | None = None,
) -> DeviceTreeCandidateEvidence:
    """Structurally verify profile-required DT artifacts and bind exact bytes to the boot plan."""
    if plan.schema_version != 1:
        raise DeviceTreeError("unsupported boot build plan schema")
    if plan.profile_id != profile.profile_id:
        raise DeviceTreeError("boot build plan profile does not match selected device profile")
    boot = profile.data["boot"]
    require_dtb = bool(boot["include_dtb"])
    require_dtbo = bool(boot["separate_dtbo"])
    planned_dtb = _planned_input(plan, "dtb", required=require_dtb)
    planned_dtbo = _planned_input(plan, "dtbo", required=require_dtbo)
    _lock, lock_sha = load_device_tree_format_locks(format_lock)

    dtb_evidence: DtbArtifactEvidence | None = None
    if require_dtb:
        if dtb is None:
            raise DeviceTreeError("profile requires a DTB artifact")
        dtb_evidence = inspect_dtb_artifact(dtb)
        if dtb_evidence.artifact_sha256 != planned_dtb.sha256 or dtb_evidence.artifact_size != planned_dtb.size:
            raise DeviceTreeError("verified DTB does not match the approved boot build plan")
    elif dtb is not None:
        raise DeviceTreeError("selected profile does not permit an in-boot DTB artifact")

    dtbo_evidence: DtboArtifactEvidence | None = None
    if require_dtbo:
        if dtbo is None:
            raise DeviceTreeError("profile requires a DTBO artifact")
        dtbo_evidence = inspect_dtbo_artifact(dtbo)
        limit = profile.data.get("partition_limits", {}).get("dtbo")
        if not isinstance(limit, int) or limit <= 0:
            raise DeviceTreeError("profile lacks a positive DTBO partition limit")
        if dtbo_evidence.artifact_size > limit:
            raise DeviceTreeError("DTBO artifact exceeds the profile partition limit")
        if dtbo_evidence.artifact_sha256 != planned_dtbo.sha256 or dtbo_evidence.artifact_size != planned_dtbo.size:
            raise DeviceTreeError("verified DTBO does not match the approved boot build plan")
    elif dtbo is not None:
        raise DeviceTreeError("selected profile does not permit a separate DTBO artifact")

    return DeviceTreeCandidateEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        boot_plan_sha256=plan.plan_sha256(),
        format_lock_sha256=lock_sha,
        dtb_evidence_sha256=dtb_evidence.evidence_sha256() if dtb_evidence else None,
        dtb_sha256=dtb_evidence.artifact_sha256 if dtb_evidence else None,
        dtb_size=dtb_evidence.artifact_size if dtb_evidence else None,
        dtb_tree_count=dtb_evidence.tree_count if dtb_evidence else None,
        dtbo_evidence_sha256=dtbo_evidence.evidence_sha256() if dtbo_evidence else None,
        dtbo_sha256=dtbo_evidence.artifact_sha256 if dtbo_evidence else None,
        dtbo_size=dtbo_evidence.artifact_size if dtbo_evidence else None,
        dtbo_entry_count=dtbo_evidence.entry_count if dtbo_evidence else None,
    )


def write_device_tree_candidate_evidence(evidence: DeviceTreeCandidateEvidence, destination: Path) -> str:
    if evidence.schema_version != 1:
        raise DeviceTreeError("unsupported device-tree candidate evidence schema")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (not destination.is_file() or destination.is_symlink()):
        raise DeviceTreeError("device-tree evidence destination must be a regular file path")
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise DeviceTreeError("refusing to overwrite stale device-tree evidence temporary file")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    digest = evidence.evidence_sha256()
    if not _SHA256_RE.fullmatch(digest):
        raise DeviceTreeError("internal device-tree evidence digest failure")
    return digest
