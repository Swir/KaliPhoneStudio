"""Reviewed authority records for strictly reproducible host-built DTB/DTBO artifacts.

A device-tree authority is an immutable host-side review decision over an already
strict A/B reproducibility chain. It never proves that a physical bootloader or
kernel accepts the artifacts and therefore can never claim hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .device_tree import DeviceTreeError
from .device_tree_build import (
    DeviceTreeBuildPlan,
    DeviceTreeBuildRunEvidence,
    DeviceTreeReproducibilityEvidence,
    RawOverlayEvidence,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class DeviceTreeAuthorityRecord:
    schema_version: int
    authority_name: str
    authority_run_id: int
    authority_commit: str
    authority_artifact_id: int
    profile_id: str
    device_tree_plan_sha256: str
    kernel_authority_sha256: str
    build_a_evidence_sha256: str
    build_b_evidence_sha256: str
    reproducibility_evidence_sha256: str
    dtb_sha256: str
    dtb_size: int
    raw_dtbo: tuple[tuple[str, str, int], ...]
    dtbo_image_sha256: str
    dtbo_image_size: int
    dtbo_entry_count: int
    strict_byte_identical: bool
    distinct_build_roots_verified: bool
    reviewed: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def authority_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


_REQUIRED = set(DeviceTreeAuthorityRecord.__dataclass_fields__)


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DeviceTreeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DeviceTreeError(f"{label} must be a positive integer")
    return value


def _raw_overlay_rows(value: Any) -> tuple[tuple[str, str, int], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise DeviceTreeError("device-tree authority raw_dtbo must be non-empty")
    rows: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise DeviceTreeError("invalid device-tree authority raw_dtbo row")
        path, digest, size = item
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise DeviceTreeError("invalid device-tree authority raw overlay path")
        if path in seen:
            raise DeviceTreeError("duplicate device-tree authority raw overlay path")
        seen.add(path)
        rows.append((path, _sha(digest, "raw DTBO SHA-256"), _positive(size, "raw DTBO size")))
    return tuple(rows)


def authority_from_dict(raw: Any) -> DeviceTreeAuthorityRecord:
    if not isinstance(raw, dict) or set(raw) != _REQUIRED:
        raise DeviceTreeError("invalid device-tree authority record fields")
    if raw.get("schema_version") != 1:
        raise DeviceTreeError("unsupported device-tree authority schema")
    name = raw.get("authority_name")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise DeviceTreeError("invalid device-tree authority name")
    commit = raw.get("authority_commit")
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise DeviceTreeError("device-tree authority commit must be a full 40-hex commit")
    profile_id = raw.get("profile_id")
    if not isinstance(profile_id, str) or not _PROFILE_RE.fullmatch(profile_id):
        raise DeviceTreeError("invalid device-tree authority profile_id")
    for field in ("strict_byte_identical", "distinct_build_roots_verified", "reviewed"):
        if raw.get(field) is not True:
            raise DeviceTreeError(f"device-tree authority requires {field}=true")
    if raw.get("hardware_verified") is not False or raw.get("beta_gate_credit") is not False:
        raise DeviceTreeError("host device-tree authority cannot claim hardware/Beta credit")

    return DeviceTreeAuthorityRecord(
        schema_version=1,
        authority_name=name,
        authority_run_id=_positive(raw.get("authority_run_id"), "authority run id"),
        authority_commit=commit,
        authority_artifact_id=_positive(raw.get("authority_artifact_id"), "authority artifact id"),
        profile_id=profile_id,
        device_tree_plan_sha256=_sha(raw.get("device_tree_plan_sha256"), "device-tree plan SHA-256"),
        kernel_authority_sha256=_sha(raw.get("kernel_authority_sha256"), "kernel authority SHA-256"),
        build_a_evidence_sha256=_sha(raw.get("build_a_evidence_sha256"), "build A evidence SHA-256"),
        build_b_evidence_sha256=_sha(raw.get("build_b_evidence_sha256"), "build B evidence SHA-256"),
        reproducibility_evidence_sha256=_sha(raw.get("reproducibility_evidence_sha256"), "reproducibility evidence SHA-256"),
        dtb_sha256=_sha(raw.get("dtb_sha256"), "DTB SHA-256"),
        dtb_size=_positive(raw.get("dtb_size"), "DTB size"),
        raw_dtbo=_raw_overlay_rows(raw.get("raw_dtbo")),
        dtbo_image_sha256=_sha(raw.get("dtbo_image_sha256"), "DTBO image SHA-256"),
        dtbo_image_size=_positive(raw.get("dtbo_image_size"), "DTBO image size"),
        dtbo_entry_count=_positive(raw.get("dtbo_entry_count"), "DTBO entry count"),
        strict_byte_identical=True,
        distinct_build_roots_verified=True,
        reviewed=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def verify_device_tree_authority(
    authority: DeviceTreeAuthorityRecord,
    plan: DeviceTreeBuildPlan,
    run_a: DeviceTreeBuildRunEvidence,
    run_b: DeviceTreeBuildRunEvidence,
    reproducibility: DeviceTreeReproducibilityEvidence,
) -> None:
    authority = authority_from_dict(asdict(authority))
    if plan.schema_version != 1:
        raise DeviceTreeError("unsupported device-tree plan schema")
    if run_a.schema_version != 1 or run_b.schema_version != 1 or reproducibility.schema_version != 1:
        raise DeviceTreeError("unsupported device-tree evidence schema")
    if reproducibility.byte_identical is not True or reproducibility.distinct_build_roots_verified is not True:
        raise DeviceTreeError("device-tree authority requires strict A/B reproducibility")
    if reproducibility.hardware_verified is not False or reproducibility.beta_gate_credit is not False:
        raise DeviceTreeError("host device-tree reproducibility cannot claim hardware/Beta credit")
    if run_a.hardware_verified is not False or run_b.hardware_verified is not False:
        raise DeviceTreeError("host device-tree build evidence cannot claim hardware verification")
    if run_a.beta_gate_credit is not False or run_b.beta_gate_credit is not False:
        raise DeviceTreeError("host device-tree build evidence cannot claim Beta credit")

    exact = {
        "profile_id": plan.profile_id,
        "device_tree_plan_sha256": plan.plan_sha256(),
        "kernel_authority_sha256": plan.kernel_authority_sha256,
        "build_a_evidence_sha256": run_a.evidence_sha256(),
        "build_b_evidence_sha256": run_b.evidence_sha256(),
        "reproducibility_evidence_sha256": reproducibility.evidence_sha256(),
        "dtb_sha256": reproducibility.dtb_sha256,
        "dtb_size": reproducibility.dtb_size,
        "raw_dtbo": reproducibility.raw_dtbo,
        "dtbo_image_sha256": reproducibility.dtbo_image_sha256,
        "dtbo_image_size": reproducibility.dtbo_image_size,
        "dtbo_entry_count": reproducibility.dtbo_entry_count,
    }
    for field, expected in exact.items():
        if getattr(authority, field) != expected:
            raise DeviceTreeError(f"device-tree authority evidence mismatch: {field}")
    if run_a.device_tree_plan_sha256 != plan.plan_sha256() or run_b.device_tree_plan_sha256 != plan.plan_sha256():
        raise DeviceTreeError("device-tree authority build evidence is detached from plan")
    if run_a.kernel_authority_sha256 != plan.kernel_authority_sha256 or run_b.kernel_authority_sha256 != plan.kernel_authority_sha256:
        raise DeviceTreeError("device-tree authority build evidence is detached from kernel authority")
    if reproducibility.device_tree_plan_sha256 != plan.plan_sha256():
        raise DeviceTreeError("device-tree reproducibility is detached from plan")
    if reproducibility.kernel_authority_sha256 != plan.kernel_authority_sha256:
        raise DeviceTreeError("device-tree reproducibility is detached from kernel authority")
    if reproducibility.build_a_evidence_sha256 != run_a.evidence_sha256():
        raise DeviceTreeError("device-tree reproducibility is detached from build A")
    if reproducibility.build_b_evidence_sha256 != run_b.evidence_sha256():
        raise DeviceTreeError("device-tree reproducibility is detached from build B")


def build_reviewed_device_tree_authority(
    *,
    authority_name: str,
    authority_run_id: int,
    authority_commit: str,
    authority_artifact_id: int,
    plan: DeviceTreeBuildPlan,
    run_a: DeviceTreeBuildRunEvidence,
    run_b: DeviceTreeBuildRunEvidence,
    reproducibility: DeviceTreeReproducibilityEvidence,
    reviewed: bool,
) -> DeviceTreeAuthorityRecord:
    if reviewed is not True:
        raise DeviceTreeError("device-tree authority creation requires reviewed=True")
    raw = {
        "schema_version": 1,
        "authority_name": authority_name,
        "authority_run_id": authority_run_id,
        "authority_commit": authority_commit,
        "authority_artifact_id": authority_artifact_id,
        "profile_id": plan.profile_id,
        "device_tree_plan_sha256": plan.plan_sha256(),
        "kernel_authority_sha256": plan.kernel_authority_sha256,
        "build_a_evidence_sha256": run_a.evidence_sha256(),
        "build_b_evidence_sha256": run_b.evidence_sha256(),
        "reproducibility_evidence_sha256": reproducibility.evidence_sha256(),
        "dtb_sha256": reproducibility.dtb_sha256,
        "dtb_size": reproducibility.dtb_size,
        "raw_dtbo": reproducibility.raw_dtbo,
        "dtbo_image_sha256": reproducibility.dtbo_image_sha256,
        "dtbo_image_size": reproducibility.dtbo_image_size,
        "dtbo_entry_count": reproducibility.dtbo_entry_count,
        "strict_byte_identical": True,
        "distinct_build_roots_verified": True,
        "reviewed": True,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    authority = authority_from_dict(raw)
    verify_device_tree_authority(authority, plan, run_a, run_b, reproducibility)
    return authority


def load_device_tree_authority(path: Path) -> DeviceTreeAuthorityRecord:
    if path.is_symlink() or not path.is_file():
        raise DeviceTreeError("device-tree authority record must be a regular non-symlink JSON file")
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise DeviceTreeError("cannot read device-tree authority record") from exc
    if len(raw_bytes) > 128 * 1024:
        raise DeviceTreeError("device-tree authority record is unexpectedly large")
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeviceTreeError("device-tree authority record is not valid UTF-8 JSON") from exc
    return authority_from_dict(raw)


def write_device_tree_authority(authority: DeviceTreeAuthorityRecord, destination: Path) -> str:
    authority = authority_from_dict(asdict(authority))
    if destination.exists():
        raise DeviceTreeError(f"refusing to overwrite existing device-tree authority: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise DeviceTreeError("refusing stale device-tree authority temporary file")
    try:
        temporary.write_text(authority.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return authority.authority_sha256()


def plan_from_json(path: Path) -> DeviceTreeBuildPlan:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw.get("dtbo_outputs"), list):
        raw["dtbo_outputs"] = tuple(raw["dtbo_outputs"])
    return DeviceTreeBuildPlan(**raw)


def run_from_json(path: Path) -> DeviceTreeBuildRunEvidence:
    raw = json.loads(path.read_text(encoding="utf-8"))
    overlays = raw.get("raw_dtbo")
    if not isinstance(overlays, list):
        raise DeviceTreeError("device-tree build raw_dtbo must be a list")
    raw["raw_dtbo"] = tuple(RawOverlayEvidence(**item) for item in overlays)
    return DeviceTreeBuildRunEvidence(**raw)


def reproducibility_from_json(path: Path) -> DeviceTreeReproducibilityEvidence:
    raw = json.loads(path.read_text(encoding="utf-8"))
    overlays = raw.get("raw_dtbo")
    if not isinstance(overlays, list):
        raise DeviceTreeError("device-tree reproducibility raw_dtbo must be a list")
    raw["raw_dtbo"] = tuple(tuple(item) for item in overlays)
    return DeviceTreeReproducibilityEvidence(**raw)
