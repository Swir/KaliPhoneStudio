# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux / NetHunter Pro as the primary phone OS/userspace**, without Android as the user-facing layer.

The repository is intentionally conservative about hardware claims: a device profile, a successful host build, or green CI never means a phone is supported. Public Beta releases require the complete device gate in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress is weighted toward physical boot, hardware validation, recovery and release readiness. Host-side reproducibility, provenance and safety are mandatory foundations, but they never substitute for evidence from the exact physical phone.

> **Current development line: `0.6.47-dev`.** The reviewed Kali ARM64 rootfs and `oneplus/avicii` kernel authorities remain strict-byte-identical host-side, and the first reviewed DTB/DTBO authority is now also accepted. Real DT authority run `35196447576` reused the exact reviewed kernel Image, deterministically rehydrated its final `.config`, then completed two independent exact-source DT builds with byte-identical `lito.dtb`, raw `avicii-overlay.dtbo` and packed `dtbo.img`. Accepted DTB SHA-256 is `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`; packed DTBO SHA-256 is `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895`. All three reviewed authorities remain **host-side only**: no physical AC2003 or Beta credit is granted.

## Source of truth and architecture

`Swir/KaliPhoneStudio` is the **only** project source of truth.

The core under `kaliphonestudio/` is device-independent. Device knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile must define identity, confirmation token, boot/partition constraints, firmware hints, pinned sources, recovery notes, host tests and hardware Beta tests before destructive actions can become eligible. Adding a JSON profile is **not** hardware support.

### Active device profiles

| Device | Profile ID | Engineering state | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The first profile pins:

- device baseline: `LineageOS/android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13`
- kernel baseline: `LineageOS/android_kernel_oneplus_sm7250@fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`)
- kernel compiler: source/object-locked Android Clang `clang-r416183b`

These are engineering baselines, not hardware-working claims.

## Offline application

`python main.py` launches the PySide6 offline profile studio. It lists only schema-validated profiles and exposes no flash/write controls.

Useful commands:

```powershell
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii
python main.py --profile-id oneplus/avicii --json
```

Profile inspection is offline and explicitly reports `hardware_verified=false` and `beta_gate_credit=false`.

## Implemented host-side foundations

### Multi-device safety

- Runtime profile registry with profile/path binding and profile-driven identity.
- Verified serial bound to `profile_id`.
- Profile-specific destructive confirmation token.
- Read-only Fastboot baseline contract for identity, serial, A/B state, security state, bootloader/baseband and exact firmware build/fingerprint.
- A/B-aware planning and temporary-boot-first policy.
- Persistent testing is not eligible before exact-device authorization and is limited to a declared inactive slot policy.
- Optional profile hooks use explicitly registered in-process callbacks only; profile JSON cannot inject shell commands or module paths.
- Recovery hooks require additional authorization.

### Firmware, stock boot and boot image

- Exact OTA → `payload.bin` → stock `boot.img` provenance chain with SHA-256 evidence.
- Source-locked boot-only payload extraction tooling.
- Profile-driven deterministic `BootBuildPlan` with exact kernel/ramdisk/DTB/DTBO hashes.
- Pre-assembly TOCTOU revalidation.
- Source-locked `mkbootimg` / `unpack_bootimg` backend.
- Independent double assembly and round-trip verification.
- Fail-closed temporary-boot authorization tied to the exact device/firmware/stock provenance/build evidence.

### Kernel and toolchain

