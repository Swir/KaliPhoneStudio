# Windows Host Development Build

KaliPhoneStudio has a dedicated Windows **development host build** pipeline for the profile browser, Safe Operator Workspace and CLI. It is intentionally separate from the physical-device Beta gate.

The workflow produces two `onedir` applications from the same reviewed source tree:

- `KaliPhoneStudio.exe` — windowed PySide6 GUI;
- `KaliPhoneStudioCLI.exe` — console-enabled CLI for profile inspection, offline doctor, recovery guidance and deterministic diagnostics export.

These artifacts are **unsigned development builds**. They are not a Beta release, do not contain a verified Kali phone image, do not prove hardware support, and do not authorize any phone write.

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
- it keeps the frozen runtime's bundled policy/profile/status files under the PyInstaller application root, matching KaliPhoneStudio's existing offline path model;
- it is easier to audit while the Windows host surface is still under active development.

This choice is a host-packaging policy only and grants no release credit.

## Bundled policy/profile inputs

Each host build includes the exact checked-out copies of:

- `devices/` — validated multi-device profiles;
- `assets/` — KaliPhoneStudio icon/readme assets used by the application;
- `tools/` — host tool policy records;
- `BUILD_STATUS.json` — current project/status ledger;
- `BETA_RELEASE_GATE.md` — current release gate.

This allows frozen offline doctor/recovery commands to validate the same repository state that was packaged into that CI run. It does not make a profile physically supported.

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

## Frozen safety smoke tests

CI does not stop at "PyInstaller returned success". It executes the **frozen CLI executable itself** and verifies:

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

## Integrity manifest

Every successful CI package creates:

- `WINDOWS_HOST_BUILD_SHA256.txt` — SHA-256 for every file in both `onedir` trees;
- `WINDOWS_HOST_BUILD_INFO.json` — commit/toolchain/build-mode metadata plus explicit `signed=false`, `hardware_verified=false`, `beta_release=false` and `beta_gate_credit=false`.

The workflow artifact is retained briefly for development/testing. It is not uploaded to GitHub Releases and is not a substitute for the final release manifest required by `BETA_RELEASE_GATE.md`.

## Release boundary

A successful Windows build proves only that the host application was packaged and its offline safety surface survived freezing. It does **not** satisfy any physical AC2003 requirement. In particular, it does not replace exact firmware/stock-boot provenance, temporary boot, rescue logs, real hardware/storage evidence, Kali early-userspace proof, charging/power validation or exercised rollback.

Until the complete physical gate is reviewed, the authoritative state remains:

```text
hardware_verified=false
beta_gate_credit=false
Beta=BLOCKED
```
