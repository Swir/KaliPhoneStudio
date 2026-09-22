param(
    [string]$CandidateRoot = ".",
    [string]$RuntimeRoot = "operator-runtime",
    [string]$EvidenceRoot = "evidence",
    [string]$LockPath,
    [switch]$DownloadOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Leaf([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
}

function Require-Directory([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Label not found: $Path"
    }
    $Item = Get-Item -LiteralPath $Path -Force
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing reparse-point $Label: $Path"
    }
}

function Resolve-CandidatePath([string]$Root, [string]$Value) {
    if ([IO.Path]::IsPathRooted($Value)) {
        return [IO.Path]::GetFullPath($Value)
    }
    return [IO.Path]::GetFullPath((Join-Path $Root $Value))
}

function Assert-Https([string]$Url, [string]$Label) {
    $Uri = New-Object System.Uri($Url)
    if ($Uri.Scheme -ne "https") {
        throw "$Label must use HTTPS: $Url"
    }
}

function Ensure-PinnedArchive($Spec, [string]$Destination, [string]$Label) {
    $Expected = ([string]$Spec.sha256).ToLowerInvariant()
    if ($Expected -notmatch '^[0-9a-f]{64}$') {
        throw "$Label lock has invalid SHA-256"
    }
    Assert-Https ([string]$Spec.url) "$Label URL"

    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $Existing = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToLowerInvariant()
        if ($Existing -eq $Expected) {
            Write-Host "Using cached pinned $Label archive: $Destination"
            return $Existing
        }
        Remove-Item -LiteralPath $Destination -Force
    }

    Write-Host "Downloading pinned $Label..."
    Invoke-WebRequest -UseBasicParsing -Uri ([string]$Spec.url) -OutFile $Destination
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) {
        Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        throw "$Label SHA-256 mismatch: expected=$Expected actual=$Actual"
    }
    return $Actual
}

$Root = (Resolve-Path $CandidateRoot).Path
$Pack = Join-Path $Root "operator-pack"
if ([string]::IsNullOrWhiteSpace($LockPath)) {
    $LockPath = Join-Path $Pack "bootstrap-lock.json"
}
else {
    $LockPath = Resolve-CandidatePath $Root $LockPath
}
Require-Leaf $LockPath "Bootstrap lock"
$Lock = Get-Content -Raw -Encoding UTF8 $LockPath | ConvertFrom-Json
if ([int]$Lock.schema_version -ne 1 -or [string]$Lock.kind -ne "kaliphonestudio-ac2003-host-bootstrap-lock") {
    throw "Unsupported AC2003 bootstrap lock"
}

$Runtime = Resolve-CandidatePath $Root $RuntimeRoot
$Evidence = Resolve-CandidatePath $Root $EvidenceRoot
if (-not (Test-Path -LiteralPath $Runtime)) {
    New-Item -ItemType Directory -Path $Runtime | Out-Null
}
Require-Directory $Runtime "Runtime root"
if (-not (Test-Path -LiteralPath $Evidence)) {
    New-Item -ItemType Directory -Path $Evidence | Out-Null
}
Require-Directory $Evidence "Evidence root"

$Downloads = Join-Path $Runtime "downloads"
if (-not (Test-Path -LiteralPath $Downloads)) {
    New-Item -ItemType Directory -Path $Downloads | Out-Null
}
Require-Directory $Downloads "Bootstrap downloads"

# Windows PowerShell 5.1 defaults can otherwise negotiate an obsolete TLS mode.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PsVersion = [string]$Lock.powershell.version
$PlatformToolsVersion = [string]$Lock.platform_tools.version
$PowerShellZip = Join-Path $Downloads ("PowerShell-" + $PsVersion + "-win-x64.zip")
$PlatformToolsZip = Join-Path $Downloads ("platform-tools_r" + $PlatformToolsVersion + "-win.zip")

$PowerShellArchiveSha = Ensure-PinnedArchive $Lock.powershell $PowerShellZip "PowerShell"
$PlatformToolsArchiveSha = Ensure-PinnedArchive $Lock.platform_tools $PlatformToolsZip "Android Platform-Tools"

