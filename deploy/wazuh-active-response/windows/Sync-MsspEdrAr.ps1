#Requires -RunAsAdministrator
# Copy Manager-shared EDR Active Response files into the agent bin folder.
# Isolate must always run the current hold-until-unisolate script, never a stale
# copy that auto-lifts after two minutes.
$ErrorActionPreference = "SilentlyContinue"
$roots = @(
  "${env:ProgramFiles(x86)}\ossec-agent",
  "$env:ProgramFiles\ossec-agent"
)
$root = $roots | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $root) { exit 0 }
$shared = Join-Path $root "shared"
$bin = Join-Path $root "active-response\bin"
if (-not (Test-Path -LiteralPath $bin)) {
  New-Item -ItemType Directory -Path $bin -Force | Out-Null
}
$files = @(
  "mssp-isolate-host.cmd", "mssp-isolate-host.ps1",
  "mssp-kill-process.cmd", "mssp-kill-process.ps1",
  "mssp-block-hash.cmd", "mssp-block-hash.ps1",
  "Sync-MsspEdrAr.ps1"
)
foreach ($f in $files) {
  $src = Join-Path $shared $f
  if (Test-Path -LiteralPath $src) {
    Copy-Item -LiteralPath $src -Destination (Join-Path $bin $f) -Force
  }
}
exit 0
