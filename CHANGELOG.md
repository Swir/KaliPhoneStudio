# Changelog

This file tracks the current development line. Historical detailed entries remain available in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) and Git history.

## 0.6.48-dev — exact physical-candidate preflight gate

- Added device-independent `PhysicalCandidateGateEvidence`, the final host-side cross-binding before a temporary-boot action may be offered.
- The gate requires one exact `PhysicalBaselineBundleEvidence`, schema-v8 `FirstBootCandidateManifest`, unified reviewed `FirstBootAuthorityBundleEvidence`, schema-v2 `TemporaryBootAuthorization`, selected device profile and exact `BootBuildPlan` to agree on profile, serial, firmware build/fingerprint, Fastboot baseline, stock OTA/boot identity, boot plan, candidate boot image, reviewed kernel/rootfs identities and profile-required DTB/DTBO inputs.
- Added profile-driven boot-layout validation: header/page/ramdisk/cmdline policy, required kernel/ramdisk/DTB/DTBO input set/order, input SHA-256/size/path sanity and boot-partition size limit are rechecked at the gate instead of hardcoding AC2003 rules in global code.
- Added fail-closed rejection for detached authority manifests, serial/firmware drift, stock-provenance substitution, boot-image substitution, kernel/DT drift, malformed evidence, unsafe input paths and any host evidence that claims physical execution or Beta/hardware success.
- Added immutable `scripts/bind_physical_candidate_gate.py` for loading typed evidence and writing the gate. It performs no ADB/Fastboot operation and explicitly reports `temporary_boot_executed=false`, `phone_storage_written=false`, `hardware_verified=false`, `beta_gate_credit=false`.
- Added focused negative/positive tests covering exact binding, serial drift, detached authority bundle, stock provenance drift, candidate boot drift, kernel input drift, profile-layout drift and immutable/no-hardware-claim output policy.
- Project completion remains **58%** because no new physical AC2003 gate has passed. Beta remains blocked pending real baseline capture, matching stock boot and physical bring-up.

## 0.6.47-dev — reviewed strict DTB/DTBO authority and unified candidate provenance

- Completed real DT authority run `35196447576` as strict success for profile-selected avicii DT artifacts from two independent exact-source roots.
- Accepted `lito.dtb` SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`, raw `avicii-overlay.dtbo` SHA-256 `b3991f2fda96d3675778299b45b9802823022ef25d593c5d00c756ceea35b90c`, and packed `dtbo.img` SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895`.
- Added reviewed immutable DT authority record and checked-in exact evidence chain tied to the reviewed kernel authority.
- Added unified first-boot authority bundle requiring reviewed kernel/rootfs/DT candidate bindings to refer to the exact same schema-v8 manifest/profile.
- Added exact Fastboot executable/capture evidence and physical Fastboot + exact stock OTA/boot provenance bundle; these remain host-side and do not authorize boot.
- Hardened OTA metadata parsing and stock provenance against malformed/ambiguous metadata, unsafe ZIP paths and TOCTOU drift.
- Project completion advanced to **58%** for the reviewed DT authority milestone; no physical AC2003 or Beta credit was granted.

## 0.6.46-dev — reviewed strict kernel authority and candidate binding

- Reviewed kernel run `35183670399` as the first strict success for `oneplus/avicii`: two independent exact-source builds produced byte-identical final `.config` and 43,878,416-byte ARM64 `Image`.
- Accepted `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3` and Image SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`.
- Added fail-closed reviewed `KernelAuthorityRecord`, checked exact execution/reproducibility evidence and candidate-level authority binding.
- Project completion advanced to **56%** for the strict kernel authority milestone; hardware/Beta remained blocked.

## 0.6.45-dev — compat-vDSO path normalization

- Reviewed run `35181516724` as strict failure with only 16 Image bytes remaining different after deterministic IKHEADERS.
- Traced remaining target-linked drift to ARM32 compat-vDSO objects and bound recursive source/output prefix maps into the profile compiler path.
- Extended target ELF diagnostics for ARM32 compat-vDSO evidence.
- The next run `35183670399` proved the policy removed the final observed kernel nondeterminism.

## Earlier development

Git history and [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) retain the detailed chronology for multi-device migration, boot/OTA provenance, rootfs authority, rescue/provisioning foundations, kernel reproducibility experiments and diagnostics.
