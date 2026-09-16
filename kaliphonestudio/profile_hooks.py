"""Generic, explicit profile hook registry for device-specific host stages.

Hooks are deliberately *not* auto-discovered or imported from device directories.
A trusted caller must register an in-process callback under a stable hook ID, and a
profile must explicitly declare that ID for the requested stage. This keeps the core
multi-device and avoids turning profile JSON into an arbitrary shell execution
surface.

Recovery hooks require an additional explicit opt-in. Hook evidence is host-side only
and can never claim physical-device or Beta credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping

from .profiles import DeviceProfile, ProfileError


HOOK_SCHEMA_VERSION = 1
_ALLOWED_STAGES = frozenset({"build", "verify", "recovery"})
_SAFE_HOOK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)*$")


class ProfileHookError(RuntimeError):
    """Raised when a profile hook contract cannot be satisfied safely."""


@dataclass(frozen=True)
class HookContext:
    """Minimal host context supplied to a registered callback.

    No ADB/Fastboot/device handle is supplied. A callback that needs phone access is
    outside this generic host-hook contract and must use a dedicated, separately
    authorized workflow.
    """

    profile_id: str
    stage: str
    workspace: Path
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class HookResult:
    hook_id: str
    stage: str
    ok: bool
    summary: str
    details: Mapping[str, Any]


@dataclass(frozen=True)
class ProfileHookExecutionEvidence:
    schema_version: int
    profile_id: str
    stage: str
    declared_hook_ids: tuple[str, ...]
    result_digests: tuple[str, ...]
    all_ok: bool
    recovery_explicitly_authorized: bool
    beta_gate_credit: bool = False
    hardware_verified: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


HookCallback = Callable[[HookContext], HookResult]


@dataclass(frozen=True)
class _RegisteredHook:
    hook_id: str
    stage: str
    callback: HookCallback


class ProfileHookRegistry:
    """In-process registry of trusted callbacks.

    Registration and execution are explicit. There is no module/path auto-import and
    no shell command expansion from profile data.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, _RegisteredHook] = {}

    def register(self, hook_id: str, stage: str, callback: HookCallback) -> None:
        _validate_hook_id(hook_id)
        _validate_stage(stage)
        if not callable(callback):
            raise ProfileHookError("hook callback must be callable")
        if hook_id in self._hooks:
            raise ProfileHookError(f"duplicate hook registration: {hook_id}")
        self._hooks[hook_id] = _RegisteredHook(hook_id=hook_id, stage=stage, callback=callback)

    def resolve(self, hook_id: str, stage: str) -> HookCallback:
        _validate_hook_id(hook_id)
        _validate_stage(stage)
        registered = self._hooks.get(hook_id)
        if registered is None:
            raise ProfileHookError(f"profile declared unregistered hook: {hook_id}")
        if registered.stage != stage:
            raise ProfileHookError(
                f"hook {hook_id} is registered for {registered.stage}, not {stage}"
            )
        return registered.callback

    def registered_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._hooks))


def _validate_stage(stage: str) -> None:
    if stage not in _ALLOWED_STAGES:
        raise ProfileHookError(f"unsupported profile hook stage: {stage!r}")


def _validate_hook_id(hook_id: str) -> None:
    if not isinstance(hook_id, str) or not _SAFE_HOOK_ID_RE.fullmatch(hook_id):
        raise ProfileHookError(f"unsafe profile hook id: {hook_id!r}")


def validate_profile_hooks_contract(raw: Any) -> None:
    """Validate the optional profile `hooks` object.

    The accepted shape is strictly stage -> ordered list of unique stable IDs. Empty
    stage lists are allowed; unknown keys are rejected so profile intent is explicit.
    """
    if raw is None:
        return
    if not isinstance(raw, dict):
        raise ProfileError("hooks must be an object")
    unknown = sorted(set(raw) - _ALLOWED_STAGES)
    if unknown:
        raise ProfileError(f"hooks contains unsupported stages: {', '.join(unknown)}")
    for stage, hook_ids in raw.items():
        if not isinstance(hook_ids, list):
            raise ProfileError(f"hooks.{stage} must be a list")
        if len(hook_ids) != len(set(hook_ids)):
            raise ProfileError(f"hooks.{stage} must not contain duplicates")
        for hook_id in hook_ids:
            if not isinstance(hook_id, str) or not _SAFE_HOOK_ID_RE.fullmatch(hook_id):
                raise ProfileError(f"hooks.{stage} contains an unsafe hook id")


