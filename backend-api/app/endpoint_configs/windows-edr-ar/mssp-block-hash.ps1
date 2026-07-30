# MSSP Windows Active Response - append SHA256 denylist entry (no Python).
$ErrorActionPreference = "Continue"
$LogCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\active-responses.log",
  "$env:ProgramFiles\ossec-agent\active-response\active-responses.log"
)
$ListCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\etc\mssp_blocked_hashes.txt",
  "$env:ProgramFiles\ossec-agent\etc\mssp_blocked_hashes.txt"
)
$Log = $LogCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $Log) { $Log = $LogCandidates[0] }
$List = $ListCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $List) { $List = $ListCandidates[0] }

function Write-ArLog([string]$Message) {
  try {
    $dir = Split-Path $Log -Parent
    if (-not (Test-Path -LiteralPath $dir)) {
      New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy/MM/dd HH:mm:ss")
    $line = "$ts mssp-block-hash: $Message`r`n"
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
}
$j = $null
try { if ($raw) { $j = $raw | ConvertFrom-Json } } catch {}

$hash = ""
if ($j -and $j.parameters -and $j.parameters.extra_args) {
  $hash = [string]$j.parameters.extra_args[0]
} elseif ($j -and $j.arguments) {
  $hash = [string]$j.arguments[0]
} elseif ($args.Count -gt 0) {
  $hash = [string]$args[0]
}
$hash = $hash.Trim().ToLowerInvariant()
if ($hash -notmatch '^[a-f0-9]{64}$') {
  Write-ArLog "invalid hash=$hash"
  exit 1
}

$dir = Split-Path $List -Parent
if (-not (Test-Path -LiteralPath $dir)) {
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
}
$existing = @()
if (Test-Path -LiteralPath $List) {
  $existing = Get-Content -LiteralPath $List | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}
if ($existing -contains $hash) {
  Write-ArLog "hash already listed"
  exit 0
}
Add-Content -LiteralPath $List -Value $hash
Write-ArLog "hash blocked=$hash"
exit 0
