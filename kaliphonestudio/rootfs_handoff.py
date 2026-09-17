"""Fail-closed rootfs staging/handoff discovery contracts.

This layer deliberately stops *before* selecting a block device, mount point or
write target. A profile may describe source-pinned storage/encryption facts that
must be checked on the exact physical device, but the common core will not turn
those hints into a storage path or an authorization to modify phone storage.

The resulting evidence is therefore useful preparation for physical bring-up,
not hardware support and not Beta-gate credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import urlsplit

from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .profiles import DeviceProfile
from .rootfs_authority import RootfsAuthorityRecord

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SAFE_FEATURE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._=:+-]*$")
_REQUIRED_DISCOVERY_EVIDENCE = frozenset(
    {
        "block-topology",
        "filesystem-identity",
        "encryption-state",
        "free-space",
        "recovery-plan",
    }
)
_ROOTFS_HANDOFF_FIELDS = frozenset(
    {
        "schema_version",
        "state",
        "layout_source_name",
        "layout_source_path",
        "layout_source_blob_sha1",
        "storage_bus",
        "partition_hint",
        "expected_filesystems",
        "encryption_features",
        "metadata_partition",
        "required_physical_evidence",
        "forbidden_partitions",
        "target_selection_allowed",
        "persistent_write_authorized",
    }
)


class RootfsHandoffError(ValueError):
    pass


@dataclass(frozen=True)
class RootfsHandoffContract:
    schema_version: int
    profile_id: str
    state: str
    layout_source_name: str
    layout_source_url: str
    layout_source_commit: str
    layout_source_path: str
    layout_source_blob_sha1: str
    storage_bus: str
    partition_hint: str
    expected_filesystems: tuple[str, ...]
    encryption_features: tuple[str, ...]
    metadata_partition: str
    required_physical_evidence: tuple[str, ...]
    forbidden_partitions: tuple[str, ...]
    target_selection_allowed: bool
    persistent_write_authorized: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def contract_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RootfsHandoffSourceEvidence:
    schema_version: int
    profile_id: str
    rootfs_handoff_contract_sha256: str
    source_url: str
    source_commit: str
    source_path: str
    source_blob_sha1: str
    checkout_head: str
    tracked_tree_clean: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RootfsHandoffAssessmentEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    physical_candidate_gate_sha256: str
    rootfs_handoff_contract_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    layout_source_name: str
    layout_source_commit: str
    layout_source_path: str
    layout_source_blob_sha1: str
    storage_bus: str
    partition_hint: str
    expected_filesystems: tuple[str, ...]
    encryption_features: tuple[str, ...]
    metadata_partition: str
    required_physical_evidence: tuple[str, ...]
    forbidden_partitions: tuple[str, ...]
    target_selected: bool
    storage_path_bound: bool
    write_authorized: bool
    handoff_ready: bool
    manual_review_required: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RootfsHandoffError(f"{label} must be non-empty text")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RootfsHandoffError(f"{label} contains control data")
    return value


def _safe_https_url(value: object, label: str) -> str:
    value = _safe_text(value, label)
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RootfsHandoffError(f"{label} must be credential-free HTTPS without query/fragment")
    return value


def _safe_id(value: object, label: str) -> str:
    value = _safe_text(value, label)
    if not _SAFE_ID_RE.fullmatch(value):
        raise RootfsHandoffError(f"{label} must be a safe lowercase identifier")
    return value


def _safe_relative(value: object, label: str) -> str:
    value = _safe_text(value, label)
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsHandoffError(f"{label} must be a safe relative POSIX path")
    if any("\\" in part for part in path.parts):
        raise RootfsHandoffError(f"{label} must be a safe relative POSIX path")
    return path.as_posix()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsHandoffError(f"{label} must be a lowercase SHA-256")
    return value


def _git_sha1(value: object, label: str) -> str:
    if not isinstance(value, str) or not _GIT_SHA1_RE.fullmatch(value):
        raise RootfsHandoffError(f"{label} must be a full lowercase Git SHA-1")
    return value


def _safe_unique_ids(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RootfsHandoffError(f"{label} must be a non-empty list")
    result = tuple(_safe_id(item, label) for item in value)
    if len(result) != len(set(result)):
        raise RootfsHandoffError(f"{label} must not contain duplicates")
    return result


def _safe_unique_features(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RootfsHandoffError(f"{label} must be a non-empty list")
    result: list[str] = []
    for item in value:
        text = _safe_text(item, label)
        if not _SAFE_FEATURE_RE.fullmatch(text):
            raise RootfsHandoffError(f"{label} contains an unsafe feature token")
        result.append(text)
    if len(result) != len(set(result)):
        raise RootfsHandoffError(f"{label} must not contain duplicates")
    return tuple(result)


def rootfs_handoff_contract(profile: DeviceProfile) -> RootfsHandoffContract:
    """Validate and resolve the profile's discovery-only rootfs handoff contract."""
    if not isinstance(profile, DeviceProfile):
        raise RootfsHandoffError("profile must be typed DeviceProfile evidence")
    raw = profile.data.get("rootfs_handoff")
    if not isinstance(raw, dict) or set(raw) != _ROOTFS_HANDOFF_FIELDS:
        raise RootfsHandoffError("profile rootfs_handoff must contain exactly the schema-v1 fields")
    if raw.get("schema_version") != 1:
        raise RootfsHandoffError("unsupported rootfs_handoff schema")
    if raw.get("state") != "discovery-only":
        raise RootfsHandoffError("rootfs_handoff state must remain discovery-only")
    if raw.get("target_selection_allowed") is not False:
        raise RootfsHandoffError("rootfs_handoff must not select a target before physical review")
    if raw.get("persistent_write_authorized") is not False:
        raise RootfsHandoffError("rootfs_handoff cannot authorize persistent writes")

    source_name = _safe_text(raw.get("layout_source_name"), "layout source name")
    sources = [item for item in profile.data.get("sources", []) if item.get("name") == source_name]
    if len(sources) != 1:
        raise RootfsHandoffError("layout source must resolve exactly one pinned profile source")
    source = sources[0]
    source_url = _safe_https_url(source.get("url"), "layout source URL")
    source_commit = _git_sha1(source.get("commit"), "layout source commit")
    source_path = _safe_relative(raw.get("layout_source_path"), "layout source path")
    source_blob = _git_sha1(raw.get("layout_source_blob_sha1"), "layout source blob SHA-1")

    storage_bus = _safe_id(raw.get("storage_bus"), "storage bus")
    partition_hint = _safe_id(raw.get("partition_hint"), "partition hint")
    metadata_partition = _safe_id(raw.get("metadata_partition"), "metadata partition")
    filesystems = _safe_unique_ids(raw.get("expected_filesystems"), "expected filesystems")
    features = _safe_unique_features(raw.get("encryption_features"), "encryption features")
    required = _safe_unique_ids(raw.get("required_physical_evidence"), "required physical evidence")
    if not _REQUIRED_DISCOVERY_EVIDENCE.issubset(required):
        missing = sorted(_REQUIRED_DISCOVERY_EVIDENCE - set(required))
        raise RootfsHandoffError(
            "rootfs_handoff is missing mandatory physical evidence: " + ", ".join(missing)
        )
    forbidden = _safe_unique_ids(raw.get("forbidden_partitions"), "forbidden partitions")
    if metadata_partition not in forbidden:
        raise RootfsHandoffError("metadata partition must remain forbidden during discovery")
    if partition_hint in forbidden:
        raise RootfsHandoffError("partition hint cannot also be a forbidden partition")

    system_partitions = set(profile.data.get("ab_partitions", []))
    if "super" in profile.data.get("partition_limits", {}):
        system_partitions.add("super")
    missing_forbidden = sorted(system_partitions - set(forbidden))
    if missing_forbidden:
        raise RootfsHandoffError(
            "discovery-only rootfs_handoff must forbid all system/A-B containers: "
            + ", ".join(missing_forbidden)
        )

    return RootfsHandoffContract(
        schema_version=1,
        profile_id=profile.profile_id,
        state="discovery-only",
        layout_source_name=source_name,
        layout_source_url=source_url,
        layout_source_commit=source_commit,
        layout_source_path=source_path,
        layout_source_blob_sha1=source_blob,
        storage_bus=storage_bus,
        partition_hint=partition_hint,
        expected_filesystems=filesystems,
        encryption_features=features,
        metadata_partition=metadata_partition,
        required_physical_evidence=required,
        forbidden_partitions=forbidden,
        target_selection_allowed=False,
        persistent_write_authorized=False,
    )


