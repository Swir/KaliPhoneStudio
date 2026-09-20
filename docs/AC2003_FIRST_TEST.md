# AC2003 First Test — Operator Runbook

This runbook is for the first physical bring-up of **OnePlus Nord AC2003** with the profile `oneplus/avicii`.

It is intentionally recovery-first and evidence-first. The Windows package produced by the Beta-test-candidate workflow is a **development test candidate**, not a public Beta and not a hardware-support claim. Nothing in this runbook authorizes a persistent phone write by itself.

## What should already be in the candidate ZIP

Keep the extracted package together. It should contain:

- `KaliPhoneStudio/` — frozen GUI;
- `KaliPhoneStudioCLI/` — frozen CLI;
- `operator-pack/AC2003_FIRST_TEST.md` — this file;
- `operator-pack/BETA_RELEASE_OPERATOR_WORKSPACE.md`;
- `operator-pack/BETA_RELEASE_GATE.md`;
- `operator-pack/BUILD_STATUS.json`;
- `operator-pack/profile.json` — exact packaged `oneplus/avicii` profile;
- `operator-pack/fastboot-tool-policy.json`;
- `operator-pack/extractor-locks.json`;
- `BETA_TEST_CANDIDATE_SHA256.txt`;
- `BETA_TEST_CANDIDATE_INFO.json`.

Verify the ZIP SHA-256 before using the package. Then keep all evidence from one phone/firmware attempt under one fresh session directory; do not overwrite or recycle files from an older attempt.

## Safety stop conditions

Stop immediately if any of these are true:

- the phone is not the expected AC2003 / `avicii` profile;
- the exact OxygenOS build or firmware fingerprint is unknown;
- Fastboot reports an unexpected serial, product, slot count or security state;
- the exact OTA matching the phone firmware is unavailable;
- extracted `boot.img` does not validate against the selected profile;
- a required evidence file or intended session directory already exists, or any command reports identity/hash drift;
- recovery/rollback is not understood before temporary boot;
- a command requests a persistent `flash`, `erase`, `set_active`, `flashing` or other write action that is not part of the reviewed runbook.

The first physical sequence below uses read-only capture and offline binding first. The only physical boot command later in the chain is the explicitly gated one-shot temporary `fastboot boot` path.

## 0. Prepare the Windows host

Open PowerShell in the extracted candidate directory and define the frozen CLI:

```powershell
$Cli = (Resolve-Path ".\KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe").Path
```

Run the packaged host checks before connecting the phone:

```powershell
& $Cli --list-profiles --json
& $Cli --doctor --profile-id oneplus/avicii --json
& $Cli --recovery-guide --profile-id oneplus/avicii --json
```

Use an exact Fastboot executable accepted by `operator-pack/fastboot-tool-policy.json`. The current repository policy is exact-version, not floating-latest. Do not substitute an unreviewed Fastboot binary after evidence capture has started.

## 1. Record the exact phone firmware before Fastboot capture

Before moving the phone into Fastboot mode, record the exact OxygenOS build and full firmware fingerprint from the device/system information available on the phone. These two strings are operator inputs to the guarded baseline capture; do not guess or shorten them.

Choose a new session path, but **do not create it**. The guarded first-test command creates it itself and refuses any existing file, directory or symlink so evidence from different attempts cannot be mixed:

```powershell
$Session = Join-Path $PWD "evidence\ac2003-first-test-01"
if (Test-Path $Session) { throw "Choose a new session path; this one already exists." }
```

Do not reuse this path after a failed or changed-firmware attempt. Choose a new session name instead.

## 2. One-command read-only Fastboot first-test session

Put the phone in Fastboot/bootloader mode using the normal device controls. Confirm the exact serial shown by the reviewed Fastboot executable, then run the guarded first-test session command.

Replace the angle-bracket values with the exact observations from this phone:

```powershell
& $Cli begin-physical-test-session `
  --profile-id oneplus/avicii `
  --serial "<EXACT_FASTBOOT_SERIAL>" `
  --firmware-build "<EXACT_OXYGENOS_BUILD>" `
  --firmware-fingerprint "<EXACT_FIRMWARE_FINGERPRINT>" `
  --confirm-token "AC2003" `
  --fastboot "<PATH_TO_REVIEWED_FASTBOOT_EXE>" `
  --session-dir "$Session"
