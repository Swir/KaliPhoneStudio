# Physical Storage Manual Review

KaliPhoneStudio 0.6.57 adds a **manual-review evidence layer** between physical storage discovery and any future rootfs staging strategy.

This layer is intentionally non-destructive. It does not connect to a phone, mount a filesystem, choose a block-device path, authorize a write, verify storage hardware or satisfy the Beta gate by itself.

## Safety boundary

The input must be one exact `PhysicalStorageDiscoveryEvidence` file produced from the same physical-candidate/rescue/rootfs chain. A review can be accepted for later strategy design only when:

- the source discovery is already `discovery_ready_for_manual_review=true`;
- the reviewer explicitly confirms the physical device/firmware context;
- whole-block topology was reviewed against the bound rescue observations;
- filesystem identity was reviewed;
- encryption state/features were reviewed;
- free-space evidence was reviewed;
- the recovery plan was reviewed;
- the complete evidence chain was reviewed.

Even an accepted review keeps all of these false:

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

`accepted_for_strategy_design=true` means only that a later milestone may use this exact reviewed evidence while designing a reversible rootfs staging strategy. That later strategy still requires a separate review and must not infer a raw device path from the profile hint alone.

## 1. Create a safe review template

Generate a template from the exact discovery evidence:

```bash
python scripts/prepare_physical_storage_review.py \
  --discovery-evidence evidence/physical-storage-discovery.json \
  --reviewer operator-1 \
  --out evidence/operator-storage-review.json
```

The generated template copies only the profile ID and device serial from the validated discovery evidence. It deliberately starts with:

- `decision: "rejected"`
- every review check set to `false`
- `target_selected: false`
- `storage_path_bound: false`
- `write_authorized: false`

The generator refuses to overwrite an existing file.

## 2. Review the physical evidence

Inspect the exact discovery evidence, original discovery report, recovery plan and bound rescue/candidate context. Record review notes in a separate UTF-8 text file.

Only after every required check has genuinely been completed may the review record use:

```json
{
  "decision": "accepted_for_strategy_design",
  "physical_context_reviewed": true,
  "topology_reviewed": true,
  "filesystem_reviewed": true,
  "encryption_reviewed": true,
  "free_space_reviewed": true,
  "recovery_plan_reviewed": true,
  "evidence_chain_reviewed": true,
  "target_selected": false,
  "storage_path_bound": false,
  "write_authorized": false
}
```

Do not add device paths, mount targets or write instructions to the structured review record. Unknown fields are rejected.

## 3. Bind the review

```bash
python scripts/review_physical_storage_discovery.py \
  --discovery-evidence evidence/physical-storage-discovery.json \
  --review-record evidence/operator-storage-review.json \
  --review-notes evidence/operator-storage-review-notes.txt \
  --out evidence/physical-storage-review.json
```

The resulting evidence binds:

- the exact physical-storage discovery evidence digest;
- candidate/rootfs/rescue/transcript identities inherited from that discovery;
- exact discovery-report and recovery-plan digests;
- exact review-record bytes, SHA-256 and size;
- exact review-notes bytes, SHA-256 and size;
- reviewer identifier, decision and all review checks.

The writer is immutable and refuses to overwrite an existing evidence file.

## Rejection is a valid result

A reviewer may record `decision: "rejected"` without turning incomplete or inconsistent observations into an error. Rejection does not authorize any later strategy. A positive acceptance fails closed unless the source discovery is review-ready and every required review check is explicitly true.

## What comes next

No storage target-selection algorithm should be implemented or used for AC2003 until a **real physical** discovery record has been captured and accepted through this review contract. The next target-selection milestone must consume the exact accepted review evidence and remain separately reviewable and reversible.