- Profile-driven exact source/version/config/build contract.
- Exact checkout evidence for source HEAD, kernel version and selected config material.
- Required `CONFIG_*` policy is applied before final `.config` verification.
- `oneplus/avicii` requires `CONFIG_RD_LZ4=y`; engineering module signing is deterministic for reproducibility-sensitive bring-up.
- Android Clang `clang-r416183b` is source/object locked, independently verified from Gitiles, and locally reverified from the fetched Git object graph before compiler byte/banner checks.
- Main compiler source/output paths are remapped to fixed virtual roots with debug/macro prefix maps and `KBUILD_ABS_SRCTREE=0`.
- The compat-vDSO32 compiler path is separately normalized through profile-bound recursive GNU make `CC` flags using `$(KBUILD_SRC)` and `$(CURDIR)`, so `CC_COMPAT ?= $(CC)` receives the same canonical source/output identities without hardcoding host paths.
- `KBUILD_BUILD_USER`, host, timestamp, version, `SOURCE_DATE_EPOCH`, locale and timezone are fixed and evidence-bound.
- Clean Git-tracked source mtimes are normalized to epoch 0 with canonical mode/blob/path evidence while `.git` and untracked files remain untouched.
- `CONFIG_IKHEADERS` remains enabled while its generated tar/xz payload is forced through deterministic sort/mtime/uid/gid/compressor policy; diagnostics compare `kernel/kheaders_data.tar.xz` directly.
- Strict reproducibility requires **two independent builds with byte-identical final `.config` and ARM64 `Image`**, plus exact executed-build provenance.
- Strict execution binding also requires the reproducibility record to match each build's exact config-verifier and Image-verifier evidence digests.
- `KernelAuthorityRecord` binds the reviewed run/commit/artifact IDs, exact plan/toolchain/recipe/environment, both build records, strict reproducibility/binding evidence and final config/Image identities. It permanently records `hardware_verified=false` and `beta_gate_credit=false`.
- A separate first-boot kernel-authority binding requires a candidate to match that exact reviewed authority before release-candidate preparation.
- Historical Actions artifacts that omitted hidden `.config` files can now be safely reused for dependent DT work: KaliPhoneStudio deterministically rehydrates only the exact final config from the pinned source/profile/toolchain policy, verifies its SHA-256/size against the reviewed kernel authority, and verifies the existing reviewed Image remains unchanged. The Image is not rebuilt in this path.

### Kernel reproducibility evidence

The acceptance criterion was **never weakened** after failures.

| Real run | Experiment | Result |
|---|---|---|
| `35166301228` | exact source/toolchain, internal `jobs=1` | strict failure; 11,293,315 differing Image bytes / 897,561 ranges |
| `35174347350` | add tracked-source mtime normalization | strict failure; 11,776,181 differing bytes / 998,609 ranges |
| `35177350001` | intermediate build-tree diagnostics | strict failure; 4,388,978 differing bytes / 229,151 ranges; only 20/4,597 selected intermediates differ |
| `35181516724` | deterministic `CONFIG_IKHEADERS` tar/xz policy | strict failure; 16 differing bytes / 2 ranges; compat-vDSO32 remained target-linked |
| `35183670399` | recursive compat-vDSO source/output prefix maps | **strict SUCCESS**; final `.config` and ARM64 `Image` are byte-identical |

The accepted run produced final `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3` (166,055 bytes) and ARM64 `Image` SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712` (43,878,416 bytes) in both independent build roots. Strict reproducibility evidence SHA-256 is `a2156ba6cc493cf7f7575a60107938f5c5455d4388ecb883cd8f01754f13f0f0`; executed-build binding SHA-256 is `dffad42df1d189170b23a95d980211e57c1f54d8f399e939b048597e79425a39`.

The reviewed authority record is `evidence/authorities/oneplus-avicii-kernel-4.19.300-2026-09-17.json`. The exact checked build-A/build-B, strict reproducibility and reproducibility-binding JSON records are preserved under `evidence/authorities/kernel/oneplus-avicii-4.19.300-2026-09-17/` and are reconstructed by focused CI. Diagnostic evidence remains available for future failures but contributes no release or hardware credit.

### DTB / DTBO

- Source-locked FDT and Android DT table format references.
- Profile-driven DT plan pins `dtbs`, `arch/arm64/boot/dts/vendor/20801/lito.dtb`, raw `avicii-overlay.dtbo`, 4096-byte DT table pages and table version 0.
- Structural DTB/DTBO verification and partition-limit checks.
- Exact source/toolchain/kernel-authority binding before any DT build.
- Two independent DT build roots are required to produce byte-identical selected DTB, raw overlay and packed `dtbo.img`.
- Real authority run `35196447576` is **strict SUCCESS**: DTB SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce` (406,620 bytes), raw overlay SHA-256 `b3991f2fda96d3675778299b45b9802823022ef25d593c5d00c756ceea35b90c` (345,405 bytes), packed DTBO SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` (352,256 bytes, one entry).
- Reviewed authority record: `evidence/authorities/oneplus-avicii-dtb-dtbo-2026-09-17.json`; the exact plan/build/reproducibility and config-rehydration evidence is preserved under `evidence/authorities/device-tree/oneplus-avicii-2026-09-17/`.
- The authority is explicitly bound to reviewed kernel authority SHA-256 `0bdc44c4625e04214981eca428872642419fb8ad3c135a96d40f25e781a7d5f2`.

This proves host-side DT reproducibility only. Physical bootloader/kernel acceptance remains unverified until an exact AC2003 candidate is temporarily booted.

## Kali ARM64 rootfs

The rootfs is also a reviewed strict reproducibility authority.

- builder: `kali-nethunter-rootfs@20238a2f2d547d7989a4dec287d4f5ef528ed701` (`2026.2`)
- repository trust: GPG-valid Kali `InRelease`, archive fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5`
- reviewed authority run: `35158577624`
- accepted canonical artifact SHA-256: `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`
- size: `137460600` bytes
- package manifest SHA-256: `11a3609a23c263c43794414b7b2f2e587133fb247c2a146321c0bdef55db3fbd`
- package count: `269`
- authority record: `evidence/authorities/kali-arm64-rootfs-2026.2-minimal.json`

