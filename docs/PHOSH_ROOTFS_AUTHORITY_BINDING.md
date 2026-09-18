# Phosh rootfs authority binding

KaliPhoneStudio now has a host-only, fail-closed boundary that freezes one exact Phosh package manifest against one reviewed reproducible Kali ARM64 rootfs authority.

This is deliberately **not** a hardware result. It does not access a phone, choose a partition, mount storage, stage a rootfs, validate display/touch, authorize a Beta release or grant Beta-gate credit.

## Inputs

The binding requires all three exact inputs:

1. `tools/phosh-source-lock.json` — pinned NetHunter Pro Phosh reference-source lock.
2. A reviewed `RootfsAuthorityRecord` — the accepted reproducible ARM64 rootfs identity.
3. The exact normalized `package<TAB>version<TAB>architecture` package manifest whose SHA-256 and package count are already recorded by that authority.

The builder re-runs the Phosh package contract over the exact package-manifest bytes, then requires:

- the manifest SHA-256 to equal the reviewed rootfs authority,
- the package count to equal the reviewed rootfs authority,
- every locked Phosh package to be present,
- each required package architecture to be `arm64` or `all`,
- the rootfs authority to remain explicitly reviewed and host-only,
- the Phosh source lock to remain pinned and non-promoting.

Any digest/count/package/architecture drift fails closed.

## Build evidence

```bash
python scripts/build_phosh_rootfs_authority_binding.py \
  --source-lock tools/phosh-source-lock.json \
  --rootfs-authority path/to/rootfs-authority.json \
  --package-manifest path/to/package-manifest.txt \
  --out path/to/phosh-rootfs-authority-binding.json
```

The output is canonical JSON and includes a deterministic evidence SHA-256. Existing outputs are never overwritten.

## Claim boundary

A successful binding means only:

- the exact reviewed rootfs package manifest satisfies the locked host-side Phosh package contract; and
- the userspace identity is ready to be bound later into an exact physical candidate/evidence chain.

It always keeps these claims false:

- `display_verified`
- `touch_verified`
- `hardware_verified`
- `beta_release_authorized`
- `beta_gate_credit`

`physical_validation_required` remains true.

## Current project status

The checked-in project still has no physically verified AC2003 Phosh userspace. The current public Beta gate remains blocked. A future Phosh-enabled rootfs authority must first be generated/reviewed from exact reproducible rootfs evidence, then bound with this contract, and only then exercised through the real AC2003 temporary-boot / early-userspace / storage / recovery evidence chain.
