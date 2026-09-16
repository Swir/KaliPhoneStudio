# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux as the primary phone operating system/userspace**, without Android as the user-facing OS layer.

## Project progress

**52% complete**

`██████████▍░░░░░░░░░ 52%`

Progress is weighted toward real device bring-up, hardware validation, recovery and release readiness. Host-side CI/tests alone do not significantly raise this percentage.

> Current status: **0.6.26-dev** — the host boot chain, exact-firmware authorization, profile-driven kernel/device-tree evidence and kernel reproducibility contracts are in place. First-boot candidate schema v6 binds the reproducible kernel evidence together with exact firmware, boot, DTB/DTBO and rootfs evidence. The real ARM64 rootfs workflow completed two independent builds but failed the strict byte-for-byte acceptance step, so `rootfs_reproducible_artifact` remains false. The new rootfs diagnostic layer records bounded member/content/metadata/order differences after such a failure without changing the strict gate or granting Beta credit. This remains **host-side provenance and preflight only**: no final kernel/DTB/DTBO candidate or Kali userspace has been proven on a physical AC2003. No public Beta is allowed until the physical device passes `BETA_RELEASE_GATE.md`.

## Architecture

The Python core under `kaliphonestudio/` is device-independent. Hardware knowledge belongs in `devices/<vendor>/<codename>/profile.json` and target documentation/build modules. Adding a JSON profile does **not** mean hardware support exists.

A schema-v2 profile must provide unambiguous identity, a destructive-action confirmation token, boot/partition constraints, firmware hints, full-commit upstream source locks, recovery notes, explicit host/hardware test contracts, a Fastboot baseline contract and a strict kernel contract. The registry fails closed when fields are missing, malformed or cross-reference a source ambiguously. Boot policy is strictly typed, A/B partition names are validated, `profile_id` is bound to its `devices/vendor/codename/profile.json` location, upstream sources must be credential-free HTTPS URLs pinned to full commits, Fastboot semantic fields must resolve to explicitly required variable names, and kernel source/config paths must remain safe profile-defined relative paths.

## Active device profiles

| Device | Profile ID | Status | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii engineering board baseline is pinned to LineageOS `android_device_oneplus_avicii` commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. That source records Android boot header v2, 4096-byte pages, in-boot DTB, separate DTBO and LZ4 ramdisk policy. Its kernel dependency is independently pinned in the device profile to LineageOS `android_kernel_oneplus_sm7250` commit `fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`) as a reviewed bring-up baseline. DTB parsing semantics are pinned to AOSP `platform/external/dtc` commit `295e585a34339f6280e561278288e4490d9390f7`; Android DT table semantics are pinned to AOSP `platform/system/libufdt` commit `1ebea487f96b2a4d1a4e1a28ea338591c36a4f8b`. These are source references, **not** proof that Kali hardware functions work and not yet the final hardware-verified first-boot kernel/device-tree set.

## Implemented host-side foundations

