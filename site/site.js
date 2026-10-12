/* Hardware_OSDR_review page behaviour: light/dark toggle (same key as the CoSE kit),
   the hardware explorer and the model-viewer tabs. No CoSE navigation rail. */
(function () {
  "use strict";
  var LS_THEME = "barker.theme";
  var SUN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';

  /* ---------- theme ---------- */
  var btn = document.querySelector(".cose-theme-btn");
  function current() {
    return document.documentElement.getAttribute("data-theme") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }
  function paint() { if (btn) btn.innerHTML = current() === "dark" ? SUN : MOON; }
  if (btn) {
    btn.addEventListener("click", function () {
      var t = current() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", t);
      try { localStorage.setItem(LS_THEME, t); } catch (e) {}
      paint();
    });
    paint();
  }

  /* ---------- model viewer tabs ---------- */
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".mtabs [role=tab]"));
  function select(tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      var p = document.getElementById(t.getAttribute("aria-controls"));
      if (p) {
        p.hidden = !on;
        if (!on) p.querySelectorAll("video").forEach(function (v) { v.pause(); });
      }
    });
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { select(t); });
    t.addEventListener("keydown", function (e) {
      var j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
      if (j === null) return;
      e.preventDefault();
      var n = tabs[(j + tabs.length) % tabs.length];
      select(n); n.focus();
    });
  });

  /* ---------- hardware explorer ---------- */
  var table = document.getElementById("xtable");
  if (!table) return;
  var body = table.querySelector("tbody");
  var q = document.getElementById("xq"), org = document.getElementById("xorg"),
      tier = document.getElementById("xtier"), used = document.getElementById("xused"),
      cur = document.getElementById("xcur"), count = document.getElementById("xcount");
  var rows = [], sortKey = "c", sortDir = -1;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function chips(a) {
    return a.length ? a.map(function (x) { return '<span class="chip">' + esc(x) + "</span>"; }).join("")
                    : '<span class="dim">not evidenced</span>';
  }
  function badge(t, miss) {
    if (!t) return '<span class="dim">–</span>';
    return '<span class="tier tier-' + esc(t) + '">' + esc(t) + "</span>" +
      (miss ? "<small>missing " + esc(miss) + "</small>" : "");
  }
  function render() {
    var term = q.value.trim().toLowerCase(), o = org.value, t = tier.value;
    var shown = rows.filter(function (r) {
      if (o && r.org.indexOf(o) < 0) return false;
      if (t && r.t !== t) return false;
      if (used.checked && !r.st) return false;
      if (cur.checked && !r.ct) return false;
      return !term || r._text.indexOf(term) >= 0;
    });
    shown.sort(function (a, b) {
      var x = a[sortKey], y = b[sortKey];
      if (x === null || x === undefined) x = sortDir > 0 ? "~" : "";
      if (y === null || y === undefined) y = sortDir > 0 ? "~" : "";
      if (typeof x === "string") return sortDir * x.localeCompare(y) || a.n.localeCompare(b.n);
      return sortDir * (x - y) || a.n.localeCompare(b.n);
    });
    body.innerHTML = shown.map(function (r) {
      return "<tr><td>" + esc(r.n) + (r.yr ? "<small>first flown " + r.yr + "</small>" : "") + "</td>" +
        "<td>" + chips(r.org) + "</td><td>" + chips(r.loc) + "</td><td>" + chips(r.nut) + "</td>" +
        '<td class="num">' + r.st + "</td>" +
        '<td class="num">' + r.c.toFixed(2) + '<span class="bar" aria-hidden="true"><i style="width:' +
        Math.round(r.c * 100) + '%"></i></span></td>' +
        "<td>" + badge(r.t, r.b) + "</td><td>" + badge(r.ct, r.cm) + "</td></tr>";
    }).join("");
    count.textContent = "Showing " + shown.length + " of " + rows.length + " specimen-housing items.";
  }
  table.querySelectorAll("th button").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.getAttribute("data-k");
      sortDir = k === sortKey ? -sortDir : (k === "n" || k === "t" || k === "ct" ? 1 : -1);
      sortKey = k;
      table.querySelectorAll("th button").forEach(function (o) { o.removeAttribute("aria-sort"); });
      b.setAttribute("aria-sort", sortDir > 0 ? "ascending" : "descending");
      render();
    });
  });
  [q, org, tier, used, cur].forEach(function (el) { el.addEventListener("input", render); });

  fetch("assets/data/habitats.json").then(function (r) { return r.json(); }).then(function (data) {
    rows = data.map(function (r) {
      r._text = [r.n, r.id, r.status].concat(r.org, r.loc, r.nut).join(" ").toLowerCase();
      return r;
    });
    var orgs = {};
    rows.forEach(function (r) { r.org.forEach(function (x) { orgs[x] = 1; }); });
    Object.keys(orgs).sort().forEach(function (x) {
      var op = document.createElement("option"); op.value = x; op.textContent = x; org.appendChild(op);
    });
    render();
  }).catch(function () {
    count.textContent = "Could not load the explorer data (assets/data/habitats.json).";
  });
})();
