# Changelog

Active development changes are listed here. Older detailed entries remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md).

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
