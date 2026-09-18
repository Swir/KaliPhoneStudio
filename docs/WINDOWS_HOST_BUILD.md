# Windows Host Development Build

KaliPhoneStudio has a dedicated Windows **development host build** pipeline for the Safe Operator Workspace, profile-driven CLI, guarded physical Fastboot baseline capture, exact stock-baseline ingress and the reviewed physical-candidate -> temporary-boot operator chain. It is intentionally separate from the physical-device Beta gate.

The workflow produces two `onedir` applications from the same reviewed source tree:

- `KaliPhoneStudio.exe` — windowed PySide6 GUI. The normal GUI remains offline and does not query a phone;
- `KaliPhoneStudioCLI.exe` — console-enabled CLI for profile inspection, offline doctor, recovery guidance, deterministic diagnostics export, explicit `capture-fastboot-baseline`, exact stock/candidate binding, temporary-boot offer preparation and the guarded one-shot temporary-boot executor.

These artifacts are **unsigned development builds**. They are not a Beta release, do not contain a verified Kali phone image, do not prove hardware support, and do not authorize a persistent phone write.

## Locked build tooling

Windows packaging currently pins:

```text
PyInstaller 6.22.3
pyinstaller-hooks-contrib 2026.7
Python 3.12 in CI
```

PyInstaller 6.22.3 was published on 2026-09-12. The project deliberately stays at or above PyInstaller 6.22.1 because that release patched `GHSA-9fxf-4qw3-ghmr`; the repository pin is exact so a later package upload cannot silently change an already-reviewed build run.

References:

- https://pypi.org/project/pyinstaller/6.22.3/
- https://github.com/pyinstaller/pyinstaller/security/advisories/GHSA-9fxf-4qw3-ghmr
- https://pypi.org/project/pyinstaller-hooks-contrib/2026.7/

## Why `onedir`

The development pipeline uses `onedir`, not `onefile`:

- it keeps the application data/profile layout inspectable;
- it avoids a temporary self-extraction step during normal startup;
- it keeps the frozen runtime's bundled policy/profile/status files under the PyInstaller application root, matching KaliPhoneStudio's existing path model;
- it is easier to audit while the Windows host surface is still under active development.

This choice is a host-packaging policy only and grants no release credit.

## Bundled policy/profile inputs

Each host build includes the exact checked-out copies of:

- `devices/` — validated multi-device profiles;
- `assets/` — KaliPhoneStudio icon/readme assets used by the application;
- `tools/` — reviewed host-tool policy records, including the Fastboot policy;
- `BUILD_STATUS.json` — current project/status ledger;
- `BETA_RELEASE_GATE.md` — current release gate.

This allows frozen offline doctor/recovery commands and explicit guarded physical commands to use the same profile/policy state that was packaged into that CI run. It does not make a profile physically supported.

## Local Windows build

