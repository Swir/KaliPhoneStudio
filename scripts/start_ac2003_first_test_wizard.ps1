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

$CurrentPwsh = Join-Path $PSHOME "pwsh.exe"
if (-not (Test-Path -LiteralPath $CurrentPwsh -PathType Leaf)) {
    throw "Current PowerShell host executable missing from PSHOME: $CurrentPwsh"
}
$CurrentPwshVersion = (& $CurrentPwsh -NoProfile -NonInteractive -Command '$PSVersionTable.PSVersion.ToString()' 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($CurrentPwshVersion)) {
    throw "Current PSHOME PowerShell host self-check failed"
}

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

function Save-WindowsFastbootUsbDiagnostic(
    [string]$FastbootPath,
    [string]$EvidenceRootPath,
    [string]$SessionLabel
) {
    $DiagnosticPath = Join-Path $EvidenceRootPath "fastboot-windows-usb-diagnostic-$SessionLabel.json"
    if (Test-Path $DiagnosticPath) {
        throw "Refusing to overwrite existing Windows Fastboot diagnostic: $DiagnosticPath"
    }

    $FastbootOutput = (& $FastbootPath "devices" 2>&1 | Out-String).Trim()
    $FastbootExit = $LASTEXITCODE
    $PnpError = $null
    $DriverError = $null
    $Candidates = @()
    $Drivers = @()

    try {
        $Candidates = @(
            Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
                Where-Object {
                    ([string]$_.PNPDeviceID).StartsWith("USB\", [StringComparison]::OrdinalIgnoreCase) -or
                    ([string]$_.Name -match '(?i)android|oneplus|fastboot|bootloader|adb')
                } |
                Select-Object Name, Manufacturer, Status, PNPDeviceID, Service, ConfigManagerErrorCode, ClassGuid
        )
    }
    catch {
        $PnpError = $_.Exception.Message
    }

    try {
        $Drivers = @(
            Get-CimInstance Win32_PnPSignedDriver -ErrorAction Stop |
                Where-Object {
                    ([string]$_.DeviceID).StartsWith("USB\", [StringComparison]::OrdinalIgnoreCase) -or
                    ([string]$_.DeviceName -match '(?i)android|oneplus|fastboot|bootloader|adb')
                } |
                Select-Object DeviceName, DeviceID, DriverProviderName, DriverVersion, InfName
        )
    }
    catch {
        $DriverError = $_.Exception.Message
    }

    $ProblemCandidates = @(
        $Candidates | Where-Object {
            $_.ConfigManagerErrorCode -ne $null -and [int]$_.ConfigManagerErrorCode -ne 0
        }
    )
    $LikelyFastbootCandidates = @(
        $Candidates | Where-Object {
            ([string]$_.Name -match '(?i)android|oneplus|fastboot|bootloader') -or
            ([string]$_.Manufacturer -match '(?i)oneplus|google|android')
        }
    )

    $Diagnosis = "fastboot-interface-not-exposed"
    if (@($ProblemCandidates | Where-Object { [int]$_.ConfigManagerErrorCode -eq 28 }).Count -gt 0) {
        $Diagnosis = "windows-driver-not-installed"
    }
    elseif (@($ProblemCandidates).Count -gt 0) {
        $Diagnosis = "windows-pnp-device-problem"
    }
    elseif (@($LikelyFastbootCandidates).Count -gt 0) {
        $Diagnosis = "usb-device-present-but-fastboot-not-bound"
    }
    elseif (@($Candidates).Count -eq 0) {
        $Diagnosis = "no-usb-pnp-device-seen"
    }

    [ordered]@{
        schema_version = 1
        kind = "kaliphonestudio-windows-fastboot-usb-diagnostic"
        profile_id = "oneplus/avicii"
        diagnosis = $Diagnosis
        fastboot_devices_exit_code = $FastbootExit
        fastboot_devices_output = $FastbootOutput
        pnp_query_error = $PnpError
        signed_driver_query_error = $DriverError
        pnp_candidates = $Candidates
        signed_drivers = $Drivers
        host_only_diagnostic = $true
        phone_write_performed = $false
        flash_erase_slot_change_performed = $false
        hardware_verified = $false
        beta_gate_credit = $false
    } | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -NoNewline $DiagnosticPath

    Write-Host ""
    Write-Host "WINDOWS FASTBOOT USB DIAGNOSTIC"
    Write-Host "  Diagnosis: $Diagnosis"
    Write-Host "  Report: $DiagnosticPath"
    if (@($LikelyFastbootCandidates).Count -gt 0) {
        Write-Host "  Matching Windows PnP candidates:"
        foreach ($Device in $LikelyFastbootCandidates) {
            Write-Host "    $([string]$Device.Name) | status=$([string]$Device.Status) | error=$([string]$Device.ConfigManagerErrorCode) | service=$([string]$Device.Service)"
        }
    }
    else {
        Write-Host "  No Android/OnePlus/Fastboot-named Windows PnP candidate was found."
    }
    Write-Host "  No driver was installed or changed by KaliPhoneStudio."
    Write-Host ""
    return $DiagnosticPath
}

function Wait-ForSingleFastbootDevice([string]$FastbootPath, [int]$TimeoutSeconds = 60) {
    $Deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $Devices = Invoke-ReadOnlyTool $FastbootPath @("devices") "fastboot devices"
        $Lines = @(
            $Devices -split "[\r\n]+" |
                ForEach-Object { $_.Trim() } |
                Where-Object { $_ -match '^\S+\s+fastboot(?:\s|$)' }
        )
        if ($Lines.Count -gt 1) {
            throw "First-test wizard requires exactly one Fastboot device; got $($Lines.Count)"
        }
        if ($Lines.Count -eq 1) {
            $Serial = (($Lines[0] -split '\s+')[0]).Trim()
            if ([string]::IsNullOrWhiteSpace($Serial)) {
                throw "Fastboot device discovery returned an empty serial"
            }
            return $Serial
        }
        if ([DateTime]::UtcNow -ge $Deadline) {
            $DiagnosticPath = Save-WindowsFastbootUsbDiagnostic $FastbootPath $script:EvidenceRootPathForFastbootDiagnostic $script:SessionLabelForFastbootDiagnostic
            throw "Timed out waiting $TimeoutSeconds seconds for exactly one Fastboot device. Windows Fastboot diagnostic: $DiagnosticPath"
        }
        Start-Sleep -Seconds 2
    } while ($true)
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
& $CurrentPwsh -NoProfile -File $Preflight -CandidateRoot $Root -FastbootExecutable $FastbootPath
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
$script:EvidenceRootPathForFastbootDiagnostic = $EvidenceRootPath
$script:SessionLabelForFastbootDiagnostic = $SessionLabel
foreach ($Path in @($IdentityPath, $SessionPath)) {
    if (Test-Path $Path) {
        throw "Refusing to reuse existing first-test evidence path: $Path"
    }
}

Write-Host "KaliPhoneStudio AC2003 FIRST TEST — phase 1/2: stock OxygenOS read-only identity"
Write-Host "No reboot/boot/flash/erase/slot-change/storage-write command is issued by this wizard."
& $CurrentPwsh -NoProfile -File $BaselineLauncher `
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

$TransitionMethod = "already-fastboot"
$AdbBootloaderRebootPerformed = $false

if (-not $FastbootAlreadyReady) {
    Write-Host "FASTBOOT MODE TRANSITION"
    Write-Host "Choose how to move the SAME AC2003 into Fastboot/bootloader:"
    Write-Host "  [M] Manual phone controls (default)"
    Write-Host "  [A] Explicitly confirmed: adb reboot bootloader"
    $TransitionChoice = (Read-Host "Choose M or A").Trim().ToUpperInvariant()
    if ([string]::IsNullOrWhiteSpace($TransitionChoice)) { $TransitionChoice = "M" }

    if ($TransitionChoice -eq "A") {
        $Confirm = Read-Host "Type exactly REBOOT-BOOTLOADER AC2003 to authorize this one reboot"
        if ($Confirm -ne "REBOOT-BOOTLOADER AC2003") {
            throw "ADB bootloader reboot was not explicitly confirmed"
        }

        $AdbShaBeforeReboot = (Get-FileHash -Algorithm SHA256 -Path $AdbPath).Hash.ToLowerInvariant()
        $FastbootShaBeforeReboot = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath).Hash.ToLowerInvariant()
        if ($AdbShaBeforeReboot -ne $AdbShaAtStart -or $FastbootShaBeforeReboot -ne $FastbootShaAtStart) {
            throw "Android Platform-Tools executable changed before requested ADB bootloader reboot"
        }

        $AdbSerialForReboot = [string]$Identity.adb_serial
        if ([string]::IsNullOrWhiteSpace($AdbSerialForReboot)) {
            throw "Captured Android identity has no ADB serial for bootloader reboot binding"
        }
        $AdbState = Invoke-ReadOnlyTool $AdbPath @("-s", $AdbSerialForReboot, "get-state") "adb get-state before bootloader reboot"
        if ($AdbState.Trim() -ne "device") {
            throw "ADB target is not in authorized device state before bootloader reboot: $AdbState"
        }

        Write-Host "Explicit operator authorization accepted."
        Write-Host "Executing exactly: adb -s <captured-serial> reboot bootloader"
        & $AdbPath "-s" $AdbSerialForReboot "reboot" "bootloader"
        $RebootExit = $LASTEXITCODE
        if ($null -eq $RebootExit -or $RebootExit -ne 0) {
            throw "Explicit ADB reboot bootloader failed: exit=$RebootExit"
        }
        $AdbBootloaderRebootPerformed = $true
        $TransitionMethod = "explicit-adb-reboot-bootloader"
    }
    elseif ($TransitionChoice -eq "M") {
        $TransitionMethod = "manual-phone-controls"
        Write-Host "Put the same AC2003 into Fastboot/bootloader using the phone controls."
        [void](Read-Host "When the phone is visibly in Fastboot/bootloader, press ENTER")
    }
    else {
        throw "Unsupported Fastboot transition choice: $TransitionChoice"
    }
}

# Fail closed if either executable changed while the operator moved the same phone
# from stock OxygenOS into the bootloader.
$AdbShaBeforeFastboot = (Get-FileHash -Algorithm SHA256 -Path $AdbPath).Hash.ToLowerInvariant()
$FastbootShaBeforeFastboot = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath).Hash.ToLowerInvariant()
if ($AdbShaBeforeFastboot -ne $AdbShaAtStart -or $FastbootShaBeforeFastboot -ne $FastbootShaAtStart) {
    throw "Android Platform-Tools executable changed between wizard phases"
}

Write-Host "KaliPhoneStudio AC2003 FIRST TEST — phase 2/2: read-only Fastboot baseline"
& $CurrentPwsh -NoProfile -File $Preflight -CandidateRoot $Root -FastbootExecutable $FastbootPath
if ($LASTEXITCODE -ne 0) {
    throw "Host/Fastboot preflight failed before device discovery: $LASTEXITCODE"
}

$FastbootSerial = Wait-ForSingleFastbootDevice $FastbootPath 60

$TransitionPath = Join-Path $EvidenceRootPath "ac2003-mode-transition-$SessionLabel.json"
if (Test-Path $TransitionPath) {
    throw "Refusing to overwrite existing mode-transition evidence: $TransitionPath"
}
[ordered]@{
    schema_version = 1
    kind = "kaliphonestudio-ac2003-mode-transition"
    profile_id = "oneplus/avicii"
    adb_serial = [string]$Identity.adb_serial
    fastboot_serial = $FastbootSerial
    transition_method = $TransitionMethod
    adb_reboot_bootloader_performed = [bool]$AdbBootloaderRebootPerformed
    adb_executable_sha256 = $AdbShaAtStart
    fastboot_executable_sha256 = $FastbootShaAtStart
    persistent_write_authorized = $false
    phone_storage_written = $false
    hardware_verified = $false
    beta_gate_credit = $false
} | ConvertTo-Json | Set-Content -Encoding UTF8 -NoNewline $TransitionPath
$TransitionSha = (Get-FileHash -Algorithm SHA256 -Path $TransitionPath).Hash.ToLowerInvariant()

& $CurrentPwsh -NoProfile -File $BaselineLauncher `
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

$BoundTransitionPath = Join-Path $SessionPath "mode-transition.json"
if (Test-Path $BoundTransitionPath) {
    throw "Refusing to overwrite bound mode-transition evidence"
}
Copy-Item -LiteralPath $TransitionPath -Destination $BoundTransitionPath
$BoundTransitionSha = (Get-FileHash -Algorithm SHA256 -Path $BoundTransitionPath).Hash.ToLowerInvariant()
if ($BoundTransitionSha -ne $TransitionSha) {
    throw "Mode-transition evidence drifted while binding physical session"
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
if ($null -eq $CapturedFastbootSha) {
    throw "Captured Fastboot tool evidence is missing executable SHA-256"
}
if ($CapturedFastbootSha -notmatch '^[0-9a-f]{64}$') {
    throw "Captured Fastboot tool evidence contains an invalid executable SHA-256"
}
if ($CapturedFastbootSha -ne $FastbootShaAtStart) {
    throw "Captured Fastboot evidence is not bound to the wizard-start Fastboot executable"
}

Write-Host ""
Write-Host "KaliPhoneStudio AC2003 FIRST TEST READ-ONLY BASELINE: PASS"
Write-Host "Identity evidence: $IdentityPath"
Write-Host "Physical session: $SessionPath"
Write-Host "Fastboot serial: $FastbootSerial"
Write-Host "Mode transition: $TransitionMethod"
Write-Host "ADB reboot bootloader performed: $AdbBootloaderRebootPerformed"
Write-Host "Mode-transition evidence SHA-256: $TransitionSha"
Write-Host "Shared Platform-Tools directory: $AdbDirectory"
Write-Host "ADB SHA-256: $AdbShaAtStart"
Write-Host "Fastboot SHA-256: $FastbootShaAtStart"
Write-Host "Persistent phone write authorized: false"
Write-Host "Temporary boot performed: false"
Write-Host "Hardware verified: false"
Write-Host "Beta gate credit: false"
Write-Host "Next: obtain the exact matching OxygenOS OTA and continue operator-pack\AC2003_FIRST_TEST.md at the stock boot.img provenance step."
