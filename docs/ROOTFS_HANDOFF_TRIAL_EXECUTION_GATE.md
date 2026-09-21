# Rootfs handoff interactive execution gate

`rootfs-handoff-interactive-execution-gate-v1` is the final **non-writing evidence boundary** immediately before a future interactive rootfs writer.

It exists to prevent an accepted rootfs trial from being executed against stale storage state. The earlier manual authorization and local-rootfs preflight remain necessary, but they are not enough: immediately before any writer is considered, KaliPhoneStudio requires another independently captured read-only storage discovery/report chain from the same physical phone and firmware.

## What the gate binds

The gate consumes four exact canonical evidence files:

1. the accepted `rootfs-handoff-interactive-trial-plan-v1` plan;
2. the matching `rootfs-handoff-local-rootfs-preflight-v1` evidence proving the local rootfs bytes still match the reviewed plan;
3. the fresh-device revalidation that was used by the accepted manual trial authorization;
4. a **second distinct** fresh-device revalidation captured for the execution boundary.

The execution-time revalidation must resolve to the same target-binding identity and the same profile, device serial, firmware build/fingerprint, logical partition role, kernel name, filesystem, encryption state, staging subpath, rootfs artifact and recovery-plan identity. Its free-space observation must still satisfy the reviewed capacity requirement.

The second capture may not reuse the authorization-time storage-discovery digest or report digest. This prevents a previously accepted snapshot from being presented as a live execution check.

## Build the create-only evidence

After the second fresh read-only capture has been converted into a valid fresh-revalidation evidence file, build the execution gate with:

```bash
python scripts/build_rootfs_handoff_trial_execution_gate.py \
  --trial-plan evidence/rootfs-trial-plan.json \
  --trial-preflight evidence/rootfs-trial-preflight.json \
  --authorized-fresh-revalidation evidence/rootfs-authorized-fresh-revalidation.json \
  --execution-fresh-revalidation evidence/rootfs-execution-fresh-revalidation.json \
  --out evidence/rootfs-trial-execution-gate.json
```

The output is create-only. Existing output is never overwritten. The command prints the evidence SHA-256 plus the explicit non-write state so an operator cannot mistake a passed evidence gate for write permission.

## What success means

A successful gate records:

- `execution_gate_passed=true`;
- exact plan and preflight binding;
- exact authorization-time revalidation binding;
- `distinct_execution_capture_bound=true`;
- live device/firmware/logical-target/filesystem/encryption/capacity revalidation;
- local rootfs exact-byte verification carried from the preflight;
- recovery-plan identity revalidation.

It also deliberately requires all of the following to remain pending:

- `explicit_operator_confirmation_required=true`;
- `write_scope_confirmation_required=true`;
- `raw_device_path_resolution_required=true`;
- `interactive_writer_required=true`;
- `physical_gate_still_incomplete=true`.

## Safety boundary

This module is non-writing and does **not** contact the phone. It cannot resolve a raw `/dev` path, create a mount target, execute the rootfs trial or authorize persistent storage writes. The evidence therefore requires:

- `trial_execution_allowed=false`;
- `persistent_write_authorized=false`;
- `persistent_write_performed=false`;
- `phone_storage_written=false`;
- `storage_verified=false`;
- `recovery_verified=false`;
- `hardware_verified=false`;
- `beta_release_authorized=false`;
- `beta_gate_credit=false`.

A later interactive writer must still reacquire the concrete target from the same live device context, verify recovery readiness, show the exact device/firmware/target/rootfs/write scope to the operator and require an explicit confirmation before any write-capable operation. Passing this gate is not proof that Kali boots, that storage or recovery works, or that Beta is ready.

## Why a second fresh capture exists

The authorization-time fresh revalidation proves that the logical target was current when a reviewer authorized proceeding to an interactive boundary. Time can pass before execution. The execution gate therefore refuses to treat that same capture as current state. A later read-only capture must independently show that the accepted logical target has not drifted.

This extra capture is intentionally evidence-only. It does not select a raw block path and cannot convert a reviewed logical identity into write permission.
