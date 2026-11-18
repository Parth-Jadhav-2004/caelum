export const ACCENTS = [
  { id: "caelum", label: "Mint" },
  { id: "caelum-iris", label: "Iris" },
  { id: "caelum-ochre", label: "Ochre" },
] as const;
export function resolveColorTheme(value?: string) {
  return ACCENTS.find((accent) => accent.id === value)?.id ?? "caelum";
}
