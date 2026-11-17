/* global localStorage, matchMedia, document */
// Run before the stylesheet and React so the first frame matches saved appearance.
(() => {
  try {
    const saved = JSON.parse(localStorage.getItem("caelum.appearance") || "{}");
    const dark =
      saved.theme === "system"
        ? matchMedia("(prefers-color-scheme: dark)").matches
        : saved.theme !== "light";
    const root = document.documentElement;
    root.classList.toggle("dark", dark);
    root.style.colorScheme = dark ? "dark" : "light";
    root.style.backgroundColor = dark ? "#121214" : "#fbfbfa";
    root.dataset.colorTheme = ["caelum-iris", "caelum-ochre"].includes(
      saved.colorTheme,
    )
      ? saved.colorTheme
      : "caelum";
    root.dataset.reducedMotion = String(saved.reducedMotion === true);
    root.dataset.highContrast = String(saved.highContrast === true);
    root.dataset.sidebarCollapsed = String(saved.sidebarVisible === false);
    if (typeof saved.setupComplete === "boolean")
      root.dataset.setupComplete = String(saved.setupComplete);
  } catch {
    document.documentElement.style.colorScheme = "dark";
    document.documentElement.style.backgroundColor = "#121214";
  }
})();
