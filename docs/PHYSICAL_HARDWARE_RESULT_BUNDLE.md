# Exact Physical Functional Result Bundle

KaliPhoneStudio uses an exact-file audit bundle after individual physical functional-test observations have been independently reviewed. The bundle is a host-side audit artifact only. It performs no phone I/O, selects no storage target, authorizes no persistent write and never grants hardware support or Beta release credit.

## Purpose

The bundle closes the exact identity chain across one physical functional-test campaign:

1. the canonical profile-driven test plan;
2. the independently accepted exact-plan review;
3. every supplied schema-v2 physical observation evidence file;
4. every supplied independent result-review evidence file; and
5. the deterministic aggregate functional-test summary.

Each source file is required to be canonical UTF-8 JSON, a regular non-symlink file and unchanged while it is hashed. The bundle records SHA-256 and byte size for the exact plan, plan-review, observation, result-review and summary evidence files.

## Fail-closed rules

A bundle is rejected when any of these conditions occurs:

- the plan review is not `decision=accepted` with `accepted_for_physical_execution=true`;
- profile, serial, functional-hardware contract, survey, boot, rescue, transcript or probe identities drift;
- a schema-v2 observation does not carry the exact accepted plan-review evidence/file/review-record/review-notes identities;
- two observations or two result reviews claim the same test id;
- a result review has no exact bundled observation for the same test id;
- the result review does not point at the exact observation evidence digest;
- the supplied summary differs from a fresh summary recomputed from the exact bundled reviews;
- any source file is non-canonical, replaced while being read, a symlink or outside the bounded file-size policy; or
- any bundle attempts to promote project support, writes, hardware verification or Beta credit.

An executed observation may legitimately remain `pending` in the summary while it waits for independent result review. That state is preserved rather than silently promoted.

## Build a bundle

```bash
python scripts/build_physical_hardware_result_bundle.py \
  --test-plan evidence/physical/test-plan.json \
  --test-plan-review-evidence evidence/physical/test-plan-review.evidence.json \
  --observation-evidence evidence/physical/display.observation.evidence.json \
  --review-evidence evidence/physical/display.review.evidence.json \
  --summary-evidence evidence/physical/functional-summary.evidence.json \
  --out evidence/physical/functional-result-bundle.evidence.json
```

Repeat `--observation-evidence` and `--review-evidence` for additional tests. Tests that have not yet been executed or reviewed remain represented by the exact plan/summary state.

## Release semantics

`beta_required_tests_all_reviewed_pass=true` means only that every Beta-required test in this exact plan has an independently reviewed pass in the bundled result set. It does **not** mean the project is Beta-ready. KaliPhoneStudio still requires the complete `BETA_RELEASE_GATE.md`, including the exact physical AC2003 baseline, matching stock boot image, temporary boot, rescue/log path, Kali early userspace/rootfs, storage/charging safety, required display/touch scope and exercised recovery/rollback.

The bundle therefore always keeps these values false:

- `project_support_claim_authorized`;
- `persistent_write_performed`;
- `phone_storage_written`;
- `hardware_verified`; and
- `beta_gate_credit`.

A separate human release-gate review remains mandatory even when the exact functional result set is complete.
