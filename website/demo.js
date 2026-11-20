const motion = matchMedia("(prefers-reduced-motion: reduce)");
const scene = document.querySelector(".desk-demo");
const pause = scene.querySelector(".motion-toggle");
const cues = [
  [0, "shortcut"],
  [1600, "listening"],
  [4200, "processing"],
  [5500, "inserted"],
  [8150, "reset"],
];
const duration = 8800;
let inView = false;
let paused = motion.matches;
let elapsed = 0;
let since = null;
let timer;

function paint() {
  const t = (elapsed + performance.now() - since) % duration;
  const [, phase] = cues.findLast(cue => cue[0] <= t);
  scene.dataset.phase = phase;
  const next = cues.find(cue => cue[0] > t)?.[0] ?? duration;
  timer = setTimeout(paint, Math.ceil(next - t));
}
function sync() {
  clearTimeout(timer);
  const now = performance.now();
  if (since !== null) elapsed = (elapsed + now - since) % duration;
  since = null;
  scene.dataset.running = String(inView && !document.hidden && !paused);
  if (scene.dataset.running === "true") {
    since = now;
    paint();
  }
  pause.textContent = paused ? "Play animation" : "Pause animation";
}
pause.hidden = false;
pause.addEventListener("click", () => { paused = !paused; sync(); });
new IntersectionObserver(([entry]) => {
  inView = entry.isIntersecting;
  sync();
}).observe(scene);
document.addEventListener("visibilitychange", sync);
motion.addEventListener("change", () => {
  paused = motion.matches;
  sync();
  if (paused) {
    elapsed = 0;
    scene.dataset.phase = "inserted";
  }
});

// Without JS these remain native disclosures. With JS, keep both panels in
// layout while they exchange height so even an interrupted close can reverse.
const faq = document.querySelector(".faq-list");
const rows = Array.from(faq.querySelectorAll("details"), (details, i) => {
  const summary = details.querySelector("summary");
  const answer = details.querySelector(".answer");
  const row = document.createElement("div");
  const heading = document.createElement("h3");
  const button = document.createElement("button");
  const panel = document.createElement("div");
  const clip = document.createElement("div");
  row.className = "faq-row";
  button.type = "button";
  button.className = "faq-trigger";
  button.append(...Array.from(summary.childNodes));
  panel.id = `answer-${i}`;
  panel.className = "faq-panel";
  panel.inert = !details.open;
  button.setAttribute("aria-controls", panel.id);
  button.setAttribute("aria-expanded", String(details.open));
  clip.append(answer);
  panel.append(clip);
  heading.append(button);
  row.append(heading, panel);
  details.replaceWith(row);
  return row;
});
faq.addEventListener("click", event => {
  const trigger = event.target.closest(".faq-trigger");
  if (!trigger) return;
  const selected = trigger.getAttribute("aria-expanded") === "true" ? null : trigger;
  const previous = rows.findIndex(row => !row.querySelector(".faq-panel").inert);
  for (const [i, row] of rows.entries()) {
    const button = row.querySelector("button");
    const open = button === selected;
    if (open) row.style.setProperty("--answer-shift", previous >= 0 && i > previous ? "9px" : "-9px");
    button.setAttribute("aria-expanded", String(open));
    row.querySelector(".faq-panel").inert = !open;
  }
});
// Introduce the questions in reading order on first arrival. Rows remain
// visible without scripting; reduced-motion visitors get the full list at once.
const arrival = new IntersectionObserver(([entry]) => {
  if (!entry.isIntersecting) return;
  arrival.disconnect();
  if (motion.matches) return;
  rows.forEach((row, index) => {
    row.animate(
      [{opacity: 0.45, transform: "translateY(7px)"}, {opacity: 1, transform: "none"}],
      {duration: 320, delay: index * 55, easing: "ease-out", fill: "backwards"},
    );
  });
}, {threshold: 0.12});
arrival.observe(faq);
