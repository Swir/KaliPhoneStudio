# Rootfs handoff local-artifact trial preflight

`rootfs-handoff-local-rootfs-preflight-v1` is an offline fail-closed boundary between an accepted non-executing rootfs trial plan and any future interactive execution code.

It proves exactly one additional fact: **the local Kali rootfs artifact available to the operator still has the exact SHA-256 and byte size recorded in the accepted trial plan**.

It does **not** contact a phone, run ADB/Fastboot, discover or bind a raw block-device path, choose a mount target, mount storage, copy files, execute a trial, authorize a persistent write, or grant storage/recovery/hardware/Beta credit.

## Required inputs

- the exact canonical `rootfs-handoff-interactive-trial-plan-v1` JSON;
- the local rootfs artifact that the plan identifies by SHA-256 and exact byte size.

The preflight revalidates the complete safety posture of the supplied plan before hashing the artifact. A plan that already carries execution/write/hardware/Beta authorization is rejected.

The rootfs artifact must be a regular non-symlink file. It is opened read-only through the shared descriptor-bound local-file verifier, using `O_NOFOLLOW` where available. The initial path identity must match the opened descriptor; hashing reads only that descriptor; descriptor metadata is checked again after hashing; and a final path lookup must still identify the same regular file. Symlink use, path replacement, truncation, growth, size drift or in-place metadata drift fails closed. The exact plan size is enforced before any successful digest is accepted.

## CLI

```bash
python main.py evidence build-rootfs-handoff-trial-preflight \
  --trial-plan evidence/rootfs-handoff-trial-plan.json \
  --rootfs-artifact build/kali-rootfs-arm64.tar.xz \
  --out evidence/rootfs-handoff-trial-preflight.json
```

Machine-readable output is available with `--json` before the subcommand:

```bash
python main.py evidence --json build-rootfs-handoff-trial-preflight \
  --trial-plan evidence/rootfs-handoff-trial-plan.json \
  --rootfs-artifact build/kali-rootfs-arm64.tar.xz \
  --out evidence/rootfs-handoff-trial-preflight.json
```

Outputs are create-only; an existing or symlink output is never overwritten.

## What success means

Successful evidence records:

- `exact_trial_plan_bound=true`;
- `local_rootfs_exact_bytes_verified=true`;
- the exact trial-plan / authorization / target-binding / fresh-revalidation identities;
- the exact local rootfs SHA-256 and byte size;
- `live_device_identity_recheck_required=true`;
- `live_firmware_recheck_required=true`;
- `live_target_identity_recheck_required=true`;
- `live_filesystem_encryption_capacity_recheck_required=true`;
- `recovery_readiness_recheck_required=true`;
- `explicit_operator_confirmation_required=true`;
- `write_scope_confirmation_required=true`;
- `interactive_executor_still_required=true`;
- `physical_gate_still_incomplete=true`.

The following stay false even after a successful preflight:

- `physical_interaction_performed`;
- `external_device_command_executed`;
- `raw_device_path_bound`;
- `mount_target_bound`;
- `trial_execution_allowed`;
- `persistent_write_authorized`;
- `persistent_write_performed`;
- `phone_storage_written`;
- `storage_verified`;
- `recovery_verified`;
- `hardware_verified`;
- `beta_release_authorized`;
- `beta_gate_credit`.

## Remaining execution boundary

This preflight intentionally does not implement the write-capable rootfs trial. A future interactive executor must still reacquire the live phone state and prove it matches the reviewed profile, serial, firmware, logical target identity, filesystem/encryption/capacity and recovery context. It must require explicit operator interaction immediately before any write-capable action.

For the first `oneplus/avicii` profile, those live requirements remain blocked until the physical OnePlus Nord AC2003 campaign supplies the exact baseline, matching stock `boot.img`, reviewed recovery readiness, successful recovery-gated temporary boot, real storage evidence and the remaining hardware/recovery release-gate evidence.

## CI contract

Focused Python 3.11/3.14 CI verifies canonical/create-only evidence, descriptor-bound exact local artifact matching, symlink/path-replacement refusal, plan-safety refusal and unified CLI routing. The shared local-file verifier is separately exercised on Linux and Windows by the recovery-readiness matrix; the frozen Windows CLI gate also verifies that the preflight command is present and that missing inputs fail closed without creating output.
