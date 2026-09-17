# Safe Operator Workspace

KaliPhoneStudio includes a consolidated **offline operator workspace** for host diagnostics, device-profile inspection, recovery guidance and redacted support exports. This surface is intentionally non-destructive: it does not execute `adb`, `fastboot`, shell commands or physical-device probes.

The workspace exists to make the first real-device session easier to prepare and audit without weakening the physical release gate.

## Safety boundary

The operator workspace may:

- validate the local `BUILD_STATUS.json` ledger and version consistency;
- validate the complete device-profile catalog;
- bind an optional selected profile to the diagnostic report using the exact profile-file SHA-256;
- check whether `fastboot`, `adb` and `git` are discoverable on the host **without executing them**;
- show profile-driven recovery notes, forbidden partitions and required physical evidence;
- export one deterministic JSON support bundle with tool paths redacted.

It may **not**:

- identify or query a connected phone;
- execute Fastboot/ADB;
- select a rootfs storage target;
- authorize a persistent write;
- claim that a hardware subsystem works;
- grant Beta release credit.

Every exported bundle therefore keeps:

```text
physical_interaction_performed = false
hardware_verified              = false
beta_gate_credit                = false
```

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

## GUI

`python main.py` opens the PySide6 Safe Operator Workspace. The GUI keeps the same offline boundary and adds:

- validated profile selector;
- profile detail view;
- **Offline doctor** view;
- **Recovery guide** view;
- **Export diagnostics…** action;
- project-local KaliPhoneStudio icon and SWIR dark/electric-cyan styling.

The GUI imports PySide6 lazily so CLI and CI remain usable on minimal hosts without Qt installed.

## Relationship to physical bring-up

This workspace is preparation/support tooling. A successful doctor report or clean diagnostics export does **not** advance physical support. The first AC2003 Beta still requires the real chain documented in [`../BETA_RELEASE_GATE.md`](../BETA_RELEASE_GATE.md): exact phone/firmware identification, matching stock `boot.img`, temporary boot, rescue/log evidence, Kali early userspace, required storage/power/hardware checks, exercised recovery and the final reviewed release manifest/checksums.

The dedicated physical/evidence scripts keep their existing confirmation and review boundaries. The operator workspace does not bypass or replace them.
