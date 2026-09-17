# Physical rescue proof acquisition

KaliPhoneStudio does **not** treat a successful `fastboot boot` return code as proof that the candidate kernel or rescue userspace actually ran on the phone. The physical proof path is intentionally split into immutable evidence layers, and read-only hardware inventory/functional signals are kept separate from verification verdicts.

## Exact rescue identity

Every schema-v2 `RescueCandidateEvidence` contains a deterministic `rescue_probe_id`, SHA-256-bound to the exact device profile, reproducible rescue payload evidence, staged payload evidence and locked `/init` bytes. The ID is embedded inside the deterministic rescue initramfs at:

```text
/etc/kaliphonestudio/rescue-probe-id
```

When that exact rescue `/init` executes, it emits:

```text
KPS_RESCUE_STAGE=init-reached-v1
KPS_RESCUE_PROBE_ID=<64-lowercase-hex-id>
```

Network and SSH remain disabled. Persistent storage is not mounted automatically.

## Layer 1 — physical boot observation

The offline observation recorder accepts only:

1. a successful schema-v1 `TemporaryBootExecutionEvidence` from the guarded one-command temporary-boot path;
2. the exact schema-v2 `RescueCandidateEvidence` containing the expected probe ID;
3. the selected device profile;
4. a raw operator-captured console/log transcript.

It requires the exact stage marker and exact candidate probe ID, rejects conflicting marker values, hashes raw transcript bytes and emits `PhysicalBootObservationEvidence` bound to the prior execution and rescue candidate.

```bash
python scripts/record_physical_boot_observation.py \
  --profile-id oneplus/avicii \
  --execution-evidence evidence/temporary-boot-execution.json \
  --rescue-evidence evidence/rescue-candidate.json \
  --console-transcript evidence/physical-console.log \
  --out evidence/physical-boot-observation.json
```

This command does **not** invoke Fastboot, ADB, serial tools or any phone operation.

## Layer 2 — automatic read-only rescue hardware signals

After the exact rescue markers, `/init` emits one bounded diagnostic block:

```text
KPS_DIAG_BEGIN=readonly-sysfs-inventory-v1
KPS_DIAG_BLOCK=<name>|<size-sectors>|<removable>
KPS_DIAG_SCSI_HOST=<host>|<proc-name>
KPS_DIAG_POWER=<name>|<type>|<status>|<capacity>|<online>|<voltage>|<current>|<temp>
KPS_DIAG_INPUT=<event>|<name>
KPS_DIAG_GRAPHICS=<fb>|<name>
KPS_DIAG_DRM=<connector>|<status>
KPS_DIAG_END=readonly-sysfs-inventory-v1
```

The inventory reads only sysfs/procfs. It does not mount or repair persistent storage, decrypt data, write block devices, modify charging controls, initialize display, open input event devices, execute Fastboot, or enable network/SSH. Each category is capped at 64 records. Machine-readable values are reduced to bounded ASCII tokens before output.

The second offline recorder requires the already-created physical boot observation plus the **same raw transcript**:

```bash
python scripts/record_physical_rescue_diagnostics.py \
  --profile-id oneplus/avicii \
  --observation-evidence evidence/physical-boot-observation.json \
  --console-transcript evidence/physical-console.log \
  --out evidence/physical-rescue-diagnostics.json
```

It rehashes the transcript and requires exact SHA-256/size equality with `PhysicalBootObservationEvidence`, exactly one diagnostic BEGIN/END block after the exact rescue markers, bounded known record types and safe field syntax. Duplicate blocks, diagnostic lines outside the block, unknown record kinds, malformed fields, profile mismatch or claim tampering fail closed.

The result may contain raw signal flags:

```text
ufs_signal_observed=true|false
battery_signal_observed=true|false
input_signal_observed=true|false
graphics_signal_observed=true|false
```

These mean **only** that the corresponding read-only sysfs signal appeared in the exact transcript. For example, an `ufshcd` SCSI host suggests that the kernel exposed a UFS-related host, but it does not prove safe block I/O, filesystem integrity, mountability or persistence. Likewise power telemetry does not prove safe charging, and framebuffer/DRM/input enumeration does not prove a usable display/touch setup.

