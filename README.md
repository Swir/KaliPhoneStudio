<div align="center">

# ⚡ KaliPhoneStudio

### Multi-device engineering studio for porting Kali Linux / NetHunter Pro as the primary phone OS/userspace

**Profile-driven device support • Reproducible boot artifacts • Fail-closed recovery and hardware bring-up**

![Python](https://img.shields.io/badge/Python-3.11--3.14-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Linux](https://img.shields.io/badge/Linux-ARM64-02050A?style=for-the-badge&logo=linux&logoColor=62E5FF)
![Windows](https://img.shields.io/badge/Windows-Host_Tools-02050A?style=for-the-badge&logo=windows11&logoColor=62E5FF)
![Fastboot](https://img.shields.io/badge/Fastboot-Temporary_Boot_First-02050A?style=for-the-badge&logo=android&logoColor=62E5FF)

[![Tests](https://github.com/Swir/KaliPhoneStudio/actions/workflows/tests.yml/badge.svg)](https://github.com/Swir/KaliPhoneStudio/actions/workflows/tests.yml)
![Status](https://img.shields.io/badge/status-pre--beta-0088FF?style=flat-square)
![Progress](https://img.shields.io/badge/project-58%25-0088FF?style=flat-square)
![Author](https://img.shields.io/badge/by-SWIR-0088FF?style=flat-square)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## Project status

**Current development line: `0.6.57-dev` — 58% complete**

`███████████▋░░░░░░░░ 58%`

KaliPhoneStudio is still in engineering bring-up. The first profile is `oneplus/avicii` for the OnePlus Nord AC2003, but **no public Beta exists yet** and the phone is not declared fully hardware-supported.

A profile, green CI run, reproducible image, successful Fastboot return code, rescue marker, storage discovery record or early-userspace marker does **not** by itself satisfy release readiness. The authoritative gate is [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## What is KaliPhoneStudio?

KaliPhoneStudio is a profile-driven toolkit and engineering workflow for bringing **Kali Linux / NetHunter Pro to supported phones as the primary user-facing OS/userspace**, without using Android as the normal UI layer.

The project separates reusable device-independent logic under `kaliphonestudio/` from device-specific facts under `devices/<vendor>/<codename>/profile.json`. Hardware claims are intentionally stricter than host-side build results: physical-device evidence, recovery and rollback must be reviewed before release.

## Highlights

| Area | What it provides |
|---|---|
| ⚡ Multi-device core | Runtime profile registry, schema validation, identity binding and profile-specific confirmation tokens |
| 🔐 Source locking | Exact upstream commits, Git object identities, checksums and reproducible toolchain/build inputs |
| 🧱 Boot chain | Profile-driven boot layout, deterministic boot-image assembly and round-trip validation |
| 🐧 Kali ARM64 rootfs | Reviewed strict byte-identical host-side rootfs authority |
| 🧠 Kernel | Reviewed strict byte-identical `oneplus/avicii` ARM64 kernel authority |
| 🌳 DTB / DTBO | Reviewed strict byte-identical device-tree authority tied to the reviewed kernel |
| 🛟 Rescue | Deterministic ARM64 rescue initramfs, exact probe identity and bounded read-only diagnostics |
| 📱 Physical bring-up | Exact Fastboot/OxygenOS baseline contracts, temporary-boot-first policy and transcript binding |
| 💾 Storage safety | Source-pinned handoff discovery, typed physical storage observations and explicit manual-review gate |
| 🔁 Recovery-first policy | No persistent install claim before exact-device recovery/rollback evidence exists |

## Compatibility

| Device | Profile ID | Engineering state | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot/review pending | **Not released** |

Current reviewed avicii source baselines:

- device tree: `LineageOS/android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13`
- kernel: `LineageOS/android_kernel_oneplus_sm7250@fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`)

These are engineering references, not proof that every AC2003 hardware function works.

## Reviewed host-side authorities

All records below are host-side reproducibility evidence only and explicitly retain `hardware_verified=false` and `beta_gate_credit=false`.

| Layer | Authority run | Reviewed artifact |
|---|---:|---|
| Kali ARM64 rootfs | `35158577624` | SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, 137,460,600 B, 269 packages |
| avicii kernel | `35183670399` | ARM64 `Image` SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`, 43,878,416 B |
| avicii DTB/DTBO | `35196447576` | DTB `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`; packed DTBO `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` |

## Quick Start

### Requirements

For repository inspection and host-side tests:

- Python 3.11, 3.12, 3.13 or 3.14
- Git
- `pytest`

Device bring-up additionally depends on the exact source-locked tools and device-specific evidence required by the selected profile. Do not substitute random Fastboot, boot images or firmware packages for reviewed inputs.

### Clone and test

```bash
git clone https://github.com/Swir/KaliPhoneStudio.git
cd KaliPhoneStudio
python -m pip install pytest
python -m pytest -q
python -m compileall -q kaliphonestudio scripts
```

### Offline profile studio

```powershell
python main.py
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii --json
```

The offline UI/CLI performs no unguarded Fastboot/ADB write action and does not imply hardware support.

## Multi-device architecture

```text
KaliPhoneStudio/
├── kaliphonestudio/              # device-independent core
├── devices/
│   └── <vendor>/<codename>/
│       └── profile.json          # hardware/device policy
├── scripts/                      # explicit host-side tools and evidence recorders
├── evidence/                     # reviewed non-release authority records
├── docs/                         # safety and bring-up policy
└── tests/                        # fail-closed contract coverage
```

A device profile must provide unique identity rules, confirmation text, boot/partition constraints, pinned sources, recovery notes and host/hardware test contracts. Adding a profile JSON does not automatically create real device support.

## Rootfs handoff and storage review

The storage path is deliberately split into separate evidence layers:

1. `kaliphonestudio.rootfs_handoff` creates a discovery-only contract from the profile and exact source-pinned layout policy.
2. `kaliphonestudio.physical_storage_discovery` binds real topology/filesystem/encryption/free-space/recovery observations to the exact physical candidate and rescue/rootfs chain.
3. `kaliphonestudio.physical_storage_review` binds an explicit reviewer decision to that exact discovery evidence.

The 0.6.57 review gate may set only `strategy_design_allowed=true` after a human approves a review-ready discovery record. It still forces:

```text
target_selected=false
storage_path_bound=false
write_authorized=false
handoff_ready=false
storage_verified=false
recovery_verified=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
```

This means KaliPhoneStudio can distinguish **“reviewed evidence is good enough to design a proposal”** from **“a real storage target has been approved”**. Those are intentionally different milestones.

See [`docs/ROOTFS_HANDOFF_POLICY.md`](docs/ROOTFS_HANDOFF_POLICY.md) and [`docs/PHYSICAL_STORAGE_REVIEW_GATE.md`](docs/PHYSICAL_STORAGE_REVIEW_GATE.md).

## Physical storage review usage

After real physical discovery evidence has been captured and a human has reviewed it, bind the exact review record offline:

```bash
python scripts/record_physical_storage_review.py \
  --discovery-evidence evidence/physical-storage-discovery.json \
  --review-record evidence/operator-storage-review.json \
  --out evidence/physical-storage-review.json
```

This command performs no phone I/O and cannot select a block device or authorize a write.

## Kali early-userspace proof

`kaliphonestudio.kali_early_userspace` builds a deterministic proof overlay tied to the exact first-boot manifest, reviewed authority bundle and strict rootfs identity. A systemd oneshot emits exact stage/probe/candidate/rootfs markers before `basic.target`.

`kaliphonestudio.physical_kali_early_userspace` binds an operator-captured transcript to the same exact physical candidate and successful non-persistent temporary-boot execution. Marker matches still require human review and never auto-promote hardware/Beta credit.

Details: [`docs/KALI_EARLY_USERSPACE_PROOF.md`](docs/KALI_EARLY_USERSPACE_PROOF.md).

## CI and verification

The primary test matrix runs on:

- Python 3.11
- Python 3.12
- Python 3.13
- Python 3.14

Focused workflows cover kernel/rootfs/DT reproducibility, rescue payloads/read-only diagnostics, Kali early-userspace proof, rootfs-handoff source locking, typed physical-storage discovery and the manual storage-review gate. A green workflow is host evidence only.

## Roadmap and release gate

The authoritative roadmap is [`ROADMAP.md`](ROADMAP.md). The first working Beta remains blocked by physical-device evidence, including:

- exact AC2003 Fastboot/OxygenOS baseline;
- matching stock `boot.img` from the exact OTA;
- one exact physical candidate bound to reviewed rootfs/kernel/DT authorities;
- real storage/encryption/free-space/recovery discovery plus human review;
- separately reviewed reversible rootfs handoff strategy and target;
- explicitly confirmed temporary boot;
- rescue/logging and exact Kali early-userspace proof;
- UFS/storage validation beyond bounded reads;
- safe charging/battery behavior;
- display/touch proof or an explicitly reviewed console-only Beta scope;
- exercised recovery/rollback;
- final compatibility matrix, known issues, release manifest and SHA-256 set.

## Releases

There is **no public Beta release yet**. KaliPhoneStudio will not publish an empty, symbolic or placeholder release. The first prerelease must be built from the exact reviewed physical candidate and pass every applicable item in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Safety and limitations

1. Prefer temporary `fastboot boot` before persistent writes.
2. Never flash a physical phone without explicit user interaction and an exact verified baseline.
3. Fail closed on identity, firmware, provenance, checksum, partition-layout or evidence drift.
4. Keep host CI separate from hardware support claims.
5. Do not weaken strict reproducibility rules to make a gate pass.
6. Do not enable remote access or embed credentials by default.
7. Keep device-specific facts in profiles and reviewed evidence, not hardcoded into the common core.
8. Never convert a storage-layout hint or review-ready record into a write target automatically.

## 🔎 Search Keywords

`KaliPhoneStudio` • `Kali Linux phone` • `NetHunter Pro porting` • `Linux on phone` • `ARM64 mobile Linux` • `OnePlus Nord AC2003` • `oneplus avicii Linux` • `multi-device phone porting` • `Fastboot temporary boot` • `Android boot image tooling` • `boot.img repack` • `DTB DTBO` • `Kali ARM64 rootfs` • `phone recovery tooling` • `reproducible kernel build` • `mobile Linux bring-up`

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

<div align="center">

### `BUILD • VERIFY • BOOT • RECOVER • EVOLVE`

⭐ **If KaliPhoneStudio is useful, consider leaving a star.**

[**← SWIR profile**](https://github.com/Swir) · [**All projects →**](https://github.com/Swir?tab=repositories)

</div>
