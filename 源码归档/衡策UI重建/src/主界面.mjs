import { icon } from './图标.mjs';
import { request, subscribe, isLive, canAnalyze } from './业务桥.mjs';
import { captureLayout, animateLayout, animateDialog, closeDialogMotion, installMotion } from './动效.mjs';
import { enhanceSelects, closeSelects, installSelects } from './下拉菜单.mjs';

const $ = (selector, root=document) => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = value => value == null ? '—' : (value/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
const wan = value => (value/1000000).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
const rate = value => value == null ? '—' : `${value>0?'+':''}${(value/100).toFixed(2)}%`;
const date = value => { const d=new Date(value); return Number.isNaN(+d)?'—':d.toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).replaceAll('/','.'); };
const time = value => new Date(value).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'});
const periodLabel = value => /-Q[1-4]$/.test(value)?`${value.slice(0,4)} 年第 ${value.slice(-1)} 季度`:`${value.slice(0,4)} 年 ${Number(value.slice(-2))} 月`;
const sum = (rows,key) => rows.reduce((a,r)=>a+(r[key]||0),0);
const btn = (action,text,ico='',cls='',extra='') => `<button class="btn ${cls}" data-action="${action}" ${extra}>${ico?icon(ico):''}${text}</button>`;
const riskNames={high:'高风险',watch:'关注',normal:'正常'};
const tag = (text,cls='neutral') => `<span class="tag ${esc(cls)}">${esc(text)}</span>`;
const pages={overview:['经营总览','overview'],data:['数据工作区','data'],analysis:['差异分析','chart'],risks:['风险与整改','risk'],organization:['组织部门','org'],reports:['报告中心','report'],history:['分析记录','history']};
const S={data:null,page:pages[location.hash.slice(1)]?location.hash.slice(1):'overview',entity:'all',module:'全部',risk:'all',search:'',sort:'variance',ascending:false,ai:false,messages:[],access:false,askRow:null,asking:false,draft:'',busy:false,progress:'',navOpen:false,selectedReport:null};
const embedded=new URLSearchParams(location.search).get('embedded')==='1';
let modalReturn=null, modalReturnHint=null, modalSubmit=null;

