# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux / NetHunter Pro as the primary phone OS/userspace**, without Android as the user-facing layer.

The project is deliberately conservative about hardware claims. A device profile, successful host build, reproducible artifact, green CI, prepared boot offer, Fastboot return code, rescue marker, raw sysfs signal, or bounded read-only functional probe does **not** mean a phone is supported. Public Beta releases require the complete host and physical-device gate in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress is weighted toward physical boot, hardware validation, recovery and release readiness. Host-side reproducibility, provenance and safety are mandatory foundations, but they never substitute for evidence from the exact physical phone.

> **Current development line: `0.6.53-dev`.** Reviewed Kali ARM64 rootfs, `oneplus/avicii` kernel and DTB/DTBO authorities remain strict-byte-identical host-side. The guarded path still permits only one explicitly confirmed serial-bound `fastboot boot`. 0.6.53 keeps the automatic rescue inventory read-only and adds a second, **manual-only** helper generated in initramfs RAM. It runs only after the exact local `--confirm-read-only` argument, reads at most one 4096-byte block from up to eight non-removable whole block devices into `/dev/null`, and samples battery telemetry twice. The resulting evidence is bound to the exact physical observation, exact read-only diagnostics and the same transcript, but never sets storage/charging/hardware/Beta verification true without manual physical review.

## Source of truth and architecture

`Swir/KaliPhoneStudio` is the **only** project source of truth. The core under `kaliphonestudio/` is device-independent. Device-specific knowledge belongs under:

```text
devices/<vendor>/<codename>/profile.json
```

A profile must define identity, confirmation token, boot/partition constraints, firmware hints, immutable upstream sources, recovery notes, host tests and hardware Beta tests before destructive actions can become eligible. Adding a profile JSON is never an automatic hardware-support claim.

### Active device profiles

| Device | Profile ID | Engineering state | Persistent install |
|---|---|---|---|
| OnePlus Nord AC2003 | `oneplus/avicii` | Bring-up; physical first boot pending | **Not released** |

The avicii baseline pins `LineageOS/android_device_oneplus_avicii@3f1270c2871e9893332073eb0f8f5f9499abbf13`, `LineageOS/android_kernel_oneplus_sm7250@fb4b4374d3b9ad0f10ba38d159585129f092fb3d` (`4.19.300`) and source/object-locked Android Clang `clang-r416183b`. These are engineering baselines, not hardware-working claims.

## Current reviewed host authorities

| Layer | Reviewed run | Accepted identity | Hardware/Beta credit |
|---|---:|---|---|
| Kali ARM64 rootfs | `35158577624` | SHA-256 `133d5d806e09917c5a3e23293f8e3ad9d8daadab9a8c8d9f6d507179b06ddb1d`, 137,460,600 bytes, 269 packages | **No** |
| ARM64 kernel | `35183670399` | `.config` SHA-256 `2ab588b240ed227101464f77465176f2c178ae09309a47e45f5ff56f14c3c7f3`; `Image` SHA-256 `be4440dc335d53c752270c484fe589a9bc1ef08f9100e885478b50df67cbe712`, 43,878,416 bytes | **No** |
| DTB / DTBO | `35196447576` | `lito.dtb` SHA-256 `48b0902a99c10a11ff52680bf81e9fec2574ad687c58ea35a00fdbf7aefe40ce`; packed `dtbo.img` SHA-256 `212392a25add2aa60fdc73163bfdbf1acc082bc5e6e1f3ff1c975e88b857b895` | **No** |

Reviewed authority records live under `evidence/authorities/`; CI checks their run/commit/artifact identities against `BUILD_STATUS.json`.

## Implemented safety and provenance chain

### Multi-device core and physical baseline

- Runtime profile registry with profile/path binding, profile-driven identity and profile-specific confirmation token.
- A/B-aware planning and temporary-boot-first policy.
- Offline GUI/CLI profile inspection with no flash/write controls.
- Read-only Fastboot capture with exact reviewed executable identity, raw transcript and parsed baseline evidence.
- Exact OTA → `payload.bin` → stock `boot.img` provenance and immutable physical-baseline bundle.
- Profile JSON cannot inject shell commands or Python module paths; optional hooks require explicit trusted registration.

### Boot chain and reviewed artifacts

- Deterministic profile-driven `BootBuildPlan` bound to exact stock provenance plus kernel/ramdisk/DTB/DTBO SHA-256 identities.
- Source-locked `mkbootimg`/`unpack_bootimg`, independent double assembly and locked round-trip verification.
- Schema-v8 first-boot manifest plus reviewed kernel/rootfs/device-tree candidate bindings and unified authority bundle.
- `PhysicalCandidateGateEvidence` cross-binds exact physical baseline, reviewed authorities, boot plan, authorization and candidate image before a temporary-boot offer can exist.
- Exact source/version/config/toolchain contracts with strict two-root reproducibility for kernel and device tree.
- Kali NetHunter ARM64 rootfs builder pinned to exact `2026.2` source and GPG-verified repository snapshot.

### Temporary-boot offer and execution gate

A local offer rehashes the exact reviewed Fastboot executable and candidate `boot.img`; the only generated command plan is equivalent to:

```text
<verified-fastboot> -s <verified-serial> boot <verified-candidate-boot.img>
```

Execution requires exact offer-bound profile confirmation, re-verifies local files, and performs a fresh read-only serial-bound `devices` + `getvar all` probe. Product, serial, active slot, slot count, unlock/security state and bootloader/baseband values must still match the reviewed baseline. Device/state drift aborts before boot.

