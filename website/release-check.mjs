import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { validateRelease } from "./release.js";
import { menuChoices, packageChoices, unsupportedPlatform } from "./downloads.js";
const manifest = JSON.parse(
  readFileSync(new URL("./release.json", import.meta.url)),
);

for (const [platform, agent, expected] of [
  ["Linux x86_64", "Ubuntu", "appimage"],
  ["Linux x86_64", "Ubuntu/22.04", "appimage"],
  ["Linux x86_64", "Ubuntu/24.04", "ubuntu-2404"],
  ["Linux x86_64", "Ubuntu/26.04", "ubuntu-2604"],
  ["Linux x86_64", "Linux", "appimage"],
  ["Linux x86_64", "Debian", "debian-12"],
  ["Linux x86_64", "Fedora", "fedora"],
  ["Linux x86_64", "Arch Linux", "arch"],
  ["Win32", "Windows NT 10.0", "windows"],
  ["MacIntel", "Macintosh", null],
  ["Linux armv8l", "Linux; Android", null],
]) {
  test(`package selection and compact menu for ${agent}`, () => {
    const packages = manifest.packages;
    const matches = packageChoices(packages, platform, agent);
    const expectedIds = expected ? [expected] : [];
    assert.deepEqual(matches.map(p => p.id), expectedIds);

    const { ordered, preferred } = menuChoices(packages, matches);
    assert.deepEqual([...preferred], expectedIds);
    const compactUbuntu = expected === "ubuntu-2404" ? "ubuntu-2404" : "ubuntu-2604";
    const otherIds = packages.map(p => p.id).filter(id =>
      id !== expected && (!id.startsWith("ubuntu-") || id === compactUbuntu));
    assert.deepEqual(ordered.map(p => p.id), [...expectedIds, ...otherIds]);
  });
}

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

test("known unsupported platforms are named without recommending an installer", () => {
  for (const [platform, agent, expected] of [
    ["macOS", "", "macOS"],
    ["MacIntel", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "macOS"],
    ["Linux armv8l", "Mozilla/5.0 (Linux; Android 15)", "Android"],
    ["iPhone", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)", "iOS"],
    ["iPad", "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)", "iPadOS"],
    ["Linux x86_64", "Mozilla/5.0 (X11; CrOS x86_64)", "ChromeOS"],
    ["FreeBSD", "", null],
    ["", "", null],
  ]) {
    assert.equal(unsupportedPlatform(platform, agent), expected);
    assert.deepEqual(packageChoices(manifest.packages, platform, agent), []);
  }
});
