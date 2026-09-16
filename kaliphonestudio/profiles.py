"""Device profile registry and schema contract for KaliPhoneStudio."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.parse import urlparse


PROFILE_SCHEMA_VERSION = 1
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SAFE_PARTITION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ALLOWED_RAMDISK_COMPRESSION = {"gzip", "lz4", "none"}


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


def _nonempty_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ProfileError(f"{field} must be a non-empty list of non-empty strings")
    return value


def _require_plain_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ProfileError(f"{field} must be an integer >= {minimum}")
    return value


def _validate_profile_id(data: dict[str, Any]) -> None:
    pid = data["profile_id"]
    if not isinstance(pid, str) or pid.count("/") != 1 or pid.startswith("/") or pid.endswith("/"):
        raise ProfileError("profile_id must be vendor/codename")
    vendor_id, codename_id = pid.split("/", 1)
    if not _SAFE_ID_RE.fullmatch(vendor_id) or not _SAFE_ID_RE.fullmatch(codename_id):
        raise ProfileError("profile_id components must use lowercase safe identifier characters")
    vendor = data.get("vendor")
    if not isinstance(vendor, str) or vendor.strip().lower() != vendor_id:
        raise ProfileError("profile_id vendor must match the profile vendor")
    codename = data.get("codename")
    if not isinstance(codename, str) or codename.strip().lower() != codename_id:
        raise ProfileError("profile_id codename must match the profile codename")


def _validate_boot_contract(boot: Any) -> None:
    if not isinstance(boot, dict):
        raise ProfileError("boot must be an object")
    required = {
        "header_version",
        "page_size",
        "kernel_image",
        "include_dtb",
        "separate_dtbo",
        "ramdisk_compression",
    }
    missing = sorted(required - boot.keys())
    if missing:
        raise ProfileError(f"missing boot contract fields: {', '.join(missing)}")
    header = _require_plain_int(boot["header_version"], "boot.header_version")
    if header > 4:
        raise ProfileError("boot.header_version is outside the supported Android boot-image range")
    page_size = _require_plain_int(boot["page_size"], "boot.page_size", minimum=512)
    if page_size & (page_size - 1):
        raise ProfileError("boot.page_size must be a power of two")
    if not isinstance(boot["kernel_image"], str) or not boot["kernel_image"].strip():
        raise ProfileError("boot.kernel_image must be a non-empty string")
    for field in ("include_dtb", "separate_dtbo"):
        if not isinstance(boot[field], bool):
            raise ProfileError(f"boot.{field} must be boolean")
    if boot["ramdisk_compression"] not in _ALLOWED_RAMDISK_COMPRESSION:
        raise ProfileError(
            "boot.ramdisk_compression must be one of gzip, lz4 or none"
        )


def _validate_partition_contract(data: dict[str, Any]) -> None:
    limits = data["partition_limits"]
    if not isinstance(limits, dict) or not limits:
        raise ProfileError("partition_limits must contain positive integer byte limits")
    for name, value in limits.items():
        if not isinstance(name, str) or not _SAFE_PARTITION_RE.fullmatch(name):
            raise ProfileError("partition_limits contains an unsafe partition identifier")
        _require_plain_int(value, f"partition_limits.{name}", minimum=1)

    if not isinstance(data["ab_device"], bool):
        raise ProfileError("ab_device must be boolean")
    if not isinstance(data["avb_enabled"], bool):
        raise ProfileError("avb_enabled must be boolean")
    if data["ab_device"]:
        partitions = _nonempty_strings(data.get("ab_partitions"), "ab_partitions")
        if len(partitions) != len(set(partitions)):
            raise ProfileError("ab_partitions must not contain duplicates")
        if any(not _SAFE_PARTITION_RE.fullmatch(item) for item in partitions):
            raise ProfileError("ab_partitions contains an unsafe partition identifier")
        if "boot" not in partitions:
            raise ProfileError("A/B device profile must declare boot in ab_partitions")


def validate_profile(data: dict[str, Any]) -> None:
    missing = sorted(REQUIRED - data.keys())
    if missing:
        raise ProfileError(f"missing profile fields: {', '.join(missing)}")
    if data["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ProfileError(f"unsupported schema_version: {data['schema_version']!r}")
    _validate_profile_id(data)
    if not isinstance(data["confirmation_text"], str) or not data["confirmation_text"].strip():
        raise ProfileError("confirmation_text must be non-empty")
    for field in ("vendor", "display_name", "model", "arch", "soc", "board"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ProfileError(f"{field} must be a non-empty string")

    _validate_boot_contract(data["boot"])
    _validate_partition_contract(data)
    _nonempty_strings(data["firmware_hints"], "firmware_hints")
    _nonempty_strings(data["recovery_notes"], "recovery_notes")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise ProfileError("sources must contain at least one pinned upstream source")
    for source in sources:
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip() for k in ("name", "url", "commit")):
            raise ProfileError("each source requires name, url and commit")
        parsed = urlparse(source["url"])
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ProfileError("source url must be an HTTPS URL without embedded credentials")
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
    return DeviceProfile(path=path, data=data)


def discover_profiles(root: Path) -> list[DeviceProfile]:
    profiles = [load_profile(p) for p in sorted(root.glob("*/*/profile.json"))]
    ids = [p.profile_id for p in profiles]
    if len(ids) != len(set(ids)):
        raise ProfileError("duplicate profile_id")
    for profile in profiles:
        expected = root / profile.profile_id / "profile.json"
        try:
            actual_resolved = profile.path.resolve(strict=True)
            expected_resolved = expected.resolve(strict=True)
        except OSError as exc:
            raise ProfileError(f"cannot resolve profile path contract: {exc}") from exc
        if actual_resolved != expected_resolved:
            raise ProfileError(
                f"profile_id/path mismatch: {profile.profile_id} is not stored at {expected}"
            )
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
