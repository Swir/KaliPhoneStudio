#!/usr/bin/env python3
"""Build a deterministic non-authorizing Beta release artifact inventory."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from kaliphonestudio.beta_release_artifact_inventory import (
    BetaReleaseArtifactInventoryError,
    build_beta_release_artifact_inventory,
    write_beta_release_artifact_inventory,
)


def _artifact(value: str) -> tuple[str, Path]:
    role, separator, path = value.partition("=")
    if not separator or not role or not path:
        raise argparse.ArgumentTypeError("artifact must use ROLE=PATH")
    return role, Path(path)


def parser() -> argparse.ArgumentParser:
    item = argparse.ArgumentParser(
        description=(
            "Hash exact reviewed-candidate release files into an offline inventory. "
            "This never publishes a release or grants Beta authorization."
        )
    )
    item.add_argument("--candidate-gate", required=True, type=Path)
    item.add_argument("--release-gate-audit", required=True, type=Path)
    item.add_argument("--strategy-review", required=True, type=Path)
    item.add_argument("--source-commit", required=True)
    item.add_argument(
        "--artifact",
        action="append",
        required=True,
        type=_artifact,
        metavar="ROLE=PATH",
        help="repeat once per release artifact role",
    )
    item.add_argument("--out", required=True, type=Path)
    return item


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    artifacts: dict[str, Path] = {}
    for role, path in args.artifact:
        if role in artifacts:
            parser().error(f"duplicate artifact role: {role}")
        artifacts[role] = path
    try:
        evidence = build_beta_release_artifact_inventory(
            args.candidate_gate,
            args.release_gate_audit,
            args.strategy_review,
            args.source_commit,
            artifacts,
        )
        digest = write_beta_release_artifact_inventory(evidence, args.out)
    except BetaReleaseArtifactInventoryError as exc:
        print(f"Beta release artifact inventory blocked: {exc}", file=sys.stderr)
        return 2
    print(digest)
    print("release_publication_allowed=false")
    print("manual_release_gate_review_required=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
