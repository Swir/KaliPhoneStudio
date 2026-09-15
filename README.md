# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux as the primary phone operating system/userspace**, without Android as the user-facing OS layer.

> Current status: **0.6.6-dev** — fail-closed A/B OTA payload inspection with SHA-256 integrity evidence. The first active target is **OnePlus Nord AC2003 (`oneplus/avicii`)**. No public Beta is allowed until the physical device passes `BETA_RELEASE_GATE.md`.

## Architecture

The Python core under `kaliphonestudio/` is device-independent. Hardware knowledge belongs in `devices/<vendor>/<codename>/profile.json` and target documentation/build modules. Adding a JSON profile does **not** mean hardware support exists.

A schema-v1 profile must provide unambiguous identity, a destructive-action confirmation token, boot/partition constraints, firmware hints, full-commit upstream source locks, recovery notes, and explicit host/hardware test contracts. The registry fails closed when these fields are missing or malformed.

## Active device profiles

| Device | Profile ID | Status | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii engineering baseline is pinned to LineageOS `android_device_oneplus_avicii` commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. This is a source reference, **not** proof that Kali hardware functions work.

## Implemented host-side foundations

- Runtime device-profile registry and profile-based ADB/Fastboot identity.
- Verified serial binding to `profile_id`.
- Profile-specific confirmation for destructive actions.
- A/B slot-aware planning, dry-run defaults and guarded inactive-slot writes.
- Temporary `fastboot boot` workflow before persistent boot-slot testing.
- Manifest/SHA-256 and partition-size validation.
- Android boot image v2 inspection/repack foundation.
- Safe OTA ZIP inspection, payload discovery and firmware metadata checks.
- Fail-closed `payload.bin` envelope inspection: `CrAU` magic, payload version, manifest/signature sizes and metadata boundary checks before extraction.
- Streaming SHA-256 evidence for both the complete payload and validated metadata envelope, binding later extraction work to exact inspected bytes.
- Kali ARM64 rootfs / Phosh and rescue-initramfs foundations.
- Diagnostics and recovery-oriented boot-session evidence.
- CI on Python **3.11, 3.12, 3.13 and 3.14**.

The OTA pipeline currently stops before partition extraction. A future extractor backend must be pinned and checksum-verifiable before its output can enter the stock `boot.img` preflight path.

## Safety model

KaliPhoneStudio prefers **temporary boot first** and **inactive slot second**. It does not bypass physical bootloader-unlock confirmation. Persistent writes require an identified supported profile, verified identity, explicit confirmation and validated artifacts. No hardware feature is marked working without evidence from that exact phone/firmware baseline.

## AC2003 Beta blockers

Before the first Beta, the exact physical AC2003 must provide its OxygenOS build/fingerprint and Fastboot evidence; a matching stock `boot.img` must be obtained and validated; the candidate must successfully temporary-boot; rescue/logging must work; the kernel must reach Kali early userspace; required storage and charging/battery behavior must be safe; and recovery must be exercised and documented. Release artifacts additionally require a compatibility matrix, manifest and SHA-256 checksums.

## Development

```powershell
python -m pip install -r requirements.txt
python main.py
python -m pytest -q
```

See `ROADMAP.md`, `BUILD_STATUS.json`, `CHANGELOG.md` and `BETA_RELEASE_GATE.md` for the source-of-truth development state.

## Disclaimer

Unlocking bootloaders and writing phone partitions can erase data or make a device unbootable. Development builds are engineering artifacts, not daily-driver releases.
