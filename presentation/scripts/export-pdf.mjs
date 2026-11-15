// Export the deck to a 5-page PDF (slides 1–4 plus slide 4's closing line), 1920×1080 per page.
// Uses your installed Google Chrome through playwright-core, so nothing large is downloaded.
//   cd presentation && npm i --no-save playwright-core@1.48.2 && node scripts/export-pdf.mjs
import { chromium } from 'playwright-core';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = process.argv[2] || path.join(root, 'second-thoughts-deck.pdf');
const states = ['1', '2', '3', '4', '4.2'];

const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
// Final states only: reduced motion skips entrances; the tag hangs still.
await page.emulateMedia({ reducedMotion: 'reduce' });
const shots = [];
for (const s of states) {
  await page.goto(`file://${path.join(root, 'index.html')}#${s}`);
  await page.reload();
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: '.deck-controls{display:none!important}' });
  await page.waitForTimeout(900);
  shots.push((await page.screenshot({ type: 'jpeg', quality: 90 })).toString('base64'));
}
const html = `<!doctype html><style>@page{size:1920px 1080px;margin:0}body{margin:0}img{display:block;width:1920px;height:1080px;break-after:page}</style>${shots.map((b) => `<img src="data:image/jpeg;base64,${b}">`).join('')}`;
const pdfPage = await browser.newPage();
await pdfPage.setContent(html, { waitUntil: 'load' });
await pdfPage.pdf({ path: out, width: '1920px', height: '1080px', printBackground: true });
await browser.close();
console.log(`Wrote ${out} (${(fs.statSync(out).size / 1e6).toFixed(1)} MB, ${shots.length} pages)`);
