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
      note.textContent = "Mockup only: this form is not connected yet, so nothing was sent. On the live site your enquiry would go to the Business Development team.";
      note.focus();
    });
  }
})();
