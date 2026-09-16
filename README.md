# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux / NetHunter Pro as the primary phone OS/userspace**, without Android as the user-facing layer.

## Project progress

**52% complete**

`██████████▍░░░░░░░░░ 52%`

Progress is deliberately weighted toward **real device bring-up, hardware validation, recovery and release readiness**. Host-side CI, reproducibility and safety infrastructure are mandatory foundations, but they never substitute for evidence from the exact physical phone.

> Current development line: **0.6.38-dev**. Candidate-level rootfs provenance is now attached to the exact schema-v8 first-boot manifest, and a generic deterministic first-boot provisioning foundation is implemented for an accepted ARM64 rootfs. The provisioning bundle contains only non-secret hostname/locale/timezone and remote-service policy, requires interactive local user setup, keeps the root password locked and disables Dropbear/OpenSSH services by default. A fresh real kernel A/B authority run is exercising fixed build identity/path remapping plus bounded divergence diagnostics, while the real Kali ARM64 rootfs A/B authority run remains in progress. **No concrete kernel/rootfs artifact, provisioning bundle or AC2003 hardware feature receives Beta credit until strict artifact evidence and the physical gate pass.**

## Source of truth and architecture

`Swir/KaliPhoneStudio` is the only project source of truth. The Python core under `kaliphonestudio/` is device-independent. Device-specific knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile does **not** mean a phone is hardware-supported. A profile must define identity, confirmation token, boot/partition constraints, firmware hints, recovery notes, pinned sources and host/hardware test contracts before destructive actions can even become eligible.

Optional profile hooks are also profile-driven. Profile JSON may declare stable hook IDs for `build`, `verify` and `recovery`, but it cannot inject shell commands or Python module paths. Trusted callbacks must be registered explicitly by host code; recovery hooks additionally require explicit runtime authorization. Hook evidence always has `hardware_verified=false` and `beta_gate_credit=false`.

### Active device profiles

| Device | Profile ID | Engineering state | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii board baseline is pinned to LineageOS `android_device_oneplus_avicii` commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. Its reviewed kernel bring-up baseline is pinned to `android_kernel_oneplus_sm7250` commit `fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`). These are engineering references, not hardware-working claims.

## Offline application

`python main.py` launches the PySide6 offline profile studio. The selector only loads profiles that pass the runtime schema/identity/path contract and shows pinned sources, boot/kernel policy, host tests, hardware Beta tests and recovery notes.

The application deliberately does **not** call `adb` or `fastboot` and does not expose destructive actions. It is safe to use before a phone is connected.

Useful machine-readable/offline commands:

```powershell
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii
python main.py --profile-id oneplus/avicii --json
```

Profile JSON inspection explicitly reports `hardware_verified=false` and `beta_gate_credit=false`.

## Implemented host-side foundations

### Multi-device safety and firmware provenance

- Runtime profile registry with profile/path binding and profile-based device identity.
- Verified serial bound to `profile_id`.
- Profile-specific destructive confirmation token.
- Optional schema-validated host hook IDs for `build`, `verify` and `recovery`, resolved only through an explicit trusted in-process registry.
- Hook execution fails closed on unknown IDs, stage mismatch, callback exceptions, malformed/negative results or missing recovery authorization; there is no shell expansion or automatic module loading from profile data.
- A/B slot-aware planning, dry-run defaults and guarded inactive-slot writes.
- Temporary `fastboot boot` path before persistent boot-slot testing.
- Offline `fastboot getvar all` baseline importer with exact transcript SHA-256, identity/A-B/security checks and exact firmware build/fingerprint binding.
- Exact OTA → `payload.bin` → stock `boot.img` provenance with SHA-256/metadata evidence.
- Source-locked payload extractor with authorized reproducible Linux/Windows binaries.

### Boot image, kernel and device tree

