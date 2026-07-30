#Requires -RunAsAdministrator
<#
.SYNOPSIS
  MSSP Windows endpoint telemetry bootstrap (Sysmon + audit + agent log channels).

.DESCRIPTION
  Production prerequisite for process-tree / EDR detection on Windows.
  Does NOT alert on every process - it enables filtered telemetry collection.
  Wazuh/manager rules decide what becomes an alert.

  Safe to re-run (idempotent).

.PARAMETER SysmonConfigPath
  Path to Sysmon XML baseline. Defaults to sibling sysmon-windows-baseline.xml
  or process-telemetry-baseline.xml.

.PARAMETER SkipSysmonDownload
  If set, only enable audit policies + agent localfile (no Sysmon binary install).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\bootstrap_windows_telemetry.ps1
#>
[CmdletBinding()]
param(
  [string]$SysmonConfigPath = "",
  [switch]$SkipSysmonDownload
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
  Write-Host "[MSSP-TELEMETRY] $Message"
}

function Assert-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script in elevated PowerShell (Run as Administrator)."
  }
}

function Resolve-SysmonConfig {
  param([string]$Explicit)
  if ($Explicit -and (Test-Path -LiteralPath $Explicit)) {
    return (Resolve-Path -LiteralPath $Explicit).Path
  }
  $candidates = @(
    (Join-Path $PSScriptRoot "sysmon-windows-baseline.xml"),
    (Join-Path $PSScriptRoot "process-telemetry-baseline.xml"),
    (Join-Path $PSScriptRoot "windows\sysmon-windows-baseline.xml"),
    (Join-Path $PSScriptRoot "windows\process-telemetry-baseline.xml")
  )
  foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) {
      return (Resolve-Path -LiteralPath $c).Path
    }
  }
  throw "Sysmon baseline XML not found next to this script. Pass -SysmonConfigPath."
}

