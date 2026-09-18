# Exact-bound temporary boot

KaliPhoneStudio's packaged `prepare-temporary-boot-offer` and `execute-temporary-boot-once` commands require an exact `PhysicalBootIdentityBindingEvidence` record before a physical temporary-boot command can be offered or executed.

This is deliberately stricter than checking only the whole candidate `boot.img` SHA-256. The binding is created after re-inspecting the exact stock and candidate boot images and ties the physical candidate gate to the declared kernel, ramdisk, embedded DTB, profile-required external DTBO, and optional structurally parsed AOSP AVB footer/vbmeta identity.

## Required order

```text
exact physical baseline + stock provenance
              ↓
reviewed physical candidate gate
              ↓
exact stock/candidate boot identity binding
              ↓
schema-v2 temporary-boot offer
              ↓
profile-specific user confirmation
              ↓
fresh read-only Fastboot identity probe
              ↓
one serial-bound `fastboot boot` command
```

Create the identity binding first:

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

Then prepare the non-executing offer:

```bash
python main.py prepare-temporary-boot-offer \
  --profile-id oneplus/avicii \
  --physical-candidate-gate evidence/physical-candidate-gate.json \
  --physical-boot-identity-binding evidence/physical-boot-identity.json \
  --capture-bundle evidence/fastboot-capture.json \
  --fastboot-tool-evidence evidence/fastboot-tool.json \
  --fastboot-executable tools/platform-tools/fastboot \
  --boot-image outputs/candidate-boot.img \
  --out evidence/temporary-boot-offer.json
```

The offer is schema v2 and stores the exact boot-identity-binding SHA-256. If the binding no longer resolves to the same profile, serial, physical candidate gate, physical baseline, stock provenance, boot plan, stock image, candidate image, kernel, DTB or external DTBO, offer creation fails closed before an argv is produced.

## Physical execution

The one-shot command requires both `--physical-boot-identity-binding` and the existing explicit `--execute-temporary-boot` opt-in. The opt-in check remains the first gate: without it, KaliPhoneStudio refuses before loading evidence or contacting Fastboot.

```bash
python main.py execute-temporary-boot-once \
  --profile-id oneplus/avicii \
  --physical-candidate-gate evidence/physical-candidate-gate.json \
  --physical-boot-identity-binding evidence/physical-boot-identity.json \
  --capture-bundle evidence/fastboot-capture.json \
  --baseline-evidence evidence/fastboot-baseline.json \
  --fastboot-tool-evidence evidence/fastboot-tool.json \
  --fastboot-executable tools/platform-tools/fastboot \
  --boot-image outputs/candidate-boot.img \
  --confirmation '<profile-specific token>' \
  --execute-temporary-boot \
  --probe-out evidence/temporary-boot-runtime-probe.json \
  --execution-out evidence/temporary-boot-execution.json
```

After opt-in, the command re-creates and verifies the schema-v2 offer, re-hashes the local Fastboot binary and candidate boot image, verifies the exact binding, checks the profile-specific confirmation, performs the fresh read-only serial-bound device probe, and exposes only the single `fastboot -s SERIAL boot IMAGE` operation.

## Safety meaning

A valid exact binding and a successful Fastboot process return code are still **not** proof that the phone booted Kali. This path exposes no `flash`, `erase`, `set_active` or other persistent-write verb. The resulting evidence keeps persistent write, Kali-userspace verification, hardware verification and Beta credit false until phone-side observations and the complete release gate are independently reviewed.
