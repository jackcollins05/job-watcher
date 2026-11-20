(function (root) {
  'use strict';
  const J = root.JW;
  function group(rows, field) {
    const counts = new Map();
    for (const r of rows) { const label = (r[field] || '').trim() || 'Not supplied'; counts.set(label,(counts.get(label)||0)+1); }
    return [...counts].map(([label,value]) => ({label,value})).sort((a,b) => b.value-a.value || a.label.localeCompare(b.label));
  }
  function newByDay(rows, dates) {
    const result = new Map(dates.map(date => [date,{date,all:0,role:0}]));
    for (const r of rows) if (!r.first_run) { const item = result.get(r.first_seen); if (item) { item.all++; if (r.in_role) item.role++; } }
    return [...result.values()];
  }
  function removedByDay(rows, dates) {
    const result = new Map(dates.map(date => [date,{date,all:0}]));
    for (const r of rows) { const item = result.get(r.removed_date); if (item) item.all++; }
    return [...result.values()];
  }
  const openByEmployer = rows => group(rows.filter(r => r.status === 'open'),'employer');
  const openByLocation = rows => group(rows.filter(r => r.status === 'open'),'location');
  const removedDaysOpen = rows => rows.filter(r => r.status === 'removed' && !r.first_run && r.removed_date).map(r => J.daysBetween(r.first_seen,r.removed_date)).filter(v => v >= 0);
  function median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a,b) => a-b), mid = Math.floor(sorted.length/2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2;
  }
  function removedWithinSevenDayShare(rows, latest) {
    const eligible = rows.filter(r => !r.first_run && J.daysBetween(r.first_seen,latest) >= 7);
    const numerator = eligible.filter(r => r.removed_date && J.daysBetween(r.first_seen,r.removed_date) >= 0 && J.daysBetween(r.first_seen,r.removed_date) <= 7).length;
    return {numerator,denominator:eligible.length,percentage:eligible.length ? numerator/eligible.length*100 : null};
  }
  // Presentation only. The original openByLocation() aggregation is retained.
  // Keep every open posting accounted for without treating count summaries as places.
  function locationPresentation(rows) {
    const open = rows.filter(r => r.status === 'open');
    const isSummary = r => /^\d+\s+locations?$/i.test((r.location || '').trim());
    const specificRows = open.filter(r => (r.location || '').trim() && !isSummary(r));
    const summaryRows = open.filter(isSummary);
    return {specific:group(specificRows,'location'), summaries:group(summaryRows,'location'),
      specificCount:specificRows.length, summaryCount:summaryRows.length,
      missing:open.length-specificRows.length-summaryRows.length, total:open.length};
  }
  Object.assign(J,{newByDay,removedByDay,openByEmployer,openByLocation,removedDaysOpen,median,removedWithinSevenDayShare,locationPresentation});
  async function start() {
    try {
      const {rows,status,latest} = await J.loadData();
      const dates = J.dateRange(status.first_run_date,latest);
      const additions = newByDay(rows,dates), removals = removedByDay(rows,dates);
      const employers = openByEmployer(rows);
      // Include configured employers with zero current openings, without inventing a count.
      for (const source of status.sources) { const name = J.names[source.name] || source.name; if (!employers.some(e => e.label === name)) employers.push({label:name,value:0}); }
      employers.sort((a,b) => b.value-a.value || a.label.localeCompare(b.label));
      const picker = document.getElementById('compare-employer');
      picker.innerHTML = '<option value="">Largest three by inventory</option>' + employers.map(e =>
        `<option value="${J.escape(e.label)}">${J.escape(e.label)}</option>`).join('');
      function compare() {
        const selected = picker.value ? employers.filter(e => e.label === picker.value) : employers.slice(0,3);
        const daily = dates.map(date => ({date}));
        const series = selected.map((e,i) => {
          const key = 'employer' + i;
          newByDay(rows.filter(r => r.employer === e.label),dates).forEach((d,index) => { daily[index][key] = d.all; });
          return {key,label:e.label};
        });
        const summary = document.getElementById('comparison-readout');
        summary.textContent = '';
        if (picker.value && selected.length) {
          const employerRows = rows.filter(row => row.employer === picker.value);
          const feeds = J.todayFeeds(employerRows,latest,'all');
          const id = employerRows[0]?.source || status.sources.find(source => J.names[source.name] === picker.value)?.name;
          summary.innerHTML = J.employerMark(id,picker.value) + ` ${J.escape(picker.value)} · ${J.number(selected[0].value)} open · ${J.number(J.financeOpen(employerRows).length)} finance & banking · ${J.number(feeds.added.length)} new · ${J.number(feeds.removed.length)} removed today`;
        }
        document.querySelectorAll('[data-compare]').forEach(button => {
          button.setAttribute('aria-pressed',String(button.dataset.compare === picker.value));
        });
        if (series.length) J.charts.timeSeries('comparison-chart',daily,series,'Daily additions by employer');
      }
      picker.addEventListener('change',compare);
      compare();
      const durations = removedDaysOpen(rows), middle = median(durations), share = removedWithinSevenDayShare(rows,latest), locations = locationPresentation(rows);
      const added = additions.reduce((s,d) => s+d.all,0), removed = removals.reduce((s,d) => s+d.all,0);
      document.getElementById('window-days').textContent = J.number(status.days_with_success);
      document.getElementById('market-asof').textContent = `${status.first_run_date} — ${latest} UTC · ${J.number(rows.length)} tracked postings`;
      function copy(id,heading,paragraph) { document.getElementById(id+'-finding').textContent = heading; document.getElementById(id+'-explanation').textContent = paragraph; }
      copy('new', added ? `${J.number(added)} postings have entered the tracked market.` : 'No post-baseline additions have been observed yet.', 'These are first appearances after each source’s baseline, grouped by the date we first saw them. The chart compares all postings with Finance & Banking Analyst roles. Zero means no observed additions; it does not prove every source succeeded on that date.');
      J.charts.timeSeries('new-chart',additions,[{key:'all',label:'All tracked market'},{key:'role',label:'Finance & Banking'}],'New postings per UTC day');
      copy('removed', removed ? `${J.number(removed)} previously tracked postings are no longer listed.` : 'No removals have been observed yet.', 'A removed posting was present in an earlier successful scan but is no longer returned by the employer’s job board. This does not necessarily mean the position was filled. Removals are grouped by removed_date; failed scans cannot create them. A later reappearance clears the earlier removal date, so this is current history rather than a permanent event ledger.');
      J.charts.timeSeries('removed-chart',removals,[{key:'all',label:'Removed postings'}],'Removed postings per UTC day');
      const leader = employers[0];
      copy('employer', leader && leader.value ? `${leader.label} leads with ${J.number(leader.value)} open postings — the largest tracked inventory.` : 'No open postings are currently recorded.', 'Every history row with status=open is grouped by employer, including postings outside the target role. All configured employers appear. Failed sources retain their last observed open inventory. JPMorgan Chase covers only its required analyst search.');
      J.charts.bars('employer-chart',employers,'Open postings by employer',true);
      document.getElementById('employer-chart').addEventListener('click',event => {
        const button = event.target.closest('[data-compare]');
        if (button) {
          picker.value = button.dataset.compare;
          compare();
          picker.focus();
        }
      });
      copy('duration',middle === null ? 'Median days open is not available yet.' : `The median observed time to removal is ${J.number(middle)} days.`, middle === null ? 'Insufficient post-baseline removals. The median will populate when a posting first observed after its source’s baseline is removed. Baseline postings have unknown true start dates and are excluded.' : `Among ${J.number(durations.length)} removed, non-baseline postings, days open is removed_date minus first_seen in UTC calendar days. This reports the median, not the mean; posted_date is not used.`);
      if (middle === null) J.charts.empty('duration-chart','INSUFFICIENT POST-BASELINE REMOVALS','No eligible duration observations yet.');
      else J.charts.histogram('duration-chart',durations,'Distribution of days open before removal');
      copy('share',share.percentage === null ? 'Seven-day removal share is not available yet.' : `${share.percentage.toFixed(1)}% of mature postings were removed within seven days.`, `The eligible population is non-baseline postings first seen at least seven days before ${latest}. Of those, the numerator counts rows with removed_date − first_seen ≤ 7 days. ${J.number(share.numerator)} qualifying removals / ${J.number(share.denominator)} mature postings. ${share.denominator ? 'Open eligible postings remain in the denominator.' : 'Not enough mature observations yet; unavailable does not mean 0%.'}`);
      if (share.percentage === null) J.charts.empty('share-chart','AWAITING MATURE OBSERVATIONS','At least seven days of exposure are required.');
      else J.charts.gauge('share-chart',share.percentage,share.numerator,share.denominator);
      const place = locations.specific[0];
      copy('location',place ? `${place.label} leads specific locations with ${J.number(place.value)} open postings.` : 'No specific-location openings are currently recorded.', 'The top ten specific, source-provided location strings among open postings are ranked here. We trim whitespace but do not rewrite geography. Numeric location-count summaries and missing locations are accounted for separately; no postings are deleted. Full labels are available on hover and in the chart-data table.');
      J.charts.bars('location-chart',locations.specific.slice(0,10),'Top ten specific locations among open postings');
      const summaryList = items => `<dl class="location-summary-list">${items.map(item => `<div><dt>${J.escape(item.label)}</dt><dd>${J.number(item.value)} <span>postings</span></dd></div>`).join('')}</dl>`;
      document.getElementById('location-summaries').innerHTML = locations.summaries.length ? summaryList(locations.summaries.slice(0,6)) + (locations.summaries.length>6 ? `<details class="summary-more"><summary>View all ${locations.summaries.length} location-count summaries</summary>${summaryList(locations.summaries.slice(6))}</details>` : '') : '<p>No location-count summaries in the current open inventory.</p>';
      document.getElementById('location-missing').textContent = `Location not supplied: ${J.number(locations.missing)} postings.`;
      document.getElementById('location-accounting').textContent = `${J.number(locations.specificCount)} specific-location postings + ${J.number(locations.summaryCount)} multi-location-summary postings + ${J.number(locations.missing)} without a location = ${J.number(locations.total)} open postings. All specific locations are included in that total; the chart shows the top ten.`;
    } catch (e) { J.showError(e); }
  }
  if (typeof document !== 'undefined' && document.body.dataset.page === 'market') start();
})(globalThis);
