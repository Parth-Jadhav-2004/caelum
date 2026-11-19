const windowsLabels: Record<string, string> = {
  SUPER: "Win",
  CTRL: "Ctrl",
  ALT: "Alt",
  SHIFT: "Shift",
  SPACE: "Space",
};

export function formatShortcut(value: string): string {
  if (!/Windows/i.test(navigator.userAgent)) return value;
  return value
    .split("+")
    .map((part) => {
      const key = part.trim();
      return windowsLabels[key] ?? key;
    })
    .join(" + ");
}
