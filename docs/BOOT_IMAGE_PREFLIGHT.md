# Android boot image structural preflight

KaliPhoneStudio treats a matching Android magic/header-version pair as **necessary but not sufficient** evidence that a boot image is structurally safe to present to the later physical-candidate gate.

For legacy Android boot headers v0/v1/v2, the host preflight follows the AOSP `boot_img_hdr_v*` layout. In header v2 the boot partition is one header page followed by page-aligned kernel, ramdisk, optional second stage, optional recovery DTBO/ACPIO and required DTB. AOSP requires the kernel, ramdisk and DTB sizes to be non-zero for v2.

For the current `oneplus/avicii` profile (header v2), `inspect_boot_image()` records and `require_candidate_compatible()` verifies:

- Android boot magic and exact profile-declared header version;
- header page size and equality with the profile contract;
- non-empty kernel and ramdisk;
- v1/v2 `header_size` equality with the exact packed header size;
- non-empty DTB for header v2;
- page-aligned component layout and, when present, the exact recovery-DTBO offset;
- that the file is at least large enough to contain all declared aligned components;
- the profile boot-partition size limit;
- SHA-256 fingerprints of the exact declared kernel, ramdisk, optional second-stage, optional recovery-DTBO and DTB bytes, excluding alignment padding.

## Optional AVB footer / vbmeta structural evidence

A legacy boot image can contain bytes after the calculated component payload. When the final 64 bytes contain the AOSP AVB footer magic `AVBf`, KaliPhoneStudio now parses that footer fail-closed and records:

- AVB footer major/minor version;
- `original_image_size`;
- exact `vbmeta_offset` and `vbmeta_size`;
- SHA-256 of the exact footer-referenced vbmeta bytes;
- whether the 256-byte vbmeta header starts with `AVB0`;
- consistency of the vbmeta authentication/auxiliary block sizes with the footer-declared vbmeta size;
- bounds proving that vbmeta stays between the original image and the final footer and does not overlap/escape the file.

The layout is derived from AOSP `external/avb` `avbtool` at commit `21e95266704e572ced1c633bbc4aea9f42afa0a5`, whose `AvbFooter` uses the 64-byte big-endian `AVBf` structure containing version, original image size, vbmeta offset and vbmeta size. This source pin documents the parser contract; KaliPhoneStudio does not download or execute `avbtool` as part of this preflight.

Footer presence is intentionally **optional**, even for a profile with AVB enabled: AVB policy can involve separate vbmeta partitions, and a host-side temporary-boot candidate must not be rejected merely because no appended footer exists. However, if an `AVBf` footer is present, malformed ranges/header sizes/magic are rejected rather than silently ignored.

This is not cryptographic AVB verification. The preflight does **not** validate vbmeta signatures, keys, rollback indexes, descriptors, partition digests or the device trust chain. It also does not prove that kernel/ramdisk/DTB bytes are semantically correct or that the phone can boot them. Component SHA-256 values are identity/provenance material only.

A report passing this host structural check remains host evidence only. The physical release gate still requires exact firmware/stock-image provenance, reviewed candidate identity, explicit one-shot temporary boot on the real phone, rescue evidence, Kali early-userspace proof and the rest of `BETA_RELEASE_GATE.md`.
