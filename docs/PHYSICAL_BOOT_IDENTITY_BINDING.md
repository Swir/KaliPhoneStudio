# Physical Boot Identity Binding

`PhysicalBootIdentityBindingEvidence` is a host-side, fail-closed evidence layer between the exact stock-firmware baseline and the reviewed physical candidate gate.

It exists because a whole-file `boot.img` SHA-256 is necessary but not sufficient for a useful bring-up audit. KaliPhoneStudio also records the exact declared boot payload identities that were actually inspected: kernel, ramdisk, optional second stage, optional recovery DTBO, embedded DTB, optional AOSP AVB footer/vbmeta layout, and — for profiles that use it — the separate candidate DTBO file.

## What is bound

The binding requires the same profile and physical device chain already represented by:

- `PhysicalBaselineBundleEvidence`;
- immutable `StockBootProvenance` from the exact OTA/payload/stock boot ingress;
- the exact `BootBuildPlan`;
- `PhysicalCandidateGateEvidence` from the reviewed host-side candidate chain;
- the exact local stock `boot.img` bytes;
- the exact local candidate `boot.img` bytes;
- the exact external candidate DTBO when the selected profile requires `separate_dtbo`.

Both boot images are re-inspected at binding time. The files must be regular non-symlink files and must remain unchanged across inspection. The stock whole-file SHA-256/size/header must match immutable stock provenance, while the candidate whole-file SHA-256/size must match the physical candidate gate.

For legacy Android boot headers currently supported by the selected profile, component hashes cover the **declared payload bytes only**, never page padding. Candidate kernel, ramdisk and embedded DTB identities must match the exact build-plan inputs. The separate DTBO is independently re-hashed and must match both the plan and the reviewed candidate gate.

## AVB scope

When an AOSP AVB footer is present, the binding records:

- footer presence and version;
- `original_image_size`;
- vbmeta offset and size;
- SHA-256 of the exact embedded vbmeta blob.

The underlying boot preflight must already accept the footer/vbmeta byte layout. This is **structural and provenance evidence only**. It does not verify AVB signatures, trust roots, rollback indexes, chained partitions, key policy, or device acceptance.

If no AVB footer exists, the evidence records that absence explicitly and rejects contradictory leftover AVB fields.

## Physical execution prerequisite

The exact binding is now a hard prerequisite for the physical temporary-boot executor, not merely a detached audit artifact. Before KaliPhoneStudio is allowed to run even the fresh read-only Fastboot probe preceding `fastboot boot`, it requires `--boot-identity-binding` and checks that the binding still matches the exact:

- physical candidate gate and physical baseline bundle;
- stock provenance and stock `boot.img` SHA-256;
- boot build plan;
- candidate `boot.img` SHA-256 and size in both the gate and the prepared offer;
- candidate kernel, embedded DTB and profile-driven external DTBO identities;
- exact-byte/component/AVB-completeness flags;
- host-only safety state (`temporary_boot_executed=false`, `phone_storage_written=false`, `hardware_verified=false`, `beta_gate_credit=false`).

A detached binding or component drift therefore fails **before any Fastboot device probe**. The successful pre-execution runtime probe records the exact binding SHA-256 in schema-v2 evidence, and the subsequent execution record commits to that probe digest.

This does not make the binding a hardware-success record: it is an execution precondition that prevents a reviewed exact-byte identity record from being silently bypassed when the real temporary boot is attempted.

## Safety boundary

This layer:

- executes no ADB command while the binding itself is produced;
- executes no Fastboot command while the binding itself is produced;
- never selects or writes a phone partition;
- never performs a temporary boot by itself;
- never converts host-side consistency into hardware verification;
- always keeps `temporary_boot_executed=false`, `phone_storage_written=false`, `hardware_verified=false`, and `beta_gate_credit=false` in the binding record.

A successful record means only that the reviewed physical-candidate chain is cryptographically tied to the exact stock/candidate boot-chain bytes supplied to the command. A separate execution layer may consume that record only after all of its independent confirmation/probe safeguards also pass.

## CLI

Create the exact identity binding offline:

```bash
python scripts/bind_physical_boot_identity.py \
  --profile-id oneplus/avicii \
  --physical-baseline evidence/physical-baseline.json \
  --candidate-gate evidence/physical-candidate-gate.json \
  --stock-provenance evidence/stock-provenance.json \
  --boot-plan evidence/boot-plan.json \
  --stock-boot inputs/stock-boot.img \
  --candidate-boot outputs/candidate-boot.img \
  --candidate-dtbo outputs/dtbo.img \
  --out evidence/physical-boot-identity.json
```

`--candidate-dtbo` is profile-driven: it is required when the active profile declares `separate_dtbo`, rejected when that profile does not permit an external DTBO, and is never inferred from a device name in global code.

The physical execution command must then receive the same immutable record:

```text
KaliPhoneStudioCLI execute-temporary-boot-once ... \
  --boot-identity-binding evidence/physical-boot-identity.json \
  --execute-temporary-boot
```

The output path is create-only. Existing files, symlink inputs, detached evidence, whole-image drift, component drift, DTBO drift and invalid AVB layout are rejected.

## Beta gate meaning

This evidence is useful before a real temporary-boot attempt, but it does **not** satisfy the AC2003 Beta hardware gate by itself. A Beta still requires the real physical device baseline, exact matching stock image, successful temporary boot on the device, usable rescue/logging, Kali early userspace/rootfs proof, storage and charging safety, recovery/rollback evidence, and the remaining reviewed physical results required by `BETA_RELEASE_GATE.md`.
