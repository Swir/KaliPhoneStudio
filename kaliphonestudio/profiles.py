"""Device profile registry and schema contract for KaliPhoneStudio."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from .functional_hardware_contract import (
    FunctionalHardwareContractError,
    validate_functional_hardware_contract,
)


PROFILE_SCHEMA_VERSION = 3
IDENTITY_SCHEMA_VERSION = 1
_IDENTITY_SIGNAL_NAMES = frozenset({"product", "model", "board"})
_IDENTITY_STRENGTHS = frozenset({"strong", "weak"})
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SAFE_PARTITION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SAFE_FASTBOOT_VAR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SAFE_KERNEL_CONFIG_RE = re.compile(r"^CONFIG_[A-Z0-9_]+$")
_SAFE_MAKE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SAFE_HOOK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$")
_KERNEL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_ALLOWED_RAMDISK_COMPRESSION = {"gzip", "lz4", "none"}
_ALLOWED_HOOK_STAGES = frozenset({"build", "verify", "recovery"})
_RAMDISK_DECOMPRESSOR_CONFIG = {
    "gzip": "CONFIG_RD_GZIP",
    "lz4": "CONFIG_RD_LZ4",
    "none": None,
}


class ProfileError(ValueError):
    pass


def _normalize_identity_value(value: object) -> str:
    return str(value).strip().casefold()


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

    def identity_signal(self, signal: str) -> dict[str, Any]:
        if signal not in _IDENTITY_SIGNAL_NAMES:
            raise ProfileError(f"unsupported identity signal: {signal}")
        return self.data["identity_signals"][signal]

    def matching_identity_strengths(
        self,
        *,
        product: str = "",
        model: str = "",
        board: str = "",
    ) -> dict[str, str]:
        provided = {"product": product, "model": model, "board": board}
        matched: dict[str, str] = {}
        for signal, raw_value in provided.items():
            value = _normalize_identity_value(raw_value)
            if not value:
                continue
            contract = self.identity_signal(signal)
            accepted = {_normalize_identity_value(item) for item in contract["values"]}
            if value in accepted:
                matched[signal] = str(contract["strength"])
        return matched

    def matches(self, product: str = "", model: str = "", board: str = "") -> bool:
        """Return true only when at least one profile-declared *strong* signal matches.

        Weak signals such as a shared SoC/bootloader board are context only. They can
        accompany a strong product/model match but can never identify a device by
        themselves.
        """
        return "strong" in self.matching_identity_strengths(
            product=product,
            model=model,
            board=board,
        ).values()


REQUIRED = {
    "schema_version", "profile_id", "vendor", "display_name", "codename", "model",
    "identity_signals", "confirmation_text", "arch", "soc", "board", "boot",
    "partition_limits", "ab_device", "avb_enabled", "firmware_hints", "sources",
    "recovery_notes", "test_contract", "fastboot_probe", "kernel",
}


def _nonempty_strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ProfileError(f"{field} must be a non-empty list of non-empty strings")
    return value


def _require_plain_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ProfileError(f"{field} must be an integer >= {minimum}")
    return value


def _safe_relative_posix_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise ProfileError(f"{field} must be a safe relative POSIX path")
    if any(not part or "\\" in part or any(ord(ch) < 0x20 for ch in part) for part in path.parts):
        raise ProfileError(f"{field} contains unsafe path data")
    return path.as_posix()


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


def _validate_identity_contract(data: dict[str, Any]) -> None:
    contract = data["identity_signals"]
    if not isinstance(contract, dict):
        raise ProfileError("identity_signals must be an object")
    if contract.get("schema_version") != IDENTITY_SCHEMA_VERSION:
        raise ProfileError(
            f"identity_signals.schema_version must be {IDENTITY_SCHEMA_VERSION}"
        )
    signal_names = set(contract) - {"schema_version"}
    unknown = sorted(signal_names - _IDENTITY_SIGNAL_NAMES)
    if unknown:
        raise ProfileError(f"identity_signals contains unsupported signals: {', '.join(unknown)}")
    if not signal_names:
        raise ProfileError("identity_signals must declare at least one signal")

    strong_count = 0
    all_values: set[str] = set()
    for signal in sorted(signal_names):
        item = contract[signal]
        if not isinstance(item, dict):
            raise ProfileError(f"identity_signals.{signal} must be an object")
        if set(item) != {"strength", "values"}:
            raise ProfileError(
                f"identity_signals.{signal} must contain only strength and values"
            )
        strength = item["strength"]
        if strength not in _IDENTITY_STRENGTHS:
            raise ProfileError(
                f"identity_signals.{signal}.strength must be strong or weak"
            )
        values = _nonempty_strings(item["values"], f"identity_signals.{signal}.values")
        normalized = [_normalize_identity_value(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ProfileError(
                f"identity_signals.{signal}.values must be unique after normalization"
            )
        all_values.update(normalized)
        if strength == "strong":
            strong_count += 1

    if strong_count == 0:
        raise ProfileError("identity_signals must declare at least one strong signal")

    product = contract.get("product")
    if not isinstance(product, dict) or product.get("strength") != "strong":
        raise ProfileError("identity_signals.product must be declared as a strong signal")
    if _normalize_identity_value(data["codename"]) not in {
        _normalize_identity_value(value) for value in product["values"]
    }:
        raise ProfileError("identity_signals.product.values must include profile codename")

    model = contract.get("model")
    if model is not None and _normalize_identity_value(data["model"]) not in {
        _normalize_identity_value(value) for value in model["values"]
    }:
        raise ProfileError("identity_signals.model.values must include profile model")

    board_name = data.get("bootloader_board_name")
    if board_name is not None:
        board = contract.get("board")
        if not isinstance(board, dict) or _normalize_identity_value(board_name) not in {
            _normalize_identity_value(value) for value in board["values"]
        }:
            raise ProfileError(
                "identity_signals.board.values must include bootloader_board_name"
            )

    aliases = data.get("aliases", [])
    if aliases is not None:
        if not isinstance(aliases, list) or any(
            not isinstance(value, str) or not value.strip() for value in aliases
        ):
            raise ProfileError("aliases must be a list of non-empty strings")
        normalized_aliases = [_normalize_identity_value(value) for value in aliases]
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ProfileError("aliases must be unique after normalization")
        missing_aliases = sorted(set(normalized_aliases) - all_values)
        if missing_aliases:
            raise ProfileError(
                "aliases are display/compatibility labels and must also be declared in identity_signals"
            )


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


def _fastboot_var(contract: dict[str, Any], field: str, required_vars: set[str], *, optional: bool = False) -> str | None:
    value = contract.get(field)
    if optional and value is None:
        return None
    if not isinstance(value, str) or not _SAFE_FASTBOOT_VAR_RE.fullmatch(value):
        raise ProfileError(f"fastboot_probe.{field} must be a safe fastboot variable name")
    if value not in required_vars:
        raise ProfileError(f"fastboot_probe.{field} must be included in required_vars")
    return value


def _validate_fastboot_probe(data: dict[str, Any]) -> None:
    contract = data["fastboot_probe"]
    if not isinstance(contract, dict):
        raise ProfileError("fastboot_probe must be an object")
    required = _nonempty_strings(contract.get("required_vars"), "fastboot_probe.required_vars")
    if len(required) != len(set(required)):
        raise ProfileError("fastboot_probe.required_vars must not contain duplicates")
    if any(not _SAFE_FASTBOOT_VAR_RE.fullmatch(name) for name in required):
        raise ProfileError("fastboot_probe.required_vars contains an unsafe variable name")
    required_vars = set(required)

    for field in ("identity_var", "serial_var", "unlocked_var", "secure_var"):
        _fastboot_var(contract, field, required_vars)
    for field in ("bootloader_version_var", "baseband_version_var"):
        _fastboot_var(contract, field, required_vars, optional=True)

    if data["ab_device"]:
        _fastboot_var(contract, "current_slot_var", required_vars)
        _fastboot_var(contract, "slot_count_var", required_vars)
        _require_plain_int(
            contract.get("expected_slot_count"),
            "fastboot_probe.expected_slot_count",
            minimum=2,
        )
    else:
        for field in ("current_slot_var", "slot_count_var"):
            _fastboot_var(contract, field, required_vars, optional=True)
        if "expected_slot_count" in contract and contract["expected_slot_count"] is not None:
            _require_plain_int(
                contract["expected_slot_count"],
                "fastboot_probe.expected_slot_count",
                minimum=1,
            )


def validate_profile_hooks_contract(raw: Any) -> None:
    """Validate optional stage -> ordered hook-ID declarations in profile JSON."""
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ProfileError("hooks must be an object")
    unknown = sorted(set(raw) - _ALLOWED_HOOK_STAGES)
    if unknown:
        raise ProfileError(f"hooks contains unsupported stages: {', '.join(unknown)}")
    for stage, hook_ids in raw.items():
        if not isinstance(hook_ids, list):
            raise ProfileError(f"hooks.{stage} must be a list")
        if len(hook_ids) != len(set(hook_ids)):
            raise ProfileError(f"hooks.{stage} must not contain duplicates")
        for hook_id in hook_ids:
            if not isinstance(hook_id, str) or not _SAFE_HOOK_ID_RE.fullmatch(hook_id):
                raise ProfileError(f"hooks.{stage} contains an unsafe hook id")


def _validate_kernel_contract(data: dict[str, Any]) -> None:
    contract = data["kernel"]
    if not isinstance(contract, dict):
        raise ProfileError("kernel must be an object")
    required_fields = {
        "source_name", "expected_version", "arch", "image_name", "defconfig",
        "config_fragments", "make_flags", "required_configs",
    }
    missing = sorted(required_fields - contract.keys())
    if missing:
        raise ProfileError(f"missing kernel contract fields: {', '.join(missing)}")

    source_name = contract["source_name"]
    if not isinstance(source_name, str) or not source_name.strip():
        raise ProfileError("kernel.source_name must be non-empty")
    matches = [source for source in data["sources"] if source.get("name") == source_name]
    if len(matches) != 1:
        raise ProfileError("kernel.source_name must resolve exactly one pinned profile source")

    version = contract["expected_version"]
    if not isinstance(version, str) or not _KERNEL_VERSION_RE.fullmatch(version):
        raise ProfileError("kernel.expected_version must be major.minor.patch")
    if contract["arch"] != data["arch"]:
        raise ProfileError("kernel.arch must match profile arch")
    if contract["image_name"] != data["boot"]["kernel_image"]:
        raise ProfileError("kernel.image_name must match boot.kernel_image")

    _safe_relative_posix_path(contract["defconfig"], "kernel.defconfig")
    fragments = contract["config_fragments"]
    if not isinstance(fragments, list) or any(not isinstance(item, str) for item in fragments):
        raise ProfileError("kernel.config_fragments must be a list of relative paths")
    normalized_fragments = [_safe_relative_posix_path(item, "kernel.config_fragments") for item in fragments]
    if len(normalized_fragments) != len(set(normalized_fragments)):
        raise ProfileError("kernel.config_fragments must not contain duplicates")

    make_flags = contract["make_flags"]
    if not isinstance(make_flags, dict):
        raise ProfileError("kernel.make_flags must be an object")
    for key, value in make_flags.items():
        if not isinstance(key, str) or not _SAFE_MAKE_KEY_RE.fullmatch(key):
            raise ProfileError("kernel.make_flags contains an unsafe variable name")
        if not isinstance(value, str) or not value or any(ord(ch) < 0x20 for ch in value):
            raise ProfileError(f"kernel.make_flags.{key} must be safe non-empty text")

    configs = contract["required_configs"]
    if not isinstance(configs, dict) or not configs:
        raise ProfileError("kernel.required_configs must be a non-empty object")
    for name, state in configs.items():
        if not isinstance(name, str) or not _SAFE_KERNEL_CONFIG_RE.fullmatch(name):
            raise ProfileError("kernel.required_configs contains an invalid CONFIG_ name")
        if state not in {"y", "m", "n"}:
            raise ProfileError(f"kernel.required_configs.{name} must be y, m or n")

    compression = data["boot"]["ramdisk_compression"]
    decompressor = _RAMDISK_DECOMPRESSOR_CONFIG[compression]
    if compression != "none" and configs.get("CONFIG_BLK_DEV_INITRD") != "y":
        raise ProfileError(
            "kernel.required_configs.CONFIG_BLK_DEV_INITRD must be y when a boot ramdisk is used"
        )
    if decompressor is not None and configs.get(decompressor) != "y":
        raise ProfileError(
            f"kernel.required_configs.{decompressor} must be y for boot.ramdisk_compression={compression}"
        )


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

    _validate_identity_contract(data)
    _validate_boot_contract(data["boot"])
    _validate_partition_contract(data)
    _validate_fastboot_probe(data)
    validate_profile_hooks_contract(data.get("hooks"))
    _nonempty_strings(data["firmware_hints"], "firmware_hints")
    _nonempty_strings(data["recovery_notes"], "recovery_notes")

    sources = data["sources"]
    if not isinstance(sources, list) or not sources:
        raise ProfileError("sources must contain at least one pinned upstream source")
    source_names: list[str] = []
    for source in sources:
        if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k].strip() for k in ("name", "url", "commit")):
            raise ProfileError("each source requires name, url and commit")
        source_names.append(source["name"])
        parsed = urlparse(source["url"])
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ProfileError("source url must be an HTTPS URL without embedded credentials")
        commit = source["commit"].lower()
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ProfileError("source commit must be a full 40-character git SHA")
    if len(source_names) != len(set(source_names)):
        raise ProfileError("source names must be unique within a profile")

    _validate_kernel_contract(data)

    contract = data["test_contract"]
    if not isinstance(contract, dict):
        raise ProfileError("test_contract must be an object")
    for key in ("host", "hardware_beta"):
        _nonempty_strings(contract.get(key), f"test_contract.{key}")
    if "functional_hardware" not in contract:
        raise ProfileError("test_contract.functional_hardware is required for every device profile")
    try:
        validate_functional_hardware_contract(contract["functional_hardware"])
    except FunctionalHardwareContractError as exc:
        raise ProfileError(f"test_contract.functional_hardware is invalid: {exc}") from exc


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
    """Resolve exactly one profile from one or more typed identity signals.

    At least one *strong* signal must match. Weak signals are deliberately ignored
    for candidate selection so a shared SoC/board identifier cannot identify a
    phone by itself. If supplied strong signals point at different profiles, the
    result is ambiguous and fails closed.
    """
    matches = [p for p in profiles if p.matches(product=product, model=model, board=board)]
    if len(matches) != 1:
        raise ProfileError(f"device identification must resolve exactly one profile; got {len(matches)}")
    return matches[0]
