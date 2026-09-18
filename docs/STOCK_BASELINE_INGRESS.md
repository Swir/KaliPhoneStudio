# Exact Stock Baseline Ingress

KaliPhoneStudio now exposes one shared **offline** path between a physical
read-only Fastboot baseline and the exact stock firmware bytes required by the
physical gate.

This workflow does **not** query a phone, boot an image, flash a partition or
authorize a write. It exists to make the OTA → payload.bin → stock boot.img
provenance chain fail closed before any candidate or temporary-boot decision.

## Why this gate exists

Matching only file sizes is not sufficient provenance. Two different
`payload.bin` files can have the same byte length. `inspect_ota_zip()` therefore
hashes the exact embedded `payload.bin`, and stock provenance now requires the
external extracted payload to have both the same size **and the same SHA-256**.

The result binds:

- selected validated `devices/<vendor>/<codename>/profile.json`;
- complete exact OTA ZIP SHA-256 and size;
- exact embedded OTA `payload.bin` SHA-256 and size;
- external extracted `payload.bin` SHA-256 and metadata-header SHA-256;
- structurally compatible stock `boot.img` SHA-256, size and boot header;
- exact OTA firmware metadata used later to match the physical Fastboot
  firmware baseline.

## 1. Prepare immutable stock provenance

The operator must already possess the exact local OTA, the `payload.bin`
extracted from that OTA and the stock `boot.img` extracted from that payload.
This command performs no extraction tool download and no device I/O.

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

The command rejects symlink inputs, missing firmware hints, a payload whose
SHA-256 differs from the OTA member, a boot image that violates the selected
profile's boot contract, and an existing output path.

## 2. Bind to one exact physical Fastboot capture

After `capture-fastboot-baseline` has produced its canonical baseline and
capture bundle, bind those files to the stock provenance:

```powershell
KaliPhoneStudioCLI.exe bind-physical-stock-baseline `
  --profile-id oneplus/avicii `
  --baseline-evidence C:\evidence\physical\fastboot-baseline.json `
  --capture-evidence C:\evidence\physical\fastboot-capture-bundle.json `
  --stock-provenance C:\evidence\stock-provenance.json `
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

## Compatibility wrapper

The historical source helper remains available and delegates to the same
implementation:

```bash
python scripts/bind_physical_stock_baseline.py --help
python scripts/prepare_stock_provenance.py --help
```

There is no second copy of the orchestration logic.

## Beta boundary

This closes a host-side provenance gap only. The first AC2003 Beta remains
blocked until the complete `BETA_RELEASE_GATE.md` is physically satisfied,
including exact-device identity, matching stock baseline, a reviewed candidate,
successful non-persistent temporary boot, usable rescue/logging, Kali early
userspace/rootfs evidence, storage and charging safety, required functional
hardware review and exercised recovery/rollback.