```

The command checks the profile confirmation token before creating the session or reaching Fastboot, refuses an existing session path, then reuses the guarded Fastboot version/device/getvar-only capture. It does **not** boot, reboot, flash, erase, change slots, mount storage or authorize a persistent phone write.

`begin-physical-test-session` is the recovery-first wrapper around the existing `capture-fastboot-baseline` primitive. Do not run both against the same session: the wrapper deliberately owns the fresh session directory and exact baseline capture so evidence cannot be duplicated or mixed.

A successful command creates the exact baseline set under `$Session\fastboot` plus the create-only session manifest:

```text
<session>/physical-first-test-session.json
<session>/fastboot/fastboot-getvar-all.txt
<session>/fastboot/fastboot-baseline.json
<session>/fastboot/fastboot-tool.json
<session>/fastboot/fastboot-capture-bundle.json
```

The session manifest binds the selected profile, exact serial, exact firmware strings and Fastboot evidence/tool digests while explicitly keeping temporary boot, phone-storage writes, hardware verification and Beta credit false.

Do not continue if the observed product/serial/A-B/security state is unexpected or the command refuses the session.

## 3. Obtain the exact matching OxygenOS OTA

Use the OTA that matches the captured physical firmware exactly. Do not use a nearby version, another region/build, a modified package or a random stock `boot.img` from the Internet.

KaliPhoneStudio does not silently download firmware. Keep the exact local OTA as evidence input.

## 4. Extract and validate stock `boot.img` offline

Use a local `payload-dumper-go` executable whose SHA-256 matches the exact platform entry in `operator-pack/extractor-locks.json`. For Windows x64 use the `windows-amd64` lock key.

```powershell
& $Cli extract-stock-boot-from-ota `
  --profile-id oneplus/avicii `
  --ota "<PATH_TO_EXACT_OTA_ZIP>" `
  --extractor "<PATH_TO_REVIEWED_PAYLOAD_DUMPER_GO_EXE>" `
  --extractor-platform windows-amd64 `
  --out-dir "$Session\stock"
```

This is host-only. It materializes the exact `payload.bin`, extracts only the required stock boot image, validates boot structure against the profile and emits create-only provenance. It does not query or modify the phone.

Expected stock paths include:

```text
<session>/stock/payload.bin
<session>/stock/partitions/boot.img
<session>/stock/stock-provenance.json
<session>/stock/stock-extraction-report.json
```

## 5. Bind the real baseline to the exact stock firmware

After the baseline and stock provenance both exist:

```powershell
& $Cli bind-physical-stock-baseline `
  --profile-id oneplus/avicii `
  --baseline-evidence "$Session\fastboot\fastboot-baseline.json" `
  --capture-evidence "$Session\fastboot\fastboot-capture-bundle.json" `
  --stock-provenance "$Session\stock\stock-provenance.json" `
  --out "$Session\physical-stock-baseline.json"
```

This remains offline and does not authorize temporary boot.

## 6. Build/bind the exact physical candidate

Do not invent these inputs. Use only the exact reviewed candidate files generated from the same repository candidate/authority chain:

- first-boot manifest;
- authority bundle;
- temporary-boot authorization;
- boot build plan;
- candidate boot image;
- boot-identity binding;
- physical recovery-readiness evidence.

Bind the exact physical candidate only after those files match the real stock baseline:

```powershell
& $Cli bind-physical-candidate-gate `
  --profile-id oneplus/avicii `
  --physical-baseline "$Session\physical-stock-baseline.json" `
  --first-boot-manifest "<EXACT_FIRST_BOOT_MANIFEST_JSON>" `
  --authority-bundle "<EXACT_AUTHORITY_BUNDLE_JSON>" `
  --boot-authorization "<EXACT_TEMPORARY_BOOT_AUTHORIZATION_JSON>" `
  --boot-plan "<EXACT_BOOT_PLAN_JSON>" `
  --out "$Session\physical-candidate-gate.json"
```

Then prepare, but do not execute, the serial-bound temporary-boot offer:

