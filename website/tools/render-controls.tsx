// Run from the repository root with npx tsx website/tools/render-controls.tsx.
import { readFileSync, writeFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { Button } from "../../src/components/ui/button";
import { Label } from "../../src/components/ui/label";

function downloadMenu() {
  return <details className="download-menu">
    <Button asChild size="lg" className="button">
      <summary><span className="download-title">Download Caelum</span><svg className="menu-chevron" aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" /></svg></summary>
    </Button>
    <div className="package-options"><a href="https://github.com/Parth-Jadhav-2004/caelum/releases/latest">View stable downloads ↗</a></div>
  </details>;
}

const controls = {
  hero: downloadMenu(),
  star: <Button asChild variant="outline" size="lg" className="github-star">
    <a href="https://github.com/Parth-Jadhav-2004/caelum" aria-label="Star Caelum on GitHub" title="Star Caelum on GitHub">
      <img src="./media/github.svg" width="22" height="22" alt="" />
    </a>
  </Button>,
  label: <Label htmlFor="distro">Choose your package</Label>,
  release: <Button asChild className="button"><a id="release-link" href="https://github.com/Parth-Jadhav-2004/caelum/releases/latest">View stable releases ↗</a></Button>,
  copy: <Button id="copy-install" variant="outline" size="sm">Copy command</Button>,
};
const path = "website/index.html";
let html = readFileSync(path, "utf8");
for (const [name, component] of Object.entries(controls)) {
  const start = "<!-- ui:" + name + " -->";
  const end = "<!-- /ui:" + name + " -->";
  const pattern = new RegExp(start + "[\\s\\S]*?" + end);
  if (!pattern.test(html)) throw new Error("Missing control: " + name);
  html = html.replace(pattern, start + renderToStaticMarkup(component) + end);
}
writeFileSync(path, html);
