param(
    [string]$CandidateRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($CandidateRoot)) {
    if ($PSScriptRoot -and (Split-Path -Leaf $PSScriptRoot) -eq "operator-pack") {
        $CandidateRoot = Split-Path -Parent $PSScriptRoot
    }
    else { $CandidateRoot = (Get-Location).Path }
}

$Root = (Resolve-Path $CandidateRoot).Path
$InfoPath = Join-Path $Root "BETA_TEST_CANDIDATE_INFO.json"
$ManifestPath = Join-Path $Root "BETA_TEST_CANDIDATE_SHA256.txt"
foreach ($Path in @($InfoPath, $ManifestPath)) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Missing candidate file: $Path" }
}

$Info = Get-Content -Raw -Encoding UTF8 $InfoPath | ConvertFrom-Json
if ($Info.schema_version -ne 1) { throw "Unsupported candidate metadata schema" }
if ($Info.kind -ne "kaliphonestudio-unsigned-ac2003-beta-test-candidate") { throw "Unexpected candidate kind" }
if ($Info.profile_id -ne "oneplus/avicii") { throw "Unexpected candidate profile" }
if ([string]$Info.git_commit -notmatch '^[0-9a-f]{40}$') { throw "Candidate commit is missing or malformed" }
if ($Info.operator_extractor_included -ne $true) { throw "Candidate does not declare bundled extractor" }
if ($Info.operator_extractor_platform -ne "windows-amd64") { throw "Unexpected bundled extractor platform" }
if ([string]$Info.operator_extractor_sha256 -notmatch '^[0-9a-f]{64}$') { throw "Bundled extractor digest is malformed" }
if ($Info.host_preflight_included -ne $true) { throw "Candidate does not declare the AC2003 host preflight" }
if ($Info.host_preflight_device_interaction -ne $false) { throw "Candidate host preflight unexpectedly claims device interaction" }
if ($Info.signed -ne $false) { throw "Candidate unexpectedly claims signing" }
if ($Info.physical_gate_passed -ne $false) { throw "Candidate unexpectedly claims physical gate success" }
if ($Info.hardware_verified -ne $false) { throw "Candidate unexpectedly claims hardware verification" }
if ($Info.beta_release -ne $false) { throw "Candidate unexpectedly claims Beta release status" }
if ($Info.beta_gate_credit -ne $false) { throw "Candidate unexpectedly claims Beta gate credit" }

$Lines = Get-Content -Encoding ASCII $ManifestPath
if ($Lines.Count -eq 0) { throw "Candidate SHA-256 manifest is empty" }
$RootPrefix = $Root.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$Seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$Verified = 0
foreach ($Line in $Lines) {
    if ($Line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "Malformed SHA-256 manifest line: $Line" }
    $Expected = $Matches[1]
    $Relative = $Matches[2]
    if ([IO.Path]::IsPathRooted($Relative)) { throw "Manifest path must be relative: $Relative" }
    $LocalRelative = $Relative.Replace('/', [IO.Path]::DirectorySeparatorChar)
    $Candidate = [IO.Path]::GetFullPath((Join-Path $Root $LocalRelative))
    if (-not $Candidate.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Manifest path escapes candidate root: $Relative" }
    if (-not $Seen.Add($Candidate)) { throw "Duplicate manifest path: $Relative" }
    if (-not (Test-Path $Candidate -PathType Leaf)) { throw "Manifest file is missing: $Relative" }
    $Actual = (Get-FileHash -Algorithm SHA256 -Path $Candidate).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) { throw "SHA-256 mismatch for $Relative" }
    $Verified += 1
}
if ($Verified -lt 6) { throw "Candidate manifest contains too few files" }

