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
$StartHerePath = Join-Path $OperatorPack "START_HERE.txt"
$VerifierPath = Join-Path $OperatorPack "verify-candidate.ps1"

foreach ($Path in @($GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack)) {
    if (-not (Test-Path $Path -PathType Container)) { throw "Candidate component missing before wizard overlay: $Path" }
}
foreach ($Path in @($InfoPath, $ManifestPath, $ZipPath, $ZipShaPath, $WizardSource, $StartHerePath, $VerifierPath)) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Wizard overlay input missing: $Path" }
}
if (Test-Path $WizardTarget) { throw "Refusing to overwrite packaged first-test wizard: $WizardTarget" }

Copy-Item -LiteralPath $WizardSource -Destination $WizardTarget

$OldStartHere = Get-Content -Raw -Encoding UTF8 $StartHerePath
$WizardIntro = @"
KaliPhoneStudio AC2003 ONE-COMMAND READ-ONLY FIRST TEST
======================================================

Preferred first physical baseline path:

1. Keep the phone booted in stock OxygenOS and explicitly authorize USB debugging.
2. Point to ADB and Fastboot from the SAME reviewed Android Platform-Tools version:
   `$Adb = (Resolve-Path "<PATH_TO_REVIEWED_ADB_EXE>").Path
   `$Fastboot = (Resolve-Path "<PATH_TO_REVIEWED_FASTBOOT_EXE>").Path
3. Run the single guided command:
   pwsh -NoProfile -File .\operator-pack\first-test-wizard.ps1 -CandidateRoot . -AdbExecutable "`$Adb" -FastbootExecutable "`$Fastboot"

The wizard captures the exact stock OxygenOS build/fingerprint read-only, pauses for a
MANUAL phone-button transition into Fastboot/bootloader, discovers exactly one Fastboot
serial, then binds the same identity into the guarded version/devices/getvar-only baseline.
It never issues adb reboot, fastboot reboot/boot/flash/erase/set_active/flashing commands,
never mounts phone storage and never grants hardware/Beta credit.

After PASS, continue with .\operator-pack\AC2003_FIRST_TEST.md at the exact matching
OxygenOS OTA -> payload.bin -> stock boot.img provenance step.

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
if ($UpdatedInfo.first_test_wizard_manual_fastboot_transition_required -ne $true) { throw "Wizard lost manual Fastboot transition gate" }
foreach ($Field in @("first_test_wizard_automatic_reboot", "first_test_wizard_temporary_boot_performed", "first_test_wizard_persistent_write_authorized", "first_test_wizard_beta_gate_credit")) {
    if ($UpdatedInfo.$Field -ne $false) { throw "Unsafe first-test wizard metadata field: $Field" }
}
if (-not (Test-Path $WizardTarget -PathType Leaf)) { throw "Packaged first-test wizard disappeared before ZIP creation" }
$WizardText = Get-Content -Raw -Encoding UTF8 $WizardTarget
foreach ($Forbidden in @("adb reboot ", "fastboot reboot ", "fastboot boot ", "fastboot flash ", "fastboot erase ", "fastboot set_active ", "fastboot flashing ")) {
    if ($WizardText.ToLowerInvariant().Contains($Forbidden)) {
        throw "Packaged first-test wizard contains forbidden command-shaped text: $Forbidden"
    }
}

Compress-Archive -Path $GuiRoot, $CliRoot, $ToolsRoot, $OperatorPack, $ManifestPath, $InfoPath -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
"$ZipHash  KaliPhoneStudio-AC2003-beta-test-candidate.zip" | Set-Content -Encoding ASCII $ZipShaPath

Write-Host "KaliPhoneStudio AC2003 one-command read-only first-test candidate overlay: PASS"
Write-Host "Wizard packaged: operator-pack/first-test-wizard.ps1"
Write-Host "Manual Fastboot transition required: true"
Write-Host "Automatic reboot: false"
Write-Host "Temporary boot performed: false"
Write-Host "Persistent phone write authorized: false"
Write-Host "Beta gate credit: false"
