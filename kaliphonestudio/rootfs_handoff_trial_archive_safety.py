"""Host-only extraction-safety preflight for an exact reviewed rootfs archive."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import tarfile

from .rootfs_handoff_trial_metadata import (
    RootfsHandoffTrialMetadataError,
    load_rootfs_handoff_trial_metadata_evidence,
    validate_rootfs_handoff_trial_metadata_evidence,
)
from .stable_file import StableFileError, hash_stable_regular_file, read_stable_regular_file

_POLICY = "exact-rootfs-archive-extraction-safety-v1"
_MAX_ARCHIVE = 32 * 1024**3
_MAX_MEMBERS = 500_000
_MAX_EVIDENCE = 8 * 1024**2


class RootfsHandoffTrialArchiveSafetyError(ValueError):
    pass


@dataclass(frozen=True)
class RootfsHandoffTrialArchiveSafetyEvidence:
    schema_version: int
    safety_policy: str
    profile_id: str
    device_serial: str
    metadata_manifest_sha256: str
    payload_manifest_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    entry_count: int
    symlink_count: int
    absolute_symlink_count: int
    relative_symlink_count: int
    hardlink_count: int
    exact_metadata_manifest_bound: bool
    exact_rootfs_bytes_verified: bool
    normalized_paths_unique: bool
    path_namespace_safe: bool
    link_targets_namespace_safe: bool
    no_link_ancestor_pivots: bool
    hardlink_targets_resolved: bool
    special_members_rejected: bool
    extraction_performed: bool
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


def _member_path(name: str) -> str | None:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise RootfsHandoffTrialArchiveSafetyError("unsafe archive member path")
    while name.startswith("./"):
        name = name[2:]
    if name in {"", "."}:
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffTrialArchiveSafetyError("archive member path escapes rootfs namespace")
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
    raise RootfsHandoffTrialArchiveSafetyError(
        f"special archive member is not allowed before extraction: {member.name!r}"
    )


def _resolve_symlink_target(member_path: str, target: str) -> tuple[str, bool]:
    if not isinstance(target, str) or not target or "\x00" in target or "\\" in target:
        raise RootfsHandoffTrialArchiveSafetyError(f"unsafe symlink target for {member_path}")
    absolute = target.startswith("/")
    parts: list[str] = [] if absolute else member_path.split("/")[:-1]
    for part in PurePosixPath(target).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if not parts:
                raise RootfsHandoffTrialArchiveSafetyError(
                    f"symlink target escapes rootfs namespace: {member_path} -> {target}"
                )
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        return ".", absolute
    return "/".join(parts), absolute


def _resolve_hardlink_target(member_path: str, target: str) -> str:
    if not isinstance(target, str) or not target or "\x00" in target or "\\" in target:
        raise RootfsHandoffTrialArchiveSafetyError(f"unsafe hardlink target for {member_path}")
    if target.startswith("/"):
        target = target.lstrip("/")
    while target.startswith("./"):
        target = target[2:]
    if not target:
        raise RootfsHandoffTrialArchiveSafetyError(f"empty hardlink target for {member_path}")
    parts: list[str] = []
    for part in PurePosixPath(target).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            if not parts:
                raise RootfsHandoffTrialArchiveSafetyError(
                    f"hardlink target escapes rootfs namespace: {member_path} -> {target}"
                )
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        raise RootfsHandoffTrialArchiveSafetyError(f"empty hardlink target for {member_path}")
    return "/".join(parts)


def _has_link_ancestor(path: str, link_paths: set[str]) -> str | None:
    parts = path.split("/")
    for end in range(1, len(parts)):
        candidate = "/".join(parts[:end])
        if candidate in link_paths:
            return candidate
    return None


def build_rootfs_handoff_trial_archive_safety_evidence(
    metadata_manifest_path: Path, rootfs_artifact_path: Path
) -> RootfsHandoffTrialArchiveSafetyEvidence:
    try:
        metadata = load_rootfs_handoff_trial_metadata_evidence(Path(metadata_manifest_path))
        validate_rootfs_handoff_trial_metadata_evidence(metadata)
    except RootfsHandoffTrialMetadataError as exc:
        raise RootfsHandoffTrialArchiveSafetyError(str(exc)) from exc

    if any(
        getattr(metadata, name)
        for name in (
            "persistent_write_authorized",
            "persistent_write_performed",
            "phone_storage_written",
            "hardware_verified",
            "beta_release_authorized",
            "beta_gate_credit",
        )
    ):
        raise RootfsHandoffTrialArchiveSafetyError("metadata manifest contains forbidden promotion")

    artifact = Path(rootfs_artifact_path)
    try:
        before = hash_stable_regular_file(
            artifact,
            max_bytes=_MAX_ARCHIVE,
            expected_size=metadata.rootfs_artifact_size,
            label="rootfs trial artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialArchiveSafetyError(str(exc)) from exc
    if before.sha256 != metadata.rootfs_artifact_sha256:
        raise RootfsHandoffTrialArchiveSafetyError("rootfs bytes differ from metadata manifest")

    expected = {item.path: item for item in metadata.entries}
    kinds: dict[str, str] = {}
    symlink_targets: dict[str, tuple[str, bool]] = {}
    hardlink_targets: dict[str, str] = {}
    seen: set[str] = set()
    try:
        with tarfile.open(artifact, "r:*") as archive:
            for index, member in enumerate(archive, 1):
                if index > _MAX_MEMBERS:
                    raise RootfsHandoffTrialArchiveSafetyError("rootfs archive has too many members")
                path = _member_path(member.name)
                if path is None:
                    continue
                if path in seen:
                    raise RootfsHandoffTrialArchiveSafetyError(f"duplicate archive path: {path}")
                seen.add(path)
                prior = expected.get(path)
                if prior is None:
                    raise RootfsHandoffTrialArchiveSafetyError(
                        f"archive member absent from metadata manifest: {path}"
                    )
                kind = _kind(member)
                if kind != prior.kind:
                    raise RootfsHandoffTrialArchiveSafetyError(f"archive member kind drift: {path}")
                kinds[path] = kind
                if kind == "symlink":
                    symlink_targets[path] = _resolve_symlink_target(path, member.linkname)
                elif kind == "hardlink":
                    hardlink_targets[path] = _resolve_hardlink_target(path, member.linkname)
    except (OSError, tarfile.TarError) as exc:
        raise RootfsHandoffTrialArchiveSafetyError(f"cannot inspect rootfs archive safety: {exc}") from exc

    if seen != set(expected):
        raise RootfsHandoffTrialArchiveSafetyError("metadata manifest/archive member scope mismatch")

    link_paths = {path for path, kind in kinds.items() if kind in {"symlink", "hardlink"}}
    for path in sorted(seen, key=lambda value: value.encode("utf-8")):
        ancestor = _has_link_ancestor(path, link_paths)
        if ancestor is not None:
            raise RootfsHandoffTrialArchiveSafetyError(
                f"archive member is nested below link pivot: {path} below {ancestor}"
            )

    for path, target in hardlink_targets.items():
        target_kind = kinds.get(target)
        if target_kind != "file":
            raise RootfsHandoffTrialArchiveSafetyError(
                f"hardlink target is missing or not a regular file: {path} -> {target}"
            )

    try:
        after = hash_stable_regular_file(
            artifact,
            max_bytes=_MAX_ARCHIVE,
            expected_size=metadata.rootfs_artifact_size,
            label="rootfs trial artifact",
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialArchiveSafetyError(str(exc)) from exc
    identity = lambda item: (
        item.sha256,
        item.device,
        item.inode,
        item.size,
        item.mtime_ns,
        item.ctime_ns,
    )
    if identity(before) != identity(after) or after.sha256 != metadata.rootfs_artifact_sha256:
        raise RootfsHandoffTrialArchiveSafetyError("rootfs artifact changed during archive safety inspection")

    absolute_symlink_count = sum(1 for _target, absolute in symlink_targets.values() if absolute)
    evidence = RootfsHandoffTrialArchiveSafetyEvidence(
        schema_version=1,
        safety_policy=_POLICY,
        profile_id=metadata.profile_id,
        device_serial=metadata.device_serial,
        metadata_manifest_sha256=metadata.evidence_sha256(),
        payload_manifest_sha256=metadata.payload_manifest_sha256,
        rootfs_artifact_sha256=metadata.rootfs_artifact_sha256,
        rootfs_artifact_size=metadata.rootfs_artifact_size,
        entry_count=len(seen),
        symlink_count=len(symlink_targets),
        absolute_symlink_count=absolute_symlink_count,
        relative_symlink_count=len(symlink_targets) - absolute_symlink_count,
        hardlink_count=len(hardlink_targets),
        exact_metadata_manifest_bound=True,
        exact_rootfs_bytes_verified=True,
        normalized_paths_unique=True,
        path_namespace_safe=True,
        link_targets_namespace_safe=True,
        no_link_ancestor_pivots=True,
        hardlink_targets_resolved=True,
        special_members_rejected=True,
        extraction_performed=False,
        physical_interaction_performed=False,
        external_device_command_executed=False,
        raw_device_path_bound=False,
        mount_target_bound=False,
        persistent_write_authorized=False,
        persistent_write_performed=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    validate_rootfs_handoff_trial_archive_safety_evidence(evidence)
    return evidence


def validate_rootfs_handoff_trial_archive_safety_evidence(
    evidence: RootfsHandoffTrialArchiveSafetyEvidence,
) -> None:
    if not isinstance(evidence, RootfsHandoffTrialArchiveSafetyEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffTrialArchiveSafetyError("archive safety evidence must be schema-v1 typed evidence")
    if evidence.safety_policy != _POLICY:
        raise RootfsHandoffTrialArchiveSafetyError("unsupported archive safety policy")
    for value in (
        evidence.metadata_manifest_sha256,
        evidence.payload_manifest_sha256,
        evidence.rootfs_artifact_sha256,
    ):
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise RootfsHandoffTrialArchiveSafetyError("archive safety evidence contains invalid SHA-256")
    if evidence.entry_count <= 0 or evidence.rootfs_artifact_size <= 0:
        raise RootfsHandoffTrialArchiveSafetyError("archive safety evidence contains invalid counts")
    if min(
        evidence.symlink_count,
        evidence.absolute_symlink_count,
        evidence.relative_symlink_count,
        evidence.hardlink_count,
    ) < 0:
        raise RootfsHandoffTrialArchiveSafetyError("archive safety evidence contains negative counts")
    if evidence.absolute_symlink_count + evidence.relative_symlink_count != evidence.symlink_count:
        raise RootfsHandoffTrialArchiveSafetyError("symlink classification count mismatch")
    required_true = (
        evidence.exact_metadata_manifest_bound,
        evidence.exact_rootfs_bytes_verified,
        evidence.normalized_paths_unique,
        evidence.path_namespace_safe,
        evidence.link_targets_namespace_safe,
        evidence.no_link_ancestor_pivots,
        evidence.hardlink_targets_resolved,
        evidence.special_members_rejected,
    )
    forbidden = (
        evidence.extraction_performed,
        evidence.physical_interaction_performed,
        evidence.external_device_command_executed,
        evidence.raw_device_path_bound,
        evidence.mount_target_bound,
        evidence.persistent_write_authorized,
        evidence.persistent_write_performed,
        evidence.phone_storage_written,
        evidence.hardware_verified,
        evidence.beta_release_authorized,
        evidence.beta_gate_credit,
    )
    if not all(value is True for value in required_true) or any(value is not False for value in forbidden):
        raise RootfsHandoffTrialArchiveSafetyError("archive safety flags are invalid")


def write_rootfs_handoff_trial_archive_safety_evidence(
    evidence: RootfsHandoffTrialArchiveSafetyEvidence, destination: Path
) -> str:
    validate_rootfs_handoff_trial_archive_safety_evidence(evidence)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RootfsHandoffTrialArchiveSafetyError(
            f"refusing to overwrite existing output: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(evidence.canonical_json())
    return evidence.evidence_sha256()


def load_rootfs_handoff_trial_archive_safety_evidence(
    path: Path,
) -> RootfsHandoffTrialArchiveSafetyEvidence:
    try:
        raw, _ = read_stable_regular_file(
            Path(path), max_bytes=_MAX_EVIDENCE, label="rootfs archive safety evidence"
        )
    except StableFileError as exc:
        raise RootfsHandoffTrialArchiveSafetyError(str(exc)) from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RootfsHandoffTrialArchiveSafetyError(
            "archive safety evidence is not valid UTF-8 JSON"
        ) from exc
    expected_fields = {item.name for item in fields(RootfsHandoffTrialArchiveSafetyEvidence)}
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise RootfsHandoffTrialArchiveSafetyError(
            "archive safety evidence fields do not match schema-v1"
        )
    try:
        evidence = RootfsHandoffTrialArchiveSafetyEvidence(**value)
    except TypeError as exc:
        raise RootfsHandoffTrialArchiveSafetyError(
            "archive safety evidence fields are invalid"
        ) from exc
    validate_rootfs_handoff_trial_archive_safety_evidence(evidence)
    if raw != evidence.canonical_json().encode("utf-8"):
        raise RootfsHandoffTrialArchiveSafetyError(
            "archive safety evidence is not canonical JSON"
        )
    return evidence
