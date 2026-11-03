const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
function closeMenu(returnFocus = false) {
  navigation.classList.remove('open');
  menuButton.setAttribute('aria-expanded', 'false');
  menuButton.setAttribute('aria-label', 'Open navigation');
  if (returnFocus) menuButton.focus();
}
menuButton.addEventListener('click', () => {
  const open = menuButton.getAttribute('aria-expanded') !== 'true';
  menuButton.setAttribute('aria-expanded', String(open));
  menuButton.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  navigation.classList.toggle('open', open);
});
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => closeMenu()));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') closeMenu(true);
});
document.addEventListener('click', event => {
  if (!navigation.contains(event.target) && !menuButton.contains(event.target)) closeMenu();
});
window.matchMedia('(min-width: 601px)').addEventListener('change', () => closeMenu());

const heights = [8,14,22,13,28,36,20,31,42,26,17,34,23,39,28,16,25,12,21,8,16,11];
document.querySelectorAll('.waveform').forEach(wave => {
  heights.forEach((height, index) => {
    const bar = document.createElement('i');
    bar.style.setProperty('--h', `${height * (wave.classList.contains('large') ? 1 : .45)}px`);
    bar.style.setProperty('--delay', `${index * -.09}s`);
    wave.append(bar);
  });
});
const pill = document.querySelector('#recording-pill');
const pillStatus = document.querySelector('#pill-status');
const demoText = document.querySelector('#demo-text');
const replay = document.querySelector('#replay-demo');
const heroDemo = document.querySelector('#hero-demo');
const resultText = 'Let’s make something that feels natural to use.';
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
// One clock drives the loop, so pause/resume keeps its place and never stacks timers.
const demoStage = document.querySelector('#demo');
const cycleDuration = 9000;
let elapsed = 0;
let lastFrame = null;
let frame = null;
let inView = false;
let paused = reducedMotion.matches;
let cycles = 0;
function renderDemo(time) {
  const listening = time < 2400;
  const processing = time >= 2400 && time < 3300;
  const typing = time >= 3300 && time < 4600;
  const phase = listening ? 'listening' : processing ? 'processing' : typing ? 'typing' : 'done';
  demoStage.dataset.phase = phase;
  demoStage.dataset.cycle = String(cycles);
  pill.classList.toggle('playing', listening);
  pillStatus.textContent = listening ? 'Listening…' : processing ? 'Finding your words…' : typing ? 'Putting it into words…' : 'Done. Back to your flow.';
  const text = time < 3300 ? '' : resultText.slice(0, typing ? Math.floor((time - 3300) / 1300 * resultText.length) : resultText.length);
  if (demoText.firstChild?.textContent !== text) {
    demoText.replaceChildren(document.createTextNode(text));
    const caret = document.createElement('span');
    caret.className = 'caret';
    caret.setAttribute('aria-hidden', 'true');
    demoText.append(caret);
  }
}
function updateControl() {
  replay.innerHTML = paused ? '<span aria-hidden="true">▶</span> Resume demo' : '<span aria-hidden="true">Ⅱ</span> Pause demo';
  replay.setAttribute('aria-label', paused ? 'Resume dictation demo' : 'Pause dictation demo');
  demoStage.classList.toggle('demo-paused', paused || !inView || document.hidden);
}
function tick(timestamp) {
  if (lastFrame !== null) elapsed += Math.min(timestamp - lastFrame, 100);
  lastFrame = timestamp;
  if (elapsed >= cycleDuration) { elapsed %= cycleDuration; cycles++; }
  renderDemo(elapsed);
  frame = requestAnimationFrame(tick);
}
function syncPlayback() {
  if (frame !== null) cancelAnimationFrame(frame);
  frame = null;
  lastFrame = null;
  updateControl();
  if (!paused && inView && !document.hidden) frame = requestAnimationFrame(tick);
}
replay.addEventListener('click', () => {
  paused = !paused;
  syncPlayback();
});
heroDemo.addEventListener('click', () => {
  demoStage.scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'center' });
  paused = false;
  elapsed = 0;
  syncPlayback();
});
new IntersectionObserver(entries => {
  inView = entries[0].isIntersecting;
  syncPlayback();
}, { threshold: .15 }).observe(demoStage);
document.addEventListener('visibilitychange', syncPlayback);
reducedMotion.addEventListener('change', () => {
  paused = reducedMotion.matches;
  if (paused) { elapsed = 6000; renderDemo(elapsed); }
  syncPlayback();
});
// Autoplay updates remain silent to assistive technology.
if (reducedMotion.matches) { elapsed = 6000; renderDemo(elapsed); }
updateControl();

