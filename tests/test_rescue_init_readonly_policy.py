from pathlib import Path


def _init_text() -> str:
    return Path("rescue/init").read_text(encoding="utf-8")


def test_rescue_init_emits_bounded_readonly_inventory_markers() -> None:
    text = _init_text()
    for marker in (
        "KPS_DIAG_BEGIN=",
        "KPS_DIAG_BLOCK=",
        "KPS_DIAG_SCSI_HOST=",
        "KPS_DIAG_POWER=",
        "KPS_DIAG_INPUT=",
        "KPS_DIAG_GRAPHICS=",
        "KPS_DIAG_DRM=",
        "KPS_DIAG_END=",
    ):
        assert marker in text
    assert 'KPS_DIAG_POLICY="readonly-sysfs-inventory-v1"' in text
    assert text.count('"$count" -lt 64') >= 6


def test_rescue_init_keeps_persistent_storage_unmounted_and_no_fastboot() -> None:
    text = _init_text()
    lowered = text.lower()
    assert "fastboot" not in lowered
    assert "mount /data" not in lowered
    assert "mount /system" not in lowered
    assert "mount /vendor" not in lowered
    assert "mount /metadata" not in lowered
    assert "storage_auto_mount=disabled" in text