$OperatorPack = Join-Path $Root "operator-pack"
$ToolsRoot = Join-Path $Root "operator-tools"
$PackagedLockPath = Join-Path $OperatorPack "extractor-locks.json"
$FastbootPolicyPath = Join-Path $OperatorPack "fastboot-tool-policy.json"
$HostPreflightPath = Join-Path $OperatorPack "host-preflight.ps1"
$ExtractorPath = Join-Path $ToolsRoot "payload-dumper-go.exe"
$ExtractorManifestPath = Join-Path $ToolsRoot "operator-extractor-manifest.json"
$RuntimeManifestPath = Join-Path $ToolsRoot "operator-extractor-runtime.json"
$LicensePath = Join-Path $ToolsRoot "payload-dumper-go-LICENSE.txt"
foreach ($Path in @($PackagedLockPath, $FastbootPolicyPath, $HostPreflightPath, $ExtractorPath, $ExtractorManifestPath, $RuntimeManifestPath, $LicensePath, (Join-Path $OperatorPack "START_HERE.txt"))) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Bundled operator-tool file missing: $Path" }
}
$Lock = Get-Content -Raw -Encoding UTF8 $PackagedLockPath | ConvertFrom-Json
$FastbootPolicy = Get-Content -Raw -Encoding UTF8 $FastbootPolicyPath | ConvertFrom-Json
if ([string]$FastbootPolicy.tool -ne "fastboot") { throw "Packaged Fastboot policy tool drift" }
if ([string]$FastbootPolicy.version_policy -ne "exact") { throw "Packaged Fastboot policy is not exact" }
if ([string]::IsNullOrWhiteSpace([string]$FastbootPolicy.platform_tools_version)) { throw "Packaged Fastboot policy version missing" }
if ($FastbootPolicy.hardware_verified -ne $false -or $FastbootPolicy.beta_gate_credit -ne $false) { throw "Packaged Fastboot policy contains unsafe hardware/Beta claims" }
$ExtractorManifest = Get-Content -Raw -Encoding UTF8 $ExtractorManifestPath | ConvertFrom-Json
$RuntimeManifest = Get-Content -Raw -Encoding UTF8 $RuntimeManifestPath | ConvertFrom-Json
$ExpectedExtractorSha = ([string]$Lock.artifacts.'windows-amd64'.sha256).ToLowerInvariant()
$ActualExtractorSha = (Get-FileHash -Algorithm SHA256 -Path $ExtractorPath).Hash.ToLowerInvariant()
if ($ActualExtractorSha -ne $ExpectedExtractorSha) { throw "Bundled extractor SHA-256 mismatch against packaged lock" }
if ($Info.operator_extractor_sha256 -ne $ExpectedExtractorSha) { throw "Candidate metadata extractor SHA-256 drift" }
if ($ExtractorManifest.executable_sha256 -ne $ExpectedExtractorSha) { throw "Extractor manifest SHA-256 drift" }
if ($ExtractorManifest.runtime_dependencies_resolved -ne $true -or $ExtractorManifest.clean_path_smoke_passed -ne $true) { throw "Extractor manifest runtime verification missing" }
if ($RuntimeManifest.all_non_system_imports_resolved -ne $true -or $RuntimeManifest.executable_sha256 -ne $ExpectedExtractorSha) { throw "Extractor runtime closure is incomplete" }
if ([int]$Info.operator_extractor_runtime_dependency_count -ne @($RuntimeManifest.runtime_dependencies).Count) { throw "Candidate metadata runtime dependency count drift" }
foreach ($Dependency in @($RuntimeManifest.runtime_dependencies)) {
    $Path = Join-Path $ToolsRoot ([string]$Dependency.name)
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Bundled extractor dependency missing: $Path" }
    $Digest = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    if ($Digest -ne ([string]$Dependency.sha256).ToLowerInvariant()) { throw "Bundled extractor dependency hash mismatch: $Path" }
}
foreach ($Field in @("physical_interaction_performed", "external_device_command_executed", "persistent_write_authorized", "phone_storage_written", "hardware_verified", "beta_release_authorized", "beta_gate_credit")) {
    if ($ExtractorManifest.$Field -ne $false) { throw "Unsafe extractor manifest field: $Field" }
}

Write-Host "KaliPhoneStudio AC2003 Beta test candidate integrity: PASS"
Write-Host "Commit: $($Info.git_commit)"
Write-Host "Profile: $($Info.profile_id)"
Write-Host "Verified files: $Verified"
Write-Host "Bundled extractor SHA-256: $ExpectedExtractorSha"
Write-Host "Host-only AC2003 preflight included: true"
Write-Host "Host preflight device interaction: false"
Write-Host "Physical gate passed: false"
Write-Host "Hardware verified: false"
Write-Host "Beta release: false"
