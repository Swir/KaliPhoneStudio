# Physical recovery readiness

`PhysicalRecoveryReadinessEvidence` is an offline, fail-closed safety record prepared before risky physical bring-up. It binds the captured slot context and an exact locally available stock `boot.img` to the same physical baseline and exact boot-identity chain used by the reviewed temporary-boot candidate.

It is deliberately **not** a rollback result, restore command, slot-switch authorization or Beta gate pass.

## What the record binds

For the selected device profile the builder verifies and records:

- exact profile, serial, firmware build and firmware fingerprint from the captured Fastboot baseline;
- exact `FastbootBaselineEvidence` and `PhysicalBaselineBundleEvidence` identities;
- exact `PhysicalBootIdentityBindingEvidence`, physical candidate gate and boot-plan identities;
- the locally present stock `boot.img` SHA-256 and size, re-hashed from a regular non-symlink file;
- the stock kernel, ramdisk, optional embedded DTB and optional AVB vbmeta identities already proven by the exact boot-identity binding;
- the exact candidate `boot.img` identity to make the recovery preparation candidate-specific;
- profile recovery notes and confirmation text by SHA-256;
- profile A/B partition contract by SHA-256;
- the captured active slot and, for an A/B profile, the opposite slot only as an **expected inactive slot**.

The file is re-hashed during construction and must fit the profile's declared boot partition limit. A detached baseline, detached boot binding, stock-image drift, component/AVB incompleteness, ambiguous A/B slot state or any pre-existing write/hardware/Beta claim fails closed.

## Enforcement before physical temporary boot

The one-shot physical executor now treats this record as a mandatory execution prerequisite rather than a detached audit artifact. Before the first fresh Fastboot command it:

1. re-verifies the reviewed temporary-boot offer, user authorization and exact boot-identity binding;
2. re-materializes the exact `PhysicalRecoveryReadinessEvidence` from the supplied profile, Fastboot baseline, physical baseline, boot-identity binding and local stock `boot.img`;
3. requires the recovery record to match the exact physical candidate gate, boot plan, candidate image identity and firmware/serial chain;
4. rejects any recovery record that claims slot switching, inactive-slot writing, persistent writing, exercised rollback, verified recovery, hardware support or Beta credit;
5. only after those offline checks performs the fresh serial-bound `fastboot devices` / `getvar all` probe;
6. for A/B profiles, compares the freshly observed active slot and slot count to the captured recovery-readiness slot context before the single allowed `fastboot ... boot IMAGE` command.

The runtime probe evidence records the SHA-256 of the exact physical baseline, boot-identity binding, recovery-readiness record and stock recovery `boot.img`. The temporary-boot execution record remains non-credit evidence: a Fastboot return code does not prove kernel/userspace/recovery success.

The shared operator/Windows CLI therefore requires all three additional exact inputs for physical execution:

```text
--physical-baseline <physical-baseline-bundle.json>
--recovery-readiness <physical-recovery-readiness.json>
--stock-boot <exact-stock-boot.img>
```

Missing, detached or drifted inputs fail before `fastboot boot`. No persistent write verb is added.

## A/B safety semantics

For an A/B profile the builder requires:

- `ab_device=true` from the profile;
- `boot` present in the profile's `ab_partitions` contract;
- a captured active slot of exactly `a` or `b`;
- exactly two captured slots.

It then records the opposite slot as `expected_inactive_slot`. This is context for later manual safety review only. It does **not** execute or authorize `set_active`, `flash`, `erase`, inactive-slot writing or any persistent operation.

The implementation is profile-driven. A single-slot profile is represented with `captured_active_slot=null`, `expected_inactive_slot=null` and `slot_count=null`; no AC2003-specific slot rule is hard-coded in the generic module.

## Safety flags

A successful record always keeps all of the following false:

- `slot_switch_authorized`;
- `inactive_slot_write_authorized`;
- `persistent_write_authorized`;
- `rollback_exercised`;
- `recovery_verified`;
- `hardware_verified`;
- `beta_gate_credit`.

`ready_for_temporary_boot_safety_review=true` means only that exact stock recovery material and slot context are available for a later human-reviewed bring-up step. It does not mean that temporary boot has run or that recovery has been exercised.

## CLI

Create the offline record:

```bash
python scripts/build_physical_recovery_readiness.py \
  --profile-id oneplus/avicii \
  --fastboot-baseline evidence/fastboot-baseline.json \
  --physical-baseline evidence/physical-baseline-bundle.json \
  --boot-identity-binding evidence/physical-boot-identity.json \
  --stock-boot stock/boot.img \
  --out evidence/physical-recovery-readiness.json
```

Then the physical one-shot temporary-boot command must receive the same exact physical baseline, recovery-readiness record and stock image alongside the previously reviewed candidate chain. Inputs must be exact-schema JSON objects and regular files. Evidence outputs are create-only.

## Beta boundary

This host-side record and its execution prerequisite improve the safety of the mandatory physical recovery/rollback campaign, but they grant **zero** physical or Beta credit. The Beta gate still requires the recovery path to be exercised and manually reviewed on the exact physical firmware baseline, with the real phone and the real candidate evidence chain.
