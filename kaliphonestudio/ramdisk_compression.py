"""Source-locked, profile-driven ramdisk compression for reviewed rescue CPIOs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .profiles import DeviceProfile
from .rescue_evidence import verify_rescue_initramfs_artifact
from .rescue_initramfs import RescueInitramfsError, RescueInitramfsEvidence


class RamdiskCompressionError(ValueError):
    """Raised when compressor provenance or output violates the contract."""


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_INVOCATION = ("-l", "-12", "--favor-decSpeed")
_LEGACY_MAGIC = bytes.fromhex("02214c18")
_MAX_COMPRESSED_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class RamdiskCompressorLock:
    schema_version: int
    algorithm: str
    source_url: str
    source_tag: str
    source_commit: str
    build_target: str
    build_toolchain: str
    build_cflags: str
    invocation: tuple[str, ...]
    format: str
    legacy_magic_hex: str
    artifacts: dict[str, str]


@dataclass(frozen=True)
class CompressedRamdiskEvidence:
    schema_version: int
    profile_id: str
    algorithm: str
    format: str
    input_sha256: str
    input_size: int
    output_sha256: str
    output_size: int
    compressor_source_url: str
    compressor_source_tag: str
    compressor_source_commit: str
    compressor_platform: str
    compressor_sha256: str
    invocation: tuple[str, ...]
    reproducible: bool

    def canonical_json(self) -> str:
        payload = asdict(self)
        payload["invocation"] = list(self.invocation)
        return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RamdiskCompressionError(f"{label} must be a lowercase SHA-256 digest")
    return value


def load_ramdisk_compressor_lock(path: Path, algorithm: str = "lz4") -> RamdiskCompressorLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RamdiskCompressionError(f"cannot read ramdisk compressor lock: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "compressors"}:
        raise RamdiskCompressionError("invalid ramdisk compressor lock root fields")
    if raw["schema_version"] != 1:
        raise RamdiskCompressionError("unsupported ramdisk compressor lock schema")
    compressors = raw["compressors"]
    if not isinstance(compressors, dict) or algorithm not in compressors:
        raise RamdiskCompressionError(f"compressor is not locked: {algorithm}")
    data = compressors[algorithm]
    required = {
        "source",
        "build",
        "invocation",
        "format",
        "legacy_magic_hex",
        "android_build_reference",
        "artifacts",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise RamdiskCompressionError("invalid compressor lock fields")

    source = data["source"]
    if not isinstance(source, dict) or set(source) != {"url", "tag", "commit"}:
        raise RamdiskCompressionError("invalid compressor source lock")
    url = source["url"]
    tag = source["tag"]
    commit = source["commit"]
    if not isinstance(url, str) or not url.startswith("https://github.com/"):
        raise RamdiskCompressionError("compressor source URL must be an HTTPS GitHub repository")
    if not isinstance(tag, str) or not tag.startswith("v") or not tag[1:]:
        raise RamdiskCompressionError("compressor source tag must be explicit")
    if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
        raise RamdiskCompressionError("compressor source commit must be a full lowercase git SHA")

    build = data["build"]
    if not isinstance(build, dict) or set(build) != {"target", "toolchain", "cflags"}:
        raise RamdiskCompressionError("invalid compressor build lock")
    if build["target"] != "programs/lz4-release" or build["toolchain"] != "gcc-make":
        raise RamdiskCompressionError("unsupported locked compressor build recipe")
    if build["cflags"] != "-O2 -g0 -fno-ident":
        raise RamdiskCompressionError("compressor CFLAGS do not match reproducibility contract")

    invocation = data["invocation"]
    if not isinstance(invocation, list) or tuple(invocation) != _ALLOWED_INVOCATION:
        raise RamdiskCompressionError("compressor invocation must match Android legacy ramdisk policy")
    if data["format"] != "lz4-legacy" or data["legacy_magic_hex"] != _LEGACY_MAGIC.hex():
        raise RamdiskCompressionError("compressor format/magic contract is invalid")
    if not isinstance(data["android_build_reference"], str) or "-l -12 --favor-decSpeed" not in data["android_build_reference"]:
        raise RamdiskCompressionError("Android ramdisk invocation provenance is missing")

    artifacts = data["artifacts"]
    if not isinstance(artifacts, dict):
        raise RamdiskCompressionError("compressor artifacts must be an object")
    normalized: dict[str, str] = {}
    for platform, digest in artifacts.items():
        if not isinstance(platform, str) or not re.fullmatch(r"[a-z0-9]+-[a-z0-9]+", platform):
            raise RamdiskCompressionError("invalid compressor artifact platform")
        normalized[platform] = _require_sha256(digest, f"artifact {platform}")

    return RamdiskCompressorLock(
        schema_version=1,
        algorithm=algorithm,
        source_url=url,
        source_tag=tag,
        source_commit=commit,
        build_target=build["target"],
        build_toolchain=build["toolchain"],
        build_cflags=build["cflags"],
        invocation=_ALLOWED_INVOCATION,
        format="lz4-legacy",
        legacy_magic_hex=_LEGACY_MAGIC.hex(),
        artifacts=normalized,
    )


def authorize_compressor_binary(
    lock: RamdiskCompressorLock,
    platform: str,
    executable: Path,
) -> str:
    expected = lock.artifacts.get(platform)
    if expected is None:
        raise RamdiskCompressionError(f"no reviewed compressor artifact is authorized for {platform}")
    if not executable.is_file():
        raise RamdiskCompressionError("compressor executable does not exist")
    try:
        digest = sha256(executable.read_bytes()).hexdigest()
    except OSError as exc:
        raise RamdiskCompressionError(f"cannot hash compressor executable: {exc}") from exc
    if digest != expected:
        raise RamdiskCompressionError("compressor executable SHA-256 does not match lock")
    return digest


def _compress_once(executable: Path, invocation: tuple[str, ...], source: Path, output: Path) -> None:
    try:
        with source.open("rb") as source_handle, output.open("wb") as output_handle:
            completed = subprocess.run(
                [str(executable), *invocation],
                stdin=source_handle,
                stdout=output_handle,
                stderr=subprocess.PIPE,
                shell=False,
                check=False,
                timeout=120,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RamdiskCompressionError(f"ramdisk compressor execution failed: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RamdiskCompressionError(f"ramdisk compressor returned {completed.returncode}: {stderr}")
    try:
        size = output.stat().st_size
        magic = output.read_bytes()[:4]
    except OSError as exc:
        raise RamdiskCompressionError(f"cannot inspect compressed ramdisk: {exc}") from exc
    if size <= 4 or size > _MAX_COMPRESSED_BYTES:
        raise RamdiskCompressionError("compressed ramdisk size is outside safety bounds")
    if magic != _LEGACY_MAGIC:
        raise RamdiskCompressionError("compressor did not emit Linux-kernel legacy LZ4 format")


def compress_rescue_ramdisk_reproducibly(
    profile: DeviceProfile,
    source_cpio: Path,
    source_evidence: RescueInitramfsEvidence,
    executable: Path,
    lock: RamdiskCompressorLock,
    platform: str,
    output: Path,
    evidence_path: Path,
) -> CompressedRamdiskEvidence:
    """Validate an uncompressed rescue CPIO, compress twice and publish only equal legacy-LZ4 bytes."""
    if profile.ramdisk_compression != "lz4":
        raise RamdiskCompressionError(
            f"profile {profile.profile_id} does not require lz4 ramdisk compression"
        )
    try:
        verify_rescue_initramfs_artifact(source_cpio, source_evidence)
    except RescueInitramfsError as exc:
        raise RamdiskCompressionError(f"source rescue initramfs failed verification: {exc}") from exc
    binary_sha = authorize_compressor_binary(lock, platform, executable)

    output = output.resolve()
    evidence_path = evidence_path.resolve()
    if output == evidence_path:
        raise RamdiskCompressionError("compressed ramdisk and evidence paths must differ")
    if output.exists() or evidence_path.exists():
        raise RamdiskCompressionError("refusing to overwrite compressed ramdisk or evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".kps-lz4-", dir=output.parent) as temp_dir:
        temp = Path(temp_dir)
        first = temp / "ramdisk-a.lz4"
        second = temp / "ramdisk-b.lz4"
        _compress_once(executable, lock.invocation, source_cpio, first)
        _compress_once(executable, lock.invocation, source_cpio, second)
        first_bytes = first.read_bytes()
        second_bytes = second.read_bytes()
        if first_bytes != second_bytes:
            raise RamdiskCompressionError("independent LZ4 ramdisk compressions are not byte-identical")

        evidence = CompressedRamdiskEvidence(
            schema_version=1,
            profile_id=profile.profile_id,
            algorithm=lock.algorithm,
            format=lock.format,
            input_sha256=source_evidence.artifact_sha256,
            input_size=source_evidence.artifact_size,
            output_sha256=sha256(first_bytes).hexdigest(),
            output_size=len(first_bytes),
            compressor_source_url=lock.source_url,
            compressor_source_tag=lock.source_tag,
            compressor_source_commit=lock.source_commit,
            compressor_platform=platform,
            compressor_sha256=binary_sha,
            invocation=lock.invocation,
            reproducible=True,
        )
        artifact_tmp = temp / "ramdisk.lz4"
        evidence_tmp = temp / "ramdisk.lz4.json"
        artifact_tmp.write_bytes(first_bytes)
        evidence_tmp.write_text(evidence.canonical_json(), encoding="utf-8")
        os.replace(artifact_tmp, output)
        try:
            os.replace(evidence_tmp, evidence_path)
        except OSError:
            output.unlink(missing_ok=True)
            raise
    return evidence
