// wordbadge content script — frozen sample app for the autonomousqa benchmark.
//
// Counts the words inside the page's <main> element (tokens containing at
// least one letter or digit; punctuation-only tokens are not words) and pins
// a badge reading "N words" to the corner of the page. Pages without a
// <main> get no badge.
(function () {
  "use strict";
  if (document.getElementById("wordbadge")) return;
  var main = document.querySelector("main");
  if (!main) return;
  var tokens = (main.innerText || "").split(/\s+/).filter(function (token) {
    return /[A-Za-z0-9]/.test(token);
  });
  var badge = document.createElement("div");
  badge.id = "wordbadge";
  badge.setAttribute("data-testid", "wordbadge");
  badge.textContent = tokens.length + " words";
  badge.style.cssText = [
    "position:fixed",
    "bottom:8px",
    "right:8px",
    "background:#123a4c",
    "color:#fff",
    "padding:4px 8px",
    "border-radius:4px",
    "font:12px system-ui, sans-serif",
    "z-index:2147483647"
  ].join(";");
  document.body.appendChild(badge);
})();
