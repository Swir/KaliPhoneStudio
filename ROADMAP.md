# KaliPhoneStudio Roadmap

Current development line — 0.6.65-dev

**58% complete**

```text
[█████████████████████████████---------------------] 58%
```

<div align="center">
  <img src="assets/readme/progress-mini.svg" alt="KaliPhoneStudio compact roadmap progress dashboard" width="900" />
</div>

**Roadmap dashboard:** **58.0%** — **BLOCKED** · **Host authorities: 3/3 reviewed** · Beta readiness: **BLOCKED**.

The compact dashboard is generated from the same authoritative `BUILD_STATUS.json` ledger as the README card. Fill width is `track_width × project_progress_percent / 100`; raw checkboxes are not interpreted as equal-weight work, and Beta readiness remains a separate gate.

> Progress is an internal reviewed roadmap ledger, not an estimate of remaining calendar time. A host-side milestone does not imply physical hardware support.

## Milestone A — multi-device host foundation — complete for current scope

- [x] Python package `kaliphonestudio` and profile registry.
- [x] Profile-scoped identity/serial verification and confirmation token.
- [x] Profile-driven boot/partition/recovery/test contracts.
- [x] First profile: `oneplus/avicii` / OnePlus Nord AC2003.
- [x] Generic safety/temporary-boot paths avoid global AC2003 hard-coding where device policy can be profile-driven.
- [x] Source/tool locking and provenance contracts.
- [x] Python 3.11–3.14 CI matrix.

## Milestone B — reproducible host candidate foundation — complete for current scope

- [x] Exact Kali ARM64 rootfs source lock, canonicalization, reproducibility evidence and reviewed authority.
- [x] Exact kernel source/toolchain lock, normalized build inputs, reproducibility evidence and reviewed authority.
- [x] Exact DTB/DTBO source/build binding, reproducibility evidence and reviewed authority bound to the reviewed kernel.
- [x] First-boot candidate authority bundle binds reviewed rootfs/kernel/device-tree state.
- [x] Boot image inspection/round-trip/size contracts fail closed.
- [x] Deterministic rescue payload and probe identity.
- [x] Exact Kali early-userspace proof overlay and markers.

## Milestone C — physical AC2003 bring-up — in progress / blocked on real hardware evidence

Host-side contracts are prepared, but **none of the items below may be promoted from host-only or synthetic evidence**.

- [x] Read-only Fastboot baseline capture/import tooling.
- [x] Exact physical stock-baseline/candidate gate contracts.
- [x] Serial/profile/firmware/candidate-bound one-shot temporary-boot execution path with explicit confirmation.
- [x] Physical rescue observation, exact rescue probe markers and bounded read-only diagnostics.
- [x] Bounded hardware-presence survey with no subsystem activation.
- [x] Exact manual contextual review of the hardware survey.
- [x] Profile-driven pending-only functional-hardware test plan.
- [x] 0.6.63 independent exact plan-file manual review before physical execution.
- [x] 0.6.64 schema-v2 per-test observation contract requires that accepted exact plan review and carries its plan-file/review-record/review-notes identities into every later physical observation.
- [x] Independent per-test result review and exact-plan status summary remain separate from project support/Beta promotion.
- [x] 0.6.65 exact-file functional result bundle cross-binds the canonical plan, accepted plan review, schema-v2 observations, result reviews and freshly recomputed summary without granting support/hardware/Beta credit.
- [x] Discovery-only rootfs-handoff policy and exact pinned storage-layout source validation.
- [x] Typed physical storage discovery evidence contract.
- [x] Manual physical-storage review contract.
- [x] Cross-bound physical bring-up session evidence contract.
- [x] Exact-file physical bring-up dossier + independent dossier review.
- [ ] Capture a real AC2003 Fastboot/OxygenOS baseline and exact firmware fingerprint.
- [ ] Extract/validate matching stock `boot.img` from the exact OTA.
- [ ] Review/instantiate the exact physical candidate for that real baseline.
- [ ] Complete real temporary `fastboot boot` and capture the phone-side rescue markers.
- [ ] Capture and accept a real hardware survey review from the exact candidate.
- [ ] Generate and accept the exact functional-test plan review for that physical context.
- [ ] Execute and independently review every applicable Beta-required schema-v2 functional test observation.
- [ ] Freeze the exact real plan/plan-review/observations/result-reviews/summary into one functional result bundle for manual release-gate review.
- [ ] Capture and accept storage/encryption/free-space/recovery evidence from the real phone.
- [ ] Review the exact physical bring-up session and source-file dossier.
- [ ] Select/review an actual reversible rootfs staging/handoff strategy only after accepted physical storage evidence and dossier review.
- [ ] Confirm intended Kali early userspace/rootfs on the physical run.
- [ ] Validate required UFS/storage behavior beyond bounded diagnostic reads.
- [ ] Validate safe charging/battery behavior for the supported scope.
- [ ] Validate display/touch, or explicitly review/document a console-only Beta scope.
- [ ] Validate required USB/rescue behavior.
- [ ] Exercise recovery/rollback on the exact physical baseline.

