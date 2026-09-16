"""Source-lock and stage a minimal static ARM64 early-rescue payload.

This module never downloads code and never touches a phone.  It validates an
already-built BusyBox binary, an independently captured applet list, and the
repository-owned /init template before constructing a deterministic staging
layout for the existing initramfs builder.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
from typing import Any
from urllib.parse import urlparse


_AARCH64_MACHINE = 183
_MAX_APPLETS = 512
_SHA256_CHARS = frozenset("0123456789abcdef")
_SBIN_APPLETS = frozenset({"mknod", "mount", "poweroff", "reboot", "switch_root", "umount"})


class RescuePayloadError(ValueError):
    """Raised when rescue payload source/binary/staging evidence is unsafe."""


@dataclass(frozen=True)
class RescuePayloadLock:
    schema_version: int
    payload_id: str
    architecture: str
    busybox_version: str
    source_url: str
    source_sha256: str
    license: str
    config_path: str
    init_template: str
    elf_machine: int
    max_binary_bytes: int
    required_applets: tuple[str, ...]
    forbidden_remote_access_applets: tuple[str, ...]
    network_default: str
    ssh_default: str

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def lock_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StaticElfInspection:
    size: int
    sha256: str
    elf_type: int
    elf_machine: int
    program_header_count: int
    has_interpreter: bool


@dataclass(frozen=True)
class RescuePayloadEvidence:
    schema_version: int
    payload_id: str
    architecture: str
    source_lock_sha256: str
    busybox_version: str
    busybox_sha256: str
    busybox_size: int
    elf_machine: int
    statically_linked: bool
    applet_manifest_sha256: str
    applet_count: int
    init_sha256: str
    staging_manifest_sha256: str
    network_default: str
    ssh_default: str
    verified: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _SHA256_CHARS for character in value)
    ):
        raise RescuePayloadError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _safe_repo_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RescuePayloadError(f"{field} must be a non-empty repository-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\x00" in value:
        raise RescuePayloadError(f"{field} must be a safe repository-relative path")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > _MAX_APPLETS:
        raise RescuePayloadError(f"{field} must be a bounded non-empty string list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or item.strip() != item:
            raise RescuePayloadError(f"{field} contains an invalid applet name")
        if "/" in item or "\\" in item or "\x00" in item:
            raise RescuePayloadError(f"{field} contains an unsafe applet name")
        items.append(item)
    if len(items) != len(set(items)):
        raise RescuePayloadError(f"{field} contains duplicates")
    return tuple(items)


def load_rescue_payload_lock(path: Path) -> RescuePayloadLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RescuePayloadError(f"cannot load rescue payload lock: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise RescuePayloadError("unsupported rescue payload lock schema")
    busybox = raw.get("busybox")
    policy = raw.get("binary_policy")
    if not isinstance(busybox, dict) or not isinstance(policy, dict):
        raise RescuePayloadError("rescue payload lock requires busybox and binary_policy objects")
    if raw.get("architecture") != "arm64":
        raise RescuePayloadError("rescue payload architecture must be arm64")
    if not isinstance(raw.get("payload_id"), str) or not raw["payload_id"]:
        raise RescuePayloadError("payload_id must be non-empty")
    if not isinstance(busybox.get("version"), str) or not busybox["version"]:
        raise RescuePayloadError("busybox.version must be non-empty")
    parsed = urlparse(str(busybox.get("source_url", "")))
    if parsed.scheme != "https" or parsed.hostname not in {"busybox.net", "www.busybox.net"}:
        raise RescuePayloadError("BusyBox source must use the official HTTPS busybox.net origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RescuePayloadError("BusyBox source URL must not contain credentials/query/fragment")
    source_sha256 = _require_sha256(busybox.get("source_sha256"), "busybox.source_sha256")
    if busybox.get("license") != "GPL-2.0-only":
        raise RescuePayloadError("BusyBox rescue source license must be explicitly GPL-2.0-only")
    if policy.get("elf_class") != 64 or policy.get("endianness") != "little":
        raise RescuePayloadError("rescue BusyBox must be little-endian ELF64")
    if policy.get("require_static") is not True:
        raise RescuePayloadError("rescue BusyBox must require static linking")
    if policy.get("elf_machine") != _AARCH64_MACHINE:
        raise RescuePayloadError("rescue BusyBox must require the AArch64 ELF machine")
    max_binary_bytes = policy.get("max_binary_bytes")
    if not isinstance(max_binary_bytes, int) or isinstance(max_binary_bytes, bool) or not (65536 <= max_binary_bytes <= 64 * 1024 * 1024):
        raise RescuePayloadError("binary_policy.max_binary_bytes is outside the safety range")
    required = _string_tuple(raw.get("required_applets"), "required_applets")
    forbidden = _string_tuple(raw.get("forbidden_remote_access_applets"), "forbidden_remote_access_applets")
    if set(required) & set(forbidden):
        raise RescuePayloadError("required and forbidden rescue applets overlap")
    if raw.get("network_default") != "disabled" or raw.get("ssh_default") != "disabled":
        raise RescuePayloadError("rescue network and SSH defaults must be disabled")
    return RescuePayloadLock(
        schema_version=1,
        payload_id=raw["payload_id"],
        architecture="arm64",
        busybox_version=busybox["version"],
        source_url=busybox["source_url"],
        source_sha256=source_sha256,
        license=busybox["license"],
        config_path=_safe_repo_path(busybox.get("config_path"), "busybox.config_path"),
        init_template=_safe_repo_path(raw.get("init_template"), "init_template"),
        elf_machine=_AARCH64_MACHINE,
        max_binary_bytes=max_binary_bytes,
        required_applets=required,
        forbidden_remote_access_applets=forbidden,
        network_default="disabled",
        ssh_default="disabled",
    )


def inspect_static_arm64_elf(path: Path, lock: RescuePayloadLock) -> StaticElfInspection:
    if not path.is_file() or path.is_symlink():
        raise RescuePayloadError("rescue BusyBox must be a regular file")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise RescuePayloadError(f"cannot stat rescue BusyBox: {exc}") from exc
    if size <= 0 or size > lock.max_binary_bytes:
        raise RescuePayloadError("rescue BusyBox size is outside the lock policy")
    payload = path.read_bytes()
    if len(payload) != size:
        raise RescuePayloadError("rescue BusyBox changed while being inspected")
    if len(payload) < 64 or payload[:4] != b"\x7fELF":
        raise RescuePayloadError("rescue BusyBox is not an ELF executable")
    ident = payload[:16]
    if ident[4] != 2 or ident[5] != 1 or ident[6] != 1:
        raise RescuePayloadError("rescue BusyBox must be current little-endian ELF64")
    elf_type, machine = struct.unpack_from("<HH", payload, 16)
    if machine != lock.elf_machine:
        raise RescuePayloadError(f"rescue BusyBox ELF machine mismatch: {machine}")
    phoff = struct.unpack_from("<Q", payload, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", payload, 54)
    if phnum <= 0 or phnum > 256 or phentsize < 56:
        raise RescuePayloadError("rescue BusyBox has invalid program-header metadata")
    table_end = phoff + phentsize * phnum
    if phoff < 64 or table_end > len(payload):
        raise RescuePayloadError("rescue BusyBox program-header table is out of bounds")
    has_interpreter = False
    for index in range(phnum):
        p_type = struct.unpack_from("<I", payload, phoff + index * phentsize)[0]
        if p_type == 3:  # PT_INTERP
            has_interpreter = True
            break
    if has_interpreter:
        raise RescuePayloadError("rescue BusyBox has PT_INTERP and is not accepted as static")
    return StaticElfInspection(
        size=size,
        sha256=sha256(payload).hexdigest(),
        elf_type=elf_type,
        elf_machine=machine,
        program_header_count=phnum,
        has_interpreter=False,
    )


def load_verified_applet_list(path: Path, lock: RescuePayloadLock) -> tuple[str, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RescuePayloadError(f"cannot read BusyBox applet list: {exc}") from exc
    applets = tuple(sorted(set(line.strip() for line in lines if line.strip())))
    if not applets or len(applets) > _MAX_APPLETS:
        raise RescuePayloadError("BusyBox applet list is empty or exceeds the safety limit")
    if any("/" in item or "\\" in item or "\x00" in item for item in applets):
        raise RescuePayloadError("BusyBox applet list contains an unsafe name")
    missing = sorted(set(lock.required_applets) - set(applets))
    if missing:
        raise RescuePayloadError(f"BusyBox is missing required rescue applets: {', '.join(missing)}")
    forbidden = sorted(set(lock.forbidden_remote_access_applets) & set(applets))
    if forbidden:
        raise RescuePayloadError(f"BusyBox contains forbidden remote-access applets: {', '.join(forbidden)}")
    return applets


def _staging_manifest(root: Path) -> bytes:
    rows: list[dict[str, Any]] = []
    for item in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix()
        metadata = item.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if item.is_symlink():
            target = item.readlink().as_posix()
            rows.append({"path": relative, "kind": "symlink", "mode": mode, "target": target})
        elif item.is_dir():
            rows.append({"path": relative, "kind": "directory", "mode": mode})
        elif item.is_file():
            data = item.read_bytes()
            rows.append({"path": relative, "kind": "file", "mode": mode, "size": len(data), "sha256": sha256(data).hexdigest()})
        else:
            raise RescuePayloadError(f"unexpected special file in rescue staging: {relative}")
    return (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def prepare_rescue_staging(
    lock: RescuePayloadLock,
    *,
    busybox: Path,
    applet_list: Path,
    init_template: Path,
    destination: Path,
) -> RescuePayloadEvidence:
    inspection = inspect_static_arm64_elf(busybox, lock)
    applets = load_verified_applet_list(applet_list, lock)
    if destination.exists():
        raise RescuePayloadError("refusing to overwrite an existing rescue staging tree")
    if not init_template.is_file() or init_template.is_symlink():
        raise RescuePayloadError("rescue /init template must be a regular file")
    init_payload = init_template.read_bytes()
    if not init_payload.startswith(b"#!/bin/sh\n") or not init_payload:
        raise RescuePayloadError("rescue /init template must be a non-empty /bin/sh script")
    if b"network=disabled" not in init_payload or b"ssh=disabled" not in init_payload:
        raise RescuePayloadError("rescue /init must explicitly retain disabled network/SSH defaults")

    destination.mkdir(parents=True)
    try:
        for name, mode in (
            ("bin", 0o755), ("sbin", 0o755), ("proc", 0o755), ("sys", 0o755),
            ("dev", 0o755), ("dev/pts", 0o755), ("run", 0o755), ("tmp", 0o1777),
        ):
            directory = destination / name
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(mode)

        target_busybox = destination / "bin" / "busybox"
        shutil.copyfile(busybox, target_busybox)
        target_busybox.chmod(0o755)
        target_init = destination / "init"
        target_init.write_bytes(init_payload)
        target_init.chmod(0o755)

        for applet in lock.required_applets:
            parent = destination / ("sbin" if applet in _SBIN_APPLETS else "bin")
            link = parent / applet
            target = "../bin/busybox" if parent.name == "sbin" else "busybox"
            link.symlink_to(target)

        manifest = _staging_manifest(destination)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

    applet_payload = ("\n".join(applets) + "\n").encode("utf-8")
    return RescuePayloadEvidence(
        schema_version=1,
        payload_id=lock.payload_id,
        architecture=lock.architecture,
        source_lock_sha256=lock.lock_sha256(),
        busybox_version=lock.busybox_version,
        busybox_sha256=inspection.sha256,
        busybox_size=inspection.size,
        elf_machine=inspection.elf_machine,
        statically_linked=not inspection.has_interpreter,
        applet_manifest_sha256=sha256(applet_payload).hexdigest(),
        applet_count=len(applets),
        init_sha256=sha256(init_payload).hexdigest(),
        staging_manifest_sha256=sha256(manifest).hexdigest(),
        network_default=lock.network_default,
        ssh_default=lock.ssh_default,
        verified=True,
    )


def write_rescue_payload_evidence(evidence: RescuePayloadEvidence, destination: Path) -> str:
    if evidence.schema_version != 1 or evidence.verified is not True:
        raise RescuePayloadError("cannot serialize unverified rescue payload evidence")
    for value, field in (
        (evidence.source_lock_sha256, "source lock"),
        (evidence.busybox_sha256, "BusyBox"),
        (evidence.applet_manifest_sha256, "applet manifest"),
        (evidence.init_sha256, "/init"),
        (evidence.staging_manifest_sha256, "staging manifest"),
    ):
        _require_sha256(value, field)
    if evidence.architecture != "arm64" or evidence.elf_machine != _AARCH64_MACHINE:
        raise RescuePayloadError("rescue payload evidence architecture is invalid")
    if evidence.statically_linked is not True:
        raise RescuePayloadError("rescue payload evidence is not static")
    if evidence.network_default != "disabled" or evidence.ssh_default != "disabled":
        raise RescuePayloadError("rescue payload evidence violates offline defaults")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
