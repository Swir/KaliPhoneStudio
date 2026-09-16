"""Device profile registry and schema contract for KaliPhoneStudio."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable


PROFILE_SCHEMA_VERSION = 1
_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")
_PARTITION_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_SUPPORTED_RAMDISK_COMPRESSION = {"gzip", "lz4", "none"}


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceProfile:
    path: Path
    data: dict[str, Any]

    @property
    def profile_id(self) -> str:
        return self.data["profile_id"]

    @property
    def confirmation_text(self) -> str:
        return self.data["confirmation_text"]

    @property
    def ramdisk_compression(self) -> str:
        return self.data["boot"]["ramdisk_compression"]

    def matches(self, product: str = "", model: str = "", board: str = "") -> bool:
        values = {x.strip().lower() for x in (product, model, board) if x and x.strip()}
        accepted = {
            str(self.data.get("codename", "")).lower(),
            str(self.data.get("model", "")).lower(),
            str(self.data.get("bootloader_board_name", "")).lower(),
        }
        accepted.update(str(x).lower() for x in self.data.get("aliases", []))
        accepted.discard("")
        return bool(values & accepted)


REQUIRED = {
    "schema_version", "profile_id", "vendor", "display_name", "codename", "model",
    "confirmation_text", "arch", "soc", "board", "boot", "partition_limits",
    "ab_device", "avb_enabled", "firmware_hints", "sources", "recovery_notes",
    "test_contract",
}

_BOOT_REQUIRED = {
    "header_version",
    "page_size",
    "kernel_image",
    "include_dtb",
    "separate_dtbo",
    "ramdisk_compression",
}


def _nonempty_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ProfileError(f"{field} must be a non-empty list of non-empty strings")
    return value


def _require_nonempty_string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{field} must be a non-empty string")
    return value


def _validate_boot_contract(boot: Any) -> None:
    if not isinstance(boot, dict):
        raise ProfileError("boot must be an object")
    missing = sorted(_BOOT_REQUIRED - boot.keys())
    if missing:
        raise ProfileError(f"missing boot fields: {', '.join(missing)}")

    header = boot["header_version"]
    if not isinstance(header, int) or isinstance(header, bool) or not 0 <= header <= 4:
        raise ProfileError("boot.header_version must be an integer from 0 through 4")

    page_size = boot["page_size"]
    if (
        not isinstance(page_size, int)
        or isinstance(page_size, bool)
        or not 2048 <= page_size <= 65536
        or page_size & (page_size - 1)
    ):
        raise ProfileError("boot.page_size must be a power of two between 2048 and 65536")

    kernel_image = boot["kernel_image"]
    if (
        not isinstance(kernel_image, str)
        or not kernel_image.strip()
        or kernel_image in {".", ".."}
        or "/" in kernel_image
        or "\\" in kernel_image
    ):
        raise ProfileError("boot.kernel_image must be a safe basename")

    for field in ("include_dtb", "separate_dtbo"):
        if not isinstance(boot[field], bool):
            raise ProfileError(f"boot.{field} must be boolean")

    compression = boot["ramdisk_compression"]
    if compression not in _SUPPORTED_RAMDISK_COMPRESSION:
        allowed = ", ".join(sorted(_SUPPORTED_RAMDISK_COMPRESSION))
        raise ProfileError(f"boot.ramdisk_compression must be one of: {allowed}")


def validate_profile(data: dict[str, Any]) -> None:
    missing = sorted(REQUIRED - data.keys())
    if missing:
        raise ProfileError(f"missing profile fields: {', '.join(missing)}")
    if data["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ProfileError(f"unsupported schema_version: {data['schema_version']!r}")

    pid = data["profile_id"]
    if not isinstance(pid, str) or not _PROFILE_ID_RE.fullmatch(pid):
        raise ProfileError("profile_id must be a safe lowercase vendor/codename identifier")

    for field in ("vendor", "display_name", "codename", "model", "confirmation_text", "arch", "soc", "board"):
        _require_nonempty_string(data, field)

    _validate_boot_contract(data["boot"])

    limits = data["partition_limits"]
    if not isinstance(limits, dict) or not limits:
        raise ProfileError("partition_limits must contain positive integer byte limits")
    for name, size in limits.items():
        if not isinstance(name, str) or not _PARTITION_RE.fullmatch(name):
            raise ProfileError("partition_limits contains an unsafe partition name")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ProfileError("partition_limits must contain positive integer byte limits")

    for flag in ("ab_device", "avb_enabled"):
        if not isinstance(data[flag], bool):
            raise ProfileError(f"{flag} must be boolean")

    if data["ab_device"]:
        ab_partitions = _nonempty_strings(data.get("ab_partitions"), "ab_partitions")
        if len(ab_partitions) != len(set(ab_partitions)):
            raise ProfileError("ab_partitions must not contain duplicates")
        if any(not _PARTITION_RE.fullmatch(name) for name in ab_partitions):
            raise ProfileError("ab_partitions contains an unsafe partition name")

    _nonempty_strings(data["firmware_hints"], "firmware_hints")
    _nonempty_strings(data["recovery_notes"], "recovery_notes")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise ProfileError("sources must contain at least one pinned upstream source")
    for source in sources:
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip() for k in ("name", "url", "commit")):
            raise ProfileError("each source requires name, url and commit")
        if not source["url"].startswith("https://"):
            raise ProfileError("source URL must use HTTPS")
        commit = source["commit"].lower()
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ProfileError("source commit must be a full 40-character git SHA")

    contract = data["test_contract"]
    if not isinstance(contract, dict):
        raise ProfileError("test_contract must be an object")
    for key in ("host", "hardware_beta"):
        _nonempty_strings(contract.get(key), f"test_contract.{key}")


def load_profile(path: Path) -> DeviceProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"cannot load profile {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError("profile root must be an object")
    validate_profile(data)

    # The directory path is part of the runtime registry contract. A profile
    # claiming another ID from a different vendor/codename directory must fail
    # before it can participate in device identification or destructive plans.
    if len(path.parts) < 3:
        raise ProfileError("profile path must end with vendor/codename/profile.json")
    expected_suffix = tuple(data["profile_id"].split("/")) + ("profile.json",)
    if tuple(path.parts[-3:]) != expected_suffix:
        raise ProfileError("profile_id does not match devices/vendor/codename path")
    return DeviceProfile(path=path, data=data)


def discover_profiles(root: Path) -> list[DeviceProfile]:
    profiles = [load_profile(p) for p in sorted(root.glob("*/*/profile.json"))]
    ids = [p.profile_id for p in profiles]
    if len(ids) != len(set(ids)):
        raise ProfileError("duplicate profile_id")
    return profiles


def get_profile(root: Path, profile_id: str) -> DeviceProfile:
    for profile in discover_profiles(root):
        if profile.profile_id == profile_id:
            return profile
    raise ProfileError(f"unknown profile: {profile_id}")


def identify_profile(profiles: Iterable[DeviceProfile], *, product: str = "", model: str = "", board: str = "") -> DeviceProfile:
    matches = [p for p in profiles if p.matches(product=product, model=model, board=board)]
    if len(matches) != 1:
        raise ProfileError(f"device identification must resolve exactly one profile; got {len(matches)}")
    return matches[0]