- Runtime device-profile registry and profile-based ADB/Fastboot identity.
- Verified serial binding to `profile_id`.
- Profile-specific confirmation for destructive actions.
- A/B slot-aware planning, dry-run defaults and guarded inactive-slot writes.
- Temporary `fastboot boot` workflow before persistent boot-slot testing.
- Manifest/SHA-256 and partition-size validation.
- Strict multi-device profile contract for boot header/page/kernel/DTB/DTBO/ramdisk compression, safe A/B partition identifiers, exact kernel metadata and full-commit HTTPS upstream sources.
- Profile schema v2 generic read-only Fastboot probe contract. `oneplus/avicii` requires product/serial, current slot, slot count, unlocked/secure state and bootloader/baseband versions, with an expected two-slot A/B layout.
- Offline Fastboot baseline importer hashes the original transcript, rejects failed/ambiguous/malformed captures and emits canonical evidence without invoking `adb`, `fastboot` or any phone write.
- Fastboot baseline evidence is deliberately marked `beta_gate_credit=false`; raw transcript/evidence may contain a serial and should be treated as private engineering data rather than a public release artifact.
- Exact Fastboot baseline firmware build/fingerprint is bound to exact OTA `post-build` / `post-build-incremental` provenance before temporary-boot authorization.
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
- Fail-closed `TemporaryBootAuthorization` schema v2 ties the verified phone serial to the captured Fastboot baseline digest, exact firmware build/fingerprint, stock OTA provenance, plan digest, reproducible assembly and structural verification.
- Device-independent kernel evidence contract creates a canonical `KernelBuildPlan` from the selected profile and exactly one pinned kernel source.
- Exact kernel checkout evidence verifies git `HEAD`, expected Makefile kernel version and SHA-256 of the profile-selected defconfig/config fragments before build evidence can advance.
- Generated final `.config` evidence must satisfy every profile-required `CONFIG_*` state and is bound by SHA-256/size.
- ARM64 kernel preflight verifies Linux `Image` magic, SHA-256 and size, then re-hashes the image when source/config/image evidence is bundled to prevent post-verification drift.
- `KernelCandidateEvidence` binds plan, source commit/version, config evidence and exact `Image`; the first-boot candidate additionally requires that the kernel SHA-256/size equal the kernel input in the approved `BootBuildPlan`.
- Kernel reproducibility evidence requires two independent build roots, revalidates both final `.config` and ARM64 `Image` outputs against the same profile-driven plan, and accepts evidence only when both pairs are byte-identical. Canonical evidence intentionally omits host paths and does not grant hardware credit.
- `tools/device-tree-format-locks.json` pins exact upstream FDT and Android DT table format references; dedicated CI fetches those exact commits and verifies the expected authoritative format definitions are still present.
- Device-independent DTB verification parses big-endian FDT v17 headers, validates block offsets/ranges/alignment, supports safe zero-padded concatenated DTB bundles and emits canonical SHA-256/size/tree-count evidence.
- Device-independent DTBO verification parses the Android DT table header/entries, validates page/table metadata, non-overlapping payload ranges, every embedded FDT and zero-only padding, then enforces the selected profile's DTBO partition limit.
- `DeviceTreeCandidateEvidence` rejects profile/plan drift and requires exact DTB/DTBO SHA-256 and size equality with the approved `BootBuildPlan`; `scripts/verify_device_tree_candidate.py` provides the same fail-closed flow offline without touching a phone.
- First-boot candidate manifest schema v6 carries Fastboot baseline/exact firmware identity, temporary-boot authorization, boot-plan digest, reproducible kernel evidence, exact structural DTB/DTBO evidence and rootfs/package evidence in one canonical host-side contract.
- Versioned `tools/extractor-locks.json` contract pinning extractor source, exact Go toolchain and deterministic build command.
- Dedicated extractor reproducibility CI builds the exact pinned source twice on Linux amd64 and Windows amd64 and emits SHA-256 evidence only after byte-for-byte equality.
- Linux amd64 and Windows amd64 extractor reproducibility passed in GitHub Actions run `35018283145`.
- Authorized extractor SHA-256: Linux amd64 `a9e5806356af76b11643f3129b5516a638e9dc0c53cefd40b665a916683c83d0`; Windows amd64 `35fbcd36c553f81375a904ceca58aef5289da2e2e067fc0e6c835390588edfa5`.
- Kali ARM64 rootfs source lock pinned to official NetHunter rootfs tag `2026.2`, commit `20238a2f2d547d7989a4dec287d4f5ef528ed701`.
- Rootfs lock schema v2 forces the Kali mirror to HTTPS and pins Kali archive signing fingerprint `827C8569F2518CC677FECA1AED65462EC8D5E4C5`.
- `scripts/capture_kali_snapshot.py` requires successful `gpgv` validation of `InRelease` by that fingerprint, then records exact `InRelease` SHA-256 and ARM64 package-index paths/sizes/SHA-256 values.
- Rootfs evidence requires two independent byte-identical tar.xz builds and derives a normalized package/version/architecture manifest directly from the archive's single safe `var/lib/dpkg/status` location, accepting the pinned builder's one-top-level-directory layout while rejecting traversal, deeper suffix tricks and ambiguous duplicates.
- Rootfs build execution performs a fail-closed host preflight requiring `qemu-aarch64-static`, rejecting a competing dynamic `qemu-aarch64`, preventing the pinned upstream dependency helper from replacing the static emulator, and revalidating the signed HTTPS `InRelease` state immediately before each build.
- The reviewed Kali archive keyring used for snapshot verification is carried into the rootfs job so debootstrap can validate Kali repository signatures itself.
- `.github/workflows/rootfs-repro.yml` performs signed-snapshot validation on PRs and executes two real pinned ARM64 builds on relevant `main` pushes; strict acceptance still requires byte-identical archives and package evidence.
- Failed strict rootfs comparisons now trigger a bounded, safe `tar.xz` diagnostic report that compares canonical member sets, order, metadata and streamed regular-file SHA-256 values. The report is non-release evidence with `beta_gate_credit=false`; it is uploaded only to explain a failure, after which the workflow still fails.
- Device-independent deterministic rescue-initramfs construction normalizes uid/gid/mtime and entry ordering, builds twice, requires byte equality, emits canonical SHA-256 evidence, and rejects setuid/setgid, world-writable regular files, special files and unsafe paths.
- Rescue initramfs supports deterministic LZ4 legacy framing for profiles whose boot policy requires `lz4`. The implementation is pinned to reviewed AOSP/LZ4 format references in `tools/ramdisk-format-locks.json`, uses bounded 8 MiB legacy blocks and independently decodes the resulting stream before acceptance.
- Source-locked ARM64 rescue payload contract pins BusyBox 1.38.0 source URL/SHA-256, reviewed local miniconfig and `/init` hashes, ARM64 static-ELF policy, required rescue applets and forbidden remote-access applets.
- Dedicated `rescue-payload-repro` CI cross-builds the static ARM64 BusyBox payload twice, requires byte-for-byte equality, executes each binary under QEMU to compare applet inventory, then stages and builds the profile-formatted deterministic rescue ramdisk. The reviewed main chain passed.
- Rescue payload keeps `poweroff`/`reboot` explicitly compiled while external telinit handoff is disabled; network and SSH remain disabled by default and `/init` enters only a local physical-console rescue shell.
- Rescue verifier independently parses normalized `newc` metadata, canonical ordering/trailer, file types, manifest digest and executable `/init`; artifact SHA-256 alone is not sufficient.
- Verified rescue-initramfs evidence can bind to a boot plan only when exact ramdisk bytes, size, compression policy and plan digest agree. This host-side binding is not a physical rescue claim.
- CI targets Python **3.11, 3.12, 3.13 and 3.14**.

