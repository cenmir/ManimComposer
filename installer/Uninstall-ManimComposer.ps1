# Manim Composer — Uninstaller
# Removes the app, shortcuts, and PATH entry. Does NOT uninstall uv or Python.

$ErrorActionPreference = "Stop"

$InstallBase = Join-Path $env:LOCALAPPDATA "ManimComposer"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Manim Composer Uninstaller" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Confirm
$answer = Read-Host "This will remove Manim Composer and all its data (including TinyTeX). Continue? [y/N]"
if ($answer -notin @('y', 'Y', 'yes', 'Yes')) {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0
}

# Remove install directory (app + TinyTeX + launcher)
if (Test-Path $InstallBase) {
    Write-Host "Removing $InstallBase..." -ForegroundColor Yellow
    Remove-Item -Path $InstallBase -Recurse -Force
    Write-Host "  Done" -ForegroundColor Green
} else {
    Write-Host "Install directory not found (already removed?)" -ForegroundColor Yellow
}

# Remove Start Menu shortcut
$startMenuLink = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Manim Composer.lnk"
if (Test-Path $startMenuLink) {
    Remove-Item $startMenuLink -Force
    Write-Host "Start Menu shortcut removed" -ForegroundColor Green
}

# Remove Desktop shortcut
$desktopLink = Join-Path ([Environment]::GetFolderPath("Desktop")) "Manim Composer.lnk"
if (Test-Path $desktopLink) {
    Remove-Item $desktopLink -Force
    Write-Host "Desktop shortcut removed" -ForegroundColor Green
}

# Remove from user PATH
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -like "*$InstallBase*") {
    $newPath = ($userPath -split ";" | Where-Object { $_ -ne $InstallBase }) -join ";"
    [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
    Write-Host "Removed from PATH" -ForegroundColor Green
}

Write-Host ""
Write-Host "Manim Composer has been uninstalled." -ForegroundColor Green
Write-Host "Note: uv and Python were NOT removed (they may be used by other apps)." -ForegroundColor Yellow
Write-Host ""
