# Changelog

This file tracks the current development line. Historical detailed entries remain available in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) and Git history.

## 0.6.50-dev — fresh runtime revalidation before one temporary boot

- Added device-independent `TemporaryBootRuntimeProbeEvidence` and `TemporaryBootExecutionEvidence` for the first real physical temporary-boot attempt path.
- The execution path re-runs exact offer verification immediately before use, so the concrete reviewed Fastboot executable and candidate `boot.img` are rehashed again and must still match the physical-candidate gate.
- Explicit `TemporaryBootUserAuthorizationEvidence` is mandatory and must bind the exact offer/profile/serial/confirmation policy while still containing no prior execution/write/hardware/Beta claim.
- Added a fresh read-only serial-bound `fastboot devices` + `getvar all` runtime probe before the boot command. Critical product, serial, active slot, slot count, unlock/security state and bootloader/baseband identities must remain equal to the reviewed baseline; device swap or state drift fails closed before `boot` is invoked.
- The baseline must report an unlocked bootloader and the fresh runtime probe must still report it unlocked.
- The only executable command remains one argv-only `fastboot -s SERIAL boot IMAGE`; no shell string and no `flash`, `erase`, `set_active`, `reboot` or persistent-write path is exposed.
- Normal Fastboot command failure is preserved as immutable execution evidence rather than being misreported as hardware failure/success. Even a return code 0 records only command acceptance: `kali_userspace_verified=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- Added immutable probe/execution evidence writers plus `scripts/execute_temporary_boot_once.py`. The CLI refuses to act unless `--execute-temporary-boot` and the exact profile confirmation are both supplied.
- Added focused tests for read-only runtime revalidation, exact serial-bound boot invocation, device swap, unlock/slot drift, detached authorization, local image TOCTOU drift, normal Fastboot failure evidence and immutable outputs.
- Kept project completion at **58%** because no physical AC2003 boot/hardware gate has actually passed. Beta remains blocked.

## 0.6.49-dev — exact temporary-boot offer, no execution

- Added device-independent `TemporaryBootOfferEvidence` and `PreparedTemporaryBootOffer` as the last host-local file-identity boundary before an explicitly confirmed physical temporary boot.
- Offer preparation requires the exact schema-v1 physical-candidate gate, exact read-only Fastboot capture bundle and exact `FastbootToolEvidence` that originally produced that capture.
- The concrete Fastboot executable is rehashed byte-for-byte and must still match reviewed filename/SHA-256/size/version evidence; there is no PATH fallback.
- The concrete candidate `boot.img` is rehashed byte-for-byte and must exactly match the physical-candidate gate SHA-256/size and remain within the selected profile's boot partition limit.
- The only generated command is an argv tuple equivalent to `fastboot -s SERIAL boot IMAGE`; no shell command is constructed and no subprocess is invoked.
- Added `TemporaryBootUserAuthorizationEvidence`. Exact profile-specific confirmation is required before an offer may be marked execution-permitted, but this still records `temporary_boot_executed=false`, `persistent_write=false`, `phone_storage_written=false`, `hardware_verified=false`, and `beta_gate_credit=false`.
- Added immutable `scripts/prepare_temporary_boot_offer.py`; it only loads exact evidence/files, persists offer evidence and prints an argv preview explicitly marked NOT EXECUTED.
- Added focused tests covering exact command preparation, detached capture rejection, Fastboot-byte drift, candidate-image drift, profile partition limits, profile/gate drift, exact confirmation and immutable writer behavior.
- Kept project completion at **58%** because no new physical AC2003 gate passed. Beta remains blocked.

## 0.6.48-dev — exact physical-candidate preflight gate

- Added device-independent `PhysicalCandidateGateEvidence`, the final artifact-level host cross-binding before a temporary-boot action may be offered.
- The gate requires one exact `PhysicalBaselineBundleEvidence`, schema-v8 `FirstBootCandidateManifest`, unified reviewed `FirstBootAuthorityBundleEvidence`, schema-v2 `TemporaryBootAuthorization`, selected device profile and exact `BootBuildPlan` to agree on profile, serial, firmware, Fastboot baseline, stock OTA/boot, candidate boot image, reviewed kernel/rootfs identities and profile-required DTB/DTBO inputs.
- Added immutable host-only CLI output and negative/positive tests. No ADB/Fastboot operation is performed and no hardware/Beta credit is granted.
- Fixed a post-merge integration regression exposed by `device-tree-real-repro`: restored immutable reviewed authority commit/artifact IDs in `BUILD_STATUS.json` and added a repository contract that keeps status identities synchronized with checked-in authority records.
- Project completion remained **58%**.

## 0.6.47-dev — reviewed strict DTB/DTBO authority and unified candidate provenance

- Completed real DT authority run `35196447576` as strict success for profile-selected avicii DT artifacts from two independent exact-source roots.
- Accepted `lito.dtb` SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`, raw `avicii-overlay.dtbo` SHA-256 `b3991f2fda96d3675778299b45b9802823022ef25d593c5d00c756ceea35b90c`, and packed `dtbo.img` SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895`.
- Added reviewed immutable DT authority record, unified first-boot authority bundle, exact Fastboot executable/capture evidence and physical Fastboot + stock OTA/boot provenance bundle.
- Hardened OTA metadata and stock provenance against malformed/ambiguous metadata, unsafe ZIP paths and TOCTOU drift.
- Project completion advanced to **58%** with no physical/Beta credit.

## 0.6.46-dev — reviewed strict kernel authority and candidate binding

- Reviewed kernel run `35183670399` as the first strict success for `oneplus/avicii`: two independent exact-source builds produced byte-identical final `.config` and 43,878,416-byte ARM64 `Image`.
- Accepted `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3` and Image SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`.
- Added fail-closed reviewed `KernelAuthorityRecord`, checked exact execution/reproducibility evidence and candidate-level authority binding.
- Project completion advanced to **56%**; hardware/Beta remained blocked.

## Earlier development

Git history and [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) retain the detailed chronology for multi-device migration, boot/OTA provenance, rootfs authority, rescue/provisioning foundations, kernel reproducibility experiments and diagnostics.
