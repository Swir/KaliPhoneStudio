# KaliPhoneStudio Roadmap

The roadmap separates **device-independent studio work** from **per-phone bring-up**. A feature is checked only when it is implemented and verified at the stated level; hardware items require physical-device evidence.

## Phase A — Multi-device Studio Core

- [x] Rename project/application to **KaliPhoneStudio**
- [x] Move Python package to `kaliphonestudio`
- [x] Device-profile registry under `devices/<vendor>/<codename>/profile.json`
- [x] Profile-based ADB identity matching
- [x] Verified serial registry tied to `profile_id`
- [x] Profile-specific destructive confirmation token
- [x] ADB/Fastboot discovery and diagnostics
- [x] Preflight checks
- [x] Engineering CLI
- [x] Manifest + SHA-256 validation
- [x] A/B slot-aware flash planning
- [x] Dry-run / guarded real-flash path
- [x] Temporary `fastboot boot` path
- [x] Transaction / boot-session journals
- [x] Windows EXE build path
- [x] Automated Python tests
- [ ] Make every boot-image builder fully profile-driven
- [ ] Generic plugin hooks for profile-specific build/verify/recovery steps
- [ ] GUI profile selector for offline builds without a connected phone
- [ ] Profile schema validation and versioning
- [ ] Device profile test contract required by CI

## Phase B — Common Kali Phone Userspace

- [x] Kali rolling ARM64 rootfs builder
- [x] Phosh phone UI stage
- [x] Safe minimal rescue initramfs foundation
- [x] SSH disabled by default
- [ ] Reproducible rootfs artifact in CI
- [ ] Generic first-boot provisioning independent of device name
- [ ] Common mobile defaults: scaling, keyboard, lock/power integration
- [ ] Update/rollback metadata format for future supported phones

## Device #1 — OnePlus Nord AC2003 (`oneplus/avicii`)

### Boot chain

- [x] Public `avicii` board-layout baseline pinned
- [x] Boot header v2 / 4096-byte page recorded
- [x] `lito` / `sm7250` baseline recorded
- [x] DTB-in-boot + separate DTBO recorded
- [x] A/B partition layout recorded
- [x] Boot/DTBO/recovery size limits recorded
- [x] Native boot-v2 parser/repacker
- [x] Candidate stock-vs-custom invariant gate
- [x] ARM64 kernel + LZ4 ramdisk candidate checks
- [x] USB ACM rescue/probe tooling prepared
- [x] Kali/systemd kernel config validation prepared
- [ ] Capture exact user's OxygenOS fingerprint/build
- [ ] Capture user's `fastboot getvar all`
- [ ] Obtain matching stock `boot.img`
- [ ] Validate parser/repacker against that exact stock image
- [ ] Pin final first-boot kernel commit
- [ ] Build kernel + DTB/DTBO candidate
- [ ] Temporary `fastboot boot` on physical AC2003
- [ ] Capture early kernel/rescue logs

### Essential hardware

- [ ] UFS/internal storage verified
- [ ] Display verified
- [ ] Touchscreen verified
- [ ] Hardware buttons verified
- [ ] USB gadget/host verified
- [ ] Charging and battery reporting verified
- [ ] Thermal management verified
- [ ] Suspend/resume verified

### Connectivity

- [ ] Wi-Fi
- [ ] Bluetooth
- [ ] Modem/SIM
- [ ] Mobile data
- [ ] SMS
- [ ] Calls where practical
- [ ] GNSS/GPS

### Phone UX / secondary hardware

- [x] Phosh userspace profile prepared
- [x] On-screen keyboard package path prepared
- [ ] Rotation/IIO
- [ ] AC2003 scaling tuning
- [ ] Audio
- [ ] Cameras
- [ ] Fingerprint
- [ ] NFC
- [ ] Remaining sensors

### Recovery / release

- [ ] Validate OxygenOS recovery path on the exact AC2003 baseline
- [ ] Test boot failure rollback
- [ ] Release manifest + checksums
- [ ] Pass all requirements in `BETA_RELEASE_GATE.md`
- [ ] **Publish first KaliPhoneStudio AC2003 Beta Release**
- [ ] Stable AC2003 release

## Device #2 and beyond

- [ ] Define candidate-selection criteria for next phone
- [ ] Add second independent profile proving the architecture is truly multi-device
- [ ] Require profile-specific tests and recovery notes before enabling destructive actions
- [ ] Extend boot-image backends for header/layout families not covered by the AC2003 path

## Release rule

Do **not** publish a GitHub Beta merely because host-side tests are green. A device beta requires real hardware validation, reproducible artifacts, exact target/firmware metadata, checksums and a documented recovery route.
