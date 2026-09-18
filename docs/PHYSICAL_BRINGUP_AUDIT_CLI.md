# Physical bring-up audit CLI

KaliPhoneStudio exposes the late physical-evidence audit stages through the same source/frozen-Windows `evidence` command group used for rescue, storage and functional-test evidence.

This surface is deliberately **offline-only**. It consumes exact files that already exist. It does not connect to a phone, execute ADB/Fastboot, select a rootfs target, mount/decrypt storage, authorize a persistent write, claim hardware support or authorize a Beta release.

## Safety boundary

Every command in this document keeps these non-promotion assertions:

```text
physical_interaction_performed = false
external_device_command_executed = false
storage_target_selected = false
persistent_write_authorized = false
phone_storage_written = false
hardware_verified = false
beta_release_authorized = false
beta_gate_credit = false
```

The commands are audit/binding helpers for evidence created by separately gated real-device work. A complete dossier or cross-campaign audit is **manual release-gate input only**.

## 1. Bind one physical bring-up session

After the exact physical candidate, temporary boot/rescue chain and physical storage discovery/review already exist:

```bash
python main.py evidence bind-bringup-session \
  --candidate-gate physical-candidate-gate.json \
  --boot-observation physical-boot-observation.json \
  --rescue-diagnostics physical-rescue-diagnostics.json \
  --functional-probes physical-rescue-functional-probes.json \
  --storage-discovery physical-storage-discovery.json \
  --storage-review physical-storage-review.json \
  --out physical-bringup-session.json
```

If the same physical run also has exact Kali early-userspace evidence, add:

```text
--kali-early-userspace physical-kali-early-userspace.json
```

The binder rejects detached profile/serial/firmware/candidate/rescue/storage chains. It never chooses a storage target or makes a write path ready.

## 2. Freeze the exact bring-up dossier

A dossier verifies the canonical session and every exact evidence/raw file named by that session:

```bash
python main.py evidence build-bringup-dossier \
  --session physical-bringup-session.json \
  --candidate-gate physical-candidate-gate.json \
  --boot-observation physical-boot-observation.json \
  --rescue-diagnostics physical-rescue-diagnostics.json \
  --functional-probes physical-rescue-functional-probes.json \
  --storage-discovery physical-storage-discovery.json \
  --storage-review physical-storage-review.json \
  --rescue-transcript rescue-console.txt \
  --storage-discovery-report physical-storage-discovery-report.json \
  --recovery-plan recovery-plan.txt \
  --storage-review-record physical-storage-review-record.json \
  --storage-review-notes physical-storage-review-notes.txt \
  --out physical-bringup-dossier.json
```

When the session contains Kali early-userspace evidence, the corresponding evidence **and** raw transcript must be supplied together. Optional `--rootfs-artifact` performs streaming SHA-256/size verification of the exact reviewed rootfs artifact without loading the entire image into memory.

The dossier stores role, size, digest and canonical-JSON policy, not local absolute paths.

## 3. Reverify after copy/archive/transfer

Before manual review, independently verify the exact dossier file set again:

```bash
python main.py evidence verify-bringup-dossier \
  --dossier physical-bringup-dossier.json \
  --file physical_bringup_session=physical-bringup-session.json \
  --file physical_candidate_gate=physical-candidate-gate.json \
  --file physical_boot_observation=physical-boot-observation.json \
  --file rescue_diagnostics=physical-rescue-diagnostics.json \
  --file rescue_functional_probe=physical-rescue-functional-probes.json \
  --file physical_storage_discovery=physical-storage-discovery.json \
  --file physical_storage_review=physical-storage-review.json \
  --file rescue_transcript=rescue-console.txt \
  --file storage_discovery_report=physical-storage-discovery-report.json \
  --file recovery_plan=recovery-plan.txt \
  --file storage_review_record=physical-storage-review-record.json \
  --file storage_review_notes=physical-storage-review-notes.txt \
  --out physical-bringup-dossier-verification.json
```

Repeat `--file ROLE=PATH` exactly once for every role recorded by the dossier, including optional Kali early-userspace/rootfs roles when present. Missing, extra, duplicate, substituted, symlinked or changed files fail closed.

## 4. Prepare and bind independent dossier review

Create rejected-by-default templates:

```bash
python main.py evidence prepare-bringup-dossier-review \
  --dossier physical-bringup-dossier.json \
  --reviewer reviewer-1 \
  --record-out physical-bringup-dossier-review-record.json \
  --notes-out physical-bringup-dossier-review-notes.txt
```

The record starts `decision=rejected`, with every substantive review check false and all target/path/write flags false. The reviewer must inspect the exact physical identity, firmware/stock boot, candidate authority chain, rescue chain, storage review chain, exact file set and recovery plan before changing the record.

Bind the completed exact record and notes:

```bash
python main.py evidence bind-bringup-dossier-review \
  --dossier physical-bringup-dossier.json \
  --verification physical-bringup-dossier-verification.json \
  --review-record physical-bringup-dossier-review-record.json \
  --review-notes physical-bringup-dossier-review-notes.txt \
  --out physical-bringup-dossier-review.json
```

Even `accepted_for_strategy_review=true` means only that a **later separate** rootfs strategy review may use this dossier. Target selection, storage-path binding and write authorization remain false.

## 5. Cross-bind bring-up and functional campaigns

After the real functional campaign has separately produced the exact accepted plan review and exact functional-result bundle, build the cross-campaign audit:

```bash
python main.py evidence build-release-gate-audit \
  --dossier physical-bringup-dossier.json \
  --dossier-verification physical-bringup-dossier-verification.json \
  --dossier-review physical-bringup-dossier-review.json \
  --functional-result-bundle physical-functional-result-bundle.json \
  --test-plan physical-functional-test-plan.json \
  --test-plan-review physical-functional-test-plan-review.json \
  --out physical-release-gate-audit.json
```

The audit fail-closes on profile/device drift and cross-checks the exact physical boot observation, rescue diagnostics, raw rescue transcript, rescue probe and functional-hardware contract between the bring-up/storage and functional-test campaigns.

Even if every applicable Beta-required functional test is independently reviewed as passing, the audit intentionally keeps:

```text
manual_release_gate_review_required = true
physical_gate_still_incomplete = true
beta_release_authorized = false
beta_gate_credit = false
```

The remaining physical requirements in [`../BETA_RELEASE_GATE.md`](../BETA_RELEASE_GATE.md) must still be manually satisfied before any Beta release.

## Frozen Windows verification

The dedicated `operator-bringup-evidence-workspace` workflow builds the real `KaliPhoneStudioCLI.exe` and checks that the late evidence commands are present after PyInstaller freezing. It also verifies representative missing/detached input cases fail closed and create no output.

A green Windows workflow proves the **host CLI package**, not the phone. It grants no physical AC2003 or Beta credit.
