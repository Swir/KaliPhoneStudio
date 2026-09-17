#!/usr/bin/env python3
"""Capture a read-only physical Fastboot baseline with reviewed tool identity.

The helper first hashes and verifies the exact Fastboot executable against the
reviewed Platform-Tools policy, then executes only ``fastboot devices`` and
``fastboot -s SERIAL getvar all`` using that exact resolved binary. It emits a
capture bundle binding tool + raw transcript + parsed baseline and never boots,
reboots, flashes, erases, changes slots or writes phone storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.fastboot_baseline import (
    capture_fastboot_baseline,
    write_fastboot_baseline_evidence,
)
from kaliphonestudio.fastboot_capture import (
    FastbootCaptureError,
    capture_fastboot_getvar_all,
    validate_capture_with_offline_parser,
    write_capture_once,
)
from kaliphonestudio.fastboot_capture_bundle import (
    FastbootCaptureBundleError,
    bind_fastboot_capture,
    write_fastboot_capture_bundle,
)
from kaliphonestudio.fastboot_tool import (
    FastbootToolError,
    inspect_fastboot_tool,
    write_fastboot_tool_evidence,
)
from kaliphonestudio.profiles import get_profile


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    p.add_argument("--serial", required=True, help="exact serial shown by fastboot devices")
    p.add_argument("--firmware-build", required=True)
    p.add_argument("--firmware-fingerprint", required=True)
    p.add_argument("--fastboot", default="fastboot", help="fastboot executable or full path")
    p.add_argument(
        "--fastboot-policy",
        type=Path,
        default=ROOT / "tools" / "fastboot-tool-policy.json",
        help="reviewed exact Platform-Tools policy",
    )
    p.add_argument("--tool-timeout", type=int, default=15)
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--transcript-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    p.add_argument("--tool-evidence-out", type=Path, required=True)
    p.add_argument("--capture-evidence-out", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    destinations = (
        (args.transcript_out, "transcript"),
        (args.evidence_out, "baseline evidence"),
        (args.tool_evidence_out, "Fastboot tool evidence"),
        (args.capture_evidence_out, "Fastboot capture bundle"),
    )
    normalized = [str(path.resolve(strict=False)) for path, _label in destinations]
    if len(set(normalized)) != len(normalized):
        raise SystemExit("all transcript/evidence destinations must be different")
    for path, label in destinations:
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing to overwrite existing {label}: {path}")

    profile = get_profile(args.devices_root, args.profile_id)
    try:
        tool_evidence, resolved_fastboot = inspect_fastboot_tool(
            args.fastboot,
            policy_path=args.fastboot_policy,
            timeout_seconds=args.tool_timeout,
        )
        payload = capture_fastboot_getvar_all(
            args.serial,
            fastboot=resolved_fastboot,
            timeout_seconds=args.timeout,
        )
        validate_capture_with_offline_parser(payload)
    except (FastbootCaptureError, FastbootToolError) as exc:
        raise SystemExit(str(exc)) from exc

    staged_transcript = args.transcript_out.with_name(args.transcript_out.name + ".capturing")
    staged_evidence = args.evidence_out.with_name(args.evidence_out.name + ".capturing")
    staged_tool = args.tool_evidence_out.with_name(args.tool_evidence_out.name + ".capturing")
    staged_capture = args.capture_evidence_out.with_name(args.capture_evidence_out.name + ".capturing")
    staged = (
        (staged_transcript, "transcript"),
        (staged_evidence, "baseline evidence"),
        (staged_tool, "Fastboot tool evidence"),
        (staged_capture, "Fastboot capture bundle"),
    )
    for path, label in staged:
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing stale {label} staging path: {path}")

    published: list[Path] = []
    try:
        write_capture_once(payload, staged_transcript)
        evidence = capture_fastboot_baseline(
            profile,
            transcript=staged_transcript,
            firmware_build=args.firmware_build,
            firmware_fingerprint=args.firmware_fingerprint,
        )
        if evidence.serialno != args.serial.strip():
            raise SystemExit("captured getvar serialno does not match requested fastboot serial")
        baseline_digest = write_fastboot_baseline_evidence(evidence, staged_evidence)
        tool_digest = write_fastboot_tool_evidence(tool_evidence, staged_tool)
        capture_bundle = bind_fastboot_capture(
            profile,
            evidence,
            tool_evidence,
            transcript=staged_transcript,
        )
        capture_digest = write_fastboot_capture_bundle(capture_bundle, staged_capture)

        if json.loads(staged_evidence.read_text(encoding="utf-8")) != json.loads(evidence.canonical_json()):
            raise SystemExit("Fastboot baseline evidence round-trip mismatch")
        if json.loads(staged_tool.read_text(encoding="utf-8")) != json.loads(tool_evidence.canonical_json()):
            raise SystemExit("Fastboot tool evidence round-trip mismatch")
        if json.loads(staged_capture.read_text(encoding="utf-8")) != json.loads(capture_bundle.canonical_json()):
            raise SystemExit("Fastboot capture bundle round-trip mismatch")
        if any(path.exists() for path, _label in destinations):
            raise SystemExit("capture destination appeared during validation")

        for staged_path, final_path in (
            (staged_transcript, args.transcript_out),
            (staged_evidence, args.evidence_out),
            (staged_tool, args.tool_evidence_out),
            (staged_capture, args.capture_evidence_out),
        ):
            staged_path.replace(final_path)
            published.append(final_path)
    except FastbootCaptureBundleError as exc:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        raise SystemExit(str(exc)) from exc
    except BaseException:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        raise
    finally:
        for path, _label in staged:
            path.unlink(missing_ok=True)

    print(json.dumps({
        "profile_id": evidence.profile_id,
        "product": evidence.product,
        "serialno": evidence.serialno,
        "current_slot": evidence.current_slot,
        "slot_count": evidence.slot_count,
        "unlocked": evidence.unlocked,
        "secure": evidence.secure,
        "firmware_build": evidence.firmware_build,
        "firmware_fingerprint": evidence.firmware_fingerprint,
        "transcript_sha256": evidence.transcript_sha256,
        "baseline_evidence_sha256": baseline_digest,
        "fastboot_platform_tools_version": tool_evidence.observed_platform_tools_version,
        "fastboot_executable_sha256": tool_evidence.executable_sha256,
        "fastboot_tool_evidence_sha256": tool_digest,
        "fastboot_capture_bundle_sha256": capture_digest,
        "capture_policy": capture_bundle.capture_policy,
        "commands": ["fastboot --version", "fastboot devices", "fastboot -s SERIAL getvar all"],
        "phone_storage_written": False,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
