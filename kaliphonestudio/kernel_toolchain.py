"""Source-locked Android Clang toolchain evidence for kernel builds.

This module is device-independent. A lock pins an immutable Gitiles commit and
subtree plus the metadata objects that identify the Android Clang prebuilt. It
can validate upstream metadata without downloading the full toolchain, and can
separately verify a materialized local toolchain before a kernel build. Neither
operation grants hardware or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import base64
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_REV_RE = re.compile(r"^r[0-9]+[a-z0-9]*$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_BUILD_ID_RE = re.compile(r"^[0-9]+$")
MAX_LOCK_BYTES = 128 * 1024
MAX_METADATA_BYTES = 1024 * 1024
MAX_CLANG_BYTES = 512 * 1024 * 1024


class KernelToolchainError(ValueError):
    pass


@dataclass(frozen=True)
class KernelToolchainLock:
    schema_version: int
    name: str
    source_url: str
    source_commit: str
    subtree: str
    tree_sha1: str
    bin_tree_sha1: str
    android_version_blob_sha1: str
    manifest_blob_sha1: str
    android_version: str
    clang_revision: str
    build_id: str
    llvm_project_commit: str
    expected_clang_banner: str
    host: str
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def lock_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class KernelToolchainSourceEvidence:
    schema_version: int
    lock_sha256: str
    source_url: str
    source_commit: str
    subtree: str
    tree_sha1: str
    bin_tree_sha1: str
    android_version_blob_sha1: str
    manifest_blob_sha1: str
    android_version: str
    clang_revision: str
    build_id: str
    llvm_project_commit: str
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaterializedKernelToolchainEvidence:
    schema_version: int
    lock_sha256: str
    clang_sha256: str
    clang_size: int
    android_version_sha256: str
    clang_banner_verified: bool
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _safe_relative(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KernelToolchainError(f"{field} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise KernelToolchainError(f"{field} must be a safe relative POSIX path")
    if any(not part or "\\" in part or any(ord(ch) < 0x20 for ch in part) for part in path.parts):
        raise KernelToolchainError(f"{field} contains unsafe path data")
    return path.as_posix()


def _sha1(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA1_RE.fullmatch(value.lower()):
        raise KernelToolchainError(f"{field} must be a full 40-character lowercase SHA-1")
    return value.lower()


def _nonempty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(ch) < 0x20 for ch in value):
        raise KernelToolchainError(f"{field} must be safe non-empty text")
    return value.strip()


def load_kernel_toolchain_lock(path: Path) -> KernelToolchainLock:
    if not path.is_file() or path.is_symlink():
        raise KernelToolchainError(f"toolchain lock is missing or symlinked: {path}")
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_LOCK_BYTES:
        raise KernelToolchainError("toolchain lock is empty or exceeds safety limit")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KernelToolchainError(f"cannot parse toolchain lock: {exc}") from exc
    if not isinstance(raw, dict):
        raise KernelToolchainError("toolchain lock root must be an object")
    if raw.get("schema_version") != 1:
        raise KernelToolchainError("unsupported kernel toolchain lock schema")

    source_url = _nonempty_text(raw.get("source_url"), "source_url").rstrip("/")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise KernelToolchainError("source_url must be HTTPS without embedded credentials")

    subtree = _safe_relative(raw.get("subtree"), "subtree")
    android_version = _nonempty_text(raw.get("android_version"), "android_version")
    if not _VERSION_RE.fullmatch(android_version):
        raise KernelToolchainError("android_version must be major.minor.patch")
    clang_revision = _nonempty_text(raw.get("clang_revision"), "clang_revision")
    if not _REV_RE.fullmatch(clang_revision):
        raise KernelToolchainError("clang_revision is malformed")
    build_id = _nonempty_text(raw.get("build_id"), "build_id")
    if not _BUILD_ID_RE.fullmatch(build_id):
        raise KernelToolchainError("build_id must be numeric")
    host = _nonempty_text(raw.get("host"), "host")
    banner = _nonempty_text(raw.get("expected_clang_banner"), "expected_clang_banner")
    if android_version not in banner or clang_revision not in banner or build_id not in banner:
        raise KernelToolchainError("expected_clang_banner must bind version, revision and build id")
    if raw.get("beta_gate_credit") is not False:
        raise KernelToolchainError("kernel toolchain source lock must set beta_gate_credit=false")

    lock = KernelToolchainLock(
        schema_version=1,
        name=_nonempty_text(raw.get("name"), "name"),
        source_url=source_url,
        source_commit=_sha1(raw.get("source_commit"), "source_commit"),
        subtree=subtree,
        tree_sha1=_sha1(raw.get("tree_sha1"), "tree_sha1"),
        bin_tree_sha1=_sha1(raw.get("bin_tree_sha1"), "bin_tree_sha1"),
        android_version_blob_sha1=_sha1(raw.get("android_version_blob_sha1"), "android_version_blob_sha1"),
        manifest_blob_sha1=_sha1(raw.get("manifest_blob_sha1"), "manifest_blob_sha1"),
        android_version=android_version,
        clang_revision=clang_revision,
        build_id=build_id,
        llvm_project_commit=_sha1(raw.get("llvm_project_commit"), "llvm_project_commit"),
        expected_clang_banner=banner,
        host=host,
        beta_gate_credit=False,
    )
    if not lock.subtree.endswith(lock.clang_revision):
        raise KernelToolchainError("subtree must end with the locked clang revision")
    return lock


def _strip_gitiles_xssi(payload: bytes) -> bytes:
    prefix = b")]}'\n"
    if not payload.startswith(prefix):
        raise KernelToolchainError("Gitiles JSON is missing the anti-XSSI prefix")
    return payload[len(prefix):]


def verify_gitiles_tree_capture(lock: KernelToolchainLock, payload: bytes) -> None:
    if not payload or len(payload) > MAX_METADATA_BYTES:
        raise KernelToolchainError("Gitiles tree capture is empty or too large")
    try:
        data = json.loads(_strip_gitiles_xssi(payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KernelToolchainError("invalid Gitiles tree JSON") from exc
    if not isinstance(data, dict) or data.get("id") != lock.tree_sha1:
        raise KernelToolchainError("Gitiles subtree id does not match the locked tree")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise KernelToolchainError("Gitiles subtree entries are missing")
    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise KernelToolchainError("Gitiles subtree contains an invalid entry")
        name = entry.get("name")
        if not isinstance(name, str) or name in by_name:
            raise KernelToolchainError("Gitiles subtree contains invalid/duplicate names")
        by_name[name] = entry

    required = {
        "AndroidVersion.txt": ("blob", lock.android_version_blob_sha1),
        f"manifest_{lock.build_id}.xml": ("blob", lock.manifest_blob_sha1),
        "bin": ("tree", lock.bin_tree_sha1),
    }
    for name, (kind, object_id) in required.items():
        entry = by_name.get(name)
        if entry is None:
            raise KernelToolchainError(f"Gitiles subtree is missing {name}")
        if entry.get("type") != kind or entry.get("id") != object_id:
            raise KernelToolchainError(f"Gitiles object identity mismatch for {name}")


def verify_android_version_capture(lock: KernelToolchainLock, payload: bytes) -> str:
    if not payload or len(payload) > 4096:
        raise KernelToolchainError("AndroidVersion capture is empty or too large")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KernelToolchainError("AndroidVersion capture must be UTF-8") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    expected = [lock.android_version, f"based on {lock.clang_revision}"]
    if lines != expected:
        raise KernelToolchainError(f"AndroidVersion mismatch: expected {expected!r}, got {lines!r}")
    return sha256(payload).hexdigest()


def create_source_evidence(
    lock: KernelToolchainLock,
    *,
    tree_payload: bytes,
    android_version_payload: bytes,
) -> KernelToolchainSourceEvidence:
    verify_gitiles_tree_capture(lock, tree_payload)
    verify_android_version_capture(lock, android_version_payload)
    return KernelToolchainSourceEvidence(
        schema_version=1,
        lock_sha256=lock.lock_sha256(),
        source_url=lock.source_url,
        source_commit=lock.source_commit,
        subtree=lock.subtree,
        tree_sha1=lock.tree_sha1,
        bin_tree_sha1=lock.bin_tree_sha1,
        android_version_blob_sha1=lock.android_version_blob_sha1,
        manifest_blob_sha1=lock.manifest_blob_sha1,
        android_version=lock.android_version,
        clang_revision=lock.clang_revision,
        build_id=lock.build_id,
        llvm_project_commit=lock.llvm_project_commit,
        beta_gate_credit=False,
    )


def _read_regular(path: Path, *, maximum: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise KernelToolchainError(f"required regular file is missing or symlinked: {path}")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise KernelToolchainError(f"file is empty or exceeds safety limit: {path}")
    data = path.read_bytes()
    if len(data) != size or path.stat().st_size != size:
        raise KernelToolchainError(f"file changed while reading: {path}")
    return data


def verify_materialized_toolchain(
    lock: KernelToolchainLock,
    root: Path,
    *,
    clang_relpath: str = "bin/clang",
) -> MaterializedKernelToolchainEvidence:
    """Verify a local exact toolchain before it is allowed into a kernel build."""
    if not root.is_dir() or root.is_symlink():
        raise KernelToolchainError("materialized toolchain root must be a real directory")
    version_payload = _read_regular(root / "AndroidVersion.txt", maximum=4096)
    version_sha256 = verify_android_version_capture(lock, version_payload)

    rel = _safe_relative(clang_relpath, "clang_relpath")
    clang = root.joinpath(*PurePosixPath(rel).parts)
    clang_payload = _read_regular(clang, maximum=MAX_CLANG_BYTES)
    if not clang.stat().st_mode & 0o111:
        raise KernelToolchainError("clang binary is not executable")
    try:
        result = subprocess.run(
            [str(clang), "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KernelToolchainError("cannot execute locked clang --version") from exc
    output = result.stdout
    if lock.expected_clang_banner not in output or lock.llvm_project_commit not in output:
        raise KernelToolchainError("clang --version does not match the locked compiler identity")

    return MaterializedKernelToolchainEvidence(
        schema_version=1,
        lock_sha256=lock.lock_sha256(),
        clang_sha256=sha256(clang_payload).hexdigest(),
        clang_size=len(clang_payload),
        android_version_sha256=version_sha256,
        clang_banner_verified=True,
        beta_gate_credit=False,
    )


def _download(url: str, *, opener: Callable[..., Any] = urlopen) -> bytes:
    request = Request(url, headers={"User-Agent": "KaliPhoneStudio-source-lock/1"})
    try:
        with opener(request, timeout=30) as response:
            payload = response.read(MAX_METADATA_BYTES + 1)
    except Exception as exc:
        raise KernelToolchainError(f"cannot fetch locked upstream metadata: {url}") from exc
    if not payload or len(payload) > MAX_METADATA_BYTES:
        raise KernelToolchainError("upstream metadata response is empty or exceeds safety limit")
    return payload


def capture_gitiles_source_evidence(
    lock: KernelToolchainLock,
    *,
    opener: Callable[..., Any] = urlopen,
) -> KernelToolchainSourceEvidence:
    base = f"{lock.source_url}/+/{lock.source_commit}/{lock.subtree}"
    tree_payload = _download(f"{base}/?format=JSON", opener=opener)
    encoded_version = _download(f"{base}/AndroidVersion.txt?format=TEXT", opener=opener)
    try:
        version_payload = base64.b64decode(encoded_version, validate=True)
    except ValueError as exc:
        raise KernelToolchainError("Gitiles AndroidVersion response is not valid base64") from exc
    return create_source_evidence(lock, tree_payload=tree_payload, android_version_payload=version_payload)


def write_evidence(evidence: Any, destination: Path) -> str:
    if destination.exists():
        raise KernelToolchainError(f"refusing to overwrite existing evidence: {destination}")
    payload = evidence.canonical_json()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8", newline="\n")
    return sha256(payload.encode("utf-8")).hexdigest()
