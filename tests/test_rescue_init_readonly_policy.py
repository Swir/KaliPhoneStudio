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


def test_functional_probe_is_manual_bounded_and_read_only() -> None:
    text = _init_text()
    assert "cat > /run/kps-readonly-probe <<'KPS_READONLY_PROBE'" in text
    assert 'if [ "$1" != "--confirm-read-only" ]; then' in text
    assert 'KPS_POLICY="readonly-functional-probes-v1"' in text
    assert 'KPS_PROBE_BLOCK_READ=' in text
    assert 'KPS_PROBE_BATTERY_SAMPLE=' in text
    assert 'of=/dev/null bs=4096 count=1' in text
    assert '"$count" -lt 8' in text
    assert '"$seq" -le 2' in text
    assert 'chmod 0755 /run/kps-readonly-probe' in text


def test_functional_probe_never_targets_storage_for_writes_or_runs_automatically() -> None:
    text = _init_text()
    assert "of=/dev/null" in text
    assert "of=/dev/$name" not in text
    assert "mkfs" not in text.lower()
    assert "fsck" not in text.lower()
    assert "cryptsetup" not in text.lower()
    assert "mount \"$dev\"" not in text
    executable_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("/run/kps-readonly-probe ")
    ]
    assert executable_lines == []
