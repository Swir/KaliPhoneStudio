# KaliPhoneStudio Roadmap

KaliPhoneStudio separates **device-independent studio engineering** from **per-device physical bring-up**. Host-side success never implies hardware support.

## Overall project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

The percentage is weighted toward physical boot, hardware validation, recovery and release readiness. CI and offline engineering are mandatory foundations, but do not receive the same weight as verified device milestones.

## Current development line — 0.6.51-dev

### Completed host-side foundations

- [x] `Swir/KaliPhoneStudio` is the only project source of truth.
- [x] Device-independent `kaliphonestudio/` core and versioned profile registry under `devices/<vendor>/<codename>/profile.json`.
- [x] Profile/path identity, confirmation token, A/B constraints, boot/partition policy, immutable sources, recovery and test contracts.
- [x] Offline GUI/CLI profile inspection with no device writes.
- [x] Read-only Fastboot baseline capture with exact transcript and reviewed Fastboot executable identity.
- [x] Exact OTA → payload → stock `boot.img` provenance and immutable physical-baseline bundle.
- [x] Deterministic boot plan, source-locked boot assembly, independent double assembly and locked round-trip verification.
- [x] Reviewed strict rootfs authority run `35158577624`.
- [x] Reviewed strict kernel authority run `35183670399`.
- [x] Reviewed strict DTB/DTBO authority run `35196447576`.
- [x] Candidate-level reviewed kernel/rootfs/device-tree authority bindings and unified first-boot authority bundle.
- [x] Physical-candidate preflight cross-binding exact device/firmware, stock provenance, reviewed authorities and candidate image.
- [x] Exact local temporary-boot offer bound to reviewed Fastboot/image bytes and profile confirmation policy.
- [x] Fresh read-only runtime device/state revalidation immediately before one serial-bound temporary `fastboot boot`.
- [x] Temporary-boot execution evidence records command result without granting Kali userspace/hardware/Beta credit.
- [x] Deterministic source-locked rescue initramfs with a per-candidate provenance probe ID.
- [x] Offline physical rescue observation evidence binds exact successful temporary-boot execution + exact rescue candidate + raw console transcript and requires exact `init-reached`/probe markers.
- [x] Rescue observation evidence remains manual-review-only and cannot promote storage/display/charging/recovery/hardware/Beta state.

### Immediate next gates

- [ ] Capture the exact physical AC2003 Fastboot/OxygenOS baseline using the reviewed read-only capture path.
- [ ] Validate matching stock `boot.img` provenance from that exact OTA.
- [ ] Assemble the exact candidate from reviewed kernel/rootfs/DT authorities plus provisioning/rescue inputs.
- [ ] Instantiate schema-v8 candidate + reviewed authority bindings + physical-candidate preflight for that exact phone/firmware.
- [ ] Prepare the exact local temporary-boot offer and pass fresh runtime device/state revalidation.
- [ ] Attempt only a physical **temporary boot** first; no persistent write.
- [ ] Capture the raw physical console/log stream and bind the exact schema-v2 rescue probe markers to the exact temporary-boot execution.
- [ ] Manually review that evidence and separately prove Kali early userspace/rootfs, storage and remaining physical gates.

## Phase A — Multi-device studio core

- [x] Runtime profile registry and versioned fail-closed schema.
- [x] Profile/path identity and profile-driven device detection.
- [x] Verified serial bound to `profile_id`.
- [x] Profile-specific confirmation token.
- [x] Typed boot/kernel/A-B/recovery/test contracts.
- [x] Immutable HTTPS full-commit sources.
- [x] Trusted in-process profile hooks only; no shell/module injection from JSON.
- [x] Offline GUI/CLI profile inspection.
- [ ] Add a second real device profile only after complete identity/partition/source/recovery/test contracts exist.

## Phase B — Boot chain, kernel and device tree

- [x] Strict OTA metadata and payload/stock-boot provenance.
- [x] Deterministic `BootBuildPlan` and source-locked `mkbootimg`/`unpack_bootimg` path.
- [x] Independent double assembly and round-trip verification.
- [x] Schema-v2 temporary-boot authorization.
- [x] Physical-candidate preflight gate.
- [x] Temporary-boot offer with exact Fastboot/image byte verification and argv-only command plan.
- [x] Guarded single temporary-boot execution boundary with fresh read-only identity/state probe.
- [ ] Instantiate the complete chain against real AC2003 firmware and stock boot evidence.

### Kernel / DTB / DTBO

- [x] Exact source/version/config/toolchain contract.
- [x] Deterministic build identity, source-mtime/path normalization and strict two-root reproducibility.
- [x] Reviewed kernel authority and candidate binding.
- [x] FDT/Android DT source locks, exact DT plan and strict DTB/raw-DTBO/packed-DTBO reproducibility.
- [x] Reviewed DT authority and unified candidate authority binding.
- [ ] Promote kernel/device-tree functionality only after physical temporary-boot proof.

## Phase C — Kali userspace and rescue

- [x] Pinned Kali/NetHunter ARM64 rootfs builder and signed repository snapshot verification.
- [x] Strict independent rootfs builds with reviewed canonicalization and authority record.
- [x] Schema-v8 first-boot candidate and reviewed candidate authority bindings.
- [x] Deterministic credential-free provisioning overlay.
- [x] Reproducible source-locked rescue initramfs foundation.
- [x] Deterministic rescue probe ID embedded in the exact candidate ramdisk.
- [x] Exact machine-readable `/init` stage/probe markers and offline raw-transcript binding contract.
- [ ] Observe and manually review the exact rescue proof markers on the physical AC2003.
- [ ] Prove Kali early userspace/rootfs on physical hardware.
- [ ] Prove a usable physical rescue/log path beyond the marker observation.
- [ ] Exercise rollback/recovery on the exact physical baseline.

## Phase D — Physical AC2003 bring-up

Nothing in this phase may be checked from host-only CI, a prepared offer, Fastboot return code, or unreviewed transcript.

- [ ] Exact model/profile/serial recognized on physical phone.
- [ ] Exact OxygenOS build/fingerprint captured.
- [ ] Matching stock boot image verified.
- [ ] Explicitly confirmed temporary boot succeeds **and independent reviewed physical evidence confirms actual boot progress**.
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
- [ ] Physical-candidate gate, local temporary-boot offer and fresh execution gate match the exact candidate/device state.
- [ ] Required physical-device evidence manually reviewed and complete.
- [ ] Installation + recovery/restore instructions.
- [ ] Known issues/hardware matrix.
- [ ] Release manifest + SHA-256 files.
- [ ] Real images/binaries attached; no empty or symbolic release.

Stable requires a later, higher hardware-completeness, recovery and regression threshold.
