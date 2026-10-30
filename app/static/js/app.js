/* Progressive enhancement only - every screen works without this file. */
(function () {
  "use strict";

  // Submit filter forms as soon as a select changes (fewer taps on a phone).
  document.querySelectorAll("select[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () {
      el.form && el.form.submit();
    });
  });

  // Long option lists: keep the chosen district after a page reload.
  var params = new URLSearchParams(window.location.search);
  document.querySelectorAll("input[name]").forEach(function (input) {
    var key = input.getAttribute("name");
    if (params.has(key) && input.type === "hidden") input.value = params.get(key);
  });

  // Confirm before a status change that ends an order.
  document.querySelectorAll('select[name="action"]').forEach(function (sel) {
    sel.addEventListener("change", function () {
      if (["cancel", "settle"].indexOf(sel.value) !== -1) {
        sel.setAttribute("data-confirm", "This closes the order for both parties. Record why in the note field.");
      } else {
        sel.removeAttribute("data-confirm");
      }
    });
    sel.form &&
      sel.form.addEventListener("submit", function (e) {
        var msg = sel.getAttribute("data-confirm");
        if (msg && !window.confirm(msg)) e.preventDefault();
      });
  });
})();
