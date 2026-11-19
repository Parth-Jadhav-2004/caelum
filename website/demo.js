const scene = document.querySelector(".laptop");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
const phases = [
  ["shortcut", 1600],
  ["listening", 3300],
  ["processing", 1000],
  ["inserted", 1300],
  ["finished", 2800],
];
const draft = scene.querySelector(".draft");
const spoken = scene.querySelector(".spoken-line");
const words = draft.textContent.trim().split(/\s+/);
let timers = [];
let visible = false;

function play(index) {
  const [phase, duration] = phases[index];
  scene.dataset.phase = phase;
  if (phase === "listening") {
    if (reduceMotion.matches) {
      spoken.textContent = "“" + words.join(" ") + "”";
    } else {
      words.forEach((word, i) => {
        timers.push(setTimeout(() => {
          spoken.textContent = "“" + words.slice(0, i + 1).join(" ") + "”";
        }, i * (duration - 500) / words.length));
      });
    }
  } else {
    spoken.textContent = "";
  }
  timers.push(setTimeout(() => {
    timers = [];
    play((index + 1) % phases.length);
  }, duration));
}

function present() {
  timers.forEach(clearTimeout);
  timers = [];
  if (!visible || document.hidden) {
    scene.dataset.phase = "finished";
    return;
  }
  play(0);
}

const observer = new IntersectionObserver(([entry]) => {
  const inView = entry.intersectionRatio >= 0.2;
  if (visible === inView) return;
  visible = inView;
  present();
}, {threshold: 0.2});
observer.observe(scene.querySelector(".screen"));
reduceMotion.addEventListener("change", present);
document.addEventListener("visibilitychange", present);

const reveal = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      entry.target.classList.add("arrived");
      reveal.unobserve(entry.target);
    }
  }
});
document.querySelectorAll(".details article, .download-grid").forEach(el => reveal.observe(el));
