# AC2003 First Test — Operator Runbook

This runbook is for the first physical bring-up of **OnePlus Nord AC2003** with the profile `oneplus/avicii`.

It is intentionally recovery-first and evidence-first. The Windows package produced by the Beta-test-candidate workflow is a **development test candidate**, not a public Beta and not a hardware-support claim. Nothing in this runbook authorizes a persistent phone write by itself.

## What should already be in the candidate ZIP

Keep the extracted package together. It should contain:

- `KaliPhoneStudio/` — frozen GUI;
- `KaliPhoneStudioCLI/` — frozen CLI;
- `operator-tools/payload-dumper-go.exe` plus its exact side-by-side runtime DLL closure;
- `operator-tools/operator-extractor-manifest.json` and `operator-extractor-runtime.json`;
- `operator-pack/START_HERE.txt`;
- `operator-pack/AC2003_FIRST_TEST.md` — this file;
- `operator-pack/BETA_RELEASE_OPERATOR_WORKSPACE.md`;
- `operator-pack/WINDOWS_OPERATOR_EXTRACTOR.md`;
- `operator-pack/BETA_RELEASE_GATE.md`;
- `operator-pack/BUILD_STATUS.json`;
- `operator-pack/profile.json` — exact packaged `oneplus/avicii` profile;
- `operator-pack/fastboot-tool-policy.json`;
- `operator-pack/extractor-locks.json`;
- `operator-pack/verify-candidate.ps1`;
- `operator-pack/readonly-baseline.ps1`;
- `BETA_TEST_CANDIDATE_SHA256.txt`;
- `BETA_TEST_CANDIDATE_INFO.json`.

Verify the ZIP SHA-256 before using the package. Then verify the extracted package itself before connecting the phone:

```powershell
pwsh -NoProfile -File .\operator-pack\verify-candidate.ps1 -CandidateRoot .
```

Keep all evidence from one phone/firmware attempt under fresh create-only paths; do not overwrite or recycle files from an older attempt.

## Safety stop conditions

Stop immediately if any of these are true:

- the phone is not the expected AC2003 / `avicii` profile;
- the exact OxygenOS build or full firmware fingerprint cannot be captured or independently checked;
- ADB sees anything other than exactly one authorized device during the stock-Android identity phase;
- Fastboot reports an unexpected serial, product, slot count or security state;
- the exact OTA matching the phone firmware is unavailable;
- extracted `boot.img` does not validate against the selected profile;
- a required evidence file or intended session directory already exists, or any command reports identity/hash drift;
- recovery/rollback is not understood before temporary boot;
- a command requests a persistent `flash`, `erase`, `set_active`, `flashing` or other write action that is not part of the reviewed runbook.

The first physical sequence below uses read-only ADB property capture, read-only Fastboot capture and offline binding first. The only physical boot command later in the chain is the explicitly gated one-shot temporary `fastboot boot` path.

## 0. Prepare the Windows host once

Open PowerShell in the extracted candidate directory and define the exact packaged tools once for the whole session:

```powershell
$Cli = (Resolve-Path ".\KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe").Path
$Extractor = (Resolve-Path ".\operator-tools\payload-dumper-go.exe").Path
$Adb = (Resolve-Path "<PATH_TO_REVIEWED_ADB_EXE>").Path
$Fastboot = (Resolve-Path "<PATH_TO_REVIEWED_FASTBOOT_EXE>").Path
```

`$Extractor` is already the exact reviewed `payload-dumper-go.exe` bundled in the candidate. Do **not** download or search for another extractor. Keep its runtime DLLs beside it exactly as packaged.

ADB and Fastboot must come from the same reviewed Android Platform-Tools version accepted by `operator-pack/fastboot-tool-policy.json`. The guarded capture re-checks the executable/version identity; do not substitute another tool binary after evidence capture starts.

Run the packaged host checks before connecting the phone:

```powershell
& $Cli --list-profiles --json
& $Cli --doctor --profile-id oneplus/avicii --json
& $Cli --recovery-guide --profile-id oneplus/avicii --json
```

## 1. Capture exact stock-Android identity read-only

While the phone is still booted into stock OxygenOS and USB debugging is explicitly authorized, capture the exact identity/build/fingerprint with the packaged read-only launcher. This phase uses only `adb devices -l`, `adb --version` and read-only `getprop` calls; it does **not** issue `adb reboot`, push/install/remount/root commands, mount storage or authorize a persistent write.

