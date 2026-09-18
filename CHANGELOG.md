# Changelog

Active development changes are listed here. Older detailed entries remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md).

## 0.6.66-dev — cross-campaign release audit and multi-device identity hardening

- Extended the current schema-v2 physical-observation admission boundary through new downstream campaign creation: hardware-survey review, functional-test planning, accepted functional-test-plan review, schema-v2 per-test observation template/binding, result-review template/binding, final functional-result-bundle creation, physical-storage discovery and bring-up session binding now require the exact current runtime/recovery-bound observation instead of accepting historical schema-v1 provenance.
- Added a reusable offline campaign-admission helper that cross-checks profile, serial, exact observation digest, rescue transcript and rescue probe id; historical evidence remains readable for audit, but cannot seed a new current campaign through the guarded operator paths.
- Updated the shared source/frozen Windows evidence workspace and focused Python 3.11/3.14 CI so new survey-review, plan-build, accepted plan-review, per-test observation, result-review and final functional-result-bundle operations require the current boot-observation file; storage/session boundaries are covered by the same admission contract. No device I/O, storage selection, persistent write, hardware verification or Beta credit was added.
- Project completion remains **58%** and Beta remains **BLOCKED** because the new provenance gate is host-side safety hardening and no physical AC2003 gate was completed.
- Added formal Draft 2020-12 `devices/profile.schema.json` for profile schema v3 and a pinned CI-only validator that also runs the runtime semantic profile validator.
- Replaced flat safety-sensitive alias matching with profile-driven typed identity signals: strong product/model values may identify a device, while weak contextual values such as a shared bootloader board can never identify a phone by themselves.
- Upgraded the registry audit so every strong identity value must resolve exactly one profile across the complete catalogue; shared weak values are allowed only while weak-only resolution remains impossible. The same contract is executed through the frozen Windows CLI.
- Migrated `oneplus/avicii` to schema v3 with strong `avicii`/AC2003 identity and weak `lito` board context; this is a host-side safety contract and does not add physical hardware support.
- Updated multi-device documentation, README/ROADMAP status wording, BUILD_STATUS and regression coverage; removed legacy text-art progress meters from maintained README/ROADMAP while preserving the numeric fallback and deterministic SWIR Progress SVG PRO presentation.
- Project completion remains **58%** and Beta remains **BLOCKED** because no new physical AC2003 gate was passed.
- Added `kaliphonestudio.physical_release_gate_audit` as a schema-v1 fail-closed audit packet joining one accepted exact physical bring-up dossier/review chain to one exact physical functional-result campaign.
- The audit requires the canonical physical bring-up dossier, independent post-copy dossier verification, accepted dossier review, exact functional-result bundle, canonical functional-test plan and accepted independent test-plan review as exact non-symlink files with SHA-256/size and TOCTOU checks.
- Cross-campaign validation now rejects profile/device drift and requires the exact physical boot observation, rescue diagnostics, raw rescue transcript and rescue probe identity to agree between the bring-up/storage dossier and the functional-test plan; the exact functional-hardware contract is also cross-checked.
- The functional-result bundle must bind the exact supplied plan and exact supplied accepted plan-review file, while the dossier review must bind the exact supplied dossier and verification. This prevents unrelated real-device campaigns from being combined for release review.
- Added immutable canonical audit evidence, `scripts/build_physical_release_gate_audit.py`, focused fail-closed regression tests, dedicated `physical-release-gate-audit` CI and `docs/PHYSICAL_RELEASE_GATE_AUDIT.md`.
- Even when every Beta-required functional test is independently reviewed as passing, the audit forces `manual_release_gate_review_required=true`, `physical_gate_still_incomplete=true`, and keeps target/path/write/support/hardware/Beta authorization false.
- Synchronized README, ROADMAP, BUILD_STATUS, Beta gate wording, version state and deterministic SWIR progress presentation with the new host-side milestone.
- Project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 physical campaign has yet produced the required baseline, temporary boot, storage/hardware evidence, early-userspace proof and exercised recovery/rollback.

