# Physical hardware test-plan manual review

KaliPhoneStudio does not treat a generated functional-hardware test plan as permission to start testing a phone. The plan is deterministic host-side evidence; before it can be used for a real physical test session, a human reviewer must inspect the **exact canonical plan bytes** and bind that review into separate evidence.

This layer is intentionally non-executing. It performs no phone I/O, activates no subsystem, writes no phone storage, and grants no hardware or Beta credit.

## Why this gate exists

The physical functional-test plan already binds a profile, device serial, accepted hardware-survey review, rescue/boot transcript chain and the profile's `functional_hardware` contract. A downstream SHA-256 alone is not enough for the operator workflow: an independent reviewer should confirm the original plan file that will actually be followed.

`PhysicalHardwareTestPlanReviewEvidence` therefore records both:

- the semantic evidence SHA-256 of the parsed plan;
- the SHA-256 and byte size of the original canonical plan file;
- the exact upstream hardware-review/survey/boot/rescue/transcript/probe/contract identities;
- the exact review-record bytes and separate UTF-8 notes bytes.

Any non-canonical plan, changed file, identity drift, incomplete accepted review or forbidden execution/write/support claim fails closed.

## Safe workflow

Prepare a rejected-by-default record:

```bash
python scripts/prepare_physical_hardware_test_plan_review.py \
  --test-plan evidence/physical-hardware-test-plan.json \
  --reviewer reviewer-1 \
  --out evidence/physical-hardware-test-plan-review-record.json
```

The generated record starts with `decision="rejected"` and every review check set to `false`. Review the exact plan and edit the canonical JSON only after checking:

1. the exact plan bytes;
2. profile/device identity and upstream evidence chain;
3. the profile functional-hardware contract;
4. which tests are required for Beta;
5. whether every Beta-required test has the required context signals;
6. the non-destructive/no-persistent-write policy;
7. limitations: plan acceptance is not hardware verification and is not Beta credit.

Record separate review notes, then bind the evidence:

```bash
python scripts/review_physical_hardware_test_plan.py \
  --test-plan evidence/physical-hardware-test-plan.json \
  --review-record evidence/physical-hardware-test-plan-review-record.json \
  --review-notes evidence/physical-hardware-test-plan-review-notes.txt \
  --out evidence/physical-hardware-test-plan-review.json
```

`accepted_for_physical_execution=true` is possible only when the plan itself is ready, `decision="accepted"`, and every exact review check is true.

## Safety semantics

Even an accepted review always retains:

- `manual_test_execution_required=true`;
- `functional_tests_executed=false`;
- `functional_hardware_verified=false`;
- `phone_storage_written=false`;
- `hardware_verified=false`;
- `beta_gate_credit=false`.

The phrase **accepted for physical execution** means only: this exact reviewed plan may be used as the checklist/input for later explicitly manual, non-destructive physical functional tests. It is not permission for flashing, storage writes, automatic hardware activation, support claims or a release.

Synthetic fixtures and CI prove only the contract. The first AC2003 still requires real exact-device observations, independent per-test reviews and the complete `BETA_RELEASE_GATE.md`.
