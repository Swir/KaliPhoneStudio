# KaliPhoneStudio Roadmap

The roadmap separates **device-independent studio work** from **per-phone bring-up**. Hardware items require physical-device evidence.

## Overall project progress

**49% complete**

`██████████░░░░░░░░░░ 49%`

This percentage is deliberately weighted toward real-device boot, hardware validation, recovery and release readiness. Host-side implementation and CI are important, but they do not count the same as verified phone hardware milestones.

## Phase A — Multi-device Studio Core

- [x] KaliPhoneStudio package/application migration
- [x] Device-profile runtime registry
- [x] Profile-based identity and verified serial binding
- [x] Profile-specific destructive confirmation token
- [x] Manifest + SHA-256 validation
- [x] A/B slot-aware guarded flash planning
- [x] Temporary `fastboot boot` path
- [x] Transaction / boot-session journals
- [x] Automated Python tests on 3.11, 3.12, 3.13 and 3.14
- [x] Versioned profile schema contract
- [x] CI-required profile recovery/test contract
- [x] Full-commit source pin requirement for profile upstreams
- [x] Fail-closed Android A/B payload envelope inspection
- [x] Payload + metadata SHA-256 evidence before extractor hand-off
- [x] Checksum-locked, source-pinned boot-only OTA extraction adapter
- [x] Versioned fail-closed host-tool lock manifest and deterministic extractor build command
- [x] Wire extractor execution to authoritative manifest platform/SHA-256 authorization
- [x] Pin extractor toolchain version and add dedicated exact-source reproducibility/source-lock CI
- [x] Linux amd64 pinned extractor builds reproducibly byte-for-byte and emits SHA-256 evidence
- [x] Windows amd64 pinned extractor builds reproducibly byte-for-byte with explicit MinGW/liblzma CGO wiring
- [x] Review reproducibility evidence and authorize exact Linux/Windows platform SHA-256 artifacts
- [x] Bind exact OTA identity evidence to extracted stock `boot.img` provenance record
- [x] Make boot-image build planning fully profile-driven and bind all inputs to exact stock provenance/SHA-256
- [x] Revalidate build plan/profile/provenance/input hashes immediately before assembly
- [x] Full-commit source lock for authoritative mkbootimg/unpack_bootimg backend with no PATH fallback
- [x] Deterministic boot-v2 image assembly from the validated build plan
- [x] Verify assembled output by locked unpacker + structural invariant round-trip
- [x] Fail-closed temporary-boot authorization binding device identity, stock provenance, plan, reproducible assembly and round-trip evidence
- [ ] Generic plugin hooks for profile-specific build/verify/recovery steps
- [ ] GUI profile selector for offline builds without a connected phone

## Phase B — Common Kali Phone Userspace

- [x] Pin official Kali/NetHunter ARM64 rootfs builder source to an exact upstream commit
- [x] Define fail-closed rootfs source/repository/reproducibility evidence contract
- [x] Require HTTPS Kali mirror + locked current Kali archive signing-key fingerprint
- [x] Verify Kali `InRelease` with `gpgv` and capture exact ARM64 package-index paths/sizes/SHA-256 values
- [x] Extract a normalized installed package/version/architecture manifest directly from each rootfs archive
- [x] Provide a host CLI to verify byte-identical independent rootfs builds and emit canonical evidence
- [x] Bind verified rootfs evidence and temporary-boot authorization into a canonical first-boot candidate manifest contract
- [x] Add real CI pipeline that prepares two independent exact-source ARM64 rootfs builds and fails closed on byte/package divergence
- [x] Add fail-closed ARM64 execution-host preflight for QEMU binfmt fix-binary semantics and locked Kali archive keyring
- [x] Guard both independent builds against signed Kali repository-snapshot drift before and after execution
- [x] Run the expensive real double-build on relevant PRs so execution regressions are caught before merge
- [ ] Obtain the first green real double-build run and review/archive its evidence
- [ ] Mark a concrete ARM64 rootfs artifact reproducible only after that run passes
- [ ] Promote first-boot evidence into a release-candidate manifest only after hardware gates exist
- [ ] Generic first-boot provisioning independent of device name
- [ ] Phosh phone UI stage on the verified common rootfs
- [ ] Safe minimal rescue initramfs artifact with reproducibility evidence
- [ ] SSH disabled by default
- [ ] Common mobile defaults: scaling, keyboard, lock/power integration
- [ ] Update/rollback metadata format

## Device #1 — OnePlus Nord AC2003 (`oneplus/avicii`)

### Boot chain

- [x] Public `avicii` board-layout baseline pinned
- [x] Boot header v2 / 4096-byte page recorded
- [x] `lito` / `sm7250` baseline recorded
- [x] DTB-in-boot + separate DTBO recorded
- [x] A/B partition layout and size limits recorded
- [x] Native boot-v2 parser/repacker
- [x] Candidate stock-vs-custom invariant gate
- [x] ARM64 kernel + LZ4 ramdisk candidate checks
- [x] USB ACM rescue/probe tooling prepared
- [x] Kali/systemd kernel config validation prepared
- [x] Profile firmware hints, recovery notes and hardware Beta contract recorded
- [x] LineageOS avicii source baseline locked to a full commit
- [x] Host-side OTA ZIP, payload-envelope and integrity-evidence validation foundation
- [x] Host-side checksum-locked boot extraction adapter (not hardware validation)
- [x] Immutable exact-OTA → payload → stock-boot provenance schema (host-side; exact user OTA still pending)
- [ ] Capture exact user's OxygenOS fingerprint/build
- [ ] Capture user's `fastboot getvar all`
- [ ] Obtain matching stock `boot.img` from exact OTA
- [ ] Validate parser/repacker against that exact stock image
- [ ] Pin final first-boot kernel commit
- [ ] Build kernel + DTB/DTBO candidate
- [ ] Temporary `fastboot boot` on physical AC2003
- [ ] Capture early kernel/rescue logs

### Essential hardware

- [ ] UFS/internal storage verified
- [ ] Display and touchscreen verified
- [ ] Hardware buttons and USB verified
- [ ] Charging/battery and thermal safety verified
- [ ] Suspend/resume verified

### Connectivity / phone hardware

- [ ] Wi-Fi / Bluetooth
- [ ] Modem, SIM, mobile data, SMS/calls
- [ ] GNSS/GPS
- [ ] Audio / cameras / fingerprint / NFC / sensors

### Recovery / release

- [ ] Validate OxygenOS recovery path on exact AC2003 baseline
- [ ] Test boot failure rollback
- [ ] Release manifest + checksums
- [ ] Pass all requirements in `BETA_RELEASE_GATE.md`
- [ ] **Publish first KaliPhoneStudio AC2003 Beta Release**
- [ ] Stable AC2003 release

## Device #2 and beyond

- [ ] Define candidate-selection criteria for next phone
- [ ] Add second independent profile proving architecture is truly multi-device
- [ ] Require schema, source locks, profile-specific tests and recovery notes before destructive actions
- [ ] Extend boot-image backends for other header/layout families

## Release rule

Do **not** publish a GitHub Beta merely because host-side tests are green. A device beta requires real hardware validation, reproducible artifacts, exact target/firmware metadata, checksums and a documented recovery route.