Choose a fresh create-only identity-evidence path:

```powershell
$Identity = Join-Path $PWD "evidence\ac2003-stock-android-identity-01.json"
if (Test-Path $Identity) { throw "Choose a new identity-evidence path; this one already exists." }

pwsh -NoProfile -File .\operator-pack\readonly-baseline.ps1 `
  -CandidateRoot . `
  -AdbExecutable "$Adb" `
  -AndroidIdentityEvidence "$Identity" `
  -CaptureAndroidIdentityOnly
```

The launcher requires exactly one authorized ADB device, requires a strong `oneplus/avicii` product/model match and records the exact OxygenOS build/fingerprint plus ADB executable SHA-256/version identity. The evidence keeps temporary boot, persistent writes, hardware verification and Beta credit false.

Do not continue if the capture refuses the phone, reports tool/version drift, or the displayed build/fingerprint does not match what the phone shows in stock system information.

Choose a fresh physical-session directory, but **do not create it**. The guarded Fastboot phase creates it itself and refuses any existing file, directory or symlink so evidence from different attempts cannot be mixed:

```powershell
$Session = Join-Path $PWD "evidence\ac2003-first-test-01"
if (Test-Path $Session) { throw "Choose a new session path; this one already exists." }
```

Do not reuse either evidence path after a failed or changed-firmware attempt.

## 2. Bind that exact identity into one-command read-only Fastboot capture

Manually put the phone in Fastboot/bootloader mode using the normal device controls. Confirm the exact serial shown by the reviewed Fastboot executable, then run the packaged launcher against the **same** `$Identity` captured in section 1:

```powershell
pwsh -NoProfile -File .\operator-pack\readonly-baseline.ps1 `
  -CandidateRoot . `
  -FastbootExecutable "$Fastboot" `
  -Serial "<EXACT_FASTBOOT_SERIAL>" `
  -AndroidIdentityEvidence "$Identity" `
  -SessionDir "$Session"
```

The launcher re-runs host preflight, takes the firmware build/fingerprint from the exact ADB evidence instead of requiring retyping, executes only the frozen `begin-physical-test-session` Fastboot version/devices/getvar capture, copies the exact ADB identity record into the new session and creates a SHA-256 binding link. It does **not** boot, reboot, flash, erase, change slots, mount storage or authorize a persistent phone write.

A successful command creates the exact baseline set under `$Session\fastboot` plus the create-only session and stock-Android identity binding:

```text
<session>/physical-first-test-session.json
<session>/stock-android-identity.json
<session>/stock-android-identity-link.json
<session>/fastboot/fastboot-getvar-all.txt
<session>/fastboot/fastboot-baseline.json
<session>/fastboot/fastboot-tool.json
<session>/fastboot/fastboot-capture-bundle.json
```

The session manifest binds the selected profile, exact Fastboot serial, exact firmware strings and Fastboot evidence/tool digests while the stock-Android link binds the original ADB identity bytes by SHA-256. Temporary boot, phone-storage writes, hardware verification and Beta credit remain false.

Do not continue if the observed product/serial/A/B/security state is unexpected, if the ADB and Fastboot firmware context conflicts, or if the command refuses the session.

## 3. Obtain the exact matching OxygenOS OTA

Use the OTA that matches the captured physical firmware exactly. Do not use a nearby version, another region/build, a modified package or a random stock `boot.img` from the Internet.

KaliPhoneStudio does not silently download firmware. Keep the exact local OTA as evidence input.

## 4. One-command offline physical-candidate preparation

After the read-only session exists and the exact matching OTA is available, use the packaged extractor and the reviewed candidate inputs in **one** host-only command:

```powershell
& $Cli prepare-physical-candidate-offline `
  --profile-id oneplus/avicii `
  --session-dir "$Session" `
  --ota "<PATH_TO_EXACT_MATCHING_OXYGENOS_OTA>" `
  --extractor "$Extractor" `
  --extractor-platform windows-amd64 `
  --first-boot-manifest "<EXACT_FIRST_BOOT_MANIFEST_JSON>" `
  --authority-bundle "<EXACT_AUTHORITY_BUNDLE_JSON>" `
  --boot-authorization "<EXACT_TEMPORARY_BOOT_AUTHORIZATION_JSON>" `
  --boot-plan "<EXACT_BOOT_PLAN_JSON>" `
  --candidate-boot "<EXACT_CANDIDATE_BOOT_IMG>" `
  --candidate-dtbo "<EXACT_CANDIDATE_DTBO_IMG>" `
  --fastboot-executable "$Fastboot"
