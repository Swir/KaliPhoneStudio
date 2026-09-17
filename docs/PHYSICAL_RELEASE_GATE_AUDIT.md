# Physical release-gate cross-campaign audit

`kaliphonestudio.physical_release_gate_audit` is an offline, fail-closed audit boundary for one physical bring-up context. It prevents a later release review from accidentally combining a storage/bring-up dossier from one phone or rescue session with functional-test results from another.

## What it binds

The audit requires the exact canonical files for:

- the physical bring-up dossier;
- the independent post-copy dossier verification;
- the accepted manual dossier review;
- the physical functional-result bundle;
- the canonical physical functional-test plan;
- the accepted independent test-plan review.

Every file is re-read as a regular non-symlink file, bounded by size, checked for change during the read, required to be canonical JSON and bound by SHA-256 plus byte size.

## Cross-campaign identity checks

The audit rejects the packet unless all supplied evidence has the same `profile_id` and physical device serial. It additionally requires the functional test plan to reference the exact same:

- physical boot observation contained in the bring-up dossier;
- rescue diagnostics contained in the bring-up dossier;
- raw rescue transcript contained in the bring-up dossier;
- rescue probe id recorded by the dossier;
- functional-hardware contract recorded by the exact functional-result bundle.

The functional-result bundle must identify the exact supplied plan and exact supplied accepted plan-review file. The dossier review must identify the exact supplied dossier and exact supplied dossier verification.

This closes an important audit gap: a functionally complete test bundle cannot be presented beside an unrelated bring-up/storage dossier merely because both use the same device model.

## What acceptance means

A successfully built `PhysicalReleaseGateAuditEvidence` means only that the exact evidence files are internally consistent and cross-bound to one physical campaign context. It remains explicit that:

- `manual_release_gate_review_required=true`;
- `physical_gate_still_incomplete=true`;
- `target_selected=false`;
- `storage_path_bound=false`;
- `write_authorized=false`;
- `project_support_claim_authorized=false`;
- `persistent_write_performed=false`;
- `phone_storage_written=false`;
- `hardware_verified=false`;
- `beta_release_authorized=false`;
- `beta_gate_credit=false`.

Even if every Beta-required functional test is independently reviewed as passing, that status is only copied into the audit packet as evidence. It does not grant hardware support or release readiness. Kali early-userspace presence is recorded separately and does not bypass the remaining physical gates.

## Build the audit packet

```bash
python scripts/build_physical_release_gate_audit.py \
  --dossier evidence/physical/dossier.json \
  --dossier-verification evidence/physical/dossier-verification.json \
  --dossier-review evidence/physical/dossier-review.json \
  --functional-result-bundle evidence/physical/functional-result-bundle.json \
  --test-plan evidence/physical/functional-test-plan.json \
  --test-plan-review evidence/physical/functional-test-plan-review.json \
  --out evidence/physical/release-gate-audit.json
```

The command performs no Fastboot/ADB operation, no mount/decrypt operation, no target selection and no phone write. The output path must not already exist.

## Release policy

This packet is an input to the mandatory manual review in `BETA_RELEASE_GATE.md`; it is not the gate itself. The first AC2003 Beta still requires real baseline/stock-boot identity, successful temporary boot, usable rescue/logging, physical Kali early userspace/rootfs proof, storage and charging safety, required hardware results, exercised recovery/rollback, and the final release manifest/checksums/compatibility review.

Synthetic or mock evidence is useful only for host-side tests and receives no hardware or Beta credit.
