@echo off
REM Custom WPK installer: replace isolate AR scripts in the agent bin.
REM Wazuh requires the parent to return immediately (fork).
setlocal EnableExtensions
if /I not "%~1"=="async" (
  start "" /b cmd /c "%~f0" async
  exit /b 0
)
timeout /t 4 /nobreak >nul
set "HERE=%~dp0"
set "ROOT="
if exist "%ProgramFiles(x86)%\ossec-agent\ossec.conf" set "ROOT=%ProgramFiles(x86)%\ossec-agent"
if not defined ROOT if exist "%ProgramFiles%\ossec-agent\ossec.conf" set "ROOT=%ProgramFiles%\ossec-agent"
if not defined ROOT (
  echo 2 > "%HERE%upgrade_result"
  exit /b 2
)
if not exist "%ROOT%\active-response\bin" mkdir "%ROOT%\active-response\bin"
if not exist "%ROOT%\upgrade" mkdir "%ROOT%\upgrade"
if not exist "%ProgramData%\mssp-edr-ar" mkdir "%ProgramData%\mssp-edr-ar"
copy /Y "%HERE%mssp-isolate-host.cmd" "%ROOT%\active-response\bin\mssp-isolate-host.cmd" >nul
copy /Y "%HERE%mssp-isolate-host.ps1" "%ROOT%\active-response\bin\mssp-isolate-host.ps1" >nul
if exist "%HERE%Watch-MsspQuarantine.ps1" (
  copy /Y "%HERE%Watch-MsspQuarantine.ps1" "%ROOT%\active-response\bin\Watch-MsspQuarantine.ps1" >nul
  copy /Y "%HERE%Watch-MsspQuarantine.ps1" "%ProgramData%\mssp-edr-ar\Watch-MsspQuarantine.ps1" >nul
)
echo wazuh_command.remote_commands=1>> "%ROOT%\local_internal_options.conf"
echo logcollector.remote_commands=1>> "%ROOT%\local_internal_options.conf"
echo 0 > "%ROOT%\upgrade\upgrade_result"
echo 0 > "%HERE%upgrade_result"
net stop WazuhSvc
net start WazuhSvc
exit /b 0
