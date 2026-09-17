#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_elf_diagnostics import (
    KernelElfDiagnosticError,
    diagnose_kernel_elf_sections,
    write_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify ARM64 ELF section divergence after strict kernel reproducibility failure"
    )
    parser.add_argument("--build-a", type=Path, required=True)
    parser.add_argument("--build-b", type=Path, required=True)
    parser.add_argument("--build-tree-evidence", type=Path, required=True)
    parser.add_argument("--max-files", type=int, default=64)
    parser.add_argument("--max-sections-per-file", type=int, default=64)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = diagnose_kernel_elf_sections(
            args.build_a,
            args.build_b,
            args.build_tree_evidence,
            max_files=args.max_files,
            max_sections_per_file=args.max_sections_per_file,
        )
        digest = write_evidence(evidence, args.out)
    except KernelElfDiagnosticError as exc:
        parser.error(str(exc))
    print(evidence.canonical_json(), end="")
    print(f"kernel ELF diagnostic evidence sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