function Enable-ProcessCreationAuditing {
  Write-Step "Enabling Windows Process Creation auditing (4688) + command line..."
  & auditpol.exe /set /subcategory:"Process Creation" /success:enable /failure:enable | Out-Null
  $regPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit"
  if (-not (Test-Path $regPath)) {
    New-Item -Path $regPath -Force | Out-Null
  }
  New-ItemProperty -Path $regPath -Name "ProcessCreationIncludeCmdLine_Enabled" `
    -PropertyType DWord -Value 1 -Force | Out-Null
  Write-Step "Audit policy OK"
}

function Install-OrUpdateSysmon {
  param([string]$ConfigPath)

  $sysmonExe = $null
  foreach ($name in @("Sysmon64", "Sysmon")) {
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($svc) {
      $cmd = Get-Command "$name.exe" -ErrorAction SilentlyContinue
      if ($cmd) { $sysmonExe = $cmd.Source }
      break
    }
  }
  # Common install locations
  if (-not $sysmonExe) {
    foreach ($p in @(
      "$env:ProgramFiles\Sysmon\Sysmon64.exe",
      "$env:ProgramFiles\Sysmon\Sysmon.exe",
      "${env:ProgramFiles(x86)}\Sysmon\Sysmon64.exe",
      "C:\Windows\Sysmon64.exe",
      "C:\Windows\Sysmon.exe"
    )) {
      if (Test-Path -LiteralPath $p) { $sysmonExe = $p; break }
    }
  }

  $work = Join-Path $env:TEMP ("mssp-sysmon-" + [guid]::NewGuid().ToString("n"))
  New-Item -ItemType Directory -Path $work -Force | Out-Null
  try {
    if (-not $sysmonExe) {
      Write-Step "Downloading Microsoft Sysmon..."
      $zip = Join-Path $work "Sysmon.zip"
      Invoke-WebRequest -Uri "https://download.sysinternals.com/files/Sysmon.zip" -OutFile $zip
      Expand-Archive -Path $zip -DestinationPath $work -Force
      $sysmonExe = Join-Path $work "Sysmon64.exe"
      if (-not (Test-Path -LiteralPath $sysmonExe)) {
        $sysmonExe = Join-Path $work "Sysmon.exe"
      }
      if (-not (Test-Path -LiteralPath $sysmonExe)) {
        throw "Sysmon executable missing after download"
      }
      Write-Step "Installing Sysmon with MSSP baseline config..."
      & $sysmonExe -accepteula -i $ConfigPath
      if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null -and $LASTEXITCODE -notin @(0, 1)) {
        # Sysmon often returns 0; treat hard failures only
        Write-Step "Sysmon install exit code: $LASTEXITCODE (continuing if service present)"
      }
    } else {
      Write-Step "Sysmon already present ($sysmonExe) - updating config..."
      & $sysmonExe -accepteula -c $ConfigPath
    }

    $svc = Get-Service -Name "Sysmon64" -ErrorAction SilentlyContinue
    if (-not $svc) { $svc = Get-Service -Name "Sysmon" -ErrorAction SilentlyContinue }
    if (-not $svc) {
      throw "Sysmon service not found after install"
    }
    if ($svc.Status -ne "Running") {
      Start-Service -Name $svc.Name
    }
    Write-Step ("Sysmon service OK: " + $svc.Name + " / " + $svc.Status)
  } finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
  }
}

function Get-OssecConfPath {
  $candidates = @(
    "${env:ProgramFiles(x86)}\ossec-agent\ossec.conf",
    "$env:ProgramFiles\ossec-agent\ossec.conf"
  )
  foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) { return $c }
  }
  return $null
}

function Ensure-AgentLocalfiles {
  $conf = Get-OssecConfPath
  if (-not $conf) {
    Write-Step "WARNING: Agent ossec.conf not found - install the endpoint agent first, then re-run this script."
    return $false
  }

  Write-Step "Ensuring agent log channels in $conf ..."
  $raw = Get-Content -LiteralPath $conf -Raw -Encoding UTF8

  $sysmonBlock = @"
  <localfile>
    <location>Microsoft-Windows-Sysmon/Operational</location>
    <log_format>eventchannel</log_format>
  </localfile>
"@

  $sec4688Block = @"
  <localfile>
    <location>Security</location>
    <log_format>eventchannel</log_format>
    <query>Event/System[EventID=4688]</query>
  </localfile>
"@

  $changed = $false
  if ($raw -notmatch "Microsoft-Windows-Sysmon/Operational") {
    if ($raw -match "</ossec_config>") {
      $raw = $raw -replace "</ossec_config>", ($sysmonBlock + "`r`n</ossec_config>")
      $changed = $true
      Write-Step "Added Sysmon Operational localfile"
    }
  } else {
    Write-Step "Sysmon localfile already present"
  }

  if ($raw -notmatch "EventID=4688") {
    if ($raw -match "</ossec_config>") {
      $raw = $raw -replace "</ossec_config>", ($sec4688Block + "`r`n</ossec_config>")
      $changed = $true
      Write-Step "Added Security 4688 localfile"
    }
  } else {
    Write-Step "Security 4688 localfile already present"
  }

  if ($changed) {
    $backup = "$conf.bak.mssp-telemetry-" + (Get-Date -Format "yyyyMMddHHmmss")
    Copy-Item -LiteralPath $conf -Destination $backup -Force
    Set-Content -LiteralPath $conf -Value $raw -Encoding UTF8
    Write-Step "Wrote ossec.conf (backup: $backup)"
  }

  $svc = Get-Service -Name "WazuhSvc" -ErrorAction SilentlyContinue
  if ($svc) {
    Write-Step "Restarting WazuhSvc..."
    Restart-Service -Name WazuhSvc -Force
    Start-Sleep -Seconds 3
    Get-Service -Name WazuhSvc | Format-List Name, Status
  } else {
    Write-Step "WARNING: WazuhSvc not found - localfile saved; start agent after install."
  }
  return $true
}

# --- main ---
Assert-Admin
Write-Step "Starting Windows telemetry bootstrap (filtered collection, not alert-everything)"

Enable-ProcessCreationAuditing

$config = Resolve-SysmonConfig -Explicit $SysmonConfigPath
Write-Step "Using Sysmon config: $config"

if ($SkipSysmonDownload) {
  Write-Step "Skipping Sysmon binary install (-SkipSysmonDownload)"
} else {
  Install-OrUpdateSysmon -ConfigPath $config
}

Ensure-AgentLocalfiles | Out-Null

Write-Host ""
Write-Host "MSSP_WINDOWS_TELEMETRY_OK"
Write-Host "Next: generate a controlled suspicious process (e.g. encoded PowerShell) and confirm"
Write-Host "alerts/incidents in Admin portal - not every process create will alert."
