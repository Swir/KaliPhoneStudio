from __future__ import annotations

import json
from pathlib import Path
import struct

import pytest

from kaliphonestudio.kernel_elf_diagnostics import (
    KernelElfDiagnosticError,
    diagnose_kernel_elf_sections,
    fingerprint_elf_sections,
)


def _align(value: int, alignment: int = 8) -> int:
    return (value + alignment - 1) // alignment * alignment


def _write_elf(
    path: Path,
    sections: list[tuple[str, int, bytes]],
    *,
    elf_class: int = 64,
    machine: int | None = None,
) -> None:
    if elf_class not in {32, 64}:
        raise ValueError("test ELF class must be 32 or 64")
    machine = (183 if elf_class == 64 else 40) if machine is None else machine
    names = b"\0"
    offsets_by_name: dict[str, int] = {"": 0}
    for name, _flags, _payload in sections + [(".shstrtab", 0, b"")]:
        if name not in offsets_by_name:
            offsets_by_name[name] = len(names)
            names += name.encode() + b"\0"
    payloads = [(name, flags, data, 1) for name, flags, data in sections]
    payloads.append((".shstrtab", 0, names, 3))
    ehdr_size = 64 if elf_class == 64 else 52
    shdr_size = 64 if elf_class == 64 else 40
    cursor = ehdr_size
    body = bytearray()
    offsets: list[int] = []
    for _name, _flags, data, _stype in payloads:
        aligned = _align(cursor)
        body.extend(b"\0" * (aligned - cursor))
        cursor = aligned
        offsets.append(cursor)
        body.extend(data)
        cursor += len(data)
    shoff = _align(cursor)
    body.extend(b"\0" * (shoff - cursor))
    shnum = 1 + len(payloads)
    shstrndx = shnum - 1
    headers = bytearray(shdr_size)
    for (name, flags, data, stype), offset in zip(payloads, offsets):
        if elf_class == 64:
            headers.extend(struct.pack(
                "<IIQQQQIIQQ", offsets_by_name[name], stype, flags, 0,
                offset, len(data), 0, 0, 1, 0,
            ))
        else:
            headers.extend(struct.pack(
                "<IIIIIIIIII", offsets_by_name[name], stype, flags, 0,
                offset, len(data), 0, 0, 1, 0,
            ))
    ident = bytearray(16)
    ident[:4] = b"\x7fELF"
    ident[4] = 2 if elf_class == 64 else 1
    ident[5] = 1
    ident[6] = 1
    if elf_class == 64:
        rest = struct.pack(
            "<HHIQQQIHHHHHH", 1, machine, 1, 0, 0, shoff, 0,
            64, 0, 0, 64, shnum, shstrndx,
        )
    else:
        rest = struct.pack(
            "<HHIIIIIHHHHHH", 1, machine, 1, 0, 0, shoff, 0,
            52, 0, 0, 40, shnum, shstrndx,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(ident) + rest + body + headers)


def _tree(path: Path, relative: str, kind: str = "content_mismatch") -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "reported_differences": [{
            "path": relative,
            "kind": kind,
            "category": "object",
            "size_a": 1,
            "size_b": 1,
            "sha256_a": "a" * 64,
            "sha256_b": "b" * 64,
        }],
        "beta_gate_credit": False,
        "hardware_verified": False,
    }, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_non_elf_returns_none(tmp_path: Path) -> None:
    item = tmp_path / "x.o"
    item.write_bytes(b"not-elf")
    assert fingerprint_elf_sections(item) is None


def test_wrong_machine_fails_closed(tmp_path: Path) -> None:
    item = tmp_path / "x.o"
    _write_elf(item, [(".text", 0x6, b"x")], machine=62)
    with pytest.raises(KernelElfDiagnosticError, match="not ARM/AArch64"):
        fingerprint_elf_sections(item)


def test_arm32_compat_vdso_sections_are_supported(tmp_path: Path) -> None:
    item = tmp_path / "arch/arm64/kernel/vdso32/vgettimeofday.o"
    _write_elf(item, [(".text", 0x6, b"ARM32"), (".debug_info", 0, b"dbg")], elf_class=32)
    sections = fingerprint_elf_sections(item)
    assert sections is not None
    assert any(section.name == ".text" and section.category == "executable" for section in sections)
    assert any(section.name == ".debug_info" and section.category == "debug" for section in sections)


