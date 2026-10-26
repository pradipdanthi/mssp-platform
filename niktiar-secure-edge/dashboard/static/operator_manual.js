/* NikTiar Secure Edge — operator manual (customer-facing, no sales/meta jargon). */
(function (global) {
  "use strict";

  function openBtn(tab, label) {
    return (
      '<p style="margin-top:.85rem"><button type="button" class="btn primary" onclick="go(\'' +
      tab +
      "')\">Open " +
      label +
      "</button></p>"
    );
  }

  function sec(id, title, body) {
    return (
      '<section class="man-sec" id="man-' +
      id +
      '">' +
      "<h3>" +
      title +
      "</h3>" +
      body +
      "</section>"
    );
  }

  function block(title, html) {
    return "<h4>" + title + "</h4>" + html;
  }

  function steps(items) {
    return "<ol class=\"man-steps\">" + items.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ol>";
  }

  function renderOperatorManual() {
    var toc = [
      ["intro", "1. What Secure Edge is"],
      ["flow", "2. How traffic is inspected"],
      ["first", "3. First-time setup path"],
      ["apply", "4. Apply changes (required)"],
      ["overview", "5. Overview"],
      ["analytics", "6. Analytics"],
      ["zones", "7. Zones / Sites"],
      ["ssl", "8. SSL / TLS"],
      ["cache", "9. Caching"],
      ["ngfw", "10. Firewall policies"],
      ["urlfilter", "11. URL Filter"],
      ["dnsfilter", "12. DNS Filter"],
      ["ransomware", "13. Ransomware Defense"],
      ["profiles", "14. Security Profiles"],
      ["firewall", "15. IP / UA / Geo Firewall"],
      ["ratelimit", "16. Rate Limit"],
      ["waf", "17. Web Application Firewall"],
      ["rules", "18. Custom WAF rules"],
      ["enterprise", "19. Advanced defenses"],
      ["isolation", "20. Deployment"],
      ["system", "21. System"],
      ["checklist", "22. Recommended baseline"],
    ]
      .map(function (x) {
        return (
          '<a href="#man-' +
          x[0] +
          '" onclick="document.getElementById(\'man-' +
          x[0] +
          "').scrollIntoView({behavior:'smooth',block:'start'});return false\">" +
          x[1] +
          "</a>"
        );
      })
      .join("");

    return (
      '<div class="teach"><strong>NikTiar Secure Edge — Operator Manual</strong> ' +
      "This page is the complete reference for every control on this appliance. " +
      "Use the table of contents to jump to a feature, then follow the numbered steps to configure it. " +
      "After any change, click <strong>Apply changes</strong> in the top bar so the live edge reloads policy.</div>" +
      '<div class="card man-toc"><h3>Contents</h3><div class="man-toc-grid">' +
      toc +
      "</div></div>" +
      sec(
        "intro",
        "1. What Secure Edge is",
        "<p>NikTiar Secure Edge is a <strong>dedicated</strong> next-generation edge appliance for one organization. " +
          "It sits in front of your public websites and applications (and, when used as LAN DNS, in front of client name resolution). " +
          "Malicious or unwanted traffic is stopped here; legitimate traffic is forwarded to the origin servers you define on each Zone.</p>" +
          block(
            "What security it brings",
            "<ul>" +
              "<li>Stops common web attacks (SQL injection, XSS, path probes) before they reach origin.</li>" +
              "<li>Blocks known-bad domains at DNS and mirrors high-risk Hosts on the web edge.</li>" +
              "<li>Reduces ransomware exposure (leak sites, droppers, WebDAV abuse, related URL/DNS categories).</li>" +
              "<li>Enforces allow/deny policies by IP, path, User-Agent, country, and application profile.</li>" +
              "<li>Throttles floods and login/API abuse with rate limits and bot defenses.</li>" +
              "</ul>"
          ) +
          block(
            "Why it must be configured",
            "<p>Out of the box the appliance has engines and sensible defaults, but <strong>it does not know your hostnames, origins, trusted offices, or business allow-lists</strong>. " +
              "Without Zones, traffic has nowhere safe to go. Without policies and filters, you miss organization-specific risk. " +
              "Configuration is how you turn a general security platform into protection for <em>your</em> sites and users.</p>"
          ) +
          block(
            "Primary use cases",
            "<ul>" +
              "<li>Protect customer or employee web apps that sit behind this edge (portal, API, VPN landing page, e-commerce).</li>" +
              "<li>Use the appliance as LAN DNS so workstations never resolve malware, phishing, or ransomware infrastructure domains.</li>" +
              "<li>Give SOC / IT operators one console to tighten WAF, firewall, DNS, and ransomware controls without touching origin servers.</li>" +
              "</ul>"
          )
      ) +
      sec(
        "flow",
        "2. How traffic is inspected (defense layers)",
        "<p>Think of Secure Edge as stacked gates. A request can be denied at the first matching layer:</p>" +
          "<table><thead><tr><th>Order</th><th>Layer</th><th>Question answered</th><th>Menu</th></tr></thead><tbody>" +
          "<tr><td>1</td><td>DNS Filter</td><td>Should this domain resolve at all?</td><td>NikTiar DNS Filter</td></tr>" +
          "<tr><td>2</td><td>Firewall policies</td><td>Is this visitor / path / app allowed?</td><td>Policies</td></tr>" +
          "<tr><td>3</td><td>IP / UA / Geo</td><td>Is the client IP, User-Agent, or country allowed?</td><td>NikTiar Firewall</td></tr>" +
          "<tr><td>4</td><td>URL Filter</td><td>Does the HTTP path match a blocked category?</td><td>NikTiar URL Filter</td></tr>" +
          "<tr><td>5</td><td>Ransomware Defense</td><td>Is this ransomware infra / dropper / note traffic?</td><td>Ransomware Defense</td></tr>" +
          "<tr><td>6</td><td>Security Profiles</td><td>Do file / spyware / EDL / URL profile rules match?</td><td>Security Profiles</td></tr>" +
          "<tr><td>7</td><td>Rate Limit</td><td>Is this client asking too often?</td><td>NikTiar Rate Limit</td></tr>" +
          "<tr><td>8</td><td>WAF + custom rules</td><td>Does the request look like an application attack?</td><td>NikTiar WAF · custom rules</td></tr>" +
          "<tr><td>9</td><td>Advanced defenses</td><td>API / bot / DLP / queue / virtual patch extras?</td><td>Advanced defenses</td></tr>" +
          "<tr><td>✓</td><td>Origin</td><td>Forward to the Zone origin URL</td><td>Zones / Sites</td></tr>" +
          "</tbody></table>" +
          "<p class=\"hint\">DNS Filter also protects clients that use this edge as their DNS server, even when they never hit the HTTP edge.</p>"
      ) +
      sec(
        "first",
        "3. First-time setup path",
        "<p>Follow this sequence the first time you bring the appliance online for a site:</p>" +
          steps([
            "<strong>Zones / Sites</strong> — add each public hostname and its origin URL.",
            "<strong>SSL / TLS</strong> — choose how the edge terminates visitor TLS and connects to origin.",
            "<strong>Overview</strong> — set global Security Level to <em>Medium</em> (production default).",
            "<strong>Policies</strong> — keep default allow for normal traffic; add deny rules for known-bad networks or admin paths if needed.",
            "<strong>URL Filter</strong> — enable malware / phishing / ransomware path categories.",
            "<strong>DNS Filter</strong> — enable; point LAN/DHCP DNS at this edge; keep malware, phishing, ransomware categories on.",
            "<strong>Ransomware Defense</strong> — leave enabled in Block mode.",
            "<strong>Security Profiles</strong> — apply <em>Recommended</em> or <em>Strict Ransomware</em> when hardening for ransomware risk.",
            "<strong>NikTiar WAF</strong> — enable per zone; start in Block (or Simulate while tuning).",
            "<strong>Rate Limit</strong> — protect <code>/login</code>, <code>/api</code>, and other abuse-prone paths.",
            "<strong>Apply changes</strong> — publish everything to the live edge.",
            "<strong>Analytics</strong> — confirm requests and blocks look sane after go-live.",
          ]) +
          '<div class="step-cards">' +
          '<div class="card" onclick="go(\'zones\')"><div class="n">1</div><strong>Zones</strong><div class="hint">Hostname → origin</div></div>' +
          '<div class="card" onclick="go(\'dnsfilter\')"><div class="n">2</div><strong>DNS Filter</strong><div class="hint">Point LAN DNS here</div></div>' +
          '<div class="card" onclick="go(\'waf\')"><div class="n">3</div><strong>WAF</strong><div class="hint">Medium + Block</div></div>' +
          '<div class="card" onclick="applyNow()"><div class="n">✓</div><strong>Apply</strong><div class="hint">Publish live</div></div>' +
          "</div>"
      ) +
      sec(
        "apply",
        "4. Apply changes (required)",
        "<p>Editing a form only updates the draft configuration in memory / API. " +
          "The live edge (WAF, firewall, DNS policy files, site routing) updates when you click <strong>Apply changes</strong> " +
          "or when a save action that already calls Apply completes successfully.</p>" +
          block(
            "What Apply does",
            "<ul>" +
              "<li>Writes zone routing and TLS stubs for each site.</li>" +
              "<li>Rebuilds firewall, URL filter, NGFW, ransomware, and security-profile rule packs.</li>" +
              "<li>Reloads the web edge so new deny/allow behavior takes effect.</li>" +
              "<li>Refreshes DNS Filter policy consumed by the DNS service when DNS controls changed.</li>" +
              "</ul>"
          ) +
          block(
            "Operator habit",
            "<p>After every meaningful edit: save on the feature page → click <strong>Apply changes</strong> → spot-check <strong>Analytics</strong> or a test request.</p>"
          )
      ) +
      sec(
        "overview",
        "5. Overview",
        block("What it is", "<p>The home dashboard: zone count, global security level, NGFW policy count, recent threat blocks, and bot-defense decisions.</p>") +
          block(
            "Security it brings",
            "<p>The global Security Level is the master dial for how aggressive NikTiar WAF inspection is across the edge. " +
              "WAF, Bot Defense, and Browser Integrity toggles enable core protections without per-zone micro-tuning.</p>"
          ) +
          block(
            "Why configure it",
            "<p>If Security Level is too low, attacks reach origin. If it is Emergency forever, legitimate users may see challenges. " +
              "Set Medium for normal production; raise temporarily during an active incident.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Morning health check: zones online, blocks not zero during an attack, bot decisions sane.</li>" +
              "<li>Incident response: switch Security Level to High or Emergency, Apply, then revert later.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>Overview</strong>.",
              "Choose Security Level: Off · Monitor only · Low · Medium · High · Emergency.",
              "Ensure <strong>WAF enabled</strong>, <strong>Bot Defense</strong>, and <strong>Browser Integrity</strong> are checked for production.",
              "Click <strong>Save global settings</strong>.",
              "Click <strong>Apply changes</strong> if the save did not already reload the edge.",
            ])
          ) +
          openBtn("overview", "Overview")
      ) +
      sec(
        "analytics",
        "6. Analytics",
        block("What it is", "<p>Sampled request counters, threat blocks, and a recent request table (status, host, URI, client).</p>") +
          block(
            "Security it brings",
            "<p>Visibility — you cannot tune what you cannot see. Analytics shows whether WAF/firewall rules are firing and whether legitimate traffic is being denied by mistake.</p>"
          ) +
          block(
            "Why configure / use it",
            "<p>No configuration is required. Use it after every policy change and during incidents to validate outcomes.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>After enabling a deny rule, confirm 403s appear for the bad path and 200s for the homepage.</li>" +
              "<li>During a flood, watch requests sampled and threats blocked climb; tighten Rate Limit if needed.</li>" +
              "</ul>"
          ) +
          block(
            "How to use",
            steps([
              "Open <strong>Analytics</strong>.",
              "Review KPI cards (requests sampled, threats blocked).",
              "Scan Recent requests for unexpected 403/429 on business paths.",
              "If false positives appear, loosen the matching WAF/URL/firewall rule, Apply, and re-check.",
            ])
          ) +
          openBtn("analytics", "Analytics")
      ) +
      sec(
        "zones",
        "7. Zones / Sites",
        block(
          "What it is",
          "<p>A Zone maps one <strong>public hostname</strong> (what browsers request) to one <strong>origin URL</strong> (where your real application listens). " +
            "Every HTTP/HTTPS protection on this edge is scoped to a Zone’s Host header.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Unknown hostnames are denied (no open fallthrough). Only hostnames you register are proxied, so random Host probes cannot reach an arbitrary backend.</p>"
          ) +
          block(
            "Why it is required",
            "<p>Without at least one Zone, the edge has no site to protect and nowhere to send legitimate traffic. " +
              "WAF, firewall, SSL, cache, and rate limits all attach to zones.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li><code>portal.customer.com</code> → <code>http://10.0.0.20:8080</code> (internal app).</li>" +
              "<li><code>api.customer.com</code> → separate origin with stricter Rate Limit and API Shield.</li>" +
              "<li>Multiple sites for the same organization on one dedicated edge.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>Zones / Sites</strong>.",
              "Enter <strong>Hostname</strong> exactly as clients will type it (DNS A/AAAA or CNAME must point to this edge).",
              "Enter <strong>Origin URL</strong> including scheme and port (example <code>http://10.0.0.20:8080</code>).",
              "Set <strong>Organization code</strong> if your operator uses one (often already pinned on the appliance).",
              "Click <strong>Add zone &amp; apply</strong>.",
              "Continue to <strong>SSL / TLS</strong> and <strong>NikTiar WAF</strong> for that hostname.",
            ])
          ) +
          openBtn("zones", "Zones / Sites")
      ) +
      sec(
        "ssl",
        "8. SSL / TLS",
        block(
          "What it is",
          "<p>Controls how Secure Edge handles HTTPS between the visitor and the edge, and between the edge and origin.</p>"
        ) +
          block(
            "Security it brings",
            "<ul>" +
              "<li>Encrypts visitor traffic so credentials and session cookies are not sent in clear text on the internet path.</li>" +
              "<li>Lets you require a trustworthy origin certificate (Full / Strict) so the edge does not talk to a spoofed backend.</li>" +
              "</ul>"
          ) +
          block(
            "Why configure it",
            "<p>Wrong SSL mode breaks the site (browser errors) or leaves an insecure hop to origin. Match the mode to how origin is actually configured.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li><strong>Flexible</strong> — HTTPS to visitors; HTTP to origin (lab / simple internal origins).</li>" +
              "<li><strong>Full</strong> — HTTPS to origin without strict cert validation.</li>" +
              "<li><strong>Strict</strong> — HTTPS to origin with valid certificate (recommended when origin has a real cert).</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Create a Zone first.",
              "Open <strong>SSL / TLS</strong> and select the active zone.",
              "Choose the SSL mode that matches your origin.",
              "Save / Apply, then test <code>https://your-hostname/</code> in a browser.",
            ])
          ) +
          openBtn("ssl", "SSL / TLS")
      ) +
      sec(
        "cache",
        "9. Caching",
        block(
          "What it is",
          "<p>Optional edge caching for cacheable responses (static assets). Bypass means every request goes to origin.</p>"
        ) +
          block(
            "Security / performance",
            "<p>Caching reduces origin load. Keep Bypass for authenticated apps and APIs so sensitive responses are not shared across users incorrectly.</p>"
          ) +
          block(
            "Why configure it",
            "<p>Only enable Standard caching when you understand which paths are static. Mis-caching dynamic HTML can leak personalized content.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Marketing site with CSS/JS/images — Standard + reasonable TTL.</li>" +
              "<li>Authenticated portal / API — leave Bypass.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>Caching</strong> for the zone.",
              "Set mode to Bypass (safe default) or Standard.",
              "If Standard, set edge TTL seconds appropriately.",
              "Save and Apply; verify pages still show correct per-user content.",
            ])
          ) +
          openBtn("cache", "Caching")
      ) +
      sec(
        "ngfw",
        "10. Firewall policies (NGFW)",
        block(
          "What it is",
          "<p>Ordered Allow / Deny / Challenge / Log rules evaluated by priority. First match wins. " +
            "Policies can match source IP groups, paths, methods, User-Agent fragments, and application profiles.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Explicit access control: only intended networks reach admin paths; scanners and known-bad ranges are denied before WAF work is spent.</p>"
          ) +
          block(
            "Why configure it",
            "<p>Default allow is convenient for go-live, but production apps usually need deny rules for <code>/admin</code>, management interfaces, or non-office source networks.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Deny internet access to <code>/admin</code>; allow only office/private networks.</li>" +
              "<li>Challenge suspicious clients instead of hard deny while investigating.</li>" +
              "<li>Log-only rule to measure impact before enforcing Deny.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>Policies</strong>.",
              "Confirm default action (Allow recommended until you intentionally lock down).",
              "Add a policy: name, priority (lower number = earlier), action (Deny / Allow / Challenge / Log).",
              "Optionally set source (Any or private networks), path contains, methods, User-Agent contains, application profile.",
              "Add a clear description for the next operator.",
              "Click <strong>Add policy &amp; apply</strong>.",
              "Verify with Analytics or a controlled curl from an allowed vs denied network.",
            ])
          ) +
          openBtn("ngfw", "Policies")
      ) +
      sec(
        "urlfilter",
        "11. NikTiar URL Filter",
        block(
          "What it is",
          "<p>Inspects the HTTP request <strong>path</strong> against threat categories and custom regexes. " +
            "This is path filtering on the web edge — not DNS. For whole-domain blocking, use DNS Filter.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Blocks malware, phishing, ransomware-related, and scanner-style URL patterns even when the Host looks legitimate.</p>"
          ) +
          block(
            "Why configure it",
            "<p>Attackers often use odd paths (<code>/wp-login.php</code>, exploit kits, ransomware staging keywords) on otherwise normal hostnames. Categories catch those patterns at scale.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Block phishing/malware path kits hitting a public site.</li>" +
              "<li>Add a custom regex for a proprietary admin path you want denied globally.</li>" +
              "<li>Per-zone categories when one site needs stricter web path policy than another.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar URL Filter</strong>.",
              "Enable the filter; choose Block (403) or Log only while tuning.",
              "Check threat categories appropriate for production (malware, phishing, ransomware at minimum).",
              "Optionally add custom block / allow regex lines.",
              "Optionally set per-zone category overrides after selecting the active zone.",
              "Save, Apply, and test a known-bad path vs a normal homepage.",
            ])
          ) +
          openBtn("urlfilter", "URL Filter")
      ) +
      sec(
        "dnsfilter",
        "12. NikTiar DNS Filter",
        block(
          "What it is",
          "<p>Category-based DNS sinkholing on this appliance (UDP/TCP port 53). " +
            "When LAN clients use this edge as DNS, blocked domains resolve to a sinkhole (typically <code>0.0.0.0</code>) so browsers never connect. " +
            "Optional <strong>WAF Host block</strong> also denies HTTP(S) requests whose Host header matches blocked domains (helps if DNS was bypassed).</p>"
        ) +
          block(
            "Security it brings",
            "<ul>" +
              "<li>Stops malware C2, phishing, ransomware infrastructure, cryptomining, and other categories before TCP connects.</li>" +
              "<li>Works for any application that uses DNS — not only browsers hitting your Zones.</li>" +
              "<li>Feed sync keeps lists current; custom allow/block covers local exceptions.</li>" +
              "</ul>"
          ) +
          block(
            "Why configure it",
            "<p>Without pointing DHCP/DNS at this edge, clients keep using public DNS and skip this control. " +
              "Without enabling critical categories, ransomware and phishing domains still resolve.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Office LAN: DHCP DNS = Secure Edge IP → workstation ransomware/phishing domains fail closed.</li>" +
              "<li>Block social/gambling categories for workplace policy (optional).</li>" +
              "<li>Allow-list a partner domain that a feed falsely classified.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar DNS Filter</strong>.",
              "Enable DNS Filter; keep <strong>Also block on NikTiar WAF (Host header)</strong> on for defense-in-depth.",
              "Enable categories: Malware &amp; C2, Phishing, Ransomware, Cryptomining at minimum.",
              "Add any custom block domains (one per line) and allow domains for exceptions.",
              "Save &amp; apply; use <strong>Refresh feeds</strong> if lists look stale.",
              "On your DHCP/DNS server, set the recursive DNS for clients to this edge’s LAN IP (port 53).",
              "Test: resolve a known-blocked domain from a client — expect sinkhole; resolve a normal domain — expect real answers.",
            ])
          ) +
          openBtn("dnsfilter", "DNS Filter")
      ) +
      sec(
        "ransomware",
        "13. NikTiar Ransomware Defense",
        block(
          "What it is",
          "<p>A coordinated pack that turns on ransomware DNS category enforcement plus WAF controls for ransom-note paths, double-extension droppers, script/ISO downloads under download paths, WebDAV write abuse, Tor2web gateways, and suspicious exfil path keywords.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Reduces web- and DNS-borne ransomware <em>exposure</em> on this edge: known infrastructure becomes unreachable, and common staging/dropper HTTP patterns are blocked. " +
              "It does <strong>not</strong> replace endpoint security or backups — keep those in place.</p>"
          ) +
          block(
            "Why configure it",
            "<p>Ransomware operators rely on leak sites, payment portals, droppers, and WebDAV planting. Leaving these layers off leaves those lanes open even if generic WAF is on.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Dedicated edge for an organization that must reduce ransomware delivery and C2 reachability.</li>" +
              "<li>Log-only mode while validating that business download paths are not false-positive blocked, then switch to Block.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>Ransomware Defense</strong>.",
              "Leave Enabled checked for production.",
              "Set <strong>When a rule matches</strong> to Block (403) (or Log only while tuning).",
              "Keep all layers enabled unless a specific layer breaks a known business workflow — document any exception.",
              "Click <strong>Save &amp; apply</strong>.",
              "Confirm DNS Filter ransomware category is also enabled and feeds show ransomware domains loaded.",
              "Optional: apply Security Profiles → Strict Ransomware for file-blocking / anti-spyware alignment.",
            ])
          ) +
          openBtn("ransomware", "Ransomware Defense")
      ) +
      sec(
        "profiles",
        "14. Security Profiles",
        block(
          "What it is",
          "<p>NGFW-style profile pack: File Blocking, Anti-Spyware, URL Filtering alignment, and External Dynamic Lists (EDL). Presets apply a known-good baseline in one click.</p>"
        ) +
          block(
            "Security it brings",
            "<ul>" +
              "<li><strong>File Blocking</strong> — stops PE/scripts/LNK/HTA, Office macros, ISO/IMG/VHD, PE magic uploads, risky download types.</li>" +
              "<li><strong>Anti-Spyware</strong> — C2-like paths, DGA-like hostnames, DNS-tunnel style labels; works with DNS sinkholes.</li>" +
              "<li><strong>EDL</strong> — operator-managed domain/IP/URL deny lists under the appliance EDL runtime path.</li>" +
              "</ul>"
          ) +
          block(
            "Why configure it",
            "<p>Individual toggles are easy to miss. Presets encode a coherent hardening baseline so ransomware and malware loaders are blocked consistently.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li><strong>Recommended</strong> — balanced production baseline.</li>" +
              "<li><strong>Strict Ransomware</strong> — aggressive file + spyware + category posture when ransomware risk is elevated.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>Security Profiles</strong>.",
              "Click <strong>Apply Recommended</strong> or <strong>Apply Strict Ransomware</strong>.",
              "Review File Blocking / Anti-Spyware / EDL checkboxes; uncheck only with a documented business reason.",
              "Click <strong>Save profile toggles &amp; apply</strong>.",
              "Test legitimate file download workflows your business requires.",
            ])
          ) +
          openBtn("profiles", "Security Profiles")
      ) +
      sec(
        "firewall",
        "15. NikTiar Firewall (IP / User-Agent / Geo)",
        block(
          "What it is",
          "<p>Classic access lists per zone: block or allow IP/CIDR, block User-Agent substrings, and optional country blocks (needs a country header on requests).</p>"
        ) +
          block(
            "Security it brings",
            "<p>Immediate containment: ban a noisy scanner IP, allow only office egress to a sensitive site, block tool User-Agents like <code>sqlmap</code>.</p>"
          ) +
          block(
            "Why configure it",
            "<p>WAF catches payload attacks; IP/UA/geo catches who is talking to you. Together they close more lanes than either alone.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Allow-list office NAT CIDRs for an internal admin hostname.</li>" +
              "<li>Block a botnet IP range observed in Analytics.</li>" +
              "<li>Edge-wide geo block for countries you never serve (when country header is available).</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar Firewall</strong> and select the zone.",
              "Paste Block IPs/CIDRs and/or Allow IPs/CIDRs (one per line).",
              "Add User-Agent substrings to block (example <code>sqlmap</code>).",
              "Optionally set country ISO codes and edge-wide geo settings.",
              "Save firewall / geo, then Apply.",
              "Verify from an allowed and a blocked address.",
            ])
          ) +
          openBtn("firewall", "Firewall")
      ) +
      sec(
        "ratelimit",
        "16. NikTiar Rate Limit",
        block(
          "What it is",
          "<p>Per-client-IP counters on a path. When the limit is exceeded, the edge returns HTTP <strong>429 Too Many Requests</strong>.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Slows credential stuffing, API scraping, and volumetric abuse against login and API endpoints without taking the whole site offline.</p>"
          ) +
          block(
            "Why configure it",
            "<p>WAF may allow each individual request while an attacker still floods login. Rate limits bound that abuse.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li><code>/login</code> — e.g. 20 requests / 60 seconds per IP.</li>" +
              "<li><code>/api/</code> — protect public APIs from scrape floods.</li>" +
              "<li>Password reset endpoints with tighter thresholds.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar Rate Limit</strong> and select the zone.",
              "Enter rule name, path prefix, max requests, and period (seconds).",
              "Add the rule (save applies to the zone).",
              "Apply changes; test with repeated requests until you see 429, then confirm normal browsing still works.",
            ])
          ) +
          openBtn("ratelimit", "Rate Limit")
      ) +
      sec(
        "waf",
        "17. NikTiar WAF",
        block(
          "What it is",
          "<p>Web Application Firewall inspection for HTTP requests: SQL injection, XSS, protocol abuse, and related application attacks. " +
            "Security Level sets strictness; mode can Block or Simulate (log only).</p>"
        ) +
          block(
            "Security it brings",
            "<p>Stops exploit payloads aimed at your application before they reach origin code or databases.</p>"
          ) +
          block(
            "Why configure it",
            "<p>Origins alone are rarely perfect. WAF is the last systematic filter for crafted requests. Paranoia level and Security Level must match your app’s tolerance for false positives.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Production public site — Medium + Block.</li>" +
              "<li>New app onboarding — Simulate for a day, review Analytics, then Block.</li>" +
              "<li>Active incident — High or Emergency + Emergency mode challenge.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar WAF</strong> and select the zone.",
              "Set Security Level (Medium recommended).",
              "Set WAF mode to Block (enforce) or Simulate (log only).",
              "Choose paranoia level 1–4 (1 safest / fewest false positives; 4 strictest).",
              "Optionally enable Emergency mode (challenge interstitial) during attacks.",
              "Save WAF settings and Apply.",
              "Test a benign page and a known probe (for example a SQLi-looking query) to confirm 200 vs 403.",
            ])
          ) +
          openBtn("waf", "NikTiar WAF")
      ) +
      sec(
        "rules",
        "18. NikTiar custom WAF rules",
        block(
          "What it is",
          "<p>Simple expression rules (path / UA / IP / query contains …) with actions block, log, allow, or challenge. Prefer Host-scoped rules on a dedicated edge.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Lets you encode business-specific protections the managed ruleset cannot know — proprietary admin paths, partner User-Agents, one-off incident IOCs.</p>"
          ) +
          block(
            "Why configure it",
            "<p>Managed WAF is generic. Custom rules close the last mile for your application’s unique surface.</p>"
          ) +
          block(
            "Use cases",
            "<ul>" +
              "<li>Block <code>path contains /internal-debug</code> on the public hostname.</li>" +
              "<li>Log <code>ua contains MyLegacyMonitor</code> before deciding to allow-list.</li>" +
              "<li>Temporary block of an attacker IP while Firewall lists are updated.</li>" +
              "</ul>"
          ) +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar custom WAF rules</strong>.",
              "Enter name, expression, and action.",
              "Set Hostname (preferred) so the rule only applies to that site.",
              "Optionally set organization code.",
              "Click <strong>Add rule</strong>, then Apply if prompted.",
              "Confirm behavior in Analytics.",
            ])
          ) +
          openBtn("rules", "custom WAF rules")
      ) +
      sec(
        "enterprise",
        "19. NikTiar advanced defenses",
        block(
          "What it is",
          "<p>Optional higher-order controls beyond core WAF/firewall. Enable only what your application needs.</p>"
        ) +
          "<table><thead><tr><th>Control</th><th>What it does</th><th>When to enable</th></tr></thead><tbody>" +
          "<tr><td>API Shield</td><td>Require JSON on /api, block TRACE/TRACK, body size caps</td><td>JSON APIs</td></tr>" +
          "<tr><td>GraphQL Guard</td><td>Block batching, deep nesting, alias abuse</td><td>GraphQL endpoints</td></tr>" +
          "<tr><td>Page Shield</td><td>Security response headers (CSP family)</td><td>Browser apps</td></tr>" +
          "<tr><td>Virtual Patching</td><td>Block .env, actuators, phpMyAdmin, common probes</td><td>Always useful on public edges</td></tr>" +
          "<tr><td>Auth Hardening</td><td>Rate-limit login / token / OAuth paths</td><td>Any login UI</td></tr>" +
          "<tr><td>Sensitive Data Detection</td><td>Detect PAN/SSN-like patterns in responses (default log)</td><td>Compliance-sensitive apps</td></tr>" +
          "<tr><td>Honeypot Paths</td><td>Decoy paths that trap scanners</td><td>Internet-facing sites</td></tr>" +
          "<tr><td>Advanced Bot Defense</td><td>Headless clients / challenge suspicious traffic</td><td>Bot abuse pressure</td></tr>" +
          "<tr><td>Leaked Credentials</td><td>Breach-corpus password check (k-anonymity)</td><td>Login hardening programs</td></tr>" +
          "<tr><td>Waiting Room</td><td>Queue visitors when capacity is exceeded</td><td>Ticket / flash sales / outages</td></tr>" +
          "<tr><td>Log export</td><td>Webhook export to your SIEM</td><td>Central monitoring</td></tr>" +
          "<tr><td>Mutual TLS</td><td>Request client certificates</td><td>Partner B2B APIs with PKI</td></tr>" +
          "</tbody></table>" +
          block(
            "How to configure",
            steps([
              "Open <strong>NikTiar advanced defenses</strong>.",
              "Enable only the controls that match your app (start with Virtual Patching, Auth Hardening, Page Shield).",
              "For Log export, paste your SIEM webhook URL; use Test Logpush.",
              "Click <strong>Save &amp; apply enterprise pack</strong>.",
              "Retest critical user journeys (login, API, checkout).",
            ])
          ) +
          openBtn("enterprise", "advanced defenses")
      ) +
      sec(
        "isolation",
        "20. Deployment",
        block(
          "What it is",
          "<p>Read-only posture page: this appliance is a <strong>Dedicated Edge</strong> for one organization. Unknown hosts are denied; firewall and custom rules stay Host-scoped.</p>"
        ) +
          block(
            "Security it brings",
            "<p>Strong isolation — no shared multi-tenant fallthrough, no accidental routing of foreign Host headers to your origin.</p>"
          ) +
          block(
            "Why review it",
            "<p>Confirm organization pinning, unknown-host deny, and that fallthrough stays disabled after any maintenance.</p>"
          ) +
          block(
            "How to use",
            steps([
              "Open <strong>Deployment</strong>.",
              "Verify Mode = Dedicated and Unknown Host = deny.",
              "Confirm Default origin fallthrough is disabled.",
              "If organization code is empty and you expect one, contact your platform operator to set the appliance pin.",
            ])
          ) +
          openBtn("isolation", "Deployment")
      ) +
      sec(
        "system",
        "21. System",
        block(
          "What it is",
          "<p>Appliance console URL, edge service URL, and service health for dashboard, DNS, WAF, bot defense, and related components.</p>"
        ) +
          block(
            "Why use it",
            "<p>First place to look if Apply fails, DNS stops resolving, or the site returns errors — confirm every service is Up.</p>"
          ) +
          block(
            "How to use",
            steps([
              "Open <strong>System</strong>.",
              "Confirm dashboard and waf (and dns, if you use DNS Filter) show Up / healthy.",
              "If a service is down, do not keep tightening policies — restore health first, then re-Apply.",
            ])
          ) +
          openBtn("system", "System")
      ) +
      sec(
        "checklist",
        "22. Recommended production baseline",
        "<ol class=\"man-steps\">" +
          "<li>At least one Zone with correct DNS pointing at this edge.</li>" +
          "<li>SSL mode matching origin reality.</li>" +
          "<li>Overview: Security Level Medium; WAF + Bot Defense + Browser Integrity on.</li>" +
          "<li>URL Filter: malware / phishing / ransomware categories in Block mode.</li>" +
          "<li>DNS Filter: enabled; critical categories on; LAN DNS aimed here; WAF Host block on.</li>" +
          "<li>Ransomware Defense: enabled, Block mode, all layers on.</li>" +
          "<li>Security Profiles: Recommended or Strict Ransomware applied.</li>" +
          "<li>WAF per zone: Block mode; paranoia starting at 1–2 unless you have tuned higher.</li>" +
          "<li>Rate limits on login and API paths.</li>" +
          "<li>Advanced: Virtual Patching + Auth Hardening (+ Page Shield for browser apps).</li>" +
          "<li>Apply changes → verify Analytics and a real user login.</li>" +
          "</ol>" +
          '<p class="hint">This manual stays on the appliance for operators. Use the Open buttons above to jump straight into each control.</p>'
      )
    );
  }

  global.SE_renderOperatorManual = renderOperatorManual;
})(typeof window !== "undefined" ? window : globalThis);
