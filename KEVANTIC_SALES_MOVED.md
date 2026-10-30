# Kevantic Sales Cloud — relocated

This CRM is **no longer under** `/opt/mssp-control/`.

**New home:** `/home/secadmin/kevantic-sales`  
Standalone deploy tree — migrate this folder independently of mssp-control.

```bash
cd /home/secadmin/kevantic-sales
docker compose up -d --build
# UI: http://192.168.0.201:8090/
```

Version **2.1.0** includes Vendor master, PO lifecycle, GRN, and Vendor Bills (AP).