function currentRows(){ return S.data.rows.filter(r=>S.entity==='all'||r.departmentId===S.entity); }
function visibleRows(){return currentRows().filter(r=>(S.module==='全部'||r.module===S.module)&&(S.risk==='all'||r.risk===S.risk)&&(!S.search||`${r.subject}${r.department}${r.module}`.toLowerCase().includes(S.search.toLowerCase()))).sort((a,b)=>{const av=S.sort==='variance'?Math.abs(a.variance):a[S.sort],bv=S.sort==='variance'?Math.abs(b.variance):b[S.sort];return (av-bv)*(S.ascending?1:-1);});}
function riskTag(row){
  const name=row.tierName||riskNames[row.risk];
  const color=row.tierColor;
  return /^#[0-9a-f]{6}$/i.test(color||'')?`<span class="tag" style="color:${color};background:${color}12">${esc(name)}</span>`:tag(name,row.risk);
}
function entityName(){return S.data.entities.find(e=>e.id===S.entity)?.name||'全部部门';}
function metrics(rows=currentRows()){
  const revenue=rows.filter(r=>r.module==='收入'),cost=rows.filter(r=>r.module==='成本'),expense=rows.filter(r=>r.module==='费用');
  return {budget:sum(revenue,'budget'),revenue:sum(revenue,'actual'),cost:sum(cost,'actual'),expense:sum(expense,'actual'),profit:sum(revenue,'actual')-sum(cost,'actual')-sum(expense,'actual'),risk:rows.filter(r=>r.risk!=='normal').length};
}
function isReady(){return S.data.rows?.length && ['预算基础','实时经营'].every(c=>S.data.files.some(f=>f.category===c&&f.status==='valid'));}
function toast(message,error=false){const el=document.createElement('div');el.className=`toast ${error?'error':''}`;el.innerHTML=`${icon(error?'risk':'circleCheck')}<span>${esc(message)}</span>`;$('#toasts').append(el);setTimeout(()=>el.remove(),6500);}
function navigate(page){S.page=page;S.navOpen=false;S.search='';S.risk='all';S.module='全部';location.hash=page;render();$('#main')?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
function syncNavigation(){
  const mobile=!embedded&&window.matchMedia('(max-width:760px)').matches;
  const sidebar=$('#main-navigation'),workspace=$('.workspace');
  if(sidebar)sidebar.inert=embedded||(mobile&&!S.navOpen);
  if(workspace)workspace.inert=mobile&&S.navOpen;
  document.body.classList.toggle('navigation-open',mobile&&S.navOpen);
}
function setNavigation(open){
  S.navOpen=open;render();
  const target=open?$('.sidebar .nav-item.active'):$('.mobile-menu');
  target?.focus({preventScroll:true});
}
function acceptData(data){if(!data||data.schemaVersion!=='1.0'||!Array.isArray(data.rows)||!Array.isArray(data.files))throw new Error('收到的工作区数据不符合接口约定。');S.data=data;if(!data.entities.some(e=>e.id===S.entity))S.entity='all';}
async function mutate(action,payload,message){const data=await request(action,payload);acceptData(data);render();if(message)toast(message);return data;}

function shell(){
  const riskCount=S.data.rows.filter(r=>r.risk!=='normal').length;
  return `<div class="shell ${embedded?'embedded':''} ${S.navOpen?'nav-open':''}">
    <button class="nav-scrim" data-action="close-menu" type="button" aria-label="关闭导航" tabindex="-1" ${S.navOpen?'':'hidden'}></button>
    <aside class="sidebar" id="main-navigation" aria-label="主导航">
      <a class="brand" href="#overview" data-action="nav" data-page="overview" aria-label="衡策经营总览"><img src="./标识.svg" alt=""><div><div class="brand-name">衡策</div><div class="brand-caption">经营分析工作台</div></div></a>
      <div class="workspace-switch">${icon('building')}<div class="grow"><strong>${esc(S.data.meta.company.replace('有限公司',''))}</strong><small>企业经营空间</small></div></div>
      <div class="nav-label">工作台</div>
      <nav>${Object.entries(pages).map(([key,[label,ico]],i)=>`${i===5?'<div class="nav-divider"></div><div class="nav-label">成果与记录</div>':''}<button class="nav-item ${S.page===key?'active':''}" data-action="nav" data-page="${key}" ${S.page===key?'aria-current="page"':''}>${icon(ico)}<span>${label}</span>${key==='risks'&&riskCount?`<span class="count">${riskCount}</span>`:''}</button>`).join('')}</nav>
      <div class="sidebar-bottom"><button class="nav-item" data-action="settings">${icon('settings')}分析设置</button><button class="nav-item" data-action="help">${icon('help')}使用帮助</button><div class="connection"><span class="dot ${!isLive?'demo':''}"></span>${isLive?'已连接衡策插件':'演示工作区'}<span class="grow"></span><span>UI 2.0</span></div></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><button class="icon-btn mobile-menu" data-action="menu" aria-label="${S.navOpen?'收起导航':'展开导航'}" aria-expanded="${S.navOpen}" aria-controls="main-navigation">${icon('menu')}</button><div class="breadcrumb"><strong>${esc(S.data.meta.company.replace('有限公司',''))}</strong>${icon('chevron')}<select id="entity-select" class="topbar-select" aria-label="选择分析部门">${S.data.entities.map(e=>`<option value="${esc(e.id)}" ${e.id===S.entity?'selected':''}>${esc(e.name)}</option>`).join('')}</select><span class="scenario">${esc(S.data.meta.scenario)}</span></div><div class="topbar-right">${!isLive?'<span class="demo-tag" title="所有数据均为虚构演示；尚未连接真实分析后端">演示模式</span>':tag('已连接','normal')}<span class="pill-select">${icon('clock')}<span class="small">${esc(S.data.meta.period)}</span></span>${btn('assistant',`<span class="assistant-label">衡策助手</span>`,'spark',S.ai?'primary':'')}<span class="avatar" title="当前企业工作区">恒</span></div>${S.busy?'<div class="loading-strip" role="progressbar" aria-label="正在执行分析"></div>':''}</header>
      ${embedded?`<nav class="embedded-nav" aria-label="衡策业务导航">${Object.entries(pages).map(([key,[label,ico]])=>`<button class="tab ${S.page===key?'active':''}" data-action="nav" data-page="${key}">${icon(ico)}${label}</button>`).join('')}<button class="tab" data-action="settings">${icon('settings')}分析设置</button></nav>`:''}
      <div class="content-layout"><main class="main" id="main" data-page="${S.page}" tabindex="-1">${pageContent()}</main>${S.ai?assistant():''}</div>
    </div></div><input id="file-input" type="file" accept=".xlsx" multiple hidden>`;
}
function heading(title,description,actions=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${description}</p></div>${actions?`<div class="heading-actions">${actions}</div>`:''}</div>`;}
function standardActions(){return `${btn('import','导入数据','upload')}${btn('run',S.busy?'正在分析':'运行分析',S.busy?'':'play','primary',S.busy?'disabled':'')}`;}
function pageContent(){
  const renderers={overview,analysis:analysisPage,data:dataPage,risks:riskPage,organization:organizationPage,reports:reportsPage,history:historyPage};
  const pending=S.data.files.some(f=>f.status==='pending');
  const warnings=(S.data.warnings||[]).map(w=>typeof w==='string'?w:w.message||JSON.stringify(w));
  return `${S.busy?`<div class="notice info"><span class="spinner"></span><span>${esc(S.progress||'正在分析，请稍候…')}</span></div>`:''}${S.data.dirty?`<div class="notice">${icon('risk')}<span>${pending?'本地文件待校验。当前结果仍为上次分析，接入后端后可校验这些文件。':'数据或设置已变更，当前展示上次分析结果。重新分析后更新报告。'}</span>${btn('run','重新分析','','small',S.busy?'disabled':'')}</div>`:''}${warnings.length?`<div class="notice">${icon('risk')}<details><summary>${warnings.length} 条分析提示</summary>${warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details></div>`:''}${renderers[S.page]()}<div class="footer-note">${icon('lock')}<span>${isLive?'金额计算由衡策插件完成':'当前为虚构演示数据，所有操作仅在本次预览生效'} · 金额以人民币展示</span></div>`;
}
function summary(){
  const m=metrics(),delta=m.revenue-m.budget;
  const ids=new Set(currentRows().map(r=>r.id)),scopedActions=S.data.actions.filter(a=>ids.has(a.rowId));
  const done=scopedActions.filter(a=>a.status==='done').length;
  return `<section class="summary-strip" aria-label="核心经营指标">
    <div class="metric"><div class="metric-label">本期营业收入${icon('chart')}</div><div class="metric-number">${wan(m.revenue)}<small>万元</small></div><div class="metric-foot"><span class="${delta>=0?'positive':'negative'}">${delta>=0?'↑':'↓'} ${Math.abs(m.budget?delta/m.budget*100:0).toFixed(2)}%</span><span>较预算 ${wan(m.budget)} 万</span></div></div>
    <div class="metric"><div class="metric-label">本期成本与费用${icon('data')}</div><div class="metric-number">${wan(m.cost+m.expense)}<small>万元</small></div><div class="metric-foot">成本 ${wan(m.cost)} · 费用 ${wan(m.expense)}</div></div>
    <div class="metric"><div class="metric-label">经营结余${icon('overview')}</div><div class="metric-number ${m.profit<0?'negative':''}">${wan(m.profit)}<small>万元</small></div><div class="metric-foot">收入 − 成本 − 费用</div></div>
    <div class="metric"><div class="metric-label">需关注差异${icon('flag')}</div><div class="metric-number">${m.risk}<small>项</small></div><div class="metric-foot"><span class="negative">${currentRows().filter(r=>r.risk==='high').length} 项高风险</span><span>· 整改完成 ${done}/${scopedActions.length}</span></div></div>
  </section>`;
}
function empty(title='准备好数据，开始本期分析',description='导入预算基础与实时经营工作簿，衡策会为你整理差异与风险。'){return `<div class="panel empty-state">${icon('chart')}<h2>${title}</h2><p>${description}</p><div class="actions-inline">${btn('import','导入数据','upload','primary')}${!isLive?btn('reset-demo','载入演示数据','refresh'):''}</div></div>`;}
function overview(){
  if(!isReady())return heading('经营总览','从预算与实际之间，找到经营变化的原因。',standardActions())+empty();
  const risks=currentRows().filter(r=>r.risk!=='normal').sort((a,b)=>Math.abs(b.variance)-Math.abs(a.variance));
  return `${heading('经营总览',`${esc(periodLabel(S.data.meta.period))} · ${esc(entityName())} · 更新于 ${date(S.data.meta.generatedAt)} ${time(S.data.meta.generatedAt)}`,standardActions())}${summary()}
  <div class="overview-grid"><section class="panel"><div class="panel-head"><div><h2>收入与预算走势</h2><p class="meta">${S.entity==='all'?'全公司年度口径':'全公司年度趋势；当前部门明细见下表'}</p></div><span class="right tag neutral">${esc(S.data.meta.period.slice(0,4))} 年</span></div>${trendChart()}</section>
  <section class="panel"><div class="panel-head"><div><h2>本期待处理</h2><p class="meta">先关注对经营影响最大的差异</p></div><button class="text-btn" data-action="nav" data-page="risks">全部 ${icon('chevron')}</button></div><div class="risk-list">${risks.slice(0,3).map(r=>`<div class="risk-row"><div class="risk-marker ${esc(r.risk)}">${icon(r.risk==='high'?'flag':'clock')}</div><div class="grow"><h3><button class="subject-button text-btn" style="color:inherit;font-size:12px" data-action="detail" data-id="${esc(r.id)}">${esc(r.subject)}</button></h3><p>${esc(r.department)} · ${esc(r.decision)}</p></div><div style="text-align:right">${tag(rate(r.rate),r.risk)}<p style="font-size:10px;color:var(--muted);margin-top:6px">${r.direction==='favorable'?'有利':'不利'}差异</p></div></div>`).join('')||'<div class="empty-column">本期没有触发预警的差异</div>'}</div><div class="risk-footer">${icon('spark')}选中差异，可让衡策助手解释原因 ${icon('arrow')}</div></section></div>
  <section class="panel"><div class="panel-head"><div><h2>差异明细</h2><p class="meta">预算与实际对照，按差额绝对值排序</p></div><button class="text-btn" data-action="nav" data-page="analysis">查看全部明细 ${icon('chevron')}</button></div>${tableSection(true)}</section>`;
}
function trendChart(){
  const data=S.data.trend||[],W=680,H=246,left=48,right=22,top=22,bottom=38;
  const values=data.flatMap(t=>[t.budget,t.actual,t.rolling]).filter(Number.isFinite);
  if(!data.length||!values.length)return `<div class="empty-state" style="padding:48px 24px">${icon('chart')}<h2>暂无趋势数据</h2><p>收到当前分析的期间序列后，收入趋势会显示在这里。</p></div>`;
  const max=Math.max(400000000,Math.ceil(Math.max(...values)/400000000)*400000000),min=Math.min(0,...values);
  const x=i=>left+i*(W-left-right)/Math.max(1,data.length-1),y=v=>top+(max-v)/(max-min)*(H-top-bottom);
  const path=key=>data.map((t,i)=>!Number.isFinite(t[key])?'':`${i===0||!Number.isFinite(data[i-1]?.[key])?'M':'L'}${x(i)},${y(t[key])}`).join(' ');
  const last=data.findLastIndex(t=>Number.isFinite(t.actual)),actualPath=path('actual');
  let area='',segment=[];
  const flush=()=>{if(segment.length){area+=segment.map((i,j)=>`${j?'L':'M'}${x(i)},${y(data[i].actual)}`).join(' ')+` L${x(segment.at(-1))},${y(0)} L${x(segment[0])},${y(0)}Z `;segment=[];}};
  data.forEach((t,i)=>{if(Number.isFinite(t.actual))segment.push(i);else flush();});flush();
  let forecast=path('rolling');
  if(last>=0&&Number.isFinite(data[last+1]?.rolling))forecast=`M${x(last)},${y(data[last].actual)} L${x(last+1)},${y(data[last+1].rolling)} `+forecast;
  const forecastStart=last>=0?last+1:data.findIndex(t=>Number.isFinite(t.rolling));
  const label=period=>period.includes('Q')?period.split('-')[1]:`${Number(period.slice(-2))}月`;
  return `<div class="legend trend-legend"><span><i></i>实际收入</span><span><i class="budget"></i>原始预算</span><span><i class="rolling"></i>滚动预测</span></div><div class="panel-body" style="padding-bottom:0"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="收入趋势。实线为实际收入，虚线为预算和滚动预测；下方可查看完整数据表。"><defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2864e7" stop-opacity=".12"/><stop offset="100%" stop-color="#2864e7" stop-opacity="0"/></linearGradient></defs>${forecastStart>=0&&forecastStart<data.length?`<rect x="${x(forecastStart)-12}" y="${top}" width="${Math.max(0,W-right-x(forecastStart)+12)}" height="${H-top-bottom}" fill="#fafbfd"/><text x="${x(forecastStart)}" y="${top+12}" style="font-size:9px">滚动预测</text>`:''}${[0,1,2,3,4].map(i=>{const v=min+(max-min)*i/4;return `<line class="grid" x1="${left}" x2="${W-right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left-12}" y="${y(v)+3}" text-anchor="end">${(v/1000000).toLocaleString()}</text>`;}).join('')}<text x="${left}" y="10" style="font-size:9px">万元</text><path d="${area}" fill="url(#area-fill)"/><path d="${path('budget')}" fill="none" stroke="#adbbcf" stroke-width="1.8" stroke-dasharray="4 5"/><path d="${forecast}" fill="none" stroke="#5b9caa" stroke-width="2" stroke-dasharray="4 5"/><path d="${actualPath}" fill="none" stroke="#2864e7" stroke-width="2.5" stroke-linejoin="round"/>${data.map((t,i)=>`<text x="${x(i)}" y="${H-14}" text-anchor="middle">${esc(label(t.period))}</text>${Number.isFinite(t.actual)?`<g class="chart-point" tabindex="0" data-action="trend-detail" data-index="${i}" role="button" aria-label="${esc(t.period)}实际收入${money(t.actual)}元，查看数据"><circle cx="${x(i)}" cy="${y(t.actual)}" r="3.5" fill="white" stroke="#2864e7" stroke-width="2"/><title>${esc(t.period)}：预算 ${money(t.budget)} 元；实际 ${money(t.actual)} 元</title></g>`:''}`).join('')}</svg></div><div class="chart-foot"><span>${last>=0?`截至 ${esc(data[last].period)} 已结账`:'尚无已结账实际数据'} · 预测不计入实际发生额</span><button class="text-btn" data-action="trend-detail">查看数据表 ${icon('chevron')}</button></div>`;
}
function tableSection(compact=false){return `<div class="tabs" aria-label="模块筛选">${['全部','收入','成本','费用','采购'].map(name=>`<button class="tab ${S.module===name?'active':''}" data-action="module" data-value="${name}" aria-pressed="${S.module===name}">${name}${name==='全部'?`<span class="tab-count">${currentRows().length}</span>`:''}</button>`).join('')}</div><div class="table-tools"><label class="search-field">${icon('search')}<input id="row-search" type="search" placeholder="搜索科目或部门" value="${esc(S.search)}" aria-label="搜索科目或部门"></label><select class="filter-select" id="risk-filter" aria-label="筛选预警等级">${[['all','全部预警等级'],['high','高风险'],['watch','关注'],['normal','正常']].map(([v,n])=>`<option value="${v}" ${S.risk===v?'selected':''}>${n}</option>`).join('')}</select><div class="right"><span class="small muted">单位：元</span>${!compact?btn('export-table','导出明细','download','small'):''}</div></div><div id="variance-table">${varianceTable(compact)}</div>`;}
function varianceTable(compact=false){const all=visibleRows(),rows=compact?all.slice(0,5):all;return `<div class="table-scroll"><table><thead><tr><th>科目 / 所属部门</th><th>模块</th><th class="numeric">预算金额</th><th class="numeric">实际金额</th><th class="numeric"><button class="sort-button" data-action="sort">差额 ${icon(S.ascending?'up':'down')}</button></th><th class="numeric">差异率</th><th>预警</th><th style="width:48px"></th></tr></thead><tbody>${rows.map(r=>`<tr><td><button class="subject-button" data-action="detail" data-id="${esc(r.id)}">${esc(r.subject)}</button><span class="sub">${esc(r.department)}</span></td><td><span class="module-dot"></span>${esc(r.module)}</td><td class="numeric">${money(r.budget)}</td><td class="numeric">${money(r.actual)}</td><td class="numeric ${r.direction==='favorable'?'positive':'negative'}">${r.variance>0?'+':''}${money(r.variance)}</td><td class="numeric ${r.direction==='favorable'?'positive':'negative'}">${rate(r.rate)}</td><td>${riskTag(r)}</td><td><button class="icon-btn" data-action="detail" data-id="${esc(r.id)}" aria-label="查看${esc(r.subject)}详情">${icon('chevron')}</button></td></tr>`).join('')||'<tr><td colspan="8" style="text-align:center;padding:40px;color:var(--muted)">没有符合条件的科目。试试其他关键词或预警等级。</td></tr>'}</tbody></table></div><div class="table-bottom"><span>显示 ${rows.length} / ${all.length} 项差异</span><span>绿：有利 · 红：不利 · 差额 = 实际 − 预算</span></div>`;}
function analysisPage(){return `${heading('差异分析','沿着科目与部门下钻，找到每一笔偏差的来源。',`${btn('settings','分析设置','settings')}${standardActions()}`)}${isReady()?`${summary()}<section class="panel">${tableSection()}</section><div class="section-spacer panel"><div class="panel-head"><h2>经营指标</h2><span class="small muted">${S.entity==='all'?'全公司口径':'指标仍为全公司口径'}</span></div><div class="panel-body"><div class="form-grid">${S.data.kpis.map(k=>`<div class="source-box" style="margin:0"><div class="small">${esc(k.name)}</div><strong class="num" style="font-size:22px;color:var(--ink)">${k.value==null?'待补充':`${(k.value/100).toFixed(2)}%`}</strong><p class="small muted">${esc(k.note)}</p></div>`).join('')}</div><p class="inline-help spacer-top">BSC 评分与价量拆分在相应输入完整后展示，缺失数据不会记为零。</p></div></div>`:empty()}`;}
function dataPage(){
  const categories=[['预算基础','全年预算是所有分析的起点。','必需'],['实时经营','已结账期间的实际经营数据。','必需'],['行业对标','为行业修正提供可核对的参考。','选填'],['经营变更','记录影响预算假设的经营事项。','选填']];
  return `${heading('数据工作区','按主体与情景整理工作簿，校验通过后开始分析。',`${!isLive?btn('reset-demo','载入演示数据','refresh'):''}${btn('import','导入工作簿','plus','primary')}`)}<div class="data-completeness">${icon(canAnalyze(S.data)?'circleCheck':'clock')}<div class="grow"><h2>${canAnalyze(S.data)?'分析所需的两类数据已就绪':'准备本次分析的数据'}</h2><p>${S.data.files.filter(f=>f.status==='valid').length} 份工作簿校验通过${S.data.files.some(f=>f.status==='pending')?' · 有本地文件待校验':''}</p></div>${btn('run','开始分析','play','',S.busy?'disabled':'')}</div><div class="data-grid">${categories.map(([name,description,required])=>{const files=S.data.files.filter(f=>f.category===name),valid=files.filter(f=>f.status==='valid');return `<section class="data-card"><div class="data-card-top"><div class="file-symbol">${icon('file')}</div><div class="grow"><h2>${name}</h2><p>${description}</p></div>${tag(required,required==='必需'?'blue':'neutral')}</div><p>${valid.length?`${icon('circleCheck')} <span class="positive">已校验 ${valid.length} 份</span> · ${valid.reduce((a,f)=>a+f.rows,0)} 行数据`:'尚无校验通过的文件'}</p><div class="data-actions">${btn('choose-files',files.length?'追加工作簿':'选择工作簿','plus','small',`data-category="${name}"`)}<button class="text-btn" data-action="template" data-category="${name}">${icon('download')}空白模板</button></div></section>`;}).join('')}</div><div class="dropzone" id="dropzone">${icon('upload')}<strong>拖拽工作簿到这里</strong>，或<button class="text-btn" data-action="choose-files">选择文件</button><p class="small" style="margin-top:8px">支持四类标准 .xlsx 工作簿，单文件不超过 28 MB</p></div><section class="panel"><div class="panel-head"><h2>本次工作簿</h2><span class="small muted">${S.data.files.length} 份文件</span></div><div class="table-scroll"><table><thead><tr><th>文件名</th><th>数据类别</th><th>校验状态</th><th>数据行数</th><th></th></tr></thead><tbody>${S.data.files.map(f=>`<tr><td><div class="file-name">${icon('file')}<div>${esc(f.name)}<span class="sub">${esc(f.entity)} · ${typeof f.size==='number'?`${(f.size/1024).toFixed(1)} KB`:esc(f.size)}</span></div></div></td><td>${esc(f.category)}</td><td>${tag(f.status==='valid'?`${f.checks} 项通过`:'待校验',f.status==='valid'?'normal':'watch')}</td><td class="num">${f.status==='valid'?f.rows:'—'}</td><td><div class="actions-inline"><button class="text-btn" data-action="file-detail" data-id="${esc(f.id)}">详情</button><button class="icon-btn" data-action="remove-file" data-id="${esc(f.id)}" aria-label="移除${esc(f.name)}">${icon('trash')}</button></div></td></tr>`).join('')||'<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--muted)">还没有导入工作簿</td></tr>'}</tbody></table></div></section><section class="panel background-box"><div class="panel-head"><h2>本期经营背景</h2>${tag(S.data.background.changeStatus==='yes'?'有经营变更':S.data.background.changeStatus==='none'?'无经营变更':'待确认')}</div><div class="panel-body"><p>${esc(S.data.background.text||'补充宏观环境或特殊事项，帮助理解本期经营变化。背景说明不替代经营变更台账。')}</p>${btn('background','编辑背景','settings')}</div></section>`;
}
function riskPage(){
  const relatedIds=new Set(currentRows().map(r=>r.id)),actions=S.data.actions.filter(a=>relatedIds.has(a.rowId));
  return `${heading('风险与整改','从发现问题到跟踪处理，让每项差异有下一步。',btn('revision-log','修订记录','history'))}<div class="risk-summary">${[['high','高风险差异','优先核对业务影响'],['watch','需关注差异','持续追踪执行偏差'],['done','已完成整改','效果在下期分析中复核']].map(([key,label,note])=>`<div class="risk-summary-item"><div><h3>${label}</h3><p>${note}</p></div><span class="num ${key==='done'?'positive':key==='high'?'negative':'warning'}">${key==='done'?actions.filter(a=>a.status==='done').length:currentRows().filter(r=>r.risk===key).length}</span></div>`).join('')}</div><div class="tasks">${[['pending','待处理'],['doing','进行中'],['done','已完成']].map(([status,label])=>{const items=actions.filter(a=>a.status===status);return `<section class="task-column"><div class="column-head"><span class="dot" style="background:${status==='pending'?'#a8b5c7':status==='doing'?'var(--blue)':'var(--green)'}"></span><strong>${label}</strong><span>${items.length}</span></div>${items.map(a=>`<article class="task-card">${tag(a.type==='revision'?'预算假设修订':'执行偏差整改',a.type==='revision'?'high':'blue')}<h3>${esc(a.title)}</h3><p>${esc(a.description)}</p><div class="task-meta"><span class="avatar">${esc(a.owner.slice(-1))}</span><span>${esc(a.owner)}</span><span class="grow"></span><span>${a.due.slice(5).replace('-','/')} 截止</span></div>${btn('task-detail','查看处理事项','arrow','small',`data-id="${esc(a.id)}"`)}</article>`).join('')||'<div class="empty-column">暂无事项</div>'}</section>`;}).join('')}</div><section class="panel section-spacer"><div class="panel-head"><h2>纠错判定</h2><span class="small muted">单双环判定与人工修订</span></div><div class="table-scroll"><table><thead><tr><th>科目</th><th>纠错判定</th><th>预警</th><th>处理</th></tr></thead><tbody>${currentRows().filter(r=>r.risk!=='normal').map(r=>`<tr><td>${esc(r.subject)}<span class="sub">${esc(r.department)}</span></td><td>${tag(r.decision,r.decision==='双环纠错'?'high':'blue')}</td><td>${riskTag(r)}</td><td>${btn(r.decision==='双环纠错'?'revise':'detail',r.decision==='双环纠错'?'提请预算修订':'查看判定依据','','small',`data-id="${esc(r.id)}"`)}</td></tr>`).join('')||'<tr><td colspan="4" style="text-align:center;padding:32px">当前没有需要处理的预警</td></tr>'}</tbody></table></div></section>`;
}
function organizationPage(){
  const deps=S.data.entities.filter(e=>e.id!=='all'),max=Math.max(...deps.map(e=>sum(S.data.rows.filter(r=>r.departmentId===e.id),'actual')));
  return `${heading('组织部门','统一口径看全局，深入部门看执行。',btn('run-all','分析全部部门','play','primary',S.busy?'disabled':''))}<div class="department-list">${deps.map(e=>{const rows=S.data.rows.filter(r=>r.departmentId===e.id),m=metrics(rows);return `<section class="dept-card"><div class="dept-header"><div class="dept-avatar">${icon('org')}</div><div class="grow"><h2>${esc(e.name)}</h2><p>${rows.length} 个分析科目</p></div>${tag(`${m.risk} 项预警`,m.risk?'watch':'normal')}</div><div class="small muted">收入实际发生额</div><div class="dept-value num">${wan(m.revenue)} <span class="small muted">万元</span></div><div class="small muted">预算 ${wan(m.budget)} 万元</div><div class="dept-bars">${['收入','成本','费用','采购'].map(module=>{const value=sum(rows.filter(r=>r.module===module),'actual');return `<div class="dept-bar"><span>${module}</span><div class="progress-track"><span style="width:${value/(max||1)*100}%"></span></div><span class="num">${wan(value)} 万</span></div>`;}).join('')}</div>${btn('department','进入部门分析','arrow','small',`data-id="${esc(e.id)}"`)}</section>`;}).join('')}</div><section class="panel"><div class="panel-head"><h2>部门差异影响</h2><span class="small muted">各科目差额绝对值合计；含独立采购视角</span></div><div class="panel-body">${deps.map(e=>({e,value:S.data.rows.filter(r=>r.departmentId===e.id).reduce((a,r)=>a+Math.abs(r.variance),0)})).sort((a,b)=>b.value-a.value).map(({e,value},i,all)=>`<div class="ranking"><span class="num">0${i+1}</span><strong class="grow">${esc(e.name)}</strong><div class="progress-track"><span style="width:${value/(all[0].value||1)*100}%"></span></div><span class="num">${wan(value)} 万元</span><button class="icon-btn" data-action="department" data-id="${esc(e.id)}" aria-label="查看${esc(e.name)}">${icon('chevron')}</button></div>`).join('')}</div></section>`;
}
function reportsPage(){return `${heading('报告中心','把分析结果、经营解读与处理记录，整理成一份报告。',btn('generate-report','生成本期报告','plus','primary',S.busy?'disabled':''))}<section class="report-feature"><div class="report-cover"><div class="paper-mini"><div class="brand-line"><img src="./标识.svg" alt="">衡策</div><h3>经营分析<br>月度报告</h3><p>${esc(S.data.meta.period)} / ${esc(S.data.meta.company.replace('有限公司',''))}</p><div class="cover-chart">${[12,18,15,23,20,30,25].map(h=>`<i style="height:${h}px"></i>`).join('')}</div><div class="paper-line"></div><div class="paper-line short"></div></div></div><div class="report-description"><div>${tag('本期成果','blue')} ${!isLive?tag('演示报告','watch'):''}</div><h2>${esc(periodLabel(S.data.meta.period))}经营分析报告</h2><p>汇总预算执行情况、关键差异与风险，附上可追溯的明细和整改记录。AI 解读在获得数据访问授权后加入。</p><div class="report-checks"><span>${icon('check')}预算执行</span><span>${icon('check')}差异与预警</span><span>${icon('check')}整改记录</span></div>${btn('preview-report','预览本期报告','eye','',`data-id="${esc(S.data.reports.find(r=>r.period===S.data.meta.period)?.id||'current')}"`)}</div></section><section class="panel"><div class="panel-head"><h2>已生成的报告</h2><span class="small muted">${S.data.reports.length} 份</span></div><div class="table-scroll"><table><thead><tr><th>报告名称</th><th>生成时间</th><th>状态</th><th>操作</th></tr></thead><tbody>${S.data.reports.map(r=>`<tr><td><div class="file-name">${icon('report')}<div>${esc(r.title)}<span class="sub">${esc(r.period)} · ${!isLive?'演示数据':'正式分析结果'}</span></div></div></td><td>${date(r.createdAt)} ${time(r.createdAt)}</td><td>${tag('已生成','normal')}</td><td><div class="actions-inline">${btn('preview-report','预览','eye','small',`data-id="${esc(r.id)}"`)}${btn('export-report','导出','download','small',`data-id="${esc(r.id)}"`)}</div></td></tr>`).join('')||'<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--muted)">尚未生成报告</td></tr>'}</tbody></table></div></section>`;}
function historyPage(){return `${heading('分析记录','保留每次分析的时间与口径，随时回到当时的结果。')}<section class="panel"><div class="panel-head"><h2>已完成的分析</h2><span class="small muted">${S.data.history.length} 次</span></div><div class="timeline">${S.data.history.map(h=>`<div class="timeline-entry"><div class="timeline-date">${date(h.createdAt)}<p style="margin-top:5px">${time(h.createdAt)}</p></div><div class="timeline-symbol">${icon('check')}</div><div class="grow"><h3>${esc(h.period)} 经营分析</h3><p>${esc(h.company)} · ${h.riskCount} 项需关注差异 ${!isLive?'· 演示快照':''}</p></div>${btn('open-history','查看结果','arrow','small',`data-id="${esc(h.id)}"`)}</div>`).join('')||'<div class="empty-state"><p>运行首次分析后，记录会显示在这里。</p></div>'}</div></section>`;}
function assistant(){const row=S.data.rows.find(r=>r.id===S.askRow);return `<aside class="assistant" aria-label="衡策助手"><div class="assistant-head">${icon('spark')}<div><h2>衡策助手</h2><p>${isLive?'基于当前分析上下文':'演示对话 · 未连接真实模型'}</p></div><button class="icon-btn" data-action="assistant" aria-label="关闭助手">${icon('close')}</button></div><div class="assistant-context">当前上下文：${esc(entityName())} / ${esc(S.data.meta.period)}${row?`<br>关注科目：${esc(row.subject)}`:''}</div><div class="assistant-log" id="assistant-log">${S.messages.length?S.messages.map(m=>`<div class="chat-message ${m.role}">${esc(m.text)}${m.sources?.length?`<div class="sources">${m.sources.map(s=>`${icon('link')} ${esc(s.title)}<br>${esc(s.excerpt)}`).join('<br>')}</div>`:''}</div>`).join(''):`<div class="assistant-welcome"><h3>一起看清<br>数字背后的原因。</h3><p>选择一项差异，或从下面的问题开始。我会结合当前分析范围给出解释。</p>${['本期最需要关注哪些问题？','为什么采购成本超出预算？','帮我梳理下一步整改重点'].map(q=>`<button class="suggestion" data-action="ask-preset" data-question="${q}">${q}${icon('arrow')}</button>`).join('')}</div>`}${S.asking?'<div class="run-stage"><span class="spinner"></span>正在整理解读…</div>':''}</div><form class="assistant-compose" id="assistant-form"><label class="permission-row"><input type="checkbox" id="data-access" ${S.access?'checked':''}>允许访问当前分析结果</label><div class="compose-box"><textarea id="chat-input" rows="2" placeholder="问一个关于本期经营的问题…" aria-label="向衡策助手提问" ${S.asking?'disabled':''}>${esc(S.draft)}</textarea><div class="compose-tools">${icon('lock')}<span>${S.access?'仅使用当前授权的分析结果':'分析数据访问已关闭'}</span><button class="btn primary" type="submit" aria-label="发送问题" ${S.asking?'disabled':''}>${icon('arrowUp')}</button></div></div></form></aside>`;}
function render(){if(!S.data)return;closeSelects();const before=captureLayout();$('#app').innerHTML=shell();bindForms();enhanceSelects($('#app'));syncNavigation();animateLayout(before);}

// 下方交互层只组织页面状态与宿主请求，不实现财务计算。
const reportSnapshots=new Map();
function modal(title,description,body,footer='',options={}){
  closeSelects();
  modalReturn=document.activeElement;
  modalReturnHint=modalReturn?.dataset.action?{scope:modalReturn.closest('.sidebar')?'.sidebar':modalReturn.closest('.topbar')?'.topbar':'#main',data:Object.fromEntries(['action','id','page','category'].filter(key=>modalReturn.dataset[key]!=null).map(key=>[key,modalReturn.dataset[key]]))}:null;
  modalSubmit=options.submit||null;
  $('#overlay').innerHTML=`<div class="overlay-backdrop"><section class="dialog ${options.wide?'wide':''} ${options.drawer?'drawer':''}" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><div class="dialog-head"><div><h2 id="dialog-title">${title}</h2>${description?`<p>${description}</p>`:''}</div><button class="icon-btn" data-action="close-dialog" aria-label="关闭弹窗">${icon('close')}</button></div>${options.submit?'<form id="modal-form" style="display:flex;flex-direction:column;min-height:0">':''}<div class="dialog-body ${options.report?'modal-report':''}">${body}<div id="modal-error" role="alert"></div></div>${footer?`<div class="dialog-footer">${footer}</div>`:''}${options.submit?'</form>':''}</section></div>`;
  enhanceSelects($('#overlay'));
  animateDialog();
  const first=$('.dialog-body input:not([type=hidden]),.dialog-body [role="combobox"],.dialog-body textarea,.dialog-footer button',$('#overlay'))||$('.dialog-head button');first?.focus();
  $('#modal-form')?.addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,submitter=$('button[type=submit]',form);if(submitter)submitter.disabled=true;
    try{await modalSubmit(new FormData(form),form);}catch(error){const area=$('#modal-error');if(area)area.innerHTML=`<div class="field-error">${esc(error.message)}</div>`;else toast(error.message,true);}finally{if(submitter?.isConnected)submitter.disabled=false;}
  });
}
function closeModal(){
  closeSelects();
  const dialog=$('.dialog'),original=modalReturn,hint=modalReturnHint;
  return closeDialogMotion(()=>{
    const active=document.activeElement;
    const restore=!active||active===document.body||dialog?.contains(active);
    $('#overlay').innerHTML='';modalSubmit=null;
    if(!restore)return; // 例如“询问助手”已显式聚焦输入框，退出动画不夺回焦点。
    const equivalent=hint?[...document.querySelectorAll(`${hint.scope} [data-action]`)].find(node=>Object.entries(hint.data).every(([key,value])=>node.dataset[key]===value)&&!node.disabled&&node.offsetParent!==null):null;
    const target=original?.isConnected&&original!==document.body?original:equivalent||$('#main');
    target?.focus({preventScroll:true});
  });
}
function inputField(name,label,value,type='text',extra=''){return `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;}
function decimal(raw,label){const text=String(raw).trim();if(!/^-?\d+(\.\d{1,2})?$/.test(text))throw new Error(`${label}必须是数字，最多保留两位小数。`);const negative=text.startsWith('-'),[whole,part='']=text.replace('-','').split('.');const n=Number(BigInt(whole)*100n+BigInt(part.padEnd(2,'0')))*(negative?-1:1);if(!Number.isSafeInteger(n))throw new Error(`${label}超出可用范围。`);return n;}
function settings(){
  const c=S.data.config;
  modal('分析设置','配置本期口径，保存后重新分析生效。',`<div class="form-grid"><label class="field"><span>分析周期</span><select name="cycle"><option ${c.cycle==='月度'?'selected':''}>月度</option><option ${c.cycle==='季度'?'selected':''}>季度</option></select></label>${inputField('period','分析期间',c.period,'text','required placeholder="2027-06 或 2027-Q2"')}${inputField('growth','企业增长率（%）',c.growth/100,'number','required step="0.01" min="-100"')}${inputField('industry','行业增长率（%）',c.industry==null?'':c.industry/100,'number','step="0.01" min="-100"')}<label class="check-label field full" style="flex-direction:row"><input type="checkbox" name="industryCorrection" ${c.industryCorrection?'checked':''}>季度分析启用行业修正</label></div><div class="form-section">判定门限</div><div class="form-grid">${inputField('noise','噪声门限（%）',c.noise/100,'number','required step="0.01" min="0"')}${inputField('significance','显著性门限（%）',c.significance/100,'number','required step="0.01" min="0"')}${inputField('industryThreshold','行业修正门限（%）',c.industryThreshold/100,'number','required step="0.01" min="0"')}</div><div class="form-section"><span>预警档位</span><button type="button" class="text-btn" data-action="add-tier">${icon('plus')}添加档位</button></div><p class="inline-help" style="margin-bottom:12px">按百分比阈值从低到高排列，颜色用于结果中的预警标记。</p><div id="tier-fields">${c.tiers.map(t=>tierFields(t)).join('')}</div>${!isLive?'<div class="notice info spacer-top">演示数据固定为 2027 年 6 月；此处可体验参数保存与预警档位筛选，真实计算由后续插件提供。</div>':''}`,`${btn('close-dialog','取消')}<button type="submit" class="btn primary">保存设置</button>`,{submit:async(fd,form)=>{
    const cfg={...c,cycle:fd.get('cycle'),period:fd.get('period').trim(),growth:decimal(fd.get('growth'),'企业增长率'),industry:fd.get('industry').trim()?decimal(fd.get('industry'),'行业增长率'):null,industryCorrection:fd.has('industryCorrection'),noise:decimal(fd.get('noise'),'噪声门限'),significance:decimal(fd.get('significance'),'显著性门限'),industryThreshold:decimal(fd.get('industryThreshold'),'行业修正门限')};
    if(!(cfg.cycle==='月度'?/^\d{4}-(0[1-9]|1[0-2])$/:/^\d{4}-Q[1-4]$/).test(cfg.period))throw new Error('期间格式与周期不一致：月度用 2027-06，季度用 2027-Q2。');
    cfg.tiers=[...form.querySelectorAll('.tier-row')].map(row=>({name:$('[name="tier-name"]',row).value.trim(),threshold:decimal($('[name="tier-threshold"]',row).value,'预警阈值'),color:$('[name="tier-color"]',row).value}));
    if(cfg.tiers.length<2||cfg.tiers.some((t,i)=>!t.name||t.threshold<=0||(i&&t.threshold<=cfg.tiers[i-1].threshold)))throw new Error('请至少设置两个档位，阈值须为正数并从低到高递增。');
    if(cfg.industryCorrection&&(cfg.cycle!=='季度'||cfg.industry==null))throw new Error('行业修正仅适用于季度分析，且需要填写行业增长率。');
    S.data.config=cfg;S.data.dirty=true;render();closeModal();toast('设置已保存，重新分析后生效。');
  }});
}
function tierFields(t={name:'',threshold:4000,color:'#9957b8'}){return `<div class="tier-row"><input name="tier-name" aria-label="档位名称" value="${esc(t.name)}" required maxlength="12"><input name="tier-threshold" type="number" aria-label="档位阈值百分比" value="${t.threshold/100}" step="0.01" min="0.01" required><input name="tier-color" type="color" aria-label="预警颜色" value="${/^#[0-9a-f]{6}$/i.test(t.color)?t.color:'#c54d57'}"><button class="icon-btn" type="button" data-action="remove-tier" aria-label="删除档位">${icon('trash')}</button></div>`;}
function detail(id){
  const row=S.data.rows.find(r=>r.id===id);if(!row)return;
  modal(esc(row.subject),`${esc(row.department)} / ${esc(row.module)} / ${esc(row.period)}`,`${riskTag(row)} ${tag(row.decision,'blue')}<div class="detail-amounts"><div><p>预算金额（元）</p><strong class="num">${money(row.budget)}</strong></div><div><p>实际金额（元）</p><strong class="num">${money(row.actual)}</strong></div></div><div class="detail-line"><span>差额</span><strong class="num ${row.direction==='favorable'?'positive':'negative'}">${row.variance>0?'+':''}${money(row.variance)} 元</strong></div><div class="detail-line"><span>差异率</span><span class="num">${rate(row.rate)}</span></div><div class="detail-line"><span>经营影响</span>${tag(row.direction==='favorable'?'有利差异':'不利差异',row.direction==='favorable'?'normal':'high')}</div><div class="form-section">判定说明</div><p class="detail-text">${esc(row.reason)}</p><div class="form-section">数据来源</div><div class="source-box">${icon('file')} ${esc(row.source)}<p class="small muted">${!isLive?'这是用于展示溯源位置的演示引用。':'金额按原始记录和本次分析口径展示。'}</p></div><div class="form-section">下一步</div><p class="detail-text">${row.decision==='双环纠错'?'核对预算假设是否发生持续性变化，确认后可提请未来期间预算修订。':'核对业务执行与来源记录，跟踪责任部门的处理进展。'}</p>`,`${btn('ask-row','让助手解释','spark','',`data-id="${esc(id)}"`)}${row.decision==='双环纠错'?btn('revise','提请预算修订','arrow','primary',`data-id="${esc(id)}"`):btn('go-risks','查看整改事项','arrow','primary')}`,{drawer:true});
}
function revise(id){
  const row=S.data.rows.find(r=>r.id===id);if(!row)return;
  const current=S.data.meta.period,year=current.slice(0,4),month=current.includes('Q')?Number(current.slice(-1))*3:Number(current.slice(-2));
  const quarter=S.data.config.cycle==='季度';
  const periods=quarter?Array.from({length:Math.max(0,4-Math.ceil(month/3))},(_,i)=>`${year}-Q${Math.ceil(month/3)+i+1}`):Array.from({length:Math.max(0,12-month)},(_,i)=>`${year}-${String(month+i+1).padStart(2,'0')}`);
  if(!periods.length){toast('当前年度没有可修订的未来期间。',true);return;}
  modal('提请预算修订',`${esc(row.subject)} · ${esc(row.department)}`,`<div class="notice info">${icon('lock')}只修订未来期间，已结账的预算与实际记录保持可追溯。</div><div class="form-grid"><label class="field"><span>生效期间</span><select name="period">${periods.map(p=>`<option>${esc(p)}</option>`).join('')}</select></label>${inputField('amount','修订后预算（元）',(row.budget/100).toFixed(2),'number','step="0.01" min="0" required')}<label class="field full"><span>修订原因</span><textarea name="reason" maxlength="2000" required placeholder="说明假设变化、核对依据与金额来源"></textarea></label><label class="check-label field full" style="flex-direction:row"><input name="approved" type="checkbox" required>我已核对科目、期间、金额与原因，确认批准本次修订。</label></div>${!isLive?'<p class="inline-help spacer-top">演示模式只记录审批交互，不执行预算重算。接入后端后将由插件重算并返回新版本。</p>':''}`,`${btn('close-dialog','取消')}<button class="btn primary" type="submit">${isLive?'批准修订并重算':'记录演示修订'}</button>`,{submit:async fd=>{await mutate('revisions.approve',{rowId:id,period:fd.get('period'),amount:decimal(fd.get('amount'),'修订金额'),reason:fd.get('reason').trim(),approved:fd.has('approved')},isLive?'修订已批准，分析结果已更新。':'演示修订已记录，原计算结果未变更。');closeModal();}});
}
function revisionLog(){modal('预算修订记录','人工确认的未来期间预算调整。',S.data.revisions.length?`<div class="table-scroll"><table><thead><tr><th>科目 / 期间</th><th class="numeric">修订金额</th><th>原因</th></tr></thead><tbody>${S.data.revisions.map(r=>`<tr><td>${esc(r.subject)}<span class="sub">${esc(r.period)} · ${date(r.createdAt)}</span></td><td class="numeric">${money(r.amount)}</td><td style="white-space:normal;max-width:280px">${esc(r.reason)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty-state">'+icon('history')+'<h2>尚无预算修订</h2><p>从双环纠错事项发起修订后，记录会保留在这里。</p></div>',btn('close-dialog','关闭'),{wide:true});}
function taskDetail(id){
  const task=S.data.actions.find(a=>a.id===id);if(!task)return;
  modal(esc(task.title),'整改处理事项',`${tag(task.type==='revision'?'预算假设修订':'执行偏差整改',task.priority)}<p class="detail-text spacer-top">${esc(task.description)}</p><div class="detail-line"><span>责任部门</span><span>${esc(task.department)}</span></div><div class="detail-line"><span>负责人</span><span>${esc(task.owner)}</span></div><div class="detail-line"><span>截止日期</span><span>${esc(task.due)}</span></div><label class="field spacer-top"><span>处理状态</span><select name="status">${[['pending','待处理'],['doing','进行中'],['done','已完成']].map(([value,label])=>`<option value="${value}" ${task.status===value?'selected':''}>${label}</option>`).join('')}</select></label><p class="inline-help spacer-top">完成整改表示处理事项已执行，财务影响仍需在下一期分析中复核。</p>`,`${btn('detail','查看关联差异','link','',`data-id="${esc(task.rowId)}"`)}${task.type==='revision'?btn('revise','提请修订','','',`data-id="${esc(task.rowId)}"`):''}<button class="btn primary" type="submit">保存状态</button>`,{submit:async fd=>{await mutate('actions.update',{id,status:fd.get('status')},'整改状态已更新。');closeModal();}});
}
function background(){modal('本期经营背景','补充经营环境，确认本期是否发生经营变更。',`<div class="form-grid"><label class="field full"><span>经营变更</span><select name="changeStatus"><option value="unknown" ${!['yes','none'].includes(S.data.background.changeStatus)?'selected':''}>尚未确认</option><option value="yes" ${S.data.background.changeStatus==='yes'?'selected':''}>有经营变更</option><option value="none" ${S.data.background.changeStatus==='none'?'selected':''}>无经营变更</option></select></label><label class="field full"><span>背景说明</span><textarea name="text" maxlength="4000" style="min-height:160px">${esc(S.data.background.text)}</textarea><small>背景说明不替代正式的经营变更台账及审批记录。</small></label></div>`,`${btn('close-dialog','取消')}<button type="submit" class="btn primary">保存背景</button>`,{submit:async fd=>{await mutate('background.save',{changeStatus:fd.get('changeStatus'),text:fd.get('text').trim()},'经营背景已保存。');closeModal();}});}
let importMode='append',importCategory=null;
function importDialog(){modal('导入工作簿','选择预算基础、实时经营及本期补充资料。',`<div class="dropzone">${icon('upload')}<strong>准备本次分析的 Excel 工作簿</strong><p class="small spacer-top">预算基础与实时经营为必需；行业对标、经营变更按需导入。</p></div><label class="field"><span>导入方式</span><select id="import-mode"><option value="append">追加到本次工作区</option><option value="replace">替换本次全部工作簿</option></select></label><div class="source-box">${icon('lock')}工作簿由本机解析。AI 仅在获得授权后读取分析结果。${!isLive?'<p class="spacer-top">当前预览尚未接入文件校验。选择文件后会显示“待校验”，不会使用演示数据冒充导入结果。</p>':''}</div>`,`${btn('close-dialog','取消')}${btn('choose-files','选择 .xlsx 文件','folder','primary')}`);}
function chooseFiles(category=null){importCategory=category;importMode=$('#import-mode')?.value||'append';$('#file-input').click();}
async function importFiles(files){if(S.busy)throw new Error('正在分析，请完成后再导入文件。');if(!files.length)return;if([...files].some(f=>! /\.xlsx$/i.test(f.name)))throw new Error('请选择 .xlsx 工作簿。');if([...files].some(f=>f.size>28*1024*1024))throw new Error('单个工作簿不能超过 28 MB。');const prepared=await Promise.all([...files].map(async f=>({name:f.name,size:f.size,bytes:await f.arrayBuffer()})));await mutate('files.import',{files:prepared,mode:importMode,category:importCategory},isLive?'文件已导入。':'文件已选择，等待后端校验。');closeModal();navigate('data');}
function fileDetail(id){const f=S.data.files.find(x=>x.id===id);if(!f)return;modal('工作簿详情',esc(f.name),`<div class="detail-line"><span>数据类别</span><span>${esc(f.category)}</span></div><div class="detail-line"><span>主体</span><span>${esc(f.entity)}</span></div><div class="detail-line"><span>状态</span>${tag(f.status==='valid'?'校验通过':'待后端校验',f.status==='valid'?'normal':'watch')}</div>${f.status==='valid'?`<div class="detail-line"><span>通过检查</span><span>${f.checks} 项</span></div><div class="detail-line"><span>入库行数</span><span>${f.rows} 行</span></div><p class="source-box">${!isLive?'这些检查数量来自演示夹具，用于展示校验结果的呈现方式。真实文件校验由插件提供。':'工作簿已通过本机校验，可用于后续分析。'}</p>`:'<p class="source-box">文件已选入工作区。当前预览不解析其业务内容；待接入插件后检查固定表头、公式与三表勾稽。</p>'}`,btn('close-dialog','关闭'));}
async function runAnalysis(all=false){
  if(S.busy)return;
  S.busy=true;S.progress=isLive?'正在校验输入并计算经营差异…':'正在载入演示分析，整理差异与整改事项…';render();
  try{const data=await request('analysis.run',{entityId:all?'all':S.entity,config:S.data.config});acceptData(data);S.page='overview';location.hash='overview';toast(isLive?'分析完成。':'演示分析已更新。真实预算计算将在接入插件后启用。');}
  catch(error){toast(error.message,true);}finally{S.busy=false;S.progress='';render();}
}
function trendDetail(index){const rows=index==null?S.data.trend:[S.data.trend[index]];modal('收入趋势数据','全公司年度口径；金额单位：元。',`<div class="table-scroll"><table><thead><tr><th>期间</th><th class="numeric">原始预算</th><th class="numeric">实际收入</th><th class="numeric">滚动预测</th></tr></thead><tbody>${rows.map(t=>`<tr><td>${esc(t.period)}</td><td class="numeric">${money(t.budget)}</td><td class="numeric">${money(t.actual)}</td><td class="numeric">${money(t.rolling)}</td></tr>`).join('')}</tbody></table></div>`,btn('close-dialog','关闭'),{wide:true});}

function reportMarkup(data){
  const m=metrics(data.rows),risks=data.rows.filter(r=>r.risk!=='normal');
  return `<article class="report-paper"><div class="brand-line"><strong>衡策</strong> / 经营分析</div>${data.demo?'<div class="report-mark">演示报告 · 虚构数据 · 未调用真实财务计算与模型</div>':''}<h1>${esc(data.meta.period)} 经营分析报告</h1><div class="report-sub">${esc(data.meta.company)}　${esc(data.meta.scenario)}<br>分析时间：${date(data.meta.generatedAt)} ${time(data.meta.generatedAt)}　金额单位：元</div><h2>经营总览</h2><p>本期营业收入 ${money(m.revenue)} 元，预算 ${money(m.budget)} 元。成本与费用共 ${money(m.cost+m.expense)} 元，经营结余 ${money(m.profit)} 元。采购采用独立管理视角，不重复扣入经营结余。</p><h2>预算与实际差异</h2><table><thead><tr><th>科目</th><th>预算</th><th>实际</th><th>差异率</th></tr></thead><tbody>${data.rows.map(r=>`<tr><td>${esc(r.subject)}</td><td class="numeric">${money(r.budget)}</td><td class="numeric">${money(r.actual)}</td><td class="numeric">${rate(r.rate)}</td></tr>`).join('')}</tbody></table><h2>重点问题与处理方向</h2>${risks.map(r=>`<p><strong>${esc(r.subject)} · ${esc(r.decision)}</strong><br>${esc(r.reason)}</p>`).join('')}<h2>整改进展</h2><table><thead><tr><th>事项</th><th>责任部门</th><th>状态</th></tr></thead><tbody>${data.actions.map(a=>`<tr><td>${esc(a.title)}</td><td>${esc(a.department)}</td><td>${{pending:'待处理',doing:'进行中',done:'已完成'}[a.status]}</td></tr>`).join('')}</tbody></table><h2>预算修订记录</h2>${data.revisions.length?data.revisions.map(r=>`<p>${esc(r.subject)} / ${esc(r.period)}：${money(r.amount)} 元。${esc(r.reason)}${data.demo?'（演示记录，尚未执行重算）':''}</p>`).join(''):'<p>本次尚无已批准的预算修订。</p>'}<h2>数据与依据说明</h2><p>${data.demo?'所有企业、人员、数值和事项均为演示夹具。此报告的说明为演示文本；没有调用知识库或真实模型，也不包含经检索验证的法规引用。':'依据以插件返回的分析结果为准。'}</p><p>生成版本：${esc(data.meta.runId)}</p></article>`;
}
async function previewReport(id='current'){
  S.selectedReport=id;
  if(isLive){const response=await request('reports.export',{id,format:'html'});if(response.handled){toast('报告已在宿主中打开。');return;}const text=new TextDecoder().decode(response.bytes);modal('报告预览','由衡策插件返回的正式报告。','<iframe id="live-report-frame" sandbox="" title="正式分析报告" style="width:100%;height:65vh;border:0;background:white"></iframe>',`${btn('close-dialog','关闭')}${btn('export-report','导出报告','download','primary',`data-id="${esc(id)}"`)}`,{wide:true});$('#live-report-frame').srcdoc=text;return;}
  const data=id==='current'?S.data:reportSnapshots.get(id);if(!data)throw new Error('此报告没有可用的演示快照。请生成一份本期报告。');
  modal('报告预览','浏览器打印可选择“另存为 PDF”。',reportMarkup(data),`${btn('close-dialog','关闭')}${btn('export-report','其他格式','download','',`data-id="${esc(id)}"`)}${btn('print-report','导出 PDF','download','primary')}`,{wide:true,report:true});
}
function generateReportDialog(){if(!isReady()){toast('请先导入数据并完成分析。',true);return;}if(S.data.dirty){toast('数据或设置已变更，请重新分析后生成报告。',true);return;}modal('生成本期报告',`${esc(S.data.meta.company)} / ${esc(S.data.meta.period)}`,`<p class="detail-text">报告包含预算执行、差异明细、风险判断、整改进展和预算修订记录。</p><label class="check-label spacer-top"><input type="checkbox" name="includeAI">加入 AI 经营解读</label><p class="inline-help spacer-top">${isLive?'勾选后需允许 AI 访问当前分析结果。':'演示模式只生成带演示标识的报告，不生成真实模型解读。'}</p>`,`${btn('close-dialog','取消')}<button type="submit" class="btn primary">生成报告</button>`,{submit:async fd=>{
    if(S.data.dirty)throw new Error('数据或设置已变更，请重新分析后生成报告。');
    if(fd.has('includeAI')&&!S.access)throw new Error('请先在衡策助手中允许访问当前分析结果。');
    const previous=new Set(S.data.reports.map(r=>r.id));const data=await request('reports.generate',{runId:S.data.meta.runId,includeAI:fd.has('includeAI')});acceptData(data);
    if(!isLive)for(const r of data.reports)if(!previous.has(r.id))reportSnapshots.set(r.id,structuredClone(data));
    closeModal();navigate('reports');toast('报告已生成，可预览与导出。');
  }});}
function exportDialog(id){S.selectedReport=id;modal('导出分析报告','选择需要保存的格式。',`<div class="export-menu">${['pdf','html','md','json'].map(format=>btn('download-report',format==='pdf'?'PDF 文档':format==='html'?'HTML 网页':format==='md'?'Markdown 文档':'JSON 数据','download','',`data-format="${format}" data-id="${esc(id)}"`)).join('')}</div><p class="inline-help spacer-top">${isLive?'文件由衡策插件生成并保存。':'HTML、Markdown 和 JSON 可直接下载；PDF 使用浏览器打印保存。'}</p>`,`${btn('open-output','打开输出文件夹','folder','',`data-id="${esc(id)}"`)}${btn('close-dialog','关闭')}`);}
function download(name,mime,bytes){const url=URL.createObjectURL(new Blob([bytes],{type:mime})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);}
async function saveResponse(response){if(response?.handled)return;if(!response?.bytes||!response?.name)throw new Error('宿主未返回有效的导出文件。');download(response.name,response.mime||'application/octet-stream',response.bytes);}
async function downloadReport(id,format){
  if(isLive){await saveResponse(await request('reports.export',{id,format}));toast('导出请求已完成。');return;}
  const data=id==='current'?S.data:reportSnapshots.get(id);if(!data)throw new Error('报告快照不存在，请重新生成。');
  if(format==='pdf'){await previewReport(id);window.print();return;}
  const name=`衡策-${data.meta.period}-演示分析报告.${format}`;
  if(format==='html'){const css=await(await fetch('./src/界面.css')).text();download(name,'text/html;charset=utf-8',`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>衡策演示报告</title><style>${css}body{max-width:960px;margin:24px auto;background:white}.report-paper{box-shadow:none}</style>${reportMarkup(data)}</html>`);}
  if(format==='json')download(name,'application/json;charset=utf-8',JSON.stringify(data,null,2));
  if(format==='md'){const lines=[`# 衡策 ${data.meta.period} 经营分析报告`,'','> 演示数据，未调用真实模型或财务计算。','',`主体：${data.meta.company}`,'','| 科目 | 预算（元） | 实际（元） | 差异率 |','|---|---:|---:|---:|',...data.rows.map(r=>`| ${r.subject} | ${money(r.budget)} | ${money(r.actual)} | ${rate(r.rate)} |`),'','## 重点问题',...data.rows.filter(r=>r.risk!=='normal').flatMap(r=>['',`### ${r.subject}`,r.reason]),'','## 整改进展',...data.actions.map(a=>`- ${a.title}：${{pending:'待处理',doing:'进行中',done:'已完成'}[a.status]}`)];download(name,'text/markdown;charset=utf-8',lines.join('\n'));}
  toast('报告已交给浏览器下载。');
}
function exportTable(){const rows=visibleRows(),quote=v=>`"${String(v).replaceAll('"','""')}"`;const text=[['科目','部门','模块','预算（元）','实际（元）','差异率','预警'],...rows.map(r=>[r.subject,r.department,r.module,(r.budget/100).toFixed(2),(r.actual/100).toFixed(2),rate(r.rate),riskNames[r.risk]])].map(row=>row.map(quote).join(',')).join('\r\n');download(`衡策-差异明细-${S.data.meta.period}.csv`,'text/csv;charset=utf-8','\uFEFF'+text);toast('已导出当前筛选范围的明细。');}
async function ask(question){
  if(S.asking||!question.trim())return;
  if(!S.access){toast('请先勾选“允许访问当前分析结果”。',true);$('#data-access')?.focus();return;}
  S.messages.push({role:'user',text:question.trim()});S.draft='';S.asking=true;render();
  try{const response=await request('assistant.ask',{question:question.trim(),context:{entityId:S.entity,period:S.data.meta.period,rowId:S.askRow||undefined,runId:S.data.meta.runId},dataAccess:S.access});if(!response.handled)S.messages.push({role:'assistant',text:response.text,sources:response.sources});else S.messages.push({role:'assistant',text:'已将问题与当前分析上下文交给宿主会话。'});}
  catch(error){S.messages.push({role:'error',text:error.message});}finally{S.asking=false;render();const log=$('#assistant-log');if(log)log.scrollTop=log.scrollHeight;$('#chat-input')?.focus();}
}
function help(){modal('使用衡策工作台','准备数据、发现问题、跟踪处理、形成报告。',`<ol class="checklist"><li>在数据工作区导入预算基础与实时经营工作簿。</li><li>确认主体、分析周期和期间，按需要调整分析参数。</li><li>运行分析，查看经营总览和科目差异。</li><li>打开风险事项，记录整改状态或发起预算修订。</li><li>生成报告，预览并导出 PDF、HTML、Markdown 或 JSON。</li></ol><div class="form-section">关于当前预览</div><p class="detail-text">${isLive?'当前页面已连接宿主插件。文件导入、分析、报告和 AI 问答均经宿主接口执行。':'当前是独立 UI 演示。数据、人物和事项均为虚构，交互只保留在页面内存，刷新会恢复初始演示。真实文件校验、预算重算、知识库检索和模型调用将在接入插件后启用。'}</p><div class="form-section">键盘操作</div><p class="detail-text">Tab 移动焦点，Enter 执行操作，Esc 关闭弹窗。助手输入框用 Enter 发送，Shift + Enter 换行。</p>`,btn('close-dialog','知道了'));
}

function bindForms(){
  $('#entity-select')?.addEventListener('change',e=>{S.entity=e.target.value;S.askRow=null;S.search='';S.module='全部';render();});
  $('#row-search')?.addEventListener('input',e=>{S.search=e.target.value;$('#variance-table').innerHTML=varianceTable(S.page==='overview');});
  $('#risk-filter')?.addEventListener('change',e=>{S.risk=e.target.value;$('#variance-table').innerHTML=varianceTable(S.page==='overview');});
  $('#file-input')?.addEventListener('change',e=>importFiles(e.target.files).catch(error=>toast(error.message,true)));
  const drop=$('#dropzone');if(drop){drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');importMode='append';importCategory=null;importFiles(e.dataTransfer.files).catch(error=>toast(error.message,true));});}
  $('#data-access')?.addEventListener('change',e=>{S.access=e.target.checked;S.draft=$('#chat-input')?.value||'';render();});
  $('#chat-input')?.addEventListener('input',e=>{S.draft=e.target.value;});
  $('#chat-input')?.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();ask(e.target.value);}});
  $('#assistant-form')?.addEventListener('submit',e=>{e.preventDefault();ask($('#chat-input').value);});
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  event.preventDefault();const {action,id,page,category,format}=button.dataset;
  if(S.busy&&['settings','import','choose-files','confirm-remove','background','revise','reset-demo','task-detail','generate-report','open-history'].includes(action)){toast('正在分析，请完成后再修改工作区。');return;}
  try{
    switch(action){
      case 'nav': navigate(page);break;
      case 'menu':setNavigation(!S.navOpen);break;
      case 'close-menu':setNavigation(false);break;
      case 'assistant':S.ai=!S.ai;render();break;
      case 'settings':settings();break;
      case 'help':help();break;
      case 'close-dialog':closeModal();break;
      case 'import':importDialog();break;
      case 'choose-files':chooseFiles(category);break;
      case 'template':await saveResponse(await request('templates.download',{category}));break;
      case 'reset-demo':await mutate('demo.reset',{},'已恢复演示数据。');for(const r of S.data.reports)reportSnapshots.set(r.id,structuredClone(S.data));break;
      case 'remove-file':modal('移除工作簿','仅从本次工作区移除，不删除磁盘上的原文件。',`<p class="detail-text">${esc(S.data.files.find(f=>f.id===id)?.name)}</p>`,`${btn('close-dialog','取消')}${btn('confirm-remove','移除文件','trash','danger',`data-id="${esc(id)}"`)}`);break;
      case 'confirm-remove':await mutate('files.remove',{id},'工作簿已从当前工作区移除。');closeModal();break;
      case 'file-detail':fileDetail(id);break;
      case 'background':background();break;
      case 'run':await runAnalysis();break;
      case 'run-all':await runAnalysis(true);break;
      case 'module':S.module=button.dataset.value;render();break;
      case 'sort':S.ascending=!S.ascending;$('#variance-table').innerHTML=varianceTable(S.page==='overview');break;
      case 'detail':detail(id);break;
      case 'trend-detail':trendDetail(button.dataset.index==null?null:Number(button.dataset.index));break;
      case 'department':S.entity=id;S.askRow=null;navigate('analysis');break;
      case 'go-risks':closeModal();navigate('risks');break;
      case 'task-detail':taskDetail(id);break;
      case 'revise':revise(id);break;
      case 'revision-log':revisionLog();break;
      case 'add-tier':$('#tier-fields').insertAdjacentHTML('beforeend',tierFields());break;
      case 'remove-tier':button.closest('.tier-row').remove();break;
      case 'generate-report':generateReportDialog();break;
      case 'preview-report':await previewReport(id);break;
      case 'export-report':exportDialog(id);break;
      case 'download-report':await downloadReport(id,format);break;
      case 'print-report':window.print();break;
      case 'open-output':await request('reports.openFolder',{id});break;
      case 'open-history':await mutate('history.open',{id},'已打开该次分析快照。');S.entity='all';navigate('overview');break;
      case 'export-table':exportTable();break;
      case 'ask-row':S.askRow=id;S.ai=true;closeModal();S.draft=`请解释「${S.data.rows.find(r=>r.id===id).subject}」的差异原因和处理建议。`;render();$('#chat-input')?.focus();break;
      case 'ask-preset':S.draft=button.dataset.question;render();await ask(S.draft);break;
    }
  }catch(error){toast(error.message,true);}
});
document.addEventListener('keydown',event=>{
  if(event.defaultPrevented)return;
  if(event.key==='Escape'){if($('#overlay').children.length)closeModal();else if(S.navOpen)setNavigation(false);else if(S.ai){S.ai=false;render();}}
  const dialog=$('[role="dialog"]');
  if(dialog&&event.key==='Tab'){const focusables=[...dialog.querySelectorAll('button:not([disabled]),input,select,textarea,a[href],[tabindex="0"]')].filter(e=>e.offsetParent!==null);const first=focusables[0],last=focusables.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  if(!dialog&&S.navOpen&&event.key==='Tab'&&window.matchMedia('(max-width:760px)').matches){const controls=[...$('.sidebar').querySelectorAll('button:not([disabled]),a[href]')];const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  if(event.key==='Enter'&&event.target.classList.contains('chart-point'))event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));
});
window.addEventListener('hashchange',()=>{const page=location.hash.slice(1);if(pages[page]&&page!==S.page){S.page=page;render();}});
window.addEventListener('resize',syncNavigation,{passive:true});
async function start(){try{acceptData(await request('workspace.load'));if(!isLive)for(const r of S.data.reports)reportSnapshots.set(r.id,structuredClone(S.data));render();subscribe(event=>{try{if(event.type==='workspace.changed'){acceptData(event.data);render();}if(event.type==='analysis.progress'){S.progress=event.data.message;if(S.busy)render();}if(event.type==='assistant.message'){S.messages.push({role:'assistant',text:event.data.text});render();}}catch(error){toast(error.message,true);}});}catch(error){$('#app').innerHTML=`<div class="boot"><div style="text-align:center;max-width:480px;padding:24px"><h1>工作区暂时无法打开</h1><p class="detail-text spacer-top">${esc(error.message)}</p><button class="btn primary spacer-top" id="retry-start">重新连接</button></div></div>`;$('#retry-start').onclick=start;}}
installMotion();
installSelects();
start();
