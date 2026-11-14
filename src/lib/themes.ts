/** Built-in T3 palettes are pinned in t3-themes.generated.css; see THIRD_PARTY_NOTICES.md. */
export const COLOR_THEMES = [
  { id: "t3-code", label: "T3 Code" },
  { id: "t3-chat", label: "T3 Chat" },
  { id: "grove", label: "Grove" },
  { id: "ocean", label: "Ocean" },
  { id: "ember", label: "Ember" },
  { id: "iris", label: "Iris" },
  { id: "caelum", label: "Caelum mint" },
] as const;
export type ColorTheme = (typeof COLOR_THEMES)[number]["id"];
export const DEFAULT_COLOR_THEME: ColorTheme = "t3-code";
export function resolveColorTheme(value: string | undefined): ColorTheme {
  return (
    COLOR_THEMES.find((theme) => theme.id === value)?.id ?? DEFAULT_COLOR_THEME
  );
}