def bind_rootfs_handoff_assessment(
    profile: DeviceProfile,
    physical_gate: PhysicalCandidateGateEvidence,
    rootfs_authority: RootfsAuthorityRecord,
) -> RootfsHandoffAssessmentEvidence:
    """Bind discovery requirements to one exact physical candidate and rootfs authority.

    This never selects a target, never produces a device path and never authorizes
    a write. It is a precondition record for later physical storage discovery.
    """
    contract = rootfs_handoff_contract(profile)
    if not isinstance(physical_gate, PhysicalCandidateGateEvidence) or physical_gate.schema_version != 1:
        raise RootfsHandoffError("physical candidate gate must be schema-v1 typed evidence")
    if physical_gate.profile_id != profile.profile_id:
        raise RootfsHandoffError("physical candidate gate profile mismatch")
    if physical_gate.ready_for_temporary_boot_offer is not True:
        raise RootfsHandoffError("physical candidate gate is not ready for a temporary-boot offer")
    if physical_gate.reviewed_authorities_bound is not True or physical_gate.exact_physical_baseline_bound is not True:
        raise RootfsHandoffError("physical candidate gate lacks exact reviewed authority/baseline binding")
    if physical_gate.temporary_boot_executed is not False or physical_gate.phone_storage_written is not False:
        raise RootfsHandoffError("rootfs handoff assessment must precede execution or storage writes")
    if physical_gate.hardware_verified is not False or physical_gate.beta_gate_credit is not False:
        raise RootfsHandoffError("host physical-candidate gate cannot claim hardware/Beta credit")

    if not isinstance(rootfs_authority, RootfsAuthorityRecord) or rootfs_authority.schema_version != 1:
        raise RootfsHandoffError("rootfs authority must be schema-v1 typed evidence")
    if rootfs_authority.reviewed is not True or rootfs_authority.strict_byte_identical is not True:
        raise RootfsHandoffError("rootfs authority must be reviewed and strict-byte-identical")
    if rootfs_authority.hardware_verified is not False or rootfs_authority.beta_gate_credit is not False:
        raise RootfsHandoffError("host rootfs authority cannot claim hardware/Beta credit")
    if rootfs_authority.architecture != profile.data.get("arch"):
        raise RootfsHandoffError("rootfs authority architecture does not match selected profile")
    if physical_gate.rootfs_artifact_sha256 != rootfs_authority.artifact_sha256:
        raise RootfsHandoffError("physical candidate rootfs is detached from reviewed rootfs authority")
    if not isinstance(rootfs_authority.artifact_size, int) or isinstance(rootfs_authority.artifact_size, bool) or rootfs_authority.artifact_size <= 0:
        raise RootfsHandoffError("rootfs authority artifact size must be positive")

    gate_sha = _sha256(physical_gate.evidence_sha256(), "physical candidate gate SHA-256")
    authority_sha = _sha256(rootfs_authority.authority_sha256(), "rootfs authority SHA-256")
    artifact_sha = _sha256(rootfs_authority.artifact_sha256, "rootfs artifact SHA-256")

    return RootfsHandoffAssessmentEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=_safe_text(physical_gate.device_serial, "device serial"),
        firmware_build=_safe_text(physical_gate.firmware_build, "firmware build"),
        firmware_fingerprint=_safe_text(physical_gate.firmware_fingerprint, "firmware fingerprint"),
        physical_candidate_gate_sha256=gate_sha,
        rootfs_handoff_contract_sha256=contract.contract_sha256(),
        rootfs_authority_sha256=authority_sha,
        rootfs_artifact_sha256=artifact_sha,
        rootfs_artifact_size=rootfs_authority.artifact_size,
        layout_source_name=contract.layout_source_name,
        layout_source_commit=contract.layout_source_commit,
        layout_source_path=contract.layout_source_path,
        layout_source_blob_sha1=contract.layout_source_blob_sha1,
        storage_bus=contract.storage_bus,
        partition_hint=contract.partition_hint,
        expected_filesystems=contract.expected_filesystems,
        encryption_features=contract.encryption_features,
        metadata_partition=contract.metadata_partition,
        required_physical_evidence=contract.required_physical_evidence,
        forbidden_partitions=contract.forbidden_partitions,
        target_selected=False,
        storage_path_bound=False,
        write_authorized=False,
        handoff_ready=False,
        manual_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def verify_rootfs_handoff_assessment(
    evidence: RootfsHandoffAssessmentEvidence,
    profile: DeviceProfile,
    physical_gate: PhysicalCandidateGateEvidence,
    rootfs_authority: RootfsAuthorityRecord,
) -> None:
    expected = bind_rootfs_handoff_assessment(profile, physical_gate, rootfs_authority)
    if evidence != expected:
        raise RootfsHandoffError("rootfs handoff assessment does not match exact inputs")


