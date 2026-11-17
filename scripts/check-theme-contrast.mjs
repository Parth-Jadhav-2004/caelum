#!/usr/bin/env node
// Audit actual shadcn text token pairs, independently of jsdom's absent layout.
import fs from "node:fs";
import process from "node:process";
import console from "node:console";
import assert from "node:assert/strict";
import { parse, wcagContrast } from "culori";
const main = fs.readFileSync("src/index.css", "utf8");

function tokens(body) {
  return Object.fromEntries(
    [...body.matchAll(/--([a-z-]+):\s*([^;]+);/g)].map((m) => [
      m[1],
      m[2].trim(),
    ]),
  );
}
const light = tokens(main.match(/:where\(:root\)\s*\{([^}]+)\}/)[1]);
const dark = tokens(main.match(/:where\(\.dark\)\s*\{([^}]+)\}/)[1]);
const palettes = new Map([
  ["caelum/light", light],
  ["caelum/dark", { ...light, ...dark }],
]);
for (const match of main.matchAll(
  /:root(\.dark)?\[data-color-theme="([\w-]+)"\]\s*\{([^}]+)\}/g,
)) {
  palettes.set(`${match[2]}/${match[1] ? "dark" : "light"}`, {
    ...light,
    ...(match[1] ? dark : {}),
    ...tokens(match[3]),
  });
}
const highLight = tokens(
  main.match(
    /:root:not\(\.dark\)\[data-high-contrast="true"\]\s*\{([^}]+)\}/,
  )[1],
);
const highDark = tokens(
  main.match(/:root\.dark\[data-high-contrast="true"\]\s*\{([^}]+)\}/)[1],
);
for (const [name, palette] of [...palettes]) {
  palettes.set(name + "/high-contrast", {
    ...palette,
    ...(name.endsWith("dark") ? highDark : highLight),
  });
}
function value(palette, name) {
  const raw = palette[name];
  return raw.startsWith("var(") ? value(palette, raw.slice(6, -1)) : raw;
}
const pairs = [
  ["foreground", "background"],
  ["muted-foreground", "popover"],
  ["muted-foreground", "sidebar"],
  ["accent-brand", "sidebar"],
  ["accent-brand", "background"],
  ["accent-brand", "sidebar-status"],
  ["foreground", "sidebar-status"],
  ["destructive", "background"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["muted-foreground", "background"],
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["accent-foreground", "accent"],
  ["sidebar-foreground", "sidebar"],
  ["sidebar-accent-foreground", "sidebar-accent"],
];
const controlPairs = [
  ["input", "background"],
  ["ring", "background"],
  ["foreground", "card"],
];
const audit = [];
for (const [name, palette] of palettes) {
  for (const [fg, bg] of [...pairs, ...controlPairs]) {
    const ratio = wcagContrast(
      parse(value(palette, fg)),
      parse(value(palette, bg)),
    );
    const minimum = controlPairs.some(([a, b]) => a === fg && b === bg)
      ? 3
      : 4.5;
    assert(ratio >= minimum, `${name}: ${fg}/${bg}: ${ratio.toFixed(2)}`);
    audit.push({
      theme: name,
      foreground: fg,
      background: bg,
      ratio: Number(ratio.toFixed(2)),
    });
  }
}
if (process.argv.includes("--json"))
  console.log(JSON.stringify(audit, null, 2));
else
  console.log(
    `Verified ${audit.length} text pairs across ${palettes.size} palette/appearance/contrast variants (text ≥4.5:1, controls ≥3:1).`,
  );
