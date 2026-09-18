# Temporary-boot post-probe integrity boundary

KaliPhoneStudio treats the interval between the fresh read-only Fastboot probe and the one allowed `fastboot -s SERIAL boot IMAGE` command as a security boundary.

## Why this exists

The initial temporary-boot offer already binds the exact Fastboot executable and candidate `boot.img`, while physical recovery readiness binds the exact local stock `boot.img`. A fresh device probe can still take enough time for one of those local files to be changed after the first validation. Executing the earlier command without another exact-byte verification would create a host-side time-of-check/time-of-use gap.

## Required ordering

`execute_temporary_boot_once()` now follows this order:

1. Validate the reviewed temporary-boot offer, exact boot-identity binding, authorization, physical baseline and recovery readiness.
2. Perform the fresh serial-bound, read-only Fastboot `devices` / `getvar all` probe.
3. Validate device identity, unlock state and profile-driven slot context.
4. Re-run exact offer verification, which re-hashes the Fastboot executable and candidate `boot.img`.
5. Re-run boot-identity, authorization and baseline binding checks.
6. Re-run physical recovery-readiness verification, which re-hashes the local matching stock `boot.img`.
7. Only if all checks still match, invoke the exact reviewed `fastboot -s SERIAL boot IMAGE` argv once.

Any drift at steps 4–6 is fail-closed and no boot subprocess is invoked.

## Safety properties

This change does **not** add `flash`, `erase`, `set_active`, slot switching, partition selection or any persistent write operation. It does not claim that the phone booted, that rollback works, that Kali userspace was reached, or that any Beta gate passed.

The execution evidence keeps `persistent_write=false`, `phone_storage_written=false`, `kali_userspace_verified=false`, `hardware_verified=false` and `beta_gate_credit=false`. The execution policy identifier is versioned so evidence produced by the post-probe exact-material revalidation path is distinguishable from older host-side execution evidence.

## CI contract

`tests/test_temporary_boot_preexecution_revalidation.py` verifies ordering and fail-closed behavior for post-probe offer drift and recovery-material drift. The focused `temporary-boot-identity-gate` workflow compiles the affected modules, runs the existing exact identity/recovery tests plus these new tests, and asserts that the temporary-boot execution surface still exposes no persistent Fastboot verb.
