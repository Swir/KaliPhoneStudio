#!/usr/bin/env python3
"""Capture a signed Kali repository snapshot for rootfs reproducibility evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from kaliphonestudio.rootfs import (
    RootfsError,
    load_rootfs_source_lock,
    repository_snapshot_from_inrelease,
    write_repository_snapshot,
)


def _verified_signer(inrelease: Path, keyring: Path, expected_fingerprint: str) -> str:
    if not inrelease.is_file() or not keyring.is_file():
        raise RootfsError("InRelease and archive keyring must both exist")
    try:
        result = subprocess.run(
            [
                "gpgv",
                "--status-fd",
                "1",
                "--keyring",
                str(keyring),
                str(inrelease),
            ],
            check=True,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RootfsError(f"Kali InRelease GPG verification failed: {exc}") from exc
    signers = []
    for line in result.stdout.splitlines():
        marker = "[GNUPG:] VALIDSIG "
        if line.startswith(marker):
            fields = line[len(marker):].split()
            if fields:
                signers.append(fields[0].upper())
    if expected_fingerprint not in signers:
        raise RootfsError("InRelease is not signed by the locked Kali archive key fingerprint")
    return expected_fingerprint


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Verify Kali InRelease with the locked archive key and emit repository snapshot evidence."
    )
    result.add_argument("--lock", type=Path, required=True)
    result.add_argument("--inrelease", type=Path, required=True)
    result.add_argument("--keyring", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    lock = load_rootfs_source_lock(args.lock)
    signer = _verified_signer(args.inrelease, args.keyring, lock.archive_key_fingerprint)
    payload = args.inrelease.read_bytes()
    snapshot = repository_snapshot_from_inrelease(
        lock, payload, signing_key_fingerprint=signer
    )
    digest = write_repository_snapshot(snapshot, args.out)
    print(f"inrelease_sha256={snapshot.inrelease_sha256}")
    print(f"snapshot_sha256={digest}")
    print(f"signing_key_fingerprint={snapshot.signing_key_fingerprint}")
    print(f"package_indexes={len(snapshot.package_indexes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
