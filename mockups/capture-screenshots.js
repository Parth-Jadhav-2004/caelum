// Simple screenshot capture using playwright
import { chromium } from 'playwright';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function captureScreenshots() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    deviceScaleFactor: 2, // High DPI
  });
  
  const pages = [
    { file: 'dashboard-idle.html', output: 'new-dashboard-idle.png' },
    { file: 'dashboard-recording.html', output: 'new-dashboard-recording.png' },
    { file: 'history.html', output: 'new-history.png' },
    { file: 'settings.html', output: 'new-settings.png' },
    { file: 'onboarding.html', output: 'new-onboarding.png' },
  ];
  
  for (const { file, output } of pages) {
    const page = await context.newPage();
    const htmlPath = path.join(__dirname, file);
    await page.goto(`file://${htmlPath}`);
    
    // Wait for fonts and rendering
    await page.waitForTimeout(1000);
    
    // Full page screenshot
    const outputPath = path.join(__dirname, output);
    await page.screenshot({ 
      path: outputPath, 
      fullPage: true,
      type: 'png'
    });
    
    console.log(`Captured: ${output}`);
    await page.close();
  }
  
  await browser.close();
  console.log('All screenshots captured successfully!');
}

captureScreenshots().catch(console.error);
