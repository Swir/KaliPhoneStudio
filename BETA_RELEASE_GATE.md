# KaliPhoneStudio Beta Release Gate

A Beta release is a **tested device build**, not a development snapshot. A profile, green CI or host-reproducible artifact never satisfies a physical-device checkbox.

## Required host-side evidence

- [ ] CI/tests green for the exact release commit.
- [ ] Device profile schema/identity tests pass for the declared device.
- [ ] Read-only Fastboot baseline evidence records exact physical profile/serial, firmware build/fingerprint, A/B/security state and the SHA-256-bound original transcript.
- [ ] Exact reviewed Fastboot executable/tool-policy evidence is cryptographically joined to the raw transcript and parsed baseline in one immutable capture bundle.
- [ ] Baseline firmware build/fingerprint matches exact stock OTA metadata.
- [ ] Matching stock `boot.img` provenance is bound to exact OTA/payload evidence.
- [ ] One immutable physical-baseline/stock-provenance bundle joins exact capture, baseline/transcript, OTA/payload/stock boot evidence and firmware metadata while keeping `temporary_boot_authorized=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- [ ] Candidate manifest records exact `profile_id`, serial, firmware baseline, boot authorization/plan/image and reviewed artifact identities.
- [ ] Reviewed kernel authority binds exact source, plan, source-locked compiler, recipe/environment, two executed build records, strict reproducibility evidence and exact `.config`/ARM64 `Image` identity.
- [ ] Kernel authority remains strict byte-identical from independent roots and explicitly records no hardware/Beta credit.
- [ ] Reviewed DT authority binds exact DT plan, reviewed kernel authority, two independent DT builds, strict equality and exact DTB/raw-DTBO/packed-DTBO identities.
- [ ] Reviewed Kali ARM64 rootfs authority comes from strict independent byte-identical builds and binds source lock, signed repository snapshot, raw A/B inputs, canonicalization provenance and package evidence.
- [ ] Candidate-level reviewed kernel, rootfs and device-tree authority records all bind to the exact same schema-v8 first-boot manifest.
- [ ] One unified first-boot authority bundle proves those three reviewed bindings refer to the same manifest/profile, DT authority references the same reviewed kernel authority, and candidate kernel/rootfs/DTB/DTBO identities match.
- [ ] One `PhysicalCandidateGateEvidence` record cross-binds the exact physical-baseline/stock bundle, schema-v8 manifest, unified reviewed authority bundle, schema-v2 temporary-boot authorization and exact `BootBuildPlan` before a temporary boot may be offered. The gate must recheck selected profile boot-layout/input policy and must record `temporary_boot_executed=false`, `phone_storage_written=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- [ ] If a provisioning overlay ships, its exact SHA-256/size/plan digest is bound to accepted rootfs evidence; it embeds no credentials, keeps root locked and remote access disabled by default.
- [ ] Every release image has SHA-256 recorded and partition-size/boot-layout gates pass.
- [ ] Build instructions reproduce artifacts from pinned sources.

## Required physical-device evidence

- [ ] Exact model/profile and serial recognized correctly before any destructive action.
- [ ] Exact OxygenOS build/fingerprint captured from the physical device.
- [ ] Stock recovery/restore information captured before persistent experiments.
- [ ] Candidate passes **temporary boot** where supported.
- [ ] Rescue/log channel is usable after candidate boot.
- [ ] Kernel reaches intended Kali early userspace/rootfs path.
- [ ] Required internal storage/UFS path is verified.
- [ ] Display/touch is usable enough for initial setup, or release is explicitly console-only.
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

Creating a profile, importing or capturing a Fastboot transcript, producing capture/physical-baseline bundles, accepting host-side kernel/rootfs/DT authorities, generating a schema-v8 candidate, creating a unified authority bundle, producing a physical-candidate preflight gate, generating a provisioning overlay, or passing host CI does **not** satisfy any physical-device checkbox above.

Only after all required gates pass for the declared compatibility scope should a GitHub **Beta** be created. Stable requires a later, higher hardware-completeness and regression threshold.
