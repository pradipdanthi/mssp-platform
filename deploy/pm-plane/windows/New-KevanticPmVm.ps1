#Requires -Version 5.1
<#
.SYNOPSIS
  Create kevantic-pm VirtualBox VM for Plane (Ubuntu 24.04, 4GB RAM).

.NOTES
  Run PowerShell as Administrator.
  Requires Oracle VirtualBox (VBoxManage on PATH).
#>
$ErrorActionPreference = "Stop"

$VmName = "kevantic-pm"
$MemoryMb = 4096
$Cpus = 2
$DiskGb = 40
$IsoUrl = "https://releases.ubuntu.com/24.04/ubuntu-24.04.3-live-server-amd64.iso"
$IsoDir = Join-Path $env:USERPROFILE "Downloads"
$IsoPath = Join-Path $IsoDir "ubuntu-24.04.3-live-server-amd64.iso"
$VmFolder = Join-Path $env:USERPROFILE "VirtualBox VMs" $VmName
$DiskPath = Join-Path $VmFolder "$VmName.vdi"

function Assert-VBox {
    if (-not (Get-Command VBoxManage -ErrorAction SilentlyContinue)) {
        throw "VBoxManage not found. Install Oracle VirtualBox and ensure it is on PATH."
    }
}

function Ensure-Iso {
    if (Test-Path $IsoPath) { return }
    New-Item -ItemType Directory -Force -Path $IsoDir | Out-Null
    Write-Host "Downloading Ubuntu 24.04 Server ISO (~2.5 GB) to $IsoPath ..."
    Invoke-WebRequest -Uri $IsoUrl -OutFile $IsoPath -UseBasicParsing
}

Assert-VBox

$existing = & VBoxManage list vms 2>$null | Select-String "`"$VmName`""
if ($existing) {
    Write-Host "VM '$VmName' already exists."
    $running = & VBoxManage list runningvms 2>$null | Select-String "`"$VmName`""
    if (-not $running) {
        Write-Host "Starting existing VM..."
        & VBoxManage startvm $VmName --type headless
    }
    Write-Host "Open VirtualBox console or wait for Ubuntu install, then run vm/install scripts."
    Write-Host "Plane URL (after install): http://localhost:8080"
    exit 0
}

Ensure-Iso
New-Item -ItemType Directory -Force -Path $VmFolder | Out-Null

Write-Host "Creating VM $VmName ($MemoryMb MB RAM, $Cpus CPUs)..."
& VBoxManage createvm --name $VmName --register --ostype "Ubuntu_64"
& VBoxManage modifyvm $VmName --memory $MemoryMb --cpus $Cpus --vram 16 --graphicscontroller vmsvga
& VBoxManage modifyvm $VmName --boot1 dvd --boot2 disk --boot3 none --boot4 none
& VBoxManage modifyvm $VmName --nic1 nat --audio none --usb off
# Plane web UI: laptop http://localhost:8080 -> guest :80
& VBoxManage modifyvm $VmName --natpf1 "plane-web,tcp,,8080,,80"
# Optional SSH: laptop localhost:2222 -> guest :22
& VBoxManage modifyvm $VmName --natpf1 "ssh,tcp,,2222,,22"

if (-not (Test-Path $DiskPath)) {
    Write-Host "Creating ${DiskGb}GB disk..."
    & VBoxManage createmedium disk --filename $DiskPath --size ($DiskGb * 1024) --format VDI
}

& VBoxManage storagectl $VmName --name "SATA" --add sata --controller IntelAhci --portcount 2
& VBoxManage storageattach $VmName --storagectl "SATA" --port 0 --device 0 --type hdd --medium $DiskPath
& VBoxManage storageattach $VmName --storagectl "SATA" --port 1 --device 0 --type dvddrive --medium $IsoPath

Write-Host "Starting VM (headless). Open VirtualBox Manager for console if needed."
& VBoxManage startvm $VmName --type gui

Write-Host @"

================================================================================
VM '$VmName' created and started.

NEXT STEPS:
  1. In the VM console: Install Ubuntu Server 24.04
     - Enable OpenSSH server
     - User: pmadmin (recommended)
  2. Copy deploy/pm-plane/vm/ into the guest (shared folder or scp)
  3. Run: sudo ./install-docker.sh && ./install-plane.sh
  4. Open on this laptop: http://localhost:8080

Optional SSH (after install): ssh -p 2222 pmadmin@127.0.0.1
================================================================================
"@
