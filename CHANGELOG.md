# Changelog

## 0.6.0-dev — KaliPhoneStudio multi-device migration

- Renamed the project and application from KaliNord AC2003 to **KaliPhoneStudio**.
- Renamed Python package to `kaliphonestudio`.
- Added runtime device-profile discovery from `devices/<vendor>/<codename>/profile.json`.
- Converted device detection from hard-coded AC2003 logic to profile matching.
- Verified-device registry now stores `profile_id` with the phone serial.
- Destructive confirmation token is profile-specific.
- Flash plan and temporary-boot core can resolve the connected device profile.
- Boot candidate gate accepts a device profile instead of assuming AC2003 globally.
- Added first profile: `oneplus/avicii` (OnePlus Nord AC2003).
- Added multi-device README, roadmap and Beta release gate.
- Local migration test suite: 15 tests passing.

## 0.5.0-dev — AC2003 bring-up hardening

- Added strict stock-vs-candidate temporary-boot gate.
- Added ARM64 Image and LZ4 ramdisk checks.
- Added boot-session journals with SHA-256 evidence.
- Added staged kernel configuration validation.
- Added automatic early hardware probe reporting over USB ACM.
