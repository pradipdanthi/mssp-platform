# MSSP Windows Active Response - kill by live PID or image name + callback.
# Invoked by Wazuh execd via mssp-kill-process.cmd
# Args (extra_args):
#   [pid, execution_id, callback_url]              — kill one PID (must still be running)
#   [name=notepad.exe, execution_id, callback_url] — resolve LIVE via Get-Process, then kill
#   [enum=notepad.exe, execution_id, callback_url] — list live matches only (no kill)
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
  $files = @()
  if ($EnvFile) { $files += $EnvFile }
  $files += @(
    "${env:ProgramFiles(x86)}\ossec-agent\shared\mssp-ar.env.defaults",
    "$env:ProgramFiles\ossec-agent\shared\mssp-ar.env.defaults",
    "${env:ProgramFiles(x86)}\ossec-agent\shared\mssp-ar.env",
    "$env:ProgramFiles\ossec-agent\shared\mssp-ar.env"
  )
  foreach ($f in $files) {
    if (-not (Test-Path -LiteralPath $f)) { continue }
    Get-Content -LiteralPath $f -ErrorAction SilentlyContinue | ForEach-Object {
      if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
      $p = $_.Split('=', 2)
      if ($p.Count -ge 2 -and -not $map.ContainsKey($p[0].Trim())) {
        $map[$p[0].Trim()] = $p[1].Trim().Trim('"').Trim("'")
      }
    }
  }
  if (-not $map['MSSP_CALLBACK_KEY']) {
    foreach ($kf in @(
      "${env:ProgramFiles(x86)}\ossec-agent\shared\mssp-callback.key",
      "$env:ProgramFiles\ossec-agent\shared\mssp-callback.key",
      "$env:ProgramData\mssp-edr-ar\mssp-callback.key"
    )) {
      if (Test-Path -LiteralPath $kf) {
        $map['MSSP_CALLBACK_KEY'] = (Get-Content -LiteralPath $kf -Raw).Trim()
        if ($map['MSSP_CALLBACK_KEY']) { break }
      }
    }
  }
  return $map
}

