# Rootfs handoff metadata manifest

`exact-payload+posix-pax-metadata-v1` is a **host-only, non-writing** boundary after the expanded payload manifest and before any future interactive rootfs writer.

The existing payload manifest proves the exact archive bytes, normalized write scope, per-file content hashes, link targets and expanded-capacity requirement. A Linux rootfs also depends on metadata that a writer must not silently discard: numeric ownership, optional owner/group names, POSIX modes and non-structural PAX metadata such as xattrs or ACL records. This stage binds that metadata to the same exact rootfs bytes without extracting the archive or contacting a phone.

## What it verifies

The builder accepts the canonical rootfs payload manifest plus the exact local rootfs archive referenced by that manifest. It hashes the archive before and after inspection and requires the same stable file identity, size and SHA-256. Every tar member must correspond to exactly one reviewed payload entry with the same normalized path, kind, mode, regular-file size and link target.

For every member it records:

- POSIX mode, numeric `uid`/`gid` and optional `uname`/`gname`;
- sorted non-structural PAX key/value records;
- deterministic path ordering and one `metadata_entries_sha256` identity.

Structural tar PAX keys (`path`, `linkpath`, `size`, timestamps and owner overrides) are intentionally not duplicated into the restorable PAX set. Security-oriented keys such as `SCHILY.xattr.*`, `LIBARCHIVE.xattr.*` and `SCHILY.acl.*` are counted explicitly so their presence cannot disappear silently before a later writer implementation.

## Build the create-only manifest

```bash
python scripts/build_rootfs_handoff_trial_metadata_manifest.py \
  --payload-manifest evidence/rootfs-trial-payload-manifest.json \
  --rootfs-artifact artifacts/kali-rootfs-arm64.tar.xz \
  --out evidence/rootfs-trial-metadata-manifest.json
```

Use `--json` for machine-readable output. The evidence is canonical JSON and create-only; an existing output is never overwritten.

## Safety and release meaning

A successful metadata manifest does **not** resolve a raw device path, mount or extract the rootfs, contact a phone, authorize a persistent write, prove storage/recovery/hardware, or grant Beta credit. It keeps the future interactive writer, explicit operator confirmation and separate write-scope confirmation mandatory. The physical AC2003 release gate remains authoritative.
