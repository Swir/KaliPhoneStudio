<!-- SWIR-README-STANDARD:v2 -->

<div align="center">

<img width="100%" src="assets/readme/hero.svg" alt="KaliPhoneStudio — evidence-driven Kali Linux phone bring-up" />

<br>

![Python](https://img.shields.io/badge/Python-3.11--3.14-02050A?style=for-the-badge&logo=python&logoColor=62E5FF)
![Architecture](https://img.shields.io/badge/Architecture-ARM64-02050A?style=for-the-badge&logo=arm&logoColor=62E5FF)
![Status](https://img.shields.io/badge/Status-Development-02050A?style=for-the-badge&logo=githubactions&logoColor=62E5FF)
![Beta](https://img.shields.io/badge/Beta-BLOCKED-02050A?style=for-the-badge&logo=securityscorecard&logoColor=62E5FF)

[![Tests](https://github.com/Swir/KaliPhoneStudio/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Swir/KaliPhoneStudio/actions/workflows/tests.yml)

**KaliPhoneStudio is a multi-device engineering studio for porting Kali Linux / NetHunter Pro as the primary phone OS/userspace, without Android as the user-facing layer.**

[**Highlights**](#highlights) · [**Quick Start**](#quick-start) · [**Compatibility**](#compatibility) · [**Architecture**](#multi-device-architecture) · [**Roadmap**](#roadmap-and-releases) · [**Safety**](#safety-and-limitations)

</div>

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

## Project status

| Item | Status |
|---|---|
| Current development line | `0.6.61-dev` |
| Completion | **58%** |
| Current stage | Development / physical bring-up |
| First device profile | OnePlus Nord AC2003 — `oneplus/avicii` |
| Latest public release | **Not published yet** |
| Beta gate | **BLOCKED** |

`███████████▋░░░░░░░░ 58%`

Host-side foundations are deliberately ahead of physical-device validation. Reviewed strict A/B authorities exist for the Kali ARM64 rootfs, avicii kernel and DTB/DTBO. The physical evidence chain now includes a bounded sysfs-only hardware-presence survey plus a fail-closed manual-review contract. None of that is counted as real hardware support until the exact AC2003 passes the physical gate.

The authoritative release rules are in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Overview

KaliPhoneStudio turns phone-specific Kali Linux / NetHunter Pro porting into a profile-driven, evidence-bound workflow instead of a set of one-off flashing scripts. The common Python core stays device-independent; device-specific identity, boot, partition, source and recovery knowledge lives under validated profiles.

Permanent flashing is not the default path. The project prefers exact provenance, temporary `fastboot boot`, read-only discovery, explicit human review and tested recovery before any persistent write is considered.

## Highlights

| Area | What KaliPhoneStudio provides |
|---|---|
| ⚡ Multi-device core | Device-independent runtime with profile-driven identity, boot, partition, source and recovery contracts. |
| 🔐 Fail-closed safety | Exact serial/profile/firmware/candidate binding before sensitive operations become eligible. |
| 🧬 Reproducible builds | Reviewed strict A/B authorities for Kali ARM64 rootfs, avicii kernel and DTB/DTBO artifacts. |
| 📦 Boot provenance | Exact OTA → payload → stock `boot.img` evidence plus deterministic boot-image assembly and round-trip checks. |
| 🛟 Rescue path | Deterministic source-locked ARM64 rescue initramfs with exact probe identity and remote access disabled by default. |
| 🧪 Physical evidence | Rescue markers, read-only diagnostics, explicit bounded functional probes, hardware-presence survey and Kali early-userspace markers. |
| 👁️ Manual hardware review | Exact survey + canonical review record + separate notes can be accepted only as context for later functional testing; no subsystem is auto-verified. |
| 💾 Storage safety | Discovery/review/session/dossier layers cannot choose a `/dev/...` target, mount storage or authorize a write. |
| 🖥️ Offline UI/CLI | Safe profile inspection without automatically invoking ADB/Fastboot or exposing unguarded write controls. |

## Compatibility

| Target | Current state |
|---|---|
| OnePlus Nord AC2003 (`oneplus/avicii`) | Bring-up; physical first boot pending |
| Other phones | Not supported until a validated profile and real hardware evidence are added |
| Persistent installation | **Not released** |
| Public Beta | **Blocked by the physical release gate** |

The avicii engineering baseline is pinned to `LineageOS/android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13` and `LineageOS/android_kernel_oneplus_sm7250@fb4b4374d3b9ad0f10ba38d159585129f092fb3d`. These are source baselines, not hardware-working claims.

## Reviewed host-side authorities

All records below remain host-side evidence only and carry no hardware/Beta credit.

| Layer | Authority run | Reviewed artifact |
|---|---:|---|
| Kali ARM64 rootfs | `35158577624` | SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, 137,460,600 B, 269 packages |
| avicii kernel | `35183670399` | ARM64 `Image` SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`, 43,878,416 B |
| avicii DTB/DTBO | `35196447576` | DTB `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`; packed DTBO `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` |

## Quick Start

### Requirements

- Python **3.11–3.14**
- Git
- packages from [`requirements.txt`](requirements.txt): PySide6 and PyYAML
- specialized Linux build dependencies only for kernel/rootfs/DT workflows documented by their scripts and CI

### Run from source

```bash
git clone https://github.com/Swir/KaliPhoneStudio.git
cd KaliPhoneStudio
python -m venv .venv
python -m pip install -r requirements.txt
python main.py
```

Useful non-destructive commands:

```bash
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii --json
```

## Multi-device architecture

`Swir/KaliPhoneStudio` is the project source of truth. Device-independent code belongs under `kaliphonestudio/`; device knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile is not a support claim. Before destructive actions can even become eligible it must define unique identity, confirmation token, boot/partition constraints, pinned sources, recovery notes and host/hardware test contracts. The common core must not hardcode AC2003-specific facts when the same decision can be profile-driven.

## Physical hardware survey review

The 0.6.60 rescue survey records only bounded sysfs-visible presence/state for USB, network/rfkill, sound, thermal, input, framebuffer/DRM and power supplies. It does not activate those subsystems.

0.6.61 adds an exact manual-review layer. A safe template is rejected by default:

```bash
python scripts/prepare_physical_hardware_review.py \
  --survey-evidence evidence/physical-hardware-survey.json \
  --reviewer operator-1 \
  --out evidence/operator-hardware-review.json
```

After real human review, bind the exact canonical record and separate notes:

```bash
python scripts/review_physical_hardware_survey.py \
  --survey-evidence evidence/physical-hardware-survey.json \
  --review-record evidence/operator-hardware-review.json \
  --review-notes evidence/operator-hardware-review-notes.txt \
  --out evidence/physical-hardware-review.json
```

`accepted_as_context=true` means only that the exact survey may inform later subsystem-specific physical tests. Display, touch, USB, Wi-Fi, Bluetooth, audio, modem, charging/power, thermal, storage, recovery, hardware verification and Beta credit remain false. See [`docs/PHYSICAL_HARDWARE_SURVEY_REVIEW.md`](docs/PHYSICAL_HARDWARE_SURVEY_REVIEW.md).

## Rootfs handoff and storage evidence

The storage pipeline intentionally stops before target selection. It binds a source-pinned layout contract, read-only physical discovery, exact manual review, cross-bound bring-up session and exact-file dossier. Even a review accepted for later strategy design cannot choose a block-device path or authorize a write.

For avicii, the pinned LineageOS `init/fstab.qcom` blob is `20873c3a84e1e6e8d2483e313f561ad35ded7355`. `userdata` is treated only as a discovery role/hint; it is not an approved Kali rootfs target.

See [`docs/ROOTFS_HANDOFF_POLICY.md`](docs/ROOTFS_HANDOFF_POLICY.md), [`docs/PHYSICAL_STORAGE_REVIEW.md`](docs/PHYSICAL_STORAGE_REVIEW.md), [`docs/PHYSICAL_BRINGUP_SESSION.md`](docs/PHYSICAL_BRINGUP_SESSION.md) and [`docs/PHYSICAL_BRINGUP_DOSSIER.md`](docs/PHYSICAL_BRINGUP_DOSSIER.md).

## Safety and limitations

- Prefer temporary `fastboot boot` over persistent writes.
- Never flash a physical phone without explicit user interaction and a verified exact-device baseline.
- Fail closed on identity, firmware, provenance, checksum, partition-layout or evidence drift.
- Keep host CI and physical hardware claims separate.
- Treat sysfs hardware presence and accepted contextual review as observations only, never functional proof.
- Never weaken strict reproducibility to make a gate pass.
- Do not embed credentials or enable remote access by default.
- No public Beta or Stable release exists until the complete physical gate is reviewed.

## Development and verification

```bash
python -m compileall -q kaliphonestudio scripts tests
python -m pytest -q
```

Focused CI covers kernel/rootfs/DT reproducibility, rescue payloads/read-only diagnostics, hardware-presence survey and review policy, Kali early-userspace proof, rootfs handoff, physical-storage evidence, bring-up sessions and exact-file dossier verification.

## Roadmap and releases

- [`ROADMAP.md`](ROADMAP.md) — authoritative milestone status
- [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md) — release gate
- [`CHANGELOG.md`](CHANGELOG.md) — active development changes
- [`BUILD_STATUS.json`](BUILD_STATUS.json) — machine-readable state

There is currently **no public Beta release**. The first Beta will be published only from an exact reviewed physical candidate with real assets, compatibility matrix, known issues, recovery instructions and SHA-256 checksums.

## 🔎 Search Keywords

`Kali Linux phone port` • `NetHunter Pro phone` • `Linux on smartphone` • `ARM64 Linux phone` • `OnePlus Nord AC2003 Linux` • `avicii Linux port` • `multi-device phone porting` • `Fastboot temporary boot` • `Android boot image tooling` • `DTB DTBO build` • `Kali ARM64 rootfs` • `phone rescue initramfs` • `phone hardware survey` • `reproducible kernel build` • `UFS storage discovery` • `safe phone flashing workflow`

<img width="100%" src="https://raw.githubusercontent.com/Swir/Swir/main/assets/power-divider-v4.svg" alt="SWIR electric divider" />

<div align="center">

### `BUILD • VERIFY • BOOT • RECOVER`

⭐ **If KaliPhoneStudio is useful, consider leaving a star.**

[**← SWIR profile**](https://github.com/Swir) · [**All projects →**](https://github.com/Swir?tab=repositories)

</div>
