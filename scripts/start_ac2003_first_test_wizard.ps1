param(
    [Parameter(Mandatory = $true)]
    [string]$AdbExecutable,
    [Parameter(Mandatory = $true)]
    [string]$FastbootExecutable,
    [string]$CandidateRoot = ".",
    [string]$EvidenceRoot = ".\evidence",
    [string]$SessionLabel,
    [switch]$FastbootAlreadyReady
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Leaf([string]$Path, [string]$Label) {
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
}

function Invoke-ReadOnlyTool([string]$ToolPath, [string[]]$Arguments, [string]$Label) {
    $Output = (& $ToolPath @Arguments 2>&1 | Out-String).Trim()
    $Exit = $LASTEXITCODE
    if ($null -eq $Exit -or $Exit -ne 0) {
        throw "$Label failed: exit=$Exit output=$Output"
    }
    return $Output
}

$Root = (Resolve-Path $CandidateRoot).Path
$BaselineLauncher = Join-Path $Root "operator-pack\readonly-baseline.ps1"
$Preflight = Join-Path $Root "operator-pack\host-preflight.ps1"
Require-Leaf $BaselineLauncher "Packaged read-only baseline launcher"
Require-Leaf $Preflight "Packaged host preflight"

$AdbPath = (Resolve-Path $AdbExecutable).Path
$FastbootPath = (Resolve-Path $FastbootExecutable).Path
Require-Leaf $AdbPath "ADB executable"
Require-Leaf $FastbootPath "Fastboot executable"

# The physical campaign must use one reviewed Android Platform-Tools installation for
# both phases. Merely reporting the same version from unrelated directories is not
# sufficient for the one-command evidence path.
$AdbDirectory = [IO.Path]::GetFullPath((Split-Path -Parent $AdbPath)).TrimEnd('\')
$FastbootDirectory = [IO.Path]::GetFullPath((Split-Path -Parent $FastbootPath)).TrimEnd('\')
if (-not $AdbDirectory.Equals($FastbootDirectory, [StringComparison]::OrdinalIgnoreCase)) {
    throw "ADB and Fastboot must come from the same Android Platform-Tools directory: adb=$AdbDirectory fastboot=$FastbootDirectory"
}

$AdbShaAtStart = (Get-FileHash -Algorithm SHA256 -Path $AdbPath).Hash.ToLowerInvariant()
$FastbootShaAtStart = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath).Hash.ToLowerInvariant()

Write-Host "KaliPhoneStudio AC2003 FIRST TEST — host Platform-Tools pairing preflight"
& pwsh -NoProfile -File $Preflight -CandidateRoot $Root -FastbootExecutable $FastbootPath
if ($LASTEXITCODE -ne 0) {
    throw "Host/Fastboot preflight failed before any phone interaction: $LASTEXITCODE"
}
Write-Host "  Shared Platform-Tools directory: $AdbDirectory"
Write-Host "  ADB SHA-256: $AdbShaAtStart"
Write-Host "  Fastboot SHA-256: $FastbootShaAtStart"

$EvidenceRootPath = [IO.Path]::GetFullPath($EvidenceRoot)
if (Test-Path $EvidenceRootPath) {
    $EvidenceRootItem = Get-Item -LiteralPath $EvidenceRootPath -Force
    if (-not $EvidenceRootItem.PSIsContainer) {
        throw "EvidenceRoot is not a directory: $EvidenceRootPath"
    }
    if ($null -ne $EvidenceRootItem.LinkType) {
        throw "Refusing symlinked EvidenceRoot: $EvidenceRootPath"
    }
}
else {
    New-Item -ItemType Directory -Path $EvidenceRootPath | Out-Null
}

if ([string]::IsNullOrWhiteSpace($SessionLabel)) {
    $SessionLabel = [DateTime]::UtcNow.ToString("yyyyMMdd-HHmmssZ")
}
if ($SessionLabel -notmatch '^[A-Za-z0-9._-]+$') {
    throw "SessionLabel may contain only A-Z, a-z, 0-9, dot, underscore and dash"
}

$IdentityPath = Join-Path $EvidenceRootPath "ac2003-stock-android-identity-$SessionLabel.json"
$SessionPath = Join-Path $EvidenceRootPath "ac2003-first-test-$SessionLabel"
foreach ($Path in @($IdentityPath, $SessionPath)) {
    if (Test-Path $Path) {
        throw "Refusing to reuse existing first-test evidence path: $Path"
    }
}

Write-Host "KaliPhoneStudio AC2003 FIRST TEST — phase 1/2: stock OxygenOS read-only identity"
Write-Host "No reboot/boot/flash/erase/slot-change/storage-write command is issued by this wizard."
& pwsh -NoProfile -File $BaselineLauncher `
    -CandidateRoot $Root `
    -AdbExecutable $AdbPath `
    -AndroidIdentityEvidence $IdentityPath `
    -CaptureAndroidIdentityOnly
if ($LASTEXITCODE -ne 0) {
    throw "Stock Android identity capture failed: $LASTEXITCODE"
}

$Identity = Get-Content -Raw -Encoding UTF8 $IdentityPath | ConvertFrom-Json
if ([string]$Identity.profile_id -ne "oneplus/avicii") {
    throw "Captured stock Android identity profile drift"
}
if ($Identity.read_only_stock_android_capture -ne $true) {
    throw "Captured stock Android identity is not marked read-only"
}
if ($Identity.adb_reboot_performed -ne $false) {
    throw "Captured stock Android identity unexpectedly claims an ADB reboot"
}
foreach ($Field in @("persistent_write_authorized", "phone_storage_written", "hardware_verified", "beta_release_authorized", "beta_gate_credit")) {
    if ($Identity.$Field -ne $false) {
        throw "Unsafe captured stock Android identity field: $Field"
    }
}
if ([string]$Identity.adb_executable_sha256 -ne $AdbShaAtStart) {
    throw "Captured ADB identity is not bound to the wizard-start ADB executable"
}

Write-Host ""
Write-Host "Captured physical stock identity:"
Write-Host "  ADB serial: $([string]$Identity.adb_serial)"
Write-Host "  Product/model: $([string]$Identity.product) / $([string]$Identity.model)"
Write-Host "  OxygenOS/build: $([string]$Identity.firmware_build)"
Write-Host "  Fingerprint: $([string]$Identity.firmware_fingerprint)"
Write-Host ""

if (-not $FastbootAlreadyReady) {
    Write-Host "MANUAL MODE CHANGE REQUIRED"
    Write-Host "Put the same AC2003 into Fastboot/bootloader using the phone controls."
    Write-Host "Do not use an ADB reboot command for this evidence campaign."
    [void](Read-Host "When the phone is visibly in Fastboot/bootloader, press ENTER")
}

# Fail closed if either executable changed while the operator moved the same phone
# from stock OxygenOS into the bootloader.
$AdbShaBeforeFastboot = (Get-FileHash -Algorithm SHA256 -Path $AdbPath).Hash.ToLowerInvariant()
$FastbootShaBeforeFastboot = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath).Hash.ToLowerInvariant()
if ($AdbShaBeforeFastboot -ne $AdbShaAtStart -or $FastbootShaBeforeFastboot -ne $FastbootShaAtStart) {
    throw "Android Platform-Tools executable changed between wizard phases"
}

Write-Host "KaliPhoneStudio AC2003 FIRST TEST — phase 2/2: read-only Fastboot baseline"
& pwsh -NoProfile -File $Preflight -CandidateRoot $Root -FastbootExecutable $FastbootPath
if ($LASTEXITCODE -ne 0) {
    throw "Host/Fastboot preflight failed before device discovery: $LASTEXITCODE"
}

$Devices = Invoke-ReadOnlyTool $FastbootPath @("devices") "fastboot devices"
$FastbootDeviceLines = @(
    $Devices -split "`r?`n" |
        Where-Object { $_ -match '^\S+\s+fastboot(?:\s|$)' }
)
if ($FastbootDeviceLines.Count -ne 1) {
    throw "First-test wizard requires exactly one Fastboot device; got $($FastbootDeviceLines.Count)"
}
$FastbootSerial = (($FastbootDeviceLines[0] -split '\s+')[0]).Trim()
if ([string]::IsNullOrWhiteSpace($FastbootSerial)) {
    throw "Fastboot device discovery returned an empty serial"
}

& pwsh -NoProfile -File $BaselineLauncher `
    -CandidateRoot $Root `
    -FastbootExecutable $FastbootPath `
    -Serial $FastbootSerial `
    -AndroidIdentityEvidence $IdentityPath `
    -SessionDir $SessionPath
if ($LASTEXITCODE -ne 0) {
    throw "Read-only Fastboot baseline capture failed: $LASTEXITCODE"
}

$ExpectedOutputs = @(
    (Join-Path $SessionPath "physical-first-test-session.json"),
    (Join-Path $SessionPath "stock-android-identity.json"),
    (Join-Path $SessionPath "stock-android-identity-link.json"),
    (Join-Path $SessionPath "fastboot\fastboot-getvar-all.txt"),
    (Join-Path $SessionPath "fastboot\fastboot-baseline.json"),
    (Join-Path $SessionPath "fastboot\fastboot-tool.json"),
    (Join-Path $SessionPath "fastboot\fastboot-capture-bundle.json")
)
foreach ($Path in $ExpectedOutputs) {
    Require-Leaf $Path "Expected first-test evidence"
}

$Session = Get-Content -Raw -Encoding UTF8 (Join-Path $SessionPath "physical-first-test-session.json") | ConvertFrom-Json
if ([int]$Session.schema_version -ne 1) { throw "Unexpected first-test session schema" }
if ([string]$Session.profile_id -ne "oneplus/avicii") { throw "First-test session profile drift" }
if ([string]$Session.device_serial -ne $FastbootSerial) { throw "First-test session Fastboot serial drift" }
if ([string]$Session.firmware_build -ne [string]$Identity.firmware_build) { throw "First-test firmware build drift" }
if ([string]$Session.firmware_fingerprint -ne [string]$Identity.firmware_fingerprint) { throw "First-test firmware fingerprint drift" }
if ($Session.read_only_baseline_only -ne $true) { throw "First-test session lost read-only marker" }
foreach ($Field in @("temporary_boot_performed", "persistent_write_authorized", "phone_storage_written", "hardware_verified", "beta_gate_credit")) {
    if ($Session.$Field -ne $false) {
        throw "Unsafe first-test session field: $Field"
    }
}

$FastbootToolRecord = Get-Content -Raw -Encoding UTF8 (Join-Path $SessionPath "fastboot\fastboot-tool.json") | ConvertFrom-Json
$CapturedFastbootSha = $null
foreach ($CandidateField in @("executable_sha256", "fastboot_executable_sha256", "sha256")) {
    if ($null -ne $FastbootToolRecord.$CandidateField -and -not [string]::IsNullOrWhiteSpace([string]$FastbootToolRecord.$CandidateField)) {
        $CapturedFastbootSha = ([string]$FastbootToolRecord.$CandidateField).ToLowerInvariant()
        break
    }
}
if ($null -ne $CapturedFastbootSha -and $CapturedFastbootSha -ne $FastbootShaAtStart) {
    throw "Captured Fastboot evidence is not bound to the wizard-start Fastboot executable"
}

Write-Host ""
Write-Host "KaliPhoneStudio AC2003 FIRST TEST READ-ONLY BASELINE: PASS"
Write-Host "Identity evidence: $IdentityPath"
Write-Host "Physical session: $SessionPath"
Write-Host "Fastboot serial: $FastbootSerial"
Write-Host "Shared Platform-Tools directory: $AdbDirectory"
Write-Host "ADB SHA-256: $AdbShaAtStart"
Write-Host "Fastboot SHA-256: $FastbootShaAtStart"
Write-Host "Persistent phone write authorized: false"
Write-Host "Temporary boot performed: false"
Write-Host "Hardware verified: false"
Write-Host "Beta gate credit: false"
Write-Host "Next: obtain the exact matching OxygenOS OTA and continue operator-pack\AC2003_FIRST_TEST.md at the stock boot.img provenance step."
