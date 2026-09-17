# Physical rescue proof acquisition

KaliPhoneStudio does **not** treat a successful `fastboot boot` return code as proof that the candidate kernel or rescue userspace actually ran on the phone. The physical proof path is intentionally split into separate immutable evidence layers.

## What 0.6.51 adds

Every schema-v2 `RescueCandidateEvidence` contains a deterministic `rescue_probe_id`. The ID is SHA-256-bound to the exact device profile, reproducible rescue payload evidence, staged payload evidence and locked `/init` bytes. The exact ID is embedded as a read-only file inside the deterministic rescue initramfs:

```text
/etc/kaliphonestudio/rescue-probe-id
```

When that exact rescue `/init` executes, it emits two machine-readable lines to the local console and, when available, `/dev/kmsg`:

```text
KPS_RESCUE_STAGE=init-reached-v1
KPS_RESCUE_PROBE_ID=<64-lowercase-hex-id>
```

Network and SSH remain disabled. Persistent storage is not mounted automatically.

## Evidence chain

The offline observation recorder accepts only:

1. a successful schema-v1 `TemporaryBootExecutionEvidence` from the one-command guarded temporary-boot path;
2. the exact schema-v2 `RescueCandidateEvidence` containing the expected probe ID;
3. the selected device profile;
4. a raw operator-captured console/log transcript.

It requires the transcript to contain the **exact** stage marker and exact candidate probe ID, rejects conflicting marker values, hashes the raw transcript byte-for-byte and emits `PhysicalBootObservationEvidence` bound to the prior execution and rescue candidate.

Example offline recording step after the operator has separately captured a console log:

```bash
python scripts/record_physical_boot_observation.py \
  --profile-id oneplus/avicii \
  --execution-evidence evidence/temporary-boot-execution.json \
  --rescue-evidence evidence/rescue-candidate.json \
  --console-transcript evidence/physical-console.log \
  --out evidence/physical-boot-observation.json
```

This command does **not** invoke Fastboot, ADB, serial tools or any phone operation.

## What the record proves — and what it does not

A matching record is useful evidence that the exact probe-bearing rescue `/init` appeared in the captured physical log after the exact recorded temporary-boot command. It remains deliberately marked:

```text
manual_review_required=true
kali_early_userspace_verified=false
storage_verified=false
display_touch_verified=false
charging_battery_verified=false
recovery_verified=false
hardware_verified=false
beta_gate_credit=false
```

The record therefore does not by itself satisfy the Beta rescue/log checkbox, and it does not prove the Kali rootfs, UFS, display/touch, charging, suspend, modem, audio or recovery path. Those require separate physical-device evidence and review.

## Capture integrity rules

- Keep the original raw transcript; do not edit or normalize it before recording.
- The recorder hashes raw bytes before any newline normalization used for marker matching.
- The transcript must be a bounded regular non-symlink file and is re-statted after reading to detect TOCTOU changes.
- Conflicting `KPS_RESCUE_STAGE=` or `KPS_RESCUE_PROBE_ID=` lines cause fail-closed rejection.
- Repeated markers are bounded to prevent implausible/replayed transcript input from being silently accepted.
- Evidence files are write-once by default; existing output paths are not overwritten.

## Safety boundary

The physical proof recorder is intentionally separate from the executor. It cannot flash, erase, set an A/B slot, reboot, mount phone storage or promote an observation to Beta readiness. Persistent-write support remains outside this path.
