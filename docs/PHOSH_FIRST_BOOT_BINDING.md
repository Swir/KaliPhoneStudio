# Phosh first-boot candidate regeneration binding

KaliPhoneStudio already has a reviewed host-side first-boot authority bundle for the
kernel, existing Kali rootfs, DTB and DTBO. The executable Phosh ARM64 build path in
PR #132 intentionally produces a **different rootfs artifact**. That artifact cannot
be inserted into the existing first-boot manifest without invalidating the manifest
and its rootfs authority binding.

`kaliphonestudio/phosh_first_boot_binding.py` closes that provenance gap without
pretending a phone was tested.

## What the binding proves

The binding joins:

- the exact existing `FirstBootAuthorityBundleEvidence`;
- its reviewed kernel authority and exact kernel `Image`;
- its reviewed device-tree authority and exact DTB/DTBO;
- the old rootfs identity that will be superseded;
- one explicitly reviewed `PhoshRootfsAuthorityRecord`;
- the exact review packet, source commit, upstream Phosh commit, source lock,
  rootfs payload and package manifest.

The output records that kernel/device-tree provenance can be reused while the rootfs
substitution requires a **new first-boot candidate manifest and new rootfs authority
chain**.

## What it does not prove

This is host-only evidence. It does not select a physical storage target, mount or
write a filesystem, execute fastboot, flash a partition, boot a phone, or validate
display/touch. The following remain false by construction:

- `display_verified`
- `touch_verified`
- `hardware_verified`
- `beta_release_authorized`
- `beta_gate_credit`

If the reviewed Phosh rootfs has the same artifact digest as the base candidate rootfs,
this regeneration path is rejected. In that special case the existing direct Phosh
candidate-binding path is the correct contract.

## Build the binding

After a real A/B Phosh build has been reviewed and promoted to a
`PhoshRootfsAuthorityRecord`:

```bash
python scripts/build_phosh_first_boot_binding.py \
  --candidate-authority-bundle first-boot-authority-bundle.json \
  --phosh-rootfs-authority phosh-rootfs-authority.json \
  --phosh-review-packet phosh-rootfs-review-packet.json \
  --out phosh-first-boot-regeneration-binding.json
```

The command is create-only and fails closed on detached, non-canonical, unreviewed or
unsafe evidence.

## Next integration step

The regeneration binding is the input contract for generating a successor schema-v8
first-boot candidate whose rootfs fields refer to the exact reviewed Phosh rootfs.
That successor must then receive a matching rootfs-authority binding and a new combined
authority bundle before any physical AC2003 temporary-boot campaign can consume it.

Nothing in this document changes Beta readiness. Real AC2003 identity, recovery,
temporary boot, early userspace/rootfs handoff, storage, charging and the declared
display/touch scope still require physical evidence.
