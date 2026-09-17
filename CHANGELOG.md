# Changelog

This file tracks the current development line. Historical entries through **0.6.27-dev** remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md). The detailed pre-sync `0.6.28-dev`–`0.6.42-dev` active-line changelog remains permanently recoverable from repository commit `43e9836bfdca651ad31727a303714e44c44929db` and earlier Git history.

## 0.6.44-dev — ELF divergence classification and deterministic IKHEADERS archive policy

- Reviewed real kernel authority run `35177350001` as another **strict failure**, never as partial reproducibility credit. Both exact-source, source-mtime-normalized `jobs=1` builds produced identical final `.config` and equal 43,878,416-byte ARM64 Images, but 4,388,978 Image bytes still differed across 229,151 ranges from offset 302,366 through 43,633,488.
- The new 0.6.43 build-tree evidence narrowed that failure to only **20 differing selected artifacts out of 4,597**, including `kernel/kheaders.o`, compat-vDSO32 objects, kallsyms objects, `System.map`, `vmlinux.o` and `vmlinux`.
- Added fail-closed `kaliphonestudio.kernel_elf_diagnostics` plus an offline CLI. It parses only bounded ARM64 ELF64 little-endian candidates and classifies differences by executable, debug, metadata, relocation and data sections while rejecting unsafe paths, symlinks, malformed/non-AArch64 ELF and moving files.
- Chained ELF-section evidence directly after the existing build-tree diagnostic so a future strict failure automatically uploads both diagnostic layers. Diagnostic evidence always keeps `hardware_verified=false` and `beta_gate_credit=false`.
- Preserved `CONFIG_IKHEADERS`; reproducibility is **not** obtained by disabling it. Instead the avicii kernel plan now binds deterministic GNU tar order/mtime/uid/gid settings and single-threaded xz for upstream embedded-header archive generation.
- Added focused regression coverage for ELF parsing/classification, traversal/symlink rejection, wrong-machine rejection and deterministic embedded-header archive policy.
- PR #45 passed the full Python 3.11/3.12/3.13/3.14 matrix plus focused kernel/source-lock/ramdisk workflows before merge as `43e9836bfdca651ad31727a303714e44c44929db`.
- Real authority run `35181516724` is the first retry carrying the IKHEADERS policy and chained ELF diagnostics. Its result must be reviewed before any kernel reproducibility claim.
- Project completion remains **54%**. No physical AC2003 or Beta gate receives credit from these host-side changes.

## 0.6.43-dev — intermediate kernel build-tree diagnostics

- Reviewed run `35174347350`: exact compiler fetch/object verification, two independent source checkouts, source-mtime normalization and both `jobs=1` builds all completed, but strict Image equality failed.
- Both Images were 43,878,416 bytes; A SHA-256 `9e47fec369406363d480330d67731d08a785ea3afee641f3f9693d754018514f` differed from B SHA-256 `98d72fd8ca078c0f009d1f0b8f9c7f809eff8ded6748f75c6e15b1447be96689`.
- Image diagnostics counted 11,776,181 differing bytes across 998,609 contiguous ranges. Source-mtime normalization alone was therefore rejected as insufficient.
- Added bounded, path-independent comparison of `.config`, `vmlinux`, `System.map`, `Module.symvers`, final `Image`, `*.o` and `*.a` from two independent build roots.
- The diagnostic reports missing, size and content mismatches plus category totals and bounded SHA-256 evidence. It never changes strict acceptance and never grants hardware/Beta credit.
- PR #44 passed the full `tests` and focused `kernel-real-repro` contracts before merge as `37f43b388b20ebdb3eac89a63f7ae8e0106607f7`.

## 0.6.42-dev — local toolchain object proof for real kernel authority

- Correctly classified run `35170273612` as a **preflight infrastructure failure**, not a kernel result: the exact locked Android Clang subtree fetched and matched its tree, then a redundant second Gitiles metadata request returned HTTP 503 before either kernel build started.
- Added fail-closed local verification of the already-fetched compiler Git object graph: SHA-1 object format, exact HEAD, credential-free HTTPS origin, clean tracked state, exact subtree/bin/version/manifest object IDs and exact `AndroidVersion.txt` bytes.
- Removed only that redundant post-fetch network dependency from the expensive authority run while retaining independent Gitiles source-lock CI and materialized compiler byte/banner checks.
- Strict final `.config` + ARM64 `Image` byte equality remained unchanged.
- Project completion remained **54%**.

## 0.6.41-dev — evidence-bearing kernel source-mtime normalization

- Reviewed run `35166301228`: identical final `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3`, equal Image size, but 11,293,315 differing Image bytes across 897,561 ranges. Strict reproducibility remained false.
- Added fail-closed exact-HEAD/clean-tree normalization of only Git-tracked source mtimes to epoch 0, with canonical mode/blob/path evidence; `.git` and untracked files are excluded.
- Required independent A/B normalization evidence itself to be byte-identical before the build pair.
- Project completion remained **54%**.

## 0.6.40-dev — candidate-level reviewed rootfs authority binding

- Added a fail-closed candidate-level link from an exact schema-v8 first-boot manifest and raw-A/B/canonicalization provenance to one reviewed `RootfsAuthorityRecord`.
- Cross-checks reject detached manifest/provenance records and artifact/package/source/snapshot/canonicalization/raw-A/B substitution.
- The reviewed rootfs authority remains run `35158577624`, artifact SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, size 137,460,600 bytes, 269 packages.
- Host-side authority binding grants no hardware/Beta credit. Project completion remained **54%**.

## Earlier development

The repository Git history retains every previous active-line entry. Major foundations already completed before this file's current window include:

- strict/reviewed Kali ARM64 rootfs reproducibility and authority record,
- rootfs canonicalization and raw-A/B provenance binding,
- deterministic first-boot provisioning,
- deterministic rescue initramfs,
- profile-driven kernel/toolchain contracts,
- kernel compiler path remapping and Image diagnostics,
- exact OTA/stock-boot provenance and deterministic boot assembly,
- multi-device profile registry, identity/safety contracts and offline GUI/CLI.

See [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md) plus repository history for the detailed chronology.
