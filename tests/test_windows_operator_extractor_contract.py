from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-operator-extractor.yml"
BUILDER = ROOT / "scripts" / "build_windows_operator_extractor.ps1"
LOCKS = ROOT / "tools" / "extractor-locks.json"
DOC = ROOT / "docs" / "WINDOWS_OPERATOR_EXTRACTOR.md"

WINDOWS_SHA256 = "3a772fda1ac854f11ce9da26d33097f927266004357fc95bceff85de70158bde"
EXPECTED_NATIVE_PACKAGES = {
    "mingw-w64-x86_64-binutils": "2.47-3",
    "mingw-w64-x86_64-crt": "14.0.0.r409.g6de5d3b4d-1",
    "mingw-w64-x86_64-gcc": "16.2.0-3",
    "mingw-w64-x86_64-gcc-libs": "16.2.0-3",
    "mingw-w64-x86_64-headers": "14.0.0.r409.g6de5d3b4d-1",
    "mingw-w64-x86_64-libwinpthread": "14.0.0.r409.g6de5d3b4d-1",
    "mingw-w64-x86_64-winpthreads": "14.0.0.r409.g6de5d3b4d-1",
    "mingw-w64-x86_64-xz": "5.8.4-1",
}


def test_extractor_lock_is_exact_and_has_windows_native_authority() -> None:
    data = json.loads(LOCKS.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["extractor"] == "payload-dumper-go"
    assert data["source"]["url"] == "https://github.com/ssut/payload-dumper-go"
    assert data["source"]["commit"] == "05fe59e21c9f271fba38398c7c040993313ecd04"
    assert data["build"]["toolchain"] == "go"
    assert data["build"]["toolchain_version"] == "1.27.0"
    assert data["build"]["command"] == [
        "go", "build", "-trimpath", "-buildvcs=false", "-ldflags=-buildid=", "-o", "payload-dumper-go", ".",
    ]

    native = data["build"]["native_dependencies"]["windows-amd64"]
    assert native["distribution"] == "MSYS2 mingw64"
    assert native["packages"] == EXPECTED_NATIVE_PACKAGES

    digest = data["artifacts"]["windows-amd64"]["sha256"]
    assert digest == WINDOWS_SHA256
    assert len(digest) == 64
    int(digest, 16)


def test_windows_extractor_builder_is_source_native_and_hash_gated() -> None:
    script = BUILDER.read_text(encoding="utf-8")

    for needle in (
        "tools/extractor-locks.json",
        "$Lock.source.commit",
        "$Lock.build.toolchain_version",
        "$Lock.artifacts.'windows-amd64'.sha256",
        "$Lock.build.native_dependencies.'windows-amd64'",
        "MSYS2 pacman is unavailable for native dependency verification",
        "pacman.exe",
        "Native package drift",
        'if ($env:CGO_ENABLED -ne "1")',
        "Reviewed Windows extractor build requires an explicit MinGW CC",
        "git fetch --quiet --depth 1 origin $ExpectedCommit",
        "git rev-parse HEAD",
        "Extractor go.mod/toolchain drift",
        "go build -trimpath -buildvcs=false '-ldflags=-buildid='",
        "Get-FileHash -Algorithm SHA256",
        "Extractor SHA-256 mismatch",
        "payload-dumper-go-LICENSE.txt",
        'kind = "kaliphonestudio-windows-operator-extractor"',
        "native_package_versions = $VerifiedNativePackages",
        "cgo_enabled = $true",
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


def test_windows_extractor_workflow_builds_exact_non_release_artifact() -> None:
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
        "tools/extractor-locks.json",
        "operator-extractor-manifest.json",
        "payload-dumper-go.exe",
        "payload-dumper-go-LICENSE.txt",
        "native_dependencies_verified",
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
    assert "native dependency" in doc.lower()
    assert "does not bundle Android Platform-Tools" in doc
    assert "not a Beta release" in doc
    assert "no phone" in doc.lower()
