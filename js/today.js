(function () {
  'use strict';
  const J = globalThis.JW;
  function changes(id,rows,removed,latest,scope) {
    const host = document.getElementById(id);
    if (!rows.length) { const view = scope === 'all' ? 'All tracked openings' : 'Finance & Banking'; host.innerHTML = `<div class="empty-feed"><span aria-hidden="true">[ — ]</span><h3>No ${removed ? 'removed' : 'new'} postings in this view.</h3><p>${J.escape(view)} only. ${removed ? 'No removal dates match this run’s UTC date.' : 'Baseline postings are excluded from additions. Future first appearances will be listed here.'}</p></div>`; return; }
    let page = 1;
    const pageSize = 25, sorted = [...rows].sort((a,b) => a.employer.localeCompare(b.employer) || a.posting_id.localeCompare(b.posting_id));
    function render() {
      const last = Math.ceil(rows.length/pageSize);
      host.innerHTML = `<ul class="change-list">${sorted.slice((page-1)*pageSize,page*pageSize).map(r => `<li><div><span class="micro">${J.escape(r.employer)}</span><h3>${J.escape(r.title)}</h3><p>${J.escape(r.location || 'Location not supplied')}${r.department ? ' · '+J.escape(r.department) : ''}</p><small>${removed ? 'Removed' : 'First seen'} ${removed ? latest : J.escape(r.first_seen)} UTC</small></div>${J.applyLink(r,removed)}</li>`).join('')}</ul><div class="pagination"><button data-prev ${page===1?'disabled':''}>Previous</button><span>Page ${page} of ${last}</span><button data-next ${page===last?'disabled':''}>Next</button></div>`;
      host.querySelector('[data-prev]').onclick = () => { page--; render(); host.querySelector('[data-prev]').focus(); };
      host.querySelector('[data-next]').onclick = () => { page++; render(); host.querySelector('[data-next]').focus(); };
    }
    render();
  }
  async function start() {
    try {
      const {rows,status,latest} = await J.loadData();
      for (const key of ['days_with_success','open','new_today','removed_today']) document.querySelectorAll(`[data-count="${key}"]`).forEach(n => { n.textContent = J.number(status[key]); n.removeAttribute('data-loading'); });
      const relevant = J.todayFeeds(rows,latest);
      const relevantCounts = {open:J.financeOpen(rows).length,new:relevant.added.length,removed:relevant.removed.length};
      for (const key of ['open','new','removed']) document.querySelectorAll(`[data-relevant-count="${key}"]`).forEach(n => { n.textContent = J.number(relevantCounts[key]); n.removeAttribute('data-loading'); });
      const healthy = status.sources.filter(s => s.ok).length;
      document.getElementById('health-count').textContent = `${healthy} / ${status.sources.length}`;
      document.getElementById('health-message').textContent = healthy === status.sources.length ? 'All sources succeeded in the latest run' : `${status.sources.length-healthy} source(s) failed in the latest run`;
      document.getElementById('source-summary').textContent = healthy === status.sources.length ? `All ${status.sources.length} employers returned data in the latest run.` : `${healthy} of ${status.sources.length} sources succeeded. Failures remain visible below.`;
      document.getElementById('employer-total').textContent = status.sources.length;
      document.getElementById('source-title').textContent = `${status.sources.length} sources. One daily market view.`;
      const sync = document.getElementById('last-run');
      sync.dateTime = status.run_time;
      sync.textContent = new Date(status.run_time).toLocaleString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',year:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});
      document.getElementById('last-run-utc').textContent = `UTC: ${status.run_time}`;
      document.getElementById('sources').innerHTML = status.sources.map((s,i) => `<article class="source ${s.ok?'':'failed'}"><div class="source-heading"><h3>${J.escape(J.names[s.name] || s.name)}</h3><span class="led" aria-hidden="true"></span></div><div class="source-bottom"><span class="source-state">${s.ok ? '✓ OK · latest run' : '× FAILED · latest run'}</span><span><strong>${J.number(s.count)}</strong> records${s.ok?'':' this run'}</span></div></article>`).join('');
      const allFeeds = J.todayFeeds(rows,latest,'all');
      const baseline = document.getElementById('baseline');
      baseline.hidden = !(status.days_with_success === 1 && !allFeeds.added.length && !allFeeds.removed.length);
      function renderFeeds(scope = 'role') {
        const selected = scope === 'all' ? allFeeds : relevant;
        document.getElementById('new-badge').textContent = J.number(selected.added.length);
        document.getElementById('removed-badge').textContent = J.number(selected.removed.length);
        document.getElementById('feed-summary').textContent = `${scope === 'all' ? 'All tracked openings' : 'Finance & Banking'} · ${J.number(selected.added.length)} new / ${J.number(selected.removed.length)} removed in the latest run.`;
        changes('new-list',selected.added,false,latest,scope);
        changes('removed-list',selected.removed,true,latest,scope);
      }
      document.getElementById('feed-scope').addEventListener('change',event => {
        if (event.target.name === 'feed_scope') renderFeeds(event.target.value);
      });
      renderFeeds();
    } catch (e) { J.showError(e); }
  }
  if (typeof document !== 'undefined' && document.body.dataset.page === 'today') start();
})();
