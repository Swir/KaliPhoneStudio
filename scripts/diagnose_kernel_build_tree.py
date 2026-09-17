#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.kernel_build_tree_diagnostics import (
    diagnose_kernel_build_tree,
    write_kernel_build_tree_evidence,
)
from kaliphonestudio.kernel_elf_diagnostics import (
    diagnose_kernel_elf_sections,
    write_evidence as write_kernel_elf_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare selected intermediate artifacts from two independent kernel build roots, "
            "then classify reported ARM64 ELF differences by section. Diagnostics never relax "
            "strict kernel reproducibility acceptance."
        )
    )
    parser.add_argument("--build-a", type=Path, required=True)
    parser.add_argument("--build-b", type=Path, required=True)
    parser.add_argument("--max-differences", type=int, default=256)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--elf-out",
        type=Path,
        default=None,
        help="ELF section evidence path; default: kernel-elf-section-divergence.json beside --out",
    )
    parser.add_argument("--max-elf-files", type=int, default=64)
    parser.add_argument("--max-sections-per-file", type=int, default=64)
    args = parser.parse_args()

    evidence = diagnose_kernel_build_tree(
        args.build_a,
        args.build_b,
        max_differences=args.max_differences,
    )
    digest = write_kernel_build_tree_evidence(evidence, args.out)
    print(
        f"selected={evidence.selected_path_count} "
        f"identical={evidence.identical_path_count} "
        f"different={evidence.differing_path_count} "
        f"reported={evidence.reported_difference_count} "
        f"omitted={evidence.omitted_difference_count}"
    )
    print(f"build-tree evidence sha256: {digest}")

    elf_out = args.elf_out or args.out.with_name("kernel-elf-section-divergence.json")
    elf = diagnose_kernel_elf_sections(
        args.build_a,
        args.build_b,
        args.out,
        max_files=args.max_elf_files,
        max_sections_per_file=args.max_sections_per_file,
    )
    elf_digest = write_kernel_elf_evidence(elf, elf_out)
    print(
        f"elf_candidates={elf.candidate_path_count} "
        f"parsed={elf.parsed_elf_path_count} "
        f"different_elf={elf.differing_elf_path_count} "
        f"executable_section_differences={elf.executable_section_difference_count} "
        f"debug_section_differences={elf.debug_section_difference_count}"
    )
    print(f"ELF evidence sha256: {elf_digest}")
    print("hardware/Beta credit: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
