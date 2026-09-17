# Physical Functional Hardware Tests

KaliPhoneStudio 0.6.62-dev adds the evidence path that follows the profile-driven pending test plan. This path is intentionally **record/review only**: the tools in this document do not connect to a phone, activate hardware, mount or decrypt storage, run Fastboot/ADB, or authorize a persistent write.

A reviewed result is useful evidence for the later release gate. It is **not** an automatic project support claim and does not grant Beta credit.

## Required chain

One functional result must remain attached to one exact chain:

```text
accepted hardware-survey review
        |
        v
physical hardware test plan
        |
        v
operator observation record + notes
        |
        v
PhysicalHardwareTestObservationEvidence
        |
        v
manual review record + notes
        |
        v
PhysicalHardwareTestReviewEvidence
        |
        v
optional exact-plan summary
```

The observation evidence carries the exact profile, serial, test-plan digest, survey/review/boot/rescue/transcript identities, rescue probe id and functional-hardware contract digest. The review layer refuses identity or outcome drift.

## 1. Start from the exact plan

Build the plan only after a real hardware-presence survey has an accepted contextual review:

```bash
python scripts/build_physical_hardware_test_plan.py \
  --profile-id oneplus/avicii \
  --hardware-review-evidence evidence/physical-hardware-review.json \
  --output evidence/physical-hardware-test-plan.json
```

A test can be recorded only when that exact test is still `pending` and its declared context signals are satisfied. A globally incomplete plan does not silently waive a selected test's own prerequisites.

## 2. Create a safe observation template

```bash
python scripts/prepare_physical_hardware_test_observation.py \
  --test-plan evidence/physical-hardware-test-plan.json \
  --test-id display \
  --operator operator-1 \
  --out evidence/display-observation-record.json
```

The generated record is deliberately **not executable evidence**:

- `outcome=inconclusive`;
- `physical_test_executed=false`;
- exact-candidate and physical-observation flags are false;
- every required observation check is false;
- hardware verification and Beta credit are false.

It must be edited only after the exact physical test has actually been performed. A `pass_candidate` is rejected unless every exact `required_observations` item from the plan is marked satisfied.

Create a separate UTF-8 notes file containing the real physical context, what was exercised, limitations, and relevant operator observations.

## 3. Bind the physical observation

After the real test attempt:

```bash
python scripts/record_physical_hardware_test_observation.py \
  --test-plan evidence/physical-hardware-test-plan.json \
  --test-id display \
  --observation-record evidence/display-observation-record.json \
  --observation-notes evidence/display-observation-notes.txt \
  --out evidence/display-observation-evidence.json
```

Binding requires:

- an actually executed physical test;
- the exact candidate identity to have been confirmed;
- the physical device to have been observed;
- limitations to be recorded;
- no persistent write and no phone-storage write;
- exact required observations from the plan with no text/order substitution.

Possible observation outcomes are `pass_candidate`, `failed`, and `inconclusive`. None is a reviewed support result yet.

## 4. Create the rejected-by-default review template

```bash
python scripts/prepare_physical_hardware_test_review.py \
  --observation-evidence evidence/display-observation-evidence.json \
  --reviewer reviewer-1 \
  --out evidence/display-review-record.json
```

The template starts with `decision=rejected` and every review check false.

For an accepted result, the decision must match the exact observation outcome:

| Observation outcome | Matching review decision | Reviewed result |
|---|---|---|
| `pass_candidate` | `accepted_pass` | `pass` |
| `failed` | `accepted_fail` | `fail` |
| `inconclusive` | `accepted_inconclusive` | `inconclusive` |

All exact-plan, exact-observation, physical-context, required-observation, notes/limitations and no-persistent-write checks must be true before an accepted review can bind.

## 5. Bind manual review

```bash
python scripts/review_physical_hardware_test_observation.py \
  --observation-evidence evidence/display-observation-evidence.json \
  --review-record evidence/display-review-record.json \
  --review-notes evidence/display-review-notes.txt \
  --out evidence/display-review-evidence.json
```

A reviewed pass sets only `test_passed_review=true` inside the exact evidence record. It still forces:

```text
project_support_claim_authorized=false
persistent_write_performed=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
manual_release_gate_review_required=true
```

This separation prevents a unit test, synthetic evidence file or one subsystem result from silently becoming a public hardware-support or release claim.

## 6. Build an exact-plan status summary

Any number of exact review evidence files can be summarized:

```bash
python scripts/summarize_physical_hardware_tests.py \
  --test-plan evidence/physical-hardware-test-plan.json \
  --review-evidence evidence/display-review-evidence.json \
  --review-evidence evidence/usb-rescue-review-evidence.json \
  --out evidence/physical-hardware-test-summary.json
```

The summary reports `pending`, `reviewed_pass`, `reviewed_fail`, `reviewed_inconclusive`, or `rejected` for every test in the exact plan. It also counts Beta-required reviewed passes.

Even `beta_required_tests_all_reviewed_pass=true` does **not** set `beta_gate_credit=true`. The complete `BETA_RELEASE_GATE.md` still requires the exact real AC2003 firmware baseline, storage/recovery evidence, temporary boot, Kali early-userspace proof and all other mandatory physical checks.

## Non-credit and safety rules

- Synthetic/mock observation and review records are useful only for tests and never satisfy a physical gate.
- A plan cannot execute hardware; observation/review tools cannot execute hardware either.
- No functional-test record may claim or perform a persistent write.
- A reviewed pass is test-level evidence, not automatic device-level support.
- Public README compatibility, `BUILD_STATUS.json`, Beta/Stable state and release publication must change only after separate review of real physical evidence.
- Never publish a Beta from these records alone.