- Profile-driven `BootBuildPlan` with exact stock provenance and SHA-256-bound kernel/ramdisk/DTB/DTBO inputs.
- Source-locked `mkbootimg`/`unpack_bootimg`, deterministic double assembly and round-trip verification.
- Exact-source kernel plan bound to profile, source commit, expected version, config material, make flags and required `CONFIG_*` states.
- Android Clang `clang-r416183b` source/object lock plus materialized compiler SHA-256/banner verification.
- Exact executed A/B kernel build records bound to strict reproducibility evidence.
- Deterministic required-kernel-config application before build and fail-closed final `.config` verification.
- `oneplus/avicii` requires `CONFIG_RD_LZ4=y`; engineering module signing is disabled in the reproducibility-sensitive bring-up policy.
- Independent kernel source/output roots are mapped to fixed virtual roots with `-fdebug-prefix-map`, `-fmacro-prefix-map` and `KBUILD_ABS_SRCTREE=0`; build user/host/timestamp/version and `SOURCE_DATE_EPOCH` are fixed and evidence-bound.
- Source-locked FDT/Android DT table references and structural DTB/DTBO verification bound to the approved boot plan.
- First-boot candidate schema v8 binds exact firmware, boot plan, kernel execution/compiler provenance, DTB/DTBO and rootfs evidence without claiming hardware success.

Real kernel authority run `35157574186` was a **strict failure**, not a partial pass. Both exact-source builds finished with identical final `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3` and identical Image size `43878416`, but Image A SHA-256 `b1af9baccb4ddbcbfff4b82e433c2c87e70c660d2b3d4770a5d5954c05ac6fab` differed from Image B SHA-256 `e0e434f3ed7c063121913dcb160aec3b6ec193261cfe3cb90824d4958b08db23`. Kernel reproducibility therefore remains false. Fresh authority run `35161227840` is exercising the fixed reproducibility environment; if strict equality still fails, schema-v1 diagnostics record exact differing byte counts, contiguous ranges and first/last offsets without relaxing acceptance.

### Kali ARM64 rootfs

