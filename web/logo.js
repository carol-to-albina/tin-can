// The TinCan mark: two Groks with a tin can each, joined by a string. Drawn after the team's sketch.
// Heads use the text colour and eyes the background, so it reads in light and dark themes.
"use strict";
window.tincanLogo = function tincanLogo({ cls = "", dots = false } = {}) {
  const head = (cx) => `<circle class="tc-face" cx="${cx}" cy="40" r="28"/>
    <rect class="tc-eye" x="${cx - 17}" y="22" width="5.5" height="11" rx="2.75" transform="rotate(28 ${cx - 14.25} 27.5)"/>
    <rect class="tc-eye" x="${cx - 6}" y="20" width="5.5" height="11" rx="2.75" transform="rotate(28 ${cx - 3.25} 25.5)"/>`;
  const can = (x, lip, side) => `<g class="tc-can tc-can-${side}"><rect x="${x}" y="30" width="24" height="20" rx="2"/>
    <path d="M${x + 6} 31v18M${x + 11} 31v18M${x + 16} 31v18"/><ellipse cx="${lip}" cy="40" rx="2.4" ry="10"/></g>`;
  const string = "M86 40 Q120 52 154 40";
  const moving = dots
    ? `<circle class="tc-dot tc-go" r="3.8"><animateMotion dur="1.1s" repeatCount="indefinite" path="${string}"/></circle>
       <circle class="tc-dot tc-back" r="3.8"><animateMotion dur="1.1s" repeatCount="indefinite" keyPoints="1;0" keyTimes="0;1" calcMode="linear" path="${string}"/></circle>`
    : "";
  return `<svg class="tc-logo ${cls}" viewBox="0 0 240 80" role="img" aria-label="TinCan: two Groks joined by a tin-can string">
    <defs><linearGradient id="tcCan" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#f7f7f8"/><stop offset=".55" stop-color="#b8bbc1"/><stop offset="1" stop-color="#e4e5e8"/></linearGradient></defs>
    <path class="tc-string" d="${string}"/>${head(34)}${can(60, 84, "l")}${can(156, 156, "r")}${head(206)}${moving}</svg>`;
};
document.querySelectorAll("[data-logo]").forEach((el) => (el.innerHTML = window.tincanLogo({ cls: el.dataset.logo })));
