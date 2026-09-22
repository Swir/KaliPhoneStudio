param(
    [string]$CandidateRoot = "dist",
    [string]$ProfileId = "oneplus/avicii"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Root = (Resolve-Path $CandidateRoot).Path
$Cli = (Resolve-Path (Join-Path $Root "KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe")).Path
$Gui = (Resolve-Path (Join-Path $Root "KaliPhoneStudio\KaliPhoneStudio.exe")).Path
$ExtractorRoot = (Resolve-Path (Join-Path $Root "operator-tools")).Path
$Extractor = (Resolve-Path (Join-Path $ExtractorRoot "payload-dumper-go.exe")).Path
$ExtractorManifestPath = Join-Path $ExtractorRoot "operator-extractor-manifest.json"
$RuntimeManifestPath = Join-Path $ExtractorRoot "operator-extractor-runtime.json"
$LockPath = Join-Path $RepoRoot "tools\extractor-locks.json"

foreach ($Path in @($Cli, $Gui, $Extractor, $ExtractorManifestPath, $RuntimeManifestPath, $LockPath)) {
    if (-not (Test-Path $Path -PathType Leaf)) { throw "Required frozen-candidate input missing: $Path" }
}

$Lock = Get-Content -Raw -Encoding UTF8 $LockPath | ConvertFrom-Json
$ExtractorManifest = Get-Content -Raw -Encoding UTF8 $ExtractorManifestPath | ConvertFrom-Json
$RuntimeManifest = Get-Content -Raw -Encoding UTF8 $RuntimeManifestPath | ConvertFrom-Json
$ExpectedExtractorSha = ([string]$Lock.artifacts.'windows-amd64'.sha256).ToLowerInvariant()
$ActualExtractorSha = (Get-FileHash -Algorithm SHA256 -Path $Extractor).Hash.ToLowerInvariant()
if ($ActualExtractorSha -ne $ExpectedExtractorSha) { throw "Bundled extractor SHA-256 drift" }
if ($ExtractorManifest.executable_sha256 -ne $ExpectedExtractorSha) { throw "Extractor manifest SHA-256 drift" }
if ($ExtractorManifest.runtime_dependencies_resolved -ne $true) { throw "Extractor runtime dependency closure not verified" }
if ($ExtractorManifest.clean_path_smoke_passed -ne $true) { throw "Extractor build did not record clean-PATH smoke" }
if ($RuntimeManifest.all_non_system_imports_resolved -ne $true) { throw "Extractor runtime manifest is incomplete" }
if ($RuntimeManifest.executable_sha256 -ne $ExpectedExtractorSha) { throw "Runtime manifest executable digest drift" }
foreach ($Dependency in @($RuntimeManifest.runtime_dependencies)) {
    $DependencyPath = Join-Path $ExtractorRoot ([string]$Dependency.name)
    if (-not (Test-Path $DependencyPath -PathType Leaf)) { throw "Bundled extractor dependency missing: $DependencyPath" }
    $Digest = (Get-FileHash -Algorithm SHA256 -Path $DependencyPath).Hash.ToLowerInvariant()
    if ($Digest -ne ([string]$Dependency.sha256).ToLowerInvariant()) { throw "Bundled extractor dependency hash drift: $DependencyPath" }
}
foreach ($Field in @("physical_interaction_performed", "external_device_command_executed", "persistent_write_authorized", "phone_storage_written", "hardware_verified", "beta_release_authorized", "beta_gate_credit")) {
    if ($ExtractorManifest.$Field -ne $false) { throw "Unsafe extractor manifest field: $Field" }
}

$SavedPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Push-Location $ExtractorRoot
    try {
        & ".\payload-dumper-go.exe" -h *> (Join-Path $Root "payload-dumper-go-help.txt")
        $ExtractorExit = $LASTEXITCODE
    }
    finally { Pop-Location }
}
finally { $env:PATH = $SavedPath }
if ($null -eq $ExtractorExit -or $ExtractorExit -ne 0) { throw "Bundled extractor failed clean-PATH smoke: exit=$ExtractorExit" }

