# Rootfs handoff payload manifest

`rootfs-handoff-trial-payload-manifest-v1` is a **host-only, non-writing** archive-inspection boundary between the accepted execution gate and any future interactive rootfs writer.

The execution gate proves that the reviewed logical target, fresh physical storage state and exact local rootfs bytes still agree. It intentionally does not inspect what the archive would expand into. This payload manifest closes that gap before a writer is considered: it inventories the exact write scope and derives capacity from the expanded regular-file payload rather than trusting the compressed archive size.

## What it consumes

The builder accepts only:

- the canonical `rootfs-handoff-interactive-execution-gate-v1` evidence file;
- the exact local rootfs archive referenced by that gate.

The rootfs file is descriptor-bound hashed before inspection and hashed again afterwards. Both observations must retain the same exact file identity and SHA-256, and that digest/size must match the gate.

## Archive safety contract

The manifest refuses to create write scope when the archive contains:

- absolute or parent-traversing member paths;
- duplicate normalized paths;
- link targets that escape the rootfs namespace;
- dangling/cyclic hardlinks or hardlinks that do not resolve to regular payload files;
- device nodes, FIFOs or unknown/special tar member types;
- an expanded regular-file payload larger than the execution-time observed free-space bound.

Regular files are streamed and SHA-256 hashed from their decompressed tar payload. Directories, symlinks and hardlinks are recorded explicitly. Entries are sorted by UTF-8 path bytes and hashed into one deterministic `entries_sha256` write-scope identity.

## Expanded-capacity rule

A compressed rootfs archive can be much smaller than the filesystem it expands into. The manifest therefore computes:

`minimum_required_free_bytes = regular_payload_bytes + max(64 MiB, ceil(regular_payload_bytes * 5%))`

Both the previously reviewed free-space requirement and the latest observed free-space value must satisfy that number. If the earlier review covered only the compressed archive size, the payload-manifest stage fails closed and the physical storage strategy must be reviewed again with a realistic capacity requirement.

## Build the create-only manifest

The installed/unified evidence workspace exposes the same non-writing contract:

```bash
KaliPhoneStudio evidence build-rootfs-handoff-trial-payload-manifest \
  --execution-gate evidence/rootfs-trial-execution-gate.json \
  --rootfs-artifact artifacts/kali-rootfs-arm64.tar.xz \
  --out evidence/rootfs-trial-payload-manifest.json
```

The repository script remains available for source-tree use:

```bash
python scripts/build_rootfs_handoff_trial_payload_manifest.py \
  --execution-gate evidence/rootfs-trial-execution-gate.json \
  --rootfs-artifact artifacts/kali-rootfs-arm64.tar.xz \
  --out evidence/rootfs-trial-payload-manifest.json
```

The unified command supports the workspace-level `--json` switch; the repository script also supports `--json`. The output is canonical JSON and create-only; existing files are never overwritten.

## What success does **not** mean

A successful manifest does not contact a phone, resolve a raw `/dev` path, bind a mount target, extract files, run `adb`/`fastboot`, authorize a write, prove storage/recovery, prove Kali booted, verify hardware or grant Beta credit.

The evidence therefore keeps all of these false:

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

It also keeps explicit operator confirmation, separate write-scope confirmation and a future interactive writer mandatory. The physical AC2003 gate in `BETA_RELEASE_GATE.md` remains authoritative.
