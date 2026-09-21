param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$SourceCommit,
    [string]$DistRoot = "dist"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Root = (Resolve-Path $DistRoot).Path
$SourceCommit = $SourceCommit.ToLowerInvariant()
$GuiRoot = Join-Path $Root "KaliPhoneStudio"
$CliRoot = Join-Path $Root "KaliPhoneStudioCLI"
$ToolsRoot = Join-Path $Root "operator-tools"
$OperatorPack = Join-Path $Root "operator-pack"

foreach ($Path in @($GuiRoot, $CliRoot, $ToolsRoot)) {
    if (-not (Test-Path $Path -PathType Container)) { throw "Candidate component missing: $Path" }
}
if (Test-Path $OperatorPack) { throw "Refusing to overwrite existing operator pack: $OperatorPack" }

$LockPath = Join-Path $RepoRoot "tools\extractor-locks.json"
$Lock = Get-Content -Raw -Encoding UTF8 $LockPath | ConvertFrom-Json
$ExpectedExtractorSha = ([string]$Lock.artifacts.'windows-amd64'.sha256).ToLowerInvariant()
$ExtractorPath = Join-Path $ToolsRoot "payload-dumper-go.exe"
$ExtractorManifestPath = Join-Path $ToolsRoot "operator-extractor-manifest.json"
$RuntimeManifestPath = Join-Path $ToolsRoot "operator-extractor-runtime.json"
foreach ($Path in @($ExtractorPath, $ExtractorManifestPath, $RuntimeManifestPath, (Join-Path $ToolsRoot "payload-dumper-go-LICENSE.txt"))) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Required operator tool file missing: $Path" }
}
$ActualExtractorSha = (Get-FileHash -Algorithm SHA256 -Path $ExtractorPath).Hash.ToLowerInvariant()
if ($ActualExtractorSha -ne $ExpectedExtractorSha) { throw "Operator extractor SHA-256 drift" }
$ExtractorManifest = Get-Content -Raw -Encoding UTF8 $ExtractorManifestPath | ConvertFrom-Json
$RuntimeManifest = Get-Content -Raw -Encoding UTF8 $RuntimeManifestPath | ConvertFrom-Json
if ($ExtractorManifest.executable_sha256 -ne $ExpectedExtractorSha) { throw "Operator extractor manifest hash drift" }
if ($ExtractorManifest.runtime_dependencies_resolved -ne $true -or $ExtractorManifest.clean_path_smoke_passed -ne $true) { throw "Operator extractor runtime verification missing" }
if ($RuntimeManifest.all_non_system_imports_resolved -ne $true -or $RuntimeManifest.executable_sha256 -ne $ExpectedExtractorSha) { throw "Operator extractor runtime closure drift" }
foreach ($Dependency in @($RuntimeManifest.runtime_dependencies)) {
    $Path = Join-Path $ToolsRoot ([string]$Dependency.name)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Operator runtime dependency missing: $Path" }
    $Digest = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    if ($Digest -ne ([string]$Dependency.sha256).ToLowerInvariant()) { throw "Operator runtime dependency hash drift: $Path" }
}
foreach ($Field in @("physical_interaction_performed", "external_device_command_executed", "persistent_write_authorized", "phone_storage_written", "hardware_verified", "beta_release_authorized", "beta_gate_credit")) {
    if ($ExtractorManifest.$Field -ne $false) { throw "Unsafe extractor manifest field: $Field" }
}

New-Item -ItemType Directory -Path $OperatorPack | Out-Null
$StageMap = [ordered]@{
    "docs/AC2003_FIRST_TEST.md" = "AC2003_FIRST_TEST.md"
    "docs/AC2003_OFFLINE_CANDIDATE_PREPARATION.md" = "AC2003_OFFLINE_CANDIDATE_PREPARATION.md"
    "docs/BETA_RELEASE_OPERATOR_WORKSPACE.md" = "BETA_RELEASE_OPERATOR_WORKSPACE.md"
    "docs/BETA_RELEASE_ARTIFACT_INVENTORY.md" = "BETA_RELEASE_ARTIFACT_INVENTORY.md"
    "docs/BETA_RELEASE_REVIEW_MANIFEST.md" = "BETA_RELEASE_REVIEW_MANIFEST.md"
    "docs/WINDOWS_OPERATOR_EXTRACTOR.md" = "WINDOWS_OPERATOR_EXTRACTOR.md"
    "BETA_RELEASE_GATE.md" = "BETA_RELEASE_GATE.md"
    "BUILD_STATUS.json" = "BUILD_STATUS.json"
    "devices/oneplus/avicii/profile.json" = "profile.json"
    "tools/fastboot-tool-policy.json" = "fastboot-tool-policy.json"
    "tools/extractor-locks.json" = "extractor-locks.json"
    "scripts/verify_windows_beta_test_candidate.ps1" = "verify-candidate.ps1"
    "scripts/preflight_ac2003_first_test.ps1" = "host-preflight.ps1"
}
foreach ($Entry in $StageMap.GetEnumerator()) {
    $Source = Join-Path $RepoRoot $Entry.Key
    if (-not (Test-Path $Source -PathType Leaf)) { throw "Operator-pack source missing: $($Entry.Key)" }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $OperatorPack $Entry.Value)
}

@"
KaliPhoneStudio AC2003 host test candidate
===========================================