The latest real ARM64 rootfs double-build completed both builds but failed the strict reproducibility verifier. `rootfs_reproducible_artifact` therefore remains **false**. Rootfs diagnostics may identify whether divergence is container-only, metadata, ordering or file-content related, but they never substitute for byte-for-byte acceptance.

## Safety model

KaliPhoneStudio prefers **temporary boot first** and **inactive slot second**. It does not bypass physical bootloader-unlock confirmation. Persistent writes require an identified supported profile, verified identity, explicit confirmation and validated artifacts. Before temporary-boot authorization, the device serial and exact captured firmware baseline must agree with the stock OTA provenance used to build the image. Kernel and device-tree evidence must additionally match the exact kernel/DTB/DTBO bytes carried by the approved boot plan. No hardware feature is marked working without evidence from that exact phone/firmware baseline.

## AC2003 Beta blockers

Before the first Beta, the exact physical AC2003 must still provide its real OxygenOS build/fingerprint and Fastboot transcript evidence; a matching stock `boot.img` must be obtained and validated; a concrete final kernel + DTB/DTBO candidate must be built and proven on that phone; the candidate must successfully temporary-boot; rescue/logging must work; the kernel must reach Kali early userspace/rootfs; required storage and charging/battery behavior must be safe; and recovery must be exercised and documented. Release artifacts additionally require a compatibility matrix, manifest and SHA-256 checksums.

## Development

```powershell
python -m pip install -r requirements.txt
python main.py
python -m pytest -q
```

`rootfs-repro` separates source/repository trust from artifact reproducibility: exact source commit + GPG-verified repository snapshot first, independent builds second, canonical evidence only after equality. When strict comparison fails, the CI emits a bounded diagnostic artifact and then remains failed.

Offline rootfs divergence diagnostics can also be generated explicitly without changing release acceptance:

```powershell
python scripts/diagnose_rootfs_repro.py --archive-a build/rootfs-a.tar.xz --archive-b build/rootfs-b.tar.xz --out evidence/rootfs-repro-diagnostic.json
```

A rescue artifact can be built with its profile-driven compression policy without touching a phone. The release-oriented rescue path should use the locked reproducibility workflow rather than an arbitrary local BusyBox binary; the lower-level initramfs builder remains useful for development fixtures:

```powershell
python scripts/build_rescue_initramfs.py --profile-id oneplus/avicii --staging staging/rescue --out build/rescue.cpio.lz4 --evidence build/rescue-initramfs.json
```

The read-only Fastboot baseline workflow is documented in `docs/FASTBOOT_BASELINE.md`. Its importer operates only on a previously saved transcript:

```powershell
python scripts/import_fastboot_baseline.py --profile-id oneplus/avicii --transcript fastboot-getvar-all.txt --firmware-build "EXACT_BUILD" --firmware-fingerprint "EXACT_FINGERPRINT" --out evidence/fastboot-baseline.json
```

DTB/DTBO validation is also offline and profile-driven. It requires the already approved canonical boot-plan JSON and produces separate canonical evidence without invoking Fastboot:

```powershell
python scripts/verify_device_tree_candidate.py --profile-id oneplus/avicii --boot-plan build/boot-plan.json --dtb build/dtb --dtbo build/dtbo.img --out evidence/device-tree.json
```

See `ROADMAP.md`, `BUILD_STATUS.json`, `CHANGELOG.md` and `BETA_RELEASE_GATE.md` for the source-of-truth development state.

## Disclaimer

Unlocking bootloaders and writing phone partitions can erase data or make a device unbootable. Development builds are engineering artifacts, not daily-driver releases.
