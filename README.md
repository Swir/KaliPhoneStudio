# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux / NetHunter Pro as the primary phone OS/userspace**, without Android as the user-facing layer.

The repository is conservative by design: a device profile, green CI, reproducible artifact, successful Fastboot command, rescue marker, read-only diagnostic or early-userspace marker does **not** by itself mean a phone is supported. Public Beta requires every applicable host and physical gate in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress is weighted toward physical boot, hardware validation, recovery and release readiness. Host reproducibility and safety are foundations, not substitutes for exact-device evidence.

> **Current development line: `0.6.54-dev`.** Reviewed Kali ARM64 rootfs, `oneplus/avicii` kernel and DTB/DTBO authorities remain strict-byte-identical host-side. 0.6.54 adds a deterministic proof overlay that can distinguish "rescue initramfs ran" from "the exact reviewed Kali rootfs reached early systemd userspace". The probe is cryptographically bound to the exact candidate/rootfs authority chain and physical transcript parser, but still sets `kali_early_userspace_verified=false`, `hardware_verified=false` and `beta_gate_credit=false` until manual review of a real phone run. Rootfs transport/staging is intentionally **not** hard-coded by this milestone.

## Source of truth and architecture

`Swir/KaliPhoneStudio` is the only project source of truth. Device-independent code belongs under `kaliphonestudio/`; device knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile is not a hardware-support claim. Before destructive actions become eligible it must define identity, confirmation token, boot/partition constraints, pinned sources, recovery notes and host/hardware test contracts. The common core must remain profile-driven.

### Active profile

| Device | Profile ID | State | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

Reviewed source baselines are pinned to full upstream commits. For avicii the current device-tree baseline is LineageOS `android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13`; the kernel bring-up baseline is `android_kernel_oneplus_sm7250@fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`). These are engineering references, not proof that hardware works.

## Reviewed host-side authorities

These records are strict, immutable host-side evidence only; all explicitly retain `hardware_verified=false` and `beta_gate_credit=false`.

| Layer | Authority run | Reviewed artifact |
|---|---:|---|
| Kali ARM64 rootfs | `35158577624` | SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, 137,460,600 B, 269 packages |
| avicii kernel | `35183670399` | ARM64 `Image` SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`, 43,878,416 B |
| avicii DTB/DTBO | `35196447576` | DTB `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`; packed DTBO `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` |

## Implemented safety/build foundations

- Runtime multi-device profile registry and schema/identity/path contract.
- Verified serial bound to `profile_id` and a profile-specific destructive confirmation token.
- A/B-aware planning, dry-run defaults and inactive-slot-only policy for any future persistent test.
- Temporary `fastboot boot` path is preferred before persistent writes.
- Source-locked Fastboot/boot-tool/payload-extractor/kernel/toolchain/rootfs/DT sources and reproducible host workflows.
- Read-only Fastboot/OxygenOS baseline capture with exact tool identity and raw transcript binding.
- Exact OTA → payload → stock `boot.img` provenance and physical-baseline bundle.
- Profile-driven boot-image assembly with deterministic double-build and round-trip checks.
- Reviewed reproducible kernel, rootfs and DTB/DTBO authorities cross-bound to an exact first-boot candidate.
- Deterministic rescue initramfs with source-locked static ARM64 BusyBox, exact probe id and no automatic persistent-storage access.
- Manual-only bounded rescue functional probes: up to one 4096-byte read from up to eight non-removable whole block devices into `/dev/null`, plus paired battery telemetry. These signals do not automatically verify storage or charging.
- Offline GUI/CLI profile inspection remains non-destructive and performs no Fastboot/ADB action.

## Kali early-userspace proof (0.6.54)

The new `kaliphonestudio.kali_early_userspace` layer builds a deterministic USTAR proof overlay bound to:

- exact first-boot manifest SHA-256;
- exact reviewed authority-bundle SHA-256;
- exact rootfs-authority binding and authority SHA-256;
- exact strict rootfs artifact SHA-256/size;
- ARM64 architecture and rootfs variant.

The overlay installs one systemd oneshot before `basic.target`. It emits five exact markers including `KPS_KALI_STAGE=rootfs-systemd-early-v1`, deterministic probe id, candidate manifest digest, rootfs authority digest and rootfs artifact digest. It enables no SSH/network service, embeds no credentials, performs no Fastboot/ADB call and writes no phone storage.

`kaliphonestudio.physical_kali_early_userspace` then binds an operator-captured transcript to the same physical candidate gate and successful non-persistent temporary-boot execution. Missing, conflicting or excessive markers; serial/profile drift; candidate/rootfs drift; changed transcripts; failed boots; or storage-write claims are rejected fail-closed.

A complete marker match is still an **observation requiring manual review**, not an automatic hardware/Beta pass. Full design details: [`docs/KALI_EARLY_USERSPACE_PROOF.md`](docs/KALI_EARLY_USERSPACE_PROOF.md).

## Rootfs handoff remains a real blocker

0.6.54 intentionally does **not** pretend that proof markers solve rootfs transport. Before a physical Kali-rootfs boot can be attempted, the exact reviewed rootfs must be made available through a safe, reversible, profile-driven staging/handoff strategy that respects UFS/encryption reality, temporary-boot-first policy and recovery. No global AC2003 storage path is hard-coded.

## Offline application

```powershell
python main.py
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii --json
```

The profile UI/CLI never implies hardware support and exposes no unguarded write path.

## CI

Primary Python matrix:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

Focused workflows cover kernel/rootfs/DT reproducibility, rescue payloads/read-only diagnostics and the Kali early-userspace proof contract. A green workflow is host evidence only.

## Beta release policy

**Beta is currently blocked.** The first AC2003 Beta requires at minimum:

- real physical Fastboot identity and exact OxygenOS build/fingerprint;
- matching stock `boot.img` from the exact OTA;
- one exact physical candidate bound to reviewed kernel/rootfs/DT authorities;
- successful temporary boot on that same phone;
- usable rescue/logging path and manually reviewed exact rescue markers;
- a safe, explicit rootfs staging/handoff method and proof that the kernel reached the intended Kali early userspace/rootfs;
- required storage/UFS validation;
- safe charging/battery behavior for testing;
- display/touch proof or an explicitly reviewed console-only Beta scope;
- documented recovery/rollback exercised on the exact physical baseline;
- final compatibility matrix, release manifest and SHA-256 checksums.

Do not publish an empty/symbolic Beta. Stable has a higher threshold.

## Safety principles

1. Prefer temporary boot over persistent writes.
2. Never flash a physical phone without explicit user interaction and a verified exact-device baseline.
3. Fail closed on identity, firmware, provenance, checksum, partition-layout or evidence drift.
4. Keep hardware claims separate from host CI.
5. Do not weaken strict reproducibility rules to make a gate pass.
6. Do not add credentials or enable remote access by default.
7. Keep the common core multi-device; phone-specific facts belong in profiles and their reviewed evidence.

## Development

```bash
python -m compileall -q kaliphonestudio scripts tests
python -m pytest -q
```

Repository documentation and checked-in authority records are part of the safety contract and are CI-validated.
