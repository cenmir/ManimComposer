# Manim Composer — Main Installer
# Installs uv, Python 3.13, Manim Composer, and TinyTeX with shortcuts.
# Called by install.ps1 (bootstrap) with -SourceDir pointing to the extracted repo.

param(
    [Parameter(Mandatory=$true)]
    [string]$SourceDir
)

$ErrorActionPreference = "Stop"

# Force TLS 1.2
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallBase = Join-Path $env:LOCALAPPDATA "ManimComposer"
$AppDir      = Join-Path $InstallBase "app"
$LauncherCmd = Join-Path $InstallBase "manim-composer.cmd"

# TinyTeX paths (must match latex_manager.py constants)
$TinyTeXDir = Join-Path $InstallBase "TinyTeX"
$TinyTeXBin = Join-Path $TinyTeXDir "bin\windows"
$TinyTeXUrl = "https://yihui.org/tinytex/TinyTeX-0.zip"
$TinyTeXPackages = @(
    "latex-bin", "dvipng", "dvisvgm", "dvipdfmx",
    "standalone", "preview", "amsmath", "amsfonts", "babel-english"
)

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Install uv
# ─────────────────────────────────────────────────────────────────────────────

function Install-Uv {
    Write-Host ""
    Write-Host "[1/6] Checking for uv..." -ForegroundColor Cyan

    $uvLocalBin = Join-Path $env:USERPROFILE ".local\bin"
    $uvExe      = Join-Path $uvLocalBin "uv.exe"

    # Check expected install location
    if (Test-Path $uvExe) {
        Write-Host "  uv found at $uvExe" -ForegroundColor Green
        Ensure-InPath $uvLocalBin
        return
    }

    # Check if it's already on PATH
    $uvInPath = (Get-Command uv -ErrorAction SilentlyContinue).Path
    if ($uvInPath) {
        Write-Host "  uv found at $uvInPath" -ForegroundColor Green
        return
    }

    Write-Host "  Installing uv..." -ForegroundColor Yellow
    $ProgressPreference = 'SilentlyContinue'
    Invoke-Expression "powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'"
    $ProgressPreference = 'Continue'

    if (-not (Test-Path $uvExe)) {
        throw "uv installation failed - uv.exe not found at $uvExe"
    }

    Ensure-InPath $uvLocalBin
    Write-Host "  uv installed successfully" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Install Python 3.13
# ─────────────────────────────────────────────────────────────────────────────

function Install-Python {
    Write-Host ""
    Write-Host "[2/6] Installing Python 3.13..." -ForegroundColor Cyan

    uv python install 3.13 --default
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.13 installation failed (exit code $LASTEXITCODE)"
    }

    $pythonPath = (uv python find 3.13 2>$null)
    if ($pythonPath -and (Test-Path $pythonPath)) {
        $version = & $pythonPath --version
        Write-Host "  $version installed at $pythonPath" -ForegroundColor Green
    } else {
        Write-Host "  Python 3.13 installed (path will be available after restart)" -ForegroundColor Green
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Copy project files to install directory
# ─────────────────────────────────────────────────────────────────────────────

function Install-App {
    Write-Host ""
    Write-Host "[3/6] Installing Manim Composer..." -ForegroundColor Cyan

    # Create install directory
    New-Item -ItemType Directory -Path $InstallBase -Force | Out-Null

    # Remove old app directory if it exists (clean update)
    if (Test-Path $AppDir) {
        Write-Host "  Removing previous installation..." -ForegroundColor Yellow
        # Preserve .venv to avoid re-downloading all packages
        $venvDir = Join-Path $AppDir ".venv"
        $venvTemp = Join-Path $InstallBase ".venv-backup"
        $hasVenv = Test-Path $venvDir
        if ($hasVenv) {
            if (Test-Path $venvTemp) { Remove-Item $venvTemp -Recurse -Force }
            Move-Item $venvDir $venvTemp -Force
        }
        Remove-Item $AppDir -Recurse -Force
        if ($hasVenv) {
            New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
            Move-Item $venvTemp $venvDir -Force
        }
    }

    # Copy project files (exclude .git, media, __pycache__, .venv)
    Write-Host "  Copying files..."
    $excludeDirs = @('.git', 'media', '__pycache__', '.venv', 'manim_composer.egg-info', '.claude')
    Copy-FilteredDirectory -Source $SourceDir -Destination $AppDir -ExcludeDirs $excludeDirs

    # Run uv sync to install dependencies
    Write-Host "  Installing dependencies (this may take a few minutes)..."
    Push-Location $AppDir
    try {
        uv sync
        if ($LASTEXITCODE -ne 0) {
            throw "uv sync failed (exit code $LASTEXITCODE)"
        }
    } finally {
        Pop-Location
    }

    Write-Host "  Manim Composer installed to $AppDir" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Install TinyTeX
# ─────────────────────────────────────────────────────────────────────────────

function Install-TinyTeX {
    Write-Host ""
    Write-Host "[4/6] Installing TinyTeX..." -ForegroundColor Cyan

    $tlmgr = Join-Path $TinyTeXBin "tlmgr.bat"

    # Skip if already installed and complete
    if ((Test-Path $tlmgr) -and (Test-Path (Join-Path $TinyTeXBin "latex.exe")) -and
        (Test-Path (Join-Path $TinyTeXBin "dvipng.exe")) -and
        (Test-Path (Join-Path $TinyTeXBin "dvipdfmx.exe"))) {
        Write-Host "  TinyTeX already installed and complete" -ForegroundColor Green
        return
    }

    # Download
    $zipPath = Join-Path $env:TEMP "TinyTeX-0.zip"
    Write-Host "  Downloading TinyTeX (~45 MB)..."
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $TinyTeXUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    $ProgressPreference = 'Continue'

    if (-not (Test-Path $zipPath)) {
        throw "TinyTeX download failed"
    }

    # Extract (ZIP contains a TinyTeX/ folder at root)
    Write-Host "  Extracting..."
    New-Item -ItemType Directory -Path $InstallBase -Force | Out-Null
    if (Test-Path $TinyTeXDir) {
        Remove-Item $TinyTeXDir -Recurse -Force
    }
    Expand-Archive -Path $zipPath -DestinationPath $InstallBase -Force
    Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

    if (-not (Test-Path $tlmgr)) {
        throw "TinyTeX extraction failed - tlmgr.bat not found at $TinyTeXBin"
    }

    # Install required TeX packages
    Write-Host "  Installing LaTeX packages (this may take a minute)..."
    & $tlmgr install @TinyTeXPackages
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Warning: tlmgr exited with code $LASTEXITCODE (some packages may already be installed)" -ForegroundColor Yellow
    }

    # Verify critical binaries
    foreach ($exe in @("latex.exe", "dvipng.exe", "dvipdfmx.exe")) {
        $exePath = Join-Path $TinyTeXBin $exe
        if (-not (Test-Path $exePath)) {
            throw "TinyTeX package install failed - $exe not found at $TinyTeXBin"
        }
    }

    Write-Host "  TinyTeX installed to $TinyTeXDir" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Create launcher script
# ─────────────────────────────────────────────────────────────────────────────

function Create-Launcher {
    Write-Host ""
    Write-Host "[5/6] Creating launcher..." -ForegroundColor Cyan

    $uvExe = (Get-Command uv -ErrorAction SilentlyContinue).Path
    if (-not $uvExe) {
        $uvExe = Join-Path $env:USERPROFILE ".local\bin\uv.exe"
    }

    # .cmd launcher for shortcuts and command line
    $cmdContent = @"
@echo off
cd /d "$AppDir"
"$uvExe" run manim-composer %*
"@
    Set-Content -Path $LauncherCmd -Value $cmdContent -Encoding ASCII

    # .vbs launcher for shortcuts (hides the console window)
    $vbsPath = Join-Path $InstallBase "manim-composer.vbs"
    $vbsContent = @"
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "$AppDir"
WshShell.Run """$uvExe"" run manim-composer", 0, False
"@
    Set-Content -Path $vbsPath -Value $vbsContent -Encoding ASCII

    Write-Host "  Launcher created at $LauncherCmd" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Create shortcuts and add to PATH
# ─────────────────────────────────────────────────────────────────────────────

function Create-Shortcuts {
    Write-Host ""
    Write-Host "[6/6] Creating shortcuts..." -ForegroundColor Cyan

    $vbsPath = Join-Path $InstallBase "manim-composer.vbs"
    $WshShell = New-Object -ComObject WScript.Shell

    # Try to find a Python icon for the shortcut
    $pythonPath = (uv python find 3.13 2>$null)
    $iconPath = ""
    if ($pythonPath -and (Test-Path $pythonPath)) {
        $iconPath = $pythonPath
    }

    # Start Menu shortcut
    $startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $startMenuLink = Join-Path $startMenuDir "Manim Composer.lnk"
    $shortcut = $WshShell.CreateShortcut($startMenuLink)
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbsPath`""
    $shortcut.WorkingDirectory = $AppDir
    $shortcut.Description = "Manim Composer - Visual animation editor"
    if ($iconPath) { $shortcut.IconLocation = "$iconPath, 0" }
    $shortcut.Save()
    Write-Host "  Start Menu shortcut created" -ForegroundColor Green

    # Desktop shortcut
    $desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Manim Composer.lnk"
    $shortcut = $WshShell.CreateShortcut($desktopLink)
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbsPath`""
    $shortcut.WorkingDirectory = $AppDir
    $shortcut.Description = "Manim Composer - Visual animation editor"
    if ($iconPath) { $shortcut.IconLocation = "$iconPath, 0" }
    $shortcut.Save()
    Write-Host "  Desktop shortcut created" -ForegroundColor Green

    # Add to user PATH for command-line access
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$InstallBase*") {
        [Environment]::SetEnvironmentVariable("PATH", "$InstallBase;$userPath", "User")
        $env:Path = "$InstallBase;$env:Path"
        Write-Host "  Added to PATH (run 'manim-composer' from any terminal)" -ForegroundColor Green
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

function Ensure-InPath([string]$Dir) {
    if ($env:Path -notlike "*$([System.Text.RegularExpressions.Regex]::Escape($Dir))*") {
        $env:Path = "$Dir;$env:Path"
    }
}

function Copy-FilteredDirectory([string]$Source, [string]$Destination, [string[]]$ExcludeDirs) {
    if (-not (Test-Path $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }

    # Copy files in current directory
    Get-ChildItem -Path $Source -File | ForEach-Object {
        Copy-Item $_.FullName -Destination $Destination -Force
    }

    # Recursively copy subdirectories (excluding filtered ones)
    Get-ChildItem -Path $Source -Directory | Where-Object {
        $_.Name -notin $ExcludeDirs
    } | ForEach-Object {
        $destSubDir = Join-Path $Destination $_.Name
        Copy-FilteredDirectory -Source $_.FullName -Destination $destSubDir -ExcludeDirs $ExcludeDirs
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

Install-Uv
Install-Python
Install-App
Install-TinyTeX
Create-Launcher
Create-Shortcuts

Write-Host ""
Write-Host "Manim Composer is ready!" -ForegroundColor Green
