"""Deterministic, security-preserving canonicalization for built Kali rootfs archives.

The pinned NetHunter builder is authoritative for package selection and filesystem
contents, but it necessarily creates machine-local values, build logs, mutable package
indexes/caches and wall-clock mtimes. This module removes only explicitly reviewed
volatile or regenerable state and rewrites the tar.xz deterministically before
independent A/B artifacts are compared.

It never extracts the archive to the host filesystem and never grants hardware/Beta
credit. Package selection remains verified separately from dpkg status and strict
byte-for-byte equality remains the final reproducibility gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import copy
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

from .rootfs import RootfsError


_CANONICAL_MTIME = 0
_DPKG_STATUS_SUFFIX = ("var", "lib", "dpkg", "status")
_ZERO_CONTENT_PATHS = {
    "etc/fake-hwclock.data",
    "etc/machine-id",
    "var/lib/dbus/machine-id",
}
# Exact generated state which is safe to recreate on the target. In particular,
# random seeds must never be cloned from a build host into multiple devices.
_DROP_PATHS = {
    "var/cache/ldconfig/aux-cache",
    "var/lib/systemd/random-seed",
    "var/lib/urandom/random-seed",
}
# Prefixes below contain only build/runtime logs, network-derived package indexes or
# derived caches. Keep their top-level directories but omit children so normal runtime
# tools can repopulate them. Do not add configuration/state paths here.
_DROP_PREFIXES = (
    "var/cache/apt/archives/",
    "var/cache/fontconfig/",
    "var/cache/man/",
    "var/lib/apt/lists/",
    "var/log/",
)
_SHADOW_PATH = "etc/shadow"
_MAX_SHADOW_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class RootfsCanonicalizationEvidence:
    schema_version: int
    input_sha256: str
    input_size: int
    output_sha256: str
    output_size: int
    member_count_input: int
    member_count_output: int
    normalized_mtime_count: int
    zeroed_volatile_files: int
    locked_password_entries: int
    dropped_cache_entries: int
    archive_prefix: str
    beta_gate_credit: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _sha256_and_size(path: Path) -> tuple[str, int]:
    if not path.is_file() or path.is_symlink():
        raise RootfsError(f"rootfs archive must be a regular file: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise RootfsError("rootfs archive is empty")
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest(), size


def _safe_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise RootfsError("rootfs archive contains an invalid member name")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise RootfsError("rootfs archive contains an absolute member path")
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if ".." in parts:
        raise RootfsError("rootfs archive contains path traversal")
    return parts


def _detect_prefix(members: list[tarfile.TarInfo]) -> tuple[str, ...]:
    candidates: list[tuple[str, ...]] = []
    for member in members:
        parts = _safe_parts(member.name)
        if len(parts) >= len(_DPKG_STATUS_SUFFIX) and parts[-4:] == _DPKG_STATUS_SUFFIX:
            prefix = parts[:-4]
            if len(prefix) > 1:
                raise RootfsError("rootfs dpkg status is nested below more than one archive prefix")
            candidates.append(prefix)
    if len(candidates) != 1:
        raise RootfsError("rootfs archive must contain exactly one safe var/lib/dpkg/status")
    return candidates[0]


def _logical_path(parts: tuple[str, ...], prefix: tuple[str, ...]) -> str:
    if prefix:
        if parts == prefix:
            return ""
        if len(parts) < len(prefix) or parts[: len(prefix)] != prefix:
            raise RootfsError("rootfs archive member escapes the single top-level prefix")
        parts = parts[len(prefix) :]
    return "/".join(parts)


def _drop_volatile_path(logical: str) -> bool:
    if logical in _DROP_PATHS:
        return True
    return any(logical.startswith(prefix) for prefix in _DROP_PREFIXES)


def _canonical_shadow(data: bytes) -> tuple[bytes, int]:
    if len(data) > _MAX_SHADOW_BYTES:
        raise RootfsError("rootfs shadow file is unreasonably large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RootfsError("rootfs shadow file is not valid UTF-8") from exc

    changed = 0
    output: list[str] = []
    for raw_line in text.splitlines():
        if not raw_line or raw_line.startswith("#"):
            output.append(raw_line)
            continue
        fields = raw_line.split(":")
        if len(fields) < 2 or not fields[0]:
            raise RootfsError("rootfs shadow file contains a malformed account record")

        # Preserve the conventional '*' non-login marker. Any other password field,
        # including !<hash>, is normalized to one locked marker. This removes random
        # salt/hash identity without introducing a shared deterministic password.
        # First-boot provisioning must create real user credentials later.
        if fields[1] != "*" and fields[1] != "!":
            fields[1] = "!"
            changed += 1
        if len(fields) >= 3 and fields[2] != "0":
            fields[2] = "0"
            changed += 1
        output.append(":".join(fields))
    return ("\n".join(output) + "\n").encode("utf-8"), changed


def _canonical_member(member: tarfile.TarInfo) -> tarfile.TarInfo:
    result = copy.copy(member)
    result.mtime = _CANONICAL_MTIME
    # Preserve security/xattr PAX keys, but remove host-observation timestamps and
    # normalize an explicit extended mtime when present.
    result.pax_headers = dict(member.pax_headers)
    result.pax_headers.pop("atime", None)
    result.pax_headers.pop("ctime", None)
    if "mtime" in result.pax_headers:
        result.pax_headers["mtime"] = str(_CANONICAL_MTIME)
    return result


def canonicalize_rootfs_archive(source_path: Path, destination_path: Path) -> RootfsCanonicalizationEvidence:
    """Rewrite one built rootfs into the deterministic comparison/release form.

    Reviewed normalization policy:
    * all tar member mtimes -> epoch 0;
    * machine-id/dbus machine-id/fake-hwclock payloads -> empty;
    * password hashes and password-aging build dates in /etc/shadow -> locked/canonical;
    * package-download/index caches, font/man/ldconfig caches and build logs -> omitted;
    * runtime random seeds -> omitted so target devices never inherit build-host entropy.

    No package payload, configuration file or persistent application state is otherwise
    changed. The legacy ``dropped_cache_entries`` evidence counter intentionally counts
    all reviewed omitted volatile entries to preserve evidence schema compatibility.
    """
    source_path = source_path.resolve(strict=True)
    destination_path = destination_path.resolve(strict=False)
    if destination_path.exists():
        raise RootfsError("refusing to overwrite an existing canonical rootfs artifact")
    if source_path == destination_path:
        raise RootfsError("canonical rootfs input and output must be different files")

    input_sha, input_size = _sha256_and_size(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_mtime_count = 0
    zeroed = 0
    locked_passwords = 0
    dropped = 0
    output_count = 0
    members: list[tarfile.TarInfo] = []
    prefix: tuple[str, ...] = ()

    try:
        with tarfile.open(source_path, mode="r:xz") as source:
            members = source.getmembers()
            if not members:
                raise RootfsError("rootfs archive has no members")
            prefix = _detect_prefix(members)
            seen_names: set[str] = set()
            for member in members:
                if member.name in seen_names:
                    raise RootfsError("rootfs archive contains duplicate member names")
                seen_names.add(member.name)

            with tarfile.open(destination_path, mode="w:xz", format=tarfile.PAX_FORMAT) as output:
                for member in members:
                    parts = _safe_parts(member.name)
                    logical = _logical_path(parts, prefix)
                    if _drop_volatile_path(logical):
                        dropped += 1
                        continue

                    normalized = _canonical_member(member)
                    if member.mtime != _CANONICAL_MTIME or member.pax_headers.get("mtime") not in {None, "0"}:
                        normalized_mtime_count += 1

                    payload = None
                    if member.isfile():
                        extracted = source.extractfile(member)
                        if extracted is None:
                            raise RootfsError(f"cannot read regular rootfs member: {member.name}")
                        if logical in _ZERO_CONTENT_PATHS:
                            normalized.size = 0
                            payload = io.BytesIO(b"")
                            zeroed += 1
                        elif logical == _SHADOW_PATH:
                            original = extracted.read(_MAX_SHADOW_BYTES + 1)
                            canonical, changed = _canonical_shadow(original)
                            normalized.size = len(canonical)
                            payload = io.BytesIO(canonical)
                            locked_passwords += changed
                        else:
                            payload = extracted

                    output.addfile(normalized, payload)
                    output_count += 1
    except (RootfsError, tarfile.TarError, OSError) as exc:
        try:
            destination_path.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, RootfsError):
            raise
        raise RootfsError(f"cannot canonicalize rootfs archive: {exc}") from exc

    output_sha, output_size = _sha256_and_size(destination_path)
    evidence = RootfsCanonicalizationEvidence(
        schema_version=1,
        input_sha256=input_sha,
        input_size=input_size,
        output_sha256=output_sha,
        output_size=output_size,
        member_count_input=len(members),
        member_count_output=output_count,
        normalized_mtime_count=normalized_mtime_count,
        zeroed_volatile_files=zeroed,
        locked_password_entries=locked_passwords,
        dropped_cache_entries=dropped,
        archive_prefix=prefix[0] if prefix else "",
        beta_gate_credit=False,
    )
    if evidence.member_count_input - evidence.member_count_output != evidence.dropped_cache_entries:
        destination_path.unlink(missing_ok=True)
        raise RootfsError("canonical rootfs member accounting mismatch")
    return evidence


def write_canonicalization_evidence(
    evidence: RootfsCanonicalizationEvidence, destination: Path
) -> str:
    if evidence.schema_version != 1 or evidence.beta_gate_credit is not False:
        raise RootfsError("invalid rootfs canonicalization evidence")
    if destination.exists():
        raise RootfsError("refusing to overwrite rootfs canonicalization evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
    return evidence.evidence_sha256()
