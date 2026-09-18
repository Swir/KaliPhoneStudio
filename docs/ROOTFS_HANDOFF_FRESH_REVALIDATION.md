# Rootfs handoff fresh-device target revalidation

KaliPhoneStudio keeps the rootfs handoff path fail-closed. An accepted logical target-binding review is **not** permission to mount, copy, write, flash, or otherwise modify the phone. Before a later manual trial can even be considered, the reviewed logical target must be checked again against a **distinct, newly captured read-only physical-storage discovery chain** from the same verified phone and firmware.

## What this stage proves

`kaliphonestudio.rootfs_handoff_fresh_revalidation` consumes three exact files:

1. the accepted `RootfsHandoffTargetBindingEvidence`;
2. a new `PhysicalStorageDiscoveryEvidence` captured after the reviewed binding;
3. the exact new physical storage discovery report bytes bound by that discovery evidence.

The fresh discovery must have a different evidence SHA-256 from the discovery used to create the target binding. Reusing the original discovery fails closed.

The revalidation cross-checks the same profile, device serial, firmware build/fingerprint, rootfs artifact SHA-256/size and recovery-plan SHA-256. The previously reviewed logical role must still resolve to exactly one non-removable kernel identity with the same filesystem and acceptable encryption state (`unlocked` or `unencrypted`) and enough current free capacity for the reviewed requirement.

A successful result records only that the logical identity survived a fresh read-only observation. It sets:

- `fresh_device_revalidated=true`;
- `ready_for_separate_manual_trial_authorization=true`;
- `manual_trial_authorization_required=true`;
- `physical_gate_still_incomplete=true`.

It always keeps these false:

- `raw_device_path_bound`;
- `mount_target_bound`;
- `trial_execution_allowed`;
- `write_authorized`;
- `handoff_ready`;
- `persistent_write_performed`;
- `phone_storage_written`;
- `storage_verified` / `recovery_verified`;
- `hardware_verified`;
- `beta_release_authorized` / `beta_gate_credit`.

## Operator command

The shared offline evidence namespace exposes the contract as:

```bash
python main.py evidence build-rootfs-handoff-fresh-revalidation \
  --target-binding evidence/target-binding.json \
  --fresh-storage-discovery evidence/fresh-storage-discovery.json \
  --fresh-storage-report evidence/fresh-storage-report.json \
  --out evidence/rootfs-fresh-revalidation.json
```

The standalone host-side wrapper is equivalent:

```bash
python scripts/build_rootfs_handoff_fresh_revalidation.py \
  --target-binding evidence/target-binding.json \
  --fresh-storage-discovery evidence/fresh-storage-discovery.json \
  --fresh-storage-report evidence/fresh-storage-report.json \
  --out evidence/rootfs-fresh-revalidation.json
```

Both paths are offline. They do not import or execute Fastboot/ADB, do not open a phone, do not select a raw block path, do not mount storage and do not perform a rootfs trial.

## Fail-closed conditions

The stage refuses to produce accepted evidence when any important identity has drifted. Examples include:

- original discovery reused instead of a distinct fresh capture;
- profile, serial, firmware, rootfs artifact or recovery-plan mismatch;
- supplied report bytes do not match the fresh discovery evidence;
- logical partition role changed or became forbidden;
- kernel identity or filesystem changed;
- encryption became locked/unsupported;
- current free capacity fell below the reviewed requirement;
- target resolves to missing, duplicate or removable block observations;
- upstream target binding is rejected, incomplete or already contains an unsafe authorization claim.

Output is create-only canonical JSON. Existing outputs are never silently overwritten.

## What comes next

This stage intentionally stops before execution. A future manual trial-authorization/execution boundary must perform its own immediate device checks and require explicit operator interaction before any write-capable rootfs staging action. That later stage must preserve recovery/rollback policy and cannot be treated as Beta-ready merely because this host-side revalidation contract passes.

For OnePlus Nord AC2003 (`oneplus/avicii`), no physical credit exists until the real phone has completed the mandatory baseline, matching stock `boot.img`, recovery-gated temporary boot, rescue/logging, storage, functional-hardware, early-userspace and recovery/rollback evidence required by [`BETA_RELEASE_GATE.md`](../BETA_RELEASE_GATE.md).
