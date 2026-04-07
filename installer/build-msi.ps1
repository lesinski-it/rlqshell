<#
.SYNOPSIS
    Builds the RLQShell MSI installer.

.DESCRIPTION
    1. Reads version from pyproject.toml
    2. Optionally rebuilds dist/RLQShell.exe with PyInstaller (-Rebuild)
    3. Runs `wix build` to produce dist/RLQShell-<version>-x64.msi

.PARAMETER Rebuild
    Rebuild the PyInstaller executable before packaging.

.PARAMETER Version
    Override the version string (default: read from pyproject.toml).

.EXAMPLE
    pwsh installer/build-msi.ps1
    pwsh installer/build-msi.ps1 -Rebuild
    pwsh installer/build-msi.ps1 -Version 0.2.0
#>
[CmdletBinding()]
param(
    [switch]$Rebuild,
    [string]$Version
)

$ErrorActionPreference = 'Stop'

# Resolve repo root (parent of this script's directory)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

Write-Host "==> Repo root: $RepoRoot" -ForegroundColor Cyan

# --- Resolve version ---------------------------------------------------------
if (-not $Version) {
    $pyproject = Get-Content (Join-Path $RepoRoot 'pyproject.toml') -Raw
    if ($pyproject -match '(?m)^\s*version\s*=\s*"([^"]+)"') {
        $Version = $Matches[1]
    } else {
        throw "Could not parse version from pyproject.toml"
    }
}
Write-Host "==> Version: $Version" -ForegroundColor Cyan

# --- Ensure dotnet + wix are on PATH for this session ------------------------
$UserDotnet     = Join-Path $env:USERPROFILE '.dotnet'
$UserDotnetTool = Join-Path $UserDotnet 'tools'
if (Test-Path $UserDotnet)     { $env:PATH = "$UserDotnet;$env:PATH"; $env:DOTNET_ROOT = $UserDotnet }
if (Test-Path $UserDotnetTool) { $env:PATH = "$UserDotnetTool;$env:PATH" }

try { $wixVersion = (wix --version) 2>$null } catch { $wixVersion = $null }
if (-not $wixVersion) {
    throw "wix.exe not found on PATH. Install with: dotnet tool install -g wix --version 6.0.2"
}
Write-Host "==> WiX: $wixVersion" -ForegroundColor Cyan

# --- Rebuild executable if requested -----------------------------------------
$SourceExe = Join-Path $RepoRoot 'dist\RLQShell.exe'
if ($Rebuild) {
    Write-Host "==> Running PyInstaller (rlqshell.spec)" -ForegroundColor Cyan
    pyinstaller --noconfirm --clean rlqshell.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}
if (-not (Test-Path $SourceExe)) {
    throw "Missing $SourceExe. Run with -Rebuild or build it first."
}

# --- Paths for WiX variables -------------------------------------------------
$IconFile   = Join-Path $RepoRoot 'rlqshell\resources\images\app_icon.ico'
$LicenseRtf = Join-Path $ScriptDir 'License.rtf'
$WxsFile    = Join-Path $ScriptDir 'RLQShell.wxs'

foreach ($p in @($IconFile, $LicenseRtf, $WxsFile)) {
    if (-not (Test-Path $p)) { throw "Missing required file: $p" }
}

# --- Build MSI ---------------------------------------------------------------
$OutputDir = Join-Path $RepoRoot 'dist'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputMsi = Join-Path $OutputDir "RLQShell-$Version-x64.msi"

Write-Host "==> Building $OutputMsi" -ForegroundColor Cyan
wix build `
    -arch x64 `
    -ext WixToolset.UI.wixext `
    -d "Version=$Version" `
    -d "SourceExe=$SourceExe" `
    -d "IconFile=$IconFile" `
    -d "LicenseRtf=$LicenseRtf" `
    -out $OutputMsi `
    $WxsFile

if ($LASTEXITCODE -ne 0) { throw "wix build failed" }

$size = [math]::Round(((Get-Item $OutputMsi).Length / 1MB), 1)
Write-Host ""
Write-Host "==> Done: $OutputMsi ($size MB)" -ForegroundColor Green
