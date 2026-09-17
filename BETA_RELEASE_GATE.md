# KaliPhoneStudio Beta Release Gate

A Beta release is a **tested device build**, not a development snapshot. A profile, green CI, host-reproducible artifact, physical-candidate gate, prepared command offer, explicit confirmation, successful Fastboot return code, or unreviewed console transcript never satisfies a physical-device checkbox.

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
- [ ] Candidate-level reviewed kernel/rootfs/device-tree authority records all bind the same exact schema-v8 first-boot manifest.
- [ ] Unified first-boot authority bundle proves those reviewed bindings refer to the same manifest/profile and exact candidate kernel/rootfs/DT identities.
- [ ] `PhysicalCandidateGateEvidence` cross-binds exact physical baseline/stock bundle, schema-v8 manifest, unified reviewed authority bundle, schema-v2 temporary-boot authorization and exact profile-driven `BootBuildPlan`; it still records no execution/write/hardware/Beta claim.
- [ ] `TemporaryBootOfferEvidence` is prepared from that exact gate and original read-only Fastboot capture/tool evidence. Concrete Fastboot and candidate `boot.img` bytes must exactly match reviewed/gated SHA-256 and size. Only serial-bound `fastboot ... boot ...` is eligible.
- [ ] Exact profile-specific confirmation is required before execution; authorization alone grants no physical/Beta credit.
- [ ] Immediately before temporary boot, exact offer files are reverified and a fresh read-only serial-bound Fastboot runtime probe matches product, serial, active slot, slot count, unlock/security state and bootloader/baseband identity.
- [ ] Reviewed baseline and fresh runtime probe both report the bootloader unlocked.
- [ ] If temporary boot is invoked, immutable execution evidence records exact offer/authorization/runtime-probe digests, argv digest, return code and bounded output digest. Return code 0 still keeps Kali-userspace/hardware/Beta flags false.
- [ ] No temporary-boot component exposes `flash`, `erase`, `set_active`, `reboot` or any persistent-write path.
- [ ] The exact rescue candidate used for physical proof is schema-v2 and contains a deterministic probe ID bound to exact profile, reproducible payload/staging and locked `/init` provenance.
- [ ] If rescue console/log evidence is used, `PhysicalBootObservationEvidence` binds the exact successful temporary-boot execution, exact rescue candidate, exact probe ID and raw transcript SHA-256/size. The transcript contains the exact `KPS_RESCUE_STAGE=init-reached-v1` and exact `KPS_RESCUE_PROBE_ID=<id>` lines, contains no conflicting markers, and the observation remains `manual_review_required=true`, `hardware_verified=false`, `beta_gate_credit=false` until separately reviewed.
- [ ] If a provisioning overlay ships, its exact SHA-256/size/plan digest is bound to accepted rootfs evidence; it embeds no credentials, keeps root locked and remote access disabled by default.
- [ ] Every release image has SHA-256 recorded and partition-size/boot-layout gates pass.
- [ ] Build instructions reproduce artifacts from pinned sources.

## Required physical-device evidence

- [ ] Exact model/profile and serial recognized correctly before any destructive action.
- [ ] Exact OxygenOS build/fingerprint captured from the physical device.
- [ ] Stock recovery/restore information captured before persistent experiments.
- [ ] Explicitly confirmed candidate succeeds with **temporary boot** where supported, with evidence beyond the host Fastboot return code.
- [ ] Rescue/log channel is usable after candidate boot; a matching rescue marker transcript must be manually reviewed and tied to the exact candidate/execution.
- [ ] Kernel reaches intended Kali early userspace/rootfs path. Rescue `/init` observation alone is not sufficient.
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

Creating a profile, importing Fastboot evidence, accepting host-side kernel/rootfs/DT authorities, generating a schema-v8 candidate, preparing a temporary-boot argv, recording profile confirmation, passing the fresh runtime probe, receiving Fastboot return code 0, generating a deterministic rescue probe ID, matching an unreviewed console marker transcript, generating a provisioning overlay, or passing host CI does **not** satisfy a physical-device checkbox.

Only after all required gates pass for the declared compatibility scope should a GitHub **Beta** be created. Stable requires a later, higher hardware-completeness and regression threshold.
