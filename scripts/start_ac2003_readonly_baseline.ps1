param(
    [string]$FastbootExecutable,
    [string]$Serial,
    [string]$FirmwareBuild,
    [string]$FirmwareFingerprint,
    [string]$SessionDir,
    [string]$CandidateRoot = ".",
    [string]$AdbExecutable,
    [string]$AndroidIdentityEvidence,
    [switch]$CaptureAndroidIdentityOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-NonEmpty([string]$Value, [string]$Name) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "AC2003 read-only baseline launcher requires $Name"
    }
}

function Invoke-AdbRead([string]$AdbPath, [string[]]$Arguments, [string]$Label) {
    $Output = (& $AdbPath @Arguments 2>&1 | Out-String).Trim()
    $Exit = $LASTEXITCODE
    if ($null -eq $Exit -or $Exit -ne 0) {
        throw "Read-only ADB capture failed for ${Label}: exit=$Exit output=$Output"
    }
    return $Output
}
function Get-ReviewedAdbVersionLine([string]$VersionOutput, [string]$ExpectedVersion) {
    if ([string]::IsNullOrWhiteSpace($VersionOutput)) {
        throw "ADB --version output is empty"
    }
    $VersionLines = @(
        $VersionOutput -split '[\r\n]+' |
            ForEach-Object { $_.Trim() } |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_) -and
                $_.StartsWith("Version ", [StringComparison]::Ordinal)
            }
    )
    if ($VersionLines.Count -ne 1) {
        throw "ADB --version must contain exactly one Version line"
    }
    $VersionLine = [string]$VersionLines[0]
    $Prefix = "Version "
    $VersionToken = $VersionLine.Substring($Prefix.Length)
    $TokenPattern = '^' + [Regex]::Escape($ExpectedVersion) + '(?:[-+][A-Za-z0-9._-]+)?\z'
    if ($VersionToken -notmatch $TokenPattern) {
        throw "ADB version drift: policy requires $ExpectedVersion; Version line: $VersionLine"
    }
    $ObservedBase = ($VersionToken -split '[-+]', 2)[0]
    if ($ObservedBase -ne $ExpectedVersion) {
        throw "ADB version drift: policy requires $ExpectedVersion; observed base version $ObservedBase"
    }
    return $VersionLine
}

$Root = (Resolve-Path $CandidateRoot).Path
$Preflight = Join-Path $Root "operator-pack\host-preflight.ps1"
$PolicyPath = Join-Path $Root "operator-pack\fastboot-tool-policy.json"
$ProfilePath = Join-Path $Root "operator-pack\profile.json"
$Cli = Join-Path $Root "KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe"
foreach ($Path in @($Preflight, $PolicyPath, $ProfilePath, $Cli)) {
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "Required AC2003 baseline-launcher input missing: $Path"
    }
}

$Policy = Get-Content -Raw -Encoding UTF8 $PolicyPath | ConvertFrom-Json
$Profile = Get-Content -Raw -Encoding UTF8 $ProfilePath | ConvertFrom-Json
if ([string]$Profile.profile_id -ne "oneplus/avicii") { throw "Packaged profile identity drift" }
if ([string]$Profile.confirmation_text -ne "AC2003") { throw "Packaged confirmation token drift" }
if ([string]$Policy.tool -ne "fastboot" -or [string]$Policy.version_policy -ne "exact") {
    throw "Packaged Android platform-tools policy drift"
}
$ExpectedPlatformToolsVersion = [string]$Policy.platform_tools_version
if ([string]::IsNullOrWhiteSpace($ExpectedPlatformToolsVersion)) {
    throw "Packaged Android platform-tools policy has no exact version"
}

