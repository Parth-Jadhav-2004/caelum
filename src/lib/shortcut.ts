import type { Status } from "./ipc";

export function portalShortcutStatus(status: Status | null): string | undefined {
  if (!status?.running || status.backend !== "portable" || !status.shortcut_description) return;
  if (status.shortcut_mode === "portal")
    return `Active shortcut: ${status.shortcut_description}`;
  if (status.shortcut_mode === "manual")
    return `No active portal shortcut. ${status.shortcut_description}`;
  if (status.shortcut_mode === "pending") return status.shortcut_description;
}

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