def write_rootfs_handoff_assessment(
    evidence: RootfsHandoffAssessmentEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, RootfsHandoffAssessmentEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffError("invalid rootfs handoff assessment evidence")
    if evidence.target_selected or evidence.storage_path_bound or evidence.write_authorized or evidence.handoff_ready:
        raise RootfsHandoffError("discovery-only handoff assessment cannot select/authorize a target")
    if evidence.manual_review_required is not True:
        raise RootfsHandoffError("rootfs handoff assessment must require manual review")
    if evidence.hardware_verified or evidence.beta_gate_credit:
        raise RootfsHandoffError("rootfs handoff assessment cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise RootfsHandoffError(f"refusing to overwrite rootfs handoff assessment: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RootfsHandoffError("refusing stale rootfs handoff assessment temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()


def _git(repository: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RootfsHandoffError(f"failed to verify rootfs handoff source with git: {args[0]}") from exc
    return completed.stdout.strip()


def verify_rootfs_handoff_layout_checkout(
    profile: DeviceProfile,
    checkout: Path,
) -> RootfsHandoffSourceEvidence:
    """Verify the exact pinned layout file in a clean source checkout.

    This is host/source-lock evidence only. It does not validate physical UFS,
    encryption state or the eventual rootfs target.
    """
    contract = rootfs_handoff_contract(profile)
    root = Path(checkout)
    if root.is_symlink() or not root.is_dir():
        raise RootfsHandoffError("rootfs handoff source checkout must be a real directory")
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise RootfsHandoffError("cannot resolve rootfs handoff source checkout") from exc
    object_format = _git(root, "rev-parse", "--show-object-format")
    if object_format != "sha1":
        raise RootfsHandoffError("rootfs handoff source checkout must use Git SHA-1 objects")
    origin = _git(root, "remote", "get-url", "origin")
    if origin != contract.layout_source_url:
        raise RootfsHandoffError("rootfs handoff source checkout origin does not match pinned source URL")
    head = _git(root, "rev-parse", "HEAD")
    if head != contract.layout_source_commit:
        raise RootfsHandoffError("rootfs handoff source checkout HEAD does not match pinned commit")
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        raise RootfsHandoffError("rootfs handoff source checkout has tracked modifications")
    blob = _git(root, "rev-parse", f"HEAD:{contract.layout_source_path}")
    if blob != contract.layout_source_blob_sha1:
        raise RootfsHandoffError("rootfs handoff layout blob does not match pinned identity")
    candidate = root.joinpath(*PurePosixPath(contract.layout_source_path).parts)
    if candidate.is_symlink():
        raise RootfsHandoffError("rootfs handoff layout source must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RootfsHandoffError("rootfs handoff layout source is missing") from exc
    if root != resolved and root not in resolved.parents:
        raise RootfsHandoffError("rootfs handoff layout source escapes checkout")
    if not resolved.is_file():
        raise RootfsHandoffError("rootfs handoff layout source must be a regular file")
    return RootfsHandoffSourceEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        rootfs_handoff_contract_sha256=contract.contract_sha256(),
        source_url=contract.layout_source_url,
        source_commit=contract.layout_source_commit,
        source_path=contract.layout_source_path,
        source_blob_sha1=blob,
        checkout_head=head,
        tracked_tree_clean=True,
    )


def write_rootfs_handoff_source_evidence(
    evidence: RootfsHandoffSourceEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, RootfsHandoffSourceEvidence) or evidence.schema_version != 1:
        raise RootfsHandoffError("invalid rootfs handoff source evidence")
    if evidence.tracked_tree_clean is not True:
        raise RootfsHandoffError("rootfs handoff source evidence must record a clean tracked tree")
    if evidence.hardware_verified or evidence.beta_gate_credit:
        raise RootfsHandoffError("rootfs handoff source evidence cannot claim hardware/Beta credit")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise RootfsHandoffError(f"refusing to overwrite rootfs handoff source evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise RootfsHandoffError("refusing stale rootfs handoff source evidence temporary path")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
