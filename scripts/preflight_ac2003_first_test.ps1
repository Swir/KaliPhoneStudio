param(
    [Parameter(Mandatory = $true)]
    [string]$FastbootExecutable,
    [string]$CandidateRoot = "."
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

$Root = (Resolve-Path $CandidateRoot).Path
$Verifier = Join-Path $Root "operator-pack\verify-candidate.ps1"
$PolicyPath = Join-Path $Root "operator-pack\fastboot-tool-policy.json"
$Cli = Join-Path $Root "KaliPhoneStudioCLI\KaliPhoneStudioCLI.exe"
$Extractor = Join-Path $Root "operator-tools\payload-dumper-go.exe"

foreach ($Path in @($Verifier, $PolicyPath, $Cli, $Extractor)) {
    if (-not (Test-Path $Path -PathType Leaf)) {
        throw "Required AC2003 host preflight input missing: $Path"
    }
}

& $CurrentPwsh -NoProfile -File $Verifier -CandidateRoot $Root
if ($LASTEXITCODE -ne 0) {
    throw "Integrated candidate integrity verification failed: $LASTEXITCODE"
}

$FastbootPath = (Resolve-Path $FastbootExecutable).Path
if (-not (Test-Path $FastbootPath -PathType Leaf)) {
    throw "Reviewed fastboot executable not found: $FastbootPath"
}

$Policy = Get-Content -Raw -Encoding UTF8 $PolicyPath | ConvertFrom-Json
if ([string]$Policy.tool -ne "fastboot") { throw "Fastboot policy tool drift" }
if ([string]$Policy.version_policy -ne "exact") { throw "Fastboot policy must remain exact" }
if ($Policy.hardware_verified -ne $false -or $Policy.beta_gate_credit -ne $false) {
    throw "Fastboot policy contains unsafe hardware/Beta claims"
}
$ExpectedVersion = [string]$Policy.platform_tools_version
if ([string]::IsNullOrWhiteSpace($ExpectedVersion)) { throw "Fastboot policy has no exact version" }

$FastbootSha256 = (Get-FileHash -Algorithm SHA256 -Path $FastbootPath).Hash.ToLowerInvariant()
$VersionText = (& $FastbootPath --version 2>&1 | Out-String).Trim()
$FastbootExit = $LASTEXITCODE
if ($null -eq $FastbootExit -or $FastbootExit -ne 0) {
    throw "Reviewed fastboot --version failed: exit=$FastbootExit"
}
$VersionPattern = "(?im)fastboot(?:\.exe)?\s+version\s+" + [Regex]::Escape($ExpectedVersion) + "(?:[-+][^\s]+)?"
if ($VersionText -notmatch $VersionPattern) {
    throw "Fastboot version drift: policy requires $ExpectedVersion; reported: $VersionText"
}

$CliSha256 = (Get-FileHash -Algorithm SHA256 -Path $Cli).Hash.ToLowerInvariant()
$ExtractorSha256 = (Get-FileHash -Algorithm SHA256 -Path $Extractor).Hash.ToLowerInvariant()

Write-Host "KaliPhoneStudio AC2003 host preflight: PASS"
Write-Host "Candidate integrity: PASS"
Write-Host "Fastboot exact policy version: $ExpectedVersion"
Write-Host "Fastboot SHA-256: $FastbootSha256"
Write-Host "Frozen CLI SHA-256: $CliSha256"
Write-Host "Bundled OTA extractor SHA-256: $ExtractorSha256"
Write-Host "Device command executed: false (fastboot --version only)"
Write-Host "Persistent phone write authorized: false"
Write-Host "Hardware verified: false"
Write-Host "Beta gate credit: false"
Write-Host "Next: follow operator-pack\AC2003_FIRST_TEST.md from the read-only baseline step."
exit 0
