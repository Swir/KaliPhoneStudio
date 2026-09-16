# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux as the primary phone operating system/userspace**, without Android as the user-facing OS layer.

## Project progress

**50% complete**

`██████████░░░░░░░░░░ 50%`

Progress is weighted toward real device bring-up, hardware validation, recovery and release readiness. Host-side CI/tests alone do not significantly raise this percentage.

> Current status: **0.6.21-dev** — the verified host boot chain is in place and the rescue path now has a source-locked, independently double-built static ARM64 BusyBox payload plus deterministic profile-formatted initramfs evidence. The payload is built from exact BusyBox 1.38.0 source bytes, its applet inventory is executed under ARM64 QEMU and checked against an allow/deny contract, and network/SSH remain disabled by default. The previous real ARM64 rootfs run reached a concrete archive but failed because the pinned upstream tarball uses one safe top-level directory before `var/lib/dpkg/status`; the parser has been repaired with traversal/ambiguity regression tests, but the artifact is **not** counted reproducible until a new `main` double-build passes. The first active target remains **OnePlus Nord AC2003 (`oneplus/avicii`)**. No public Beta is allowed until the physical device passes `BETA_RELEASE_GATE.md`.

## Architecture

The Python core under `kaliphonestudio/` is device-independent. Hardware knowledge belongs in `devices/<vendor>/<codename>/profile.json` and target documentation/build modules. Adding a JSON profile does **not** mean hardware support exists.

A schema-v1 profile must provide unambiguous identity, a destructive-action confirmation token, boot/partition constraints, firmware hints, full-commit upstream source locks, recovery notes, and explicit host/hardware test contracts. The registry fails closed when these fields are missing or malformed. Boot policy is strictly typed, A/B partition names are validated, `profile_id` is bound to its `devices/vendor/codename/profile.json` location, and upstream profile sources must be credential-free HTTPS URLs pinned to full commits.

## Active device profiles

| Device | Profile ID | Status | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii engineering baseline is pinned to LineageOS `android_device_oneplus_avicii` commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. That exact board configuration records Android boot header v2, 4096-byte pages, in-boot DTB, separate DTBO and `BOARD_RAMDISK_USE_LZ4 := true`. This is a source reference, **not** proof that Kali hardware functions work.

## Implemented host-side foundations

