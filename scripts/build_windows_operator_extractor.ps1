param(
    [string]$OutputDir = "dist/operator-tools"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$LockPath = Join-Path $RepoRoot "tools/extractor-locks.json"
$RuntimeStager = Join-Path $RepoRoot "scripts/stage_windows_extractor_runtime.ps1"
if (-not (Test-Path $LockPath -PathType Leaf)) {
    throw "Extractor lock file is missing: $LockPath"
}
if (-not (Test-Path $RuntimeStager -PathType Leaf)) {
    throw "Extractor runtime stager is missing: $RuntimeStager"
}

$Lock = Get-Content -Raw -Encoding UTF8 $LockPath | ConvertFrom-Json
if ($Lock.extractor -ne "payload-dumper-go") {
    throw "Unexpected extractor in lock: $($Lock.extractor)"
}
if (-not $Lock.source.url -or -not $Lock.source.commit) {
    throw "Extractor source URL/commit is missing from lock"
}
if ($Lock.build.toolchain -ne "go" -or -not $Lock.build.toolchain_version) {
    throw "Extractor Go toolchain lock is missing"
}
if (-not $Lock.artifacts.'windows-amd64'.sha256) {
    throw "Windows extractor SHA-256 lock is missing"
}
$NativeLock = $Lock.build.native_dependencies.'windows-amd64'
if (-not $NativeLock -or -not $NativeLock.packages) {
    throw "Windows native dependency lock is missing"
}
$WindowsBuild = $Lock.build.platform_overrides.'windows-amd64'
if (-not $WindowsBuild -or $WindowsBuild.linkage -ne "mixed-side-by-side") {
    throw "Windows extractor must use the reviewed side-by-side runtime closure"
}
if ($WindowsBuild.runtime_dependency_policy -ne "recursive-non-system-pe-import-closure") {
    throw "Unexpected Windows runtime dependency policy: $($WindowsBuild.runtime_dependency_policy)"
}
$WindowsLdFlags = [string]$WindowsBuild.ldflags
if ($WindowsLdFlags -ne "-buildid= -extldflags=-static") {
    throw "Unexpected Windows extractor ldflags: $WindowsLdFlags"
}

$ExpectedCommit = [string]$Lock.source.commit
$ExpectedGo = [string]$Lock.build.toolchain_version
$ExpectedSha256 = ([string]$Lock.artifacts.'windows-amd64'.sha256).ToLowerInvariant()
$SourceUrl = [string]$Lock.source.url

$GoVersionOutput = (& go version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Go toolchain is unavailable"
}
if ($GoVersionOutput -notmatch "\bgo$([regex]::Escape($ExpectedGo))\b") {
    throw "Go toolchain drift: expected $ExpectedGo, got: $GoVersionOutput"
}
if ($env:CGO_ENABLED -ne "1") {
    throw "Reviewed Windows extractor build requires CGO_ENABLED=1"
}
if (-not $env:CC) {
    throw "Reviewed Windows extractor build requires an explicit MinGW CC"
}

$Pacman = "C:\msys64\usr\bin\pacman.exe"
if (-not (Test-Path $Pacman -PathType Leaf)) {
    throw "MSYS2 pacman is unavailable for native dependency verification"
}
$VerifiedNativePackages = [ordered]@{}
foreach ($Package in $NativeLock.packages.PSObject.Properties) {
    $PackageName = [string]$Package.Name
    $ExpectedVersion = [string]$Package.Value
    $ActualPackage = (& $Pacman -Q $PackageName 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Required native package is unavailable: $PackageName"
    }
    $ExpectedPackage = "$PackageName $ExpectedVersion"
    if ($ActualPackage -ne $ExpectedPackage) {
        throw "Native package drift: expected '$ExpectedPackage', got '$ActualPackage'"
    }
    $VerifiedNativePackages[$PackageName] = $ExpectedVersion
}

$Destination = if ([IO.Path]::IsPathRooted($OutputDir)) {
    [IO.Path]::GetFullPath($OutputDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))
}
if (Test-Path $Destination) {
    throw "Refusing to overwrite existing operator-tools directory: $Destination"
}

