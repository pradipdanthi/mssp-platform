(() => {
  const $ = (s) => document.querySelector(s);
  const money = (v) =>
    Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const titles = {
    home: "Dashboard",
    builder: "New quote",
    quotes: "Quotes",
    invoices: "Invoices",
    parties: "Parties",
    catalog: "Product catalog",
    settings: "Company settings",
  };

  let catalog = [];
  let parties = [];
  let states = [];
  let builderLines = [];
  let filter = "";

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

  function switchTab(name) {
    document.querySelectorAll("#nav button").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll("#main .panel").forEach((p) => p.classList.add("hidden"));
    $(`#tab-${name}`).classList.remove("hidden");
    $("#pageTitle").textContent = titles[name] || name;
    if (name === "home") renderHome();
    if (name === "quotes") renderQuotes();
    if (name === "invoices") renderInvoices();
    if (name === "parties") renderParties();
    if (name === "catalog") renderCatalog();
    if (name === "builder") renderBuilder();
    if (name === "settings") renderSettings();
  }

  function openDrawer(html) {
    $("#drawerBody").innerHTML = html;
    $("#drawer").classList.remove("hidden");
  }
  function closeDrawer() {
    $("#drawer").classList.add("hidden");
  }

  async function login() {
    localStorage.setItem("kb_user", $("#user").value.trim());
    localStorage.setItem("kb_pass", $("#pass").value);
    try {
      const me = await api("/api/me");
      showApp(true);
      $("#sideCompany").textContent = me.company_name;
      $("#userChip").textContent = me.user;
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
    states = await api("/api/settings/states");
  }

  function stateOptions(selectedCode = "27") {
    return states
      .map(
        (s) =>
          `<option value="${s.code}" data-name="${s.name}" ${
            s.code === selectedCode ? "selected" : ""
          }>${s.code} — ${s.name}</option>`
      )
      .join("");
  }

  async function renderHome() {
    const el = $("#tab-home");
    el.innerHTML = `<div class="card"><p>Loading dashboard…</p></div>`;
    try {
      const d = await api("/api/dashboard");
      const k = d.kpis;
      const agingMax = Math.max(...Object.values(d.aging), 1);
      el.innerHTML = `
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Open quotes</div><div class="value">${k.open_quotes}</div><div class="hint muted">Pipeline ₹ ${money(k.open_quotes_value)}</div></div>
          <div class="kpi"><div class="label">Outstanding AR</div><div class="value">₹ ${money(k.outstanding_ar)}</div><div class="hint muted">${k.overdue_count} overdue</div></div>
          <div class="kpi"><div class="label">Invoiced MTD</div><div class="value">₹ ${money(k.invoiced_mtd)}</div><div class="hint muted">Collected ₹ ${money(k.collected_mtd)}</div></div>
          <div class="kpi"><div class="label">Pending approval</div><div class="value">${k.pending_approval}</div><div class="hint muted">${k.parties} parties</div></div>
        </div>
        <div class="grid-2">
          <div class="card">
            <h3>GST this month</h3>
            <table><tbody>
              <tr><td>Taxable</td><td class="money">₹ ${money(d.gst_mtd.taxable)}</td></tr>
              <tr><td>CGST</td><td class="money">₹ ${money(d.gst_mtd.cgst)}</td></tr>
              <tr><td>SGST</td><td class="money">₹ ${money(d.gst_mtd.sgst)}</td></tr>
              <tr><td>IGST</td><td class="money">₹ ${money(d.gst_mtd.igst)}</td></tr>
              <tr><td>Credit-note tax</td><td class="money">₹ ${money(d.gst_mtd.credit_note_tax)}</td></tr>
            </tbody></table>
          </div>
          <div class="card">
            <h3>Receivables aging</h3>
            ${["current", "1_30", "31_60", "61_90", "90_plus"]
              .map((key) => {
                const label = { current: "Not due", "1_30": "1–30 days", "31_60": "31–60", "61_90": "61–90", "90_plus": "90+" }[key];
                const pct = Math.round((d.aging[key] / agingMax) * 100);
                return `<div class="bar-row"><span style="width:5.5rem">${label}</span><div class="bar"><span style="width:${pct}%"></span></div><span class="money">₹ ${money(d.aging[key])}</span></div>`;
              })
              .join("")}
          </div>
        </div>
        <div class="grid-2">
          <div class="card">
            <h3>Overdue invoices</h3>
            ${
              d.overdue.length
                ? `<table><thead><tr><th>Invoice</th><th>Days</th><th>Balance</th></tr></thead><tbody>
              ${d.overdue
                .map(
                  (o) =>
                    `<tr><td><code>${o.invoice_number}</code></td><td>${o.days_overdue}</td><td class="money">₹ ${money(o.balance)}</td></tr>`
                )
                .join("")}</tbody></table>`
                : `<p class="muted">None overdue — good.</p>`
            }
          </div>
          <div class="card">
            <h3>Quotes expiring ≤ 7 days</h3>
            ${
              d.expiring_quotes.length
                ? `<table><thead><tr><th>Quote</th><th>Until</th><th>Total</th></tr></thead><tbody>
              ${d.expiring_quotes
                .map(
                  (q) =>
                    `<tr><td><code>${q.quote_number}</code></td><td>${q.valid_until}</td><td class="money">₹ ${money(q.total_amount)}</td></tr>`
                )
                .join("")}</tbody></table>`
                : `<p class="muted">No quotes expiring this week.</p>`
            }
          </div>
        </div>
        <div class="card">
          <h3>Quick actions</h3>
          <div class="row-actions">
            <button type="button" class="accent" data-go="builder">New quote</button>
            <button type="button" class="ghost" data-go="parties">Add party</button>
            <button type="button" class="ghost" data-go="invoices">Open invoices</button>
            <button type="button" class="ghost" data-go="settings">Company / bank GSTIN</button>
          </div>
        </div>`;
      el.querySelectorAll("[data-go]").forEach((b) =>
        b.addEventListener("click", () => switchTab(b.dataset.go))
      );
    } catch (e) {
      el.innerHTML = `<div class="card"><p>${e.message}</p></div>`;
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
      el.innerHTML = `<div class="card">
        <table><thead><tr>
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
        </tbody></table></div>`;
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
      b.addEventListener("click", () => act(`/api/quotes/${b.dataset.acc}/accept`, "Accepted"))
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
      el.innerHTML = `<div class="card"><table><thead><tr>
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
      </tbody></table></div>`;
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
      <p class="muted">List prices (INR). Subscription SKUs are monthly; quotes multiply by term. Click price to edit.</p>
      <table><thead><tr><th>SKU</th><th>Name</th><th>Family</th><th>Model</th><th>List</th><th>GST%</th><th>Active</th></tr></thead>
      <tbody>
      ${rows
        .map(
          (c) => `<tr>
        <td><code>${c.sku}</code></td>
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
        <label>Opportunity <input id="bqOpp" placeholder="e.g. Acme Gold + SecureEdge" /></label>
        <label>Sales owner <input id="bqOwner" placeholder="Your name" /></label>
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
      <div id="bqLines"></div>
      <div class="form-row">
        <label>SKU
          <select id="bqSku">${active
            .map((c) => `<option value="${c.sku}">${c.sku} — ${c.name} (₹${money(c.list_price)})</option>`)
            .join("")}</select>
        </label>
        <label>Qty <input id="bqQty" type="number" value="25" min="1" /></label>
        <label>Line discount % <input id="bqLineDisc" type="number" value="0" min="0" step="0.01" /></label>
        <button type="button" id="bqAdd" class="ghost">Add line</button>
      </div>
      <p class="muted">Subscriptions are priced monthly × term. Discounts ≥ company threshold need approval before send/invoice.</p>
      <button type="button" id="bqCreate" class="accent">Create quote</button>
    </div>`;
    const linesEl = $("#bqLines");
    const paint = () => {
      linesEl.innerHTML =
        builderLines
          .map(
            (ln, i) => `<div class="line-pick">
          <strong>${ln.sku}</strong> × ${ln.quantity}
          ${ln.discount_percent ? ` · line disc ${ln.discount_percent}%` : ""}
          <button type="button" class="ghost" style="float:right" data-rm="${i}">Remove</button>
        </div>`
          )
          .join("") || `<p class="muted">Add NikTiar SKUs above</p>`;
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
      builderLines.push({
        sku,
        quantity: Number($("#bqQty").value || item?.min_qty || 1),
        discount_percent: Number($("#bqLineDisc").value || 0),
      });
      paint();
    });
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
  $("#drawerClose").addEventListener("click", closeDrawer);
  $("#drawer").addEventListener("click", (ev) => {
    if (ev.target.id === "drawer") closeDrawer();
  });
  $("#nav").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-tab]");
    if (btn) switchTab(btn.dataset.tab);
  });
  $("#globalSearch").addEventListener("input", (ev) => {
    filter = ev.target.value.trim();
    const active = document.querySelector("#nav button.active")?.dataset.tab;
    if (active === "quotes") renderQuotes();
    if (active === "invoices") renderInvoices();
    if (active === "parties") renderParties();
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
