"""Fail-closed cross-profile registry audit for KaliPhoneStudio.

The runtime profile loader validates each profile independently. This module adds
registry-wide guarantees for a growing multi-device catalogue: profile-specific
confirmation tokens remain unique, every declared strong identity signal resolves
back to exactly one profile, and weak contextual signals can be shared without
becoming sufficient to identify a device by themselves.

The audit is host-only. It never invokes ADB/Fastboot, never talks to a phone,
never selects a partition or storage target, and grants no hardware/Beta credit.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
    strong_identity_probe_count: int
    weak_identity_probe_count: int
    shared_weak_identity_value_count: int
    canonical_identity_bundle_count: int
    weak_identity_alone_allowed: bool
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


def _identity_probes(profile: DeviceProfile) -> tuple[tuple[str, str, str], ...]:
    probes: list[tuple[str, str, str]] = []
    contract = profile.data["identity_signals"]
    for signal in ("product", "model", "board"):
        signal_contract = contract.get(signal)
        if signal_contract is None:
            continue
        strength = str(signal_contract["strength"])
        for value in signal_contract["values"]:
            probes.append((signal, str(value).strip(), strength))
    return tuple(probes)


def _resolve_strong_probe(
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
            f"strong identity probe {signal}={value!r} for {expected_profile_id} "
            f"is ambiguous or unresolved: {exc}"
        ) from exc
    if resolved.profile_id != expected_profile_id:
        raise ProfileRegistryAuditError(
            f"strong identity probe {signal}={value!r} resolved {resolved.profile_id}, "
            f"expected {expected_profile_id}"
        )


def _assert_weak_probe_cannot_identify(
    profiles: Sequence[DeviceProfile],
    *,
    signal: str,
    value: str,
) -> None:
    kwargs = {"product": "", "model": "", "board": ""}
    kwargs[signal] = value
    try:
        resolved = identify_profile(profiles, **kwargs)
    except ProfileError:
        return
    raise ProfileRegistryAuditError(
        f"weak identity probe {signal}={value!r} unexpectedly identified {resolved.profile_id}"
    )


def audit_profile_registry(root: Path) -> ProfileRegistryAuditResult:
    """Validate the complete registry as one fail-closed typed identity namespace."""
    profiles = tuple(discover_profiles(Path(root)))
    if not profiles:
        raise ProfileRegistryAuditError("device profile registry is empty")

    _check_confirmation_tokens(profiles)

    identity_probe_count = 0
    strong_identity_probe_count = 0
    weak_identity_probe_count = 0
    weak_tokens: list[tuple[str, str]] = []
    canonical_bundle_count = 0

    for profile in profiles:
        for signal, value, strength in _identity_probes(profile):
            identity_probe_count += 1
            if strength == "strong":
                _resolve_strong_probe(
                    profiles,
                    expected_profile_id=profile.profile_id,
                    signal=signal,
                    value=value,
                )
                strong_identity_probe_count += 1
            elif strength == "weak":
                _assert_weak_probe_cannot_identify(
                    profiles,
                    signal=signal,
                    value=value,
                )
                weak_identity_probe_count += 1
                weak_tokens.append((signal, value.casefold()))
            else:  # per-profile validation should make this unreachable
                raise ProfileRegistryAuditError(
                    f"{profile.profile_id}: unsupported identity strength {strength!r}"
                )

        contract = profile.data["identity_signals"]
        product_values = contract.get("product", {}).get("values", [])
        model_values = contract.get("model", {}).get("values", [])
        board_values = contract.get("board", {}).get("values", [])
        product = str(product_values[0]).strip() if product_values else ""
        model = str(model_values[0]).strip() if model_values else ""
        board = str(board_values[0]).strip() if board_values else ""
        try:
            resolved = identify_profile(
                profiles,
                product=product,
                model=model,
                board=board,
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

    weak_counts = Counter(weak_tokens)
    shared_weak_identity_value_count = sum(1 for count in weak_counts.values() if count > 1)

    return ProfileRegistryAuditResult(
        schema_version=2,
        status="pass",
        profile_count=len(profiles),
        profile_ids=tuple(profile.profile_id for profile in profiles),
        confirmation_tokens_unique=True,
        identity_probe_count=identity_probe_count,
        strong_identity_probe_count=strong_identity_probe_count,
        weak_identity_probe_count=weak_identity_probe_count,
        shared_weak_identity_value_count=shared_weak_identity_value_count,
        canonical_identity_bundle_count=canonical_bundle_count,
        weak_identity_alone_allowed=False,
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
            "Validate the complete multi-device profile registry for unique confirmation tokens, "
            "unique strong identity signals and non-identifying weak context signals. Host-only; "
            "grants no hardware/Beta credit."
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
        print(f"strong identity probes: {result.strong_identity_probe_count}")
        print(f"weak identity probes: {result.weak_identity_probe_count}")
        print(f"shared weak identity values: {result.shared_weak_identity_value_count}")
        print("confirmation tokens: unique and profile-specific")
        print("weak-only identification: forbidden")
        print("ambiguous strong identity: forbidden")
        print("physical interaction/device commands: no")
        print("hardware/Beta credit: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
