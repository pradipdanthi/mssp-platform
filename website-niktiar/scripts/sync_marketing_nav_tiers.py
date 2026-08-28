#!/usr/bin/env python3
"""Sync marketing site nav + service copy to Silver/Gold/Platinum tier model."""
from __future__ import annotations

import re
from pathlib import Path

ROOTS = [
    Path("/opt/mssp-control/website-niktiar"),
    Path("/home/secadmin/kevantic-website"),
]

SERVICE_TIER = {
    "cloud-identity-protection.html": "Silver",
    "log-event-monitoring.html": "Silver",
    "incident-response.html": "Silver",
    "security-automation.html": "Gold",
    "vulnerability-management.html": "Gold",
    "external-attack-surface.html": "Gold",
    "network-detection-response.html": "Platinum",
    "threat-intelligence.html": "Platinum",
    "endpoint-forensics-deception.html": "Platinum",
    "continuous-compliance.html": "Platinum",
}

FORM_NOTE_OLD = (
    "Existing customers can also request add-ons from the Service Portfolio inside the portal."
)
FORM_NOTE_NEW = (
    "Existing customers can request a tier upgrade from the Service Portfolio inside the client portal."
)


def mega_grid(prefix: str) -> str:
    p = prefix
    return f"""              <div class="mega-col">
                <h4>Silver &middot; Identity ITDR <span class="badge badge-core">Tier 1</span></h4>
                <a class="mega-item" href="{p}services/cloud-identity-protection.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M7.5 18.5h10a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.6 1.5A3.5 3.5 0 0 0 7.5 18.5Z"/></svg></span><span class="mega-copy"><strong>Cloud &amp; Identity Protection (ITDR)</strong><span>Okta / Entra / AD protection, MFA fatigue, impossible travel.</span></span></a>
                <a class="mega-item" href="{p}services/log-event-monitoring.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M12 3 4.5 6v6.2c0 4.6 3.1 8.8 7.5 10.1 4.4-1.3 7.5-5.5 7.5-10.1V6L12 3Z"/></svg></span><span class="mega-copy"><strong>Log &amp; Event Monitoring</strong><span>NikTiar&trade; telemetry retention with zero cloud log tax.</span></span></a>
                <a class="mega-item" href="{p}services/incident-response.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M13 2 4 14h7l-1 8 10-14h-7l0-6Z"/></svg></span><span class="mega-copy"><strong>Incident Response &amp; Casework</strong><span>24/7 analyst-led triage with AI-assisted executive summaries.</span></span></a>
              </div>
              <div class="mega-col">
                <h4>Gold &middot; Core MDR <span class="badge badge-core">Tier 2</span></h4>
                <a class="mega-item" href="{p}services/security-automation.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="11" width="17" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.75"/><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M7 11V8a5 5 0 0 1 10 0v3"/></svg></span><span class="mega-copy"><strong>Security Automation &amp; Containment</strong><span>Hold-until-unisolate host containment with verified endpoint callback.</span></span></a>
                <a class="mega-item" href="{p}services/vulnerability-management.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M12 3.5 21 19H3L12 3.5Z"/><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M12 10v4M12 16.5h.01"/></svg></span><span class="mega-copy"><strong>Vulnerability Management (NikTiar Aegis)</strong><span>Continuous CVE prioritization and patch guidance.</span></span></a>
                <a class="mega-item" href="{p}services/external-attack-surface.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.75"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M3.5 12h17M12 3.5c2.5 2.8 2.5 14.2 0 17M12 3.5c-2.5 2.8-2.5 14.2 0 17"/></svg></span><span class="mega-copy"><strong>External Attack Surface (EASM)</strong><span>Continuous perimeter domain &amp; SSL exposure discovery.</span></span></a>
              </div>
              <div class="mega-col">
                <h4>Platinum &middot; Full MXDR <span class="badge badge-core">Tier 3</span></h4>
                <a class="mega-item" href="{p}services/network-detection-response.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="6" r="2.2" fill="none" stroke="currentColor" stroke-width="1.75"/><circle cx="18" cy="6" r="2.2" fill="none" stroke="currentColor" stroke-width="1.75"/><circle cx="12" cy="18" r="2.2" fill="none" stroke="currentColor" stroke-width="1.75"/><path fill="none" stroke="currentColor" stroke-width="1.75" d="M8 7.2 10.5 16M16 7.2 13.5 16M8.2 6h7.6"/></svg></span><span class="mega-copy"><strong>Network Detection (NikTiar DeepSight NDR)</strong><span>Packet-level inspection for lateral movement and beaconing.</span></span></a>
                <a class="mega-item" href="{p}services/threat-intelligence.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" stroke-width="1.75"/><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="m20 20-3.5-3.5"/></svg></span><span class="mega-copy"><strong>Threat Intelligence &amp; Retrospective Sweeps</strong><span>90-day retrospective zero-day sweeps across retained telemetry.</span></span></a>
                <a class="mega-item" href="{p}services/endpoint-forensics-deception.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7.5" fill="none" stroke="currentColor" stroke-width="1.75"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.75"/><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M12 2.5v2.5M12 19v2.5M2.5 12h2.5M19 12h2.5"/></svg></span><span class="mega-copy"><strong>Endpoint Forensics (NikTiar Spectre DFIR)</strong><span>Process tree DFIR, canary traps, and deep investigation support.</span></span></a>
                <a class="mega-item" href="{p}services/continuous-compliance.html"><span class="mega-ico" aria-hidden="true"><svg class="mega-ico-svg" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" d="M8 4.5h8a2 2 0 0 1 2 2v13l-6-3-6 3v-13a2 2 0 0 1 2-2Z"/><path fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" d="M9 11h6M9 14h4"/></svg></span><span class="mega-copy"><strong>Continuous Compliance &amp; Hardening</strong><span>CIS · ISO 27001 · PCI-DSS · HIPAA §164.312 · NIST indicators.</span></span></a>
              </div>"""


