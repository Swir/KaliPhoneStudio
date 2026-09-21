from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-operator-extractor.yml"
REPRO_WORKFLOW = ROOT / ".github" / "workflows" / "extractor-repro.yml"
BUILDER = ROOT / "scripts" / "build_windows_operator_extractor.ps1"
RUNTIME_STAGER = ROOT / "scripts" / "stage_windows_extractor_runtime.ps1"
LOCKS = ROOT / "tools" / "extractor-locks.json"
DOC = ROOT / "docs" / "WINDOWS_OPERATOR_EXTRACTOR.md"

# Exact-head A/B run 35643537783 proved the current Windows digest with the
# locked MinGW 16.2.0-4 and r420 native package set plus clean-PATH closure.
WINDOWS_SHA256 = "e84d038e803b07503aa843aca5a82b0441877afc6cd5025247dd31d6046d02c3"
EXPECTED_NATIVE_PACKAGES = {
    "mingw-w64-x86_64-binutils": "2.47-3",
    "mingw-w64-x86_64-cc-libs": "16.2.0-4",
    "mingw-w64-x86_64-crt": "14.0.0.r420.g61d40c4c0-1",
    "mingw-w64-x86_64-gcc": "16.2.0-4",
    "mingw-w64-x86_64-headers": "14.0.0.r420.g61d40c4c0-1",
    "mingw-w64-x86_64-libgcc": "16.2.0-4",
    "mingw-w64-x86_64-libstdc++": "16.2.0-4",
    "mingw-w64-x86_64-libwinpthread": "14.0.0.r420.g61d40c4c0-1",
    "mingw-w64-x86_64-winpthreads": "14.0.0.r420.g61d40c4c0-1",
    "mingw-w64-x86_64-xz": "5.8.4-1",
}


