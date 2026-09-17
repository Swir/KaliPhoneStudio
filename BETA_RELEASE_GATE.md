# KaliPhoneStudio Beta Release Gate

**Status: BLOCKED**

A green CI run, device profile, successful host build, reviewed reproducibility authority, progress SVG, Fastboot return code, rescue marker, bounded hardware-presence signal, accepted contextual hardware-survey review, generated or accepted host-side functional-test plan/review, complete host-side functional-result bundle, early-userspace marker, source-pinned storage-layout hint, storage-discovery contract, syntactically valid manual-review record, host-only evidence-session bundle or exact-file dossier does not by itself authorize a Beta release.

The first public Beta may be published only when the exact release candidate passes every applicable item below and the evidence is reviewed.

## Host-side mandatory gate

- [x] Multi-device profile schema/identity/path contract is enforced.
- [x] The selected profile has a unique identity and explicit confirmation token.
- [x] Boot layout/partition constraints, pinned sources and recovery/test contracts are declared by profile.
- [x] Exact source/tool locks and checksums/object identities are recorded.
- [x] Kali ARM64 rootfs has a reviewed strict byte-identical authority.
- [x] Kernel has a reviewed strict byte-identical authority.
- [x] Required DTB/DTBO artifacts have a reviewed strict byte-identical authority bound to the reviewed kernel.
- [x] Exact first-boot candidate binds kernel/rootfs/DT authorities and firmware/boot provenance without claiming hardware success.
- [x] Boot image assembly/round-trip and partition-size checks are fail-closed.
- [x] Temporary boot is serial/profile/firmware/candidate bound and cannot silently become a flash/write action.
- [x] Rescue initramfs/payload is deterministic, network/SSH disabled by default, and has an exact probe identity.
- [x] Bounded rescue hardware-presence survey is sysfs-only, exact-transcript/probe/diagnostics bound and cannot activate a subsystem or promote observed presence to functional hardware/Beta verification.
- [x] Manual hardware-survey review can bind one exact survey to canonical review-record bytes and separate notes; contextual acceptance requires all explicit presence/limitations checks and still cannot promote any subsystem to functional/hardware/Beta verification.
- [x] Profile-driven physical functional-test planning is pending-only, non-destructive/no-write and bound to the exact accepted hardware-survey review plus the profile functional-hardware contract.
- [x] Independent exact test-plan review binds the original canonical plan file bytes, exact upstream identity chain, canonical review record and separate notes; acceptance only makes that exact plan eligible as a later manual non-destructive test checklist and grants no hardware/Beta credit.
- [x] Schema-v2 per-test observation evidence requires that exact accepted plan review and cross-binds its review evidence, canonical plan file, review record, review notes and reviewer identity before a physical result can even become eligible for later result review.
- [x] Exact per-test physical result-review and aggregate exact-plan summary contracts keep project support/hardware/Beta promotion separate from test-level evidence.
- [x] Exact functional-result bundle verifies canonical plan/plan-review/observation/result-review/summary files, exact plan-review propagation, one-to-one test ids and a freshly recomputed summary while forcing support/write/hardware/Beta promotion false.
- [x] Kali early-userspace proof overlay is deterministic and bound to exact candidate/rootfs authority identities.
- [x] Early-userspace transcript parser requires exact stage/probe/manifest/rootfs-authority/rootfs-artifact markers and never auto-promotes them to hardware/Beta credit.
- [x] Rootfs handoff **discovery contract** is profile-driven, exact-source/blob pinned, bound to the physical-candidate/rootfs authority chain and cannot select a storage path or authorize writes.
- [x] Typed physical-storage discovery evidence can bind exact report/recovery-plan bytes to the exact handoff/rescue/rootfs chain while rejecting device paths, write claims and automatic target/storage/hardware/Beta promotion.
- [x] Manual storage-review evidence can bind exact review-record and review-notes bytes to one exact physical-storage discovery chain; acceptance requires a review-ready source and explicit physical-context/topology/filesystem/encryption/free-space/recovery/evidence-chain checks, but still cannot select a target or authorize writes.
- [x] Physical bring-up session evidence can cross-bind the exact candidate gate, rescue observation, diagnostics, functional probes, storage discovery/review and optional Kali early-userspace identities while forcing all target/write/hardware/Beta claims false.
- [x] Physical bring-up exact-file dossier can verify the canonical session plus every bound original evidence/raw transcript/report/recovery/review file by exact SHA-256/size, with optional exact rootfs verification, while granting no physical/Beta credit.
- [x] SWIR Progress SVG PRO reads the existing authoritative project ledger deterministically and shows Beta readiness separately; it is presentation-only and grants no release credit.
- [ ] Capture and manually review the real storage/encryption/free-space/recovery evidence required by those contracts and produce one accepted review record for the exact physical device.
- [ ] Produce and review one cross-bound bring-up session from the exact real candidate/rescue/storage evidence before later storage-strategy approval.
- [ ] Produce and review the exact-file dossier from that real session and its original bound source bytes before later storage-strategy approval.
- [ ] Select and separately review the actual reversible rootfs staging/handoff strategy only after that exact physical review and dossier audit are accepted.
- [ ] Final release manifest/compatibility matrix/known issues and SHA-256 set are generated from the exact reviewed physical candidate.

