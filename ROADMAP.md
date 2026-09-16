# KaliPhoneStudio Roadmap

The roadmap separates **device-independent studio work** from **per-phone bring-up**. Hardware items require physical-device evidence.

## Overall project progress

**52% complete**

`██████████▍░░░░░░░░░ 52%`

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
- [x] Strict profile boot/A-B/source validation (typed boot contract, safe partition IDs, HTTPS full-commit sources, profile path binding)
- [x] Profile schema v2 read-only Fastboot probe contract with required variables and expected A/B slot count
- [x] Offline `fastboot getvar all` transcript parser/importer with exact-byte SHA-256 evidence and fail-closed ambiguity checks
- [x] Bind captured Fastboot profile/serial/firmware evidence to exact OTA `post-build` / `post-build-incremental` provenance
- [x] Carry baseline evidence digest and firmware identity through temporary-boot authorization and first-boot candidate manifests
- [x] CI-required profile recovery/test contract
- [x] Full-commit source pin requirement for profile upstreams
- [x] Strict profile-driven kernel contract with exact pinned source, version, architecture, Image name, config material, build flags and required CONFIG states
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
- [x] Fail-closed temporary-boot authorization binding device identity, exact captured firmware baseline, stock provenance, plan, reproducible assembly and round-trip evidence
- [x] Device-independent kernel evidence model for exact checkout, final `.config` and ARM64 `Image`
- [x] Bind kernel source/config/Image evidence to the exact kernel SHA-256/size in the approved boot build plan
- [x] Require two independent byte-identical final kernel `.config` and ARM64 `Image` builds before kernel reproducibility evidence is accepted
- [x] Pin the Android Clang kernel compiler to an immutable AOSP commit/subtree/object set and verify it against live Gitiles metadata
- [x] Bind the kernel plan to the exact checkout build configuration selecting the locked Clang revision; reject toolchain/path drift fail-closed
- [x] Carry kernel provenance, reproducibility and exact Image evidence into schema-v6 first-boot candidate manifests
- [x] Pin exact upstream FDT and Android DT table format references
- [x] Device-independent structural DTB/DTBO validation with bounded parsing, partition limits and exact boot-plan SHA-256/size binding
- [x] Carry DTB/DTBO evidence and format-lock digest into first-boot candidate manifests
- [x] Offline profile-driven DTB/DTBO evidence verifier that never accesses a phone
- [ ] Generic plugin hooks for profile-specific build/verify/recovery steps
- [ ] GUI profile selector for offline builds without a connected phone

## Phase B — Common Kali Phone Userspace

- [x] Pin official Kali/NetHunter ARM64 rootfs builder source to an exact upstream commit
- [x] Define fail-closed rootfs source/repository/reproducibility evidence contract
- [x] Require HTTPS Kali mirror + locked current Kali archive signing-key fingerprint
- [x] Verify Kali `InRelease` with `gpgv` and capture exact ARM64 package-index paths/sizes/SHA-256 values
- [x] Extract a normalized installed package/version/architecture manifest directly from each rootfs archive
- [x] Provide a host CLI to verify byte-identical independent rootfs builds and emit canonical evidence
- [x] Bind verified rootfs evidence, firmware-baseline-bound temporary-boot authorization, exact kernel/device-tree evidence and package manifest into a canonical first-boot candidate manifest contract
- [x] Add real CI pipeline that prepares two independent exact-source ARM64 rootfs builds and fails closed on byte/package divergence
- [x] Harden the real rootfs runner after the first main run exposed Ubuntu replacing `qemu-user-static`; require static ARM64 emulation, bind each build to the signed snapshot and install the reviewed Kali keyring for debootstrap
- [x] Add bounded canonical rootfs divergence diagnostics for strict CI failures; compare member sets/order/metadata/content hashes without extraction, mark the report `beta_gate_credit=false`, and keep the strict job failed
- [ ] Obtain the first green real double-build run and review/archive its evidence (latest completed strict run failed; the next diagnostics-enabled run is still executing)
- [ ] Mark a concrete ARM64 rootfs artifact reproducible only after that run passes
- [ ] Promote first-boot evidence into a release-candidate manifest only after hardware gates exist
- [ ] Generic first-boot provisioning independent of device name
- [ ] Phosh phone UI stage on the verified common rootfs
- [x] Device-independent deterministic rescue-initramfs gzip/newc builder and canonical reproducibility-evidence contract
- [x] Deterministic Linux-kernel-compatible LZ4 legacy ramdisk stage with pinned AOSP/LZ4 format references
- [x] Independent post-compression LZ4 decode + canonical `newc` structural verification before rescue evidence is accepted
- [x] Profile-driven rescue compression selection and exact rescue-evidence → boot-plan ramdisk binding
- [x] Add a source-locked static ARM64 rescue payload (`/init` + minimum required tools) with exact BusyBox 1.38.0 source hash, two independent byte-identical cross-builds, verified applet inventory and network/SSH disabled by default
- [ ] Produce a concrete safe minimal rescue initramfs artifact and prove its device rescue/logging path (host candidate generation is green; physical proof still required)
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
- [x] Host-side rescue ramdisk format matches the profile's required LZ4 legacy boot policy
- [x] Host-side AC2003 Fastboot baseline contract prepared (`product`, `serialno`, A/B slot/count, lock/security, bootloader/baseband); no physical transcript claimed
- [x] Public LineageOS `android_kernel_oneplus_sm7250` bring-up baseline pinned to exact commit `fb4b4374d3b9ad0f10ba38d159585129f092fb3d` and kernel `4.19.300`
- [x] Host-side exact kernel checkout/config/Image evidence and boot-plan binding implemented
- [x] Host-side kernel reproducibility evidence contract implemented; no concrete final hardware kernel is credited yet
- [x] AOSP Android Clang `r416183b` source identity locked to exact commit/tree/blob metadata and bound to the kernel checkout's declared compiler path
- [x] Host-side DTB/DTBO structural evidence, exact boot-plan binding and partition-bound checks implemented
- [ ] Produce and review a concrete double-build kernel artifact using the locked toolchain
- [ ] Capture exact user's OxygenOS fingerprint/build
- [ ] Capture user's `fastboot getvar all`
- [ ] Obtain matching stock `boot.img` from exact OTA
- [ ] Validate parser/repacker against that exact stock image
- [ ] Pin final first-boot kernel commit after exact-firmware/hardware review
- [ ] Build final kernel + DTB/DTBO candidate from pinned sources
- [ ] Bind concrete final kernel/DTB/DTBO artifacts into the exact first-boot candidate
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
