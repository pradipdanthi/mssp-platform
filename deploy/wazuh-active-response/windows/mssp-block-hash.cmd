@echo off
setlocal EnableExtensions
set "MSSP_AR_PS1=%~dp0mssp-block-hash.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps1=$env:MSSP_AR_PS1; $raw=[Console]::In.ReadLine(); if ($null -eq $raw) { $raw = '' }; & $ps1 $raw; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
