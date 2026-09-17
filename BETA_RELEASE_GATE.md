# KaliPhoneStudio Beta Release Gate

A Beta release is a **tested device build**, not a development snapshot.

For a device profile to receive its first public Beta, all items below must be satisfied.

## Required host-side evidence

- [ ] CI/tests green for the exact release commit.
- [ ] Device profile schema/identity tests pass.
- [ ] Read-only Fastboot baseline evidence records the exact physical profile/serial plus firmware build/fingerprint and is SHA-256 bound to the original transcript.
- [ ] The exact reviewed Fastboot executable/tool-policy evidence used during guarded capture is cryptographically joined to that raw transcript and parsed baseline in one immutable read-only capture bundle; detached tool evidence is not acceptable.
- [ ] The baseline firmware fingerprint/build matches the exact stock OTA provenance used for the candidate.
- [ ] Matching stock `boot.img` provenance is bound to the exact OTA/payload evidence used by the build.
- [ ] One physical-baseline/stock-provenance bundle joins the exact capture bundle, baseline/transcript, OTA/payload/stock `boot.img` evidence and canonical firmware metadata before candidate instantiation. That bundle must keep `temporary_boot_authorized=false`, `hardware_verified=false` and `beta_gate_credit=false`.
- [ ] Candidate manifest records exact `profile_id`, firmware baseline and hashes.
- [ ] Kernel evidence records an exact pinned source commit, expected kernel version, generated final `.config` digest and exact ARM64 `Image` digest/size.
- [ ] Kernel compiler/toolchain evidence is source-locked and bound to the approved kernel plan/build configuration; a moving host compiler or PATH fallback is not acceptable.
- [ ] Reviewed kernel reproducibility evidence proves two independent builds produced byte-identical final `.config` and ARM64 `Image` outputs for the same approved kernel plan and locked toolchain.
- [ ] Kernel reproducibility is bound to the exact two executed build-run evidence records, with the same kernel plan, source commit, toolchain lock, canonical build recipe and reproducibility environment; output-only equality without execution provenance is insufficient.
- [ ] The strict kernel reproducibility record's build-A/build-B config-verifier and Image-verifier evidence digests match the exact per-build run records; detached verifier evidence is not acceptable.
- [ ] The accepted kernel has a reviewed immutable authority record binding exact authority run/commit/artifact identity, profile/source/plan/toolchain/recipe/environment, both executed-build records, strict reproducibility evidence, reproducibility-binding evidence and final config/Image identity. The authority must explicitly record strict byte equality, distinct build roots, `hardware_verified=false` and `beta_gate_credit=false`.
- [ ] A first-boot kernel authority record additionally binds the exact schema-v8 candidate-manifest digest to the reviewed kernel authority digest/run/commit/artifact identity and rejects source/plan/toolchain/build/repro/config/Image substitution.
- [ ] The kernel evidence SHA-256/size matches the exact kernel input embedded in the approved boot build plan; source/config/Image evidence may not be mixed across plans or profiles.
- [ ] Final DTB/DTBO artifacts satisfy the selected profile layout and are bound to the same approved first-boot build evidence.
- [ ] Reviewed DTB/DTBO reproducibility evidence proves two independent exact-source roots produced byte-identical selected DTB, every required raw overlay and the final packed `dtbo.img`, all tied to the exact approved kernel authority and device-tree plan.
- [ ] The accepted device tree has a reviewed immutable authority record binding exact authority run/commit/artifact identity, profile, DT plan, reviewed kernel authority, both DT build records, strict reproducibility evidence and exact DTB/raw-DTBO/packed-DTBO hashes/sizes. It must explicitly record strict byte equality, distinct build roots, `hardware_verified=false` and `beta_gate_credit=false`.
- [ ] A first-boot device-tree authority record binds the exact schema-v8 candidate-manifest digest to the reviewed DT authority and rejects DTB/DTBO/format/kernel-authority substitution.
- [ ] If a historical reviewed kernel artifact omitted hidden `.config`, any regenerated config used by dependent DT work is produced only from the exact pinned source/profile/toolchain build recipe and must match the immutable reviewed kernel authority SHA-256/size; the already-reviewed kernel Image must also be reverified and must not be rebuilt as part of that recovery path.
- [ ] Reviewed reproducible Kali ARM64 rootfs evidence comes from a strict byte-identical independent double-build and is bound to the candidate manifest; diagnostic or semantic-equality reports cannot substitute for this evidence.
- [ ] The accepted rootfs has a reviewed immutable authority record binding the exact authority run/commit/artifact identity, source lock, signed repository snapshot/`InRelease`, strict rootfs evidence, raw A/B inputs and canonicalization evidence/policy; the record itself must explicitly grant no hardware/Beta credit.
- [ ] If the rootfs pipeline canonicalizes reviewed volatile builder state, both A/B canonicalization audit records must bind each raw input SHA-256 to the exact canonical output and must use the same reviewed policy.
- [ ] A first-boot rootfs provenance record must cryptographically bind the exact candidate-manifest digest to the strict rootfs evidence, canonicalization-binding digest/policy, both A/B canonicalization evidence digests and both raw input hashes/sizes; transformation provenance may not be detached during release preparation.
- [ ] A first-boot rootfs authority record must additionally bind that exact candidate/provenance digest chain to the reviewed rootfs authority digest/run/commit/artifact identity and reject artifact/package/source/snapshot/canonicalization/raw-A/B substitution.
- [ ] One unified first-boot authority bundle binds the reviewed kernel, rootfs and device-tree candidate-authority records to the **same** exact schema-v8 candidate-manifest digest/profile; it additionally proves the DT authority references the same reviewed kernel authority and rechecks candidate kernel/rootfs/DTB/DTBO identities before release-candidate assembly.
- [ ] If a first-boot provisioning overlay is shipped, its exact SHA-256/size and provisioning-plan digest are bound to the accepted reproducible ARM64 rootfs evidence; it embeds no credentials, keeps the root password locked and remote access disabled by default.
- [ ] Every release image has SHA-256 recorded.
- [ ] Partition-size and boot-layout gates pass.
- [ ] Build instructions are reproducible from pinned sources.

