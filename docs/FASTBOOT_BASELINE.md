# Fastboot baseline evidence

KaliPhoneStudio treats the first physical-device observation as **evidence**, not permission to flash. The baseline workflow is intentionally read-only and separate from temporary boot or persistent writes.

## Evidence chain

The guarded capture produces four immutable outputs:

1. raw `fastboot getvar all` transcript bytes,
2. canonical parsed baseline evidence,
3. canonical reviewed Fastboot-tool identity evidence,
4. a `FastbootCaptureBundleEvidence` record that cryptographically joins the first three.

The capture bundle binds profile, serial, product, firmware build/fingerprint, transcript SHA-256/size, baseline evidence digest, exact Fastboot executable SHA-256/size, exact Platform-Tools policy/version and the fixed read-only command policy. It records `read_only=true`, `phone_storage_written=false`, `hardware_verified=false` and `beta_gate_credit=false`.

This prevents a later workflow from combining a valid baseline transcript with unrelated Fastboot tool evidence.

## Reviewed Fastboot tool policy

The guarded path is fail-closed against `tools/fastboot-tool-policy.json`. The current reviewed policy pins **Android SDK Platform-Tools 37.0.1** and the official Android Developers release-notes source.

The helper resolves the Fastboot executable once, rejects symlinks, hashes the exact regular-file bytes, records its size, runs only `fastboot --version`, validates the reported version against the exact policy, and records the version-output SHA-256. The same resolved binary is then used for device discovery and baseline capture.

Tool evidence remains host provenance only and never grants hardware/Beta credit.

## Guarded read-only capture

The helper executes only:

```text
fastboot --version
fastboot devices
fastboot -s SERIAL getvar all
```

Only the last two communicate with the phone. The helper never invokes `boot`, `reboot`, `flash`, `erase`, `set_active`, `flashing` or any other state-changing verb. The requested serial must first appear in `fastboot devices`; `serialno` returned by `getvar all` must match the same serial.

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
  --tool-evidence-out evidence/fastboot-tool.json `
  --capture-evidence-out evidence/fastboot-capture-bundle.json
```

All four outputs must be distinct and absent before capture. They are staged, cross-checked and round-tripped before publication; partial final publication is rolled back.

The capture is still only an operator-initiated read. It does **not** authorize temporary boot or any persistent write.

## Baseline contract

For `oneplus/avicii`, profile schema v2 currently requires `product`, `serialno`, `current-slot`, `slot-count`, `unlocked`, `secure`, `version-bootloader`, and `version-baseband`. The parser rejects missing required variables, conflicting duplicates, failed-command transcripts, invalid A/B state, unexpected slot count, malformed booleans, unsafe control data and an identity that does not match the selected profile.

The raw transcript is hashed byte-for-byte. Do not edit it after capture. It may contain a device serial and other identifying data, so keep raw physical evidence private unless identifiers have been intentionally handled for publication.

## Manual capture alternative

A separately captured transcript can still be imported offline with `scripts/import_fastboot_baseline.py`, but manual capture does **not** automatically prove the exact Fastboot executable used. Such evidence therefore lacks the stronger joined capture provenance created by the guarded helper.

## Exact OTA / stock `boot.img` binding

A captured baseline is not enough to prepare a first-boot candidate. The exact physical firmware must be joined to exact stock provenance:

- baseline firmware fingerprint must equal OTA metadata `post-build`,
- `post-build-incremental`, when present, must equal the recorded firmware build,
- the stock provenance must bind exact OTA bytes, payload bytes/metadata and extracted `boot.img` bytes,
- the physical capture bundle must remain attached to the same baseline digest, transcript and serial.

Use the offline binder after exact OTA/payload/stock-boot provenance exists:

```powershell
python scripts/bind_physical_stock_baseline.py `
  --profile-id oneplus/avicii `
  --baseline-evidence evidence/fastboot-baseline.json `
  --capture-evidence evidence/fastboot-capture-bundle.json `
  --stock-provenance evidence/stock-boot-provenance.json `
  --out evidence/physical-baseline-bundle.json
```

`PhysicalBaselineBundleEvidence` records the exact capture digest, baseline/transcript digests, OTA/payload/stock-boot digests and sizes, stock boot header version and a canonical firmware-metadata digest. A successful bundle states `ready_for_candidate_instantiation=true` but deliberately keeps `temporary_boot_authorized=false`, `hardware_verified=false` and `beta_gate_credit=false`.

## OTA metadata hardening

OTA firmware metadata is treated as security/provenance input. Parsing is strict and bounded: UTF-8 only, no NUL/control data, bounded size/count/key/value lengths, no duplicate keys, no ambiguous duplicate metadata members, no unsafe ZIP paths, and no malformed non-comment metadata lines. The OTA file is re-statted after hashing to catch mutation during inspection.

## Beta boundary

Even a valid physical baseline bundle is only the ingress to the physical-firmware candidate pipeline. Beta still requires a matching assembled candidate, explicitly authorized temporary boot, real rescue/log access, Kali early userspace, UFS/storage, display/touch or a documented console-only scope, safe charging/battery behavior and exercised recovery/rollback.
