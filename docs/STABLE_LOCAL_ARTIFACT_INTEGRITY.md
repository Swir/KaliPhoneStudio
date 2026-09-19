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
- POSIX requests `O_NOFOLLOW` when the host exposes it;
- Windows opens the final component with `CreateFileW` + `FILE_FLAG_OPEN_REPARSE_POINT` and shares **reads only**, excluding concurrent write/delete opens while the secured handle is held;
- pre-open `lstat` and post-open `fstat` identify the same file state;
- bytes are read only from the secured descriptor;
- growth or truncation during hashing is rejected;
- post-read descriptor identity must still match the pre-read descriptor identity;
- final `lstat` must still identify the same regular file state;
- device, inode, size and `mtime_ns` are portable equality gates; POSIX additionally requires stable `ctime_ns`.

The POSIX `ctime_ns` gate is intentional. A writer can restore a previous mtime after modifying bytes, while ordinary file APIs cannot restore ctime. On Windows the helper does not depend on version-specific ctime semantics: the Win32 handle itself denies later write/delete sharing for the duration of the hash, while device/inode/size/mtime and final path/descriptor identity checks still remain mandatory.

## Threat model and limitations

This boundary protects the path/descriptor transition and detects file-state drift during hashing. The Windows share-mode gate prevents normal later write/delete opens while verification is active, but it is still not a filesystem lock or a trusted-host boundary. A writer already holding a sufficiently permissive handle before verification, privileged process, compromised kernel, hostile filesystem, direct block access, or storage implementation that lies about metadata remains outside the guarantee. The evidence layer must still compare the returned SHA-256 and size to the exact reviewed authority/candidate values before granting its own next-stage readiness flag.

## Verification

`tests/test_stable_file.py` covers exact hashing, expected-size drift, empty/symlink refusal, path replacement, short/overlong descriptor streams, a POSIX same-size mutation that restores the original mtime, and a Windows-only adversarial attempt to open a concurrent writer while the secured hash handle is active. The dedicated CI matrix runs the contract on Linux and Windows with Python 3.11 and 3.14, matching the oldest/newest supported project lines used for focused safety gates.

No passing result from this helper changes the project roadmap percentage or Beta status. Physical AC2003 verification remains mandatory for the hardware gate.
