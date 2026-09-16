# Fastboot baseline evidence

KaliPhoneStudio treats the first physical-device observation as **evidence**, not as permission to flash. The baseline workflow is intentionally read-only and separate from temporary boot or persistent writes.

## Purpose

A baseline binds one device profile to:

- the exact `fastboot getvar all` transcript bytes and SHA-256,
- the device product and serial returned by the bootloader,
- A/B slot state and slot count where the profile requires them,
- bootloader lock/security state,
- bootloader/baseband version strings required by the profile,
- an operator-recorded exact firmware build and Android build fingerprint.

The generated JSON sets `beta_gate_credit` to `false`. Importing a transcript therefore cannot by itself satisfy a physical Beta gate.

## Capture

Use an official/current Android platform-tools `fastboot` binary. Capture the output before destructive work and preserve the original file unchanged. `fastboot getvar all` normally writes its variables to stderr, so capture both streams.

PowerShell:

```powershell
fastboot devices
fastboot getvar all 2>&1 | Tee-Object -FilePath fastboot-getvar-all.txt
```

POSIX shell:

```sh
fastboot devices
fastboot getvar all >fastboot-getvar-all.txt 2>&1
```

Do not edit the transcript after capture. It may contain a device serial and other identifying data, so keep the raw transcript and generated evidence private unless identifiers have been intentionally handled for publication.

## Import

The importer never invokes `adb` or `fastboot` and never writes to a phone:

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
