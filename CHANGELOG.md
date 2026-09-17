# Changelog

This file tracks the current development line. Historical entries through **0.6.27-dev** remain in [`CHANGELOG_HISTORY.md`](CHANGELOG_HISTORY.md). The detailed pre-sync `0.6.28-dev`–`0.6.42-dev` active-line changelog remains permanently recoverable from repository commit `43e9836bfdca651ad31727a303714e44c44929db` and earlier Git history.

## 0.6.47-dev — reviewed strict DTB/DTBO authority and unified candidate provenance

- Completed real DT authority run `35196447576` as the first **strict SUCCESS** for profile-selected avicii device-tree artifacts. Two independent exact-source roots produced byte-identical `arch/arm64/boot/dts/vendor/20801/lito.dtb`, raw `avicii-overlay.dtbo` and packed `dtbo.img` while retaining the exact reviewed kernel authority as an input.
- Accepted DTB SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce` (406,620 bytes), raw overlay SHA-256 `b3991f2fda96d3675778299b45b9802823022ef25d593c5d00c756ceea35b90c` (345,405 bytes), and packed DTBO SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` (352,256 bytes, one entry).
- Fixed reuse of historical accepted kernel artifact `10482645697`: GitHub Actions had omitted hidden `.config` files even though both accepted ARM64 Images and the full reviewed evidence chain were intact. KaliPhoneStudio now deterministically rehydrates only the exact final config from pinned source/profile/toolchain policy, verifies its SHA-256/size against the immutable kernel authority, and verifies the existing Image remains unchanged. The kernel Image is never rebuilt by this path.
- Added fail-closed `ReviewedKernelBuildRootEvidence` plus focused tests covering rehydration, verification-only reuse, recipe drift and config substitution.
- Added and reviewed `DeviceTreeAuthorityRecord` for run `35196447576`, main commit `50a10688a20e3189b97291426118e7d0c466e108` and workflow artifact `10486420567`.
- Preserved exact DT plan, build-A/build-B, strict reproducibility, config-rehydration, source-normalization and toolchain evidence under `evidence/authorities/device-tree/oneplus-avicii-2026-09-17/` and added CI reconstruction of the checked-in authority chain.
- Added `FirstBootAuthorityBundleEvidence`, a final host-side cross-binding that requires reviewed kernel, rootfs and device-tree candidate authority bindings to refer to the exact same schema-v8 first-boot manifest/profile; it also requires the DT authority to reference the same reviewed kernel authority and rechecks candidate kernel/rootfs/DTB/DTBO identities.
- Project completion advances to **58%** for the reviewed host-side DT authority milestone. Physical bootloader/kernel acceptance remains unverified; `hardware_verified=false`, `beta_gate_credit=false`, and the Beta gate remains blocked until exact AC2003 firmware/stock-boot evidence and physical bring-up are complete.

## 0.6.46-dev — reviewed strict kernel authority and candidate binding

