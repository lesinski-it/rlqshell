<#
.SYNOPSIS
    Downloads FreeRDP for Windows and stages it for the MSI build.

.DESCRIPTION
    Pulls the freerdp.portable package from the Chocolatey community
    repository (a .nupkg is just a ZIP), extracts the wfreerdp.exe and
    its dependent DLLs, and copies them into installer/freerdp/. The
    MSI build picks the directory up via the FreeRDPDir variable.

    Idempotent -- does nothing if installer/freerdp/wfreerdp.exe is
    already present, unless -Force is passed.

.PARAMETER Version
    freerdp.portable version on Chocolatey. Default: 3.25.1.
    Version 3.25.1 is required for /floatbar support in wfreerdp.exe.
    Version 3.21.0 does not show the floatbar in fullscreen sessions.

.PARAMETER Force
    Re-download even if files are already present.

.EXAMPLE
    pwsh installer/fetch-freerdp.ps1
    pwsh installer/fetch-freerdp.ps1 -Force
    pwsh installer/fetch-freerdp.ps1 -Version 3.25.1
#>
[CmdletBinding()]
param(
    [string]$Version = '3.25.1',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$TargetDir = Join-Path $ScriptDir 'freerdp'
$Marker    = Join-Path $TargetDir 'wfreerdp.exe'

if ((Test-Path $Marker) -and -not $Force) {
    Write-Host "==> FreeRDP already staged at $TargetDir" -ForegroundColor Green
    Write-Host "    Pass -Force to re-download."
    return
}

if (Test-Path $TargetDir) {
    Write-Host "==> Cleaning existing $TargetDir" -ForegroundColor Yellow
    Remove-Item $TargetDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

$Url       = "https://community.chocolatey.org/api/v2/package/freerdp.portable/$Version"
$TempDir   = Join-Path $env:TEMP "rlqshell-freerdp-$([guid]::NewGuid().ToString('N'))"
$NupkgPath = Join-Path $TempDir 'freerdp.portable.nupkg'
$ExtractDir = Join-Path $TempDir 'extracted'

New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

try {
    Write-Host "==> Downloading freerdp.portable $Version" -ForegroundColor Cyan
    Write-Host "    $Url"
    # Chocolatey CDN throttles requests without a UA -- set one explicitly
    Invoke-WebRequest -Uri $Url -OutFile $NupkgPath -UseBasicParsing `
        -UserAgent 'rlqshell-build/1.0' -MaximumRedirection 5

    $size = [math]::Round(((Get-Item $NupkgPath).Length / 1MB), 1)
    Write-Host "    Got $size MB"

    Write-Host "==> Extracting" -ForegroundColor Cyan
    # Expand-Archive only recognizes .zip extensions; rename so it cooperates.
    $nupkgZip = [System.IO.Path]::ChangeExtension($NupkgPath, '.zip')
    Move-Item $NupkgPath $nupkgZip
    Expand-Archive -Path $nupkgZip -DestinationPath $ExtractDir -Force

    # The portable package puts binaries in tools/ -- find wfreerdp.exe and copy
    # everything from its directory (DLLs + license files + manifest)
    $wfreerdp = Get-ChildItem $ExtractDir -Recurse -Filter 'wfreerdp.exe' |
        Select-Object -First 1
    if (-not $wfreerdp) {
        throw "wfreerdp.exe not found in extracted package -- has the package layout changed?"
    }

    $sourceDir = $wfreerdp.Directory.FullName
    Write-Host "    Source: $sourceDir"

    # Skip Chocolatey-internal files; copy the rest verbatim
    $excludeNames = @(
        'chocolateyinstall.ps1', 'chocolateyuninstall.ps1', 'chocolateyBeforeModify.ps1',
        'VERIFICATION.txt', '.ignore'
    )
    Get-ChildItem $sourceDir -File | Where-Object {
        $_.Name -notin $excludeNames -and $_.Extension -notin @('.ignore')
    } | ForEach-Object {
        Copy-Item $_.FullName -Destination (Join-Path $TargetDir $_.Name)
    }

    # Recurse into any subdirs (rare, but FreeRDP ships locale/ for translations)
    Get-ChildItem $sourceDir -Directory | ForEach-Object {
        Copy-Item $_.FullName -Destination $TargetDir -Recurse
    }

    if (-not (Test-Path $Marker)) {
        throw "wfreerdp.exe was not copied to $TargetDir -- copy step failed?"
    }

    $files = (Get-ChildItem $TargetDir -Recurse -File).Count
    $totalMb = [math]::Round(((Get-ChildItem $TargetDir -Recurse -File |
        Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Host ""
    Write-Host "==> Done: $files files, $totalMb MB in $TargetDir" -ForegroundColor Green

    # Quick smoke test -- make sure the binary even runs.
    # Use Start-Process with file redirection: invoking native EXEs with
    # `2>$null` or `2>&1` in Windows PowerShell 5.1 wraps every stderr
    # line as an ErrorRecord (NativeCommandError), which combined with
    # $ErrorActionPreference='Stop' aborts the script even on exit code 0.
    # FreeRDP 3.21 writes deprecation warnings about wfreerdp to stderr,
    # so we have to dodge that here.
    Write-Host ""
    Write-Host "==> Verifying binary" -ForegroundColor Cyan
    $tmpOut = [System.IO.Path]::GetTempFileName()
    $tmpErr = [System.IO.Path]::GetTempFileName()
    try {
        Start-Process -FilePath $Marker -ArgumentList '/version' `
            -NoNewWindow -Wait `
            -RedirectStandardOutput $tmpOut `
            -RedirectStandardError $tmpErr | Out-Null
        $verLine = Get-Content $tmpOut |
            Where-Object { $_ -match 'FreeRDP version' } |
            Select-Object -First 1
        if ($verLine) { Write-Host "    $($verLine.Trim())" -ForegroundColor Green }
        else { Write-Host "    (could not parse version output)" -ForegroundColor Yellow }
    } finally {
        Remove-Item $tmpOut, $tmpErr -ErrorAction SilentlyContinue
    }
}
finally {
    if (Test-Path $TempDir) {
        Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
