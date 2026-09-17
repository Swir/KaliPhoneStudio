# Physical functional-hardware test plan

KaliPhoneStudio keeps device discovery, contextual review and actual functional verification separate.

`test_contract.functional_hardware` in each device profile is the machine-readable list of later physical subsystem tests. The schema is intentionally fail-closed: every test requires manual review, `destructive` must be `false`, and `persistent_write_allowed` must be `false`. Adding a profile or a test contract never means the hardware works.

`scripts/build_physical_hardware_test_plan.py` accepts only an exact `PhysicalHardwareReviewEvidence` record whose bounded hardware-presence survey was manually accepted as context. It then binds that review to the selected profile contract and writes a deterministic pending-only plan. The command performs no phone I/O and cannot activate Wi-Fi, Bluetooth, modem, audio, display, charging controls, storage writes, Fastboot or recovery actions.

Every generated test starts with `status=pending`. The plan also fixes `functional_tests_executed=false`, `functional_hardware_verified=false`, `phone_storage_written=false`, `hardware_verified=false` and `beta_gate_credit=false`. Later physical-test evidence must be implemented and manually reviewed separately before any individual subsystem can be promoted.

For `oneplus/avicii`, the contract currently describes USB rescue/logging, display, touch, Wi-Fi, Bluetooth, audio, modem, power/charging, thermal behavior, storage and recovery. Beta-required flags describe the project's gate policy only; they are not pass results. Display/touch retain the documented possibility of a separately reviewed console-only Beta scope rather than being silently assumed functional.

Example (after a real accepted review exists):

```bash
python scripts/build_physical_hardware_test_plan.py \
  --profile-id oneplus/avicii \
  --hardware-review-evidence evidence/physical/hardware-review.json \
  --output evidence/physical/hardware-test-plan.json
```

Do not manufacture an accepted review from synthetic data for a release. Host tests validate the evidence contract only; physical Beta credit requires reviewed evidence from the exact supported phone and firmware.
