// Captures de la section « étalement vu du ciel » (serveur local déjà lancé sur le port donné).
// Usage : node tests/capture_etalement.mjs <port ou adresse du site> <dossier de sortie> [code]
import { chromium } from 'playwright-core';

const [port = '8766', sortie = '.', code = '92142'] = process.argv.slice(2);
const nav = await chromium.launch({ channel: process.env.NAVIGATEUR || 'msedge', headless: true });
const erreurs = [];
for (const [nom, vue, theme, langue] of [['bureau', { width: 1440, height: 1000 }, 'light', 'fr'], ['telephone', { width: 390, height: 844 }, 'light', 'fr'], ['sombre-en', { width: 1440, height: 1000 }, 'dark', 'en']]) {
  const ctx = await nav.newContext({ viewport: vue, deviceScaleFactor: 1 });
  await ctx.addInitScript(([t, l]) => { localStorage.setItem('sols-theme', t); localStorage.setItem('sols-langue', l); }, [theme, langue]);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => erreurs.push(`${nom}: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') erreurs.push(`${nom}: ${m.text()}`); });
  await page.goto(`${port.startsWith('http') ? port : `http://localhost:${port}/`}#commune-${code}`);
  await page.waitForSelector('#etalement .etal-tache');
  const section = page.locator('#etalement');
  await page.waitForTimeout(Number(process.env.ATTENTE || 0));
  await section.screenshot({ path: `${sortie}/etalement_${code}_${nom}.png` });
  // Zoom deux fois, puis clic sur la plus grande tache visible
  await page.click('.etal-outils button:nth-child(1)');
  await page.click('.etal-outils button:nth-child(1)');
  const i = await page.evaluate(() => {
    const svg = document.querySelector('.etal-carte svg'), c = svg.getBoundingClientRect();
    let best = null, aire = 0;
    for (const p of svg.querySelectorAll('.etal-tache.construction')) {
      const r = p.getBoundingClientRect();
      if (r.left > c.left && r.right < c.right && r.top > c.top && r.bottom < c.bottom && r.width * r.height > aire) { aire = r.width * r.height; best = p; }
    }
    if (!best) return null;
    const r = best.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  });
  if (i) await page.mouse.click(i[0], i[1]);
  await page.locator('.etal-zone-carte').screenshot({ path: `${sortie}/etalement_${code}_${nom}_zoom.png` });
  // Voir de près, en photo, pour deux années du curseur
  const pres = page.locator('.etal-zone-carte .etal-bouton');
  if (await pres.count()) {
    await pres.click();
    for (const a of (process.env.ANNEES || '2018,2026').split(',')) {
      await page.$eval('#etalement input[type=range]', (x, v) => { x.value = v; x.dispatchEvent(new Event('input')); }, Number(a));
      await page.waitForFunction(() => [...document.querySelectorAll('.etal-carte image')].every((im) => !im.getAttribute('href') || im.dataset.ok || im.getBBox), null, { timeout: 5000 }).catch(() => {});
      await page.waitForTimeout(Number(process.env.ATTENTE || 1500));
      await page.locator('.etal-zone-carte').screenshot({ path: `${sortie}/etalement_${code}_${nom}_photo_${a}.png` });
    }
  }
  const encart = await page.locator('.etal-zone-carte .encart').innerText();
  console.log(nom, '|', encart.replace(/\s+/g, ' ').slice(0, 300));
  if (langue === 'en') console.log('manquants', JSON.stringify([...(await page.evaluate(() => [...window.textesManquants]))]));
  await ctx.close();
}
await nav.close();
console.log(erreurs.length ? erreurs.join('\n') : 'aucune erreur');
