# Rootfs handoff policy

KaliPhoneStudio treats rootfs transport as a separate safety gate from kernel/rescue boot. A reproducible Kali ARM64 rootfs does not imply that any phone partition is a safe staging target.

## 0.6.55 discovery-only contract

`kaliphonestudio.rootfs_handoff` adds a device-independent, fail-closed contract that binds one exact physical candidate to one reviewed rootfs authority while deliberately refusing to select a block device, mount path or write target.

The profile contract must remain `state=discovery-only`, `target_selection_allowed=false` and `persistent_write_authorized=false`. The resulting assessment likewise records:

- `target_selected=false`;
- `storage_path_bound=false`;
- `write_authorized=false`;
- `handoff_ready=false`;
- `manual_review_required=true`;
- `hardware_verified=false`;
- `beta_gate_credit=false`.

This contract is preparation for physical discovery, not permission to copy or install the rootfs.

## Source-pinned avicii storage facts

The first profile derives its storage/encryption expectations from the exact pinned LineageOS device-tree commit `3f1270c2871e9893332073eb0f8f5f9499abbf13`. The exact source file is `init/fstab.qcom`, Git blob `20873c3a84e1e6e8d2483e313f561ad35ded7355`.

That pinned fstab describes:

- userdata as F2FS on UFS;
- `fileencryption=ice` and `wrappedkey` for userdata;
- metadata as a separate ext4 partition and the metadata-encryption key directory below `/metadata`;
- dynamic/system partitions with AVB/slot selection and read-only system-side expectations.

The same pinned `BoardConfig.mk` declares a metadata partition, A/B partitions, a super/dynamic-partition layout and AVB. These facts are strong reasons not to assume that Android userdata will be unlocked, mountable or safe for rootfs staging from a non-Android early userspace.

## What the profile may describe

A profile may contain source-pinned **hints** needed for physical discovery:

- exact layout source name, commit-relative path and Git blob identity;
- storage bus identifier;
- a partition *hint* whose real topology still has to be discovered;
- expected filesystem/encryption feature tokens;
- metadata partition identifier;
- mandatory physical evidence categories;
- partitions that remain forbidden during discovery.

It may not contain an approved raw block path or authorize persistent writes. The contract rejects unknown fields so a new `block_path`, mount target or write switch cannot be smuggled into profile JSON without corresponding reviewed code.

For discovery-only policy, every declared A/B partition plus the `super` container remains forbidden. Metadata is also forbidden because it participates in encryption/recovery state. The avicii `userdata` name is only a discovery hint, not an approved staging target.

## Required physical evidence before target selection

At minimum the exact phone/firmware must provide reviewed evidence for:

1. block topology;
2. filesystem identity;
3. encryption/unlock state;
4. available free space;
5. a concrete recovery/rollback plan.

The rootfs handoff assessment is bound to the exact `PhysicalCandidateGateEvidence` and exact reviewed `RootfsAuthorityRecord`. Any rootfs digest mismatch, prior phone-storage write, already-executed temporary boot, missing reviewed-authority binding or hardware/Beta claim fails closed.

## Upstream source locking

The focused `rootfs-handoff-policy` workflow performs two separate checks:

1. offline contract tests across every repository device profile;
2. an exact checkout of the pinned avicii device-source commit, followed by Git-object verification that `init/fstab.qcom` is the profile-declared blob and the tracked checkout is clean.

The generated source evidence is explicitly non-release evidence. It proves only which upstream storage-layout file informed the policy.

## What still blocks physical Kali rootfs handoff

0.6.55 does **not** choose a storage strategy. A later reviewed milestone must consume real AC2003 storage/encryption/recovery evidence and select a reversible method. Until then KaliPhoneStudio will not generate a target path, mount instruction or write authorization from the common core.

A successful rescue boot or early-systemd marker does not change this rule.