if ($CaptureAndroidIdentityOnly) {
    Require-NonEmpty $AdbExecutable "AdbExecutable in -CaptureAndroidIdentityOnly mode"
    Require-NonEmpty $AndroidIdentityEvidence "AndroidIdentityEvidence in -CaptureAndroidIdentityOnly mode"

    $EvidencePath = [IO.Path]::GetFullPath($AndroidIdentityEvidence)
    if (Test-Path $EvidencePath) {
        throw "Refusing to overwrite existing stock Android identity evidence: $EvidencePath"
    }
    $EvidenceParent = Split-Path -Parent $EvidencePath
    if ([string]::IsNullOrWhiteSpace($EvidenceParent)) {
        throw "Android identity evidence path must have a parent directory"
    }
    New-Item -ItemType Directory -Path $EvidenceParent -Force | Out-Null

    $AdbPath = (Resolve-Path $AdbExecutable).Path
    if (-not (Test-Path $AdbPath -PathType Leaf)) { throw "ADB executable not found: $AdbPath" }
    $AdbShaBefore = (Get-FileHash -Algorithm SHA256 -Path $AdbPath).Hash.ToLowerInvariant()
    $AdbVersionBefore = Invoke-AdbRead $AdbPath @("--version") "adb --version"
    $AdbVersionLine = Get-ReviewedAdbVersionLine $AdbVersionBefore $ExpectedPlatformToolsVersion

    $AdbSerial = $null
    $AuthorizationDeadline = [DateTime]::UtcNow.AddSeconds(120)
    $LastAdbStateSummary = "none"
    do {
        $Devices = Invoke-AdbRead $AdbPath @("devices", "-l") "adb devices -l"
        $Rows = @(
            $Devices -split "[\r\n]+" |
                ForEach-Object { $_.Trim() } |
                Where-Object {
                    -not [string]::IsNullOrWhiteSpace($_) -and
                    -not $_.StartsWith("List of devices attached", [StringComparison]::OrdinalIgnoreCase)
                }
        )

        $Authorized = @($Rows | Where-Object { $_ -match '^\S+\s+device(?:\s|$)' })
        $Unauthorized = @($Rows | Where-Object { $_ -match '^\S+\s+unauthorized(?:\s|$)' })
        $Offline = @($Rows | Where-Object { $_ -match '^\S+\s+offline(?:\s|$)' })
        $RecognizedRows = @($Authorized + $Unauthorized + $Offline)

        if ($RecognizedRows.Count -gt 1) {
            throw "Stock Android identity capture requires exactly one physical ADB target; detected multiple entries: $($Rows -join ' | ')"
        }
        if ($Authorized.Count -eq 1) {
            $AdbSerial = (($Authorized[0] -split '\s+')[0]).Trim()
            break
        }

        if ($Unauthorized.Count -eq 1) {
            $LastAdbStateSummary = "unauthorized"
            Write-Host "ADB DEVICE FOUND BUT NOT AUTHORIZED."
            Write-Host "Unlock the AC2003 and tap 'Allow USB debugging' / 'Zezwalaj na debugowanie USB'."
            Write-Host "Keep this window open — KaliPhoneStudio will retry automatically."
        }
        elseif ($Offline.Count -eq 1) {
            $LastAdbStateSummary = "offline"
            Write-Host "ADB device is offline. Keep the phone unlocked and reconnect the USB data cable if needed."
            Write-Host "KaliPhoneStudio will retry automatically."
        }
        else {
            $LastAdbStateSummary = "not-detected"
            Write-Host "Waiting for one authorized ADB device..."
            Write-Host "Phone must be booted into OxygenOS, unlocked, USB debugging enabled, and connected with a data-capable USB cable."
        }

        if ([DateTime]::UtcNow -ge $AuthorizationDeadline) {
            throw "Timed out waiting 120 seconds for one authorized ADB device; last state=$LastAdbStateSummary. Enable USB debugging, unlock the phone and accept the RSA authorization prompt, then retry."
        }
        Start-Sleep -Seconds 2
    } while ($true)

    Require-NonEmpty $AdbSerial "authorized ADB serial"
    Write-Host "ADB authorization: PASS ($AdbSerial)"

    $PropertyKeys = @(
        "ro.product.device",
        "ro.product.model",
        "ro.product.board",
        "ro.build.fingerprint",
        "ro.build.version.ota",
        "ro.build.display.id",
        "ro.build.id",
        "ro.build.version.incremental",
        "ro.boot.slot_suffix",
        "ro.boot.bootloader",
        "gsm.version.baseband"
    )
    $Properties = [ordered]@{}
    foreach ($Key in $PropertyKeys) {
        $Value = Invoke-AdbRead $AdbPath @("-s", $AdbSerial, "shell", "getprop", $Key) "getprop $Key"
        $Properties[$Key] = $Value.Trim()
    }

    $Product = [string]$Properties["ro.product.device"]
    $Model = [string]$Properties["ro.product.model"]
    $Board = [string]$Properties["ro.product.board"]
    $Fingerprint = [string]$Properties["ro.build.fingerprint"]
    $BuildCandidates = @(
        [string]$Properties["ro.build.version.ota"],
        [string]$Properties["ro.build.display.id"],
        [string]$Properties["ro.build.id"]
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if ($BuildCandidates.Count -eq 0) { throw "ADB stock identity capture returned no usable firmware build" }
    $CapturedFirmwareBuild = [string]$BuildCandidates[0]
    Require-NonEmpty $Fingerprint "ro.build.fingerprint"

    $StrongProductValues = @($Profile.identity_signals.product.values) | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() }
    $StrongModelValues = @($Profile.identity_signals.model.values) | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() }
    $ProductStrongMatch = $StrongProductValues -contains $Product.Trim().ToLowerInvariant()
    $ModelStrongMatch = $StrongModelValues -contains $Model.Trim().ToLowerInvariant()
    if (-not ($ProductStrongMatch -or $ModelStrongMatch)) {
        throw "ADB stock identity does not match a strong oneplus/avicii product/model signal: product=$Product model=$Model"
    }

    $AdbShaAfter = (Get-FileHash -Algorithm SHA256 -Path $AdbPath).Hash.ToLowerInvariant()
    $AdbVersionAfter = Invoke-AdbRead $AdbPath @("--version") "final adb --version"
    if ($AdbShaAfter -ne $AdbShaBefore) { throw "ADB executable changed during stock identity capture" }
    if ($AdbVersionAfter -ne $AdbVersionBefore) { throw "ADB version output changed during stock identity capture" }

    $Evidence = [ordered]@{
        schema_version = 1
        kind = "kaliphonestudio-readonly-stock-android-identity"
        profile_id = "oneplus/avicii"
        profile_confirmation_text = "AC2003"
        adb_serial = $AdbSerial
        product = $Product
        model = $Model
        board = $Board
        product_strong_match = [bool]$ProductStrongMatch
        model_strong_match = [bool]$ModelStrongMatch
        firmware_build = $CapturedFirmwareBuild
        firmware_fingerprint = $Fingerprint
        build_display_id = [string]$Properties["ro.build.display.id"]
        build_id = [string]$Properties["ro.build.id"]
        build_incremental = [string]$Properties["ro.build.version.incremental"]
        ota_build = [string]$Properties["ro.build.version.ota"]
        slot_suffix = [string]$Properties["ro.boot.slot_suffix"]
        bootloader_version = [string]$Properties["ro.boot.bootloader"]
        baseband_version = [string]$Properties["gsm.version.baseband"]
        platform_tools_version = $ExpectedPlatformToolsVersion
        adb_executable_sha256 = $AdbShaBefore
        adb_version_output = $AdbVersionBefore
        adb_version_line = $AdbVersionLine
        read_only_stock_android_capture = $true
        device_interaction_performed = $true
        adb_reboot_performed = $false
        fastboot_interaction_performed = $false
        temporary_boot_performed = $false
        persistent_write_authorized = $false
        phone_storage_written = $false
        hardware_verified = $false
        beta_release_authorized = $false
        beta_gate_credit = $false
    }
    $Evidence | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -NoNewline $EvidencePath
    $EvidenceSha = (Get-FileHash -Algorithm SHA256 -Path $EvidencePath).Hash.ToLowerInvariant()

    Write-Host "KaliPhoneStudio AC2003 stock Android identity capture: PASS"
    Write-Host "Evidence: $EvidencePath"
    Write-Host "Evidence SHA-256: $EvidenceSha"
    Write-Host "ADB serial: $AdbSerial"
    Write-Host "Product/model: $Product / $Model"
    Write-Host "Firmware build: $CapturedFirmwareBuild"
    Write-Host "Firmware fingerprint: $Fingerprint"
    Write-Host "Read-only Android property capture: true"
    Write-Host "ADB reboot performed: false"
    Write-Host "Persistent phone write authorized: false"
    Write-Host "Hardware verified: false"
    Write-Host "Beta gate credit: false"
    Write-Host "Next: manually put the phone in Fastboot, then rerun readonly-baseline.ps1 with -AndroidIdentityEvidence."
    exit 0
}

