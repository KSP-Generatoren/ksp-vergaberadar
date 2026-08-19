/* E2E gegen docs/index.html — echte Interaktionen, echte Persistenz. */
const { chromium } = require('playwright');
const URL = 'file://' + __dirname + '/../docs/index.html';
let fails = 0;
const ok = (cond, name) => { console.log((cond?'  PASS ':'  FAIL ') + name); if(!cond) fails++; };

(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' }).catch(()=>chromium.launch());
  const ctx = await b.newContext({ viewport:{width:1440,height:1000}, deviceScaleFactor:2 });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));

  console.log('— Laden & Leitstand');
  await p.goto(URL); await p.waitForTimeout(900);
  ok(await p.$$eval('.readout', e=>e.length) === 6, 'Leitstand: 6 Instrumente');
  ok(await p.$$eval('#alarms .watch-item', e=>e.length) === 2, 'Leitstand: 2 jüngste Änderungen');
  ok((await p.$eval('#sourcelamps', e=>e.textContent)).includes('TED'), 'Quellen-Lampen sichtbar');
  await p.screenshot({ path:'../shots/f1-leitstand.png' });

  console.log('— Radar: Suche & Filter');
  await p.click('button[data-view="radar"]'); await p.waitForTimeout(400);
  const total = await p.$$eval('#list tr.row', e=>e.length);
  ok(total >= 10, `Radar zeigt offene Verfahren (${total})`);
  await p.fill('#q', 'Anhängeraggregat Feuerwehr 50 kVA'); await p.waitForTimeout(400);
  const first = await p.$eval('#list tr.row .t-title', e=>e.textContent);
  ok(first.includes('Feuerwehranhängern'), 'Beste Suchtreffer oben: ' + first.slice(0,44));
  await p.screenshot({ path:'../shots/f2-suche.png' });

  console.log('— Suchprofil speichern und reaktivieren');
  await p.click('#saveprofile'); await p.waitForTimeout(250);
  await p.fill('#profilename', 'FwA-NEA bundesweit');
  await p.click('#dlg-save'); await p.waitForTimeout(350);
  ok(await p.$$eval('.sprofile', e=>e.length) === 1, 'Profil-Chip erscheint');
  const cnt = await p.$eval('.sprofile .cnt', e=>+e.textContent);
  ok(cnt >= 3, `Profil-Trefferzähler plausibel (${cnt})`);

  console.log('— Dossier: Status, Notizen, Assistent');
  await p.fill('#q', ''); await p.waitForTimeout(300);
  const rows = await p.$$('#list tr.row');
  for (const r of rows){
    if ((await r.$eval('.t-title', e=>e.textContent)).includes('Notfallinformationspunkte')) { await r.click(); break; }
  }
  await p.waitForTimeout(600);
  ok(await p.$('#sheettitle') !== null, 'Dossier öffnet');
  ok((await p.$eval('.verdict .big', e=>e.textContent)).toLowerCase().includes('angebot'), 'Urteil sichtbar');
  await p.selectOption('#sh-status', 'angebot'); await p.waitForTimeout(300);
  await p.fill('#sh-notes', 'Kalkulation liegt bei M. — Abgabe Montag.'); await p.waitForTimeout(700);
  await p.click('.ask .qs button:nth-child(2)'); await p.waitForTimeout(250);
  ok((await p.$eval('#answer', e=>e.textContent)).includes('65 dB(A)'), 'Assistent antwortet mit Fundstelle');
  ok(await p.$('#sh-ics') !== null, 'Kalender-Button vorhanden');
  await p.screenshot({ path:'../shots/f3-dossier.png' });
  await p.keyboard.press('Escape'); await p.waitForTimeout(250);

  console.log('— Pipeline: echtes Drag & Drop');
  await p.click('button[data-view="pipeline"]'); await p.waitForTimeout(400);
  const inAngebot = await p.$$eval('[data-col="angebot"] .card', e=>e.length);
  ok(inAngebot >= 1, `Statuswechsel aus Dossier sichtbar (${inAngebot} in "Angebot in Arbeit")`);
  const card = await p.$('[data-col="neu"] .card');
  const cid = await card.getAttribute('data-cid');
  const target = await p.$('[data-col="pruefen"]');
  const cb = await card.boundingBox(), tb = await target.boundingBox();
  await p.mouse.move(cb.x+cb.width/2, cb.y+20); await p.mouse.down();
  await p.mouse.move(tb.x+tb.width/2, tb.y+80, {steps:12}); await p.waitForTimeout(150);
  await p.mouse.up(); await p.waitForTimeout(450);
  const moved = await p.$(`[data-col="pruefen"] .card[data-cid="${cid}"]`);
  ok(moved !== null, 'Karte per Drag & Drop verschoben: ' + cid);
  await p.screenshot({ path:'../shots/f4-pipeline.png' });

  console.log('— Persistenz über Neustart');
  await p.reload(); await p.waitForTimeout(900);
  await p.click('button[data-view="pipeline"]'); await p.waitForTimeout(400);
  ok(await p.$(`[data-col="pruefen"] .card[data-cid="${cid}"]`) !== null, 'Kanban-Status überlebt Reload');
  await p.click('button[data-view="radar"]'); await p.waitForTimeout(300);
  ok(await p.$$eval('.sprofile', e=>e.length) === 1, 'Suchprofil überlebt Reload');
  const rows2 = await p.$$('#list tr.row');
  for (const r of rows2){
    if ((await r.$eval('.t-title', e=>e.textContent)).includes('Notfallinformationspunkte')) { await r.click(); break; }
  }
  await p.waitForTimeout(500);
  ok((await p.$eval('#sh-notes', e=>e.value)).includes('Kalkulation'), 'Notizen überleben Reload');
  await p.keyboard.press('Escape');

  console.log('— Wächter: gelesen markieren');
  await p.click('button[data-view="waechter"]'); await p.waitForTimeout(400);
  const before = await p.$eval('#navwatch', e=>e.textContent);
  await p.click('[data-seen]'); await p.waitForTimeout(350);
  const after = await p.$eval('#navwatch', e=>e.textContent);
  ok(before !== after, `Badge reagiert auf Gelesen (${before||'leer'} → ${after||'leer'})`);
  await p.screenshot({ path:'../shots/f5-waechter.png' });

  console.log('— Profil-Editor');
  await p.click('button[data-view="profil"]'); await p.waitForTimeout(350);
  ok((await p.$eval('#pf-text', e=>e.value)).includes('KSP Generatoren'), 'Profiltext geladen');
  await p.fill('#pf-go', '75'); await p.click('#pf-save'); await p.waitForTimeout(300);
  ok((await p.$eval('#pf-note', e=>e.textContent)).includes('profile_override.json'), 'Speichern mit Export-Hinweis');
  const dl = p.waitForEvent('download');
  await p.click('#pf-export');
  const file = await dl;
  ok((await file.suggestedFilename()) === 'profile_override.json', 'Override-Export lädt herunter');
  await p.screenshot({ path:'../shots/f6-profil.png' });

  console.log('— CSV-Export');
  await p.click('button[data-view="radar"]'); await p.waitForTimeout(300);
  const dl2 = p.waitForEvent('download');
  await p.click('#csv');
  ok((await (await dl2).suggestedFilename()) === 'vergaberadar.csv', 'CSV lädt herunter');

  console.log('— Mobile 390px');
  const m = await b.newPage({ viewport:{width:390,height:844}, deviceScaleFactor:2 });
  m.on('pageerror', e=>errs.push('mobile: '+e.message));
  await m.goto(URL); await m.waitForTimeout(800);
  const overflow = await m.evaluate(()=>document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ok(overflow <= 1, `Kein horizontales Scrollen (Überstand ${overflow}px)`);
  await m.click('button[data-view="radar"]'); await m.waitForTimeout(300);
  ok(await m.$$eval('#list tr.row', e=>e.length) >= 5, 'Radar auf Mobil nutzbar');
  await m.screenshot({ path:'../shots/f7-mobil.png' });

  ok(errs.length === 0, 'Keine JS-Fehler: ' + (errs.join(' | ') || 'sauber'));
  console.log(fails === 0 ? '\nALLE E2E-TESTS BESTANDEN' : `\n${fails} FEHLER`);
  await b.close();
  process.exit(fails === 0 ? 0 : 1);
})();
