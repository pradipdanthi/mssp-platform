# Velociraptor client install pack (VM 104 Windows)

1. On control plane, pull fresh client config from VM 110:

```bash
ssh -i ~/.ssh/id_ed25519_velociraptor secadmin@192.168.0.220 \
  'sudo cat /opt/mssp-velociraptor/clients/client.config.yaml' \
  > deploy/velociraptor-client/client.config.yaml
```

2. Download Velociraptor **v0.77.1** Windows amd64 into the same folder as `velociraptor.exe`.

3. Copy this folder to Windows lab VM **104** and run `Install-WindowsClient.ps1` as Administrator.

Linux lab VM **105** is enrolled via `scripts/kb110_enroll_velociraptor_clients.sh`.

Do **not** commit `client.config.yaml` (contains CA material for your lab server).
