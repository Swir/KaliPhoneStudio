from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from kaliphonestudio.fastboot_tool import (
    FastbootToolError,
    inspect_fastboot_tool,
    load_fastboot_tool_policy,
    write_fastboot_tool_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "tools" / "fastboot-tool-policy.json"


def _fake_fastboot(tmp_path: Path) -> Path:
    path = tmp_path / ("fastboot.exe" if __import__("os").name == "nt" else "fastboot")
    path.write_bytes(b"reviewed-fastboot-binary\x00fixture")
    path.chmod(0o755)
    return path


def _runner(calls: list[tuple[list[str], dict]], output: bytes = b"fastboot version 37.0.1-13704100\nInstalled as /fixture/fastboot\n"):
    def run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return SimpleNamespace(returncode=0, stdout=output)
    return run


def test_policy_is_exact_reviewed_platform_tools_version():
    policy, digest = load_fastboot_tool_policy(POLICY)
    assert policy["tool"] == "fastboot"
    assert policy["platform_tools_version"] == "37.0.1"
    assert policy["version_policy"] == "exact"
    assert policy["release_notes_url"] == "https://developer.android.com/tools/releases/platform-tools"
    assert policy["hardware_verified"] is False
    assert policy["beta_gate_credit"] is False
    assert len(digest) == 64


def test_inspection_hashes_exact_binary_and_uses_only_version_command(tmp_path: Path):
    binary = _fake_fastboot(tmp_path)
    calls = []
    evidence, resolved = inspect_fastboot_tool(
        binary,
        policy_path=POLICY,
        runner=_runner(calls),
    )
    assert resolved == binary.resolve()
    assert evidence.observed_platform_tools_version == "37.0.1"
    assert evidence.required_platform_tools_version == "37.0.1"
    assert evidence.executable_sha256 == sha256(binary.read_bytes()).hexdigest()
    assert evidence.executable_size == binary.stat().st_size
    assert evidence.hardware_verified is False
    assert evidence.beta_gate_credit is False
    assert [item[0] for item in calls] == [[str(binary.resolve()), "--version"]]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdin"] is not None


def test_unreviewed_platform_tools_version_is_rejected(tmp_path: Path):
    binary = _fake_fastboot(tmp_path)
    calls = []
    with pytest.raises(FastbootToolError, match="not the reviewed Platform-Tools version 37.0.1"):
        inspect_fastboot_tool(
            binary,
            policy_path=POLICY,
            runner=_runner(calls, b"fastboot version 36.0.2-123456\n"),
        )
    assert len(calls) == 1


def test_malformed_version_output_fails_closed(tmp_path: Path):
    binary = _fake_fastboot(tmp_path)
    with pytest.raises(FastbootToolError, match="unsupported format"):
        inspect_fastboot_tool(
            binary,
            policy_path=POLICY,
            runner=_runner([], b"something claiming to be fastboot\n"),
        )


def test_symlink_executable_is_rejected(tmp_path: Path):
    binary = _fake_fastboot(tmp_path)
    link = tmp_path / "fastboot-link"
    try:
        link.symlink_to(binary)
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(FastbootToolError, match="must not be a symlink"):
        inspect_fastboot_tool(link, policy_path=POLICY, runner=_runner([]))


def test_tool_evidence_write_is_immutable(tmp_path: Path):
    binary = _fake_fastboot(tmp_path)
    evidence, _resolved = inspect_fastboot_tool(binary, policy_path=POLICY, runner=_runner([]))
    out = tmp_path / "tool.json"
    digest = write_fastboot_tool_evidence(evidence, out)
    assert digest == evidence.evidence_sha256()
    assert out.read_text(encoding="utf-8") == evidence.canonical_json()
    with pytest.raises(FastbootToolError, match="refusing to overwrite"):
        write_fastboot_tool_evidence(evidence, out)


def test_version_runner_failure_and_nonbyte_output_fail_closed(tmp_path: Path):
    binary = _fake_fastboot(tmp_path)

    def failed(argv, **kwargs):
        return SimpleNamespace(returncode=1, stdout=b"fastboot version 37.0.1\n")

    with pytest.raises(FastbootToolError, match="did not exit successfully"):
        inspect_fastboot_tool(binary, policy_path=POLICY, runner=failed)

    def text(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="fastboot version 37.0.1")

    with pytest.raises(FastbootToolError, match="byte output"):
        inspect_fastboot_tool(binary, policy_path=POLICY, runner=text)
