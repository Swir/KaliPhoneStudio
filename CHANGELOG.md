# Changelog

## 0.6.20-dev — deterministic LZ4 rescue ramdisk and stricter multi-device profile contracts

- Closed the `oneplus/avicii` rescue-format gap without hardcoding AC2003 into the core: the profile continues to declare `ramdisk_compression: lz4`, while the common initramfs layer now supports that policy generically.
- Added a small audited pure-Python LZ4 legacy-frame implementation. It emits deterministic literal-only blocks under the Linux-kernel legacy magic, uses the legacy 8 MiB block contract, and includes a bounded decoder so generated output is independently decoded rather than trusted by hash alone.
- Pinned the ramdisk-format references in `tools/ramdisk-format-locks.json`: AOSP `platform/build` commit `5db2b8fa45a8ba9e90f76f583bc46ffdcf6c3c57` for the `lz4 -l` kernel-ramdisk policy and upstream `lz4` v1.10.0 commit `ebb370ca83af193212df4dcbadcc5d87bc0de2f0` for legacy framing semantics.
- Refactored rescue initramfs construction so gzip and LZ4 both originate from the same normalized `newc` payload and both still require two byte-identical independent builds.
- Added independent post-compression structural verification: decompression is followed by a native `newc` parser that rechecks canonical inode/order/uid/gid/mtime/device metadata, entry types, trailer/padding, manifest SHA-256, entry count and executable `/init` SHA-256.
- Tightened rescue staging by rejecting world-writable regular files in addition to the existing setuid/setgid, special-file, unsafe-path and resource-limit gates.
- Extended rescue-to-boot binding so `lz4-legacy-literal-v1` maps only to boot plans whose profile policy is exactly `lz4`; exact artifact SHA-256/size and plan digest still have to match.
- Made the offline rescue CLI profile-aware: `--profile-id oneplus/avicii` derives LZ4 from `devices/oneplus/avicii/profile.json`, while an explicit conflicting compression choice fails closed.
- Hardened the versioned multi-device profile contract: strictly typed boot header/page/kernel/DTB/DTBO/compression fields, power-of-two page sizes, safe/unique A/B partition identifiers, required A/B boot partition, credential-free HTTPS source URLs, full commit locks, safe lowercase `profile_id` components and `profile_id` ↔ repository path binding.
- Added focused regression coverage for LZ4 block/stream decoding, malformed legacy frames, multi-block round-trips, format-lock consistency, deterministic LZ4 rescue output, structural inspection, world-writable rejection, LZ4 boot-plan binding and stricter profile validation.
- Overall completion remains 49%: this is substantial host-side safety/format work but does not satisfy any physical AC2003 Beta gate. The repaired real ARM64 rootfs run is still not considered reproducible until its full double-build evidence passes and is reviewed.

## 0.6.19-dev — rootfs execution hardening and deterministic rescue initramfs

