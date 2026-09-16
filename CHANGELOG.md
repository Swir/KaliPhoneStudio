# Changelog

Historical development entries through **0.6.27-dev** are preserved verbatim in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md). This file contains the active development line.

## 0.6.33-dev — rootfs volatile-state canonicalization and kernel path remapping

- Reviewed the latest real Kali ARM64 A/B failure instead of guessing: both builds had identical normalized 269-package manifests, no type/order/add/remove drift, exactly five changed payload files and 4817 metadata differences, all mtime-only.
- Added a device-independent, no-extraction rootfs canonicalization stage that normalizes archive mtimes, clears `etc/machine-id`, D-Bus machine-id and fake-clock state, locks generated password hashes without introducing a shared deterministic password, and omits only the regenerable `ldconfig` auxiliary cache.
- The canonicalizer validates safe archive paths/layout, rejects duplicate/ambiguous members, preserves unrelated payloads and PAX security/xattr metadata, and emits per-build audit evidence with `beta_gate_credit=false`.
- Strict rootfs acceptance is unchanged: post-canonicalization A/B archives must still be byte-identical and their normalized installed-package evidence must match.
- Reviewed real kernel run `35151043468`: both exact-source builds used the same locked compiler/recipe and produced identical final `.config` plus equal-size ARM64 `Image` files, but the Image bytes differed.
- The pinned defconfig enables `CONFIG_DEBUG_INFO`; the exact-source runner now maps independent A/B source/output paths to fixed virtual roots with Clang `-fdebug-prefix-map`, `-fmacro-prefix-map` and `KBUILD_ABS_SRCTREE=0`, with the remap policy bound into reproducibility-environment evidence.
- Added focused regression tests for both rootfs canonicalization and kernel path remapping. PR #31 passed the full Python 3.11/3.12/3.13/3.14 matrix plus rootfs/kernel contract workflows before merge as `6f02c69b13ad8a156bc95d66a6374dd6eb64c972`.
- Real post-merge A/B kernel/rootfs runs remain authoritative for artifact acceptance. Project completion stays at 52% and no physical AC2003/Beta gate is credited.

## 0.6.32-dev — actionable rootfs divergence diagnostics

- Upgraded non-release rootfs divergence diagnostics to schema v2 after the real A/B rootfs run exposed a small number of payload changes mixed with thousands of metadata differences.
- Bounded diagnostic output now prioritizes type/content/add/remove/order differences ahead of metadata noise so changed payload files cannot be hidden merely by earlier path-sorted mtime differences.
- Added explicit per-field metadata counters plus an `mtime`-only counter to separate broad build-time timestamp drift from ownership/mode/link/PAX differences.
- Added reported/omitted counts by difference kind so a truncated diagnostic is itself auditable and operators know exactly which classes were omitted.
- Added regression coverage proving content changes remain visible under a strict output cap even when many files differ only by mtime.
- Strict rootfs acceptance is unchanged: only byte-identical independent builds plus matching package evidence can produce reproducibility evidence; diagnostics always keep `beta_gate_credit=false`.
- Project completion remains 52% because this is host-side diagnosis/hardening and does not satisfy a physical AC2003 gate.

## 0.6.31-dev — deterministic profile-required kernel config policy

- Made the exact-source kernel runner apply the profile-bound required `CONFIG_*` policy before the guarded build rather than only validating the final `.config` afterward.
- Added `CONFIG_RD_LZ4=y` for the `oneplus/avicii` profile so a future accepted kernel is capable of consuming the profile-required LZ4 rescue/initramfs payload.
- Disabled engineering module signing in the host bring-up policy (`CONFIG_MODULE_SIG=n`, `CONFIG_MODULE_SIG_FORCE=n`) to remove an unsourced build-time signing-key path from reproducibility-sensitive output.
- Added deterministic required-config fragment generation, `scripts/config` application and `olddefconfig` normalization with fail-closed checks for invalid/duplicate policy entries.
- Added focused compatibility/policy tests. The first test revision exposed a bad `DeviceProfile` accessor and was corrected in the same development iteration before merge.
- Full Python 3.11/3.12/3.13/3.14 CI passed before PR #28 was merged as `e7cadeaad668a1794d224ccd83456eb4579a04e1`.
- The expensive real post-merge A/B kernel build remains non-release evidence until strict equality and execution-provenance binding finish and are reviewed.

## 0.6.30-dev — first-boot execution provenance binding

- Upgraded the host-side first-boot candidate contract to schema v8.
- A candidate now requires `KernelReproducibilityBindingEvidence` **and both exact `KernelBuildRunEvidence` records**, not only output-level kernel reproducibility and compiler provenance.
- The candidate re-hashes the supplied A/B run records and requires those digests to equal the execution binding; a substituted run record therefore fails closed even when final kernel bytes happen to match.
- Both run records are cross-checked against the accepted profile, kernel-plan digest, source commit, checkout evidence, toolchain lock, compiler-selection evidence, materialized compiler evidence, canonical build recipe and reproducibility environment.
- Each run's config/Image verification-evidence digest and final SHA-256/size must agree with strict reproducibility evidence and `KernelCandidateEvidence`, closing the remaining summary-only provenance gap.
- Schema-v8 manifests carry the execution-binding digest, canonical build-recipe/environment digests and both A/B build-run evidence digests so release-candidate provenance cannot silently detach from the builds that produced the accepted bytes.
- Added fail-closed regression coverage for run-record substitution, checkout drift, reproducibility-digest drift, toolchain substitution, incomplete independent-build equality and host evidence attempting to claim hardware/Beta credit.
- Updated README, ROADMAP, BUILD_STATUS and `BETA_RELEASE_GATE.md`; project completion intentionally remains 52% because this milestone is host-side provenance hardening only.
- Real kernel run `35146536390` and real rootfs run `35142328320` remain authoritative and are not credited until their strict final verification completes and evidence is reviewed.

## 0.6.29-dev — real source-locked kernel execution and provenance

- Added a device-independent exact-source kernel build runner for the profile-driven `KernelBuildPlan` and immutable Android Clang toolchain.
- The runner records a canonical build recipe and deterministic reproducibility environment rather than trusting CI shell history as build provenance.
- Added real two-build kernel CI using independent exact-source checkout/build roots and the materialized source-locked compiler; strict `.config` and ARM64 `Image` equality remains mandatory.
- Added canonical per-build `KernelBuildRunEvidence` binding plan, source, toolchain, checkout, compiler binding, materialized compiler, recipe/environment and final config/Image evidence.
- Added `KernelReproducibilityBindingEvidence` to close the output-to-execution provenance gap: both A/B build records must agree on exact plan/source/toolchain/recipe/environment and the final bytes accepted by strict reproducibility verification.
- PR #25 passed its focused/full host checks before merge as `1ebf97eaa2840408ea26f155166d550a0a7d3d1f`.
- No concrete reproducible kernel or AC2003 hardware gate is claimed until the expensive post-merge main run completes and its evidence is reviewed.

## 0.6.28-dev — compiler evidence bound into first-boot candidates

- Bound immutable Android Clang source evidence, exact kernel checkout/build-config compiler selection and materialized `clang` SHA-256/banner evidence into one canonical toolchain-candidate contract.
- Hardened first-boot candidates so compiler source, build configuration and concrete compiler bytes must resolve to the same profile-driven kernel plan.
- Rejected source-object drift, plan/profile/source substitution, different toolchain locks, invalid compiler bytes/banner evidence and host evidence claiming physical Beta credit.
- Kept the project at 52% because compiler provenance does not replace real kernel/rootfs reproducibility or physical-device validation.