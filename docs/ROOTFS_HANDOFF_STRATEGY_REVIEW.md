# Reversible rootfs handoff strategy review

This stage is a **host-side, offline review boundary** between accepted physical storage discovery/dossier evidence and any future target-binding or rootfs trial. It is intentionally fail-closed.

## What it consumes

The binder requires one exact chain for the same profile, serial and firmware baseline:

- physical storage discovery evidence;
- an accepted independent physical storage review;
- the exact bring-up dossier containing those two files;
- an accepted independent dossier review;
- the cross-campaign physical release-gate audit;
- a separate strategy review record and notes.

The binder verifies digest continuity between these layers. A review from another campaign, a substituted discovery/review, identity or firmware drift, a changed rootfs artifact, or a changed recovery plan is rejected. The unified operator path additionally recomputes the canonical strategy-review record SHA-256 and byte size before any upstream evidence is loaded, so detached record metadata fails closed.

## What may be reviewed

The record describes only a **logical candidate design**: profile-driven partition role, relative staging subpath, minimum required free bytes, the exact reviewed rootfs artifact and exact recovery plan. The candidate role must equal the reviewed profile-driven discovery hint and must not appear in the discovery contract's forbidden partitions.

Absolute paths, Windows drive paths, backslashes and raw device paths are rejected. The template generator also refuses a minimum free-space requirement smaller than the reviewed rootfs artifact. The review requires explicit checks for the physical evidence chain, capacity evidence, filesystem/encryption state, rollback plan, forbidden partitions, absence of a raw device path, and absence of write authorization.

## What acceptance does not mean

`accepted_for_trial_design` means only that the logical design can move to a **later manual target-binding stage**. The evidence always forces:

- `target_selected=false`
- `storage_path_bound=false`
- `trial_execution_allowed=false`
- `write_authorized=false`
- `handoff_ready=false`
- `persistent_write_performed=false`
- `phone_storage_written=false`
- `hardware_verified=false`
- `beta_release_authorized=false`
- `beta_gate_credit=false`

No command in this stage invokes ADB/Fastboot, mounts or decrypts storage, chooses a block device, or writes to a phone. It does not complete the AC2003 physical gate and does not change the project progress percentage.

## Operator flow

Use the shared evidence workspace so the same source command surface is available to normal host operation and the frozen Windows CLI path. Prepare a rejected-by-default record only after the real physical storage discovery/review files exist:

```bash
python main.py evidence prepare-rootfs-handoff-strategy-review \
  --storage-discovery physical-storage-discovery.json \
  --storage-review physical-storage-review.json \
  --reviewer REVIEWER_ID \
  --candidate-partition-role ROLE \
  --staging-subpath kaliphonestudio/rootfs-stage \
  --required-free-bytes BYTES \
  --record-out strategy-review-record.json \
  --notes-out strategy-review-notes.txt
```

After an independent reviewer edits the record and notes, bind the exact chain:

```bash
python main.py evidence bind-rootfs-handoff-strategy-review \
  --storage-discovery physical-storage-discovery.json \
  --storage-review physical-storage-review.json \
  --dossier physical-bringup-dossier.json \
  --dossier-review physical-bringup-dossier-review.json \
  --release-gate-audit physical-release-gate-audit.json \
  --review-record strategy-review-record.json \
  --review-notes strategy-review-notes.txt \
  --out rootfs-handoff-strategy-review.json
```

The standalone `scripts/prepare_rootfs_handoff_strategy_review.py` and `scripts/bind_rootfs_handoff_strategy_review.py` entry points remain available for focused tooling, but the shared evidence workspace is the preferred operator route.

The next safe milestone is a separate target-binding/execution gate that must revalidate the real phone and exact evidence again; this review is not that gate.