- Diagnosed the first real post-merge ARM64 rootfs reproducibility run `35090859764` instead of treating ordinary Python CI as sufficient. The pinned upstream builder's Debian dependency helper installed `qemu-user`/`qemu-user-binfmt`, removed `qemu-user-static`, and left the foreign ARM64 debootstrap second stage unable to enter chroot.
- Added a fail-closed rootfs host preflight that requires `qemu-aarch64-static`, rejects an ambiguous competing dynamic `qemu-aarch64`, verifies the exact checkout is clean, and only then creates the upstream untracked `.dep_check` sentinel so the pinned builder cannot replace the validated static emulator.
- Bound every real rootfs build invocation to the previously GPG-verified repository snapshot: the runner re-fetches the live HTTPS `InRelease` and requires its SHA-256 to remain identical immediately before build execution.
- Carried the reviewed Kali archive keyring into the build job so debootstrap validates Kali repository signatures itself rather than relying only on the earlier snapshot-capture step.
- Added focused rootfs-runner regression tests for missing static QEMU, dynamic-QEMU precedence, exact snapshot acceptance and repository-state drift. PR #9 passed Python CI and the signed-snapshot rootfs contract before merge as `efbc8bee1d5abd2f71835d5ef7331fdd9dd37dcd`.
- Added a device-independent deterministic rescue initramfs contract: native gzip/newc construction with normalized uid/gid/mtime/order, two-pass byte-for-byte reproducibility, executable `/init` requirement, canonical artifact/entry evidence and post-build drift verification.
- Rescue-initramfs staging now rejects unsafe paths, setuid/setgid entries, special files and bounded-resource violations; the offline CLI refuses output overwrite and never accesses a phone.
- PR #10 passed the complete Python 3.11/3.12/3.13/3.14 test/compile matrix before merge as `f359fdb272abd5c300b5cac8fb42c027662c38f4`.
- The repaired full `main` ARM64 double-build run `35098070478` is intentionally not declared reproducible until both real builds finish, byte/package equality passes and the resulting evidence is reviewed.
- Overall project completion remains 49%; the initramfs work is a host artifact contract only and no AC2003 hardware/Beta gate is credited.

## 0.6.18-dev — signed repository snapshots and real ARM64 rootfs reproducibility CI

