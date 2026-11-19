"""Website contract, exact browser calculations, real-data read-only checks."""
import csv
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import struct

import pytest

from js_runtime import evaluate
from job_watcher.sources import PRIMARY_SOURCES

ROOT = Path(__file__).resolve().parents[1]
PAGES = [('index.html','today'),('browse.html','browse'),('market.html','market')]


class Elements(HTMLParser):
    def __init__(self, path):
        super().__init__(); self.tags=[]; self.feed(path.read_text())
    def handle_starttag(self,tag,attrs):
        self.tags.append((tag,dict(attrs)))


@pytest.mark.parametrize('file,script',PAGES)
def test_page_contract_and_local_references(file,script):
    tree = Elements(ROOT/file)
    assert ('html',{'lang':'en'}) in tree.tags
    assert any(tag=='link' and a.get('href')=='css/styles.css' for tag,a in tree.tags)
    for page,_ in PAGES:
        assert any(tag=='a' and a.get('href')==page for tag,a in tree.tags)
    for js in ('common',script):
        assert any(tag=='script' and a.get('src')==f'js/{js}.js' and 'defer' in a for tag,a in tree.tags)
    assert any(tag=='link' and a.get('rel')=='manifest' and a.get('href')=='manifest.webmanifest' for tag,a in tree.tags)
    for tag,a in tree.tags:
        if tag not in ('script','link'): continue
        href=a.get('src') or a.get('href','')
        assert href and not href.startswith(('/', 'http')), 'Assets must work under a Pages project prefix.'
        assert (ROOT/href).is_file()
    assert any(a.get('id')=='methodology' for _,a in tree.tags)
    assert any(a.get('id')=='connection' for _,a in tree.tags)
    assert sum(a.get('aria-current')=='page' for _,a in tree.tags)==1


def test_manifest_icons_and_service_worker_assets():
    manifest=json.loads((ROOT/'manifest.webmanifest').read_text())
    assert manifest['display']=='standalone' and manifest['start_url']=='./index.html' and manifest['scope']=='./'
    for icon in manifest['icons']:
        p=ROOT/icon['src']; assert p.is_file()
        if p.suffix=='.png':
            raw=p.read_bytes(); assert raw[:8]==b'\x89PNG\r\n\x1a\n'
            w,h=struct.unpack('>II',raw[16:24]); assert f'{w}x{h}'==icon['sizes']
    sw=(ROOT/'service-worker.js').read_text()
    shell=re.search(r'const SHELL = \[(.*?)\];',sw,re.S).group(1)
    for name in re.findall(r"'([^']+)'",shell):
        assert (ROOT/name).exists()
    for path in ('data/status.json','data/history.csv'):
        assert path in sw and path in (ROOT/'js/common.js').read_text()
    assert 'self.registration.scope' in sw and "importScripts('js/common.js')" in sw
    assert sw.index('validateData(status,rows)') < sw.index('await meta.put(pointerURL')
    assert 'cachedPair()' in sw and 'X-Job-Watcher-Cache' in sw
    assert 'controller.abort()' in sw and '12000' in sw


def test_required_controls_and_six_analysis_sections():
    today=(ROOT/'index.html').read_text()
    for key in ('days_with_success','open','new_today','removed_today'):
        assert f'data-count="{key}"' in today
    browse=Elements(ROOT/'browse.html')
    assert any(tag=='input' and a.get('name')=='role' and a.get('value')=='role' and 'checked' in a for tag,a in browse.tags)
    for key in ('employer','location','days','query','sort'):
        assert any(a.get('name')==key for _,a in browse.tags)
    market=Elements(ROOT/'market.html')
    for key in ('new','removed','employer','duration','share','location'):
        assert any(tag=='h2' and a.get('id')==key+'-finding' for tag,a in market.tags)
        assert any(tag=='p' and a.get('id')==key+'-explanation' for tag,a in market.tags)
        assert any(a.get('id')==key+'-chart' for _,a in market.tags)


