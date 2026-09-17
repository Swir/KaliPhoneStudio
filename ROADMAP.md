# KaliPhoneStudio Roadmap

**Current development line — 0.6.61-dev**

**58% complete**

`███████████▋░░░░░░░░ 58%`

Progress intentionally does not rise for host-only plumbing while the physical-device risk gates remain unchanged.

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
- [x] **0.6.60:** bounded automatic sysfs-only hardware-presence survey covering USB UDC/device identity, network interfaces, rfkill, sound, thermal, input, framebuffer/DRM and power-supply state without activating those subsystems.
- [x] **0.6.61:** fail-closed manual hardware-survey review contract binds the exact survey to canonical review-record bytes and separate notes.
- [x] **0.6.61:** contextual acceptance requires a non-empty survey plus explicit physical-context, integrity, USB, network/radio, audio, input/display, thermal/power and limitations review; all functional/hardware/Beta flags remain false.
- [x] Deterministic Kali-rootfs/systemd early-userspace proof overlay bound to exact candidate/rootfs authority identity.
- [x] Physical transcript evidence contract requiring exact stage/probe/manifest/rootfs-authority/rootfs-artifact markers while keeping automatic hardware/Beta credit false.
- [x] **0.6.55:** discovery-only, source-pinned rootfs handoff contract bound to exact physical candidate and reviewed rootfs authority without target selection or write authorization.
- [x] **0.6.56:** typed physical-storage discovery report/evidence bound to exact rescue/rootfs chain, report bytes and recovery-plan digest.
- [x] **0.6.57:** fail-closed manual storage-review record bound to exact discovery evidence, review record and notes.
- [x] **0.6.58:** immutable physical bring-up session cross-binds candidate, rescue, storage discovery/review and optional Kali early-userspace evidence.
- [x] **0.6.59:** exact-file physical bring-up dossier verifies the canonical session and all bound original evidence/raw files by SHA-256 and size.
- [x] **0.6.59:** post-transfer dossier reverification and a separate manual dossier-review gate keep target/write/hardware/Beta claims false.

Still physically blocked:

- [ ] Capture real AC2003 Fastboot/OxygenOS baseline.
- [ ] Validate matching stock `boot.img` from the exact physical firmware OTA.
- [ ] Instantiate one exact physical first-boot candidate.
- [ ] Capture the real bounded hardware-presence survey and bind an accepted-as-context manual review; contextual acceptance still gives no functional credit.
- [ ] Capture real physical block topology, filesystem identity, encryption state, free-space evidence and recovery plan under the typed discovery contract.
- [ ] Complete and bind a manual review of that exact storage discovery; `accepted_for_strategy_design=true` is not target approval.
- [ ] Cross-bind real candidate/rescue/storage records into one physical bring-up session.
- [ ] Build, independently reverify and manually review the exact-file dossier from that real session.
- [ ] Select and separately review a safe, reversible rootfs staging/handoff target only after accepted physical discovery/dossier review; no guessed UFS/userdata path.
- [ ] Execute explicitly confirmed temporary boot on the exact AC2003.
- [ ] Capture usable console/log evidence and manually review rescue markers.
- [ ] Reach the exact reviewed Kali rootfs and manually review the early-systemd marker chain.
- [ ] Verify required UFS/storage behavior beyond bounded diagnostic reads.
- [ ] Verify charging/battery safety for bring-up sessions.
- [ ] Verify display/touch or explicitly constrain Beta to reviewed console-only scope.
- [ ] Exercise recovery/rollback on the exact firmware baseline.

## Milestone D — hardware enablement

No item here may be marked complete from host CI, sysfs presence or contextual review alone.

- [ ] Display/framebuffer/DRM.
- [ ] Touch/input.
- [ ] USB host/device and rescue path.
- [ ] Wi-Fi.
- [ ] Bluetooth.
- [ ] Modem/telephony policy and safety scope.
- [ ] Audio.
- [ ] Sensors required by supported scope.
- [ ] Power/charging/thermal behavior.
- [ ] Suspend/resume.
- [ ] UFS/storage integrity under the selected rootfs strategy.

## Milestone E — first working Beta

Required before release:

- [ ] All mandatory physical gates in `BETA_RELEASE_GATE.md` reviewed and recorded.
- [ ] Exact compatibility matrix and known issues.
- [ ] Release manifest with SHA-256 for every published binary/image.
- [ ] Recovery instructions validated on the exact supported firmware.
- [ ] Windows GUI/CLI path can reproduce/verify the supported flow without hidden substitutions.
- [ ] No empty/symbolic release; published assets must be the exact reviewed candidate.

## Milestone F — Stable

Stable requires repeated device testing, stronger recovery confidence, broader hardware coverage, upgrade/rollback behavior and a materially lower known-risk surface than Beta.

## Immediate highest-impact work

1. Keep rescue diagnostics, hardware survey/review, storage discovery/review, session and dossier layers fail-closed; none may convert observed presence into functional support or authorize a storage write.
2. Do **not** implement storage-target selection before a real AC2003 discovery record has passed exact manual review and dossier audit.
3. When a physical AC2003 is available, capture the real read-only Fastboot/OxygenOS baseline first, validate the exact OTA/stock boot, instantiate the exact physical candidate, then collect rescue marker/diagnostic/hardware-survey evidence and manual reviews before any persistent write.
4. Treat accepted hardware-survey context only as an input to later subsystem-specific functional tests; it must never mark display/touch/USB/Wi-Fi/Bluetooth/audio/modem/power/thermal as verified.
