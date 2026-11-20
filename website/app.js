import "./demo.js?v=16";
import { packageChoices, populateDownloads } from "./downloads.js?v=15";
import { validateRelease } from "./release.js";

const distroSelect = document.querySelector("#distro");
const releaseLink = document.querySelector("#release-link");
const installCommand = document.querySelector("#install-command");
const distroInfo = document.querySelector("#distro-info");
const installInstructions = document.querySelector("#install-instructions");
let release;
function applyDistro(value) {
  const distribution = release?.packages.find((item) => item.id === value);
  document.querySelector("#copy-status").textContent = "";
  if (!distribution) {
    releaseLink.href =
      release?.releaseUrl ||
      "https://github.com/Parth-Jadhav-2004/caelum/releases/latest";
    releaseLink.textContent = "View stable releases ↗";
    distroInfo.textContent = "Choose a package to see its download and installation details.";
    installInstructions.hidden = true;
    installCommand.textContent = "";
    return;
  }
  distroInfo.textContent = `${distribution.name} · x86-64 · ${(distribution.size / 1_000_000).toFixed(1)} MB`;
  releaseLink.href = distribution.url;
  releaseLink.textContent = `Download ${release.version} for ${distribution.name} ↓`;
  installCommand.textContent = distribution.command;
  installInstructions.hidden = !distribution.command;
}
async function loadRelease() {
  try {
    const response = await fetch("./release.json", { cache: "no-cache" });
    if (!response.ok) throw new Error("Release manifest unavailable");
    release = validateRelease(await response.json());
    document.querySelectorAll("[data-release-label]").forEach((item) => {
      item.textContent = `Caelum ${release.version} · Stable release`;
    });
    document.querySelector("#checksum-link").href = release.checksumsUrl;
    distroSelect.replaceChildren(
      new Option("Choose a published package", ""),
      ...release.packages.map((item) => new Option(item.name, item.id)),
    );
    distroSelect.disabled = false;
    const matches = packageChoices(release.packages, navigator.userAgentData?.platform || navigator.platform, navigator.userAgent);
    populateDownloads(release, matches);
    const requested = new URLSearchParams(location.search).get("download");
    distroSelect.value = requested ?? (matches.length === 1 ? matches[0].id : "");
    applyDistro(distroSelect.value);

  } catch {
    distroSelect.disabled = true;
    applyDistro("");
    distroInfo.textContent =
      "Package information is unavailable. Open the stable release for downloads and SHA256SUMS.";
  }
}
distroSelect.addEventListener("change", () => applyDistro(distroSelect.value));
document.querySelector("#copy-install").addEventListener("click", async () => {
  const status = document.querySelector("#copy-status");
  try {
    await navigator.clipboard.writeText(installCommand.textContent);
    status.textContent = "Copied";
  } catch {
    status.textContent = "Select the command to copy it manually.";
    installCommand.focus();
  }
});
void loadRelease();
