# KaliPhoneStudio Beta Release Gate

**Status: BLOCKED**

A green CI run, device profile, successful host build, reviewed reproducibility authority, Fastboot return code, rescue marker or early-userspace marker does not by itself authorize a Beta release.

The first public Beta may be published only when the exact release candidate passes every applicable item below and the evidence is reviewed.

## Host-side mandatory gate

- [x] Multi-device profile schema/identity/path contract is enforced.
- [x] The selected profile has a unique identity and explicit confirmation token.
- [x] Boot layout/partition constraints, pinned sources and recovery/test contracts are declared by profile.
- [x] Exact source/tool locks and checksums/object identities are recorded.
- [x] Kali ARM64 rootfs has a reviewed strict byte-identical authority.
- [x] Kernel has a reviewed strict byte-identical authority.
- [x] Required DTB/DTBO artifacts have a reviewed strict byte-identical authority bound to the reviewed kernel.
- [x] Exact first-boot candidate binds kernel/rootfs/DT authorities and firmware/boot provenance without claiming hardware success.
- [x] Boot image assembly/round-trip and partition-size checks are fail-closed.
- [x] Temporary boot is serial/profile/firmware/candidate bound and cannot silently become a flash/write action.
- [x] Rescue initramfs/payload is deterministic, network/SSH disabled by default, and has an exact probe identity.
- [x] Kali early-userspace proof overlay is deterministic and bound to exact candidate/rootfs authority identities.
- [x] Early-userspace transcript parser requires exact stage/probe/manifest/rootfs-authority/rootfs-artifact markers and never auto-promotes them to hardware/Beta credit.
- [ ] Select and review the actual rootfs staging/handoff strategy for the physical device. The common core must not guess or hard-code an unverified storage/encryption path.
- [ ] Final release manifest/compatibility matrix/known issues and SHA-256 set are generated from the exact reviewed physical candidate.

## Physical AC2003 mandatory gate

These must come from the exact physical phone/firmware intended for support.

- [ ] Real device identity captured and matches profile `oneplus/avicii` / OnePlus Nord AC2003.
- [ ] Exact OxygenOS build and firmware fingerprint captured read-only.
- [ ] Matching stock `boot.img` extracted from the exact OTA and validated against that physical baseline.
- [ ] Recovery path is documented before risky testing begins.
- [ ] Exact reviewed physical candidate is instantiated from that baseline and reviewed authorities.
- [ ] `fastboot boot` succeeds on the exact phone after explicit user confirmation.
- [ ] Rescue/logging path is usable and exact rescue probe markers are manually reviewed.
- [ ] The selected rootfs handoff makes the exact reviewed Kali rootfs available without violating the approved storage/recovery policy.
- [ ] Exact `KPS_KALI_STAGE=rootfs-systemd-early-v1` plus matching probe/manifest/rootfs-authority/rootfs-artifact markers are captured from the physical run and manually reviewed.
- [ ] Reviewer confirms the kernel reached the intended Kali early userspace/rootfs; parser output alone is not sufficient.
- [ ] Required UFS/storage behavior is validated beyond bounded diagnostic reads.
- [ ] Charging/battery behavior is safe enough for the documented test/release scope.
- [ ] Display/touch works for the supported scope, or Beta is explicitly reviewed and documented as console-only.
- [ ] Required USB/rescue behavior is verified.
- [ ] Recovery/rollback is exercised on the exact physical baseline.

## Non-credit evidence

The following remain useful diagnostics but **cannot** satisfy a physical checkbox on their own:

- green host CI;
- profile JSON presence;
- reproducible kernel/rootfs/DT artifacts without phone testing;
- a `fastboot boot` process return code without observed phone-side evidence;
- rescue `init-reached` marker without Kali-rootfs proof;
- a Kali early-userspace marker set without manual review of the exact candidate/physical context;
- one bounded 4096-byte block read;
- two battery telemetry samples;
- synthetic/mock transcripts.

## Release publication rule

Do not create an empty, symbolic or placeholder Beta. Only after the full gate is reviewed should a GitHub prerelease be created from the exact candidate commit with actual binaries/images, instructions, compatibility matrix, known issues and SHA-256 checksums.

Stable requires a later, higher threshold.
