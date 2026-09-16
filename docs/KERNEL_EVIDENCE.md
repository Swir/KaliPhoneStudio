# Kernel evidence workflow

KaliPhoneStudio treats a kernel candidate as a chain of exact, reviewable host-side evidence. This workflow is deliberately separate from hardware validation: a source lock, successful build or valid ARM64 `Image` does **not** prove that the kernel boots on a supported phone.

## Profile contract

Kernel knowledge belongs in `devices/<vendor>/<codename>/profile.json`. The common Python core does not hard-code the OnePlus Nord AC2003.

A kernel profile contract identifies:

- one exact upstream source from the profile `sources` list, pinned to a full 40-character commit;
- the expected kernel version;
- target architecture and output image name;
- defconfig and optional config fragments as safe relative paths;
- explicit build-variable inputs;
- required final `CONFIG_*` states.

The current `oneplus/avicii` host-side bring-up baseline pins LineageOS `android_kernel_oneplus_sm7250` commit `fb4b4374d3b9ad0f10ba38d159585129f092fb3d` and expects kernel `4.19.300`. It is a reviewed public source baseline, not yet the final hardware-verified AC2003 first-boot kernel.

## Evidence stages

1. `KernelBuildPlan` is created from the validated profile. It canonically binds the profile ID, exact source URL/commit, expected version, architecture, image name, config inputs, build variables and required config states.
2. `KernelCheckoutEvidence` verifies the checkout `HEAD`, parses the kernel version from the exact source `Makefile`, and hashes the selected defconfig/config fragments.
3. `KernelConfigEvidence` parses the generated final `.config`, rejects conflicting duplicate settings and requires every profile-declared `CONFIG_*` state.
4. `KernelImageEvidence` verifies the ARM64 Linux `Image` header magic and records the exact image SHA-256 and size.
5. `KernelCandidateEvidence` requires all three evidence records to reference the same profile and kernel-plan digest, then re-hashes the `Image` to detect post-verification drift.
6. The first-boot candidate manifest additionally requires the verified kernel SHA-256 and size to match the `kernel` input in the exact approved `BootBuildPlan` used for boot-image assembly.

This prevents source/config/image evidence from being mixed across profiles, build plans or artifacts.

## Offline verification CLI

The verifier does not invoke Fastboot and does not write a phone. Point it at an already checked-out exact source tree, the generated final `.config` and the built uncompressed ARM64 `Image`:

```bash
python scripts/verify_kernel_candidate.py \
  --profile-id oneplus/avicii \
  --checkout build/kernel/source \
  --config build/kernel/out/.config \
  --image build/kernel/out/arch/arm64/boot/Image \
  --out evidence/kernel-candidate.json
```

The command fails closed on source-commit drift, version drift, missing config material, final-config mismatch, malformed ARM64 image metadata, invalid hashes or artifact mutation. Successful output is canonical JSON suitable for SHA-256 binding into later candidate evidence.

## CI source-lock check

`.github/workflows/kernel-source-lock.yml` independently resolves the kernel plan from the device profile, fetches the exact pinned upstream commit, verifies `HEAD`, version and selected config material, then runs focused profile/kernel/candidate regression tests.

Passing this workflow proves only that the repository's host-side source lock and evidence contract are internally consistent. It does not satisfy any physical-device item in `BETA_RELEASE_GATE.md`.

## Hardware boundary

Before a public AC2003 Beta, KaliPhoneStudio still requires the exact physical firmware baseline, matching stock `boot.img`, a final reviewed kernel + DTB/DTBO candidate, successful temporary boot, useful rescue/log capture, proof that the kernel reaches Kali early userspace/rootfs, safe required storage and charging behavior, and an exercised recovery path.
