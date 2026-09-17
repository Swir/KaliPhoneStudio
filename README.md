# KaliPhoneStudio

**KaliPhoneStudio** is a multi-device engineering studio for porting **Kali Linux / NetHunter Pro as the primary phone OS/userspace**, without Android as the user-facing layer.

The repository is conservative by design: a device profile, green CI, reproducible artifact, successful Fastboot command, rescue marker, read-only diagnostic, early-userspace marker, storage-layout hint or storage-discovery record does **not** by itself mean a phone is supported. Public Beta requires every applicable host and physical gate in [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md).

## Project progress

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress is weighted toward physical boot, hardware validation, recovery and release readiness. Host reproducibility and safety are foundations, not substitutes for exact-device evidence.

> **Current development line: `0.6.56-dev`.** Reviewed Kali ARM64 rootfs, `oneplus/avicii` kernel and DTB/DTBO authorities remain strict-byte-identical host-side. 0.6.56 adds a typed, fail-closed physical-storage discovery evidence layer on top of the 0.6.55 source-pinned handoff contract. It can bind real topology/filesystem/encryption/free-space/recovery observations to the exact physical candidate, rescue transcript chain and reviewed rootfs authority **without carrying a `/dev/...` target, selecting userdata, authorizing a write or claiming storage support**. No real AC2003 discovery record has been reviewed yet. **Beta remains blocked.**

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

## Kali early-userspace proof

`kaliphonestudio.kali_early_userspace` builds a deterministic USTAR proof overlay bound to the exact first-boot manifest, reviewed authority bundle, rootfs-authority binding, reviewed rootfs authority and strict rootfs artifact SHA-256/size.

The overlay installs one systemd oneshot before `basic.target` and emits exact stage/probe/candidate/rootfs markers. `kaliphonestudio.physical_kali_early_userspace` binds an operator-captured transcript to the same exact physical candidate and successful non-persistent temporary-boot execution. A complete marker match is still an **observation requiring manual review**, not an automatic hardware/Beta pass. Details: [`docs/KALI_EARLY_USERSPACE_PROOF.md`](docs/KALI_EARLY_USERSPACE_PROOF.md).

## Rootfs handoff discovery contract

`kaliphonestudio.rootfs_handoff` adds a separate safety boundary between “we have the correct reproducible rootfs” and “we know where it can safely be made available on this physical phone”. The contract:

- resolves one exact profile-pinned storage-layout source and Git blob;
- records only source-backed storage/filesystem/encryption expectations;
- requires physical evidence for block topology, filesystem identity, encryption state, free space and recovery plan;
- forbids all profile-declared A/B/system partitions plus the super container during discovery;
- keeps metadata forbidden because it participates in encryption/recovery state;
- rejects any profile attempt to select a target or authorize persistent writes;
- binds one exact `PhysicalCandidateGateEvidence` to one exact reviewed `RootfsAuthorityRecord`;
- always returns `target_selected=false`, `storage_path_bound=false`, `write_authorized=false`, `handoff_ready=false`, `hardware_verified=false` and `beta_gate_credit=false`.

For avicii, the exact pinned LineageOS `init/fstab.qcom` blob is `20873c3a84e1e6e8d2483e313f561ad35ded7355`. It describes userdata as F2FS with `fileencryption=ice` and `wrappedkey` on UFS, with separate metadata-based encryption state. KaliPhoneStudio treats `userdata` only as a **discovery hint**, never as an approved rootfs target. The focused CI workflow also fetches the exact pinned device-source commit and verifies that exact blob in a clean tracked checkout.

Full policy: [`docs/ROOTFS_HANDOFF_POLICY.md`](docs/ROOTFS_HANDOFF_POLICY.md).

## Typed physical storage discovery (0.6.56)

`kaliphonestudio.physical_storage_discovery` provides the evidence format needed for the next real-device step without turning discovery into an installation action.

- The operator report uses kernel names/partition **roles**, never absolute block-device paths.
- Whole-block topology entries must match the exact `KPS_DIAG_BLOCK` records from the already-bound rescue transcript by kernel name, sector count and removable bit.
- The expected storage-bus signal is taken from the same exact rescue evidence chain; for avicii that currently means a reviewed UFS signal.
- Filesystem, encryption and free-space observations are typed and checked against profile expectations for the `userdata` role, but that role is never converted to a target path.
- The exact original discovery-report bytes are SHA-256 bound, as is a separate recovery-plan text file.
- Evidence is also bound to the exact rootfs-handoff assessment, physical candidate, reviewed rootfs artifact, rescue diagnostics, manual functional probe, transcript and rescue probe id.
- A complete/matching observation set may become `discovery_ready_for_manual_review=true`. That means only “there is enough evidence for a human review”; it **does not** mean a target is approved.
- `target_selected=false`, `storage_path_bound=false`, `write_authorized=false`, `handoff_ready=false`, `storage_verified=false`, `recovery_verified=false`, `phone_storage_written=false`, `hardware_verified=false` and `beta_gate_credit=false` remain mandatory.

Recorder CLI:

```bash
python scripts/record_physical_storage_discovery.py \
  --profile-id oneplus/avicii \
  --handoff-assessment evidence/rootfs-handoff-assessment.json \
  --rescue-diagnostics evidence/physical-rescue-diagnostics.json \
  --functional-probes evidence/physical-rescue-functional-probes.json \
  --discovery-report evidence/operator-storage-discovery.json \
  --recovery-plan evidence/recovery-plan.txt \
  --out evidence/physical-storage-discovery.json
```

This command is offline evidence binding only. It does not connect to a phone, mount a filesystem, decrypt storage, run Fastboot, select a partition or perform a write.

## Rootfs handoff is still a physical blocker

0.6.56 completes the **typed discovery evidence layer**, not the actual staging strategy. Before any physical Kali-rootfs handoff can be attempted, the exact AC2003 still must supply real, reviewed storage/encryption/free-space/recovery observations and a later milestone must explicitly select and review a reversible strategy. The common core still generates no raw block path, mount target or write authorization.

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

Focused workflows cover kernel/rootfs/DT reproducibility, rescue payloads/read-only diagnostics, Kali early-userspace proof, rootfs-handoff source locking and typed physical-storage discovery contracts. A green workflow is host evidence only.

## Beta release policy

**Beta is currently blocked.** The first AC2003 Beta requires at minimum:

- real physical Fastboot identity and exact OxygenOS build/fingerprint;
- matching stock `boot.img` from the exact OTA;
- one exact physical candidate bound to reviewed kernel/rootfs/DT authorities;
- successful temporary boot on that same phone;
- usable rescue/logging path and manually reviewed exact rescue markers;
- real physical storage/encryption/free-space/recovery discovery, manual review, then a separately reviewed reversible rootfs staging/handoff method;
- proof that the kernel reached the intended Kali early userspace/rootfs;
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
8. A storage-layout hint, discovery role or review-ready observation set is not a target path and never implies permission to write it.

## Development

```bash
python -m compileall -q kaliphonestudio scripts tests
python -m pytest -q
```

Repository documentation and checked-in authority records are part of the safety contract and are CI-validated.
