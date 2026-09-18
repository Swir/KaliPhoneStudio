# Safe Operator Workspace

KaliPhoneStudio includes a consolidated **offline operator workspace** for host diagnostics, device-profile inspection, recovery guidance, redacted support exports and exact-file evidence processing. The default GUI remains intentionally non-destructive: it does not execute `adb`, `fastboot`, shell commands or physical-device probes. The shared `evidence` CLI group likewise performs no device I/O; it only processes evidence and transcripts that were captured through separately gated physical workflows.

The workspace exists to make the first real-device session easier to prepare and audit without weakening the physical release gate.

## Safety boundary

The operator workspace may:

- validate the local `BUILD_STATUS.json` ledger and version consistency;
- validate the complete device-profile catalog;
- bind an optional selected profile to the diagnostic report using the exact profile-file SHA-256;
- check whether `fastboot`, `adb` and `git` are discoverable on the host **without executing them**;
- show profile-driven recovery notes, forbidden partitions and required physical evidence;
- export one deterministic JSON support bundle with tool paths redacted;
- parse an already captured rescue transcript into exact rescue-diagnostics evidence;
- bind an already captured bounded hardware-presence survey to exact rescue evidence;
- prepare rejected-by-default hardware/storage/test-plan/result-review records;
- bind exact review records/notes to exact survey, storage-discovery, functional-plan and functional-observation files;
- build a pending-only profile-driven functional test plan from accepted contextual survey review;
- prepare a not-executed/inconclusive observation template only after the exact plan has an accepted independent review;
- bind an operator-authored record from an already performed physical functional test to that exact plan/review chain;
- summarize independently reviewed functional results and freeze the exact plan/review/observation/result-review/summary files into a functional-result bundle.

It may **not**:

- identify or query a connected phone through the offline workspace/evidence group;
- execute Fastboot/ADB from the offline evidence group;
- perform the physical functional test represented by an observation record;
- select a rootfs storage target;
- authorize a persistent write;
- claim that a hardware subsystem works;
- grant Beta release credit.

Every offline workspace/evidence result therefore keeps the same non-promotion boundary:

```text
physical_interaction_performed = false
storage_target_selected         = false
persistent_write_authorized     = false
hardware_verified               = false
beta_gate_credit                = false
```

An observation evidence file may truthfully record `physical_test_executed=true` when the supplied operator record describes a test that was actually performed outside this offline command. That field is evidence about the earlier physical action; it never means the `evidence` CLI executed a phone command itself.

## CLI

### Validate the host/repository state

```bash
python main.py --doctor
```

Use a specific validated profile as context:

```bash
python main.py --doctor --profile-id oneplus/avicii
```

Machine-readable output:

```bash
python main.py --doctor --profile-id oneplus/avicii --json
```

Doctor results use three states:

- `pass` — the checked host/repository contract is satisfied;
- `warn` — the offline workspace can continue, but an optional/physical-session prerequisite such as a discoverable Fastboot executable is absent or outside the recorded CI matrix;
- `fail` — a fail-closed repository/profile/version contract is broken. The command exits non-zero.

Missing Fastboot is a warning rather than a false hardware failure because doctor mode does not communicate with a phone.

## Profile-driven recovery guidance

```bash
python main.py --recovery-guide --profile-id oneplus/avicii
```

JSON form:

```bash
python main.py --recovery-guide --profile-id oneplus/avicii --json
```

The guide is built from the selected `devices/<vendor>/<codename>/profile.json`. Device-specific forbidden partitions, required physical storage evidence and recovery notes therefore remain profile data rather than global AC2003 conditions.

The guide is advisory only. Even if a future profile contains a reviewed persistent strategy, the operator workspace itself does not turn that into write authorization.

## Deterministic diagnostics export

```bash
python main.py \
  --export-diagnostics operator-diagnostics.json \
  --profile-id oneplus/avicii \
  --json
```

The exported `kaliphonestudio-offline-operator-bundle` contains:

- application/version/platform/Python state;
- SHA-256 of the exact `BUILD_STATUS.json` bytes;
- selected profile ID and exact profile-file SHA-256 when a profile is selected;
- host-tool availability booleans;
- diagnostic check results and counts;
- current project progress and Beta-gate state from the repository ledger;
- the current repository Beta blocker list;
- optional profile-driven recovery guidance;
- explicit non-promotion/privacy assertions.

Absolute executable paths are intentionally not exported because they can reveal local usernames/home directories. The writer is atomic, refuses a symlink destination, and emits canonical sorted JSON so identical inputs produce identical bytes and SHA-256.

## Shared exact-file evidence CLI

The same entry point shipped as `KaliPhoneStudioCLI.exe` exposes an offline evidence group:

```bash
python main.py evidence --help
```

The group consolidates these review-gated stages:

```text
record-rescue-diagnostics
record-hardware-survey
prepare-hardware-survey-review
bind-hardware-survey-review
prepare-storage-review
bind-storage-review
build-functional-test-plan
prepare-functional-test-plan-review
bind-functional-test-plan-review
prepare-functional-test-observation
bind-functional-test-observation
prepare-functional-test-result-review
bind-functional-test-result-review
summarize-functional-test-results
build-functional-result-bundle
```

