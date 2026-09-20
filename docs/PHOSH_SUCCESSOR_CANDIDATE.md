# Phosh successor first-boot candidate

The existing schema-v8 `FirstBootCandidateManifest` is immutable evidence for one exact
legacy Kali rootfs. A reviewed Phosh rootfs must **not** be inserted by editing those
rootfs fields because the old rootfs evidence, source-lock and authority chain would no
longer describe the bytes being tested.

`kaliphonestudio/phosh_successor_candidate.py` therefore creates a separate,
create-only `PhoshSuccessorCandidateManifest`.

## Exact inputs

The successor binds three immutable objects:

1. the existing schema-v8 first-boot manifest;
2. its reviewed/strict `FirstBootAuthorityBundleEvidence`;
3. one `PhoshFirstBootBindingEvidence` created from an explicitly reviewed Phosh
   rootfs authority.

The resulting manifest carries the unchanged device/firmware/Fastboot identity,
boot authorization, boot plan, boot image, kernel and DTB/DTBO identity, plus the
reviewed replacement Phosh rootfs artifact and package-manifest identity. It stores
SHA-256 links back to all three base objects.

This avoids pretending that the legacy schema-v8 rootfs provenance applies to the
new Phosh filesystem.

## Safety semantics

The successor is host-only assembly evidence. It does not:

- select, mount or write a phone storage target;
- run ADB or Fastboot;
- flash a partition;
- prove boot, display, touch or any other hardware function;
- grant Beta readiness.

`physical_validation_required=true` remains mandatory while
`display_verified`, `touch_verified`, `hardware_verified`,
`beta_release_authorized` and `beta_gate_credit` remain false by construction.

## Build

After the real A/B Phosh rootfs output has been reviewed and the preceding
`phosh-first-boot-regeneration-binding.json` exists:

```bash
python scripts/build_phosh_successor_candidate.py \
  --base-first-boot-manifest first-boot-manifest.json \
  --base-authority-bundle first-boot-authority-bundle.json \
  --phosh-first-boot-binding phosh-first-boot-regeneration-binding.json \
  --out phosh-successor-first-boot-candidate.json
```

The output is canonical JSON and create-only. Any mismatch in the exact base
manifest, authority bundle, kernel/device-tree identity, superseded rootfs identity or
reviewed Phosh binding fails closed.

## Next gate

This manifest is intentionally not passed to the legacy physical-candidate gate as a
fake schema-v8 manifest. The next integration step is an explicit physical-candidate
adapter that binds this successor identity to the real AC2003 physical baseline and
rootfs staging evidence. Until that adapter and the physical tests exist, this path
earns no hardware or Beta credit.
