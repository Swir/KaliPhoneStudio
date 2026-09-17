"""Fail-closed identity evidence for the host Fastboot binary used for baseline capture.

The reviewed policy pins a concrete Android SDK Platform-Tools version.  A capture
must execute the exact regular-file binary whose bytes and ``fastboot --version``
output were inspected.  This is host provenance only and never grants hardware or
Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable


MAX_FASTBOOT_BINARY_BYTES = 128 * 1024 * 1024
MAX_VERSION_OUTPUT_BYTES = 64 * 1024
DEFAULT_TIMEOUT_SECONDS = 15
_VERSION_RE = re.compile(r"^fastboot version ([0-9]+\.[0-9]+\.[0-9]+)(?:-[A-Za-z0-9._+~-]+)?$")
_POLICY_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class FastbootToolError(ValueError):
    pass


@dataclass(frozen=True)
class FastbootToolEvidence:
    schema_version: int
    tool: str
    policy_sha256: str
    required_platform_tools_version: str
    observed_platform_tools_version: str
    executable_filename: str
    executable_sha256: str
    executable_size: int
    version_line: str
    version_output_sha256: str
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _canonical_policy(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_fastboot_tool_policy(path: Path) -> tuple[dict[str, Any], str]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise FastbootToolError("Fastboot tool policy must be a regular non-symlink file")
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FastbootToolError("cannot load Fastboot tool policy") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise FastbootToolError("unsupported Fastboot tool policy schema")
    expected_keys = {
        "schema_version", "tool", "platform_tools_version", "release_month",
        "release_notes_url", "version_policy", "hardware_verified", "beta_gate_credit",
    }
    if set(data) != expected_keys:
        raise FastbootToolError("Fastboot tool policy contains missing or unexpected fields")
    if data.get("tool") != "fastboot" or data.get("version_policy") != "exact":
        raise FastbootToolError("Fastboot tool policy must require exact fastboot version identity")
    version = data.get("platform_tools_version")
    if not isinstance(version, str) or not _POLICY_VERSION_RE.fullmatch(version):
        raise FastbootToolError("Fastboot tool policy version must be major.minor.patch")
    url = data.get("release_notes_url")
    if not isinstance(url, str) or not url.startswith("https://developer.android.com/"):
        raise FastbootToolError("Fastboot tool policy must reference Android Developers over HTTPS")
    month = data.get("release_month")
    if not isinstance(month, str) or not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", month):
        raise FastbootToolError("Fastboot tool policy release_month must be YYYY-MM")
    if data.get("hardware_verified") is not False or data.get("beta_gate_credit") is not False:
        raise FastbootToolError("Fastboot tool policy must explicitly grant no hardware/Beta credit")
    return data, sha256(_canonical_policy(data)).hexdigest()


def _resolve_executable(value: str | Path) -> Path:
    raw = str(value)
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        raise FastbootToolError("Fastboot executable path is invalid")
    found = shutil.which(raw)
    candidate = Path(found) if found else Path(raw)
    if candidate.is_symlink():
        raise FastbootToolError("Fastboot executable must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FastbootToolError("Fastboot executable cannot be resolved") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise FastbootToolError("Fastboot executable must be a regular non-symlink file")
    return resolved


def _hash_regular_file(path: Path) -> tuple[str, int]:
    before = path.stat()
    if before.st_size <= 0 or before.st_size > MAX_FASTBOOT_BINARY_BYTES:
        raise FastbootToolError("Fastboot executable size is outside the safety bound")
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    after = path.stat()
    if size != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise FastbootToolError("Fastboot executable changed while being inspected")
    return digest.hexdigest(), size


def _run_version(
    executable: Path,
    *,
    timeout_seconds: int,
    runner: Callable[..., Any],
) -> bytes:
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= 60:
        raise FastbootToolError("Fastboot version timeout must be an integer between 1 and 60 seconds")
    try:
        result = runner(
            [str(executable), "--version"],
            shell=False,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FastbootToolError("Fastboot --version failed to execute") from exc
    returncode = getattr(result, "returncode", None)
    payload = getattr(result, "stdout", None)
    if not isinstance(returncode, int) or isinstance(returncode, bool) or returncode != 0:
        raise FastbootToolError("Fastboot --version did not exit successfully")
    if not isinstance(payload, (bytes, bytearray)):
        raise FastbootToolError("Fastboot --version did not return byte output")
    output = bytes(payload)
    if not output or len(output) > MAX_VERSION_OUTPUT_BYTES or b"\x00" in output:
        raise FastbootToolError("Fastboot --version output is empty or outside the safety bound")
    return output


def inspect_fastboot_tool(
    fastboot: str | Path,
    *,
    policy_path: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[FastbootToolEvidence, Path]:
    """Return canonical tool evidence and the exact resolved executable to run later."""
    policy, policy_sha = load_fastboot_tool_policy(policy_path)
    executable = _resolve_executable(fastboot)
    binary_sha, binary_size = _hash_regular_file(executable)
    version_output = _run_version(executable, timeout_seconds=timeout_seconds, runner=runner)
    try:
        text = version_output.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FastbootToolError("Fastboot --version output must be UTF-8") from exc
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    if not nonempty:
        raise FastbootToolError("Fastboot --version contains no version line")
    match = _VERSION_RE.fullmatch(nonempty[0])
    if not match:
        raise FastbootToolError("Fastboot --version first line has an unsupported format")
    observed = match.group(1)
    required = policy["platform_tools_version"]
    if observed != required:
        raise FastbootToolError(
            f"Fastboot version {observed} is not the reviewed Platform-Tools version {required}"
        )
    evidence = FastbootToolEvidence(
        schema_version=1,
        tool="fastboot",
        policy_sha256=policy_sha,
        required_platform_tools_version=required,
        observed_platform_tools_version=observed,
        executable_filename=executable.name,
        executable_sha256=binary_sha,
        executable_size=binary_size,
        version_line=nonempty[0],
        version_output_sha256=sha256(version_output).hexdigest(),
    )
    return evidence, executable


def write_fastboot_tool_evidence(evidence: FastbootToolEvidence, destination: Path) -> str:
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise FastbootToolError(f"refusing to overwrite Fastboot tool evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FastbootToolError("refusing stale Fastboot tool evidence temporary path")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
