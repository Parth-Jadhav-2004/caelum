export function unsupportedPlatform(platform, userAgent) {
  const system = platform + " " + userAgent;
  // Mobile identifiers can also contain "Linux" or "like Mac OS X".
  if (/Android/i.test(system)) return "Android";
  if (/CrOS|Chrome OS/i.test(system)) return "ChromeOS";
  if (/iPad/i.test(system)) return "iPadOS";
  if (/iPhone|iPod|\biOS\b/i.test(system)) return "iOS";
  if (/MacIntel|MacPPC|Macintosh|Mac OS|macOS/i.test(system)) return "macOS";
  return null;
}

// Browser identifiers often omit the Linux distribution or version.
export function packageChoices(packages, platform, userAgent) {
  const system = platform + " " + userAgent;
  if (unsupportedPlatform(platform, userAgent)) return [];
  if (/Windows|Win32/i.test(system)) return packages.filter(p => p.manager === "exe");
  if (!/Linux|Ubuntu|Arch Linux|Debian|Fedora/i.test(system)) return [];
  const linux = packages.filter(p => p.manager !== "exe");
  const ubuntu = system.match(/Ubuntu(?:[ /-]+(\d{2})\.(\d{2}))?/i);
  if (ubuntu) {
    const exact = ubuntu[1] && linux.find(p => p.id === "ubuntu-" + ubuntu[1] + ubuntu[2]);
    if (exact) return [exact];
    return linux.filter(p => p.manager === "appimage");
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

export function populateDownloads(release, matches, unsupported) {
  const { ordered, preferred } = menuChoices(release.packages, matches);
  const platformLabel = matches.some(p => p.id.startsWith("ubuntu-")) ? "Ubuntu" : matches[0]?.name;
  for (const menu of document.querySelectorAll(".download-menu")) {
    const trigger = menu.querySelector("summary");
    trigger.querySelector(".download-title").textContent = platformLabel ? "Download for " + platformLabel :
      unsupported ? `No ${unsupported} build` : "Choose a package manually";
    const list = menu.querySelector(".package-options");
    list.replaceChildren();
    if (!matches.length) {
      const link = document.createElement("a");
      link.href = "#distro";
      link.textContent = "Browse all published packages";
      list.append(link);
    } else {
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
    }
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
