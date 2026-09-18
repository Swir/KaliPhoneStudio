# Current physical observation admission gate

KaliPhoneStudio keeps historical physical evidence readable, but new rescue evidence must not be created from an observation shape that predates the current runtime/recovery integrity chain.

## Admission rule

`validate_physical_boot_observation_evidence()` intentionally accepts both schema-v1 and schema-v2 records so old evidence remains auditable. New rescue diagnostics use a stricter boundary: `require_current_physical_boot_observation_for_rescue()` requires schema-v2 before the profile or transcript is consumed.

The same gate now applies before recording new rescue functional-probe evidence. This closes a compatibility gap where a historical schema-v1 observation plus historical diagnostics could otherwise have been reused to seed a newly recorded functional-probe artifact. Rejection happens before diagnostics validation, profile access or transcript access.

A schema-v2 observation is already required to bind the successful one-shot temporary boot to the exact schema-v3 runtime probe, physical baseline, boot-identity binding, recovery-readiness record, matching stock `boot.img`, fresh Fastboot transcript and the post-probe exact-material revalidation policy.

This prevents a historical schema-v1 observation from being reused as the root of newly recorded rescue diagnostics or functional probes while preserving read-only historical inspection of existing evidence.

## Safety properties

The admission gate is offline. It does not invoke ADB, Fastboot, serial I/O, slot switching, flashing, erasing, mounting, decryption or any persistent write. Passing it only permits the existing bounded rescue transcript parsers to continue.

Passing the gate does **not** verify storage, display/touch, charging/battery, recovery, Kali early userspace, hardware support or Beta readiness. A successful functional-probe record remains a bounded signal that requires later physical review; all release-credit gates remain separate.

## CI contract

`.github/workflows/current-physical-observation-rescue-gate.yml` runs focused regression coverage on Python 3.11 and 3.14. It proves that historical schema-v1 observations still validate for audit/readback, that they cannot seed new rescue diagnostics or functional probes, that rejection occurs before downstream evidence or transcript access, and that a current schema-v2 observation passes the admission boundary.

The workflow also compiles both offline rescue parser modules and statically rejects accidental ADB/Fastboot/subprocess/persistent-write surfaces. The repository-wide test matrix remains authoritative for broader regression coverage.