From PowerShell in the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r build/windows-requirements.txt
./scripts/build_windows.ps1
```

Expected outputs:

```text
dist/KaliPhoneStudio/KaliPhoneStudio.exe
dist/KaliPhoneStudioCLI/KaliPhoneStudioCLI.exe
```

The build script fails if required policy/profile inputs or either executable are missing.

## Frozen offline safety smoke tests

CI does not stop at "PyInstaller returned success". It executes the **frozen CLI executable itself** and verifies the default offline surface:

```text
--list-profiles --json
--doctor --profile-id oneplus/avicii --json
--recovery-guide --profile-id oneplus/avicii --json
--export-diagnostics ... --profile-id oneplus/avicii --json
```

The resulting JSON must still prove the offline safety boundary:

```text
physical_interaction_performed=false
persistent_write_authorized=false
hardware_verified=false
beta_gate_credit=false
```

The exported diagnostics bundle must additionally report that no external command was executed, no device was queried and no absolute executable paths were exported. The GUI executable is smoke-tested through its frozen `--version` bootstrap path so the build can fail if it cannot start at all without opening an interactive window in CI.

## Explicit guarded physical capture

Physical interaction is not hidden behind the normal GUI or doctor workflow. The operator must explicitly invoke:

```powershell
KaliPhoneStudioCLI.exe capture-fastboot-baseline --help
```

A real capture additionally requires the exact selected profile's confirmation token through `--confirm-token`. The shared capture core validates that token before inspecting or executing Fastboot and then permits only:

```text
fastboot --version
fastboot devices
fastboot -s SERIAL getvar all
```

It never performs a persistent phone write: no `boot`, `reboot`, `flash`, `erase`, `set_active` or `flashing` verb exists in the capture path. The output is an exact four-file evidence set that is staged, round-trip checked and published atomically enough for the repository's evidence contract; an error rolls back files created by that invocation.

Windows CI proves the frozen CLI contains this path by running its help text. It then invokes the command **without** `--confirm-token` and requires the frozen executable to exit with code 2 before creating an evidence directory. CI deliberately does not connect a phone and therefore grants no physical-device credit.

Full operator instructions and the evidence/privacy boundary are in [`PHYSICAL_FASTBOOT_OPERATOR_CAPTURE.md`](PHYSICAL_FASTBOOT_OPERATOR_CAPTURE.md).

## Shared physical candidate and temporary-boot chain

The next reviewed host stages are now available through the same frozen CLI instead of requiring separate repository scripts:

```powershell
KaliPhoneStudioCLI.exe bind-physical-candidate-gate --help
KaliPhoneStudioCLI.exe prepare-temporary-boot-offer --help
KaliPhoneStudioCLI.exe execute-temporary-boot-once --help
```

`bind-physical-candidate-gate` and `prepare-temporary-boot-offer` are strictly offline. They load exact typed evidence with bounded UTF-8 JSON parsing, reject schema drift and changed files, and never invoke Fastboot.

`execute-temporary-boot-once` is intentionally different: it is the only command in this chain allowed to invoke the exact serial-bound `fastboot ... boot ...` argv already authorized by the reviewed offer. It still exposes **no persistent write verb** and requires all of the following before device I/O:

1. every required evidence/file argument;
2. the profile-specific `--confirmation` text;
3. a separate explicit `--execute-temporary-boot` opt-in;
4. distinct, unused runtime-probe and execution-evidence output paths whose parent directories pass a host writeability preflight;
5. exact reviewed Fastboot executable and boot-image bytes;
6. a fresh read-only serial-bound Fastboot probe matching the reviewed baseline.

The output-path preflight happens before any physical Fastboot call. This closes an operator failure mode where a one-shot temporary boot could otherwise execute and only afterwards discover that the requested audit-evidence path was already occupied or trivially unwritable.

A successful Fastboot return code is **not** hardware verification. The execution evidence explicitly keeps:

```text
persistent_write=false
phone_storage_written=false
kali_userspace_verified=false
hardware_verified=false
beta_gate_credit=false
```

Windows CI smoke-tests all three frozen command help surfaces, proves missing-evidence candidate/offer commands fail closed without creating outputs, and proves the temporary executor exits with code 2 **before evidence loading or device probing** when `--execute-temporary-boot` is absent. CI never supplies the opt-in and never connects a phone.

See [`PHYSICAL_CANDIDATE_OPERATOR.md`](PHYSICAL_CANDIDATE_OPERATOR.md) for the exact operator sequence and evidence boundaries.

## Integrity manifest

Every successful CI package creates:

- `WINDOWS_HOST_BUILD_SHA256.txt` — SHA-256 for every file in both `onedir` trees;
- `WINDOWS_HOST_BUILD_INFO.json` — commit/toolchain/build-mode metadata plus explicit `signed=false`, `hardware_verified=false`, `beta_release=false` and `beta_gate_credit=false`.

The workflow artifact is retained briefly for development/testing. It is not uploaded to GitHub Releases and is not a substitute for the final release manifest required by `BETA_RELEASE_GATE.md`.

## Release boundary

A successful Windows build proves only that the host application was packaged and its safety boundaries survived freezing. A successful read-only baseline capture proves only the exact captured baseline/tool/transcript provenance. Successful offline candidate/offer binding proves only exact host evidence consistency. Even a successful one-shot `fastboot boot` command proves only that Fastboot accepted that exact temporary command; it does not prove the kernel reached Kali userspace or that hardware is functional.

These host results do not replace matching stock `boot.img` provenance, phone-side temporary-boot observation, usable rescue logs, real hardware/storage evidence, Kali early-userspace proof, charging/power validation or exercised rollback.

Until the complete physical gate is reviewed, the authoritative state remains:

```text
hardware_verified=false
beta_gate_credit=false
Beta=BLOCKED
```
