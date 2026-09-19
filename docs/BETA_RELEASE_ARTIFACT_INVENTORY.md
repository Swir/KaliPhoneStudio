# Beta release artifact inventory

`kaliphonestudio.beta_release_artifact_inventory` is an **offline, non-authorizing** packaging-safety layer for KaliPhoneStudio.

It exists to make the later release review consume exact files instead of filenames or assumptions. It does **not** publish a GitHub release, run ADB/Fastboot, select a phone-storage target, write a phone, claim hardware support, or grant Beta credit.

## Admission boundary

An inventory can be created only when all supplied evidence agrees on the exact profile, device serial, firmware build and firmware fingerprint, and when:

- the physical candidate gate is canonical and still contains no write/hardware/Beta promotion;
- the cross-campaign physical release-gate audit is canonical;
- every Beta-required functional result in that audit is independently reviewed pass;
- the audit carries the exact Kali early-userspace signal from its dossier chain;
- the rootfs handoff strategy review is accepted for trial design and binds that exact release-gate audit;
- the reviewed rootfs identity agrees with the exact physical candidate;
- the requested source commit is an exact 40-hex Git commit id.

These checks make the inventory suitable only as **input to the final manual release review**. The evidence always keeps `release_publication_allowed=false`, `beta_release_authorized=false`, `hardware_verified=false` and `beta_gate_credit=false`.

## Required release-file roles

The first inventory schema requires one exact file for each of these roles:

- `candidate_boot`
- `kali_rootfs`
- `operator_instructions`
- `compatibility_matrix`
- `known_issues`

Optional roles are `kernel_image`, `dtb`, `dtbo_image` and `windows_host_bundle`. If the exact physical candidate requires DTB or DTBO material, the matching role becomes mandatory and its SHA-256 must match the candidate gate.

Every file must be a regular non-symlink file. Safety-sensitive reads use the shared descriptor-bound `stable_file` verifier: the path is bound to one secured descriptor before bytes are consumed, release artifacts are SHA-256 hashed without reopening them, and bounded canonical JSON evidence is parsed from bytes returned by that same verified descriptor. Symlink/reparse-point traversal, path replacement, truncation, growth and metadata/content drift fail closed. On Windows the read handle denies concurrent write/delete sharing while verification is active.

## CLI

Run from the repository root:

```bash
PYTHONPATH=. python scripts/build_beta_release_artifact_inventory.py \
  --candidate-gate evidence/physical-candidate-gate.json \
  --release-gate-audit evidence/physical-release-gate-audit.json \
  --strategy-review evidence/rootfs-handoff-strategy-review.json \
  --source-commit <exact-40-hex-commit> \
  --artifact candidate_boot=release/candidate-boot.img \
  --artifact kali_rootfs=release/kali-rootfs.tar.zst \
  --artifact operator_instructions=release/INSTALL.txt \
  --artifact compatibility_matrix=release/COMPATIBILITY.json \
  --artifact known_issues=release/KNOWN_ISSUES.txt \
  --out evidence/beta-release-artifact-inventory.json
```

Add `--artifact dtb=...`, `--artifact dtbo_image=...`, `--artifact kernel_image=...` or `--artifact windows_host_bundle=...` when those files are part of the reviewed candidate/release set.

The command prints the inventory SHA-256 and explicitly reports that release publication is still disallowed and the final manual gate review is still required.

## CI contract

The inventory workflow runs on Linux and Windows with Python 3.11 and 3.14. Changes to the shared `kaliphonestudio/stable_file.py` verifier retrigger this release-safety boundary, preventing verifier drift from bypassing inventory tests.

## What this does not satisfy

A green inventory is **not** the final release manifest and does not complete any physical AC2003 checkbox. The following still require real-phone evidence and manual review before a public Beta can exist:

- exact physical AC2003/OxygenOS baseline and matching stock `boot.img`;
- recovery-gated temporary boot and reviewed rescue evidence;
- real functional-test observations and reviews;
- accepted storage/recovery evidence and exercised rollback;
- intended Kali early-userspace/rootfs confirmation;
- required storage, power/charging, USB/rescue and declared UI scope verification;
- final manual release-gate approval;
- the final compatibility matrix, known issues, release manifest and SHA-256 set produced from the approved candidate.

The public Beta publication rule in [`../BETA_RELEASE_GATE.md`](../BETA_RELEASE_GATE.md) remains authoritative.
