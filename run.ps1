# 使用本地 venv + 本地 Chromium 运行工具
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "未找到 .venv，请先运行: .\setup.ps1"
    exit 1
}

$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot ".playwright-browsers"
& $Python -m chaoxing_dl @args
exit $LASTEXITCODE
