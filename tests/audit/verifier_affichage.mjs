// Compare ce que le navigateur affiche aux données du portail, sur les 261 fiches, en français et en anglais.
//
// Usage, une fois depuis la racine du projet :  npm install --prefix tests
// Puis :                                        node tests/audit/verifier_affichage.mjs
//
// Le test sert lui-même portail/ sur un port libre et pilote Chrome, ou Edge à défaut (variable NAVIGATEUR pour imposer
// l'un des deux).
// Code de sortie 1 si un écart est trouvé. Les valeurs de portail/data/ sont contrôlées par verifier_donnees.py :
// lancer celui-ci d'abord. Durée : quelques minutes.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const RACINE = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const SITE = join(RACINE, 'portail');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.csv': 'text/csv', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
const serveur = createServer(async (req, res) => {
  const chemin = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const fichier = join(SITE, normalize(chemin === '/' ? '/index.html' : chemin));
  try {
    const contenu = await readFile(fichier);
    res.writeHead(200, { 'content-type': TYPES[extname(fichier)] || 'application/octet-stream' });
    res.end(contenu);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise((ok) => serveur.listen(0, 'localhost', ok));
const base = `http://localhost:${serveur.address().port}/`;

const ecarts = {}; const controles = {};
const ctrl = (famille, ok, message) => { controles[famille] = (controles[famille] || 0) + 1; if (!ok) (ecarts[famille] ||= []).push(message); };
const sp = (t) => String(t).replace(/[\s  ]+/g, ' ').trim();
// Chrome d'abord : depuis novembre 2026, Edge ne démarre plus en mode headless avec playwright-core 1.48.
async function lanceNavigateur() {
  let erreur;
  for (const channel of process.env.NAVIGATEUR ? [process.env.NAVIGATEUR] : ['chrome', 'msedge']) {
    try { return await chromium.launch({ channel, headless: true }); } catch (e) { erreur = e; }
  }
  throw erreur;
}
const navigateur = await lanceNavigateur();

for (const langue of ['fr', 'en']) {
  const contexte = await navigateur.newContext({ viewport: { width: 1440, height: 900 } });
  // Le service de photos du SPW est bloqué ici, comme dans un artifact : la carte doit se rabattre sur les photos
  // publiées avec le portail, ou sur le plan de secteur. Le mode direct est contrôlé à part, plus bas.
  await contexte.route(/geoservices\.wallonie\.be/, (r) => r.abort());
  const p = await contexte.newPage();
  const erreurs = [];
  p.on('pageerror', (e) => erreurs.push(e.message));
  await p.addInitScript((l) => { localStorage.setItem('sols-langue', l); }, langue);
  await p.goto(base + '#accueil');
  await p.waitForSelector('path.commune');
  const idx = await (await p.request.get(base + 'data/index.json')).json();
  const loc = langue === 'en' ? 'en-GB' : 'fr-BE';
  const nb = (v, d = 0) => new Intl.NumberFormat(loc, { minimumFractionDigits: d, maximumFractionDigits: d }).format(v).replace('-', '−');
  const sg = (v, d = 0) => (v > 0 ? '+' : v < 0 ? '−' : '') + nb(Math.abs(v), d);
  const pc = (s) => sp(langue === 'en' ? `${s}%` : `${s} %`);
  const haf = (v) => nb(v, Math.abs(v) < 100 ? 1 : 0);
  const m = idx.meta;
  const cats = [...m.artif, ...m.non_artif];
  const groupes = [['resid'], ['comm', 'equip', 'loisirs', 'agri_bat', 'indus', 'carrieres', 'transport', 'autres_art'], ['arable', 'herbe'], ['foret', 'seminat', 'humide', 'eau'], ['inconnu']];
  const paquets = {};
  const fiche = async (code) => {
    const q = Math.floor(code / 1000);
    paquets[q] ||= await (await p.request.get(`${base}data/communes/${q}.json`)).json();
    return paquets[q][String(code)];
  };
  const parts = {};

  for (const co of idx.communes) {
    const f = await fiche(co.code);
    await p.evaluate((x) => { location.hash = 'commune-' + x; }, co.code);
    await p.waitForFunction((nom) => document.querySelector('h1')?.innerText.toUpperCase() === nom.toUpperCase(), co.nom, { timeout: 8000 });
    await p.waitForSelector('.graphique svg rect.barre');
    // La courbe des parts n'est dessinée qu'une fois son panneau affiché : on l'affiche, puis on revient aux hectares
    await p.click('#evolution .bascule button:nth-child(2)');
    await p.waitForSelector('#panneau-part svg polyline');
    await p.click('#evolution .bascule button:nth-child(1)');
    const d = await p.evaluate(() => {
      const t = (e) => (e ? e.textContent : '');
      const svgs = [...document.querySelectorAll('.graphique svg')];
      const bar = svgs.find((s) => s.querySelector('rect.barre'));
      return {
        tuiles: [...document.querySelectorAll('.tuiles > div, .tuiles .tuile')].map((x) => t(x.querySelector('dd'))),
        petits: [...document.querySelectorAll('.tuiles > div')].map((x) => t(x.querySelector('small'))),
        voisines: [...document.querySelectorAll('.voisines a')].map((a) => [t(a.querySelector('span')), t(a.querySelector('b')), a.getAttribute('href')]),
        tables: [...document.querySelectorAll('#vue table')].map((tb) => [...tb.querySelectorAll('tbody tr')].map((r) => [...r.children].map((c) => c.textContent))),
        phrases: [...document.querySelectorAll('.retenir li')].map((x) => x.textContent),
        legendes: [...document.querySelectorAll('.legende li')].map((x) => x.textContent),
        barres: [...bar.querySelectorAll('rect.barre')].map((r) => ({ y: +r.getAttribute('y'), h: +r.getAttribute('height'), saut: r.classList.contains('saut') })),
        y0: +bar.querySelector('line.base').getAttribute('y1'),
        corriges: [...bar.querySelectorAll('line.corrige')].map((l) => +l.getAttribute('y1')),
        lignes: [...bar.querySelectorAll('polyline')].map((l) => ({ c: l.getAttribute('class'), pts: l.getAttribute('points') })),
        courbes: [...svgs.find((s) => !s.querySelector('rect.barre')).querySelectorAll('polyline')].map((l) => ({ c: l.getAttribute('class'), pts: l.getAttribute('points') })),
      };
    });
    const nom = `${langue} ${f.nom}`;

    // Tuiles et phrases
    const dd = d.tuiles.map(sp);
    const hectaresAn = (v) => sp(`${v} ${langue === 'en' ? 'ha/yr' : 'ha/an'}`);
    // Chiffres clés : part (avec l'IWEPS en petit), rythme récent, m² par habitant, puis la surface vue du ciel si la commune est calculée
    const avecEtalement = ((m.etalement && m.etalement.communes) || []).some((x) => x.code === co.code);
    const Rn = f.reperes.population.length - 1;
    ctrl('tuiles', dd.length === 3 + (avecEtalement ? 1 : 0), `${nom} ${dd.length} tuiles`);
    ctrl('tuiles', dd[0] === pc(nb(f.part, 1)), `${nom} part ${dd[0]} pour ${f.part}`);
    if (f.part_iweps !== null) ctrl('tuiles', sp(d.petits[0]).includes(pc(nb(f.part_iweps, 1))), `${nom} IWEPS ${d.petits[0]}`);
    else ctrl('tuiles', !/IWEPS/.test(d.petits[0]), `${nom} IWEPS inattendu ${d.petits[0]}`);
    const med = f.mediane_bassin !== null ? f.mediane_bassin : m.stats.mediane_wallonie;
    ctrl('tuiles', dd[1] === hectaresAn(nb(f.rythme_recent, 1)), `${nom} rythme ${dd[1]}`);
    ctrl('tuiles', dd[2] === sp(`${nb(f.reperes.m2_habitant[Rn])} m²`), `${nom} m² par habitant ${dd[2]}`);
    const toutes = f.phrases.map((x) => sp(langue === 'en' ? x.texte_en : x.texte));
    // « En bref » reprend les phrases, sauf la première (la part), déjà dans les chiffres clés
    const attendues = f.phrases.filter((x) => x.regle !== 'part').map((x) => sp(langue === 'en' ? x.texte_en : x.texte));
    ctrl('phrases', JSON.stringify(d.phrases.map(sp)) === JSON.stringify(attendues), `${nom} phrases différentes des données`);

    // Un même chiffre, le même à chaque endroit de la fiche
    parts[co.code] = dd[0];
    const debut = toutes[0].match(langue === 'en' ? /^[\d.]+%/ : /^[\d,]+ %/)?.[0];
    ctrl('coherence-fiche', debut === dd[0], `${nom} part : tuile ${dd[0]}, phrase ${debut}`);
    const rythme = attendues.find((x) => /ha\/(an|yr)/.test(x) && /(rythme récent|recent pace)/i.test(x));
    const [, recentPhrase, passePhrase] = rythme.match(langue === 'en' ? /is (−?[\d.,]+) ha\/yr .*?against (−?[\d.,]+) ha\/yr/ : /de (−?[\d,  ]+) ha\/an .*?contre (−?[\d,  ]+) ha\/an/);
    if (Math.abs(f.rythme_recent) < 100) ctrl('coherence-fiche', hectaresAn(recentPhrase) === dd[1], `${nom} rythme : tuile ${dd[1]}, phrase ${recentPhrase}`);
    if (Math.abs(f.rythme_passe) < 100) ctrl('coherence-fiche', d.legendes.some((l) => sp(l).includes(`2011-2019`) && sp(l).endsWith(hectaresAn(passePhrase))), `${nom} rythme passé : phrase ${passePhrase} absente de la légende`);
    ctrl('coherence-fiche', attendues.some((x) => x.includes(pc(nb(med, 1)))), `${nom} médiane : tuile et phrase`);
    const compo = attendues.find((x) => /(cette part|this share)/i.test(x));
    const moteur = compo.match(langue === 'en' ? /including ([\d.]+) for|reaches ([\d.]+) point|\(([\d.]+) point/ : /dont ([\d,]+) pour|atteint ([\d,]+) point|\(([\d,]+) point/);
    const tableCategories = d.tables[0];
    if (moteur) {
      const valeur = moteur[1] || moteur[2] || moteur[3];
      const ligne = tableCategories[cats.indexOf(f.moteur[0])];
      ctrl('coherence-fiche', sp(ligne[4]).replace('+', '') === valeur, `${nom} composition : phrase ${valeur}, tableau ${ligne[4]}`);
    }

    // Légende et tableaux
    for (const g of groupes) {
      const v = g.reduce((s, k) => s + f.parts_estimees[k].at(-1), 0);
      ctrl('legende', d.legendes.some((x) => sp(x).endsWith(pc(nb(v, 1)))), `${nom} groupe ${g[0]} ${v}`);
    }
    ctrl('tableau-categories', tableCategories.length === 16, `${nom} ${tableCategories.length} catégories`);
    cats.forEach((k, i) => {
      const serie = f.parts_estimees[k];
      const libelle = (langue === 'en' ? m.libelles_en : m.libelles)[k];
      const iw = f.parts_iweps ? f.parts_iweps[k].at(-1) : null;
      const att = [libelle, nb(serie.at(-1), 1), haf(f.ha_estimes[k]), iw === null ? null : nb(iw, 1), sg(f.hausses[k], 1)].map((x) => (x === null ? null : sp(x)));
      const lu = tableCategories[i].map(sp);
      ctrl('tableau-categories', att.every((x, j) => x === null || x === lu[j]), `${nom} ${k} : ${lu} pour ${att}`);
    });
    const tableFlux = d.tables[1], tableVoisins = d.voisines;
    ctrl('tableau-flux', tableFlux.length === m.annees_flux.length, `${nom} ${tableFlux.length} années`);
    m.annees_flux.forEach((a, i) => {
      ctrl('tableau-flux', tableFlux[i][0].startsWith(String(a)) && sp(tableFlux[i][1]) === sp(sg(f.flux[i], 2)), `${nom} ${a} ${tableFlux[i]} pour ${f.flux[i]}`);
      const saut = f.sauts.some((x) => x[0] === a), reclass = f.reclassements.some((x) => x.annee === a);
      ctrl('tableau-flux', /reclass/i.test(tableFlux[i][0]) === reclass && /vérifier|to check/i.test(tableFlux[i][0]) === saut, `${nom} ${a} libellé ${tableFlux[i][0]}`);
    });
    if (f.voisins.length) {
      ctrl('tableau-voisins', tableVoisins.length === f.voisins.length, `${nom} voisins`);
      for (const v of f.voisins) {
        const l = tableVoisins.find((r) => r[0] === v.nom);
        ctrl('tableau-voisins', l && sp(l[1]) === pc(nb(v.part, 1)) && l[2] === `#commune-${v.code}`, `${nom} voisin ${v.nom} ${l} pour ${v.part}`);
      }
    }

    // Habitants, terres agricoles et activités : le tableau suit les données, les barres sont à la même échelle
    const R = f.reperes, n = R.population.length - 1;
    const rep = await p.$eval('#reperes', (s) => ({
      texte: s.innerText,
      lignes: [...s.querySelectorAll('tbody tr')].map((r) => [...r.children].map((c) => c.textContent)),
      barres: [...s.querySelectorAll('.piste span')].map((x) => parseFloat(x.style.width)),
      valeurs: [...s.querySelectorAll('dd.val')].map((x) => x.textContent),
    })).catch(() => null);
    ctrl('reperes', rep !== null, `${nom} section des repères absente`);
    if (rep) {
      ctrl('reperes', rep.lignes.length === m.annees_stock.length, `${nom} repères : ${rep.lignes.length} années`);
      m.annees_stock.forEach((a, i) => {
        const att = [String(a), nb(R.population[i]), nb(R.m2_habitant[i]), nb(R.agricole_ha[i], 1), nb(R.industrie_ha[i], 1), nb(R.commerce_ha[i], 1)].map(sp);
        const lu = (rep.lignes[i] || []).map(sp);
        ctrl('reperes', att.every((x, j) => x === lu[j]), `${nom} repères ${a} : ${lu} pour ${att}`);
      });
      const b = idx.bassins.find((x) => x.cle === f.bassin_cle || x.nom === f.bassin);
      const vals = [R.m2_habitant[n], ...(f.bassin ? [b.reperes.m2_habitant[n]] : []), m.region.reperes.m2_habitant[n]];
      ctrl('reperes', rep.valeurs.map(sp).join('|') === vals.map((v) => sp(`${nb(v)} m²`)).join('|'), `${nom} repères : barres ${rep.valeurs} pour ${vals}`);
      const vmax = Math.max(...vals);
      vals.forEach((v, i) => ctrl('reperes', Math.abs(rep.barres[i] - v / vmax * 100) < 0.01, `${nom} repères : largeur ${rep.barres[i]} pour ${v}`));
      const txt = sp(rep.texte);
      ctrl('reperes', txt.includes(sp(`${nb(R.m2_habitant[n])} m²`)) && txt.includes(sp(`${nb(R.m2_habitant[0])} m²`)), `${nom} repères : phrase par habitant`);
      const partAgri = f.parts_estimees.arable[n] + f.parts_estimees.herbe[n];
      ctrl('reperes', txt.includes(sp(`${nb(R.agricole_ha[n])} ha`)) && txt.includes(pc(nb(partAgri))), `${nom} repères : phrase agricole`);
      const hausseAct = R.industrie_ha[n] - R.industrie_ha[0] + R.commerce_ha[n] - R.commerce_ha[0], hausseArtif = R.artif_ha[n] - R.artif_ha[0];
      const partAct = hausseArtif >= 1 && hausseAct > 0 && hausseAct <= hausseArtif ? hausseAct / hausseArtif * 100 : null;
      ctrl('reperes', partAct === null ? !/(de la hausse des terrains|of the increase in artificialised)/.test(txt) : txt.includes(pc(nb(partAct))), `${nom} repères : part des activités ${partAct}`);
    }

    // Graphique des flux : chaque barre proportionnelle à son flux, du bon côté, marquée si l'année est signalée
    ctrl('graphique-barres', d.barres.length === m.annees_flux.length, `${nom} ${d.barres.length} barres`);
    const echelles = d.barres.map((x, i) => (Math.abs(f.flux[i]) > 0.5 ? x.h / Math.abs(f.flux[i]) : null)).filter((x) => x !== null).sort((a, b) => a - b);
    const k = echelles[Math.floor(echelles.length / 2)];
    d.barres.forEach((x, i) => {
      const v = f.flux[i], a = m.annees_flux[i];
      ctrl('graphique-barres', Math.abs(x.h - Math.abs(v) * k) < 0.6, `${nom} ${a} hauteur ${x.h} pour ${v}`);
      if (Math.abs(v) * k > 1) ctrl('graphique-barres', v >= 0 ? x.y + x.h <= d.y0 + 0.5 : x.y >= d.y0 - 0.5, `${nom} ${a} mauvais côté (${v})`);
      ctrl('graphique-barres', x.saut === (f.sauts.some((q) => q[0] === a) || f.reclassements.some((q) => q.annee === a)), `${nom} ${a} couleur`);
    });
    const yDe = (v) => d.y0 - v * k;
    f.reclassements.forEach((r, i) => ctrl('graphique-lignes', Math.abs(d.corriges[i] - yDe(r.corrige)) < 0.8, `${nom} trait corrigé ${r.annee}`));
    const niveau = (c) => d.lignes.filter((l) => l.c.includes(c)).map((l) => +l.pts.split(' ')[0].split(',')[1]);
    ctrl('graphique-lignes', Math.abs(niveau('passe')[0] - yDe(f.rythme_passe)) < 0.8, `${nom} moyenne passée`);
    ctrl('graphique-lignes', Math.abs(niveau('recent')[0] - yDe(f.rythme_recent)) < 0.8, `${nom} moyenne récente`);

    // Courbe : les points suivent les valeurs
    const pts = d.courbes.find((l) => l.c.includes('estim')).pts.split(' ').map((q) => q.split(',').map(Number));
    ctrl('graphique-courbe', pts.length === m.annees_stock.length, `${nom} ${pts.length} points`);
    const vs = f.parts_estimees.artif;
    const i0 = vs.indexOf(Math.min(...vs)), i1 = vs.indexOf(Math.max(...vs));
    if (vs[i1] - vs[i0] > 0.05) {
      const pente = (pts[i1][1] - pts[i0][1]) / (vs[i1] - vs[i0]);
      pts.forEach((q, i) => ctrl('graphique-courbe', Math.abs(q[1] - (pts[i0][1] + pente * (vs[i] - vs[i0]))) < 0.8, `${nom} point ${m.annees_stock[i]}`));
    }

    // Étalement vu du ciel : seulement sur les communes calculées, avec les chiffres de leur fichier
    if (!avecEtalement) ctrl('etalement', !(await p.$('#etalement')), `${nom} section étalement inattendue`);
    else {
      await p.waitForSelector('#etalement .etal-tache');
      const e = await (await p.request.get(`${base}data/etalement/${co.code}.json`)).json();
      const r = e.resume;
      // textContent : une partie des chiffres est dans les détails repliés
      const txt = sp(await p.$eval('#etalement', (x) => x.textContent));
      ctrl('tuiles', dd[3] === sp(`${nb(r.neuf_ha, 1)} ha`), `${nom} vu du ciel ${dd[3]} pour ${r.neuf_ha}`);
      ctrl('etalement', (await p.$$eval('#etalement .etal-tache', (l) => l.length)) === e.taches.length, `${nom} nombre de taches`);
      for (const [cle, v] of [['bâtiments', r.batiments_ha], ['abords', r.abords_ha], ['neuf', r.neuf_ha], ['cadastre', r.flux_cadastre.ha]]) {
        ctrl('etalement', txt.includes(sp(nb(v, 1)) + ' ha'), `${langue} ${nom} ${cle} ${nb(v, 1)} ha absent`);
      }
      ctrl('etalement', txt.includes(pc(nb(r.centralite.neuf_ha / r.neuf_ha * 100))), `${langue} ${nom} part en centralité`);
      const bruit = (r.bruit.batiments_inverses_ha + r.bruit.abords_inverses_ha) / r.neuf_ha * 100;
      ctrl('etalement', txt.includes(pc(nb(bruit))), `${langue} ${nom} part du bruit ${nb(bruit)}`);
      if (rep && r.neuf_ha > 0) {
        const t = sp(rep.texte), culture = (r.avant.herbe_rotation || 0) / r.neuf_ha * 100, prairie = (r.avant.herbe_permanente || 0) / r.neuf_ha * 100;
        // une part arrondie à zéro n'est pas citée
        const citee = (v) => Math.round(v) === 0 || t.includes(pc(nb(v)));
        const aucune = Math.round(culture) === 0 && Math.round(prairie) === 0;
        ctrl('reperes', aucune ? !t.includes(sp(`${nb(r.neuf_ha, 1)} ha`) + (langue === 'en' ? ' built or paved' : ' bâtis ou revêtus'))
          : t.includes(sp(`${nb(r.neuf_ha, 1)} ha`)) && citee(culture) && citee(prairie) && !/(^|[^\d,.])0\s?% (étaient|were)/.test(t), `${nom} repères : ce qu'il y avait en 2018`);
      }
      const barres = await p.$$eval('#etalement .etal-barres:not(.etal-periodes) dd.val', (l) => l.map((x) => x.textContent));
      const attendues = Object.values(r.par_famille).map((v) => (v.batiments_ha + v.abords_ha) / r.neuf_ha * 100);
      ctrl('etalement', barres.length > 0 && barres.every((b) => attendues.some((a) => sp(b) === pc(nb(a)))), `${langue} ${nom} parts par zone ${barres}`);
      // Rythme par période : surface par an, période de 1, 1 et 3 ans
      const rythme = await p.$$eval('#etalement .etal-periodes dd.val', (l) => l.map((x) => x.textContent));
      const durees = [1, 1, 3], pe = Object.values(r.periodes);
      ctrl('etalement', rythme.length === 3 && rythme.every((b, i) => sp(b).startsWith(sp(nb((pe[i].batiments_ha + pe[i].abords_ha) / durees[i], 1)))), `${langue} ${nom} rythme ${rythme}`);
      // Curseur : une tache est « à venir » tant que l'année choisie précède la fin de sa période
      const fin = [2019, 2020, 2023];
      const avecPhotos = m.etalement.communes.find((x) => x.code === co.code).photos;
      const repPh = await p.request.get(`${base}data/photos/${co.code}/index.json`);
      ctrl('etalement', avecPhotos === repPh.ok(), `${nom} photos annoncées ${avecPhotos}`);
      const ph = avecPhotos ? await repPh.json() : null;
      const derniere = ph ? ph.annees.at(-1) : 2023;
      for (const a of [2018, 2019, 2020, 2022, 2023, derniere]) {
        await p.$eval('#etalement input[type=range]', (x, v) => { x.value = v; x.dispatchEvent(new Event('input')); }, a);
        const n = await p.$$eval('#etalement .etal-tache.a-venir', (l) => l.length);
        ctrl('etalement', n === e.taches.filter((t) => a < fin[t.an]).length, `${nom} ${a} : ${n} taches à venir`);
        ctrl('etalement', sp(await p.$eval('.etal-annee', (x) => x.textContent)) === String(a), `${nom} année affichée ${a}`);
      }
      // Photos : le fond pointe vers des images qui existent, et la mention cite le SPW
      if (ph) {
      const fonds = await p.$$eval('#etalement .etal-carte image', (l) => l.map((x) => x.getAttribute('href')).filter(Boolean));
      ctrl('etalement', fonds.length >= ph.fond.tuiles.length && fonds.every((f) => /fond_2026_/.test(f)), `${nom} fond 2026 : ${fonds.slice(0, 2)}`);
      for (const f of fonds.slice(0, 2)) ctrl('etalement', (await p.request.get(base + f)).ok(), `${nom} image ${f}`);
      ctrl('etalement', /SPW, 2026/.test(await p.$eval('.etal-credit', (x) => x.textContent)), `${nom} mention de la photo`);
      } else ctrl('etalement', !(await p.$('.etal-credit')) && !(await p.$('#etalement .etal-carte image')), `${nom} photos sans index`);
      // Clic sur la plus grande construction visible (après deux zooms, ou sur toute la commune si le centre est vide) :
      // l'encart donne sa surface et sa période. Le point visé doit toucher la tache elle-même : le centre de la boîte
      // d'un bâtiment en L ou en U tombe à côté.
      const viser = () => p.evaluate(() => {
        const c = document.querySelector('.etal-carte svg').getBoundingClientRect();
        const visibles = [...document.querySelectorAll('.etal-tache.construction')].map((x) => [x, x.getBoundingClientRect()])
          .filter(([, b]) => b.left > c.left && b.right < c.right && b.top > c.top && b.bottom < c.bottom && b.width >= 3 && b.height >= 3)
          .sort((u, v) => v[1].width * v[1].height - u[1].width * u[1].height);
        for (const [x] of visibles.slice(0, 20)) {
          x.scrollIntoView({ block: 'center' });
          const b = x.getBoundingClientRect(), px = b.left + b.width / 2, py = b.top + b.height / 2;
          if (document.elementFromPoint(px, py) === x) return { i: Number(x.dataset.i), x: px, y: py };
        }
        return null;
      });
      await p.click('.etal-outils button:nth-child(1)'); await p.click('.etal-outils button:nth-child(1)');
      let cible = await viser();
      if (!cible) {   // petite commune : on zoome à la molette (Ctrl) sur sa plus grande construction, comme un visiteur
        await p.click('.etal-outils button:nth-child(3)');
        // La position est relue à chaque cran : la page peut encore bouger pendant que les sections se mettent en place
        const position = () => p.evaluate(() => {
          let best = null, aire = 0;
          for (const x of document.querySelectorAll('.etal-tache.construction')) { const b = x.getBBox(); if (b.width * b.height > aire) { aire = b.width * b.height; best = x; } }
          let r = best.getBoundingClientRect();
          if (r.top < 0 || r.bottom > innerHeight) { best.scrollIntoView({ block: 'center' }); r = best.getBoundingClientRect(); }
          return [r.left + r.width / 2, r.top + r.height / 2];
        });
        for (let k = 0; k < 12; k++) {
          const [x, y] = await position();
          await p.mouse.move(x, y);
          await p.keyboard.down('Control'); await p.mouse.wheel(0, -100); await p.keyboard.up('Control');
          await p.waitForTimeout(30);
        }
        cible = await viser();
      }
      ctrl('etalement', cible !== null, `${nom} aucune construction cliquable`);
      if (cible) {
        await p.mouse.click(cible.x, cible.y);
        const encart = sp(await p.$eval('.etal-zone-carte .encart', (x) => x.innerText));
        ctrl('etalement', encart.includes(`${sp(nb(e.taches[cible.i].m2))} m²`), `${langue} ${nom} encart : ${encart.slice(0, 160)}`);
        const per = ['2018', '2019', '2020'][e.taches[cible.i].an];
        ctrl('etalement', encart.includes(per), `${langue} ${nom} période dans l'encart : ${encart.slice(0, 120)}`);
        const voir = await p.$('.etal-zone-carte .etal-bouton');
        ctrl('etalement', voir !== null, `${langue} ${nom} bouton « Voir de près » absent après le clic`);
        if (voir) await voir.click();
        if (ph && voir) {
        const vuesVisibles = await p.$$eval('#etalement .etal-carte svg svg image', (l) => l.map((x) => x.getAttribute('href')));
        ctrl('etalement', vuesVisibles.length > 0 && vuesVisibles.every((f) => /vues_2026_\d+\.jpg$/.test(f)), `${nom} vues à 0,5 m après zoom : ${vuesVisibles.length}`);
        for (const f of [...new Set(vuesVisibles)].slice(0, 2)) ctrl('etalement', (await p.request.get(base + f)).ok(), `${nom} image ${f}`);
        }
      }
    }
  }

  // Bulles de survol, sur un échantillon
  for (const code of [62118, 25005, 92094, 53053]) {
    const f = await fiche(code);
    await p.evaluate((x) => { location.hash = 'commune-' + x; }, code);
    await p.waitForFunction((nom) => document.querySelector('h1')?.innerText.toUpperCase() === nom.toUpperCase(), f.nom);
    await p.waitForTimeout(200);
    const bar = await p.evaluateHandle(() => [...document.querySelectorAll('.graphique svg')].find((s) => s.querySelector('rect.barre')));
    await bar.scrollIntoViewIfNeeded();
    const rects = await bar.$$('rect.barre');
    for (const i of [0, 7, 14]) {
      const bb = await rects[i].boundingBox();
      const cadre = await bar.boundingBox();
      await p.mouse.move(bb.x + bb.width / 2, cadre.y + cadre.height / 2);
      await p.waitForTimeout(60);
      const t = sp(await p.$$eval('.bulle', (l) => l.map((x) => x.textContent).join(' ')));
      ctrl('bulles', t.includes(String(m.annees_flux[i])) && t.includes(sp(`${sg(f.flux[i], 1)} ha`)), `${langue} ${f.nom} ${m.annees_flux[i]} : ${t} pour ${f.flux[i]}`);
    }
  }

  // Tableau de toutes les communes
  await p.evaluate(() => { location.hash = 'communes'; });
  await p.waitForSelector('#vue tbody tr');
  const lignes = await p.$$eval('#vue tbody tr', (l) => l.map((r) => [r.querySelector('a').getAttribute('href').slice(9), ...[...r.children].map((c) => c.textContent)]));
  ctrl('tableau-communes', lignes.length === idx.communes.length, `${lignes.length} lignes`);
  for (const l of lignes) {
    const co = idx.communes.find((x) => String(x.code) === l[0]);
    const f = await fiche(co.code);
    const part = sp(l[3]).match(/[\d.,]+ ?%/)?.[0];
    ctrl('tableau-communes', part === pc(nb(co.part, 1)) && sp(l[4]) === sp(nb(co.rythme, 1)) && sp(l[5]) === sp(sg(co.ecart, 1)), `${langue} ${co.nom} ${l.slice(3, 6)} pour ${co.part} ${co.rythme} ${co.ecart}`);
    ctrl('tableau-communes', l[1].endsWith('*') === co.saut, `${langue} ${co.nom} astérisque`);
    ctrl('tableau-communes', f.phrases.find((x) => x.regle === 'rythme').signal === co.signal, `${langue} ${co.nom} constat`);
    ctrl('coherence-pages', parts[co.code] === part, `${langue} ${co.nom} part : fiche ${parts[co.code]}, tableau ${part}`);
    ctrl('coherence-pages', sp(l[4]) === sp(nb(f.rythme_recent, 1)), `${langue} ${co.nom} rythme : fiche ${nb(f.rythme_recent, 1)}, tableau ${l[4]}`);
    for (const v of f.voisins) ctrl('coherence-pages', parts[v.code] === pc(nb(v.part, 1)), `${langue} ${v.nom} part : sa fiche ${parts[v.code]}, chez ${co.nom} ${pc(nb(v.part, 1))}`);
  }

  // Carte : la couleur suit la valeur
  await p.evaluate(() => { location.hash = 'accueil'; });
  await p.waitForSelector('path.commune');
  const carte = await p.$$eval('path.commune', (l) => l.map((x) => ({ code: x.dataset.code || x.getAttribute('data-code'), couleur: x.getAttribute('fill') || x.style.fill })));
  ctrl('carte', carte.length === idx.communes.length, `${carte.length} communes sur la carte`);
  const seuils = [5, 10, 20, 35];
  const classe = (v) => { let i = 0; while (i < seuils.length && v >= seuils[i]) i++; return i; };
  for (const x of carte) {
    const co = idx.communes.find((q) => String(q.code) === x.code);
    ctrl('carte', co && x.couleur === `var(--seq-${classe(co.part)})`, `${langue} ${co?.nom} couleur ${x.couleur} pour ${co?.part}`);
  }

  // Accueil : le chiffre unique de la Wallonie (cumul des années définitives), sa situation, puis le tableau des bassins
  const libelle = { fr: { 'au-dessus': 'Au-dessus de sa trajectoire', 'en-dessous': 'Sous sa trajectoire', proche: 'Proche de sa trajectoire' },
    en: { 'au-dessus': 'Above its trajectory', 'en-dessous': 'Below its trajectory', proche: 'Close to its trajectory' } }[langue];
  const ecartTexte = (b) => {
    const e = sp(nb(Math.abs(Math.round(b.ratio * 100) - 100)));
    return { 'au-dessus': langue === 'en' ? `${e}% more` : `${e} % de plus`, 'en-dessous': langue === 'en' ? `${e}% less` : `${e} % de moins`,
      proche: langue === 'en' ? `within ${m.ecart_proche_pct}%` : `moins de ${m.ecart_proche_pct} % près` }[b.statut];
  };
  const w = idx.wallonie;
  ctrl('situation', Math.abs(w.ratio - w.cumul_observe_confirme / w.cumul_autorise_confirme) < 1e-5, `ratio Wallonie ${w.ratio}`);
  const constat = await p.$eval('#vue .constat', (x) => ({ chiffre: x.querySelector('.constat-chiffre')?.textContent, badge: x.querySelector('.situation')?.textContent }));
  ctrl('situation', sp(constat.chiffre) === pc(nb(w.ratio * 100)), `${langue} accueil chiffre ${constat.chiffre}, attendu ${pc(nb(w.ratio * 100))}`);
  ctrl('situation', sp(constat.badge).endsWith(libelle[w.statut]), `${langue} accueil situation ${constat.badge}, attendu ${libelle[w.statut]}`);
  const tete = sp(await p.$eval('#vue', (x) => x.innerText.slice(0, 600)));
  ctrl('situation', tete.includes(sp(nb(w.cumul_observe_confirme))) && tete.includes(sp(nb(w.cumul_autorise_confirme))), `${langue} accueil cumuls : ${tete.slice(0, 200)}`);
  ctrl('situation', tete.includes(sp(ecartTexte(w))), `${langue} accueil écart « ${ecartTexte(w)} » absent : ${tete.slice(0, 400)}`);
  const lignesB = await p.$$eval('#vue tr[data-bassin]', (l) => l.map((r) => ({ cle: r.dataset.bassin, texte: r.innerText, badge: r.querySelector('.situation')?.textContent })));
  ctrl('situation', lignesB.length === idx.bassins.length, `${langue} accueil ${lignesB.length} bassins`);
  for (const l of lignesB) {
    const b = idx.bassins.find((x) => x.cle === l.cle);
    ctrl('situation', sp(l.texte).includes(pc(nb(b.ratio * 100))) && sp(l.badge).endsWith(libelle[b.statut]), `${langue} accueil ${b.nom} : ${sp(l.texte)}`);
  }
  const lateral = await p.$$eval('.index details[data-bassin] > summary i', (l) => l.map((x) => ({ cle: x.closest('details').dataset.bassin, texte: x.textContent, classe: x.className })));
  for (const l of lateral) {
    const b = idx.bassins.find((x) => x.cle === l.cle);
    ctrl('situation', b && sp(l.texte) === pc(nb(b.ratio * 100)) && l.classe === b.statut, `${langue} index ${l.cle} ${l.texte} ${l.classe}`);
  }
  ctrl('situation', lateral.length === idx.bassins.length, `${langue} index ${lateral.length} bassins`);

  // Pages de bassin
  for (const b of idx.bassins) {
    await p.evaluate((x) => { location.hash = 'bassin-' + x; }, b.cle);
    await p.waitForFunction(() => document.querySelector('#vue tbody tr a[href^="#commune-"]'));
    await p.waitForTimeout(250);
    const t = sp(await p.$eval('#vue', (x) => x.innerText));
    ctrl('bassins', Math.abs(b.ratio - b.cumul_observe_confirme / b.cumul_autorise_confirme) < 1e-5, `${b.nom} ratio ${b.ratio}`);
    ctrl('bassins', t.includes(pc(nb(b.ratio * 100))) && t.toLowerCase().includes(libelle[b.statut].toLowerCase()) && t.includes(sp(ecartTexte(b))), `${langue} ${b.nom} chiffre, situation ou écart absents`);
    ctrl('bassins', !t.includes(pc(nb(b.ratios.avec_provisoire * 100))) || nb(b.ratios.avec_provisoire * 100) === nb(b.ratio * 100), `${langue} ${b.nom} affiche encore la lecture avec ${m.derniere_annee_flux}`);
    ctrl('bassins', t.includes(sp(nb(b.cumul_observe_confirme))) && t.includes(sp(nb(b.cumul_autorise_confirme))), `${langue} ${b.nom} cumuls`);
    ctrl('bassins', t.includes(sp(haf(b.reference))) && t.includes(sp(haf(b.plafond_derniere_annee))), `${langue} ${b.nom} référence, plafond`);
    const rangs = await p.$$eval('#vue .section table tbody tr', (l) => l.map((r) => [r.querySelector('a')?.getAttribute('href')?.slice(9), ...[...r.children].map((c) => c.textContent)]).filter((x) => x[0]));
    ctrl('bassins', rangs.length === b.communes.length, `${langue} ${b.nom} ${rangs.length} lignes`);
    for (const r of rangs) {
      const x = b.communes.find((q) => String(q.code) === r[0]);
      ctrl('bassins', sp(r[2]).endsWith(pc(nb(x.part, 1))) && sp(r[3]) === sp(nb(x.rythme, 1)) && sp(r[4]) === sp(nb(x.cumul, 1)), `${langue} ${b.nom} ${x.nom} ${r} pour ${x.part} ${x.rythme} ${x.cumul}`);
      ctrl('coherence-pages', sp(r[2]).endsWith(parts[x.code]), `${langue} ${x.nom} part : fiche ${parts[x.code]}, bassin ${sp(r[2])}`);
    }
  }

  // Page Méthode : le test du seuil affiché vient bien des données
  await p.evaluate(() => { location.hash = 'methode'; });
  await p.waitForFunction(() => document.querySelector('#vue h1'));
  await p.waitForTimeout(250);
  const methode = sp(await p.$eval('#vue', (x) => x.innerText));
  for (const t of m.verifications.test_seuil) {
    const morceau = langue === 'en' ? `(${t.oui} of ${t.total})` : `(${t.oui} sur ${t.total})`;
    ctrl('methode', methode.includes(morceau) && methode.includes(pc(nb(t.oui / t.total * 100))), `${langue} test du seuil à ${t.ha} ha`);
  }
  ctrl('methode', !/undefined|NaN/.test(methode), `${langue} valeur vide dans la Méthode`);

  ctrl('erreurs', erreurs.length === 0, `${langue} ${erreurs.slice(0, 3)}`);
  const manquants = await p.evaluate(() => [...(window.textesManquants || [])]);
  ctrl('erreurs', manquants.length === 0, `${langue} textes sans traduction : ${manquants.slice(0, 3)}`);
  await contexte.close();
}

// Photos du SPW en direct (site hébergé hors artifact), sur une commune calculée, en français : les tuiles suivent
// l'année et le zoom, la mention cite le bon vol, et les années à vol partiel citent leur repli.
{
  const meta = (await (await fetch(base + 'data/index.json')).json()).meta;
  const pil = meta.etalement.communes.find((x) => x.code === 83034) || meta.etalement.communes[0];
  const contexte = await navigateur.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await contexte.newPage();
  const erreurs = [];
  p.on('pageerror', (e) => erreurs.push(e.message));
  await p.goto(base + '#commune-' + pil.code);
  await p.waitForSelector('#etalement .etal-tache');
  // Chaque tuile garde son adresse d'origine (data-src) ; l'image affichée vient de la mémoire de la page (blob:)
  const hrefs = () => p.$$eval('#etalement .etal-carte image', (l) => l.map((x) => x.dataset.src || x.getAttribute('href') || ''));
  const credit = () => p.$eval('.etal-credit', (x) => x.textContent);
  const direct = (await hrefs()).every((f) => f.startsWith('https://geoservices.wallonie.be/'));
  ctrl('photos-direct', (await hrefs()).length > 0 && direct, `${pil.nom} : tuiles en direct ${(await hrefs()).slice(0, 1)}`);
  const affichees = await p.waitForFunction(() => [...document.querySelectorAll('#etalement .etal-carte image')].every((x) => /^(blob:|https:)/.test(x.getAttribute('href') || '')), null, { timeout: 15000 }).then(() => true, () => false);
  ctrl('photos-direct', affichees, `${pil.nom} : toutes les tuiles reçoivent une image`);
  if (direct) {
    // La dernière année du curseur est celle affichée à l'ouverture (si son vol est partiel, ce contrôle signale le repli à vérifier).
    const der = await p.$eval('#etalement input[type=range]', (x) => x.max);
    ctrl('photos-direct', (await hrefs()).every((f) => f.includes(`/ORTHO_${der}`)) && (await hrefs()).length <= 8, `${pil.nom} ${der} : ${(await hrefs()).length} tuiles`);
    ctrl('photos-direct', new RegExp(`SPW, ${der}$`).test(await credit()), `mention ${der} : ${await credit()}`);
    for (const [a, vols, repli] of [[2022, ['ORTHO_2022_ETE', 'ORTHO_2022_PRINTEMPS', 'ORTHO_2021'], '2021'], [2024, ['ORTHO_2024', 'ORTHO_2023_ETE'], '2023'], [2019, ['ORTHO_2019'], null]]) {
      await p.$eval('#etalement input[type=range]', (x, v) => { x.value = v; x.dispatchEvent(new Event('input')); }, a);
      await p.waitForTimeout(300);
      const h = await hrefs(), courantes = h.slice(-vols.length);
      ctrl('photos-direct', vols.every((v) => courantes.some((f) => f.includes(`/${v}/`))), `${a} : vols ${courantes.map((f) => f.split('/')[7])}`);
      ctrl('photos-direct', repli ? (await credit()).includes(`(${repli} `) : /SPW, 2019$/.test(await credit()), `${a} : mention ${await credit()}`);
    }
    // Zoom sur un chantier : tuiles fines (au plus 512 m de côté), toujours de l'année choisie
    await p.click('.etal-outils button:nth-child(1)'); await p.click('.etal-outils button:nth-child(1)');
    const cible = await p.evaluate(() => {
      const c = document.querySelector('.etal-carte svg').getBoundingClientRect();
      let best = null, aire = 0;
      for (const x of document.querySelectorAll('.etal-tache.construction')) {
        const b = x.getBoundingClientRect();
        if (b.left > c.left && b.right < c.right && b.top > c.top && b.bottom < c.bottom && b.width * b.height > aire) { aire = b.width * b.height; best = x; }
      }
      best.scrollIntoView({ block: 'center' });
      const b = best.getBoundingClientRect();
      return [b.left + b.width / 2, b.top + b.height / 2];
    });
    await p.mouse.click(cible[0], cible[1]);
    await p.click('.etal-zone-carte .etal-bouton');
    await p.waitForTimeout(300);
    const fines = (await hrefs()).filter((f) => { const b = new URL(f).searchParams.get('bbox').split(',').map(Number); return b[2] - b[0] <= 512; });
    ctrl('photos-direct', fines.length > 0 && fines.every((f) => f.includes('/ORTHO_2019/')), `zoom : ${fines.length} tuiles fines`);
    const lambert = (await (await fetch(`${base}data/etalement/${pil.code}.json`)).json());
    ctrl('photos-direct', fines.every((f) => { const b = new URL(f).searchParams.get('bbox').split(',').map(Number); return b[0] % (b[2] - b[0]) === 0 && b[1] % (b[3] - b[1]) === 0 && b[0] < lambert.lambert_x0 + lambert.largeur && b[2] > lambert.lambert_x0; }), 'tuiles calées sur la grille Lambert');
  }
  ctrl('photos-direct', erreurs.length === 0, `erreurs : ${erreurs.slice(0, 2)}`);
  await contexte.close();
}
await navigateur.close();
serveur.close();

// Le dictionnaire anglais garde les nombres du français
const dictionnaire = await readFile(join(SITE, 'assets/en.js'), 'utf8');
const fenetre = {};
new Function('window', dictionnaire)(fenetre);
const nombres = (t) => (t.match(/\d+(?:[.,]\d+)?/g) || []).map((x) => x.replace(',', '.')).sort().join('|');
for (const [cle, valeur] of Object.entries(fenetre.TEXTES_EN)) ctrl('dictionnaire', nombres(cle) === nombres(valeur), `« ${cle.slice(0, 90)} » : ${nombres(cle)} / ${nombres(valeur)}`);

const total = Object.values(controles).reduce((a, b) => a + b, 0);
const nbEcarts = Object.values(ecarts).reduce((a, b) => a + b.length, 0);
console.log(`Audit de l'affichage : ${total} contrôles, français et anglais, ${nbEcarts} écart(s).`);
for (const k of Object.keys(controles).sort()) console.log(`  ${k.padEnd(22)} ${String(controles[k]).padStart(7)} contrôles, ${(ecarts[k] || []).length} écart(s)`);
for (const [k, liste] of Object.entries(ecarts)) {
  console.log(`\n--- ${k} : ${liste.length} écart(s)`);
  [...new Set(liste)].slice(0, 15).forEach((x) => console.log('   ', x.slice(0, 280)));
}
process.exit(nbEcarts ? 1 : 0);
