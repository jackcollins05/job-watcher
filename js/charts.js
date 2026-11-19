/* Editorial SVG graphics. Source labels and exact values remain in data tables. */
(function (root) {
  'use strict';
  const J = root.JW, E = J.escape, N = J.number;
  const resizeBindings = new WeakMap();
  function watchWidth(node, redraw) {
    if (typeof ResizeObserver === 'undefined') return;
    const previous = resizeBindings.get(node);
    if (previous) { previous.redraw = redraw; return; }
    const binding = {width:node.clientWidth,redraw};
    const observer = new ResizeObserver(() => {
      if (Math.abs(node.clientWidth-binding.width)>2) { binding.width=node.clientWidth; binding.redraw(); }
    });
    resizeBindings.set(node,binding); observer.observe(node);
  }
  function svg(id,title,body,width=760,height=280,extra='') {
    return `<svg class="chart-svg ${extra}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="${id}-title"><title id="${id}-title">${E(title)}</title>${body}</svg>`;
  }
  function table(headers,rows,title) {
    return `<details class="chart-data"><summary>View chart data<span class="sr-only">: ${E(title)}</span></summary><div class="table-scroll"><table><thead><tr>${headers.map(h => `<th scope="col">${E(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map((cell,i) => i ? `<td>${E(cell)}</td>` : `<th scope="row">${E(cell)}</th>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
  }
  function frame(id,title,visual,headers,rows,legend='') {
    document.getElementById(id).innerHTML = `${legend}${visual}${table(headers,rows,title)}`;
  }
  function bars(id,items,title) {
    if (!items.length) return empty(id,'NO OBSERVATIONS',title);
    const max = Math.max(1,...items.map(i => i.value));
    const chart = `<div class="ranked-chart" role="group" aria-label="${E(title)}"><ol>${items.map((item,i) => `<li class="ranking-row ${i===0?'ranking-leader':''}"><span class="rank-position" aria-hidden="true">${String(i+1).padStart(2,'0')}</span><span class="rank-label" title="${E(item.label)}">${E(item.label)}</span><svg class="ranking-bar" viewBox="0 0 1000 12" preserveAspectRatio="none" aria-hidden="true"><rect class="bar-track" x="0" y="3" width="1000" height="6"/><rect class="bar-fill ${i===0?'leading':''}" x="0" y="3" width="${item.value/max*1000}" height="6"/></svg><span class="rank-value">${N(item.value)}</span></li>`).join('')}</ol></div>`;
    frame(id,title,chart,['Group','Count'],items.map(i => [i.label,i.value]));
  }
  function timeSeries(id,items,series,title) {
    if (!items.length) return empty(id,'NO SUCCESSFUL SNAPSHOTS',title);
    const node=document.getElementById(id), width=Math.max(280,Math.min(1100,node.clientWidth||760));
    const height=width<450?260:300, left=45, right=width-18, bottom=height-43;
    const observedMax = items.reduce((max,item)=>Math.max(max,...series.map(s=>item[s.key])),0);
    const magnitude = Math.pow(10,Math.floor(Math.log10(Math.max(1,observedMax))));
    const max=[1,2,5,10].map(n=>n*magnitude).find(n=>n>=Math.max(1,observedMax));
    const x=i=>items.length===1 ? (left+right)/2 : left+i/(items.length-1)*(right-left);
    const y=value=>bottom-value/max*(bottom-28);
    let body='';
    const ticks=max===1?[0,1]:[0,Math.floor(max/2),max];
    for(const value of ticks) body+=`<line class="chart-grid" x1="${left}" x2="${right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis-label" x="${left-13}" y="${y(value)+4}" text-anchor="end">${N(value)}</text>`;
    const indices=[...new Set([0,...(items.length>3?[Math.floor((items.length-1)/2)]:[]),items.length-1])];
    for(const i of indices) {
      const label=new Date(items[i].date+'T00:00:00Z').toLocaleDateString('en-US',{timeZone:'UTC',month:'short',day:'numeric'});
      const anchor=items.length===1?'middle':i===0?'start':i===items.length-1?'end':'middle';
      body+=`<text class="axis-label" x="${x(i)}" y="${height-13}" text-anchor="${anchor}">${E(label)}</text>`;
    }
    series.forEach((s,k)=>{
      const points=items.map((item,i)=>`${x(i)},${y(item[s.key])}`).join(' ');
      if(k===0&&items.length>1) body+=`<defs><linearGradient id="${id}-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7fdbdf" stop-opacity=".13"/><stop offset="1" stop-color="#7fdbdf" stop-opacity="0"/></linearGradient></defs><polygon points="${x(0)},${bottom} ${points} ${x(items.length-1)},${bottom}" fill="url(#${id}-area)"/>`;
      body+=`<polyline class="line-series series-${k}" points="${points}"/>`;
      if(items.length<=90) items.forEach((item,i)=>{body+=`<circle class="point series-${k}" cx="${x(i)}" cy="${y(item[s.key])}" r="${k?3:4.5}"><title>${item.date}: ${E(s.label)} ${N(item[s.key])}</title></circle>`;});
    });
    const legend=`<div class="chart-legend">${series.map((s,i)=>`<span class="legend-${i}"><i aria-hidden="true"></i>${E(s.label)} <strong>${N(items[items.length-1][s.key])}</strong><small>${i?'dashed':'solid'} · latest day</small></span>`).join('')}</div>`;
    frame(id,title,svg(id,title,body,width,height),['UTC date',...series.map(s=>s.label)],items.map(i=>[i.date,...series.map(s=>i[s.key])]),legend);
    watchWidth(node,()=>timeSeries(id,items,series,title));
  }
  function empty(id,label,explanation) {
    document.getElementById(id).innerHTML=`<div class="empty-chart" role="img" aria-label="${E(label+': '+explanation)}"><svg viewBox="0 0 320 64" aria-hidden="true"><path class="chart-grid" d="M0 16H320M0 48H320"/><path class="waiting-line" d="M115 32H205"/></svg><span class="micro">${E(label)}</span><p>${E(explanation)}</p><span class="muted">Unavailable, not zero.</span></div>`;
  }
  function histogram(id,values,title) {
    const bins=[{label:'0–7 days',value:0},{label:'8–14 days',value:0},{label:'15–30 days',value:0},{label:'31–60 days',value:0},{label:'61+ days',value:0}];
    values.forEach(v=>bins[v<=7?0:v<=14?1:v<=30?2:v<=60?3:4].value++);
    bars(id,bins,title);
  }
  function gauge(id,percentage,numerator,denominator) {
    const circumference=2*Math.PI*76;
    const body=`<circle class="gauge-track" cx="120" cy="115" r="76"/><circle class="gauge-value" cx="120" cy="115" r="76" stroke-dasharray="${circumference*percentage/100} ${circumference}" transform="rotate(-90 120 115)"/><text class="gauge-text" x="120" y="126" text-anchor="middle">${percentage.toFixed(1)}%</text>`;
    frame(id,'Share removed within seven days',`<div class="gauge-composition">${svg(id,'Share removed within seven days',body,240,230,'gauge-svg')}<p>${N(numerator)} qualifying removals<br><strong>${N(denominator)} mature postings</strong></p></div>`,['Population','Count'],[['Removed within seven days',numerator],['Eligible mature postings',denominator]]);
  }
  J.charts={bars,timeSeries,empty,histogram,gauge};
})(globalThis);
