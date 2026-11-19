import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { validateRelease } from "./release.js";
const manifest = JSON.parse(
  readFileSync(new URL("./release.json", import.meta.url)),
);

test("every published package has a matching version, architecture, URL and install command", () => {
  const release = validateRelease(manifest);
  assert.equal(release.packages.length, manifest.packages.length);
  for (const item of release.packages) {
    assert.ok(item.url.includes(`/v${release.version}/${item.file}`));
    if (item.manager === "exe") {
      assert.equal(item.command, null);
      continue;
    }
    if (item.manager === "appimage") {
      assert.equal(item.command, `chmod +x ./${item.file} && ./${item.file}`);
      continue;
    }
    assert.ok(item.command.startsWith(`sudo ${item.manager} `));
    assert.ok(item.command.endsWith(item.file));
    assert.ok(item.manager === "pacman" || item.command.includes("install ./"));
  }
  assert.equal(
    release.packages.some((item) => item.id === "debian-13"),
    false,
  );
});

test("missing, prerelease, mismatched, unsafe and ambiguous data fail closed", () => {
  for (const invalid of [
    null,
    {},
    { ...manifest, version: "0.5.0-beta.1" },
    { ...manifest, packages: [] },
    { ...manifest, releaseUrl: "https://example.com" },
    { ...manifest, checksumsUrl: "https://example.com/SHA256SUMS" },
    { ...manifest, packages: [manifest.packages[0], manifest.packages[0]] },
  ]) {
    assert.throws(() => validateRelease(invalid));
  }
  for (const replacement of [
    { file: "caelum_0.3.0-1_ubuntu-24.04_amd64.deb" },
    { file: "caelum_0.4.2-1_ubuntu-24.04_arm64.deb" },
    { file: "../../package.deb" },
    { manager: "sh" },
    { size: 0 },
    { sha256: "invalid" },
    { name: "" },
  ]) {
    assert.throws(() =>
      validateRelease({
        ...manifest,
        packages: [{ ...manifest.packages[0], ...replacement }],
      }),
    );
  }
});

test("published desktop assets use versioned filenames and platform install instructions", () => {
  const desktop = [
    { id: "appimage", manager: "appimage", file: "caelum-0.5.0-x86_64.AppImage" },
    { id: "windows", manager: "exe", file: "caelum-0.5.0-x64-setup.exe" },
  ];
  const base = "https://github.com/Parth-Jadhav-2004/caelum/releases";
  const { packages } = validateRelease({
    version: "0.5.0",
    releaseUrl: base + "/tag/v0.5.0",
    checksumsUrl: base + "/download/v0.5.0/SHA256SUMS",
    packages: desktop.map((item) => ({ ...item, name: item.id, size: 123, sha256: "a".repeat(64) })),
  });
  assert.equal(packages[0].command, `chmod +x ./${desktop[0].file} && ./${desktop[0].file}`);
  assert.equal(packages[1].command, null);
});
