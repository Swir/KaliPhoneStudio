# Physical bring-up evidence session

`PhysicalBringupSessionEvidence` is an **offline audit boundary** for evidence already collected during physical bring-up. It does not operate a phone and it deliberately does not turn individual observations into support claims.

## Purpose

The physical path now has several intentionally separate records:

1. exact physical-candidate gate;
2. successful non-persistent temporary-boot observation with exact rescue probe markers;
3. read-only rescue diagnostics;
4. explicitly authorized bounded functional probes;
5. typed storage discovery;
6. manual storage-review record;
7. optional Kali early-userspace marker evidence.

Keeping those layers separate is important for safety, but operators also need one artifact that proves the records belong to the same profile, serial, firmware, rootfs/candidate chain, rescue transcript and storage-review chain. `kaliphonestudio.physical_bringup_session` provides that cross-binding.

## What it verifies

The binder fails closed unless the supplied evidence agrees on the exact:

- `profile_id` and physical device serial;
- firmware build and firmware fingerprint across candidate/storage evidence;
- physical candidate gate digest;
- boot-observation → diagnostics → functional-probe chain;
- rescue transcript SHA-256 and deterministic rescue probe id;
- rootfs handoff assessment/contract;
- reviewed rootfs authority and strict rootfs artifact identity;
- storage discovery report and recovery-plan identity;
- storage review record and notes identity;
- optional Kali early-userspace manifest, authority bundle, rootfs authority and rootfs artifact identities.

Every upstream typed evidence object is validated before the session is created. The session JSON itself is strict-schema, canonical and immutable-on-write.

## What it never does

A valid session is **not** a rootfs placement decision and is **not** release evidence. The session hard-requires all of these to remain false:

- `target_selected`;
- `storage_path_bound`;
- `write_authorized`;
- `handoff_ready`;
- `storage_verified`;
- `charging_battery_verified`;
- `display_touch_verified`;
- `recovery_verified`;
- `kali_early_userspace_verified`;
- `phone_storage_written`;
- `hardware_verified`;
- `beta_gate_credit`.

If a real manual storage review has `accepted_for_strategy_design=true`, the session may mirror that fact only as `storage_review_accepted_for_strategy_design=true`. It still cannot choose a device path or authorize any write. Target/strategy review remains a later physical milestone.

## Offline CLI

After the real evidence files exist, bind them without phone I/O:

```bash
python scripts/bind_physical_bringup_session.py \
  --candidate-gate evidence/physical-candidate-gate.json \
  --boot-observation evidence/physical-boot-observation.json \
  --rescue-diagnostics evidence/physical-rescue-diagnostics.json \
  --functional-probes evidence/physical-rescue-functional-probes.json \
  --storage-discovery evidence/physical-storage-discovery.json \
  --storage-review evidence/physical-storage-review.json \
  --out evidence/physical-bringup-session.json
```

When a separate physical Kali early-userspace observation exists for the same candidate/rootfs chain, add:

```bash
  --kali-early-userspace evidence/physical-kali-early-userspace.json
```

The CLI reads evidence files only. It contains no Fastboot/ADB call, no mount/decrypt logic, no `/dev/...` target selection and no phone write path.

## Release-gate interpretation

This artifact improves auditability and reduces the chance of accidentally combining evidence from different devices, firmware builds, candidates or transcripts. It does **not** complete any physical AC2003 checkbox by itself. The Beta gate still requires reviewed evidence from the exact real phone, a separately reviewed reversible rootfs strategy, successful temporary boot and rescue path, Kali early userspace, storage/charging/display scope, exercised recovery/rollback, and the final release manifest/checksums.
