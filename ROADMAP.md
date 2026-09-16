# KaliPhoneStudio Roadmap

KaliPhoneStudio separates **device-independent studio work** from **per-device bring-up**. A host-side implementation checkbox never implies hardware support; hardware milestones require evidence from the exact physical phone/firmware baseline.

## Overall project progress

**52% complete**

`██████████▍░░░░░░░░░ 52%`

The percentage is intentionally weighted toward physical boot, hardware validation, recovery and release readiness. CI and offline engineering are mandatory foundations, but they do not count the same as a verified device milestone.

## Current development line — 0.6.33-dev

- [x] First-boot schema v8 binds exact executed A/B kernel build provenance.
- [x] Exact-source kernel runner applies the profile-required `CONFIG_*` policy deterministically before build.
- [x] `oneplus/avicii` kernel policy explicitly requires LZ4 initramfs support and disables engineering module signing for deterministic bring-up builds.
- [x] Real kernel A/B failure was narrowed to different `Image` bytes despite identical final `.config`, toolchain, recipe and Image size.
- [x] Independent kernel source/output host paths are compiler-prefix-mapped to fixed virtual roots and the remap policy is evidence-bound.
- [x] Rootfs diagnostics isolated the latest pre-fix run to identical 269-package manifests, five volatile payload files and 4817 mtime-only metadata differences.
- [x] Rootfs canonicalization now removes only that reviewed volatile state before strict A/B comparison, with audit evidence and no Beta credit.
- [ ] Accept a concrete reproducible kernel only after a post-fix exact-source A/B build passes strict `.config` + `Image` equality and execution-provenance review.
- [ ] Accept a concrete reproducible Kali ARM64 rootfs only after a post-fix real A/B build passes strict byte equality and package-evidence equality.

## Phase A — Multi-device Studio Core

### Device/profile architecture

- [x] KaliPhoneStudio package/application migration.
- [x] Runtime device-profile registry.
- [x] Profile/path binding and profile-based device identity.
- [x] Verified serial bound to `profile_id`.
- [x] Profile-specific destructive confirmation token.
- [x] Versioned fail-closed profile schema and CI contract.
- [x] Typed boot/kernel contracts, safe A/B identifiers and full-commit HTTPS source requirements.
- [x] Recovery notes and host/hardware test contract required by supported-profile schema.
- [ ] Generic plugin hooks for profile-specific build/verify/recovery stages.
- [ ] GUI profile selector for offline builds without a connected phone.

### Device identification / firmware baseline

- [x] Generic read-only Fastboot baseline profile contract.
- [x] Offline `fastboot getvar all` transcript parser/importer with exact-byte SHA-256 evidence.
- [x] Fail-closed identity, A/B slot/count, lock/security and bootloader/baseband checks.
- [x] Exact firmware build/fingerprint bound to exact OTA `post-build` / `post-build-incremental` provenance.
- [x] Baseline digest carried into temporary-boot authorization and first-boot candidate evidence.

### OTA / stock boot / boot image

- [x] OTA ZIP inspection and `payload.bin` discovery.
- [x] Fail-closed payload envelope and SHA-256 evidence.
- [x] Checksum/source-locked boot-only payload extraction adapter.
- [x] Reproducible authorized Linux amd64 and Windows amd64 extractor binaries.
- [x] Exact OTA → payload → stock `boot.img` immutable provenance record.
- [x] Profile-driven deterministic `BootBuildPlan` with kernel/ramdisk/DTB/DTBO hashes.
- [x] Pre-assembly TOCTOU revalidation.
- [x] Source-locked `mkbootimg`/`unpack_bootimg` backend.
- [x] Deterministic independent double assembly and locked round-trip verification.
- [x] Fail-closed temporary-boot authorization.

### Kernel / toolchain / DTB / DTBO

- [x] Profile-driven exact kernel source/version/config/build contract.
- [x] Exact checkout evidence for source HEAD, Makefile version and selected config material.
- [x] Final `.config` evidence and ARM64 `Image` structural/hash evidence.
- [x] Strict two-root kernel reproducibility contract.
- [x] Android Clang `clang-r416183b` source/object lock and materialized compiler verification.
- [x] Compiler selection/build-config binding to the exact kernel plan.
- [x] Exact-source kernel runner with canonical recipe/environment/run evidence.
- [x] A/B executed-build provenance binding to strict kernel reproducibility evidence.
- [x] Deterministic profile-required config fragment application before build.
- [x] `CONFIG_RD_LZ4=y` compatibility for the avicii LZ4 ramdisk policy.
- [x] Deterministic engineering module-signing policy.
- [x] Canonical compiler source/output path remapping with `KBUILD_ABS_SRCTREE=0`, `-fdebug-prefix-map` and `-fmacro-prefix-map`.
- [x] Source-locked FDT and Android DT table format references.
- [x] Structural DTB and DTBO verification bound to the exact boot plan.
- [ ] Review and accept first real byte-identical kernel A/B evidence.
- [ ] Pin the final hardware-verified first-boot kernel commit after physical bring-up.

### First-boot evidence

