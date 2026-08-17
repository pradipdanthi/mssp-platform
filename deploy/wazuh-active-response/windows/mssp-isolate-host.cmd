@echo off
REM Wazuh execd sends one JSON line on STDIN.
REM Do NOT use "more" (deadlocks). Do NOT put JSON on cmd argv (quotes break).
REM Launch PowerShell once; it reads STDIN itself, then invokes the .ps1 with a
REM PowerShell string argument (safe for embedded quotes).
setlocal EnableExtensions
REM %~dp0 is active-response\bin\. Shared files live at agent-root\shared\.
REM Do NOT use %ProgramFiles(x86)% here: parentheses break cmd parsing and the
REM copy silently never runs, leaving the stale auto-lift script in bin.
set "MSSP_AR_PS1=%~dp0mssp-isolate-host.ps1"
set "MSSP_SHARED_PS1=%~dp0..\..\shared\mssp-isolate-host.ps1"
if exist "%MSSP_SHARED_PS1%" copy /Y "%MSSP_SHARED_PS1%" "%MSSP_AR_PS1%" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ps1=$env:MSSP_AR_PS1; $raw=[Console]::In.ReadLine(); if ($null -eq $raw) { $raw = '' }; & $ps1 $raw; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%
