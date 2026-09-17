# Rootfs handoff policy

KaliPhoneStudio treats rootfs transport as a separate safety gate from kernel/rescue boot. A reproducible Kali ARM64 rootfs does not imply that any phone partition is a safe staging target.

## Discovery-only handoff contract

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

## 0.6.56 typed physical storage discovery evidence

`kaliphonestudio.physical_storage_discovery` records the physical evidence required by the handoff contract while keeping discovery and target selection separate.

The evidence chain binds:

1. one exact `RootfsHandoffAssessmentEvidence`;
2. the exact rescue diagnostics and explicitly invoked functional-probe evidence from the same physical transcript/probe id;
3. the exact original bytes and SHA-256 of an operator storage-discovery JSON report;
4. the exact bytes/SHA-256 of a separate recovery-plan UTF-8 text file;
5. the exact physical-candidate/rootfs authority identities already carried by the handoff assessment.

The report schema deliberately has no field capable of expressing `/dev/block/...`, a mount target, a staging target or write authorization. Kernel block identifiers are bounded single tokens such as `sda`; partition references are semantic roles such as `userdata`.

Whole-block topology is cross-checked against the exact `KPS_DIAG_BLOCK=<name>|<sectors>|<removable>` records already captured by the rescue sysfs inventory. For avicii, review readiness additionally requires the UFS signal from the same exact rescue evidence chain. Filesystem, encryption and free-space observations are checked against profile expectations for the `userdata` role but do not convert that role into a path.

A complete matching set may set `discovery_ready_for_manual_review=true`. This means only that the record contains enough internally bound observations for a human review. The evidence still requires:

- `target_selected=false`;
- `storage_path_bound=false`;
- `write_authorized=false`;
- `handoff_ready=false`;
- `storage_verified=false`;
- `recovery_verified=false`;
- `phone_storage_written=false`;
- `manual_review_required=true`;
- `hardware_verified=false`;
- `beta_gate_credit=false`.

### Operator report shape

A report is strict schema-v1 JSON. Example values below are illustrative only and are **not** AC2003 evidence:

```json
{
  "schema_version": 1,
  "profile_id": "oneplus/avicii",
  "device_serial": "SERIAL_FROM_EXACT_PHYSICAL_CANDIDATE",
  "collection_policy": "operator-read-only-storage-discovery-v1",
  "block_devices": [
    {"kernel_name": "sda", "size_sectors": 0, "removable": false}
  ],
  "filesystems": [
    {"partition_role": "userdata", "kernel_name": "unknown", "filesystem": "unknown", "observed": false}
  ],
  "encryption": [
    {"partition_role": "userdata", "state": "unknown", "features": [], "observed": false}
  ],
  "free_space": [
    {"partition_role": "userdata", "total_bytes": null, "free_bytes": null, "observed": false}
  ],
  "phone_storage_written": false,
  "target_selected": false,
  "storage_path_bound": false
}
```

The example intentionally cannot become review-ready; real block sector counts must be positive and must match the bound rescue transcript. Unknown filesystem/encryption/free-space observations remain valid placeholders but do not satisfy their physical evidence categories.

Recorder:

```bash
python scripts/record_physical_storage_discovery.py \
  --profile-id oneplus/avicii \
  --handoff-assessment evidence/rootfs-handoff-assessment.json \
  --rescue-diagnostics evidence/physical-rescue-diagnostics.json \
  --functional-probes evidence/physical-rescue-functional-probes.json \
  --discovery-report evidence/operator-storage-discovery.json \
  --recovery-plan evidence/recovery-plan.txt \
  --out evidence/physical-storage-discovery.json
```

The recorder is offline. It does not run Fastboot/ADB, mount/decrypt storage, read new phone blocks, or perform any write.

## Required physical evidence before target selection

At minimum the exact phone/firmware must provide reviewed evidence for:

1. block topology;
2. filesystem identity;
3. encryption/unlock state;
4. available free space;
5. a concrete recovery/rollback plan.

The rootfs handoff assessment is bound to the exact `PhysicalCandidateGateEvidence` and exact reviewed `RootfsAuthorityRecord`. The 0.6.56 discovery evidence further binds that assessment to the exact rescue evidence chain and operator report/recovery plan. Any identity/digest drift, phone-storage write claim, path-like token, duplicate role, inconsistent unknown observation or hardware/Beta promotion fails closed.

## Upstream source locking

The focused `rootfs-handoff-policy` workflow performs:

1. offline handoff and physical-discovery contract tests across repository profiles;
2. compilation checks for the evidence/CLI surfaces;
3. an exact checkout of the pinned avicii device-source commit, followed by Git-object verification that `init/fstab.qcom` is the profile-declared blob and the tracked checkout is clean.

The generated source evidence is explicitly non-release evidence. It proves only which upstream storage-layout file informed the policy.

## What still blocks physical Kali rootfs handoff

0.6.56 does **not** choose a storage strategy. A later reviewed milestone must consume a **real, manually reviewed** AC2003 physical-storage discovery record and then select a reversible method. Until then KaliPhoneStudio will not generate a target path, mount instruction or write authorization from the common core.

A successful rescue boot, `discovery_ready_for_manual_review=true`, or early-systemd marker does not change this rule.