def index_services_section() -> str:
    return """        <div class="section-head reveal">
          <span class="section-label">NikTiar&trade; capability modules</span>
          <h2>Capabilities bundled by subscription tier.</h2>
          <p>Silver, Gold, and Platinum include capability modules &mdash; not per-module add-ons. Upgrade your tier from the client portal when you are ready to expand coverage.</p>
        </div>

        <div class="svc-block reveal">
          <div class="svc-block-head">
            <h3>Silver &middot; Identity ITDR</h3>
            <span class="badge badge-core">Tier 1</span>
          </div>
          <div class="grid-3">
            <a class="card-link" href="services/cloud-identity-protection.html"><article class="card svc-card"><span class="badge badge-core">Silver</span><h3>Cloud &amp; Identity Protection (ITDR)</h3><p>Okta / Entra / AD protection, MFA fatigue, and impossible travel detection.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/log-event-monitoring.html"><article class="card svc-card"><span class="badge badge-core">Silver</span><h3>Log &amp; Event Monitoring</h3><p>NikTiar&trade; telemetry retention with zero cloud log tax &mdash; 24/7 monitoring.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/incident-response.html"><article class="card svc-card"><span class="badge badge-core">Silver</span><h3>Incident Response &amp; Casework</h3><p>24/7 analyst-led triage with AI-assisted executive summaries.</p><span class="card-cta">View full details &rarr;</span></article></a>
          </div>
        </div>

        <div class="svc-block reveal">
          <div class="svc-block-head">
            <h3>Gold &middot; Core MDR</h3>
            <span class="badge badge-core">Tier 2</span>
          </div>
          <p class="tier-inherits">Everything in Silver, plus:</p>
          <div class="grid-3">
            <a class="card-link" href="services/security-automation.html"><article class="card svc-card"><span class="badge badge-core">Gold</span><h3>Security Automation &amp; Containment</h3><p>Hold-until-unisolate host containment with verified endpoint callback.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/vulnerability-management.html"><article class="card svc-card"><span class="badge badge-core">Gold</span><h3>Vulnerability Management (NikTiar Aegis)</h3><p>Continuous CVE prioritization and patch guidance for your IT team.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/external-attack-surface.html"><article class="card svc-card"><span class="badge badge-core">Gold</span><h3>External Attack Surface (EASM)</h3><p>Continuous perimeter domain &amp; SSL exposure discovery.</p><span class="card-cta">View full details &rarr;</span></article></a>
          </div>
        </div>

        <div class="svc-block reveal">
          <div class="svc-block-head">
            <h3>Platinum &middot; Full MXDR</h3>
            <span class="badge badge-core">Tier 3</span>
          </div>
          <p class="tier-inherits">Everything in Gold, plus:</p>
          <div class="grid-4">
            <a class="card-link" href="services/network-detection-response.html"><article class="card svc-card"><span class="badge badge-core">Platinum</span><h3>Network Detection (NikTiar DeepSight NDR)</h3><p>Packet-level inspection for lateral movement and beaconing.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/threat-intelligence.html"><article class="card svc-card"><span class="badge badge-core">Platinum</span><h3>Threat Intelligence &amp; Retrospective Sweeps</h3><p>90-day retrospective zero-day sweeps across retained telemetry.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/endpoint-forensics-deception.html"><article class="card svc-card"><span class="badge badge-core">Platinum</span><h3>Endpoint Forensics (NikTiar Spectre DFIR)</h3><p>Process tree DFIR, canary traps, and deep investigation support.</p><span class="card-cta">View full details &rarr;</span></article></a>
            <a class="card-link" href="services/continuous-compliance.html"><article class="card svc-card"><span class="badge badge-core">Platinum</span><h3>Continuous Compliance &amp; Hardening</h3><p>Live CIS, ISO 27001, PCI-DSS, HIPAA §164.312, and NIST indicators.</p><span class="card-cta">View full details &rarr;</span></article></a>
          </div>
        </div>"""


