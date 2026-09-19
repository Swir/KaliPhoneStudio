# Rootfs handoff interactive trial plan

The `rootfs-handoff-interactive-trial-plan-v1` evidence layer is the last **offline, non-executing** planning step after an accepted manual rootfs trial authorization. It exists to make the later physical execution boundary explicit and auditable without silently turning host-side review into permission to write to a phone.

## Inputs

The builder consumes three exact canonical evidence files:

- the accepted rootfs handoff trial authorization;
- the target binding referenced by that authorization;
- the distinct fresh-device revalidation referenced by that authorization.

All three identities are rebound by SHA-256 and their profile, serial, firmware, logical target, filesystem, encryption/capacity, rootfs artifact, staging subpath and recovery-plan fields must agree. Detached or drifted evidence fails closed.

## What the plan records

A valid plan records the exact evidence chain plus mandatory requirements for a **future interactive executor**:

- reacquire live device identity;
- reacquire firmware build/fingerprint;
- reacquire logical target identity;
- recheck filesystem, encryption state and free capacity;
- re-hash the local rootfs artifact;
- recheck recovery readiness;
- require explicit operator confirmation;
- require a separate write-scope confirmation.

The plan intentionally carries **no raw block-device path and no mount target**.

## What it does not authorize

Building a plan does not connect to a phone, call `adb` or `fastboot`, mount storage, copy a rootfs, write a partition, mark storage/recovery/hardware verified, or grant Beta gate credit. The following fields remain false by contract:

- `trial_execution_allowed`;
- `persistent_write_authorized`;
- `persistent_write_performed`;
- `phone_storage_written`;
- `storage_verified`;
- `recovery_verified`;
- `hardware_verified`;
- `beta_release_authorized`;
- `beta_gate_credit`.

`plan_ready_for_later_interactive_executor=true` means only that the offline evidence chain is internally consistent enough to be presented to a later, separately reviewed interactive executor. It is not permission to execute.

## CLI

```bash
python -m kaliphonestudio.operator_evidence_workspace \
  build-rootfs-handoff-trial-plan \
  --trial-authorization evidence/rootfs/trial-authorization.json \
  --target-binding evidence/rootfs/target-binding.json \
  --fresh-revalidation evidence/rootfs/fresh-revalidation.json \
  --out evidence/rootfs/trial-plan.json
```

Use `--json` before the command for machine-readable output. Outputs are create-only and canonical JSON.

## Physical gate

For `oneplus/avicii`, Beta remains blocked until the real AC2003 satisfies `BETA_RELEASE_GATE.md`, including exact firmware baseline, matching stock `boot.img`, recovery readiness, temporary boot, Kali early userspace/rootfs, safe storage/power observations and the remaining hardware evidence. This host-side plan receives no hardware credit.
