# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux as the primary phone OS/userspace**, without Android as the user-facing layer.

## Project progress

**52% complete**

`██████████▍░░░░░░░░░ 52%`

Progress is deliberately weighted toward **real device bring-up, hardware validation, recovery and release readiness**. Host-side CI and safety infrastructure are required, but they do not substitute for physical evidence.

> Current development line: **0.6.32-dev**. The host-side boot/provenance chain, exact-source kernel pipeline, locked Android Clang toolchain, DTB/DTBO verification, deterministic rescue path and strict Kali ARM64 rootfs reproducibility gate are implemented. The profile-required kernel config is now applied deterministically before builds, including LZ4 initramfs support for `oneplus/avicii`. Rootfs divergence diagnostics now prioritize real payload changes over timestamp noise and compare normalized installed-package manifests. **No concrete kernel/rootfs artifact or AC2003 hardware feature is accepted for Beta until its strict evidence gate passes.**

## Architecture

The Python core under `kaliphonestudio/` is device-independent. Device-specific knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile does **not** mean the phone is supported. Before destructive actions are even eligible, a profile must define unambiguous identity, confirmation token, boot/partition constraints, firmware hints, recovery notes, source locks and host/hardware test contracts.

### Active device profiles

| Device | Profile ID | Engineering state | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii board baseline is pinned to LineageOS `android_device_oneplus_avicii` commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. Its reviewed kernel bring-up baseline is pinned separately to `android_kernel_oneplus_sm7250` commit `fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`). These are engineering source references, **not hardware-working claims**.

## Implemented host-side foundations

### Multi-device safety and firmware provenance

- Runtime device-profile registry with profile-bound identity and verified serial handling.
- Profile-specific confirmation tokens for destructive actions.
- A/B slot-aware planning, dry-run defaults and guarded inactive-slot writes.
- Temporary `fastboot boot` path before persistent boot-slot testing.
- Offline `fastboot getvar all` baseline importer with exact transcript SHA-256, identity/A-B/security checks and exact firmware build/fingerprint binding.
- Exact OTA → `payload.bin` → stock `boot.img` provenance with SHA-256 and metadata evidence.
- Source-locked payload extractor with authorized reproducible Linux/Windows binaries.

### Boot image, kernel and device tree

- Android boot header-v2 inspection/repack foundation and profile-driven `BootBuildPlan`.
- Source-locked `mkbootimg`/`unpack_bootimg`, deterministic double assembly and round-trip verification.
- Exact-source kernel plan bound to profile, source commit, expected version, config material, make flags and required `CONFIG_*` states.
- Android Clang `clang-r416183b` toolchain source/object lock plus materialized compiler SHA-256/banner verification.
- Canonical per-run kernel build evidence and strict A/B reproducibility binding.
- Deterministic required-kernel-config application before build, followed by fail-closed final `.config` verification.
- `oneplus/avicii` requires `CONFIG_RD_LZ4=y`; engineering module signing is disabled in the reproducibility-sensitive build policy.
- Source-locked FDT/Android DT table format references and structural DTB/DTBO verification bound to the approved boot plan.
- First-boot candidate schema v8 binds exact firmware, boot plan, kernel execution provenance, compiler evidence, DTB/DTBO evidence and rootfs evidence without claiming hardware success.

### Kali ARM64 rootfs

- Official NetHunter rootfs builder pinned to tag `2026.2`, commit `20238a2f2d547d7989a4dec287d4f5ef528ed701`.
- HTTPS Kali mirror plus GPG-verified `InRelease` evidence pinned to archive key fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5`.
- Two independent exact-source ARM64 builds must be **byte-identical** and produce matching normalized installed-package evidence.
- Real A/B builds are bound to one verified rolling-repository start state.
- Failed strict comparisons generate non-release diagnostic evidence only; acceptance criteria are never relaxed.
- Diagnostic schema v2 prioritizes type/content/add/remove/order differences before metadata noise, counts metadata fields/mtime-only drift, records omitted difference classes and compares normalized installed-package manifests.
- The most recent reviewed failed A/B run exposed **5 content changes and 5050 metadata changes**. Therefore `rootfs_reproducible_artifact` remains **false**.

### Rescue / recovery foundations

- Deterministic `newc` rescue initramfs with gzip and Linux-compatible LZ4 legacy framing.
- Source-locked static ARM64 BusyBox payload; network/SSH disabled by default.
- Independent initramfs structural verification and exact ramdisk-to-boot-plan binding.
- Rescue payload reproducibility passed host-side CI, but the physical AC2003 rescue path is still unverified.

### CI

Primary Python test matrix:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

See [`BUILD_STATUS.json`](BUILD_STATUS.json) for the current run IDs and evidence state, and [`ROADMAP.md`](ROADMAP.md) for milestone status.

## Safety model

KaliPhoneStudio follows **temporary boot first, inactive slot second**. It does not bypass physical bootloader-unlock confirmation. Persistent writes require a supported profile, verified device identity, explicit confirmation and validated artifacts.

No Wi-Fi, Bluetooth, modem, display, touch, storage, charging, suspend, audio, camera, sensor or other hardware function is marked working without evidence from the exact physical phone/firmware baseline.

## AC2003 Beta gate

The first public Beta stays **BLOCKED** until the exact physical AC2003 provides all required evidence, including:

- real Fastboot identification and exact OxygenOS build/fingerprint;
- matching stock `boot.img` from the exact OTA;
- reviewed reproducible kernel + DTB/DTBO + rootfs candidate;
- successful physical temporary `fastboot boot`;
- usable rescue/logging path;
- kernel reaching Kali early userspace/rootfs;
- verified storage and safe charging/battery behavior;
- exercised OxygenOS recovery/rollback path;
- release compatibility matrix, manifest and SHA-256 checksums.

Passing host CI alone can never publish a Beta. See [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Development

```powershell
python -m pip install -r requirements.txt
python main.py
python -m pytest -q
```

Useful offline verification entry points include:

```powershell
python scripts/verify_kernel_toolchain_upstream.py --lock tools/kernel-toolchain-lock.json --out evidence/kernel-toolchain-source.json
python scripts/import_fastboot_baseline.py --profile-id oneplus/avicii --transcript fastboot-getvar-all.txt --firmware-build "EXACT_BUILD" --firmware-fingerprint "EXACT_FINGERPRINT" --out evidence/fastboot-baseline.json
python scripts/diagnose_rootfs_repro.py --archive-a rootfs-a.tar.xz --archive-b rootfs-b.tar.xz --out evidence/rootfs-repro-diagnostic.json
```

## Release policy

There is intentionally **no public Beta yet**. A release will only be created from verified artifacts after the complete physical-device gate passes. Stable has a higher threshold and follows later.

## Disclaimer

Unlocking bootloaders and writing phone partitions can erase data or make a device unbootable. Development builds are engineering artifacts, not daily-driver releases.
