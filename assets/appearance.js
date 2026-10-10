/* Resolve the theme before the stylesheet paints, then wire up the controls. */
(() => {
  const root = document.documentElement;
  const storageKey = "ckzhu-theme";
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = null;
  let toggle;

  const validTheme = (value) => value === "light" || value === "dark";
  try {
    const stored = window.localStorage.getItem(storageKey);
    if (validTheme(stored)) preference = stored;
  } catch {
    // The controls still work when browser storage is unavailable.
  }

  const applyTheme = () => {
    const theme = preference || (systemTheme.matches ? "dark" : "light");
    root.dataset.theme = theme;
    if (toggle) {
      toggle.setAttribute("aria-pressed", String(theme === "dark"));
      toggle.title = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
    }
  };
  applyTheme();
  systemTheme.addEventListener("change", () => {
    if (!preference) applyTheme();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    preference = validTheme(event.newValue) ? event.newValue : null;
    applyTheme();
  });

  const initialize = () => {
    toggle = document.querySelector(".theme-toggle");
    if (toggle) {
      toggle.hidden = false;
      applyTheme();
      toggle.addEventListener("click", () => {
        preference = root.dataset.theme === "dark" ? "light" : "dark";
        applyTheme();
        try {
          window.localStorage.setItem(storageKey, preference);
        } catch {
          // Retain the chosen theme for this page even without storage.
        }
      });
    }

    const glow = document.querySelector(".cursor-glow");
    if (!glow) return;
    const motionAllowed = window.matchMedia("(hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)");
    let frame = null;
    let x = 0;
    let y = 0;
    const hideGlow = () => {
      glow.classList.remove("is-active");
      if (frame !== null) window.cancelAnimationFrame(frame);
      frame = null;
    };
    document.addEventListener("pointermove", (event) => {
      if (!motionAllowed.matches || event.pointerType === "touch") return;
      x = event.clientX;
      y = event.clientY;
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        glow.style.setProperty("--cursor-x", x + "px");
        glow.style.setProperty("--cursor-y", y + "px");
        glow.classList.add("is-active");
        frame = null;
      });
    }, { passive: true });
    root.addEventListener("pointerleave", hideGlow);
    window.addEventListener("blur", hideGlow);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) hideGlow();
    });
    motionAllowed.addEventListener("change", hideGlow);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