def declared_profile_hooks(profile: DeviceProfile, stage: str) -> tuple[str, ...]:
    _validate_stage(stage)
    raw = profile.data.get("hooks")
    validate_profile_hooks_contract(raw)
    if raw is None:
        return ()
    return tuple(raw.get(stage, ()))


def _canonical_result_digest(result: HookResult) -> str:
    payload = {
        "details": dict(result.details),
        "hook_id": result.hook_id,
        "ok": result.ok,
        "stage": result.stage,
        "summary": result.summary,
    }
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n").encode("utf-8")
    return sha256(encoded).hexdigest()


def execute_profile_hooks(
    profile: DeviceProfile,
    stage: str,
    registry: ProfileHookRegistry,
    *,
    workspace: Path,
    metadata: Mapping[str, Any] | None = None,
    allow_recovery: bool = False,
) -> tuple[list[HookResult], ProfileHookExecutionEvidence]:
    """Execute one declared host stage in profile order and emit canonical evidence.

    Recovery is fail-closed unless the caller explicitly sets `allow_recovery=True`.
    Any exception, malformed result, wrong hook/stage result, or negative result stops
    the chain and raises `ProfileHookError`; partial success cannot be misrepresented
    as accepted evidence.
    """
    _validate_stage(stage)
    if stage == "recovery" and not allow_recovery:
        raise ProfileHookError("recovery hooks require explicit allow_recovery=True")

    hook_ids = declared_profile_hooks(profile, stage)
    work = Path(workspace)
    if not work.exists() or not work.is_dir():
        raise ProfileHookError("hook workspace must be an existing directory")

    safe_metadata = MappingProxyType(dict(metadata or {}))
    context = HookContext(
        profile_id=profile.profile_id,
        stage=stage,
        workspace=work.resolve(),
        metadata=safe_metadata,
    )

    results: list[HookResult] = []
    digests: list[str] = []
    for hook_id in hook_ids:
        callback = registry.resolve(hook_id, stage)
        try:
            result = callback(context)
        except Exception as exc:  # callback boundary must fail closed
            raise ProfileHookError(f"hook {hook_id} raised {type(exc).__name__}: {exc}") from exc
        if not isinstance(result, HookResult):
            raise ProfileHookError(f"hook {hook_id} returned an invalid result type")
        if result.hook_id != hook_id or result.stage != stage:
            raise ProfileHookError(f"hook {hook_id} returned mismatched identity/stage")
        if not isinstance(result.ok, bool):
            raise ProfileHookError(f"hook {hook_id} returned non-boolean ok state")
        if not isinstance(result.summary, str) or not result.summary.strip():
            raise ProfileHookError(f"hook {hook_id} returned an empty summary")
        if not isinstance(result.details, Mapping):
            raise ProfileHookError(f"hook {hook_id} returned invalid details")
        results.append(result)
        digests.append(_canonical_result_digest(result))
        if not result.ok:
            raise ProfileHookError(f"hook {hook_id} failed: {result.summary}")

    evidence = ProfileHookExecutionEvidence(
        schema_version=HOOK_SCHEMA_VERSION,
        profile_id=profile.profile_id,
        stage=stage,
        declared_hook_ids=hook_ids,
        result_digests=tuple(digests),
        all_ok=True,
        recovery_explicitly_authorized=(stage == "recovery" and allow_recovery),
        beta_gate_credit=False,
        hardware_verified=False,
    )
    return results, evidence
