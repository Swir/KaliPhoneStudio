"""Fail-closed cross-profile registry audit for KaliPhoneStudio.

The runtime profile loader validates each profile independently and the device
identifier already refuses ambiguous matches. This module adds the registry-wide
contract needed for a growing multi-device catalogue: profile-specific
confirmation tokens must remain unique and every declared identity token must
resolve back to exactly one profile under the current matching semantics.

The audit is host-only. It never invokes ADB/Fastboot, never talks to a phone,
never selects a partition or storage target, and grants no hardware/Beta credit.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

from .profiles import DeviceProfile, ProfileError, discover_profiles, identify_profile


DEFAULT_DEVICES_ROOT = Path(__file__).resolve().parents[1] / "devices"
_GENERIC_CONFIRMATION_TOKENS = frozenset(
    {
        "ok",
        "yes",
        "confirm",
        "continue",
        "boot",
        "flash",
        "write",
        "install",
        "proceed",
    }
)


class ProfileRegistryAuditError(ProfileError):
    """Raised when the device-profile registry is unsafe or ambiguous."""


@dataclass(frozen=True)
class ProfileRegistryAuditResult:
    schema_version: int
    status: str
    profile_count: int
    profile_ids: tuple[str, ...]
    confirmation_tokens_unique: bool
    identity_probe_count: int
    canonical_identity_bundle_count: int
    ambiguous_identity_allowed: bool
    physical_interaction_performed: bool
    external_device_command_executed: bool
    storage_target_selected: bool
    persistent_write_authorized: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_gate_credit: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalized_token(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileRegistryAuditError(f"{label} must be a non-empty string")
    return value.strip().casefold()


def _aliases(profile: DeviceProfile) -> tuple[str, ...]:
    raw = profile.data.get("aliases", [])
    if not isinstance(raw, list):
        raise ProfileRegistryAuditError(f"{profile.profile_id}: aliases must be a list")
    aliases: list[str] = []
    normalized: set[str] = set()
    for index, value in enumerate(raw):
        token = _normalized_token(value, f"{profile.profile_id}: aliases[{index}]")
        if token in normalized:
            raise ProfileRegistryAuditError(
                f"{profile.profile_id}: aliases contain a duplicate after normalization: {value!r}"
            )
        normalized.add(token)
        aliases.append(value.strip())
    return tuple(aliases)


def _check_confirmation_tokens(profiles: Sequence[DeviceProfile]) -> None:
    owners: dict[str, str] = {}
    for profile in profiles:
        raw = profile.confirmation_text
        token = _normalized_token(raw, f"{profile.profile_id}: confirmation_text")
        if len(token) < 4 or token in _GENERIC_CONFIRMATION_TOKENS:
            raise ProfileRegistryAuditError(
                f"{profile.profile_id}: confirmation_text must be profile-specific, not generic"
            )
        previous = owners.get(token)
        if previous is not None:
            raise ProfileRegistryAuditError(
                "confirmation_text collision after normalization between "
                f"{previous} and {profile.profile_id}"
            )
        owners[token] = profile.profile_id


def _identity_probes(profile: DeviceProfile) -> tuple[tuple[str, str], ...]:
    probes: list[tuple[str, str]] = [
        ("product", str(profile.data["codename"]).strip()),
        ("model", str(profile.data["model"]).strip()),
    ]
    board = profile.data.get("bootloader_board_name")
    if board is not None:
        probes.append(("board", str(board).strip()))
    # DeviceProfile.matches intentionally accepts legacy aliases for every signal.
    # Probe aliases through product because any cross-profile collision would be
    # ambiguous for at least one accepted signal under the same matching logic.
    probes.extend(("product", alias) for alias in _aliases(profile))

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for signal, value in probes:
        if not value:
            raise ProfileRegistryAuditError(
                f"{profile.profile_id}: {signal} identity token must be non-empty"
            )
        key = (signal, value.casefold())
        if key not in seen:
            seen.add(key)
            deduped.append((signal, value))
    return tuple(deduped)


def _resolve_probe(
    profiles: Sequence[DeviceProfile],
    *,
    expected_profile_id: str,
    signal: str,
    value: str,
) -> None:
    kwargs = {"product": "", "model": "", "board": ""}
    kwargs[signal] = value
    try:
        resolved = identify_profile(profiles, **kwargs)
    except ProfileError as exc:
        raise ProfileRegistryAuditError(
            f"identity probe {signal}={value!r} for {expected_profile_id} is ambiguous or unresolved: {exc}"
        ) from exc
    if resolved.profile_id != expected_profile_id:
        raise ProfileRegistryAuditError(
            f"identity probe {signal}={value!r} resolved {resolved.profile_id}, expected {expected_profile_id}"
        )


def audit_profile_registry(root: Path) -> ProfileRegistryAuditResult:
    """Validate the complete registry as one fail-closed identity namespace."""
    profiles = tuple(discover_profiles(Path(root)))
    if not profiles:
        raise ProfileRegistryAuditError("device profile registry is empty")

    _check_confirmation_tokens(profiles)

    identity_probe_count = 0
    canonical_bundle_count = 0
    for profile in profiles:
        for signal, value in _identity_probes(profile):
            _resolve_probe(
                profiles,
                expected_profile_id=profile.profile_id,
                signal=signal,
                value=value,
            )
            identity_probe_count += 1

        board = profile.data.get("bootloader_board_name")
        try:
            resolved = identify_profile(
                profiles,
                product=str(profile.data["codename"]).strip(),
                model=str(profile.data["model"]).strip(),
                board=str(board).strip() if board is not None else "",
            )
        except ProfileError as exc:
            raise ProfileRegistryAuditError(
                f"canonical identity bundle for {profile.profile_id} is ambiguous or unresolved: {exc}"
            ) from exc
        if resolved.profile_id != profile.profile_id:
            raise ProfileRegistryAuditError(
                f"canonical identity bundle resolved {resolved.profile_id}, expected {profile.profile_id}"
            )
        canonical_bundle_count += 1

    return ProfileRegistryAuditResult(
        schema_version=1,
        status="pass",
        profile_count=len(profiles),
        profile_ids=tuple(profile.profile_id for profile in profiles),
        confirmation_tokens_unique=True,
        identity_probe_count=identity_probe_count,
        canonical_identity_bundle_count=canonical_bundle_count,
        ambiguous_identity_allowed=False,
        physical_interaction_performed=False,
        external_device_command_executed=False,
        storage_target_selected=False,
        persistent_write_authorized=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_gate_credit=False,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio audit-profile-registry",
        description=(
            "Validate the complete multi-device profile registry for unique confirmation tokens and "
            "unambiguous declared identity probes. Host-only; grants no hardware/Beta credit."
        ),
    )
    parser.add_argument(
        "--devices-root",
        type=Path,
        default=DEFAULT_DEVICES_ROOT,
        help="Path containing devices/<vendor>/<codename>/profile.json.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable audit output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = audit_profile_registry(args.devices_root)
    except (ProfileError, OSError) as exc:
        print(f"Profile registry audit error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print("profile registry audit: PASS")
        print(f"profiles: {result.profile_count}")
        print(f"identity probes: {result.identity_probe_count}")
        print("confirmation tokens: unique and profile-specific")
        print("ambiguous identity: forbidden")
        print("physical interaction/device commands: no")
        print("hardware/Beta credit: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
