# KaliPhoneStudio Roadmap

KaliPhoneStudio separates **device-independent studio engineering** from **per-device physical bring-up**. A host-side checkbox never implies hardware support.

## Overall project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

The percentage is weighted toward physical boot, hardware validation, recovery and release readiness. CI and offline engineering are mandatory foundations, but do not receive the same weight as verified device milestones.

## Current development line — 0.6.47-dev

### Completed in the current kernel/rootfs/DT authority milestone

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
- [x] Review kernel run `35181516724`: deterministic IKHEADERS reduces final divergence to only 16 bytes across 2 ranges and 14/4,597 selected artifacts while final `.config` remains identical.
- [x] Confirm that `kernel/kheaders.o`, `System.map`, kallsyms objects and earlier archive drift disappear after deterministic IKHEADERS policy.
- [x] Narrow the remaining target-linked divergence to four ARM32 compat-vDSO objects (`note.o`, `sigreturn.o`, `vdso.o`, `vgettimeofday.o`).
- [x] Add recursive source/output prefix maps to the profile-bound `CC` path consumed by pinned `CC_COMPAT ?= $(CC)` in the compat-vDSO Makefile.
- [x] Extend ELF diagnostics to ARM ELF32 compat-vDSO objects while excluding unrelated `scripts/*` host-tool objects.
- [x] Compare generated `kernel/kheaders_data.tar.xz` directly in build-tree diagnostics.
- [x] Complete real kernel A/B run `35183670399` with strict byte-identical final `.config` and ARM64 `Image` outputs from two independent exact-source builds.
- [x] Verify accepted kernel `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3` and Image SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712` (43,878,416 bytes).
- [x] Close the executed-build provenance gap by requiring strict reproducibility evidence to match each build's exact config/Image verifier evidence digests.
- [x] Add and populate a fail-closed reviewed `KernelAuthorityRecord` for run `35183670399`, main commit `e600a5de13fa91085464c7ce2d4a6327f39b96e8` and artifact `10482645697`.
- [x] Preserve exact build-A/build-B, strict reproducibility and execution-binding records under `evidence/authorities/kernel/oneplus-avicii-4.19.300-2026-09-17/` for independent reconstruction in CI.
- [x] Add candidate-level binding from a schema-v8 first-boot manifest to the exact reviewed kernel authority.
- [x] Review and accept the first strict byte-identical Kali ARM64 rootfs authority from run `35158577624`.
- [x] Bind rootfs authority, raw A/B provenance and canonicalization evidence to first-boot candidate contracts.
- [x] Add deterministic credential-free first-boot provisioning and reproducible rescue-initramfs foundations.
- [x] Add a profile-driven DT build plan tied to the exact reviewed kernel authority, source/toolchain locks and selected avicii DTB/DTBO outputs.
- [x] Repair historical reviewed-kernel artifact reuse without rebuilding `Image`: if Actions omitted hidden `.config`, deterministically rehydrate only the exact final config and verify both config and existing Image against the immutable kernel authority.
- [x] Complete real DTB/DTBO A/B run `35196447576` with strict byte-identical `lito.dtb`, raw `avicii-overlay.dtbo` and packed `dtbo.img` from two independent exact-source roots.
- [x] Accept DTB SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce` (406,620 bytes), raw overlay SHA-256 `b3991f2fda96d3675778299b45b9802823022ef25d593c5d00c756ceea35b90c` (345,405 bytes) and packed DTBO SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` (352,256 bytes, one entry).
- [x] Add and populate a reviewed `DeviceTreeAuthorityRecord` for run `35196447576`, main commit `50a10688a20e3189b97291426118e7d0c466e108` and artifact `10486420567`, retaining `hardware_verified=false` and `beta_gate_credit=false`.
- [x] Preserve exact DT plan/build-A/build-B/reproducibility, source-normalization, config-rehydration and toolchain evidence under `evidence/authorities/device-tree/oneplus-avicii-2026-09-17/`.
- [x] Add candidate-level reviewed DT authority binding and a unified first-boot authority bundle that requires kernel/rootfs/DT authority bindings to reference the same schema-v8 manifest/profile and the DT authority to reference the same reviewed kernel authority.

### Immediate next gates

- [ ] Capture the exact physical AC2003 Fastboot/OxygenOS baseline.
- [ ] Validate matching stock `boot.img` provenance from that exact OTA.
- [ ] Instantiate one schema-v8 first-boot candidate against the physical firmware/stock boot baseline and reviewed kernel/rootfs/DT authorities.
- [ ] Emit and verify the unified first-boot authority bundle for that exact candidate.
- [ ] Assemble the exact temporary-boot candidate and rescue/log path without performing a persistent write.
- [ ] Attempt only an explicitly authorized physical **temporary boot** first.

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
- [x] ARM64 + ARM32 target ELF section diagnostics.
- [x] Deterministic `CONFIG_IKHEADERS` archive/compressor policy.
- [x] Compat-vDSO recursive source/output prefix-map policy bound to the profile build recipe.
- [x] Strict build-run verifier-evidence provenance binding.
- [x] Reviewed kernel-authority schema and candidate-authority binding contract.
- [x] Accept first real byte-identical kernel A/B authority from run `35183670399`.
- [ ] Promote an exact kernel commit/patchset as hardware-working only after physical temporary boot evidence.

### DTB / DTBO

- [x] FDT and Android DT table format source locks.
- [x] Structural FDT/DTBO verification.
- [x] Partition-limit and exact boot-plan binding.
- [x] Profile-driven exact DT build plan bound to source, toolchain and reviewed kernel authority.
- [x] Strict two-root DTB/raw-DTBO/packed-DTBO reproducibility contract.
- [x] Accept real strict DT authority run `35196447576` and preserve its exact evidence chain in-repo.
- [x] Add reviewed DT authority schema and candidate-level binding contract.
- [x] Add unified candidate authority bundle across reviewed kernel/rootfs/DT provenance.
- [ ] Bind the reviewed DT authority to one exact physical-firmware first-boot candidate.
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
- [x] Candidate-level reviewed-kernel-authority binding contract.
- [x] Candidate-level reviewed-device-tree-authority binding contract.
- [x] Unified fail-closed candidate authority bundle across reviewed kernel/rootfs/DT authorities.
- [x] Deterministic provisioning overlay with no credentials and remote access disabled.
- [ ] Instantiate the exact candidate against physical firmware + stock boot + reviewed kernel/rootfs/DT evidence.

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
- [ ] Reviewed strict kernel/rootfs/DT evidence instantiated and bound to the exact physical-firmware candidate.
- [ ] Required physical-device evidence complete.
- [ ] Installation instructions.
- [ ] Recovery/restore instructions.
- [ ] Known-issues and hardware matrix.
- [ ] Release manifest and SHA-256 files.
- [ ] Real binaries/images attached; no empty or symbolic release.

## Stable release

Stable is intentionally outside the first Beta gate. It requires a later, higher hardware-completeness threshold, repeated regression testing, recovery confidence and a reviewed long-term update/signing strategy.
