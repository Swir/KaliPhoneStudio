# Changelog

Historical development entries through **0.6.27-dev** are preserved verbatim in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md). This file contains the active development line.

## 0.6.40-dev — candidate-level reviewed rootfs authority binding

- Added `FirstBootRootfsAuthorityEvidence`, a fail-closed host-side link from an exact schema-v8 first-boot manifest and its schema-v1 rootfs canonicalization/raw-A/B provenance to one reviewed `RootfsAuthorityRecord`.
- Candidate/authority binding cross-checks the first-boot manifest digest, candidate rootfs-provenance digest, reviewed authority digest/name/run/commit/artifact identity, strict rootfs evidence, artifact SHA-256/size, package manifest/count, source lock, signed repository snapshot, canonicalization binding/policy, both A/B transformation records and both raw A/B input identities.
- The binding rejects a detached manifest/provenance record, artifact/package/source/snapshot/canonicalization/raw-A/B substitution, unreviewed authority records and any host evidence attempting to claim physical hardware or Beta credit.
- Added canonical atomic evidence writing plus focused substitution/detachment/overwrite regression coverage. Initial CI correctly caught one test that mutated the manifest and was rejected earlier by the detached-provenance guard than the intended size-mismatch layer; the regression was corrected to exercise the target layer without weakening implementation checks.
- The first real reviewed rootfs authority remains run `35158577624`, accepted artifact SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, 269 packages. This new contract does not instantiate a physical AC2003 candidate and grants no hardware/Beta credit.
- Kept project completion at **54%** because this is provenance hardening; physical AC2003 baseline/boot/hardware/recovery gates remain unresolved.

## 0.6.39-dev — reviewed ARM64 rootfs authority and serial kernel reproducibility retry

- Reviewed real `rootfs-repro` authority run `35158577624` after completion: both independently built/canonicalized Kali ARM64 rootfs outputs passed strict byte equality, normalized package-manifest equality and canonicalization-provenance binding.
- Accepted the first concrete host-side reproducible rootfs artifact: SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, size `137460600`, package-manifest SHA-256 `11a3609a23c263c43794414b7b2f2e587133fb247c2a146321c0bdef55db3fbd`, 269 packages.
- Added `RootfsAuthorityRecord` plus `evidence/authorities/kali-arm64-rootfs-2026.2-minimal.json`, binding exact authority run/commit/artifact IDs, source lock, GPG-verified repository snapshot and `InRelease`, strict rootfs evidence, both raw A/B inputs, canonicalization policy and both canonicalization records.
- Added fail-closed authority loading/verification, an offline `scripts/verify_rootfs_authority.py` CLI and tamper regression tests. Authority evidence explicitly requires `reviewed=true`, `strict_byte_identical=true`, `hardware_verified=false` and `beta_gate_credit=false`.
- Reviewed real kernel authority run `35161227840` as another strict failure: final `.config` SHA-256 was identical and Image size matched at `43878416`, but Image SHA-256 differed. Diagnostics counted `11695369` differing bytes across `960780` ranges, from offset `73` through `43876937`; no kernel reproducibility credit was granted.
- Changed the next real kernel authority experiment to keep independent A/B builds concurrent while forcing each internal vendor-kernel make graph to `jobs=1`, isolating parallel build-order nondeterminism without weakening provenance. The jobs value is already part of the canonical build recipe.
- Synchronized package version, README, ROADMAP and BUILD_STATUS. Project completion moves conservatively from 52% to **54%** for the reviewed reproducible rootfs milestone; no physical AC2003/Beta gate is credited.

## 0.6.38-dev — deterministic generic first-boot provisioning

- Added a device-independent `FirstBootProvisioningPlan` bound to typed, reproducible ARM64 rootfs evidence; malformed hashes/counts/sizes, unsafe hostname/locale/timezone values and non-reproducible/non-ARM64 evidence fail closed.
- Added a deterministic USTAR provisioning overlay containing only hostname, locale, timezone, a systemd preset disabling Dropbear/OpenSSH units and the canonical provisioning manifest.
- Provisioning requires interactive local user creation, keeps the root password locked, accepts/embeds no password/hash/private key and keeps remote access disabled by default.
- Added independent bundle verification for exact SHA-256/size, rootfs/plan binding, member set/order, canonical uid/gid/owner/mode/mtime and exact payload bytes; bundle/evidence outputs refuse overwrite.
- Added `scripts/build_first_boot_provisioning.py` for offline generation with machine-readable safety output and direct-script import hardening.
- Initial CI correctly exposed two regression assumptions (the manifest legitimately contains the `root_password_locked` policy field and `PurePosixPath` normalizes duplicate slashes); both were repaired in the same iteration and the regression suite was expanded.
- Added end-to-end CLI coverage and synchronized README, ROADMAP, BUILD_STATUS and package version. Project completion remains 52% because no physical AC2003 hardware gate is credited.