def test_debug_only_difference_is_classified(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    rel = "drivers/example.o"
    _write_elf(a / rel, [(".text", 0x6, b"CODE"), (".debug_info", 0, b"A")])
    _write_elf(b / rel, [(".text", 0x6, b"CODE"), (".debug_info", 0, b"B")])
    tree = tmp_path / "tree.json"
    _tree(tree, rel)
    evidence = diagnose_kernel_elf_sections(a, b, tree)
    assert evidence.parsed_elf_path_count == 1
    assert evidence.differing_elf_path_count == 1
    assert evidence.executable_section_difference_count == 0
    assert evidence.debug_section_difference_count == 1
    assert evidence.beta_gate_credit is False
    assert evidence.hardware_verified is False
    assert any(x.name == ".debug_info" for x in evidence.files[0].reported_section_differences)


def test_arm32_debug_difference_is_classified_without_failure(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    rel = "arch/arm64/kernel/vdso32/note.o"
    _write_elf(a / rel, [(".text", 0x6, b"same"), (".debug_line", 0, b"A")], elf_class=32)
    _write_elf(b / rel, [(".text", 0x6, b"same"), (".debug_line", 0, b"B")], elf_class=32)
    tree = tmp_path / "tree.json"
    _tree(tree, rel)
    evidence = diagnose_kernel_elf_sections(a, b, tree)
    assert evidence.parsed_elf_path_count == 1
    assert evidence.debug_section_difference_count == 1
    assert evidence.executable_section_difference_count == 0


def test_executable_difference_is_counted(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    rel = "kernel/core.o"
    _write_elf(a / rel, [(".text", 0x6, b"A"), (".debug_info", 0, b"same")])
    _write_elf(b / rel, [(".text", 0x6, b"B"), (".debug_info", 0, b"same")])
    tree = tmp_path / "tree.json"
    _tree(tree, rel)
    evidence = diagnose_kernel_elf_sections(a, b, tree)
    assert evidence.executable_section_difference_count == 1
    assert evidence.debug_section_difference_count == 0


def test_section_order_change_is_reported(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    rel = "x.o"
    _write_elf(a / rel, [(".text", 0x6, b"x"), (".data", 0x3, b"y")])
    _write_elf(b / rel, [(".data", 0x3, b"y"), (".text", 0x6, b"x")])
    tree = tmp_path / "tree.json"
    _tree(tree, rel)
    result = diagnose_kernel_elf_sections(a, b, tree).files[0]
    assert result.section_order_mismatch_count == 2
    assert result.data_section_difference_count >= 1
    assert "order_mismatch" in {x.kind for x in result.reported_section_differences}


def test_non_elf_pair_is_diagnostic_not_failure(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    rel = "foo.o"
    (a / rel).parent.mkdir(parents=True)
    (b / rel).parent.mkdir(parents=True)
    (a / rel).write_bytes(b"LLVM-A")
    (b / rel).write_bytes(b"LLVM-B")
    tree = tmp_path / "tree.json"
    _tree(tree, rel)
    evidence = diagnose_kernel_elf_sections(a, b, tree)
    assert evidence.non_elf_path_count == 1
    assert evidence.files[0].status == "non_elf"


def test_host_scripts_objects_are_excluded_from_target_section_analysis(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    tree = tmp_path / "tree.json"
    _tree(tree, "scripts/dtc/checks.o")
    evidence = diagnose_kernel_elf_sections(a, b, tree)
    assert evidence.candidate_path_count == 0
    assert evidence.files == ()


def test_path_traversal_fails_closed(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    tree = tmp_path / "tree.json"
    _tree(tree, "../escape.o")
    with pytest.raises(KernelElfDiagnosticError, match="safe and relative"):
        diagnose_kernel_elf_sections(a, b, tree)


def test_selected_symlink_fails_closed(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    target = tmp_path / "target"
    _write_elf(target, [(".text", 0x6, b"x")])
    (a / "x.o").symlink_to(target)
    _write_elf(b / "x.o", [(".text", 0x6, b"y")])
    tree = tmp_path / "tree.json"
    _tree(tree, "x.o")
    with pytest.raises(KernelElfDiagnosticError, match="must not be a symlink"):
        diagnose_kernel_elf_sections(a, b, tree)
