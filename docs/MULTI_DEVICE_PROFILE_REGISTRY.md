# Multi-device profile registry

KaliPhoneStudio keeps device-specific knowledge under `devices/<vendor>/<codename>/profile.json`. The Python core should stay generic wherever practical; adding a JSON file alone never means a phone is physically supported.

## Profile schema v3

Every maintained profile uses `schema_version: 3` and is checked in two layers:

1. `devices/profile.schema.json` — Draft 2020-12 structural validation for required fields and typed identity structure.
2. `kaliphonestudio.profiles.validate_profile()` — fail-closed semantic validation for cross-field constraints such as profile/path identity, boot/A-B contracts, pinned source commits, kernel/ramdisk compatibility and the functional hardware test contract.

Run both layers locally with:

```bash
python -m pip install -r build/profile-schema-requirements.txt
PYTHONPATH=. python scripts/validate_device_profiles_jsonschema.py
```

The CI-only schema dependency is pinned. It is not added to the normal runtime requirements because the packaged application already ships profiles that must have passed CI before distribution.

## Typed identity signals

Profile v3 replaces the old flat alias-matching rule with explicit identity strength:

```json
"identity_signals": {
  "schema_version": 1,
  "product": {"strength": "strong", "values": ["avicii"]},
  "model": {"strength": "strong", "values": ["AC2003"]},
  "board": {"strength": "weak", "values": ["lito"]}
}
```

A **strong** signal may identify a profile if it resolves uniquely across the complete registry. A **weak** signal is context only and must never identify a device by itself. This distinction matters because multiple phones can legitimately share a SoC/bootloader board identifier.

For `oneplus/avicii`, product `avicii` and the declared model values are strong. Board `lito` is weak. Therefore:

- `product=avicii` may resolve `oneplus/avicii`;
- `model=AC2003` may resolve `oneplus/avicii`;
- `board=lito` alone must fail closed;
- `product=avicii` plus `board=lito` may resolve `oneplus/avicii` because the strong product signal is sufficient and the weak board signal is only context.

Aliases remain compatibility/display labels. Every alias must also be declared under a typed identity signal, but the flat alias list itself does not participate in safety-sensitive resolution.

## Registry-wide audit

Per-profile validity is not enough for a multi-device catalogue. The registry audit treats all profiles as one identity namespace and verifies that:

- confirmation tokens are profile-specific and unique after normalization;
- every declared strong identity value resolves exactly one profile;
- a weak identity value never identifies a profile alone;
- weak values may be shared across profiles only while remaining non-identifying;
- canonical identity bundles still resolve to the expected profile;
- no audit step performs ADB/Fastboot I/O, chooses storage, authorizes a write or grants hardware/Beta credit.

Run it with:

```bash
python -m kaliphonestudio.profile_registry_audit --devices-root devices --json
```

The dedicated GitHub Actions workflow additionally builds the real frozen Windows CLI and reruns the registry audit through `KaliPhoneStudioCLI.exe`, preventing source-only behavior from drifting away from the packaged application.

## Requirements before adding a profile

A new profile must not be advertised as supported merely because it loads. Before destructive actions can ever be considered, the profile needs unambiguous identity, a profile-specific confirmation token, boot/partition constraints, pinned sources, recovery notes and a functional hardware test contract. The cross-profile registry audit must stay green.

Physical support is a later and separate gate. Real firmware baseline, matching stock boot image, temporary boot, rescue/log path, storage/power safety, required subsystem testing and exercised recovery/rollback are still required for the declared release scope.
