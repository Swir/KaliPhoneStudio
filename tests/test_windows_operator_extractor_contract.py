from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-operator-extractor.yml"
BUILDER = ROOT / "scripts" / "build_windows_operator_extractor.ps1"
LOCKS = ROOT / "tools" / "extractor-locks.json"
DOC = ROOT / "docs" / "WINDOWS_OPERATOR_EXTRACTOR.md"


def test_extractor_lock_is_exact_and_has_windows_hash() -> None:
    data = json.loads(LOCKS.read_text(encoding="utf-8"))
    assert data["extractor"] == "payload-dumper-go"
    assert len(data["source"]["commit"]) == 40
    assert data["build"]["toolchain"] == "go"
    assert data["build"]["toolchain_version"] == "1.27.0"
    digest = data["artifacts"]["windows-amd64"]["sha256"]
    assert len(digest) == 64
    int(digest, 16)


def test_windows_extractor_builder_is_source_locked_and_hash_gated() -> None:
    script = BUILDER.read_text(encoding="utf-8")

    for needle in (
        "tools/extractor-locks.json",
        "$Lock.source.commit",
        "$Lock.build.toolchain_version",
        "$Lock.artifacts.'windows-amd64'.sha256",
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
        "cgo_enabled = $true",
        "source_lock_verified = $true",
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
    assert "35fbcd36c553f81375a904ceca58aef5289da2e2e067fc0e6c835390588edfa5" in doc
    assert "does not bundle Android Platform-Tools" in doc
    assert "not a Beta release" in doc
    assert "no phone" in doc.lower()
