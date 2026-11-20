/* The inner orbit holds the highest inventories. Orbit positions follow rank clockwise. */
(function (J) {
  'use strict';
  const shortNames = {jpmorgan_chase:'JPMorgan', bank_of_america:'BofA', wells_fargo:'Wells Fargo',
    fifth_third_bank:'Fifth Third', huntington_bank:'Huntington', simmons_bank:'Simmons', jb_hunt:'J.B. Hunt'};
  const E = J.escape, N = J.number;
  const signed = n => n > 0 ? '+' + N(n) : n < 0 ? '−' + N(-n) : '0';
  const tone = n => n > 0 ? 'gain' : n < 0 ? 'loss' : 'flat';

  function renderLandscape({rows,status,allFeeds}) {
    const employers = new Map(status.sources.map(source => [source.name, {
      id:source.name, name:J.names[source.name] || source.name, ok:source.ok,
      open:0, finance:0, added:0, removed:0, net:0
    }]));
    for (const row of rows) {
      const employer = employers.get(row.source);
      if (employer && row.status === 'open') {
        employer.open++;
        if (row.in_role) employer.finance++;
      }
    }
    for (const row of allFeeds.added) if (employers.has(row.source)) employers.get(row.source).added++;
    for (const row of allFeeds.removed) if (employers.has(row.source)) employers.get(row.source).removed++;
    const ordered = [...employers.values()].sort((a,b) => b.open-a.open || a.name.localeCompare(b.name));
    for (const employer of ordered) employer.net = employer.added-employer.removed;
    const svg = document.getElementById('network');
    const compact = matchMedia('(max-width: 620px)');
    const quiet = matchMedia('(prefers-reduced-motion: reduce)');
    const detail = document.getElementById('employer-detail');
    let selected = ordered.slice().sort((a,b) => b.finance-a.finance)[0]?.id;
    const net = document.getElementById('net-total');
    net.textContent = signed(status.new_today-status.removed_today);
    net.className = tone(status.new_today-status.removed_today);

    function rank(id,key,format,color) {
      const ranked = ordered.filter(e => key === 'net' ? e.net !== 0 : e[key] > 0)
        .sort((a,b) => (key === 'net' ? Math.abs(b.net)-Math.abs(a.net) : b[key]-a[key]) || a.name.localeCompare(b.name)).slice(0,4);
      document.getElementById(id).innerHTML = ranked.map(e => `<button class="desk-row" data-employer="${E(e.id)}"><span class="employer-label">${J.employerMark(e.id,e.name,16)}<span>${E(e.name)}</span></span><b class="${color || tone(e.net)}">${format(e[key])}</b></button>`).join('') || '<p class="muted">No observations</p>';
    }
    rank('rank-finance','finance',N,'neutral');
    rank('rank-added','added',signed,'gain');
    rank('rank-removed','removed',n => signed(-n),'loss');
    rank('rank-net','net',signed);
    function select(id) {
      selected = id;
      const e = employers.get(id);
      document.querySelectorAll('[data-employer]').forEach(node => {
        node.setAttribute('aria-pressed', String(node.dataset.employer === id));
      });
      svg.querySelectorAll('[data-route]').forEach(path => path.classList.toggle('selected',path.dataset.route === id));
      detail.innerHTML = e ? `<div class="detail-identity">${J.employerMark(e.id,e.name,36)}<div><h3>${E(e.name)}</h3><p class="selection-status ${tone(e.net)}">${signed(e.net)} net today</p></div></div>
        <dl>${[['Total open',e.open],['Finance & banking',e.finance],['New today',e.added],['Removed today',e.removed]].map(([label,value]) => `<div><dt>${label}</dt><dd>${N(value)}</dd></div>`).join('')}</dl>
        <p class="health-line">${e.ok ? '● Reporting' : '× Collection failed'}</p><button id="clear-selection">Clear selection</button>` : '<h3>Employer readout</h3><p>Select an employer to inspect its inventory and daily movement.</p>';
    }
    function draw() {
      const small = compact.matches;
      const w = small ? 370 : 820, h = small ? 410 : 370;
      const cx = w/2, cy = h/2;
      const rings = small ? [[67,83],[139,165]] : [[147,76],[324,141]];
      const inner = Math.max(1,Math.ceil(ordered.length/3));
      let routes = '', nodes = '', particles = '';
      ordered.forEach((e,i) => {
        const inside = i < inner;
        const count = inside ? inner : ordered.length-inner;
        const angle = (inside ? i : i-inner)*Math.PI*2/count - Math.PI/2 + (inside ? .36 : 0);
        const [rx,ry] = rings[inside ? 0 : 1];
        const x = cx+rx*Math.cos(angle), y = cy+ry*Math.sin(angle);
        const r = 4 + Math.sqrt(e.open/Math.max(1,ordered[0].open))*(small ? 6 : 10);
        const path = `M${cx} ${cy} Q${cx+(x-cx)*.60-(y-cy)*.20} ${cy+(y-cy)*.42+(x-cx)*.08} ${x} ${y}`;
        routes += `<path class="route" data-route="${E(e.id)}" d="${path}"/>`;
        if (i%3===0 && i<(small ? 6 : 18)) particles += `<circle class="particle" r="2"><animateMotion path="${path}" dur="${7+i/4}s" begin="-${i+2}s" repeatCount="indefinite"/></circle>`;
        const description = `${e.name} · Total open: ${N(e.open)} · Finance & banking: ${N(e.finance)} · New today: ${N(e.added)} · Removed today: ${N(e.removed)}`;
        const label = shortNames[e.id] || e.name;
        nodes += `<g class="employer-node ${tone(e.net)}" role="button" tabindex="0" data-employer="${E(e.id)}" aria-label="${E(description)}" transform="translate(${x} ${y})" style="--delay:${i*42}ms">
          <title>${E(description)}</title><circle r="${r+9}" class="hit"/><circle r="${r+5}" class="halo"/><circle r="${r}" class="disc"/>${J.employerMark(e.id,e.name,r*1.5,true)}
          <text y="${r+21}" text-anchor="middle">${E(label)}</text></g>`;
      });
      svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
      svg.innerHTML = `<g class="guides" aria-hidden="true"><path d="M0 ${cy}H${w} M${cx} 0V${h}"/>${rings.map(([rx,ry])=>`<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}"/>`).join('')}</g>
        <g aria-hidden="true">${routes}${quiet.matches ? '' : particles}</g>
        <g class="hub" transform="translate(${cx} ${cy})" aria-hidden="true"><circle class="wave" r="22"/><circle r="27"/><circle r="21"/><path d="M-11 7v-8m7 11v-18m7 15v-11m7 7v-13"/></g>${nodes}`;
      select(selected);
      syncMotion();
    }
    function syncMotion() {
      if (document.hidden || quiet.matches) svg.pauseAnimations();
      else svg.unpauseAnimations();
    }
    document.addEventListener('click',event => {
      const target = event.target.closest('[data-employer]');
      if (target) select(target.dataset.employer);
      if (event.target.id === 'clear-selection') {
        const node = svg.querySelector('[aria-pressed="true"]');
        select(null);
        node?.focus();
      }
    });
    svg.addEventListener('keydown',event => {
      if (['Enter',' '].includes(event.key) && event.target.hasAttribute('data-employer')) {
        event.preventDefault();
        select(event.target.dataset.employer);
      }
    });
    const panel = svg.closest('.landscape');
    let pulseEnd;
    document.getElementById('pulse').addEventListener('click',() => {
      clearTimeout(pulseEnd);
      panel.classList.remove('pulsing');
      void panel.offsetWidth;
      panel.classList.add('pulsing');
      pulseEnd = setTimeout(() => panel.classList.remove('pulsing'),1800);
    });
    document.addEventListener('visibilitychange',syncMotion);
    compact.addEventListener('change',draw);
    quiet.addEventListener('change',draw);
    draw();
  }
  J.renderLandscape = renderLandscape;
})(globalThis.JW);
