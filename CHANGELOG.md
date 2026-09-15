# Changelog

## 0.6.7-dev — checksum-locked OTA boot extraction adapter

- Added a device-independent adapter for extracting only `boot.img` from a preflighted Android A/B payload.
- Pinned extractor source provenance to `ssut/payload-dumper-go` commit `05fe59e21c9f271fba38398c7c040993313ecd04` (upstream 2.0.2-era main).
- The adapter never downloads or trusts an extractor implicitly: a local binary must match an explicit SHA-256 lock before execution.
- Extraction runs without a shell, has a 10-minute timeout, requires an empty output directory, and rejects missing/invalid `boot.img` output.
- Extracted stock boot images immediately pass the existing profile-driven Android boot header/partition-size preflight.
- Added tests for valid extractor locks, hash mismatch, malformed SHA locks, and unpinned source commits.
- Confirmed the complete preceding 0.6.6-dev GitHub Actions run succeeded across Python 3.11/3.12/3.13/3.14.
- This does not claim AC2003 hardware compatibility; exact OTA and physical-device Beta gates remain open.

## 0.6.6-dev — OTA payload integrity evidence

- Added streaming SHA-256 evidence for the complete `payload.bin` and its validated metadata envelope.
- Payload reports now bind structural preflight results to exact bytes before a future extractor hand-off.
- Added a post-hash size stability check to fail closed if the payload changes during inspection.
- Added tests proving whole-payload hashes change with partition data while metadata hashes remain stable when metadata is unchanged.
- Confirmed the preceding 0.6.5-dev GitHub Actions run completed successfully across Python 3.11/3.12/3.13/3.14.
- Partition extraction remains deliberately unimplemented until its backend/source/checksum contract is pinned.

## 0.6.5-dev — fail-closed A/B OTA payload envelope inspection

- Added device-independent `payload.bin` header inspection using the Android update_engine `CrAU` envelope.
- Validates payload major version, manifest/signature sizes, metadata boundaries and truncation before any future partition extraction is allowed.
- Added strict host-side limits for manifest and metadata-signature allocation risk.
- Added CI tests for valid v1/v2 payloads plus bad magic, unsupported versions and metadata-past-EOF failures.
- Confirmed the preceding 0.6.4-dev GitHub Actions run completed successfully across the configured Python matrix.
- Partition extraction remains deliberately unimplemented until a pinned, checksum-verifiable backend contract is added.

## 0.6.4-dev — versioned device-profile safety contract

- Added profile schema version 1 and fail-closed validation in the runtime registry.
- Every device profile must now declare firmware identity hints, pinned upstream source commits, recovery notes and host/hardware test contracts.
- Added CI tests that reject unpinned source refs and incomplete recovery/hardware contracts.
- Upgraded `oneplus/avicii` to schema v1 and pinned its LineageOS device-tree baseline to commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`.
- Recorded AC2003 firmware hints and explicit Beta hardware obligations as profile data rather than global core assumptions.
- Python CI remains 3.11/3.12/3.13/3.14; the pre-milestone 3.14 matrix completed successfully.

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
