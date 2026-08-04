(function () {
  const site = window.JUNEXIS_SITE || {};
  const portalUrl = site.customerPortalUrl || "https://portal.junexis.com";
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
    let idx = 0;
    let timer = null;

    function activate(i) {
      idx = i;
      tabs.forEach(function (t, n) {
        t.classList.toggle("is-active", n === i);
        t.setAttribute("aria-selected", n === i ? "true" : "false");
      });
      panels.forEach(function (p, n) {
        p.classList.toggle("is-active", n === i);
      });
    }

    function start() {
      stop();
      timer = window.setInterval(function () {
        activate((idx + 1) % tabs.length);
      }, 5600);
    }

    function stop() {
      if (timer) window.clearInterval(timer);
      timer = null;
    }

    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () {
        activate(i);
        start();
      });
    });

    deployRoot.addEventListener("mouseenter", stop);
    deployRoot.addEventListener("mouseleave", start);
    activate(0);
    start();
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
        "Junexis executive demo — " + (String(data.get("company") || data.get("name") || "Website").trim())
      );
      const body = encodeURIComponent(lines.join("\n"));
      const success = document.getElementById("form-success");
      if (success) success.classList.add("is-visible");
      window.location.href = "mailto:sales@junexis.com?subject=" + subject + "&body=" + body;
      form.reset();
    });
  }

  document.querySelectorAll("[data-year]").forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  /* Mega-menu: click/tap + keyboard; hover still works via CSS on desktop */
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
