# Physical Bring-up Exact-file Dossier

`kaliphonestudio.physical_bringup_dossier` is the final **offline audit packaging**
layer for one already-created physical bring-up session. It does not talk to a
phone and does not make any hardware decision.

## Why it exists

`PhysicalBringupSessionEvidence` cross-binds the semantic evidence chain. The
dossier adds a second guarantee: the files handed to a reviewer are the exact
bytes named by that session.

The dossier verifies:

- the canonical `physical-bringup-session.json` bytes;
- candidate-gate evidence;
- physical boot observation evidence;
- rescue diagnostics evidence;
- explicitly authorized rescue functional-probe evidence;
- physical storage discovery evidence;
- physical storage manual-review evidence;
- the raw rescue transcript;
- the raw storage discovery report;
- the raw recovery plan;
- the raw storage review record;
- the raw storage review notes;
- when the session contains Kali early-userspace evidence, both that evidence
  file and its raw transcript;
- optionally, the exact reviewed rootfs artifact by both SHA-256 and size.

Every file is read fail-closed as a regular non-symlink file with bounded size,
streaming SHA-256 and before/after metadata checks. The manifest is path
independent: it records roles, sizes and digests, not host absolute paths.

## Safety boundary

A valid dossier means only:

> one internally consistent byte set is ready for manual audit/archive review.

It does **not** mean:

- a storage target has been selected;
- a `/dev/...` path has been approved;
- a write is authorized;
- rootfs handoff is ready;
- storage or recovery is verified;
- hardware works;
- the Beta gate has passed.

Those fields remain hard-false in the dossier schema.

## Build a dossier

After a real physical session and its underlying evidence files exist:

```bash
python scripts/build_physical_bringup_dossier.py \
  --session evidence/physical-bringup-session.json \
  --candidate-gate evidence/physical-candidate-gate.json \
  --boot-observation evidence/physical-boot-observation.json \
  --rescue-diagnostics evidence/physical-rescue-diagnostics.json \
  --functional-probes evidence/physical-rescue-functional-probes.json \
  --storage-discovery evidence/physical-storage-discovery.json \
  --storage-review evidence/physical-storage-review.json \
  --rescue-transcript evidence/rescue-transcript.log \
  --storage-discovery-report evidence/operator-storage-discovery.json \
  --recovery-plan evidence/recovery-plan.txt \
  --storage-review-record evidence/operator-storage-review.json \
  --storage-review-notes evidence/operator-storage-review-notes.txt \
  --out evidence/physical-bringup-dossier.json
```

If the bound session contains Kali early-userspace evidence, both of these are
mandatory as a pair:

```text
--kali-early-userspace-evidence ...
--kali-early-userspace-transcript ...
```

`--rootfs-artifact` is optional. Supplying it causes the exact rootfs file to be
stream-hashed and size-checked against the session.

## Review order

1. Verify the dossier itself.
2. Confirm all expected file roles are present exactly once.
3. Review the candidate/baseline identity.
4. Review rescue transcript and probe identity.
5. Review storage discovery plus recovery plan.
6. Review the manual storage decision and notes.
7. If present, review Kali early-userspace markers independently.
8. Only after all physical evidence is accepted may a later, separate reversible
   rootfs-target/strategy review be designed.

The dossier never performs step 8 automatically.
