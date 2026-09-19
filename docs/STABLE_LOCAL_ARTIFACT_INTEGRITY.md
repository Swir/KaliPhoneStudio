# Stable local artifact integrity

`kaliphonestudio.stable_file` is the shared host-only integrity boundary for safety-sensitive local artifacts that are about to be bound into KaliPhoneStudio evidence.

## Scope

The verifier is deliberately narrow. It hashes one local regular file through a secured read-only descriptor and returns its exact SHA-256, byte size and filesystem identity. It performs no phone I/O, does not invoke ADB/Fastboot, does not mount storage, and does not authorize booting, flashing, rootfs writes, hardware claims or a Beta release.

Current guarded consumers include the physical recovery-readiness stock `boot.img` path and the rootfs handoff local-artifact preflight. A successful local integrity check is only one prerequisite inside those larger fail-closed gates.

## Fail-closed invariants

For one verification call, the helper requires all of the following:

- the path initially names a non-empty regular file and is not a symlink;
- the file is no larger than the caller's explicit safety limit;
- an optional expected byte size matches before hashing begins;
- `O_NOFOLLOW` is requested when the host exposes it;
- pre-open `lstat` and post-open `fstat` identify the same file state;
- bytes are read only from the secured descriptor;
- growth or truncation during hashing is rejected;
- post-read descriptor identity must still match the pre-read descriptor identity;
- final `lstat` must still identify the same regular file state;
- device, inode, size, `mtime_ns` and `ctime_ns` are compared where Python exposes the normal `stat_result` fields.

The `ctime_ns` check is intentional. On POSIX filesystems a writer can restore a previous mtime after modifying bytes, while ordinary file APIs cannot restore ctime. This closes a same-size mutation race that a size+mtime-only check could miss. On platforms where ctime has different semantics, the comparison remains conservative: unexpected drift causes refusal rather than acceptance.

## Threat model and limitations

This boundary protects the path/descriptor transition and detects file-state drift during hashing. It is not a filesystem lock and cannot make an untrusted host safe. A privileged process, compromised kernel, hostile filesystem, or storage implementation that lies about metadata remains outside the guarantee. The evidence layer must still compare the returned SHA-256 and size to the exact reviewed authority/candidate values before granting its own next-stage readiness flag.

## Verification

`tests/test_stable_file.py` covers exact hashing, expected-size drift, symlink refusal, path replacement, truncation, growth and a POSIX same-size mutation that restores the original mtime. The dedicated CI matrix runs the contract on Linux and Windows with the oldest and newest supported Python lines used by this project.

No passing result from this helper changes the project roadmap percentage or Beta status. Physical AC2003 verification remains mandatory for the hardware gate.
