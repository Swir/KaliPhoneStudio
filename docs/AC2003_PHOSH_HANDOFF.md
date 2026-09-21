# AC2003 reviewed Phosh handoff

This is the host-only bridge from the reviewed reproducible Kali ARM64 + Phosh rootfs authority to one exact real AC2003 physical campaign. It is intended to be used from the frozen Windows Beta-test-candidate CLI after the read-only baseline and offline physical-candidate preparation have succeeded.

It does **not** stage rootfs bytes, run Fastboot, write phone storage, prove hardware support, or grant Beta credit.

## Packaged reviewed Phosh authority

The Windows candidate carries these immutable reviewed records in `operator-pack/`:

- `phosh-rootfs-authority.json`
- `phosh-rootfs-review-packet.json`

The authority currently binds the byte-identical reviewed rootfs artifact with SHA-256 `c6f8088a5253983703768bced4e936c9c228f89d804df25ff9b172c8467c764e`, size `881665284` bytes and package-manifest SHA-256 `d2fef9b14f8100ad87a9a3429aeacb998f3c7a63dd00b161e4f8dfc518fa1ed7`.

The large rootfs artifact bytes are **not** embedded in the Windows host ZIP. Before any later storage trial, obtain the exact reviewed artifact identified by the packaged authority record and verify its size and SHA-256 locally. Do not substitute a rebuilt, nearby, or similarly named rootfs.

## Preconditions

Complete the recovery-first sequence in `AC2003_FIRST_TEST.md` through the host-only offline candidate preparation. You must have all of the following exact files from the same candidate/physical campaign:

- base schema-v8 first-boot manifest used for `prepare-physical-candidate-offline`;
- its reviewed first-boot authority bundle;
- `$Session\physical-candidate-gate.json` produced from the real read-only AC2003 baseline;
- the packaged reviewed Phosh authority and review packet.

Use a fresh output path for every command. All writers are create-only and fail closed on identity or digest drift.

## 1. Bind the reviewed Phosh rootfs to the base first-boot authority

```powershell
$Cli = (Resolve-Path ".\KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe").Path
$PhoshAuthority = (Resolve-Path ".\operator-pack\phosh-rootfs-authority.json").Path
$PhoshReview = (Resolve-Path ".\operator-pack\phosh-rootfs-review-packet.json").Path

& $Cli phosh build-first-boot-binding `
  --candidate-authority-bundle "<EXACT_BASE_AUTHORITY_BUNDLE_JSON>" `
  --phosh-rootfs-authority "$PhoshAuthority" `
  --phosh-review-packet "$PhoshReview" `
  --out "$Session\phosh-first-boot-binding.json"
```

A successful result still reports `hardware_verified=false` and `beta_gate_credit=false`.

## 2. Build the immutable Phosh successor candidate

```powershell
& $Cli phosh build-successor-candidate `
  --base-first-boot-manifest "<EXACT_BASE_FIRST_BOOT_MANIFEST_JSON>" `
  --base-authority-bundle "<EXACT_BASE_AUTHORITY_BUNDLE_JSON>" `
  --phosh-first-boot-binding "$Session\phosh-first-boot-binding.json" `
  --out "$Session\phosh-successor-first-boot-candidate.json"
```

This preserves the reviewed kernel, DTB/DTBO, boot authorization/plan, firmware and Fastboot identity while replacing only the legacy rootfs authority with the reviewed Phosh rootfs authority.

## 3. Cross-bind the successor to the exact physical candidate gate

```powershell
& $Cli phosh bind-physical-candidate `
  --phosh-successor-candidate "$Session\phosh-successor-first-boot-candidate.json" `
  --physical-candidate-gate "$Session\physical-candidate-gate.json" `
  --out "$Session\phosh-physical-candidate-adapter.json"
```

The adapter must end with:

- `exact_physical_gate_bound=true`
- `reviewed_phosh_successor_bound=true`
- `ready_for_physical_staging_review=true`
- `physical_validation_required=true`
- `staging_target_selected=false`
- `rootfs_staged=false`
- `temporary_boot_authorized=false`
- `phone_storage_written=false`
- `hardware_verified=false`
- `beta_gate_credit=false`

Any mismatch in serial, firmware, Fastboot baseline, boot image, kernel, DTB/DTBO, base first-boot authority or superseded rootfs fails closed.

## 4. Physical staging remains a separate manual gate

`ready_for_physical_staging_review=true` is **not** permission to write storage. Continue only after the real storage/recovery evidence, reversible target strategy, fresh-device revalidation and explicit manual rootfs trial authorization required by `BETA_RELEASE_GATE.md` and the evidence workspace are complete.

No command in this document performs `fastboot flash`, `fastboot erase`, slot switching, rootfs staging, or any persistent write.
