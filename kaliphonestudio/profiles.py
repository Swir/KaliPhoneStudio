"""Device profile registry for KaliPhoneStudio."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


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
    "profile_id", "vendor", "display_name", "codename", "model",
    "confirmation_text", "arch", "soc", "board", "boot",
    "partition_limits", "ab_device", "avb_enabled", "source_baseline",
}


def validate_profile(data: dict[str, Any]) -> None:
    missing = sorted(REQUIRED - data.keys())
    if missing:
        raise ProfileError(f"missing profile fields: {', '.join(missing)}")
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


def load_profile(path: Path) -> DeviceProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
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
