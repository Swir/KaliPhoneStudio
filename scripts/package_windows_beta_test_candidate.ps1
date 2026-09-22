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
    "docs/AC2003_PHOSH_HANDOFF.md" = "AC2003_PHOSH_HANDOFF.md"
    "docs/PHOSH_FIRST_BOOT_BINDING.md" = "PHOSH_FIRST_BOOT_BINDING.md"
    "docs/PHOSH_SUCCESSOR_CANDIDATE.md" = "PHOSH_SUCCESSOR_CANDIDATE.md"
    "docs/PHOSH_PHYSICAL_CANDIDATE_ADAPTER.md" = "PHOSH_PHYSICAL_CANDIDATE_ADAPTER.md"
    "evidence/authorities/phosh-arm64-rootfs-2026-09-21.json" = "phosh-rootfs-authority.json"
    "evidence/authorities/phosh-arm64-rootfs-2026-09-21-review-packet.json" = "phosh-rootfs-review-packet.json"
    "docs/OPERATOR_WORKSPACE.md" = "OPERATOR_WORKSPACE.md"
    "docs/KALI_EARLY_USERSPACE_PROOF.md" = "KALI_EARLY_USERSPACE_PROOF.md"
    "docs/ROOTFS_HANDOFF_STRATEGY_REVIEW.md" = "ROOTFS_HANDOFF_STRATEGY_REVIEW.md"
    "docs/ROOTFS_HANDOFF_TARGET_BINDING.md" = "ROOTFS_HANDOFF_TARGET_BINDING.md"
    "docs/ROOTFS_HANDOFF_FRESH_REVALIDATION.md" = "ROOTFS_HANDOFF_FRESH_REVALIDATION.md"
    "docs/ROOTFS_HANDOFF_TRIAL_PLAN.md" = "ROOTFS_HANDOFF_TRIAL_PLAN.md"
    "docs/ROOTFS_HANDOFF_TRIAL_PREFLIGHT.md" = "ROOTFS_HANDOFF_TRIAL_PREFLIGHT.md"
    "docs/ROOTFS_HANDOFF_TRIAL_AUTHORIZATION.md" = "ROOTFS_HANDOFF_TRIAL_AUTHORIZATION.md"
    "docs/ROOTFS_HANDOFF_TRIAL_EXECUTION_GATE.md" = "ROOTFS_HANDOFF_TRIAL_EXECUTION_GATE.md"
    "docs/ROOTFS_HANDOFF_TRIAL_METADATA_MANIFEST.md" = "ROOTFS_HANDOFF_TRIAL_METADATA_MANIFEST.md"
    "docs/ROOTFS_HANDOFF_TRIAL_PAYLOAD_MANIFEST.md" = "ROOTFS_HANDOFF_TRIAL_PAYLOAD_MANIFEST.md"
    "docs/ROOTFS_HANDOFF_INTERACTIVE_EXECUTOR.md" = "ROOTFS_HANDOFF_INTERACTIVE_EXECUTOR.md"
    "docs/ROOTFS_TRIAL_CHAIN_AUDIT.md" = "ROOTFS_TRIAL_CHAIN_AUDIT.md"
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
    "scripts/start_ac2003_readonly_baseline.ps1" = "readonly-baseline.ps1"
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

3. After recording the exact OxygenOS build/fingerprint and putting the phone in Fastboot,
   create the fresh read-only physical baseline in one command:
   pwsh -NoProfile -File .\operator-pack\readonly-baseline.ps1 -CandidateRoot . -FastbootExecutable "`$Fastboot" -Serial "<EXACT_FASTBOOT_SERIAL>" -FirmwareBuild "<EXACT_OXYGENOS_BUILD>" -FirmwareFingerprint "<EXACT_FIRMWARE_FINGERPRINT>" -SessionDir ".\evidence\ac2003-first-test-01"

   The launcher re-runs host preflight, then executes only the frozen
   begin-physical-test-session path (Fastboot version/devices/getvar capture). It does not
   boot, reboot, flash, erase, change slots, mount storage or authorize a persistent write.

4. Frozen CLI:
   .\KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe

5. Exact bundled OTA extractor (no separate download/search required):
   .\operator-tools\payload-dumper-go.exe

6. Continue the recovery-first physical campaign with:
   .\operator-pack\AC2003_FIRST_TEST.md

7. For the one-command host-only OTA/candidate preparation details:
   .\operator-pack\AC2003_OFFLINE_CANDIDATE_PREPARATION.md

8. After the exact physical-candidate gate exists, bind the reviewed Phosh successor with
   the frozen CLI and packaged reviewed authority records:
   .\operator-pack\AC2003_PHOSH_HANDOFF.md
   .\operator-pack\phosh-rootfs-authority.json
   .\operator-pack\phosh-rootfs-review-packet.json

   This handoff is host-only. It does not stage rootfs bytes or authorize a phone write.

9. After temporary boot, keep the whole physical/evidence/rootfs chain offline and use the
   packaged operator references instead of searching the repository or Internet:
   .\operator-pack\OPERATOR_WORKSPACE.md
   .\operator-pack\KALI_EARLY_USERSPACE_PROOF.md
   .\operator-pack\ROOTFS_HANDOFF_STRATEGY_REVIEW.md
   .\operator-pack\ROOTFS_HANDOFF_TARGET_BINDING.md
   .\operator-pack\ROOTFS_HANDOFF_FRESH_REVALIDATION.md
   .\operator-pack\ROOTFS_HANDOFF_TRIAL_PLAN.md
   .\operator-pack\ROOTFS_HANDOFF_TRIAL_PREFLIGHT.md
   .\operator-pack\ROOTFS_HANDOFF_TRIAL_AUTHORIZATION.md
   .\operator-pack\ROOTFS_HANDOFF_TRIAL_EXECUTION_GATE.md
   .\operator-pack\ROOTFS_HANDOFF_TRIAL_METADATA_MANIFEST.md
   .\operator-pack\ROOTFS_HANDOFF_TRIAL_PAYLOAD_MANIFEST.md
   .\operator-pack\ROOTFS_HANDOFF_INTERACTIVE_EXECUTOR.md
   .\operator-pack\ROOTFS_TRIAL_CHAIN_AUDIT.md

   The interactive staging helper is inside the deterministic rescue candidate and is never
   auto-run. Rootfs staging remains a separately reviewed, local-console, explicit-confirmation
   boundary and is not authorized by merely possessing this Windows package.

10. After the REAL physical gate evidence is complete, use the offline release-prep chain only:
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
    readonly_baseline_launcher_included = $true
    readonly_baseline_device_interaction = $true
    readonly_baseline_persistent_write_authorized = $false
    phosh_handoff_included = $true
    phosh_reviewed_authority_included = $true
    phosh_rootfs_bytes_included = $false
    offline_post_boot_operator_chain_included = $true
    rootfs_interactive_staging_auto_run = $false
    rootfs_persistent_write_authorized = $false
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
Write-Host "One-command AC2003 read-only baseline launcher: INCLUDED"
Write-Host "Reviewed Phosh handoff: INCLUDED (authority records only; rootfs bytes excluded)"
Write-Host "Offline post-boot/rootfs operator chain: INCLUDED (documentation and frozen CLI only)"
Write-Host "Physical gate passed: false"
Write-Host "Beta release: false"