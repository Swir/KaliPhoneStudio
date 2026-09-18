# Physical Candidate Operator Chain

This document describes the shared KaliPhoneStudio host CLI path from an already-reviewed physical stock baseline to a one-shot **temporary** Fastboot boot attempt. It is multi-device and profile-driven; it does not make `oneplus/avicii` or any other profile physically supported.

The same entry points are available through source `main.py` and the frozen Windows development CLI.

## Safety boundary

The chain intentionally has three separate stages:

1. `bind-physical-candidate-gate` — offline evidence binding only;
2. `prepare-temporary-boot-offer` — offline exact-file/argv preparation only;
3. `execute-temporary-boot-once` — the only stage that may query the phone and invoke the already-reviewed serial-bound `fastboot boot` command.

No stage exposes `flash`, `erase`, `set_active`, `flashing` or another persistent Fastboot write verb. A successful Fastboot command is not proof that the kernel booted, Kali userspace was reached, storage works, charging is safe or any Beta hardware gate passed.

## 1. Bind the exact physical candidate gate

The operator must already have an exact physical stock baseline, first-boot candidate manifest, reviewed authority bundle, temporary-boot authorization and deterministic boot plan from the same profile/device/firmware chain.

```powershell
KaliPhoneStudioCLI.exe bind-physical-candidate-gate `
  --profile-id oneplus/avicii `
  --physical-baseline evidence/physical-baseline.json `
  --first-boot-manifest evidence/first-boot-candidate.json `
  --authority-bundle evidence/first-boot-authorities.json `
  --boot-authorization evidence/temporary-boot-authorization.json `
  --boot-plan evidence/boot-build-plan.json `
  --out evidence/physical-candidate-gate.json
```

The command is offline. It rejects unknown/missing fields, non-regular evidence files, changed files and a detached identity/firmware/authority/boot chain. A valid result can only set `ready_for_temporary_boot_offer=true`; it cannot execute Fastboot or grant hardware/Beta credit.

## 2. Prepare the exact temporary-boot offer

The offer stage re-hashes the exact reviewed Fastboot executable and exact candidate boot image and joins them to the same physical candidate/capture/tool evidence.

```powershell
KaliPhoneStudioCLI.exe prepare-temporary-boot-offer `
  --profile-id oneplus/avicii `
  --physical-candidate-gate evidence/physical-candidate-gate.json `
  --capture-bundle evidence/fastboot-capture-bundle.json `
  --fastboot-tool-evidence evidence/fastboot-tool.json `
  --fastboot-executable tools/platform-tools/fastboot.exe `
  --boot-image artifacts/candidate-boot.img `
  --out evidence/temporary-boot-offer.json
```

This stage is also offline. It prints an argv preview but does **not** authorize or execute it. The offer remains `temporary_boot_executed=false`, `phone_storage_written=false`, `hardware_verified=false`, `beta_gate_credit=false`.

## 3. One-shot temporary boot

Physical execution is never implicit. The operator must supply the selected profile's exact confirmation text and the separate `--execute-temporary-boot` flag in the same invocation:

```powershell
KaliPhoneStudioCLI.exe execute-temporary-boot-once `
  --profile-id oneplus/avicii `
  --physical-candidate-gate evidence/physical-candidate-gate.json `
  --capture-bundle evidence/fastboot-capture-bundle.json `
  --baseline-evidence evidence/fastboot-baseline.json `
  --fastboot-tool-evidence evidence/fastboot-tool.json `
  --fastboot-executable tools/platform-tools/fastboot.exe `
  --boot-image artifacts/candidate-boot.img `
  --confirmation "<EXACT PROFILE CONFIRMATION TEXT>" `
  --execute-temporary-boot `
  --probe-out evidence/temporary-boot-runtime-probe.json `
  --execution-out evidence/temporary-boot-execution.json
```

Before any phone query, the CLI verifies that the two evidence output paths are distinct and unused and that their host directories are writable. It then re-loads exact typed evidence, re-hashes the executable/image and validates the profile confirmation. Only after those checks does the core perform a fresh read-only serial-bound Fastboot probe and compare critical identity/security/slot variables with the reviewed baseline.

If and only if that fresh probe still matches, the core may invoke exactly:

```text
fastboot -s <EXACT_SERIAL> boot <EXACT_REVIEWED_IMAGE>
```

There is no general Fastboot command passthrough.

## Evidence meaning

`TemporaryBootRuntimeProbeEvidence` proves the fresh pre-execution read-only identity observation used for that attempt.

`TemporaryBootExecutionEvidence` records whether the exact command was invoked, its return code and bounded output digest. Even when the return code is zero, the record deliberately retains:

```text
persistent_write=false
phone_storage_written=false
kali_userspace_verified=false
hardware_verified=false
beta_gate_credit=false
```

A later physical boot-observation/rescue transcript must independently prove what actually happened on the phone. The Beta release gate still requires the complete real-device evidence chain in `BETA_RELEASE_GATE.md`.

## Refusal behavior

The execution command fails before evidence loading or device I/O when `--execute-temporary-boot` is missing. It also fails before device I/O when the requested audit output paths collide, already exist, have stale `.tmp` paths or cannot pass the local writeability preflight.

The Windows build workflow verifies these fail-closed boundaries from the frozen `KaliPhoneStudioCLI.exe` without connecting a phone and without ever supplying the execution opt-in.