## Milestone D — rootfs handoff and user-space integration — gated by Milestone C evidence

- [x] Deterministic Kali early-userspace proof overlay exists host-side.
- [x] Exact rootfs authority/candidate identities are available for physical proof.
- [x] Profile-driven discovery expectations exist without selecting a guessed `/dev/...` path.
- [ ] Choose the real reversible staging/handoff target only after reviewed physical storage evidence.
- [ ] Make the exact reviewed Kali rootfs available through that approved strategy.
- [ ] Confirm systemd early userspace on the physical phone.
- [ ] Integrate/validate Phosh for the declared release scope.
- [ ] Validate persistent configuration without violating rollback/recovery policy.

## Milestone E — subsystem bring-up

Each subsystem requires real physical evidence before it can be called working.

- [ ] UFS/storage.
- [ ] Display.
- [ ] Touch.
- [ ] USB/rescue.
- [ ] Wi-Fi.
- [ ] Bluetooth.
- [ ] Modem/cellular.
- [ ] Audio.
- [ ] Charging/battery.
- [ ] Suspend/resume and broader power behavior.
- [ ] Thermal behavior.

## Milestone F — host application and operator UX

- [x] Current Python host application and profile registry foundation.
- [x] Fail-closed evidence/operator CLI paths for baseline, candidate, temporary boot, rescue, storage and functional-hardware review.
- [ ] Consolidate the safety/evidence flow into a polished Windows GUI/CLI without bypassing explicit confirmation boundaries.
- [ ] Add clearer diagnostics export and guided recovery workflow.
- [ ] Package Windows executable only after the CLI safety contracts stay equivalent under packaging.

## Milestone G — Beta release

- [x] [`BETA_RELEASE_GATE.md`](BETA_RELEASE_GATE.md) exists and separates host-side from physical mandatory checks.
- [x] 0.6.64 deterministic SWIR Progress SVG PRO card/mini/template are generated from the authoritative project ledger; they are presentation only and grant no release credit.
- [ ] Every applicable mandatory physical AC2003 gate is passed and manually reviewed.
- [ ] Exact release manifest + SHA-256 set is generated from the reviewed physical candidate.
- [ ] Compatibility matrix and known issues reflect only physically verified scope.
- [ ] Real binaries/images and instructions are attached to the exact candidate GitHub prerelease.
- [ ] Publish first Beta.

## Milestone H — Stable

Stable requires a later, higher threshold than Beta, including wider repeat testing, rollback confidence and declared supported hardware behavior. A Beta success does not automatically satisfy Stable.

## Progress presentation contract

KaliPhoneStudio follows `SWIR-PROGRESS-SVG-PRO:v1` for the README/roadmap visual dashboard:

- authoritative numeric source: `BUILD_STATUS.json -> project_progress_percent`;
- measured scope: **Current project roadmap**;
- fill geometry: `track_width × project_progress_percent / 100`;
- current host-authority counter: the three reviewed reproducibility authority state fields in `BUILD_STATUS.json`;
- unknown/unverifiable progress renders **N/A**, never fabricated `0%`/`100%`;
- project progress and Beta release readiness are separate signals;
- the protected text bar and percent remain human-readable fallbacks.

## Immediate next work

The highest-value next step is **real physical AC2003 evidence**, not another guessed block-device target. With the physical phone available, run the established baseline → stock boot provenance → candidate → temporary rescue boot → accepted survey review → accepted exact plan review → schema-v2 observations/reviews → exact functional result bundle → storage review/dossier chain. Only then design and review the reversible rootfs handoff target for that exact device state.
