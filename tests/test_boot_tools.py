from pathlib import Path
import json

import pytest

from kaliphonestudio.boot_image import BootImageError
from kaliphonestudio.boot_tools import load_boot_tool_locks, require_assembler_for_header

ROOT = Path(__file__).parents[1]
LOCKS = ROOT / "tools" / "boot-tool-locks.json"


def test_authoritative_boot_tools_are_full_commit_locked():
    locks = load_boot_tool_locks(LOCKS)
    assert set(locks) == {"mkbootimg", "unpack_bootimg"}
    assert len(locks["mkbootimg"].commit) == 40
    assert locks["mkbootimg"].repository == "https://github.com/LineageOS/android_system_tools_mkbootimg"
    assert 2 in locks["mkbootimg"].supported_header_versions


def test_avicii_header_v2_has_authorized_assembler():
    lock = require_assembler_for_header(load_boot_tool_locks(LOCKS), 2)
    assert lock.entrypoint == "mkbootimg.py"


def test_unknown_header_fails_closed():
    with pytest.raises(BootImageError, match="no source-locked assembler"):
        require_assembler_for_header(load_boot_tool_locks(LOCKS), 99)


def test_manifest_rejects_moving_ref(tmp_path):
    raw = json.loads(LOCKS.read_text(encoding="utf-8"))
    raw["mkbootimg"]["commit"] = "lineage-23.0"
    path = tmp_path / "locks.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BootImageError, match="full 40-character commit"):
        load_boot_tool_locks(path)


def test_manifest_rejects_unsafe_entrypoint(tmp_path):
    raw = json.loads(LOCKS.read_text(encoding="utf-8"))
    raw["mkbootimg"]["entrypoint"] = "../mkbootimg.py"
    path = tmp_path / "locks.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(BootImageError, match="unsafe boot tool entrypoint"):
        load_boot_tool_locks(path)


def test_locked_argv_never_path_discovers_script(tmp_path):
    lock = load_boot_tool_locks(LOCKS)["mkbootimg"]
    with pytest.raises(BootImageError, match="entrypoint missing"):
        lock.argv(tmp_path)
    (tmp_path / "mkbootimg.py").write_text("# locked fixture\n", encoding="utf-8")
    assert lock.argv(tmp_path) == ("python", str(tmp_path / "mkbootimg.py"))
