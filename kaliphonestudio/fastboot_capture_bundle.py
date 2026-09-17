"""Cryptographic join for one guarded, read-only physical Fastboot baseline capture.

This evidence closes the provenance gap between the reviewed Fastboot executable,
the exact raw ``getvar all`` transcript and the parsed baseline evidence. It is
capture provenance only: it does not claim that a candidate boots or satisfy a
Beta hardware gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

from .fastboot_baseline import FastbootBaselineEvidence
from .fastboot_tool import FastbootToolEvidence
from .profiles import DeviceProfile

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CAPTURE_POLICY = "fastboot-version+devices+serial-getvar-all-v1"
_MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024


class FastbootCaptureBundleError(ValueError):
    pass


@dataclass(frozen=True)
class FastbootCaptureBundleEvidence:
    schema_version: int
    profile_id: str
    device_serial: str
    product: str
    firmware_build: str
    firmware_fingerprint: str
    transcript_sha256: str
    transcript_size: int
    baseline_evidence_sha256: str
    fastboot_tool_evidence_sha256: str
    fastboot_tool_policy_sha256: str
    fastboot_executable_sha256: str
    fastboot_executable_size: int
    platform_tools_version: str
    capture_policy: str
    read_only: bool
    phone_storage_written: bool
    hardware_verified: bool = False
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FastbootCaptureBundleError(f"{label} must be a lowercase SHA-256")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise FastbootCaptureBundleError(f"{label} must be a positive integer")
    return value


def _hash_regular(path: Path) -> tuple[str, int]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise FastbootCaptureBundleError("Fastboot transcript must be a regular non-symlink file")
    before = candidate.stat()
    if before.st_size <= 0 or before.st_size > _MAX_TRANSCRIPT_BYTES:
        raise FastbootCaptureBundleError("Fastboot transcript size is outside the safety bound")
    digest = sha256()
    size = 0
    with candidate.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    after = candidate.stat()
    if size != before.st_size or after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise FastbootCaptureBundleError("Fastboot transcript changed while being bound")
    return digest.hexdigest(), size


def bind_fastboot_capture(
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    tool: FastbootToolEvidence,
    *,
    transcript: Path,
) -> FastbootCaptureBundleEvidence:
    if baseline.schema_version != 1:
        raise FastbootCaptureBundleError("unsupported Fastboot baseline schema")
    if baseline.profile_id != profile.profile_id:
        raise FastbootCaptureBundleError("Fastboot baseline profile mismatch")
    if baseline.beta_gate_credit is not False:
        raise FastbootCaptureBundleError("Fastboot baseline cannot claim Beta credit")
    if not profile.matches(product=baseline.product):
        raise FastbootCaptureBundleError("Fastboot baseline product no longer matches profile")
    if not isinstance(baseline.serialno, str) or not baseline.serialno.strip():
        raise FastbootCaptureBundleError("Fastboot baseline serial is invalid")

    transcript_sha, transcript_size = _hash_regular(transcript)
    if transcript_sha != baseline.transcript_sha256 or transcript_size != baseline.transcript_size:
        raise FastbootCaptureBundleError("raw transcript does not match Fastboot baseline evidence")

    if tool.schema_version != 1 or tool.tool != "fastboot":
        raise FastbootCaptureBundleError("unsupported Fastboot tool evidence")
    if tool.hardware_verified is not False or tool.beta_gate_credit is not False:
        raise FastbootCaptureBundleError("Fastboot tool evidence cannot claim hardware/Beta credit")
    if tool.required_platform_tools_version != tool.observed_platform_tools_version:
        raise FastbootCaptureBundleError("Fastboot tool evidence does not prove exact reviewed version")
    for value, label in (
        (baseline.evidence_sha256(), "baseline evidence SHA-256"),
        (tool.evidence_sha256(), "Fastboot tool evidence SHA-256"),
        (tool.policy_sha256, "Fastboot policy SHA-256"),
        (tool.executable_sha256, "Fastboot executable SHA-256"),
        (transcript_sha, "transcript SHA-256"),
    ):
        _require_sha(value, label)
    _require_positive_int(tool.executable_size, "Fastboot executable size")

    return FastbootCaptureBundleEvidence(
        schema_version=1,
        profile_id=profile.profile_id,
        device_serial=baseline.serialno,
        product=baseline.product,
        firmware_build=baseline.firmware_build,
        firmware_fingerprint=baseline.firmware_fingerprint,
        transcript_sha256=transcript_sha,
        transcript_size=transcript_size,
        baseline_evidence_sha256=baseline.evidence_sha256(),
        fastboot_tool_evidence_sha256=tool.evidence_sha256(),
        fastboot_tool_policy_sha256=tool.policy_sha256,
        fastboot_executable_sha256=tool.executable_sha256,
        fastboot_executable_size=tool.executable_size,
        platform_tools_version=tool.observed_platform_tools_version,
        capture_policy=_CAPTURE_POLICY,
        read_only=True,
        phone_storage_written=False,
    )


def verify_fastboot_capture_bundle(
    evidence: FastbootCaptureBundleEvidence,
    profile: DeviceProfile,
    baseline: FastbootBaselineEvidence,
    tool: FastbootToolEvidence,
    *,
    transcript: Path,
) -> None:
    expected = bind_fastboot_capture(profile, baseline, tool, transcript=transcript)
    if evidence != expected:
        raise FastbootCaptureBundleError("Fastboot capture bundle does not match its exact inputs")


def write_fastboot_capture_bundle(evidence: FastbootCaptureBundleEvidence, destination: Path) -> str:
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise FastbootCaptureBundleError(f"refusing to overwrite Fastboot capture bundle: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FastbootCaptureBundleError("refusing stale Fastboot capture bundle temporary path")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return evidence.evidence_sha256()