## 0.6.65-dev — exact-file physical functional result bundle

- Added `kaliphonestudio.physical_hardware_result_bundle` as a schema-v1 fail-closed audit layer for one exact physical functional-test campaign.
- The bundle verifies canonical SHA-256/size identities for the exact test plan, accepted exact-plan review, every supplied schema-v2 observation, every supplied independent result review and the aggregate summary.
- Every schema-v2 observation is rechecked against the accepted plan-review evidence/file/review-record/review-notes identities and reviewer; every result review must bind the exact bundled observation for the same unique test id.
- The supplied summary is freshly recomputed from the exact bundled reviews and must match byte-for-byte semantic state; detached, duplicate or drifted result files fail closed.
- Added immutable bundle load/write validation, symlink/TOCTOU/file-size hardening, `scripts/build_physical_hardware_result_bundle.py`, operator documentation and focused regression coverage.
- Even complete Beta-required reviewed-pass coverage remains release-gate input only: project support, persistent writes, phone-storage writes, hardware verification and Beta credit remain forced false.
- Extended `physical-hardware-functional-results` CI to compile and test the exact-file bundle chain.
- Project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 physical functional campaign has passed the mandatory gate.

## 0.6.64-dev — accepted-plan-review-bound physical observations and deterministic progress SVGs

- Upgraded `kaliphonestudio.physical_hardware_test_observation` to schema-v2 so no physical per-test observation can be prepared or bound unless the original canonical test plan has a separate `accepted_for_physical_execution=true` exact-plan review.
- Every schema-v2 observation now carries the exact plan-review evidence SHA-256, canonical plan-file SHA-256, review-record SHA-256, review-notes SHA-256 and reviewer identity in addition to the existing profile/device/survey/boot/rescue/transcript/probe/functional-contract chain.
- Added fail-closed cross-checking for plan/review profile and serial identity, semantic plan digest, canonical plan bytes/size, test counts, upstream evidence digests and plan readiness. Rejected, detached or drifted plan reviews cannot produce valid physical observation evidence.
- Updated the safe observation-template and observation-recording CLIs to require `--test-plan-review-evidence`; neither command performs phone I/O or grants hardware/Beta credit.
- Extended focused regression tests and `physical-hardware-functional-results` CI around rejected/detached review handling, immutable schema-v2 round trips and forbidden write/hardware/Beta promotion.
- Implemented **SWIR Progress SVG PRO v1** with deterministic `progress-card.svg`, `progress-mini.svg`, a reusable N/A template, generator/check, XML/geometry/math tests and dedicated CI. The assets read the authoritative `BUILD_STATUS.json` project ledger and render Beta readiness separately.
- For the current 58% ledger value, the generated fill is exactly 638/1100 px on the card and 406/700 px on the mini. Unknown progress renders N/A with no fabricated fill.
- Embedded the card in README and mini in ROADMAP with textual fallback while preserving SWIR README PRO v2 and Search Keywords.
- Project completion remains **58%** and Beta remains **BLOCKED** because no new physical AC2003 gate has been passed.

## 0.6.63-dev — independent exact physical test-plan manual review

- Added `kaliphonestudio.physical_hardware_test_plan_review` as a separate fail-closed review boundary between deterministic plan generation and any real-device functional-test session.
- The review binds the original canonical test-plan file by SHA-256 and byte size in addition to the plan semantic evidence digest, preventing a reviewer from approving only a detached downstream hash.
- Exact profile/device, survey-review, survey, boot, rescue, transcript, rescue-probe and functional-hardware-contract identities are carried into the review evidence.
- `decision="accepted"` requires explicit review of exact plan bytes, identity chain, functional contract, Beta-required scope, context readiness, no-write policy and limitations; a plan that is not itself ready still cannot become `accepted_for_physical_execution=true`.
- Added rejected-by-default review templates, separate UTF-8 review notes, immutable canonical evidence output and offline operator CLIs. No command performs phone I/O or hardware activation.
- Even accepted plan review forces manual test execution and keeps functional execution/verification, phone-storage writes, hardware verification and Beta credit false.
- Added focused fail-closed tests, dedicated `physical-hardware-test-plan-review` CI and `docs/PHYSICAL_HARDWARE_TEST_PLAN_REVIEW.md`.
- Synchronized README/ROADMAP/BUILD_STATUS/Beta-gate wording with SWIR README PRO v2; project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 plan or physical functional result has passed the gate.

