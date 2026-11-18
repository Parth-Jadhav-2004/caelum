import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { afterEach, expect, it, vi } from "vitest";

const startup = readFileSync("public/theme-init.js", "utf8");
afterEach(() => localStorage.clear());

it.each(["light", "dark", "system"])(
  "applies saved %s appearance before React mounts",
  (theme) => {
    localStorage.setItem(
      "caelum.appearance",
      JSON.stringify({
        theme,
        colorTheme: "caelum-iris",
        reducedMotion: true,
        highContrast: true,
        sidebarVisible: false,
        setupComplete: true,
      }),
    );
    runInNewContext(startup, {
      document,
      localStorage,
      matchMedia: () => ({ matches: false }),
    });
    const root = document.documentElement;
    expect(root.classList.contains("dark")).toBe(theme === "dark");
    expect(root.style.colorScheme).toBe(theme === "dark" ? "dark" : "light");
    expect(root.style.backgroundColor).toBe(
      theme === "dark" ? "rgb(18, 18, 20)" : "rgb(251, 251, 250)",
    );
    expect(root.dataset.colorTheme).toBe("caelum-iris");
    expect(root.dataset.reducedMotion).toBe("true");
    expect(root.dataset.highContrast).toBe("true");
    expect(root.dataset.sidebarCollapsed).toBe("true");
  },
);

it("still paints the dark startup background when webview storage is unavailable", () => {
  document.documentElement.classList.add("dark");
  runInNewContext(startup, {
    document,
    localStorage: {
      getItem: vi.fn(() => {
        throw new Error("Unavailable");
      }),
    },
  });
  expect(document.documentElement.style.colorScheme).toBe("dark");
  expect(document.documentElement.style.backgroundColor).toBe(
    "rgb(18, 18, 20)",
  );
});
