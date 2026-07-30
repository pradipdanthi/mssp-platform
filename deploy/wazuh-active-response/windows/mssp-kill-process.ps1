# MSSP Windows Active Response - kill process by PID (no Python).
# Invoked by Wazuh execd via mssp-kill-process.cmd
$ErrorActionPreference = "Continue"
$LogCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\active-responses.log",
  "$env:ProgramFiles\ossec-agent\active-response\active-responses.log"
)
$Log = $LogCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $Log) { $Log = $LogCandidates[0] }

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
if ($j -and $j.parameters -and $j.parameters.extra_args) {
  $pidStr = [string]$j.parameters.extra_args[0]
} elseif ($j -and $j.arguments) {
  $pidStr = [string]$j.arguments[0]
} elseif ($args.Count -gt 0 -and $args[0] -match '^\d+$') {
  $pidStr = [string]$args[0]
}

if ($pidStr -notmatch '^\d+$') {
  Write-ArLog "invalid pid=$pidStr"
  exit 1
}
$targetPid = [int]$pidStr
if ($targetPid -le 4) {
  Write-ArLog "refusing system pid=$targetPid"
  exit 1
}

$proc = Start-Process -FilePath "taskkill.exe" -ArgumentList @("/PID", "$targetPid", "/F") -Wait -PassThru -WindowStyle Hidden
if ($proc.ExitCode -eq 0) {
  Write-ArLog "killed pid=$targetPid"
  exit 0
}
Write-ArLog "kill failed pid=$targetPid code=$($proc.ExitCode)"
exit 1