- Reviewed real kernel authority run `35183670399` as the first **strict SUCCESS** for `oneplus/avicii`: two independent exact-source, source-mtime-normalized `jobs=1` builds produced byte-identical final `.config` and byte-identical 43,878,416-byte ARM64 `Image` outputs.
- Accepted final `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3` (166,055 bytes) and Image SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712` (43,878,416 bytes).
- Preserved strict reproducibility evidence SHA-256 `a2156ba6cc493cf7f7575a60107938f5c5455d4388ecb883cd8f01754f13f0f0` and executed-build binding SHA-256 `dffad42df1d189170b23a95d980211e57c1f54d8f399e939b048597e79425a39` from workflow artifact `10482645697` on main commit `e600a5de13fa91085464c7ce2d4a6327f39b96e8`.
- Closed a provenance gap between strict A/B reproducibility and the executed builds: `kernel_build_binding` now requires the reproducibility record's build-A/build-B config and Image verifier-evidence digests to match the exact per-build run records, not only the final artifact bytes.
- Added fail-closed `KernelAuthorityRecord`. The reviewed record binds exact run/commit/artifact IDs, profile/source/kernel-plan/toolchain/recipe/environment, both executed-build evidence digests, strict reproducibility evidence, reproducibility-binding evidence and accepted config/Image hashes/sizes.
- Authority verification reconstructs the typed build/reproducibility binding from the plan, toolchain, A/B run records and strict reproducibility evidence before accepting the reviewed record, preventing detached/substituted chains.
- Added checked evidence under `evidence/authorities/kernel/oneplus-avicii-4.19.300-2026-09-17/` plus immutable authority record `evidence/authorities/oneplus-avicii-kernel-4.19.300-2026-09-17.json`.
- Added candidate-level `FirstBootKernelAuthorityEvidence`: a schema-v8 first-boot candidate must match the exact reviewed authority's source, plan, toolchain lock, recipe/environment, A/B run records, strict reproducibility/binding evidence and final config/Image identity.
- Added strict JSON/schema/digest validation, immutable writers, symlink-safe authority loading and negative tests for injected fields, detached evidence, artifact substitution and host-side hardware/Beta claims.
- Project completion advances to **56%** for the real strict kernel reproducibility milestone. This remains a host-side authority: `hardware_verified=false`, `beta_gate_credit=false`, and every physical AC2003 Beta gate remains blocked.

## 0.6.45-dev — compat-vDSO path normalization after 16-byte strict failure

- Reviewed real run `35181516724` as a **strict failure** despite the dramatic narrowing: final `.config` was still byte-identical, both Images were exactly 43,878,416 bytes, but only 16 Image bytes remained different across two 8-byte ranges at offsets `24740796..24740803` and `38215952..38215959`.
- Image A SHA-256 was `5c34e4e86b858ec02cc28abd06673747620dc00d45160b0fc084df997f7faf9c`; Image B SHA-256 was `97d6ba26afbea7aa543803a9f15e111e6ed5826cbf4c3c3c819e896998a64e54`.
- Build-tree evidence narrowed divergence to 14 of 4,597 selected artifacts. Deterministic IKHEADERS removed the prior `kernel/kheaders.o`, kallsyms, `System.map` and archive-related differences.
- The four remaining target-linked divergent objects were the ARM32 compat-vDSO objects `note.o`, `sigreturn.o`, `vdso.o` and `vgettimeofday.o`. Remaining `scripts/dtc` / `scripts/kconfig` differences were host-tool objects, not target Image inputs.
- The pinned vDSO32 Makefile uses its own `VDSO_CAFLAGS` and `CC_COMPAT ?= $(CC)`, so normal kernel `KCFLAGS` path remapping is not inherited. The profile now binds canonical source/output prefix maps into recursive GNU make `CC` using `$(KBUILD_SRC)` and `$(CURDIR)` so `CC_COMPAT` receives path-independent debug/macro identities.
- Extended ELF diagnostics to support target ARM ELF32 compat-vDSO objects while excluding unrelated `scripts/*` host objects. The earlier ARM64-only classifier's fail-closed rejection is therefore fixed without weakening target validation.
- Extended build-tree diagnostics to compare generated `kernel/kheaders_data.tar.xz` directly.
- Full Python 3.11/3.12/3.13/3.14 CI and focused kernel contracts passed before PR #47 was merged as `e600a5de13fa91085464c7ce2d4a6327f39b96e8`.
- Real A/B run `35183670399` subsequently proved the recursive compat-vDSO prefix-map policy removed the final observed nondeterminism and passed strict equality; that acceptance is recorded in 0.6.46.

## 0.6.44-dev — ELF divergence classification and deterministic IKHEADERS archive policy

- Reviewed real kernel authority run `35177350001` as another **strict failure**, never as partial reproducibility credit. Both exact-source, source-mtime-normalized `jobs=1` builds produced identical final `.config` and equal 43,878,416-byte ARM64 Images, but 4,388,978 Image bytes still differed across 229,151 ranges from offset 302,366 through 43,633,488.
- The new 0.6.43 build-tree evidence narrowed that failure to only **20 differing selected artifacts out of 4,597**, including `kernel/kheaders.o`, compat-vDSO32 objects, kallsyms objects, `System.map`, `vmlinux.o` and `vmlinux`.
- Added fail-closed kernel ELF diagnostics and chained them after strict failure without changing acceptance.
- Preserved `CONFIG_IKHEADERS`; reproducibility was not obtained by disabling it. Instead the avicii kernel plan bound deterministic GNU tar order/mtime/uid/gid settings and single-threaded xz for upstream embedded-header archive generation.
- Added focused regression coverage for ELF parsing/classification, traversal/symlink rejection, wrong-machine rejection and deterministic embedded-header archive policy.
- Project completion remained **54%**. No physical AC2003 or Beta gate received credit from these host-side changes.

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
