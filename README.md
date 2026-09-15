# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux as the primary phone operating system/userspace**, not merely running Kali inside Android.

The project combines a Windows desktop application, CLI, device profiles, kernel/rootfs build tooling, boot-image inspection/repacking, temporary-boot validation, guarded flashing, diagnostics and recovery workflows.

> Current status: **0.6.0-dev** — multi-device architecture introduced. The first active target is **OnePlus Nord AC2003 (`avicii`)**. A public Beta Release is intentionally blocked until a real supported phone passes the Beta release gate.

## Supported / active device profiles

| Device | Profile ID | Status | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up / first real boot pending | **Not yet released** |

More phones will be added under `devices/<vendor>/<codename>/profile.json` without cloning the whole application.

## What KaliPhoneStudio already does

- PySide6 Windows GUI and engineering CLI.
- Detects ADB and Fastboot devices.
- Matches a phone against installed **device profiles** instead of a single hard-coded model.
- Remembers a verified ADB identity by serial before trusting a reduced Fastboot identity.
- Uses a profile-specific typed confirmation token for destructive actions.
- Captures diagnostics and `fastboot getvar all` data.
- Supports A/B slot-aware planning and inactive-slot strategy.
- Manifest + SHA-256 validation and partition size guards.
- Dry-run by default; real flashing is behind explicit safety gates.
- Temporary `fastboot boot` workflow before persistent boot-slot flashing.
- Android boot image v2 parser/repacker for the first AC2003 profile.
- Kali rolling ARM64 rootfs builder and Phosh mobile userspace stage.
- Rescue initramfs with USB ACM console/hardware-probe support for AC2003 bring-up.
- Kernel configuration validation split into early-boot, Linux userspace and advanced tooling stages.
- Pinned upstream source references and CI tests.

## Architecture

```text
KaliPhoneStudio/
├─ kaliphonestudio/          # device-independent GUI/CLI/core
├─ devices/
│  └─ oneplus/
│     └─ avicii/
│        ├─ profile.json     # identity + boot/partition constraints
│        └─ README.md        # target-specific status and notes
├─ build/                    # build helpers, progressively profile-driven
├─ scripts/                  # diagnostics / verification / source sync
├─ tests/                    # safety and boot-pipeline tests
├─ ROADMAP.md
└─ BETA_RELEASE_GATE.md
```

### Device profile rule

A profile defines at minimum the model/codename identity, confirmation token, architecture, SoC/board, boot header/page layout, A/B behavior, partition limits and target-specific kernel hints. The core must never infer a destructive target from a vague product name when a verified profile identity is unavailable.

## Start on Windows

```powershell
python -m pip install -r requirements.txt
python main.py
```

CLI:

```powershell
python -m kaliphonestudio.cli profiles
python -m kaliphonestudio.cli device
python -m kaliphonestudio.cli preflight
```

The GUI can download Google's Android Platform Tools when `adb` / `fastboot` are missing.

## First active target: OnePlus Nord AC2003

The AC2003 profile currently uses the public `avicii` board baseline: ARM64, `lito`/`sm7250`, Android boot header v2, 4096-byte boot page, LZ4 ramdisk, A/B slots and separate DTBO. Those values are **engineering constraints**, not proof that every Linux hardware function works.

Before the first real candidate can be declared working we still need hardware evidence from an actual AC2003: exact OxygenOS fingerprint/build, `fastboot getvar all`, matching stock `boot.img`, candidate temporary boot and collected rescue/kernel logs.

## Safety model

KaliPhoneStudio is designed around **temporary boot first** and **inactive slot second**. Real flashing requires a supported profile, verified identity, Fastboot mode, unlocked bootloader, exact profile confirmation token, explicit data-loss acknowledgement, a validated manifest and image checks.

It does not bypass the phone's physical bootloader-unlock confirmation, and it must not claim a device-specific feature as working without hardware validation.

## Beta release policy

There is deliberately **no Beta Release yet**. `BETA_RELEASE_GATE.md` defines the minimum evidence required before publishing the first GitHub Beta. For the first AC2003 beta that includes a successful real-device temporary boot, usable rescue/log path, verified image/manifest hashes and a documented recovery path.

## Development status

Current automated test baseline after the multi-device migration: **15 tests passing** locally. CI is intended to compile and test the Python core; hardware milestones remain separate because GitHub runners cannot prove phone hardware support.

## Disclaimer

Unlocking bootloaders and flashing phone partitions can erase data or make a device unbootable. Always use images built for the exact supported device profile and firmware baseline. KaliPhoneStudio is an engineering project; development builds are not daily-driver releases.
