# Fastboot baseline evidence

KaliPhoneStudio treats the first physical-device observation as **evidence**, not as permission to flash. The baseline workflow is intentionally read-only and separate from temporary boot or persistent writes.

## Purpose

A baseline binds one device profile to:

- the exact `fastboot getvar all` transcript bytes and SHA-256,
- the device product and serial returned by the bootloader,
- A/B slot state and slot count where the profile requires them,
- bootloader lock/security state,
- bootloader/baseband version strings required by the profile,
- an operator-recorded exact firmware build and Android build fingerprint,
- companion evidence for the exact Fastboot executable bytes and reviewed Platform-Tools version used for capture.

The generated JSON records set `beta_gate_credit` to `false`. Capturing or importing a transcript therefore cannot by itself satisfy a physical Beta gate.

## Reviewed Fastboot tool policy

The guarded capture path is fail-closed against `tools/fastboot-tool-policy.json`. The current reviewed policy pins **Android SDK Platform-Tools 37.0.1 (July 2026)** and the official Android Developers release-notes URL. Android's release notes identify 37.0.1 as the current stable Platform-Tools revision in this project baseline and state that recent `adb`/`fastboot` versions are intended to remain backward compatible.

The capture helper resolves the executable once, rejects symlinks, hashes the exact regular-file bytes, records its size, runs only `fastboot --version`, checks the first version line against the exact reviewed policy, and records the complete version-output SHA-256. The same resolved binary path is then used for the device-list and `getvar all` reads. This prevents a different `fastboot` found later on `PATH` from silently performing the capture.

The tool evidence is host provenance only: `hardware_verified=false` and `beta_gate_credit=false`.

## Guarded read-only capture

The helper executes only these three non-writing commands:

```text
fastboot --version
fastboot devices
fastboot -s SERIAL getvar all
```

Only the last two communicate with the phone. It never invokes `boot`, `reboot`, `flash`, `erase`, `set_active`, `flashing` or any other phone-storage/state-changing verb. The requested serial must first appear in `fastboot devices`, and the `serialno` returned inside `getvar all` must match the same exact serial before evidence is published.

PowerShell example:

```powershell
python scripts/capture_fastboot_baseline.py `
  --profile-id oneplus/avicii `
  --serial "EXACT_FASTBOOT_SERIAL" `
  --firmware-build "EXACT_BUILD" `
  --firmware-fingerprint "EXACT_ANDROID_BUILD_FINGERPRINT" `
  --fastboot "C:\path\to\platform-tools\fastboot.exe" `
  --transcript-out evidence/fastboot-getvar-all.txt `
  --evidence-out evidence/fastboot-baseline.json `
  --tool-evidence-out evidence/fastboot-tool.json
```

`--fastboot-policy` defaults to the checked repository policy. The helper runs subprocesses as fixed argv arrays with `shell=False`, disables stdin, bounds output and timeouts, rejects malformed output and serial option injection, and refuses to overwrite existing transcript/evidence paths. Raw transcript, canonical baseline evidence and canonical tool evidence are all staged and validated before any requested output is published; a partial final publication is rolled back.

This is still an operator-initiated physical read operation. It does **not** authorize temporary boot or persistent writes.

## Manual capture alternative

If the guarded helper is not available, preserve the original output unchanged. `fastboot getvar all` normally writes its variables to stderr, so capture both streams.

PowerShell:

```powershell
fastboot --version
fastboot devices
fastboot -s EXACT_FASTBOOT_SERIAL getvar all 2>&1 | Tee-Object -FilePath fastboot-getvar-all.txt
```

POSIX shell:

```sh
fastboot --version
fastboot devices
fastboot -s EXACT_FASTBOOT_SERIAL getvar all >fastboot-getvar-all.txt 2>&1
```

Manual capture does not automatically create the exact Fastboot tool identity evidence produced by the guarded helper. Do not edit the transcript after capture. It may contain a device serial and other identifying data, so keep raw transcript/evidence private unless identifiers have been intentionally handled for publication.

## Offline import

The existing importer remains available when a transcript was captured separately. It never invokes `adb` or `fastboot` and never writes to a phone:

```powershell
python scripts/import_fastboot_baseline.py `
  --profile-id oneplus/avicii `
  --transcript fastboot-getvar-all.txt `
  --firmware-build "EXACT_BUILD" `
  --firmware-fingerprint "EXACT_ANDROID_BUILD_FINGERPRINT" `
  --out evidence/fastboot-baseline.json
```

For `oneplus/avicii`, profile schema v2 requires `product`, `serialno`, `current-slot`, `slot-count`, `unlocked`, `secure`, `version-bootloader`, and `version-baseband`. The parser rejects missing required variables, conflicting duplicates, failed-command transcripts, invalid A/B state, unexpected slot count, malformed booleans, unsafe control data and a product that does not identify the selected profile.

## OTA/provenance binding

Before a candidate can receive `TemporaryBootAuthorization`, KaliPhoneStudio requires the baseline to match the same profile/serial and the exact stock OTA provenance. The baseline fingerprint must equal the OTA metadata `post-build`; if `post-build-incremental` exists, it must equal the recorded firmware build. This closes the gap where a structurally valid boot image from a different firmware baseline could otherwise reach the temporary-boot authorization boundary.

A successful authorization is still **host-side safety evidence only**. Physical temporary boot, rescue/logging, early Kali userspace, storage, charging/battery behavior and recovery remain separate Beta gates.
