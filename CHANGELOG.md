# Changelog

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
