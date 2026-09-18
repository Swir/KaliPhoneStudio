# Rootfs handoff manual trial authorization

This document defines the **offline, non-executing** review boundary that follows an accepted logical target binding and a distinct-capture fresh-device revalidation.

It does **not** mount storage, resolve or store a raw `/dev/...` path, copy the rootfs, contact a phone, run ADB/Fastboot, authorize a persistent write, execute a trial, verify hardware, or grant Beta credit. Its only positive outcome is an exact-file review record stating that the reviewed evidence chain is suitable to be handed to a later interactive execution boundary.

## Required inputs

The authorization review consumes exactly:

1. one accepted `RootfsHandoffTargetBindingEvidence` record;
2. one `RootfsHandoffFreshRevalidationEvidence` record that is bound to that exact target-binding digest and has `fresh_device_revalidated=true`;
3. one canonical manual review record;
4. separate UTF-8 review notes.

Profile, serial, firmware build/fingerprint, logical partition role, kernel token, filesystem, encryption state, required capacity, staging subpath, rootfs SHA-256/size and recovery-plan SHA-256 must agree across the chain. The fresh revalidation must still report an unlocked/unencrypted state and enough free capacity.

## Prepare a rejected-by-default review

```bash
python scripts/prepare_rootfs_handoff_trial_authorization.py \
  --target-binding evidence/physical/rootfs-target-binding.json \
  --fresh-revalidation evidence/physical/rootfs-fresh-revalidation.json \
  --reviewer operator-1 \
  --record-out evidence/physical/rootfs-trial-authorization-review.json \
  --notes-out evidence/physical/rootfs-trial-authorization-notes.txt
```

The generated record starts with `decision="rejected"` and every review check false. A reviewer must inspect and intentionally edit the exact record after reviewing the exact evidence chain.

An accepted review uses `decision="accepted_for_interactive_execution_boundary"` and requires every check to be true, including exact target/fresh evidence, logical identity, filesystem/encryption/capacity, rootfs/recovery identities, staging subpath, rollback limitations, explicit operator interaction, no automatic execution, no raw path in the evidence and no persistent-write authorization at this stage.

## Bind the exact review

```bash
python scripts/bind_rootfs_handoff_trial_authorization.py \
  --target-binding evidence/physical/rootfs-target-binding.json \
  --fresh-revalidation evidence/physical/rootfs-fresh-revalidation.json \
  --review-record evidence/physical/rootfs-trial-authorization-review.json \
  --review-notes evidence/physical/rootfs-trial-authorization-notes.txt \
  --out evidence/physical/rootfs-trial-authorization.json
```

The binder rejects non-canonical JSON, symlinks, changed files, detached digests, identity drift, insufficient current free space, unacceptable encryption state, incomplete accepted reviews and any attempt to set execution/write/hardware/Beta flags.

## Meaning of an accepted authorization

An accepted record sets only:

- `manual_trial_authorization_accepted=true`;
- `ready_for_interactive_trial_execution_boundary=true`;
- `live_device_recheck_required_at_execution=true`;
- `explicit_operator_confirmation_required_at_execution=true`;
- `execution_boundary_required=true`.

It still forces:

- `raw_device_path_bound=false`;
- `mount_target_bound=false`;
- `trial_execution_allowed=false`;
- `persistent_write_authorized=false`;
- `phone_storage_written=false`;
- `storage_verified=false`;
- `recovery_verified=false`;
- `hardware_verified=false`;
- `beta_release_authorized=false`;
- `beta_gate_credit=false`.

The later execution boundary must re-bind this exact authorization, re-check live phone/firmware/target state, resolve any raw target only inside that explicitly interactive session, require explicit operator confirmation and retain rollback/recovery protections. Implementing this host-side review does not change KaliPhoneStudio's physical support status or Beta gate.
