$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

py -3.12 -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath "$projectRoot\dist-standalone" `
    --workpath "$projectRoot\build-standalone" `
    "$projectRoot\LVGLLibrarySwapperStandalone.spec"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Standalone build complete:"
Write-Host "$projectRoot\dist-standalone\FAH-Visuino-LVGL-Library-Swapper.exe"