FIXTURE = '''
const J = JW;
const make = (id,extra={}) => ({posting_id:id,source:'test',source_id:id,employer:'Example Bank',title:'Finance Analyst',location:' Town ',department:'',url:'https://example.test/job/'+id,in_role:true,first_run:false,first_seen:'2026-11-01',last_seen:'2026-11-14',status:'open',removed_date:'',...extra});
const latest='2026-11-14';
'''
CASES = [
    ('csv_quotes_commas_blanks', '''return J.parseCSV('a,b,c\\r\\n"X, Y","Say ""hello""",\\r\\n');''', [{'a':'X, Y','b':'Say "hello"','c':''}]),
    ('csv_multiline', '''return J.parseCSV('a,b\\n"one\\ntwo",x\\n');''', [{'a':'one\ntwo','b':'x'}]),
    ('csv_empty_quoted_and_bom', '''return J.parseCSV('\\uFEFFa,b\\n"",\\n');''', [{'a':'','b':''}]),
    ('csv_all_blank_fields_retained', '''return J.parseCSV('a,b,c\\n,,\\n');''', [{'a':'','b':'','c':''}]),
    ('csv_unclosed_rejected', '''try { J.parseCSV('a,b\\n"open,x'); return false; } catch(e) { return true; }''', True),
    ('csv_mismatched_columns_rejected', '''try { J.parseCSV('a,b\\nx'); return false; } catch(e) { return true; }''', True),
    ('today_baseline_excluded', '''return J.newToday([make('base',{first_run:true,first_seen:latest}),make('new',{first_seen:latest}),make('old')],latest).map(r=>r.posting_id);''', ['new']),
    ('today_removal_date', '''return J.removedToday([make('gone',{status:'removed',removed_date:latest}),make('old')],latest).map(r=>r.posting_id);''', ['gone']),
    ('browse_default_role', '''return J.filterJobs([make('yes'),make('no',{in_role:false}),make('gone',{status:'removed'})],J.defaultFilters(),latest).map(r=>r.posting_id);''', ['yes']),
    ('browse_all_open', '''return J.filterJobs([make('yes'),make('no',{in_role:false}),make('gone',{status:'removed'})],{...J.defaultFilters(),role:'all'},latest).length;''', 2),
    ('browse_title_only_case_insensitive', '''return J.filterJobs([make('match',{title:'CREDIT analyst'}),make('other',{title:'Data Engineer',employer:'Credit Analyst'})],{...J.defaultFilters(),query:'credit ANALYST'},latest).map(r=>r.posting_id);''', ['match']),
    ('browse_employer_and_location', '''return J.filterJobs([make('a'),make('b',{employer:'Other'}),make('c',{location:'Elsewhere'})],{...J.defaultFilters(),employer:'Example Bank',location:'town'},latest).map(r=>r.posting_id);''', ['a']),
    ('baseline_days_unknown', '''return J.daysOpen(make('b',{first_run:true}),latest);''', None),
    ('non_baseline_days', '''return J.daysOpen(make('n',{first_seen:'2026-11-07'}),latest);''', 7),
    ('baseline_not_numeric_bucket', '''return [J.daysMatch(make('b',{first_run:true}),latest,'0-7'),J.daysMatch(make('b',{first_run:true}),latest,'baseline')];''', [False,True]),
    ('day_bucket_boundaries', '''return [0,7,8,14,15,30,31,60,61].map(n=>J.daysMatch(make('n',{first_seen:new Date(J.day(latest)*86400000-n*86400000).toISOString().slice(0,10)}),latest,n<=7?'0-7':n<=14?'8-14':n<=30?'15-30':n<=60?'31-60':'61+'));''', [True]*9),
    ('sort_first_seen_both_directions', '''const rows=[make('a',{first_seen:'2026-11-01'}),make('b',{first_seen:'2026-11-02'})]; return ['newest','oldest'].map(sort=>J.filterJobs(rows,{...J.defaultFilters(),sort},latest).map(r=>r.posting_id));''', [['b','a'],['a','b']]),
    ('shortlist_persists_across_reload', '''const memory={};const storage={getItem:k=>memory[k],setItem:(k,v)=>{memory[k]=v;}};let ids=J.toggleShortlist(J.readShortlist(storage),'stable:123'); J.saveShortlist(storage,ids);return [...J.readShortlist(storage)];''', ['stable:123']),
    ('shortlist_unstar', '''return [...J.toggleShortlist(new Set(['one']),'one')];''', []),
    ('shortlist_storage_failure', '''return [J.saveShortlist(null,new Set(['a'])),[...J.readShortlist(null)]];''', [False,[]]),
    ('shortlist_invalid_payload', '''return [...J.readShortlist({getItem:()=>'{broken'})];''', []),
    ('shortlist_only_open_matches', '''return J.filterJobs([make('a'),make('b'),make('c',{status:'removed'})],{...J.defaultFilters(),shortlist:true},latest,new Set(['b','c'])).map(r=>r.posting_id);''', ['b']),
    ('new_daily_all_and_role', '''return J.newByDay([make('a'),make('b',{in_role:false}),make('baseline',{first_run:true})],['2026-11-01','2026-11-02']);''', [{'date':'2026-11-01','all':2,'role':1},{'date':'2026-11-02','all':0,'role':0}]),
    ('removed_daily', '''return J.removedByDay([make('a',{removed_date:latest,status:'removed'}),make('base',{first_run:true,removed_date:latest,status:'removed'}),make('open')],[latest]);''', [{'date':'2026-11-14','all':2}]),
    ('open_employers', '''return J.openByEmployer([make('a'),make('b'),make('c',{employer:'Other'}),make('gone',{status:'removed'})]);''', [{'label':'Example Bank','value':2},{'label':'Other','value':1}]),
    ('duration_exact_population', '''return J.removedDaysOpen([make('a',{status:'removed',removed_date:'2026-11-04'}),make('base',{first_run:true,status:'removed',removed_date:latest}),make('open')]);''', [3]),
    ('median_odd_even_empty_zero', '''return [J.median([7,1,3]),J.median([1,8,3,4]),J.median([]),J.median([0])];''', [3,3.5,None,0]),
    ('seven_day_exact_eligibility', '''return J.removedWithinSevenDayShare([make('seven',{first_seen:'2026-11-07',status:'removed',removed_date:latest}),make('eight',{status:'removed',removed_date:'2026-11-09'}),make('open'),make('young',{first_seen:'2026-11-08',status:'removed',removed_date:'2026-11-09'}),make('baseline',{first_run:true})],latest);''', {'numerator':1,'denominator':3,'percentage':100/3}),
    ('seven_day_unavailable_not_zero', '''return J.removedWithinSevenDayShare([make('baseline',{first_run:true}),make('young',{first_seen:latest})],latest);''', {'numerator':0,'denominator':0,'percentage':None}),
    ('locations_trim_not_normalize', '''return J.openByLocation([make('a'),make('b',{location:'Town'}),make('c',{location:'town'}),make('d',{location:''}),make('gone',{status:'removed'})]);''', [{'label':'Town','value':2},{'label':'Not supplied','value':1},{'label':'town','value':1}]),
    ('utc_date_and_no_dst_rounding', '''return [J.latestDate({run_time:'2026-11-14T23:59:00-06:00'}),J.daysBetween('2026-10-31','2026-11-02')];''', ['2026-11-15',2]),
    ('date_validation', '''try { J.day('2026-02-30');return false; }catch(e){return true;}''', True),
    ('escaping_and_link_safety', '''return [J.escape('<img onerror="x">'),J.safeURL('javascript:alert(1)'),J.safeURL('https://user:secret@example.test/job/1')];''', ['&lt;img onerror=&quot;x&quot;&gt;',None,None]),
    ('apply_safe_new_tab', '''const link=J.applyLink(make('a'));return link.includes('target="_blank"')&&link.includes('rel="noopener noreferrer"')&&link.includes('https://example.test/job/a');''', True),
]


