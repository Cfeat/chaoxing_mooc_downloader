@echo off
setlocal
cd /d "%~dp0"

rem PowerShell 调用本 bat 时，URL 中的 & 会被拆成多条命令。
rem 统一转交给 run.ps1，由 PowerShell 正确传参。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %ERRORLEVEL%
