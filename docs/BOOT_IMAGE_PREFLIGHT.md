# Android boot image structural preflight

KaliPhoneStudio treats a matching Android magic/header-version pair as **necessary but not sufficient** evidence that a boot image is structurally safe to present to the later physical-candidate gate.

For legacy Android boot headers v0/v1/v2, the host preflight follows the AOSP `boot_img_hdr_v*` layout. In header v2 the boot partition is one header page followed by page-aligned kernel, ramdisk, optional second stage, optional recovery DTBO/ACPIO and required DTB. AOSP requires the kernel, ramdisk and DTB sizes to be non-zero for v2.

For the current `oneplus/avicii` profile (header v2), `inspect_boot_image()` therefore records and `require_candidate_compatible()` verifies:

- Android boot magic and exact profile-declared header version;
- header page size and equality with the profile contract;
- non-empty kernel and ramdisk;
- v1/v2 `header_size` equality with the exact packed header size;
- non-empty DTB for header v2;
- page-aligned component layout and, when present, the exact recovery-DTBO offset;
- that the file is at least large enough to contain all declared aligned components;
- the profile boot-partition size limit.

The preflight intentionally accepts bytes after the calculated payload end because a production boot partition may carry trailing boot-signature/AVB data outside the legacy component calculation. It does **not** parse or validate AVB, prove signatures, prove that the kernel/ramdisk/DTB content is semantically correct, or claim that the phone can boot the image.

A report passing this host structural check remains host evidence only. The physical release gate still requires exact firmware/stock-image provenance, reviewed candidate identity, explicit one-shot temporary boot on the real phone, rescue evidence, Kali early-userspace proof and the rest of `BETA_RELEASE_GATE.md`.