@pytest.mark.parametrize('name,code,expected',CASES,ids=[c[0] for c in CASES])
def test_browser_calculation(name,code,expected):
    result=evaluate(FIXTURE+code)
    if name=='seven_day_exact_eligibility':
        assert result['percentage']==pytest.approx(expected['percentage'])
        assert result['numerator']==expected['numerator'] and result['denominator']==expected['denominator']
    else:
        assert result==expected


def test_real_browser_data_reconciles_read_only():
    paths=[p for p in (ROOT/'data').rglob('*') if p.is_file()]
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    csv_text=(ROOT/'data/history.csv').read_text()
    status=json.loads((ROOT/'data/status.json').read_text())
    result=evaluate('const status='+json.dumps(status)+'; const rows=JW.historyRows('+json.dumps(csv_text)+''');
JW.validateData(status,rows);
return {open:rows.filter(r=>r.status==='open').length,newToday:JW.newToday(rows,JW.latestDate(status)).length,removedToday:JW.removedToday(rows,JW.latestDate(status)).length,sourceCounts:Object.fromEntries(status.sources.filter(s=>s.ok).map(s=>[s.name,rows.filter(r=>r.source===s.name&&r.status==='open'&&r.last_seen===JW.latestDate(status)).length]))};''')
    assert result['open']==status['open']
    assert result['newToday']==status['new_today'] and result['removedToday']==status['removed_today']
    assert {s['name'] for s in status['sources']}=={s.key for s in PRIMARY_SOURCES}
    # The current clean baseline has no unresolved malformed records. In later
    # snapshots, protected malformed IDs may legitimately exceed normalized count.
    for s in status['sources']:
        if s['ok']:
            assert result['sourceCounts'][s['name']]>=s['count']
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def test_js_syntax_service_worker_and_no_external_dependencies():
    for path in [*sorted((ROOT/'js').glob('*.js')),ROOT/'service-worker.js']:
        source=path.read_text()
        assert evaluate('new Function('+json.dumps(source)+'); return true;')
    css=(ROOT/'css/styles.css').read_text()
    assert 'prefers-reduced-motion' in css and ':focus-visible' in css
    assert '@import' not in css and 'fonts.googleapis' not in css
    common=(ROOT/'js/common.js').read_text()
    assert "register('service-worker.js')" in common and "cache:'no-store'" in common
    browse=(ROOT/'js/browse.js').read_text()
    assert 'const pageSize = 25' in browse and 'setTimeout(update,180)' in browse


