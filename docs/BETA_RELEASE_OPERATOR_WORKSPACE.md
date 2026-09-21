# Beta release preparation in the unified evidence workspace

KaliPhoneStudio exposes the final **offline** release-preparation stages through the same
`KaliPhoneStudio evidence` namespace used by the physical bring-up evidence chain.

These commands do not contact a phone, run ADB/Fastboot, upload anything, create a GitHub
Release, authorize a persistent write, mark hardware as verified, or grant Beta credit.
They only consume already reviewed local evidence and exact local release files.

## 1. Build the exact artifact inventory

After the physical candidate, physical release-gate audit, and accepted rootfs handoff
strategy review exist, bind those exact evidence files to the exact files intended for a
future Beta review:

```bash
KaliPhoneStudio evidence build-beta-artifact-inventory \
  --candidate-gate evidence/physical-candidate-gate.json \
  --release-gate-audit evidence/physical-release-gate-audit.json \
  --strategy-review evidence/rootfs-handoff-strategy-review.json \
  --source-commit <40-hex-commit> \
  --artifact candidate_boot=release/candidate-boot.img \
  --artifact kali_rootfs=release/kali-rootfs-arm64.tar.xz \
  --artifact operator_instructions=release/INSTALL.md \
  --artifact compatibility_matrix=release/COMPATIBILITY.md \
  --artifact known_issues=release/KNOWN_ISSUES.md \
  --out evidence/beta-release-artifact-inventory.json
```

Optional roles supported by the existing inventory contract include `kernel_image`, `dtb`,
`dtbo_image`, and `windows_host_bundle`. The inventory re-hashes exact regular files and
cross-checks the candidate boot/rootfs/kernel/DTB identities against the reviewed physical
evidence. Missing required roles, identity drift, non-reviewed functional coverage, or a
missing Kali early-userspace signal fail closed.

A successful inventory means only **ready for final manual release review**. It keeps
`release_publication_allowed=false`, `beta_release_authorized=false`,
`hardware_verified=false`, and `beta_gate_credit=false`.

## 2. Reverify the release directory and build the review bundle

Place exactly the inventoried files in one local release directory, then run:

```bash
KaliPhoneStudio evidence build-beta-review-manifest \
  --inventory evidence/beta-release-artifact-inventory.json \
  --release-dir release \
  --version 0.6.67-dev \
  --manifest-out evidence/beta-release-review-manifest.json \
  --checksums-out release/SHA256SUMS
```

This stage re-hashes every exact file, rejects any mismatch, and emits deterministic
canonical manifest metadata plus deterministic `SHA256SUMS`. Both outputs are create-only:
pre-existing outputs are refused rather than overwritten.

Even a successful review manifest still requires the independent **final manual release
gate** from `BETA_RELEASE_GATE.md`. It does not publish a release and does not convert
host-side evidence into physical AC2003 verification.

## JSON output

Place `--json` before the command for machine-readable safety/result output:

```bash
KaliPhoneStudio evidence --json build-beta-artifact-inventory ...
KaliPhoneStudio evidence --json build-beta-review-manifest ...
```

The summary explicitly keeps phone interaction, network publication, persistent write,
hardware verification, Beta authorization, and Beta credit false.

## Why this is separate from publication

The release-preparation boundary is intentionally offline. GitHub publication must remain a
separate human-controlled action performed only after every mandatory physical gate is
reviewed and the exact release manifest/SHA-256 set is accepted. Green host CI alone is
never sufficient to publish Beta.
