# Guarded Physical Fastboot Baseline Capture

KaliPhoneStudio has one shared operator-facing implementation for the first real physical-device evidence step: `kaliphonestudio.physical_fastboot_capture`.

This path **queries a physical phone**, so it is intentionally not part of the GUI's default offline mode. It is nevertheless read-only: it can only verify the reviewed Fastboot binary, list Fastboot devices and capture `getvar all` from one exact serial. It contains no boot, reboot, flash, erase, slot-change or phone-storage write operation.

A successful capture is **evidence input only**. It does not prove that Kali boots, does not verify hardware support, and grants no Beta credit.

## Safety boundary

Before any external command is executed, the capture layer requires:

- one validated device profile;
- the exact profile-specific confirmation token;
- one exact Fastboot serial;
- an exact firmware build string and firmware fingerprint supplied by the operator;
- four distinct, non-existing output/staging paths with no symlinked output directory;
- the reviewed `tools/fastboot-tool-policy.json` policy.

The confirmation token is profile-driven. The generic capture core never hard-codes `AC2003` or any other model token.

The only command shapes reachable through this workflow are:

```text
fastboot --version
fastboot devices
fastboot -s SERIAL getvar all
```

`--version` verifies the host tool. `devices` and `getvar all` are the only phone queries. The exact resolved Fastboot executable inspected by the tool-provenance layer is reused for the capture.

## Windows CLI

The packaged console host exposes the guarded path as an explicit subcommand:

```powershell
KaliPhoneStudioCLI.exe capture-fastboot-baseline `
  --profile-id oneplus/avicii `
  --serial <EXACT_FASTBOOT_SERIAL> `
  --firmware-build <EXACT_OXYGENOS_BUILD> `
  --firmware-fingerprint <EXACT_FIRMWARE_FINGERPRINT> `
  --confirm-token AC2003 `
  --output-dir evidence\physical-baseline
```

`AC2003` above is only the current `oneplus/avicii` profile example. Every future device profile supplies its own confirmation token.

The normal `KaliPhoneStudio.exe` GUI remains offline. Double-clicking it does not query a device.

## Python / repository CLI

The same implementation can be reached without Windows packaging:

```bash
python main.py capture-fastboot-baseline \
  --profile-id oneplus/avicii \
  --serial '<EXACT_FASTBOOT_SERIAL>' \
  --firmware-build '<EXACT_OXYGENOS_BUILD>' \
  --firmware-fingerprint '<EXACT_FIRMWARE_FINGERPRINT>' \
  --confirm-token AC2003 \
  --output-dir evidence/physical-baseline
```

The historical helper remains as a compatibility wrapper and delegates to the same core instead of carrying a second copy of the orchestration logic:

```bash
python scripts/capture_fastboot_baseline.py --help
```

For existing automation, the wrapper still accepts the four explicit output options (`--transcript-out`, `--evidence-out`, `--tool-evidence-out`, `--capture-evidence-out`) when all four are provided. `--output-dir` and explicit output paths cannot be mixed.

## Evidence set

With `--output-dir DIR`, the capture publishes exactly these files only after the complete staged set validates:

```text
DIR/fastboot-getvar-all.txt
DIR/fastboot-baseline.json
DIR/fastboot-tool.json
DIR/fastboot-capture-bundle.json
```

The bundle binds the exact raw transcript to the parsed baseline and exact Fastboot tool evidence. The result reports SHA-256 identities and explicitly keeps:

```text
read_only=true
phone_storage_written=false
persistent_write_authorized=false
hardware_verified=false
beta_gate_credit=false
```

If the captured `serialno` differs from the requested serial, an evidence round-trip fails, a destination appears during staging, or any evidence writer fails, the run fails closed. Any finals published by that invocation are rolled back and staging files are removed.

## Privacy

The raw transcript and baseline evidence can contain a device serial, firmware identifiers and other bootloader metadata. Treat a real physical capture as private engineering evidence. Do not attach it to a public issue or release without reviewing/redacting what is appropriate; redacted diagnostics are a separate operator feature and must not be substituted for the exact private evidence used by the physical gate.

## Beta boundary

This capture only prepares the first exact physical baseline input. The Beta gate still requires matching stock `boot.img` provenance, an exact candidate, successful temporary boot with phone-side evidence, usable rescue/logging, reviewed storage/hardware evidence, Kali early-userspace/rootfs proof, safe charging/power behavior and exercised recovery/rollback. See `BETA_RELEASE_GATE.md` for the authoritative release conditions.
