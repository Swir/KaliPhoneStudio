param(
    [Parameter(Mandatory = $true)]
    [string]$FastbootExecutable,
    [Parameter(Mandatory = $true)]
    [string]$Serial,
    [Parameter(Mandatory = $true)]
    [string]$FirmwareBuild,
    [Parameter(Mandatory = $true)]
    [string]$FirmwareFingerprint,
    [Parameter(Mandatory = $true)]
    [string]$SessionDir,
    [string]$CandidateRoot = "."
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

foreach ($Value in @($FastbootExecutable, $Serial, $FirmwareBuild, $FirmwareFingerprint, $SessionDir)) {
    if ([string]::IsNullOrWhiteSpace([string]$Value)) {
        throw "AC2003 read-only baseline launcher requires every exact input"
    }
}

$Root = (Resolve-Path $CandidateRoot).Path
$Preflight = Join-Path $Root "operator-pack\host-preflight.ps1"
$PolicyPath = Join-Path $Root "operator-pack\fastboot-tool-policy.json"
$Cli = Join-Path $Root "KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe"
foreach ($Path in @($Preflight, $PolicyPath, $Cli)) {
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "Required AC2003 baseline-launcher input missing: $Path"
    }
}

$SessionPath = [IO.Path]::GetFullPath($SessionDir)
if (Test-Path $SessionPath) {
    throw "Refusing to reuse an existing physical test session: $SessionPath"
}

$FastbootPath = (Resolve-Path $FastbootExecutable).Path
& pwsh -NoProfile -File $Preflight -CandidateRoot $Root -FastbootExecutable $FastbootPath
if ($LASTEXITCODE -ne 0) {
    throw "AC2003 host preflight failed before physical read-only capture: $LASTEXITCODE"
}

$CliArgs = @(
    "begin-physical-test-session",
    "--profile-id", "oneplus/avicii",
    "--serial", $Serial,
    "--firmware-build", $FirmwareBuild,
    "--firmware-fingerprint", $FirmwareFingerprint,
    "--confirm-token", "AC2003",
    "--fastboot", $FastbootPath,
    "--fastboot-policy", $PolicyPath,
    "--session-dir", $SessionPath
)
& $Cli @CliArgs
$CliExit = $LASTEXITCODE
if ($null -eq $CliExit -or $CliExit -ne 0) {
    throw "Frozen CLI refused the AC2003 read-only baseline session: exit=$CliExit"
}

$ManifestPath = Join-Path $SessionPath "physical-first-test-session.json"
$TranscriptPath = Join-Path $SessionPath "fastboot\fastboot-getvar-all.txt"
$BaselinePath = Join-Path $SessionPath "fastboot\fastboot-baseline.json"
$ToolPath = Join-Path $SessionPath "fastboot\fastboot-tool.json"
$CapturePath = Join-Path $SessionPath "fastboot\fastboot-capture-bundle.json"
foreach ($Path in @($ManifestPath, $TranscriptPath, $BaselinePath, $ToolPath, $CapturePath)) {
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "Expected read-only baseline evidence missing after capture: $Path"
    }
}

$Manifest = Get-Content -Raw -Encoding UTF8 $ManifestPath | ConvertFrom-Json
if ([int]$Manifest.schema_version -ne 1) { throw "Unexpected first-test session schema" }
if ([string]$Manifest.profile_id -ne "oneplus/avicii") { throw "First-test profile identity drift" }
if ([string]$Manifest.device_serial -ne $Serial) { throw "First-test serial identity drift" }
if ([string]$Manifest.firmware_build -ne $FirmwareBuild) { throw "First-test firmware build drift" }
if ([string]$Manifest.firmware_fingerprint -ne $FirmwareFingerprint) { throw "First-test firmware fingerprint drift" }
if ($Manifest.confirmation_token_verified -ne $true) { throw "Profile confirmation token was not verified" }
if ($Manifest.physical_interaction_performed -ne $true) { throw "Read-only physical capture did not run" }
if ($Manifest.read_only_baseline_only -ne $true) { throw "First-test session is not marked read-only" }
if ($Manifest.temporary_boot_performed -ne $false) { throw "Unexpected temporary boot claim in baseline session" }
if ($Manifest.persistent_write_authorized -ne $false) { throw "Unexpected persistent-write authorization in baseline session" }
if ($Manifest.phone_storage_written -ne $false) { throw "Unexpected phone-storage write claim in baseline session" }
if ($Manifest.hardware_verified -ne $false) { throw "Unexpected hardware-verification claim in baseline session" }
if ($Manifest.beta_gate_credit -ne $false) { throw "Unexpected Beta-gate credit in baseline session" }

$Policy = Get-Content -Raw -Encoding UTF8 $PolicyPath | ConvertFrom-Json
if ([string]$Manifest.fastboot_platform_tools_version -ne [string]$Policy.platform_tools_version) {
    throw "Fastboot version drift between packaged policy and captured session"
}
$FastbootSha = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath).Hash.ToLowerInvariant()
if ([string]$Manifest.fastboot_executable_sha256 -ne $FastbootSha) {
    throw "Fastboot executable drifted after physical baseline capture"
}

$EvidenceDigests = [ordered]@{
    fastboot_capture_bundle_sha256 = (Get-FileHash -Algorithm SHA256 -Path $CapturePath).Hash.ToLowerInvariant()
    fastboot_baseline_sha256 = (Get-FileHash -Algorithm SHA256 -Path $BaselinePath).Hash.ToLowerInvariant()
    fastboot_tool_evidence_sha256 = (Get-FileHash -Algorithm SHA256 -Path $ToolPath).Hash.ToLowerInvariant()
    fastboot_transcript_sha256 = (Get-FileHash -Algorithm SHA256 -Path $TranscriptPath).Hash.ToLowerInvariant()
}
foreach ($Entry in $EvidenceDigests.GetEnumerator()) {
    $Recorded = [string]$Manifest.PSObject.Properties[$Entry.Key].Value
    if ($Recorded -ne [string]$Entry.Value) {
        throw "Physical first-test evidence drift after capture: $($Entry.Key)"
    }
}

Write-Host "KaliPhoneStudio AC2003 read-only baseline: PASS"
Write-Host "Session: $SessionPath"
Write-Host "Profile: oneplus/avicii"
Write-Host "Serial: $Serial"
Write-Host "Firmware build: $FirmwareBuild"
Write-Host "Fastboot SHA-256: $FastbootSha"
Write-Host "Physical interaction performed: true (read-only Fastboot baseline only)"
Write-Host "Temporary boot performed: false"
Write-Host "Persistent phone write authorized: false"
Write-Host "Hardware verified: false"
Write-Host "Beta gate credit: false"
Write-Host "Next: obtain the exact matching OxygenOS OTA, then follow AC2003_FIRST_TEST.md section 4."
exit 0
