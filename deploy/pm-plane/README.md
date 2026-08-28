# Kevantic PM Stack — Plane on VirtualBox (laptop)

Self-hosted **Plane** (free, AGPL) for tracking MSSP platform work: phases, issues, design links, and releases.

**Target host:** Your Windows laptop (16 GB RAM) → VirtualBox VM with **4 GB RAM**, **2 vCPUs**, **40 GB disk**.

**Access after install:** `http://localhost:8080` (port-forwarded from the VM).

---

## What you get

| Component | Purpose |
|-----------|---------|
| Ubuntu 24.04 VM | Isolated PM host (does not touch VM 100 / production) |
| Docker + Plane CE | Issues, cycles, modules, roadmap, pages |
| Pre-written bootstrap | Kevantic workspace/project template |

---

## Prerequisites (Windows laptop)

1. **Oracle VirtualBox** 7.x installed ([download](https://www.virtualbox.org/wiki/Downloads))
2. **PowerShell** (Run as Administrator for VM creation script)
3. **~45 GB free disk** (ISO + VM disk + Docker images)
4. Internet on the laptop

Optional: clone or copy this folder from the repo:

```text
/opt/mssp-control/deploy/pm-plane/
```

On Windows, e.g. `C:\dev\mssp-platform\deploy\pm-plane\`

---

## End-to-end (recommended path)

### Step 1 — Create the VirtualBox VM (Windows, Admin PowerShell)

```powershell
cd C:\path\to\mssp-platform\deploy\pm-plane\windows
Set-ExecutionPolicy -Scope Process Bypass
.\New-KevanticPmVm.ps1
```

This script:

- Downloads Ubuntu 24.04 Server ISO (if missing)
- Creates VM `kevantic-pm` (4096 MB RAM, 2 CPUs, 40 GB disk)
- Attaches ISO, enables NAT port forward **host 8080 → guest 80**
- Starts the VM

### Step 2 — Install Ubuntu (first boot, VM console)

1. Choose **Install Ubuntu Server**
2. Hostname: `kevantic-pm`
3. User: `pmadmin` (or your choice — scripts assume `pmadmin`)
4. Enable **OpenSSH server**
5. Use entire disk, no LVM complications needed
6. Reboot when prompted; **remove ISO** from VirtualBox storage if the installer asks

### Step 3 — Copy install scripts into the VM

From Windows PowerShell (adjust IP if using bridged networking instead of NAT):

```powershell
# After Ubuntu install, find guest IP (optional if using only localhost:8080):
# VBoxManage guestproperty get kevantic-pm /VirtualBox/GuestInfo/Net/0/V4/IP

scp -r ..\vm pmadmin@127.0.0.1:~/pm-plane-vm
# If SSH via NAT doesn't work, use VirtualBox shared folder or paste scripts manually.
```

**Easier:** In VirtualBox → VM Settings → Shared Folders → add `deploy\pm-plane\vm` as `pm-plane` (auto-mount). Then in the guest:

```bash
sudo mkdir -p /mnt/pm-plane
sudo mount -t vboxsf pm-plane /mnt/pm-plane
cp -r /mnt/pm-plane/* ~/pm-plane-vm/
```

### Step 4 — Install Docker + Plane (inside Ubuntu VM)

```bash
cd ~/pm-plane-vm
chmod +x *.sh
sudo ./install-docker.sh
# Log out and back in so docker group applies, OR:
newgrp docker

./install-plane.sh
```

Wait 3–8 minutes for images to pull. When done, open on the laptop:

**http://localhost:8080**

### Step 5 — First login & workspace

1. Create admin account (first user = instance admin)
2. Create workspace: **Kevantic**
3. Follow `docs/KEVANTIC_PM_BOOTSTRAP.md` to create projects/phases

---

## Ports & networking

| Where | URL |
|-------|-----|
| Laptop browser | `http://localhost:8080` |
| VM internal | `http://127.0.0.1:80` (Plane listens on 80 inside guest) |
| SSH (optional) | Forward host `2222` → guest `22` if you enable it in the PS script |

To reach Plane from another machine on your LAN, change VM network to **Bridged Adapter** in VirtualBox and set `WEB_URL` / `CORS_ALLOWED_ORIGINS` in `~/plane-app/plane.env` to `http://<VM-LAN-IP>`.

---

## Operations

Inside the VM, Plane lives in `~/plane-app/`:

```bash
cd ~/plane-app
../plane-setup.sh   # symlink created by install-plane.sh
# Menu: 2=Start, 3=Stop, 5=Upgrade, 7=Backup
```

**Backup:** Plane setup option 7, or snapshot the VM in VirtualBox.

**RAM:** If the VM feels slow, close other laptop apps; do not run this VM on VM 100.

---

## Why Plane (not OpenProject) here

- Fits **software delivery** (issues ↔ GitHub)
- Lighter than OpenProject on a **4 GB** VM
- Fully free self-hosted (Community Edition)
- OpenProject remains an option later on a bigger VM if you need Gantt/time-tracking suite

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `localhost:8080` refused | VM running? `VBoxManage list runningvms`. Plane started? `./setup.sh` → 2 |
| Docker permission denied | `sudo usermod -aG docker $USER` then re-login |
| Plane OOM on 4 GB | Stop other containers; ensure VM has full 4096 MB in VirtualBox settings |
| CORS errors after IP change | Edit `~/plane-app/plane.env`: `WEB_URL` and `CORS_ALLOWED_ORIGINS` must match browser URL |

---

## Files in this package

```text
deploy/pm-plane/
├── README.md                 ← this file
├── windows/
│   └── New-KevanticPmVm.ps1  ← VirtualBox VM creator (Windows)
├── vm/
│   ├── install-docker.sh
│   ├── install-plane.sh
│   └── plane.env.kevantic    ← starter env (copied into plane-app)
└── docs/
    └── KEVANTIC_PM_BOOTSTRAP.md  ← initial projects & phases
```
