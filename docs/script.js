const softToggle = document.getElementById("soft-toggle");
const trackedNodes = document.querySelectorAll("[data-track]");

if (softToggle) {
  softToggle.addEventListener("click", () => {
    const enabled = document.body.classList.toggle("soft-mode");
    softToggle.textContent = enabled
      ? "Restore default mode"
      : document.documentElement.lang === "zh-CN"
        ? "切换柔和模式"
        : "Toggle softer mode";

    if (typeof window.gtag === "function") {
      window.gtag("event", "toggle_soft_mode", {
        event_category: "engagement",
        event_label: document.documentElement.lang,
        value: enabled ? 1 : 0
      });
    }
  });
}

trackedNodes.forEach((node) => {
  node.addEventListener("click", () => {
    const name = node.getAttribute("data-track");
    if (typeof window.gtag === "function" && name) {
      window.gtag("event", name, {
        event_category: "cta",
        event_label: document.documentElement.lang
      });
    }
  });
});