& $Cli --list-profiles --json | Set-Content -Encoding utf8 (Join-Path $Root "profiles.json")
if ($LASTEXITCODE -ne 0) { throw "Frozen profile listing failed: $LASTEXITCODE" }
& $Cli --doctor --profile-id $ProfileId --json | Set-Content -Encoding utf8 (Join-Path $Root "doctor.json")
if ($LASTEXITCODE -ne 0) { throw "Frozen doctor failed: $LASTEXITCODE" }
& $Cli --recovery-guide --profile-id $ProfileId --json | Set-Content -Encoding utf8 (Join-Path $Root "recovery.json")
if ($LASTEXITCODE -ne 0) { throw "Frozen recovery guide failed: $LASTEXITCODE" }

foreach ($Command in @(
    "begin-physical-test-session",
    "capture-fastboot-baseline",
    "extract-stock-boot-from-ota",
    "bind-physical-stock-baseline",
    "bind-physical-candidate-gate",
    "bind-physical-boot-identity",
    "build-physical-recovery-readiness",
    "prepare-physical-candidate-offline",
    "prepare-temporary-boot-offer",
    "execute-temporary-boot-once",
    "phosh"
)) {
    & $Cli $Command --help | Set-Content -Encoding utf8 (Join-Path $Root ("help-" + $Command + ".txt"))
    if ($LASTEXITCODE -ne 0) { throw "Frozen help failed for $Command : $LASTEXITCODE" }
}
foreach ($Command in @("build-first-boot-binding", "build-successor-candidate", "bind-physical-candidate")) {
    & $Cli phosh $Command --help | Set-Content -Encoding utf8 (Join-Path $Root ("help-phosh-" + $Command + ".txt"))
    if ($LASTEXITCODE -ne 0) { throw "Frozen Phosh help failed for $Command : $LASTEXITCODE" }
}
foreach ($Command in @("build-beta-artifact-inventory", "build-beta-review-manifest")) {
    & $Cli evidence $Command --help | Set-Content -Encoding utf8 (Join-Path $Root ("help-evidence-" + $Command + ".txt"))
    if ($LASTEXITCODE -ne 0) { throw "Frozen evidence help failed for $Command : $LASTEXITCODE" }
}

