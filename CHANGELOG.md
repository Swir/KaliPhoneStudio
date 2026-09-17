# Changelog

Active development changes are listed here. Older detailed entries remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md).

## 0.6.57-dev — explicit human physical-storage review gate

- Added `kaliphonestudio.physical_storage_review` as a fail-closed boundary between typed physical discovery and any future rootfs staging proposal.
- Added `PhysicalStorageReviewRecord` and `PhysicalStorageReviewEvidence`, binding one exact reviewer decision to the exact physical-storage discovery evidence, raw discovery-report digest, recovery-plan digest, device identity, physical candidate and reviewed rootfs chain.
- `approve_for_strategy_design` is accepted only when the bound discovery evidence is already `discovery_ready_for_manual_review=true`; `reject` can record a negative review without granting any strategy permission.
- Approval can only set `strategy_design_allowed=true`. `target_selected`, `storage_path_bound`, `write_authorized`, `handoff_ready`, `storage_verified`, `recovery_verified`, `phone_storage_written`, `hardware_verified` and `beta_gate_credit` remain false.
- Added exact required reviewer attestation, bounded reviewer identifiers, exact-byte review-record SHA-256/size binding, symlink/TOCTOU hardening and immutable output writes.
- Added `scripts/record_physical_storage_review.py`, focused tests and `rootfs-handoff-policy` CI coverage.
- Added `docs/PHYSICAL_STORAGE_REVIEW_GATE.md` with the exact review-record schema and offline usage.
- Updated README to the canonical SWIR README PRO structure, including centered electric-cyan hero/badges, clearer compatibility/safety/release sections, mandatory Search Keywords and SWIR footer without changing hardware/release claims.
- Project completion remains **58%** because no real AC2003 storage discovery has been reviewed and no reversible rootfs target has been selected or tested.

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
