# Phosh rootfs first-boot assembly candidate

PR #132 builds two independent ARM64 Kali/Phosh rootfs candidates from the exact
pinned NetHunter Pro source lock. A successful A/B comparison proves that the
canonical rootfs artifact identity and normalized dpkg package manifest are
byte-identical across both builds, but that comparison deliberately remains
review input rather than a reviewed rootfs authority.

The `materialize-candidate` job closes the practical delivery gap after A/B
success. It keeps the exact build-A `tar.xz` payload long enough to verify it
against:

- the exact build-A evidence file;
- the exact A/B reproducibility-candidate evidence;
- the exact normalized package manifest; and
- the build-A origin recorded by the A/B comparison.

The output artifact is named:

`phosh-rootfs-first-boot-assembly-candidate`

It contains:

- `phosh-arm64-rootfs-candidate.tar.xz` — the exact verified rootfs payload;
- `phosh-packages.tsv` — the exact normalized installed-package manifest;
- `phosh-build-a.json` — the selected real-build evidence;
- `phosh-rootfs-reproducibility-candidate.json` — the independent A/B equality evidence;
- `phosh-rootfs-candidate-artifact.json` — the cross-binding record proving those bytes belong together.

## Local verification command

```bash
python scripts/prepare_phosh_rootfs_candidate_artifact.py \
  --rootfs phosh-a.tar.xz \
  --package-manifest phosh-packages.tsv \
  --build-evidence phosh-build.json \
  --reproducibility-candidate phosh-rootfs-reproducibility-candidate.json \
  --selected-origin "github-actions/OWNER/REPO/RUN/ATTEMPT/build-a" \
  --out phosh-rootfs-candidate-artifact.json
```

The command performs no device I/O. It streams the rootfs hash from a stable
regular-file descriptor, verifies the package manifest bytes and record count,
and cross-checks the selected build against the exact A/B candidate.

## What this does not prove

This artifact is a **first-boot assembly candidate**, not a release and not a
hardware-support claim. Its evidence always keeps:

- `reproducibility_authority=false`
- `physical_validation_required=true`
- `hardware_verified=false`
- `beta_gate_credit=false`

A later explicit review must create any Phosh reproducibility authority. The
physical AC2003 gate still requires the exact firmware baseline, matching stock
`boot.img`, safe temporary boot, rescue/logging, Kali early-userspace/rootfs
proof, charging/battery safety, storage validation, recovery/rollback, and the
required functional hardware checks before Beta can be authorized.
