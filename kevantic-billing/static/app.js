(() => {
  const $ = (s) => document.querySelector(s);
  const money = (v) =>
    Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const titles = {
    home: "Home",
    leads: "Leads",
    pipeline: "Opportunities",
    builder: "New Quote",
    quotes: "Quotes",
    invoices: "Invoices",
    parties: "Accounts",
    team: "Sales Team",
    catalog: "Product Catalog",
    settings: "Company Settings",
  };
  const subs = {
    home: "Pipeline, forecast, and cash collection",
    leads: "Capture, qualify, and convert",
    pipeline: "Kanban lifecycle to Closed Won",
    builder: "Build a customer quote from any supplier",
    quotes: "Quote approvals and PDF",
    invoices: "Tax invoices, AR, and payments",
    parties: "Customer accounts (GST parties)",
    team: "BDC, BDE, and managers",
    catalog: "NikTiar and resale catalog",
    settings: "Seller profile on PDFs",
  };
  const stageLabels = {
    prospecting: "Prospecting",
    needs_analysis: "Needs Analysis",
    proposal: "Proposal Sent",
    negotiation: "Negotiation",
    closed_won: "Closed Won",
    closed_lost: "Closed Lost",
  };
  const stageOrder = ["prospecting", "needs_analysis", "proposal", "negotiation", "closed_won", "closed_lost"];
  const leadPath = ["new", "contacted", "qualified", "converted"];
  const leadStatusLabels = {
    new: "New",
    contacted: "Contacted",
    qualified: "Qualified",
    unqualified: "Unqualified",
    converted: "Converted",
  };
  const leadSources = ["Web", "Referral", "Cold Call", "Event", "Website", "Partner", "Existing customer", "Webform", "API"];
  let catalog = [];
  let parties = [];
  let team = [];
  let states = [];
  let builderLines = [];
  let filter = "";
  let builderPrefill = null;
  let leadFilter = "open";
  let currentUser = "";

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
  function initials(name) {
    const p = String(name || "?").trim().split(/\s+/);
    return ((p[0] || "?").slice(0, 1) + (p[1] || "").slice(0, 1)).toUpperCase();
  }
  function pill(status) {
    const map = {
      new: "blue", contacted: "amber", qualified: "amber", unqualified: "gray", converted: "green",
      prospecting: "blue", needs_analysis: "amber", proposal: "amber", negotiation: "amber",
      closed_won: "green", closed_lost: "red",
      draft: "gray", sent: "blue", accepted: "green", invoiced: "green", declined: "red",
      pending_approval: "amber", paid: "green", partially_paid: "amber", issued: "blue", overdue: "red", void: "gray",
    };
    const label = leadStatusLabels[status] || stageLabels[status] || status;
    return `<span class="pill ${map[status] || "gray"}">${esc(label)}</span>`;
  }
  function chevron(steps, current, { won = false, lost = false } = {}) {
    const idx = steps.indexOf(current);
    return `<div class="path">${steps
      .map((s, i) => {
        let cls = "path-step";
        if (lost && s === current) cls += " lost";
        else if (won && i === steps.length - 1) cls += " won";
        else if (i < idx) cls += " done";
        else if (i === idx) cls += " active";
        const label = leadStatusLabels[s] || stageLabels[s] || s;
        return `<div class="${cls}">${esc(label)}</div>`;
      })
      .join("")}</div>`;
  }
  function creds() {
    const u = localStorage.getItem("kb_user") || "";
    const p = localStorage.getItem("kb_pass") || "";
    if (!u || !p) return null;
    return "Basic " + btoa(`${u}:${p}`);
  }
  function setStatus(msg, err = false) {
    const el = $("#status");
    el.textContent = msg;
    el.classList.add("show");
    el.classList.toggle("err", !!err);
    clearTimeout(setStatus._t);
    setStatus._t = setTimeout(() => el.classList.remove("show"), 4200);
  }
  async function api(path, opts = {}) {
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    const auth = creds();
    if (auth) headers.Authorization = auth;
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401) throw new Error("Unauthorized — check credentials");
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }
  function openPdf(url) {
    const u = localStorage.getItem("kb_user");
    const p = localStorage.getItem("kb_pass");
    fetch(url, { headers: { Authorization: "Basic " + btoa(`${u}:${p}`) } })
      .then((r) => {
        if (!r.ok) throw new Error("PDF failed");
        return r.blob();
      })
      .then((blob) => window.open(URL.createObjectURL(blob), "_blank"))
      .catch((e) => setStatus(e.message, true));
  }
  function showApp(on) {
    $("#loginGate").classList.toggle("hidden", on);
    $("#appShell").classList.toggle("hidden", !on);
  }
  function openDrawer(html) {
    $("#drawerBody").innerHTML = html;
    $("#drawer").classList.remove("hidden");
  }
  function closeDrawer() {
    $("#drawer").classList.add("hidden");
  }
  function openModal(title, bodyHtml, footHtml) {
    $("#modalTitle").textContent = title;
    $("#modalBody").innerHTML = bodyHtml;
    $("#modalFoot").innerHTML = footHtml || "";
    $("#modal").classList.remove("hidden");
  }
  function closeModal() {
    $("#modal").classList.add("hidden");
  }
  function teamOptions(selected = "", { allowEmpty = true } = {}) {
    const empty = allowEmpty ? `<option value="">Unassigned</option>` : `<option value="">Select owner…</option>`;
    return empty + team
      .filter((p) => p.active)
      .map((p) => `<option value="${p.id}" ${p.id === selected ? "selected" : ""}>${esc(p.name)} (${esc(p.role_label || p.role)})</option>`)
      .join("");
  }
  function switchTab(name) {
    document.querySelectorAll("#nav button").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll("#main .panel").forEach((p) => p.classList.add("hidden"));
    $(`#tab-${name}`).classList.remove("hidden");
    $("#pageTitle").textContent = titles[name] || name;
    $("#pageSub").textContent = subs[name] || "";
    if (name === "home") renderHome();
    if (name === "leads") renderLeads();
    if (name === "pipeline") renderPipeline();
    if (name === "quotes") renderQuotes();
    if (name === "invoices") renderInvoices();
    if (name === "parties") renderParties();
    if (name === "team") renderTeam();
    if (name === "catalog") renderCatalog();
    if (name === "builder") renderBuilder();
    if (name === "settings") renderSettings();
  }
  async function login() {
    localStorage.setItem("kb_user", $("#user").value.trim());
    localStorage.setItem("kb_pass", $("#pass").value);
    try {
      const me = await api("/api/me");
      currentUser = me.user;
      showApp(true);
      $("#sideCompany").textContent = me.company_name;
      $("#userChip").textContent = me.user;
      $("#userAvatar").textContent = initials(me.user);
      await bootstrap();
      switchTab("home");
      setStatus(`Signed in · ${me.company_name}`);
    } catch (e) {
      showApp(false);
      setStatus(e.message, true);
    }
  }
  function logout() {
    localStorage.removeItem("kb_user");
    localStorage.removeItem("kb_pass");
    showApp(false);
    setStatus("Signed out");
  }
  async function bootstrap() {
    catalog = await api("/api/catalog?active_only=false");
    parties = await api("/api/parties");
    team = await api("/api/crm/team");
    states = await api("/api/settings/states");
  }
  function stateOptions(selectedCode = "27") {
    return states
      .map((s) => `<option value="${s.code}" data-name="${s.name}" ${s.code === selectedCode ? "selected" : ""}>${s.code} — ${s.name}</option>`)
      .join("");
  }

  async function renderHome() {
    const el = $("#tab-home");
    el.innerHTML = `<div class="card"><p class="muted">Loading workspace…</p></div>`;
    try {
      const [d, crm] = await Promise.all([api("/api/dashboard"), api("/api/crm/summary")]);
      const k = d.kpis;
      const agingMax = Math.max(...Object.values(d.aging), 1);
      const stages = stageOrder.filter((s) => s !== "closed_lost");
      const maxStage = Math.max(...stages.map((s) => (crm.by_stage[s] || {}).amount || 0), 1);
      el.innerHTML = `
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Open leads</div><div class="value">${crm.open_leads}</div><div class="hint muted">Ready to qualify</div></div>
          <div class="kpi"><div class="label">Pipeline value</div><div class="value">₹ ${money(crm.pipeline_value)}</div><div class="hint muted">${crm.open_opportunities} open opportunities</div></div>
          <div class="kpi warn"><div class="label">Weighted forecast</div><div class="value">₹ ${money(crm.weighted_forecast)}</div><div class="hint muted">Deal value × win %</div></div>
          <div class="kpi ok"><div class="label">Closed Won</div><div class="value">${crm.won_count}</div><div class="hint muted">₹ ${money(crm.won_value)} · win ${crm.win_rate || 0}%</div></div>
        </div>
        <div class="kpi-grid">
          <div class="kpi warn"><div class="label">Outstanding AR</div><div class="value">₹ ${money(k.outstanding_ar)}</div><div class="hint muted">${k.overdue_count} overdue</div></div>
          <div class="kpi"><div class="label">Invoiced MTD</div><div class="value">₹ ${money(k.invoiced_mtd)}</div><div class="hint muted">Collected ₹ ${money(k.collected_mtd)}</div></div>
          <div class="kpi"><div class="label">Open quotes</div><div class="value">${k.open_quotes}</div><div class="hint muted">₹ ${money(k.open_quotes_value)}</div></div>
          <div class="kpi"><div class="label">Accounts</div><div class="value">${k.parties}</div><div class="hint muted">Customer parties</div></div>
        </div>
        <div class="grid-2">
          <div class="card">
            <div class="card-head"><h3 class="card-title">Pipeline by stage</h3></div>
            ${stages.map((s) => {
              const row = crm.by_stage[s] || { count: 0, amount: 0 };
              const pct = Math.round((row.amount / maxStage) * 100);
              return `<div class="bar-row"><span style="width:8.5rem">${esc(stageLabels[s])}</span><div class="bar"><span style="width:${pct}%"></span></div><span class="money">₹ ${money(row.amount)}</span></div>`;
            }).join("")}
          </div>
          <div class="card">
            <div class="card-head"><h3 class="card-title">Receivables aging</h3></div>
            ${["current", "1_30", "31_60", "61_90", "90_plus"].map((key) => {
              const label = { current: "Not due", "1_30": "1–30 days", "31_60": "31–60", "61_90": "61–90", "90_plus": "90+" }[key];
              const val = d.aging[key] || 0;
              const pct = Math.round((val / agingMax) * 100);
              return `<div class="bar-row"><span style="width:5.5rem">${label}</span><div class="bar"><span style="width:${pct}%;background:${key === "90_plus" ? "var(--danger)" : "var(--brand)"}"></span></div><span class="money">₹ ${money(val)}</span></div>`;
            }).join("")}
          </div>
        </div>
        <div class="card">
          <div class="card-head"><h3 class="card-title">Quick actions</h3></div>
          <div class="launcher">
            <button type="button" data-go="lead"><strong>+ New Lead</strong><span>Manual capture</span></button>
            <button type="button" data-go="leads"><strong>Lead inbox</strong><span>Qualify & convert</span></button>
            <button type="button" data-go="pipeline"><strong>Opportunity board</strong><span>Move deals forward</span></button>
            <button type="button" data-go="builder"><strong>New Quote</strong><span>Any supplier / part</span></button>
            <button type="button" data-go="invoices"><strong>Collect cash</strong><span>Record payments</span></button>
            <button type="button" data-go="team"><strong>Sales team</strong><span>BDC / BDE owners</span></button>
          </div>
        </div>`;
      el.querySelectorAll("[data-go]").forEach((b) =>
        b.addEventListener("click", () => {
          if (b.dataset.go === "lead") openNewLeadModal();
          else switchTab(b.dataset.go);
        })
      );
    } catch (e) {
      el.innerHTML = `<div class="card">${esc(e.message)}</div>`;
    }
  }


  function splitName(full) {
    const parts = String(full || "").trim().split(/\s+/);
    return { first: parts[0] || "", last: parts.slice(1).join(" ") };
  }

  function openNewLeadModal(prefill = {}) {
    const n = splitName(prefill.contact_name);
    openModal(
      "New Lead",
      `<div class="form-grid">
        <label class="field">First name <input id="nlFirst" value="${esc(n.first)}" /></label>
        <label class="field">Last name <input id="nlLast" value="${esc(n.last)}" /></label>
        <label class="field span-2">Company name <input id="nlCompany" value="${esc(prefill.company_name || "")}" required /></label>
        <label class="field">Email <input id="nlEmail" type="email" value="${esc(prefill.email || "")}" /></label>
        <label class="field">Phone <input id="nlPhone" value="${esc(prefill.phone || "")}" /></label>
        <label class="field">Lead source
          <select id="nlSource">${leadSources.map((s) => `<option ${prefill.source === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
        </label>
        <label class="field">Lead status
          <select id="nlStatus">
            <option value="new">New</option><option value="contacted">Contacted</option><option value="qualified">Qualified</option>
          </select>
        </label>
        <label class="field">Estimated budget ₹ <input id="nlBudget" type="number" min="0" step="0.01" value="${prefill.estimated_budget ?? ""}" /></label>
        <label class="field">Assigned to <select id="nlOwner">${teamOptions(prefill.salesperson_id || "")}</select></label>
        <label class="field span-2">Requirement / interest <input id="nlInterest" value="${esc(prefill.interest || "")}" placeholder="What the customer wants" /></label>
        <label class="field span-2">Notes <textarea id="nlNotes" rows="3">${esc(prefill.notes || "")}</textarea></label>
      </div>`,
      `<button type="button" class="btn btn-ghost" data-close-modal>Cancel</button>
       <button type="button" class="btn btn-brand" id="nlSave">Save Lead</button>`
    );
    $("#nlSave").addEventListener("click", async () => {
      const company = $("#nlCompany").value.trim();
      if (!company) return setStatus("Company name is required", true);
      try {
        const lead = await api("/api/crm/leads", {
          method: "POST",
          body: JSON.stringify({
            company_name: company,
            first_name: $("#nlFirst").value.trim() || null,
            last_name: $("#nlLast").value.trim() || null,
            email: $("#nlEmail").value.trim() || null,
            phone: $("#nlPhone").value.trim() || null,
            source: $("#nlSource").value,
            status: $("#nlStatus").value,
            estimated_budget: $("#nlBudget").value === "" ? null : Number($("#nlBudget").value),
            salesperson_id: $("#nlOwner").value || null,
            interest: $("#nlInterest").value.trim() || null,
            notes: $("#nlNotes").value.trim() || null,
          }),
        });
        closeModal();
        setStatus(`Lead ${lead.lead_number} created`);
        switchTab("leads");
        openLeadDetail(lead.id);
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  async function openConvertModal(leadId) {
    const lead = await api(`/api/crm/leads/${leadId}`);
    openModal(
      "Convert Lead",
      `<p class="muted">This creates an <strong>Account</strong>, a <strong>Contact</strong>, and an <strong>Opportunity</strong> in one step — Salesforce style.</p>
       <div class="form-grid" style="margin-top:1rem">
         <label class="field span-2">Account (company) <input id="cvAccount" value="${esc(lead.company_name)}" disabled /></label>
         <label class="field span-2">Contact <input id="cvContact" value="${esc(lead.contact_name || "")}" disabled /></label>
         <label class="field span-2">Opportunity name <input id="cvOppName" value="${esc(lead.company_name + " — " + (lead.interest || "New opportunity").split(String.fromCharCode(10))[0])}" /></label>
         <label class="field">Deal value ₹ <input id="cvAmount" type="number" min="0" step="0.01" value="${lead.estimated_budget ?? 0}" /></label>
         <label class="field">Close date <input id="cvClose" type="date" /></label>
         <label class="field span-2">Opportunity owner <select id="cvOwner">${teamOptions(lead.salesperson_id || "", { allowEmpty: false })}</select></label>
       </div>`,
      `<button type="button" class="btn btn-ghost" data-close-modal>Cancel</button>
       <button type="button" class="btn btn-brand" id="cvGo">Convert</button>`
    );
    $("#cvGo").addEventListener("click", async () => {
      if (!$("#cvOwner").value) return setStatus("Assign a BDE or BDC", true);
      try {
        const res = await api(`/api/crm/leads/${leadId}/convert`, {
          method: "POST",
          body: JSON.stringify({
            salesperson_id: $("#cvOwner").value,
            opportunity_name: $("#cvOppName").value.trim() || null,
            amount_expected: Number($("#cvAmount").value || 0),
            close_date: $("#cvClose").value || null,
            create_opportunity: true,
          }),
        });
        parties = await api("/api/parties");
        closeModal();
        setStatus(`Converted → ${res.opportunity.opportunity_number}`);
        switchTab("pipeline");
        openOpportunity(res.opportunity.id);
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  async function openLeadDetail(id) {
    try {
      const lead = await api(`/api/crm/leads/${id}`);
      const pathSteps = lead.status === "unqualified" ? ["new", "contacted", "unqualified"] : leadPath;
      openDrawer(`
        <div class="record-banner" style="margin:0 0 1rem;box-shadow:none;border:0;padding:0">
          <div class="record-banner-top">
            <div>
              <p class="record-type">Lead · ${esc(lead.lead_number)}</p>
              <h2>${esc(lead.company_name)}</h2>
              <div style="margin-top:.45rem">${pill(lead.status)}</div>
            </div>
            <div class="quick-actions">
              ${lead.status !== "converted" && lead.status !== "unqualified" ? `<button type="button" class="btn btn-brand" id="ldConvert">Convert Lead</button>` : ""}
              ${lead.opportunity_id ? `<button type="button" class="btn btn-ghost" id="ldOpenOpp">Open Opportunity</button>` : ""}
            </div>
          </div>
          ${chevron(pathSteps, lead.status === "unqualified" ? "unqualified" : lead.status, { lost: lead.status === "unqualified" })}
          <div class="record-meta">
            <div><div class="m-label">Contact</div><div class="m-value">${esc(lead.contact_name || "—")}</div></div>
            <div><div class="m-label">Owner</div><div class="m-value">${esc(lead.owner || "Unassigned")}</div></div>
            <div><div class="m-label">Source</div><div class="m-value">${esc(lead.source || "—")}</div></div>
            <div><div class="m-label">Est. budget</div><div class="m-value">₹ ${money(lead.estimated_budget || 0)}</div></div>
          </div>
        </div>
        <div class="card">
          <h3 class="card-title">Lead details</h3>
          <div class="form-grid">
            <label class="field">Status
              <select id="ldStatus" ${lead.status === "converted" ? "disabled" : ""}>
                ${["new","contacted","qualified","unqualified"].map((s) => `<option value="${s}" ${lead.status===s?"selected":""}>${leadStatusLabels[s]}</option>`).join("")}
              </select>
            </label>
            <label class="field">Assigned to <select id="ldOwner" ${lead.status === "converted" ? "disabled" : ""}>${teamOptions(lead.salesperson_id || "")}</select></label>
            <label class="field span-2">Requirement <input id="ldInterest" value="${esc(lead.interest || "")}" ${lead.status === "converted" ? "disabled" : ""} /></label>
            <label class="field">Email <input id="ldEmail" value="${esc(lead.email || "")}" ${lead.status === "converted" ? "disabled" : ""} /></label>
            <label class="field">Phone <input id="ldPhone" value="${esc(lead.phone || "")}" ${lead.status === "converted" ? "disabled" : ""} /></label>
            <label class="field span-2">Notes <textarea id="ldNotes" rows="3" ${lead.status === "converted" ? "disabled" : ""}>${esc(lead.notes || "")}</textarea></label>
          </div>
          ${lead.status !== "converted" ? `<div class="row-actions" style="margin-top:.8rem"><button type="button" class="btn btn-brand" id="ldSave">Save</button></div>` : ""}
        </div>
        <div class="card">
          <h3 class="card-title">Activity</h3>
          <div class="form-row">
            <label>Type <select id="ldActKind"><option value="call">Call</option><option value="email">Email</option><option value="meeting">Meeting</option><option value="note">Note</option><option value="task">Task</option></select></label>
            <label>Subject <input id="ldActSub" /></label>
            <button type="button" class="btn btn-ghost" id="ldActSave">Log</button>
          </div>
          <ul class="timeline">
            ${(lead.activities || []).map((a) => `<li><div class="t-kind">${esc(a.kind)}</div><div class="t-sub">${esc(a.subject)}</div><div class="t-when">${esc((a.created_at || "").slice(0, 16))} · ${esc(a.owner || "")}</div></li>`).join("") || "<li class='muted'>No activity yet</li>"}
          </ul>
        </div>`);
      const saveBtn = $("#ldSave");
      if (saveBtn) {
        saveBtn.addEventListener("click", async () => {
          try {
            const res = await api(`/api/crm/leads/${id}`, {
              method: "PATCH",
              body: JSON.stringify({
                status: $("#ldStatus").value,
                salesperson_id: $("#ldOwner").value || null,
                interest: $("#ldInterest").value.trim() || null,
                email: $("#ldEmail").value.trim() || null,
                phone: $("#ldPhone").value.trim() || null,
                notes: $("#ldNotes").value.trim() || null,
              }),
            });
            if (res.converted) {
              parties = await api("/api/parties");
              setStatus(`Converted → ${res.opportunity.opportunity_number}`);
              closeDrawer();
              openOpportunity(res.opportunity.id);
            } else {
              setStatus("Lead saved");
              openLeadDetail(id);
              if (!$("#tab-leads").classList.contains("hidden")) renderLeads();
            }
          } catch (e) {
            setStatus(e.message, true);
          }
        });
      }
      const conv = $("#ldConvert");
      if (conv) conv.addEventListener("click", () => openConvertModal(id));
      const oo = $("#ldOpenOpp");
      if (oo) oo.addEventListener("click", () => openOpportunity(lead.opportunity_id));
      $("#ldActSave").addEventListener("click", async () => {
        const subject = $("#ldActSub").value.trim();
        if (!subject) return setStatus("Subject required", true);
        try {
          await api(`/api/crm/leads/${id}/activities`, {
            method: "POST",
            body: JSON.stringify({ kind: $("#ldActKind").value, subject }),
          });
          openLeadDetail(id);
        } catch (e) {
          setStatus(e.message, true);
        }
      });
    } catch (e) {
      setStatus(e.message, true);
    }
  }

  async function renderLeads() {
    const el = $("#tab-leads");
    el.innerHTML = `<div class="card"><p class="muted">Loading leads…</p></div>`;
    try {
      if (!team.length) team = await api("/api/crm/team");
      const leads = await api("/api/crm/leads");
      let rows = leads.filter(
        (r) =>
          matchFilter(r.company_name) ||
          matchFilter(r.contact_name) ||
          matchFilter(r.interest) ||
          matchFilter(r.source) ||
          matchFilter(r.lead_number) ||
          matchFilter(r.owner)
      );
      if (leadFilter === "open") rows = rows.filter((r) => ["new", "contacted", "qualified"].includes(r.status));
      if (leadFilter === "mine") {
        rows = leads.filter(
          (r) =>
            r.owner &&
            ["new", "contacted", "qualified"].includes(r.status) &&
            (matchFilter(r.company_name) ||
              matchFilter(r.contact_name) ||
              matchFilter(r.lead_number) ||
              matchFilter(r.owner) ||
              !filter)
        );
      }
      if (leadFilter === "converted") {
        rows = leads.filter(
          (r) =>
            r.status === "converted" &&
            (matchFilter(r.company_name) || matchFilter(r.lead_number) || !filter)
        );
      }
      if (leadFilter === "all") {
        rows = leads.filter(
          (r) =>
            matchFilter(r.company_name) ||
            matchFilter(r.contact_name) ||
            matchFilter(r.lead_number) ||
            !filter
        );
      }

      el.innerHTML = `
        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Lead inbox</h3>
            <button type="button" class="btn btn-brand" id="btnNewLead2">+ New Lead</button>
          </div>
          <div class="filter-tabs">
            <button type="button" data-lf="open" class="${leadFilter === "open" ? "active" : ""}">All Open Leads</button>
            <button type="button" data-lf="mine" class="${leadFilter === "mine" ? "active" : ""}">My Leads</button>
            <button type="button" data-lf="converted" class="${leadFilter === "converted" ? "active" : ""}">Converted</button>
            <button type="button" data-lf="all" class="${leadFilter === "all" ? "active" : ""}">All</button>
          </div>
          <div class="table-wrap">
            <table class="data">
              <thead><tr><th>Lead</th><th>Company / Contact</th><th>Requirement</th><th>Source</th><th>Budget</th><th>Status</th><th>Owner</th><th></th></tr></thead>
              <tbody>
              ${rows.map((r) => `<tr class="clickable" data-open-lead="${r.id}">
                <td><code>${esc(r.lead_number)}</code></td>
                <td><strong>${esc(r.company_name)}</strong><div class="muted">${esc(r.contact_name || "")}</div></td>
                <td>${esc(r.interest || "—")}</td>
                <td>${esc(r.source || "—")}</td>
                <td class="money">₹ ${money(r.estimated_budget || 0)}</td>
                <td>${pill(r.status)}</td>
                <td><span class="avatar sm" title="${esc(r.owner || "")}">${esc(initials(r.owner || "?"))}</span> ${esc(r.owner || "—")}</td>
                <td class="row-actions" onclick="event.stopPropagation()">
                  ${r.status !== "converted" && r.status !== "unqualified" ? `<button type="button" class="btn btn-brand btn-sm" data-convert="${r.id}">Convert</button>` : ""}
                  <button type="button" class="btn btn-ghost btn-sm" data-open-lead-btn="${r.id}">Open</button>
                </td>
              </tr>`).join("") || `<tr><td colspan="8" class="muted">No leads in this view. Create one with + New Lead.</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>`;
      $("#btnNewLead2").addEventListener("click", () => openNewLeadModal());
      el.querySelectorAll("[data-lf]").forEach((b) =>
        b.addEventListener("click", () => {
          leadFilter = b.dataset.lf;
          renderLeads();
        })
      );
      el.querySelectorAll("[data-open-lead]").forEach((tr) =>
        tr.addEventListener("click", () => openLeadDetail(tr.dataset.openLead))
      );
      el.querySelectorAll("[data-open-lead-btn]").forEach((b) =>
        b.addEventListener("click", () => openLeadDetail(b.dataset.openLeadBtn))
      );
      el.querySelectorAll("[data-convert]").forEach((b) =>
        b.addEventListener("click", () => openConvertModal(b.dataset.convert))
      );
    } catch (e) {
      el.innerHTML = `<div class="card">${esc(e.message)}</div>`;
    }
  }

  async function renderPipeline() {
    const el = $("#tab-pipeline");
    el.innerHTML = `<div class="card"><p class="muted">Loading opportunities…</p></div>`;
    try {
      if (!team.length) team = await api("/api/crm/team");
      if (!parties.length) parties = await api("/api/parties");
      const opps = await api("/api/crm/opportunities");
      const rows = opps.filter(
        (r) => matchFilter(r.name) || matchFilter(r.party_name) || matchFilter(r.opportunity_number) || matchFilter(r.owner)
      );
      const openStages = ["prospecting", "needs_analysis", "proposal", "negotiation"];
      el.innerHTML = `
        <div class="card">
          <div class="card-head"><h3 class="card-title">New opportunity on existing Account</h3></div>
          <div class="form-row">
            <label>Account <select id="opParty"><option value="">Select…</option>${parties.map((p) => `<option value="${p.id}">${esc(p.legal_name)}</option>`).join("")}</select></label>
            <label>Opportunity name <input id="opName" placeholder="Customer requirement" /></label>
            <label>Deal value ₹ <input id="opAmount" type="number" min="0" step="0.01" value="0" /></label>
            <label>Owner <select id="opOwner">${teamOptions("", { allowEmpty: false })}</select></label>
            <button type="button" id="opSave" class="btn btn-brand">Create</button>
          </div>
        </div>
        <div class="board">
          ${openStages.map((stage) => {
            const items = rows.filter((r) => r.stage === stage);
            return `<div class="col" data-stage="${stage}">
              <div class="col-head"><h3>${stageLabels[stage]}</h3><span class="col-count">${items.length}</span></div>
              ${items.map((r) => `<div class="deal" draggable="true" data-opp-id="${r.id}">
                <strong>${esc(r.name)}</strong>
                <div class="deal-account">${esc(r.party_name || "")}</div>
                <div class="deal-amt">₹ ${money(r.amount_expected)}</div>
                <div class="deal-foot">
                  <span>${r.close_date || "No close date"}</span>
                  <span class="avatar sm" title="${esc(r.owner || "")}">${esc(initials(r.owner || "?"))}</span>
                </div>
              </div>`).join("") || `<p class="muted" style="padding:.4rem">Drop deals here</p>`}
            </div>`;
          }).join("")}
        </div>
        <div class="card" style="margin-top:.9rem">
          <h3 class="card-title">Closed</h3>
          <div class="table-wrap"><table class="data"><thead><tr><th>Opportunity</th><th>Account</th><th>Stage</th><th>Owner</th><th>Value</th></tr></thead>
          <tbody>
          ${rows.filter((r) => r.stage === "closed_won" || r.stage === "closed_lost").map((r) => `
            <tr class="clickable" data-open-opp="${r.id}">
              <td>${esc(r.opportunity_number)}<br/>${esc(r.name)}</td>
              <td>${esc(r.party_name || "")}</td>
              <td>${pill(r.stage)}</td>
              <td>${esc(r.owner || "—")}</td>
              <td class="money">₹ ${money(r.amount_expected)}</td>
            </tr>`).join("") || `<tr><td colspan="5" class="muted">No closed opportunities yet</td></tr>`}
          </tbody></table></div>
        </div>`;
      $("#opSave").addEventListener("click", async () => {
        if (!$("#opParty").value || !$("#opName").value.trim()) return setStatus("Account and name required", true);
        if (!$("#opOwner").value) return setStatus("Assign an owner", true);
        try {
          const opp = await api("/api/crm/opportunities", {
            method: "POST",
            body: JSON.stringify({
              party_id: $("#opParty").value,
              name: $("#opName").value.trim(),
              amount_expected: Number($("#opAmount").value || 0),
              salesperson_id: $("#opOwner").value,
            }),
          });
          setStatus(`Opportunity ${opp.opportunity_number} created`);
          openOpportunity(opp.id);
        } catch (e) {
          setStatus(e.message, true);
        }
      });
      el.querySelectorAll("[data-open-opp]").forEach((n) => n.addEventListener("click", () => openOpportunity(n.dataset.openOpp)));
      el.querySelectorAll(".deal").forEach((card) => {
        card.addEventListener("dragstart", (ev) => {
          ev.dataTransfer.setData("text/plain", card.dataset.oppId);
          card.classList.add("dragging");
        });
        card.addEventListener("dragend", () => card.classList.remove("dragging"));
        card.addEventListener("click", () => openOpportunity(card.dataset.oppId));
      });
      el.querySelectorAll(".col").forEach((col) => {
        col.addEventListener("dragover", (ev) => {
          ev.preventDefault();
          col.classList.add("drag-over");
        });
        col.addEventListener("dragleave", () => col.classList.remove("drag-over"));
        col.addEventListener("drop", async (ev) => {
          ev.preventDefault();
          col.classList.remove("drag-over");
          const id = ev.dataTransfer.getData("text/plain");
          const stage = col.dataset.stage;
          if (!id || !stage) return;
          try {
            await api(`/api/crm/opportunities/${id}`, { method: "PATCH", body: JSON.stringify({ stage }) });
            setStatus(`Moved to ${stageLabels[stage]}`);
            renderPipeline();
          } catch (e) {
            setStatus(e.message, true);
          }
        });
      });
    } catch (e) {
      el.innerHTML = `<div class="card">${esc(e.message)}</div>`;
    }
  }

  async function openOpportunity(id) {
    try {
      if (!team.length) team = await api("/api/crm/team");
      const o = await api(`/api/crm/opportunities/${id}`);
      const openPath = ["prospecting", "needs_analysis", "proposal", "negotiation", "closed_won"];
      openDrawer(`
        <div class="record-banner" style="margin:0 0 1rem;box-shadow:none;border:0;padding:0">
          <div class="record-banner-top">
            <div>
              <p class="record-type">Opportunity · ${esc(o.opportunity_number)}</p>
              <h2>${esc(o.name)}</h2>
              <div style="margin-top:.45rem">${pill(o.stage)}</div>
            </div>
            <div class="quick-actions">
              <button type="button" class="btn btn-brand" id="oppQuote">Create Quote</button>
              <button type="button" class="btn btn-ghost" id="oppSave">Save</button>
            </div>
          </div>
          ${chevron(openPath, o.stage === "closed_lost" ? "negotiation" : o.stage, { won: o.stage === "closed_won", lost: o.stage === "closed_lost" })}
          <div class="record-meta">
            <div><div class="m-label">Account</div><div class="m-value">${esc(o.party_name || "—")}</div></div>
            <div><div class="m-label">Deal value</div><div class="m-value">₹ ${money(o.amount_expected)}</div></div>
            <div><div class="m-label">Weighted</div><div class="m-value">₹ ${money(o.weighted_value)} (${o.probability || 0}%)</div></div>
            <div><div class="m-label">Owner</div><div class="m-value">${esc(o.owner || "—")}</div></div>
          </div>
        </div>
        <div class="card">
          <h3 class="card-title">Deal properties</h3>
          <div class="form-grid">
            <label class="field">Stage <select id="oppStage">${Object.entries(stageLabels).map(([k,l]) => `<option value="${k}" ${o.stage===k?"selected":""}>${l}</option>`).join("")}</select></label>
            <label class="field">Assigned to <select id="oppOwner">${teamOptions(o.salesperson_id || "")}</select></label>
            <label class="field">Deal value ₹ <input id="oppAmount" type="number" step="0.01" value="${o.amount_expected}" /></label>
            <label class="field">Close date <input id="oppClose" type="date" value="${o.close_date || ""}" /></label>
            <label class="field span-2">Requirement <input id="oppReq" value="${esc(o.requirement || "")}" /></label>
            <label class="field span-2">Next step <input id="oppNext" value="${esc(o.next_step || "")}" /></label>
            <label class="field">Customer PO <input id="oppPo" value="${esc(o.customer_po || "")}" /></label>
            <label class="field">Fulfillment
              <select id="oppFulfill">${["none","customer_po","ordered_from_supplier","delivered","invoiced","collected"].map((k)=>`<option value="${k}" ${o.fulfillment_status===k?"selected":""}>${k.replaceAll("_"," ")}</option>`).join("")}</select>
            </label>
            <label class="field span-2">Notes <textarea id="oppNotes" rows="2">${esc(o.notes || "")}</textarea></label>
          </div>
        </div>
        <div class="card">
          <h3 class="card-title">Quotes ↔ Invoices</h3>
          <ul>
            ${(o.quotes || []).map((q) => `<li><strong>${esc(q.quote_number)}</strong> · ${esc(q.status)} · ₹ ${money(q.total_amount)}</li>`).join("") || "<li class='muted'>No quote yet — use Create Quote</li>"}
            ${(o.invoices || []).map((i) => `<li><strong>${esc(i.invoice_number)}</strong> · ${esc(i.status)} · ₹ ${money(i.total_amount)} · paid ₹ ${money(i.amount_paid)}</li>`).join("")}
          </ul>
        </div>
        <div class="card">
          <h3 class="card-title">OEM / distributor prices</h3>
          <ul>${(o.supplier_prices || []).map((p) => `<li><strong>${esc(p.supplier_name)}</strong> (${esc(p.supplier_kind)}) · ${esc(p.item_name)} · cost ₹ ${money(p.unit_cost)} · sell ₹ ${money(p.sell_unit_price)} · ${esc(p.status)}</li>`).join("") || "<li class='muted'>None logged yet</li>"}</ul>
        </div>
        <div class="card">
          <h3 class="card-title">Activity timeline</h3>
          <div class="form-row">
            <label>Type <select id="actKind"><option value="note">Note</option><option value="call">Call</option><option value="email">Email</option><option value="meeting">Meeting</option><option value="task">Task</option></select></label>
            <label>Subject <input id="actSubject" /></label>
            <button type="button" class="btn btn-ghost" id="actSave">Add</button>
          </div>
          <ul class="timeline">
            ${(o.activities || []).map((a) => `<li><div class="t-kind">${esc(a.kind)}</div><div class="t-sub">${esc(a.subject)}</div><div class="t-when">${esc((a.created_at || "").slice(0,16))} · ${esc(a.owner || "")}</div></li>`).join("") || "<li class='muted'>No activity yet</li>"}
          </ul>
        </div>`);
      $("#oppSave").addEventListener("click", async () => {
        try {
          await api(`/api/crm/opportunities/${id}`, {
            method: "PATCH",
            body: JSON.stringify({
              stage: $("#oppStage").value,
              salesperson_id: $("#oppOwner").value || null,
              amount_expected: Number($("#oppAmount").value || 0),
              close_date: $("#oppClose").value || null,
              requirement: $("#oppReq").value.trim() || null,
              next_step: $("#oppNext").value.trim() || null,
              customer_po: $("#oppPo").value.trim() || null,
              fulfillment_status: $("#oppFulfill").value,
              notes: $("#oppNotes").value.trim() || null,
            }),
          });
          setStatus("Opportunity saved");
          openOpportunity(id);
          if (!$("#tab-pipeline").classList.contains("hidden")) renderPipeline();
        } catch (e) {
          setStatus(e.message, true);
        }
      });
      $("#oppQuote").addEventListener("click", () => {
        builderPrefill = {
          party_id: o.party_id,
          opportunity_id: o.id,
          opportunity_name: o.name,
          sales_owner: o.owner || "",
        };
        closeDrawer();
        switchTab("builder");
      });
      $("#actSave").addEventListener("click", async () => {
        const subject = $("#actSubject").value.trim();
        if (!subject) return setStatus("Subject required", true);
        try {
          await api(`/api/crm/opportunities/${id}/activities`, {
            method: "POST",
            body: JSON.stringify({ kind: $("#actKind").value, subject }),
          });
          openOpportunity(id);
        } catch (e) {
          setStatus(e.message, true);
        }
      });
    } catch (e) {
      setStatus(e.message, true);
    }
  }

  async function renderTeam() {
    const el = $("#tab-team");
    el.innerHTML = `<div class="card"><p class="muted">Loading…</p></div>`;
    try {
      team = await api("/api/crm/team");
      el.innerHTML = `
        <div class="card">
          <div class="card-head"><h3 class="card-title">Add sales person</h3></div>
          <div class="form-row">
            <label>Name <input id="tmName" /></label>
            <label>Role <select id="tmRole"><option value="bdc">BDC</option><option value="bde">BDE</option><option value="manager">Sales manager</option></select></label>
            <label>Email <input id="tmEmail" /></label>
            <label>Phone <input id="tmPhone" /></label>
            <button type="button" id="tmSave" class="btn btn-brand">Add</button>
          </div>
        </div>
        <div class="card"><div class="table-wrap"><table class="data">
          <thead><tr><th></th><th>Name</th><th>Role</th><th>Email</th><th>Phone</th><th>Status</th></tr></thead>
          <tbody>${team.map((p) => `<tr>
            <td><span class="avatar sm">${esc(initials(p.name))}</span></td>
            <td><strong>${esc(p.name)}</strong></td>
            <td>${esc(p.role_label || p.role)}</td>
            <td>${esc(p.email || "—")}</td>
            <td>${esc(p.phone || "—")}</td>
            <td>${p.active ? pill("qualified").replace("Qualified","Active") : pill("unqualified").replace("Unqualified","Inactive")}</td>
          </tr>`).join("")}</tbody>
        </table></div></div>`;
      $("#tmSave").addEventListener("click", async () => {
        const name = $("#tmName").value.trim();
        if (!name) return setStatus("Name required", true);
        try {
          await api("/api/crm/team", {
            method: "POST",
            body: JSON.stringify({
              name,
              role: $("#tmRole").value,
              email: $("#tmEmail").value.trim() || null,
              phone: $("#tmPhone").value.trim() || null,
            }),
          });
          setStatus("Sales person added");
          renderTeam();
        } catch (e) {
          setStatus(e.message, true);
        }
      });
    } catch (e) {
      el.innerHTML = `<div class="card">${esc(e.message)}</div>`;
    }
  }


  function matchFilter(text) {
    if (!filter) return true;
    return String(text || "").toLowerCase().includes(filter.toLowerCase());
  }

  async function renderQuotes() {
    const el = $("#tab-quotes");
    el.innerHTML = `<div class="card">Loading…</div>`;
    try {
      const quotes = await api("/api/quotes");
      const rows = quotes.filter(
        (q) =>
          matchFilter(q.quote_number) ||
          matchFilter(q.party_name) ||
          matchFilter(q.status) ||
          matchFilter(q.opportunity_name)
      );
      el.innerHTML = `<div class="card"><div class="table-wrap"><table class="data"><thead><tr>
          <th>Number</th><th>Party</th><th>Opportunity</th><th>Status</th><th>Tax</th><th>Total</th><th></th>
        </tr></thead><tbody>
        ${
          rows
            .map(
              (q) => `<tr>
            <td><code>${q.quote_number}</code>${q.requires_approval && !q.approved_by ? ' <span class="badge warn">approval</span>' : ""}</td>
            <td>${q.party_name || "—"}</td>
            <td>${q.opportunity_name || "—"}</td>
            <td><span class="badge">${q.status}</span></td>
            <td>${q.tax_mode}</td>
            <td class="money">${q.currency} ${money(q.total_amount)}</td>
            <td class="row-actions">
              <button type="button" class="ghost" data-view="${q.id}">View</button>
              <button type="button" class="ghost" data-pdf="${q.id}">PDF</button>
              <button type="button" class="ghost" data-dup="${q.id}">Duplicate</button>
              ${q.status === "pending_approval" ? `<button type="button" class="accent" data-apr="${q.id}">Approve</button>` : ""}
              <button type="button" class="ghost" data-send="${q.id}">Send</button>
              <button type="button" class="ghost" data-acc="${q.id}">Accept</button>
              <button type="button" class="accent" data-inv="${q.id}">Tax invoice</button>
              <button type="button" class="ghost" data-pf="${q.id}">Proforma</button>
              <button type="button" class="warn" data-dec="${q.id}">Decline</button>
            </td>
          </tr>`
            )
            .join("") || `<tr><td colspan="7">No quotes match</td></tr>`
        }
        </tbody></table></div></div>`;
      bindQuoteActions(el);
    } catch (e) {
      el.innerHTML = `<div class="card">${e.message}</div>`;
    }
  }

  function bindQuoteActions(el) {
    el.querySelectorAll("[data-pdf]").forEach((b) =>
      b.addEventListener("click", () => openPdf(`/api/quotes/${b.dataset.pdf}/pdf`))
    );
    el.querySelectorAll("[data-view]").forEach((b) =>
      b.addEventListener("click", () => showQuoteDetail(b.dataset.view))
    );
    const act = async (path, msg) => {
      try {
        await api(path, { method: "POST" });
        setStatus(msg);
        renderQuotes();
        renderHome();
      } catch (e) {
        setStatus(e.message, true);
      }
    };
    el.querySelectorAll("[data-send]").forEach((b) =>
      b.addEventListener("click", () => act(`/api/quotes/${b.dataset.send}/send`, "Marked sent"))
    );
    el.querySelectorAll("[data-acc]").forEach((b) =>
      b.addEventListener("click", () => act(`/api/quotes/${b.dataset.acc}/accept`, "Accepted · Opportunity Closed Won · Invoice created when linked"))
    );
    el.querySelectorAll("[data-dec]").forEach((b) =>
      b.addEventListener("click", () => act(`/api/quotes/${b.dataset.dec}/decline`, "Declined"))
    );
    el.querySelectorAll("[data-apr]").forEach((b) =>
      b.addEventListener("click", () => act(`/api/quotes/${b.dataset.apr}/approve`, "Discount approved"))
    );
    el.querySelectorAll("[data-dup]").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          const q = await api(`/api/quotes/${b.dataset.dup}/duplicate`, { method: "POST" });
          setStatus(`Duplicated as ${q.quote_number}`);
          renderQuotes();
        } catch (e) {
          setStatus(e.message, true);
        }
      })
    );
    el.querySelectorAll("[data-inv]").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          const inv = await api(`/api/invoices/from-quote/${b.dataset.inv}`, { method: "POST" });
          setStatus(`Invoice ${inv.invoice_number}`);
          switchTab("invoices");
        } catch (e) {
          setStatus(e.message, true);
        }
      })
    );
    el.querySelectorAll("[data-pf]").forEach((b) =>
      b.addEventListener("click", async () => {
        try {
          const inv = await api(`/api/invoices/from-quote/${b.dataset.pf}?invoice_type=proforma`, {
            method: "POST",
          });
          setStatus(`Proforma ${inv.invoice_number}`);
          switchTab("invoices");
        } catch (e) {
          setStatus(e.message, true);
        }
      })
    );
  }

  async function showQuoteDetail(id) {
    const q = await api(`/api/quotes/${id}`);
    openDrawer(`
      <h3>${q.quote_number}</h3>
      <p class="muted">${q.party_name || ""} · ${q.status} · ${q.tax_mode}</p>
      <p>${q.opportunity_name || ""} ${q.sales_owner ? "· Owner " + q.sales_owner : ""}</p>
      <table><thead><tr><th>Line</th><th>Qty</th><th>Total</th></tr></thead><tbody>
      ${q.lines
        .map(
          (l) =>
            `<tr><td><strong>${l.sku}</strong><br/>${l.description}</td><td>${l.quantity}</td><td class="money">${money(l.line_total)}</td></tr>`
        )
        .join("")}
      </tbody></table>
      <div class="totals">
        <div><span>Subtotal</span><span>₹ ${money(q.subtotal)}</span></div>
        <div><span>Discount</span><span>₹ ${money(q.discount_amount)}</span></div>
        <div><span>CGST / SGST / IGST</span><span>${money(q.cgst_amount)} / ${money(q.sgst_amount)} / ${money(q.igst_amount)}</span></div>
        <div class="grand"><span>Total</span><span>₹ ${money(q.total_amount)}</span></div>
      </div>
      <pre style="white-space:pre-wrap;font-size:.82rem;background:#f6f8fb;padding:.75rem">${q.terms_text || ""}</pre>
    `);
  }

  async function renderInvoices() {
    const el = $("#tab-invoices");
    el.innerHTML = `<div class="card">Loading…</div>`;
    try {
      const invoices = await api("/api/invoices");
      const rows = invoices.filter(
        (i) =>
          matchFilter(i.invoice_number) ||
          matchFilter(i.party_name) ||
          matchFilter(i.status) ||
          matchFilter(i.invoice_type)
      );
      el.innerHTML = `<div class="card"><div class="table-wrap"><table class="data"><thead><tr>
        <th>Number</th><th>Party</th><th>Type</th><th>Status</th><th>Total</th><th>Paid</th><th>Balance</th><th></th>
      </tr></thead><tbody>
      ${
        rows
          .map((inv) => {
            const bal = Number(inv.balance_due ?? inv.total_amount - (inv.amount_paid || 0));
            return `<tr>
          <td><code>${inv.invoice_number}</code></td>
          <td>${inv.party_name || "—"}</td>
          <td>${inv.invoice_type}</td>
          <td><span class="badge ${inv.status === "paid" ? "ok" : bal > 0 && inv.due_date ? "warn" : ""}">${inv.status}</span></td>
          <td class="money">${inv.currency} ${money(inv.total_amount)}</td>
          <td class="money">${money(inv.amount_paid)}</td>
          <td class="money">${money(bal)}</td>
          <td class="row-actions">
            <button type="button" class="ghost" data-view="${inv.id}">View</button>
            <button type="button" class="ghost" data-pdf="${inv.id}">PDF</button>
            ${
              inv.invoice_type === "tax_invoice" && inv.status !== "credited" && inv.status !== "void"
                ? `<button type="button" class="accent" data-pay="${inv.id}">Record payment</button>
                   <button type="button" class="warn" data-cn="${inv.id}">Credit note</button>
                   <button type="button" class="ghost" data-void="${inv.id}">Void</button>`
                : ""
            }
          </td>
        </tr>`;
          })
          .join("") || `<tr><td colspan="8">No invoices</td></tr>`
      }
      </tbody></table></div></div>`;
      el.querySelectorAll("[data-pdf]").forEach((b) =>
        b.addEventListener("click", () => openPdf(`/api/invoices/${b.dataset.pdf}/pdf`))
      );
      el.querySelectorAll("[data-view]").forEach((b) =>
        b.addEventListener("click", () => showInvoiceDetail(b.dataset.view))
      );
      el.querySelectorAll("[data-pay]").forEach((b) =>
        b.addEventListener("click", () => paymentModal(b.dataset.pay))
      );
      el.querySelectorAll("[data-cn]").forEach((b) =>
        b.addEventListener("click", async () => {
          if (!confirm("Issue credit note?")) return;
          try {
            const cn = await api(`/api/invoices/${b.dataset.cn}/credit-note`, { method: "POST" });
            setStatus(`Credit note ${cn.invoice_number}`);
            renderInvoices();
          } catch (e) {
            setStatus(e.message, true);
          }
        })
      );
      el.querySelectorAll("[data-void]").forEach((b) =>
        b.addEventListener("click", async () => {
          if (!confirm("Void this invoice?")) return;
          try {
            await api(`/api/invoices/${b.dataset.void}/void`, { method: "POST" });
            setStatus("Invoice voided");
            renderInvoices();
          } catch (e) {
            setStatus(e.message, true);
          }
        })
      );
    } catch (e) {
      el.innerHTML = `<div class="card">${e.message}</div>`;
    }
  }

  async function showInvoiceDetail(id) {
    const inv = await api(`/api/invoices/${id}`);
    openDrawer(`
      <h3>${inv.invoice_number}</h3>
      <p class="muted">${inv.party_name || ""} · ${inv.invoice_type} · ${inv.status}</p>
      <p>Due ${inv.due_date || "—"} · Tax ${inv.tax_mode}</p>
      <table><thead><tr><th>Line</th><th>Qty</th><th>Total</th></tr></thead><tbody>
      ${inv.lines
        .map(
          (l) =>
            `<tr><td><strong>${l.sku}</strong><br/>${l.description}</td><td>${l.quantity}</td><td class="money">${money(l.line_total)}</td></tr>`
        )
        .join("")}
      </tbody></table>
      <div class="totals">
        <div class="grand"><span>Total</span><span>₹ ${money(inv.total_amount)}</span></div>
        <div><span>Paid</span><span>₹ ${money(inv.amount_paid)}</span></div>
        <div><span>Balance</span><span>₹ ${money(inv.balance_due)}</span></div>
      </div>
      <h4>Payments</h4>
      ${
        (inv.payments || []).length
          ? `<table><thead><tr><th>Date</th><th>Method</th><th>Ref</th><th>Amount</th></tr></thead><tbody>
        ${inv.payments
          .map(
            (p) =>
              `<tr><td>${p.payment_date}</td><td>${p.method}</td><td>${p.reference || "—"}</td><td class="money">${money(p.amount)}</td></tr>`
          )
          .join("")}</tbody></table>`
          : `<p class="muted">No payments recorded</p>`
      }
    `);
  }

  async function paymentModal(id) {
    const inv = await api(`/api/invoices/${id}`);
    const bal = Number(inv.balance_due ?? inv.total_amount - (inv.amount_paid || 0));
    openDrawer(`
      <h3>Record payment</h3>
      <p class="muted">${inv.invoice_number} · balance ₹ ${money(bal)}</p>
      <form id="payForm">
        <div class="form-row">
          <label>Amount <input name="amount" type="number" step="0.01" value="${bal.toFixed(2)}" required /></label>
          <label>Method
            <select name="method">
              <option value="bank_transfer">Bank transfer</option>
              <option value="upi">UPI</option>
              <option value="cheque">Cheque</option>
              <option value="card">Card</option>
              <option value="cash">Cash</option>
              <option value="other">Other</option>
            </select>
          </label>
        </div>
        <div class="form-row">
          <label>Reference / UTR <input name="reference" placeholder="UTR / cheque no." /></label>
          <label>Date <input name="payment_date" type="date" value="${new Date().toISOString().slice(0, 10)}" /></label>
        </div>
        <div class="form-row"><label>Notes <input name="notes" /></label></div>
        <button type="submit" class="accent">Save payment</button>
      </form>
    `);
    $("#payForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      try {
        await api(`/api/invoices/${id}/mark-paid`, {
          method: "POST",
          body: JSON.stringify({
            amount: Number(fd.get("amount")),
            method: fd.get("method"),
            reference: fd.get("reference") || null,
            notes: fd.get("notes") || null,
            payment_date: fd.get("payment_date") || null,
          }),
        });
        closeDrawer();
        setStatus("Payment recorded");
        renderInvoices();
        renderHome();
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  function renderParties() {
    const el = $("#tab-parties");
    const rows = parties.filter(
      (p) => matchFilter(p.legal_name) || matchFilter(p.gstin) || matchFilter(p.email)
    );
    el.innerHTML = `<div class="grid-2">
      <div class="card">
        <h3>Customer parties</h3>
        <table><thead><tr><th>Name</th><th>State</th><th>GSTIN</th><th>Terms</th></tr></thead>
        <tbody>${
          rows
            .map(
              (p) => `<tr>
            <td><strong>${p.legal_name}</strong><br/><span class="muted">${p.email || ""}</span></td>
            <td>${p.state} (${p.state_code})</td>
            <td>${p.gstin || "—"}</td>
            <td>${p.payment_terms_days}d ${p.is_export ? "· Export" : ""}</td>
          </tr>`
            )
            .join("") || `<tr><td colspan="4">No parties</td></tr>`
        }</tbody></table>
      </div>
      <div class="card">
        <h3>Add party</h3>
        <form id="partyForm">
          <div class="form-row">
            <label>Legal name <input name="legal_name" required /></label>
            <label>Email <input name="email" type="email" /></label>
          </div>
          <div class="form-row">
            <label>State
              <select name="state_code" id="partyState">${stateOptions("27")}</select>
            </label>
            <label>GSTIN <input name="gstin" /></label>
            <label>PAN <input name="pan" /></label>
          </div>
          <div class="form-row">
            <label>Billing address <textarea name="billing_address" rows="3"></textarea></label>
          </div>
          <div class="form-row">
            <label><input name="is_export" type="checkbox" /> Export customer</label>
            <label>Payment terms (days) <input name="payment_terms_days" type="number" value="15" /></label>
          </div>
          <button type="submit" class="accent">Save party</button>
        </form>
      </div>
    </div>`;
    $("#partyForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      const sel = $("#partyState");
      const opt = sel.options[sel.selectedIndex];
      try {
        await api("/api/parties", {
          method: "POST",
          body: JSON.stringify({
            legal_name: fd.get("legal_name"),
            email: fd.get("email") || null,
            state: opt.dataset.name,
            state_code: fd.get("state_code"),
            gstin: fd.get("gstin") || null,
            pan: fd.get("pan") || null,
            billing_address: fd.get("billing_address") || null,
            is_export: !!fd.get("is_export"),
            payment_terms_days: Number(fd.get("payment_terms_days") || 15),
          }),
        });
        parties = await api("/api/parties");
        setStatus("Party saved");
        renderParties();
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  function renderCatalog() {
    const el = $("#tab-catalog");
    const rows = catalog.filter(
      (c) => matchFilter(c.sku) || matchFilter(c.name) || matchFilter(c.product_family)
    );
    el.innerHTML = `<div class="card">
      <h3>Add any product you resell</h3>
      <div class="form-row">
        <label>Supplier <input id="catVendor" placeholder="Brand or distributor" /></label>
        <label>Part number <input id="catSku" placeholder="Unique part no." /></label>
        <label>Name <input id="catName" placeholder="What it is" /></label>
      </div>
      <div class="form-row">
        <label>List price ₹ <input id="catPrice" type="number" min="0" step="0.01" value="0" /></label>
        <label>GST % <input id="catGst" type="number" min="0" step="0.01" value="18" /></label>
        <label>Billing
          <select id="catModel">
            <option value="one_time">One time</option>
            <option value="subscription">Monthly subscription</option>
            <option value="usage">Usage</option>
          </select>
        </label>
        <button type="button" id="catAdd" class="accent">Save to catalog</button>
      </div>
      <p class="muted">Saved parts can be dropped onto the next quote. NikTiar subscriptions stay monthly; a server or licence you type in is usually one time.</p>
      <table><thead><tr><th>Supplier</th><th>Part</th><th>Name</th><th>Family</th><th>Model</th><th>List</th><th>GST%</th><th>Active</th></tr></thead>
      <tbody>
      ${rows
        .map(
          (c) => `<tr>
        <td>${esc(c.vendor_name || "—")}</td>
        <td><code>${esc(c.sku)}</code></td>
        <td><strong>${c.name}</strong><br/><span class="muted" style="font-size:.82rem">${c.description || ""}</span></td>
        <td>${c.product_family}</td>
        <td>${c.billing_model}<br/><span class="muted">${c.unit_label}</span></td>
        <td><input data-price="${c.id}" type="number" step="0.01" value="${c.list_price}" style="width:7rem" /></td>
        <td>${c.gst_rate}</td>
        <td><input data-active="${c.id}" type="checkbox" ${c.active ? "checked" : ""} /></td>
      </tr>`
        )
        .join("")}
      </tbody></table>
      <button type="button" id="saveCatalog" class="accent" style="margin-top:.75rem">Save catalog changes</button>
    </div>`;
    $("#catAdd").addEventListener("click", async () => {
      const sku = $("#catSku").value.trim();
      const name = $("#catName").value.trim();
      if (!sku || !name) return setStatus("Part number and name are required", true);
      try {
        await api("/api/catalog", {
          method: "POST",
          body: JSON.stringify({
            sku,
            name,
            vendor_name: $("#catVendor").value.trim() || null,
            list_price: Number($("#catPrice").value || 0),
            gst_rate: Number($("#catGst").value || 0),
            billing_model: $("#catModel").value,
            product_family: "resale",
          }),
        });
        catalog = await api("/api/catalog?active_only=false");
        setStatus("Product saved");
        renderCatalog();
      } catch (e) {
        setStatus(e.message, true);
      }
    });
    $("#saveCatalog").addEventListener("click", async () => {
      try {
        for (const c of catalog) {
          const priceEl = el.querySelector(`[data-price="${c.id}"]`);
          const actEl = el.querySelector(`[data-active="${c.id}"]`);
          if (!priceEl) continue;
          const list_price = Number(priceEl.value);
          const active = actEl.checked;
          if (list_price !== Number(c.list_price) || active !== c.active) {
            await api(`/api/catalog/${c.id}`, {
              method: "PATCH",
              body: JSON.stringify({ list_price, active }),
            });
          }
        }
        catalog = await api("/api/catalog?active_only=false");
        setStatus("Catalog updated");
        renderCatalog();
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  function renderBuilder() {
    const el = $("#tab-builder");
    const active = catalog.filter((c) => c.active);
    el.innerHTML = `<div class="card">
      <div class="form-row">
        <label>Party
          <select id="bqParty"><option value="">Select…</option>
          ${parties.map((p) => `<option value="${p.id}">${p.legal_name} (${p.state_code})</option>`).join("")}
          </select>
        </label>
        <label>Deal name <input id="bqOpp" placeholder="Shown on the quote" /></label>
        <label>Sales owner <input id="bqOwner" placeholder="Your name" /></label>
        <input id="bqOppId" type="hidden" />
      </div>
      <div class="form-row">
        <label>Term (months) <input id="bqTerm" type="number" value="12" min="1" /></label>
        <label>Doc discount % <input id="bqDisc" type="number" value="0" min="0" max="100" step="0.01" /></label>
        <label>Tax mode
          <select id="bqTax">
            <option value="auto">Auto (place of supply)</option>
            <option value="cgst_sgst">CGST + SGST</option>
            <option value="igst">IGST</option>
            <option value="export_zero">Export zero (LUT)</option>
          </select>
        </label>
      </div>
      <div class="form-row">
        <label>Customer notes <input id="bqNotes" placeholder="Shown on quote PDF" /></label>
        <label>Internal notes <input id="bqInternal" placeholder="Not on PDF" /></label>
      </div>
      <h3>Lines</h3>
      <p class="muted">Use a saved catalog item, or type any supplier and part. Nothing is limited to one brand.</p>
      <div id="bqLines"></div>
      <div class="form-row">
        <label>Catalog item
          <select id="bqSku">${active
            .map((c) => `<option value="${c.sku}">${esc(c.vendor_name || "Catalog")} · ${esc(c.sku)} — ${esc(c.name)} (₹${money(c.list_price)})</option>`)
            .join("")}</select>
        </label>
        <label>Qty <input id="bqQty" type="number" value="1" min="1" /></label>
        <label>Line discount % <input id="bqLineDisc" type="number" value="0" min="0" step="0.01" /></label>
        <button type="button" id="bqAdd" class="ghost">Add catalog line</button>
      </div>
      <div class="form-row">
        <label>Supplier <input id="bqVendor" placeholder="Any brand or distributor" /></label>
        <label>Part number <input id="bqPart" placeholder="Supplier part no." /></label>
        <label>Description <input id="bqDesc" placeholder="What the customer is buying" /></label>
      </div>
      <div class="form-row">
        <label>Unit price ₹ <input id="bqPrice" type="number" min="0" step="0.01" value="0" /></label>
        <label>Qty <input id="bqCustomQty" type="number" min="1" value="1" /></label>
        <label>GST % <input id="bqGst" type="number" min="0" step="0.01" value="18" /></label>
        <label>HSN / SAC <input id="bqHsn" placeholder="Optional" /></label>
        <button type="button" id="bqAddCustom" class="ghost">Add this part</button>
      </div>
      <p class="muted">Catalog subscriptions are priced monthly × term. A typed part is a one-time resale line. Discounts at or above the company threshold need approval before send or invoice.</p>
      <button type="button" id="bqCreate" class="accent">Create quote</button>
    </div>`;
    const linesEl = $("#bqLines");
    const paint = () => {
      linesEl.innerHTML =
        builderLines
          .map(
            (ln, i) => `<div class="line-pick">
          <strong>${esc(ln.vendor_name || "Catalog")}</strong> ${esc(ln.sku)} × ${ln.quantity}
          ${ln.description ? `<div class="muted">${esc(ln.description)}</div>` : ""}
          ${ln.unit_price != null ? `<div class="muted">₹ ${money(ln.unit_price)} each · GST ${ln.gst_rate ?? 18}%</div>` : `<div class="muted">Catalog price · discount ${ln.discount_percent || 0}%</div>`}
          <button type="button" class="ghost" style="float:right" data-rm="${i}">Remove</button>
        </div>`
          )
          .join("") || `<p class="muted">No lines yet.</p>`;
      linesEl.querySelectorAll("[data-rm]").forEach((b) =>
        b.addEventListener("click", () => {
          builderLines.splice(Number(b.dataset.rm), 1);
          paint();
        })
      );
    };
    paint();
    $("#bqAdd").addEventListener("click", () => {
      const sku = $("#bqSku").value;
      const item = catalog.find((c) => c.sku === sku);
      if (!item) return setStatus("Pick a catalog item", true);
      builderLines.push({
        sku,
        vendor_name: item.vendor_name || null,
        quantity: Number($("#bqQty").value || item.min_qty || 1),
        discount_percent: Number($("#bqLineDisc").value || 0),
      });
      paint();
    });
    $("#bqAddCustom").addEventListener("click", () => {
      const description = $("#bqDesc").value.trim();
      const sku = $("#bqPart").value.trim() || "PART";
      if (!description) return setStatus("Describe the part", true);
      builderLines.push({
        sku,
        description,
        vendor_name: $("#bqVendor").value.trim() || null,
        quantity: Number($("#bqCustomQty").value || 1),
        unit_price: Number($("#bqPrice").value || 0),
        gst_rate: Number($("#bqGst").value || 0),
        hsn_sac: $("#bqHsn").value.trim() || null,
        billing_model: "one_time",
        discount_percent: 0,
      });
      paint();
    });
    if (builderPrefill) {
      if (builderPrefill.party_id) $("#bqParty").value = builderPrefill.party_id;
      if (builderPrefill.opportunity_name) $("#bqOpp").value = builderPrefill.opportunity_name;
      if (builderPrefill.sales_owner) $("#bqOwner").value = builderPrefill.sales_owner;
      if (builderPrefill.opportunity_id) $("#bqOppId").value = builderPrefill.opportunity_id;
      builderPrefill = null;
    }
    $("#bqCreate").addEventListener("click", async () => {
      if (!$("#bqParty").value) return setStatus("Select a party", true);
      if (!builderLines.length) return setStatus("Add lines", true);
      try {
        const q = await api("/api/quotes", {
          method: "POST",
          body: JSON.stringify({
            party_id: $("#bqParty").value,
            term_months: Number($("#bqTerm").value || 12),
            discount_percent: Number($("#bqDisc").value || 0),
            tax_mode: $("#bqTax").value,
            notes: $("#bqNotes").value || null,
            internal_notes: $("#bqInternal").value || null,
            opportunity_name: $("#bqOpp").value || null,
            sales_owner: $("#bqOwner").value || null,
            opportunity_id: $("#bqOppId").value || null,
            lines: builderLines,
          }),
        });
        builderLines = [];
        setStatus(
          `Quote ${q.quote_number} · ₹ ${money(q.total_amount)}` +
            (q.status === "pending_approval" ? " · needs discount approval" : "")
        );
        switchTab("quotes");
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  async function renderSettings() {
    const el = $("#tab-settings");
    el.innerHTML = `<div class="card">Loading…</div>`;
    try {
      const c = await api("/api/settings/company");
      el.innerHTML = `<div class="card">
        <h3>Seller company (appears on PDFs)</h3>
        <form id="coForm">
          <div class="form-row">
            <label>Legal name <input name="legal_name" value="${c.legal_name || ""}" required /></label>
            <label>GSTIN <input name="gstin" value="${c.gstin || ""}" /></label>
            <label>PAN <input name="pan" value="${c.pan || ""}" /></label>
          </div>
          <div class="form-row">
            <label>State
              <select name="state_code" id="coState">${stateOptions(c.state_code || "27")}</select>
            </label>
            <label>Email <input name="email" value="${c.email || ""}" /></label>
            <label>Phone <input name="phone" value="${c.phone || ""}" /></label>
          </div>
          <div class="form-row">
            <label>Address <textarea name="address" rows="2">${c.address || ""}</textarea></label>
            <label>Website <input name="website" value="${c.website || ""}" /></label>
          </div>
          <h3>Bank / UPI (on invoices)</h3>
          <div class="form-row">
            <label>Bank <input name="bank_name" value="${c.bank_name || ""}" /></label>
            <label>Account <input name="bank_account" value="${c.bank_account || ""}" /></label>
            <label>IFSC <input name="bank_ifsc" value="${c.bank_ifsc || ""}" /></label>
            <label>Branch <input name="bank_branch" value="${c.bank_branch || ""}" /></label>
            <label>UPI <input name="upi_id" value="${c.upi_id || ""}" /></label>
          </div>
          <div class="form-row">
            <label>Quote validity (days) <input name="quote_validity_days" type="number" value="${c.quote_validity_days}" /></label>
            <label>Discount approval threshold % <input name="discount_approval_threshold" type="number" step="0.01" value="${c.discount_approval_threshold}" /></label>
            <label><input name="lut_filed" type="checkbox" ${c.lut_filed ? "checked" : ""} /> LUT filed (export zero-rate)</label>
          </div>
          <div class="form-row">
            <label>Default terms <textarea name="default_terms" rows="6">${c.default_terms || ""}</textarea></label>
          </div>
          <div class="form-row">
            <label>Invoice footer <textarea name="invoice_footer" rows="2">${c.invoice_footer || ""}</textarea></label>
          </div>
          <button type="submit" class="accent">Save company settings</button>
        </form>
      </div>`;
      $("#coForm").addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const fd = new FormData(ev.target);
        const sel = $("#coState");
        const opt = sel.options[sel.selectedIndex];
        try {
          const body = Object.fromEntries(fd.entries());
          body.state = opt.dataset.name;
          body.lut_filed = !!fd.get("lut_filed");
          body.quote_validity_days = Number(body.quote_validity_days);
          body.discount_approval_threshold = Number(body.discount_approval_threshold);
          await api("/api/settings/company", { method: "PUT", body: JSON.stringify(body) });
          const me = await api("/api/me");
          $("#sideCompany").textContent = me.company_name;
          setStatus("Company settings saved");
        } catch (e) {
          setStatus(e.message, true);
        }
      });
    } catch (e) {
      el.innerHTML = `<div class="card">${e.message}</div>`;
    }
  }



  $("#btnLogin").addEventListener("click", login);
  $("#btnLogout").addEventListener("click", logout);
  $("#btnQuickLead").addEventListener("click", () => openNewLeadModal());
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawer").addEventListener("click", (ev) => {
    if (ev.target.hasAttribute("data-close-drawer") || ev.target.id === "drawer") closeDrawer();
  });
  $("#modalClose").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (ev) => {
    if (ev.target.hasAttribute("data-close-modal") || ev.target.id === "modal") closeModal();
  });
  document.addEventListener("click", (ev) => {
    if (ev.target.closest("[data-close-modal]")) closeModal();
  });
  $("#nav").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-tab]");
    if (btn) switchTab(btn.dataset.tab);
  });
  $("#globalSearch").addEventListener("input", (ev) => {
    filter = ev.target.value.trim();
    const active = document.querySelector("#nav button.active")?.dataset.tab;
    if (active === "quotes") renderQuotes();
    if (active === "leads") renderLeads();
    if (active === "pipeline") renderPipeline();
    if (active === "invoices") renderInvoices();
    if (active === "parties") renderParties();
    if (active === "team") renderTeam();
    if (active === "catalog") renderCatalog();
  });
  $("#pass").addEventListener("keydown", (e) => {
    if (e.key === "Enter") login();
  });

  if (localStorage.getItem("kb_user")) {
    $("#user").value = localStorage.getItem("kb_user") || "";
    $("#pass").value = localStorage.getItem("kb_pass") || "";
    login();
  }
})();
