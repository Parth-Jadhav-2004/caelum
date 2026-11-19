// Browser identifiers often omit the Linux distribution or version.
export function packageChoices(packages, platform, userAgent) {
  const system = platform + " " + userAgent;
  if (/Android|CrOS|iPhone|iPad/i.test(system)) return [];
  if (/Windows|Win32/i.test(system)) return packages.filter(p => p.manager === "exe");
  if (!/Linux|Ubuntu|Arch Linux|Debian|Fedora/i.test(system)) return [];
  const linux = packages.filter(p => p.manager !== "exe");
  const ubuntu = system.match(/Ubuntu(?:[ /-]+(\d{2})\.(\d{2}))?/i);
  if (ubuntu) {
    const exact = ubuntu[1] && linux.find(p => p.id === "ubuntu-" + ubuntu[1] + ubuntu[2]);
    if (exact) return [exact];
    return linux.filter(p => p.id.startsWith("ubuntu-"));
  }
  if (/Arch(?:[ -]?Linux)?\b/i.test(system)) return linux.filter(p => p.id === "arch");
  if (/Fedora/i.test(system)) return linux.filter(p => p.id === "fedora");
  if (/Debian/i.test(system)) return linux.filter(p => p.id.startsWith("debian-"));
  return linux.filter(p => p.manager === "appimage");
}

const formats = { exe: ".exe", apt: ".deb", dnf: ".rpm", pacman: ".pkg.tar.zst", appimage: ".AppImage" };

export function menuChoices(packages, matches) {
  const ubuntu = matches.length === 1 && matches[0].id.startsWith("ubuntu-") ? matches[0] :
    packages.filter(p => p.id.startsWith("ubuntu-"))
    .sort((a, b) => b.id.localeCompare(a.id, undefined, { numeric: true }))[0];
  const preferred = new Set(matches.map(p => p.id));
  const ordered = packages.filter(p => !p.id.startsWith("ubuntu-") || p.id === ubuntu?.id)
    .sort((a, b) => Number(preferred.has(b.id)) - Number(preferred.has(a.id)));
  return { ordered, preferred };
}

export function populateDownloads(release, matches) {
  const { ordered, preferred } = menuChoices(release.packages, matches);
  const platformLabel = matches.some(p => p.id.startsWith("ubuntu-")) ? "Ubuntu" : matches[0]?.name;
  for (const menu of document.querySelectorAll(".download-menu")) {
    const trigger = menu.querySelector("summary");
    trigger.querySelector(".download-title").textContent = platformLabel ? "Download for " + platformLabel : "Download Caelum";
    const list = menu.querySelector(".package-options");
    list.replaceChildren();
    ordered.forEach((p, index) => {
      const link = document.createElement("a");
      if (index && preferred.has(ordered[index - 1].id) && !preferred.has(p.id)) link.classList.add("after-preferred");
      link.href = p.url;
      link.textContent = p.name;
      const format = document.createElement("small");
      format.textContent = formats[p.manager];
      link.append(format);
      list.append(link);
    });
    menu.addEventListener("keydown", e => {
      if (e.key === "Escape") { menu.open = false; trigger.focus(); }
    });
    menu.addEventListener("focusout", e => {
      if (e.relatedTarget && !menu.contains(e.relatedTarget)) menu.open = false;
    });
    document.addEventListener("click", e => {
      if (!menu.contains(e.target) || e.target.closest(".package-options a")) menu.open = false;
    });
  }
}
