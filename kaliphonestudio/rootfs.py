"""Device-independent Kali ARM64 rootfs source and reproducibility evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from typing import Any


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_FINGERPRINT_RE = re.compile(r"^[0-9A-F]{40}$")
_PACKAGE_INDEX_RE = re.compile(
    r"^(?:main|contrib|non-free|non-free-firmware)/binary-(?P<arch>[a-z0-9]+)/(?:Packages)(?:\.(?:xz|gz))?$"
)
_MAX_DPKG_STATUS_BYTES = 64 * 1024 * 1024


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
    archive_keyring_url: str
    archive_key_fingerprint: str
    repository_evidence_required: bool
    double_build_required: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def lock_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RepositoryIndexEvidence:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class RepositorySnapshotEvidence:
    schema_version: int
    mirror: str
    suite: str
    architecture: str
    signing_key_fingerprint: str
    inrelease_sha256: str
    package_indexes: tuple[RepositoryIndexEvidence, ...]

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
    package_manifest_sha256: str
    package_count: int
    reproducible: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def validate_rootfs_source_lock(lock: RootfsSourceLock) -> None:
    if lock.schema_version != 2:
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
    if not isinstance(lock.mirror, str) or not lock.mirror.startswith("https://"):
        raise RootfsError("rootfs mirror must be an explicit HTTPS URL")
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
    if not isinstance(lock.archive_keyring_url, str) or not lock.archive_keyring_url.startswith("https://"):
        raise RootfsError("Kali archive keyring URL must use HTTPS")
    if not isinstance(lock.archive_key_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(lock.archive_key_fingerprint):
        raise RootfsError("Kali archive key fingerprint must be exactly 40 uppercase hex characters")
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
    if set(raw) != {"schema_version", "source", "build_contract", "repository_trust"}:
        raise RootfsError("unexpected rootfs source-lock top-level fields")
    if raw["schema_version"] != 2:
        raise RootfsError("unsupported rootfs source-lock schema")
    source = raw["source"]
    build = raw["build_contract"]
    trust = raw["repository_trust"]
    if not isinstance(source, dict) or set(source) != {"url", "commit", "release_tag"}:
        raise RootfsError("unexpected rootfs source fields")
    required_build = {
        "suite", "architecture", "variant", "mirror", "command",
        "repository_evidence_required", "double_build_required",
    }
    if not isinstance(build, dict) or set(build) != required_build:
        raise RootfsError("unexpected rootfs build-contract fields")
    if not isinstance(trust, dict) or set(trust) != {"archive_keyring_url", "archive_key_fingerprint"}:
        raise RootfsError("unexpected rootfs repository-trust fields")
    command = build["command"]
    if not isinstance(command, list):
        raise RootfsError("rootfs build command must be an argv list")
    lock = RootfsSourceLock(
        2,
        _require_text(source["url"], "rootfs source URL"),
        _require_text(source["commit"], "rootfs source commit"),
        _require_text(source["release_tag"], "rootfs release tag"),
        _require_text(build["suite"], "rootfs suite"),
        _require_text(build["architecture"], "rootfs architecture"),
        _require_text(build["variant"], "rootfs variant"),
        _require_text(build["mirror"], "rootfs mirror"),
        tuple(command),
        _require_text(trust["archive_keyring_url"], "Kali archive keyring URL"),
        _require_text(trust["archive_key_fingerprint"], "Kali archive key fingerprint"),
        build["repository_evidence_required"],
        build["double_build_required"],
    )
    validate_rootfs_source_lock(lock)
    return lock


def repository_snapshot_from_dict(raw: dict[str, Any]) -> RepositorySnapshotEvidence:
    if not isinstance(raw, dict):
        raise RootfsError("repository snapshot evidence must be a JSON object")
    required = {
        "schema_version", "mirror", "suite", "architecture", "signing_key_fingerprint",
        "inrelease_sha256", "package_indexes",
    }
    if set(raw) != required or raw["schema_version"] != 2:
        raise RootfsError("invalid repository snapshot evidence schema")
    indexes = raw["package_indexes"]
    if not isinstance(indexes, list) or not indexes:
        raise RootfsError("repository snapshot requires at least one package-index entry")
    parsed: list[RepositoryIndexEvidence] = []
    for item in indexes:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise RootfsError("invalid package-index evidence entry")
        path = _require_text(item["path"], "package index path")
        if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise RootfsError("unsafe package-index path")
        size = item["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise RootfsError("package-index size must be positive")
        parsed.append(RepositoryIndexEvidence(path, size, _require_sha256(item["sha256"], "package index")))
    return RepositorySnapshotEvidence(
        2,
        _require_text(raw["mirror"], "repository mirror"),
        _require_text(raw["suite"], "repository suite"),
        _require_text(raw["architecture"], "repository architecture"),
        _require_text(raw["signing_key_fingerprint"], "repository signing key fingerprint"),
        _require_sha256(raw["inrelease_sha256"], "InRelease"),
        tuple(parsed),
    )


def load_repository_snapshot(path: Path) -> RepositorySnapshotEvidence:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RootfsError(f"cannot read repository snapshot evidence: {exc}") from exc
    return repository_snapshot_from_dict(raw)


def repository_snapshot_from_inrelease(
    lock: RootfsSourceLock,
    inrelease: bytes,
    *,
    signing_key_fingerprint: str,
) -> RepositorySnapshotEvidence:
    """Create evidence from an already GPG-verified Kali InRelease payload."""
    validate_rootfs_source_lock(lock)
    if signing_key_fingerprint != lock.archive_key_fingerprint:
        raise RootfsError("InRelease signature was not made by the locked Kali archive key")
    if not inrelease or len(inrelease) > 16 * 1024 * 1024:
        raise RootfsError("InRelease payload is empty or unreasonably large")
    try:
        text = inrelease.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RootfsError("InRelease is not valid UTF-8") from exc
    in_sha256 = sha256(inrelease).hexdigest()
    in_sha_section = False
    indexes: list[RepositoryIndexEvidence] = []
    seen_paths: set[str] = set()
    for line in text.splitlines():
        if line == "SHA256:":
            in_sha_section = True
            continue
        if not in_sha_section:
            continue
        if line and not line.startswith(" "):
            break
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 3:
            raise RootfsError("malformed SHA256 entry in InRelease")
        digest, size_text, path = parts
        match = _PACKAGE_INDEX_RE.fullmatch(path)
        if not match or match.group("arch") != lock.architecture:
            continue
        _require_sha256(digest, "InRelease package index")
        try:
            size = int(size_text)
        except ValueError as exc:
            raise RootfsError("invalid package-index size in InRelease") from exc
        if size <= 0 or path in seen_paths:
            raise RootfsError("invalid or duplicate package-index entry in InRelease")
        seen_paths.add(path)
        indexes.append(RepositoryIndexEvidence(path, size, digest))
    if not indexes:
        raise RootfsError(f"InRelease contains no {lock.architecture} package indexes")
    indexes.sort(key=lambda item: item.path)
    return RepositorySnapshotEvidence(
        2, lock.mirror, lock.suite, lock.architecture,
        signing_key_fingerprint, in_sha256, tuple(indexes),
    )


def validate_repository_snapshot(lock: RootfsSourceLock, snapshot: RepositorySnapshotEvidence) -> None:
    validate_rootfs_source_lock(lock)
    if snapshot.schema_version != 2:
        raise RootfsError("unsupported repository snapshot schema")
    if snapshot.mirror != lock.mirror or snapshot.suite != lock.suite or snapshot.architecture != lock.architecture:
        raise RootfsError("repository snapshot does not match rootfs source lock")
    if snapshot.signing_key_fingerprint != lock.archive_key_fingerprint:
        raise RootfsError("repository snapshot signing key does not match rootfs source lock")
    _require_sha256(snapshot.inrelease_sha256, "InRelease")
    if not snapshot.package_indexes:
        raise RootfsError("repository snapshot has no package-index evidence")
    for item in snapshot.package_indexes:
        if not _PACKAGE_INDEX_RE.fullmatch(item.path):
            raise RootfsError("repository snapshot contains an unexpected package-index path")
        if item.size <= 0:
            raise RootfsError("repository snapshot package-index size must be positive")
        _require_sha256(item.sha256, "package index")


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


def _parse_dpkg_status(data: bytes) -> tuple[bytes, int]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RootfsError("dpkg status file is not valid UTF-8") from exc
    records: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if not line or line[0].isspace() or ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key] = value.strip()
        if fields.get("Status") != "install ok installed":
            continue
        package = fields.get("Package")
        version = fields.get("Version")
        architecture = fields.get("Architecture")
        if not package or not version or not architecture:
            raise RootfsError("installed dpkg status record is missing package/version/architecture")
        records.append(f"{package}\t{version}\t{architecture}")
    if not records:
        raise RootfsError("rootfs contains no installed dpkg package records")
    records.sort()
    payload = ("\n".join(records) + "\n").encode("utf-8")
    return payload, len(records)


def package_manifest_from_rootfs(artifact: Path) -> tuple[bytes, int]:
    """Extract a normalized installed-package manifest from a rootfs tar archive."""
    try:
        with tarfile.open(artifact, mode="r:*") as archive:
            candidates = [
                member for member in archive.getmembers()
                if member.isfile() and member.name.lstrip("./") == "var/lib/dpkg/status"
            ]
            if len(candidates) != 1:
                raise RootfsError("rootfs must contain exactly one var/lib/dpkg/status file")
            member = candidates[0]
            if member.size <= 0 or member.size > _MAX_DPKG_STATUS_BYTES:
                raise RootfsError("rootfs dpkg status file has an invalid size")
            handle = archive.extractfile(member)
            if handle is None:
                raise RootfsError("cannot read rootfs dpkg status file")
            data = handle.read(_MAX_DPKG_STATUS_BYTES + 1)
            if len(data) > _MAX_DPKG_STATUS_BYTES:
                raise RootfsError("rootfs dpkg status file exceeds safety limit")
    except (tarfile.TarError, OSError) as exc:
        raise RootfsError(f"cannot inspect rootfs archive: {exc}") from exc
    return _parse_dpkg_status(data)


def write_package_manifest(artifact: Path, destination: Path) -> str:
    payload, _ = package_manifest_from_rootfs(artifact)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return sha256(payload).hexdigest()


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
    first_manifest, first_count = package_manifest_from_rootfs(first_artifact)
    second_manifest, second_count = package_manifest_from_rootfs(second_artifact)
    if first_manifest != second_manifest or first_count != second_count:
        raise RootfsError("rootfs double build produced different installed-package manifests")
    return RootfsArtifactEvidence(
        2, lock.lock_sha256(), snapshot.evidence_sha256(), lock.architecture,
        lock.variant, first_hash, first_size, sha256(first_manifest).hexdigest(), first_count, True,
    )


def verify_rootfs_artifact(
    lock: RootfsSourceLock,
    snapshot: RepositorySnapshotEvidence,
    evidence: RootfsArtifactEvidence,
    *,
    artifact: Path,
) -> None:
    validate_repository_snapshot(lock, snapshot)
    if evidence.schema_version != 2 or not evidence.reproducible:
        raise RootfsError("rootfs artifact lacks reproducibility evidence")
    _require_sha256(evidence.source_lock_sha256, "rootfs source-lock evidence")
    _require_sha256(evidence.repository_snapshot_sha256, "repository snapshot evidence")
    _require_sha256(evidence.artifact_sha256, "rootfs artifact")
    _require_sha256(evidence.package_manifest_sha256, "rootfs package manifest")
    if evidence.source_lock_sha256 != lock.lock_sha256():
        raise RootfsError("rootfs source lock changed after build")
    if evidence.repository_snapshot_sha256 != snapshot.evidence_sha256():
        raise RootfsError("rootfs repository snapshot changed after build")
    if evidence.architecture != lock.architecture or evidence.variant != lock.variant:
        raise RootfsError("rootfs artifact evidence target mismatch")
    if evidence.artifact_size <= 0 or evidence.package_count <= 0:
        raise RootfsError("rootfs artifact evidence contains an invalid size/package count")
    digest, size = _sha256_and_size(artifact)
    if digest != evidence.artifact_sha256 or size != evidence.artifact_size:
        raise RootfsError("rootfs artifact changed after reproducibility verification")
    manifest, package_count = package_manifest_from_rootfs(artifact)
    if sha256(manifest).hexdigest() != evidence.package_manifest_sha256 or package_count != evidence.package_count:
        raise RootfsError("rootfs installed-package manifest changed after verification")


def write_repository_snapshot(snapshot: RepositorySnapshotEvidence, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return snapshot.evidence_sha256()


def write_rootfs_artifact_evidence(evidence: RootfsArtifactEvidence, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return evidence.evidence_sha256()