@pytest.mark.parametrize('scenario',['offline','mismatched_update','storage_failure','shell_install'])
def test_service_worker_snapshot_lifecycle_without_network(scenario):
    setup = r'''
const stores = new Map(), events = {}, timers = [];
globalThis.self = globalThis;
self.registration = {scope:'https://example.test/job-watcher/'};
self.clients = {claim:async()=>{}}; self.skipWaiting = async()=>{};
self.addEventListener = (name,fn)=>{events[name]=fn;};
globalThis.importScripts = ()=>{};
globalThis.setTimeout = fn=>{timers.push(fn);return timers.length;};
globalThis.clearTimeout = ()=>{};
globalThis.AbortController = class {constructor(){this.signal={};} abort(){}};
globalThis.URL = class {constructor(value,base){this.href=value.startsWith('https://')?value:base+value.replace(/^\.\//,'');this.origin='https://example.test';this.pathname=this.href.slice(this.origin.length);}};
globalThis.Headers = class {constructor(value={}){this.map=value.map?{...value.map}:{...value};}set(k,v){this.map[k]=v;}get(k){return this.map[k]||null;}};
globalThis.Response = class {constructor(body,options={}){this.body=body;this.status=options.status||200;this.ok=this.status>=200&&this.status<300;this.headers=new Headers(options.headers);}clone(){return new Response(this.body,{status:this.status,headers:this.headers});}async text(){return this.body;}async json(){return JSON.parse(this.body);}};
let failWrite=false;
globalThis.caches={async open(name){if(!stores.has(name)) stores.set(name,new Map());const store=stores.get(name);return {async put(key,value){if(failWrite&&key.endsWith('history.csv'))throw Error('quota');store.set(key,value.clone());},async match(key){return store.get(key)?.clone();},async addAll(paths){for(const path of paths)store.set(path,new Response('shell'));}};},async keys(){return [...stores.keys()];},async delete(name){return stores.delete(name);}};
const status={run_time:'2026-11-14T12:00:00Z',first_run_date:'2026-11-14',days_with_success:1,open:1,new_today:0,removed_today:0,sources:[{name:'test',ok:true,count:1}]};
const csv=JW.columns.join(',')+'\n'+'test:a,test,a,Example Bank,Finance Analyst,Town,,,https://example.test/a,true,true,2026-11-14,2026-11-14,open,\n';
let online=true, mismatch=false;
globalThis.fetch=async url=>{if(!online)throw Error('offline');return new Response(String(url).endsWith('status.json')?JSON.stringify({...status,open:mismatch?2:1}):csv);};
'''
    checks = {
        'offline': '''await refreshPair();online=false;const result=await dataResponse('data/status.json');const got=await result.json();return [result.headers.get('X-Job-Watcher-Cache'),got.open,got.run_time];''',
        'mismatched_update': '''await refreshPair();mismatch=true;const result=await refreshPair();return [result.cached,(await result.responses[0].json()).open];''',
        'storage_failure': '''await refreshPair();failWrite=true;const fresh=await refreshPair();online=false;const fallback=await refreshPair();return [fresh.cached,fallback.cached,(await fallback.responses[0].json()).open];''',
        'shell_install': '''let promise;events.install({waitUntil:p=>{promise=p;}});await promise;const cache=await caches.open(VERSION);return [!!await cache.match(base+'browse.html'),!!await cache.match(base+'market.html'),!!await cache.match(base+'assets/icon-512.png')];''',
    }
    worker=(ROOT/'service-worker.js').read_text()
    code = 'return new Function('+json.dumps(setup+'\n'+worker+'\nreturn (async()=>{'+checks[scenario]+'})();')+')();'
    expected={'offline':['offline',1,'2026-11-14T12:00:00Z'],'mismatched_update':[True,1],'storage_failure':[False,True,1],'shell_install':[True,True,True]}
    assert evaluate(code)==expected[scenario]


