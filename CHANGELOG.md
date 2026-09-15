# Changelog

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
- Python CI remains 3.11/3.12/3.13/3.14. This milestone does not claim AC2003 hardware compatibility.

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
