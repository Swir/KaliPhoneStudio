# Physical Bring-up Dossier Manual Review

`kaliphonestudio.physical_bringup_dossier_review` adds the human-review boundary after the exact-file dossier has been independently reverified following copy/archive/transfer.

The review is intentionally **offline and non-operational**. It does not talk to a phone and cannot select a block device, choose a rootfs target, authorize a write, mount/decrypt storage, execute Fastboot, or grant hardware/Beta credit.

## Required inputs

The reviewer must bind one exact set of:

- canonical `PhysicalBringupDossierEvidence`;
- canonical `PhysicalBringupDossierVerificationEvidence` for that exact dossier;
- canonical review-record JSON;
- non-empty UTF-8 review notes.

An `accepted_for_strategy_review` decision is rejected unless the dossier already carries an accepted physical storage review, both dossier layers report the exact file set verified, and every manual checklist item is true.

## Review checklist

The canonical review record has schema version `1`, policy `manual-physical-bringup-dossier-review-v1`, exact `profile_id` and device serial, a bounded reviewer identifier, and these explicit checks:

- physical device identity reviewed;
- firmware / matching stock boot binding reviewed;
- physical candidate authority chain reviewed;
- rescue observation/evidence chain reviewed;
- storage discovery/review chain reviewed;
- exact transferred file set reviewed;
- recovery plan reviewed.

The record must keep `target_selected=false`, `storage_path_bound=false`, and `write_authorized=false`.

## CLI

```bash
python scripts/review_physical_bringup_dossier.py \
  --dossier evidence/physical-bringup-dossier.json \
  --verification evidence/physical-bringup-dossier-verification.json \
  --review-record evidence/operator-dossier-review.json \
  --review-notes evidence/operator-dossier-review-notes.txt \
  --out evidence/physical-bringup-dossier-review.json
```

The output is immutable schema-v1 evidence bound to the exact dossier, post-transfer verification, review record and notes.

## Safety boundary

Acceptance means only: **this exact physical dossier is accepted as input to a later, separate reversible strategy review**. It still records:

- `separate_strategy_review_required=true`;
- `target_selected=false`;
- `storage_path_bound=false`;
- `write_authorized=false`;
- `handoff_ready=false`;
- `storage_verified=false`;
- `recovery_verified=false`;
- `hardware_verified=false`;
- `beta_gate_credit=false`.

No target-selection algorithm is introduced by this milestone. The physical AC2003 evidence gate remains authoritative.