function Send-Callback(
  [string]$Url,
  [string]$ExecutionId,
  [bool]$Applied,
  [string]$Message,
  [object]$Processes = $null,
  [string]$Action = "KILL_PROCESS"
) {
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
  $payload = @{ applied = $Applied; action = $Action }
  if ($null -ne $Processes) { $payload['processes'] = @($Processes) }
  $body = @{
    execution_id = $ExecutionId
    status = $(if ($Applied) { 'success' } else { 'failed' })
    message = $Message
    applied = $Applied
    payload = $payload
  } | ConvertTo-Json -Compress -Depth 6
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

function Normalize-ImageName([string]$Name) {
  $n = ($Name -replace '^name=', '' -replace '^enum=', '').Trim()
  if ($n -match '(?i)\.exe$') { return $n }
  return "$n.exe"
}

function Get-LiveProcessesByName([string]$ImageName) {
  $base = [IO.Path]::GetFileNameWithoutExtension($ImageName)
  $found = @()
  try {
    $procs = Get-Process -Name $base -ErrorAction SilentlyContinue
  } catch {
    $procs = @()
  }
  foreach ($p in @($procs)) {
    if ($p.Id -le 4) { continue }
    $path = ""
    try { $path = [string]$p.Path } catch { $path = "" }
    $found += @{
      pid = [int]$p.Id
      name = [string]$p.ProcessName
      path = $path
    }
  }
  return $found
}

function Stop-LivePid([int]$TargetPid) {
  if ($TargetPid -le 4) { return $false }
  $existing = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
  if (-not $existing) { return $false }
  $proc = Start-Process -FilePath "taskkill.exe" -ArgumentList @("/PID", "$TargetPid", "/F") `
    -Wait -PassThru -WindowStyle Hidden
  if ($proc.ExitCode -eq 0) { return $true }
  $still = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
  return -not [bool]$still
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

$target = ""
$executionId = ""
$callbackUrl = ""
if ($j -and $j.parameters -and $j.parameters.extra_args) {
  $target = [string]$j.parameters.extra_args[0]
  if ($j.parameters.extra_args.Count -gt 1) { $executionId = [string]$j.parameters.extra_args[1] }
  if ($j.parameters.extra_args.Count -gt 2) { $callbackUrl = [string]$j.parameters.extra_args[2] }
} elseif ($j -and $j.arguments) {
  $target = [string]$j.arguments[0]
  if ($j.arguments.Count -gt 1) { $executionId = [string]$j.arguments[1] }
  if ($j.arguments.Count -gt 2) { $callbackUrl = [string]$j.arguments[2] }
} elseif ($args.Count -gt 0) {
  $target = [string]$args[0]
  if ($args.Count -gt 1) { $executionId = [string]$args[1] }
  if ($args.Count -gt 2) { $callbackUrl = [string]$args[2] }
}

if (-not $callbackUrl) {
  $envMap = Get-EnvMap
  $callbackUrl = [string]$envMap['MSSP_CALLBACK_URL']
}

$target = ($target -replace '^\s+|\s+$', '')
if (-not $target) {
  Write-ArLog "missing target"
  Send-Callback $callbackUrl $executionId $false "missing kill target"
  exit 1
}

# Live enum (no kill) — used by control-plane process discovery.
if ($target -match '^(?i)enum=') {
  $image = Normalize-ImageName $target
  $matches = @(Get-LiveProcessesByName $image)
  Write-ArLog "enum image=$image count=$($matches.Count)"
  if ($matches.Count -gt 0) {
    Send-Callback $callbackUrl $executionId $true "live processes name=$image count=$($matches.Count)" `
      -Processes $matches -Action "LIST_PROCESSES"
    exit 0
  }
  Send-Callback $callbackUrl $executionId $false "no live process named $image" `
    -Processes @() -Action "LIST_PROCESSES"
  exit 1
}

# Kill by live image name (preferred — avoids stale syscollector PIDs).
if ($target -match '^(?i)name=' -or $target -notmatch '^\d+$') {
  $image = Normalize-ImageName $target
  $matches = @(Get-LiveProcessesByName $image)
  if ($matches.Count -lt 1) {
    Write-ArLog "no live process named $image"
    Send-Callback $callbackUrl $executionId $false "no live process named $image" -Processes @()
    exit 1
  }
  $killed = @()
  $failed = @()
  foreach ($m in $matches) {
    $pidNum = [int]$m.pid
    if (Stop-LivePid $pidNum) {
      $killed += $pidNum
      Write-ArLog "killed pid=$pidNum name=$image"
    } else {
      $failed += $pidNum
      Write-ArLog "kill failed pid=$pidNum name=$image"
    }
  }
  if ($killed.Count -gt 0) {
    Send-Callback $callbackUrl $executionId $true `
      ("killed name=$image pids=" + ($killed -join ",")) -Processes $matches
    exit 0
  }
  Send-Callback $callbackUrl $executionId $false `
    ("kill failed name=$image pids=" + ($failed -join ",")) -Processes $matches
  exit 1
}

# Kill by PID — process must still be running (do not treat missing PID as success;
# that hid stale syscollector PIDs as "verified").
$targetPid = [int]$target
if ($targetPid -le 4) {
  Write-ArLog "refusing system pid=$targetPid"
  Send-Callback $callbackUrl $executionId $false "refusing system pid=$targetPid"
  exit 1
}
$existing = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
if (-not $existing) {
  Write-ArLog "pid=$targetPid not running (stale inventory?)"
  Send-Callback $callbackUrl $executionId $false "pid=$targetPid not running (stale inventory?)"
  exit 1
}
if (Stop-LivePid $targetPid) {
  Write-ArLog "killed pid=$targetPid"
  Send-Callback $callbackUrl $executionId $true "killed pid=$targetPid" `
    -Processes @(@{ pid = $targetPid; name = [string]$existing.ProcessName })
  exit 0
}
Write-ArLog "kill failed pid=$targetPid"
Send-Callback $callbackUrl $executionId $false "kill failed pid=$targetPid"
exit 1
