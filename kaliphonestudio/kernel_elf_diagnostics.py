"""Bounded, non-release ELF diagnostics for divergent kernel build artifacts.

The final kernel reproducibility rule remains strict byte equality. This module
only classifies already-reported divergent target artifacts. It supports both
AArch64 ELF64 objects and the ARM ELF32 compat-vDSO objects produced by the
pinned arm64 kernel tree. Host-tool objects under ``scripts/`` are intentionally
excluded because they are not linked into the target kernel Image.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import struct
from typing import BinaryIO

SCHEMA_VERSION = 1
BUILD_TREE_SCHEMA_VERSION = 1
DEFAULT_MAX_FILES = 64
DEFAULT_MAX_SECTIONS = 64
DEFAULT_CHUNK = 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024 * 1024
MAX_SECTIONS = 65535
MAX_SHSTRTAB_BYTES = 16 * 1024 * 1024
ELF_MAGIC = b"\x7fELF"
ELFCLASS32 = 1
ELFCLASS64 = 2
ELFDATA2LSB = 1
EV_CURRENT = 1
EM_ARM = 40
EM_AARCH64 = 183
SHT_NOBITS = 8
SHF_EXECINSTR = 0x4
ELF32_EHDR_SIZE = 52
ELF64_EHDR_SIZE = 64
ELF32_SHDR_SIZE = 40
ELF64_SHDR_SIZE = 64


class KernelElfDiagnosticError(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    name: str
    occurrence: int
    index: int
    category: str
    section_type: int
    flags: int
    size: int
    sha256: str | None


@dataclass(frozen=True)
class SectionDifference:
    name: str
    occurrence: int
    category: str
    kind: str
    index_a: int | None
    index_b: int | None
    size_a: int | None
    size_b: int | None
    sha256_a: str | None
    sha256_b: str | None


@dataclass(frozen=True)
class ArtifactDiagnostic:
    path: str
    status: str
    section_count_a: int | None
    section_count_b: int | None
    differing_section_count: int
    executable_section_difference_count: int
    debug_section_difference_count: int
    metadata_section_difference_count: int
    relocation_section_difference_count: int
    data_section_difference_count: int
    section_order_mismatch_count: int
    reported_section_difference_count: int
    omitted_section_difference_count: int
    reported_section_differences: tuple[SectionDifference, ...]


@dataclass(frozen=True)
class KernelElfDivergenceEvidence:
    schema_version: int
    build_tree_evidence_sha256: str
    candidate_path_count: int
    parsed_elf_path_count: int
    non_elf_path_count: int
    format_mismatch_path_count: int
    differing_elf_path_count: int
    executable_section_difference_count: int
    debug_section_difference_count: int
    metadata_section_difference_count: int
    relocation_section_difference_count: int
    data_section_difference_count: int
    reported_file_count: int
    omitted_file_count: int
    files: tuple[ArtifactDiagnostic, ...]
    beta_gate_credit: bool = False
    hardware_verified: bool = False

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _root(path: Path, label: str) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise KernelElfDiagnosticError(f"{label} must be a real directory")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise KernelElfDiagnosticError(f"cannot resolve {label}") from exc


def _relative(raw: object) -> str:
    if not isinstance(raw, str) or not raw:
        raise KernelElfDiagnosticError("diagnostic path must be a non-empty string")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in path.parts):
        raise KernelElfDiagnosticError("diagnostic path must be safe and relative")
    if any("\\" in p or any(ord(ch) < 0x20 for ch in p) for p in path.parts):
        raise KernelElfDiagnosticError("diagnostic path contains unsafe data")
    return path.as_posix()


def _artifact(root: Path, relative: str) -> Path:
    item = root.joinpath(*PurePosixPath(relative).parts)
    if item.is_symlink():
        raise KernelElfDiagnosticError(f"selected ELF artifact must not be a symlink: {relative}")
    try:
        item = item.resolve(strict=True)
    except OSError as exc:
        raise KernelElfDiagnosticError(f"selected ELF artifact is missing: {relative}") from exc
    if root != item and root not in item.parents:
        raise KernelElfDiagnosticError(f"selected ELF artifact escapes build root: {relative}")
    if not item.is_file():
        raise KernelElfDiagnosticError(f"selected ELF artifact is not a regular file: {relative}")
    return item


def _read(handle: BinaryIO, offset: int, size: int, file_size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > file_size or size > file_size - offset:
        raise KernelElfDiagnosticError(f"ELF {label} escapes file bounds")
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise KernelElfDiagnosticError(f"ELF {label} is truncated")
    return data


def _hash(handle: BinaryIO, offset: int, size: int, file_size: int, chunk: int) -> str:
    if offset < 0 or size < 0 or offset > file_size or size > file_size - offset:
        raise KernelElfDiagnosticError("ELF section payload escapes file bounds")
    handle.seek(offset)
    digest = sha256()
    remaining = size
    while remaining:
        data = handle.read(min(chunk, remaining))
        if not data:
            raise KernelElfDiagnosticError("ELF section payload is truncated")
        digest.update(data)
        remaining -= len(data)
    return digest.hexdigest()


def _cstring(table: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(table):
        raise KernelElfDiagnosticError("ELF section name offset escapes string table")
    end = table.find(b"\0", offset)
    if end < 0:
        raise KernelElfDiagnosticError("ELF section name is not NUL-terminated")
    try:
        value = table[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KernelElfDiagnosticError("ELF section name is not UTF-8") from exc
    if any(ord(ch) < 0x20 for ch in value):
        raise KernelElfDiagnosticError("ELF section name contains control data")
    return value


def _category(name: str, flags: int) -> str:
    if flags & SHF_EXECINSTR or name == ".text" or name.startswith(".text."):
        return "executable"
    if name.startswith((".debug", ".zdebug")):
        return "debug"
    if name.startswith((".rel", ".rela")):
        return "relocation"
    if name in {".symtab", ".strtab", ".shstrtab"} or name.startswith(".note"):
        return "metadata"
    return "data"


def _target_candidate(relative: str, kind: object) -> bool:
    """Select target-side ELF candidates and exclude known host build tools."""
    if kind not in {"content_mismatch", "size_mismatch"}:
        return False
    path = PurePosixPath(relative)
    if path.name == "vmlinux":
        return True
    if path.suffix != ".o":
        return False
    if path.parts and path.parts[0] == "scripts":
        return False
    return True


def _elf_layout(ident: bytes) -> tuple[int, int, str, str]:
    if len(ident) < 16 or ident[5] != ELFDATA2LSB or ident[6] != EV_CURRENT:
        raise KernelElfDiagnosticError("unsupported ELF data/version")
    if ident[4] == ELFCLASS64:
        return ELF64_EHDR_SIZE, ELF64_SHDR_SIZE, "<HHIQQQIHHHHHH", "<IIQQQQ"
    if ident[4] == ELFCLASS32:
        return ELF32_EHDR_SIZE, ELF32_SHDR_SIZE, "<HHIIIIIHHHHHH", "<IIIIII"
    raise KernelElfDiagnosticError("unsupported ELF class")


def fingerprint_elf_sections(path: Path, *, chunk_size: int = DEFAULT_CHUNK) -> tuple[Section, ...] | None:
    """Fingerprint little-endian AArch64 ELF64 or ARM compat-vDSO ELF32 sections."""
    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 4096:
        raise KernelElfDiagnosticError("chunk_size must be an integer >= 4096")
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise KernelElfDiagnosticError("ELF candidate must be a regular non-symlink file")
    before = path.stat()
    size = before.st_size
    if size < 4:
        return None
    if size > MAX_FILE_BYTES:
        raise KernelElfDiagnosticError("ELF candidate exceeds safety size limit")
    with path.open("rb") as handle:
        if handle.read(4) != ELF_MAGIC:
            return None
        ident = _read(handle, 0, 16, size, "ident")
        ehdr_size, minimum_shdr_size, header_fmt, section_fmt = _elf_layout(ident)
        header = _read(handle, 0, ehdr_size, size, "header")
        unpacked = struct.unpack_from(header_fmt, header, 16)
        machine = unpacked[1]
        version = unpacked[2]
        shoff = unpacked[5]
        shentsize, shnum, shstrndx = unpacked[10], unpacked[11], unpacked[12]
        if version != EV_CURRENT:
            raise KernelElfDiagnosticError("unsupported ELF header version")
        if machine not in {EM_ARM, EM_AARCH64}:
            raise KernelElfDiagnosticError("ELF artifact is not ARM/AArch64")
        if ident[4] == ELFCLASS64 and machine != EM_AARCH64:
            raise KernelElfDiagnosticError("ELF64 target artifact is not AArch64")
        if ident[4] == ELFCLASS32 and machine != EM_ARM:
            raise KernelElfDiagnosticError("ELF32 compat artifact is not ARM")
        if shentsize < minimum_shdr_size:
            raise KernelElfDiagnosticError("unsupported ELF section-header format")
        if shnum < 1 or shnum > MAX_SECTIONS or shstrndx >= shnum:
            raise KernelElfDiagnosticError("unsupported ELF section table")
        table = _read(handle, shoff, shentsize * shnum, size, "section header table")
        headers: list[tuple[int, int, int, int, int]] = []
        for index in range(shnum):
            off = index * shentsize
            name, stype, flags, _addr, data_off, data_size = struct.unpack_from(section_fmt, table, off)
            headers.append((name, stype, flags, data_off, data_size))
        names_hdr = headers[shstrndx]
        if names_hdr[1] == SHT_NOBITS or names_hdr[4] > MAX_SHSTRTAB_BYTES:
            raise KernelElfDiagnosticError("unsafe ELF section-name table")
        names = _read(handle, names_hdr[3], names_hdr[4], size, "section-name table")
        occurrences: dict[str, int] = {}
        result: list[Section] = []
        for index, (name_off, stype, flags, data_off, data_size) in enumerate(headers):
            name = _cstring(names, name_off)
            occurrence = occurrences.get(name, 0)
            occurrences[name] = occurrence + 1
            digest = None if stype == SHT_NOBITS else _hash(handle, data_off, data_size, size, chunk_size)
            result.append(Section(name, occurrence, index, _category(name, flags), stype, flags, data_size, digest))
    after = path.stat()
    if after.st_size != before.st_size or after.st_mtime_ns != before.st_mtime_ns:
        raise KernelElfDiagnosticError("ELF candidate changed while being diagnosed")
    return tuple(result)


def _compare(a_items: tuple[Section, ...], b_items: tuple[Section, ...], max_sections: int):
    a_map = {(x.name, x.occurrence): x for x in a_items}
    b_map = {(x.name, x.occurrence): x for x in b_items}
    counts = {"executable": 0, "debug": 0, "metadata": 0, "relocation": 0, "data": 0}
    order = 0
    differences: list[SectionDifference] = []
    for key in sorted(set(a_map) | set(b_map)):
        a, b = a_map.get(key), b_map.get(key)
        if a is None:
            category, kind = b.category, "missing_from_a"
        elif b is None:
            category, kind = a.category, "missing_from_b"
        else:
            category = a.category if a.category == b.category else "metadata"
            if a.index != b.index:
                order += 1
            if (a.section_type, a.flags, a.size, a.sha256, a.index) == (b.section_type, b.flags, b.size, b.sha256, b.index):
                continue
            if a.section_type != b.section_type or a.flags != b.flags:
                kind = "header_mismatch"
            elif a.size != b.size:
                kind = "size_mismatch"
            elif a.sha256 != b.sha256:
                kind = "content_mismatch"
            else:
                kind = "order_mismatch"
        counts[category] += 1
        differences.append(SectionDifference(
            key[0], key[1], category, kind,
            None if a is None else a.index, None if b is None else b.index,
            None if a is None else a.size, None if b is None else b.size,
            None if a is None else a.sha256, None if b is None else b.sha256,
        ))
    return len(differences), counts, order, tuple(differences[:max_sections])


def diagnose_kernel_elf_sections(
    build_a: Path,
    build_b: Path,
    build_tree_evidence: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_sections_per_file: int = DEFAULT_MAX_SECTIONS,
    chunk_size: int = DEFAULT_CHUNK,
) -> KernelElfDivergenceEvidence:
    if not isinstance(max_files, int) or isinstance(max_files, bool) or max_files < 1:
        raise KernelElfDiagnosticError("max_files must be an integer >= 1")
    if not isinstance(max_sections_per_file, int) or isinstance(max_sections_per_file, bool) or max_sections_per_file < 1:
        raise KernelElfDiagnosticError("max_sections_per_file must be an integer >= 1")
    root_a, root_b = _root(build_a, "build A"), _root(build_b, "build B")
    if root_a == root_b:
        raise KernelElfDiagnosticError("build A and build B must be independent directories")
    evidence_path = Path(build_tree_evidence)
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise KernelElfDiagnosticError("build-tree evidence must be a regular non-symlink file")
    raw = evidence_path.read_bytes()
    try:
        tree = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KernelElfDiagnosticError("build-tree evidence is not valid JSON") from exc
    if not isinstance(tree, dict) or tree.get("schema_version") != BUILD_TREE_SCHEMA_VERSION:
        raise KernelElfDiagnosticError("unsupported build-tree evidence schema")
    if tree.get("beta_gate_credit") is not False or tree.get("hardware_verified") is not False:
        raise KernelElfDiagnosticError("build-tree evidence must be explicitly non-release")
    reported = tree.get("reported_differences")
    if not isinstance(reported, list):
        raise KernelElfDiagnosticError("build-tree evidence has no reported differences")
    candidates: set[str] = set()
    for item in reported:
        if not isinstance(item, dict):
            raise KernelElfDiagnosticError("malformed build-tree difference")
        relative = _relative(item.get("path"))
        if _target_candidate(relative, item.get("kind")):
            candidates.add(relative)

    files: list[ArtifactDiagnostic] = []
    totals = {"executable": 0, "debug": 0, "metadata": 0, "relocation": 0, "data": 0}
    parsed = non_elf = format_mismatch = differing = 0
    for relative in sorted(candidates)[:max_files]:
        a = fingerprint_elf_sections(_artifact(root_a, relative), chunk_size=chunk_size)
        b = fingerprint_elf_sections(_artifact(root_b, relative), chunk_size=chunk_size)
        if a is None and b is None:
            non_elf += 1
            files.append(ArtifactDiagnostic(relative, "non_elf", None, None, 0, 0, 0, 0, 0, 0, 0, 0, 0, ()))
            continue
        if (a is None) != (b is None):
            format_mismatch += 1
            files.append(ArtifactDiagnostic(relative, "format_mismatch", None if a is None else len(a), None if b is None else len(b), 0, 0, 0, 0, 0, 0, 0, 0, 0, ()))
            continue
        assert a is not None and b is not None
        parsed += 1
        diff_count, counts, order, differences = _compare(a, b, max_sections_per_file)
        if diff_count:
            differing += 1
        for key in totals:
            totals[key] += counts[key]
        files.append(ArtifactDiagnostic(
            relative, "different" if diff_count else "section_equal", len(a), len(b), diff_count,
            counts["executable"], counts["debug"], counts["metadata"], counts["relocation"], counts["data"],
            order, len(differences), max(0, diff_count - len(differences)), differences,
        ))
    return KernelElfDivergenceEvidence(
        SCHEMA_VERSION, sha256(raw).hexdigest(), len(candidates), parsed, non_elf, format_mismatch, differing,
        totals["executable"], totals["debug"], totals["metadata"], totals["relocation"], totals["data"],
        len(files), max(0, len(candidates) - len(files)), tuple(files),
    )


def write_evidence(evidence: KernelElfDivergenceEvidence, destination: Path) -> str:
    path = Path(destination)
    if path.exists() and path.is_symlink():
        raise KernelElfDiagnosticError("refusing to overwrite symlink evidence path")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = evidence.canonical_json()
    path.write_text(payload, encoding="utf-8", newline="\n")
    return sha256(payload.encode("utf-8")).hexdigest()