## 0.6.62-dev — exact physical functional-test observation and review

- Added `kaliphonestudio.physical_hardware_test_observation` to bind one actually executed physical functional test to one exact pending profile-driven test plan, exact device/candidate context, canonical operator record and separate notes.
- `pass_candidate` now requires every exact `required_observations` item from the selected plan test to be satisfied; missing context signals, identity drift, changed files and any persistent-write claim fail closed.
- Added a safe observation-template CLI that starts `inconclusive`, not executed, with candidate/device confirmation false and all observation checks false; it cannot be bound until edited after a real physical test.
- Added `kaliphonestudio.physical_hardware_test_review` as an independent exact manual-review layer. Accepted pass/fail/inconclusive decisions must match the bound observation outcome and require exact-plan, exact-observation, physical-context, required-observation, notes/limitations and no-write checks.
- Added rejected-by-default review templates plus offline observation/review binder CLIs. A reviewed pass remains test-level evidence only and cannot authorize a public support claim or Beta release.
- Added `kaliphonestudio.physical_hardware_test_summary` to aggregate exact-plan statuses (`pending`, `reviewed_pass`, `reviewed_fail`, `reviewed_inconclusive`, `rejected`) and count Beta-required reviewed passes while forcing project-support/hardware/Beta promotion false.
- Added focused fail-closed tests and dedicated `physical-hardware-functional-results` CI covering exact binding, canonical round trips, outcome/review matching, duplicate/detached review rejection, safe template defaults and forbidden support/write/Beta promotion.
- Added `docs/PHYSICAL_HARDWARE_FUNCTIONAL_TESTS.md` and synchronized README/ROADMAP/version state with SWIR README PRO v2.
- Project completion remains **58%** and Beta remains **BLOCKED** because no real AC2003 functional test result has been captured/reviewed and the mandatory physical release gate remains open.

## 0.6.61-dev — fail-closed physical hardware survey manual review

- Added `kaliphonestudio.physical_hardware_review` as a schema-v1 offline manual-review layer for one exact bounded `PhysicalHardwareSurveyEvidence` record.
- Bound the exact hardware survey, physical boot/rescue/transcript/probe identity, canonical review-record bytes and separate UTF-8 review-notes bytes by SHA-256 and size.
- Context acceptance requires a non-empty recorded survey plus explicit review of physical context, survey integrity, USB presence, network/radio presence, audio presence, input/display presence, thermal/power presence and the limitation that sysfs presence is not functionality.
- Added a rejected-by-default template generator, `scripts/prepare_physical_hardware_review.py`, and the offline binder `scripts/review_physical_hardware_survey.py`; neither command performs phone I/O.
- `accepted_as_context=true` means only that the exact survey may be used as contextual input for later subsystem-specific physical functional tests. It never promotes display/touch/USB/Wi-Fi/Bluetooth/audio/modem/power/thermal/storage/recovery/hardware verification or Beta credit.
- Added fail-closed tests covering contextual acceptance, incomplete/empty survey rejection, identity drift, canonical JSON, exact file binding, safe template defaults and forbidden functional/Beta promotion.
- Extended `rescue-readonly-diagnostics` CI to compile and test the manual survey-review contract together with the existing rescue observation/diagnostic/survey layers.
- Added `docs/PHYSICAL_HARDWARE_SURVEY_REVIEW.md` and synchronized README/ROADMAP/BUILD_STATUS with SWIR README PRO v2 while keeping all release and compatibility claims unchanged.
- Project completion remains **58%** because no real AC2003 survey has been captured/reviewed and no subsystem has passed a physical functional test.

