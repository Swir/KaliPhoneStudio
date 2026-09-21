# Executable Phosh ARM64 rootfs build

KaliPhoneStudio now has a first-class **host build path** for a Phosh-capable ARM64 userspace. This is intentionally separate from the already reviewed minimal-rootfs authority: the minimal authority does not contain the full Phosh package contract and must not be presented as the graphical userspace candidate.

## Source and build locks

The build consumes two independent inputs:

- `tools/phosh-source-lock.json` — exact NetHunter Pro commit and reviewed Phosh recipes;
- `tools/phosh-rootfs-build-contract.json` — KaliPhoneStudio's executable ARM64/QCOM rootfs build parameters, bound to the canonical Phosh source-lock SHA-256.

The current source remains pinned to NetHunter Pro commit `8460a1faca1a00c2faf61d30c0f8354ea55cb518`. The executable path invokes `debos` directly on the pinned `rootfs.yaml`; it does **not** run upstream `build.sh`, select an upstream phone, or import an upstream kernel/boot image.

The base build is explicitly ARM64 + Phosh, uses `kali-rolling`, the reviewed Mobian suite, HTTPS Kali mirror, and the required contrib/non-free components. A second KaliPhoneStudio-owned Debos stage installs only the package list from the locked `devices/qcom/packages-phosh.yaml` userspace recipe. It deliberately does not consume `devices/qcom/packages-base.yaml`, so unsupported upstream Qualcomm kernel/device packages cannot silently become AC2003 support.

## Run one candidate leg

Use a clean checkout of the **exact** commit pinned by `tools/phosh-source-lock.json` with `debos` installed on a suitable Linux build host:

```bash
python scripts/run_locked_phosh_rootfs_build.py \
  --checkout /path/to/kali-nethunter-pro \
  --out out/phosh-rootfs-a.tar.xz \
  --package-manifest out/phosh-rootfs-a.packages.tsv \
  --build-evidence out/phosh-rootfs-a.build.json \
  --canonicalization-evidence out/phosh-rootfs-a.canonicalization.json
```

The runner rejects the wrong Git commit or tracked source modifications, verifies the pinned Phosh template/recipes, builds the generic ARM64 Phosh rootfs without an upstream device image, adds only the locked QCOM Phosh userspace supplement, canonicalizes the archive, extracts the real dpkg package manifest, and refuses the result unless every locked Phosh package is installed.

## What this does **not** prove

A successful run is useful build output, but it is **not yet a reviewed reproducibility authority**. The build contract requires an independent A/B build before an authority can be reviewed. It also does not prove display, touch, GPU, modem, audio, suspend, charging, storage, rescue, or any other physical-phone function.

`hardware_verified` and `beta_gate_credit` therefore remain false. Physical AC2003 temporary boot and the existing Beta gate remain mandatory.