Examples:

```bash
python main.py evidence record-rescue-diagnostics \
  --profile-id oneplus/avicii \
  --observation-evidence physical-boot-observation.json \
  --console-transcript rescue-console.txt \
  --out physical-rescue-diagnostics.json
```

```bash
python main.py evidence prepare-storage-review \
  --discovery-evidence physical-storage-discovery.json \
  --reviewer reviewer-1 \
  --out physical-storage-review-record.json
```

```bash
python main.py evidence build-functional-test-plan \
  --profile-id oneplus/avicii \
  --hardware-review-evidence physical-hardware-review.json \
  --out physical-functional-test-plan.json
```

After the exact plan has a separate accepted review, create the safe observation template:

```bash
python main.py evidence prepare-functional-test-observation \
  --test-plan physical-functional-test-plan.json \
  --test-plan-review-evidence physical-functional-test-plan-review.json \
  --test-id display \
  --operator operator-1 \
  --out display-observation-record.json
```

The generated record is deliberately `inconclusive`, `physical_test_executed=false` and all required observation checks are false. It is only a template. The operator must physically perform the exact test outside this offline command, edit the record to match what was actually observed, keep separate notes, and then bind those exact files:

```bash
python main.py evidence bind-functional-test-observation \
  --test-plan physical-functional-test-plan.json \
  --test-plan-review-evidence physical-functional-test-plan-review.json \
  --test-id display \
  --observation-record display-observation-record.json \
  --observation-notes display-observation-notes.txt \
  --out display-observation-evidence.json
```

Independent result review stays a separate boundary:

```bash
python main.py evidence prepare-functional-test-result-review \
  --observation-evidence display-observation-evidence.json \
  --reviewer reviewer-2 \
  --out display-result-review-record.json
```

After the review record and notes are completed, bind them and then build the aggregate exact-plan summary. Repeat `--review-evidence` for each reviewed test:

```bash
python main.py evidence bind-functional-test-result-review \
  --observation-evidence display-observation-evidence.json \
  --review-record display-result-review-record.json \
  --review-notes display-result-review-notes.txt \
  --out display-result-review-evidence.json

python main.py evidence summarize-functional-test-results \
  --test-plan physical-functional-test-plan.json \
  --review-evidence display-result-review-evidence.json \
  --out physical-functional-test-summary.json
```

Finally, freeze the exact campaign into one non-promoting result bundle. Repeat `--observation-evidence` and `--review-evidence` for every included test:

```bash
python main.py evidence build-functional-result-bundle \
  --test-plan physical-functional-test-plan.json \
  --test-plan-review-evidence physical-functional-test-plan-review.json \
  --observation-evidence display-observation-evidence.json \
  --review-evidence display-result-review-evidence.json \
  --summary-evidence physical-functional-test-summary.json \
  --out physical-functional-result-bundle.json
```

All output paths are create-only. Missing, detached, non-canonical or invalid upstream evidence fails closed before a new evidence file is written. Review templates start rejected with checks false. A generated functional plan contains pending tests only. These commands do not capture the phone themselves and cannot transform host-side processing into hardware/Beta verification.

Physical capture and the explicitly authorized temporary-boot command remain separate top-level commands with their existing confirmation boundaries. The offline `evidence` group never calls them internally.

## GUI

`python main.py` opens the PySide6 Safe Operator Workspace. The GUI keeps the offline boundary and adds:

- validated profile selector;
- profile detail view;
- **Offline doctor** view;
- **Recovery guide** view;
- **Export diagnostics…** action;
- project-local KaliPhoneStudio icon and SWIR dark/electric-cyan styling.

The GUI imports PySide6 lazily so CLI and CI remain usable on minimal hosts without Qt installed. Exact-file evidence stages currently live in the shared CLI so explicit filenames/review records remain visible and auditable; a future GUI front-end must preserve the same confirmation and review boundaries rather than hide them.

## Windows verification

The Windows host package continues to build both GUI and console `onedir` artifacts. The dedicated `operator-evidence-workspace` workflow additionally builds the frozen CLI on Windows and verifies that the evidence command group is present, the rescue/storage/functional help surfaces carry their safety wording, and representative missing-input cases across plan/observation/result/bundle stages exit fail-closed without creating output files.

This is host-package verification only. It does not count as a physical AC2003 test or a Beta gate pass.

## Relationship to physical bring-up

This workspace is preparation/support tooling. A successful doctor report, clean diagnostics export, valid offline evidence transform, complete functional result bundle or green frozen-Windows test does **not** advance physical support. The first AC2003 Beta still requires the real chain documented in [`../BETA_RELEASE_GATE.md`](../BETA_RELEASE_GATE.md): exact phone/firmware identification, matching stock `boot.img`, temporary boot, rescue/log evidence, Kali early userspace, required storage/power/hardware checks, exercised recovery and the final reviewed release manifest/checksums.

The dedicated physical capture/execution commands keep their existing confirmation boundaries. The shared evidence workspace consolidates only offline exact-file transformations and does not bypass or replace any physical review gate.
