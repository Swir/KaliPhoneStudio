"""Device-independent Kali ARM64 rootfs source and reproducibility evidence.

This module deliberately separates a *build source lock* from proof that a concrete
rootfs artifact was reproducible. A moving kali-rolling mirror is never treated as
reproducible by itself: callers must bind repository metadata/package-index hashes
and compare two independently produced artifacts byte-for-byte.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class RootfsError(ValueError):
    """Raised when rootfs provenance/reproducibility evidence is incomplete."""


def _require_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RootfsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RootfsError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True)
class RootfsSourceLock:
    schema_version: int
    source_url: str
    source_commit: str
    release_tag: str
    suite: str
    architecture: str
    variant: str
    mirror: str
    command: tuple[str, ...]
    repository_evidence_required: bool
    double_build_required: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def lock_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RepositorySnapshotEvidence:
    schema_version: int
    mirror: str
    suite: str
    architecture: str
    inrelease_sha256: str
    package_index_sha256s: tuple[str, ...]
    package_manifest_sha256: str

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RootfsArtifactEvidence:
    schema_version: int
    source_lock_sha256: str
    repository_snapshot_sha256: str
    architecture: str
    variant: str
    artifact_sha256: str
    artifact_size: int
    reproducible: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def validate_rootfs_source_lock(lock: RootfsSourceLock) -> None:
    if lock.schema_version != 1:
        raise RootfsError("unsupported rootfs source-lock schema")
    if not isinstance(lock.source_commit, str) or not _COMMIT_RE.fullmatch(lock.source_commit):
        raise RootfsError("rootfs source must be pinned to a full 40-hex commit")
    if not isinstance(lock.source_url, str) or not lock.source_url.startswith("https://"):
        raise RootfsError("rootfs source URL must use HTTPS")
    _require_text(lock.release_tag, "rootfs release tag")
    if lock.architecture != "arm64":
        raise RootfsError("KaliPhoneStudio common phone rootfs must be arm64")
    if lock.suite != "kali-rolling":
        raise RootfsError("rootfs suite must be explicitly kali-rolling")
    if lock.variant not in {"minimal", "full"}:
        raise RootfsError("unsupported rootfs variant")
    if not isinstance(lock.mirror, str) or not lock.mirror.startswith(("http://", "https://")):
        raise RootfsError("rootfs mirror must be an explicit HTTP(S) URL")
    if not lock.command or not all(isinstance(item, str) and item for item in lock.command):
        raise RootfsError("rootfs build command must be a non-empty argv list")
    if lock.command[0] != "./build-fs.sh" or "arm64" not in lock.command:
        raise RootfsError("rootfs build command is not bound to the pinned ARM64 builder")
    if lock.mirror not in lock.command:
        raise RootfsError("rootfs build command must use the locked mirror")
    if lock.variant == "minimal" and not ({"--minimal", "-m"} & set(lock.command)):
        raise RootfsError("minimal rootfs lock must request the minimal variant")
    if lock.variant == "full" and not ({"--full", "-f"} & set(lock.command)):
        raise RootfsError("full rootfs lock must request the full variant")
    if lock.repository_evidence_required is not True:
        raise RootfsError("rolling rootfs builds must require repository snapshot evidence")
    if lock.double_build_required is not True:
        raise RootfsError("rootfs reproducibility requires independent double-build equality")


def load_rootfs_source_lock(path: Path) -> RootfsSourceLock:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read rootfs source lock: {exc}") from exc
    if not isinstance(raw, dict):
        raise RootfsError("rootfs source lock must be a JSON object")
    if set(raw) != {"schema_version", "source", "build_contract"}:
        raise RootfsError("unexpected rootfs source-lock top-level fields")
    if raw["schema_version"] != 1:
        raise RootfsError("unsupported rootfs source-lock schema")
    source = raw["source"]
    build = raw["build_contract"]
    if not isinstance(source, dict) or set(source) != {"url", "commit", "release_tag"}:
        raise RootfsError("unexpected rootfs source fields")
    required_build = {
        "suite", "architecture", "variant", "mirror", "command",
        "repository_evidence_required", "double_build_required",
    }
    if not isinstance(build, dict) or set(build) != required_build:
        raise RootfsError("unexpected rootfs build-contract fields")
    command = build["command"]
    if not isinstance(command, list):
        raise RootfsError("rootfs build command must be an argv list")
    lock = RootfsSourceLock(
        1,
        _require_text(source["url"], "rootfs source URL"),
        _require_text(source["commit"], "rootfs source commit"),
        _require_text(source["release_tag"], "rootfs release tag"),
        _require_text(build["suite"], "rootfs suite"),
        _require_text(build["architecture"], "rootfs architecture"),
        _require_text(build["variant"], "rootfs variant"),
        _require_text(build["mirror"], "rootfs mirror"),
        tuple(command),
        build["repository_evidence_required"],
        build["double_build_required"],
    )
    validate_rootfs_source_lock(lock)
    return lock


def repository_snapshot_from_dict(raw: dict[str, Any]) -> RepositorySnapshotEvidence:
    if not isinstance(raw, dict):
        raise RootfsError("repository snapshot evidence must be a JSON object")
    required = {
        "schema_version", "mirror", "suite", "architecture", "inrelease_sha256",
        "package_index_sha256s", "package_manifest_sha256",
    }
    if set(raw) != required or raw["schema_version"] != 1:
        raise RootfsError("invalid repository snapshot evidence schema")
    indexes = raw["package_index_sha256s"]
    if not isinstance(indexes, list) or not indexes:
        raise RootfsError("repository snapshot requires at least one package-index SHA-256")
    return RepositorySnapshotEvidence(
        1,
        _require_text(raw["mirror"], "repository mirror"),
        _require_text(raw["suite"], "repository suite"),
        _require_text(raw["architecture"], "repository architecture"),
        _require_sha256(raw["inrelease_sha256"], "InRelease"),
        tuple(_require_sha256(item, "package index") for item in indexes),
        _require_sha256(raw["package_manifest_sha256"], "package manifest"),
    )


def load_repository_snapshot(path: Path) -> RepositorySnapshotEvidence:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read repository snapshot evidence: {exc}") from exc
    return repository_snapshot_from_dict(raw)


def validate_repository_snapshot(lock: RootfsSourceLock, snapshot: RepositorySnapshotEvidence) -> None:
    validate_rootfs_source_lock(lock)
    if snapshot.schema_version != 1:
        raise RootfsError("unsupported repository snapshot schema")
    if snapshot.mirror != lock.mirror or snapshot.suite != lock.suite or snapshot.architecture != lock.architecture:
        raise RootfsError("repository snapshot does not match rootfs source lock")
    _require_sha256(snapshot.inrelease_sha256, "InRelease")
    if not snapshot.package_index_sha256s:
        raise RootfsError("repository snapshot has no package-index hashes")
    for digest in snapshot.package_index_sha256s:
        _require_sha256(digest, "package index")
    _require_sha256(snapshot.package_manifest_sha256, "package manifest")


def _sha256_and_size(path: Path) -> tuple[str, int]:
    if not path.is_file():
        raise RootfsError(f"rootfs artifact does not exist: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RootfsError("rootfs artifact is empty")
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest(), size


def _files_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            a = left.read(1024 * 1024)
            b = right.read(1024 * 1024)
            if a != b:
                return False
            if not a:
                return True


def create_reproducible_rootfs_evidence(
    lock: RootfsSourceLock,
    snapshot: RepositorySnapshotEvidence,
    *,
    first_artifact: Path,
    second_artifact: Path,
) -> RootfsArtifactEvidence:
    validate_repository_snapshot(lock, snapshot)
    first_hash, first_size = _sha256_and_size(first_artifact)
    second_hash, second_size = _sha256_and_size(second_artifact)
    if first_size != second_size or first_hash != second_hash or not _files_equal(first_artifact, second_artifact):
        raise RootfsError("rootfs double build is not reproducible byte-for-byte")
    return RootfsArtifactEvidence(
        1, lock.lock_sha256(), snapshot.evidence_sha256(), lock.architecture,
        lock.variant, first_hash, first_size, True,
    )


def verify_rootfs_artifact(
    lock: RootfsSourceLock,
    snapshot: RepositorySnapshotEvidence,
    evidence: RootfsArtifactEvidence,
    *,
    artifact: Path,
) -> None:
    validate_repository_snapshot(lock, snapshot)
    if evidence.schema_version != 1 or not evidence.reproducible:
        raise RootfsError("rootfs artifact lacks reproducibility evidence")
    _require_sha256(evidence.source_lock_sha256, "rootfs source-lock evidence")
    _require_sha256(evidence.repository_snapshot_sha256, "repository snapshot evidence")
    _require_sha256(evidence.artifact_sha256, "rootfs artifact")
    if evidence.source_lock_sha256 != lock.lock_sha256():
        raise RootfsError("rootfs source lock changed after build")
    if evidence.repository_snapshot_sha256 != snapshot.evidence_sha256():
        raise RootfsError("rootfs repository snapshot changed after build")
    if evidence.architecture != lock.architecture or evidence.variant != lock.variant:
        raise RootfsError("rootfs artifact evidence target mismatch")
    if evidence.artifact_size <= 0:
        raise RootfsError("rootfs artifact evidence contains an invalid size")
    digest, size = _sha256_and_size(artifact)
    if digest != evidence.artifact_sha256 or size != evidence.artifact_size:
        raise RootfsError("rootfs artifact changed after reproducibility verification")


def write_rootfs_artifact_evidence(evidence: RootfsArtifactEvidence, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
