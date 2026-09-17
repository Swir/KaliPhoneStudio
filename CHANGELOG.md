# Changelog

Active development changes are listed here. Older detailed entries remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md).

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
- Added an avicii profile policy pinned to LineageOS `android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13`, `init/fstab.qcom` blob `20873c3a84e1e6e8d2483e313f561ad35ded7355`.
- The avicii profile records UFS, F2FS, `fileencryption=ice`, `wrappedkey` and metadata as **discovery expectations only**; `userdata` is a partition hint, not an approved rootfs target.
- Discovery policy requires physical block-topology, filesystem-identity, encryption-state, free-space and recovery-plan evidence, while all declared A/B/system partitions, `super` and metadata remain forbidden.
- Added focused tests for exact source binding, path/field hardening, forbidden-system coverage, rootfs-authority/candidate binding, immutable evidence, prior-device-action rejection and clean-checkout Git-object verification.
- Added `rootfs-handoff-policy` CI with an offline contract job plus a real exact-commit upstream layout-source verification job.
- Added `docs/ROOTFS_HANDOFF_POLICY.md`.
- Project completion remains **58%** because no physical AC2003 storage target has been discovered, selected or validated.

## 0.6.54-dev — exact Kali early-userspace identity proof

- Added `kaliphonestudio.kali_early_userspace` with a deterministic schema-v1 proof plan bound to the exact first-boot manifest, reviewed authority bundle, rootfs-authority binding, reviewed rootfs authority, strict rootfs artifact SHA-256/size, ARM64 architecture and rootfs variant.
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