$RefusedSession = Join-Path $Root "should-not-session"
& $Cli begin-physical-test-session --profile-id $ProfileId --serial NEVER-CONNECTED --firmware-build TEST --firmware-fingerprint TEST --confirm-token WRONG --session-dir $RefusedSession 2> (Join-Path $Root "refusal-session.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen first-test session did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedSession) { throw "Refused first-test session created output" }

$RefusedCapture = Join-Path $Root "should-not-capture"
& $Cli capture-fastboot-baseline --profile-id $ProfileId --serial NEVER-CONNECTED --firmware-build TEST --firmware-fingerprint TEST --output-dir $RefusedCapture 2> (Join-Path $Root "refusal-capture.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen capture did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedCapture) { throw "Refused capture created output" }

$RefusedStock = Join-Path $Root "should-not-stock"
& $Cli extract-stock-boot-from-ota --profile-id $ProfileId --ota (Join-Path $Root "missing-ota.zip") --extractor $Extractor --extractor-platform windows-amd64 --out-dir $RefusedStock 2> (Join-Path $Root "refusal-stock.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen stock extraction did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedStock) { throw "Refused stock extraction created output" }

$RefusedBootIdentity = Join-Path $Root "should-not-boot-identity.json"
& $Cli bind-physical-boot-identity --profile-id $ProfileId --physical-baseline (Join-Path $Root "missing-physical.json") --physical-candidate-gate (Join-Path $Root "missing-gate.json") --stock-provenance (Join-Path $Root "missing-provenance.json") --boot-plan (Join-Path $Root "missing-plan.json") --stock-boot (Join-Path $Root "missing-stock-boot.img") --candidate-boot (Join-Path $Root "missing-candidate-boot.img") --candidate-dtbo (Join-Path $Root "missing-candidate-dtbo.img") --out $RefusedBootIdentity 2> (Join-Path $Root "refusal-boot-identity.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen boot-identity command did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedBootIdentity) { throw "Refused boot-identity command created output" }

$RefusedRecovery = Join-Path $Root "should-not-recovery-readiness.json"
& $Cli build-physical-recovery-readiness --profile-id $ProfileId --baseline-evidence (Join-Path $Root "missing-baseline.json") --physical-baseline (Join-Path $Root "missing-physical.json") --boot-identity-binding (Join-Path $Root "missing-binding.json") --stock-boot (Join-Path $Root "missing-stock-boot.img") --out $RefusedRecovery 2> (Join-Path $Root "refusal-recovery-readiness.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen recovery-readiness command did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedRecovery) { throw "Refused recovery command created output" }

$RefusedPhosh = Join-Path $Root "should-not-phosh-adapter.json"
& $Cli phosh bind-physical-candidate --phosh-successor-candidate (Join-Path $Root "missing-phosh-successor.json") --physical-candidate-gate (Join-Path $Root "missing-gate.json") --out $RefusedPhosh 2> (Join-Path $Root "refusal-phosh-adapter.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen Phosh physical adapter did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedPhosh) { throw "Refused Phosh adapter created output" }

$RefusedProbe = Join-Path $Root "should-not-probe.json"
$RefusedExecution = Join-Path $Root "should-not-execute.json"
& $Cli execute-temporary-boot-once --profile-id $ProfileId --physical-candidate-gate (Join-Path $Root "missing-gate.json") --boot-identity-binding (Join-Path $Root "missing-binding.json") --physical-baseline (Join-Path $Root "missing-physical.json") --recovery-readiness (Join-Path $Root "missing-recovery.json") --stock-boot (Join-Path $Root "missing-stock-boot.img") --capture-bundle (Join-Path $Root "missing-capture.json") --baseline-evidence (Join-Path $Root "missing-baseline.json") --fastboot-tool-evidence (Join-Path $Root "missing-tool.json") --fastboot-executable (Join-Path $Root "missing-fastboot.exe") --boot-image (Join-Path $Root "missing-candidate-boot.img") --confirmation AC2003 --probe-out $RefusedProbe --execution-out $RefusedExecution 2> (Join-Path $Root "refusal-execution.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen temporary boot did not fail closed without opt-in: $LASTEXITCODE" }
if (Test-Path $RefusedProbe) { throw "Refused temporary boot created probe evidence" }
if (Test-Path $RefusedExecution) { throw "Refused temporary boot created execution evidence" }

$RefusedInventory = Join-Path $Root "should-not-inventory.json"
& $Cli evidence build-beta-artifact-inventory --candidate-gate (Join-Path $Root "missing-candidate.json") --release-gate-audit (Join-Path $Root "missing-release-audit.json") --strategy-review (Join-Path $Root "missing-strategy.json") --source-commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --artifact ("candidate_boot=" + (Join-Path $Root "missing-boot.img")) --out $RefusedInventory 2> (Join-Path $Root "refusal-inventory.txt")
if ($LASTEXITCODE -ne 2) { throw "Frozen Beta inventory did not fail closed: $LASTEXITCODE" }
if (Test-Path $RefusedInventory) { throw "Refused Beta inventory created output" }

$Profiles = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "profiles.json") | ConvertFrom-Json
if (-not ($Profiles | Where-Object { $_.profile_id -eq $ProfileId })) { throw "Frozen profile registry omitted $ProfileId" }
$Doctor = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "doctor.json") | ConvertFrom-Json
if ($Doctor.selected_profile_id -ne $ProfileId -or $Doctor.physical_interaction_performed -ne $false -or $Doctor.hardware_verified -ne $false -or $Doctor.beta_gate_credit -ne $false) { throw "Frozen doctor safety contract drift" }
$Recovery = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "recovery.json") | ConvertFrom-Json
if ($Recovery.persistent_write_authorized -ne $false -or $Recovery.hardware_verified -ne $false -or $Recovery.beta_gate_credit -ne $false) { throw "Frozen recovery safety contract drift" }

$GuiProcess = Start-Process -FilePath $Gui -ArgumentList "--version" -Wait -PassThru
if ($GuiProcess.ExitCode -ne 0) { throw "Frozen GUI bootstrap/version path failed: $($GuiProcess.ExitCode)" }

$global:LASTEXITCODE = 0
Write-Host "KaliPhoneStudio frozen Windows Beta-test-candidate smoke: PASS"
Write-Host "Bundled payload-dumper-go.exe SHA-256: $ExpectedExtractorSha"
Write-Host "Frozen reviewed Phosh handoff CLI: PASS"
Write-Host "Physical interaction performed: false"
exit 0