The rootfs authority proves host-side reproducibility only. It does not prove boot, storage, display, radio, charging or recovery on the physical phone.

## First-boot and rescue foundations

- First-boot candidate schema v8 binds exact firmware, temporary-boot authorization, boot plan, executed/reproducible kernel/compiler provenance, DTB/DTBO and strict rootfs evidence.
- Reviewed rootfs, kernel and device-tree authorities have separate fail-closed candidate bindings.
- `FirstBootAuthorityBundleEvidence` adds a final host-side cross-binding: all three reviewed authorities must refer to the exact same schema-v8 manifest/profile, the DT authority must reference the same reviewed kernel authority, and candidate kernel/rootfs/DTB/DTBO artifact identities are rechecked before one compact provenance bundle can be emitted.
- No physical-firmware first-boot candidate exists yet because the real AC2003 Fastboot/OxygenOS baseline and matching stock boot provenance have not been captured.
- Deterministic device-independent provisioning overlay contains no credentials, keeps the root account locked and remote access disabled by default.
- Deterministic rescue initramfs supports gzip/LZ4 with source-locked static ARM64 BusyBox payload and exact boot-plan binding.
- Rescue reproducibility passes host-side; the physical rescue/log path remains unverified.

## Beta release gate

**Beta is BLOCKED.** A GitHub Beta will be created only after all required host and physical checks in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md) pass.

For the first AC2003 this includes at minimum:

- exact physical Fastboot/OxygenOS build + fingerprint capture,
- matching stock `boot.img` from the exact OTA,
- binding the reviewed kernel/rootfs/DTB/DTBO authorities to that exact physical-firmware first-boot candidate,
- successful physical temporary boot,
- usable rescue/log channel,
- Kali early userspace/rootfs proof,
- required UFS/storage validation,
- usable display/touch path or an explicit console-only release decision,
- safe charging/battery behavior for testing,
- exercised recovery/rollback procedure,
- compatibility matrix, release manifest and SHA-256 files.

No empty, symbolic or host-CI-only Beta release is acceptable.

## Testing

Primary Python CI matrix:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

Focused workflows additionally exercise source locks, kernel contracts/reproducibility/authority, DTB/DTBO reproducibility/authority, rootfs reproducibility, ramdisk formats and other provenance/safety gates.

Run locally:

```bash
python -m compileall -q kaliphonestudio scripts tests
python -m pytest -q
```

## Adding another device

A new device starts as **profile-only / unsupported hardware**.

1. Add `devices/<vendor>/<codename>/profile.json`.
2. Pin immutable upstream source commits and required format/tool references.
3. Define identity, confirmation token, boot/partition limits and recovery notes.
4. Define host and hardware test contracts.
5. Pass schema/registry/CI validation.
6. Build and verify artifacts offline.
7. Capture exact physical baseline evidence.
8. Prefer temporary boot before any persistent write.
9. Exercise rescue/recovery before release eligibility.

Adding the profile never auto-promotes support.

## Safety model

KaliPhoneStudio is built around fail-closed evidence rather than optimistic automation. It will not treat green CI, a matching model string, an upstream device tree, a generated boot image or a successful host build as proof that a physical device is safe to flash.

The first public Beta will be a tested device build, not a development snapshot.