- Upgraded the common rootfs lock to schema v2, switched the Kali mirror to HTTPS, and pinned the Kali archive signing fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5` alongside the exact NetHunter rootfs source commit.
- Added `gpgv`-verified Kali `InRelease` capture; snapshot evidence now records the exact `InRelease` SHA-256 and ARM64 package-index path/size/SHA-256 entries published by the signed repository metadata.
- Corrected the evidence model so repository snapshot state is separate from the installed-package manifest produced by a concrete rootfs artifact.
- Added safe tar inspection of `var/lib/dpkg/status` and a normalized package/version/architecture manifest with digest and package count in rootfs evidence.
- Hardened first-boot candidate schema v2 so it carries the package-manifest digest/count and strictly validates all boot-side SHA-256 fields before binding evidence.
- Added a direct exact-checkout rootfs build runner that verifies the locked Git commit, invokes the locked argv without a shell, validates the resulting archive and refuses ambiguous/missing ARM64 outputs.
- Added `.github/workflows/rootfs-repro.yml`: PRs verify signed repository snapshot contracts; pushes to `main` prepare two independent exact-source ARM64 builds and fail closed unless rootfs bytes and package evidence match.
- Added direct-run CLI regression coverage after the first `rootfs-repro` PR run exposed missing repository import paths; the failure was diagnosed from Actions logs and fixed in the same development iteration.
- Python 3.11–3.14 tests, the source-lock workflow and the repaired PR rootfs snapshot workflow are green before merge. The real expensive double-build is intentionally not claimed until the post-merge `main` job completes.
- Overall project completion remains 49%; no physical AC2003 gate is credited for this host-side work.

## 0.6.17-dev — rootfs source and reproducibility evidence contract

- Pinned the official Kali Linux NetHunter rootfs builder tag `2026.2` to full commit `20238a2f2d547d7989a4dec287d4f5ef528ed701` instead of trusting a moving branch/tag at runtime.
- Added a strict schema-v1 rootfs source lock for `kali-rolling`, ARM64 and the selected minimal build recipe.
- Added repository snapshot evidence binding the exact mirror, suite, architecture, `InRelease` SHA-256, package-index SHA-256 values and package-manifest SHA-256.
- Added streaming rootfs artifact hashing and mandatory independent double-build byte equality before an artifact can receive reproducibility evidence.
- Added post-build drift verification and atomic canonical evidence output.
- Added `scripts/verify_rootfs_pair.py` so future CI can verify two real rootfs builds without embedding device-specific knowledge in the core.
- Added focused negative tests for moving source refs, missing repository evidence requirements, mismatched repository snapshots, non-identical builds, malformed hashes and post-build artifact mutation.
- Reconciled README/ROADMAP/BUILD_STATUS with already merged boot assembly, locked round-trip and temporary-boot authorization work; project progress moves conservatively to 49%.
- No real Kali ARM64 rootfs artifact or AC2003 hardware milestone is claimed yet.

## 0.6.16-dev — source-locked boot assembly and authorization

- Added a full-commit source lock for LineageOS `android_system_tools_mkbootimg` commit `808ecd09666ffe0ff5800f02af693abce56eb395` with no fallback to a host `mkbootimg` from `PATH`.
- Added deterministic profile-driven `mkbootimg` argv generation from the approved boot build plan.
- Added real source-locked assembly execution with two independent builds and mandatory byte-for-byte equality before publishing a candidate image.
- Added source-locked `unpack_bootimg` round-trip verification of kernel, ramdisk and required in-boot DTB against the approved plan.
- Added fail-closed `TemporaryBootAuthorization` tying the verified physical-device identity to exact stock provenance, plan digest, reproducible assembly and structural verification.
- These are host-side safety milestones only; they do not prove AC2003 boot or hardware functionality.

## 0.6.15-dev — deterministic boot build planning

- Added deterministic schema-v1 boot build plans binding exact stock-boot provenance to profile-driven header/page/compression/cmdline policy and kernel/ramdisk/DTB/DTBO SHA-256 inputs.
- Added pre-assembly TOCTOU revalidation so profile policy, provenance or input-file drift fails closed immediately before assembly.
- Added safe canonical boot-plan serialization and path checks.
- Added tests for deterministic plans, profile/provenance mismatch, mandatory DTB/DTBO handling and changed build inputs.

## 0.6.14-dev — exact OTA to stock boot provenance

- Investigated the 0.6.13 Python CI regression: the old test still expected an empty extractor artifact map after Linux/Windows hashes had intentionally been authorized; all four Python jobs failed on that stale assertion.
- Replaced the stale assertion with checks that reviewed platform hashes resolve exactly, tampered local binaries fail SHA-256 verification, and unknown platforms remain fail-closed.
- Added immutable schema-v1 stock-boot provenance records binding `profile_id`, complete OTA SHA-256/size and firmware metadata, payload SHA-256/metadata SHA-256/size, and extracted `boot.img` SHA-256/size/header version.
- Provenance creation rejects mismatched OTA-vs-inspected payload sizes, missing firmware metadata, malformed hashes and attempts to overwrite existing evidence with different bytes.
- Added focused provenance contract tests.
- Advanced README/ROADMAP progress to 46% for the completed host-side provenance contract; the exact user's OxygenOS OTA and all physical AC2003 Beta evidence remain pending.

## 0.6.13-dev — cross-platform reproducible extractor authorization

- Verified GitHub Actions `extractor-repro` run `35018283145` completed successfully on both Linux amd64 and Windows amd64.
- Reviewed the uploaded SHA-256 evidence after each platform built the exact pinned source twice and passed byte-for-byte equality.
- Authorized Linux amd64 extractor SHA-256 `a9e5806356af76b11643f3129b5516a638e9dc0c53cefd40b665a916683c83d0`.
- Authorized Windows amd64 extractor SHA-256 `35fbcd36c553f81375a904ceca58aef5289da2e2e067fc0e6c835390588edfa5`.
- Updated repository tests so supported platforms must resolve to those exact hashes while unknown platforms still fail closed.
- Advanced README/ROADMAP progress to 45% for completing the cross-platform extractor authorization milestone; no AC2003 hardware milestone is claimed.
- Next high-impact host milestone is binding exact OTA identity/integrity evidence to the extracted stock `boot.img` provenance record.

## 0.6.12-dev — Windows extractor CGO toolchain repair

- Inspected the completed repaired `extractor-repro` run: Linux amd64 now builds twice byte-for-byte and emits SHA-256 evidence successfully.
- Isolated the remaining Windows failure: installing the MSYS2 xz package alone did not make `lzma.h` visible to Go CGO under the Git-for-Windows bash build shell.
- Windows CI now installs both `mingw-w64-x86_64-gcc` and `mingw-w64-x86_64-xz`, explicitly pins `CC`/`CXX`, and supplies deterministic MinGW include/library paths to CGO.
- Added a fail-fast Windows native-toolchain visibility check for `lzma.h` and GCC before either reproducibility build starts.
- Kept exact extractor source commit, Go 1.27.0, double-build comparison and fail-closed artifact authorization unchanged.
- Progress remains 44% because this is host build hardening, not physical-device validation.

## 0.6.11-dev — extractor native-dependency reproducibility repair

- Inspected the first real `extractor-repro` run instead of treating ordinary Python CI success as extractor success.
- Confirmed both Linux amd64 and Windows amd64 jobs failed at the build step because the pinned upstream `go-xz` dependency requires native `lzma.h` headers.
- Added explicit Linux `liblzma-dev` provisioning and Windows MSYS2 `mingw-w64-x86_64-xz` provisioning before the pinned Go build.
- Kept CGO explicitly enabled and retained the exact source commit, Go 1.27.0 lock, deterministic build flags and double-build byte comparison.
- No platform binary hash is authorized until the repaired workflow actually passes and its evidence is reviewed.
- README and ROADMAP remain at 44%; fixing host build prerequisites does not claim physical AC2003 progress.

## 0.6.10-dev — pinned-toolchain extractor reproducibility CI

- Pinned the extractor build toolchain to Go 1.27.0, matching the exact pinned upstream commit's `go.mod` requirement.
- Extended the fail-closed host-tool lock parser so an unversioned or unsupported build toolchain is rejected.
- Added a dedicated `extractor-repro` workflow for Linux amd64 and Windows amd64.
- The workflow checks out the exact locked upstream commit, verifies `HEAD`, installs the exact locked Go version, verifies the upstream `go.mod` requirement, builds twice with deterministic flags, and fails unless both binaries are byte-for-byte identical.
- Successful jobs emit per-platform SHA-256 evidence as workflow artifacts; hashes are not automatically trusted or committed.
- Added tests for exact toolchain pinning and rejection of missing/`latest` toolchain versions.
- Kept README and ROADMAP at a conservative 44%; this host-side hardening does not claim physical AC2003 progress.
- No extractor binary is authorized until the new reproducibility evidence is green and reviewed.

## 0.6.9-dev — manifest-backed extractor authorization

- Wired OTA extractor authorization directly to the versioned `tools/extractor-locks.json` contract instead of relying on caller-supplied hashes for release-oriented execution.
- Added `lock_from_manifest()` so the requested host platform must have an explicit artifact entry before an extractor can be authorized.
- Local binaries must still match the exact manifest SHA-256; source URL and full source commit are propagated into the runtime lock.
- The repository artifact map intentionally remains empty, so no unverified extractor binary is currently authorized.
- Added tests for fail-closed repository defaults, authoritative platform hash resolution and tampered-binary rejection.
- README and ROADMAP progress bars advanced conservatively to 44%; no physical AC2003 hardware milestone is claimed.
- Python CI remains 3.11/3.12/3.13/3.14.

## 0.6.8-dev — versioned reproducible host-tool lock contract

- Added `tools/extractor-locks.json` schema v1 for pinned extractor source provenance and deterministic build instructions.
- Added a fail-closed Python lock-manifest loader with strict full-commit and SHA-256 validation.
- Platform artifacts are deliberately unauthorized until an exact binary SHA-256 is recorded; the initial artifacts map is empty rather than trusting an unverified download.
- Added tests for source pinning, platform lookup, malformed artifact hashes and the repository's fail-closed default.
- Updated README and ROADMAP completion bars to 43%; progress remains weighted toward physical-device and release evidence.
- Python CI remains 3.11/3.12/3.13/3.14.

## 0.6.7-dev — checksum-locked OTA boot extraction adapter

- Added a device-independent adapter for extracting only `boot.img` from a preflighted Android A/B payload.
- Pinned extractor source provenance to `ssut/payload-dumper-go` commit `05fe59e21c9f271fba38398c7c040993313ecd04`.
- The adapter never downloads or trusts an extractor implicitly: a local binary must match an explicit SHA-256 lock before execution.
- Extraction runs without a shell, has a 10-minute timeout, requires an empty output directory, and rejects missing/invalid `boot.img` output.
- Extracted stock boot images immediately pass the existing profile-driven Android boot header/partition-size preflight.
- Added tests for valid extractor locks, hash mismatch, malformed SHA locks, and unpinned source commits.
- Confirmed the complete preceding 0.6.6-dev GitHub Actions run succeeded across Python 3.11/3.12/3.13/3.14.
- This does not claim AC2003 hardware compatibility; exact OTA and physical-device Beta gates remain open.

## 0.6.6-dev — OTA payload integrity evidence

- Added streaming SHA-256 evidence for the complete `payload.bin` and its validated metadata envelope.
- Payload reports now bind structural preflight results to exact bytes before extractor hand-off.
- Added a post-hash size stability check to fail closed if the payload changes during inspection.
- Added tests proving whole-payload hashes change with partition data while metadata hashes remain stable when metadata is unchanged.
- Confirmed the preceding 0.6.5-dev GitHub Actions run completed successfully across Python 3.11/3.12/3.13/3.14.

## 0.6.5-dev — fail-closed A/B OTA payload envelope inspection

- Added device-independent `payload.bin` header inspection using the Android update_engine `CrAU` envelope.
- Validates payload major version, manifest/signature sizes, metadata boundaries and truncation before partition extraction.
- Added strict host-side limits for manifest and metadata-signature allocation risk.
- Added CI tests for valid v1/v2 payloads plus bad magic, unsupported versions and metadata-past-EOF failures.

## 0.6.4-dev — versioned device-profile safety contract

- Added profile schema version 1 and fail-closed validation in the runtime registry.
- Every device profile must declare firmware identity hints, pinned upstream source commits, recovery notes and host/hardware test contracts.
- Added CI tests that reject unpinned source refs and incomplete recovery/hardware contracts.
- Upgraded `oneplus/avicii` to schema v1 and pinned its LineageOS device-tree baseline to commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`.
- Recorded AC2003 firmware hints and explicit Beta hardware obligations as profile data rather than global core assumptions.

