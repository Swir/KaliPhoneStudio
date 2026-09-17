# Changelog

Active development changes are listed here. Older detailed entries remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md).

## 0.6.54-dev — exact Kali early-userspace identity proof

- Added `kaliphonestudio.kali_early_userspace` with a deterministic schema-v1 proof plan bound to the exact first-boot manifest, reviewed authority bundle, rootfs-authority binding, reviewed rootfs authority, strict rootfs artifact SHA-256/size, ARM64 architecture and rootfs variant.
- Added a deterministic five-member USTAR overlay containing the canonical plan/probe id, hardened proof emitter, systemd oneshot unit and fixed relative activation link. Bundle member order/type/mode/uid/gid/mtime/link target/content and final SHA-256/size are re-verified after build.
- Added exact runtime markers for stage, deterministic probe id, first-boot manifest digest, rootfs-authority digest and strict rootfs-artifact digest.
- Added `kaliphonestudio.physical_kali_early_userspace` to bind an operator-captured transcript to one successful non-persistent temporary-boot execution, one exact physical-candidate gate and one exact proof bundle.
- Transcript validation fails closed on missing/conflicting/excessive markers, profile/serial drift, candidate/authority/rootfs drift, changed files, failed temporary boot or persistent-write claims.
- A marker match records strong identity-scoped signals but deliberately retains `kali_early_userspace_verified=false`, `manual_review_required=true`, `hardware_verified=false` and `beta_gate_credit=false`.
- Added focused Python 3.14 `kali-early-userspace-proof` CI plus nine contract tests covering authority binding, deterministic archive bytes, immutable evidence, tamper rejection and physical-marker safety semantics.
- Added `docs/KALI_EARLY_USERSPACE_PROOF.md` and explicitly documented that 0.6.54 does **not** implement or assume a rootfs transport/staging path.
- Project completion remains **58%** because no new physical AC2003 gate was satisfied.

## 0.6.53-dev — explicit read-only physical rescue probes

- Added manual-only, explicitly confirmed bounded rescue functional probes.
- Limited block-device reads to one 4096-byte read from up to eight non-removable whole block devices into `/dev/null`; no mount/repair/format/decrypt/write path is invoked.
- Added paired battery telemetry evidence without changing charging policy.
- Bound probe evidence to the exact prior physical observation/read-only diagnostics/transcript while keeping storage, charging, hardware and Beta verification false pending manual review.

## 0.6.52-dev — read-only rescue diagnostics

- Added bounded rescue-side read-only sysfs inventory/telemetry and exact transcript binding.
- Kept all physical capability claims false until reviewed evidence from the real device exists.

## 0.6.51-dev — physical rescue boot markers

- Added deterministic rescue probe identity and exact console/kmsg markers bound to the rescue candidate.
- Added offline physical-boot observation evidence requiring exact markers from one successful non-persistent temporary boot.

## 0.6.50-dev and earlier

See [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) for the prior multi-device migration, provenance, rootfs/kernel/DT reproducibility, physical-candidate gate and temporary-boot safety work.
