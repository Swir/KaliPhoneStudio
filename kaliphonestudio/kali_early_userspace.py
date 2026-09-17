"""Deterministic proof overlay for the first Kali ARM64 userspace handoff.

This module does not implement or infer a storage/rootfs transport.  Instead it
builds a tiny deterministic overlay that can be applied to the exact reviewed
Kali rootfs once a separate handoff strategy is selected.  A systemd oneshot
unit emits cryptographically bound markers only after that real Kali rootfs has
started systemd and reached the early basic-target path.

The overlay is provenance/diagnostic infrastructure only.  It performs no phone
I/O, enables no network service, embeds no credentials, and never grants
hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import tarfile

from .candidate_authority_bundle import FirstBootAuthorityBundleEvidence
from .candidate_rootfs_authority import FirstBootRootfsAuthorityEvidence


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROBE_POLICY = "kali-rootfs-systemd-early-v1"
_STAGE_MARKER_VALUE = "rootfs-systemd-early-v1"
_PROBE_FILE = "usr/share/kaliphonestudio/kali-early-userspace-probe-id"
_PLAN_FILE = "usr/share/kaliphonestudio/kali-early-userspace-plan.json"
_SCRIPT_FILE = "usr/libexec/kaliphonestudio/emit-early-userspace-proof"
_UNIT_FILE = "usr/lib/systemd/system/kaliphonestudio-early-userspace-proof.service"
_WANTS_LINK = "etc/systemd/system/basic.target.wants/kaliphonestudio-early-userspace-proof.service"
_WANTS_TARGET = "../../../../usr/lib/systemd/system/kaliphonestudio-early-userspace-proof.service"
_MAX_JSON_BYTES = 2 * 1024 * 1024


class KaliEarlyUserspaceError(ValueError):
    pass


@dataclass(frozen=True)
class KaliEarlyUserspaceProbePlan:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    first_boot_authority_bundle_sha256: str
    rootfs_authority_binding_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    architecture: str
    variant: str
    probe_policy: str
    probe_id: str
    service_unit: str
    marker_stage: str
    marker_probe_id: str
    marker_manifest_sha256: str
    marker_rootfs_authority_sha256: str
    marker_rootfs_artifact_sha256: str
    remote_access_enabled: bool
    credentials_embedded: bool
    phone_storage_written: bool
    manual_physical_review_required: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def plan_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KaliEarlyUserspaceProbeBundleEvidence:
    schema_version: int
    profile_id: str
    first_boot_manifest_sha256: str
    first_boot_authority_bundle_sha256: str
    rootfs_authority_binding_sha256: str
    rootfs_authority_sha256: str
    rootfs_artifact_sha256: str
    rootfs_artifact_size: int
    probe_plan_sha256: str
    probe_id: str
    probe_policy: str
    bundle_sha256: str
    bundle_size: int
    member_count: int
    systemd_activation_bound: bool
    remote_access_enabled: bool
    credentials_embedded: bool
    phone_storage_written: bool
    manual_physical_review_required: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise KaliEarlyUserspaceError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _positive(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise KaliEarlyUserspaceError(f"{label} must be a positive integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KaliEarlyUserspaceError(f"{label} must be a non-empty string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise KaliEarlyUserspaceError(f"{label} contains control data")
    return value


def _typed_json(path: Path, cls: type, label: str):
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise KaliEarlyUserspaceError(f"{label} must be a regular non-symlink file")
    raw = source.read_bytes()
    if not raw or len(raw) > _MAX_JSON_BYTES:
        raise KaliEarlyUserspaceError(f"{label} size is outside the safety limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KaliEarlyUserspaceError(f"{label} is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(cls)}
    if not isinstance(value, dict) or set(value) != expected:
        raise KaliEarlyUserspaceError(f"{label} fields do not match the supported schema")
    try:
        return cls(**value)
    except TypeError as exc:
        raise KaliEarlyUserspaceError(f"{label} types are invalid") from exc


def load_first_boot_authority_bundle(path: Path) -> FirstBootAuthorityBundleEvidence:
    return _typed_json(path, FirstBootAuthorityBundleEvidence, "first-boot authority bundle")


def load_first_boot_rootfs_authority_binding(path: Path) -> FirstBootRootfsAuthorityEvidence:
    return _typed_json(path, FirstBootRootfsAuthorityEvidence, "rootfs authority binding")


def _probe_material(
    authorities: FirstBootAuthorityBundleEvidence,
    rootfs: FirstBootRootfsAuthorityEvidence,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile_id": authorities.profile_id,
        "first_boot_manifest_sha256": authorities.first_boot_manifest_sha256,
        "first_boot_authority_bundle_sha256": authorities.evidence_sha256(),
        "rootfs_authority_binding_sha256": rootfs.evidence_sha256(),
        "rootfs_authority_sha256": rootfs.rootfs_authority_sha256,
        "rootfs_artifact_sha256": rootfs.artifact_sha256,
        "rootfs_artifact_size": rootfs.artifact_size,
        "probe_policy": _PROBE_POLICY,
    }


def _expected_probe_id(authorities: FirstBootAuthorityBundleEvidence, rootfs: FirstBootRootfsAuthorityEvidence) -> str:
    payload = json.dumps(_probe_material(authorities, rootfs), sort_keys=True, separators=(",", ":")) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()


def create_kali_early_userspace_probe_plan(
    authorities: FirstBootAuthorityBundleEvidence,
    rootfs: FirstBootRootfsAuthorityEvidence,
) -> KaliEarlyUserspaceProbePlan:
    if not isinstance(authorities, FirstBootAuthorityBundleEvidence) or authorities.schema_version != 1:
        raise KaliEarlyUserspaceError("early-userspace proof requires schema-v1 authority bundle evidence")
    if authorities.all_authorities_reviewed is not True or authorities.all_required_artifacts_strict is not True:
        raise KaliEarlyUserspaceError("authority bundle is not fully reviewed and strict")
    if authorities.hardware_verified is not False or authorities.beta_gate_credit is not False:
        raise KaliEarlyUserspaceError("host authority bundle cannot claim hardware/Beta credit")
    profile_id = _text(authorities.profile_id, "profile_id")
    manifest_sha = _sha(authorities.first_boot_manifest_sha256, "first-boot manifest")
    authority_bundle_sha = _sha(authorities.evidence_sha256(), "first-boot authority bundle")
    rootfs_binding_sha = _sha(authorities.rootfs_binding_sha256, "rootfs authority binding from bundle")

    if not isinstance(rootfs, FirstBootRootfsAuthorityEvidence) or rootfs.schema_version != 1:
        raise KaliEarlyUserspaceError("early-userspace proof requires schema-v1 rootfs authority binding")
    if rootfs.profile_id != profile_id or rootfs.first_boot_manifest_sha256 != manifest_sha:
        raise KaliEarlyUserspaceError("rootfs authority binding is detached from the authority bundle candidate")
    if _sha(rootfs.evidence_sha256(), "rootfs authority binding") != rootfs_binding_sha:
        raise KaliEarlyUserspaceError("rootfs authority binding digest does not match authority bundle")
    if _sha(rootfs.rootfs_authority_sha256, "rootfs authority") != _sha(authorities.rootfs_authority_sha256, "bundle rootfs authority"):
        raise KaliEarlyUserspaceError("rootfs authority identity differs from authority bundle")
    if _sha(rootfs.artifact_sha256, "rootfs artifact") != _sha(authorities.rootfs_artifact_sha256, "bundle rootfs artifact"):
        raise KaliEarlyUserspaceError("rootfs artifact differs from authority bundle")
    if rootfs.strict_byte_identical is not True or rootfs.reviewed is not True:
        raise KaliEarlyUserspaceError("rootfs authority binding is not reviewed/strict")
    if rootfs.hardware_verified is not False or rootfs.beta_gate_credit is not False:
        raise KaliEarlyUserspaceError("rootfs authority binding cannot claim hardware/Beta credit")
    if rootfs.architecture != "arm64":
        raise KaliEarlyUserspaceError("Kali early-userspace proof currently requires ARM64 rootfs authority")
    artifact_size = _positive(rootfs.artifact_size, "rootfs artifact size")
    variant = _text(rootfs.variant, "rootfs variant")

    probe_id = _expected_probe_id(authorities, rootfs)
    plan = KaliEarlyUserspaceProbePlan(
        schema_version=1,
        profile_id=profile_id,
        first_boot_manifest_sha256=manifest_sha,
        first_boot_authority_bundle_sha256=authority_bundle_sha,
        rootfs_authority_binding_sha256=rootfs_binding_sha,
        rootfs_authority_sha256=rootfs.rootfs_authority_sha256,
        rootfs_artifact_sha256=rootfs.artifact_sha256,
        rootfs_artifact_size=artifact_size,
        architecture="arm64",
        variant=variant,
        probe_policy=_PROBE_POLICY,
        probe_id=probe_id,
        service_unit="kaliphonestudio-early-userspace-proof.service",
        marker_stage=f"KPS_KALI_STAGE={_STAGE_MARKER_VALUE}",
        marker_probe_id=f"KPS_KALI_PROBE_ID={probe_id}",
        marker_manifest_sha256=f"KPS_KALI_MANIFEST_SHA256={manifest_sha}",
        marker_rootfs_authority_sha256=f"KPS_KALI_ROOTFS_AUTHORITY_SHA256={rootfs.rootfs_authority_sha256}",
        marker_rootfs_artifact_sha256=f"KPS_KALI_ROOTFS_ARTIFACT_SHA256={rootfs.artifact_sha256}",
        remote_access_enabled=False,
        credentials_embedded=False,
        phone_storage_written=False,
        manual_physical_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    validate_kali_early_userspace_probe_plan(plan)
    return plan


def validate_kali_early_userspace_probe_plan(plan: KaliEarlyUserspaceProbePlan) -> None:
    if not isinstance(plan, KaliEarlyUserspaceProbePlan) or plan.schema_version != 1:
        raise KaliEarlyUserspaceError("unsupported Kali early-userspace proof plan")
    _text(plan.profile_id, "profile_id")
    for value, label in (
        (plan.first_boot_manifest_sha256, "first-boot manifest"),
        (plan.first_boot_authority_bundle_sha256, "authority bundle"),
        (plan.rootfs_authority_binding_sha256, "rootfs authority binding"),
        (plan.rootfs_authority_sha256, "rootfs authority"),
        (plan.rootfs_artifact_sha256, "rootfs artifact"),
        (plan.probe_id, "probe id"),
    ):
        _sha(value, label)
    _positive(plan.rootfs_artifact_size, "rootfs artifact size")
    if plan.architecture != "arm64" or plan.probe_policy != _PROBE_POLICY:
        raise KaliEarlyUserspaceError("early-userspace architecture/policy drifted")
    _text(plan.variant, "rootfs variant")
    if plan.service_unit != "kaliphonestudio-early-userspace-proof.service":
        raise KaliEarlyUserspaceError("early-userspace service unit drifted")
    expected_markers = (
        f"KPS_KALI_STAGE={_STAGE_MARKER_VALUE}",
        f"KPS_KALI_PROBE_ID={plan.probe_id}",
        f"KPS_KALI_MANIFEST_SHA256={plan.first_boot_manifest_sha256}",
        f"KPS_KALI_ROOTFS_AUTHORITY_SHA256={plan.rootfs_authority_sha256}",
        f"KPS_KALI_ROOTFS_ARTIFACT_SHA256={plan.rootfs_artifact_sha256}",
    )
    actual_markers = (
        plan.marker_stage,
        plan.marker_probe_id,
        plan.marker_manifest_sha256,
        plan.marker_rootfs_authority_sha256,
        plan.marker_rootfs_artifact_sha256,
    )
    if actual_markers != expected_markers:
        raise KaliEarlyUserspaceError("early-userspace proof markers drifted from plan identities")
    if (
        plan.remote_access_enabled is not False
        or plan.credentials_embedded is not False
        or plan.phone_storage_written is not False
        or plan.manual_physical_review_required is not True
        or plan.hardware_verified is not False
        or plan.beta_gate_credit is not False
    ):
        raise KaliEarlyUserspaceError("early-userspace proof plan contains an invalid safety claim")


def _proof_script(plan: KaliEarlyUserspaceProbePlan) -> bytes:
    validate_kali_early_userspace_probe_plan(plan)
    markers = (
        plan.marker_stage,
        plan.marker_probe_id,
        plan.marker_manifest_sha256,
        plan.marker_rootfs_authority_sha256,
        plan.marker_rootfs_artifact_sha256,
    )
    quoted = " ".join("'" + item + "'" for item in markers)
    text = f"""#!/bin/sh