## 0.6.3-dev — safe OTA inspection foundation

- Added safe OTA ZIP inspection with path traversal rejection, payload discovery, metadata parsing and package SHA-256 evidence.
- Added profile-driven firmware hint verification foundation.
- Fixed the repository version contract and expanded CI to Python 3.14.

## 0.6.0-dev — KaliPhoneStudio multi-device migration

- Renamed the project and application to **KaliPhoneStudio**.
- Renamed Python package to `kaliphonestudio`.
- Added runtime device-profile discovery from `devices/<vendor>/<codename>/profile.json`.
- Converted device detection from hard-coded AC2003 logic to profile matching.
- Verified-device registry now stores `profile_id` with the phone serial.
- Destructive confirmation token is profile-specific.
- Flash plan and temporary-boot core can resolve the connected device profile.
- Boot candidate gate accepts a device profile instead of assuming AC2003 globally.
- Added first profile: `oneplus/avicii` (OnePlus Nord AC2003).
- Added multi-device README, roadmap and Beta release gate.

## 0.5.0-dev — AC2003 bring-up hardening

- Added strict stock-vs-candidate temporary-boot gate.
- Added ARM64 Image and LZ4 ramdisk checks.
- Added boot-session journals with SHA-256 evidence.
- Added staged kernel configuration validation.
- Added automatic early hardware probe reporting over USB ACM.
