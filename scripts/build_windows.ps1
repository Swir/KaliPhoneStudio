param(
    [string]$Python = "python",
    [string]$DistPath = "dist"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$RequiredInputs = @(
    "main.py",
    "BUILD_STATUS.json",
    "BETA_RELEASE_GATE.md",
    "devices",
    "assets",
    "tools"
)
foreach ($item in $RequiredInputs) {
    if (-not (Test-Path (Join-Path $RepoRoot $item))) {
        throw "Required packaging input is missing: $item"
    }
}

$BuildRoot = Join-Path $RepoRoot "build\pyinstaller"
$SpecRoot = Join-Path $BuildRoot "spec"
New-Item -ItemType Directory -Force -Path $BuildRoot, $SpecRoot | Out-Null

# PyInstaller resolves --add-data sources relative to the generated .spec file,
# so use absolute source paths while keeping stable relative destinations.
$DevicesPath = Join-Path $RepoRoot "devices"
$AssetsPath = Join-Path $RepoRoot "assets"
$ToolsPath = Join-Path $RepoRoot "tools"
$BuildStatusPath = Join-Path $RepoRoot "BUILD_STATUS.json"
$BetaGatePath = Join-Path $RepoRoot "BETA_RELEASE_GATE.md"

$CommonArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onedir",
    "--noupx",
    "--paths", $RepoRoot,
    "--distpath", (Join-Path $RepoRoot $DistPath),
    "--specpath", $SpecRoot,
    "--add-data", "${DevicesPath};devices",
    "--add-data", "${AssetsPath};assets",
    "--add-data", "${ToolsPath};tools",
    "--add-data", "${BuildStatusPath};.",
    "--add-data", "${BetaGatePath};.",
    "--hidden-import", "PySide6.QtSvg"
)

function Invoke-KpsBuild {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][bool]$Windowed
    )

    $WorkPath = Join-Path $BuildRoot $Name
    $Args = @($CommonArgs)
    $Args += @("--workpath", $WorkPath, "--name", $Name)
    if ($Windowed) {
        $Args += "--windowed"
    }
    else {
        $Args += "--console"
    }
    $Args += "main.py"

    Write-Host "Building $Name (windowed=$Windowed, onedir=true)..."
    & $Python @Args
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed for $Name with exit code $LASTEXITCODE"
    }

    $Exe = Join-Path $RepoRoot "$DistPath\$Name\$Name.exe"
    if (-not (Test-Path $Exe -PathType Leaf)) {
        throw "Expected executable was not produced: $Exe"
    }
    return $Exe
}

# Two front ends intentionally share the same source and bundled policy/profile data:
# - GUI: clean double-click experience, no console window.
# - CLI: console-enabled so machine-readable doctor/recovery/export output is visible.
$GuiExe = Invoke-KpsBuild -Name "KaliPhoneStudio" -Windowed $true
$CliExe = Invoke-KpsBuild -Name "KaliPhoneStudioCLI" -Windowed $false

Write-Host "Windows host builds completed."
Write-Host "GUI: $GuiExe"
Write-Host "CLI: $CliExe"
Write-Host "These are unsigned development host artifacts, not KaliPhoneStudio Beta releases."
