# KaliPhoneStudio Roadmap

KaliPhoneStudio separates **device-independent studio engineering** from **per-device physical bring-up**. Host-side success never implies hardware support.

## Overall project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

The percentage is weighted toward physical boot, hardware validation, recovery and release readiness. CI and offline engineering are mandatory foundations, but do not receive the same weight as verified device milestones.

## Current development line — 0.6.48-dev

### Completed host-side foundations

- [x] Make `Swir/KaliPhoneStudio` the only project source of truth.
- [x] Device-independent `kaliphonestudio/` core with profile registry under `devices/<vendor>/<codename>/profile.json`.
- [x] Profile/path identity binding, confirmation token, A/B constraints, recovery notes and host/hardware test contracts.
- [x] Offline GUI/CLI profile inspection with no device writes.
- [x] Read-only Fastboot baseline capture and exact transcript evidence.
- [x] Source-locked Fastboot executable/tool-policy verification and immutable capture bundle.
- [x] Exact OTA → payload → stock `boot.img` provenance and physical-baseline/stock-provenance bundle.
- [x] Deterministic boot plan, source-locked boot assembly, independent double assembly and locked round-trip verification.
- [x] Exact kernel source/toolchain/config contract and strict two-root reproducibility.
- [x] Review kernel authority run `35183670399` as strict byte-identical success.
- [x] Preserve reviewed kernel authority and exact A/B execution/reproducibility evidence in-repo.
- [x] Review rootfs authority run `35158577624` as strict byte-identical success.
- [x] Preserve rootfs raw A/B, canonicalization, package and signed-repository provenance.
- [x] Complete strict DTB/DTBO authority run `35196447576` and preserve exact DT evidence in-repo.
- [x] Add candidate-level reviewed kernel, rootfs and device-tree authority bindings.
- [x] Add unified first-boot authority bundle requiring all reviewed authorities to bind to the same schema-v8 manifest/profile.
- [x] Add deterministic credential-free provisioning and reproducible rescue-initramfs foundations.
- [x] Add `PhysicalCandidateGateEvidence`: fail-closed cross-binding of one physical-baseline bundle, one schema-v8 first-boot manifest, one unified reviewed authority bundle, one temporary-boot authorization and one exact boot plan.
- [x] Keep the physical-candidate gate device-independent and profile-driven; it validates profile boot layout/input presence instead of hardcoding AC2003 rules in the core.
- [x] Add immutable CLI output for the physical-candidate gate; the CLI performs no ADB/Fastboot command and records `temporary_boot_executed=false`, `phone_storage_written=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- [x] Add negative tests for serial/firmware/provenance/authority/boot-image/kernel/layout drift plus immutable-writer and no-hardware-claim enforcement.

### Immediate next gates

- [ ] Capture the exact physical AC2003 Fastboot/OxygenOS baseline using the reviewed read-only capture path.
- [ ] Validate matching stock `boot.img` provenance from that exact OTA.
- [ ] Assemble the exact candidate from reviewed kernel/rootfs/DT authorities plus candidate provisioning/rescue inputs.
- [ ] Instantiate schema-v8 candidate + reviewed authority bindings + physical-candidate preflight gate for that exact firmware/device serial.
- [ ] Review the generated preflight evidence; do not execute a device action automatically.
- [ ] Attempt only an explicitly authorized physical **temporary boot** first.

## Phase A — Multi-device studio core

### Device/profile architecture

- [x] Runtime profile registry and versioned fail-closed schema.
- [x] Profile/path identity binding and profile-driven device detection.
- [x] Verified serial bound to `profile_id`.
- [x] Profile-specific destructive confirmation token.
- [x] Typed boot/kernel/A-B/recovery/test contracts.
- [x] Immutable HTTPS full-commit source requirements.
- [x] Explicit trusted in-process profile hooks; no shell/module injection from JSON.
- [x] Offline GUI and machine-readable CLI profile inspection.
- [ ] Add a second real device profile only when identity/partition/source/recovery/test contracts are complete.

### Firmware baseline / stock recovery

- [x] Generic read-only Fastboot baseline contract and exact transcript importer.
- [x] Exact Fastboot tool identity and capture-bundle contract.
- [x] Exact OTA/stock provenance binding and physical-baseline bundle.
- [ ] Capture exact physical AC2003 baseline evidence.
- [ ] Capture stock recovery/restore information before persistent device experiments.

## Phase B — Boot chain, kernel and device tree

### OTA / stock boot / boot assembly

- [x] Strict OTA ZIP metadata inspection and payload discovery.
- [x] Fail-closed payload envelope/checksum evidence.
- [x] Source-locked boot-only extractor.
- [x] Exact OTA → payload → stock boot provenance.
- [x] Deterministic profile-driven `BootBuildPlan`.
- [x] Source-locked `mkbootimg`/`unpack_bootimg` backend.
- [x] Independent double assembly and locked round-trip verification.
- [x] Temporary-boot authorization contract.
- [x] Physical-candidate preflight contract that rechecks exact plan/layout/stock/candidate identities before temporary boot can be offered.
- [ ] Instantiate the full chain against real AC2003 firmware/stock boot evidence.

### Kernel/toolchain reproducibility

- [x] Exact kernel source/version/config/toolchain contract.
- [x] Deterministic build identity, source-mtime normalization and compiler path remapping.
- [x] Deterministic `CONFIG_IKHEADERS` and compat-vDSO path policy.
- [x] Byte-range, build-tree and ARM64/ARM32 target ELF diagnostics.
- [x] Strict build-run verifier-evidence provenance binding.
- [x] Reviewed kernel-authority schema and candidate-authority binding.
- [x] First real byte-identical kernel authority from run `35183670399`.
- [ ] Promote a kernel patchset as hardware-working only after physical temporary boot evidence.

### DTB / DTBO

- [x] FDT/Android DT table source locks and structural verification.
- [x] Profile-driven exact DT plan tied to reviewed kernel authority.
- [x] Strict two-root DTB/raw-DTBO/packed-DTBO reproducibility.
- [x] Reviewed authority run `35196447576` and candidate-level authority binding.
- [x] Unified candidate authority bundle across kernel/rootfs/DT.
- [ ] Bind reviewed DT authority to one exact physical-firmware candidate.
- [ ] Verify device-tree functionality on physical AC2003.

## Phase C — Kali userspace and rescue

### Kali ARM64 rootfs

- [x] Pin official NetHunter rootfs builder to exact `2026.2` commit.
- [x] GPG-verify Kali `InRelease` and exact ARM64 package indexes.
- [x] Strict independent double-build + reviewed canonicalization provenance.
- [x] Reviewed rootfs authority run `35158577624`.
- [ ] Prove accepted rootfs reaches Kali early userspace on physical hardware.

### First boot / provisioning

- [x] Schema-v8 first-boot candidate manifest.
- [x] Candidate-level reviewed rootfs/kernel/device-tree authority bindings.
- [x] Unified reviewed authority bundle.
- [x] Deterministic provisioning overlay with no embedded credentials and remote access disabled.
- [x] Physical-candidate gate joining exact physical baseline, candidate, authorities, boot authorization and boot plan.
- [ ] Instantiate against real physical firmware and reviewed artifacts.

### Rescue / recovery

- [x] Deterministic `newc` rescue initramfs, gzip/LZ4 support and source-locked static ARM64 BusyBox.
- [x] Network/SSH disabled by default and host-side reproducibility verification.
- [ ] Prove a usable physical rescue/log path.
- [ ] Exercise rollback/recovery on exact physical baseline.

## Phase D — Physical AC2003 bring-up

Nothing in this phase may be checked from host-only CI.

- [ ] Exact model/profile and serial recognized on physical phone.
- [ ] Exact OxygenOS build/fingerprint captured.
- [ ] Matching stock boot image verified.
- [ ] Temporary boot succeeds.
- [ ] Rescue/log channel works after candidate boot.
- [ ] Kernel reaches Kali early userspace/rootfs.
- [ ] Required UFS/storage path verified.
- [ ] Display and touchscreen usable for setup, or release explicitly console-only.
- [ ] USB rescue behavior verified.
- [ ] Wi-Fi verified.
- [ ] Bluetooth verified.
- [ ] Modem/cellular behavior verified/documented for declared Beta scope.
- [ ] Audio verified for declared Beta scope.
- [ ] Charging/battery behavior safe enough for testing.
- [ ] Suspend/resume/power behavior documented.
- [ ] Recovery and A/B rollback exercised.

## Phase E — Beta release

A first GitHub Beta is allowed only when [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md) is fully satisfied for the declared compatibility scope.

- [ ] CI green for exact release commit.
- [ ] Exact device/firmware compatibility matrix.
- [ ] Reviewed strict authorities instantiated against the exact physical candidate.
- [ ] Physical-candidate preflight gate matches the exact release candidate.
- [ ] Required physical-device evidence complete.
- [ ] Installation and recovery/restore instructions.
- [ ] Known-issues and hardware matrix.
- [ ] Release manifest and SHA-256 files.
- [ ] Real binaries/images attached; no empty or symbolic release.

## Stable release

Stable requires a later, higher hardware-completeness threshold, repeated regression testing, recovery confidence and a reviewed long-term update/signing strategy.
