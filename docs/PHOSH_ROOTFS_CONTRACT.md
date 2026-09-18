# Phosh rootfs contract

KaliPhoneStudio treats Phosh as a **user-space integration target**, not as evidence that
display, touch, GPU, suspend, modem, audio or any other phone subsystem works.

## Pinned upstream reference

The host contract in `tools/phosh-source-lock.json` pins the public Kali NetHunter Pro
repository to commit:

`8460a1faca1a00c2faf61d30c0f8354ea55cb518`

At that exact commit the NetHunter Pro rootfs recipe defaults to `arm64` + `phosh` and
dispatches to `include/packages-{{ $environment }}.yaml`. KaliPhoneStudio additionally
locks the common Phosh recipe and the NetHunter Pro `qcom` Phosh recipe by SHA-256. The
lock records the exact package lists and the common recipe's `getty@.service` disable
action. CI downloads those exact immutable files and refuses any byte/package/service
drift.

This is deliberately a **reference-source lock**. It does not import NetHunter Pro
device support and it does not mean that its generic Qualcomm recipe supports
`oneplus/avicii`.

## Host-side verification

```bash
python scripts/verify_phosh_source_lock.py \
  --lock tools/phosh-source-lock.json \
  --source-root /path/to/kali-nethunter-pro-at-the-locked-commit
```

The verifier requires exactly the locked files, rejects symlinks, checks the SHA-256 of
each source file, confirms the rootfs template still defaults to ARM64 Phosh, and checks
that the parsed package/service contract still matches the lock.

`kaliphonestudio.phosh.evaluate_phosh_package_manifest()` can also evaluate the normalized
`package<TAB>version<TAB>architecture` manifest already produced by the rootfs pipeline.
It reports exact installed versions and missing packages. Even when every package is
present, the result only means **host userspace package contract satisfied**.

## Required separation of claims

A successful source/package check keeps all of these false:

- `display_verified`
- `touch_verified`
- `hardware_verified`
- `beta_gate_credit`

Physical AC2003 work is still mandatory. In particular, Phosh cannot be declared usable
until the exact reviewed physical candidate reaches the intended Kali rootfs and the
release scope's display/touch (or an explicitly accepted console-only scope), input,
power and recovery requirements are physically exercised.

## Next integration step

After real storage evidence selects and reviews a reversible rootfs handoff target, build
the Phosh-enabled ARM64 userspace from an explicitly reviewed repository snapshot, freeze
its rootfs/package-manifest identity, bind it to the existing rootfs/candidate authority,
and only then test it through the physical bring-up evidence chain.
