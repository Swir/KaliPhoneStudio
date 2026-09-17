# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux / NetHunter Pro as the primary phone OS/userspace**, without Android as the user-facing layer.

The project is deliberately conservative about hardware claims. A device profile, successful host build, reproducible artifact, or green CI does **not** mean a phone is supported. Public Beta releases require the complete host and physical-device gate in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress is weighted toward physical boot, hardware validation, recovery and release readiness. Host-side reproducibility, provenance and safety are mandatory foundations, but they never substitute for evidence from the exact physical phone.

> **Current development line: `0.6.49-dev`.** The reviewed Kali ARM64 rootfs, `oneplus/avicii` kernel, and avicii DTB/DTBO authorities remain strict-byte-identical host-side. 0.6.48 added the exact physical-candidate preflight gate. 0.6.49 adds the next host-only boundary: a path-independent temporary-boot offer that rehashes the exact reviewed Fastboot executable and exact candidate `boot.img`, binds them back to the read-only capture and physical-candidate gate, and produces only one serial-bound `fastboot -s SERIAL boot IMAGE` argv. It never invokes Fastboot. A separate explicit profile confirmation can authorize the offer in memory, but that authorization still records `temporary_boot_executed=false` and grants no hardware/Beta credit.

## Source of truth and architecture

`Swir/KaliPhoneStudio` is the **only** project source of truth. The core under `kaliphonestudio/` is device-independent. Device-specific knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile must define identity, confirmation token, boot/partition constraints, firmware hints, immutable upstream sources, recovery notes, host tests and hardware Beta tests before destructive actions can become eligible. Adding a profile JSON is never an automatic hardware-support claim.

### Active device profiles

| Device | Profile ID | Engineering state | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The first profile pins `LineageOS/android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13`, kernel `LineageOS/android_kernel_oneplus_sm7250@fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`) and source/object-locked Android Clang `clang-r416183b`. These are engineering baselines, not hardware-working claims.

## Current reviewed host authorities

| Layer | Reviewed run | Accepted identity | Hardware/Beta credit |
|---|---:|---|---|
| Kali ARM64 rootfs | `35158577624` | SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, 137,460,600 bytes, 269 packages | **No** |
| ARM64 kernel | `35183670399` | `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3`; `Image` SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`, 43,878,416 bytes | **No** |
| DTB / DTBO | `35196447576` | `lito.dtb` SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`; packed `dtbo.img` SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` | **No** |

The reviewed authority records are checked into `evidence/authorities/` and are independently reconstructed by CI. `BUILD_STATUS.json` retains the exact authority run/commit/artifact identities and CI now verifies them against the immutable records.

## Implemented safety and provenance chain

### Multi-device core

- Runtime profile registry with profile/path binding and profile-driven identity.
- Verified serial tied to `profile_id` and profile-specific confirmation token.
- A/B-aware planning and temporary-boot-first policy.
- Offline GUI/CLI profile inspection with no flash/write controls.
- Optional profile hooks resolved only through an explicit trusted in-process registry; profile JSON cannot inject shell commands or module paths.
- Recovery hooks require additional authorization.

### Physical baseline and stock provenance

- Read-only Fastboot capture using a reviewed Fastboot tool policy and exact executable identity.
- Capture bundle joins exact Fastboot executable evidence, raw `getvar all` transcript and parsed baseline.
- Exact OTA → `payload.bin` → stock `boot.img` provenance with SHA-256 and firmware metadata evidence.
- `PhysicalBaselineBundleEvidence` joins the read-only capture to the matching exact OTA/payload/stock boot chain and remains `temporary_boot_authorized=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- OTA metadata parsing is strict UTF-8, bounded, duplicate-aware, path-safe and TOCTOU-hardened.

### Boot chain

- Profile-driven deterministic `BootBuildPlan` with exact stock provenance plus SHA-256-bound kernel/ramdisk/DTB/DTBO inputs.
- Source-locked `mkbootimg`/`unpack_bootimg` backend.
- Independent double assembly and locked round-trip verification.
- `TemporaryBootAuthorization` binds exact verified device, baseline, stock provenance, plan, reproducible assembly, round-trip evidence and final boot image. Creating authorization does **not** execute Fastboot.

### Kernel and device tree

