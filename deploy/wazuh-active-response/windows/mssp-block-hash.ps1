# MSSP Windows Active Response - AppLocker Publisher/Hash deny + callback proof.
$ErrorActionPreference = "Continue"
$LogCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\active-response\active-responses.log",
  "$env:ProgramFiles\ossec-agent\active-response\active-responses.log"
)
$ListCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\etc\mssp_blocked_hashes.txt",
  "$env:ProgramFiles\ossec-agent\etc\mssp_blocked_hashes.txt"
)
$EnvCandidates = @(
  "${env:ProgramFiles(x86)}\ossec-agent\etc\mssp-ar.env",
  "$env:ProgramFiles\ossec-agent\etc\mssp-ar.env"
)
$Log = $LogCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $Log) { $Log = $LogCandidates[0] }
$List = $ListCandidates | Where-Object { Test-Path (Split-Path $_ -Parent) } | Select-Object -First 1
if (-not $List) { $List = $ListCandidates[0] }
$EnvFile = $EnvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

function Write-ArLog([string]$Message) {
  try {
    $dir = Split-Path $Log -Parent
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy/MM/dd HH:mm:ss")
    Add-Content -LiteralPath $Log -Value "$ts mssp-block-hash: $Message"
  } catch {}
}

function Get-EnvMap {
  $map = @{}
  if (-not $EnvFile) { return $map }
  Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $p = $_.Split('=',2); $map[$p[0].Trim()] = $p[1].Trim().Trim('"')
  }
  return $map
}

function Send-Callback([string]$Url, [string]$ExecutionId, [bool]$Applied, [string]$Message) {
  if (-not $Url -or -not $ExecutionId) { return }
  $envMap = Get-EnvMap
  $key = $envMap['MSSP_CALLBACK_KEY']; if (-not $key) { $key = $envMap['EDR_CALLBACK_API_KEY'] }
  $body = @{
    execution_id = $ExecutionId
    status = $(if ($Applied) { 'success' } else { 'failed' })
    message = $Message
    payload = @{ applied = $Applied; action = 'BLOCK_HASH' }
  } | ConvertTo-Json -Compress
  try {
    $headers = @{ 'Content-Type' = 'application/json' }
    if ($key) { $headers['X-EDR-Callback-Key'] = $key; $headers['X-SOC-Sync-Key'] = $key }
    Invoke-RestMethod -Method Post -Uri $Url -Body $body -Headers $headers -TimeoutSec 8 | Out-Null
    Write-ArLog "callback ok applied=$Applied"
  } catch {
    Write-ArLog "callback failed: $($_.Exception.Message)"
  }
}

$raw = ""
if ($args.Count -gt 0 -and $args[0] -match '[\{\[]') { $raw = [string]$args[0] }
else { try { $raw = [Console]::In.ReadLine() } catch { $raw = "" } }
$j = $null
try { if ($raw) { $j = $raw | ConvertFrom-Json } } catch {}

$hash = ""; $executionId = ""; $callbackUrl = ""
if ($j -and $j.parameters -and $j.parameters.extra_args) {
  $hash = [string]$j.parameters.extra_args[0]
  if ($j.parameters.extra_args.Count -gt 1) { $executionId = [string]$j.parameters.extra_args[1] }
  if ($j.parameters.extra_args.Count -gt 2) { $callbackUrl = [string]$j.parameters.extra_args[2] }
} elseif ($args.Count -gt 0) {
  $hash = [string]$args[0]
  if ($args.Count -gt 1) { $executionId = [string]$args[1] }
  if ($args.Count -gt 2) { $callbackUrl = [string]$args[2] }
}
$hash = $hash.Trim().ToLowerInvariant()
if ($hash -notmatch '^[a-f0-9]{64}$') {
  Write-ArLog "invalid hash=$hash"
  Send-Callback $callbackUrl $executionId $false "invalid hash"
  exit 1
}

$dir = Split-Path $List -Parent
if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$existing = @()
if (Test-Path -LiteralPath $List) {
  $existing = Get-Content -LiteralPath $List | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}
if ($existing -notcontains $hash) { Add-Content -LiteralPath $List -Value $hash }

$enforced = $false
$detail = "denylist"
try {
  # AppLocker hash rule via PowerShell policy (requires AppLocker service / Enterprise SKU).
  $policyDir = "C:\Windows\System32\AppLocker"
  if (Get-Command Get-AppLockerPolicy -ErrorAction SilentlyContinue) {
    $xmlPath = Join-Path $env:ProgramData "MSSP\AppLocker-mssp-hashes.xml"
    New-Item -ItemType Directory -Force -Path (Split-Path $xmlPath) | Out-Null
    $ruleId = [guid]::NewGuid().ToString()
    $xml = @"
<AppLockerPolicy Version="1">
  <RuleCollection Type="Exe" EnforcementMode="Enabled">
    <FileHashRule Id="$ruleId" Name="MSSP Block $hash" Description="MSSP block-hash" UserOrGroupSid="S-1-1-0" Action="Deny">
      <Conditions>
        <FileHashCondition>
          <FileHash Type="SHA256" Data="0x$hash" SourceFileName="blocked.bin" SourceFileLength="0" />
        </FileHashCondition>
      </Conditions>
    </FileHashRule>
  </RuleCollection>
</AppLockerPolicy>
"@
    Set-Content -LiteralPath $xmlPath -Value $xml -Encoding UTF8
    try {
      Set-AppLockerPolicy -XmlPolicy $xmlPath -Merge -ErrorAction Stop
      $enforced = $true
      $detail = "applocker+denylist"
    } catch {
      $detail = "denylist; applocker_set_failed=$($_.Exception.Message)"
    }
  } else {
    $detail = "denylist; applocker_cmd_unavailable"
  }
} catch {
  $detail = "denylist; enforce_error=$($_.Exception.Message)"
}

Write-ArLog "hash blocked=$hash $detail enforced=$enforced"
Send-Callback $callbackUrl $executionId $true "hash blocked=$hash; $detail"
exit 0
