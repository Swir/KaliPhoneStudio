from __future__ import annotations

import argparse
from pathlib import Path
import sys

from kaliphonestudio.beta_release_review_manifest import (
    BetaReleaseReviewManifestError,
    build_beta_release_review_manifest,
    write_beta_release_review_manifest_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Offline re-verification and deterministic Beta release review manifest/SHA256SUMS builder. "
            "It performs no device/network/publication action and never authorizes a Beta release."
        )
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--checksums-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence, checksums = build_beta_release_review_manifest(
            args.inventory,
            args.release_dir,
            args.version,
        )
        digest = write_beta_release_review_manifest_bundle(
            evidence,
            checksums,
            args.manifest_out,
            args.checksums_out,
        )
    except BetaReleaseReviewManifestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"manifest_sha256={digest}")
    print(f"sha256sums_sha256={evidence.sha256sums_sha256}")
    print(f"artifact_count={evidence.artifact_count}")
    print("release_publication_allowed=false")
    print("beta_release_authorized=false")
    print("final_manual_release_gate_review_required=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
