param(
    [string]$DistRoot = "dist"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Root = (Resolve-Path $DistRoot).Path
$GuiRoot = Join-Path $Root "KaliPhoneStudio"
$CliRoot = Join-Path $Root "KaliPhoneStudioCLI"
$ToolsRoot = Join-Path $Root "operator-tools"
$OperatorPack = Join-Path $Root "operator-pack"
$InfoPath = Join-Path $Root "BETA_TEST_CANDIDATE_INFO.json"
$ManifestPath = Join-Path $Root "BETA_TEST_CANDIDATE_SHA256.txt"
$ZipPath = Join-Path $Root "KaliPhoneStudio-AC2003-beta-test-candidate.zip"
$ZipShaPath = "$ZipPath.sha256"
$WizardSource = Join-Path $RepoRoot "scripts\start_ac2003_first_test_wizard.ps1"
$WizardTarget = Join-Path $OperatorPack "first-test-wizard.ps1"
$BootstrapSource = Join-Path $RepoRoot "scripts\bootstrap_ac2003_first_test.ps1"
$BootstrapTarget = Join-Path $OperatorPack "bootstrap-first-test.ps1"
$BootstrapCmdSource = Join-Path $RepoRoot "scripts\start_ac2003_first_test.cmd"
$BootstrapCmdTarget = Join-Path $OperatorPack "START_FIRST_TEST.cmd"
$BootstrapLockSource = Join-Path $RepoRoot "tools\ac2003-bootstrap-lock.json"
$BootstrapLockTarget = Join-Path $OperatorPack "bootstrap-lock.json"
$StartHerePath = Join-Path $OperatorPack "START_HERE.txt"
$VerifierPath = Join-Path $OperatorPack "verify-candidate.ps1"

foreach ($Path in @($GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack)) {
    if (-not (Test-Path $Path -PathType Container)) { throw "Candidate component missing before wizard overlay: $Path" }
}
foreach ($Path in @($InfoPath, $ManifestPath, $ZipPath, $ZipShaPath, $WizardSource, $BootstrapSource, $BootstrapCmdSource, $BootstrapLockSource, $StartHerePath, $VerifierPath)) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Wizard overlay input missing: $Path" }
}
foreach ($Target in @($WizardTarget, $BootstrapTarget, $BootstrapCmdTarget, $BootstrapLockTarget)) {
    if (Test-Path $Target) { throw "Refusing to overwrite packaged first-test bootstrap/wizard file: $Target" }
}

Copy-Item -LiteralPath $WizardSource -Destination $WizardTarget
Copy-Item -LiteralPath $BootstrapSource -Destination $BootstrapTarget
Copy-Item -LiteralPath $BootstrapCmdSource -Destination $BootstrapCmdTarget
Copy-Item -LiteralPath $BootstrapLockSource -Destination $BootstrapLockTarget

$OldStartHere = Get-Content -Raw -Encoding UTF8 $StartHerePath
$WizardIntro = @"
KaliPhoneStudio AC2003 ONE-COMMAND READ-ONLY FIRST TEST
======================================================

Preferred first physical baseline path:

1. Keep the phone booted in stock OxygenOS and explicitly authorize USB debugging.
2. Run ONE launcher from the extracted candidate:
   .\operator-pack\START_FIRST_TEST.cmd

The launcher first uses built-in Windows PowerShell only as a downloader/bootstrapper.
It downloads the exact pinned portable PowerShell and Android Platform-Tools archives,
verifies their repository-locked SHA-256 values BEFORE extraction, verifies the exact
runtime/tool versions, writes operator-runtime\bootstrap-runtime.json, and only then
starts the guarded read-only first-test wizard with the downloaded adb.exe/fastboot.exe.

To download/verify/extract the host prerequisites without touching the phone, run:
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\operator-pack\bootstrap-first-test.ps1 -CandidateRoot . -DownloadOnly

The bootstrap itself performs no phone I/O. The wizard captures the exact stock OxygenOS
build/fingerprint read-only, pauses for a MANUAL phone-button transition into
Fastboot/bootloader, discovers exactly one Fastboot serial, then binds the same identity
into the guarded version/devices/getvar-only baseline. It never issues adb reboot,
fastboot reboot/boot/flash/erase/set_active/flashing commands, never mounts phone storage
and never grants hardware/Beta credit.

The exact OxygenOS OTA is intentionally NOT guessed or downloaded before the real phone
identity is captured. After PASS, continue with .\operator-pack\AC2003_FIRST_TEST.md at
the matching OTA -> payload.bin -> stock boot.img provenance step.

------------------------------------------------------------------------
Legacy/manual operator reference follows below.
------------------------------------------------------------------------

"@
$WizardIntro + $OldStartHere | Set-Content -Encoding UTF8 $StartHerePath

$Info = Get-Content -Raw -Encoding UTF8 $InfoPath | ConvertFrom-Json
if ($Info.schema_version -ne 1 -or $Info.kind -ne "kaliphonestudio-unsigned-ac2003-beta-test-candidate") {
    throw "Unexpected candidate metadata before first-test wizard overlay"
}
$Info | Add-Member -NotePropertyName first_test_wizard_included -NotePropertyValue $true -Force
$Info | Add-Member -NotePropertyName automatic_host_bootstrap_included -NotePropertyValue $true -Force
$Info | Add-Member -NotePropertyName automatic_host_bootstrap_pinned_sha256 -NotePropertyValue $true -Force
$Info | Add-Member -NotePropertyName automatic_host_bootstrap_phone_interaction -NotePropertyValue $false -Force
$Info | Add-Member -NotePropertyName automatic_ota_download_before_identity -NotePropertyValue $false -Force
$Info | Add-Member -NotePropertyName first_test_wizard_manual_fastboot_transition_required -NotePropertyValue $true -Force
$Info | Add-Member -NotePropertyName first_test_wizard_automatic_reboot -NotePropertyValue $false -Force
$Info | Add-Member -NotePropertyName first_test_wizard_temporary_boot_performed -NotePropertyValue $false -Force
$Info | Add-Member -NotePropertyName first_test_wizard_persistent_write_authorized -NotePropertyValue $false -Force
$Info | Add-Member -NotePropertyName first_test_wizard_beta_gate_credit -NotePropertyValue $false -Force
$Info | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $InfoPath