- Exact source/version/config/toolchain contracts with immutable source commits and Android Clang `clang-r416183b` source/object/materialized-byte verification.
- Fixed build identity/time/locale, canonical compiler path remapping, deterministic `CONFIG_IKHEADERS`, tracked-source mtime normalization and compat-vDSO path normalization.
- Strict kernel acceptance requires independent byte-identical `.config` and ARM64 `Image` plus executed-build provenance.
- DT build plan is bound to reviewed kernel authority and requires independent byte-identical selected DTB, raw overlay and packed DTBO outputs.
- Historical kernel artifacts that omitted hidden `.config` can rehydrate only exact authority-matching config; the reviewed `Image` is never rebuilt by that recovery path.

### Kali rootfs, first boot and rescue

- Kali NetHunter ARM64 rootfs builder pinned to exact `2026.2` commit and repository snapshot verified with Kali archive signing key fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5`.
- Strict independent rootfs double-build authority with reviewed canonicalization provenance.
- Schema-v8 first-boot manifest binds firmware, boot authorization/plan/image, exact kernel execution/compiler provenance, DTB/DTBO and rootfs evidence.
- Separate reviewed kernel/rootfs/device-tree candidate bindings and one unified `FirstBootAuthorityBundleEvidence` require all three authorities to refer to the same exact schema-v8 manifest.
- Deterministic credential-free provisioning overlay keeps root locked and remote access disabled by default.
- Deterministic source-locked rescue initramfs foundation is host-reproducible; physical rescue/log behavior is still unverified.

### Physical candidate preflight — 0.6.48

`PhysicalCandidateGateEvidence` is the final artifact-level cross-binding before a temporary-boot action may even be offered. It requires selected profile/boot layout, physical Fastboot/stock-provenance bundle, schema-v8 candidate, unified reviewed authorities, schema-v2 temporary-boot authorization and exact boot plan to agree. It fail-closes on detached evidence, serial/firmware/stock/authority/kernel/DT drift, unsafe paths or host evidence that claims physical success.

A valid record explicitly remains host-only:

```text
ready_for_temporary_boot_offer=true
temporary_boot_executed=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
```

### Temporary-boot offer — 0.6.49

`TemporaryBootOfferEvidence` closes the last host-local file-identity gap without performing the boot. Preparation requires:

- exact physical-candidate gate and exact read-only Fastboot capture bundle,
- the exact reviewed `FastbootToolEvidence` originally used by that capture,
- byte-for-byte rehash of the concrete Fastboot executable currently selected for use,
- byte-for-byte rehash of the concrete candidate `boot.img`, with exact gate SHA-256/size and profile boot-partition limit,
- exact profile/serial identity and profile-specific confirmation policy.

The only generated command plan is an argv tuple equivalent to:

```text
<verified-fastboot> -s <verified-serial> boot <verified-candidate-boot.img>
```

No shell string is generated and no subprocess is invoked. The CLI only writes immutable offer evidence and prints an argv preview marked **NOT EXECUTED**. `authorize_temporary_boot_offer()` requires the exact profile confirmation token but still only emits authorization evidence with `temporary_boot_executed=false`, `persistent_write=false`, `phone_storage_written=false`, `hardware_verified=false` and `beta_gate_credit=false`.

## Offline application

```powershell
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii
python main.py --profile-id oneplus/avicii --json
```

Profile inspection is offline and always distinguishes profile availability from hardware support.

## Beta release gate

**Beta is BLOCKED.** The first AC2003 Beta still requires a real physical Fastboot/OxygenOS baseline, matching stock `boot.img`, exact physical-firmware candidate + reviewed bindings + physical candidate gate + local temporary-boot offer, explicitly confirmed physical temporary boot, rescue/log proof, Kali early userspace/rootfs, UFS/storage, display/touch or declared console-only scope, safe charging/battery, exercised recovery/rollback, and a compatibility/release manifest with SHA-256 files.

No empty, symbolic, or host-CI-only Beta release is acceptable.

## Testing

Primary CI matrix: Python 3.11, 3.12, 3.13 and 3.14.

```bash
python -m compileall -q kaliphonestudio scripts tests
python -m pytest -q
```

## Adding another device

A new device starts as **profile-only / unsupported hardware**. Add `devices/<vendor>/<codename>/profile.json`, pin immutable upstream sources, define identity/confirmation/boot/partition/recovery/test contracts, pass schema and CI validation, build and verify artifacts offline, capture exact physical baseline, and prefer temporary boot before any persistent write.

## Safety model

KaliPhoneStudio is built around fail-closed evidence rather than optimistic automation. Green CI, matching model strings, upstream device trees and reproducible host artifacts are necessary engineering evidence, not proof that a physical device is safe to flash. The first public Beta will be a tested device build, not a development snapshot.
