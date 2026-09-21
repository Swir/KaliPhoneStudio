param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$MingwBin = "C:\msys64\mingw64\bin",
    [string]$SystemDir = "$env:SystemRoot\System32"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExeSource = (Resolve-Path $Executable).Path
$Objdump = Join-Path $MingwBin "objdump.exe"
if (-not (Test-Path $Objdump -PathType Leaf)) {
    throw "MinGW objdump is unavailable: $Objdump"
}
if (-not (Test-Path $SystemDir -PathType Container)) {
    throw "Windows system directory is unavailable: $SystemDir"
}

$Destination = if ([IO.Path]::IsPathRooted($OutputDir)) {
    [IO.Path]::GetFullPath($OutputDir)
} else {
    [IO.Path]::GetFullPath((Join-Path (Get-Location).Path $OutputDir))
}
if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination | Out-Null
}
elseif (-not (Test-Path $Destination -PathType Container)) {
    throw "Runtime output is not a directory: $Destination"
}

$BundledExe = Join-Path $Destination "payload-dumper-go.exe"
if ([IO.Path]::GetFullPath($ExeSource) -ne [IO.Path]::GetFullPath($BundledExe)) {
    if (Test-Path $BundledExe) {
        throw "Refusing to overwrite runtime executable: $BundledExe"
    }
    Copy-Item -LiteralPath $ExeSource -Destination $BundledExe
}

function Get-PeImports {
    param([Parameter(Mandatory = $true)][string]$Path)

    $Output = (& $Objdump -p $Path 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "objdump failed for $Path with exit code $LASTEXITCODE"
    }
    $Imports = [regex]::Matches($Output, '(?im)^\s*DLL Name:\s*(\S+)\s*$') |
        ForEach-Object { $_.Groups[1].Value } |
        Sort-Object -Unique
    return @($Imports)
}

function Test-SystemImport {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($Name -match '^(?i:api-ms-win-|ext-ms-win-)') {
        return $true
    }
    return Test-Path (Join-Path $SystemDir $Name) -PathType Leaf
}

$Queue = [System.Collections.Generic.Queue[string]]::new()
$Queue.Enqueue($BundledExe)
$VisitedFiles = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$BundledDependencies = [ordered]@{}
$SystemImports = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

while ($Queue.Count -gt 0) {
    $Current = $Queue.Dequeue()
    $CurrentFull = [IO.Path]::GetFullPath($Current)
    if (-not $VisitedFiles.Add($CurrentFull)) {
        continue
    }

    foreach ($Dll in (Get-PeImports -Path $CurrentFull)) {
        if (Test-SystemImport -Name $Dll) {
            $null = $SystemImports.Add($Dll)
            continue
        }

        if ($BundledDependencies.Contains($Dll)) {
            continue
        }

        $Source = Join-Path $MingwBin $Dll
        if (-not (Test-Path $Source -PathType Leaf)) {
            throw "Unresolved non-system PE dependency '$Dll' imported by '$CurrentFull'"
        }
        $Target = Join-Path $Destination $Dll
        if (Test-Path $Target) {
            throw "Refusing to overwrite runtime dependency: $Target"
        }
        Copy-Item -LiteralPath $Source -Destination $Target
        $SourceHash = (Get-FileHash -Algorithm SHA256 -Path $Source).Hash.ToLowerInvariant()
        $TargetHash = (Get-FileHash -Algorithm SHA256 -Path $Target).Hash.ToLowerInvariant()
        if ($SourceHash -ne $TargetHash) {
            throw "Runtime dependency copy hash mismatch for $Dll"
        }
        $BundledDependencies[$Dll] = [ordered]@{
            sha256 = $TargetHash
            size = (Get-Item -LiteralPath $Target).Length
        }
        $Queue.Enqueue($Target)
    }
}

$RuntimeEntries = @()
foreach ($Name in ($BundledDependencies.Keys | Sort-Object)) {
    $Entry = $BundledDependencies[$Name]
    $RuntimeEntries += [ordered]@{
        name = $Name
        sha256 = $Entry.sha256
        size = $Entry.size
    }
}

$RuntimeManifest = [ordered]@{
    schema_version = 1
    kind = "kaliphonestudio-windows-extractor-runtime-closure"
    executable = "payload-dumper-go.exe"
    executable_sha256 = (Get-FileHash -Algorithm SHA256 -Path $BundledExe).Hash.ToLowerInvariant()
    dependency_policy = "recursive-non-system-pe-import-closure"
    runtime_dependencies = $RuntimeEntries
    runtime_dependency_count = $RuntimeEntries.Count
    system_imports = @($SystemImports | Sort-Object)
    all_non_system_imports_resolved = $true
}
$RuntimeManifestPath = Join-Path $Destination "operator-extractor-runtime.json"
$RuntimeManifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $RuntimeManifestPath

$SavedPath = $env:PATH
$HelpPath = Join-Path $Destination "payload-dumper-go-help.txt"
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Push-Location $Destination
    try {
        & ".\payload-dumper-go.exe" -h *> $HelpPath
        $ExitCode = $LASTEXITCODE
    }
    catch {
        $Message = $_ | Out-String
        if ($Message) {
            $Message | Set-Content -Encoding UTF8 $HelpPath
        }
        throw "Bundled extractor failed to start on a clean Windows PATH: $($_.Exception.Message)"
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:PATH = $SavedPath
}
if ($null -eq $ExitCode -or $ExitCode -ne 0) {
    $Diagnostic = if (Test-Path $HelpPath) { Get-Content -Raw -Encoding UTF8 $HelpPath } else { "<no output>" }
    throw "Bundled extractor failed on a clean Windows PATH: exit=$ExitCode output=$Diagnostic"
}

Write-Host "Windows extractor runtime closure staged successfully."
Write-Host "Bundled non-system runtime dependencies: $($RuntimeEntries.Count)"
Write-Host "Runtime manifest: $RuntimeManifestPath"