```powershell
& $Cli prepare-temporary-boot-offer `
  --profile-id oneplus/avicii `
  --physical-candidate-gate "$Session\physical-candidate-gate.json" `
  --capture-bundle "$Session\fastboot\fastboot-capture-bundle.json" `
  --fastboot-tool-evidence "$Session\fastboot\fastboot-tool.json" `
  --fastboot-executable "<PATH_TO_THE_SAME_REVIEWED_FASTBOOT_EXE>" `
  --boot-image "<EXACT_CANDIDATE_BOOT_IMG>" `
  --out "$Session\temporary-boot-offer.json"
```

Review the generated argv and evidence before any physical boot.

## 7. Recovery-readiness gate before temporary boot

Do not run the temporary executor until the exact real baseline has a reviewed recovery-readiness record bound to:

- the captured A/B slot context;
- matching local stock `boot.img`;
- exact boot identity;
- physical candidate gate;
- reviewed boot plan.

The temporary executor requires all of those inputs again and performs a fresh read-only device/slot probe immediately before the one allowed temporary boot.

## 8. One-shot temporary boot — explicit manual action

Only when the recovery-readiness evidence has been reviewed and the candidate is exact, run the executor with the explicit opt-in. The command intentionally has no persistent write verb:

```powershell
& $Cli execute-temporary-boot-once `
  --profile-id oneplus/avicii `
  --physical-candidate-gate "$Session\physical-candidate-gate.json" `
  --boot-identity-binding "<EXACT_BOOT_IDENTITY_BINDING_JSON>" `
  --physical-baseline "$Session\physical-stock-baseline.json" `
  --recovery-readiness "<EXACT_PHYSICAL_RECOVERY_READINESS_JSON>" `
  --stock-boot "$Session\stock\partitions\boot.img" `
  --capture-bundle "$Session\fastboot\fastboot-capture-bundle.json" `
  --baseline-evidence "$Session\fastboot\fastboot-baseline.json" `
  --fastboot-tool-evidence "$Session\fastboot\fastboot-tool.json" `
  --fastboot-executable "<PATH_TO_THE_SAME_REVIEWED_FASTBOOT_EXE>" `
  --boot-image "<EXACT_CANDIDATE_BOOT_IMG>" `
  --confirmation "AC2003" `
  --execute-temporary-boot `
  --probe-out "$Session\temporary-boot-runtime-probe.json" `
  --execution-out "$Session\temporary-boot-execution.json"
```

A Fastboot return code is not proof that Kali booted. Preserve the phone-side console/rescue transcript and continue only through the reviewed physical evidence chain.

## 9. After temporary boot

Capture and review, in order:

1. rescue/log markers and exact rescue probe identity;
2. bounded read-only diagnostics and hardware-presence survey;
3. manual survey review;
4. exact functional-test plan and independent plan review;
5. real per-test schema-v2 observations and independent result reviews;
6. exact functional-result bundle;
7. physical storage/encryption/free-space/recovery evidence and manual review;
8. bring-up session and exact-file dossier/review;
9. cross-campaign release-gate audit;
10. reversible rootfs strategy review, logical target binding and distinct fresh-device revalidation;
11. explicit manual rootfs trial authorization/preflight chain;
12. Kali early-userspace/rootfs markers and required subsystem validation;
13. exercised recovery/rollback.

Use `KaliPhoneStudioCLI.exe evidence --help` and `operator-pack/BETA_RELEASE_OPERATOR_WORKSPACE.md` for the exact offline evidence commands. All evidence files from one campaign must remain tied to the same profile, serial, firmware, boot observation, rescue transcript/probe and reviewed candidate.

## 10. Final Beta preparation remains offline until the physical gate passes

After all required physical evidence is real and independently reviewed, the package exposes:

```powershell
& $Cli evidence build-beta-artifact-inventory --help
& $Cli evidence build-beta-review-manifest --help
```

Those commands create the exact local artifact inventory, review manifest and SHA-256 set. They still do not publish a GitHub release and do not grant Beta authorization by themselves.

Public Beta publication remains forbidden until every applicable item in `operator-pack/BETA_RELEASE_GATE.md` is passed for the exact physical AC2003 candidate.
