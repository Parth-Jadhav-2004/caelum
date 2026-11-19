// The generated manifest is the only source of release versions and package names.
const repository = "https://github.com/Parth-Jadhav-2004/caelum";
export function validateRelease(data) {
  if (
    !data ||
    !/^\d+\.\d+\.\d+$/.test(data.version) ||
    !Array.isArray(data.packages) ||
    !data.packages.length
  ) {
    throw new Error("No stable packages are available");
  }
  const base = `${repository}/releases/download/v${data.version}/`;
  if (
    data.releaseUrl !== `${repository}/releases/tag/v${data.version}` ||
    data.checksumsUrl !== `${base}SHA256SUMS`
  ) {
    throw new Error("Unexpected release location");
  }
  const ids = new Set();
  const packages = data.packages.map((item) => {
    if (
      !item ||
      !/^[a-z0-9-]+$/.test(item.id) ||
      ids.has(item.id) ||
      typeof item.name !== "string" ||
      !item.name.trim() ||
      !Number.isSafeInteger(item.size) ||
      item.size <= 0 ||
      !["apt", "dnf", "pacman", "appimage", "exe"].includes(item.manager) ||
      typeof item.file !== "string" ||
      !/^[a-zA-Z0-9_.-]+$/.test(item.file) ||
      !item.file.startsWith(
        `${item.manager === "appimage" ? "Caelum" : "caelum"}${item.manager === "apt" ? "_" : "-"}${data.version}-`,
      )
    ) {
      throw new Error("Invalid package entry");
    }
    const extension = {
      apt: "_amd64.deb",
      dnf: ".x86_64.rpm",
      pacman: "-x86_64.pkg.tar.zst",
      exe: "-windows-x64.exe",
      appimage: "-x86_64.AppImage",
    }[item.manager];
    if (!item.file.endsWith(extension))
      throw new Error("Unexpected package architecture");
    ids.add(item.id);
    return {
      ...item,
      url: base + item.file,
      command:
        item.manager === "exe" ? null :
        item.manager === "appimage" ? `chmod +x ./${item.file} && ./${item.file}` :
        item.manager === "pacman"
          ? `sudo pacman -U ${item.file}`
          : `sudo ${item.manager} install ./${item.file}`,
    };
  });
  return { ...data, packages };
}
