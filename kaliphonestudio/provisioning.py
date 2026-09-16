"""Device-independent first-boot provisioning bundle for the common Kali rootfs.

The bundle intentionally contains only non-secret policy and identity defaults.  User
credentials remain an explicit local/interactive first-boot responsibility, the root
password must stay locked, and remote access is disabled by default.  The generated
tar is deterministic and bound to the exact accepted rootfs evidence digest.

This module performs no phone I/O and grants no hardware/Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

from .rootfs import RootfsArtifactEvidence, RootfsError


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HOSTNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}_[A-Za-z]{2}(?:\.[A-Za-z0-9-]{1,16})?$")
_TZ_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")

_REMOTE_UNITS = ("dropbear.service", "ssh.service", "sshd.service")
_MANIFEST_PATH = "usr/share/kaliphonestudio/first-boot-provisioning.json"
_PRESET_PATH = "etc/systemd/system-preset/90-kaliphonestudio-firstboot.preset"


@dataclass(frozen=True)
class FirstBootProvisioningPlan:
    schema_version: int
    rootfs_evidence_sha256: str
    architecture: str
    hostname: str
    locale: str
    timezone: str
    interactive_user_setup_required: bool
    root_password_locked: bool
    remote_access_enabled: bool
    disabled_remote_units: tuple[str, ...]
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def plan_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FirstBootProvisioningBundleEvidence:
    schema_version: int
    rootfs_evidence_sha256: str
    provisioning_plan_sha256: str
    bundle_sha256: str
    bundle_size: int
    member_count: int
    credentials_embedded: bool
    remote_access_enabled: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_hostname(value: object) -> str:
    if not isinstance(value, str) or not _HOSTNAME_RE.fullmatch(value):
        raise RootfsError("first-boot hostname must be one lowercase RFC-style label")
    return value


def _validate_locale(value: object) -> str:
    if not isinstance(value, str) or not _LOCALE_RE.fullmatch(value):
        raise RootfsError("first-boot locale has invalid syntax")
    return value


def _validate_timezone(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 160:
        raise RootfsError("first-boot timezone has invalid syntax")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RootfsError("first-boot timezone must be a safe relative zoneinfo name")
    if not all(_TZ_SEGMENT_RE.fullmatch(part) for part in path.parts):
        raise RootfsError("first-boot timezone contains an invalid segment")
    return value


def validate_first_boot_provisioning_plan(plan: FirstBootProvisioningPlan) -> None:
    if not isinstance(plan, FirstBootProvisioningPlan) or plan.schema_version != 1:
        raise RootfsError("unsupported first-boot provisioning plan")
    _require_sha256(plan.rootfs_evidence_sha256, "rootfs evidence")
    if plan.architecture != "arm64":
        raise RootfsError("first-boot provisioning currently requires arm64 rootfs evidence")
    _validate_hostname(plan.hostname)
    _validate_locale(plan.locale)
    _validate_timezone(plan.timezone)
    if plan.interactive_user_setup_required is not True:
        raise RootfsError("first-boot provisioning must require interactive user setup")
    if plan.root_password_locked is not True:
        raise RootfsError("first-boot provisioning must keep the root password locked")
    if plan.remote_access_enabled is not False:
        raise RootfsError("first-boot provisioning cannot enable remote access by default")
    if plan.disabled_remote_units != _REMOTE_UNITS:
        raise RootfsError("first-boot remote-service denylist drifted")
    if plan.beta_gate_credit is not False:
        raise RootfsError("host provisioning plan cannot claim Beta credit")


def create_first_boot_provisioning_plan(
    rootfs_evidence: RootfsArtifactEvidence,
    *,
    hostname: str = "kali-phone",
    locale: str = "en_US.UTF-8",
    timezone: str = "UTC",
) -> FirstBootProvisioningPlan:
    if not isinstance(rootfs_evidence, RootfsArtifactEvidence):
        raise RootfsError("first-boot provisioning requires typed rootfs artifact evidence")
    if rootfs_evidence.schema_version != 2 or rootfs_evidence.reproducible is not True:
        raise RootfsError("first-boot provisioning requires reproducible rootfs evidence schema v2")
    _require_sha256(rootfs_evidence.evidence_sha256(), "rootfs evidence")
    if rootfs_evidence.architecture != "arm64":
        raise RootfsError("first-boot provisioning requires an ARM64 rootfs")

    plan = FirstBootProvisioningPlan(
        schema_version=1,
        rootfs_evidence_sha256=rootfs_evidence.evidence_sha256(),
        architecture=rootfs_evidence.architecture,
        hostname=_validate_hostname(hostname),
        locale=_validate_locale(locale),
        timezone=_validate_timezone(timezone),
        interactive_user_setup_required=True,
        root_password_locked=True,
        remote_access_enabled=False,
        disabled_remote_units=_REMOTE_UNITS,
        beta_gate_credit=False,
    )
    validate_first_boot_provisioning_plan(plan)
    return plan


def _bundle_members(plan: FirstBootProvisioningPlan) -> dict[str, bytes]:
    validate_first_boot_provisioning_plan(plan)
    preset = "".join(f"disable {unit}\n" for unit in plan.disabled_remote_units)
    return {
        "etc/hostname": f"{plan.hostname}\n".encode("utf-8"),
        "etc/locale.conf": f"LANG={plan.locale}\n".encode("utf-8"),
        "etc/timezone": f"{plan.timezone}\n".encode("utf-8"),
        _PRESET_PATH: preset.encode("utf-8"),
        _MANIFEST_PATH: plan.canonical_json().encode("utf-8"),
    }


def _regular_tarinfo(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mode = 0o644
    return info


def _sha256_and_size(path: Path) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        raise RootfsError("first-boot provisioning bundle must be a regular file")
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if size <= 0:
        raise RootfsError("first-boot provisioning bundle is empty")
    return digest.hexdigest(), size


def build_first_boot_provisioning_bundle(
    plan: FirstBootProvisioningPlan,
    destination: Path,
) -> FirstBootProvisioningBundleEvidence:
    """Build a deterministic USTAR overlay containing only non-secret defaults."""
    validate_first_boot_provisioning_plan(plan)
    destination = destination.resolve(strict=False)
    if destination.exists():
        raise RootfsError("refusing to overwrite first-boot provisioning bundle")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise RootfsError("refusing stale first-boot provisioning temporary bundle")

    members = _bundle_members(plan)
    try:
        with tarfile.open(temporary, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name in sorted(members):
                payload = members[name]
                archive.addfile(_regular_tarinfo(name, len(payload)), io.BytesIO(payload))
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    bundle_sha, bundle_size = _sha256_and_size(destination)
    evidence = FirstBootProvisioningBundleEvidence(
        schema_version=1,
        rootfs_evidence_sha256=plan.rootfs_evidence_sha256,
        provisioning_plan_sha256=plan.plan_sha256(),
        bundle_sha256=bundle_sha,
        bundle_size=bundle_size,
        member_count=len(members),
        credentials_embedded=False,
        remote_access_enabled=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )
    verify_first_boot_provisioning_bundle(plan, evidence, destination)
    return evidence


def verify_first_boot_provisioning_bundle(
    plan: FirstBootProvisioningPlan,
    evidence: FirstBootProvisioningBundleEvidence,
    bundle: Path,
) -> None:
    """Independently verify bytes, metadata and plan binding for a built bundle."""
    validate_first_boot_provisioning_plan(plan)
    if not isinstance(evidence, FirstBootProvisioningBundleEvidence) or evidence.schema_version != 1:
        raise RootfsError("unsupported first-boot provisioning bundle evidence")
    if evidence.rootfs_evidence_sha256 != plan.rootfs_evidence_sha256:
        raise RootfsError("provisioning bundle rootfs binding drifted")
    if evidence.provisioning_plan_sha256 != plan.plan_sha256():
        raise RootfsError("provisioning bundle plan digest drifted")
    if evidence.credentials_embedded is not False:
        raise RootfsError("first-boot provisioning bundle must not embed credentials")
    if evidence.remote_access_enabled is not False:
        raise RootfsError("first-boot provisioning bundle cannot enable remote access")
    if evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise RootfsError("host provisioning evidence cannot claim hardware/Beta credit")

    bundle = bundle.resolve(strict=True)
    actual_sha, actual_size = _sha256_and_size(bundle)
    if actual_sha != evidence.bundle_sha256 or actual_size != evidence.bundle_size:
        raise RootfsError("first-boot provisioning bundle bytes do not match evidence")

    expected = _bundle_members(plan)
    try:
        with tarfile.open(bundle, mode="r:") as archive:
            members = archive.getmembers()
            if [member.name for member in members] != sorted(expected):
                raise RootfsError("first-boot provisioning bundle member set/order drifted")
            if len(members) != evidence.member_count or len(members) != len(expected):
                raise RootfsError("first-boot provisioning bundle member count drifted")
            for member in members:
                if not member.isfile() or member.issym() or member.islnk():
                    raise RootfsError("first-boot provisioning bundle contains a non-regular member")
                if (member.uid, member.gid, member.uname, member.gname, member.mtime, member.mode) != (
                    0,
                    0,
                    "root",
                    "root",
                    0,
                    0o644,
                ):
                    raise RootfsError("first-boot provisioning bundle metadata is not canonical")
                extracted = archive.extractfile(member)
                if extracted is None or extracted.read() != expected[member.name]:
                    raise RootfsError("first-boot provisioning bundle payload drifted")
    except (tarfile.TarError, OSError) as exc:
        if isinstance(exc, RootfsError):
            raise
        raise RootfsError(f"cannot verify first-boot provisioning bundle: {exc}") from exc


def write_first_boot_provisioning_evidence(
    evidence: FirstBootProvisioningBundleEvidence,
    destination: Path,
) -> str:
    if not isinstance(evidence, FirstBootProvisioningBundleEvidence):
        raise RootfsError("invalid first-boot provisioning evidence type")
    if evidence.schema_version != 1 or evidence.credentials_embedded is not False:
        raise RootfsError("invalid first-boot provisioning evidence")
    if evidence.remote_access_enabled is not False or evidence.hardware_verified is not False or evidence.beta_gate_credit is not False:
        raise RootfsError("invalid first-boot provisioning safety flags")
    destination = destination.resolve(strict=False)
    if destination.exists():
        raise RootfsError("refusing to overwrite first-boot provisioning evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        raise RootfsError("refusing stale first-boot provisioning evidence temporary file")
    try:
        temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