## Physical AC2003 mandatory gate

These must come from the exact physical phone/firmware intended for support.

- [ ] Real device identity captured and matches profile `oneplus/avicii` / OnePlus Nord AC2003.
- [ ] Exact OxygenOS build and firmware fingerprint captured read-only.
- [ ] Matching stock `boot.img` extracted from the exact OTA and validated against that physical baseline.
- [ ] Recovery path is documented before risky testing begins.
- [ ] Exact reviewed physical candidate is instantiated from that baseline and reviewed authorities.
- [ ] Bounded rescue hardware-presence survey is captured from that exact candidate/transcript and an exact manual review is bound with `accepted_as_context=true`; that acceptance remains contextual evidence only.
- [ ] The exact profile-driven functional-test plan is generated from that real accepted survey review, and the original canonical plan bytes pass an independent manual review with `accepted_for_physical_execution=true` before any plan item is treated as a valid test attempt.
- [ ] Every applicable Beta-required functional test is manually executed against that exact reviewed plan/candidate; each schema-v2 observation must carry the accepted exact plan-review evidence/file/review-record/review-notes identities and then pass an independent result review. Synthetic/mock records grant no credit.
- [ ] The exact real plan, accepted plan-review evidence, schema-v2 observation files, independent result-review files and aggregate summary are frozen into one verified functional-result bundle before manual release-gate review.
- [ ] Rootfs-handoff discovery evidence from the real phone confirms the exact physical block topology, filesystem identity, encryption/unlock state, free space and recovery plan.
- [ ] That exact discovery record is manually reviewed and bound; `accepted_for_strategy_design=true` only authorizes later strategy design, not a write or target selection.
- [ ] The real candidate/rescue/storage evidence is cross-bound into one reviewed physical bring-up session without identity/transcript/rootfs drift.
- [ ] The canonical real session and its original evidence/transcript/report/recovery/review bytes are frozen into one exact-file dossier and reviewed for completeness before target-strategy approval.
- [ ] A reversible rootfs handoff target is explicitly reviewed after accepted discovery review and dossier audit; no guessed UFS/userdata path is accepted.
- [ ] `fastboot boot` succeeds on the exact phone after explicit user confirmation.
- [ ] Rescue/logging path is usable and exact rescue probe markers are manually reviewed.
- [ ] The selected rootfs handoff makes the exact reviewed Kali rootfs available without violating the approved storage/recovery policy.
- [ ] Exact `KPS_KALI_STAGE=rootfs-systemd-early-v1` plus matching probe/manifest/rootfs-authority/rootfs-artifact markers are captured from the physical run and manually reviewed.
- [ ] Reviewer confirms the kernel reached the intended Kali early userspace/rootfs; parser output alone is not sufficient.
- [ ] Required UFS/storage behavior is validated beyond bounded diagnostic reads.
- [ ] Charging/battery behavior is safe enough for the documented test/release scope.
- [ ] Display/touch works for the supported scope, or Beta is explicitly reviewed and documented as console-only.
- [ ] Required USB/rescue behavior is verified.
- [ ] Recovery/rollback is exercised on the exact physical baseline.

## Non-credit evidence

The following remain useful diagnostics but **cannot** satisfy a physical functional checkbox on their own:

- green host CI;
- profile JSON presence;
- reproducible kernel/rootfs/DT artifacts without phone testing;
- deterministic progress SVGs or their project percentage/counter;
- a `fastboot boot` process return code without observed phone-side evidence;
- rescue `init-reached` marker without Kali-rootfs proof;
- bounded USB/network/rfkill/sound/thermal/input/graphics/power sysfs presence records without separate functional verification;
- an `accepted_as_context=true` hardware-survey review, even when all contextual review checks pass;
- a generated physical functional-test plan or an `accepted_for_physical_execution=true` exact-plan review without real per-test physical observations;
- a schema-v2 observation file without a real physical test and separate result review;
- an exact functional-result bundle, even when all Beta-required rows are reviewed pass, without the underlying real physical tests and the complete release gate;
- a Kali early-userspace marker set without manual review of the exact candidate/physical context;
- one bounded 4096-byte block read;
- two battery telemetry samples;
- the pinned LineageOS fstab/BoardConfig storage expectations;
- a discovery-only rootfs handoff assessment;
- a syntactically valid or even `discovery_ready_for_manual_review=true` storage record before manual review of the exact physical context;
- a manual-review contract or synthetic review record without real physical discovery evidence;
- `accepted_for_strategy_design=true` before a separate reversible target/strategy review;
- a valid host-side physical bring-up session bundle without the underlying real reviewed physical evidence;
- a valid exact-file dossier without accepted underlying real physical evidence and later strategy/hardware review;
- synthetic/mock hardware surveys/reviews, test plans/plan reviews, schema-v2 functional observations/result reviews/bundles, storage reports/reviews, sessions, dossiers or transcripts.

## Release publication rule

Do not create an empty, symbolic or placeholder Beta. Only after the full gate is reviewed should a GitHub prerelease be created from the exact candidate commit with actual binaries/images, instructions, compatibility matrix, known issues and SHA-256 checksums.

Stable requires a later, higher threshold.
