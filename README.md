# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux as the primary phone operating system/userspace**, without Android as the user-facing OS layer.

## Project progress

**49% complete**

`██████████░░░░░░░░░░ 49%`

Progress is weighted toward real device bring-up, hardware validation, recovery and release readiness. Host-side CI/tests alone do not significantly raise this percentage.

> Current status: **0.6.19-dev** — the verified host boot chain is in place, the rootfs path uses a GPG-verified Kali repository snapshot and exact-source double-build workflow, and a device-independent deterministic rescue-initramfs artifact contract is now implemented and cryptographically bound to boot-plan ramdisk evidence. Compression compatibility is fail-closed: the current deterministic rescue builder emits gzip, while `oneplus/avicii` requires LZ4, so AC2003 rescue boot remains blocked until a deterministic LZ4 stage is implemented and verified. The first post-merge real rootfs build exposed an Ubuntu/QEMU packaging conflict; KaliPhoneStudio now fail-closes on the host emulator state, preserves `qemu-aarch64-static`, revalidates the signed repository state immediately before each build, and supplies the reviewed Kali keyring to debootstrap. The repaired real double-build is being validated on `main`; it is **not** counted as reproducible until that run passes and its evidence is reviewed. The first active target remains **OnePlus Nord AC2003 (`oneplus/avicii`)**. No public Beta is allowed until the physical device passes `BETA_RELEASE_GATE.md`.

## Architecture

The Python core under `kaliphonestudio/` is device-independent. Hardware knowledge belongs in `devices/<vendor>/<codename>/profile.json` and target documentation/build modules. Adding a JSON profile does **not** mean hardware support exists.

A schema-v1 profile must provide unambiguous identity, a destructive-action confirmation token, boot/partition constraints, firmware hints, full-commit upstream source locks, recovery notes, and explicit host/hardware test contracts. The registry fails closed when these fields are missing or malformed.

## Active device profiles

| Device | Profile ID | Status | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii engineering baseline is pinned to LineageOS `android_device_oneplus_avicii` commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. This is a source reference, **not** proof that Kali hardware functions work.

## Implemented host-side foundations

- Runtime device-profile registry and profile-based ADB/Fastboot identity.
- Verified serial binding to `profile_id`.
- Profile-specific confirmation for destructive actions.
- A/B slot-aware planning, dry-run defaults and guarded inactive-slot writes.
- Temporary `fastboot boot` workflow before persistent boot-slot testing.
- Manifest/SHA-256 and partition-size validation.
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
- Rootfs evidence requires two independent byte-identical tar.xz builds and derives a normalized package/version/architecture manifest directly from `var/lib/dpkg/status` inside the archive.
- Rootfs build execution now performs a fail-closed host preflight that requires `qemu-aarch64-static`, rejects a competing dynamic `qemu-aarch64`, prevents the pinned upstream dependency helper from replacing the static emulator, and verifies the live HTTPS `InRelease` still matches the previously GPG-validated snapshot before each real build.
- The reviewed Kali archive keyring used for snapshot verification is carried into the rootfs job so debootstrap can validate Kali repository signatures itself.
- `.github/workflows/rootfs-repro.yml` performs signed-snapshot validation on PRs and executes two real pinned ARM64 builds on relevant `main` pushes; the result is fail-closed if bytes or package evidence diverge.
- Device-independent deterministic rescue-initramfs construction: gzip/newc output normalizes uid/gid/mtime and entry ordering, builds twice, requires byte equality, emits canonical SHA-256 evidence, and rejects setuid/setgid/special-file/unsafe-path inputs. This is an artifact contract, not proof of a phone rescue path.
- Fail-closed initramfs-to-boot-plan binding ties the exact reproducible ramdisk bytes, `/init` digest and initramfs evidence digest to a profile-bound `BootBuildPlan`; incompatible compression policies are rejected rather than coerced.
- First-boot candidate manifest schema v2 binds the verified boot authorization, rootfs evidence, package-manifest digest/count, source lock and repository snapshot.
- CI on Python **3.11, 3.12, 3.13 and 3.14**.

The rootfs CI pipeline is **not** proof that a reproducible KaliPhoneStudio rootfs artifact already exists. `rootfs_reproducible_artifact` remains false until a real double-build run passes and its evidence is reviewed.

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

See `ROADMAP.md`, `BUILD_STATUS.json`, `CHANGELOG.md` and `BETA_RELEASE_GATE.md` for the source-of-truth development state.

## Disclaimer

Unlocking bootloaders and writing phone partitions can erase data or make a device unbootable. Development builds are engineering artifacts, not daily-driver releases.