@pytest.mark.parametrize('file,script',PAGES)
def test_page_initial_render_with_fixture_data_without_browser(file,script):
    tags=Elements(ROOT/file).tags
    ids=[a['id'] for _,a in tags if 'id' in a]
    counts=[a['data-count'] for _,a in tags if 'data-count' in a]
    assert len(ids)==len(set(ids)), 'Duplicate HTML IDs'
    status={'run_time':'2026-11-14T12:00:00Z','first_run_date':'2026-11-14','days_with_success':1,'open':1,'new_today':0,'removed_today':0,
            'sources':[{'name':s.key,'ok':True,'count':1 if s.key=='pnc' else 0} for s in PRIMARY_SOURCES]}
    fixture=FIXTURE+'''
const elements={};
function element(id){return {id,textContent:'',innerHTML:'',hidden:false,dataset:{},addEventListener(){},setAttribute(){},removeAttribute(){},focus(){},add(){}};}
'''+f'''for(const id of {json.dumps(ids)}) elements[id]=element(id);
const countNodes={json.dumps(counts)}.map(key=>({{...element(key),key}}));
globalThis.document={{body:{{dataset:{{page:{json.dumps(script)}}}}},getElementById(id){{if(!elements[id])throw Error('Missing HTML node '+id);return elements[id];}},querySelectorAll(selector){{if(selector.startsWith('[data-count='))return countNodes.filter(n=>selector.includes('"'+n.key+'"'));return [];}}}};
globalThis.window={{addEventListener(){{}},localStorage:{{getItem:()=>null,setItem(){{}}}}}};
globalThis.Option=function(label,value){{this.label=label;this.value=value;}};
if(elements.filters) elements.filters.elements=Object.fromEntries(Object.entries(J.defaultFilters()).map(([k,value])=>[k,{{value,add(){{}}}}]));
const status={json.dumps(status)};
J.loadData=async()=>({{status,rows:[make('pnc:one',{{source:'pnc',employer:'PNC',first_run:true,first_seen:latest}})],latest,cached:false}});
new Function({json.dumps((ROOT/'js'/f'{script}.js').read_text())})();
return (async()=>{{await Promise.resolve();await Promise.resolve();
if(elements['data-error'].hidden===false && elements['data-error'].textContent)throw Error(elements['data-error'].textContent);
return {{html:Object.fromEntries(Object.entries(elements).map(([id,node])=>[id,node.innerHTML])),text:Object.fromEntries(Object.entries(elements).map(([id,node])=>[id,node.textContent]))}};
}})();'''
    result=evaluate(fixture)
    if script=='today':
        assert result['html']['sources'].count('<article ')==15
        assert result['text']['health-count']=='15 / 15'
        assert 'No new postings' in result['html']['new-list']
    elif script=='browse':
        assert result['text']['match-count']=='1'
        assert result['html']['results'].count('<tr>')==1
        assert 'data-star=' in result['html']['results'] and 'View opening' in result['html']['results']
        assert 'BASELINE' in result['html']['results']
    else:
        assert result['text']['new-finding']=='No post-baseline additions have been observed yet.'
        assert 'PNC leads with 1' in result['text']['employer-finding']
        assert 'INSUFFICIENT POST-BASELINE REMOVALS' in result['html']['duration-chart']
        assert 'AWAITING MATURE OBSERVATIONS' in result['html']['share-chart']