set -eu
PROBE_FILE=/{_PROBE_FILE}
EXPECTED_PROBE_ID='{plan.probe_id}'
observed="$(tr -d '\\r\\n' < \"$PROBE_FILE\")"
[ \"$observed\" = \"$EXPECTED_PROBE_ID\" ] || {{
    echo 'KPS: Kali early-userspace probe id mismatch' >&2
    exit 65
}}
for marker in {quoted}; do
    printf '%s\\n' \"$marker\"
    if [ -w /dev/console ]; then printf '%s\\n' \"$marker\" > /dev/console; fi
    if [ -w /dev/kmsg ]; then printf '%s\\n' \"$marker\" > /dev/kmsg; fi
done
exit 0
"""
    return text.encode("utf-8")


def _unit_payload() -> bytes:
    return f"""[Unit]
Description=KaliPhoneStudio early Kali rootfs proof
DefaultDependencies=no
After=local-fs.target
Before=basic.target
ConditionPathExists=/{_PROBE_FILE}

[Service]
Type=oneshot
ExecStart=/{_SCRIPT_FILE}
NoNewPrivileges=yes
PrivateNetwork=yes
ProtectHome=yes
RemainAfterExit=yes

""".encode("utf-8")


def _regular(name: str, payload: bytes, mode: int) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mode = mode
    return info, payload


def _symlink(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    info.size = 0
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mode = 0o777
    return info


def _members(plan: KaliEarlyUserspaceProbePlan) -> dict[str, tuple[str, bytes | str, int]]:
    return {
        _PROBE_FILE: ("file", (plan.probe_id + "\n").encode("ascii"), 0o644),
        _PLAN_FILE: ("file", plan.canonical_json().encode("utf-8"), 0o644),
        _SCRIPT_FILE: ("file", _proof_script(plan), 0o755),
        _UNIT_FILE: ("file", _unit_payload(), 0o644),
        _WANTS_LINK: ("symlink", _WANTS_TARGET, 0o777),
    }


def _file_sha_size(path: Path) -> tuple[str, int]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise KaliEarlyUserspaceError("Kali early-userspace bundle must be a regular non-symlink file")
    before = source.stat()
    digest = sha256()
    size = 0
    with source.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or size != before.st_size:
        raise KaliEarlyUserspaceError("Kali early-userspace bundle changed while being verified")
    return digest.hexdigest(), size


def build_kali_early_userspace_probe_bundle(
    plan: KaliEarlyUserspaceProbePlan,
    destination: Path,
) -> KaliEarlyUserspaceProbeBundleEvidence:
    validate_kali_early_userspace_probe_plan(plan)
    destination = Path(destination).resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise KaliEarlyUserspaceError("refusing to overwrite Kali early-userspace probe bundle")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise KaliEarlyUserspaceError("refusing stale Kali early-userspace probe temporary bundle")
    members = _members(plan)
    try:
        with tarfile.open(temporary, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name in sorted(members):
                kind, value, mode = members[name]
                if kind == "file":
                    payload = value if isinstance(value, bytes) else value.encode("utf-8")
                    info, payload = _regular(name, payload, mode)
                    archive.addfile(info, io.BytesIO(payload))
                else:
                    archive.addfile(_symlink(name, str(value)))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    bundle_sha, bundle_size = _file_sha_size(destination)
    evidence = KaliEarlyUserspaceProbeBundleEvidence(
        schema_version=1,
        profile_id=plan.profile_id,
        first_boot_manifest_sha256=plan.first_boot_manifest_sha256,
        first_boot_authority_bundle_sha256=plan.first_boot_authority_bundle_sha256,
        rootfs_authority_binding_sha256=plan.rootfs_authority_binding_sha256,
        rootfs_authority_sha256=plan.rootfs_authority_sha256,
        rootfs_artifact_sha256=plan.rootfs_artifact_sha256,
        rootfs_artifact_size=plan.rootfs_artifact_size,
        probe_plan_sha256=plan.plan_sha256(),
        probe_id=plan.probe_id,
        probe_policy=plan.probe_policy,
        bundle_sha256=bundle_sha,
        bundle_size=bundle_size,
        member_count=len(members),
        systemd_activation_bound=True,
        remote_access_enabled=False,
        credentials_embedded=False,
        phone_storage_written=False,
        manual_physical_review_required=True,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    verify_kali_early_userspace_probe_bundle(plan, evidence, destination)
    return evidence


def validate_kali_early_userspace_probe_bundle_evidence(evidence: KaliEarlyUserspaceProbeBundleEvidence) -> None:
    if not isinstance(evidence, KaliEarlyUserspaceProbeBundleEvidence) or evidence.schema_version != 1:
        raise KaliEarlyUserspaceError("unsupported Kali early-userspace bundle evidence")
    for value, label in (
        (evidence.first_boot_manifest_sha256, "first-boot manifest"),
        (evidence.first_boot_authority_bundle_sha256, "authority bundle"),
        (evidence.rootfs_authority_binding_sha256, "rootfs authority binding"),
        (evidence.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.probe_plan_sha256, "probe plan"),
        (evidence.probe_id, "probe id"),
        (evidence.bundle_sha256, "probe bundle"),
    ):
        _sha(value, label)
    _positive(evidence.rootfs_artifact_size, "rootfs artifact size")
    _positive(evidence.bundle_size, "probe bundle size")
    if evidence.member_count != 5 or evidence.probe_policy != _PROBE_POLICY:
        raise KaliEarlyUserspaceError("Kali early-userspace bundle policy/member contract drifted")
    if (
        evidence.systemd_activation_bound is not True
        or evidence.remote_access_enabled is not False
        or evidence.credentials_embedded is not False
        or evidence.phone_storage_written is not False
        or evidence.manual_physical_review_required is not True
        or evidence.hardware_verified is not False
        or evidence.beta_gate_credit is not False
    ):
        raise KaliEarlyUserspaceError("Kali early-userspace bundle contains an invalid safety claim")


def verify_kali_early_userspace_probe_bundle(
    plan: KaliEarlyUserspaceProbePlan,
    evidence: KaliEarlyUserspaceProbeBundleEvidence,
    bundle: Path,
) -> None:
    validate_kali_early_userspace_probe_plan(plan)
    validate_kali_early_userspace_probe_bundle_evidence(evidence)
    expected_pairs = (
        (evidence.profile_id, plan.profile_id, "profile"),
        (evidence.first_boot_manifest_sha256, plan.first_boot_manifest_sha256, "manifest"),
        (evidence.first_boot_authority_bundle_sha256, plan.first_boot_authority_bundle_sha256, "authority bundle"),
        (evidence.rootfs_authority_binding_sha256, plan.rootfs_authority_binding_sha256, "rootfs binding"),
        (evidence.rootfs_authority_sha256, plan.rootfs_authority_sha256, "rootfs authority"),
        (evidence.rootfs_artifact_sha256, plan.rootfs_artifact_sha256, "rootfs artifact"),
        (evidence.rootfs_artifact_size, plan.rootfs_artifact_size, "rootfs artifact size"),
        (evidence.probe_plan_sha256, plan.plan_sha256(), "probe plan"),
        (evidence.probe_id, plan.probe_id, "probe id"),
    )
    for observed, expected, label in expected_pairs:
        if observed != expected:
            raise KaliEarlyUserspaceError(f"Kali early-userspace bundle {label} binding mismatch")
    actual_sha, actual_size = _file_sha_size(bundle)
    if actual_sha != evidence.bundle_sha256 or actual_size != evidence.bundle_size:
        raise KaliEarlyUserspaceError("Kali early-userspace bundle bytes do not match evidence")

    expected = _members(plan)
    with tarfile.open(bundle, mode="r:") as archive:
        members = archive.getmembers()
        if [m.name for m in members] != sorted(expected):
            raise KaliEarlyUserspaceError("Kali early-userspace bundle member set/order drifted")
        for member in members:
            kind, value, mode = expected[member.name]
            if member.uid != 0 or member.gid != 0 or member.uname != "root" or member.gname != "root" or member.mtime != 0:
                raise KaliEarlyUserspaceError("Kali early-userspace bundle metadata is not canonical")
            if member.mode != mode:
                raise KaliEarlyUserspaceError("Kali early-userspace bundle mode drifted")
            if kind == "symlink":
                if not member.issym() or member.linkname != value or member.size != 0:
                    raise KaliEarlyUserspaceError("Kali early-userspace systemd activation symlink drifted")
                continue
            if not member.isfile() or member.issym():
                raise KaliEarlyUserspaceError("Kali early-userspace regular member changed type")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise KaliEarlyUserspaceError("cannot read Kali early-userspace bundle member")
            payload = extracted.read()
            if payload != value or member.size != len(payload):
                raise KaliEarlyUserspaceError("Kali early-userspace bundle member payload drifted")


def write_kali_early_userspace_plan(plan: KaliEarlyUserspaceProbePlan, destination: Path) -> str:
    validate_kali_early_userspace_probe_plan(plan)
    return _write_immutable_text(plan.canonical_json(), destination, "Kali early-userspace probe plan")


def write_kali_early_userspace_bundle_evidence(evidence: KaliEarlyUserspaceProbeBundleEvidence, destination: Path) -> str:
    validate_kali_early_userspace_probe_bundle_evidence(evidence)
    return _write_immutable_text(evidence.canonical_json(), destination, "Kali early-userspace probe evidence")


def load_kali_early_userspace_bundle_evidence(path: Path) -> KaliEarlyUserspaceProbeBundleEvidence:
    evidence = _typed_json(path, KaliEarlyUserspaceProbeBundleEvidence, "Kali early-userspace probe evidence")
    validate_kali_early_userspace_probe_bundle_evidence(evidence)
    return evidence


def _write_immutable_text(payload: str, destination: Path, label: str) -> str:
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise KaliEarlyUserspaceError(f"refusing to overwrite {label}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise KaliEarlyUserspaceError(f"refusing stale {label} temporary path")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(payload.encode("utf-8")).hexdigest()
