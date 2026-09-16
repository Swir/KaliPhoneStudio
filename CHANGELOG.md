# Changelog

Historical development entries through **0.6.27-dev** are preserved verbatim in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md). This file contains the active development line.

## 0.6.30-dev — first-boot execution provenance binding

- Upgraded the host-side first-boot candidate contract to schema v8.
- A candidate now requires `KernelReproducibilityBindingEvidence`, not only output-level kernel reproducibility and compiler provenance.
- The execution binding must match the exact profile, kernel-plan digest, source commit, toolchain-lock digest and strict reproducibility-evidence digest.
- Final `.config` and ARM64 `Image` SHA-256/size must agree across kernel candidate evidence, strict reproducibility evidence and executed-build binding evidence.
- Schema-v8 manifests carry the canonical kernel build-recipe digest, reproducibility-environment digest and both A/B build-run evidence digests so release-candidate provenance cannot silently detach from the builds that produced the accepted bytes.
- Added fail-closed regression coverage for reproducibility-digest drift, toolchain substitution, incomplete independent-build equality and host evidence attempting to claim hardware/Beta credit.
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
