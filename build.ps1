# GateScout build script
# Usage: .\build.ps1
# Requires: pip install pyinstaller  |  https://jrsoftware.org/isdl.php (Inno Setup)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Read version from version.py
$versionLine = Get-Content "version.py" | Where-Object { $_ -match 'VERSION\s*=' }
$version = ($versionLine -replace '.*=\s*"([^"]+)".*', '$1').Trim()
Write-Host "Building GateScout v$version" -ForegroundColor Cyan

# Step 1: Clean previous build artefacts
Write-Host "`n[1/2] Cleaning previous build..." -ForegroundColor Yellow
@("build", "dist\GateScout") | ForEach-Object {
    if (Test-Path $_) { Remove-Item $_ -Recurse -Force }
}

# Step 2: PyInstaller
Write-Host "`n[2/3] Running PyInstaller..." -ForegroundColor Yellow
pyinstaller --noconfirm gatescout.spec
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller failed."; exit 1 }
Write-Host "PyInstaller done." -ForegroundColor Green

# Step 3: Inno Setup
Write-Host "`n[3/3] Running Inno Setup..." -ForegroundColor Yellow

$iscc = @(
    "$env:ProgramFiles (x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host "Inno Setup not found. Download from https://jrsoftware.org/isdl.php" -ForegroundColor Red
    Write-Host "PyInstaller output is in dist\GateScout\" -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path "dist\installer" | Out-Null
& $iscc /DMyAppVersion=$version installer.iss
if ($LASTEXITCODE -ne 0) { Write-Error "Inno Setup failed."; exit 1 }

Write-Host "`nDone! Installer: dist\installer\GateScout_Setup_$version.exe" -ForegroundColor Green
