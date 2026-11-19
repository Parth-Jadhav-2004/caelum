import { validateRelease } from "./release.js";

const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector("#navigation");
function closeMenu(returnFocus = false) {
  navigation.classList.remove("open");
  menuButton.setAttribute("aria-expanded", "false");
  menuButton.setAttribute("aria-label", "Open navigation");
  if (returnFocus) menuButton.focus();
}
menuButton.addEventListener("click", () => {
  const open = menuButton.getAttribute("aria-expanded") !== "true";
  menuButton.setAttribute("aria-expanded", String(open));
  menuButton.setAttribute(
    "aria-label",
    open ? "Close navigation" : "Open navigation",
  );
  navigation.classList.toggle("open", open);
});
navigation
  .querySelectorAll("a")
  .forEach((link) => link.addEventListener("click", () => closeMenu()));
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    menuButton.getAttribute("aria-expanded") === "true"
  )
    closeMenu(true);
});
document.addEventListener("click", (event) => {
  if (!navigation.contains(event.target) && !menuButton.contains(event.target))
    closeMenu();
});
window
  .matchMedia("(min-width: 601px)")
  .addEventListener("change", () => closeMenu());

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

const tourContent = document.querySelector("#tour-content");
const tourPanel = document.querySelector("#tour-panel");
const tourTabs = [...document.querySelectorAll("[data-tab]")];
const panels = {
  home: '<h3>Home</h3><p class="app-subtitle">Record, finish, then copy your transcript.</p><div class="today-totals"><span><strong>248</strong> Words today</span><span><strong>142</strong> Words/min</span><span><strong>3</strong> Day streak</span></div><div class="recent-heading"><h4>Recent dictations</h4><span>Today</span></div><div class="history-item"><p>Let’s make something that feels natural to use.</p><span>10:42 · 9 words</span></div><div class="history-item"><p>I’ll send the updated notes over this afternoon.</p><span>09:18 · 8 words</span></div>',
  history:
    '<h3>History</h3><p class="app-subtitle">Search, revisit, and copy your saved dictations.</p><div class="sample-search">Search dictations</div><div class="history-item"><p>Let’s make something that feels natural to use.</p><span>Today, 10:42 · 9 words</span></div><div class="history-item"><p>A reminder to slow down and follow the interesting idea.</p><span>Today, 09:18 · 10 words</span></div><div class="history-item"><p>I’ll send the updated notes over this afternoon.</p><span>Yesterday, 16:35 · 8 words</span></div><p class="sample-muted">History on · Keep for 30 days</p>',
  dictionary:
    '<h3>Dictionary</h3><p class="app-subtitle">Your spoken terms, written the way you want.</p><div class="dictionary-row"><span>When you say</span><span>Replace with</span></div><div class="dictionary-row"><span>kay lum</span><strong>Caelum</strong></div><div class="dictionary-row"><span>hyper land</span><strong>Hyprland</strong></div><p class="sample-muted">Sample spoken-term replacements.</p>',
  insights:
    '<h3>Insights</h3><p class="app-subtitle">Your dictation activity at a glance.</p><div class="insight-totals"><div><strong>1,284</strong><span>Words this week</span></div><div><strong>12 min</strong><span>Recording time</span></div></div><div class="sample-chart" role="img" aria-label="Sample word totals Monday through Sunday: 115, 179, 230, 141, 294, 192, 133"><span style="--size:39%"></span><span style="--size:61%"></span><span style="--size:78%"></span><span style="--size:48%"></span><span style="--size:100%"></span><span style="--size:65%"></span><span style="--size:45%"></span></div><div class="chart-days" aria-hidden="true"><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span><span>S</span></div>',
  settings:
    '<h3>Settings</h3><p class="app-subtitle">Appearance</p><div class="settings-row"><span>Theme</span><span class="settings-value">Dark · Light · System</span></div><div class="settings-row"><span>Accent</span><span class="settings-value">Mint · Iris · Ochre</span></div><div class="settings-row"><span>Transcription</span><span class="settings-value">Groq · whisper-large-v3-turbo</span></div><div class="settings-row"><span>Text cleanup</span><span class="settings-value">Optional · openai/gpt-oss-20b</span></div><div class="settings-row"><span>System</span><span class="settings-value">Check for signed updates</span></div>',
};
let tourAnimation;
function selectTab(tab, focus = false) {
  if (tourContent.dataset.activeTab === tab.dataset.tab) {
    if (focus) tab.focus();
    return;
  }
  tourTabs.forEach((item) => {
    const selected = item === tab;
    item.setAttribute("aria-selected", String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  tourPanel.setAttribute("aria-labelledby", tab.id);
  const changing = Boolean(tourContent.dataset.activeTab);
  tourContent.dataset.activeTab = tab.dataset.tab;
  tourContent.innerHTML = panels[tab.dataset.tab];
  tourAnimation?.cancel();
  if (changing && !reducedMotion.matches) {
    tourAnimation = tourContent.animate([{ opacity: 0.4 }, { opacity: 1 }], {
      duration: 160,
    });
  }
  document
    .querySelectorAll("[data-side]")
    .forEach((item) =>
      item.classList.toggle("selected", item.dataset.side === tab.dataset.tab),
    );
  if (focus) tab.focus();
}
tourTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (["ArrowRight", "ArrowDown"].includes(event.key))
      next = (index + 1) % tourTabs.length;
    if (["ArrowLeft", "ArrowUp"].includes(event.key))
      next = (index + tourTabs.length - 1) % tourTabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tourTabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      selectTab(tourTabs[next], true);
    }
  });
});
selectTab(tourTabs[0]);

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
    distroInfo.textContent =
      "No verified package for this distribution. See the release for available packages.";
    installInstructions.hidden = true;
    installCommand.textContent = "";
    return;
  }
  distroInfo.textContent = `${distribution.name} · x86-64 · ${(distribution.size / 1_000_000).toFixed(1)} MB`;
  releaseLink.href = distribution.url;
  releaseLink.textContent = `Download for ${distribution.name} ↓`;
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
    document.querySelectorAll("[data-release-link]").forEach((item) => {
      item.href = release.releaseUrl;
    });
    document.querySelector("#checksum-link").href = release.checksumsUrl;
    distroSelect.replaceChildren(
      ...release.packages.map((item) => new Option(item.name, item.id)),
    );
    distroSelect.disabled = false;
    const requested = new URLSearchParams(location.search).get("download");
    if (requested) distroSelect.value = requested;
    applyDistro(distroSelect.value);
    for (const link of document.querySelectorAll("[data-platform-download]")) {
      const platform = release.packages.find((p) => p.id === link.dataset.platformDownload);
      if (platform) {
        link.href = platform.url;
        link.hidden = false;
      }
    }
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
// A compatibility anchor opens its disclosure before the browser scrolls to it.
document.querySelectorAll('a[href="#compatibility"]').forEach((link) =>
  link.addEventListener("click", () => {
    document.querySelector("#compatibility").open = true;
  }),
);
if (location.hash === "#compatibility")
  document.querySelector("#compatibility").open = true;
