(function (root) {
  'use strict';
  const J = root.JW;
  const daysOpen = (row, latest) => row.first_run ? null : J.daysBetween(row.first_seen, latest);
  function daysMatch(row, latest, bucket, age = daysOpen(row,latest)) {
    if (bucket === 'all') return true;
    if (bucket === 'baseline') return age === null;
    if (age === null || age < 0) return false;
    const ranges = {'0-7':[0,7], '8-14':[8,14], '15-30':[15,30], '31-60':[31,60], '61+':[61,Infinity]};
    const range = ranges[bucket]; return !!range && age >= range[0] && age <= range[1];
  }
  function filterJobs(rows, options, latest, shortlist = new Set(), ageCache = null) {
    return rows.filter(r => r.status === 'open' && (options.role === 'all' || r.in_role) &&
      (!options.employer || r.employer === options.employer) &&
      (!options.location || r.location.toLocaleLowerCase().includes(options.location.trim().toLocaleLowerCase())) &&
      (!options.query || r.title.toLocaleLowerCase().includes(options.query.trim().toLocaleLowerCase())) &&
      daysMatch(r,latest,options.days || 'all',ageCache ? ageCache.get(r.posting_id) : undefined) && (!options.shortlist || shortlist.has(r.posting_id)))
      .sort((a,b) => (options.sort === 'oldest' ? a.first_seen.localeCompare(b.first_seen) : b.first_seen.localeCompare(a.first_seen)) || a.posting_id.localeCompare(b.posting_id));
  }
  const defaultFilters = () => ({role:'role',employer:'',location:'',query:'',days:'all',sort:'newest',shortlist:false});
  Object.assign(J,{daysOpen,daysMatch,filterJobs,defaultFilters});
  async function start() {
    try {
      const {rows,status,latest} = await J.loadData();
      const open = rows.filter(r => r.status === 'open');
      const ageCache = new Map(open.map(r => [r.posting_id,daysOpen(r,latest)]));
      const form = document.getElementById('filters');
      const employer = form.elements.employer;
      [...new Set(open.map(r => r.employer))].sort().forEach(name => employer.add(new Option(name,name)));
      const locations = document.getElementById('locations');
      locations.innerHTML = [...new Set(open.map(r => r.location).filter(Boolean))].sort().map(l => `<option value="${J.escape(l)}"></option>`).join('');
      let storage; try { storage = window.localStorage; } catch (_) { storage = null; }
      if (!storage) document.getElementById('storage-note').textContent = 'Browser storage unavailable. Stars last only for this page session.';
      let saved = J.readShortlist(storage), currentPage = 1, onlySaved = false, filtered = [], timer;
      const pageSize = 25;
      function options() { return {role:form.elements.role.value,employer:employer.value,location:form.elements.location.value,query:form.elements.query.value,days:form.elements.days.value,sort:form.elements.sort.value,shortlist:onlySaved}; }
      function render() {
        filtered = J.filterJobs(open,options(),latest,saved,ageCache);
        const totalPages = Math.max(1,Math.ceil(filtered.length/pageSize));
        currentPage = Math.min(currentPage,totalPages);
        const displayed = filtered.slice((currentPage-1)*pageSize,currentPage*pageSize);
        document.getElementById('match-count').textContent = J.number(filtered.length);
        document.getElementById('employer-count').textContent = J.number(new Set(filtered.map(r => r.employer)).size);
        document.getElementById('location-count').textContent = J.number(new Set(filtered.map(r => r.location).filter(Boolean)).size);
        document.getElementById('shortlist-count').textContent = J.number(saved.size);
        document.getElementById('shortlist-toggle').setAttribute('aria-pressed',String(onlySaved));
        document.getElementById('results-caption').textContent = `${J.number(filtered.length)} matching open postings · ${latest} UTC · showing ${displayed.length ? (currentPage-1)*pageSize+1 : 0}–${Math.min(currentPage*pageSize,filtered.length)}`;
        document.getElementById('results').innerHTML = displayed.map(r => {
          const age = ageCache.get(r.posting_id), starred = saved.has(r.posting_id);
          return `<tr><td data-label="Shortlist"><button class="star" data-star="${J.escape(r.posting_id)}" aria-pressed="${starred}" aria-label="${starred ? 'Remove from' : 'Add to'} shortlist: ${J.escape(r.title)}">${starred ? '★' : '☆'}</button></td><td data-label="Job title"><strong>${J.escape(r.title)}</strong>${r.department ? `<small>${J.escape(r.department)}</small>` : ''}<span class="role-tag">${r.in_role ? 'Finance / Banking Analyst' : 'Full source inventory'}</span></td><td data-label="Employer">${J.escape(r.employer)}</td><td data-label="Location"><span class="location-text" title="${J.escape(r.location || 'Not supplied')}">${J.escape(r.location || 'Not supplied')}</span></td><td data-label="Days open"><span class="age">${age === null ? 'BASELINE' : J.number(age) + ' days'}</span>${age === null ? '<small>Start unknown</small>' : ''}</td><td data-label="First seen"><time datetime="${r.first_seen}" title="${r.first_seen} UTC">${new Date(r.first_seen+'T00:00:00Z').toLocaleDateString('en-US',{timeZone:'UTC',month:'short',day:'numeric',year:'numeric'})}</time></td><td data-label="Apply">${J.applyLink(r)}</td></tr>`;
        }).join('');
        document.getElementById('no-results').hidden = filtered.length > 0;
        document.getElementById('page-label').textContent = `Page ${currentPage} of ${totalPages}`;
        document.getElementById('previous').disabled = currentPage === 1;
        document.getElementById('next').disabled = currentPage === totalPages;
      }
      function update() { currentPage = 1; render(); }
      form.addEventListener('submit',e => e.preventDefault());
      form.addEventListener('input',e => { clearTimeout(timer); if (['query','location'].includes(e.target.name)) timer = setTimeout(update,180); else update(); });
      document.getElementById('reset').addEventListener('click',() => { clearTimeout(timer); form.reset(); onlySaved = false; update(); });
      document.getElementById('shortlist-toggle').addEventListener('click',() => { onlySaved = !onlySaved; update(); });
      document.getElementById('results').addEventListener('click',e => {
        const button = e.target.closest('[data-star]'); if (!button) return;
        const id = button.dataset.star; saved = J.toggleShortlist(saved,id);
        const ok = J.saveShortlist(storage,saved);
        document.getElementById('storage-note').textContent = ok ? `${saved.has(id) ? 'Saved to' : 'Removed from'} this browser’s shortlist.` : 'Browser storage unavailable. Shortlist lasts only for this page session.';
        render();
        const replacement = [...document.querySelectorAll('[data-star]')].find(b => b.dataset.star === id);
        (replacement || document.getElementById('shortlist-toggle')).focus();
      });
      window.addEventListener('storage',e => { if (e.key === J.SHORTLIST_KEY) { saved = J.readShortlist(storage); render(); } });
      document.getElementById('browse-asof').textContent = `${J.number(status.open)} open postings in the full inventory. Finance & Banking is the default view.`;
      render();
    } catch (e) { J.showError(e); }
  }
  if (typeof document !== 'undefined' && document.body.dataset.page === 'browse') start();
})(globalThis);