Require-NonEmpty $FastbootExecutable "FastbootExecutable"
Require-NonEmpty $Serial "Serial"
Require-NonEmpty $SessionDir "SessionDir"

$Identity = $null
$IdentityEvidenceSha = $null
if (-not [string]::IsNullOrWhiteSpace($AndroidIdentityEvidence)) {
    $IdentityPath = (Resolve-Path $AndroidIdentityEvidence).Path
    $Identity = Get-Content -Raw -Encoding UTF8 $IdentityPath | ConvertFrom-Json
    if ([int]$Identity.schema_version -ne 1) { throw "Unexpected stock Android identity evidence schema" }
    if ([string]$Identity.kind -ne "kaliphonestudio-readonly-stock-android-identity") { throw "Unexpected stock Android identity evidence kind" }
    if ([string]$Identity.profile_id -ne "oneplus/avicii") { throw "Stock Android identity profile drift" }
    if ($Identity.read_only_stock_android_capture -ne $true) { throw "Stock Android identity is not marked read-only" }
    if ($Identity.device_interaction_performed -ne $true) { throw "Stock Android identity did not capture a physical device" }
    if ($Identity.adb_reboot_performed -ne $false) { throw "Stock Android identity unexpectedly claims adb reboot" }
    foreach ($Field in @("temporary_boot_performed", "persistent_write_authorized", "phone_storage_written", "hardware_verified", "beta_release_authorized", "beta_gate_credit")) {
        if ($Identity.$Field -ne $false) { throw "Unsafe stock Android identity field: $Field" }
    }
    if (-not ($Identity.product_strong_match -eq $true -or $Identity.model_strong_match -eq $true)) {
        throw "Stock Android identity evidence has no strong profile match"
    }
    $EvidenceBuild = [string]$Identity.firmware_build
    $EvidenceFingerprint = [string]$Identity.firmware_fingerprint
    Require-NonEmpty $EvidenceBuild "firmware_build in AndroidIdentityEvidence"
    Require-NonEmpty $EvidenceFingerprint "firmware_fingerprint in AndroidIdentityEvidence"
    if (-not [string]::IsNullOrWhiteSpace($FirmwareBuild) -and $FirmwareBuild -ne $EvidenceBuild) {
        throw "Explicit firmware build conflicts with Android identity evidence"
    }
    if (-not [string]::IsNullOrWhiteSpace($FirmwareFingerprint) -and $FirmwareFingerprint -ne $EvidenceFingerprint) {
        throw "Explicit firmware fingerprint conflicts with Android identity evidence"
    }
    $FirmwareBuild = $EvidenceBuild
    $FirmwareFingerprint = $EvidenceFingerprint
    $IdentityEvidenceSha = (Get-FileHash -Algorithm SHA256 -Path $IdentityPath).Hash.ToLowerInvariant()
}
else {
    Require-NonEmpty $FirmwareBuild "FirmwareBuild when AndroidIdentityEvidence is not supplied"
    Require-NonEmpty $FirmwareFingerprint "FirmwareFingerprint when AndroidIdentityEvidence is not supplied"
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

if ($null -ne $Identity) {
    $BoundIdentityPath = Join-Path $SessionPath "stock-android-identity.json"
    if (Test-Path $BoundIdentityPath) { throw "Refusing to overwrite bound stock Android identity evidence" }
    Copy-Item -LiteralPath $IdentityPath -Destination $BoundIdentityPath
    $BoundSha = (Get-FileHash -Algorithm SHA256 -Path $BoundIdentityPath).Hash.ToLowerInvariant()
    if ($BoundSha -ne $IdentityEvidenceSha) { throw "Stock Android identity evidence drifted while binding session" }

    $LinkPath = Join-Path $SessionPath "stock-android-identity-link.json"
    [ordered]@{
        schema_version = 1
        kind = "kaliphonestudio-stock-android-identity-link"
        profile_id = "oneplus/avicii"
        fastboot_device_serial = $Serial
        adb_device_serial = [string]$Identity.adb_serial
        firmware_build = $FirmwareBuild
        firmware_fingerprint = $FirmwareFingerprint
        stock_android_identity_sha256 = $BoundSha
        physical_first_test_session_sha256 = (Get-FileHash -Algorithm SHA256 -Path $ManifestPath).Hash.ToLowerInvariant()
        read_only_identity_bound = $true
        persistent_write_authorized = $false
        hardware_verified = $false
        beta_gate_credit = $false
    } | ConvertTo-Json | Set-Content -Encoding UTF8 -NoNewline $LinkPath
}

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
if ($null -ne $Identity) {
    Write-Host "Stock Android identity evidence SHA-256: $IdentityEvidenceSha"
    Write-Host "Firmware build/fingerprint source: read-only ADB evidence"
}
else {
    Write-Host "Firmware build/fingerprint source: explicit operator input"
}
Write-Host "Physical interaction performed: true (read-only Fastboot baseline only)"
Write-Host "Temporary boot performed: false"
Write-Host "Persistent phone write authorized: false"
Write-Host "Hardware verified: false"
Write-Host "Beta gate credit: false"
Write-Host "Next: obtain the exact matching OxygenOS OTA, then follow AC2003_FIRST_TEST.md section 4."
exit 0