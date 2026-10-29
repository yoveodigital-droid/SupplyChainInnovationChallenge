(function () {
  // Mobile navigation
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "Close" : "Menu";
    });
  }

  // Copy buttons: navigator.clipboard where allowed, otherwise select the text
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var target = document.getElementById(btn.getAttribute("data-copy"));
      if (!target) return;
      var text = target.textContent.trim();
      var done = function () {
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = "Copy"; }, 1600);
      };
      var fallback = function () {
        var range = document.createRange();
        range.selectNodeContents(target);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        btn.textContent = "Selected";
        setTimeout(function () { btn.textContent = "Copy"; }, 1600);
      };
      try {
        navigator.clipboard.writeText(text).then(done, fallback);
      } catch (e) {
        fallback();
      }
    });
  });

  // Office hours clocks: Nueva Ecija (PHT) and Brussels (CET/CEST)
  var clocks = document.querySelectorAll("[data-tz]");
  function tick() {
    var now = new Date();
    clocks.forEach(function (el) {
      try {
        el.textContent = new Intl.DateTimeFormat("en-GB", {
          timeZone: el.getAttribute("data-tz"),
          weekday: "short", hour: "2-digit", minute: "2-digit"
        }).format(now);
      } catch (e) { /* keep static text */ }
    });
  }
  if (clocks.length) { tick(); setInterval(tick, 30000); }

  // Enquiry form (mockup: nothing is sent)
  var form = document.querySelector("form.enquiry");
  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var note = form.querySelector(".form-note");
      if (!form.checkValidity()) { form.reportValidity(); return; }
      note.hidden = false;
      note.textContent = "Mockup only: this form is not connected yet, so nothing was sent. On the live site your request would go to the Business Development team, who reply with next steps for a site survey.";
      note.focus();
    });
  }
})();

// Coverage checker (indicative; core towns from the company profile)
(function () {
  var form = document.getElementById("coverage");
  if (!form) return;
  var CORE = ["Carranglan", "Llanera", "Pantabangan", "Rizal", "San Jose City", "Science City of Mu\u00f1oz"];
  var select = document.getElementById("cov-town");
  var out = document.getElementById("cov-result");
  function show() {
    var town = select.value;
    if (!town) return;
    var core = CORE.indexOf(town) !== -1;
    out.className = "result " + (core ? "yes" : "ask");
    out.innerHTML = core
      ? "<b>" + town + ": HER Net core area</b><span>Business internet and on-site support are available here. Request a site survey to confirm your exact address.</span><a href=\"quote.html\">Book a site survey &rarr;</a>"
      : "<b>" + town + ": project basis</b><span>This town is outside our core network today. Fiber builds, enterprise IT, CCTV and solar projects are scoped site by site.</span><a href=\"quote.html\">Ask about your site &rarr;</a>";
  }
  form.addEventListener("submit", function (ev) { ev.preventDefault(); show(); });
  select.addEventListener("change", show);
  show();
})();

// Program-area tabs (HER Net page)
(function () {
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"]'));
  if (!tabs.length) return;
  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
    if (focus) tab.focus();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () { select(t); });
    t.addEventListener("keydown", function (e) {
      var n = null;
      if (e.key === "ArrowRight") n = tabs[(i + 1) % tabs.length];
      if (e.key === "ArrowLeft") n = tabs[(i - 1 + tabs.length) % tabs.length];
      if (e.key === "Home") n = tabs[0];
      if (e.key === "End") n = tabs[tabs.length - 1];
      if (n) { e.preventDefault(); select(n, true); }
    });
  });
})();

// Event filters
(function () {
  var btns = document.querySelectorAll(".ev-filter");
  if (!btns.length) return;
  btns.forEach(function (b) {
    b.addEventListener("click", function () {
      var f = b.getAttribute("data-filter");
      btns.forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      document.querySelectorAll(".ev[data-kind]").forEach(function (ev) {
        ev.hidden = !(f === "all" || ev.getAttribute("data-kind") === f);
      });
    });
  });
})();

// District LGU map
(function () {
  var nodes = document.querySelectorAll(".lgu[data-lgu]");
  if (!nodes.length) return;
  var TOTAL = 493038;
  var D = {
    sanjose: ["San Jose City", "Component city", 38, 150917, "185.99", 811, "Commercial and transshipment hub; gateway to Cagayan Valley.", true],
    munoz: ["Science City of Mu\u00f1oz", "Component city", 37, 84308, "163.05", 517, "National agri R&D hub: CLSU, PhilRice and PhilMech; seed multiplication.", true],
    rizal: ["Rizal", "Municipality", 26, 70196, "120.55", 582, "Lowland and foothill onion and vegetable farming; upland barangays in the GIDA corridor.", true],
    lupao: ["Lupao", "Municipality", 24, 45917, "121.33", 378, "Northern border town; rice and corn.", false],
    carranglan: ["Carranglan", "Municipality", 17, 42420, "705.31", 60, "Upland pass and primary GIDA cluster; corn, onion and vegetables.", true],
    llanera: ["Llanera", "Municipality", 22, 42281, "114.44", 369, "Central irrigated rice plains.", true],
    pantabangan: ["Pantabangan", "Municipality", 14, 31763, "392.56", 81, "Hydro reservoir and watershed; power, irrigation and inland fisheries.", true],
    talugtug: ["Talugtug", "Municipality", 28, 25236, "93.95", 269, "Western rainfed rice and livestock.", false]
  };
  function fmt(n) { return n.toLocaleString("en-US"); }
  function show(key) {
    var d = D[key]; if (!d) return;
    nodes.forEach(function (n) { n.classList.toggle("active", n.getAttribute("data-lgu") === key); });
    document.getElementById("lgu-name").textContent = d[0];
    document.getElementById("lgu-type").textContent = d[1];
    document.getElementById("lgu-brgy").textContent = d[2];
    document.getElementById("lgu-pop").textContent = fmt(d[3]);
    document.getElementById("lgu-area").textContent = d[4];
    document.getElementById("lgu-dens").textContent = d[5];
    document.getElementById("lgu-profile").textContent = d[6];
    var st = document.getElementById("lgu-status");
    st.textContent = d[7] ? "HER Net LGU" : "Not yet served";
    st.className = d[7] ? "tag" : "tag amber";
    document.getElementById("lgu-share").textContent = (d[3] / TOTAL * 100).toFixed(1) + "% of the district\u2019s population.";
  }
  nodes.forEach(function (n) {
    var key = n.getAttribute("data-lgu");
    if (D[key] && !D[key][7]) n.classList.add("out");
    n.addEventListener("click", function () { show(key); });
    n.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); show(key); } });
  });
  show("sanjose");
})();
