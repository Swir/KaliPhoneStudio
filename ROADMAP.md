# KaliPhoneStudio Roadmap

KaliPhoneStudio separates **device-independent studio engineering** from **per-device physical bring-up**. Host-side success never implies hardware support.

## Overall project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

The percentage is weighted toward physical boot, hardware validation, recovery and release readiness. CI and offline engineering are mandatory foundations, but do not receive the same weight as verified device milestones.

## Current development line — 0.6.49-dev

### Completed host-side foundations

- [x] `Swir/KaliPhoneStudio` is the only project source of truth.
- [x] Device-independent `kaliphonestudio/` core with profile registry under `devices/<vendor>/<codename>/profile.json`.
- [x] Profile/path identity, confirmation token, A/B constraints, boot/partition policy, immutable sources, recovery and test contracts.
- [x] Offline GUI/CLI profile inspection with no device writes.
- [x] Read-only Fastboot baseline capture with exact transcript, exact reviewed Fastboot executable/tool policy and immutable capture bundle.
- [x] Exact OTA → payload → stock `boot.img` provenance and physical-baseline/stock-provenance bundle.
- [x] Deterministic boot plan, source-locked boot assembly, independent double assembly and locked round-trip verification.
- [x] Reviewed strict rootfs authority run `35158577624`.
- [x] Reviewed strict kernel authority run `35183670399`.
- [x] Reviewed strict DTB/DTBO authority run `35196447576`.
- [x] Candidate-level reviewed kernel/rootfs/device-tree authority bindings and one unified first-boot authority bundle.
- [x] Deterministic credential-free provisioning and source-locked rescue-initramfs foundations.
- [x] `PhysicalCandidateGateEvidence` cross-binding exact physical baseline/stock provenance, schema-v8 candidate, reviewed authorities, temporary-boot authorization and exact profile-bound boot plan.
- [x] BUILD_STATUS authority run/commit/artifact identities are regression-tested against immutable reviewed authority records.
- [x] `TemporaryBootOfferEvidence` rehashes the exact local Fastboot executable and exact local candidate `boot.img`, binds them back to read-only capture + physical-candidate gate, and creates only one serial-bound `fastboot ... boot ...` argv without executing it.
- [x] Explicit profile confirmation can authorize a prepared offer in memory, but authorization still records no execution, persistent write, hardware verification or Beta credit.

### Immediate next gates

- [ ] Capture the exact physical AC2003 Fastboot/OxygenOS baseline using the reviewed read-only capture path.
- [ ] Validate matching stock `boot.img` provenance from that exact OTA.
- [ ] Assemble the exact candidate from reviewed kernel/rootfs/DT authorities plus provisioning/rescue inputs.
- [ ] Instantiate schema-v8 candidate + reviewed authority bindings + physical-candidate preflight gate for that exact device/firmware.
- [ ] Prepare the exact local temporary-boot offer from the reviewed Fastboot executable and exact candidate boot image.
- [ ] Require explicit profile confirmation before any execution path is permitted.
- [ ] Attempt only a physical **temporary boot** first; no persistent write until later gates explicitly allow it.

## Phase A — Multi-device studio core

- [x] Runtime profile registry and versioned fail-closed schema.
- [x] Profile/path identity and profile-driven device detection.
- [x] Verified serial bound to `profile_id`.
- [x] Profile-specific confirmation token.
- [x] Typed boot/kernel/A-B/recovery/test contracts.
- [x] Immutable HTTPS full-commit sources.
- [x] Trusted in-process profile hooks only; no shell/module injection from JSON.
- [x] Offline GUI/CLI profile inspection.
- [ ] Add a second real device profile only after full identity/partition/source/recovery/test contracts exist.

## Phase B — Boot chain, kernel and device tree

- [x] Strict OTA metadata and payload/stock-boot provenance.
- [x] Deterministic `BootBuildPlan` and source-locked `mkbootimg`/`unpack_bootimg` path.
- [x] Independent double assembly and round-trip verification.
- [x] Schema-v2 temporary-boot authorization.
- [x] Physical-candidate preflight gate.
- [x] Temporary-boot offer with exact Fastboot/image byte verification and argv-only command plan.
- [ ] Instantiate the complete chain against real AC2003 firmware and stock boot evidence.

### Kernel/toolchain

- [x] Exact source/version/config/toolchain contract.
- [x] Deterministic build identity, source-mtime normalization, compiler path remapping and deterministic IKHEADERS/compat-vDSO policy.
- [x] Strict two-root reproducibility plus build/verifier provenance binding.
- [x] Reviewed kernel authority and candidate binding.
- [ ] Promote the kernel as hardware-working only after physical temporary boot proof.

### DTB / DTBO

- [x] FDT/Android DT source locks and structural verification.
- [x] Exact DT plan tied to reviewed kernel authority.
- [x] Strict two-root DTB/raw-DTBO/packed-DTBO reproducibility.
- [x] Reviewed DT authority and unified candidate authority binding.
- [ ] Verify device-tree functionality on the physical AC2003.

## Phase C — Kali userspace and rescue

- [x] Pinned Kali/NetHunter ARM64 rootfs builder and signed repository snapshot verification.
- [x] Strict independent rootfs builds with reviewed canonicalization and authority record.
- [x] Schema-v8 first-boot candidate.
- [x] Reviewed candidate authority bindings and deterministic provisioning overlay.
- [x] Reproducible rescue initramfs foundation.
- [ ] Prove Kali early userspace/rootfs on physical hardware.
- [ ] Prove a usable physical rescue/log path.
- [ ] Exercise rollback/recovery on the exact physical baseline.

## Phase D — Physical AC2003 bring-up

Nothing in this phase may be checked from host-only CI.

- [ ] Exact model/profile/serial recognized on physical phone.
- [ ] Exact OxygenOS build/fingerprint captured.
- [ ] Matching stock boot image verified.
- [ ] Explicitly confirmed temporary boot succeeds.
- [ ] Rescue/log channel works.
- [ ] Kernel reaches Kali early userspace/rootfs.
- [ ] Required UFS/storage path verified.
- [ ] Display/touch usable or release explicitly console-only.
- [ ] USB rescue behavior verified.
- [ ] Wi-Fi verified.
- [ ] Bluetooth verified.
- [ ] Modem/cellular documented for Beta scope.
- [ ] Audio documented for Beta scope.
- [ ] Charging/battery behavior safe enough for testing.
- [ ] Suspend/resume/power behavior documented.
- [ ] Recovery and A/B rollback exercised.

## Phase E — Beta release

A GitHub Beta is allowed only when [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md) is satisfied for the declared compatibility scope.

- [ ] Exact release commit CI green.
- [ ] Exact device/firmware compatibility matrix.
- [ ] Reviewed authorities instantiated against exact physical candidate.
- [ ] Physical-candidate gate and local temporary-boot offer match the exact candidate.
- [ ] Required physical-device evidence complete.
- [ ] Installation + recovery/restore instructions.
- [ ] Known issues/hardware matrix.
- [ ] Release manifest + SHA-256 files.
- [ ] Real images/binaries attached; no empty or symbolic release.

Stable requires a later, higher hardware-completeness, recovery and regression threshold.
