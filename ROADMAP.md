# KaliPhoneStudio Roadmap

**Current development line — 0.6.54-dev**

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
- [x] **0.6.54:** deterministic Kali-rootfs/systemd early-userspace proof overlay bound to exact candidate/rootfs authority identity.
- [x] **0.6.54:** physical transcript evidence contract requiring exact stage/probe/manifest/rootfs-authority/rootfs-artifact markers while keeping automatic hardware/Beta credit false.

Still physically blocked:

- [ ] Capture real AC2003 Fastboot/OxygenOS baseline.
- [ ] Validate matching stock `boot.img` from the exact physical firmware OTA.
- [ ] Instantiate one exact physical first-boot candidate.
- [ ] Select and review a safe, reversible, profile-driven rootfs staging/handoff strategy; do not hard-code a guessed UFS/userdata path.
- [ ] Execute explicitly confirmed temporary boot on the exact AC2003.
- [ ] Capture usable console/log evidence and manually review rescue markers.
- [ ] Reach the exact reviewed Kali rootfs and manually review the new early-systemd marker chain.
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

1. Design a safe rootfs **handoff/staging contract** that does not assume an unverified AC2003 partition/encryption layout.
2. Keep the proof overlay tied to exact reviewed authorities and integrate it only through a candidate path that preserves those identities.
3. When a physical AC2003 is available, collect the real read-only baseline before any boot/write action, then execute only the explicitly confirmed temporary-boot path.
4. Review physical rescue and Kali-rootfs markers separately; rescue success must never be treated as Kali-rootfs success.