1. Point to the reviewed Fastboot executable governed by the packaged exact policy:
   `$Fastboot = (Resolve-Path "<PATH_TO_REVIEWED_FASTBOOT_EXE>").Path

2. Run the one-command HOST-ONLY preflight before connecting the phone:
   pwsh -NoProfile -File .\operator-pack\host-preflight.ps1 -CandidateRoot . -FastbootExecutable "`$Fastboot"

   This re-verifies the full candidate integrity set, checks the exact Fastboot version,
   records its SHA-256 on screen, and runs ONLY `fastboot --version` (no device command).

3. Frozen CLI:
   .\KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe

4. Exact bundled OTA extractor (no separate download/search required):
   .\operator-tools\payload-dumper-go.exe

5. Start the physical campaign with:
   .\operator-pack\AC2003_FIRST_TEST.md

6. For the one-command host-only OTA/candidate preparation details:
   .\operator-pack\AC2003_OFFLINE_CANDIDATE_PREPARATION.md

7. After the REAL physical gate evidence is complete, use the offline release-prep chain only:
   .\operator-pack\BETA_RELEASE_OPERATOR_WORKSPACE.md
   .\operator-pack\BETA_RELEASE_ARTIFACT_INVENTORY.md
   .\operator-pack\BETA_RELEASE_REVIEW_MANIFEST.md

This is an unsigned host-side test candidate, NOT a public Beta and NOT hardware verification.
No persistent phone write is authorized by this package. Release-prep files do not authorize publication.
"@ | Set-Content -Encoding UTF8 (Join-Path $OperatorPack "START_HERE.txt")

$InfoPath = Join-Path $Root "BETA_TEST_CANDIDATE_INFO.json"
$ManifestPath = Join-Path $Root "BETA_TEST_CANDIDATE_SHA256.txt"
$ZipPath = Join-Path $Root "KaliPhoneStudio-AC2003-beta-test-candidate.zip"
$ZipShaPath = "$ZipPath.sha256"
foreach ($Path in @($InfoPath, $ManifestPath, $ZipPath, $ZipShaPath)) {
    if (Test-Path $Path) { throw "Refusing to overwrite candidate output: $Path" }
}

[ordered]@{
    schema_version = 1
    kind = "kaliphonestudio-unsigned-ac2003-beta-test-candidate"
    git_commit = $SourceCommit
    profile_id = "oneplus/avicii"
    python = "3.12"
    pyinstaller = "6.22.3"
    pyinstaller_hooks_contrib = "2026.7"
    packaging_mode = "onedir"
    operator_extractor_included = $true
    operator_extractor_platform = "windows-amd64"
    operator_extractor_sha256 = $ExpectedExtractorSha
    operator_extractor_runtime_dependency_count = @($RuntimeManifest.runtime_dependencies).Count
    host_preflight_included = $true
    host_preflight_device_interaction = $false
    signed = $false
    physical_gate_passed = $false
    hardware_verified = $false
    beta_release = $false
    beta_gate_credit = $false
} | ConvertTo-Json | Set-Content -Encoding UTF8 $InfoPath

$Files = @()
foreach ($Target in @($GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack)) {
    $Files += Get-ChildItem -Path $Target -Recurse -File
}
$Files += Get-Item $InfoPath
$Lines = $Files |
    Sort-Object FullName |
    ForEach-Object {
        $Hash = (Get-FileHash -Algorithm SHA256 -Path $_.FullName).Hash.ToLowerInvariant()
        $Relative = [IO.Path]::GetRelativePath($Root, $_.FullName).Replace('\\', '/')
        "$Hash  $Relative"
    }
$Lines | Set-Content -Encoding ASCII $ManifestPath

& pwsh -NoProfile -File (Join-Path $OperatorPack "verify-candidate.ps1") -CandidateRoot $Root
if ($LASTEXITCODE -ne 0) { throw "Candidate integrity verifier failed: $LASTEXITCODE" }

$FastbootPolicy = Get-Content -Raw -Encoding UTF8 (Join-Path $OperatorPack "fastboot-tool-policy.json") | ConvertFrom-Json
$PreflightScratch = Join-Path ([IO.Path]::GetTempPath()) ("kps-ac2003-preflight-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $PreflightScratch | Out-Null
try {
    $FakeFastboot = Join-Path $PreflightScratch "fastboot.cmd"
    @(
        "@echo off",
        "echo fastboot version $([string]$FastbootPolicy.platform_tools_version)-kps-packaging-smoke",
        "exit /b 0"
    ) | Set-Content -Encoding ASCII $FakeFastboot
    & pwsh -NoProfile -File (Join-Path $OperatorPack "host-preflight.ps1") -CandidateRoot $Root -FastbootExecutable $FakeFastboot
    if ($LASTEXITCODE -ne 0) { throw "AC2003 host preflight packaging smoke failed: $LASTEXITCODE" }
}
finally {
    Remove-Item -LiteralPath $PreflightScratch -Recurse -Force -ErrorAction SilentlyContinue
}

Compress-Archive -Path $GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack, $ManifestPath, $InfoPath -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
"$ZipHash  KaliPhoneStudio-AC2003-beta-test-candidate.zip" | Set-Content -Encoding ASCII $ZipShaPath

Write-Host "Integrated AC2003 Windows host test candidate: PASS"
Write-Host "Source commit: $SourceCommit"
Write-Host "Bundled extractor SHA-256: $ExpectedExtractorSha"
Write-Host "Host-only AC2003 preflight: PASS"
Write-Host "Physical gate passed: false"
Write-Host "Beta release: false"
