# KaliPhoneStudio Roadmap

KaliPhoneStudio separates **device-independent studio engineering** from **per-device physical bring-up**. A host-side checkbox never implies hardware support.

## Overall project progress

**54% complete**

`██████████▊░░░░░░░░░ 54%`

The percentage is weighted toward physical boot, hardware validation, recovery and release readiness. CI and offline engineering are mandatory, but do not receive the same weight as verified device milestones.

## Current development line — 0.6.44-dev

### Completed in the current kernel/rootfs milestone

- [x] Migrate the project to the device-independent `kaliphonestudio/` package and profile registry.
- [x] Make `Swir/KaliPhoneStudio` the only project source of truth.
- [x] Keep device hardware knowledge under `devices/<vendor>/<codename>/profile.json`.
- [x] Add profile/path identity binding, confirmation tokens, A/B constraints, recovery notes and host/hardware test contracts.
- [x] Add offline GUI/CLI profile inspection with no ADB/Fastboot writes.
- [x] Add read-only Fastboot baseline evidence and exact OTA/stock-boot provenance contracts.
- [x] Add deterministic boot-plan, boot-image double-build and round-trip host verification.
- [x] Pin the avicii kernel source baseline and Android Clang `clang-r416183b` by immutable source/object identity.
- [x] Add strict two-root kernel reproducibility with executed-build provenance.
- [x] Add canonical main-kernel compiler path remapping and fixed build identity/time environment.
- [x] Add fail-closed Git-tracked source-mtime normalization.
- [x] Review kernel run `35174347350` as a strict failure after mtime normalization; no partial reproducibility credit.
- [x] Add bounded intermediate build-tree diagnostics.
- [x] Review kernel run `35177350001`: identical `.config`, equal 43,878,416-byte Images, but 4,388,978 differing Image bytes across 229,151 ranges; only 20 of 4,597 selected intermediate artifacts differ.
- [x] Identify `kernel/kheaders.o` as a concrete differing kernel-linked artifact while keeping `CONFIG_IKHEADERS` enabled.
- [x] Bind deterministic GNU tar order/mtime/uid/gid and single-threaded xz policy to the avicii kernel build plan for embedded headers.
- [x] Add bounded ARM64 ELF-section diagnostics classifying executable/debug/metadata/relocation/data divergence after strict failure.
- [x] Review and accept the first strict byte-identical Kali ARM64 rootfs authority from run `35158577624`.
- [x] Bind rootfs authority, raw A/B provenance and canonicalization evidence to first-boot candidate contracts.
- [x] Add deterministic credential-free first-boot provisioning and reproducible rescue-initramfs foundations.

### Immediate next gates

- [ ] Review real kernel authority run `35181516724`, the first retry with deterministic `CONFIG_IKHEADERS` archive policy and ELF-section diagnostics.
- [ ] If strict kernel equality still fails, confirm whether `kernel/kheaders.o` became byte-identical and use the ELF evidence to isolate the next smallest divergence source.
- [ ] Produce reviewed byte-identical final kernel `.config` + ARM64 `Image` evidence from two independent exact-source builds.
- [ ] Bind the accepted kernel authority to the exact DTB/DTBO and first-boot candidate.
- [ ] Capture the exact physical AC2003 Fastboot/OxygenOS baseline.
- [ ] Validate matching stock `boot.img` provenance from that exact OTA.
- [ ] Attempt only an authorized physical **temporary boot** first.

## Phase A — Multi-device studio core

### Device/profile architecture

- [x] Runtime profile registry.
- [x] Versioned fail-closed profile schema.
- [x] Profile/path binding and profile-driven device identity.
- [x] Verified serial bound to `profile_id`.
- [x] Profile-specific destructive confirmation token.
- [x] Typed boot/kernel contracts and A/B identifiers.
- [x] Immutable HTTPS full-commit source requirements.
- [x] Recovery notes and host/hardware test contracts.
- [x] Explicit trusted in-process profile hooks with extra recovery authorization.
- [x] Offline GUI and machine-readable CLI profile inspection.
- [ ] Add a second real device profile only when its identity/partition/source/recovery/test contracts are complete.

### Firmware baseline / stock recovery

- [x] Generic read-only Fastboot baseline contract.
- [x] Exact-transcript SHA-256 importer/parser.
- [x] Identity, serial, A/B, lock/security, bootloader and baseband validation.
- [x] Firmware build/fingerprint binding to OTA `post-build` / `post-build-incremental` provenance.
- [ ] Capture exact physical AC2003 baseline evidence.
- [ ] Capture stock recovery/restore information before persistent device experiments.

## Phase B — Boot chain, kernel and device tree

### OTA / stock boot / boot assembly

