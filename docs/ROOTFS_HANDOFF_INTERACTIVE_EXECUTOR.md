# Rootfs handoff interactive staging executor

This is the final **local rescue-console write boundary** for the reversible rootfs trial. It is deliberately separate from `RootfsHandoffTrialExecutionGateEvidence`: that evidence remains non-writing and keeps `persistent_write_authorized=false`. The rescue helper performs no action unless the operator supplies the exact accepted gate bytes, exact rootfs archive bytes, an already-mounted reviewed target, and then types a fresh write-scope confirmation.

The helper is packaged into the deterministic rescue candidate as:

```text
/sbin/kps-rootfs-stage-once
```

It is **never executed by `/init`**. Network/SSH remain disabled and persistent storage is still not mounted automatically.

## Preconditions on the real phone

Complete the existing physical chain first. In particular, use the exact same phone/firmware campaign and an accepted `rootfs-handoff-trial-execution-gate.json`. The gate must still say that the physical gate is incomplete and that a separate interactive writer plus operator confirmation are required.

Before invoking the helper, the operator must make the exact reviewed rootfs archive and exact execution-gate JSON locally visible in rescue, then mount the deliberately selected target read-write under a fresh `/mnt/kps-*` mountpoint. KaliPhoneStudio does not guess a raw block path, choose a partition, decrypt storage, format a filesystem, or mount a target automatically.

The helper rechecks:

- exact SHA-256 of the execution-gate file;
- exact SHA-256 of the rootfs archive;
- the execution-gate pass/confirmation/write-scope contract;
- the exact rootfs digest, staging subpath and required-free-bytes bound by the gate;
- that the target is a real mountpoint backed by `/dev/*`;
- that the mount is read-write and not a pseudo-filesystem;
- that the live filesystem type still matches the accepted execution gate;
- current free space;
- basic archive path traversal safety before extraction;
- that both the temporary and final staging paths do not already exist.

It never flashes, erases, changes A/B slots, reboots, formats, repairs, decrypts, auto-mounts or overwrites an existing rootfs staging directory.

## Invocation

From the already-reached local rescue console:

```sh
/sbin/kps-rootfs-stage-once \
  --execution-gate /PATH/rootfs-handoff-trial-execution-gate.json \
  --execution-gate-sha256 <EXACT_GATE_SHA256> \
  --archive /PATH/kali-phosh-arm64-rootfs.tar.xz \
  --rootfs-sha256 <EXACT_ROOTFS_SHA256> \
  --target-mount /mnt/kps-rootfs-target \
  --staging-subpath kaliphonestudio/rootfs-stage \
  --required-free-bytes <EXACT_BYTES_FROM_GATE>
```

The helper prints the resolved live block source, filesystem, free-space values and final staging path, then prints one exact confirmation sentence. **Nothing is written until the operator types that sentence exactly.**

On success it extracts into a create-only temporary directory on the selected filesystem, syncs, renames that directory atomically to the final staging path, syncs again, and emits `KPS_ROOTFS_STAGE_*` transcript markers. On extraction failure it deliberately leaves the temporary directory in place for review rather than deleting unknown partial state automatically.

A successful staging operation is physical evidence only. The helper explicitly emits:

```text
KPS_ROOTFS_STAGE_HARDWARE_VERIFIED=false
KPS_ROOTFS_STAGE_BETA_AUTHORIZED=false
KPS_ROOTFS_STAGE_BETA_CREDIT=false
```

Physical storage verification, recovery proof, Kali early-userspace/rootfs proof, charging/display/touch and the remaining `BETA_RELEASE_GATE.md` requirements still have to pass before Beta can be published.
