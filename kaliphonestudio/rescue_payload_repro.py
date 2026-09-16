"""Reproducibility contract for the static ARM64 early-rescue payload.

This layer sits above :mod:`kaliphonestudio.rescue_payload`.  The lower-level
module validates an already-built binary and creates staging.  This module adds
the missing source/material and two-build evidence so a staging tree can only be
promoted as a *reproducible rescue payload candidate* after all locked inputs,
two independent binaries and their applet manifests agree.

No function here downloads source or touches a phone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .rescue_payload import (
    RescuePayloadError,
    RescuePayloadEvidence,
    RescuePayloadLock,
    inspect_static_arm64_elf,
    load_rescue_payload_lock,
    load_verified_applet_list,
    prepare_rescue_staging,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_COMPILER_ID_RE = re.compile(r"^[ -~]{1,512}$")


@dataclass(frozen=True)
class RescuePayloadReproEvidence:
    schema_version: int
    payload_id: str
    architecture: str
    lock_manifest_sha256: str
    build_contract_sha256: str
    source_archive_sha256: str
    config_sha256: str
    init_sha256: str
    busybox_sha256: str
    busybox_size: int
    applet_manifest_sha256: str
    applet_count: int
    elf_machine: int
    compiler_id: str
    compiler_id_sha256: str
    target_machine: str
    independent_builds: int
    reproducible: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RescuePayloadError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RescuePayloadError(f"cannot load {label}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RescuePayloadError(f"{label} must be a JSON object")
    return raw


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    return sha256(payload.encode("utf-8")).hexdigest()


def _hash_regular_file(path: Path, *, label: str, max_bytes: int) -> tuple[int, str]:
    if not path.is_file() or path.is_symlink():
        raise RescuePayloadError(f"{label} must be a regular file")
    try:
        before = path.stat()
    except OSError as exc:
        raise RescuePayloadError(f"cannot stat {label}: {exc}") from exc
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise RescuePayloadError(f"{label} size is outside the safety limit")
    try:
        payload = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise RescuePayloadError(f"cannot read {label}: {exc}") from exc
    if len(payload) != before.st_size or (
        before.st_size,
        before.st_mtime_ns,
        before.st_ino,
    ) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise RescuePayloadError(f"{label} changed while being verified")
    return len(payload), sha256(payload).hexdigest()


def _resolve_locked_material(repository_root: Path, relative: str, *, label: str) -> Path:
    try:
        root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise RescuePayloadError(f"cannot resolve repository root: {exc}") from exc
    if not root.is_dir():
        raise RescuePayloadError("repository root must be a directory")
    candidate = root / relative
    if candidate.is_symlink():
        raise RescuePayloadError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RescuePayloadError(f"{label} escapes or is missing from repository root") from exc
    return resolved


def load_repro_contract(
    lock_manifest_path: Path,
    *,
    repository_root: Path,
) -> tuple[RescuePayloadLock, str, str, str, str]:
    """Load and verify the full rescue lock plus repository-owned material digests.

    Returns ``(lock, manifest_sha256, build_contract_sha256, config_sha256,
    init_sha256)``.  The full manifest hash intentionally covers fields ignored
    by the lower-level schema-v1 loader, so changing the build/material contract
    invalidates reproducibility evidence.
    """

    lock = load_rescue_payload_lock(lock_manifest_path)
    raw = _read_json_object(lock_manifest_path, "rescue payload lock")
    materials = raw.get("materials")
    build = raw.get("build")
    if not isinstance(materials, dict) or not isinstance(build, dict):
        raise RescuePayloadError("rescue payload lock requires materials and build contracts")

    config_expected = _require_sha256(materials.get("config_sha256"), "materials.config_sha256")
    init_expected = _require_sha256(materials.get("init_sha256"), "materials.init_sha256")

    config = _resolve_locked_material(
        repository_root, lock.config_path, label="locked BusyBox config"
    )
    init = _resolve_locked_material(
        repository_root, lock.init_template, label="locked rescue /init"
    )
    _, config_actual = _hash_regular_file(config, label="locked BusyBox config", max_bytes=1024 * 1024)
    _, init_actual = _hash_regular_file(init, label="locked rescue /init", max_bytes=1024 * 1024)
    if config_actual != config_expected:
        raise RescuePayloadError("locked BusyBox config SHA-256 does not match repository bytes")
    if init_actual != init_expected:
        raise RescuePayloadError("locked rescue /init SHA-256 does not match repository bytes")

    if build.get("cross_compile") != "aarch64-linux-gnu-":
        raise RescuePayloadError("rescue build cross compiler prefix must be aarch64-linux-gnu-")
    if build.get("kconfig_target") != "allnoconfig":
        raise RescuePayloadError("rescue build must use the locked allnoconfig recipe")
    if build.get("make_target") != "busybox":
        raise RescuePayloadError("rescue build target must be busybox")
    if build.get("ldflags") != "--static":
        raise RescuePayloadError("rescue build must retain static linker policy")
    if build.get("source_date_epoch") != 0:
        raise RescuePayloadError("rescue build SOURCE_DATE_EPOCH must be normalized to zero")
    if build.get("independent_builds") != 2:
        raise RescuePayloadError("rescue build contract requires exactly two independent builds")

    return (
        lock,
        _canonical_sha256(raw),
        _canonical_sha256(build),
        config_actual,
        init_actual,
    )


def verify_reproducible_payload_pair(
    *,
    lock_manifest_path: Path,
    repository_root: Path,
    source_archive: Path,
    first_binary: Path,
    second_binary: Path,
    first_applet_list: Path,
    second_applet_list: Path,
    compiler_id: str,
    target_machine: str,
) -> RescuePayloadReproEvidence:
    """Verify source/material locks and two byte-identical ARM64 BusyBox builds."""

    (
        lock,
        lock_manifest_sha256,
        build_contract_sha256,
        config_sha256,
        init_sha256,
    ) = load_repro_contract(lock_manifest_path, repository_root=repository_root)

    _, source_digest = _hash_regular_file(
        source_archive, label="BusyBox source archive", max_bytes=64 * 1024 * 1024
    )
    if source_digest != lock.source_sha256:
        raise RescuePayloadError("BusyBox source archive SHA-256 does not match the lock")

    first = inspect_static_arm64_elf(first_binary, lock)
    second = inspect_static_arm64_elf(second_binary, lock)
    if first.sha256 != second.sha256 or first.size != second.size:
        raise RescuePayloadError("independent rescue BusyBox builds are not byte-identical")
    if first_binary.read_bytes() != second_binary.read_bytes():
        raise RescuePayloadError("independent rescue BusyBox builds differ byte-for-byte")

    applets_a = load_verified_applet_list(first_applet_list, lock)
    applets_b = load_verified_applet_list(second_applet_list, lock)
    if applets_a != applets_b:
        raise RescuePayloadError("independent BusyBox applet manifests differ")
    applet_payload = ("\n".join(applets_a) + "\n").encode("utf-8")

    if not isinstance(compiler_id, str) or not _SAFE_COMPILER_ID_RE.fullmatch(compiler_id):
        raise RescuePayloadError("compiler_id must be a bounded printable single-line string")
    if target_machine != "aarch64-linux-gnu":
        raise RescuePayloadError("compiler target machine must be aarch64-linux-gnu")

    return RescuePayloadReproEvidence(
        schema_version=1,
        payload_id=lock.payload_id,
        architecture=lock.architecture,
        lock_manifest_sha256=lock_manifest_sha256,
        build_contract_sha256=build_contract_sha256,
        source_archive_sha256=source_digest,
        config_sha256=config_sha256,
        init_sha256=init_sha256,
        busybox_sha256=first.sha256,
        busybox_size=first.size,
        applet_manifest_sha256=sha256(applet_payload).hexdigest(),
        applet_count=len(applets_a),
        elf_machine=first.elf_machine,
        compiler_id=compiler_id,
        compiler_id_sha256=sha256((compiler_id + "\n").encode("utf-8")).hexdigest(),
        target_machine=target_machine,
        independent_builds=2,
        reproducible=True,
    )


def stage_reproducible_payload(
    *,
    repro: RescuePayloadReproEvidence,
    lock_manifest_path: Path,
    repository_root: Path,
    busybox: Path,
    applet_list: Path,
    destination: Path,
) -> RescuePayloadEvidence:
    """Stage only bytes that match previously verified pair evidence."""

    (
        lock,
        lock_manifest_sha256,
        build_contract_sha256,
        config_sha256,
        init_sha256,
    ) = load_repro_contract(lock_manifest_path, repository_root=repository_root)

    if repro.schema_version != 1 or repro.reproducible is not True:
        raise RescuePayloadError("rescue payload lacks reproducibility evidence")
    if repro.payload_id != lock.payload_id or repro.architecture != lock.architecture:
        raise RescuePayloadError("rescue payload evidence does not match the lock identity")
    if repro.lock_manifest_sha256 != lock_manifest_sha256:
        raise RescuePayloadError("rescue payload lock changed after reproducibility verification")
    if repro.build_contract_sha256 != build_contract_sha256:
        raise RescuePayloadError("rescue build contract changed after reproducibility verification")
    if repro.config_sha256 != config_sha256 or repro.init_sha256 != init_sha256:
        raise RescuePayloadError("rescue repository materials changed after reproducibility verification")

    inspection = inspect_static_arm64_elf(busybox, lock)
    if inspection.sha256 != repro.busybox_sha256 or inspection.size != repro.busybox_size:
        raise RescuePayloadError("BusyBox bytes do not match reproducibility evidence")
    applets = load_verified_applet_list(applet_list, lock)
    applet_payload = ("\n".join(applets) + "\n").encode("utf-8")
    if sha256(applet_payload).hexdigest() != repro.applet_manifest_sha256:
        raise RescuePayloadError("BusyBox applet manifest does not match reproducibility evidence")
    if len(applets) != repro.applet_count:
        raise RescuePayloadError("BusyBox applet count does not match reproducibility evidence")

    init_template = _resolve_locked_material(
        repository_root, lock.init_template, label="locked rescue /init"
    )
    staged = prepare_rescue_staging(
        lock,
        busybox=busybox,
        applet_list=applet_list,
        init_template=init_template,
        destination=destination,
    )
    if staged.busybox_sha256 != repro.busybox_sha256:
        raise RescuePayloadError("staged BusyBox drifted after reproducibility verification")
    if staged.applet_manifest_sha256 != repro.applet_manifest_sha256:
        raise RescuePayloadError("staged applet evidence drifted after reproducibility verification")
    if staged.init_sha256 != repro.init_sha256:
        raise RescuePayloadError("staged /init drifted after reproducibility verification")
    return staged


def write_repro_evidence(evidence: RescuePayloadReproEvidence, destination: Path) -> str:
    if evidence.schema_version != 1 or evidence.reproducible is not True:
        raise RescuePayloadError("cannot serialize unverified rescue reproducibility evidence")
    for value, field in (
        (evidence.lock_manifest_sha256, "lock manifest"),
        (evidence.build_contract_sha256, "build contract"),
        (evidence.source_archive_sha256, "source archive"),
        (evidence.config_sha256, "config"),
        (evidence.init_sha256, "init"),
        (evidence.busybox_sha256, "BusyBox"),
        (evidence.applet_manifest_sha256, "applet manifest"),
        (evidence.compiler_id_sha256, "compiler id"),
    ):
        _require_sha256(value, field)
    if evidence.architecture != "arm64" or evidence.elf_machine != 183:
        raise RescuePayloadError("rescue reproducibility evidence architecture is invalid")
    if evidence.target_machine != "aarch64-linux-gnu":
        raise RescuePayloadError("rescue reproducibility evidence target machine is invalid")
    if evidence.independent_builds != 2:
        raise RescuePayloadError("rescue reproducibility evidence requires two builds")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