- Official NetHunter rootfs builder pinned to tag `2026.2`, commit `20238a2f2d547d7989a4dec287d4f5ef528ed701`.
- HTTPS Kali mirror plus GPG-verified `InRelease` evidence pinned to archive key fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5`.
- Two independent ARM64 builds must be **byte-identical** and produce matching normalized installed-package evidence.
- Real A/B builds share one verified rolling-repository start boundary.
- Failed strict comparisons emit non-release diagnostic evidence only; the acceptance rule is never relaxed.
- Diagnostic schema v2 prioritizes content/type/add/remove/order before metadata and compares normalized package manifests.
- A reviewed deterministic canonicalization stage removes only the volatile state proven by prior real A/B diagnostics before strict comparison.
- Canonicalization provenance is bound end-to-end: both A/B audit records and raw-input hashes are tied to the exact signed repository snapshot, source lock and strict accepted canonical artifact.
- Candidate-level schema-v1 rootfs provenance evidence additionally binds the exact first-boot manifest digest to that canonicalization binding/policy, both transformation-evidence digests and both raw input hashes/sizes; all of it remains `beta_gate_credit=false` and `hardware_verified=false`.
- `rootfs_reproducible_artifact` remains **false** until the current real post-fix A/B run `35158577624` passes strict equality and evidence review.

### Generic first-boot provisioning

- `FirstBootProvisioningPlan` accepts only typed **reproducible ARM64 rootfs evidence** and binds the plan to that exact evidence digest.
- The deterministic USTAR overlay contains only `hostname`, locale, timezone, a systemd preset disabling `dropbear.service`, `ssh.service` and `sshd.service`, plus its canonical provisioning manifest.
- Root account policy remains locked; no password, password hash, private key or remote-access credential is accepted or embedded. Local user setup remains explicitly interactive.
- All bundle members are regular files with canonical uid/gid, owner/group, mode, order and zero mtime. The bundle is re-opened and independently verified against its exact SHA-256/size/evidence before acceptance.
- `scripts/build_first_boot_provisioning.py` exposes the flow as an offline CLI and prints machine-readable safety evidence with `credentials_embedded=false`, `remote_access_enabled=false`, `hardware_verified=false` and `beta_gate_credit=false`.
- This is a host-side common-userspace foundation only. It does not prove that systemd, locale, timezone, login or any UI path works on the physical AC2003.

### Rescue / recovery foundations

- Deterministic `newc` rescue initramfs with gzip and Linux-compatible LZ4 legacy framing.
- Source-locked static ARM64 BusyBox payload; network/SSH disabled by default.
- Independent initramfs structural verification and exact ramdisk-to-boot-plan binding.
- Rescue payload reproducibility passed host-side CI, but the physical AC2003 rescue path remains unverified.

### CI

Primary Python matrix:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

Application/profile tests run in the minimal CI environment without installing Qt; the GUI dependency is lazy-loaded only when the GUI is launched. Expensive real kernel/rootfs jobs remain independent artifact-authority checks.

See [`BUILD_STATUS.json`](BUILD_STATUS.json) for current authority run IDs and [`ROADMAP.md`](ROADMAP.md) for milestone status.

## Safety model

KaliPhoneStudio follows **temporary boot first, inactive slot second**. It does not bypass physical bootloader-unlock confirmation. Persistent writes require a declared profile, verified device identity, explicit confirmation and validated artifacts.

No Wi-Fi, Bluetooth, modem, display, touch, storage, charging, suspend, audio, camera, sensor or other hardware function is marked working without evidence from the exact physical phone/firmware baseline.

## AC2003 Beta gate

The first public Beta remains **BLOCKED** until the exact physical AC2003 provides all required evidence, including:

- real Fastboot identification and exact OxygenOS build/fingerprint;
- matching stock `boot.img` from the exact OTA;
- reviewed reproducible kernel + DTB/DTBO + rootfs candidate, including candidate-level rootfs canonicalization provenance binding;
- successful physical temporary `fastboot boot`;
- usable rescue/logging path;
- kernel reaching Kali early userspace/rootfs;
- verified UFS/storage and safe charging/battery behavior;
- exercised OxygenOS recovery/rollback path;
- release compatibility matrix, manifest and SHA-256 checksums.

Passing host CI or generating a provisioning overlay alone can never publish a Beta. See [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Development

```powershell
python -m pip install -r requirements.txt
python main.py
python -m pytest -q
```

Selected offline engineering entry points:

```powershell
python scripts/verify_kernel_toolchain_upstream.py --lock tools/kernel-toolchain-lock.json --out evidence/kernel-toolchain-source.json
python scripts/diagnose_kernel_image_repro.py --image-a build-a/arch/arm64/boot/Image --image-b build-b/arch/arm64/boot/Image --out evidence/kernel-image-divergence.json
python scripts/import_fastboot_baseline.py --profile-id oneplus/avicii --transcript fastboot-getvar-all.txt --firmware-build "EXACT_BUILD" --firmware-fingerprint "EXACT_FINGERPRINT" --out evidence/fastboot-baseline.json
python scripts/diagnose_rootfs_repro.py --archive-a rootfs-a.tar.xz --archive-b rootfs-b.tar.xz --out evidence/rootfs-repro-diagnostic.json
python scripts/build_first_boot_provisioning.py --rootfs-evidence evidence/rootfs-repro.json --out build/firstboot-provisioning.tar --evidence evidence/firstboot-provisioning.json --hostname kali-phone --locale pl_PL.UTF-8 --timezone Europe/Oslo
```

## Release policy

There is intentionally **no public Beta yet**. A release will only be created from verified artifacts after the complete physical-device gate passes. Stable has a later, higher threshold.

## Disclaimer

Unlocking bootloaders and writing phone partitions can erase data or make a device unbootable. Development builds are engineering artifacts, not daily-driver releases.
