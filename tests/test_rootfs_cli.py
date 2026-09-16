from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).parents[1]


def test_rootfs_clis_are_directly_runnable_from_checkout():
    for relative in (
        "scripts/capture_kali_snapshot.py",
        "scripts/run_locked_rootfs_build.py",
        "scripts/verify_rootfs_pair.py",
    ):
        result = subprocess.run(
            [sys.executable, str(ROOT / relative), "--help"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"{relative}: {result.stderr}"
        assert "usage:" in result.stdout.lower()
