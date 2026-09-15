"""Safety primitives for operations that can modify a phone."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .profiles import DeviceProfile


class SafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedDevice:
    profile_id: str
    serial: str
    current_slot: str
    unlocked: bool


def require_confirmation(profile: DeviceProfile, typed: str) -> None:
    if typed.strip() != profile.confirmation_text:
        raise SafetyError("confirmation token does not match selected device profile")


def require_verified_device(profile: DeviceProfile, device: VerifiedDevice) -> None:
    if device.profile_id != profile.profile_id:
        raise SafetyError("verified device belongs to a different profile")
    if not device.serial.strip():
        raise SafetyError("device serial is missing")
    if device.current_slot not in {"a", "b"}:
        raise SafetyError("A/B current slot must be a or b")
    if not device.unlocked:
        raise SafetyError("bootloader must be unlocked before boot-image testing")


def inactive_slot(current_slot: str) -> str:
    if current_slot == "a":
        return "b"
    if current_slot == "b":
        return "a"
    raise SafetyError("invalid current slot")


def validate_image(profile: DeviceProfile, partition: str, image: Path) -> str:
    if partition not in profile.data["partition_limits"]:
        raise SafetyError(f"partition {partition!r} is not allowed by profile")
    if not image.is_file():
        raise SafetyError(f"image not found: {image}")
    size = image.stat().st_size
    limit = profile.data["partition_limits"][partition]
    if size <= 0 or size > limit:
        raise SafetyError(f"{partition} image size {size} exceeds profile limit {limit}")
    digest = sha256()
    with image.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def persistent_target(profile: DeviceProfile, device: VerifiedDevice, partition: str) -> str:
    require_verified_device(profile, device)
    if not profile.data.get("ab_device"):
        raise SafetyError("persistent writes are disabled for non-A/B profiles")
    if partition not in set(profile.data.get("ab_partitions", [])):
        raise SafetyError("persistent write is not permitted for this partition")
    return f"{partition}_{inactive_slot(device.current_slot)}"
