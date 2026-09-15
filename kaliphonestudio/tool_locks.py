"""Versioned, fail-closed host-tool lock manifests."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")


class ToolLockError(ValueError):
    pass


@dataclass(frozen=True)
class ToolArtifact:
    platform: str
    sha256: str


@dataclass(frozen=True)
class ToolLockManifest:
    extractor: str
    source_url: str
    source_commit: str
    toolchain: str
    toolchain_version: str
    build_command: tuple[str, ...]
    artifacts: Mapping[str, ToolArtifact]

    def require_artifact(self, platform: str) -> ToolArtifact:
        try:
            return self.artifacts[platform]
        except KeyError as exc:
            raise ToolLockError(f"no locked extractor artifact for platform: {platform}") from exc


def load_tool_lock(path: Path) -> ToolLockManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolLockError(f"cannot read tool lock manifest: {exc}") from exc

    if data.get("schema_version") != 1:
        raise ToolLockError("unsupported tool lock schema")
    extractor = data.get("extractor")
    source = data.get("source") or {}
    build = data.get("build") or {}
    if not isinstance(extractor, str) or not extractor:
        raise ToolLockError("extractor name is required")
    source_url = source.get("url")
    source_commit = source.get("commit")
    if not isinstance(source_url, str) or not source_url.startswith("https://github.com/"):
        raise ToolLockError("extractor source must be an HTTPS GitHub URL")
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        raise ToolLockError("extractor source must be pinned to a full commit")

    toolchain = build.get("toolchain")
    toolchain_version = build.get("toolchain_version")
    if toolchain != "go":
        raise ToolLockError("unsupported extractor toolchain")
    if not isinstance(toolchain_version, str) or not _VERSION_RE.fullmatch(toolchain_version):
        raise ToolLockError("pinned toolchain version is required")

    command = build.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise ToolLockError("reproducible build command is required")

    raw_artifacts = data.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        raise ToolLockError("artifacts must be an object")
    artifacts: dict[str, ToolArtifact] = {}
    for platform, entry in raw_artifacts.items():
        if not isinstance(platform, str) or not platform or not isinstance(entry, dict):
            raise ToolLockError("invalid artifact entry")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ToolLockError(f"invalid SHA-256 for platform: {platform}")
        artifacts[platform] = ToolArtifact(platform=platform, sha256=digest)

    return ToolLockManifest(
        extractor=extractor,
        source_url=source_url,
        source_commit=source_commit,
        toolchain=toolchain,
        toolchain_version=toolchain_version,
        build_command=tuple(command),
        artifacts=artifacts,
    )
