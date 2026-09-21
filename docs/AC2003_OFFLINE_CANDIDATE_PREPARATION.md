# AC2003 offline physical-candidate preparation

`prepare-physical-candidate-offline` collapses the host-only portion of the first AC2003 bring-up from several independent commands into one fail-closed preparation step.

It is intended to run **after** `begin-physical-test-session` has created a fresh read-only Fastboot baseline and **before** the separately reviewed `execute-temporary-boot-once` action. It does not contact the phone, does not run ADB/Fastboot, does not boot/reboot, does not switch slots and does not write phone storage.

## Inputs

The command requires:

- the fresh first-test session directory;
- the exact OxygenOS OTA matching that session;
- the source-locked `payload-dumper-go` executable and platform key;
- the exact reviewed first-boot manifest;
- the reviewed authority bundle;
- the exact temporary-boot authorization;
- the exact boot build plan;
- the exact candidate `boot.img`;
- the exact candidate DTBO when required by the device profile;
- the **same reviewed Fastboot executable** already bound by the first-test capture.

All supplied local artifacts are stable-file checked before the first preparation stage. Every generated safety output is re-hashed again before the final preparation manifest is committed.

## Windows operator example

From the extracted Windows Beta-test-candidate package:

```powershell
$Cli = (Resolve-Path ".\KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe").Path

& $Cli prepare-physical-candidate-offline `
  --profile-id oneplus/avicii `
  --session-dir "$Session" `
  --ota "<PATH_TO_EXACT_MATCHING_OXYGENOS_OTA>" `
  --extractor "<PATH_TO_REVIEWED_PAYLOAD_DUMPER_GO_EXE>" `
  --extractor-platform windows-amd64 `
  --first-boot-manifest "<EXACT_FIRST_BOOT_MANIFEST_JSON>" `
  --authority-bundle "<EXACT_AUTHORITY_BUNDLE_JSON>" `
  --boot-authorization "<EXACT_TEMPORARY_BOOT_AUTHORIZATION_JSON>" `
  --boot-plan "<EXACT_BOOT_PLAN_JSON>" `
  --candidate-boot "<EXACT_CANDIDATE_BOOT_IMG>" `
  --candidate-dtbo "<EXACT_CANDIDATE_DTBO_IMG>" `
  --fastboot-executable "<SAME_REVIEWED_FASTBOOT_EXE>"
```

The current `oneplus/avicii` candidate requires the exact external candidate DTBO from the reviewed boot plan, so provide `--candidate-dtbo` for AC2003.

## Stages performed

The command reuses the existing independently tested boundaries in this exact order:

1. exact OTA → `payload.bin` → stock `boot.img` extraction and provenance;
2. physical Fastboot baseline + stock provenance → physical stock baseline;
3. physical stock baseline + reviewed authorities/candidate data → physical candidate gate;
4. local stock/candidate boot-chain inspection → physical boot-identity binding;
5. captured Fastboot identity + exact candidate image → **non-executing** temporary-boot offer;
6. exact stock boot + A/B context + boot identity → physical recovery-readiness evidence;
7. stable re-hash of the generated safety evidence → final offline-preparation manifest.

The session receives these outputs when all stages pass:

```text
<session>/stock/...
<session>/physical-stock-baseline.json
<session>/physical-candidate-gate.json
<session>/physical-boot-identity.json
<session>/temporary-boot-offer.json
<session>/physical-recovery-readiness.json
<session>/physical-candidate-offline-preparation.json
```

The final manifest binds the first-test session identity, firmware, operator-supplied candidate sources and all five generated safety outputs. It records `ready_for_temporary_boot_safety_review=true` only after every host stage and final re-hash succeeds.

## Fail-closed rules

The command refuses before preparation when:

- the session path does not exist or is a symlink;
- the session manifest does not describe the selected profile;
- the session is not the read-only baseline state;
- temporary boot/write/hardware/Beta flags in the session are unsafe;
- any required baseline/candidate/source file is missing, symlinked or unstable;
- the stock directory or any later evidence output already exists;
- any existing host-side subcommand rejects identity, provenance, structure, source lock, candidate binding or recovery readiness.

A partial host stage is never treated as complete and the final preparation manifest is not written when a stage fails. Do not delete or recycle partial evidence after a refusal; start a new physical test session if the exact evidence campaign changes.

## What success does **not** mean

Success does not mean the phone booted Kali, Phosh works, storage is safe to write, recovery has been exercised, hardware is supported, or Beta is ready. The preparation command itself always keeps:

- `physical_interaction_performed_by_this_command=false`;
- `external_device_command_executed=false`;
- `temporary_boot_executed=false`;
- `persistent_write_authorized=false`;
- `phone_storage_written=false`;
- `hardware_verified=false`;
- `beta_release_authorized=false`;
- `beta_gate_credit=false`.

After reviewing the generated candidate and recovery-readiness evidence, continue with the separately gated one-shot temporary boot from `docs/AC2003_FIRST_TEST.md`. A public Beta still requires the complete physical gate in `BETA_RELEASE_GATE.md`.
