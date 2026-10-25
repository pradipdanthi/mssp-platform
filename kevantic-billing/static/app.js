(() => {
  const $ = (sel) => document.querySelector(sel);
  const money = (v) =>
    Number(v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  let catalog = [];
  let parties = [];
  let builderLines = [];

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
    setStatus._t = setTimeout(() => el.classList.remove("show"), 4000);
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    const auth = creds();
    if (auth) headers.Authorization = auth;
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401) throw new Error("Unauthorized — check billing credentials");
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = await res.json();
        detail = j.detail || JSON.stringify(j);
      } catch (_) {}
      throw new Error(detail);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res;
  }

  function showApp(on) {
    $("#tabs").hidden = !on;
    $("#main").hidden = !on;
    $("#btnLogout").classList.toggle("hidden", !on);
  }

  async function login() {
    const u = $("#user").value.trim();
    const p = $("#pass").value;
    localStorage.setItem("kb_user", u);
    localStorage.setItem("kb_pass", p);
    try {
      const me = await api("/api/me");
      $("#companyLine").textContent = `${me.company_name} · GSTIN ${me.company_gstin || "—"} · ${me.company_state}`;
      showApp(true);
      await refreshAll();
      setStatus(`Signed in as ${me.user}`);
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

  function switchTab(name) {
    document.querySelectorAll(".tabs button").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll(".panel").forEach((p) => p.classList.add("hidden"));
    $(`#tab-${name}`).classList.remove("hidden");
  }

  async function refreshAll() {
    catalog = await api("/api/catalog");
    parties = await api("/api/parties");
    renderCatalog();
    renderParties();
    renderQuotes();
    renderInvoices();
    renderBuilder();
  }

  function renderCatalog() {
    const el = $("#tab-catalog");
    el.innerHTML = `<h2>Product catalog</h2>
      <p class="sub">NikTiar portfolio list prices (INR). Subscription lines are priced monthly and multiplied by quote term.</p>
      <table><thead><tr>
        <th>SKU</th><th>Name</th><th>Family</th><th>Model</th><th>Unit</th><th>List</th><th>GST%</th><th>Min</th>
      </tr></thead><tbody>
      ${catalog
        .map(
          (c) => `<tr>
          <td><code>${c.sku}</code></td>
          <td><strong>${c.name}</strong><br/><span style="color:var(--muted);font-size:.85rem">${c.description || ""}</span></td>
          <td>${c.product_family}</td>
          <td>${c.billing_model}</td>
          <td>${c.unit_label}</td>
          <td class="money">${money(c.list_price)}</td>
          <td>${c.gst_rate}</td>
          <td>${c.min_qty}</td>
        </tr>`
        )
        .join("")}
      </tbody></table>`;
  }

  function renderParties() {
    const el = $("#tab-parties");
    el.innerHTML = `<h2>Parties (customers)</h2>
      <div class="grid-2">
        <div>
          <table><thead><tr><th>Name</th><th>State</th><th>GSTIN</th><th>Export</th></tr></thead>
          <tbody>
          ${parties
            .map(
              (p) => `<tr>
              <td>${p.legal_name}<br/><span style="color:var(--muted);font-size:.8rem">${p.email || ""}</span></td>
              <td>${p.state} (${p.state_code})</td>
              <td>${p.gstin || "—"}</td>
              <td>${p.is_export ? "Yes" : "No"}</td>
            </tr>`
            )
            .join("") || `<tr><td colspan="4">No parties yet</td></tr>`}
          </tbody></table>
        </div>
        <form id="partyForm">
          <h3>Add party</h3>
          <div class="form-row">
            <label>Legal name <input name="legal_name" required /></label>
            <label>Email <input name="email" type="email" /></label>
          </div>
          <div class="form-row">
            <label>State <input name="state" value="Maharashtra" /></label>
            <label>State code <input name="state_code" value="27" style="min-width:4rem" /></label>
            <label>GSTIN <input name="gstin" /></label>
          </div>
          <div class="form-row">
            <label style="flex:1">Billing address <textarea name="billing_address" rows="3" style="min-width:100%"></textarea></label>
          </div>
          <div class="form-row">
            <label><input name="is_export" type="checkbox" /> Export customer</label>
            <label>Payment terms (days) <input name="payment_terms_days" type="number" value="15" style="min-width:5rem" /></label>
          </div>
          <button type="submit" class="accent">Save party</button>
        </form>
      </div>`;
    $("#partyForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      const body = {
        legal_name: fd.get("legal_name"),
        email: fd.get("email") || null,
        state: fd.get("state"),
        state_code: fd.get("state_code"),
        gstin: fd.get("gstin") || null,
        billing_address: fd.get("billing_address") || null,
        is_export: !!fd.get("is_export"),
        payment_terms_days: Number(fd.get("payment_terms_days") || 15),
      };
      try {
        await api("/api/parties", { method: "POST", body: JSON.stringify(body) });
        setStatus("Party created");
        await refreshAll();
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  async function renderQuotes() {
    const el = $("#tab-quotes");
    el.innerHTML = `<h2>Quotes</h2><p>Loading…</p>`;
    try {
      const quotes = await api("/api/quotes");
      el.innerHTML = `<h2>Quotes</h2>
        <table><thead><tr>
          <th>Number</th><th>Status</th><th>Tax</th><th>Term</th><th>Total</th><th></th>
        </tr></thead><tbody>
        ${quotes
          .map(
            (q) => `<tr>
            <td><code>${q.quote_number}</code></td>
            <td><span class="badge">${q.status}</span></td>
            <td>${q.tax_mode}</td>
            <td>${q.term_months} mo</td>
            <td class="money">${q.currency} ${money(q.total_amount)}</td>
            <td class="row-actions">
              <button data-pdf="${q.id}" type="button" class="ghost">PDF</button>
              <button data-send="${q.id}" type="button" class="ghost">Mark sent</button>
              <button data-accept="${q.id}" type="button" class="ghost">Accept</button>
              <button data-inv="${q.id}" type="button" class="accent">Create invoice</button>
            </td>
          </tr>`
          )
          .join("") || `<tr><td colspan="6">No quotes yet — use New Quote</td></tr>`}
        </tbody></table>`;
      el.querySelectorAll("[data-pdf]").forEach((b) =>
        b.addEventListener("click", () => openAuthed(`/api/quotes/${b.dataset.pdf}/pdf`))
      );
      el.querySelectorAll("[data-send]").forEach((b) =>
        b.addEventListener("click", async () => {
          await api(`/api/quotes/${b.dataset.send}/send`, { method: "POST" });
          setStatus("Quote marked sent");
          renderQuotes();
        })
      );
      el.querySelectorAll("[data-accept]").forEach((b) =>
        b.addEventListener("click", async () => {
          await api(`/api/quotes/${b.dataset.accept}/accept`, { method: "POST" });
          setStatus("Quote accepted");
          renderQuotes();
        })
      );
      el.querySelectorAll("[data-inv]").forEach((b) =>
        b.addEventListener("click", async () => {
          try {
            const inv = await api(`/api/invoices/from-quote/${b.dataset.inv}`, { method: "POST" });
            setStatus(`Invoice ${inv.invoice_number} created`);
            switchTab("invoices");
            renderQuotes();
            renderInvoices();
          } catch (e) {
            setStatus(e.message, true);
          }
        })
      );
    } catch (e) {
      el.innerHTML = `<p>${e.message}</p>`;
    }
  }

  async function renderInvoices() {
    const el = $("#tab-invoices");
    el.innerHTML = `<h2>Invoices</h2><p>Loading…</p>`;
    try {
      const invoices = await api("/api/invoices");
      el.innerHTML = `<h2>Tax invoices & credit notes</h2>
        <table><thead><tr>
          <th>Number</th><th>Type</th><th>Status</th><th>Tax</th><th>Total</th><th>Paid</th><th></th>
        </tr></thead><tbody>
        ${invoices
          .map(
            (inv) => `<tr>
            <td><code>${inv.invoice_number}</code></td>
            <td>${inv.invoice_type}</td>
            <td><span class="badge">${inv.status}</span></td>
            <td>${inv.tax_mode}</td>
            <td class="money">${inv.currency} ${money(inv.total_amount)}</td>
            <td class="money">${money(inv.amount_paid)}</td>
            <td class="row-actions">
              <button data-pdf="${inv.id}" type="button" class="ghost">PDF</button>
              ${
                inv.invoice_type === "tax_invoice" && inv.status !== "credited"
                  ? `<button data-pay="${inv.id}" type="button" class="accent">Mark paid</button>
                     <button data-cn="${inv.id}" type="button" class="warn">Credit note</button>`
                  : ""
              }
            </td>
          </tr>`
          )
          .join("") || `<tr><td colspan="7">No invoices yet</td></tr>`}
        </tbody></table>`;
      el.querySelectorAll("[data-pdf]").forEach((b) =>
        b.addEventListener("click", () => openAuthed(`/api/invoices/${b.dataset.pdf}/pdf`))
      );
      el.querySelectorAll("[data-pay]").forEach((b) =>
        b.addEventListener("click", async () => {
          await api(`/api/invoices/${b.dataset.pay}/mark-paid`, {
            method: "POST",
            body: JSON.stringify({}),
          });
          setStatus("Marked paid");
          renderInvoices();
        })
      );
      el.querySelectorAll("[data-cn]").forEach((b) =>
        b.addEventListener("click", async () => {
          if (!confirm("Issue a credit note against this invoice?")) return;
          const cn = await api(`/api/invoices/${b.dataset.cn}/credit-note`, { method: "POST" });
          setStatus(`Credit note ${cn.invoice_number}`);
          renderInvoices();
        })
      );
    } catch (e) {
      el.innerHTML = `<p>${e.message}</p>`;
    }
  }

  function openAuthed(url) {
    const u = localStorage.getItem("kb_user");
    const p = localStorage.getItem("kb_pass");
    // Browser PDF: open with fetch blob
    fetch(url, { headers: { Authorization: "Basic " + btoa(`${u}:${p}`) } })
      .then((r) => {
        if (!r.ok) throw new Error("PDF failed");
        return r.blob();
      })
      .then((blob) => {
        const obj = URL.createObjectURL(blob);
        window.open(obj, "_blank");
      })
      .catch((e) => setStatus(e.message, true));
  }

  function renderBuilder() {
    const el = $("#tab-builder");
    if (!builderLines.length && catalog.length) {
      // default empty
    }
    el.innerHTML = `<h2>New quote</h2>
      <div class="form-row">
        <label>Party
          <select id="bqParty">
            <option value="">Select…</option>
            ${parties.map((p) => `<option value="${p.id}">${p.legal_name}</option>`).join("")}
          </select>
        </label>
        <label>Term (months) <input id="bqTerm" type="number" value="12" min="1" style="min-width:5rem" /></label>
        <label>Doc discount % <input id="bqDisc" type="number" value="0" min="0" max="100" step="0.01" style="min-width:5rem" /></label>
        <label>Tax mode
          <select id="bqTax">
            <option value="auto">Auto (GST place of supply)</option>
            <option value="cgst_sgst">Force CGST+SGST</option>
            <option value="igst">Force IGST</option>
            <option value="export_zero">Export zero-rated (LUT)</option>
          </select>
        </label>
      </div>
      <div class="form-row">
        <label style="flex:1">Notes <input id="bqNotes" style="min-width:100%" placeholder="Optional commercial notes" /></label>
      </div>
      <h3>Lines</h3>
      <div id="bqLines"></div>
      <div class="form-row">
        <label>Add SKU
          <select id="bqSku">
            ${catalog.map((c) => `<option value="${c.sku}">${c.sku} — ${c.name} (${money(c.list_price)})</option>`).join("")}
          </select>
        </label>
        <label>Qty <input id="bqQty" type="number" value="25" min="1" style="min-width:5rem" /></label>
        <button type="button" id="bqAdd" class="ghost">Add line</button>
      </div>
      <button type="button" id="bqCreate" class="accent">Create quote</button>`;

    const linesEl = $("#bqLines");
    function paintLines() {
      linesEl.innerHTML =
        builderLines
          .map(
            (ln, i) => `<div class="line-pick">
            <strong>${ln.sku}</strong> × ${ln.quantity}
            <button type="button" data-rm="${i}" class="ghost" style="float:right">Remove</button>
          </div>`
          )
          .join("") || `<p style="color:var(--muted)">No lines yet</p>`;
      linesEl.querySelectorAll("[data-rm]").forEach((b) =>
        b.addEventListener("click", () => {
          builderLines.splice(Number(b.dataset.rm), 1);
          paintLines();
        })
      );
    }
    paintLines();

    $("#bqAdd").addEventListener("click", () => {
      const sku = $("#bqSku").value;
      const item = catalog.find((c) => c.sku === sku);
      const qty = Number($("#bqQty").value || item?.min_qty || 1);
      builderLines.push({ sku, quantity: qty });
      paintLines();
    });

    $("#bqCreate").addEventListener("click", async () => {
      const party_id = $("#bqParty").value;
      if (!party_id) return setStatus("Select a party", true);
      if (!builderLines.length) return setStatus("Add at least one line", true);
      const body = {
        party_id,
        term_months: Number($("#bqTerm").value || 12),
        discount_percent: Number($("#bqDisc").value || 0),
        tax_mode: $("#bqTax").value,
        notes: $("#bqNotes").value || null,
        lines: builderLines,
      };
      try {
        const q = await api("/api/quotes", { method: "POST", body: JSON.stringify(body) });
        builderLines = [];
        setStatus(`Quote ${q.quote_number} · total ${q.currency} ${money(q.total_amount)}`);
        switchTab("quotes");
        renderQuotes();
        renderBuilder();
      } catch (e) {
        setStatus(e.message, true);
      }
    });
  }

  $("#btnLogin").addEventListener("click", login);
  $("#btnLogout").addEventListener("click", logout);
  $("#tabs").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-tab]");
    if (!btn) return;
    switchTab(btn.dataset.tab);
  });

  // restore session
  if (localStorage.getItem("kb_user")) {
    $("#user").value = localStorage.getItem("kb_user") || "";
    $("#pass").value = localStorage.getItem("kb_pass") || "";
    login();
  }
})();
