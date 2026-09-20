# Exact Stock Baseline Ingress

KaliPhoneStudio exposes one shared **offline** path between an exact local stock
OTA and the physical baseline evidence required by the Beta gate.

This workflow does **not** query a phone, boot an image, flash a partition or
authorize a write. It exists to make the OTA → payload.bin → stock boot.img
provenance chain fail closed before any candidate or temporary-boot decision.

## Recommended: extract and bind the exact stock boot in one command

The `extract-stock-boot-from-ota` command removes the old manual extraction
gap. It accepts one exact local OTA ZIP plus a **local** `payload-dumper-go`
binary that must match the reviewed SHA-256 for the selected host platform in
`tools/extractor-locks.json`.

The command never downloads an extractor. It:

1. validates the selected device profile and OTA firmware hints;
2. hashes the complete OTA and its exact embedded `payload.bin`;
3. materializes that exact payload into a private staging directory;
4. verifies the local extractor against the reviewed platform SHA-256 and
   pinned upstream source commit;
5. asks the extractor for **boot.img only**;
6. validates the resulting boot image against the profile boot contract;
7. rebuilds the complete OTA/payload/boot provenance from the produced bytes;
8. atomically publishes a create-only evidence bundle only after all checks
   pass.

Windows example:

```powershell
KaliPhoneStudioCLI.exe extract-stock-boot-from-ota `
  --profile-id oneplus/avicii `
  --ota C:\evidence\oxygenos.zip `
  --extractor C:\tools\payload-dumper-go.exe `
  --extractor-platform windows-amd64 `
  --out-dir C:\evidence\stock-bundle
```

Linux example:

```bash
python main.py extract-stock-boot-from-ota \
  --profile-id oneplus/avicii \
  --ota evidence/oxygenos.zip \
  --extractor tools/local/payload-dumper-go \
  --extractor-platform linux-amd64 \
  --out-dir evidence/stock-bundle
```

The successful output directory contains:

```text
stock-bundle/
├── payload.bin
├── partitions/
│   └── boot.img
├── stock-provenance.json
└── stock-extraction-report.json
```

`stock-extraction-report.json` records the exact OTA, payload, boot and extractor
SHA-256 identities plus the extractor source commit and host-platform lock. It
also explicitly records:

```text
phone_queried=false
phone_storage_written=false
temporary_boot_authorized=false
hardware_verified=false
beta_gate_credit=false
```

The output directory is create-only. A failed run removes its private staging
directory instead of leaving a partial bundle that could be confused with a
validated result.

## Why this gate exists

Matching only file sizes is not sufficient provenance. Two different
`payload.bin` files can have the same byte length. `inspect_ota_zip()` therefore
hashes the exact embedded `payload.bin`, and stock provenance requires the
materialized payload to have both the same size **and the same SHA-256**.

The result binds:

- selected validated `devices/<vendor>/<codename>/profile.json`;
- complete exact OTA ZIP SHA-256 and size;
- exact embedded OTA `payload.bin` SHA-256 and size;
- materialized `payload.bin` SHA-256 and metadata-header SHA-256;
- reviewed local extractor binary SHA-256, platform lock and pinned source;
- structurally compatible stock `boot.img` SHA-256, size and boot header;
- exact OTA firmware metadata used later to match the physical Fastboot
  firmware baseline.

## Manual compatibility path

If payload and boot extraction have already been performed by a separately
reviewed process, the lower-level provenance command remains available:

```powershell
KaliPhoneStudioCLI.exe prepare-stock-provenance `
  --profile-id oneplus/avicii `
  --ota C:\evidence\oxygenos.zip `
  --payload C:\evidence\payload.bin `
  --stock-boot C:\evidence\boot.img `
  --out C:\evidence\stock-provenance.json
```

Repository/Python equivalent:

```bash
python main.py prepare-stock-provenance \
  --profile-id oneplus/avicii \
  --ota evidence/oxygenos.zip \
  --payload evidence/payload.bin \
  --stock-boot evidence/boot.img \
  --out evidence/stock-provenance.json
```

This path still rejects symlink inputs, missing firmware hints, a payload whose
SHA-256 differs from the OTA member, a boot image that violates the selected
profile's boot contract, and conflicting existing provenance.

## Bind to one exact physical Fastboot capture

After `capture-fastboot-baseline` has produced its canonical baseline and
capture bundle, bind those files to the stock provenance:

```powershell
KaliPhoneStudioCLI.exe bind-physical-stock-baseline `
  --profile-id oneplus/avicii `
  --baseline-evidence C:\evidence\physical\fastboot-baseline.json `
  --capture-evidence C:\evidence\physical\fastboot-capture-bundle.json `
  --stock-provenance C:\evidence\stock-bundle\stock-provenance.json `
  --out C:\evidence\physical-baseline-bundle.json
```

The binder validates exact JSON schemas and requires the Fastboot firmware
fingerprint/build to match the exact OTA metadata. It also revalidates the
profile, serial/capture relationship and all relevant SHA-256 identities.

A successful result may report:

```text
ready_for_candidate_instantiation=true
```

but still always keeps:

```text
phone_queried=false
phone_storage_written=false
temporary_boot_authorized=false
hardware_verified=false
beta_gate_credit=false
```

`ready_for_candidate_instantiation` means only that the exact host-side inputs
are internally consistent enough for the separate candidate construction
stage. It is **not** permission to boot or flash anything.

## Compatibility wrappers

The source helpers delegate to the same implementations:

```bash
python scripts/extract_stock_boot_from_ota.py --help
python scripts/prepare_stock_provenance.py --help
python scripts/bind_physical_stock_baseline.py --help
```

There is no second copy of the orchestration logic.

## Beta boundary

This closes a host-side extraction/provenance gap only. It does **not** raise
roadmap progress by itself. The first AC2003 Beta remains blocked until the
complete `BETA_RELEASE_GATE.md` is physically satisfied, including exact-device
identity, matching physical firmware baseline, a reviewed candidate, successful
non-persistent temporary boot, usable rescue/logging, Kali early
userspace/rootfs evidence, storage and charging safety, required functional
hardware review and exercised recovery/rollback.
