"""Strict loading and artifact revalidation for rescue initramfs evidence."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .rescue_initramfs import RescueInitramfsError, RescueInitramfsEvidence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE_FIELDS = {
    "schema_version",
    "archive_format",
    "compression",
    "source_date_epoch",
    "source_tree_sha256",
    "artifact_sha256",
    "artifact_size",
    "entry_count",
    "init_sha256",
    "reproducible",
}


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RescueInitramfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def evidence_from_dict(raw: dict[str, Any]) -> RescueInitramfsEvidence:
    if not isinstance(raw, dict) or set(raw) != _EVIDENCE_FIELDS:
        raise RescueInitramfsError("invalid rescue initramfs evidence fields")
    if raw["schema_version"] != 1:
        raise RescueInitramfsError("unsupported rescue initramfs evidence schema")
    if raw["archive_format"] != "newc" or raw["compression"] != "none":
        raise RescueInitramfsError("unsupported rescue initramfs artifact format")
    epoch = raw["source_date_epoch"]
    if not isinstance(epoch, int) or isinstance(epoch, bool) or not 0 <= epoch <= 0xFFFFFFFF:
        raise RescueInitramfsError("invalid rescue initramfs SOURCE_DATE_EPOCH")
    artifact_size = raw["artifact_size"]
    if (
        not isinstance(artifact_size, int)
        or isinstance(artifact_size, bool)
        or artifact_size < 512
        or artifact_size % 512 != 0
    ):
        raise RescueInitramfsError("invalid rescue initramfs artifact size")
    entry_count = raw["entry_count"]
    if not isinstance(entry_count, int) or isinstance(entry_count, bool) or entry_count <= 0:
        raise RescueInitramfsError("invalid rescue initramfs entry count")
    if raw["reproducible"] is not True:
        raise RescueInitramfsError("rescue initramfs evidence must prove reproducibility")
    return RescueInitramfsEvidence(
        schema_version=1,
        archive_format="newc",
        compression="none",
        source_date_epoch=epoch,
        source_tree_sha256=_require_sha256(raw["source_tree_sha256"], "source tree"),
        artifact_sha256=_require_sha256(raw["artifact_sha256"], "artifact"),
        artifact_size=artifact_size,
        entry_count=entry_count,
        init_sha256=_require_sha256(raw["init_sha256"], "init"),
        reproducible=True,
    )


def load_rescue_initramfs_evidence(path: Path) -> RescueInitramfsEvidence:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RescueInitramfsError(f"cannot read rescue initramfs evidence: {exc}") from exc
    return evidence_from_dict(raw)


def verify_rescue_initramfs_artifact(
    artifact: Path,
    evidence: RescueInitramfsEvidence,
) -> None:
    """Fail closed if the published artifact no longer matches canonical evidence."""
    # Round-trip through the strict schema validator so callers cannot construct a
    # permissive dataclass instance and bypass evidence invariants.
    evidence_from_dict(json.loads(evidence.canonical_json()))
    if not artifact.is_file():
        raise RescueInitramfsError("rescue initramfs artifact does not exist")
    try:
        size = artifact.stat().st_size
        digest = sha256()
        with artifact.open("rb") as handle:
            magic = handle.read(6)
            if magic != b"070701":
                raise RescueInitramfsError("rescue initramfs is not a newc CPIO archive")
            digest.update(magic)
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise RescueInitramfsError(f"cannot verify rescue initramfs artifact: {exc}") from exc
    if size != evidence.artifact_size:
        raise RescueInitramfsError("rescue initramfs size does not match evidence")
    if digest.hexdigest() != evidence.artifact_sha256:
        raise RescueInitramfsError("rescue initramfs SHA-256 does not match evidence")
