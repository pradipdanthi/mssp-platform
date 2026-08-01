# Run as Administrator on Windows lab VM 104.
$ErrorActionPreference = "Stop"
$Root = "C:\Program Files\MSSP\Velociraptor"
New-Item -ItemType Directory -Force -Path $Root | Out-Null
$Cfg = Join-Path $Root "client.config.yaml"
Copy-Item -Force "$PSScriptRoot\client.config.yaml" $Cfg
$Bin = Join-Path $Root "velociraptor.exe"
if (-not (Test-Path $Bin)) {
  Write-Host "Download Velociraptor Windows amd64 release v0.77.1 into $Bin then re-run."
  Write-Host "https://github.com/Velocidex/velociraptor/releases/download/v0.77.1/velociraptor-v0.77.1-windows-amd64.exe"
  exit 1
}
& sc.exe create VelociraptorClient binPath= "`"$Bin`" --config `"$Cfg`" client -v" start= auto
& sc.exe start VelociraptorClient
Write-Host "Velociraptor client service started"
