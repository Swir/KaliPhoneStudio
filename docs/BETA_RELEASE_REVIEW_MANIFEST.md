# Beta release review manifest

`kaliphonestudio.beta_release_review_manifest` is an offline, fail-closed packaging review layer. It consumes one canonical `BetaReleaseArtifactInventoryEvidence`, re-hashes every named release file from a single directory, and produces deterministic manifest metadata plus `SHA256SUMS` text for a later independent final release-gate review.

It does **not** communicate with a phone, run ADB/Fastboot, access the network, create/upload a GitHub Release, select a storage target, write phone storage, claim hardware support, authorize Beta, or grant Beta credit.

## Admission boundary

The input inventory must already be canonical and `ready_for_final_manual_release_review=true`. Its publication/hardware/Beta promotion flags must still be false. The manifest builder then:

- requires the exact 40-hex source commit carried by the inventory;
- requires a bounded semantic-version-like release identifier;
- rejects a symlink release directory and symlink artifacts;
- rejects unsafe artifact basenames before rendering checksum lines, including whitespace/control/newline injection;
- re-hashes every exact artifact and rechecks byte size against the inventory;
- emits `SHA256SUMS` in deterministic filename order;
- binds the exact inventory digest, source commit, device/firmware identity, artifact set, checksum-set digest and count into canonical JSON;
- keeps `release_publication_allowed=false`, `beta_release_authorized=false`, `hardware_verified=false` and `beta_gate_credit=false`.

## CLI

```bash
PYTHONPATH=. python scripts/build_beta_release_review_manifest.py \
  --inventory evidence/beta-release-artifact-inventory.json \
  --release-dir release \
  --version 0.6.67-beta.1 \
  --manifest-out evidence/beta-release-review-manifest.json \
  --checksums-out release/SHA256SUMS
```

Both outputs are create-only. Existing destinations are never overwritten. The generated manifest is review material, **not** the final public release authorization.

## Release gate status

This contract strengthens the host-side packaging boundary but does not satisfy the unchecked real-device items in [`../BETA_RELEASE_GATE.md`](../BETA_RELEASE_GATE.md). A public Beta remains blocked until the exact AC2003 candidate passes the complete physical gate and a later final manual release review explicitly approves publication.
