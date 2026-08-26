# MSSP Windows Active Response - kill process by PID + control-plane applied callback.
# Invoked by Wazuh execd via mssp-kill-process.cmd
# Args (extra_args): [pid, execution_id, callback_url]
$ErrorActionPreference = "Continue"
$LogCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\active-responses.log",
  "$env:ProgramFiles\ossec-agent\active-response\active-responses.log"
)
$EnvCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\etc\mssp-ar.env",
  "$env:ProgramFiles\ossec-agent\etc\mssp-ar.env",
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\bin\mssp-ar.env",
  "$env:ProgramFiles\ossec-agent\active-response\bin\mssp-ar.env"
)
$Log = $LogCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $Log) { $Log = $LogCandidates[0] }
$EnvFile = $EnvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

# Prefer Manager-shared scripts when present (auto fleet sync).
try {
  $syncCand = @(
    "$env:ProgramData\mssp-edr-ar\Sync-MsspEdrAr.ps1",
    "${env:ProgramFiles(x86)}\ossec-agent\shared\Sync-MsspEdrAr.ps1",
    "$env:ProgramFiles\ossec-agent\shared\Sync-MsspEdrAr.ps1"
  ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if ($syncCand) { & $syncCand | Out-Null }
} catch {}

function Write-ArLog([string]$Message) {
  try {
    $dir = Split-Path $Log -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
      New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy/MM/dd HH:mm:ss")
    $line = "$ts mssp-kill-process: $Message`r`n"
    $fs = [System.IO.File]::Open(
      $Log,
      [System.IO.FileMode]::Append,
      [System.IO.FileAccess]::Write,
      [System.IO.FileShare]::ReadWrite
    )
    try {
      $bytes = [System.Text.Encoding]::UTF8.GetBytes($line)
      $fs.Write($bytes, 0, $bytes.Length)
    } finally {
      $fs.Dispose()
    }
  } catch {}
}

function Get-EnvMap {
  $map = @{}
  if (-not $EnvFile) { return $map }
  Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $p = $_.Split('=', 2)
    $map[$p[0].Trim()] = $p[1].Trim().Trim('"')
  }
  return $map
}

function Send-Callback([string]$Url, [string]$ExecutionId, [bool]$Applied, [string]$Message) {
  if (-not $Url -or -not $ExecutionId) {
    Write-ArLog "callback skip: url or execution_id missing"
    return
  }
  $envMap = Get-EnvMap
  $key = $envMap['MSSP_CALLBACK_KEY']
  if (-not $key) { $key = $envMap['EDR_CALLBACK_API_KEY'] }
  if (-not $Url) { $Url = $envMap['MSSP_CALLBACK_URL'] }
  if (-not $Url) {
    Write-ArLog "callback skip: no callback URL"
    return
  }
  $body = @{
    execution_id = $ExecutionId
    status = $(if ($Applied) { 'success' } else { 'failed' })
    message = $Message
    payload = @{ applied = $Applied; action = 'KILL_PROCESS' }
  } | ConvertTo-Json -Compress
  try {
    $headers = @{ 'Content-Type' = 'application/json' }
    if ($key) {
      $headers['X-EDR-Callback-Key'] = $key
      $headers['X-SOC-Sync-Key'] = $key
    }
    Invoke-RestMethod -Method Post -Uri $Url -Body $body -Headers $headers -TimeoutSec 8 | Out-Null
    Write-ArLog "callback ok applied=$Applied"
  } catch {
    Write-ArLog "callback failed: $($_.Exception.Message)"
  }
}

$raw = ""
if ($args.Count -gt 0 -and $args[0] -match '[\{\[]') {
  $raw = [string]$args[0]
} else {
  try { $raw = [Console]::In.ReadLine() } catch { $raw = "" }
  if (-not $raw -and $args.Count -gt 0) { $raw = [string]$args[0] }
}
$j = $null
try { if ($raw) { $j = $raw | ConvertFrom-Json } } catch {}

$pidStr = ""
$executionId = ""
$callbackUrl = ""
if ($j -and $j.parameters -and $j.parameters.extra_args) {
  $pidStr = [string]$j.parameters.extra_args[0]
  if ($j.parameters.extra_args.Count -gt 1) { $executionId = [string]$j.parameters.extra_args[1] }
  if ($j.parameters.extra_args.Count -gt 2) { $callbackUrl = [string]$j.parameters.extra_args[2] }
} elseif ($j -and $j.arguments) {
  $pidStr = [string]$j.arguments[0]
  if ($j.arguments.Count -gt 1) { $executionId = [string]$j.arguments[1] }
  if ($j.arguments.Count -gt 2) { $callbackUrl = [string]$j.arguments[2] }
} elseif ($args.Count -gt 0 -and $args[0] -match '^\d+$') {
  $pidStr = [string]$args[0]
  if ($args.Count -gt 1) { $executionId = [string]$args[1] }
  if ($args.Count -gt 2) { $callbackUrl = [string]$args[2] }
}

if (-not $callbackUrl) {
  $envMap = Get-EnvMap
  $callbackUrl = [string]$envMap['MSSP_CALLBACK_URL']
}

if ($pidStr -notmatch '^\d+$') {
  Write-ArLog "invalid pid=$pidStr"
  Send-Callback $callbackUrl $executionId $false "invalid pid=$pidStr"
  exit 1
}
$targetPid = [int]$pidStr
if ($targetPid -le 4) {
  Write-ArLog "refusing system pid=$targetPid"
  Send-Callback $callbackUrl $executionId $false "refusing system pid=$targetPid"
  exit 1
}

# Already gone = success (idempotent)
$existing = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if (-not $existing) {
  Write-ArLog "pid=$targetPid already gone"
  Send-Callback $callbackUrl $executionId $true "pid=$targetPid already gone"
  exit 0
}

$proc = Start-Process -FilePath "taskkill.exe" -ArgumentList @("/PID", "$targetPid", "/F") -Wait -PassThru -WindowStyle Hidden
if ($proc.ExitCode -eq 0) {
  Write-ArLog "killed pid=$targetPid"
  Send-Callback $callbackUrl $executionId $true "killed pid=$targetPid"
  exit 0
}

# Race: process exited between check and taskkill
$still = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if (-not $still) {
  Write-ArLog "pid=$targetPid gone after taskkill code=$($proc.ExitCode)"
  Send-Callback $callbackUrl $executionId $true "pid=$targetPid gone"
  exit 0
}

Write-ArLog "kill failed pid=$targetPid code=$($proc.ExitCode)"
Send-Callback $callbackUrl $executionId $false "kill failed pid=$targetPid code=$($proc.ExitCode)"
exit 1