## Layer 3 — explicit bounded read-only functional probes (0.6.53)

The locked rescue `/init` generates `/run/kps-readonly-probe` inside initramfs RAM. It is **not run automatically**. From the already reached local rescue shell, the operator must explicitly type:

```text
/run/kps-readonly-probe --confirm-read-only
```

Without the exact argument, the helper exits without performing the raw block-read/battery probe. With explicit authorization it emits exactly one bounded block:

```text
KPS_PROBE_BEGIN=readonly-functional-probes-v1
KPS_PROBE_BLOCK_READ=<device>|4096|<ok|fail|missing>
KPS_PROBE_BATTERY_SAMPLE=<name>|<1|2>|<status>|<health>|<capacity>|<voltage>|<current>|<temp>
KPS_PROBE_END=readonly-functional-probes-v1
```

Safety limits are deliberate: loop/ram/zram/dm/md devices are skipped; only non-removable whole block devices are considered; at most eight are sampled; exactly one 4096-byte read per candidate goes to `/dev/null`; block contents are never printed or hashed. Battery data is read from sysfs for at most eight supplies and sampled twice one second apart. The helper never mounts, formats, repairs, decrypts, writes a block device, changes charging policy, enables network/SSH or invokes Fastboot.

The third offline recorder binds these records to both previous layers and the exact same transcript:

```bash
python scripts/record_physical_rescue_functional_probes.py \
  --profile-id oneplus/avicii \
  --physical-observation evidence/physical-boot-observation.json \
  --rescue-diagnostics evidence/physical-rescue-diagnostics.json \
  --console-transcript evidence/physical-console.log \
  --out evidence/physical-rescue-functional-probes.json
```

It rejects transcript substitution, a diagnostics record detached from the supplied observation, duplicate/out-of-block probe markers, malformed read byte counts/outcomes, invalid battery sample sequence values, unsafe fields and hardware/Beta claim tampering. Accepted evidence may report:

```text
storage_read_signal_observed=true|false
battery_sampling_signal_observed=true|false
```

A successful 4096-byte read is stronger evidence than enumeration, but it still does not prove filesystem integrity, complete UFS behavior, sustained I/O or persistence. A paired battery sample proves only that bounded telemetry could be read at two instants; it does not prove charging safety or thermal behavior.

## What the evidence still does not prove

All three layers deliberately keep the physical release claims false until separate physical review and functional tests exist:

```text
explicit_local_authorization_required=true   # functional-probe layer
manual_review_required=true
kali_early_userspace_verified=false
storage_verified=false
display_touch_verified=false
charging_battery_verified=false
recovery_verified=false
phone_storage_written=false
hardware_verified=false
beta_gate_credit=false
```

A matching rescue observation plus automatic inventory plus a successful bounded read-only probe therefore does not by itself satisfy the Beta rescue/log, Kali rootfs, UFS/storage, display/touch, charging, suspend, modem, audio or recovery gates.

## Capture integrity rules

- Keep the original raw transcript; do not edit or normalize it before recording.
- Raw bytes are SHA-256-bound before newline normalization used for marker parsing.
- The transcript must be a bounded regular non-symlink file and is re-statted after reading to detect TOCTOU changes.
- Conflicting rescue markers, duplicate diagnostics/probe blocks or machine-readable records outside the exact block cause fail-closed rejection.
- Unrelated non-ASCII console noise is ignored; every machine-readable `KPS_DIAG_*` and `KPS_PROBE_*` record itself must be strict bounded ASCII.
- Functional-probe evidence must bind the exact prior observation and exact prior read-only diagnostics digests, not merely matching profile strings.
- Evidence files are write-once by default; existing output paths are not overwritten.

## Safety boundary

The observation, diagnostics and functional-probe recorders are intentionally separate from the executor. They cannot flash, erase, set an A/B slot, reboot, mount phone storage or promote an observation to Beta readiness. The optional rescue helper itself is local-only, explicit, bounded and read-only; persistent-write support remains outside this path.
