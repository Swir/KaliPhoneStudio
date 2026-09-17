# Physical Storage Manual Review Gate

KaliPhoneStudio does not promote a syntactically complete storage-discovery record directly into a rootfs staging target. A separate human review decision is required first.

This gate is intentionally narrow: it may allow **offline strategy design only**. It never selects a block device, mount point, filesystem target or write operation, and it never grants hardware or Beta credit.

## Inputs

The review binds one exact `PhysicalStorageDiscoveryEvidence` record produced by `scripts/record_physical_storage_discovery.py` to one exact reviewer-authored JSON record.

An approval is accepted only when the bound discovery evidence already has `discovery_ready_for_manual_review=true`. A rejection may be recorded even when discovery evidence is incomplete.

## Review record schema

```json
{
  "schema_version": 1,
  "profile_id": "oneplus/avicii",
  "device_serial": "REPLACE_WITH_EXACT_SERIAL",
  "review_policy": "human-storage-discovery-review-v1",
  "review_scope": "discovery-evidence-only-no-target-v1",
  "reviewer_id": "REPLACE_WITH_REVIEWER_ID",
  "decision": "approve_for_strategy_design",
  "physical_storage_discovery_sha256": "REPLACE_WITH_EXACT_EVIDENCE_SHA256",
  "discovery_report_sha256": "REPLACE_WITH_EXACT_REPORT_SHA256",
  "recovery_plan_sha256": "REPLACE_WITH_EXACT_RECOVERY_PLAN_SHA256",
  "target_selected": false,
  "storage_path_bound": false,
  "write_authorized": false,
  "phone_storage_written": false,
  "attestation": "I reviewed the exact physical storage discovery evidence and recovery plan; this decision does not select a storage target or authorize a write."
}
```

Valid decisions are:

- `approve_for_strategy_design` — the exact reviewed discovery evidence may be used to design a later reversible handoff proposal offline;
- `reject` — the exact discovery evidence is not accepted for strategy design.

Approval is **not** permission to stage a rootfs and is **not** a target approval.

## Recorder

```bash
python scripts/record_physical_storage_review.py \
  --discovery-evidence evidence/physical-storage-discovery.json \
  --review-record evidence/operator-storage-review.json \
  --out evidence/physical-storage-review.json
```

The recorder performs no phone I/O. It only verifies and binds files already present on the host.

## Fail-closed rules

The review gate rejects:

- profile or serial drift;
- detached discovery/report/recovery digests;
- approval of discovery evidence that is not review-ready;
- unknown decisions, policy versions or review scopes;
- modified required attestation text;
- unsafe reviewer identifiers;
- target-selection, storage-path, write or phone-storage-write claims;
- promoted hardware/Beta claims in generated evidence;
- symlink review records and mutable output overwrite attempts.

Generated `PhysicalStorageReviewEvidence` always keeps:

```text
target_selected=false
storage_path_bound=false
write_authorized=false
handoff_ready=false
storage_verified=false
recovery_verified=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
```

`strategy_design_allowed=true` means only that a human accepted the exact discovery evidence as sufficient input for **offline design of a later proposal**. A future milestone must still define a reversible strategy, bind an exact target only after physical review, and require separate explicit user authorization before any device write.
