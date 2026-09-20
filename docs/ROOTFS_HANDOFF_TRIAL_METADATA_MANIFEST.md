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

## Extraction-safety companion evidence

Before any future extractor or writer is allowed to consume the archive, `exact-rootfs-archive-extraction-safety-v1` performs a second host-only fail-closed inspection bound to the exact metadata manifest and exact rootfs bytes. It does **not** extract anything. It rejects:

- absolute or parent-traversing archive member paths, duplicate normalized paths and unsupported special members;
- symlink targets whose lexical resolution escapes the rootfs namespace;
- any archive member nested below a symlink or hardlink path, preventing link-pivot extraction attacks;
- hardlinks that do not resolve to a reviewed regular-file member.

Absolute symlink targets are classified separately and interpreted as rootfs-namespace targets for safety analysis; their presence does not authorize host-path traversal. The resulting canonical evidence records symlink/hardlink counts and keeps extraction, raw-device binding, mounting, writes, hardware claims and Beta credit false.

```bash
python scripts/build_rootfs_handoff_trial_archive_safety.py \
  --metadata-manifest evidence/rootfs-trial-metadata-manifest.json \
  --rootfs-artifact artifacts/kali-rootfs-arm64.tar.xz \
  --out evidence/rootfs-trial-archive-safety.json
```

This output is also create-only. Use `--json` for a compact machine-readable summary.

## Safety and release meaning

A successful metadata manifest or archive-safety preflight does **not** resolve a raw device path, mount or extract the rootfs, contact a phone, authorize a persistent write, prove storage/recovery/hardware, or grant Beta credit. Both keep the future interactive writer, explicit operator confirmation and separate write-scope confirmation mandatory. The physical AC2003 release gate remains authoritative.
