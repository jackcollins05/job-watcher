/* Network-first coherent status/history pairs; versioned, local-only app shell. */
'use strict';
const VERSION = 'jw-shell-v5';
const META = 'jw-snapshot-meta-v1';
const DATA_PREFIX = 'jw-data-v1-';
const SHELL = ['./','index.html','browse.html','market.html','css/styles.css','js/common.js','js/today.js','js/landscape.js','js/browse.js','js/market.js','js/charts.js','manifest.webmanifest','assets/favicon.svg','assets/icon-192.png','assets/icon-512.png'];
const base = self.registration.scope;
const dataPaths = ['data/status.json','data/history.csv'];
const pointerURL = new URL('__cached_snapshot__',base).href;
let pendingPair;
self.addEventListener('install',event => {
  event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(SHELL.map(path => new URL(path,base).href))).then(() => self.skipWaiting()));
});
self.addEventListener('activate',event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('jw-shell-') && k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
async function cachedPair() {
  const meta = await caches.open(META), pointer = await meta.match(pointerURL);
  if (!pointer) throw new Error('No complete offline snapshot yet.');
  const cache = await caches.open(await pointer.text());
  const responses = await Promise.all(dataPaths.map(path => cache.match(new URL(path,base).href)));
  if (responses.some(r => !r)) throw new Error('Offline snapshot incomplete.');
  return {responses,cached:true};
}
async function refreshPair() {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(),12000);
  let responses;
  try {
    responses = await Promise.all(dataPaths.map(path => fetch(new URL(path,base).href,{cache:'no-store',signal:controller.signal})));
    if (responses.some(r => !r.ok)) throw new Error('Data request failed.');
    const status = await responses[0].clone().json();
    const csv = await responses[1].clone().text();
    // Reuse the browser parser and reconciliation before replacing offline data.
    const rows = self.JW.historyRows(csv); self.JW.validateData(status,rows);
  } catch (_) { return cachedPair(); }
  finally { clearTimeout(timer); }
  const name = DATA_PREFIX+Date.now()+'-'+Math.random().toString(36).slice(2);
  let published = false;
  try {
    const cache = await caches.open(name);
    await Promise.all(responses.map((r,i) => cache.put(new URL(dataPaths[i],base).href,r.clone())));
    const meta = await caches.open(META);
    // Publish the pointer only after both validated files have been persisted.
    await meta.put(pointerURL,new Response(name));
    published = true;
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith(DATA_PREFIX) && k !== name).map(k => caches.delete(k)));
  } catch (_) { if (!published) { try { await caches.delete(name); } catch (_) { /* Browser storage unavailable. */ } } }
  return {responses,cached:false};
}
importScripts('js/common.js');
SHELL.push(...Object.values(JW.employerAssets));
async function dataResponse(path) {
  if (!pendingPair) {
    pendingPair = refreshPair();
    // Both concurrent browser requests share a single pair fetch/validation.
    const current = pendingPair;
    current.finally(() => setTimeout(() => { if (pendingPair === current) pendingPair = null; },1000)).catch(() => {});
  }
  try {
    const pair = await pendingPair, response = pair.responses[dataPaths.indexOf(path)].clone();
    const headers = new Headers(response.headers);
    headers.set('X-Job-Watcher-Cache',pair.cached ? 'offline' : 'network');
    return new Response(response.body,{status:response.status,headers});
  } catch (_) { return new Response('No cached data is available. Connect and reload.',{status:503}); }
}
self.addEventListener('fetch',event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== new URL(base).origin || !url.href.startsWith(base)) return;
  const path = url.pathname.slice(new URL(base).pathname.length);
  if (dataPaths.includes(path)) { event.respondWith(dataResponse(path)); return; }
  const normalized = path || 'index.html';
  if (!SHELL.includes(normalized)) return;
  // Network-first HTML/assets avoids holding yesterday's shell forever. Offline
  // fallback is exact-page only: a missing URL is never replaced by a false page.
  event.respondWith((async () => {
    const cache = await caches.open(VERSION);
    try { const response = await fetch(event.request); if (response.ok) { try { await cache.put(new URL(normalized,base).href,response.clone()); } catch (_) { /* Keep fresh shell usable if storage is full. */ } return response; } }
    catch (_) { /* exact cached shell below */ }
    return await cache.match(new URL(normalized,base).href) || new Response('Offline page unavailable.',{status:503});
  })());
});