def test_extractor_lock_is_exact_and_has_windows_runtime_authority() -> None:
    data = json.loads(LOCKS.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["extractor"] == "payload-dumper-go"
    assert data["source"]["url"] == "https://github.com/ssut/payload-dumper-go"
    assert data["source"]["commit"] == "05fe59e21c9f271fba38398c7c040993313ecd04"
    assert data["build"]["toolchain"] == "go"
    assert data["build"]["toolchain_version"] == "1.27.0"

    windows_build = data["build"]["platform_overrides"]["windows-amd64"]
    assert windows_build == {
        "linkage": "mixed-side-by-side",
        "ldflags": "-buildid= -extldflags=-static",
        "runtime_dependency_policy": "recursive-non-system-pe-import-closure",
    }

    native = data["build"]["native_dependencies"]["windows-amd64"]
    assert native["distribution"] == "MSYS2 mingw64"
    assert native["packages"] == EXPECTED_NATIVE_PACKAGES

    digest = data["artifacts"]["windows-amd64"]["sha256"]
    assert digest == WINDOWS_SHA256
    assert len(digest) == 64
    int(digest, 16)
    notes = data["build"]["notes"]
    assert "35643537783" in notes
    assert "side-by-side runtime closure" in notes
    assert "no manual DLL search" in notes


def test_windows_extractor_builder_is_source_native_runtime_and_hash_gated() -> None:
    script = BUILDER.read_text(encoding="utf-8")

    for needle in (
        "tools/extractor-locks.json",
        "scripts/stage_windows_extractor_runtime.ps1",
        "$Lock.source.commit",
        "$Lock.build.toolchain_version",
        "$Lock.artifacts.'windows-amd64'.sha256",
        "$Lock.build.native_dependencies.'windows-amd64'",
        "$Lock.build.platform_overrides.'windows-amd64'",
        'linkage -ne "mixed-side-by-side"',
        'runtime_dependency_policy -ne "recursive-non-system-pe-import-closure"',
        '"-buildid= -extldflags=-static"',
        "MSYS2 pacman is unavailable for native dependency verification",
        "pacman.exe",
        "Native package drift",
        'if ($env:CGO_ENABLED -ne "1")',
        "Reviewed Windows extractor build requires an explicit MinGW CC",
        "git fetch --quiet --depth 1 origin $ExpectedCommit",
        "git rev-parse HEAD",
        "Extractor go.mod/toolchain drift",
        'go build -trimpath -buildvcs=false "-ldflags=$WindowsLdFlags"',
        "Get-FileHash -Algorithm SHA256",
        "Extractor SHA-256 mismatch",
        "operator-extractor-runtime.json",
        "runtime_dependencies_resolved = $true",
        "clean_path_smoke_passed = $true",
        "payload-dumper-go-LICENSE.txt",
        'kind = "kaliphonestudio-windows-operator-extractor"',
        "native_package_versions = $VerifiedNativePackages",
        "source_lock_verified = $true",
        "native_dependencies_verified = $true",
        "executable_hash_verified = $true",
        "hardware_verified = $false",
        "beta_release_authorized = $false",
        "beta_gate_credit = $false",
    ):
        assert needle in script

    forbidden = (
        "fastboot ",
        "adb ",
        "Invoke-WebRequest",
        "Invoke-RestMethod",
        "Start-BitsTransfer",
        "phone_storage_written = $true",
        "persistent_write_authorized = $true",
    )
    for needle in forbidden:
        assert needle not in script


def test_runtime_stager_recursively_closes_non_system_pe_imports() -> None:
    script = RUNTIME_STAGER.read_text(encoding="utf-8")
    for needle in (
        "objdump.exe",
        "DLL Name:",
        "recursive-non-system-pe-import-closure",
        "Unresolved non-system PE dependency",
        "Copy-Item -LiteralPath $Source -Destination $Target",
        "Runtime dependency copy hash mismatch",
        "operator-extractor-runtime.json",
        "all_non_system_imports_resolved = $true",
        '$env:PATH = "$env:SystemRoot\\System32;$env:SystemRoot"',
        '".\\payload-dumper-go.exe" -h',
        "Bundled extractor failed to start on a clean Windows PATH",
    ):
        assert needle in script

    for forbidden in (
        "Invoke-WebRequest",
        "Invoke-RestMethod",
        "Start-BitsTransfer",
        "fastboot ",
        "adb ",
    ):
        assert forbidden not in script


def test_repro_workflow_requires_locked_digest_and_runtime_smoke() -> None:
    workflow = REPRO_WORKFLOW.read_text(encoding="utf-8")
    for needle in (
        "scripts/stage_windows_extractor_runtime.ps1",
        "mixed-side-by-side",
        "recursive-non-system-pe-import-closure",
        "Prove byte-for-byte reproducibility and record observed SHA-256",
        'lock["artifacts"]["${{ matrix.platform }}"]["sha256"]',
        "Stage and smoke-test self-contained Windows runtime closure",
        "extractor-runtime-bundle/operator-extractor-runtime.json",
        "all_non_system_imports_resolved",
        "Upload reproducibility evidence with observed digest",
        "Enforce reviewed extractor digest lock",
        "steps.proof.outputs.digest",
        "steps.proof.outputs.matches_lock",
    ):
        assert needle in workflow


def test_windows_extractor_workflow_builds_exact_non_release_bundle() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for needle in (
        "runs-on: windows-latest",
        "actions/setup-go@v6",
        'go-version: "1.27.0"',
        "mingw-w64-x86_64-gcc",
        "mingw-w64-x86_64-xz",
        "CGO_ENABLED=1",
        "CGO_CFLAGS=-IC:/msys64/mingw64/include",
        "CGO_LDFLAGS=-LC:/msys64/mingw64/lib",
        "./scripts/build_windows_operator_extractor.ps1",
        "scripts/stage_windows_extractor_runtime.ps1",
        "tools/extractor-locks.json",
        "operator-extractor-manifest.json",
        "operator-extractor-runtime.json",
        "payload-dumper-go.exe",
        "payload-dumper-go-LICENSE.txt",
        "runtime_dependencies_resolved",
        "all_non_system_imports_resolved",
        "Re-run clean-PATH smoke from the delivered directory",
        "$env:SystemRoot\\System32;$env:SystemRoot",
        "actions/upload-artifact@v4",
        "retention-days: 7",
        "KaliPhoneStudio-windows-operator-extractor-",
        "github.event.pull_request.head.sha || github.sha",
    ):
        assert needle in workflow

    forbidden_publishers = (
        "softprops/action-gh-release",
        "gh release create",
        "actions/create-release",
        "beta_release_authorized = $true",
        "hardware_verified = $true",
    )
    for needle in forbidden_publishers:
        assert needle not in workflow


def test_operator_extractor_doc_keeps_fastboot_and_beta_separate() -> None:
    doc = DOC.read_text(encoding="utf-8")
    assert "payload-dumper-go.exe" in doc
    assert "Apache-2.0" in doc
    assert WINDOWS_SHA256 in doc
    assert "MSYS2 mingw64" in doc
    assert "runtime closure" in doc.lower()
    assert "side-by-side" in doc.lower()
    assert "native dependency" in doc.lower()
    assert "does not bundle Android Platform-Tools" in doc
    assert "not a Beta release" in doc
    assert "no phone" in doc.lower()
