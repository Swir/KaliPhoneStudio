# Phosh rootfs A/B reproducibility candidate

This stage verifies that two separately executed host builds of the pinned Phosh ARM64
rootfs path produce the same canonical rootfs identity and the same installed-package
manifest. It advances the host-side userspace build path, but it is **not** physical
AC2003 validation and it does not authorize Beta.

## Inputs

Each build must be produced by `scripts/run_locked_phosh_rootfs_build.py` from the same:

- pinned `tools/phosh-source-lock.json`;
- `tools/phosh-rootfs-build-contract.json`;
- generated build plan;
- canonicalization policy.

The comparator accepts only canonical schema-v1 build-evidence JSON where the Phosh
package contract passed and all authority/hardware/Beta flags remain false.

## Independent build boundary

`.github/workflows/phosh-rootfs-reproducibility.yml` launches build A and build B as
separate Ubuntu jobs after the cross-platform comparator contract passes. Each job
checks out the exact pinned upstream commit and executes a complete Debos rootfs build.
Only the small exact evidence/manifest files are transferred between jobs.

The comparison step records two distinct workflow origins and fails closed unless these
fields match across A/B:

- upstream commit;
- source-lock SHA-256;
- build-contract SHA-256;
- build-plan SHA-256;
- canonical rootfs SHA-256 and byte size;
- installed package-manifest SHA-256 and package count.

## Output semantics

A successful comparison produces
`phosh-rootfs-reproducibility-candidate.json` with:

- `strict_byte_identical=true`;
- `package_manifest_identical=true`;
- `review_required=true`;
- `reproducibility_authority=false`;
- `physical_validation_required=true`;
- `hardware_verified=false`;
- `beta_gate_credit=false`.

This is intentionally a **candidate for review**, not a reviewed authority. The exact
workflow run and evidence must still be reviewed before any Phosh reproducibility
authority can be recorded. Even a reviewed host authority would not prove display,
touch, power, storage, modem, audio or any other phone hardware support.

## Local/offline comparison

```bash
python scripts/compare_phosh_rootfs_builds.py \
  --build-a evidence/build-a/phosh-build.json \
  --build-b evidence/build-b/phosh-build.json \
  --origin-a local/run-a \
  --origin-b local/run-b \
  --out evidence/phosh-rootfs-reproducibility-candidate.json
```

The origins must be distinct bounded identifiers. They identify the two build contexts;
they do not replace review of the actual execution provenance.
