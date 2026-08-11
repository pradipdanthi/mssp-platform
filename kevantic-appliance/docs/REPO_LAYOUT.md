# Kevantic Appliance — Repository Layout

Status: Design scaffold (KB-093). No production ISO yet.

```
kevantic-appliance/
├── README.md
├── VERSION                          # appliance software train (e..g. 0.1.0-dev)
├── appliance/                       # Edge engine (KB-093E)
│   ├── datalake/                    # DuckDB + ZSTD Parquet archiver/query
│   ├── telemetry/                   # Anonymizing forwarder + buffer
│   ├── hunting/                     # Retrospective IOC sweeper
│   ├── api/                         # Local job REST (loopback)
│   └── common/                      # paths, metadata SQLite, privacy
├── docs/
│   ├── REPO_LAYOUT.md               # this file
│   ├── KEVANTIC_CLI_SPEC.md          # CLI contract
│   ├── B2_PACKER_DISPOSABLE_VM.md
│   ├── PACKAGE_PURGE_LIST.md        # packages removed / retained
│   └── SERVICE_MATRIX.md            # services 1–10 ↔ local components
├── packer/
│   ├── ubuntu-lts.pkr.hcl           # ISO / QEMU / Proxmox / Hyper-V builders
│   ├── vars/
│   │   └── appliance.pkrvars.hcl.example
│   ├── http/
│   │   ├── user-data                # Subiquity autoinstall (minimal)
│   │   └── meta-data
│   └── scripts/
│       ├── 00-minimize-bootstrap.sh
│       ├── 10-install-ansible-deps.sh
│       └── 99-cleanup-shrink.sh
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/
│   │   └── localhost.ini
│   ├── group_vars/
│   │   └── all.yml
│   ├── playbooks/
│   │   ├── site.yml                 # full appliance image provision
│   │   ├── harden.yml
│   │   ├── runtime.yml
│   │   └── services.yml             # enable subscribed modules only
│   └── roles/
│       ├── minimize/                # purge packages, mask units
│       ├── harden_cis/              # CIS Level 2 Server
│       ├── firewall_nftables/       # default-deny inbound
│       ├── apparmor_profiles/
│       ├── auditd/
│       ├── container_runtime/       # Podman preferred (rootless where possible)
│       ├── kevantic_runtime/         # dirs, users, base units
│       ├── channel_agent/           # outbound mTLS channel daemon
│       ├── license_enforcer/        # verify signed entitlements
│       ├── service_manager/         # start/stop modular services 01–10
│       ├── wazuh_local/             # local Manager/Fluent Bit staging
│       └── ota_staging/             # local package + WPK cache
├── hardening/
│   ├── cis/                         # benchmark overlays / exceptions register
│   ├── apparmor/                    # profiles for kevantic-* daemons
│   ├── nftables/
│   │   └── kevantic-appliance.nft
│   └── auditd/
│       └── kevantic.rules
├── services/                        # one folder per Kevantic service module
│   ├── 01-log-event/                # Core LEM
│   ├── 02-ir-worker/                # local remediation worker
│   ├── 03-automation/               # containment / active response bridge
│   ├── 04-vmaas/                    # agentless scan + syscollector aggregate
│   ├── 05-compliance/               # SCA parser / CaaS
│   ├── 06-ndr/                      # Suricata/Zeek (SPAN/TAP)
│   ├── 07-threat-intel/             # local IOC cache
│   ├── 08-forensics/                # FIM / deception listener glue
│   ├── 09-easm/                     # internal perimeter probes
│   └── 10-itdr/                     # AD/LDAP + identity connectors
├── channel/
│   ├── proto/                       # optional protobuf IDL
│   └── schemas/                     # JSON Schema for control/data frames
├── licensing/
│   ├── keys/                        # PLACEHOLDERS ONLY — public verify keys
│   └── payloads/                    # example signed entitlement envelopes
├── ota/
│   ├── manifests/                   # signed update manifests
│   ├── staging/                     # local cache layout docs
│   └── wpk/                         # Wazuh WPK staging layout
├── cli/
│   └── kevantic-cli/                 # Go (preferred) or Python CLI sources
│       ├── cmd/
│       └── internal/{config,license,channel,fingerprint,wipe}/
├── configs/systemd/                 # unit templates shipped to image
├── scripts/                         # operator helpers (build, sign, promote)
├── tests/
│   ├── unit/
│   ├── integration/                 # register → channel → entitlement
│   ├── security/                    # port scan, CIS checks, wipe proof
│   └── fixtures/
└── ci/
    ├── github/                      # workflow templates
    └── scripts/                     # ephemeral VM boot + smoke
```

## Naming conventions

| Item | Rule |
|------|------|
| ISO | `Kevantic-Appliance-v{MAJOR}.{MINOR}.iso` |
| Service id | `svc-01` … `svc-10` (stable; never rename) |
| Systemd units | `kevantic-channeld.service`, `kevantic-svc-NN-*.service` |
| Container images | `registry.kevantic.com/appliance/<svc>:<version>` (pulled over mTLS channel or signed OTA) |
| Config root | `/etc/kevantic/` |
| Data root | `/var/lib/kevantic/` |
| Secrets | `/var/lib/kevantic/secrets/` (0600, not in Git) |
| OTA cache | `/var/lib/kevantic/ota/` |
| WPK cache | `/var/lib/kevantic/wpk/` |

## Relationship to `/opt/mssp-control/templates/on-prem-appliance/`

KB-058 remains the **thin Compose placeholder** downloadable from Admin today.  
This `kevantic-appliance/` tree is the **full hardened ISO product** that replaces that placeholder for production field deployment. Until the first ISO ship, field use may still start from the KB-058 template for lab registration tests.
