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
let playing = false;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function playDemo() {
  if (playing) return;
  playing = true;
  replay.disabled = true;
  heroDemo.disabled = true;
  if (!reducedMotion.matches) {
    demoText.textContent = '';
    pill.classList.add('playing');
    pillStatus.textContent = 'Listening…';
    await delay(1800);
    pill.classList.remove('playing');
    pillStatus.textContent = 'Turning voice into text…';
    await delay(700);
    for (let i = 1; i <= resultText.length; i++) {
      demoText.textContent = resultText.slice(0, i);
      await delay(20);
    }
  } else {
    demoText.textContent = resultText;
  }
  pillStatus.textContent = 'Done. Back to your flow.';
  replay.innerHTML = '<span aria-hidden="true">↻</span> Replay demo';
  replay.setAttribute('aria-label', 'Replay dictation demo');
  replay.disabled = false;
  heroDemo.disabled = false;
  playing = false;
}
replay.addEventListener('click', playDemo);
heroDemo.addEventListener('click', () => {
  document.querySelector('#demo').scrollIntoView({ behavior: reducedMotion.matches ? 'instant' : 'smooth', block: 'center' });
  playDemo();
});
pillStatus.setAttribute('aria-live', 'polite');

const tourContent = document.querySelector('#tour-content');
const tourPanel = document.querySelector('#tour-panel');
const tourTabs = [...document.querySelectorAll('[data-tab]')];
const panels = {
  history: '<h3>History</h3><p class="app-subtitle">Your words, right where you left them.</p><div class="sample-search">⌕ &nbsp; Search dictations</div><div class="history-item"><p>Let’s make something that feels natural to use.</p><span>Today, 10:42 &nbsp; · &nbsp; 9 words</span></div><div class="history-item"><p>A reminder to slow down and follow the interesting idea.</p><span>Today, 09:18 &nbsp; · &nbsp; 10 words</span></div><div class="history-item"><p>I’ll send the updated notes over this afternoon.</p><span>Yesterday, 16:35 &nbsp; · &nbsp; 8 words</span></div>',
  statistics: '<h3>Statistics</h3><p class="app-subtitle">An illustrative week of finding your flow.</p><div class="stat-total">1,284 <span class="stat-label">words this week</span></div><div class="sample-chart" role="img" aria-label="Illustrative word totals for Monday through Sunday: 115, 179, 230, 141, 294, 192, 133"><span style="--size:39%"></span><span style="--size:61%"></span><span style="--size:78%"></span><span style="--size:48%"></span><span style="--size:100%"></span><span style="--size:65%"></span><span style="--size:45%"></span></div><div class="stat-label">Mon &nbsp; &nbsp; Tue &nbsp; &nbsp; Wed &nbsp; &nbsp; Thu &nbsp; &nbsp; Fri &nbsp; &nbsp; Sat &nbsp; &nbsp; Sun</div>',
  settings: '<h3>Settings</h3><p class="app-subtitle">A setup that feels like yours.</p><div class="settings-row"><span>Dictation shortcut</span><span class="settings-value">Super + Alt + V</span></div><div class="settings-row"><span>Microphone</span><span class="settings-value">System default</span></div><div class="settings-row"><span>Transcription</span><span class="settings-value">Your configured provider</span></div><div class="settings-row"><span>Text cleanup</span><span class="settings-value">Optional</span></div><div class="settings-row"><span>History</span><span class="settings-value">Saved locally</span></div>'
};
function selectTab(tab, focus = false) {
  tourTabs.forEach(item => {
    const selected = item === tab;
    item.setAttribute('aria-selected', String(selected));
    item.tabIndex = selected ? 0 : -1;
  });
  tourPanel.setAttribute('aria-labelledby', tab.id);
  tourContent.innerHTML = panels[tab.dataset.tab];
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

const distributions = {
  ubuntu: ['Ubuntu', 'Packages for Ubuntu 24.04 and 26.04 · x86-64'],
  debian: ['Debian', 'Packages for Debian 12 and 13 · x86-64'],
  arch: ['Arch Linux', 'Arch Linux package · x86-64'],
  fedora: ['Fedora', 'Package for Fedora 43 · x86-64']
};
document.querySelector('#distro').addEventListener('change', event => {
  const [name, description] = distributions[event.target.value];
  document.querySelector('#distro-info').textContent = description;
  document.querySelector('#release-link').innerHTML = `View ${name} downloads <span aria-hidden="true">↓</span>`;
});
