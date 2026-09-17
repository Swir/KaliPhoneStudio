# KaliPhoneStudio Beta Release Gate

A Beta release is a **tested device build**, not a development snapshot. A profile, green CI, host-reproducible artifact, physical-candidate gate or prepared command offer never satisfies a physical-device checkbox.

## Required host-side evidence

- [ ] CI/tests green for the exact release commit.
- [ ] Device profile schema/identity tests pass for the declared device.
- [ ] Read-only Fastboot baseline records exact physical profile/serial, firmware build/fingerprint, A/B/security state and SHA-256-bound original transcript.
- [ ] Exact reviewed Fastboot executable/tool-policy evidence is joined to raw transcript and parsed baseline in one immutable capture bundle.
- [ ] Baseline firmware matches exact stock OTA metadata and matching stock `boot.img` provenance is bound to exact OTA/payload evidence.
- [ ] One immutable physical-baseline bundle joins exact capture, baseline/transcript, OTA/payload/stock boot and firmware metadata while keeping `temporary_boot_authorized=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- [ ] Candidate manifest records exact `profile_id`, serial, firmware, boot authorization/plan/image and reviewed artifact identities.
- [ ] Reviewed kernel authority binds exact source, compiler, plan, recipe/environment, two executed builds, strict reproducibility and exact `.config`/ARM64 `Image` identity.
- [ ] Reviewed DT authority binds exact DT plan, reviewed kernel authority, independent DT builds, strict equality and exact DTB/raw-DTBO/packed-DTBO identities.
- [ ] Reviewed Kali ARM64 rootfs authority binds strict independent builds, signed repository snapshot, raw A/B inputs, canonicalization provenance and package evidence.
- [ ] Candidate-level reviewed kernel/rootfs/device-tree authority records all bind the exact same schema-v8 first-boot manifest.
- [ ] Unified first-boot authority bundle proves those three reviewed bindings refer to the same manifest/profile and exact candidate kernel/rootfs/DT identities.
- [ ] `PhysicalCandidateGateEvidence` cross-binds exact physical baseline/stock bundle, schema-v8 manifest, unified reviewed authority bundle, schema-v2 temporary-boot authorization and exact profile-driven `BootBuildPlan`; it must still record no execution/write/hardware/Beta claim.
- [ ] `TemporaryBootOfferEvidence` is prepared from that exact gate and exact original read-only Fastboot capture/tool evidence. The concrete Fastboot executable and concrete candidate `boot.img` must be rehashed locally and exactly match reviewed/gated SHA-256 and size. The only eligible command plan is serial-bound `fastboot ... boot ...`, with `persistent_write=false`, `phone_storage_written=false`, `temporary_boot_executed=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- [ ] Exact profile-specific confirmation is required before execution can be permitted. Confirmation authorization by itself still records `temporary_boot_executed=false` and grants no hardware/Beta credit.
- [ ] If a provisioning overlay ships, its exact SHA-256/size/plan digest is bound to accepted rootfs evidence; it embeds no credentials, keeps root locked and remote access disabled by default.
- [ ] Every release image has SHA-256 recorded and partition-size/boot-layout gates pass.
- [ ] Build instructions reproduce artifacts from pinned sources.

## Required physical-device evidence

- [ ] Exact model/profile and serial recognized correctly before any destructive action.
- [ ] Exact OxygenOS build/fingerprint captured from the physical device.
- [ ] Stock recovery/restore information captured before persistent experiments.
- [ ] Explicitly confirmed candidate succeeds with **temporary boot** where supported.
- [ ] Rescue/log channel is usable after candidate boot.
- [ ] Kernel reaches intended Kali early userspace/rootfs path.
- [ ] Required internal storage/UFS path is verified.
- [ ] Display/touch is usable enough for setup, or release is explicitly console-only.
- [ ] Charging/battery behavior is safe enough for testing.
- [ ] Failed boot can be recovered by a documented procedure and required rollback/recovery has been exercised.

## Required release content

- [ ] Clear device/firmware compatibility table.
- [ ] Installation instructions.
- [ ] Recovery/restore instructions.
- [ ] Known issues and hardware matrix.
- [ ] Release manifest and SHA-256 files.
- [ ] Real binaries/images attached; no empty or symbolic release.
- [ ] No proprietary firmware/blob redistribution unless redistribution is explicitly permitted.

Creating a profile, capturing/importing Fastboot evidence, accepting host-side kernel/rootfs/DT authorities, generating a schema-v8 candidate, creating unified authority/physical-candidate evidence, preparing a temporary-boot argv, recording profile confirmation, generating a provisioning overlay, or passing host CI does **not** satisfy a physical-device checkbox.

Only after all required gates pass for the declared compatibility scope should a GitHub **Beta** be created. Stable requires a later, higher hardware-completeness and regression threshold.
