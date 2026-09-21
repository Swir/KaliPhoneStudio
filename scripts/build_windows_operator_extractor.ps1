param(
    [string]$OutputDir = "dist/operator-tools"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$LockPath = Join-Path $RepoRoot "tools/extractor-locks.json"
if (-not (Test-Path $LockPath -PathType Leaf)) {
    throw "Extractor lock file is missing: $LockPath"
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

$Destination = if ([IO.Path]::IsPathRooted($OutputDir)) {
    [IO.Path]::GetFullPath($OutputDir)
} else {
    [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))
}
if (Test-Path $Destination) {
    throw "Refusing to overwrite existing operator-tools directory: $Destination"
}
New-Item -ItemType Directory -Path $Destination | Out-Null

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

    $GoMod = Get-Content -Raw -Encoding UTF8 (Join-Path $Scratch "go.mod")
    $GoRequirement = [regex]::Match($GoMod, '(?m)^go\s+([^\s]+)$'.Replace('\\', '\'))
    if (-not $GoRequirement.Success) {
        throw "Pinned extractor go.mod has no Go version"
    }
    if ($GoRequirement.Groups[1].Value -ne $ExpectedGo) {
        throw "Extractor go.mod/toolchain drift: expected $ExpectedGo, got $($GoRequirement.Groups[1].Value)"
    }

    $LicenseSource = Join-Path $Scratch "LICENSE"
    if (-not (Test-Path $LicenseSource -PathType Leaf)) {
        throw "Pinned extractor source does not contain LICENSE"
    }

    $Exe = Join-Path $Destination "payload-dumper-go.exe"
    & go build -trimpath -buildvcs=false '-ldflags=-buildid=' -o $Exe .
    if ($LASTEXITCODE -ne 0) {
        throw "Exact payload-dumper-go build failed"
    }
    if (-not (Test-Path $Exe -PathType Leaf)) {
        throw "Expected extractor executable was not produced"
    }

    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -Path $Exe).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        throw "Extractor SHA-256 mismatch: expected $ExpectedSha256, got $ActualSha256"
    }

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
        schema_version = 1
        kind = "kaliphonestudio-windows-operator-extractor"
        platform = "windows-amd64"
        extractor = "payload-dumper-go"
        source_url = $SourceUrl
        source_commit = $ExpectedCommit
        go_toolchain_version = $ExpectedGo
        cgo_enabled = $true
        build_flags = @("-trimpath", "-buildvcs=false", "-ldflags=-buildid=")
        executable = "payload-dumper-go.exe"
        executable_sha256 = $ActualSha256
        expected_sha256 = $ExpectedSha256
        license_file = "payload-dumper-go-LICENSE.txt"
        license_sha256 = $LicenseSha256
        notice_sha256 = $NoticeSha256
        source_lock_verified = $true
        executable_hash_verified = $true
        physical_interaction_performed = $false
        external_device_command_executed = $false
        persistent_write_authorized = $false
        phone_storage_written = $false
        hardware_verified = $false
        beta_release_authorized = $false
        beta_gate_credit = $false
    } | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Destination "operator-extractor-manifest.json")
}
finally {
    if ($Pushed) {
        Pop-Location
    }
    if (Test-Path $Scratch) {
        Remove-Item -LiteralPath $Scratch -Recurse -Force
    }
}

Write-Host "Windows operator extractor built from exact source lock."
Write-Host "payload-dumper-go.exe SHA-256: $ExpectedSha256"
Write-Host "No phone/device command was executed."