- Runtime device-profile registry and profile-based ADB/Fastboot identity.
- Verified serial binding to `profile_id`.
- Profile-specific confirmation for destructive actions.
- A/B slot-aware planning, dry-run defaults and guarded inactive-slot writes.
- Temporary `fastboot boot` workflow before persistent boot-slot testing.
- Manifest/SHA-256 and partition-size validation.
- Strict multi-device profile contract for boot header/page/kernel/DTB/DTBO/ramdisk compression, safe A/B partition identifiers and full-commit HTTPS upstream sources.
- Android boot image v2 inspection/repack foundation.
- Safe OTA ZIP inspection, payload discovery and firmware metadata checks.
- Fail-closed `payload.bin` envelope inspection and streaming SHA-256 evidence.
- Checksum-locked, boot-only OTA extraction adapter whose output immediately enters boot-image preflight.
- Immutable schema-v1 stock-boot provenance records bind `profile_id`, exact OTA SHA-256 and firmware metadata, payload SHA-256/metadata SHA-256, and extracted `boot.img` SHA-256/size/header version.
- Deterministic schema-v1 boot build plans bind exact stock provenance to profile-driven header/page/compression/cmdline policy and SHA-256 of kernel, ramdisk, DTB and DTBO inputs.
- Mandatory pre-assembly TOCTOU revalidation detects changed profile policy, provenance, component size/hash or unsafe input paths.
- Boot assembler/unpacker source lock in `tools/boot-tool-locks.json`: LineageOS `android_system_tools_mkbootimg` commit `808ecd09666ffe0ff5800f02af693abce56eb395`; header-v2 plans cannot fall back to an arbitrary host `mkbootimg` from PATH.
- Deterministic source-locked `mkbootimg` invocation, independent double assembly and byte-for-byte equality requirement before an image can be accepted.
- Source-locked `unpack_bootimg` round-trip verification of kernel, ramdisk and in-boot DTB against the original plan.
- Fail-closed `TemporaryBootAuthorization` tying the verified phone identity to stock provenance, plan digest, reproducible assembly and structural verification before temporary boot may be offered.
- Versioned `tools/extractor-locks.json` contract pinning extractor source, exact Go toolchain and deterministic build command.
- Dedicated extractor reproducibility CI builds the exact pinned source twice on Linux amd64 and Windows amd64 and emits SHA-256 evidence only after byte-for-byte equality.
- Linux amd64 and Windows amd64 extractor reproducibility passed in GitHub Actions run `35018283145`.
- Authorized extractor SHA-256: Linux amd64 `a9e5806356af76b11643f3129b5516a638e9dc0c53cefd40b665a916683c83d0`; Windows amd64 `35fbcd36c553f81375a904ceca58aef5289da2e2e067fc0e6c835390588edfa5`.
- Kali ARM64 rootfs source lock pinned to official NetHunter rootfs tag `2026.2`, commit `20238a2f2d547d7989a4dec287d4f5ef528ed701`.
- Rootfs lock schema v2 forces the Kali mirror to HTTPS and pins the current Kali archive signing fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5`.
- `scripts/capture_kali_snapshot.py` requires a successful `gpgv` validation of `InRelease` by that fingerprint, then records the exact `InRelease` SHA-256 and ARM64 package-index paths/sizes/SHA-256 values.
- Rootfs evidence requires two independent byte-identical tar.xz builds and derives a normalized package/version/architecture manifest directly from the archive's single safe `var/lib/dpkg/status` location, accepting the pinned builder's one-top-level-directory layout while rejecting traversal, deeper suffix tricks and ambiguous duplicates.
- Rootfs build execution performs a fail-closed host preflight requiring `qemu-aarch64-static`, rejecting a competing dynamic `qemu-aarch64`, preventing the pinned upstream dependency helper from replacing the static emulator, and revalidating the signed HTTPS `InRelease` state immediately before each build.
- The reviewed Kali archive keyring used for snapshot verification is carried into the rootfs job so debootstrap can validate Kali repository signatures itself.
- `.github/workflows/rootfs-repro.yml` performs signed-snapshot validation on PRs and executes two real pinned ARM64 builds on relevant `main` pushes; the result is fail-closed if bytes or package evidence diverge.
- Device-independent deterministic rescue-initramfs construction normalizes uid/gid/mtime and entry ordering, builds twice, requires byte equality, emits canonical SHA-256 evidence, and rejects setuid/setgid, world-writable regular files, special files and unsafe paths.
- Rescue initramfs supports deterministic LZ4 legacy framing for profiles whose boot policy requires `lz4`. The implementation is pinned to reviewed AOSP/LZ4 format references in `tools/ramdisk-format-locks.json`, uses bounded 8 MiB legacy blocks and independently decodes the resulting stream before acceptance.
- Source-locked ARM64 rescue payload contract pins BusyBox 1.38.0 source URL/SHA-256, the reviewed local miniconfig and `/init` hashes, ARM64 static-ELF policy, required rescue applets and forbidden remote-access applets.
- Dedicated `rescue-payload-repro` CI cross-builds the static ARM64 BusyBox payload twice, requires byte-for-byte equality, executes each binary under QEMU to collect an independently matching applet inventory, then stages and builds the profile-formatted deterministic rescue ramdisk. Run `35107467164` passed the entire chain.
- The rescue payload keeps `poweroff`/`reboot` explicitly compiled while external telinit handoff is disabled; network and SSH remain disabled by default and the init script enters only a local physical-console rescue shell.
- The rescue verifier independently parses normalized `newc` metadata, canonical ordering/trailer, file types, manifest digest and executable `/init`; artifact SHA-256 alone is not sufficient.
- Verified rescue-initramfs evidence can bind to a boot plan only when the exact ramdisk bytes, size, compression policy and plan digest agree. This host-side binding is not a physical rescue claim.
- First-boot candidate manifest schema v2 binds the verified boot authorization, rootfs evidence, package-manifest digest/count, source lock and repository snapshot.
- CI on Python **3.11, 3.12, 3.13 and 3.14**.

The rootfs CI pipeline is **not** proof that a reproducible KaliPhoneStudio rootfs artifact already exists. `rootfs_reproducible_artifact` remains false until a new real double-build run passes and its evidence is reviewed.

## Safety model

KaliPhoneStudio prefers **temporary boot first** and **inactive slot second**. It does not bypass physical bootloader-unlock confirmation. Persistent writes require an identified supported profile, verified identity, explicit confirmation and validated artifacts. No hardware feature is marked working without evidence from that exact phone/firmware baseline.

## AC2003 Beta blockers

Before the first Beta, the exact physical AC2003 must provide its OxygenOS build/fingerprint and Fastboot evidence; a matching stock `boot.img` must be obtained and validated; the candidate must successfully temporary-boot; rescue/logging must work; the kernel must reach Kali early userspace; required storage and charging/battery behavior must be safe; and recovery must be exercised and documented. Release artifacts additionally require a compatibility matrix, manifest and SHA-256 checksums.

## Development

```powershell
python -m pip install -r requirements.txt
python main.py
python -m pytest -q
```

`rootfs-repro` separates source/repository trust from artifact reproducibility: exact source commit + GPG-verified repository snapshot first, independent builds second, canonical evidence only after equality.

A rescue artifact can be built with its profile-driven compression policy without touching a phone. The release-oriented rescue path should use the locked reproducibility workflow rather than an arbitrary local BusyBox binary; the lower-level initramfs builder remains useful for development fixtures:

```powershell
python scripts/build_rescue_initramfs.py --profile-id oneplus/avicii --staging staging/rescue --out build/rescue.cpio.lz4 --evidence build/rescue-initramfs.json
```

See `ROADMAP.md`, `BUILD_STATUS.json`, `CHANGELOG.md` and `BETA_RELEASE_GATE.md` for the source-of-truth development state.

## Disclaimer

Unlocking bootloaders and writing phone partitions can erase data or make a device unbootable. Development builds are engineering artifacts, not daily-driver releases.