## 0.6.60-dev — bounded physical hardware-presence survey

- Added a separate `readonly-hardware-presence-v1` block to rescue userspace after the existing locked rescue diagnostic block.
- The automatic survey reads only bounded sysfs attributes for USB UDC/device identity, network-interface presence/state, rfkill presence/state, sound cards, thermal zones, input event names, framebuffer/DRM presence and power-supply state.
- The survey never activates radios/network/audio/display hardware, never reads input event streams, never mounts/decrypts/formats storage and never invokes Fastboot or persistent writes.
- Added `kaliphonestudio.physical_hardware_survey` schema-v1 evidence bound to one exact physical boot observation, exact rescue diagnostics digest, exact console transcript and exact rescue probe id.
- Presence flags (`usb_signal_observed`, `wifi_signal_observed`, etc.) are explicitly observational only. Display/touch/USB/Wi-Fi/Bluetooth/audio/modem/power/thermal/storage/recovery/hardware verification and Beta credit remain false and manual review is mandatory.
- Added immutable canonical evidence loading/writing plus `scripts/record_physical_hardware_survey.py` for offline recording; the CLI performs no phone I/O.
- Added focused fail-closed tests for exact transcript/cross-evidence binding, duplicate/out-of-block markers, malformed records, detached diagnostics, profile drift, forbidden verification promotion, empty-but-well-formed surveys and immutable round trips.
- Extended rescue init policy tests to prove the survey is bounded and contains no network/radio/audio activation commands.
- Project completion remains **58%** because no real AC2003 hardware survey has been captured or manually reviewed and no functional hardware/Beta gate is credited from host-side code.

## 0.6.59-dev — exact-file physical bring-up dossier

- Added `kaliphonestudio.physical_bringup_dossier` as a schema-v1 offline audit-packaging layer for one already-created `PhysicalBringupSessionEvidence`.
- The dossier verifies the canonical session file and every evidence/raw file named by that session: candidate gate, boot observation, rescue diagnostics, rescue functional probes, physical-storage discovery, manual storage review, raw rescue transcript, storage discovery report, recovery plan, review record and review notes.
- When the session contains Kali early-userspace evidence, both the exact evidence file and raw transcript become mandatory dossier members; missing, extra or role-drifted files fail closed.
- Added optional streaming verification of the exact reviewed rootfs artifact by SHA-256 and size without loading the full artifact into memory.
- All dossier inputs must be regular non-symlink files, remain unchanged while hashed and stay within role-specific safety limits; the resulting manifest is path-independent and records only role, size, SHA-256 and canonical-JSON policy.
- Added immutable dossier load/write validation and `scripts/build_physical_bringup_dossier.py`; the CLI performs no phone I/O, mount/decrypt operation, target selection or write authorization.
- Added nine focused tests covering exact binding, early-userspace file pairing, extra/missing roles, raw-file substitution, non-canonical session bytes, optional rootfs verification, symlink rejection, forbidden hardware/write promotion and immutable round-trip behavior.
- Extended `rootfs-handoff-policy` CI to compile/test the dossier together with the existing physical evidence chain and exact pinned layout source verification.
- Project completion remains **58%** because the dossier improves audit integrity only; no real AC2003 baseline, accepted physical storage review, reversible target, temporary boot or hardware gate has been completed.

## 0.6.58-dev — cross-bound physical bring-up evidence session

