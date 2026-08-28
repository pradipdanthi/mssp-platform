# Marketing Website Updates — kevantic.com Pricing & Capabilities

Paste the block below into the **Pricing & Capabilities** section of [www.kevantic.com](https://www.kevantic.com/) (e.g. `website-junexis/services.html` or your CMS pricing module).

---

## React / JSX component

```jsx
<section id="pricing-capabilities" className="tier-pricing-section">
  <div className="container">
    <header className="section-head">
      <p className="eyebrow">NikTiar™ Cyber Defense Platform</p>
      <h2>Pricing &amp; Capabilities</h2>
      <p className="section-lead">
        Three subscription tiers — Silver, Gold, and Platinum — aligned to identity ITDR, core MDR,
        and full MXDR coverage.
      </p>
    </header>

    <div className="tier-matrix-cards">
      <article className="tier-card tier-card--silver">
        <p className="tier-eyebrow">Tier 1</p>
        <h3>Silver</h3>
        <p className="tier-headline">
          Cloud &amp; Identity ITDR — Okta, Entra ID, &amp; Active Directory Protection
        </p>
        <ul>
          <li>Okta / Active Directory ingest</li>
          <li>MFA fatigue detection</li>
          <li>Impossible travel alerts</li>
          <li>Kerberoasting detection</li>
          <li>Portal MFA enforcement</li>
          <li>90-day log retention</li>
        </ul>
      </article>

      <article className="tier-card tier-card--gold">
        <p className="tier-eyebrow">Tier 2</p>
        <h3>Gold</h3>
        <p className="tier-headline">
          Core MDR — 24/7 Host Protection, Automated Containment &amp; Pre-LLM AI Triage
        </p>
        <p className="tier-inherits">Everything in Silver, plus:</p>
        <ul>
          <li>Wazuh EDR telemetry &amp; alerting</li>
          <li>Automated active containment (host isolation)</li>
          <li>Pre-LLM AI veto gate</li>
          <li>Vulnerability management sync</li>
          <li>External attack surface (EASM) sync</li>
        </ul>
      </article>

      <article className="tier-card tier-card--platinum">
        <p className="tier-eyebrow">Tier 3</p>
        <h3>Platinum</h3>
        <p className="tier-headline">
          Full MXDR — DeepSight NDR, Spectre Endpoint DFIR &amp; Retrospective Sweeps
        </p>
        <p className="tier-inherits">Everything in Gold, plus:</p>
        <ul>
          <li>Suricata / Zeek NDR (NikTiar DeepSight)</li>
          <li>Spectre endpoint DFIR (process tree &amp; artifacts)</li>
          <li>90-day retrospective threat sweeps</li>
          <li>ClickHouse OLAP analytics &amp; log archiver</li>
        </ul>
      </article>
    </div>

    <div className="tier-comparison-wrap">
      <table className="tier-comparison-table">
        <thead>
          <tr>
            <th scope="col">Capability</th>
            <th scope="col">Silver</th>
            <th scope="col">Gold</th>
            <th scope="col">Platinum</th>
          </tr>
        </thead>
        <tbody>
          <tr><th scope="row">Okta / AD ingest</th><td>✓</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">MFA fatigue detection</th><td>✓</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Impossible travel</th><td>✓</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Kerberoasting detection</th><td>✓</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Portal MFA</th><td>✓</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">90-day retention</th><td>✓</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Wazuh EDR</th><td>—</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Automated active containment (host isolation)</th><td>—</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Pre-LLM AI veto gate</th><td>—</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Vulnerability &amp; EASM sync</th><td>—</td><td>✓</td><td>✓</td></tr>
          <tr><th scope="row">Suricata / Zeek NDR (DeepSight)</th><td>—</td><td>—</td><td>✓</td></tr>
          <tr><th scope="row">Spectre endpoint DFIR (process tree / artifacts)</th><td>—</td><td>—</td><td>✓</td></tr>
          <tr><th scope="row">90-day retrospective sweeps</th><td>—</td><td>—</td><td>✓</td></tr>
          <tr><th scope="row">ClickHouse OLAP &amp; archiver</th><td>—</td><td>—</td><td>✓</td></tr>
        </tbody>
      </table>
    </div>

    <p className="tier-note">
      Powered by the NikTiar™ Cyber Defense Platform. Need a mapped quote?{" "}
      <a href="/contact.html">Request a NikTiar™ Edge Node demo →</a>
    </p>
  </div>
</section>
```

---

## Plain HTML (CMS paste)

```html
<section id="pricing-capabilities" class="tier-pricing-section">
  <div class="container">
    <header class="section-head">
      <p class="eyebrow">NikTiar&trade; Cyber Defense Platform</p>
      <h2>Pricing &amp; Capabilities</h2>
      <p class="section-lead">
        Three subscription tiers &mdash; Silver, Gold, and Platinum &mdash; aligned to identity ITDR,
        core MDR, and full MXDR coverage.
      </p>
    </header>

    <div class="tier-matrix-cards">
      <article class="tier-card tier-card--silver">
        <p class="tier-eyebrow">Tier 1</p>
        <h3>Silver</h3>
        <p class="tier-headline">Cloud &amp; Identity ITDR &mdash; Okta, Entra ID, &amp; Active Directory Protection</p>
        <ul>
          <li>Okta / Active Directory ingest</li>
          <li>MFA fatigue detection</li>
          <li>Impossible travel alerts</li>
          <li>Kerberoasting detection</li>
          <li>Portal MFA enforcement</li>
          <li>90-day log retention</li>
        </ul>
      </article>

      <article class="tier-card tier-card--gold">
        <p class="tier-eyebrow">Tier 2</p>
        <h3>Gold</h3>
        <p class="tier-headline">Core MDR &mdash; 24/7 Host Protection, Automated Containment &amp; Pre-LLM AI Triage</p>
        <p class="tier-inherits">Everything in Silver, plus:</p>
        <ul>
          <li>Wazuh EDR telemetry &amp; alerting</li>
          <li>Automated active containment (host isolation)</li>
          <li>Pre-LLM AI veto gate</li>
          <li>Vulnerability management sync</li>
          <li>External attack surface (EASM) sync</li>
        </ul>
      </article>

      <article class="tier-card tier-card--platinum">
        <p class="tier-eyebrow">Tier 3</p>
        <h3>Platinum</h3>
        <p class="tier-headline">Full MXDR &mdash; DeepSight NDR, Spectre Endpoint DFIR &amp; Retrospective Sweeps</p>
        <p class="tier-inherits">Everything in Gold, plus:</p>
        <ul>
          <li>Suricata / Zeek NDR (NikTiar DeepSight)</li>
          <li>Spectre endpoint DFIR (process tree &amp; artifacts)</li>
          <li>90-day retrospective threat sweeps</li>
          <li>ClickHouse OLAP analytics &amp; log archiver</li>
        </ul>
      </article>
    </div>

    <div class="tier-comparison-wrap">
      <table class="tier-comparison-table">
        <thead>
          <tr>
            <th scope="col">Capability</th>
            <th scope="col">Silver</th>
            <th scope="col">Gold</th>
            <th scope="col">Platinum</th>
          </tr>
        </thead>
        <tbody>
          <tr><th scope="row">Okta / AD ingest</th><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">MFA fatigue detection</th><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Impossible travel</th><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Kerberoasting detection</th><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Portal MFA</th><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">90-day retention</th><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Wazuh EDR</th><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Automated active containment (host isolation)</th><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Pre-LLM AI veto gate</th><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Vulnerability &amp; EASM sync</th><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Suricata / Zeek NDR (DeepSight)</th><td>&mdash;</td><td>&mdash;</td><td>&#10003;</td></tr>
          <tr><th scope="row">Spectre endpoint DFIR (process tree / artifacts)</th><td>&mdash;</td><td>&mdash;</td><td>&#10003;</td></tr>
          <tr><th scope="row">90-day retrospective sweeps</th><td>&mdash;</td><td>&mdash;</td><td>&#10003;</td></tr>
          <tr><th scope="row">ClickHouse OLAP &amp; archiver</th><td>&mdash;</td><td>&mdash;</td><td>&#10003;</td></tr>
        </tbody>
      </table>
    </div>

    <p class="tier-note">
      Powered by the NikTiar&trade; Cyber Defense Platform. Need a mapped quote?
      <a href="contact.html" style="color:var(--cyan);font-weight:600;">Request a NikTiar&trade; Edge Node demo &rarr;</a>
    </p>
  </div>
</section>
```

---

## Suggested CSS (optional)

```css
.tier-pricing-section .tier-matrix-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.25rem;
  margin: 2rem 0;
}
.tier-pricing-section .tier-card {
  border: 1px solid rgba(103, 232, 249, 0.2);
  border-radius: 14px;
  padding: 1.25rem;
  background: linear-gradient(160deg, rgba(15, 23, 42, 0.85), rgba(15, 23, 42, 0.55));
}
.tier-pricing-section .tier-eyebrow {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--cyan, #22d3ee);
  margin: 0 0 0.35rem;
}
.tier-pricing-section .tier-headline {
  color: #cbd5e1;
  line-height: 1.5;
  margin: 0.5rem 0 1rem;
}
.tier-pricing-section .tier-inherits {
  font-size: 0.9rem;
  color: #94a3b8;
  margin: 0 0 0.5rem;
}
.tier-comparison-wrap { overflow-x: auto; margin-top: 2rem; }
.tier-comparison-table { width: 100%; border-collapse: collapse; }
.tier-comparison-table th, .tier-comparison-table td {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  text-align: center;
}
.tier-comparison-table th[scope="row"] { text-align: left; }
```

---

*Generated for Phase 7 — 3-tier entitlement rollout. Replaces legacy Bronze–Platinum four-column table with Silver / Gold / Platinum.*
