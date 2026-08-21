(function () {
  const site = window.KEVANTIC_SITE || window.JUNEXIS_SITE || {};
  const portalUrl = site.customerPortalUrl || "/portal.html";
  const header = document.querySelector(".site-header");
  const nav = document.querySelector(".nav");
  const toggle = document.querySelector(".nav-toggle");

  document.querySelectorAll("[data-customer-portal]").forEach(function (el) {
    el.setAttribute("href", portalUrl);
  });

  function onScroll() {
    if (!header) return;
    header.classList.toggle("is-scrolled", window.scrollY > 8);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", nav.classList.contains("is-open") ? "true" : "false");
    });
  }

  const path = (location.pathname.split("/").pop() || "index.html").toLowerCase();
  document.querySelectorAll(".nav-links a").forEach(function (a) {
    const href = (a.getAttribute("href") || "").toLowerCase();
    if (href === path || (path === "" && href.indexOf("index") === 0 && href.indexOf("#") === -1)) {
      a.classList.add("is-active");
    }
  });

  const reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -36px 0px" }
    );
    reveals.forEach(function (el) {
      io.observe(el);
    });
  } else {
    reveals.forEach(function (el) {
      el.classList.add("is-in");
    });
  }

  const deployRoot = document.querySelector("[data-deploy]");
  if (deployRoot) {
    const tabs = Array.prototype.slice.call(deployRoot.querySelectorAll(".deploy-tab"));
    const panels = Array.prototype.slice.call(deployRoot.querySelectorAll(".deploy-panel"));
    const envPills = Array.prototype.slice.call(document.querySelectorAll(".env-pill"));
    let env = deployRoot.getAttribute("data-env") || "cloud";

    function applyEnv(next) {
      env = next;
      deployRoot.setAttribute("data-env", env);
      envPills.forEach(function (pill) {
        const on = pill.getAttribute("data-env") === env;
        pill.classList.toggle("is-active", on);
        pill.setAttribute("aria-selected", on ? "true" : "false");
      });
      deployRoot.querySelectorAll("[data-cloud]").forEach(function (el) {
        const text = el.getAttribute("data-" + env);
        if (text) el.textContent = text;
      });
    }

    function activateArch(arch) {
      tabs.forEach(function (tab) {
        const on = tab.getAttribute("data-arch") === arch;
        tab.classList.toggle("is-active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach(function (panel) {
        panel.classList.toggle("is-active", panel.getAttribute("data-arch") === arch);
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateArch(tab.getAttribute("data-arch"));
      });
    });
    envPills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        applyEnv(pill.getAttribute("data-env"));
      });
    });
    applyEnv(env);
    activateArch("direct");
  }

  const form = document.getElementById("demo-form");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const data = new FormData(form);
      const lines = [
        "Name: " + String(data.get("name") || "").trim(),
        "Work email: " + String(data.get("email") || "").trim(),
        "Company: " + String(data.get("company") || "").trim(),
        "Endpoints/servers: " + String(data.get("scale") || "").trim(),
        "Interest: " + String(data.get("interest") || "").trim(),
        "",
        String(data.get("notes") || "").trim(),
      ];
      const subject = encodeURIComponent(
        "Kevantic executive demo — " + (String(data.get("company") || data.get("name") || "Website").trim())
      );
      const body = encodeURIComponent(lines.join("\n"));
      const success = document.getElementById("form-success");
      if (success) success.classList.add("is-visible");
      window.location.href = "mailto:sales@kevantic.com?subject=" + subject + "&body=" + body;
      form.reset();
    });
  }

  document.querySelectorAll("[data-year]").forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  /* Service tier matrix highlight (cards + mobile column switcher) */
  (function () {
    const cards = Array.prototype.slice.call(document.querySelectorAll("[data-tier-cards] .tier-card"));
    const switches = Array.prototype.slice.call(document.querySelectorAll(".tier-switch"));
    const cells = Array.prototype.slice.call(document.querySelectorAll("[data-tier-matrix] [data-col]"));
    if (!cards.length && !switches.length) return;

    function activate(tier) {
      cards.forEach(function (card) {
        card.classList.toggle("is-active", card.getAttribute("data-tier") === tier);
      });
      switches.forEach(function (btn) {
        const on = btn.getAttribute("data-tier") === tier;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
      cells.forEach(function (cell) {
        const on = cell.getAttribute("data-col") === tier;
        cell.classList.toggle("is-active", on);
        cell.classList.toggle("is-show", on);
      });
    }

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        activate(card.getAttribute("data-tier"));
      });
    });
    switches.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activate(btn.getAttribute("data-tier"));
      });
    });
    activate("gold");
  })();

  /* Architecture stack tabs — bind to the shell, not the first data-stack tab button */
  (function () {
    const root = document.querySelector("[data-stack-root]") || document.querySelector(".stack-shell");
    const tablist = document.querySelector(".stack-tabs[role='tablist'], .stack-tabs");
    if (!root || !tablist) return;

    const tabs = Array.prototype.slice.call(tablist.querySelectorAll(".stack-tab"));
    const nodes = Array.prototype.slice.call(root.querySelectorAll(".stack-node"));
    const panels = Array.prototype.slice.call(root.querySelectorAll(".stack-panel"));
    if (!tabs.length || !panels.length) return;

    function activate(id, opts) {
      if (!id) return;
      opts = opts || {};
      tabs.forEach(function (tab) {
        const on = tab.getAttribute("data-stack") === id;
        tab.classList.toggle("is-active", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.tabIndex = on ? 0 : -1;
      });
      nodes.forEach(function (node) {
        node.classList.toggle("is-active", node.getAttribute("data-stack") === id);
      });
      panels.forEach(function (panel) {
        const on = panel.getAttribute("data-stack") === id;
        panel.classList.toggle("is-active", on);
        panel.setAttribute("aria-hidden", on ? "false" : "true");
      });
      if (opts.focus) {
        const current = tabs.filter(function (tab) {
          return tab.getAttribute("data-stack") === id;
        })[0];
        if (current) current.focus();
      }
    }

    tablist.addEventListener("click", function (event) {
      const tab = event.target.closest(".stack-tab");
      if (!tab || !tablist.contains(tab)) return;
      activate(tab.getAttribute("data-stack"));
    });

    tablist.addEventListener("keydown", function (event) {
      const delta = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      const current = tabs.indexOf(document.activeElement);
      if (current < 0) return;
      let next = current;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else if (event.key in delta) next = (current + delta[event.key] + tabs.length) % tabs.length;
      else return;
      event.preventDefault();
      activate(tabs[next].getAttribute("data-stack"), { focus: true });
    });

    nodes.forEach(function (node) {
      node.addEventListener("click", function () {
        activate(node.getAttribute("data-stack"));
      });
    });

    const initialTab = tabs.filter(function (tab) {
      return tab.classList.contains("is-active");
    })[0] || tabs[0];
    activate(initialTab.getAttribute("data-stack"));
  })();

  /* Deep-link demo interest from CTAs */
  document.querySelectorAll("[data-demo-interest]").forEach(function (el) {
    el.addEventListener("click", function () {
      const value = el.getAttribute("data-demo-interest");
      const select = document.getElementById("interest");
      if (!select || !value) return;
      for (let i = 0; i < select.options.length; i += 1) {
        if (select.options[i].value === value || select.options[i].text === value) {
          select.value = select.options[i].value;
          break;
        }
      }
    });
  });

  /* Mega-menu: click/tap + keyboard only (no hover-open) */
  document.querySelectorAll(".has-mega").forEach(function (item) {
    const trigger = item.querySelector(".mega-trigger");
    if (!trigger) return;

    trigger.addEventListener("click", function (e) {
      e.preventDefault();
      const open = item.classList.toggle("is-open");
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      document.querySelectorAll(".has-mega").forEach(function (other) {
        if (other !== item) {
          other.classList.remove("is-open");
          const t = other.querySelector(".mega-trigger");
          if (t) t.setAttribute("aria-expanded", "false");
        }
      });
    });
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest(".has-mega")) return;
    document.querySelectorAll(".has-mega.is-open").forEach(function (item) {
      item.classList.remove("is-open");
      const t = item.querySelector(".mega-trigger");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".has-mega.is-open").forEach(function (item) {
      item.classList.remove("is-open");
      const t = item.querySelector(".mega-trigger");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  });
})();