def patch_mega_menu(text: str, path: Path) -> str:
    if "services/" in str(path) and path.parent.name == "services":
        prefix = "../"
    else:
        prefix = ""
    new_grid = mega_grid(prefix)
    return re.sub(
        r"<div class=\"mega-grid\">.*?</div>\s*<div class=\"mega-foot\">",
        f"<div class=\"mega-grid\">\n{new_grid}\n            </div>\n            <div class=\"mega-foot\">",
        text,
        count=1,
        flags=re.S,
    )


def patch_index_services(text: str) -> str:
    return re.sub(
        r"<div class=\"section-head reveal\">\s*<span class=\"section-label\">Capability catalog</span>.*?"
        r"<p style=\"margin-top:0\.5rem;\"><a class=\"btn btn-ghost\" href=\"services\.html\">Explore full service detail</a></p>",
        index_services_section()
        + '\n        <p style="margin-top:0.5rem;"><a class="btn btn-ghost" href="services.html">Explore full service detail</a></p>',
        text,
        count=1,
        flags=re.S,
    )


def patch_service_detail_badges(text: str, path: Path) -> str:
    name = path.name
    tier = SERVICE_TIER.get(name)
    if tier:
        text = re.sub(
            r'<div style="margin:0\.85rem 0 0\.7rem;"><span class="badge badge-addon">Add-on</span></div>',
            f'<div style="margin:0.85rem 0 0.7rem;"><span class="badge badge-core">{tier} tier</span></div>',
            text,
        )
        text = re.sub(
            r'<div style="margin:0\.85rem 0 0\.7rem;"><span class="badge badge-core">Core</span></div>',
            f'<div style="margin:0.85rem 0 0.7rem;"><span class="badge badge-core">{tier} tier</span></div>',
            text,
        )
    return text


def patch_global_replacements(text: str) -> str:
    text = text.replace(FORM_NOTE_OLD, FORM_NOTE_NEW)
    text = text.replace(
        '<span class="tele-meta">Add-on</span>',
        '<span class="tele-meta">Tier upgrade</span>',
    )
    text = text.replace(
        "<div>1-click consulting request</div>",
        "<div>1-click tier upgrade request</div>",
    )
    text = text.replace("styles.css?v=8", "styles.css?v=9")
    return text


def patch_file(path: Path) -> bool:
    if not path.is_file() or path.suffix != ".html":
        return False
    original = path.read_text(encoding="utf-8")
    text = original
    if "mega-grid" in text:
        text = patch_mega_menu(text, path)
    if path.name == "index.html" and 'id="services"' in text:
        text = patch_index_services(text)
    if path.parent.name == "services":
        text = patch_service_detail_badges(text, path)
    text = patch_global_replacements(text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = 0
    for root in ROOTS:
        if not root.is_dir():
            continue
        for html in sorted(root.rglob("*.html")):
            if patch_file(html):
                print(f"patched {html}")
                changed += 1
    print(f"Done. {changed} files updated.")


if __name__ == "__main__":
    main()
