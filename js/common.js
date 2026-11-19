/* Shared data contract. No job data, title classifiers, or analytics are embedded. */
(function (root) {
  'use strict';
  const JW = root.JW = root.JW || {};
  const names = {tyson_foods:'Tyson Foods', keybank:'KeyBank', pepsico:'PepsiCo', jb_hunt:'J.B. Hunt', simmons_bank:'Simmons Bank', bank_of_america:'Bank of America', jpmorgan_chase:'JPMorgan Chase', wells_fargo:'Wells Fargo', huntington_bank:'Huntington Bank', truist:'Truist', pnc:'PNC', us_bank:'U.S. Bank', capital_one:'Capital One', fifth_third_bank:'Fifth Third Bank', bmo:'BMO'};
  const columns = ['posting_id','source','source_id','employer','title','location','department','posted_date','url','in_role','first_run','first_seen','last_seen','status','removed_date'];
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = value => new Intl.NumberFormat('en-US').format(value);
  function parseCSV(input) {
    const text = input.replace(/^\uFEFF/, '');
    const rows = []; let row = [], value = '', quoted = false, closed = false;
    function field() { row.push(value); value = ''; closed = false; }
    function record() { const present = row.length > 0 || value !== '' || closed; field(); if (present) rows.push(row); row = []; }
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"') { if (text[i+1] === '"') { value += '"'; i++; } else { quoted = false; closed = true; } }
        else value += ch;
      } else if (ch === '"' && !value && !closed) quoted = true;
      else if (ch === ',') field();
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i+1] === '\n') i++; record(); }
      else { if (closed || ch === '"') throw new Error('Malformed CSV quoting.'); value += ch; }
    }
    if (quoted) throw new Error('Unclosed CSV quote.');
    if (value || row.length || closed) record();
    if (!rows.length) throw new Error('CSV header is missing.');
    const header = rows.shift();
    if (new Set(header).size !== header.length) throw new Error('Duplicate CSV columns.');
    return rows.map((cells, i) => {
      if (cells.length !== header.length) throw new Error(`CSV row ${i+2} has the wrong number of fields.`);
      return Object.fromEntries(header.map((key, j) => [key, cells[j]]));
    });
  }
  function day(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Invalid UTC date.');
    const date = new Date(value + 'T00:00:00Z');
    if (!Number.isFinite(+date) || date.toISOString().slice(0,10) !== value) throw new Error('Invalid UTC date.');
    return +date / 86400000;
  }
  const daysBetween = (start, end) => day(end) - day(start);
  const latestDate = status => new Date(status.run_time).toISOString().slice(0,10);
  function dateRange(start, end) {
    if (!start) return [];
    const first = day(start), last = day(end);
    if (last < first || last - first > 36600) throw new Error('Invalid history date window.');
    return Array.from({length:last-first+1}, (_, i) => new Date((first+i)*86400000).toISOString().slice(0,10));
  }
  function historyRows(csv) {
    const header = csv.replace(/^\uFEFF/, '').split(/\r?\n/,1)[0];
    if (header !== columns.join(',')) throw new Error('History schema does not match the assignment.');
    const rows = parseCSV(csv), ids = new Set();
    for (const row of rows) {
      if (!row.posting_id || ids.has(row.posting_id)) throw new Error('Missing or duplicate posting ID.');
      ids.add(row.posting_id);
      for (const key of ['in_role','first_run']) {
        if (!['true','false'].includes(row[key])) throw new Error('Invalid history boolean.');
        row[key] = row[key] === 'true';
      }
      if (!['open','removed'].includes(row.status)) throw new Error('Invalid history state.');
      day(row.first_seen); day(row.last_seen); if (row.removed_date) day(row.removed_date);
      if (row.last_seen < row.first_seen || (row.removed_date && row.removed_date < row.first_seen) ||
          (row.status === 'removed') !== !!row.removed_date) throw new Error('Inconsistent history dates/state.');
      row.location = row.location.trim();
    }
    return rows;
  }
  const newToday = (rows, latest) => rows.filter(r => !r.first_run && r.first_seen === latest);
  const removedToday = (rows, latest) => rows.filter(r => r.removed_date === latest);
  // Relevance is supplied by history.csv. Never classify titles in the browser.
  const financeOpen = rows => rows.filter(r => r.status === 'open' && r.in_role === true);
  function todayFeeds(rows, latest, scope = 'role') {
    const visible = r => scope === 'all' || r.in_role === true;
    return {added:newToday(rows,latest).filter(visible),removed:removedToday(rows,latest).filter(visible)};
  }
  function validateData(status, rows) {
    if (!status || !Array.isArray(status.sources) || !Number.isFinite(Date.parse(status.run_time))) throw new Error('Invalid status file.');
    for (const key of ['days_with_success','open','new_today','removed_today']) if (!Number.isInteger(status[key]) || status[key] < 0) throw new Error('Invalid status counts.');
    const latest = latestDate(status);
    if (status.first_run_date) day(status.first_run_date);
    if (rows.some(r => r.first_seen > latest || r.last_seen > latest || r.removed_date > latest)) throw new Error('History is newer than status. Retry after the daily update.');
    if (rows.filter(r => r.status === 'open').length !== status.open || newToday(rows,latest).length !== status.new_today || removedToday(rows,latest).length !== status.removed_today) throw new Error('Status and history counts disagree. Retry after the daily update.');
    const seen = new Set();
    for (const s of status.sources) {
      if (seen.has(s.name) || typeof s.ok !== 'boolean' || !Number.isInteger(s.count) || s.count < 0 || (!s.ok && s.count !== 0)) throw new Error('Invalid source status.');
      seen.add(s.name);
    }
  }
  function safeURL(value) {
    if (!/^https:\/\/[^\s/@?#]+(?:\/[^\s]*)?$/i.test(value || '')) return null;
    if (typeof URL !== 'undefined') { try { const u = new URL(value); if (u.username || u.password || u.protocol !== 'https:') return null; } catch (_) { return null; } }
    return value;
  }
  function applyLink(row, removed = false) {
    const url = safeURL(row.url);
    return url ? `<a class="apply" href="${escape(url)}" target="_blank" rel="noopener noreferrer">${removed ? 'Former listing' : 'View opening'} <span aria-hidden="true">↗</span><span class="sr-only">: ${escape(row.title)} (opens a new tab)</span></a>` : '<span class="muted">Link unavailable</span>';
  }
  const SHORTLIST_KEY = 'job-watcher.shortlist.v1';
  function readShortlist(storage) {
    try { const value = JSON.parse(storage.getItem(SHORTLIST_KEY) || '[]'); return new Set(Array.isArray(value) ? value.filter(v => typeof v === 'string' && v.length > 0) : []); }
    catch (_) { return new Set(); }
  }
  function saveShortlist(storage, ids) {
    try { storage.setItem(SHORTLIST_KEY, JSON.stringify([...ids].sort())); return true; } catch (_) { return false; }
  }
  function toggleShortlist(ids, id) { const result = new Set(ids); result.has(id) ? result.delete(id) : result.add(id); return result; }
  function showError(error) {
    const node = document.getElementById('data-error');
    if (node) { node.hidden = false; node.textContent = `Data unavailable: ${error.message} No numbers have been estimated. Reconnect and reload.`; }
    document.querySelectorAll('[data-loading]').forEach(n => { n.textContent = '—'; n.setAttribute('aria-label','Unavailable'); });
  }
  function connection(cached = false) {
    const offline = !navigator.onLine || cached;
    const node = document.getElementById('connection');
    if (node) { node.classList.toggle('is-offline',offline); node.textContent = !navigator.onLine ? 'OFFLINE MODE / Showing last successfully loaded data' : cached ? 'CACHED SNAPSHOT / Fresh data unavailable — showing last loaded data' : 'NETWORK MODE / Last run shown below'; }
  }
  let workerPromise;
  function prepareWorker() {
    if (workerPromise) return workerPromise;
    workerPromise = (async () => {
      if (!('serviceWorker' in navigator)) return;
      try {
        await navigator.serviceWorker.register('service-worker.js');
        if (!navigator.serviceWorker.controller) await Promise.race([
          new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, {once:true})),
          new Promise(resolve => setTimeout(resolve, 3000))
        ]);
      } catch (_) { const note = document.getElementById('install-note'); if (note && !navigator.serviceWorker.controller) note.textContent = 'Offline storage unavailable in this browser session.'; }
    })();
    return workerPromise;
  }
  let dataPromise;
  function loadData() {
    if (dataPromise) return dataPromise;
    dataPromise = (async () => {
      await prepareWorker();
      const controller = new AbortController(), timer = setTimeout(() => controller.abort(),20000);
      let responses;
      try { responses = await Promise.all(['data/status.json','data/history.csv'].map(path => fetch(path,{cache:'no-store',signal:controller.signal}))); }
      finally { clearTimeout(timer); }
      if (responses.some(r => !r.ok)) throw new Error('Could not load the fixed data files.');
      const [status, csv] = await Promise.all([responses[0].json(), responses[1].text()]);
      const rows = historyRows(csv); validateData(status,rows);
      const cached = responses.some(r => r.headers.get('X-Job-Watcher-Cache') === 'offline');
      connection(cached);
      window.addEventListener('offline', () => connection(true));
      window.addEventListener('online', () => { connection(cached); document.getElementById('connection').textContent = 'CONNECTION RESTORED / Loaded snapshot shown — reload for fresh data'; });
      document.querySelectorAll('[data-sync]').forEach(n => { n.textContent = new Date(status.run_time).toLocaleString('en-US',{timeZone:'UTC',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) + ' UTC'; });
      return {status,rows,latest:latestDate(status),cached};
    })();
    return dataPromise;
  }
  function initialize() {
    connection();
    let prompt;
    const button = document.getElementById('install');
    window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); prompt = event; button.hidden = false; });
    button?.addEventListener('click', async () => { if (prompt) { await prompt.prompt(); await prompt.userChoice; prompt = null; button.hidden = true; } });
    window.addEventListener('appinstalled', () => { if (button) button.hidden = true; });
  }
  Object.assign(JW,{names,columns,escape,number,parseCSV,day,daysBetween,dateRange,latestDate,historyRows,newToday,removedToday,financeOpen,todayFeeds,validateData,safeURL,applyLink,SHORTLIST_KEY,readShortlist,saveShortlist,toggleShortlist,loadData,showError});
  if (typeof document !== 'undefined') initialize();
})(globalThis);
