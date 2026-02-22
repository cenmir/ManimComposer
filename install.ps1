# Manim Composer — One-liner bootstrap installer
# Usage: irm https://raw.githubusercontent.com/cenmir/ManimComposer/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

# Force TLS 1.2 (required by GitHub, not default on older PowerShell)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repoUrl = "https://github.com/cenmir/ManimComposer/archive/refs/heads/main.zip"
$tempDir = Join-Path $env:TEMP "ManimComposer-install-$(Get-Random)"
$zipPath = Join-Path $tempDir "ManimComposer.zip"

try {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Manim Composer Installer" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "Downloading Manim Composer..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

    # Disable progress bar for faster download
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $repoUrl -OutFile $zipPath -UseBasicParsing -TimeoutSec 120
    $ProgressPreference = 'Continue'

    if (-not (Test-Path $zipPath)) {
        throw "Download failed - ZIP file not found"
    }

    Write-Host "Extracting..." -ForegroundColor Cyan
    Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

    $extractedDir = Join-Path $tempDir "ManimComposer-main"
    $installScript = Join-Path $extractedDir "installer\Install-ManimComposer.ps1"

    if (-not (Test-Path $installScript)) {
        throw "Extraction failed - installer script not found at $installScript"
    }

    Write-Host "Running installer..." -ForegroundColor Cyan
    & $installScript -SourceDir $extractedDir

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  Installation complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now launch Manim Composer from:"
    Write-Host "  - Start Menu: 'Manim Composer'"
    Write-Host "  - Desktop shortcut"
    Write-Host "  - Command line: manim-composer"
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Host "Installation failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Manual installation:" -ForegroundColor Yellow
    Write-Host "  1. Install uv:    irm https://astral.sh/uv/install.ps1 | iex" -ForegroundColor Yellow
    Write-Host "  2. Install Python: uv python install 3.13" -ForegroundColor Yellow
    Write-Host "  3. Clone repo:    git clone https://github.com/cenmir/ManimComposer" -ForegroundColor Yellow
    Write-Host "  4. Install deps:  cd ManimComposer && uv sync" -ForegroundColor Yellow
    Write-Host "  5. Run:           uv run manim-composer" -ForegroundColor Yellow
    throw
}
finally {
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