- Added `kaliphonestudio.physical_bringup_session` as a schema-v1 offline audit boundary across one exact physical-candidate gate, rescue boot observation, read-only diagnostics, explicitly authorized functional probes, physical-storage discovery and manual storage-review evidence chain.
- The binder fail-closes on profile/serial/firmware drift, detached candidate/discovery/review digests, mismatched rescue transcript/probe identity, rootfs authority/artifact drift, or storage report/recovery-plan substitution.
- Optional physical Kali early-userspace evidence can be attached only when its candidate manifest, reviewed authority bundle, rootfs authority and strict rootfs artifact identities match the same physical candidate/storage chain.
- Added immutable canonical session evidence and `scripts/bind_physical_bringup_session.py`; the CLI reads existing evidence only and contains no Fastboot/ADB, mount/decrypt, block-target selection or phone-write path.
- A session may mirror `accepted_for_strategy_design=true` from an exact completed manual storage review, but always forces `target_selected=false`, `storage_path_bound=false`, `write_authorized=false`, `handoff_ready=false`, all hardware verification flags false and `beta_gate_credit=false`.
- Added focused cross-layer tests, `docs/PHYSICAL_BRINGUP_SESSION.md`, and rootfs-handoff-policy CI coverage for the complete evidence-chain binder.
- Project completion remains **58%** because no real AC2003 baseline/storage review/temporary boot/hardware gate has been completed; this milestone improves evidence integrity only.

## 0.6.57-dev — fail-closed physical storage manual review

- Added `kaliphonestudio.physical_storage_review` with a schema-v1 manual-review record/evidence layer bound to one exact `PhysicalStorageDiscoveryEvidence` chain.
- Acceptance for later strategy design requires the source discovery to be review-ready plus explicit review of physical context, topology, filesystem identity, encryption, free space, recovery plan and evidence-chain integrity.
- Bound the exact original review-record bytes and separate review-notes bytes by SHA-256 and size, with TOCTOU checks, immutable evidence output and strict schema validation.
- Added `scripts/review_physical_storage_discovery.py` as an offline-only recorder. It cannot connect to a phone, select a device path, mount storage or authorize a write.
- Added focused tests for accepted/rejected review states, incomplete-source rejection, profile/serial drift, forbidden target/write claims, unsafe reviewer identifiers, exact-byte binding and immutable evidence.
- Extended `rootfs-handoff-policy` CI to compile and test the manual-review layer together with discovery and exact pinned layout-source verification.
- Aligned `README.md` with the current canonical **SWIR README PRO v2** standard: local 1200×320 electric-cyan project hero, unique KaliPhoneStudio phone/terminal icon, truthful status badges/table, quick navigation, Quick Start, compatibility, release/safety sections, mandatory Search Keywords and SWIR footer. Repository-contract tests verify the v2 marker and local SVG assets.
- Project completion remains **58%** because no real AC2003 physical storage record has been captured or reviewed, no reversible handoff target is approved and no physical temporary boot has passed the Beta gate.

## 0.6.56-dev — typed physical storage discovery evidence

- Added `kaliphonestudio.physical_storage_discovery` with a strict schema-v1 report/evidence layer for read-only physical storage discovery; it never carries a `/dev/...` target path, never selects a staging target and can never authorize a write.
- Bound every discovery record to one exact `RootfsHandoffAssessmentEvidence`, exact rescue diagnostics, exact manual functional-probe evidence, transcript/probe identity, firmware identity and reviewed rootfs authority chain.
- Whole-block topology observations must match the exact `KPS_DIAG_BLOCK` sysfs inventory from the bound rescue transcript by kernel name, sector count and removable bit; the expected UFS bus signal must also be present for review readiness.
- Added typed filesystem, encryption-feature and free-space observations for the profile-declared partition **role** only. The avicii `userdata` value remains a hint/role and is never converted into a block-device path.
- Added exact-byte SHA-256 binding for the operator discovery report and a separate recovery-plan text file. Complete categories can become `discovery_ready_for_manual_review=true`, but `target_selected`, `storage_path_bound`, `write_authorized`, `handoff_ready`, `storage_verified`, `recovery_verified`, `hardware_verified` and `beta_gate_credit` remain false.
- Added fail-closed parsing for unsafe names/paths, duplicate roles, inconsistent unknown observations, serial/profile drift, detached rescue evidence chains, changed files and promoted hardware/Beta claims.
- Added `scripts/record_physical_storage_discovery.py`, immutable evidence writing/loading, eight focused tests and rootfs-handoff-policy CI coverage.
- Project completion remains **58%** because this is an evidence contract only; no real AC2003 storage/encryption/free-space evidence or reversible handoff target has been reviewed yet.

