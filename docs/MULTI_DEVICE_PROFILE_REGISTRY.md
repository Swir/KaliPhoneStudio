# Multi-device profile registry contract

KaliPhoneStudio keeps phone-specific knowledge under `devices/<vendor>/<codename>/profile.json` while the Python core remains device-agnostic. A profile that validates in isolation is not enough for safe multi-device operation: the **complete registry must also remain unambiguous**.

## Registry-wide audit

Run the same check used by CI:

```bash
python -m kaliphonestudio.profile_registry_audit --devices-root devices --json
```

The packaged CLI exposes the same host-only command:

```text
KaliPhoneStudioCLI.exe audit-profile-registry --json
```

The audit loads every profile through the normal `discover_profiles()` schema/path contract and then checks the registry as one identity namespace.

## Fail-closed rules

A registry is rejected when any of these conditions is present:

- no device profiles are available;
- two profiles use the same confirmation token after whitespace/case normalization;
- a confirmation token is a generic action word such as `YES`, `CONFIRM`, `FLASH` or `BOOT` instead of a profile-specific token;
- a profile contains malformed or duplicate aliases after normalization;
- a declared codename, model, bootloader-board token or legacy alias cannot resolve uniquely to the profile that declared it;
- the canonical product/model/board bundle becomes ambiguous under the current runtime matching semantics.

This is deliberately strict. If two future phones legitimately share a weak identifier such as a bootloader board name, the runtime identity contract must first be evolved to distinguish strong and weak signals. CI must not silently accept a registry that the current runtime matcher can resolve ambiguously.

## What the audit does not prove

A passing registry audit proves only that the checked **host-side profile catalogue** is internally coherent under the current matching policy. It does not prove that a phone boots Kali, that a hardware subsystem works, or that the profile has passed physical bring-up.

The command performs no physical interaction, executes no ADB/Fastboot command, selects no partition or storage target, authorizes no persistent write, and grants neither hardware-verification nor Beta-gate credit.

## Adding a device

Before a new profile can be considered for destructive or persistent actions it still needs its normal per-profile contract: exact `profile_id`, profile-specific confirmation token, boot and partition constraints, pinned upstream sources, recovery notes, host tests and a functional-hardware test contract. Adding a valid JSON file only makes the profile discoverable; it does **not** establish real device support.

After adding or changing any profile, run both the registry audit and the full test suite. Physical support remains governed separately by the device-specific bring-up and release gate.
