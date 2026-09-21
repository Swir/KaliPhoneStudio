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

## Physical-campaign adapter

This manifest is intentionally not passed to the legacy physical-candidate gate as a
fake schema-v8 manifest. `kaliphonestudio.phosh_physical_candidate_adapter` instead
cross-binds the successor to the already-reviewed exact physical-candidate gate for the
same phone, firmware, Fastboot baseline, boot image, kernel and DT identity. It also
proves that the rootfs superseded by the successor is exactly the rootfs carried by the
original physical gate.

The adapter is still host-only: it selects no storage target, stages no rootfs, runs no
Fastboot command and authorizes no temporary boot or write. Its successful state is
only `ready_for_physical_staging_review=true`, with hardware/Beta credit forced false.

See [`PHOSH_PHYSICAL_CANDIDATE_ADAPTER.md`](PHOSH_PHYSICAL_CANDIDATE_ADAPTER.md).

## Next gate

Bind that exact adapter to real reviewed physical storage/recovery evidence and an
explicitly approved reversible rootfs staging strategy. A distinct fresh read-only
storage revalidation and a separate manual trial authorization are still required
immediately before any write-capable staging attempt. Real AC2003 boot/display/touch
evidence remains mandatory before this path earns hardware or Beta credit.
