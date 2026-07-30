@echo off
REM Wazuh execd sends one JSON line on STDIN.
REM Do NOT use "more" (deadlocks). Do NOT put JSON on cmd argv (quotes break).
REM Launch PowerShell once; it reads STDIN itself, then invokes the .ps1 with a
REM PowerShell string argument (safe for embedded quotes).
setlocal EnableExtensions
set "MSSP_AR_PS1=%~dp0mssp-isolate-host.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps1=$env:MSSP_AR_PS1; $raw=[Console]::In.ReadLine(); if ($null -eq $raw) { $raw = '' }; & $ps1 $raw; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
