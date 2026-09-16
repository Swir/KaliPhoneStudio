# KaliPhoneStudio Beta Release Gate

A Beta release is a **tested device build**, not a development snapshot.

For a device profile to receive its first public Beta, all items below must be satisfied.

## Required host-side evidence

- [ ] CI/tests green for the exact release commit.
- [ ] Device profile schema/identity tests pass.
- [ ] Read-only Fastboot baseline evidence records the exact physical profile/serial plus firmware build/fingerprint and is SHA-256 bound to the original transcript.
- [ ] The baseline firmware fingerprint/build matches the exact stock OTA provenance used for the candidate.
- [ ] Candidate manifest records exact `profile_id`, firmware baseline and hashes.
- [ ] Every release image has SHA-256 recorded.
- [ ] Partition-size and boot-layout gates pass.
- [ ] Build instructions are reproducible from pinned sources.

## Required physical-device evidence

- [ ] Exact model/profile recognized correctly before any destructive action.
- [ ] Stock recovery information captured before unlock/flash.
- [ ] Candidate passes **temporary boot** where supported.
- [ ] Rescue/log channel is usable after candidate boot.
- [ ] Kernel reaches the intended Kali early userspace/rootfs path.
- [ ] Internal storage path required by the release is verified.
- [ ] Display and touchscreen are usable enough to complete initial setup, or the release is explicitly labeled console-only.
- [ ] Charging/battery behavior is safe enough for testing.
- [ ] A failed boot can be recovered by a documented procedure.

## Required release content

- [ ] Clear device/firmware compatibility table.
- [ ] Installation instructions.
- [ ] Recovery/restore instructions.
- [ ] Known issues and hardware matrix.
- [ ] Release manifest and SHA-256 files.
- [ ] No proprietary firmware/blob redistribution unless redistribution is explicitly permitted.

Importing a saved Fastboot transcript or producing host-side authorization evidence does **not** by itself satisfy any physical-device checkbox above.

Only after these gates pass should a GitHub **Beta** be created. Stable releases require a substantially higher hardware-completeness and regression threshold.
