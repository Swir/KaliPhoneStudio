# KaliPhoneStudio Roadmap

**Current development line — 0.6.57-dev**

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress intentionally does not rise for host-only plumbing when the physical-device risk gates remain unchanged.

## Milestone A — multi-device core and provenance — COMPLETE host-side

- [x] Device-independent `kaliphonestudio/` core.
- [x] `devices/<vendor>/<codename>/profile.json` runtime registry/schema contract.
- [x] Profile-driven identity, confirmation token, partition/boot constraints and test contract.
- [x] Profile hooks restricted to explicitly registered in-process callbacks; no profile shell injection.
- [x] Exact source/tool locking and checksum/object provenance.
- [x] Read-only Fastboot baseline evidence and exact tool identity.
- [x] Exact OTA/payload/stock-boot provenance and physical-baseline bundle.
- [x] Guarded temporary-boot authorization/execution path with no persistent write.

## Milestone B — reproducible first-boot ingredients — COMPLETE host-side

- [x] Reviewed Kali ARM64 rootfs authority (`35158577624`).
- [x] Reviewed avicii kernel authority (`35183670399`).
- [x] Reviewed avicii DTB/DTBO authority (`35196447576`).
- [x] Exact candidate binding across kernel/rootfs/device-tree authorities.
- [x] Deterministic boot-image assembly and round-trip verification.
- [x] Deterministic rescue initramfs and static ARM64 payload reproducibility.
- [x] Deterministic first-boot provisioning foundation with locked root and remote access disabled.

## Milestone C — physical bring-up evidence — IN PROGRESS

Host-side preparation now complete:

- [x] Rescue `init-reached` marker + deterministic rescue probe id.
- [x] Offline transcript binding to one successful non-persistent temporary boot.
- [x] Read-only rescue sysfs diagnostics.
- [x] Explicit manual-only bounded block-read and paired battery probes.
- [x] Deterministic Kali-rootfs/systemd early-userspace proof overlay bound to exact candidate/rootfs authority identity.
- [x] Physical transcript evidence contract requiring exact stage/probe/manifest/rootfs-authority/rootfs-artifact markers while keeping automatic hardware/Beta credit false.
- [x] **0.6.55:** discovery-only, source-pinned rootfs handoff contract that binds one exact physical-candidate gate to one exact reviewed rootfs authority without selecting a device path or authorizing writes.
- [x] **0.6.55:** exact pinned avicii `fstab.qcom` blob verification in CI plus policy checks that keep A/B/system/super/metadata partitions forbidden during discovery.
- [x] **0.6.56:** typed physical-storage discovery report/evidence contract bound to the exact handoff assessment, rescue diagnostics/functional probe, transcript/probe identity and reviewed rootfs chain.
- [x] **0.6.56:** whole-block topology must cross-match exact rescue `KPS_DIAG_BLOCK` name/sector/removable observations; filesystem/encryption/free-space remain typed partition-role observations, never a target path.
- [x] **0.6.56:** exact discovery-report bytes and a separate recovery-plan file are SHA-256 bound; a complete set can become review-ready but all target/write/storage/recovery/hardware/Beta claims remain false.
- [x] **0.6.57:** safe operator template generator pre-fills only already-bound whole-block rescue topology and leaves filesystem/encryption/free-space explicitly unknown until genuinely observed.
- [x] **0.6.57:** template output is strict-schema revalidated and immutable, and cannot express `/dev/...`, target selection, a mount/staging target or write authorization.

Still physically blocked:

- [ ] Capture real AC2003 Fastboot/OxygenOS baseline.
- [ ] Validate matching stock `boot.img` from the exact physical firmware OTA.
- [ ] Instantiate one exact physical first-boot candidate.
- [ ] Generate the operator discovery template from the exact physical rescue evidence, fill only real read-only filesystem/encryption/free-space observations, bind the recovery plan and record the typed discovery evidence.
- [ ] Manually review that exact discovery evidence; `discovery_ready_for_manual_review=true` is not itself approval.
- [ ] Select and review a safe, reversible rootfs staging/handoff target **after** reviewed physical evidence exists; no guessed UFS/userdata path.
- [ ] Execute explicitly confirmed temporary boot on the exact AC2003.
- [ ] Capture usable console/log evidence and manually review rescue markers.
- [ ] Reach the exact reviewed Kali rootfs and manually review the early-systemd marker chain.
- [ ] Verify required UFS/storage behavior beyond bounded diagnostic reads.
- [ ] Verify charging/battery safety for bring-up sessions.
- [ ] Verify display/touch or explicitly constrain Beta to reviewed console-only scope.
- [ ] Exercise recovery/rollback on the exact firmware baseline.

## Milestone D — hardware enablement

No item in this section may be marked complete from host CI alone.

- [ ] Display/framebuffer/DRM.
- [ ] Touch/input.
- [ ] USB host/device and rescue path.
- [ ] Wi-Fi.
- [ ] Bluetooth.
- [ ] Modem/telephony policy and safety scope.
- [ ] Audio.
- [ ] Sensors as required by supported scope.
- [ ] Power/charging/thermal behavior.
- [ ] Suspend/resume.
- [ ] UFS/storage integrity under the selected rootfs strategy.

## Milestone E — first working Beta

Required before release:

- [ ] All mandatory physical gates in `BETA_RELEASE_GATE.md` reviewed and recorded.
- [ ] Exact compatibility matrix and known issues.
- [ ] Release manifest with SHA-256 for every published binary/image.
- [ ] Recovery instructions validated on the exact supported firmware.
- [ ] Windows GUI/CLI path can reproduce/verify the supported flow without hidden manual substitutions.
- [ ] No empty/symbolic release; published assets must be the exact reviewed candidate.

## Milestone F — Stable

Stable requires a later, higher threshold: repeated device testing, stronger recovery confidence, broader hardware coverage, upgrade/rollback behavior and a materially lower known-risk surface than Beta.

## Immediate highest-impact work

1. Do **not** implement storage-target selection before real AC2003 evidence exists; the next target-selection milestone must consume a manually reviewed exact discovery record, never profile hints or a generated template.
2. Keep physical evidence acquisition read-only and auditable. When a real AC2003 is available, collect the Fastboot/OxygenOS baseline, validate the exact OTA/stock boot, instantiate the exact physical candidate, then generate/fill the storage-discovery template and bind the recovery plan.
3. Review rescue, storage-discovery and Kali-rootfs observations as separate evidence layers; success in one layer must never auto-promote another.
4. While hardware is unavailable, continue hardening verification/recovery/release tooling that can be proven host-side without inventing hardware success.
