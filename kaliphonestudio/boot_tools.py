"""Source-lock contract for Android boot image assembly/inspection tooling."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from .boot_image import BootImageError

_FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_TOOLS = {"mkbootimg", "unpack_bootimg"}


@dataclass(frozen=True)
class BootToolLock:
    name: str
    repository: str
    commit: str
    entrypoint: str
    supported_header_versions: tuple[int, ...]
    invocation_policy: str

    def argv(self, checkout: Path) -> tuple[str, str]:
        """Return an explicit Python-script invocation target; never PATH-discover tools."""
        script = checkout / self.entrypoint
        if not script.is_file():
            raise BootImageError(f"locked boot tool entrypoint missing: {script}")
        return ("python", str(script))


def load_boot_tool_locks(path: Path) -> dict[str, BootToolLock]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BootImageError(f"cannot load boot tool lock manifest: {exc}") from exc
    if raw.get("schema_version") != 1:
        raise BootImageError("unsupported boot tool lock schema")
    if set(raw) != {"schema_version", *_ALLOWED_TOOLS}:
        raise BootImageError("boot tool lock manifest must contain exactly the required tools")

    locks: dict[str, BootToolLock] = {}
    for name in sorted(_ALLOWED_TOOLS):
        item = raw.get(name)
        if not isinstance(item, dict):
            raise BootImageError(f"missing boot tool lock: {name}")
        commit = str(item.get("commit", "")).lower()
        repository = str(item.get("repository", "")).strip()
        entrypoint = str(item.get("entrypoint", "")).strip()
        policy = str(item.get("invocation_policy", "")).strip()
        versions = item.get("supported_header_versions")
        if not _FULL_COMMIT.fullmatch(commit):
            raise BootImageError(f"boot tool {name} must pin a full 40-character commit")
        if not repository.startswith("https://github.com/"):
            raise BootImageError(f"boot tool {name} repository must be an HTTPS GitHub source")
        if Path(entrypoint).name != entrypoint or not entrypoint.endswith(".py"):
            raise BootImageError(f"unsafe boot tool entrypoint: {name}")
        if policy != "python-entrypoint-from-exact-commit-only":
            raise BootImageError(f"unsupported boot tool invocation policy: {name}")
        if not isinstance(versions, list) or not versions or any(not isinstance(v, int) or v < 0 for v in versions):
            raise BootImageError(f"invalid supported header versions for {name}")
        if len(versions) != len(set(versions)):
            raise BootImageError(f"duplicate supported header version for {name}")
        locks[name] = BootToolLock(name, repository, commit, entrypoint, tuple(versions), policy)
    return locks


def _require_tool_for_header(locks: dict[str, BootToolLock], name: str, header_version: int) -> BootToolLock:
    lock = locks.get(name)
    if lock is None or header_version not in lock.supported_header_versions:
        raise BootImageError(f"no source-locked {name} authorized for boot header v{header_version}")
    return lock


def require_assembler_for_header(locks: dict[str, BootToolLock], header_version: int) -> BootToolLock:
    return _require_tool_for_header(locks, "mkbootimg", header_version)


def require_inspector_for_header(locks: dict[str, BootToolLock], header_version: int) -> BootToolLock:
    return _require_tool_for_header(locks, "unpack_bootimg", header_version)