- [x] OTA ZIP inspection and `payload.bin` discovery.
- [x] Fail-closed payload envelope and checksum evidence.
- [x] Source-locked boot-only extractor.
- [x] Exact OTA → payload → stock `boot.img` provenance.
- [x] Deterministic profile-driven `BootBuildPlan`.
- [x] Source-locked `mkbootimg`/`unpack_bootimg` backend.
- [x] Independent double assembly and locked round-trip verification.
- [x] Temporary-boot authorization contract.
- [ ] Instantiate against exact physical AC2003 firmware/stock boot evidence.

### Kernel/toolchain reproducibility

- [x] Exact kernel source/version/config contract.
- [x] Exact source checkout evidence.
- [x] Final `.config` and ARM64 `Image` evidence.
- [x] Android Clang r416183b source/object/materialized-byte lock.
- [x] Independent Gitiles verification plus local fetched-object verification.
- [x] Deterministic required-config application.
- [x] LZ4 initramfs decompressor policy for avicii.
- [x] Deterministic engineering module-signing behavior.
- [x] Fixed build identity/time/locale and main compiler path remapping.
- [x] Git-tracked source-mtime normalization.
- [x] Final Image byte-range diagnostics.
- [x] Intermediate build-tree diagnostics.
- [x] ARM64 ELF section diagnostics.
- [x] Deterministic `CONFIG_IKHEADERS` archive/compressor policy.
- [ ] Accept first real byte-identical kernel A/B authority.
- [ ] Promote an exact kernel commit/patchset only after physical temporary boot evidence.

### DTB / DTBO

- [x] FDT and Android DT table format source locks.
- [x] Structural FDT/DTBO verification.
- [x] Partition-limit and exact boot-plan binding.
- [ ] Bind final kernel + DTB + DTBO into one reviewed first-boot candidate.
- [ ] Verify device-tree functionality on physical AC2003.

## Phase C — Kali userspace and rescue

### Kali ARM64 rootfs

- [x] Pin official NetHunter rootfs builder to exact `2026.2` commit.
- [x] GPG-verify Kali `InRelease` and exact ARM64 package indexes.
- [x] Build two independent rootfs outputs.
- [x] Diagnose volatile builder state without relaxing strict equality.
- [x] Canonicalize only reviewed volatile state with auditable provenance.
- [x] Pass strict byte equality and normalized installed-package equality.
- [x] Review authority run `35158577624`.
- [x] Pin authority record and exact artifact/package hashes.
- [ ] Prove the accepted rootfs reaches Kali early userspace on the physical device.

### First boot / provisioning

- [x] Schema-v8 first-boot candidate manifest.
- [x] Candidate-level rootfs raw-A/B/canonicalization provenance binding.
- [x] Candidate-level reviewed-rootfs-authority binding.
- [x] Deterministic provisioning overlay with no credentials and remote access disabled.
- [ ] Instantiate the exact candidate against physical firmware + stock boot + accepted kernel/DT evidence.

### Rescue / recovery

- [x] Deterministic `newc` rescue initramfs.
- [x] gzip and Linux-compatible LZ4 support.
- [x] Source-locked static ARM64 BusyBox payload.
- [x] Network/SSH disabled by default.
- [x] Host-side reproducibility/structure verification.
- [ ] Prove a usable physical rescue/log path.
- [ ] Exercise rollback/recovery on the exact physical baseline.

## Phase D — Physical AC2003 bring-up

Nothing in this phase may be checked from host-only CI.

- [ ] Exact model/profile and serial recognized on the physical phone.
- [ ] Exact OxygenOS build/fingerprint captured.
- [ ] Matching stock `boot.img` verified.
- [ ] Temporary boot succeeds.
- [ ] Rescue/log channel works after candidate boot.
- [ ] Kernel reaches Kali early userspace/rootfs.
- [ ] UFS/storage path required for release is verified.
- [ ] Display and touchscreen are usable for setup, or release is explicitly console-only.
- [ ] USB rescue behavior verified.
- [ ] Wi-Fi verified.
- [ ] Bluetooth verified.
- [ ] Modem/cellular behavior documented and verified to the intended Beta scope.
- [ ] Audio verified to the intended Beta scope.
- [ ] Charging/battery behavior is safe enough for testing.
- [ ] Suspend/resume/power behavior documented.
- [ ] Recovery and A/B rollback exercised.

## Phase E — Beta release

A first GitHub Beta is allowed only when [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md) is fully satisfied for its declared compatibility scope.

- [ ] CI green for exact release commit.
- [ ] Exact device/firmware compatibility matrix.
- [ ] Reviewed strict kernel/rootfs/DT evidence bound to the candidate.
- [ ] Required physical-device evidence complete.
- [ ] Installation instructions.
- [ ] Recovery/restore instructions.
- [ ] Known-issues and hardware matrix.
- [ ] Release manifest and SHA-256 files.
- [ ] Real binaries/images attached; no empty or symbolic release.

## Stable release

Stable is intentionally outside the first Beta gate. It requires a later, higher hardware-completeness threshold, repeated regression testing, recovery confidence and a reviewed long-term update/signing strategy.