- [x] First-boot candidate manifest binds firmware baseline, temporary-boot authorization, boot plan, kernel source/config/Image, compiler evidence, DTB/DTBO and rootfs evidence.
- [x] Schema v8 additionally binds exact executed A/B kernel build records, canonical recipe/environment and execution-binding digest.
- [ ] Promote host candidate evidence to a release-candidate manifest only after required physical gates exist.

## Phase B — Common Kali Phone Userspace

### Kali ARM64 rootfs

- [x] Official NetHunter ARM64 builder pinned to exact tag/commit.
- [x] HTTPS mirror and Kali archive signing fingerprint locked.
- [x] `gpgv`-verified `InRelease` snapshot with exact ARM64 package-index hashes.
- [x] Normalized installed package/version/architecture manifest extracted from rootfs.
- [x] Strict independent double-build contract.
- [x] Real main CI executes two exact-source ARM64 builds concurrently from one verified repository start state.
- [x] Fail-closed rootfs divergence diagnostics for failed strict comparisons.
- [x] Diagnostic v2 prioritizes content/type/add/remove/order before metadata, counts mtime-only/field drift and compares package manifests.
- [x] Latest pre-fix real A/B divergence reduced to five reviewed volatile payloads plus 4817 mtime-only differences while package manifests remain identical.
- [x] Device-independent canonicalization normalizes tar mtimes, machine identity/fake-clock state, generated password hash state and the regenerable ldconfig auxiliary cache before strict comparison.
- [x] Canonicalization emits per-build non-release audit evidence; it never substitutes for strict byte equality.
- [ ] Produce and review the first byte-identical ARM64 rootfs artifact.
- [ ] Generic first-boot provisioning independent of device name.
- [ ] Phosh stage on the verified common rootfs.
- [ ] Common mobile defaults: scaling, keyboard and lock/power integration.
- [ ] Update/rollback metadata format.

### Rescue initramfs

- [x] Device-independent deterministic `newc` builder.
- [x] gzip and Linux-compatible LZ4 legacy output.
- [x] Independent post-compression structural verification.
- [x] Source-locked static ARM64 BusyBox payload.
- [x] Required rescue applet inventory; network/SSH disabled by default.
- [x] Profile-driven rescue ramdisk → boot-plan binding.
- [ ] Prove rescue/logging path on physical hardware.

## Device #1 — OnePlus Nord AC2003 (`oneplus/avicii`)

### Boot chain / baseline

- [x] Public avicii board-layout baseline pinned.
- [x] Android boot header v2 / 4096-byte page policy recorded.
- [x] `lito` / `sm7250` baseline recorded.
- [x] DTB-in-boot + separate DTBO recorded.
- [x] A/B partition layout and partition limits recorded.
- [x] Profile firmware hints, recovery notes and physical Beta test contract recorded.
- [x] LineageOS device and kernel bring-up source baselines pinned to full commits.
- [x] Host-side LZ4 rescue ramdisk format matches profile boot policy.
- [x] AC2003 Fastboot baseline contract prepared.
- [ ] Capture exact physical phone OxygenOS build/fingerprint.
- [ ] Capture physical phone `fastboot getvar all` transcript.
- [ ] Obtain matching stock `boot.img` from the exact OTA.
- [ ] Validate parser/repacker against that exact stock image.
- [ ] Review a real reproducible kernel + DTB/DTBO first-boot candidate.
- [ ] Temporary `fastboot boot` on the physical AC2003.
- [ ] Capture early kernel/rescue logs.
- [ ] Confirm kernel reaches Kali early userspace/rootfs.

### Essential hardware

- [ ] UFS/internal storage verified.
- [ ] Display verified.
- [ ] Touchscreen verified.
- [ ] Hardware buttons verified.
- [ ] USB data/rescue verified.
- [ ] Charging/battery safety verified.
- [ ] Thermal behavior verified.
- [ ] Suspend/resume verified.

### Connectivity / phone hardware

- [ ] Wi-Fi.
- [ ] Bluetooth.
- [ ] Modem / SIM / mobile data.
- [ ] SMS / calls.
- [ ] GNSS/GPS.
- [ ] Audio.
- [ ] Cameras.
- [ ] Fingerprint.
- [ ] NFC.
- [ ] Sensors.

### Recovery / release

- [ ] Validate exact OxygenOS recovery path.
- [ ] Exercise boot-failure rollback.
- [ ] Produce compatibility matrix.
- [ ] Produce release manifest + SHA-256 checksums.
- [ ] Pass every item in `BETA_RELEASE_GATE.md`.
- [ ] **Publish first KaliPhoneStudio AC2003 Beta Release.**
- [ ] Stable AC2003 release after the higher stable threshold.

## Device #2 and beyond

- [ ] Define next-device selection criteria.
- [ ] Add a second independent profile to prove the architecture is genuinely multi-device.
- [ ] Require full schema/source-lock/recovery/test contract before any destructive action.
- [ ] Add boot-image backend support for other header/layout families as needed.

## Release rule

A green host CI run is **never sufficient** to publish a device Beta. A Beta requires reproducible release artifacts, exact physical target/firmware evidence, successful temporary boot, recovery proof, required hardware safety checks and release manifests/checksums. Stable requires a later, higher verification threshold.