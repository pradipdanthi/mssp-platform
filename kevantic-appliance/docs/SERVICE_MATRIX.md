# Kevantic 10-Service Matrix (Appliance)

| ID | Commercial name | Local runtime | Endpoint (wazuh-agent) | Agentless |
|----|-----------------|---------------|--------------------------|-----------|
| svc-01 | Log & Event Monitoring | Manager, Fluent Bit, collectors | Ship events to local Manager | Syslog/API collectors |
| svc-02 | IR local worker only | `ir-worker` (jobs) — **no TheHive / no tickets** | AR scripts when job says so | — |
| svc-03 | Security Automation | Orchestration worker | Active Response | Network device APIs |
| svc-04 | VMaaS | Scanner + inventory aggregator | syscollector | Network scan |
| svc-05 | CaaS | SCA aggregator | SCA module | — |
| svc-06 | NDR | Suricata + Zeek | — | SPAN/TAP |
| svc-07 | Threat Intel | Local IOC cache | — | Feed sync via channel |
| svc-08 | Forensics & Deception | Collection listener | FIM / deception rules | — |
| svc-09 | EASM | Probe runner | — | Internal probes |
| svc-10 | ITDR | AD/LDAP/IdP connectors | — | API collectors |

**Ticketing / TheHive:** Cloud SOC only — never packaged on this appliance.

Core always-on for appliance SKU: **svc-01** (and minimal channel/license stack). Others require entitlement.

**One ISO** serves physical (factory) and customer-VM deploys; network starts in **bootstrap** for critical patches, then **locked** (LAN agents + SOC channel only).