$ScratchParent = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$Scratch = Join-Path $ScratchParent ("kps-payload-dumper-go-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Scratch | Out-Null
$Pushed = $false

try {
    Push-Location $Scratch
    $Pushed = $true
    & git init --quiet
    if ($LASTEXITCODE -ne 0) { throw "git init failed" }
    & git remote add origin $SourceUrl
    if ($LASTEXITCODE -ne 0) { throw "git remote add failed" }
    & git fetch --quiet --depth 1 origin $ExpectedCommit
    if ($LASTEXITCODE -ne 0) { throw "cannot fetch exact extractor source commit $ExpectedCommit" }
    & git checkout --quiet --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "cannot checkout exact extractor source commit" }

    $ActualCommit = (& git rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
    if ($ActualCommit -ne $ExpectedCommit.ToLowerInvariant()) {
        throw "Extractor source commit drift: expected $ExpectedCommit, got $ActualCommit"
    }

    $GoRequirementLine = Get-Content -Encoding UTF8 (Join-Path $Scratch "go.mod") |
        Where-Object { $_ -match '^go\s+[^\s]+$' } |
        Select-Object -First 1
    if (-not $GoRequirementLine) {
        throw "Pinned extractor go.mod has no Go version"
    }
    $GoRequirementParts = $GoRequirementLine -split '\s+', 2
    if ($GoRequirementParts.Count -ne 2) {
        throw "Pinned extractor go.mod Go version is malformed"
    }
    $ActualGoRequirement = $GoRequirementParts[1]
    if ($ActualGoRequirement -ne $ExpectedGo) {
        throw "Extractor go.mod/toolchain drift: expected $ExpectedGo, got $ActualGoRequirement"
    }

    $LicenseSource = Join-Path $Scratch "LICENSE"
    if (-not (Test-Path $LicenseSource -PathType Leaf)) {
        throw "Pinned extractor source does not contain LICENSE"
    }

    $BuiltExe = Join-Path $Scratch "payload-dumper-go.exe"
    & go build -trimpath -buildvcs=false "-ldflags=$WindowsLdFlags" -o $BuiltExe .
    if ($LASTEXITCODE -ne 0) {
        throw "Exact payload-dumper-go Windows build failed"
    }
    if (-not (Test-Path $BuiltExe -PathType Leaf)) {
        throw "Expected extractor executable was not produced"
    }

    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -Path $BuiltExe).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Extractor SHA-256 mismatch: expected $ExpectedSha256, got $ActualSha256"
    }

    # The pinned Windows build is byte-reproducible but still imports a small
    # MinGW runtime set. Resolve that closure recursively from the exact locked
    # MSYS2 package set and prove it starts with MSYS2 removed from PATH.
    & $RuntimeStager -Executable $BuiltExe -OutputDir $Destination
    if ($LASTEXITCODE -ne 0) {
        throw "Windows extractor runtime staging failed: $LASTEXITCODE"
    }

    $RuntimeManifestPath = Join-Path $Destination "operator-extractor-runtime.json"
    if (-not (Test-Path $RuntimeManifestPath -PathType Leaf)) {
        throw "Runtime closure manifest was not produced"
    }
    $RuntimeManifest = Get-Content -Raw -Encoding UTF8 $RuntimeManifestPath | ConvertFrom-Json
    if ($RuntimeManifest.executable_sha256 -ne $ExpectedSha256) {
        throw "Runtime closure executable hash drift"
    }
    if ($RuntimeManifest.all_non_system_imports_resolved -ne $true) {
        throw "Runtime closure is incomplete"
    }
    $RuntimeManifestSha256 = (Get-FileHash -Algorithm SHA256 -Path $RuntimeManifestPath).Hash.ToLowerInvariant()

    $LicenseDestination = Join-Path $Destination "payload-dumper-go-LICENSE.txt"
    Copy-Item -LiteralPath $LicenseSource -Destination $LicenseDestination
    $LicenseSha256 = (Get-FileHash -Algorithm SHA256 -Path $LicenseDestination).Hash.ToLowerInvariant()

    $NoticeSource = Join-Path $Scratch "NOTICE"
    $NoticeSha256 = $null
    if (Test-Path $NoticeSource -PathType Leaf) {
        $NoticeDestination = Join-Path $Destination "payload-dumper-go-NOTICE.txt"
        Copy-Item -LiteralPath $NoticeSource -Destination $NoticeDestination
        $NoticeSha256 = (Get-FileHash -Algorithm SHA256 -Path $NoticeDestination).Hash.ToLowerInvariant()
    }

    [ordered]@{
        schema_version = 2
        kind = "kaliphonestudio-windows-operator-extractor"
        platform = "windows-amd64"
        extractor = "payload-dumper-go"
        source_url = $SourceUrl
        source_commit = $ExpectedCommit
        go_toolchain_version = $ExpectedGo
        native_distribution = [string]$NativeLock.distribution
        native_package_versions = $VerifiedNativePackages
        cgo_enabled = $true
        linkage = [string]$WindowsBuild.linkage
        ldflags = $WindowsLdFlags
        runtime_dependency_policy = [string]$WindowsBuild.runtime_dependency_policy
        build_flags = @("-trimpath", "-buildvcs=false", "-ldflags=$WindowsLdFlags")
        executable = "payload-dumper-go.exe"
        executable_sha256 = $ActualSha256
        expected_sha256 = $ExpectedSha256
        runtime_manifest = "operator-extractor-runtime.json"
        runtime_manifest_sha256 = $RuntimeManifestSha256
        runtime_dependency_count = [int]$RuntimeManifest.runtime_dependency_count
        runtime_dependencies_resolved = $true
        clean_path_smoke_passed = $true
        license_file = "payload-dumper-go-LICENSE.txt"
        license_sha256 = $LicenseSha256
        notice_sha256 = $NoticeSha256
        source_lock_verified = $true
        native_dependencies_verified = $true
        executable_hash_verified = $true
        physical_interaction_performed = $false
        external_device_command_executed = $false
        persistent_write_authorized = $false
        phone_storage_written = $false
        hardware_verified = $false
        beta_release_authorized = $false
        beta_gate_credit = $false
    } | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $Destination "operator-extractor-manifest.json")
}
finally {
    if ($Pushed) {
        Pop-Location
    }
    if (Test-Path $Scratch) {
        Remove-Item -LiteralPath $Scratch -Recurse -Force
    }
}

Write-Host "Windows operator extractor bundle built from exact source/native dependency/runtime-closure lock."
Write-Host "payload-dumper-go.exe SHA-256: $ExpectedSha256"
Write-Host "No phone/device command was executed."