## 0.6.37-dev — candidate-level rootfs canonicalization provenance

- Added `FirstBootRootfsProvenanceEvidence`, a fail-closed host-side link from the exact schema-v8 first-boot manifest digest to the strict rootfs evidence and accepted canonicalization binding.
- The link carries the reviewed canonicalization-policy digest, both A/B canonicalization evidence digests, both raw rootfs input SHA-256/size pairs, canonical artifact SHA-256/size, package-manifest evidence, source lock and signed repository snapshot.
- Cross-checks reject candidate artifact/package/source/snapshot substitution, detached or mutated A/B transformation records, unknown policy digests, non-strict bindings and any host evidence attempting to claim Beta credit.
- Added atomic non-overwriting evidence output and regression coverage across Python 3.11/3.12/3.13/3.14.
- Tightened `BETA_RELEASE_GATE.md`: a future release candidate must keep canonicalization/raw-build provenance cryptographically attached to the exact first-boot manifest; this does not satisfy any physical-device gate.
- Synchronized README, ROADMAP, BUILD_STATUS and package version. Project completion remains 52% because this is provenance hardening only.

## 0.6.36-dev — actionable kernel Image divergence diagnostics and profile-hook status

- Added bounded streaming kernel `Image` A/B diagnostics that report exact differing-byte count, contiguous differing ranges, first/last differing offsets and SHA-256/size without loading full Images into memory.
- Diagnostics reject symlinks, same-file inputs and invalid bounds, cap reported ranges while preserving exact total counts, and always carry `beta_gate_credit=false` / `hardware_verified=false`.
- Wired diagnostics into the real strict kernel workflow only after equality failure; strict byte-identical acceptance remains unchanged.
- Recorded real authority run `35157574186` as a strict failure: identical final `.config` and equal Image size, but unequal Image SHA-256 values.
- Reconciled the already-merged fail-closed profile-hook registry into README/ROADMAP/BUILD_STATUS and marked generic profile hooks implemented.
- PR #37 passed the full branch test workflow and was merged as `58a0d24c830ce43dcfded984658279e55224d70f`; post-merge main tests run `35161227859` passed and a fresh real kernel authority run `35161227840` started.
- Project completion remains 52%; no hardware or Beta gate is credited.

## 0.6.35-dev — restored application entrypoint and safe offline profile studio

- Restored the missing `kaliphonestudio.app` module consumed by `main.py`; the normal desktop entrypoint is no longer an import-time dead end.
- Added a device-independent offline profile catalog backed by the same schema-validated `devices/<vendor>/<codename>/profile.json` registry used by the core.
- Added a PySide6 offline profile selector that exposes device identity, boot/kernel policy, pinned upstream sources, host/hardware test contracts and recovery notes without invoking `adb`, `fastboot` or any write/flash path.
- Added CLI/JSON profile inspection with `--list-profiles`, `--profile-id` and `--json`; machine-readable profile inspection explicitly reports `hardware_verified=false` and `beta_gate_credit=false`.
- Kept PySide6 lazy-loaded so CLI/imports and the minimal Python CI matrix remain usable when Qt is not installed.
- Added regression coverage for profile discovery, deterministic JSON output, fail-closed unknown profiles and Qt-free application import.
- The first PR run correctly exposed a repository-contract mismatch between `__version__` and `BUILD_STATUS.json` (275 tests passed, one failed); the mismatch was fixed in the same development iteration and the final PR #34 Python 3.11/3.12/3.13/3.14 matrix passed before merge.
- PR #34 was merged as `17b3d6ef64c3efcf9e90f49caa54cc8de839b237`; post-merge main test run `35159240894` also passed.
- Project completion remains 52%; this host-side usability milestone grants no physical AC2003/Beta credit.

## 0.6.34-dev — rootfs canonicalization provenance binding

- Closed the provenance gap between reviewed rootfs canonicalization and strict reproducibility evidence.
- Both independent A/B canonicalization audit records are now bound to their raw input SHA-256/size, the exact rootfs source lock, the GPG-verified repository snapshot and the strict accepted canonical artifact.
- Added an explicit versioned canonicalization-policy digest so future policy changes cannot silently inherit older evidence.
- Added fail-closed schema parsing/accounting and cross-record consistency checks for canonicalization evidence.
- Wired the binding into the real `rootfs-repro` workflow only after strict byte/package equality succeeds; the binding is uploaded alongside accepted non-release rootfs evidence.
- Strict acceptance is unchanged: canonicalization audit/binding evidence can never substitute for byte-identical A/B output or matching package evidence and always grants no hardware/Beta credit.
- Merged as `763763b886a9d272d82db115e1db8d9c49e4ae04` via PR #33.

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
