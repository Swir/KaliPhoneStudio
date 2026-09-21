"""Host-only POSIX/PAX metadata manifest for an exact reviewed rootfs payload."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from typing import Any

from .rootfs_handoff_trial_payload import (
    RootfsHandoffTrialPayloadError,
    load_rootfs_handoff_trial_payload_evidence,
    validate_rootfs_handoff_trial_payload_evidence,
)
from .stable_file import StableFileError, hash_stable_regular_file, read_stable_regular_file

_POLICY = "exact-payload+posix-pax-metadata-v1"
_MAX_ARCHIVE = 32 * 1024**3
_MAX_EVIDENCE = 512 * 1024**2
_MAX_MEMBERS = 500_000
_MAX_PAX_BYTES = 256 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_STRUCTURAL_PAX = {"path", "linkpath", "size", "mtime", "atime", "ctime", "uid", "gid", "uname", "gname"}
_SECURITY_PAX_PREFIXES = ("SCHILY.xattr.", "LIBARCHIVE.xattr.", "SCHILY.acl.")


class RootfsHandoffTrialMetadataError(ValueError):
    pass


@dataclass(frozen=True)
class RootfsTrialMetadataEntry:
    path: str
    kind: str
    mode: int
    uid: int
    gid: int
    uname: str
    gname: str
    pax_headers: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class RootfsHandoffTrialMetadataEvidence:
    schema_version: int
    metadata_policy: str
    profile_id: str
    device_serial: str
    payload_manifest_sha256: str
    execution_gate_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    entry_count: int
    pax_header_count: int
    security_metadata_entry_count: int
    metadata_entries_sha256: str
    entries: tuple[RootfsTrialMetadataEntry, ...]
    exact_payload_manifest_bound: bool
    exact_rootfs_bytes_verified: bool
    archive_member_scope_cross_checked: bool
    posix_ownership_manifested: bool
    pax_metadata_manifested: bool
    interactive_writer_still_required: bool
    explicit_operator_confirmation_still_required: bool
    write_scope_confirmation_still_required: bool
    physical_interaction_performed: bool
    external_device_command_executed: bool
    raw_device_path_bound: bool
    mount_target_bound: bool
    persistent_write_authorized: bool
    persistent_write_performed: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _norm(name: str) -> str | None:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise RootfsHandoffTrialMetadataError("unsafe archive path")
    while name.startswith("./"):
        name = name[2:]
    if name in {"", "."}:
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTrialMetadataError("archive path escapes rootfs namespace")
    return "/".join(path.parts)


def _kind(member: tarfile.TarInfo) -> str:
    if member.isdir():
        return "dir"
    if member.isreg():
        return "file"
    if member.issym():
        return "symlink"
    if member.islnk():
        return "hardlink"
    raise RootfsHandoffTrialMetadataError(f"unsupported tar member type: {member.name!r}")


def _text(value: object, label: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise RootfsHandoffTrialMetadataError(f"{label} is not safe text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise RootfsHandoffTrialMetadataError(f"{label} is not UTF-8") from exc
    if size > maximum:
        raise RootfsHandoffTrialMetadataError(f"{label} is too large")
    return value


def _pax(member: tarfile.TarInfo) -> tuple[tuple[str, str], ...]:
    if not isinstance(member.pax_headers, dict):
        raise RootfsHandoffTrialMetadataError("PAX metadata is not a mapping")
    output: list[tuple[str, str]] = []
    total = 0
    for raw_key, raw_value in member.pax_headers.items():
        key = _text(raw_key, "PAX key")
        value = _text(raw_value, f"PAX value for {key}", maximum=64 * 1024)
        if key in _STRUCTURAL_PAX:
            continue
        total += len(key.encode("utf-8")) + len(value.encode("utf-8"))
        if total > _MAX_PAX_BYTES:
            raise RootfsHandoffTrialMetadataError("PAX metadata exceeds per-member bound")
        output.append((key, value))
    return tuple(sorted(output, key=lambda item: item[0].encode("utf-8")))


def _entry_bytes(entry: RootfsTrialMetadataEntry) -> bytes:
    return (json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build_rootfs_handoff_trial_metadata_manifest(
    payload_manifest_path: Path, rootfs_artifact_path: Path
) -> RootfsHandoffTrialMetadataEvidence:
    try:
        payload = load_rootfs_handoff_trial_payload_evidence(Path(payload_manifest_path))
        validate_rootfs_handoff_trial_payload_evidence(payload)
    except RootfsHandoffTrialPayloadError as exc:
        raise RootfsHandoffTrialMetadataError(str(exc)) from exc
    if not payload.deterministic_write_scope_manifested or not payload.interactive_writer_still_required:
        raise RootfsHandoffTrialMetadataError("payload manifest is not eligible for metadata inspection")
    if any(getattr(payload, name) for name in (
        "persistent_write_authorized", "persistent_write_performed", "phone_storage_written",
        "hardware_verified", "beta_release_authorized", "beta_gate_credit",
    )):
        raise RootfsHandoffTrialMetadataError("payload manifest contains forbidden promotion")

    artifact = Path(rootfs_artifact_path)
    try:
        before = hash_stable_regular_file(
            artifact, max_bytes=_MAX_ARCHIVE, expected_size=payload.rootfs_artifact_size,
            label="rootfs trial artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialMetadataError(str(exc)) from exc
    if before.sha256 != payload.rootfs_artifact_sha256:
        raise RootfsHandoffTrialMetadataError("rootfs bytes differ from payload manifest")

    expected = {item.path: item for item in payload.entries}
    seen: set[str] = set()
    entries: list[RootfsTrialMetadataEntry] = []
    try:
        with tarfile.open(artifact, "r:*") as archive:
            for index, member in enumerate(archive, 1):
                if index > _MAX_MEMBERS:
                    raise RootfsHandoffTrialMetadataError("rootfs archive has too many members")
                path = _norm(member.name)
                if path is None:
                    continue
                if path in seen:
                    raise RootfsHandoffTrialMetadataError(f"duplicate archive path: {path}")
                seen.add(path)
                prior = expected.get(path)
                if prior is None:
                    raise RootfsHandoffTrialMetadataError(f"member absent from payload manifest: {path}")
                kind = _kind(member)
                mode = int(member.mode) & 0o7777
                if kind != prior.kind or mode != prior.mode:
                    raise RootfsHandoffTrialMetadataError(f"member kind/mode drift: {path}")
                if kind == "file" and int(member.size) != prior.size:
                    raise RootfsHandoffTrialMetadataError(f"member size drift: {path}")
                if kind in {"symlink", "hardlink"} and member.linkname != prior.link_target:
                    raise RootfsHandoffTrialMetadataError(f"member link drift: {path}")
                uid, gid = member.uid, member.gid
                if not isinstance(uid, int) or not isinstance(gid, int) or uid < 0 or gid < 0:
                    raise RootfsHandoffTrialMetadataError(f"invalid ownership metadata: {path}")
                entries.append(RootfsTrialMetadataEntry(
                    path, kind, mode, uid, gid,
                    _text(member.uname or "", f"uname for {path}"),
                    _text(member.gname or "", f"gname for {path}"),
                    _pax(member),
                ))
    except (OSError, tarfile.TarError) as exc:
        raise RootfsHandoffTrialMetadataError(f"cannot inspect rootfs metadata: {exc}") from exc
    if seen != set(expected):
        raise RootfsHandoffTrialMetadataError("payload manifest/archive member scope mismatch")

    try:
        after = hash_stable_regular_file(
            artifact, max_bytes=_MAX_ARCHIVE, expected_size=payload.rootfs_artifact_size,
            label="rootfs trial artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialMetadataError(str(exc)) from exc
    identity = lambda item: (item.sha256, item.device, item.inode, item.size, item.mtime_ns, item.ctime_ns)
    if identity(before) != identity(after) or after.sha256 != payload.rootfs_artifact_sha256:
        raise RootfsHandoffTrialMetadataError("rootfs artifact changed during metadata inspection")

    ordered = tuple(sorted(entries, key=lambda item: item.path.encode("utf-8")))
    digest = sha256(b"".join(_entry_bytes(item) for item in ordered)).hexdigest()
    pax_count = sum(len(item.pax_headers) for item in ordered)
    security_count = sum(
        1 for item in ordered
        if any(key.startswith(_SECURITY_PAX_PREFIXES) for key, _ in item.pax_headers)
    )
    evidence = RootfsHandoffTrialMetadataEvidence(
        1, _POLICY, payload.profile_id, payload.device_serial, payload.evidence_sha256(),
        payload.execution_gate_sha256, payload.rootfs_artifact_sha256, payload.rootfs_artifact_size,
        len(ordered), pax_count, security_count, digest, ordered,
        True, True, True, True, True, True, True, True,
        False, False, False, False, False, False, False, False, False, False,
    )
    validate_rootfs_handoff_trial_metadata_evidence(evidence)
    return evidence


def validate_rootfs_handoff_trial_metadata_evidence(evidence: RootfsHandoffTrialMetadataEvidence) -> None:
    if not isinstance(evidence, RootfsHandoffTrialMetadataEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTrialMetadataError("metadata manifest must be schema-v1 typed evidence")
    if evidence.metadata_policy != _POLICY:
        raise RootfsHandoffTrialMetadataError("unsupported metadata policy")
    for value in (evidence.payload_manifest_sha256, evidence.execution_gate_sha256,
                  evidence.rootfs_artifact_sha256, evidence.metadata_entries_sha256):
        if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
            raise RootfsHandoffTrialMetadataError("metadata manifest contains invalid SHA-256")
    if evidence.entry_count <= 0 or evidence.entry_count != len(evidence.entries):
        raise RootfsHandoffTrialMetadataError("metadata entry count mismatch")
    paths = [item.path for item in evidence.entries]
    if paths != sorted(paths, key=lambda value: value.encode("utf-8")) or len(paths) != len(set(paths)):
        raise RootfsHandoffTrialMetadataError("metadata entries are not deterministic unique path order")
    digest = sha256()
    pax_count = 0
    security_count = 0
    for item in evidence.entries:
        if _norm(item.path) != item.path or item.kind not in {"file", "dir", "symlink", "hardlink"}:
            raise RootfsHandoffTrialMetadataError("invalid metadata entry path/type")
        if not 0 <= item.mode <= 0o7777 or item.uid < 0 or item.gid < 0:
            raise RootfsHandoffTrialMetadataError("invalid POSIX metadata entry")
        _text(item.uname, "uname")
        _text(item.gname, "gname")
        keys = [key for key, _ in item.pax_headers]
        if keys != sorted(keys, key=lambda value: value.encode("utf-8")) or len(keys) != len(set(keys)):
            raise RootfsHandoffTrialMetadataError("PAX metadata is not deterministic unique key order")
        for key, value in item.pax_headers:
            _text(key, "PAX key")
            _text(value, "PAX value", maximum=64 * 1024)
            if key in _STRUCTURAL_PAX:
                raise RootfsHandoffTrialMetadataError("structural PAX key leaked into restorable metadata")
        pax_count += len(item.pax_headers)
        if any(key.startswith(_SECURITY_PAX_PREFIXES) for key, _ in item.pax_headers):
            security_count += 1
        digest.update(_entry_bytes(item))
    if pax_count != evidence.pax_header_count or security_count != evidence.security_metadata_entry_count:
        raise RootfsHandoffTrialMetadataError("metadata summary mismatch")
    if digest.hexdigest() != evidence.metadata_entries_sha256:
        raise RootfsHandoffTrialMetadataError("metadata digest mismatch")
    required_true = (
        evidence.exact_payload_manifest_bound, evidence.exact_rootfs_bytes_verified,
        evidence.archive_member_scope_cross_checked, evidence.posix_ownership_manifested,
        evidence.pax_metadata_manifested, evidence.interactive_writer_still_required,
        evidence.explicit_operator_confirmation_still_required, evidence.write_scope_confirmation_still_required,
    )
    forbidden = (
        evidence.physical_interaction_performed, evidence.external_device_command_executed,
        evidence.raw_device_path_bound, evidence.mount_target_bound, evidence.persistent_write_authorized,
        evidence.persistent_write_performed, evidence.phone_storage_written, evidence.hardware_verified,
        evidence.beta_release_authorized, evidence.beta_gate_credit,
    )
    if not all(value is True for value in required_true) or any(value is not False for value in forbidden):
        raise RootfsHandoffTrialMetadataError("metadata manifest safety flags are invalid")


def write_rootfs_handoff_trial_metadata_evidence(
    evidence: RootfsHandoffTrialMetadataEvidence, destination: Path
) -> str:
    validate_rootfs_handoff_trial_metadata_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialMetadataError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(evidence.canonical_json())
    return evidence.evidence_sha256()


def load_rootfs_handoff_trial_metadata_evidence(path: Path) -> RootfsHandoffTrialMetadataEvidence:
    try:
        raw, _ = read_stable_regular_file(Path(path), max_bytes=_MAX_EVIDENCE, label="rootfs trial metadata manifest")
    except StableFileError as exc:
        raise RootfsHandoffTrialMetadataError(str(exc)) from exc
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialMetadataError("metadata manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {item.name for item in fields(RootfsHandoffTrialMetadataEvidence)}:
        raise RootfsHandoffTrialMetadataError("metadata manifest fields do not match schema-v1")
    entry_fields = {item.name for item in fields(RootfsTrialMetadataEntry)}
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list):
        raise RootfsHandoffTrialMetadataError("metadata entries do not match schema-v1")
    entries: list[RootfsTrialMetadataEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != entry_fields:
            raise RootfsHandoffTrialMetadataError("metadata entry fields do not match schema-v1")
        pax = raw_entry.get("pax_headers")
        if not isinstance(pax, list) or any(not isinstance(item, list) or len(item) != 2 for item in pax):
            raise RootfsHandoffTrialMetadataError("metadata PAX headers do not match schema-v1")
        item = dict(raw_entry)
        item["pax_headers"] = tuple((pair[0], pair[1]) for pair in pax)
        entries.append(RootfsTrialMetadataEntry(**item))
    value["entries"] = tuple(entries)
    try:
        evidence = RootfsHandoffTrialMetadataEvidence(**value)
    except TypeError as exc:
        raise RootfsHandoffTrialMetadataError("metadata manifest fields are invalid") from exc
    validate_rootfs_handoff_trial_metadata_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialMetadataError("metadata manifest is not canonical JSON")
    return evidence
