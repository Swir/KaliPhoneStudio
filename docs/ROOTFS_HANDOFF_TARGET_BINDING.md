# Rootfs handoff logical target binding

This stage is the next host-side safety boundary after an accepted reversible rootfs handoff strategy review. It binds one **logical physical-storage identity** from the exact previously captured storage report to the reviewed rootfs staging strategy. It is intentionally still **non-executing**.

## Exact inputs

The binder requires one consistent chain:

- exact `PhysicalStorageDiscoveryEvidence`;
- the exact original physical storage discovery report whose SHA-256 and byte size are already bound by that evidence;
- an accepted `RootfsHandoffStrategyReviewEvidence` for the same profile, serial, firmware, rootfs artifact and recovery plan;
- a separate canonical target-binding review record;
- separate UTF-8 review notes.

Identity, firmware, rootfs, recovery-plan, report digest/size and strategy continuity are rechecked. Symlinked review/evidence files and changed record bytes fail closed through the existing canonical loaders plus the new exact-file boundary.

## What is allowed to be bound

Only a logical target identity derived from the exact report:

- the reviewed profile-driven partition role;
- the observed kernel name token associated with that role;
- the observed filesystem identity;
- an observed encryption state of `unlocked` or `unencrypted`;
- exact observed free capacity, which must satisfy the reviewed strategy requirement;
- the already reviewed relative staging subpath;
- exact rootfs and recovery-plan SHA-256 identities.

The observed kernel identity must map to exactly one non-removable block observation. The role must match the profile-driven discovery hint and must not be in the forbidden-partition set.

## What is deliberately not represented

The target-binding evidence contains no raw `/dev/...` path and binds no mount target. It always forces:

- `raw_device_path_bound=false`
- `mount_target_bound=false`
- `trial_execution_allowed=false`
- `write_authorized=false`
- `handoff_ready=false`
- `persistent_write_performed=false`
- `phone_storage_written=false`
- `hardware_verified=false`
- `beta_release_authorized=false`
- `beta_gate_credit=false`

Even an accepted review only sets `logical_target_identity_bound=true`. It also keeps `fresh_device_revalidation_required=true`, `manual_trial_execution_required=true` and `physical_gate_still_incomplete=true`.

No command in this stage runs ADB/Fastboot, mounts/decrypts storage, copies the rootfs, changes an A/B slot or writes to the phone.

## Shared evidence workspace

Prepare a rejected-by-default review record only after the real physical storage report and accepted strategy review exist:

```bash
python main.py evidence prepare-rootfs-handoff-target-binding-review \
  --storage-discovery physical-storage-discovery.json \
  --storage-report physical-storage-report.json \
  --strategy-review rootfs-handoff-strategy-review.json \
  --reviewer REVIEWER_ID \
  --record-out target-binding-review-record.json \
  --notes-out target-binding-review-notes.txt
```

The reviewer must independently inspect the exact chain and change the record to `decision="accepted_for_manual_trial"` only when every explicit review boolean is true and the observed target remains unlocked/unencrypted, non-removable and sufficiently large.

Then bind the exact review:

```bash
python main.py evidence bind-rootfs-handoff-target-binding-review \
  --storage-discovery physical-storage-discovery.json \
  --storage-report physical-storage-report.json \
  --strategy-review rootfs-handoff-strategy-review.json \
  --review-record target-binding-review-record.json \
  --review-notes target-binding-review-notes.txt \
  --out rootfs-handoff-target-binding.json
```

A focused standalone helper is also available as `scripts/build_rootfs_handoff_target_binding.py` with `prepare` and `bind` subcommands.

## Next safe milestone

The next stage is a separate **fresh-device trial-execution gate**. It must revalidate the exact phone/firmware and logical target immediately before any write-capable action, require explicit operator interaction, preserve the documented recovery path, use the narrowest reversible staging operation possible, capture phone-side evidence and still avoid converting one process return code into hardware or Beta verification.

This target-binding review does not increase project completion by itself and cannot satisfy the physical AC2003 Beta gate without the real device evidence and later manual trial/recovery review.