def test_exact_three_pages_and_balanced_local_markup():
    assert sorted(p.name for p in ROOT.glob('*.html'))==['browse.html','index.html','market.html']
    void={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    class Balanced(HTMLParser):
        def __init__(self): super().__init__(); self.stack=[]
        def handle_starttag(self,tag,attrs):
            assert len([a[0] for a in attrs])==len(set(a[0] for a in attrs)), 'Duplicate attribute'
            if tag not in void: self.stack.append(tag)
        def handle_endtag(self,tag):
            assert self.stack and self.stack.pop()==tag, f'Misnested closing tag {tag}'
    for page,_ in PAGES:
        parser=Balanced(); parser.feed((ROOT/page).read_text()); assert not parser.stack
    import xml.etree.ElementTree as ET
    ET.parse(ROOT/'assets/favicon.svg')
    css=(ROOT/'css/styles.css').read_text()
    assert css.count('{')==css.count('}')


def test_history_state_and_dates_are_validated_before_charting():
    assert evaluate('''const csv=JW.columns.join(',')+'\\n'+
      'x,a,x,Example,Title,Town,,,https://example.test/x,true,false,2026-11-14,2026-11-13,open,\\n';
      try { JW.historyRows(csv); return false; } catch(e) { return true; }''')


def test_location_presentation_partitions_without_mutating_source_strings():
    result=evaluate(FIXTURE+'''const rows=[make('a',{location:' 2 Locations '}),make('b',{location:'2 Locations'}),make('c',{location:'3 locations'}),make('d',{location:'1 Location'}),make('e',{location:'Toronto, ON, CAN'}),make('f',{location:'  '}),make('gone',{status:'removed',location:'5 Locations'}),make('named',{location:'Building 2 Locations Office'})];
const before=JSON.stringify(rows);const result=J.locationPresentation(rows);return {...result,unchanged:before===JSON.stringify(rows)};''')
    assert result['unchanged']
    assert result['specific']==[{'label':'Building 2 Locations Office','value':1},{'label':'Toronto, ON, CAN','value':1}]
    assert result['summaries']==[{'label':'2 Locations','value':2},{'label':'1 Location','value':1},{'label':'3 locations','value':1}]
    assert (result['specificCount'],result['summaryCount'],result['missing'],result['total'])==(2,4,1,7)
    assert sum(x['value'] for x in result['specific'])+sum(x['value'] for x in result['summaries'])+result['missing']==result['total']


def test_location_presentation_only_summaries_or_empty_is_not_a_false_place():
    result=evaluate(FIXTURE+'''return [J.locationPresentation([make('a',{location:'2 Locations'}),make('b',{location:''})]),J.locationPresentation([])];''')
    assert result[0]['specific']==[] and result[0]['summaryCount']==1 and result[0]['missing']==1
    assert result[1]=={'specific':[],'summaries':[],'specificCount':0,'summaryCount':0,'missing':0,'total':0}


def test_location_presentation_reconciles_current_open_inventory_read_only():
    data=(ROOT/'data/history.csv').read_text()
    result=evaluate('const rows=JW.historyRows('+json.dumps(data)+');return JW.locationPresentation(rows);')
    status=json.loads((ROOT/'data/status.json').read_text())
    assert result['total']==status['open']
    assert result['specificCount']+result['summaryCount']+result['missing']==status['open']
    assert all(not re.fullmatch(r'\d+\s+locations?',x['label'],re.I) for x in result['specific'])


def test_chart_full_location_labels_and_responsive_time_series():
    result=evaluate('''const nodes={bars:{},line:{clientWidth:320}};globalThis.document={getElementById:id=>nodes[id]};
JW.charts.bars('bars',[{label:'A very long source-provided location, never rewritten <North>',value:20}],'Locations');
JW.charts.timeSeries('line',[{date:'2026-11-14',all:0,role:0},{date:'2026-11-15',all:43,role:2}],[{key:'all',label:'All postings'},{key:'role',label:'Your role'}],'New per day');
return {bars:nodes.bars.innerHTML,line:nodes.line.innerHTML};''')
    assert 'title="A very long source-provided location, never rewritten &lt;North&gt;"' in result['bars']
    assert 'class="ranking-bar"' in result['bars'] and 'View chart data' in result['bars']
    assert 'viewBox="0 0 320 260"' in result['line']
    assert '<strong>43</strong>' in result['line'] and '<strong>2</strong>' in result['line']


def test_editorial_design_keeps_required_content_without_faux_desktop_chrome():
    for page,_ in PAGES:
        html=(ROOT/page).read_text()
        assert 'SYS://' not in html and '.EXE' not in html and 'window-bar' not in html
    today=(ROOT/'index.html').read_text()
    assert 'The hiring market,' in today
    assert 'REMOVED TODAY' in today and 'does not necessarily mean the position was filled' in today
    market=(ROOT/'market.html').read_text()
    assert 'location-summaries' in market and 'location-missing' in market and 'location-accounting' in market
    assert 'Some employer boards provide location-count summaries rather than city names.' in market


def test_today_movement_feed_renders_dates_and_keeps_baseline_exclusion():
    tags=Elements(ROOT/'index.html').tags
    ids=[a['id'] for _,a in tags if 'id' in a]
    code=FIXTURE+'''
const nodes={};const controls={};
function node(id){return {innerHTML:'',textContent:'',hidden:false,addEventListener(){},removeAttribute(){},setAttribute(){},focus(){},querySelector(selector){return controls[id+selector]||(controls[id+selector]={focus(){}});}};}
'''+f'''for(const id of {json.dumps(ids)})nodes[id]=node(id);
globalThis.document={{body:{{dataset:{{page:'today'}}}},getElementById:id=>nodes[id],querySelectorAll:()=>[]}};
const sources={json.dumps([{'name':s.key,'ok':s.key!='pnc','count':0} for s in PRIMARY_SOURCES])};
J.loadData=async()=>({{latest,status:{{run_time:'2026-11-14T12:00:00Z',days_with_success:2,open:2,new_today:1,removed_today:1,sources}},rows:[make('new',{{title:'New Finance Analyst',first_seen:latest}}),make('baseline',{{title:'Baseline Analyst',first_run:true,first_seen:latest}}),make('removed',{{title:'Previous Analyst',first_run:true,status:'removed',removed_date:latest}})]}});
new Function({json.dumps((ROOT/'js/today.js').read_text())})();
return(async()=>{{await Promise.resolve();await Promise.resolve();return {{newHTML:nodes['new-list'].innerHTML,removedHTML:nodes['removed-list'].innerHTML,newCount:nodes['new-badge'].textContent,removedCount:nodes['removed-badge'].textContent,health:nodes['health-count'].textContent,status:nodes.sources.innerHTML,error:nodes['data-error'].textContent}};}})();'''
    result=evaluate(code)
    assert not result['error']
    assert result['newCount']=='1' and result['removedCount']=='1'
    assert 'New Finance Analyst' in result['newHTML'] and 'Baseline Analyst' not in result['newHTML']
    assert 'First seen 2026-11-14 UTC' in result['newHTML']
    assert 'Removed 2026-11-14 UTC' in result['removedHTML'] and 'Former listing' in result['removedHTML']
    assert result['health']=='14 / 15' and 'FAILED · latest run' in result['status']


@pytest.mark.parametrize('code,expected',[
    ('''return J.financeOpen([make('yes'),make('removed',{status:'removed'}),make('driver',{title:'OTR Driver',in_role:false}),make('not-classified-here',{title:'Financial Analyst',in_role:false}),make('field-is-authoritative',{title:'Example',in_role:true})]).map(r=>r.posting_id);''', ['yes','field-is-authoritative']),
    ('''return J.todayFeeds([make('new',{first_seen:latest,posted_date:'2020-01-01'}),make('baseline',{first_seen:latest,first_run:true}),make('driver',{first_seen:latest,in_role:false}),make('old',{posted_date:latest})],latest).added.map(r=>r.posting_id);''', ['new']),
    ('''return J.todayFeeds([make('baseline-removed',{status:'removed',removed_date:latest,first_run:true}),make('driver',{status:'removed',removed_date:latest,in_role:false}),make('earlier',{status:'removed',removed_date:'2026-11-13'})],latest).removed.map(r=>r.posting_id);''', ['baseline-removed']),
    ('''const rows=[make('finance',{first_seen:latest}),make('driver',{title:'OTR Driver',first_seen:latest,in_role:false})];return [J.todayFeeds(rows,latest).added.map(r=>r.posting_id),J.todayFeeds(rows,latest,'all').added.map(r=>r.posting_id)];''', [['finance'],['finance','driver']]),
])
def test_finance_focus_exact_definitions_and_all_feed_access(code,expected):
    assert evaluate(FIXTURE+code)==expected


def test_finance_focus_markup_defaults_and_assignment_totals():
    for name,field in [('index.html','feed_scope'),('browse.html','role')]:
        html=(ROOT/name).read_text();tree=Elements(ROOT/name)
        assert 'FINANCE &amp; BANKING' in html and 'ALL OPENINGS' in html
        assert any(tag=='input' and a.get('name')==field and a.get('value')=='role' and 'checked' in a for tag,a in tree.tags)
    html=(ROOT/'index.html').read_text()
    for name in ('days_with_success','open','new_today','removed_today'):
        assert f'data-count="{name}"' in html
    for name in ('open','new','removed'):
        assert f'data-relevant-count="{name}"' in html
    assert 'FINANCE &amp; BANKING OPPORTUNITIES' in html and 'ALL TRACKED OPENINGS' in html
    assert 'RELEVANT NEW TODAY' in html and 'RELEVANT REMOVED TODAY' in html


def test_today_feed_toggle_renders_non_role_jobs_without_changing_required_totals():
    ids=[a['id'] for _,a in Elements(ROOT/'index.html').tags if 'id' in a]
    code=FIXTURE+'''
const nodes={},handlers={},totals={},relevant={};
const fake=()=>({innerHTML:'',textContent:'',hidden:false,removeAttribute(){},focus(){},addEventListener(type,fn){handlers[type]=fn;},querySelector(){return {focus(){}};}});
'''+f'''for(const id of {json.dumps(ids)})nodes[id]=fake();
for(const key of ['open','new_today','removed_today','days_with_success'])totals[key]=fake();for(const key of ['open','new','removed'])relevant[key]=fake();
globalThis.document={{body:{{dataset:{{page:'today'}}}},getElementById:id=>nodes[id],querySelectorAll:selector=>{{const match=selector.match(/="([^"]+)"/);if(!match)return [];const map=selector.startsWith('[data-relevant-count=')?relevant:totals;return map[match[1]]?[map[match[1]]]:[];}}}};
const sources={json.dumps([{'name':s.key,'ok':True,'count':0} for s in PRIMARY_SOURCES])};
const rows=[make('new',{{title:'Finance Opportunity',first_seen:latest}}),make('driver',{{title:'OTR Driver',first_seen:latest,in_role:false}}),make('base',{{first_run:true,first_seen:latest}}),make('removed',{{status:'removed',removed_date:latest,first_run:true}}),make('removed-driver',{{title:'Previous Driver',status:'removed',removed_date:latest,in_role:false}})];
J.loadData=async()=>({{latest,rows,status:{{run_time:latest+'T12:00:00Z',days_with_success:2,open:3,new_today:2,removed_today:2,sources}}}});
new Function({json.dumps((ROOT/'js/today.js').read_text())})();
return(async()=>{{await Promise.resolve();await Promise.resolve();
const before={{newHTML:nodes['new-list'].innerHTML,removedHTML:nodes['removed-list'].innerHTML}};
handlers.change({{target:{{name:'feed_scope',value:'all'}}}});
const after={{newHTML:nodes['new-list'].innerHTML,removedHTML:nodes['removed-list'].innerHTML,summary:nodes['feed-summary'].textContent}};
handlers.change({{target:{{name:'feed_scope',value:'role'}}}});
return {{before,after,restored:nodes['new-list'].innerHTML,totals:Object.fromEntries(Object.entries(totals).map(([k,n])=>[k,n.textContent])),relevant:Object.fromEntries(Object.entries(relevant).map(([k,n])=>[k,n.textContent])),error:nodes['data-error'].textContent}};
}})();'''
    result=evaluate(code)
    assert not result['error']
    assert 'OTR Driver' not in result['before']['newHTML'] and 'Previous Driver' not in result['before']['removedHTML']
    assert 'OTR Driver' in result['after']['newHTML'] and 'Previous Driver' in result['after']['removedHTML']
    assert 'All tracked openings' in result['after']['summary'] and 'OTR Driver' not in result['restored']
    assert result['totals']=={'open':'3','new_today':'2','removed_today':'2','days_with_success':'2'}
    assert result['relevant']=={'open':'2','new':'1','removed':'1'}


def test_relevance_counts_reconcile_with_current_history_and_total_status():
    status=json.loads((ROOT/'data/status.json').read_text())
    with (ROOT/'data/history.csv').open(newline='') as f:
        rows=list(csv.DictReader(f))
    latest=status['run_time'][:10]
    expected={
        'open':sum(r['status']=='open' and r['in_role']=='true' for r in rows),
        'new':sum(r['first_seen']==latest and r['first_run']=='false' and r['in_role']=='true' for r in rows),
        'removed':sum(r['removed_date']==latest and r['in_role']=='true' for r in rows),
    }
    result=evaluate('const rows=JW.historyRows('+json.dumps((ROOT/'data/history.csv').read_text())+');const feed=JW.todayFeeds(rows,'+json.dumps(latest)+');return {open:JW.financeOpen(rows).length,new:feed.added.length,removed:feed.removed.length};')
    assert result==expected
    assert result['open']<=status['open'] and result['new']<=status['new_today'] and result['removed']<=status['removed_today']
