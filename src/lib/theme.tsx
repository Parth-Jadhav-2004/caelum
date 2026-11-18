import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import { resolveColorTheme } from "./themes";
type Theme = "dark" | "light";
const ThemeContext = createContext<{ theme: Theme }>({ theme: "dark" });
export function ThemeProvider({
  theme,
  colorTheme,
  reducedMotion = false,
  highContrast = false,
  sidebarVisible = true,
  setupComplete = true,
  children,
}: {
  theme: string;
  colorTheme?: string;
  reducedMotion?: boolean;
  highContrast?: boolean;
  sidebarVisible?: boolean;
  setupComplete?: boolean;
  children: ReactNode;
}) {
  const [system, setSystem] = useState<Theme>(() =>
    window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light",
  );
  const resolved =
    theme === "system" ? system : theme === "light" ? "light" : "dark";
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystem(query.matches ? "dark" : "light");
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useLayoutEffect(() => {
    const accent = resolveColorTheme(colorTheme);
    document.documentElement.dataset.colorTheme = accent;
    document.documentElement.classList.toggle("dark", resolved === "dark");
    document.documentElement.style.colorScheme = resolved;
    document.documentElement.style.removeProperty("background-color");
    document.documentElement.dataset.reducedMotion = String(reducedMotion);
    document.documentElement.dataset.highContrast = String(highContrast);
    document.documentElement.dataset.sidebarCollapsed = String(!sidebarVisible);
    document.documentElement.dataset.setupComplete = String(setupComplete);
    try {
      localStorage.setItem(
        "caelum.appearance",
        JSON.stringify({
          theme,
          colorTheme: accent,
          reducedMotion,
          highContrast,
          sidebarVisible,
          setupComplete,
        }),
      );
    } catch {
      // Backend settings remain authoritative when webview storage is unavailable.
    }
  }, [
    theme,
    resolved,
    colorTheme,
    reducedMotion,
    highContrast,
    sidebarVisible,
    setupComplete,
  ]);
  return (
    <ThemeContext.Provider value={{ theme: resolved }}>
      {children}
    </ThemeContext.Provider>
  );
}
export function useTheme() {
  return useContext(ThemeContext);
}