$PowerShellRoot = Join-Path $Runtime ("powershell-" + $PsVersion)
$PlatformToolsRoot = Join-Path $Runtime ("platform-tools-" + $PlatformToolsVersion)
foreach ($Path in @($PowerShellRoot, $PlatformToolsRoot)) {
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

Write-Host "Extracting verified host runtime..."
Expand-Archive -LiteralPath $PowerShellZip -DestinationPath $PowerShellRoot -Force
Expand-Archive -LiteralPath $PlatformToolsZip -DestinationPath $PlatformToolsRoot -Force

$Pwsh = Join-Path $PowerShellRoot "pwsh.exe"
$PlatformToolsDir = Join-Path $PlatformToolsRoot "platform-tools"
$Adb = Join-Path $PlatformToolsDir "adb.exe"
$Fastboot = Join-Path $PlatformToolsDir "fastboot.exe"
Require-Leaf $Pwsh "Pinned portable PowerShell"
Require-Leaf $Adb "Pinned ADB"
Require-Leaf $Fastboot "Pinned Fastboot"

$ObservedPwsh = (& $Pwsh -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()' 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $ObservedPwsh -ne $PsVersion) {
    throw "Portable PowerShell version drift: expected=$PsVersion observed=$ObservedPwsh"
}

$AdbVersionText = (& $Adb --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $AdbVersionText -notmatch [Regex]::Escape($PlatformToolsVersion)) {
    throw "ADB version drift: expected Platform-Tools $PlatformToolsVersion"
}
$FastbootVersionText = (& $Fastboot --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $FastbootVersionText -notmatch [Regex]::Escape($PlatformToolsVersion)) {
    throw "Fastboot version drift: expected Platform-Tools $PlatformToolsVersion"
}

$PwshSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Pwsh).Hash.ToLowerInvariant()
$AdbSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Adb).Hash.ToLowerInvariant()
$FastbootSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Fastboot).Hash.ToLowerInvariant()
$RuntimeManifest = Join-Path $Runtime "bootstrap-runtime.json"

[ordered]@{
    schema_version = 1
    kind = "kaliphonestudio-ac2003-host-bootstrap-runtime"
    created_utc = [DateTime]::UtcNow.ToString("o")
    powershell_version = $PsVersion
    powershell_url = [string]$Lock.powershell.url
    powershell_archive_sha256 = $PowerShellArchiveSha
    powershell_executable_sha256 = $PwshSha
    platform_tools_version = $PlatformToolsVersion
    platform_tools_url = [string]$Lock.platform_tools.url
    platform_tools_archive_sha256 = $PlatformToolsArchiveSha
    adb_executable_sha256 = $AdbSha
    fastboot_executable_sha256 = $FastbootSha
    phone_interaction_performed = $false
    persistent_write_authorized = $false
    phone_storage_written = $false
    hardware_verified = $false
    beta_gate_credit = $false
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $RuntimeManifest

Write-Host ""
Write-Host "KaliPhoneStudio AC2003 HOST BOOTSTRAP: PASS"
Write-Host "PowerShell: $PsVersion"
Write-Host "Platform-Tools: $PlatformToolsVersion"
Write-Host "Runtime manifest: $RuntimeManifest"
Write-Host "Phone interaction performed by bootstrap: false"

if ($DownloadOnly) {
    Write-Host "Download-only mode: PASS"
    exit 0
}

$Wizard = Join-Path $Pack "first-test-wizard.ps1"
Require-Leaf $Wizard "Packaged first-test wizard"
Write-Host ""
Write-Host "Starting guarded read-only AC2003 FIRST TEST wizard..."
& $Pwsh -NoProfile -File $Wizard -CandidateRoot $Root -EvidenceRoot $Evidence -AdbExecutable $Adb -FastbootExecutable $Fastboot
if ($LASTEXITCODE -ne 0) {
    throw "AC2003 FIRST TEST wizard failed: $LASTEXITCODE"
}
exit 0
