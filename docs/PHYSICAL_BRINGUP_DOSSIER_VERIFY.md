# Physical Bring-up Dossier Reverification

`kaliphonestudio.physical_bringup_dossier_verify` independently rechecks a
physical bring-up dossier after it has been copied, archived or moved between
machines.

It verifies the canonical dossier bytes plus **exactly one file for every role**
recorded inside it. Every member must retain the exact SHA-256 and size. Evidence
roles must also still be canonical UTF-8 JSON. Files are regular non-symlinks and
are checked for changes while being read.

The verifier does not trust file names or host paths: the operator maps dossier
roles to files explicitly with repeated `--file ROLE=PATH` arguments.

```bash
python scripts/verify_physical_bringup_dossier.py \
  --dossier evidence/physical-bringup-dossier.json \
  --file physical_bringup_session=evidence/physical-bringup-session.json \
  --file physical_candidate_gate=evidence/physical-candidate-gate.json \
  --file physical_boot_observation=evidence/physical-boot-observation.json \
  --file rescue_diagnostics=evidence/physical-rescue-diagnostics.json \
  --file rescue_functional_probe=evidence/physical-rescue-functional-probes.json \
  --file physical_storage_discovery=evidence/physical-storage-discovery.json \
  --file physical_storage_review=evidence/physical-storage-review.json \
  --file rescue_transcript=evidence/rescue-transcript.log \
  --file storage_discovery_report=evidence/operator-storage-discovery.json \
  --file recovery_plan=evidence/recovery-plan.txt \
  --file storage_review_record=evidence/operator-storage-review.json \
  --file storage_review_notes=evidence/operator-storage-review-notes.txt \
  --out evidence/physical-bringup-dossier-verification.json
```

If the dossier includes Kali early-userspace or `rootfs_artifact`, those roles
must also be supplied. Missing roles and extra roles both fail closed.

A successful reverification means only that the audit byte set survived transfer
unchanged. It does not select a target, authorize a write, verify storage or
recovery, prove hardware, or grant Beta credit.