Remove-Item -LiteralPath $ManifestPath -Force
Remove-Item -LiteralPath $ZipPath -Force
Remove-Item -LiteralPath $ZipShaPath -Force

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

& pwsh -NoProfile -File $VerifierPath -CandidateRoot $Root
if ($LASTEXITCODE -ne 0) { throw "Candidate verifier failed after first-test wizard overlay: $LASTEXITCODE" }

$UpdatedInfo = Get-Content -Raw -Encoding UTF8 $InfoPath | ConvertFrom-Json
if ($UpdatedInfo.first_test_wizard_included -ne $true) { throw "First-test wizard metadata missing" }
if ($UpdatedInfo.automatic_host_bootstrap_included -ne $true) { throw "Automatic host bootstrap metadata missing" }
if ($UpdatedInfo.automatic_host_bootstrap_pinned_sha256 -ne $true) { throw "Automatic host bootstrap lost pinned SHA-256 marker" }
if ($UpdatedInfo.automatic_host_bootstrap_phone_interaction -ne $false) { throw "Automatic host bootstrap unexpectedly claims phone interaction" }
if ($UpdatedInfo.automatic_ota_download_before_identity -ne $false) { throw "Candidate unexpectedly permits OTA download before physical identity" }
if ($UpdatedInfo.first_test_wizard_manual_fastboot_transition_required -ne $true) { throw "Wizard lost manual Fastboot transition gate" }
foreach ($Field in @("first_test_wizard_automatic_reboot", "first_test_wizard_temporary_boot_performed", "first_test_wizard_persistent_write_authorized", "first_test_wizard_beta_gate_credit")) {
    if ($UpdatedInfo.$Field -ne $false) { throw "Unsafe first-test wizard metadata field: $Field" }
}
foreach ($Path in @($WizardTarget, $BootstrapTarget, $BootstrapCmdTarget, $BootstrapLockTarget)) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Packaged first-test bootstrap/wizard file disappeared before ZIP creation: $Path" }
}

$BootstrapLock = Get-Content -Raw -Encoding UTF8 $BootstrapLockTarget | ConvertFrom-Json
if ([int]$BootstrapLock.schema_version -ne 1 -or [string]$BootstrapLock.kind -ne "kaliphonestudio-ac2003-host-bootstrap-lock") {
    throw "Packaged bootstrap lock schema/kind drift"
}
if ([string]$BootstrapLock.platform_tools.version -ne "37.0.1") {
    throw "Packaged Platform-Tools bootstrap version drift"
}
foreach ($Digest in @([string]$BootstrapLock.powershell.sha256, [string]$BootstrapLock.platform_tools.sha256)) {
    if ($Digest -notmatch '^[0-9a-fA-F]{64}$') { throw "Packaged bootstrap lock SHA-256 is invalid" }
}

$BootstrapText = (Get-Content -Raw -Encoding UTF8 $BootstrapTarget).ToLowerInvariant()
if (-not $BootstrapText.Contains('get-filehash -algorithm sha256')) { throw "Packaged bootstrap lost SHA-256 verification" }
if (-not $BootstrapText.Contains('invoke-webrequest')) { throw "Packaged bootstrap lost automatic download path" }

$WizardText = (Get-Content -Raw -Encoding UTF8 $WizardTarget).ToLowerInvariant()
if (-not $WizardText.Contains('invoke-readonlytool $fastbootpath @("devices")')) {
    throw "Packaged first-test wizard lost the expected read-only Fastboot devices invocation"
}
# Reject executable argv-shaped state-changing verbs while allowing safety prose that
# names those verbs to tell the operator what the wizard deliberately does not do.
foreach ($ForbiddenArgv in @('@("reboot")', '@("boot")', '@("flash")', '@("erase")', '@("set_active")', '@("flashing")')) {
    if ($WizardText.Contains($ForbiddenArgv)) {
        throw "Packaged first-test wizard contains forbidden state-changing argv: $ForbiddenArgv"
    }
}

Compress-Archive -Path $GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack, $ManifestPath, $InfoPath -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
"$ZipHash  KaliPhoneStudio-AC2003-beta-test-candidate.zip" | Set-Content -Encoding ASCII $ZipShaPath

Write-Host "KaliPhoneStudio AC2003 one-command read-only first-test candidate overlay: PASS"
Write-Host "Wizard packaged: operator-pack/first-test-wizard.ps1"
Write-Host "Automatic host bootstrap: operator-pack/START_FIRST_TEST.cmd"
Write-Host "Pinned PowerShell + Platform-Tools download/checksum verification: true"
Write-Host "Manual Fastboot transition required: true"
Write-Host "Automatic reboot: false"
Write-Host "Temporary boot performed: false"
Write-Host "Persistent phone write authorized: false"
Write-Host "Beta gate credit: false"