## 0.6.55-dev — discovery-only rootfs handoff contract

- Added `kaliphonestudio.rootfs_handoff` with a fail-closed schema-v1 contract that resolves one exact profile-pinned storage-layout source and explicitly forbids target selection or persistent-write authorization.
- Added `RootfsHandoffAssessmentEvidence` binding one exact `PhysicalCandidateGateEvidence` to one exact reviewed `RootfsAuthorityRecord` while retaining `target_selected=false`, `storage_path_bound=false`, `write_authorized=false`, `handoff_ready=false`, `manual_review_required=true`, `hardware_verified=false` and `beta_gate_credit=false`.
- Added a source-lock verifier that requires a clean Git SHA-1 checkout at the exact pinned commit and verifies the exact profile-declared layout-file blob before emitting non-release evidence.
- The avicii profile records UFS, F2FS, `fileencryption=ice`, `wrappedkey` and metadata as **discovery expectations only**; `userdata` is a partition hint, not an approved rootfs target.
- Discovery policy requires physical block-topology, filesystem-identity, encryption-state, free-space and recovery-plan evidence, while all declared A/B/system partitions, `super` and metadata remain forbidden.
- Added focused tests for exact source binding, path/field hardening, forbidden-system coverage, rootfs-authority/candidate binding, immutable evidence, prior-device-action rejection and clean-checkout Git-object verification.
- Added `rootfs-handoff-policy` CI with an offline contract job plus a real exact-commit upstream layout-source verification job.
- Added `docs/ROOTFS_HANDOFF_POLICY.md`.
- Project completion remains **58%** because no physical AC2003 storage target has been discovered, selected or validated.

## 0.6.54-dev — exact Kali early-userspace identity proof

- Added `kaliphonestudio.kali_early_userspace` with a deterministic schema-v1 proof plan bound to the exact first-boot manifest, reviewed authority bundle, rootfs-authority binding, reviewed rootfs authority, strict ARM64 rootfs artifact SHA-256/size, ARM64 architecture and rootfs variant.
- Added a deterministic five-member USTAR overlay containing the canonical plan/probe id, hardened proof emitter, systemd oneshot unit and fixed relative activation link.
- Added exact runtime markers for stage, deterministic probe id, first-boot manifest digest, rootfs-authority digest and strict rootfs-artifact digest.
- Added `kaliphonestudio.physical_kali_early_userspace` to bind an operator-captured transcript to one successful non-persistent temporary-boot execution, one exact physical-candidate gate and one exact proof bundle.
- Marker matches remain manual-review-only and do not grant hardware/Beta credit.

## 0.6.53-dev — explicit read-only physical rescue probes

- Added manual-only, explicitly confirmed bounded rescue functional probes.
- Limited block-device reads to one 4096-byte read from up to eight non-removable whole block devices into `/dev/null`; no mount/repair/format/decrypt/write path is invoked.
- Added paired battery telemetry evidence without changing charging policy.
- Bound probe evidence to exact prior physical evidence while keeping storage, charging, hardware and Beta verification false pending manual review.

## 0.6.52-dev — read-only rescue diagnostics

- Added bounded rescue-side read-only sysfs inventory/telemetry and exact transcript binding.
- Kept all physical capability claims false until reviewed evidence from the real device exists.

## 0.6.51-dev — physical rescue boot markers

- Added deterministic rescue probe identity and exact console/kmsg markers bound to the rescue candidate.
- Added offline physical-boot observation evidence requiring exact markers from one successful non-persistent temporary boot.

## 0.6.50-dev and earlier

See [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) for the prior multi-device migration, provenance, rootfs/kernel/DT reproducibility, physical-candidate gate and temporary-boot safety work.
