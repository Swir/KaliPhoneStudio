# Phosh candidate provenance binding

`kaliphonestudio.phosh_candidate_binding` is a host-only, fail-closed provenance boundary between the reviewed first-boot candidate authority bundle and the reviewed Phosh/rootfs package binding.

## Why this exists

The rootfs authority can prove byte identity and the Phosh/rootfs binding can prove that the exact reviewed package manifest contains the locked Phosh userspace contract. A physical candidate must not silently combine those records with a different rootfs. This boundary cross-binds both evidence objects before any later real-device Phosh validation.

The binding requires:

- a canonical schema-v1 `FirstBootAuthorityBundleEvidence` with reviewed/strict kernel, rootfs and device-tree authorities;
- a canonical schema-v1 `PhoshRootfsAuthorityBindingEvidence` with the required package contract satisfied;
- identical rootfs authority SHA-256 in both records;
- identical rootfs artifact SHA-256 in both records;
- exact SHA-256 identities for the candidate authority bundle and Phosh/rootfs binding;
- the pinned Phosh source-lock digest and exact upstream commit;
- explicit continued requirement for physical Phosh validation.

## Safety boundary

A successful binding means only that one exact host-reviewed candidate and one exact host-reviewed Phosh package identity share the same reviewed rootfs provenance. It does **not** mean Phosh booted or that display/touch works.

The evidence always keeps these claims false:

- `display_verified`
- `touch_verified`
- `hardware_verified`
- `beta_release_authorized`
- `beta_gate_credit`

The module performs no Fastboot/ADB/device access, chooses no storage target, carries no raw device path or mount target, and cannot authorize a rootfs trial or persistent write.

## Unified evidence CLI

The preferred operator path is the same source/frozen Windows evidence namespace used by the other offline review stages:

```bash
python main.py evidence bind-phosh-candidate \
  --candidate-authority-bundle evidence/first-boot-authority-bundle.json \
  --phosh-rootfs-binding evidence/phosh-rootfs-authority-binding.json \
  --out evidence/phosh-candidate-binding.json
```

The standalone builder remains available for reproducible scripting:

```bash
python scripts/build_phosh_candidate_binding.py \
  --candidate-authority-bundle evidence/first-boot-authority-bundle.json \
  --phosh-rootfs-binding evidence/phosh-rootfs-authority-binding.json \
  --output evidence/phosh-candidate-binding.json
```

Both inputs must be canonical regular files and not symlinks. The output is create-only canonical JSON. Existing output or stale temporary paths are refused. The unified command emits the same explicit safety boundary: no phone interaction, no storage selection/write authorization and no display/touch/hardware/Beta credit.

## What comes next

`ready_for_physical_phosh_validation=true` is a provenance hand-off only. Physical credit still requires the exact AC2003 candidate to pass the real recovery-gated temporary boot, intended Kali rootfs/early-userspace proof and the separately reviewed display/touch or explicitly approved console-only release scope. Beta remains governed solely by `BETA_RELEASE_GATE.md`.
