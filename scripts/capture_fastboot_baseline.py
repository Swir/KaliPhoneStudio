#!/usr/bin/env python3
"""Capture and validate a read-only physical Fastboot baseline for one exact serial.

Only ``fastboot devices`` and ``fastboot -s SERIAL getvar all`` are executed. The
command never boots, reboots, flashes, erases, changes slots or writes phone
storage. The resulting baseline is host evidence only and keeps
``beta_gate_credit=false``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.fastboot_baseline import (  # noqa: E402
    capture_fastboot_baseline,
    write_fastboot_baseline_evidence,
)
from kaliphonestudio.fastboot_capture import (  # noqa: E402
    FastbootCaptureError,
    capture_fastboot_getvar_all,
    validate_capture_with_offline_parser,
    write_capture_once,
)
from kaliphonestudio.profiles import get_profile  # noqa: E402


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    p.add_argument("--serial", required=True, help="exact serial shown by fastboot devices")
    p.add_argument("--firmware-build", required=True)
    p.add_argument("--firmware-fingerprint", required=True)
    p.add_argument("--fastboot", default="fastboot", help="fastboot executable or full path")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--transcript-out", type=Path, required=True)
    p.add_argument("--evidence-out", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    if args.transcript_out == args.evidence_out:
        raise SystemExit("transcript and evidence destinations must be different")
    for path, label in (
        (args.transcript_out, "transcript"),
        (args.evidence_out, "evidence"),
    ):
        if path.exists() or path.is_symlink():
            raise SystemExit(f"refusing to overwrite existing {label}: {path}")

    profile = get_profile(args.devices_root, args.profile_id)
    try:
        payload = capture_fastboot_getvar_all(
            args.serial,
            fastboot=args.fastboot,
            timeout_seconds=args.timeout,
        )
        validate_capture_with_offline_parser(payload)
    except FastbootCaptureError as exc:
        raise SystemExit(str(exc)) from exc

    staged_transcript = args.transcript_out.with_name(args.transcript_out.name + ".capturing")
    staged_evidence = args.evidence_out.with_name(args.evidence_out.name + ".capturing")
    if staged_transcript.exists() or staged_transcript.is_symlink():
        raise SystemExit(f"refusing stale transcript staging path: {staged_transcript}")
    if staged_evidence.exists() or staged_evidence.is_symlink():
        raise SystemExit(f"refusing stale evidence staging path: {staged_evidence}")

    published_transcript = False
    published_evidence = False
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
        digest = write_fastboot_baseline_evidence(evidence, staged_evidence)

        # Re-read the canonical evidence before publishing either requested path.
        saved = json.loads(staged_evidence.read_text(encoding="utf-8"))
        if saved != json.loads(evidence.canonical_json()):
            raise SystemExit("fastboot baseline evidence round-trip mismatch")
        if args.transcript_out.exists() or args.evidence_out.exists():
            raise SystemExit("capture destination appeared during validation")

        staged_transcript.replace(args.transcript_out)
        published_transcript = True
        staged_evidence.replace(args.evidence_out)
        published_evidence = True
    except BaseException:
        # Two separate files cannot be committed atomically together. If the second
        # rename fails, remove any final path created by this invocation so callers
        # never observe a half-published baseline pair.
        if published_evidence:
            args.evidence_out.unlink(missing_ok=True)
        if published_transcript:
            args.transcript_out.unlink(missing_ok=True)
        raise
    finally:
        staged_transcript.unlink(missing_ok=True)
        staged_evidence.unlink(missing_ok=True)

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
        "baseline_evidence_sha256": digest,
        "commands": ["fastboot devices", "fastboot -s SERIAL getvar all"],
        "phone_storage_written": False,
        "beta_gate_credit": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
