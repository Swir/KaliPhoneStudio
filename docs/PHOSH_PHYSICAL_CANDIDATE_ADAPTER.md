# Phosh successor → physical-candidate adapter

`kaliphonestudio/phosh_physical_candidate_adapter.py` closes the host-side provenance gap
between the immutable reviewed Phosh successor candidate and the existing exact physical
candidate gate.

The adapter is deliberately **not** a boot executor and **not** a storage-staging action.
Its job is to prove that the replacement Phosh rootfs belongs to the same physical
campaign identity that was already reviewed for the original schema-v8 first-boot
candidate.

## Exact inputs

The adapter accepts exactly two canonical evidence files:

1. `phosh-successor-first-boot-candidate.json`
2. `physical-candidate-gate.json`

The physical gate must already be reviewed-authority-bound, exact-baseline-bound and
eligible only to offer the existing non-persistent temporary-boot flow. It must not
claim a temporary boot was executed, phone storage was written, hardware was verified,
or Beta credit was earned.

The Phosh successor must still pass its own fail-closed validation.

## Cross-binding rules

The adapter requires exact equality for:

- profile id and physical device serial;
- firmware build and fingerprint;
- Fastboot baseline evidence identity;
- base first-boot manifest and base authority-bundle identity;
- temporary-boot authorization and boot-plan identity;
- boot image SHA-256 and size;
- kernel Image SHA-256;
- DTB and DTBO identity;
- the rootfs that the successor explicitly supersedes.

That last rule is important: the original physical gate must refer to the exact legacy
rootfs that the reviewed Phosh successor says it replaces. The new Phosh rootfs must be
different and keeps its own reviewed authority, review packet, package manifest, byte
size and package count.

## Output semantics

A valid `PhoshPhysicalCandidateAdapterEvidence` records:

- the exact physical-candidate gate digest and physical baseline digest;
- the exact Phosh successor digest;
- unchanged phone / firmware / Fastboot / boot / kernel / DT identities;
- the reviewed replacement Phosh rootfs identity and authority chain.

Success means only:

- `exact_physical_gate_bound=true`
- `reviewed_phosh_successor_bound=true`
- `ready_for_physical_staging_review=true`
- `physical_validation_required=true`

The adapter forces all of these to remain false:

- `staging_target_selected`
- `rootfs_staged`
- `temporary_boot_authorized`
- `temporary_boot_executed`
- `phone_storage_written`
- `hardware_verified`
- `beta_release_authorized`
- `beta_gate_credit`

So this record cannot be used as evidence that Phosh booted, display/touch worked, a
rootfs was copied, or the Beta gate passed.

## Build

```bash
python scripts/build_phosh_physical_candidate_adapter.py \
  --phosh-successor-candidate phosh-successor-first-boot-candidate.json \
  --physical-candidate-gate physical-candidate-gate.json \
  --out phosh-physical-candidate-adapter.json
```

Inputs are read through the shared stable regular-file verifier, must be canonical JSON,
and the output is canonical/create-only.

## What remains before a physical Phosh attempt

The next step is to bind this adapter to **real, reviewed physical storage/recovery
evidence** and an explicitly approved reversible rootfs staging strategy. A distinct
fresh read-only storage revalidation and a separate manual trial authorization remain
mandatory immediately before any write-capable rootfs staging attempt.

Only after that physical campaign may the existing recovery-gated temporary-boot,
early-userspace, display/touch and subsystem checks produce real device evidence. The
adapter itself earns no hardware or Beta credit.
