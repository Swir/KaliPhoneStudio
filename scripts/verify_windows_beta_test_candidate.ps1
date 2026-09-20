param(
    [string]$CandidateRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($CandidateRoot)) {
    if ($PSScriptRoot -and (Split-Path -Leaf $PSScriptRoot) -eq "operator-pack") {
        $CandidateRoot = Split-Path -Parent $PSScriptRoot
    }
    else {
        $CandidateRoot = (Get-Location).Path
    }
}

$Root = (Resolve-Path $CandidateRoot).Path
$InfoPath = Join-Path $Root "BETA_TEST_CANDIDATE_INFO.json"
$ManifestPath = Join-Path $Root "BETA_TEST_CANDIDATE_SHA256.txt"

if (-not (Test-Path $InfoPath -PathType Leaf)) {
    throw "Missing candidate metadata: $InfoPath"
}
if (-not (Test-Path $ManifestPath -PathType Leaf)) {
    throw "Missing candidate SHA-256 manifest: $ManifestPath"
}

$Info = Get-Content -Raw -Encoding utf8 $InfoPath | ConvertFrom-Json
if ($Info.schema_version -ne 1) { throw "Unsupported candidate metadata schema" }
if ($Info.kind -ne "kaliphonestudio-unsigned-ac2003-beta-test-candidate") {
    throw "Unexpected candidate kind"
}
if ($Info.profile_id -ne "oneplus/avicii") { throw "Unexpected candidate profile" }
if ([string]::IsNullOrWhiteSpace([string]$Info.git_commit)) { throw "Candidate commit is missing" }
if ($Info.signed -ne $false) { throw "Candidate unexpectedly claims signing" }
if ($Info.physical_gate_passed -ne $false) { throw "Candidate unexpectedly claims physical gate success" }
if ($Info.hardware_verified -ne $false) { throw "Candidate unexpectedly claims hardware verification" }
if ($Info.beta_release -ne $false) { throw "Candidate unexpectedly claims Beta release status" }
if ($Info.beta_gate_credit -ne $false) { throw "Candidate unexpectedly claims Beta gate credit" }

$Lines = Get-Content -Encoding ascii $ManifestPath
if ($Lines.Count -eq 0) { throw "Candidate SHA-256 manifest is empty" }

$RootPrefix = $Root.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$Seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$Verified = 0

foreach ($Line in $Lines) {
    if ($Line -notmatch '^([0-9a-f]{64})  (.+)$') {
        throw "Malformed SHA-256 manifest line: $Line"
    }
    $Expected = $Matches[1]
    $Relative = $Matches[2]
    if ([IO.Path]::IsPathRooted($Relative)) { throw "Manifest path must be relative: $Relative" }

    $LocalRelative = $Relative.Replace('/', [IO.Path]::DirectorySeparatorChar)
    $Candidate = [IO.Path]::GetFullPath((Join-Path $Root $LocalRelative))
    if (-not $Candidate.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest path escapes candidate root: $Relative"
    }
    if (-not $Seen.Add($Candidate)) { throw "Duplicate manifest path: $Relative" }
    if (-not (Test-Path $Candidate -PathType Leaf)) { throw "Manifest file is missing: $Relative" }

    $Actual = (Get-FileHash -Algorithm SHA256 -Path $Candidate).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) {
        throw "SHA-256 mismatch for $Relative"
    }
    $Verified += 1
}

if ($Verified -lt 3) { throw "Candidate manifest contains too few files" }

Write-Host "KaliPhoneStudio AC2003 Beta test candidate integrity: PASS"
Write-Host "Commit: $($Info.git_commit)"
Write-Host "Profile: $($Info.profile_id)"
Write-Host "Verified files: $Verified"
Write-Host "Physical gate passed: false"
Write-Host "Hardware verified: false"
Write-Host "Beta release: false"
