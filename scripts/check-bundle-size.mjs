#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import assert from "node:assert/strict";
import console from "node:console";
const root = "dist/frontend";
const manifest = JSON.parse(
  fs.readFileSync(path.join(root, ".vite/manifest.json"), "utf8"),
);
const entry = Object.values(manifest).find((item) => item.isEntry);
assert(entry, "No frontend entry in build manifest");
const sizes = new Map(
  fs
    .readdirSync(path.join(root, "assets"))
    .filter((file) => file.endsWith(".js"))
    .map((file) => {
      const raw = fs.readFileSync(path.join(root, "assets", file));
      return [
        "assets/" + file,
        { bytes: raw.length, gzip: zlib.gzipSync(raw).length },
      ];
    }),
);
const initial = new Set();
function visit(chunk) {
  if (initial.has(chunk.file)) return;
  initial.add(chunk.file);
  for (const name of chunk.imports ?? []) visit(manifest[name]);
}
visit(entry);
const largest = Math.max(...[...sizes.values()].map((item) => item.bytes));
const initialGzip = [...initial].reduce(
  (total, file) => total + (sizes.get(file)?.gzip ?? 0),
  0,
);
assert(largest <= 350 * 1024, `Largest JS chunk exceeds 350KiB: ${largest}`);
assert(
  sizes.get(entry.file).bytes <= 120 * 1024,
  "Application entry exceeds 120KiB",
);
assert(
  initialGzip <= 230 * 1024,
  `Initial static dependency graph exceeds 230KiB gzip: ${initialGzip}`,
);
console.log(
  JSON.stringify({
    entry_bytes: sizes.get(entry.file).bytes,
    largest_chunk_bytes: largest,
    initial_static_gzip_bytes: initialGzip,
    total_js_bytes: [...sizes.values()].reduce((n, item) => n + item.bytes, 0),
    chunks: sizes.size,
  }),
);
