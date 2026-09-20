"""Deterministic, non-writing write-scope manifest for a reviewed rootfs trial."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from typing import Any

from .rootfs_handoff_trial_execution_gate import (
    RootfsHandoffTrialExecutionGateError,
    load_rootfs_handoff_trial_execution_gate_evidence,
    validate_rootfs_handoff_trial_execution_gate_evidence,
)
from .stable_file import StableFileError, hash_stable_regular_file, read_stable_regular_file

_POLICY = "exact-gate+exact-rootfs+safe-tar-scope+expanded-capacity-v1"
_MAX_ARCHIVE = 32 * 1024**3
_MAX_MANIFEST = 512 * 1024**2
_MAX_EXPANDED = 256 * 1024**3
_MAX_MEMBERS = 500_000
_MAX_TEXT = 4096
_MIN_MARGIN = 64 * 1024**2
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class RootfsHandoffTrialPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class RootfsTrialPayloadEntry:
    path: str
    kind: str
    size: int
    mode: int
    link_target: str | None
    resolved_link_target: str | None
    content_sha256: str | None


@dataclass(frozen=True)
class RootfsHandoffTrialPayloadEvidence:
    schema_version: int
    payload_policy: str
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    execution_gate_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    staging_subpath: str
    candidate_partition_role: str
    observed_filesystem: str
    observed_encryption_state: str
    reviewed_required_free_bytes: int
    observed_free_bytes: int
    entry_count: int
    regular_file_count: int
    directory_count: int
    symlink_count: int
    hardlink_count: int
    regular_payload_bytes: int
    capacity_margin_bytes: int
    minimum_required_free_bytes: int
    entries_sha256: str
    entries: tuple[RootfsTrialPayloadEntry, ...]
    exact_execution_gate_bound: bool
    exact_rootfs_bytes_verified: bool
    deterministic_write_scope_manifested: bool
    path_traversal_absent: bool
    duplicate_paths_absent: bool
    unsupported_special_files_absent: bool
    expanded_capacity_requirement_satisfied: bool
    interactive_writer_still_required: bool
    explicit_operator_confirmation_still_required: bool
    write_scope_confirmation_still_required: bool
    physical_interaction_performed: bool
    external_device_command_executed: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    trial_execution_allowed: bool
    persistent_write_authorized: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    storage_verified: bool
    recovery_verified: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode()).hexdigest()


_TRUE = (
    "exact_execution_gate_bound", "exact_rootfs_bytes_verified",
    "deterministic_write_scope_manifested", "path_traversal_absent",
    "duplicate_paths_absent", "unsupported_special_files_absent",
    "expanded_capacity_requirement_satisfied", "interactive_writer_still_required",
    "explicit_operator_confirmation_still_required", "write_scope_confirmation_still_required",
)
_FALSE = (
    "physical_interaction_performed", "external_device_command_executed",
    "raw_device_path_bound", "mount_target_bound", "trial_execution_allowed",
    "persistent_write_authorized", "persistent_write_performed", "phone_storage_written",
    "storage_verified", "recovery_verified", "hardware_verified",
    "beta_release_authorized", "beta_gate_credit",
)


def _text(value: object, label: str, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value:
        raise RootfsHandoffTrialPayloadError(f"{label} is empty")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise RootfsHandoffTrialPayloadError(f"{label} is not valid UTF-8 text") from exc
    if len(encoded) > maximum or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise RootfsHandoffTrialPayloadError(f"{label} is unsafe or too long")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise RootfsHandoffTrialPayloadError(f"{label} must be lowercase SHA-256")
    return value


def _path(name: str) -> str | None:
    _text(name, "archive path")
    if "\\" in name or "\x00" in name:
        raise RootfsHandoffTrialPayloadError("archive path contains unsafe separator/NUL")
    while name.startswith("./"):
        name = name[2:]
    if name in {"", "."}:
        return None
    if name.startswith("/"):
        raise RootfsHandoffTrialPayloadError("archive path must be relative")
    parts = PurePosixPath(name).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RootfsHandoffTrialPayloadError("archive path is not safe normalized relative scope")
    return "/".join(parts)


def _link(member_path: str, target: str, *, hard: bool) -> tuple[str, str]:
    _text(target, "archive link target")
    if "\\" in target or "\x00" in target or (hard and target.startswith("/")):
        raise RootfsHandoffTrialPayloadError("archive link target is unsafe")
    resolved = [] if target.startswith("/") or hard else member_path.split("/")[:-1]
    for part in PurePosixPath(target.lstrip("/")).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not resolved:
                raise RootfsHandoffTrialPayloadError("archive link target escapes rootfs namespace")
            resolved.pop()
        else:
            resolved.append(part)
    if not resolved:
        raise RootfsHandoffTrialPayloadError("archive link target resolves to root")
    return target, "/".join(resolved)


def _entry_bytes(entry: RootfsTrialPayloadEntry) -> bytes:
    return (json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n").encode()


def _hash_member(handle: Any, expected: int) -> str:
    digest, total = sha256(), 0
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > expected:
            raise RootfsHandoffTrialPayloadError("tar member exceeds declared size")
        digest.update(chunk)
    if total != expected:
        raise RootfsHandoffTrialPayloadError("tar member content size mismatch")
    return digest.hexdigest()


def _inspect(path: Path, free_bytes: int) -> tuple[tuple[RootfsTrialPayloadEntry, ...], dict[str, int]]:
    entries: list[RootfsTrialPayloadEntry] = []
    by_path: dict[str, RootfsTrialPayloadEntry] = {}
    counts = {"file": 0, "dir": 0, "symlink": 0, "hardlink": 0}
    hardlinks: list[tuple[str, str]] = []
    payload = 0
    try:
        archive = tarfile.open(path, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise RootfsHandoffTrialPayloadError(f"cannot open rootfs tar: {exc}") from exc
    try:
        for index, member in enumerate(archive, 1):
            if index > _MAX_MEMBERS:
                raise RootfsHandoffTrialPayloadError("rootfs tar has too many members")
            normalized = _path(member.name)
            if normalized is None:
                continue
            if normalized in by_path:
                raise RootfsHandoffTrialPayloadError(f"duplicate normalized path: {normalized}")
            size = member.size
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise RootfsHandoffTrialPayloadError("invalid tar member size")
            mode = int(member.mode) & 0o7777
            link_target = resolved = content_sha = None
            if member.isdir():
                kind, size = "dir", 0
            elif member.isreg():
                kind = "file"
                payload += size
                if payload > _MAX_EXPANDED or payload > free_bytes:
                    raise RootfsHandoffTrialPayloadError("expanded payload exceeds observed free-space bound")
                stream = archive.extractfile(member)
                if stream is None:
                    raise RootfsHandoffTrialPayloadError(f"cannot read tar member: {normalized}")
                try:
                    content_sha = _hash_member(stream, size)
                finally:
                    stream.close()
            elif member.issym():
                kind, size = "symlink", 0
                link_target, resolved = _link(normalized, member.linkname, hard=False)
            elif member.islnk():
                kind, size = "hardlink", 0
                link_target, resolved = _link(normalized, member.linkname, hard=True)
                hardlinks.append((normalized, resolved))
            else:
                raise RootfsHandoffTrialPayloadError(
                    f"unsupported special tar member {normalized!r}; device nodes/FIFOs are refused"
                )
            entry = RootfsTrialPayloadEntry(normalized, kind, size, mode, link_target, resolved, content_sha)
            entries.append(entry)
            by_path[normalized] = entry
            counts[kind] += 1
    except (OSError, tarfile.TarError) as exc:
        raise RootfsHandoffTrialPayloadError(f"cannot inspect rootfs tar: {exc}") from exc
    finally:
        archive.close()
    if not entries or not counts["file"]:
        raise RootfsHandoffTrialPayloadError("rootfs tar has no regular payload files")
    for source, target in hardlinks:
        seen = {source}
        while True:
            if target in seen:
                raise RootfsHandoffTrialPayloadError(f"hardlink cycle: {source}")
            seen.add(target)
            target_entry = by_path.get(target)
            if target_entry is None:
                raise RootfsHandoffTrialPayloadError(f"hardlink target missing: {source} -> {target}")
            if target_entry.kind == "file":
                break
            if target_entry.kind != "hardlink" or target_entry.resolved_link_target is None:
                raise RootfsHandoffTrialPayloadError(f"hardlink target is not a regular file: {source}")
            target = target_entry.resolved_link_target
    return tuple(sorted(entries, key=lambda item: item.path.encode())), {**counts, "payload": payload}


def build_rootfs_handoff_trial_payload_manifest(
    execution_gate_path: Path, rootfs_artifact_path: Path
) -> RootfsHandoffTrialPayloadEvidence:
    try:
        gate = load_rootfs_handoff_trial_execution_gate_evidence(Path(execution_gate_path))
        validate_rootfs_handoff_trial_execution_gate_evidence(gate)
    except RootfsHandoffTrialExecutionGateError as exc:
        raise RootfsHandoffTrialPayloadError(str(exc)) from exc
    if not gate.execution_gate_passed or not gate.local_rootfs_exact_bytes_verified or not gate.interactive_writer_required:
        raise RootfsHandoffTrialPayloadError("execution gate is not ready for payload inspection")
    if any(getattr(gate, name) for name in (
        "trial_execution_allowed", "persistent_write_authorized", "persistent_write_performed",
        "phone_storage_written", "hardware_verified", "beta_release_authorized", "beta_gate_credit",
    )):
        raise RootfsHandoffTrialPayloadError("execution gate contains invalid write/hardware/Beta claim")

    artifact = Path(rootfs_artifact_path)
    try:
        before = hash_stable_regular_file(
            artifact, max_bytes=_MAX_ARCHIVE, expected_size=gate.rootfs_artifact_size,
            label="rootfs trial artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialPayloadError(str(exc)) from exc
    if before.sha256 != gate.rootfs_artifact_sha256:
        raise RootfsHandoffTrialPayloadError("rootfs artifact digest differs from execution gate")

    entries, counts = _inspect(artifact, gate.observed_free_bytes)
    try:
        after = hash_stable_regular_file(
            artifact, max_bytes=_MAX_ARCHIVE, expected_size=gate.rootfs_artifact_size,
            label="rootfs trial artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialPayloadError(str(exc)) from exc
    identity = lambda item: (item.sha256, item.device, item.inode, item.size, item.mtime_ns, item.ctime_ns)
    if identity(before) != identity(after) or after.sha256 != gate.rootfs_artifact_sha256:
        raise RootfsHandoffTrialPayloadError("rootfs artifact changed during payload inspection")

    payload = counts["payload"]
    margin = max(_MIN_MARGIN, (payload + 19) // 20)
    minimum = payload + margin
    if gate.required_free_bytes < minimum:
        raise RootfsHandoffTrialPayloadError(
            "reviewed free-space requirement is below expanded payload plus deterministic safety margin"
        )
    if gate.observed_free_bytes < minimum:
        raise RootfsHandoffTrialPayloadError("execution-time free space is below expanded payload requirement")
    entries_digest = sha256(b"".join(_entry_bytes(item) for item in entries)).hexdigest()

    evidence = RootfsHandoffTrialPayloadEvidence(
        1, _POLICY, gate.profile_id, gate.device_serial, gate.firmware_build, gate.firmware_fingerprint,
        gate.evidence_sha256(), before.sha256, before.size, gate.staging_subpath,
        gate.candidate_partition_role, gate.observed_filesystem, gate.observed_encryption_state,
        gate.required_free_bytes, gate.observed_free_bytes, len(entries), counts["file"], counts["dir"],
        counts["symlink"], counts["hardlink"], payload, margin, minimum, entries_digest, entries,
        True, True, True, True, True, True, True, True, True, True,
        False, False, False, False, False, False, False, False, False, False, False, False, False,
    )
    validate_rootfs_handoff_trial_payload_evidence(evidence)
    return evidence


def validate_rootfs_handoff_trial_payload_evidence(evidence: RootfsHandoffTrialPayloadEvidence) -> None:
    if not isinstance(evidence, RootfsHandoffTrialPayloadEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTrialPayloadError("payload manifest must be schema-v1 typed evidence")
    if evidence.payload_policy != _POLICY:
        raise RootfsHandoffTrialPayloadError("unsupported payload policy")
    _sha(evidence.execution_gate_sha256, "execution gate")
    _sha(evidence.rootfs_artifact_sha256, "rootfs artifact")
    _sha(evidence.entries_sha256, "entries")
    if evidence.entry_count != len(evidence.entries) or evidence.regular_file_count <= 0:
        raise RootfsHandoffTrialPayloadError("payload entry counts are invalid")
    expected_count = evidence.regular_file_count + evidence.directory_count + evidence.symlink_count + evidence.hardlink_count
    if evidence.entry_count != expected_count:
        raise RootfsHandoffTrialPayloadError("payload type counts do not sum to entry count")
    if evidence.minimum_required_free_bytes != evidence.regular_payload_bytes + evidence.capacity_margin_bytes:
        raise RootfsHandoffTrialPayloadError("expanded capacity math is invalid")
    if evidence.reviewed_required_free_bytes < evidence.minimum_required_free_bytes or evidence.observed_free_bytes < evidence.minimum_required_free_bytes:
        raise RootfsHandoffTrialPayloadError("expanded capacity bound is not satisfied")
    paths = [item.path for item in evidence.entries]
    if paths != sorted(paths, key=lambda value: value.encode()) or len(paths) != len(set(paths)):
        raise RootfsHandoffTrialPayloadError("payload entries are not unique deterministic path order")
    digest, payload, counts = sha256(), 0, {"file": 0, "dir": 0, "symlink": 0, "hardlink": 0}
    for item in evidence.entries:
        if _path(item.path) != item.path or item.kind not in counts or not 0 <= item.mode <= 0o7777:
            raise RootfsHandoffTrialPayloadError("payload entry metadata is invalid")
        counts[item.kind] += 1
        if item.kind == "file":
            if item.size < 0 or item.link_target is not None or item.resolved_link_target is not None:
                raise RootfsHandoffTrialPayloadError("regular payload entry is invalid")
            _sha(item.content_sha256, "regular file content")
            payload += item.size
        elif item.kind == "dir":
            if item.size or item.link_target is not None or item.resolved_link_target is not None or item.content_sha256 is not None:
                raise RootfsHandoffTrialPayloadError("directory payload entry is invalid")
        else:
            if item.size or item.link_target is None or item.resolved_link_target is None or item.content_sha256 is not None:
                raise RootfsHandoffTrialPayloadError("link payload entry is invalid")
            _, resolved = _link(item.path, item.link_target, hard=item.kind == "hardlink")
            if resolved != item.resolved_link_target:
                raise RootfsHandoffTrialPayloadError("link target resolution drifted")
        digest.update(_entry_bytes(item))
    if payload != evidence.regular_payload_bytes or digest.hexdigest() != evidence.entries_sha256:
        raise RootfsHandoffTrialPayloadError("payload summary/digest mismatch")
    if counts != {"file": evidence.regular_file_count, "dir": evidence.directory_count,
                  "symlink": evidence.symlink_count, "hardlink": evidence.hardlink_count}:
        raise RootfsHandoffTrialPayloadError("payload type summary mismatch")
    if any(getattr(evidence, name) is not True for name in _TRUE) or any(getattr(evidence, name) is not False for name in _FALSE):
        raise RootfsHandoffTrialPayloadError("payload manifest safety flags are invalid")


def write_rootfs_handoff_trial_payload_evidence(evidence: RootfsHandoffTrialPayloadEvidence, destination: Path) -> str:
    validate_rootfs_handoff_trial_payload_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialPayloadError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(evidence.canonical_json())
    return evidence.evidence_sha256()


def load_rootfs_handoff_trial_payload_evidence(path: Path) -> RootfsHandoffTrialPayloadEvidence:
    try:
        raw, _ = read_stable_regular_file(Path(path), max_bytes=_MAX_MANIFEST, label="rootfs trial payload manifest")
    except StableFileError as exc:
        raise RootfsHandoffTrialPayloadError(str(exc)) from exc
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialPayloadError("payload manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(RootfsHandoffTrialPayloadEvidence)}:
        raise RootfsHandoffTrialPayloadError("payload manifest fields do not match schema-v1")
    entry_fields = {item.name for item in fields(RootfsTrialPayloadEntry)}
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list) or any(not isinstance(item, dict) or set(item) != entry_fields for item in raw_entries):
        raise RootfsHandoffTrialPayloadError("payload entries do not match schema-v1")
    value["entries"] = tuple(RootfsTrialPayloadEntry(**item) for item in raw_entries)
    try:
        evidence = RootfsHandoffTrialPayloadEvidence(**value)
    except TypeError as exc:
        raise RootfsHandoffTrialPayloadError("payload manifest fields are invalid") from exc
    validate_rootfs_handoff_trial_payload_evidence(evidence)
    if raw != evidence.canonical_json().encode():
        raise RootfsHandoffTrialPayloadError("payload manifest is not canonical JSON")
    return evidence
