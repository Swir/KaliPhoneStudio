# Rootfs trial-chain safety audit

`rootfs-trial-chain-audit-v1` is a deterministic host-side guard for the three reviewed, non-executing boundaries that sit after fresh rootfs target revalidation and before any future interactive trial executor.

The audit exists to stop source, documentation, tests, and safety-sensitive helper dependencies from drifting independently. It does **not** connect to a phone, import an execution path, resolve a raw `/dev/...` target, mount storage, authorize writes, perform a trial, verify hardware, or grant Beta credit.

## Audited contracts

The checker binds the currently reviewed policy identifiers to their source, documentation, focused tests, and any declared safety dependency:

| Boundary | Reviewed policy | Safety meaning |
|---|---|---|
| Manual authorization | `rootfs-handoff-manual-trial-authorization-v1` | An independent review may accept the exact evidence chain for handoff to a later interactive boundary, but may not authorize execution or writes. |
| Interactive trial plan | `rootfs-handoff-interactive-trial-plan-v1` | The exact authorization/target/fresh-revalidation chain is converted into a non-executing plan that explicitly requires live rechecks and operator confirmation. |
| Local rootfs preflight | `rootfs-handoff-local-rootfs-preflight-v1` | The exact local Kali rootfs bytes are re-hashed while all physical/device/write permissions remain false; its descriptor-bound `kaliphonestudio/stable_file.py` helper is part of the audited boundary. |

## What is checked

`tools/audit_rootfs_trial_chain.py` parses the Python source with `ast` rather than importing the evidence modules. For every audited boundary it verifies:

- the exact reviewed policy identifier;
- required fail-closed fields such as `raw_device_path_bound`, `mount_target_bound`, `trial_execution_allowed`, `persistent_write_authorized`, `hardware_verified`, `beta_release_authorized`, and `beta_gate_credit` remain in the forbidden set;
- required live recheck / explicit operator-boundary fields remain present;
- the matching focused test file exists;
- documentation still contains the safety markers that distinguish host-side readiness from physical verification or execution authorization;
- every declared safety dependency exists and, together with the boundary source, remains free of `subprocess` imports/calls and `os.system` / `os.popen` execution primitives.

The machine-readable report records the declared dependency paths per contract and hard-codes all physical interaction, write, hardware, and Beta claims to `false`.

## Run locally

Human-readable audit:

```bash
python tools/audit_rootfs_trial_chain.py
```

Deterministic machine-readable audit:

```bash
python tools/audit_rootfs_trial_chain.py --json
```

Focused regression suite:

```bash
python -m unittest \
  tests.test_rootfs_handoff_trial_authorization \
  tests.test_rootfs_handoff_trial_plan \
  tests.test_rootfs_handoff_trial_preflight \
  tests.test_rootfs_trial_chain_audit \
  -v
```

The audit tests intentionally tamper with copied contracts to prove that policy drift, removal of a Beta fail-closed flag, documentation safety-marker drift, and an execution primitive introduced into the shared local-file safety dependency are rejected.

## CI contract

`.github/workflows/rootfs-trial-chain-audit.yml` runs the deterministic audit and the focused trial-chain test set on Python 3.11 and 3.14 when the audited source, declared `stable_file` dependency, documentation, tests, audit tool, or workflow changes.

A green audit means only that the checked-in host-side safety contract is internally consistent. It is **not** evidence that a phone has been tested and it does not change project progress or Beta readiness.

## Physical gate remains separate

For `oneplus/avicii`, the real OnePlus Nord AC2003 campaign is still required. `BETA_RELEASE_GATE.md` remains authoritative for physical identity, exact firmware baseline, matching stock `boot.img`, recovery readiness, recovery-gated temporary boot, Kali early userspace/rootfs, storage, safe charging/battery behavior, hardware evidence, recovery, and the release manifest/checksums.

Until that physical gate passes, KaliPhoneStudio remains Beta-blocked regardless of this host-side audit result.