const tourContent = document.querySelector('#tour-content');
const tourPanel = document.querySelector('#tour-panel');
const tourTabs = [...document.querySelectorAll('[data-tab]')];
const panels = {
  history: '<h3>History</h3><p class="app-subtitle">Your words, right where you left them.</p><div class="sample-search">⌕ &nbsp; Search dictations</div><div class="history-item"><p>Let’s make something that feels natural to use.</p><span>Today, 10:42 &nbsp; · &nbsp; 9 words</span></div><div class="history-item"><p>A reminder to slow down and follow the interesting idea.</p><span>Today, 09:18 &nbsp; · &nbsp; 10 words</span></div><div class="history-item"><p>I’ll send the updated notes over this afternoon.</p><span>Yesterday, 16:35 &nbsp; · &nbsp; 8 words</span></div>',
  statistics: '<h3>Statistics</h3><p class="app-subtitle">An illustrative week of finding your flow.</p><div class="stat-total">1,284 <span class="stat-label">words this week</span></div><div class="sample-chart" role="img" aria-label="Illustrative word totals for Monday through Sunday: 115, 179, 230, 141, 294, 192, 133"><span style="--size:39%"></span><span style="--size:61%"></span><span style="--size:78%"></span><span style="--size:48%"></span><span style="--size:100%"></span><span style="--size:65%"></span><span style="--size:45%"></span></div><div class="stat-label">Mon &nbsp; &nbsp; Tue &nbsp; &nbsp; Wed &nbsp; &nbsp; Thu &nbsp; &nbsp; Fri &nbsp; &nbsp; Sat &nbsp; &nbsp; Sun</div>',
  settings: '<h3>Settings</h3><p class="app-subtitle">A setup that feels like yours.</p><div class="settings-row"><span>Dictation shortcut</span><span class="settings-value">Super + Alt + V</span></div><div class="settings-row"><span>Microphone</span><span class="settings-value">System default</span></div><div class="settings-row"><span>Transcription</span><span class="settings-value">Your configured provider</span></div><div class="settings-row"><span>Text cleanup</span><span class="settings-value">Optional</span></div><div class="settings-row"><span>History</span><span class="settings-value">Saved locally</span></div>'
};
let tourAnimation;
function selectTab(tab, focus = false) {
  if (tourContent.dataset.activeTab === tab.dataset.tab) { if (focus) tab.focus(); return; }
  tourTabs.forEach(item => {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  tourPanel.setAttribute('aria-labelledby', tab.id);
  const changing = Boolean(tourContent.dataset.activeTab);
  tourContent.dataset.activeTab = tab.dataset.tab;
  tourContent.innerHTML = panels[tab.dataset.tab];
  tourAnimation?.cancel();
  if (changing && !reducedMotion.matches) {
    tourAnimation = tourContent.animate([
      { opacity: .35, transform: 'translateY(5px)' },
      { opacity: 1, transform: 'translateY(0)' }
    ], { duration: 240, easing: 'cubic-bezier(.22,1,.36,1)' });
  }
  document.querySelectorAll('[data-side]').forEach(item => item.classList.toggle('selected', item.dataset.side === tab.dataset.tab));
  if (focus) tab.focus();
}
tourTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', event => {
    let next;
    if (['ArrowRight', 'ArrowDown'].includes(event.key)) next = (index + 1) % tourTabs.length;
    if (['ArrowLeft', 'ArrowUp'].includes(event.key)) next = (index + tourTabs.length - 1) % tourTabs.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tourTabs.length - 1;
    if (next !== undefined) { event.preventDefault(); selectTab(tourTabs[next], true); }
  });
});
selectTab(tourTabs[0]);

const assetBase = 'https://github.com/Parth-Jadhav-2004/caelum/releases/download/v0.3.0/';
const distributions = {
  'ubuntu-2404': ['Ubuntu 24.04', 'Ubuntu 24.04 package · x86-64', 'caelum_0.3.0-1_ubuntu-24.04_amd64.deb'],
  'ubuntu-2604': ['Ubuntu 26.04', 'Ubuntu 26.04 package · x86-64', 'caelum_0.3.0-1_ubuntu-26.04_amd64.deb'],
  'debian-12': ['Debian 12', 'Debian 12 package · x86-64', 'caelum_0.3.0-1_debian-12_amd64.deb'],
  'debian-13': ['Debian 13', 'Debian 13 package · x86-64', 'caelum_0.3.0-1_debian-13_amd64.deb'],
  arch: ['Arch Linux', 'Arch Linux package · x86-64', 'caelum-0.3.0-1-x86_64.pkg.tar.zst'],
  fedora: ['Fedora 43', 'Fedora 43 package · x86-64', 'caelum-0.3.0-1.fedora43.x86_64.rpm']
};
const distroSelect = document.querySelector('#distro');
const releaseLink = document.querySelector('#release-link');
function applyDistro(value) {
  const [name, description, file] = distributions[value];
  document.querySelector('#distro-info').textContent = description;
  releaseLink.href = assetBase + file;
  releaseLink.innerHTML = `Download for ${name} <span aria-hidden="true">↓</span>`;
}
distroSelect.addEventListener('change', () => applyDistro(distroSelect.value));
applyDistro(distroSelect.value);

// A small stagger connects the parts of each section without delaying navigation.
const revealItems = [...document.querySelectorAll(
  '.section-heading, .steps article, .portable-note, .tour-controls, .app-preview, .tour-disclaimer, .privacy-art, .privacy-copy, .download-section .section > div, .faq > div, footer'
)];
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    entry.target.classList.replace('reveal-pending', 'reveal-shown');
    revealObserver.unobserve(entry.target);
  });
}, { threshold: .05, rootMargin: '0px 0px -24px 0px' });
if (!reducedMotion.matches) {
  revealItems.forEach(item => {
    const siblings = [...item.parentElement.children].filter(child => revealItems.includes(child));
    item.style.setProperty('--reveal-delay', `${Math.min(siblings.indexOf(item), 2) * 90}ms`);
    item.classList.add('reveal-pending');
    revealObserver.observe(item);
  });
}
function showReveal(item) {
  item.classList.remove('reveal-pending', 'reveal-shown');
  revealObserver.unobserve(item);
}
document.addEventListener('focusin', event => {
  const item = event.target.closest('.reveal-pending, .reveal-shown');
  if (item) showReveal(item);
});
reducedMotion.addEventListener('change', () => {
  if (reducedMotion.matches) {
    revealItems.forEach(showReveal);
    tourAnimation?.cancel();
  }
});
