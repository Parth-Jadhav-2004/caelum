import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { resolveColorTheme } from "./themes";
type Theme = "dark" | "light";
const ThemeContext = createContext<{ theme: Theme }>({ theme: "dark" });
export function ThemeProvider({
  theme,
  colorTheme,
  children,
}: {
  theme: string;
  colorTheme?: string;
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
  useEffect(() => {
    document.documentElement.dataset.colorTheme = resolveColorTheme(colorTheme);
    document.documentElement.classList.toggle("dark", resolved === "dark");
    document.documentElement.style.colorScheme = resolved;
  }, [resolved, colorTheme]);
  return (
    <ThemeContext.Provider value={{ theme: resolved }}>
      {children}
    </ThemeContext.Provider>
  );
}
export function useTheme() {
  return useContext(ThemeContext);
}