```

For `oneplus/avicii`, provide the exact candidate DTBO required by the reviewed boot plan.

This single command performs the already-tested host-only chain in order:

1. `extract-stock-boot-from-ota` — exact OTA → `payload.bin` → matching stock `boot.img` + provenance;
2. `bind-physical-stock-baseline` — bind captured Fastboot baseline to exact stock provenance;
3. `bind-physical-candidate-gate` — bind the reviewed candidate to that physical baseline;
4. `bind-physical-boot-identity` — re-inspect and hash the exact stock/candidate boot-chain bytes;
5. `prepare-temporary-boot-offer` — prepare the serial-bound, non-executing temporary-boot offer;
6. `build-physical-recovery-readiness` — bind exact local stock `boot.img`, A/B slot context and recovery prerequisites;
7. final stable re-hash — commit `physical-candidate-offline-preparation.json` only if every stage still matches.

It does **not** contact the phone, run ADB/Fastboot, boot/reboot, switch slots, mount storage or authorize a persistent write.

Expected outputs include:

```text
<session>/stock/payload.bin
<session>/stock/partitions/boot.img
<session>/stock/stock-provenance.json
<session>/stock/stock-extraction-report.json
<session>/physical-stock-baseline.json
<session>/physical-candidate-gate.json
<session>/physical-boot-identity.json
<session>/temporary-boot-offer.json
<session>/physical-recovery-readiness.json
<session>/physical-candidate-offline-preparation.json
```

Do not continue if any stage refuses identity, firmware, source lock, structure, hash, boot-plan or recovery state.

## 5. Review the exact temporary-boot and recovery state

Before any physical boot, review:

- `$Session\physical-candidate-offline-preparation.json`;
- `$Session\physical-candidate-gate.json`;
- `$Session\physical-boot-identity.json`;
- `$Session\temporary-boot-offer.json`;
- `$Session\physical-recovery-readiness.json`;
- `$Session\stock\partitions\boot.img` and its bound provenance.

`physical-recovery-readiness.json` must still report `ready_for_temporary_boot_safety_review=true` while slot switching, inactive-slot writes, persistent writes, rollback/recovery verification, hardware verification and Beta credit remain false.

The temporary executor requires those exact inputs again and performs a fresh read-only device/slot probe immediately before the one allowed temporary boot.

## 6. One-shot temporary boot — explicit manual action

Only when the recovery-readiness evidence has been reviewed and the candidate is exact, run the executor with the explicit opt-in. The command intentionally has no persistent write verb:

```powershell
& $Cli execute-temporary-boot-once `
  --profile-id oneplus/avicii `
  --physical-candidate-gate "$Session\physical-candidate-gate.json" `
  --boot-identity-binding "$Session\physical-boot-identity.json" `
  --physical-baseline "$Session\physical-stock-baseline.json" `
  --recovery-readiness "$Session\physical-recovery-readiness.json" `
  --stock-boot "$Session\stock\partitions\boot.img" `
  --capture-bundle "$Session\fastboot\fastboot-capture-bundle.json" `
  --baseline-evidence "$Session\fastboot\fastboot-baseline.json" `
  --fastboot-tool-evidence "$Session\fastboot\fastboot-tool.json" `
  --fastboot-executable "$Fastboot" `
  --boot-image "<EXACT_CANDIDATE_BOOT_IMG>" `
  --confirmation "AC2003" `
  --execute-temporary-boot `
  --probe-out "$Session\temporary-boot-runtime-probe.json" `
  --execution-out "$Session\temporary-boot-execution.json"
```

A Fastboot return code is not proof that Kali booted. Preserve the phone-side console/rescue transcript and continue only through the reviewed physical evidence chain.

## 7. After temporary boot

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

## 8. Final Beta preparation remains offline until the physical gate passes

After all required physical evidence is real and independently reviewed, the package exposes:

```powershell
& $Cli evidence build-beta-artifact-inventory --help
& $Cli evidence build-beta-review-manifest --help
```

Those commands create the exact local artifact inventory, review manifest and SHA-256 set. They still do not publish a GitHub release and do not grant Beta authorization by themselves.

Public Beta publication remains forbidden until every applicable item in `operator-pack/BETA_RELEASE_GATE.md` is passed for the exact physical AC2003 candidate.