The executor exposes no `flash`, `erase`, `set_active`, `reboot` or persistent-write verb. Even return code 0 proves only Fastboot command acceptance and leaves all hardware/Beta claims false.

### Rescue physical proof, inventory and explicit read-only probes — 0.6.53

The reproducible rescue candidate is schema-v2 and embeds one deterministic 64-hex `rescue_probe_id` in `/etc/kaliphonestudio/rescue-probe-id`. The locked rescue `/init` first emits:

```text
KPS_RESCUE_STAGE=init-reached-v1
KPS_RESCUE_PROBE_ID=<exact-candidate-probe-id>
```

It then emits exactly one bounded automatic diagnostics block:

```text
KPS_DIAG_BEGIN=readonly-sysfs-inventory-v1
KPS_DIAG_BLOCK=<name>|<size-sectors>|<removable>
KPS_DIAG_SCSI_HOST=<host>|<proc-name>
KPS_DIAG_POWER=<name>|<type>|<status>|<capacity>|<online>|<voltage>|<current>|<temp>
KPS_DIAG_INPUT=<event>|<name>
KPS_DIAG_GRAPHICS=<fb>|<name>
KPS_DIAG_DRM=<connector>|<status>
KPS_DIAG_END=readonly-sysfs-inventory-v1
```

That automatic inventory only reads procfs/sysfs. It does **not** mount persistent storage, repair/decrypt data, change charging policy, initialize display, open input event nodes, execute Fastboot, or enable network/SSH. Each category is capped at 64 records and each field is reduced to a bounded ASCII token.

0.6.53 additionally writes `/run/kps-readonly-probe` into initramfs RAM but deliberately does not run it. The operator must explicitly invoke:

```text
/run/kps-readonly-probe --confirm-read-only
```

Only then can the helper emit one functional block:

```text
KPS_PROBE_BEGIN=readonly-functional-probes-v1
KPS_PROBE_BLOCK_READ=<device>|4096|<ok|fail|missing>
KPS_PROBE_BATTERY_SAMPLE=<name>|<1|2>|<status>|<health>|<capacity>|<voltage>|<current>|<temp>
KPS_PROBE_END=readonly-functional-probes-v1
```

The helper considers only non-removable whole block devices, skips loop/ram/zram/dm/md devices, caps the set at eight, reads exactly one 4096-byte block per candidate **to `/dev/null`**, and never prints block contents. Battery sampling is capped at eight battery supplies and two samples separated by one second. It does not mount, format, repair, decrypt, write a block device, change charging policy, enable networking/SSH or execute Fastboot.

`PhysicalBootObservationEvidence` proves only that the exact rescue markers appeared in the exact captured transcript after one recorded temporary-boot execution. `PhysicalRescueDiagnosticsEvidence` binds the automatic inventory to that same transcript. `PhysicalRescueFunctionalProbeEvidence` then requires the exact same profile, serial, transcript digest/size, rescue probe ID, physical-observation digest and read-only-diagnostics digest before accepting the manually invoked probe records.

It may expose raw signal booleans such as:

```text
storage_read_signal_observed=true|false
battery_sampling_signal_observed=true|false
```

Those booleans are deliberately **not** release-gate verdicts. The evidence always keeps:

```text
explicit_local_authorization_required=true
manual_review_required=true
storage_verified=false
display_touch_verified=false
charging_battery_verified=false
recovery_verified=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
```

See [`docs/RESCUE_PHYSICAL_PROOF.md`](docs/RESCUE_PHYSICAL_PROOF.md).

## Offline application

```powershell
python main.py --list-profiles
python main.py --list-profiles --json
python main.py --profile-id oneplus/avicii
python main.py --profile-id oneplus/avicii --json
```

Profile inspection always distinguishes profile availability from hardware support.

## Beta release gate

**Beta is BLOCKED.** The first AC2003 Beta still requires a real physical Fastboot/OxygenOS baseline, matching stock `boot.img`, exact physical-firmware candidate and reviewed bindings, an explicitly confirmed temporary boot, manually reviewed proof of the actual boot path, usable rescue/logging, Kali early userspace/rootfs, real UFS/storage verification, display/touch or an explicit console-only scope, safe charging/battery, exercised recovery/rollback, and a compatibility/release manifest with SHA-256 files.

Raw rescue sysfs presence, one successful bounded 4096-byte read, or two battery telemetry samples are useful diagnostic signals, but are explicitly insufficient by themselves for the storage, display/touch or charging/battery Beta gates.

## Testing

Primary CI matrix: Python 3.11, 3.12, 3.13 and 3.14.

```bash
python -m compileall -q kaliphonestudio scripts tests
python -m pytest -q
```

The dedicated `rescue-readonly-diagnostics` workflow additionally compiles both rescue diagnostic evidence layers/CLIs, validates `rescue/init` shell syntax and runs focused physical-observation, explicit-probe and no-write source-policy contracts. The rescue-payload reproducibility workflow still rebuilds the source-locked static ARM64 payload independently after `/init` changes.

## Adding another device

A new device starts as **profile-only / unsupported hardware**. Add `devices/<vendor>/<codename>/profile.json`, pin immutable upstream sources, define identity/confirmation/boot/partition/recovery/test contracts, pass schema/CI validation, build and verify artifacts offline, capture exact physical baseline, and prefer temporary boot before any persistent write.

## Safety model

KaliPhoneStudio is built around fail-closed evidence rather than optimistic automation. Green CI, matching model strings, reproducible host artifacts, successful host-side Fastboot commands, machine-readable rescue markers, sysfs inventory and bounded explicitly authorized read-only functional probes are engineering evidence—not automatic proof that a physical device safely boots Kali. The first public Beta will be a tested device build, not a development snapshot.
