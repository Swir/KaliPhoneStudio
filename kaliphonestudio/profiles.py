"""Device profile registry and schema contract for KaliPhoneStudio."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROFILE_SCHEMA_VERSION = 1


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


def validate_profile(data: dict[str, Any]) -> None:
    missing = sorted(REQUIRED - data.keys())
    if missing:
        raise ProfileError(f"missing profile fields: {', '.join(missing)}")
    if data["schema_version"] != PROFILE_SCHEMA_VERSION:
        raise ProfileError(f"unsupported schema_version: {data['schema_version']!r}")
    pid = data["profile_id"]
    if not isinstance(pid, str) or pid.count("/") != 1 or pid.startswith("/") or pid.endswith("/"):
        raise ProfileError("profile_id must be vendor/codename")
    if not isinstance(data["confirmation_text"], str) or not data["confirmation_text"].strip():
        raise ProfileError("confirmation_text must be non-empty")
    boot = data["boot"]
    if not isinstance(boot, dict) or int(boot.get("header_version", -1)) < 0:
        raise ProfileError("boot.header_version is required")
    limits = data["partition_limits"]
    if not isinstance(limits, dict) or not limits or any(not isinstance(v, int) or v <= 0 for v in limits.values()):
        raise ProfileError("partition_limits must contain positive integer byte limits")
    _nonempty_strings(data["firmware_hints"], "firmware_hints")
    _nonempty_strings(data["recovery_notes"], "recovery_notes")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise ProfileError("sources must contain at least one pinned upstream source")
    for source in sources:
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip() for k in ("name", "url", "commit")):
            raise ProfileError("each source requires name, url and commit")
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
