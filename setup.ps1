# 本地虚拟环境 + 国内镜像安装
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PyPi = "https://mirrors.aliyun.com/pypi/simple/"
$HostTrusted = "mirrors.aliyun.com"
$PwHost = "https://npmmirror.com/mirrors/playwright"

Write-Host "==> 创建/3 创建本地 venv (.venv)"
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    python -m venv .venv
}

Write-Host "==> 2/3 安装 Python 依赖 (阿里云 PyPI)"
.\.venv\Scripts\python.exe -m pip install -U pip -i $PyPi --trusted-host $HostTrusted
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i $PyPi --trusted-host $HostTrusted

Write-Host "==> 3/3 安装 Chromium 到项目目录 (npmmirror)"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PSScriptRoot ".playwright-browsers"
$env:PLAYWRIGHT_DOWNLOAD_HOST = $PwHost
New-Item -ItemType Directory -Force -Path $env:PLAYWRIGHT_BROWSERS_PATH | Out-Null
.\.venv\Scripts\python.exe -m playwright install chromium

Write-Host ""
Write-Host "完成。之后请用 run.ps1 / run.bat 启动，例如:"
Write-Host "  .\run.ps1 login --url `"你的课程页URL`""
Write-Host "  .\run.ps1 download --url `"你的课程页URL`""
