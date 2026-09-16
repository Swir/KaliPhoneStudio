from __future__ import annotations

from pathlib import Path

import pytest

from scripts.apply_busybox_miniconfig import (
    MiniConfigError,
    apply_overlay,
    load_miniconfig,
    verify_overlay,
)


def test_apply_and_verify_busybox_miniconfig(tmp_path: Path) -> None:
    mini = tmp_path / "mini"
    config = tmp_path / ".config"
    mini.write_text("CONFIG_STATIC=y\nCONFIG_ASH=y\nCONFIG_WGET=n\n", encoding="utf-8")
    config.write_text(
        "# CONFIG_STATIC is not set\n# CONFIG_ASH is not set\nCONFIG_WGET=y\nCONFIG_OTHER=y\n",
        encoding="utf-8",
    )
    locked = load_miniconfig(mini)
    assert apply_overlay(config, locked) == 3
    assert config.read_text(encoding="utf-8") == (
        "CONFIG_STATIC=y\nCONFIG_ASH=y\n# CONFIG_WGET is not set\nCONFIG_OTHER=y\n"
    )
    assert verify_overlay(config, locked) == 3


def test_repository_rescue_miniconfig_keeps_inventory_and_static_contract() -> None:
    """Keep inventory and local power controls explicit under ``allnoconfig``.

    The evidence workflow needs the BusyBox applet itself for ``--list``. The
    rescue shell also promises local recovery controls, so halt/poweroff/reboot
    must stay compiled while external telinit handoff stays disabled.
    """

    locked = load_miniconfig(Path("rescue/busybox-minimal.config"))
    assert locked["CONFIG_BUSYBOX"] == "y"
    assert locked["CONFIG_STATIC"] == "y"
    assert locked["CONFIG_ASH"] == "y"
    assert locked["CONFIG_SH_IS_ASH"] == "y"
    assert locked["CONFIG_HALT"] == "y"
    assert locked["CONFIG_POWEROFF"] == "y"
    assert locked["CONFIG_REBOOT"] == "y"
    assert locked["CONFIG_FEATURE_CALL_TELINIT"] == "n"


def test_rejects_unknown_locked_symbol(tmp_path: Path) -> None:
    mini = tmp_path / "mini"
    config = tmp_path / ".config"
    mini.write_text("CONFIG_DOES_NOT_EXIST=y\n", encoding="utf-8")
    config.write_text("CONFIG_STATIC=y\n", encoding="utf-8")
    with pytest.raises(MiniConfigError, match="missing"):
        apply_overlay(config, load_miniconfig(mini))


def test_rejects_duplicate_miniconfig_symbol(tmp_path: Path) -> None:
    mini = tmp_path / "mini"
    mini.write_text("CONFIG_STATIC=y\nCONFIG_STATIC=n\n", encoding="utf-8")
    with pytest.raises(MiniConfigError, match="duplicate"):
        load_miniconfig(mini)


def test_rejects_unsafe_miniconfig_syntax(tmp_path: Path) -> None:
    mini = tmp_path / "mini"
    mini.write_text("CONFIG_STATIC=$(touch /tmp/nope)\n", encoding="utf-8")
    with pytest.raises(MiniConfigError, match="unsafe"):
        load_miniconfig(mini)


def test_check_catches_kconfig_dependency_drift(tmp_path: Path) -> None:
    mini = tmp_path / "mini"
    config = tmp_path / ".config"
    mini.write_text("CONFIG_STATIC=y\nCONFIG_ASH=y\n", encoding="utf-8")
    config.write_text("CONFIG_STATIC=y\n# CONFIG_ASH is not set\n", encoding="utf-8")
    with pytest.raises(MiniConfigError, match="Kconfig changed"):
        verify_overlay(config, load_miniconfig(mini))


def test_apply_rejects_duplicate_symbol_in_generated_config(tmp_path: Path) -> None:
    mini = tmp_path / "mini"
    config = tmp_path / ".config"
    mini.write_text("CONFIG_STATIC=y\n", encoding="utf-8")
    config.write_text("# CONFIG_STATIC is not set\nCONFIG_STATIC=y\n", encoding="utf-8")
    with pytest.raises(MiniConfigError, match="duplicate"):
        apply_overlay(config, load_miniconfig(mini))