## Required physical-device evidence

- [ ] Exact model/profile recognized correctly before any destructive action.
- [ ] Stock recovery information captured before unlock/flash.
- [ ] Candidate passes **temporary boot** where supported.
- [ ] Rescue/log channel is usable after candidate boot.
- [ ] Kernel reaches the intended Kali early userspace/rootfs path.
- [ ] Internal storage path required by the release is verified.
- [ ] Display and touchscreen are usable enough to complete initial setup, or the release is explicitly labeled console-only.
- [ ] Charging/battery behavior is safe enough for testing.
- [ ] A failed boot can be recovered by a documented procedure.

## Required release content

- [ ] Clear device/firmware compatibility table.
- [ ] Installation instructions.
- [ ] Recovery/restore instructions.
- [ ] Known issues and hardware matrix.
- [ ] Release manifest and SHA-256 files.
- [ ] No proprietary firmware/blob redistribution unless redistribution is explicitly permitted.

Importing a saved Fastboot transcript, creating a joined capture bundle or physical-baseline/stock-provenance bundle, producing host-side authorization evidence, pinning a public kernel/compiler source, binding exact executed kernel or DT builds, accepting or binding reviewed kernel/rootfs/DT authorities, reconstructing a reviewed hidden kernel config, canonicalizing a rootfs, binding candidate provenance, creating a unified host authority bundle, generating a deterministic provisioning overlay, or passing host-side kernel/rootfs/DT checks does **not** by itself satisfy any physical-device checkbox above.

Only after these gates pass should a GitHub **Beta** be created. Stable releases require a substantially higher hardware-completeness and regression threshold.
