// 图标层：39 个 24×24 线性图标（内联 SVG）。界面里所有图标都从这里取，
// 不引入图标字体或第三方库，保证离线可用、颜色继承 currentColor。
import { icon } from './图标.mjs';
// 业务桥是唯一的取数通道：request 发 action、subscribe 收宿主推送、isLive 区分真实/演示模式。
// 界面绝不直接算财务数字，所有金额与比率都来自桥返回的整数分、整数基点。
import { request, subscribe, isLive, canAnalyze } from './业务桥.mjs';
// 动效层：整页重绘前抓布局快照（captureLayout），重绘后补出场/入场（animateLayout），
// 弹窗与关闭动画走 animateDialog / closeDialogMotion；减少动效的系统设置由该模块统一降级。
import { captureLayout, animateLayout, animateDialog, closeDialogMotion, installMotion } from './动效.mjs';
// 原生 select 增强：enhanceSelects 把新渲染的 select 换成玻璃风格按钮，closeSelects 在重绘前收起旧面板，
// installSelects 只装一次全局监听（点外面/Esc/滚动/缩放时关闭）。
import { enhanceSelects, closeSelects, installSelects } from './下拉菜单.mjs';

// 查询简写：默认在 document 内查，弹窗渲染后需要限定在 #overlay 内，所以保留 root 参数。
const $ = (selector, root=document) => root.querySelector(selector);
// 所有拼接进 innerHTML 的动态文本必须过这一道：转义 & < > " '，
// 演示数据里可能出现公司名、科目名、修订原因等自由文本，不转义就有注入与串行风险。
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// 金额格式化：入参是整数分，除以 100 显示到元，保留两位小数并加千分位。
// null/undefined 一律显示破折号，表示“该口径没有数据”，不要显示成 0。
const money = value => value == null ? '—' : (value/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
// 万元格式化：整数分 ÷ 100（→元）÷ 10000（→万元），即除以一百万。
// 概览页的四张指标卡与图表的纵轴标注都用它，全站看金额的“大数”统一以万元为单位。
const wan = value => (value/1000000).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});
// 比率格式化：入参是整数基点（1% = 100 基点），除以 100 得到百分比并固定两位小数。
// 正数强制显示 + 号，让“有利/不利”的判断先来自符号、再来自颜色。
const rate = value => value == null ? '—' : `${value>0?'+':''}${(value/100).toFixed(2)}%`;
// 日期格式化固定在 Asia/Shanghai：报告与历史记录的时间戳若按本机时区渲染，
// 跨时区打开会出现“同一次分析两个日期”，因此这里显式指定时区并统一成 2027.06.30 的写法。
const date = value => { const d=new Date(value); return Number.isNaN(+d)?'—':d.toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).replaceAll('/','.'); };
// 时间格式化同样按 Asia/Shanghai，只取小时与分钟：时间戳精确到分即可，秒只会增加噪音。
const time = value => new Date(value).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'});
// 期间标签：2027-06 显示「2027 年 6 月」，2027-Q2 显示「2027 年第 2 季度」。
// 季度用 -Q1..Q4 结尾判断，月度的月份去掉前导零，避免出现「2027 年 06 月」这种公文式写法。
const periodLabel = value => /-Q[1-4]$/.test(value)?`${value.slice(0,4)} 年第 ${value.slice(-1)} 季度`:`${value.slice(0,4)} 年 ${Number(value.slice(-2))} 月`;
// 求和工具：按字段累加，缺失值按 0 处理（r[key]||0）。
// 只用于界面上的聚合展示，真正的财务口径由插件计算，这里不做任何修订与重算。
const sum = (rows,key) => rows.reduce((a,r)=>a+(r[key]||0),0);
// 统一按钮模板：把 data-action 与可选的 data-id / data-format 等属性拼进 HTML。
// 全部交互都走事件委托（document 上的 click 监听），所以按钮只负责携带 action 名与参数，
// 不各自绑定处理器——这保证整页重绘后行为不会丢失。
const btn = (action,text,ico='',cls='',extra='') => `<button class="btn ${cls}" data-action="${action}" ${extra}>${ico?icon(ico):''}${text}</button>`;
// 风险档位的中文名兜底：插件返回 tierName 时优先用插件的档位名（见 riskTag），
// 没有时退回这三档，保证旧快照与演示数据也能正常显示。
const riskNames={high:'高风险',watch:'关注',normal:'正常'};
// 标签模板：class 决定配色（normal/watch/high/blue/neutral），文本一律转义。
// 表格里的预警列、整改看板里的类型标签都复用它，样式只在 界面.css 定义一处。
const tag = (text,cls='neutral') => `<span class="tag ${esc(cls)}">${esc(text)}</span>`;
// 导航表：键同时是路由 hash 与 pageContent 的渲染键，值是「标题 + 图标名」。
// 顺序决定侧栏顺序；第 6 项之前插入分隔线与「成果与记录」小标题（见 shell 里的 i===5）。
// 新增页面必须同时改这里与 renderers，否则 pageContent 会回落经营总览。
const pages={overview:['经营总览','overview'],data:['数据工作区','data'],analysis:['差异分析','chart'],risks:['风险与整改','risk'],reports:['报告中心','report'],history:['分析记录','history']};
// 单一状态对象：整个界面所有可变状态都收在这里，render() 读取它重绘整页。
// data：最近一次的工作区快照（rows/files/reports/actions…），未加载前为 null；
// page：当前页面键（初次进入取 location.hash，非法 hash 回落 overview）；
// entity：当前分析主体（'all' 为全公司，其余为部门 id，决定所有口径）；
// module：差异表的模块筛选（全部/收入/成本/费用/采购）；
// risk：差异表的预警档位筛选（all/high/watch/normal）；
// search：差异表关键词（科目、部门、模块三者做包含匹配）；
// sort / ascending：差异表排序字段与方向（默认按差额绝对值降序）；
// ai：衡策助手侧栏是否展开（顶栏按钮与 Esc 都会切换它）；
// messages：助手对话历史，元素形如 {role:'user'|'assistant'|'error',text,sources?,system?}；
// access：是否允许助手读取当前分析结果（未授权时提问会被拦下）；
// askRow：从差异详情带入助手的关注科目行 id；
// asking：助手正在等待回答（禁用输入框、显示整理中动画）；
// draft：尚未发送的输入内容（重绘后要还原，否则用户打字会被清空）；
// busy：正在运行分析（禁用会改工作区的操作，顶栏显示进度条）；
// progress：宿主推送的分析阶段文案（busy 时显示在页面顶部提示条）；
// navOpen：移动端侧栏是否展开（同时控制 inert 与遮罩）；
// chartType：经营总览当前图表类型（对应 CHART_KINDS 的键）；
// pageNo：差异表分页页码（切换筛选时统一重置为 1）；
// selectedReport：最近一次操作的报告 id（导出菜单与预览之间传递）。
const S={data:null,page:pages[location.hash.slice(1)]?location.hash.slice(1):'overview',entity:'all',module:'全部',risk:'all',search:'',sort:'variance',ascending:false,ai:false,messages:[],access:false,askRow:null,asking:false,draft:'',busy:false,progress:'',navOpen:false,chartType:'trend',pageNo:1,selectedReport:null};
// 嵌入式窗口标记：宿主以 ?embedded=1 打开时，页面会隐藏顶部拖动条并调整布局，
// 用于“在应用内嵌一块工作台”的场景，普通浏览器打开不受影响。
const embedded=new URLSearchParams(location.search).get('embedded')==='1';
// 弹窗焦点三件套：打开前记录触发元素（modalReturn）、它所在区域与 data-* 指纹（modalReturnHint）、
// 以及表单提交回调（modalSubmit）。关闭后优先把焦点还给原按钮；原按钮已被重绘掉时，
// 按指纹找回等价按钮，最后兜底到 #main——键盘用户的上下文不会丢。
let modalReturn=null, modalReturnHint=null, modalSubmit=null;

// 当前口径的差异行：选了部门就只留该部门的行；
// 全公司时优先取 departmentId==='all' 的公司汇总行，旧演示数据没有汇总行时退回全部明细。
// 所有指标、图表、表格都从这一个函数取数，保证同一屏内的数字互相自洽。
function currentRows(){
  const rows=S.data.rows;
  if(S.entity!=='all')return rows.filter(r=>r.departmentId===S.entity);
  // 新分析同时包含公司汇总与部门明细；旧演示只有部门明细，仍按原口径展示。
  const totals=rows.filter(r=>r.departmentId==='all');
  return totals.length?totals:rows;
}
// 差异表的最终行集：在 currentRows 基础上依次过滤模块、预警档位、关键词，
// 再按当前排序字段排序（差额按绝对值比较，这样“最大偏差”在正负两侧都能排到前面）。
// 排序方向由 S.ascending 决定，切换时只重算这张表，不整页重绘。
function visibleRows(){return currentRows().filter(r=>(S.module==='全部'||r.module===S.module)&&(S.risk==='all'||r.risk===S.risk)&&(!S.search||`${r.subject}${r.department}${r.module}`.toLowerCase().includes(S.search.toLowerCase()))).sort((a,b)=>{const av=S.sort==='variance'?Math.abs(a.variance):a[S.sort],bv=S.sort==='variance'?Math.abs(b.variance):b[S.sort];return (av-bv)*(S.ascending?1:-1);});}
// 预警标签：优先使用插件下发的档位名与颜色（tierName/tierColor），
// 颜色只接受 #rrggbb 形式的六位十六进制（用 12 透明度做淡底），非法值退回内置三档样式，
// 避免脏数据把任意字符串注入 style 属性。
function riskTag(row){
  const name=row.tierName||riskNames[row.risk];
  const color=row.tierColor;
  return /^#[0-9a-f]{6}$/i.test(color||'')?`<span class="tag" style="color:${color};background:${color}12">${esc(name)}</span>`:tag(name,row.risk);
}
// 当前主体的显示名：从 entities 里按 id 查，找不到时显示「全部部门」。
// 报告抬头、助手上下文、页面副标题都用它，保证“当前在看谁”在各处一致。
function entityName(){return S.data.entities.find(e=>e.id===S.entity)?.name||'全部部门';}
// 指标口径再强调：所有金额都是整数分，累加用普通加法即可（远小于 2^53），
// 但显示前一律经 money/wan/rate 换算——界面里不允许出现“元”字面量参与运算的写法，
// 否则同一块页面会出现分与元混算的隐性错误。
// 核心指标聚合（全部为整数分）：预算只累加收入行的预算（收入预算才是经营预算的分母），
// 实际收入、实际成本、实际费用分别按模块汇总，经营结余 = 收入 − 成本 − 费用。
// 采购模块不参与结余计算（独立管理视角，避免与成本重复扣减）；
// risk 统计非 normal 的差异行数，作为“需关注差异”的口径。
function metrics(rows=currentRows()){
  const revenue=rows.filter(r=>r.module==='收入'),cost=rows.filter(r=>r.module==='成本'),expense=rows.filter(r=>r.module==='费用');
  return {budget:sum(revenue,'budget'),revenue:sum(revenue,'actual'),cost:sum(cost,'actual'),expense:sum(expense,'actual'),profit:sum(revenue,'actual')-sum(cost,'actual')-sum(expense,'actual'),risk:rows.filter(r=>r.risk!=='normal').length};
}
// 是否可以开始分析：必须有差异行，且「预算基础」「实时经营」两类文件各至少一份校验通过。
// 这是界面层的判断，真正运行时后端还会再校验一次（前端判断只为避免空转与误操作）。
function isReady(){return S.data.rows?.length && ['预算基础','实时经营'].every(c=>S.data.files.some(f=>f.category===c&&f.status==='valid'));}
// 轻提示：动态插入一条气泡，6.5 秒后自动移除；error 为真时用红色与风险图标。
// 不阻断操作、不需要确认——符合“操作已发生，只做告知”的场景；
// 校验类错误同时会写进弹窗的 #modal-error，双通道避免提示被忽略。
function toast(message,error=false){const el=document.createElement('div');el.className=`toast ${error?'error':''}`;el.innerHTML=`${icon(error?'risk':'circleCheck')}<span>${esc(message)}</span>`;$('#toasts').append(el);setTimeout(()=>el.remove(),6500);}
// 页面切换：重置分页、收起移动端抽屉、清空搜索/筛选（避免把上一页的筛选带到新页面），
// 写 hash 触发 hashchange 以便浏览器前进后退，重绘后把焦点移到主区 #main，
// 并把滚动位置拉回顶部（instant 是为了不被“平滑滚动”拖慢）。
function navigate(page){S.page=page;S.pageNo=1;S.navOpen=false;S.search='';S.risk='all';S.module='全部';location.hash=page;render();$('#main')?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
// 移动端导航的可访问性开关：窄屏且抽屉未展开时，把侧栏设为 inert（不可聚焦、不被读屏器读到），
// 展开时反过来把工作区设为 inert，并给 body 加 navigation-open 供 CSS 显示遮罩。
// inert 比单纯 display:none 更稳：它同时屏蔽焦点、指针与辅助技术。
function syncNavigation(){
  const mobile=window.matchMedia('(max-width:760px)').matches;
  const sidebar=$('#main-navigation'),workspace=$('.workspace');
  if(sidebar)sidebar.inert=mobile&&!S.navOpen;
  if(workspace)workspace.inert=mobile&&S.navOpen;
  document.body.classList.toggle('navigation-open',mobile&&S.navOpen);
}
// 开合移动端抽屉：先更新状态并重绘，再把焦点移到“当前激活的导航项”或“汉堡按钮”，
// 保证键盘/读屏用户在抽屉开合后不会落在不可见区域。
function setNavigation(open){
  S.navOpen=open;render();
  const target=open?$('.sidebar .nav-item.active'):$('.mobile-menu');
  target?.focus({preventScroll:true});
}
// 统一的数据入口与最后一层校验：schemaVersion 必须是 1.0，rows 与 files 必须是数组，
// 不合格直接抛错（错误文案会被 toast 或弹窗原样展示，不做二次包装）。
// 通过后替换快照；若当前选中的部门在新数据里不存在，自动回落到全公司，
// 避免“切主体后重新分析，页面却卡在一个已消失的部门”。
function acceptData(data){if(!data||data.schemaVersion!=='1.0'||!Array.isArray(data.rows)||!Array.isArray(data.files))throw new Error('收到的工作区数据不符合接口约定。');S.data=data;if(!data.entities.some(e=>e.id===S.entity))S.entity='all';}
// “改数据再重绘”的通用动作：调一次宿主 action，接受返回的新快照，重绘，最后按需提示。
// 所有会改变工作区的操作（导入、删除、整改状态、预算修订、背景保存、历史回看）都走它，
// 保证“只有宿主返回的新数据才会被渲染”，界面不维护自己的可变副本。
async function mutate(action,payload,message){const data=await request(action,payload);acceptData(data);render();if(message)toast(message);return data;}

// 布局栅格：外层 .shell 是「侧栏 + 工作区」两列，760px 以下侧栏变成覆盖式抽屉；
// 工作区内部再分顶栏与内容区，内容区里 .content-layout 在助手展开时切成两列。
// 顶栏 sticky 在顶部（top:12px 的玻璃条），所以页面滚动时顶栏与侧栏底部状态行都保持可见。
// 整页骨架：侧栏（品牌、主体、导航、底部设置/帮助/连接状态）+ 工作区（顶栏、内容区）。
// 顶栏集中放：移动端汉堡、面包屑与部门选择、演示/已连接标记、期间、助手开关、头像、分析进度条。
// 嵌入式模式额外画一条窗口拖动区；隐藏的 file input 也放在骨架里，供“选择文件”复用。
function shell(){
  const riskCount=currentRows().filter(r=>r.risk!=='normal').length;
  return `<div class="shell ${embedded?'embedded':''} ${S.navOpen?'nav-open':''}">
    ${embedded?'<div class="win-grip" aria-hidden="true"></div>':''}
    <button class="nav-scrim" data-action="close-menu" type="button" aria-label="关闭导航" tabindex="-1" ${S.navOpen?'':'hidden'}></button>
    <aside class="sidebar" id="main-navigation" aria-label="主导航">
      <a class="brand" href="#overview" data-action="nav" data-page="overview" aria-label="衡策经营总览"><img src="./标识.svg" alt=""><div><div class="brand-name">衡策</div><div class="brand-caption">经营分析工作台</div></div></a>
      <div class="workspace-switch">${icon('building')}<div class="grow"><strong>${esc(S.data.meta.company.replace('有限公司',''))}</strong><small>企业经营空间</small></div></div>
      <div class="nav-label">工作台</div>
      <nav>${Object.entries(pages).map(([key,[label,ico]],i)=>`${i===5?'<div class="nav-divider"></div><div class="nav-label">成果与记录</div>':''}<button class="nav-item ${S.page===key?'active':''}" data-action="nav" data-page="${key}" ${S.page===key?'aria-current="page"':''}>${icon(ico)}<span>${label}</span>${key==='risks'&&riskCount?`<span class="count">${riskCount}</span>`:''}</button>`).join('')}</nav>
      <div class="sidebar-bottom"><button class="nav-item" data-action="settings">${icon('settings')}分析设置</button><button class="nav-item" data-action="help">${icon('help')}使用帮助</button><div class="connection"><span class="dot ${!isLive?'demo':''}"></span>${isLive?'已连接衡策插件':'演示工作区'}<span class="grow"></span><span>UI 2.0</span></div></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><button class="icon-btn mobile-menu" data-action="menu" aria-label="${S.navOpen?'收起导航':'展开导航'}" aria-expanded="${S.navOpen}" aria-controls="main-navigation">${icon('menu')}</button><div class="breadcrumb"><strong>${esc(S.data.meta.company.replace('有限公司',''))}</strong>${icon('chevron')}<select id="entity-select" class="topbar-select" aria-label="选择分析部门">${S.data.entities.map(e=>`<option value="${esc(e.id)}" title="${esc(e.title||e.fullName||e.name)}" ${e.id===S.entity?'selected':''}>${esc(e.name)}</option>`).join('')}</select></div><div class="topbar-right">${!isLive?'<span class="demo-tag" title="所有数据均为虚构演示；尚未连接真实分析后端">演示模式</span>':tag('已连接','normal')}<span class="pill-select">${icon('clock')}<span class="small">${esc(S.data.meta.period)}</span></span>${btn('assistant',`<span class="assistant-label">衡策助手</span>`,'spark',S.ai?'primary':'')}<span class="avatar" title="当前企业工作区">恒</span></div>${S.busy?'<div class="loading-strip" role="progressbar" aria-label="正在执行分析"></div>':''}</header>
      <div class="content-layout"><main class="main" id="main" data-page="${S.page}" tabindex="-1">${pageContent()}</main>${S.ai?assistant():''}</div>
    </div></div><input id="file-input" type="file" accept=".xlsx" multiple hidden>`;
}
// 页头模板：左标题+说明、右操作按钮组。所有页面共用同一套间距与字号，
// 新页面只需传标题、一句说明和按钮，不需要自己拼结构。
function heading(title,description,actions=''){return `<div class="page-heading"><div><h1>${title}</h1><p>${description}</p></div>${actions?`<div class="heading-actions">${actions}</div>`:''}</div>`;}
// 标准操作组：导入数据 + 运行分析（分析中按钮禁用并改文案）。
// 放在页头右上角，与数据工作区里的“开始分析”指向同一个 action，避免两套入口行为不一致。
function standardActions(){return `${btn('import','导入数据','upload')}${btn('run',S.busy?'正在分析':'运行分析',S.busy?'':'play','primary',S.busy?'disabled':'')}`;}
// 页面路由与全局提示条：按 S.page 选渲染函数，非法键回落到经营总览。
// 顶部三条提示依次是：分析中（进度文案）、数据已变更/待校验（附“重新分析”）、分析警告折叠列表；
// 底部固定一行口径说明（正式模式写“插件计算”，演示模式写“虚构演示数据”）。
function pageContent(){
  const renderers={overview,analysis:analysisPage,data:dataPage,risks:riskPage,reports:reportsPage,history:historyPage};
  if(!renderers[S.page])S.page='overview';
  const pending=S.data.files.some(f=>f.status==='pending');
  const warnings=(S.data.warnings||[]).map(w=>typeof w==='string'?w:w.message||JSON.stringify(w));
  return `${S.busy?`<div class="notice info"><span class="spinner"></span><span>${esc(S.progress||'正在分析，请稍候…')}</span></div>`:''}${S.data.dirty?`<div class="notice">${icon('risk')}<span>${pending?'本地文件待校验。当前结果仍为上次分析，接入后端后可校验这些文件。':'数据或设置已变更，当前展示上次分析结果。重新分析后更新报告。'}</span>${btn('run','重新分析','','small',S.busy?'disabled':'')}</div>`:''}${warnings.length?`<div class="notice">${icon('risk')}<details><summary>${warnings.length} 条分析提示</summary>${warnings.map(w=>`<p>${esc(w)}</p>`).join('')}</details></div>`:''}${renderers[S.page]()}<div class="footer-note">${icon('lock')}<span>${isLive?'金额计算由衡策插件完成':'当前为虚构演示数据，所有操作仅在本次预览生效'} · 金额以人民币展示</span></div>`;
}
// 摘要四卡：本期营业收入（含较预算的百分比差）、本期成本与费用、经营结余、需关注差异。
// 部门是费用中心时没有收入，也没有“结余”，因此自动降为两列（gongSi 判断依据是主体 title 是否含「/」）；
// “整改完成 done/x”按当前口径下关联的事项统计，而不是全公司总数。
function summary(){
  const m=metrics(),delta=m.revenue-m.budget;
  const ids=new Set(currentRows().map(r=>r.id)),scopedActions=S.data.actions.filter(a=>ids.has(a.rowId));
  const done=scopedActions.filter(a=>a.status==='done').length;
  // 部门是费用中心：没有收入也就没有"结余"，这两张卡在公司口径才展示
  const gongSi=!String((S.data.entities.find(e=>e.id===S.entity)||{}).title||'').includes('/');
  return `<section class="summary-strip ${gongSi?'':'two-cols'}" aria-label="核心经营指标">
    ${gongSi?`<div class="metric"><div class="metric-label">本期营业收入${icon('chart')}</div><div class="metric-number">${wan(m.revenue)}<small>万元</small></div><div class="metric-foot"><span class="${delta>=0?'positive':'negative'}">${delta>=0?'↑':'↓'} ${Math.abs(m.budget?delta/m.budget*100:0).toFixed(2)}%</span><span>较预算 ${wan(m.budget)} 万</span></div></div>`:''}
    <div class="metric"><div class="metric-label">本期成本与费用${icon('data')}</div><div class="metric-number">${wan(m.cost+m.expense)}<small>万元</small></div><div class="metric-foot">成本 ${wan(m.cost)} · 费用 ${wan(m.expense)}</div></div>
    ${gongSi?`<div class="metric"><div class="metric-label">经营结余${icon('overview')}</div><div class="metric-number ${m.profit<0?'negative':''}">${wan(m.profit)}<small>万元</small></div><div class="metric-foot">收入 − 成本 − 费用</div></div>`:''}
    <div class="metric"><div class="metric-label">需关注差异${icon('flag')}</div><div class="metric-number">${m.risk}<small>项</small></div><div class="metric-foot"><span class="negative">${currentRows().filter(r=>r.risk==='high').length} 项高风险</span><span>· 整改完成 ${done}/${scopedActions.length}</span></div></div>
  </section>`;
}
// 空状态：没数据时告诉用户下一步做什么（导入两类工作簿），
// 并区分模式——演示模式额外给一个“载入演示数据”按钮，真实模式只给导入。
function empty(title='准备好数据，开始本期分析',description='导入预算基础与实时经营工作簿，衡策会为你整理差异与风险。'){return `<div class="panel empty-state">${icon('chart')}<h2>${title}</h2><p>${description}</p><div class="actions-inline">${btn('import','导入数据','upload','primary')}${!isLive?btn('reset-demo','载入演示数据','refresh'):''}</div></div>`;}
// ===================== 经营总览 · 图表组（2026-10-21）=====================
// 数据全部来自 currentRows()（部门切换即时联动）；SVG 纯静态标记，
// 入场动画交给 CSS（prefers-reduced-motion 下自动关闭）。
// 图表配色（10 色）：从蓝到紫的定性色板，结构类图表按顺序取色。
// 颜色只做区分不做评价，正负评价固定用绿（有利）/红（不利），保证同一屏内颜色语言不冲突。
const CHART_COLORS=['#2b6ef6','#06b6d4','#14b8a6','#22c55e','#f59e0b','#fb923c','#ef4444','#ec4899','#8b5cf6','#6366f1'];
// 把 undefined/NaN 统一成 0 再进图表，避免 NaN 让 SVG 坐标变成 "NaN" 而整块图消失。
const chartVal=v=>Number.isFinite(v)?v:0;
// 图表外框：标题 + 一句口径说明 + 图表主体，统一内边距与玻璃面板样式。
// 口径说明（meta）是硬要求：同一张图在不同主体下含义不同（比如部门口径只算成本费用）。
function chartPanel(title,meta,body,cls=''){
  return `<section class="panel chart-panel ${cls}"><div class="panel-head"><div><h2>${title}</h2><p class="meta">${meta}</p></div></div><div class="chart-body">${body}</div></section>`;
}
// 环图：用 stroke-dasharray 画弧（每段长度按占比 × 周长），负值取绝对值参与占比，
// 段间留 2.5 的空隙让相邻色块不糊在一起；悬停用原生 <title> 给出名称、数值与占比。
// 过滤掉 0 值项；全为 0 时显示“暂无可展示的构成数据”，不画空环。
// 中心显示合计与单位，右侧图例带数值和取整百分比（取整是为了图例宽度稳定）。
function donutChart(items,unit='万元',fmt=wan){
  const list=items.filter(x=>Math.abs(chartVal(x.value))>0);
  if(!list.length)return `<div class="chart-empty">暂无可展示的构成数据</div>`;
  const total=list.reduce((n,x)=>n+Math.abs(chartVal(x.value)),0)||1;
  const R=52,C=2*Math.PI*R;let acc=0;
  const segs=list.map((x,i)=>{
    const len=Math.abs(chartVal(x.value))/total*C;
    const seg=`<circle r="${R}" cx="70" cy="70" fill="none" stroke="${x.color}" stroke-width="17" stroke-dasharray="${Math.max(len-2.5,0.6)} ${C}" stroke-dashoffset="${-acc}" style="--i:${i}"><title>${esc(x.name)}：${fmt(chartVal(x.value))} ${unit}（${(Math.abs(chartVal(x.value))/total*100).toFixed(1)}%）</title></circle>`;
    acc+=len;return seg;
  }).join('');
  const legend=list.map((x,i)=>`<li style="--i:${i}"><i style="background:${x.color}"></i><span>${esc(x.name)}</span><b>${fmt(chartVal(x.value))}</b><em>${(Math.abs(chartVal(x.value))/total*100).toFixed(0)}%</em></li>`).join('');
  return `<div class="donut-wrap"><svg class="donut" viewBox="0 0 140 140" role="img" aria-label="构成占比"><g transform="rotate(-90 70 70)"><g class="donut-ring">${segs}</g></g><text x="70" y="67" text-anchor="middle" class="donut-num">${fmt(total)}</text><text x="70" y="85" text-anchor="middle" class="donut-cap">${unit}</text></svg><ul class="chart-legend">${legend}</ul></div>`;
}
// 差异驱动瀑布：起点是预算结余（收入预算 − 成本预算 − 费用预算），
// 每根柱子是一项科目差异的累计贡献，终点是实际结余。
// 收入差异按正号累加、成本费用差异取反（多花钱等于拉低结余），
// 前 4 项单独显示、其余合并为“其他科目”，避免柱子过多导致标签重叠；
// 纵轴范围覆盖所有柱子端点并保证 hi>lo（否则除以 0）；
// 底部固定说明“绿色＝正向贡献，红色＝负向拖累”，并给出合计差额。
function waterfallChart(){
  const rows=currentRows();
  if(!rows.length)return `<div class="chart-empty">暂无可展示的差异数据</div>`;
  const bySub=new Map();
  for(const r of rows){
    const v=chartVal(r.variance)*(r.module==='收入'?1:-1);
    if(v)bySub.set(r.subject,(bySub.get(r.subject)||0)+v);
  }
  const list=[...bySub.entries()].map(([name,v])=>({name,v})).filter(x=>x.v)
    .sort((a,b)=>Math.abs(b.v)-Math.abs(a.v));
  const top5=list.slice(0,4),rest=list.slice(4).reduce((n,x)=>n+x.v,0);
  const steps=rest?[...top5,{name:'其他科目',v:rest}]:top5;
  const start=sum(rows.filter(r=>r.module==='收入'),'budget')-sum(rows.filter(r=>r.module==='成本'),'budget')-sum(rows.filter(r=>r.module==='费用'),'budget');
  const items=[{name:'预算结余',from:0,to:start,kind:'total'}];
  let run=start;
  for(const s of steps){items.push({name:s.name,from:run,to:run+s.v,kind:s.v>=0?'up':'down'});run+=s.v;}
  items.push({name:'实际结余',from:0,to:run,kind:'end'});
  const W=560,H=252,L=48,R=14,T=22,B=46,vals=items.flatMap(x=>[x.from,x.to,0]);
  let lo=Math.min(...vals),hi=Math.max(...vals);if(hi===lo)hi=lo+1;
  const y=v=>T+(hi-v)/(hi-lo)*(H-T-B),step=(W-L-R)/items.length,bw=Math.min(44,step*.58);
  const bars=items.map((x,i)=>{
    const cx=L+step*i+step/2,y1=y(Math.max(x.from,x.to)),y2=y(Math.min(x.from,x.to));
    const h=Math.max(2,y2-y1);
    const color=x.kind==='up'?'#22c55e':x.kind==='down'?'#ef4444':x.kind==='end'?'#8b5cf6':'#2b6ef6';
    const ly=x.kind==='total'||x.kind==='end'?wan(x.to):(x.to-x.from>=0?'+':'')+wan(x.to-x.from);
    const link=i?`<line class="wf-link" x1="${cx-step+bw/2}" y1="${y(items[i-1].to)}" x2="${cx-bw/2}" y2="${y(items[i-1].to)}"/>`:'';
    return `<g class="wf-bar" style="--i:${i}">${link}<rect x="${cx-bw/2}" y="${y1}" width="${bw}" height="${h}" rx="5" fill="${color}"><title>${esc(x.name)}：${ly} 万元</title></rect><text x="${cx}" y="${y1-7}" text-anchor="middle" class="wf-val">${ly}</text><text x="${cx}" y="${H-24}" text-anchor="middle" class="wf-name">${esc(x.name.length>5?x.name.slice(0,5)+'…':x.name)}</text></g>`;
  }).join('');
  return `<svg class="chart wf" viewBox="0 0 ${W} ${H}" role="img" aria-label="差异驱动瀑布：从预算结余到实际结余">${bars}</svg><div class="chart-foot"><span>绿色＝正向贡献，红色＝负向拖累；合计 ${wan(run-start)} 万元</span></div>`;
}
// 科目排行：按差额绝对值取前 n 项，横向条形图。
// 左列科目名超 9 字截断加省略号（保留可比对的前缀），条尾标数值并同色，
// 纵轴不需要刻度——这里比的是排序，读者只需要相对长度与具体数字。
function topVarianceChart(n=8){
  const rows=currentRows(),bySub=new Map();
  for(const r of rows){const v=chartVal(r.variance);if(v)bySub.set(r.subject,(bySub.get(r.subject)||0)+v);}
  const list=[...bySub.entries()].map(([name,v])=>({name,v}))
    .sort((a,b)=>Math.abs(b.v)-Math.abs(a.v)).slice(0,n);
  if(!list.length)return `<div class="chart-empty">暂无可展示的差异</div>`;
  const W=560,rowH=31,H=list.length*rowH+24,L=140,R=84;
  const max=Math.max(...list.map(x=>Math.abs(x.v)))||1;
  const bars=list.map((x,i)=>{
    const y=10+i*rowH,w=Math.max(3,(Math.abs(x.v)/max)*(W-L-R));
    const color=x.v>=0?'#22c55e':'#ef4444';
    return `<g class="bar-row" style="--i:${i}"><text x="${L-10}" y="${y+14}" text-anchor="end" class="bar-name">${esc(x.name.length>9?x.name.slice(0,9)+'…':x.name)}</text><rect x="${L}" y="${y+3}" width="${w}" height="15" rx="7.5" fill="${color}" opacity=".92"><title>${esc(x.name)}：${wan(x.v)} 万元</title></rect><text x="${L+w+8}" y="${y+15}" class="bar-val" style="fill:${color}">${x.v>=0?'+':''}${wan(x.v)}</text></g>`;
  }).join('');
  return `<svg class="chart bars" viewBox="0 0 ${W} ${H}" role="img" aria-label="差异最大的科目">${bars}</svg><div class="chart-foot"><span>按差额绝对值排序 · 单位万元</span></div>`;
}
// 量价拆分：把“原标准总差异”拆成规划差异（不可控）与执行差异（可控），
// 再细分价格/用量的规划与执行四项。接口没给数据时提示需要带「量价拆分」表的工作簿。
// 四项细分存在交叉残差，因此底部明确写“以总量为准”，避免用户把四项相加后与总量对不上而误判。
// 恒等式异常（identityOk===false）时打“恒等式异常”标记，提示数据本身有问题。
function liangjiaChart(){
  const sp=S.data.splits;
  if(!sp||!sp.length)return `<div class="chart-empty">暂无量价拆分数据（需带「量价拆分」表的实时经营工作簿）</div>`;
  const hang=sp.map((x,i)=>{
    const fu=v=>Number.isFinite(v)?`${v>=0?'+':''}${wan(v)}`:'—';
    const se=(v,fa)=>!Number.isFinite(v)?'':(fa==='F'?'#22c55e':fa==='A'?'#ef4444':'#94a3b8');
    return `<div class="lj-row" style="--i:${i}">
      <div class="lj-head"><b>${esc(x.subject)}</b><span class="muted">${esc(x.period||'')}</span>${x.identityOk===false?'<span class="jimu-fa a">恒等式异常</span>':''}</div>
      <div class="lj-grid">
        <div class="lj-cell"><span>原标准总差异</span><b style="color:${se(x.total,x.totalFa)}">${fu(x.total)}</b></div>
        <div class="lj-cell gui"><span>规划差异（不可控）</span><b style="color:${se(x.planning,x.planningFa)}">${fu(x.planning)}</b></div>
        <div class="lj-cell zhi"><span>执行差异（可控）</span><b style="color:${se(x.execution,x.executionFa)}">${fu(x.execution)}</b></div>
      </div>
      <div class="lj-fine">
        <span>价格规划 ${fu(x.pricePlanning)}</span><span>价格执行 ${fu(x.priceExecution)}</span>
        <span>用量规划 ${fu(x.usagePlanning)}</span><span>用量执行 ${fu(x.usageExecution)}</span>
        <span class="muted">残差 ${fu(x.residual)}</span>
      </div>
    </div>`;
  }).join('');
  return `<div class="lj-wrap">${hang}<div class="chart-foot"><span>总量恒等式：原标准总差异 = 规划 + 执行 · 单位万元 · 细分四项含交叉残差，以总量为准</span></div></div>`;
}
// 积木拆解：收入/成本/费用/采购四个模块固定全列（无数据也显示 0，保持版式稳定），
// 条长按模块净差额绝对值相对最大值缩放，比例用基点换算成百分比。
// “未归属”行单独列出（存在行数时才显示），提示还有科目没映射到模块；
// 底部给净总差异、核心问题模块，并说明占比分母是各模块净差额绝对值之和。
function jimuChart(){
  const b=S.data.blocks;
  if(!b||!b.modules)return `<div class="chart-empty">暂无积木拆解数据（先运行分析）</div>`;
  const mo=b.modules.map((m,i)=>({...m,i}));   // 四模块固定全列（无数据行显示 0）
  if(!mo.length)return `<div class="chart-empty">暂无积木拆解数据（先运行分析）</div>`;
  const max=Math.max(...mo.map(m=>Math.abs(chartVal(m.variance))),1);
  const faTag=m=>m.fa==='F'?`<span class="jimu-fa f">有利</span>`:m.fa==='A'?`<span class="jimu-fa a">不利</span>`:`<span class="jimu-fa">—</span>`;
  const bars=mo.map(m=>{
    const w=m.variance?Math.max(3,Math.abs(chartVal(m.variance))/max*100):0;
    const col=m.fa==='F'?'#22c55e':m.fa==='A'?'#ef4444':'#94a3b8';
    const bps=Number.isFinite(m.ratioBps)?(m.ratioBps/100).toFixed(1)+'%':'—';
    return `<div class="jimu-row${b.core===m.name?' core':''}" style="--i:${m.i}">
      <span class="jimu-name">${esc(m.name)}${b.core===m.name?`<em class="jimu-core">核心</em>`:''}</span>
      <span class="jimu-bar"><i style="width:${w}%;background:${col}"></i></span>
      <b class="jimu-amount" style="color:${col}">${m.variance>=0?'+':''}${wan(m.variance)}</b>
      <span class="jimu-ratio">${bps}</span>
      <span class="jimu-rows">${m.rows} 行</span>
      ${faTag(m)}
    </div>`;
  }).join('');
  const weiRow=b.unassignedRows?`<div class="jimu-row unassigned" style="--i:9">
      <span class="jimu-name">未归属</span>
      <span class="jimu-bar"><i style="width:${Math.min(100,Math.abs(chartVal(b.unassigned))/max*100)}%;background:#94a3b8"></i></span>
      <b class="jimu-amount">${b.unassigned>=0?'+':''}${wan(b.unassigned)}</b>
      <span class="jimu-ratio">${Number.isFinite(b.unassignedBps)?(b.unassignedBps/100).toFixed(1)+'%':'—'}</span>
      <span class="jimu-rows">${b.unassignedRows} 行</span>
      <span class="jimu-fa">待映射</span>
    </div>`:'';
  return `<div class="jimu-wrap">${bars}${weiRow}
    <div class="jimu-foot"><span>净总差异 <b>${wan(b.netTotal)}</b> 万元</span>${b.core?`<span>核心问题模块 <b>${esc(b.core)}</b></span>`:'<span>当前无不利模块</span>'}<span class="muted">占比分母 Σ|模块净差额|</span></div>
  </div>`;
}
// 预警分布环图：高风险/需关注/正常三档的差异行数。
// 复用 donutChart 并传“项”为单位、整数格式（行数是计数，不能显示万元或小数）。
function riskRing(){
  const rows=currentRows();
  const gao=rows.filter(r=>r.risk==='high').length;
  const guan=rows.filter(r=>r.risk==='watch').length;
  const zheng=rows.filter(r=>r.risk==='normal').length;
  return donutChart([
    {name:'高风险',value:gao,color:'#ef4444'},
    {name:'需关注',value:guan,color:'#f59e0b'},
    {name:'正常',value:zheng,color:'#22c55e'}],'项',v=>String(Math.round(v)));
}
// 月度差异热力图：行为科目（按累计绝对差异取前 8），列为期间（升序），
// 格子颜色按差额正负取绿/红，透明度随 |差额|/最大值 递增，无数据显示接近透明的灰。
// 行标签超 9 字截断；底部图例说明颜色深浅代表差额大小，避免被误读成“风险等级”。
function heatmapChart(){
  const rows=currentRows();
  const periods=[...new Set(rows.map(r=>r.period))].filter(Boolean).sort();
  if(!periods.length)return `<div class="chart-empty">暂无月度数据</div>`;
  const zong=new Map();
  for(const r of rows)zong.set(r.subject,(zong.get(r.subject)||0)+Math.abs(chartVal(r.variance)));
  const subs=[...zong.entries()].sort((a,b)=>b[1]-a[1]).slice(0,8).map(x=>x[0]);
  const map=new Map();for(const r of rows)map.set(`${r.subject}|${r.period}`,chartVal(r.variance));
  let max=0;for(const s of subs)for(const p of periods)max=Math.max(max,Math.abs(map.get(s+'|'+p)||0));
  max=max||1;
  const cw=Math.max(24,Math.floor(520/Math.max(1,periods.length))),ch=26,L=134,T=20,W=L+cw*periods.length+8,H=T+ch*subs.length+14;
  const cells=subs.map((s,ri)=>periods.map((p,ci)=>{
    const v=map.get(s+'|'+p);const n=Math.abs(chartVal(v))/max;
    const col=v>0?'34,197,94':v<0?'239,68,68':'148,163,184';
    return `<rect class="heat-cell" x="${L+ci*cw+1.5}" y="${T+ri*ch+1.5}" width="${cw-3}" height="${ch-3}" rx="5" fill="rgba(${col},${v==null?0.04:(0.10+n*0.78).toFixed(2)})" style="--i:${ri*periods.length+ci}"><title>${esc(s)} ${esc(p)}：${v==null?'无数据':((v>=0?'+':'')+wan(v)+' 万元')}</title></rect>`;
  }).join('')+`<text x="${L-10}" y="${T+ri*ch+17}" text-anchor="end" class="bar-name">${esc(s.length>9?s.slice(0,9)+'…':s)}</text>`).join('');
  const months=periods.map((p,ci)=>`<text x="${L+ci*cw+cw/2}" y="${T-7}" text-anchor="middle" class="heat-cap">${esc(p.slice(-2))}</text>`).join('');
  return `<svg class="chart heat" viewBox="0 0 ${W} ${H}" role="img" aria-label="科目月度差异热力图">${months}${cells}</svg><div class="chart-foot"><span><i class="heat-dot" style="background:rgba(239,68,68,.85)"></i> 不利差异 <i class="heat-dot" style="background:rgba(34,197,94,.85);margin-left:14px"></i> 有利差异 · 颜色深浅＝差额大小</span></div>`;
}
// 部门对比柱图：只在存在至少两个“公司/部门”命名的主体时展示，
// 数值取各部门非收入模块的实际金额合计（费用中心口径，收入留在公司级）。
// 全为 0 时返回空串（由调用方给出提示），避免出现一排贴底的空柱子。
function deptBars(){
  const deps=S.data.entities.filter(e=>e.id!=='all'&&String(e.title||'').includes('/'));
  if(deps.length<2)return '';
  const rows=S.data.rows;
  const data=deps.map((e,i)=>({name:e.name,value:rows.filter(r=>r.departmentId===e.id&&r.module!=='收入').reduce((n,r)=>n+Math.abs(chartVal(r.actual)),0),color:CHART_COLORS[i%CHART_COLORS.length]}));
  if(data.every(x=>!x.value))return '';
  const W=560,H=250,L=44,R=14,T=22,B=52,max=Math.max(...data.map(x=>x.value))||1;
  const step=(W-L-R)/data.length,bw=Math.min(56,step*.55);
  const bars=data.map((x,i)=>{
    const h=Math.max(3,(x.value/max)*(H-T-B)),cx=L+step*i+step/2,y=T+(H-T-B)-h;
    return `<g class="dept-bar" style="--i:${i}"><rect x="${cx-bw/2}" y="${y}" width="${bw}" height="${h}" rx="8" fill="${x.color}"><title>${esc(x.name)}：${wan(x.value)} 万元</title></rect><text x="${cx}" y="${y-8}" text-anchor="middle" class="wf-val">${wan(x.value)}</text><text x="${cx}" y="${H-26}" text-anchor="middle" class="wf-name">${esc(x.name)}</text></g>`;
  }).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="各部门本期成本费用">${bars}</svg><div class="chart-foot"><span>本期成本费用（万元，费用中心口径）· 收入留公司级</span></div>`;
}
// 图表类型表：[键, 中文名]。“部门”一项只有满足部门口径时才可用（见 chartBoard 过滤），
// 顺序即切换器的按钮顺序。
const CHART_KINDS=[['trend','走势'],['waterfall','瀑布'],['jimu','积木'],['liangjia','量价'],['top','科目排行'],['structure','结构'],['risk','预警'],['heat','热力'],['dept','部门']];
// 图表标题与口径说明：走势图的标题随口径变化（公司看收入、部门看成本费用），
// 其余图表各给一句“看什么”的说明。新增图表必须在这里补一条，否则标题为 undefined。
function chartDesc(kind){
  return {
    trend:buMenShiTu()?['成本费用与预算走势','当前部门费用中心口径；收入留在公司级']:['收入与预算走势','全公司年度口径'],
    waterfall:['差异驱动','从预算结余走到实际结余，看谁在拉高或拖低'],
    top:['差异最大的科目','按差额绝对值排序的前八项'],
    structure:['差异结构','各模块贡献的差异金额占比'],
    jimu:['积木拆解','四模块差异聚合（收入/成本/费用/采购）+ 未归属 + 净总差异'],
    liangjia:['量价拆分','规划差异（不可控）与执行差异（可控）分解 + 价格/用量四项细分'],
    risk:['预警分布','按风险档位统计的差异行数'],
    heat:['月度差异热力','颜色越深＝该科目当月偏差越大'],
    dept:['部门对比','各部门本期成本费用（万元）']
  }[kind];
}
// 图表分发：把类型键映射到具体渲染函数；“结构”在本地按模块聚合差额后复用环图，
// 未匹配的类型统一回落到走势图（保证任何异常状态都有内容可显示）。
function chartBody(kind){
  if(kind==='waterfall')return waterfallChart();
  if(kind==='top')return topVarianceChart();
  if(kind==='structure'){
    const mo=new Map();
    for(const r of currentRows()){const m=r.module||'其他';mo.set(m,(mo.get(m)||0)+Math.abs(chartVal(r.variance)));}
    return donutChart([...mo.entries()].map(([name,v],i)=>({name:name==='收入'?'收入模块':name==='成本'?'成本模块':name==='费用'?'费用模块':name,value:v,color:CHART_COLORS[i%CHART_COLORS.length]})));
  }
  if(kind==='jimu')return jimuChart();
  if(kind==='liangjia')return liangjiaChart();
  if(kind==='risk')return riskRing();
  if(kind==='heat')return heatmapChart();
  if(kind==='dept')return deptBars()||`<div class="chart-empty">部门对比需要至少两个部门（工作簿主体名称写成「公司/部门」）</div>`;
  return trendChart();
}
// 图表面板：类型切换器 + 当前图表。切换器用 role=tablist/tab + aria-selected，
// 只保留在当前口径下合法的类型（部门图需要至少两个部门），
// 若当前 chartType 已不合法则回落到 trend——避免切主体后看到一张空白图。
function chartBoard(){
  const youBuMen=S.data.entities.filter(e=>e.id!=='all'&&String(e.title||'').includes('/')).length>=2;
  const ke=CHART_KINDS.filter(([k])=>k!=='dept'||youBuMen);
  const dang=ke.some(([k])=>k===S.chartType)?S.chartType:'trend';
  const [biaoti,shuoming]=chartDesc(dang);
  const qie=ke.map(([k,m])=>`<button class="chart-tab${k===dang?' active':''}" type="button" role="tab" aria-selected="${k===dang}" data-action="chart" data-chart="${k}">${m}</button>`).join('');
  return `<section class="panel"><div class="panel-head chart-head"><div><h2>${biaoti}</h2><p class="meta">${shuoming}</p></div></div><div class="chart-tabs" role="tablist" aria-label="切换图表类型">${qie}</div><div class="chart-body">${chartBody(dang)}</div></section>`;
}


// 经营总览：未就绪时只显示页头与空状态；就绪时依次是摘要卡、
// 「图表 + 本期待处理」两栏（右侧最多列 3 条非正常差异，可点进详情）、
// 以及折叠为紧凑模式的差异明细表。页面副标题交代当前期间、主体与更新时间。
function overview(){
  if(!isReady())return heading('经营总览','从预算与实际之间，找到经营变化的原因。',standardActions())+empty();
  const risks=currentRows().filter(r=>r.risk!=='normal').sort((a,b)=>Math.abs(b.variance)-Math.abs(a.variance));
  return `${heading('经营总览',`${esc(periodLabel(S.data.meta.period))} · ${esc(entityName())} · 更新于 ${date(S.data.meta.generatedAt)} ${time(S.data.meta.generatedAt)}`,standardActions())}${summary()}
  <div class="overview-grid">${chartBoard()}<section class="panel"><div class="panel-head"><div><h2>本期待处理</h2><p class="meta">先关注对经营影响最大的差异</p></div><button class="text-btn" data-action="nav" data-page="risks">全部 ${icon('chevron')}</button></div><div class="risk-list">${risks.slice(0,3).map(r=>`<div class="risk-row"><div class="risk-marker ${esc(r.risk)}">${icon(r.risk==='high'?'flag':'clock')}</div><div class="grow"><h3><button class="subject-button text-btn" style="color:inherit;font-size:12px" data-action="detail" data-id="${esc(r.id)}">${esc(r.subject)}</button></h3><p>${esc(r.department)} · ${esc(r.decision)}</p></div><div style="text-align:right">${tag(rate(r.rate),r.risk)}<p style="font-size:10px;color:var(--muted);margin-top:6px">${r.direction==='favorable'?'有利':'不利'}差异</p></div></div>`).join('')||'<div class="empty-column">本期没有触发预警的差异</div>'}</div><div class="risk-footer">${icon('spark')}选中差异，可让衡策助手解释原因 ${icon('arrow')}</div></section></div>
  <section class="panel"><div class="panel-head"><div><h2>差异明细</h2><p class="meta">预算与实际对照，按差额绝对值排序</p></div><button class="text-btn" data-action="nav" data-page="analysis">查看全部明细 ${icon('chevron')}</button></div>${tableSection(true)}</section>`;
}
// 是否处于“部门视角”：选了具体部门且该主体的 title 含「/」（工作簿用「公司/部门」表示费用中心）。
// 这个判断决定趋势图、摘要卡与提示文案的口径，集中在这里避免各处判断写法不一致。
function buMenShiTu(){
  const e=S.data.entities.find(x=>x.id===S.entity);
  return S.entity!=='all'&&String((e||{}).title||'').includes('/');
}
// 趋势数据：公司视角直接用插件给的 trend（含滚动预测）；
// 部门视角按当前部门的非收入模块逐月聚合预算与实际，期间取数据里出现过的月份升序。
// 部门没有滚动预测，因此返回行里不带 rolling 字段，图表自然不画虚线。
function trendData(){
  // 部门是费用中心：按当前部门的成本费用逐月聚合；公司视图沿用后端趋势（含滚动预测）
  if(!buMenShiTu())return {rows:S.data.trend||[],buMen:false};
  const rows=currentRows().filter(r=>r.module!=='收入');
  const qi=[...new Set(rows.map(r=>r.period))].filter(Boolean).sort();
  const he=(p,k)=>{const x=rows.filter(r=>r.period===p);return x.length?x.reduce((n,r)=>n+chartVal(r[k]),0):null;};
  return {buMen:true,rows:qi.map(p=>({period:p,budget:he(p,'budget'),actual:he(p,'actual')}))};
}
// 坐标细节：SVG 用 viewBox 做等比缩放，左右留 56px 给纵轴数字、上下各 14px 防止描边被裁；
// 网格线取 4 条等分线，刻度值经 wan 转成万元；面积用线性渐变从 24% 透明度淡出到 0，
// 这样预算线与实际线重叠时仍能看清线本身；横轴标签过多时按每 2 个取 1 个显示，避免文字挤在一起。
// 收入/成本费用趋势：预算（琥珀实线）、实际（渐变实线 + 面积）、滚动预测（青色虚线）。
// 纵轴自适应：按数据跨度取 1/2/2.5/5 的整齐刻度并上下留 12% 余量（固定刻度会让小数据贴底）；
// 负数时纵轴下限取到 0 以下；“滚动预测”用浅底色块标出来，避免被误读成实际值；
// 每个实际值点都是可聚焦的 chart-point，点击/回车打开该期间的数据表。
function trendChart(){
  const {rows:data,buMen}=trendData(),W=680,H=246,left=48,right=22,top=22,bottom=38;
  const values=data.flatMap(t=>[t.budget,t.actual,t.rolling]).filter(Number.isFinite);
  if(!data.length||!values.length)return `<div class="empty-state" style="padding:48px 24px">${icon('chart')}<h2>暂无趋势数据</h2><p>收到当前分析的期间序列后，收入趋势会显示在这里。</p></div>`;
  // 纵轴自适应：按数据跨度取 1/2/2.5/5 的整齐刻度，上下留 12% 余量（原实现固定 400 万起，数据小时线贴底）
  const rawMax=Math.max(...values),rawMin=Math.min(...values);
  const nice=v=>{const e=Math.pow(10,Math.floor(Math.log10(Math.max(Math.abs(v),1)))),f=Math.abs(v)/e;return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*e;};
  const pad=Math.max((rawMax-rawMin)*0.12,Math.abs(rawMax)*0.02,1);
  const ji=nice((rawMax+pad-Math.min(0,rawMin))/4)||1;
  const max=Math.ceil((rawMax+pad)/ji)*ji,min=Math.floor(Math.min(0,rawMin)/ji)*ji;
  const yTicks=[];for(let v=min;v<=max+ji/2;v+=ji)yTicks.push(v);
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
  return `<div class="legend trend-legend">${buMen?'<span><i></i>实际费用</span><span><i class="budget"></i>预算费用</span>':'<span><i></i>实际收入</span><span><i class="budget"></i>原始预算</span><span><i class="rolling"></i>滚动预测</span>'}</div><div class="panel-body" style="padding-bottom:0"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${buMen?'成本费用趋势。实线为实际费用，琥珀线为预算费用。':'收入趋势。实线为实际收入，琥珀线为预算，虚线为滚动预测；下方可查看完整数据表。'}"><defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2864e7" stop-opacity=".12"/><stop offset="100%" stop-color="#2864e7" stop-opacity="0"/></linearGradient><linearGradient id="line-grad" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#2b6ef6"/><stop offset="55%" stop-color="#06b6d4"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient></defs>${forecastStart>=0&&forecastStart<data.length?`<rect x="${x(forecastStart)-12}" y="${top}" width="${Math.max(0,W-right-x(forecastStart)+12)}" height="${H-top-bottom}" fill="#fafbfd"/><text x="${x(forecastStart)}" y="${top+12}" style="font-size:9px">滚动预测</text>`:''}${yTicks.map(v=>`<line class="grid" x1="${left}" x2="${W-right}" y1="${y(v)}" y2="${y(v)}"/><text x="${left-12}" y="${y(v)+3}" text-anchor="end">${(v/1000000).toLocaleString('zh-CN',{maximumFractionDigits:ji<1000000?2:0})}</text>`).join('')}<text x="${left}" y="10" style="font-size:9px">万元</text><path d="${area}" fill="url(#area-fill)"/><path d="${path('budget')}" fill="none" stroke="#f59e0b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="${forecast}" fill="none" stroke="#14b8a6" stroke-width="2" stroke-dasharray="4 5"/><path class="chart-line" d="${actualPath}" fill="none" stroke="url(#line-grad)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" pathLength="100"/>${data.map((t,i)=>`<text x="${x(i)}" y="${H-14}" text-anchor="middle">${esc(label(t.period))}</text>${Number.isFinite(t.actual)?`<g class="chart-point" tabindex="0" data-action="trend-detail" data-index="${i}" role="button" aria-label="${esc(t.period)}实际收入${money(t.actual)}元，查看数据"><circle cx="${x(i)}" cy="${y(t.actual)}" r="3.5" fill="white" stroke="#2864e7" stroke-width="2"/><title>${esc(t.period)}：预算 ${money(t.budget)} 元；实际 ${money(t.actual)} 元</title></g>`:''}`).join('')}</svg></div><div class="chart-foot"><span>${buMen?(last>=0?`该部门 ${esc(data[last].period)} 及以前已结账 · 费用中心口径`:'尚无已结账实际数据'):(last>=0?`截至 ${esc(data[last].period)} 已结账`:'尚无已结账实际数据')+' · 预测不计入实际发生额'}</span><button class="text-btn" data-action="trend-detail">查看数据表 ${icon('chevron')}</button></div>`;
}
// 差异表外壳：模块标签页（带当前口径行数）、搜索框、预警档位选择、导出按钮，
// 下面才是表格本体。compact 模式用在经营总览，去掉导出按钮并减少外层留白。
// 搜索与筛选只重绘表格区域（见 bindForms），不整页重绘，保住输入焦点。
function tableSection(compact=false){return `<div class="tabs" aria-label="模块筛选">${['全部','收入','成本','费用','采购'].map(name=>`<button class="tab ${S.module===name?'active':''}" data-action="module" data-value="${name}" aria-pressed="${S.module===name}">${name}${name==='全部'?`<span class="tab-count">${currentRows().length}</span>`:''}</button>`).join('')}</div><div class="table-tools"><label class="search-field">${icon('search')}<input id="row-search" type="search" placeholder="搜索科目或部门" value="${esc(S.search)}" aria-label="搜索科目或部门"></label><select class="filter-select" id="risk-filter" aria-label="筛选预警等级">${[['all','全部预警等级'],['high','高风险'],['watch','关注'],['normal','正常']].map(([v,n])=>`<option value="${v}" ${S.risk===v?'selected':''}>${n}</option>`).join('')}</select><div class="right"><span class="small muted">单位：元</span>${!compact?btn('export-table','导出明细','download','small'):''}</div></div><div id="variance-table">${varianceTable(compact)}</div>`;}
// 差异明细表：先取 visibleRows，再按每页 5 行分页（页码越界时自动夹回合法范围）。
// 数值列统一 class="numeric" 右对齐并用等宽数字，差额与差异率按有利/不利上色；
// “差额”列头是可点的排序按钮，排序状态用箭头图标表示；
// 末列箭头按钮进入详情（抽屉式弹窗）。无结果时给一行跨列提示而不是空表。
function varianceTable(compact=false){
  const all=visibleRows(),size=5;
  const pages=Math.max(1,Math.ceil(all.length/size));
  const page=Math.min(Math.max(1,S.pageNo||1),pages);S.pageNo=page;
  const rows=all.slice((page-1)*size,page*size);
  const yejiao=pages>1?`<span class="pager"><button class="text-btn" data-action="page" data-value="${page-1}" ${page<=1?'disabled':''}>上一页</button><span class="pager-info">第 ${page} / ${pages} 页</span><button class="text-btn" data-action="page" data-value="${page+1}" ${page>=pages?'disabled':''}>下一页</button></span>`:'<span>绿：有利 · 红：不利 · 差额 = 实际 − 预算</span>';
return `<div class="table-scroll"><table><thead><tr><th>科目 / 所属部门</th><th>期间</th><th>模块</th><th class="numeric">预算金额</th><th class="numeric">实际金额</th><th class="numeric"><button class="sort-button" data-action="sort">差额 ${icon(S.ascending?'up':'down')}</button></th><th class="numeric">差异率</th><th>预警</th><th style="width:48px"></th></tr></thead><tbody>${rows.map(r=>`<tr><td><button class="subject-button" data-action="detail" data-id="${esc(r.id)}">${esc(r.subject)}</button><span class="sub">${esc(r.department)}</span></td><td class="period-cell">${esc(r.period)}</td><td><span class="module-dot"></span>${esc(r.module)}</td><td class="numeric">${money(r.budget)}</td><td class="numeric">${money(r.actual)}</td><td class="numeric ${r.direction==='favorable'?'positive':'negative'}">${r.variance>0?'+':''}${money(r.variance)}</td><td class="numeric ${r.direction==='favorable'?'positive':'negative'}">${rate(r.rate)}</td><td>${riskTag(r)}</td><td><button class="icon-btn" data-action="detail" data-id="${esc(r.id)}" aria-label="查看${esc(r.subject)}详情">${icon('chevron')}</button></td></tr>`).join('')||'<tr><td colspan="9" style="text-align:center;padding:40px;color:var(--muted)">没有符合条件的科目。试试其他关键词或预警等级。</td></tr>'}</tbody></table></div><div class="table-bottom"><span>共 ${all.length} 项差异${pages>1?` · 每页 ${size} 项`:""}</span>${yejiao}</div>`;}
// 数值口径细节：财务指标里“收入达成率/销售毛利率/费用收入比”等百分比项在快照里是基点，
// 非财务指标“客户续约率”同样是基点但可能为 null；单位为“天”的交付周期与单位为“次”的异常事项数量
// 在快照里就是原始计数，不经过 rate()。每项都带 periods 数组（至少 3 期）供详情里画迷你走势，
// 缺失期用 null 占位而不是 0，避免把“没统计”画成“降到零”。
// 经营指标：15 项按财务 9 项 / 非财务 6 项分两组展示。
// 接口没给值（null）时显示“待补充 / 需相应输入（不虚构）”，绝不填 0 或估算值；
// 单位按指标性质区分：百分比指标入参是基点（÷100 显示两位小数），
// 交付周期按天、异常事项数量按次，这两项不做百分比换算。
function kpiGroups(){
  // 15 项按 财务 9 / 非财务 6 分组；单位：% 基点、天、次（异常/交付周期非百分比）
  const CAI=['营收达成率','成本控制率','费用偏差率','毛利率','净利润率','销售利润率','资产周转率','资金周转率','采购成本变动率'];
  const FEI=['供应链履约率','产能利用率','交付周期','客户满意度','业务完成进度','异常事项数量'];
  const zhi=k=>{const x=S.data.kpis.find(i=>i.name===k);
    if(!x||x.value==null)return null;
    if(k==='交付周期')return {v:(x.value/1).toFixed(1),u:'天'};
    if(k==='异常事项数量')return {v:String(x.value),u:'次'};
    return {v:(x.value/100).toFixed(2),u:'%'};
  };
  const ka=(lie)=>lie.map(k=>{const z=zhi(k);
    return `<div class="source-box kpi-card${z?'':' lack'}" style="margin:0"><div class="small">${k}</div><strong class="num" style="font-size:22px;color:var(--ink)">${z?`${z.v}<small style="font-size:11px;margin-left:3px">${z.u}</small>`:'待补充'}</strong><p class="small muted">${z?'':'需相应输入（不虚构）'}</p></div>`;}).join('');
  return `<div class="kpi-group"><h3>财务指标 <span>9 项</span></h3><div class="form-grid">${ka(CAI)}</div></div>
    <div class="kpi-group"><h3>非财务指标 <span>6 项</span></h3><div class="form-grid">${ka(FEI)}</div>
    <p class="inline-help">非财务指标来自实时经营工作簿的「非财务指标」表（六项固定行）；未提供时如实缺数。</p></div>`;
}
// 差异分析页：未就绪时给空状态；就绪时是摘要卡 + 差异表 + 经营指标面板。
// 页头多一个“分析设置”入口；指标区标注当前是否为全公司口径（部门视角下指标仍按全公司给）。
function analysisPage(){return `${heading('差异分析','沿着科目与部门下钻，找到每一笔偏差的来源。',`${btn('settings','分析设置','settings')}${standardActions()}`)}${isReady()?`${summary()}<section class="panel">${tableSection()}</section><div class="section-spacer panel"><div class="panel-head"><h2>经营指标</h2><span class="small muted">${S.entity==='all'?'全公司口径':'指标仍为全公司口径'}</span></div><div class="panel-body">${kpiGroups()}</div></div>`:empty()}`;}
// 数据工作区：按四类（预算基础/实时经营/行业对标/经营变更）展示上传卡片，
// 每张卡片给类别说明、必需/选填标签、已校验文件数与行数，以及“选择工作簿”“空白模板”两个入口。
// 下方是拖放区与本次工作簿表；清空全部只移除工作区文件，历史运行记录保留。
// 演示模式额外给“载入演示数据”，真实模式不给。
function dataPage(){
  const categories=[['预算基础','全年预算是所有分析的起点。','必需'],['实时经营','已结账期间的实际经营数据。','必需'],['行业对标','为行业修正提供可核对的参考。','选填'],['经营变更','记录影响预算假设的经营事项。','选填']];
  return `${heading('数据工作区','按主体与情景整理工作簿，校验通过后开始分析。',`${!isLive?btn('reset-demo','载入演示数据','refresh'):''}${btn('import','导入工作簿','plus','primary')}`)}<div class="data-completeness">${icon(canAnalyze(S.data)?'circleCheck':'clock')}<div class="grow"><h2>${canAnalyze(S.data)?'分析所需的两类数据已就绪':'准备本次分析的数据'}</h2><p>${S.data.files.filter(f=>f.status==='valid').length} 份工作簿校验通过${S.data.files.some(f=>f.status==='pending')?' · 有本地文件待校验':''}</p></div>${btn('run','开始分析','play','',S.busy?'disabled':'')}</div><div class="data-grid">${categories.map(([name,description,required])=>{const files=S.data.files.filter(f=>f.category===name),valid=files.filter(f=>f.status==='valid');return `<section class="data-card"><div class="data-card-top"><div class="file-symbol">${icon('file')}</div><div class="grow"><h2>${name}</h2><p>${description}</p></div>${tag(required,required==='必需'?'blue':'neutral')}</div><p>${valid.length?`${icon('circleCheck')} <span class="positive">已校验 ${valid.length} 份</span> · ${valid.reduce((a,f)=>a+f.rows,0)} 行数据`:'尚无校验通过的文件'}</p><div class="data-actions">${btn('choose-files',files.length?'追加工作簿':'选择工作簿','plus','small',`data-category="${name}"`)}<button class="text-btn" data-action="template" data-category="${name}">${icon('download')}空白模板</button></div></section>`;}).join('')}</div><div class="dropzone" id="dropzone">${icon('upload')}<strong>拖拽工作簿到这里</strong>，或<button class="text-btn" data-action="choose-files">选择文件</button><p class="small" style="margin-top:8px">支持四类标准 .xlsx 工作簿，单文件不超过 28 MB</p></div><section class="panel"><div class="panel-head"><h2>本次工作簿</h2><span class="small muted">${S.data.files.length} 份文件</span>${S.data.files.length?`<button class="text-btn danger" data-action="clear-all" style="margin-left:auto" title="移除全部已导入工作簿，历史运行保留">${icon('trash')}清空全部</button>`:''}</div><div class="table-scroll"><table><thead><tr><th>文件名</th><th>数据类别</th><th>校验状态</th><th>数据行数</th><th></th></tr></thead><tbody>${S.data.files.map(f=>`<tr><td><div class="file-name">${icon('file')}<div>${esc(f.name)}<span class="sub">${esc(f.entity)} · ${typeof f.size==='number'?`${(f.size/1024).toFixed(1)} KB`:esc(f.size)}</span></div></div></td><td>${esc(f.category)}</td><td>${tag(f.status==='valid'?`${f.checks} 项通过`:'待校验',f.status==='valid'?'normal':'watch')}</td><td class="num">${f.status==='valid'?f.rows:'—'}</td><td><div class="actions-inline"><button class="text-btn" data-action="file-detail" data-id="${esc(f.id)}">详情</button><button class="icon-btn" data-action="remove-file" data-id="${esc(f.id)}" aria-label="移除${esc(f.name)}">${icon('trash')}</button></div></td></tr>`).join('')||'<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--muted)">还没有导入工作簿</td></tr>'}</tbody></table></div></section><section class="panel background-box"><div class="panel-head"><h2>本期经营背景</h2>${tag(S.data.background.changeStatus==='yes'?'有经营变更':S.data.background.changeStatus==='none'?'无经营变更':'待确认')}</div><div class="panel-body"><p>${esc(S.data.background.text||'补充宏观环境或特殊事项，帮助理解本期经营变化。背景说明不替代经营变更台账。')}</p>${btn('background','编辑背景','settings')}</div></section>`;
}
// 风险与整改：单双环判定汇总（单环改执行、双环改预算、混合、复核）、
// 三张风险摘要、三列整改看板（待处理/进行中/已完成）、以及纠错判定明细表。
// 判定说明写清“单环＝修正执行行为，双环＝修订预算方案本身”，
// 明细表里双环/混合纠错行的主按钮是“提请修订”，其余是“查看详情”。
function riskPage(){
  const relatedIds=new Set(currentRows().map(r=>r.id)),actions=S.data.actions.filter(a=>relatedIds.has(a.rowId));
  const huanlu=()=>{
    const rows=currentRows();
    const dan=rows.filter(r=>String(r.decision).includes('单环')).length;
    const shuang=rows.filter(r=>String(r.decision).includes('双环')).length;
    const hun=rows.filter(r=>String(r.decision).includes('混合')).length;
    const fuhe=rows.filter(r=>String(r.decision).includes('复核')).length;
    if(!dan&&!shuang&&!hun&&!fuhe)return '';
    return `<section class="panel huanlu-panel"><div class="panel-head"><div><h2>单双环判定</h2><p class="meta">单环＝修正执行行为；双环＝修订预算方案本身；混合＝两者并行；复核＝信息不足先核实</p></div></div><div class="huanlu-grid">
      <div class="huanlu-cell dan"><span class="huanlu-cap">单环（改执行）</span><b>${dan}</b><small>可控偏差 · 走执行整改</small></div>
      <div class="huanlu-cell shuang"><span class="huanlu-cap">双环（改预算）</span><b>${shuang}</b><small>结构已变 · 走预算修订</small></div>
      <div class="huanlu-cell hun"><span class="huanlu-cap">混合纠错</span><b>${hun}</b><small>双环优先 · 同步执行整改</small></div>
      <div class="huanlu-cell fuhe"><span class="huanlu-cap">复核提示</span><b>${fuhe}</b><small>先确认经营变更/差异率未过门</small></div>
    </div></section>`;
  };
  return `${heading('风险与整改','从发现问题到跟踪处理，让每项差异有下一步。',btn('revision-log','修订记录','history'))}${huanlu()}<div class="risk-summary">${[['high','高风险差异','优先核对业务影响'],['watch','需关注差异','持续追踪执行偏差'],['done','已完成整改','效果在下期分析中复核']].map(([key,label,note])=>`<div class="risk-summary-item"><div><h3>${label}</h3><p>${note}</p></div><span class="num ${key==='done'?'positive':key==='high'?'negative':'warning'}">${key==='done'?actions.filter(a=>a.status==='done').length:currentRows().filter(r=>r.risk===key).length}</span></div>`).join('')}</div><div class="tasks">${[['pending','待处理'],['doing','进行中'],['done','已完成']].map(([status,label])=>{const items=actions.filter(a=>a.status===status);return `<section class="task-column"><div class="column-head"><span class="dot" style="background:${status==='pending'?'#a8b5c7':status==='doing'?'var(--blue)':'var(--green)'}"></span><strong>${label}</strong><span>${items.length}</span></div>${items.map(a=>`<article class="task-card">${tag(a.type==='revision'?'预算假设修订':'执行偏差整改',a.type==='revision'?'high':'blue')}<h3>${esc(a.title)}</h3><p>${esc(a.description)}</p><div class="task-meta"><span class="avatar">${esc(a.owner.slice(-1))}</span><span>${esc(a.owner)}</span><span class="grow"></span><span>${a.due.slice(5).replace('-','/')} 截止</span></div>${btn('task-detail','查看处理事项','arrow','small',`data-id="${esc(a.id)}"`)}</article>`).join('')||'<div class="empty-column">暂无事项</div>'}</section>`;}).join('')}</div><section class="panel section-spacer"><div class="panel-head"><h2>纠错判定</h2><span class="small muted">单双环判定与人工修订</span></div><div class="table-scroll"><table><thead><tr><th>科目</th><th>纠错判定</th><th>预警</th><th>处理</th></tr></thead><tbody>${currentRows().filter(r=>r.risk!=='normal').map(r=>`<tr><td>${esc(r.subject)}<span class="sub">${esc(r.department)}</span></td><td>${tag(r.decision,['双环','混合纠错模式'].includes(r.decision)?'high':'blue')}</td><td>${riskTag(r)}</td><td>${btn(['双环','混合纠错模式'].includes(r.decision)?'revise':'detail',['双环','混合纠错模式'].includes(r.decision)?'提请预算修订':'查看判定依据','','small',`data-id="${esc(r.id)}"`)}</td></tr>`).join('')||'<tr><td colspan="4" style="text-align:center;padding:32px">当前没有需要处理的预警</td></tr>'}</tbody></table></div></section>`;
}
// 报告中心：封面卡（期间、主体、内容清单、预览入口）+ 已生成报告表。
// 含 AI 解读的报告（includeAI）在标题后加「AI 解读」标签，悬浮提示统一文案；
// 演示模式的副标题显示“演示数据”，正式模式显示“正式分析结果”。
function reportsPage(){return `${heading('报告中心','把分析结果、经营解读与处理记录，整理成一份报告。',btn('generate-report','生成本期报告','plus','primary',S.busy?'disabled':''))}<section class="report-feature"><div class="report-cover"><div class="paper-mini"><div class="brand-line"><img src="./标识.svg" alt="">衡策</div><h3>经营分析<br>月度报告</h3><p>${esc(S.data.meta.period)} / ${esc(S.data.meta.company.replace('有限公司',''))}</p><div class="cover-chart">${[12,18,15,23,20,30,25].map(h=>`<i style="height:${h}px"></i>`).join('')}</div><div class="paper-line"></div><div class="paper-line short"></div></div></div><div class="report-description"><div>${tag('本期成果','blue')} ${!isLive?tag('演示报告','watch'):''}</div><h2>${esc(periodLabel(S.data.meta.period))}经营分析报告</h2><p>汇总预算执行情况、关键差异与风险，附上可追溯的明细和整改记录。AI 解读在获得数据访问授权后加入。</p><div class="report-checks"><span>${icon('check')}预算执行</span><span>${icon('check')}差异与预警</span><span>${icon('check')}整改记录</span></div>${btn('preview-report','预览本期报告','eye','',`data-id="${esc(S.data.reports.find(r=>r.period===S.data.meta.period)?.id||'current')}"`)}</div></section><section class="panel"><div class="panel-head"><h2>已生成的报告</h2><span class="small muted">${S.data.reports.length} 份</span></div><div class="table-scroll"><table><thead><tr><th>报告名称</th><th>生成时间</th><th>状态</th><th>操作</th></tr></thead><tbody>${S.data.reports.map(r=>`<tr><td><div class="file-name">${icon('report')}<div>${esc(r.title)}${r.includeAI?aiBadge():''}<span class="sub">${esc(r.period)} · ${!isLive?'演示数据':'正式分析结果'}</span></div></div></td><td>${date(r.createdAt)} ${time(r.createdAt)}</td><td>${tag('已生成','normal')}</td><td><div class="actions-inline">${btn('preview-report','预览','eye','small',`data-id="${esc(r.id)}"`)}${btn('export-report','导出','download','small',`data-id="${esc(r.id)}"`)}</div></td></tr>`).join('')||'<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--muted)">尚未生成报告</td></tr>'}</tbody></table></div></section>`;}
// 分析记录：按时间倒序列出每次分析（期间、主体、需关注差异数），
// 演示模式的条目额外标“演示快照”。点击“查看结果”会加载当时的快照，
// 加载后把主体重置为全公司并回到经营总览——快照是完整工作区状态，口径必须从总览看。
function historyPage(){return `${heading('分析记录','保留每次分析的时间与口径，随时回到当时的结果。')}<section class="panel"><div class="panel-head"><h2>已完成的分析</h2><span class="small muted">${S.data.history.length} 次</span></div><div class="timeline">${S.data.history.map(h=>`<div class="timeline-entry"><div class="timeline-date">${date(h.createdAt)}<p style="margin-top:5px">${time(h.createdAt)}</p></div><div class="timeline-symbol">${icon('check')}</div><div class="grow"><h3>${esc(h.period)} 经营分析</h3><p>${esc(h.company)} · ${h.riskCount} 项需关注差异 ${!isLive?'· 演示快照':''}</p></div>${btn('open-history','查看结果','arrow','small',`data-id="${esc(h.id)}"`)}</div>`).join('')||'<div class="empty-state"><p>运行首次分析后，记录会显示在这里。</p></div>'}</div></section>`;}
// 衡策助手侧栏：头部（标题 + 模式副标题 + 关闭）、当前上下文、对话区、输入区。
// 对话区：自己的提问不标 AI；AI 回答在气泡尾部挂统一标注；错误消息不标；
// 宿主接管型回答（system 标记）只是转交通知，同样不标。
// 输入区必须先勾选“允许访问当前分析结果”，未勾选时发送会被拦下并聚焦复选框。
// 这里的三重判断都有明确理由：role 只标 AI 回答；!m.system 排除“已转交宿主会话”这类系统通知，
// 它只是转场提示而不是 AI 生成内容；用户提问与错误消息同理不标。
function assistant(){const row=S.data.rows.find(r=>r.id===S.askRow);return `<aside class="assistant" aria-label="衡策助手"><div class="assistant-head">${icon('spark')}<div><h2>衡策助手</h2><p>${isLive?'基于当前分析上下文':'演示对话 · 未连接真实模型'}</p></div><button class="icon-btn" data-action="assistant" aria-label="关闭助手">${icon('close')}</button></div><div class="assistant-context">当前上下文：${esc(entityName())} / ${esc(S.data.meta.period)}${row?`<br>关注科目：${esc(row.subject)}`:''}</div><div class="assistant-log" id="assistant-log">${S.messages.length?S.messages.map(m=>`<div class="chat-message ${m.role}">${esc(m.text)}${m.sources?.length?`<div class="sources">${m.sources.map(s=>`${icon('link')} ${esc(s.title)}<br>${esc(s.excerpt)}`).join('<br>')}</div>`:''}${m.role==='assistant'&&!m.system?aiNotice():''}</div>`).join(''):`<div class="assistant-welcome"><h3>一起看清<br>数字背后的原因。</h3><p>选择一项差异，或从下面的问题开始。我会结合当前分析范围给出解释。</p>${['本期最需要关注哪些问题？','为什么采购成本超出预算？','帮我梳理下一步整改重点'].map(q=>`<button class="suggestion" data-action="ask-preset" data-question="${q}">${q}${icon('arrow')}</button>`).join('')}</div>`}${S.asking?'<div class="run-stage"><span class="spinner"></span>正在整理解读…</div>':''}</div><form class="assistant-compose" id="assistant-form"><label class="permission-row"><input type="checkbox" id="data-access" ${S.access?'checked':''}>允许访问当前分析结果</label><div class="compose-box"><textarea id="chat-input" rows="2" placeholder="问一个关于本期经营的问题…" aria-label="向衡策助手提问" ${S.asking?'disabled':''}>${esc(S.draft)}</textarea><div class="compose-tools">${icon('lock')}<span>${S.access?'仅使用当前授权的分析结果':'分析数据访问已关闭'}</span><button class="btn primary" type="submit" aria-label="发送问题" ${S.asking?'disabled':''}>${icon('arrowUp')}</button></div></div></form></aside>`;}
// 整页重绘的唯一入口：先收起下拉面板（它们挂在 body 上，重绘前必须清掉），
// 抓布局快照 → 替换 #app 内容 → 重新绑定表单 → 增强新出现的 select → 同步移动端导航状态 →
// 播放布局动画（前后位置差异由动效层插值）。
// 任何状态变化最终都收敛到这一次 render，界面没有第二套更新通道。
function render(){if(!S.data)return;closeSelects();const before=captureLayout();$('#app').innerHTML=shell();bindForms();enhanceSelects($('#app'));syncNavigation();animateLayout(before);}

// 下方交互层只组织页面状态与宿主请求，不实现财务计算。
// 演示模式的报告快照：报告 id → 生成时刻的完整工作区数据。
// 生成报告、载入演示数据时写入；预览与导出优先从这里取，取不到才回落到当前 S.data。
// 正式模式不用它——正式报告由插件导出，界面不缓存正文。
// 快照只存“生成那一刻”的完整工作区，不随后续分析变化，因此“历史报告预览”看到的数字与当时导出的完全一致，
// 不会出现旧报告显示新数字的情况；也正因为是整份快照，导出 JSON 与 HTML 才能与预览逐项对齐。
const reportSnapshots=new Map();

// AI 生成内容的统一标注（规范：文案一字不改，全站只有这一份常量）。
// 界面只负责“显示”标注，是否标注由数据决定：报告条目看 includeAI，对话看 role。
// 占位类文本（如“模块暂无数据”）是确定性逻辑，不在此列，绝不能贴 AI 标注。
// 统一文案常量已在上方定义，这里只补充使用纪律：
// 界面层任何新增的 AI 展示位都必须引用它，不允许再写一份字面量，
// 否则后端、导出文件与界面三处文案会出现不一致。
const AI_NOTICE='内容为AI生成，仅供参考';
// 标注小字的唯一渲染入口：role=note 让读屏器把它当说明而不是正文，
// title 悬浮提示与可见文本用同一常量，保证“看到的”和“悬停读到的”完全一致。
function aiNotice(){
// 统一标注的第二处使用点（助手气泡）：由 assistant() 在每条 AI 回答尾部调用，
// 用户自己的提问与错误提示都不调用——标注只跟随 AI 生成的内容。
  return `<div class="ai-notice" role="note" title="${AI_NOTICE}">${AI_NOTICE}</div>`;
}
// 报告卡片上的「AI 解读」标签：只表示该报告包含 AI 生成章节，
// 具体内容与边界由报告正文与标注小字说明；标签本身不承担免责声明功能。
function aiBadge(){
  return `<span class="ai-badge" title="${AI_NOTICE}">AI 解读</span>`;
}
// 报告是否含 AI 解读：列表项上的 includeAI 由生成报告时勾选写入；
// id 为 'current' 时退化为“本期报告”，覆盖预览页“预览本期报告”这一入口。
// 判断依据只有报告条目上的 includeAI：它由“生成报告”弹窗的勾选决定，
// 并由插件在 reports.generate 时写入报告记录。'current' 表示“本期报告”，
// 所以退化为按期间匹配；找不到条目时一律按“不含 AI”处理，宁可少标不可错标。
function reportHasAI(data,id){
  const list=data.reports||[];
  const item=id&&id!=='current'?list.find(r=>r.id===id):list.find(r=>r.period===data.meta.period);
  return Boolean(item&&item.includeAI);
}
// 演示模式的 JSON 报告：对照后端 reports.export(format='json') 的字段子集。
// 口径纪律：金额一律整数分、比率一律整数基点，本函数不做任何单位换算，
// 也不把确定性指标写成“AI 结论”；aiAnalysis 在演示模式保持空正文，只说明原因。
// JSON 与界面的一致性约束：modules 的 budget/actual/variance 必须与经营总览的摘要卡逐项相等，
// rows 的字段顺序固定为 id/subject/module/department/period/budget/actual/variance/rate/risk/decision/source，
// warnings 复用快照里的原文（不重新生成措辞），以保证同一份数据导出的 JSON 与界面读数一一对应、可被外部系统复核。
// 结构化 JSON 报告的字段说明（演示模式合成，正式模式由插件生成同构文件）：
// schema 固定 hengce.report/1，便于下游按版本解析；
// meta.unit 明确写“金额=分、比率=基点”，提醒消费方不要再猜单位；
// modules 是四个经营模块的聚合（budget/actual/variance 均为整数分），
// rows 保留每行原始字段（含 source 溯源），actions/revisions 保留整改进展与修订记录；
// aiAnalysis 只有 conclusion 与 actions 正文可能为 AI 文本，演示模式恒为空并写 notice 说明原因。
function reportJSON(data,id){
  const ai=reportHasAI(data,id);
// 聚合直接复用界面同一套 metrics：JSON 里的 overview 文案与经营总览页的摘要卡出自同一函数，
// 避免出现“导出的营业收入与页面上显示的不一致”这种最难排查的口径分裂。
  const jie=metrics(data.rows);
  const moKuai=['收入','成本','费用','采购'].map((name,i)=>{
    const rows=data.rows.filter(r=>r.module===name);
    const bud=rows.reduce((n,r)=>n+(r.budget||0),0),act=rows.reduce((n,r)=>n+(r.actual||0),0);
    return {no:i+1,name,table:name,budget:bud,actual:act,variance:act-bud,rows:rows.length,analysis:'',aiGenerated:false,citations:[]};
  });
  return {
    schema:'hengce.report/1',
    generatedAt:data.meta.generatedAt,
    aiGenerated:ai,
    aiNotice:AI_NOTICE,
    demo:Boolean(data.demo),
    meta:{company:data.meta.company,period:data.meta.period,scenarioName:data.meta.scenario,seed:data.meta.runId,unit:'金额=分、比率=基点'},
    overview:`本期营业收入 ${money(jie.revenue)} 元，预算 ${money(jie.budget)} 元，成本与费用合计 ${money(jie.cost+jie.expense)} 元，经营结余 ${money(jie.profit)} 元；需关注差异 ${jie.risk} 项。`,
// 模块固定四个（收入/成本/费用/采购），没有数据的模块也保留 0 值条目，
// 这样下游按 modules 建表时列数稳定；rows 是该模块的行数而不是行数组，行明细统一放在顶层 rows 里。
    modules:moKuai,
    aiAnalysis:{conclusion:'',actions:[],aiGenerated:false,notice:ai?'本报告勾选了 AI 解读，但演示模式不调用真实模型，解读正文以插件返回结果为准。':'演示模式未调用真实模型，未生成 AI 解读。'},
    warnings:(data.warnings||[]).map(w=>typeof w==='string'?w:(w&&w.message)||String(w)),
// 行明细严格只挑白名单字段并保持固定顺序：金额与差异率保持整数分/整数基点原值，
// source 原样带出用于溯源；这样 JSON 可逐字段与快照核对，也不会把内部的临时标记带进对外文件。
    rows:data.rows.map(r=>({id:r.id,subject:r.subject,module:r.module,department:r.department,period:r.period,budget:r.budget,actual:r.actual,variance:r.variance,rate:r.rate,risk:r.risk,decision:r.decision,source:r.source})),
    actions:(data.actions||[]).map(a=>({no:a.id,type:a.type,owner:a.owner,desc:a.title,suggestion:a.description,status:a.status,due:a.due})),
    revisions:(data.revisions||[]).map(r=>({subject:r.subject,period:r.period,amount:r.amount,reason:r.reason}))
  };
}
// 通用弹窗：先收起下拉、记录触发元素与其上下文指纹，再渲染对话框结构。
// options 支持 wide（宽版，表格/预览用）、drawer（右侧抽屉，详情用）、
// report（报告纸样式，预览与打印用）、submit（表单提交回调）。
// 打开后增强 select、播放动画、聚焦第一个可聚焦控件；
// 表单提交时自动禁用提交按钮，错误写进 #modal-error，避免重复提交。
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
// 关闭弹窗：走关闭动画（返回 Promise），动画结束后清空 #overlay 并清掉提交回调。
// 焦点恢复有明确边界：只有当前焦点落在弹窗内或 body 上时才夺回，
// 否则说明关闭前后有代码显式聚焦了别处（例如“询问助手”已聚焦输入框），这时不抢焦点。
// 原按钮若已被重绘移除，按区域 + data-* 指纹找回等价按钮，最后兜底 #main。
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
// 表单输入模板：label 包住 input，可访问性靠包裹关系而不是 for/id 硬绑定；
// value 一律转义，extra 用来放 required/step/min 等原生约束，让浏览器先做一层校验。
function inputField(name,label,value,type='text',extra=''){return `<label class="field"><span>${label}</span><input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;}
// 字符串金额/百分比转整数：只接受最多两位小数的数字（正则先挡非法输入），
// 用 BigInt 拼出“分/基点”再做整数运算，避免浮点误差（0.1+0.2 这类问题在金额上是事故）。
// 负数保留符号；超出安全整数范围时报错而不是静默截断。
function decimal(raw,label){const text=String(raw).trim();if(!/^-?\d+(\.\d{1,2})?$/.test(text))throw new Error(`${label}必须是数字，最多保留两位小数。`);const negative=text.startsWith('-'),[whole,part='']=text.replace('-','').split('.');const n=Number(BigInt(whole)*100n+BigInt(part.padEnd(2,'0')))*(negative?-1:1);if(!Number.isSafeInteger(n))throw new Error(`${label}超出可用范围。`);return n;}
// 期间下拉选项：按周期生成合法取值（月度 12 项、季度 4 项），年份取自当前期间。
// 一份数据只覆盖一个年度，所以选项不跨年；当前值不在列表里时选中第一项。
function qijianXuanxiang(zhouqi, dangqian){
  // 分析期间只给合法选项：一份数据就是一个年度，月度 12 项 / 季度 4 项
  const nian=Number(String(dangqian||'').slice(0,4))||new Date().getFullYear();
  const lie=zhouqi==='季度'
    ?[1,2,3,4].map(q=>`${nian}-Q${q}`)
    :Array.from({length:12},(_,i)=>`${nian}-${String(i+1).padStart(2,'0')}`);
  const xuan=lie.includes(dangqian)?dangqian:lie[0];
  return lie.map(v=>`<option value="${v}" ${v===xuan?'selected':''}>${zhouqi==='季度'?`${v.slice(0,4)} 年第 ${v.slice(-1)} 季度`:`${v.slice(0,4)} 年 ${Number(v.slice(-2))} 月`}</option>`).join('');
}
// 设置校验的边界情况：季度周期必须同时填行业增长率与行业修正，否则 growth 与 industryFlag 语义不完整；
// 档位阈值必须严格递增且都在 0–100% 之间（内部基点 0–10000），否则预警分级会出现“关注比高风险还高”的荒谬结果；
// 期间越界（早于数据起始月）时后端会拒绝，界面在提交前先给出“该期间没有实际数”的提示。
// 分析设置弹窗：周期与期间、增长率、判定门限、预警档位、AI 密钥。
// 期间随周期换算（月度 2027-06 ↔ 季度 2027-Q2，季度取该季末月），不重置到第一项；
// 提交时逐项用 decimal 转整数，并校验：期间格式与周期一致、至少两个档位且阈值递增、
// 行业修正仅限季度且必须有行业增长率；保存后只改本地快照并标记 dirty，重新分析才生效。
// AI 密钥不落前端：保存/清除都走宿主接口，状态行显示“已配置（掩码）/未配置”。
function settings(){
  const c=S.data.config;
  modal('分析设置','配置本期口径，保存后重新分析生效。',`<div class="form-grid"><label class="field"><span>分析周期</span><select name="cycle"><option ${c.cycle==='月度'?'selected':''}>月度</option><option ${c.cycle==='季度'?'selected':''}>季度</option></select></label><label class="field"><span>分析期间</span><select name="period" required>${qijianXuanxiang(c.cycle,c.period||S.data.meta.period||'')}</select></label>${inputField('growth','企业增长率（%）',c.growth/100,'number','required step="0.01" min="-100"')}${inputField('industry','行业增长率（%）',c.industry==null?'':c.industry/100,'number','step="0.01" min="-100"')}<label class="check-label field full" style="flex-direction:row"><input type="checkbox" name="industryCorrection" ${c.industryCorrection?'checked':''}>季度分析启用行业修正</label></div><div class="form-section">判定门限</div><div class="form-grid">${inputField('noise','噪声门限（%）',c.noise/100,'number','required step="0.01" min="0"')}${inputField('significance','显著性门限（%）',c.significance/100,'number','required step="0.01" min="0"')}${inputField('industryThreshold','行业修正门限（%）',c.industryThreshold/100,'number','required step="0.01" min="0"')}</div><div class="form-section"><span>预警档位</span><button type="button" class="text-btn" data-action="add-tier">${icon('plus')}添加档位</button></div><p class="inline-help" style="margin-bottom:12px">按百分比阈值从低到高排列，颜色用于结果中的预警标记。</p><div id="tier-fields">${c.tiers.map(t=>tierFields(t)).join('')}</div><div class="form-section">AI 服务</div><p class="inline-help" style="margin-bottom:12px">用于 AI 对话与报告解读；也可在 DeepSeek Harness 客户端登录账号开通。密钥保存在本机凭据中，保存后即时生效；留空保存即清除。</p><div class="form-grid"><label class="field full"><span>DeepSeek API 密钥</span><input name="apikey" type="password" placeholder="粘贴 sk- 开头的密钥" autocomplete="off"></label><button type="button" class="text-btn" data-action="save-key" style="justify-self:start">${icon('spark')}保存密钥</button></div><div id="apikey-status" class="small muted" style="margin:0 0 12px"></div>${!isLive?'<div class="notice info spacer-top">演示数据固定为 2027 年 6 月；此处可体验参数保存与预警档位筛选，真实计算由后续插件提供。</div>':''}`,`${btn('close-dialog','取消')}<button type="submit" class="btn primary">保存设置</button>`,{submit:async(fd,form)=>{
    const cfg={...c,cycle:fd.get('cycle'),period:fd.get('period').trim(),growth:decimal(fd.get('growth'),'企业增长率'),industry:fd.get('industry').trim()?decimal(fd.get('industry'),'行业增长率'):null,industryCorrection:fd.has('industryCorrection'),noise:decimal(fd.get('noise'),'噪声门限'),significance:decimal(fd.get('significance'),'显著性门限'),industryThreshold:decimal(fd.get('industryThreshold'),'行业修正门限')};
    if(!(cfg.cycle==='月度'?/^\d{4}-(0[1-9]|1[0-2])$/:/^\d{4}-Q[1-4]$/).test(cfg.period))throw new Error('期间格式与周期不一致：月度用 2027-06，季度用 2027-Q2。');
    cfg.tiers=[...form.querySelectorAll('.tier-row')].map(row=>({name:$('[name="tier-name"]',row).value.trim(),threshold:decimal($('[name="tier-threshold"]',row).value,'预警阈值'),color:$('[name="tier-color"]',row).value}));
    if(cfg.tiers.length<2||cfg.tiers.some((t,i)=>!t.name||t.threshold<=0||(i&&t.threshold<=cfg.tiers[i-1].threshold)))throw new Error('请至少设置两个档位，阈值须为正数并从低到高递增。');
    if(cfg.industryCorrection&&(cfg.cycle!=='季度'||cfg.industry==null))throw new Error('行业修正仅适用于季度分析，且需要填写行业增长率。');
    S.data.config=cfg;S.data.dirty=true;render();closeModal();toast('设置已保存，重新分析后生效。');
  }});
  $('[name="cycle"]')?.addEventListener('change',e=>{
    const p=$('[name="period"]');if(!p)return;
    // 期间随周期换算：2027-06 ↔ 2027-Q2（季度取该季末月），避免重置到首项
    const jiu=p.value;
    let xin=jiu;
    if(e.target.value==='季度'&&/^\d{4}-\d{2}$/.test(jiu)){
      xin=`${jiu.slice(0,4)}-Q${Math.ceil(Number(jiu.slice(-2))/3)}`;
    }else if(e.target.value!=='季度'&&/^\d{4}-Q[1-4]$/.test(jiu)){
      xin=`${jiu.slice(0,4)}-${String(Number(jiu.slice(-1))*3).padStart(2,'0')}`;
    }
    p.innerHTML=qijianXuanxiang(e.target.value,xin);
    p.dispatchEvent(new Event('change',{bubbles:true}));
  });
  shuaxin_miyao();
}
// 刷新 AI 密钥状态：读宿主返回的 configured/masked/source 显示一行状态。
// 读取失败只写一行提示，不影响计算与报告——密钥缺失不应阻断主流程。
async function shuaxin_miyao(){const kuang=$('#apikey-status');if(!kuang)return;try{const zt=await request('hosting.apiKey',{});kuang.textContent=zt.configured?`已配置（${zt.masked}，${zt.source==='env'?'启动环境变量':'本机凭据'}）。留空保存即清除。`:'未配置：计算与报告不受影响；配置后可用 AI 对话与报告解读。';}catch(e){kuang.textContent=`状态读取失败：${e.message}`;}}
// 预警档位行模板：名称（≤12 字）、阈值（百分比，内部按基点存）、颜色（只接受 #rrggbb）。
// 默认档位 4000 基点即 40%；颜色非法时退回内置红，避免 color 输入框拿到脏值。
function tierFields(t={name:'',threshold:4000,color:'#9957b8'}){return `<div class="tier-row"><input name="tier-name" aria-label="档位名称" value="${esc(t.name)}" required maxlength="12"><input name="tier-threshold" type="number" aria-label="档位阈值百分比" value="${t.threshold/100}" step="0.01" min="0.01" required><input name="tier-color" type="color" aria-label="预警颜色" value="${/^#[0-9a-f]{6}$/i.test(t.color)?t.color:'#c54d57'}"><button class="icon-btn" type="button" data-action="remove-tier" aria-label="删除档位">${icon('trash')}</button></div>`;}
// 差异详情抽屉：金额、差额、差异率、经营影响、判定说明、数据来源、下一步动作。
// 底部两个按钮：让助手解释（把该行带入助手上下文），
// 双环纠错行额外给“提请预算修订”（其余行是“查看整改事项”）。
// 演示模式在数据来源下明说“这是用于展示溯源位置的演示引用”。
function detail(id){
  const row=S.data.rows.find(r=>r.id===id);if(!row)return;
  modal(esc(row.subject),`${esc(row.department)} / ${esc(row.module)} / ${esc(row.period)}`,`${riskTag(row)} ${tag(row.decision,'blue')}<div class="detail-amounts"><div><p>预算金额（元）</p><strong class="num">${money(row.budget)}</strong></div><div><p>实际金额（元）</p><strong class="num">${money(row.actual)}</strong></div></div><div class="detail-line"><span>差额</span><strong class="num ${row.direction==='favorable'?'positive':'negative'}">${row.variance>0?'+':''}${money(row.variance)} 元</strong></div><div class="detail-line"><span>差异率</span><span class="num">${rate(row.rate)}</span></div><div class="detail-line"><span>经营影响</span>${tag(row.direction==='favorable'?'有利差异':'不利差异',row.direction==='favorable'?'normal':'high')}</div><div class="form-section">判定说明</div><p class="detail-text">${esc(row.reason)}</p><div class="form-section">数据来源</div><div class="source-box">${icon('file')} ${esc(row.source)}<p class="small muted">${!isLive?'这是用于展示溯源位置的演示引用。':'金额按原始记录和本次分析口径展示。'}</p></div><div class="form-section">下一步</div><p class="detail-text">${row.decision==='双环纠错'?'核对预算假设是否发生持续性变化，确认后可提请未来期间预算修订。':'核对业务执行与来源记录，跟踪责任部门的处理进展。'}</p>`,`${btn('ask-row','让助手解释','spark','',`data-id="${esc(id)}"`)}${row.decision==='双环纠错'?btn('revise','提请预算修订','arrow','primary',`data-id="${esc(id)}"`):btn('go-risks','查看整改事项','arrow','primary')}`,{drawer:true});
}
// 预算修订：只允许修订未来期间（已结账期间不可改，保证可追溯），
// 期间列表从当前期间之后开始按周期生成；当前年度没有未来期间时直接提示。
// 表单要求勾选“我已核对…”确认框，金额用 decimal 转整数分；
// 提交走 revisions.approve，演示模式只记录审批交互并说明不做重算。
function revise(id){
  const row=S.data.rows.find(r=>r.id===id);if(!row)return;
  const current=S.data.meta.period,year=current.slice(0,4),month=current.includes('Q')?Number(current.slice(-1))*3:Number(current.slice(-2));
  const quarter=S.data.config.cycle==='季度';
  const periods=quarter?Array.from({length:Math.max(0,4-Math.ceil(month/3))},(_,i)=>`${year}-Q${Math.ceil(month/3)+i+1}`):Array.from({length:Math.max(0,12-month)},(_,i)=>`${year}-${String(month+i+1).padStart(2,'0')}`);
  if(!periods.length){toast('当前年度没有可修订的未来期间。',true);return;}
  modal('提请预算修订',`${esc(row.subject)} · ${esc(row.department)}`,`<div class="notice info">${icon('lock')}只修订未来期间，已结账的预算与实际记录保持可追溯。</div><div class="form-grid"><label class="field"><span>生效期间</span><select name="period">${periods.map(p=>`<option>${esc(p)}</option>`).join('')}</select></label>${inputField('amount','修订后预算（元）',(row.budget/100).toFixed(2),'number','step="0.01" min="0" required')}<label class="field full"><span>修订原因</span><textarea name="reason" maxlength="2000" required placeholder="说明假设变化、核对依据与金额来源"></textarea></label><label class="check-label field full" style="flex-direction:row"><input name="approved" type="checkbox" required>我已核对科目、期间、金额与原因，确认批准本次修订。</label></div>${!isLive?'<p class="inline-help spacer-top">演示模式只记录审批交互，不执行预算重算。接入后端后将由插件重算并返回新版本。</p>':''}`,`${btn('close-dialog','取消')}<button class="btn primary" type="submit">${isLive?'批准修订并重算':'记录演示修订'}</button>`,{submit:async fd=>{await mutate('revisions.approve',{rowId:id,period:fd.get('period'),amount:decimal(fd.get('amount'),'修订金额'),reason:fd.get('reason').trim(),approved:fd.has('approved')},isLive?'修订已批准，分析结果已更新。':'演示修订已记录，原计算结果未变更。');closeModal();}});
}
// 预算修订记录：表格列出科目/期间、修订金额（整数分→元）、原因。
// 没有记录时给空状态并说明“从双环纠错事项发起修订后，记录会保留在这里”。
function revisionLog(){modal('预算修订记录','人工确认的未来期间预算调整。',S.data.revisions.length?`<div class="table-scroll"><table><thead><tr><th>科目 / 期间</th><th class="numeric">修订金额</th><th>原因</th></tr></thead><tbody>${S.data.revisions.map(r=>`<tr><td>${esc(r.subject)}<span class="sub">${esc(r.period)} · ${date(r.createdAt)}</span></td><td class="numeric">${money(r.amount)}</td><td style="white-space:normal;max-width:280px">${esc(r.reason)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty-state">'+icon('history')+'<h2>尚无预算修订</h2><p>从双环纠错事项发起修订后，记录会保留在这里。</p></div>',btn('close-dialog','关闭'),{wide:true});}
// 整改事项详情：类型、描述、责任部门、负责人、截止日期，以及处理状态下拉。
// 提交只改状态（actions.update），并提示“完成后财务影响仍要在下一期分析中复核”，
// 避免把“整改完成”误解成“差异已消除”。可跳到关联差异，修订类事项可直接发起修订。
function taskDetail(id){
  const task=S.data.actions.find(a=>a.id===id);if(!task)return;
  modal(esc(task.title),'整改处理事项',`${tag(task.type==='revision'?'预算假设修订':'执行偏差整改',task.priority)}<p class="detail-text spacer-top">${esc(task.description)}</p><div class="detail-line"><span>责任部门</span><span>${esc(task.department)}</span></div><div class="detail-line"><span>负责人</span><span>${esc(task.owner)}</span></div><div class="detail-line"><span>截止日期</span><span>${esc(task.due)}</span></div><label class="field spacer-top"><span>处理状态</span><select name="status">${[['pending','待处理'],['doing','进行中'],['done','已完成']].map(([value,label])=>`<option value="${value}" ${task.status===value?'selected':''}>${label}</option>`).join('')}</select></label><p class="inline-help spacer-top">完成整改表示处理事项已执行，财务影响仍需在下一期分析中复核。</p>`,`${btn('detail','查看关联差异','link','',`data-id="${esc(task.rowId)}"`)}${task.type==='revision'?btn('revise','提请修订','','',`data-id="${esc(task.rowId)}"`):''}<button class="btn primary" type="submit">保存状态</button>`,{submit:async fd=>{await mutate('actions.update',{id,status:fd.get('status')},'整改状态已更新。');closeModal();}});
}
// 经营背景弹窗：确认本期是否发生经营变更（未确认/有/无）+ 背景说明。
// 说明文案明确“背景说明不替代正式的经营变更台账及审批记录”，
// 保存走 background.save，属于会改工作区的操作（分析中会被拦下）。
function background(){modal('本期经营背景','补充经营环境，确认本期是否发生经营变更。',`<div class="form-grid"><label class="field full"><span>经营变更</span><select name="changeStatus"><option value="unknown" ${!['yes','none'].includes(S.data.background.changeStatus)?'selected':''}>尚未确认</option><option value="yes" ${S.data.background.changeStatus==='yes'?'selected':''}>有经营变更</option><option value="none" ${S.data.background.changeStatus==='none'?'selected':''}>无经营变更</option></select></label><label class="field full"><span>背景说明</span><textarea name="text" maxlength="4000" style="min-height:160px">${esc(S.data.background.text)}</textarea><small>背景说明不替代正式的经营变更台账及审批记录。</small></label></div>`,`${btn('close-dialog','取消')}<button type="submit" class="btn primary">保存背景</button>`,{submit:async fd=>{await mutate('background.save',{changeStatus:fd.get('changeStatus'),text:fd.get('text').trim()},'经营背景已保存。');closeModal();}});}
// 导入参数：mode 为“追加/替换”，category 为从某张数据卡点进来的类别。
// 从拖放区导入时固定 append 且不指定类别（由后端按工作簿内容判定）。
let importMode='append',importCategory=null;
// 导入弹窗：说明必需/选填类别、四个空白模板下载入口、导入方式选择与安全说明。
// 演示模式额外说明“当前预览尚未接入文件校验，选择文件后显示待校验，不会用演示数据冒充导入结果”。
function importDialog(){modal('导入工作簿','选择预算基础、实时经营及本期补充资料。',`<div class="dropzone">${icon('upload')}<strong>准备本次分析的 Excel 工作簿</strong><p class="small spacer-top">预算基础与实时经营为必需；行业对标、经营变更按需导入。</p></div><div class="template-row"><span class="small muted">还没有模板？下载官方空白模板：</span>${['预算基础','实时经营','行业对标','经营变更'].map(c=>`<button class="text-btn" type="button" data-action="template" data-category="${c}">${icon('download')}${c}</button>`).join('')}</div><label class="field"><span>导入方式</span><select id="import-mode"><option value="append">追加到本次工作区</option><option value="replace">替换本次全部工作簿</option></select></label><div class="source-box">${icon('lock')}工作簿由本机解析。AI 仅在获得授权后读取分析结果。${!isLive?'<p class="spacer-top">当前预览尚未接入文件校验。选择文件后会显示“待校验”，不会使用演示数据冒充导入结果。</p>':''}</div>`,`${btn('close-dialog','取消')}${btn('choose-files','选择 .xlsx 文件','folder','primary')}`);}
// “选择文件”统一入口：记住点击来源的类别与导入方式，然后触发隐藏的 file input。
// 真正读取文件在 bindForms 的 change 监听里，这里只负责把上下文带到那一步。
function chooseFiles(category=null){importCategory=category;importMode=$('#import-mode')?.value||'append';$('#file-input').click();}
// 导入文件：分析中禁止导入；扩展名必须是 .xlsx；单文件上限 28 MB（与模板体积匹配）。
// 读取成 ArrayBuffer 后连同 name/size 一起提交给 files.import，
// 模式与类别来自导入对话框；成功后关闭弹窗并跳到数据工作区。
// 校验失败的错误文案直接展示给用户，不做改写。
async function importFiles(files){if(S.busy)throw new Error('正在分析，请完成后再导入文件。');if(!files.length)return;if([...files].some(f=>! /\.xlsx$/i.test(f.name)))throw new Error('请选择 .xlsx 工作簿。');if([...files].some(f=>f.size>28*1024*1024))throw new Error('单个工作簿不能超过 28 MB。');const prepared=await Promise.all([...files].map(async f=>({name:f.name,size:f.size,bytes:await f.arrayBuffer()})));await mutate('files.import',{files:prepared,mode:importMode,category:importCategory},isLive?'文件已导入。':'文件已选择，等待后端校验。');closeModal();navigate('data');}
// 工作簿详情：类别、主体、校验状态、通过检查项数、入库行数。
// 演示模式明确说“检查数量来自演示夹具”，真实模式说明“已通过本机校验”；
// 待校验文件说明“当前预览不解析业务内容，接入插件后校验表头、公式与三表勾稽”。
function fileDetail(id){const f=S.data.files.find(x=>x.id===id);if(!f)return;modal('工作簿详情',esc(f.name),`<div class="detail-line"><span>数据类别</span><span>${esc(f.category)}</span></div><div class="detail-line"><span>主体</span><span>${esc(f.entity)}</span></div><div class="detail-line"><span>状态</span>${tag(f.status==='valid'?'校验通过':'待后端校验',f.status==='valid'?'normal':'watch')}</div>${f.status==='valid'?`<div class="detail-line"><span>通过检查</span><span>${f.checks} 项</span></div><div class="detail-line"><span>入库行数</span><span>${f.rows} 行</span></div><p class="source-box">${!isLive?'这些检查数量来自演示夹具，用于展示校验结果的呈现方式。真实文件校验由插件提供。':'工作簿已通过本机校验，可用于后续分析。'}</p>`:'<p class="source-box">文件已选入工作区。当前预览不解析其业务内容；待接入插件后检查固定表头、公式与三表勾稽。</p>'}`,btn('close-dialog','关闭'));}
// 运行分析：置 busy 并写进度文案（真实/演示模式措辞不同），重绘后请求 analysis.run。
// 成功后接受新快照、回到经营总览并写 hash；失败只 toast 错误原文；
// finally 一定清 busy 与进度并重绘，避免异常把界面卡在“分析中”。
async function runAnalysis(all=false){
  if(S.busy)return;
  S.busy=true;S.progress=isLive?'正在校验输入并计算经营差异…':'正在载入演示分析，整理差异与整改事项…';render();
  try{const data=await request('analysis.run',{entityId:all?'all':S.entity,config:S.data.config});acceptData(data);S.page='overview';location.hash='overview';toast(isLive?'分析完成。':'演示分析已更新。真实预算计算将在接入插件后启用。');}
  catch(error){toast(error.message,true);}finally{S.busy=false;S.progress='';render();}
}
// 趋势数据表：把某个月（或整段）的预算/实际/滚动预测以表格给出，供核对与读屏。
// 公司与部门两套表头（部门没有滚动预测列），金额单位统一为元。
function trendDetail(index){const {rows:data,buMen}=trendData(),rows=index==null?data:[data[index]];const tou=buMen?'<tr><th>期间</th><th class="numeric">预算费用</th><th class="numeric">实际费用</th></tr>':'<tr><th>期间</th><th class="numeric">原始预算</th><th class="numeric">实际收入</th><th class="numeric">滚动预测</th></tr>';modal(buMen?'成本费用趋势数据':'收入趋势数据',buMen?'当前部门费用中心口径；金额单位：元。':'全公司年度口径；金额单位：元。',`<div class="table-scroll"><table><thead>${tou}</thead><tbody>${rows.map(t=>buMen?`<tr><td>${esc(t.period)}</td><td class="numeric">${money(t.budget)}</td><td class="numeric">${money(t.actual)}</td></tr>`:`<tr><td>${esc(t.period)}</td><td class="numeric">${money(t.budget)}</td><td class="numeric">${money(t.actual)}</td><td class="numeric">${money(t.rolling)}</td></tr>`).join('')}</tbody></table></div>`,btn('close-dialog','关闭'),{wide:true});}

// 报告纸（HTML）：经营总览、预算与实际差异表、重点问题与处理方向、整改进展、预算修订记录、数据与依据说明。
// 金额用整数分转元、差异率用基点转百分比，表头标“金额单位：元”；
// 演示报告在抬头打“演示报告 · 虚构数据 · 未调用真实财务计算与模型”，
// 末段说明“没有调用知识库或真实模型，也不包含经检索验证的法规引用”——这句是口径承诺，不能删。
function reportMarkup(data){
  const m=metrics(data.rows),risks=data.rows.filter(r=>r.risk!=='normal');
  return `<article class="report-paper"><div class="brand-line"><strong>衡策</strong> / 经营分析</div>${data.demo?'<div class="report-mark">演示报告 · 虚构数据 · 未调用真实财务计算与模型</div>':''}<h1>${esc(data.meta.period)} 经营分析报告</h1><div class="report-sub">${esc(data.meta.company)}　${esc(data.meta.scenario)}<br>分析时间：${date(data.meta.generatedAt)} ${time(data.meta.generatedAt)}　金额单位：元</div><h2>经营总览</h2><p>本期营业收入 ${money(m.revenue)} 元，预算 ${money(m.budget)} 元。成本与费用共 ${money(m.cost+m.expense)} 元，经营结余 ${money(m.profit)} 元。采购采用独立管理视角，不重复扣入经营结余。</p><h2>预算与实际差异</h2><table><thead><tr><th>科目</th><th>预算</th><th>实际</th><th>差异率</th></tr></thead><tbody>${data.rows.map(r=>`<tr><td>${esc(r.subject)}</td><td class="numeric">${money(r.budget)}</td><td class="numeric">${money(r.actual)}</td><td class="numeric">${rate(r.rate)}</td></tr>`).join('')}</tbody></table><h2>重点问题与处理方向</h2>${risks.map(r=>`<p><strong>${esc(r.subject)} · ${esc(r.decision)}</strong><br>${esc(r.reason)}</p>`).join('')}<h2>整改进展</h2><table><thead><tr><th>事项</th><th>责任部门</th><th>状态</th></tr></thead><tbody>${data.actions.map(a=>`<tr><td>${esc(a.title)}</td><td>${esc(a.department)}</td><td>${{pending:'待处理',doing:'进行中',done:'已完成'}[a.status]}</td></tr>`).join('')}</tbody></table><h2>预算修订记录</h2>${data.revisions.length?data.revisions.map(r=>`<p>${esc(r.subject)} / ${esc(r.period)}：${money(r.amount)} 元。${esc(r.reason)}${data.demo?'（演示记录，尚未执行重算）':''}</p>`).join(''):'<p>本次尚无已批准的预算修订。</p>'}<h2>数据与依据说明</h2><p>${data.demo?'所有企业、人员、数值和事项均为演示夹具。此报告的说明为演示文本；没有调用知识库或真实模型，也不包含经检索验证的法规引用。':'依据以插件返回的分析结果为准。'}</p><p>生成版本：${esc(data.meta.runId)}</p></article>`;
}
// 报告预览：正式模式请求插件导出 html 并用 sandbox iframe 展示（宿主接管时直接提示已打开）。
// 演示模式从 reportSnapshots 取快照（'current' 用当前数据）渲染报告纸，
// 取不到时提示先生成报告；底部按钮：关闭、其他格式、导出 PDF（浏览器打印）。
// 含 AI 解读时在底部显示统一标注，覆盖“打印成 PDF”这条导出路径。
async function previewReport(id='current'){
  S.selectedReport=id;
  if(isLive){const response=await request('reports.export',{id,format:'html'});if(response.handled){toast('报告已在宿主中打开。');return;}const text=new TextDecoder().decode(response.bytes);modal('报告预览','由衡策插件返回的正式报告。','<iframe id="live-report-frame" sandbox="" title="正式分析报告" style="width:100%;height:65vh;border:0;background:white"></iframe>',`${btn('close-dialog','关闭')}${btn('export-report','导出报告','download','primary',`data-id="${esc(id)}"`)}`,{wide:true});$('#live-report-frame').srcdoc=text;return;}
  const data=id==='current'?S.data:reportSnapshots.get(id);if(!data)throw new Error('此报告没有可用的演示快照。请生成一份本期报告。');
  modal('报告预览','浏览器打印可选择“另存为 PDF”。',reportMarkup(data),`${btn('close-dialog','关闭')}${btn('export-report','其他格式','download','',`data-id="${esc(id)}"`)}${reportHasAI(data,id)?aiNotice():''}${btn('print-report','导出 PDF','download','primary')}`,{wide:true,report:true});
}
// 生成报告弹窗：未就绪或数据已变更时先拦下（并说明先重新分析）。
// “加入 AI 经营解读”需要先在助手里授权数据访问，否则报错；
// 生成后接受新快照，演示模式把新报告的数据存进 reportSnapshots 供预览/导出，
// 然后关弹窗并跳到报告中心。
function generateReportDialog(){if(!isReady()){toast('请先导入数据并完成分析。',true);return;}if(S.data.dirty){toast('数据或设置已变更，请重新分析后生成报告。',true);return;}modal('生成本期报告',`${esc(S.data.meta.company)} / ${esc(S.data.meta.period)}`,`<p class="detail-text">报告包含预算执行、差异明细、风险判断、整改进展和预算修订记录。</p><label class="check-label spacer-top"><input type="checkbox" name="includeAI">加入 AI 经营解读</label><p class="inline-help spacer-top">${isLive?'勾选后需允许 AI 访问当前分析结果。':'演示模式只生成带演示标识的报告，不生成真实模型解读。'}</p>`,`${btn('close-dialog','取消')}<button type="submit" class="btn primary">生成报告</button>`,{submit:async fd=>{
    if(S.data.dirty)throw new Error('数据或设置已变更，请重新分析后生成报告。');
    if(fd.has('includeAI')&&!S.access)throw new Error('请先在衡策助手中允许访问当前分析结果。');
    const previous=new Set(S.data.reports.map(r=>r.id));const data=await request('reports.generate',{runId:S.data.meta.runId,includeAI:fd.has('includeAI')});acceptData(data);
    if(!isLive)for(const r of data.reports)if(!previous.has(r.id))reportSnapshots.set(r.id,structuredClone(data));
    closeModal();navigate('reports');toast('报告已生成，可预览与导出。');
  }});}
// 导出菜单：PDF / HTML / Markdown / JSON 四种格式，各带一个下载按钮。
// PDF 走浏览器打印（演示模式）或宿主导出；其余三种由前端直接下载。
// 底部给“打开输出文件夹”（正式模式的宿主能力）与关闭。
// （补充）JSON 选项在演示模式与正式模式都可点：前者由前端合成 schema，
// 后者转发给插件导出；两种路径产出的字段集必须保持一致，便于外部系统统一解析。
function exportDialog(id){S.selectedReport=id;modal('导出分析报告','选择需要保存的格式。',`<div class="export-menu">${['pdf','html','md','json'].map(format=>btn('download-report',format==='pdf'?'PDF 文档':format==='html'?'HTML 网页':format==='md'?'Markdown 文档':'JSON 数据','download','',`data-format="${format}" data-id="${esc(id)}"`)).join('')}</div><p class="inline-help spacer-top">${isLive?'文件由衡策插件生成并保存。':'HTML、Markdown 和 JSON 可直接下载；PDF 使用浏览器打印保存。'}</p>`,`${btn('open-output','打开输出文件夹','folder','',`data-id="${esc(id)}"`)}${btn('close-dialog','关闭')}`);}
// 浏览器下载：Blob + 临时 <a download> 触发，点击后立刻移除节点，
// 15 秒后再释放 objectURL——立刻释放会让部分浏览器下载中断。
// 文件名与 mime 由调用方给，这里不做业务判断。
function download(name,mime,bytes){const url=URL.createObjectURL(new Blob([bytes],{type:mime})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);}
// 把宿主返回的导出结果落盘：handled 表示宿主已自行处理（例如弹出保存框），界面不再重复下载；
// 否则必须同时有 bytes 与 name，缺失就报“宿主未返回有效的导出文件”，
// 避免生成一个 0 字节或无名文件让用户以为导出成功。
async function saveResponse(response){if(response?.handled)return;if(!response?.bytes||!response?.name)throw new Error('宿主未返回有效的导出文件。');download(response.name,response.mime||'application/octet-stream',response.bytes);}
// 格式导出总入口：正式模式一律转发给宿主 reports.export 并落盘；
// 演示模式取快照（'current' 用当前数据）后分四条分支：
// PDF＝预览 + 浏览器打印；HTML＝内联当前样式表生成单文件网页，含 AI 解读时补 footer 标注；
// JSON＝按 schema 合成结构化报告（整数分/整数基点原样，不换算单位）；
// Markdown＝标题、差异表、重点问题、整改进展，含 AI 解读时补一行引用式标注。
// （补充）JSON 的 mime 为 application/json;charset=utf-8、后缀 .json，
// 与规范里的 reports.export 约定一致；文件名沿用「衡策-期间-演示分析报告.json」，
// 用户从下载列表里能一眼看出是哪个期间的数据。
async function downloadReport(id,format){
  if(isLive){await saveResponse(await request('reports.export',{id,format}));toast('导出请求已完成。');return;}
  const data=id==='current'?S.data:reportSnapshots.get(id);if(!data)throw new Error('报告快照不存在，请重新生成。');
  if(format==='pdf'){await previewReport(id);window.print();return;}
  const name=`衡策-${data.meta.period}-演示分析报告.${format}`;
// HTML 导出内联当前样式表，保证单文件离线可读（外链 CSS 在用户机器上会 404）。
// 正式模式的 HTML 由插件生成、自带 footer 标注，所以这里只在演示路径按需补 foot注，避免同一份文件出现两条标注。
// 标注 footer 只在报告含 AI 解读时出现：判定复用 reportHasAI（与报告中心卡片、JSON 的 aiGenerated 同源），
// 这样“卡片上有标签、导出文件里没有标注”或反过来的不一致情况不会发生。
  if(format==='html'){const css=await(await fetch('./src/界面.css')).text();download(name,'text/html;charset=utf-8',`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>衡策演示报告</title><style>${css}body{max-width:960px;margin:24px auto;background:white}.report-paper{box-shadow:none}</style>${reportMarkup(data)}${reportHasAI(data,id)?`<footer class="report-ai-notice" style="max-width:960px;margin:0 auto 32px;padding:0 16px;text-align:center;font-size:12px;color:#788599">${AI_NOTICE}</footer>`:''}</html>`);}
// JSON 下载在两种模式下走不同实现但同一份契约：正式模式由插件 reports.export 生成并落盘，
// 演示模式在这里本地合成（见 reportJSON），两者的 schema、字段名与单位完全一致；
// 所以外部系统不需要判断当前是演示还是正式，只要按 schema 解析即可。
  if(format==='json'){const json=reportJSON(data,id);download(name,'application/json;charset=utf-8',JSON.stringify(json,null,2));}
  if(format==='md'){const lines=[`# 衡策 ${data.meta.period} 经营分析报告`,'','> 演示数据，未调用真实模型或财务计算。',...(reportHasAI(data,id)?[`> ${AI_NOTICE}`]:[]),'',`主体：${data.meta.company}`,'','| 科目 | 预算（元） | 实际（元） | 差异率 |','|---|---:|---:|---:|',...data.rows.map(r=>`| ${r.subject} | ${money(r.budget)} | ${money(r.actual)} | ${rate(r.rate)} |`),'','## 重点问题',...data.rows.filter(r=>r.risk!=='normal').flatMap(r=>['',`### ${r.subject}`,r.reason]),'','## 整改进展',...data.actions.map(a=>`- ${a.title}：${{pending:'待处理',doing:'进行中',done:'已完成'}[a.status]}`)];download(name,'text/markdown;charset=utf-8',lines.join('\n'));}
  toast('报告已交给浏览器下载。');
}
// 导出明细 CSV：字段固定（科目/期间/部门/模块/预算/实际/差额/差异率/预警），
// 金额转元后保留两位小数，字段全部加引号并转义内部引号，行分隔用 \r\n 兼容 Excel。
// 开头加 UTF-8 BOM，否则 Excel 打开中文会乱码；导出范围是当前筛选后的全部行，不只是当前页。
function exportTable(){const rows=visibleRows(),quote=v=>`"${String(v).replaceAll('"','""')}"`;const text=[['科目','期间','部门','模块','预算（元）','实际（元）','差额（元）','差异率','预警'],...rows.map(r=>[r.subject,r.period,r.department,r.module,(r.budget/100).toFixed(2),(r.actual/100).toFixed(2),(r.variance/100).toFixed(2),rate(r.rate),riskNames[r.risk]])].map(row=>row.map(quote).join(',')).join('\r\n');download(`衡策-差异明细-${S.data.meta.period}.csv`,'text/csv;charset=utf-8','\uFEFF'+text);toast('已导出当前筛选范围的明细。');}
// 助手提问：正在回答或问题为空时忽略；未授权时先提示并聚焦授权复选框。
// 先把自己的提问压入消息、清空草稿、置 asking 并重绘（输入框立刻禁用）；
// 请求 assistant.ask 时带当前上下文（主体、期间、关注行、运行 id）与授权标记；
// AI 回答与错误分别压入 assistant / error 消息，finally 里解除 asking、
// 重绘、把对话区滚到底并重新聚焦输入框。
async function ask(question){
  if(S.asking||!question.trim())return;
  if(!S.access){toast('请先勾选“允许访问当前分析结果”。',true);$('#data-access')?.focus();return;}
  S.messages.push({role:'user',text:question.trim()});S.draft='';S.asking=true;render();
  try{const response=await request('assistant.ask',{question:question.trim(),context:{entityId:S.entity,period:S.data.meta.period,rowId:S.askRow||undefined,runId:S.data.meta.runId},dataAccess:S.access});if(!response.handled)S.messages.push({role:'assistant',text:response.text,sources:response.sources});else S.messages.push({role:'assistant',system:true,text:'已将问题与当前分析上下文交给宿主会话。'});}
  catch(error){S.messages.push({role:'error',text:error.message});}finally{S.asking=false;render();const log=$('#assistant-log');if(log)log.scrollTop=log.scrollHeight;$('#chat-input')?.focus();}
}
// 使用帮助弹窗：五步流程（导入 → 设置 → 分析 → 整改 → 报告）、
// 当前预览的性质（正式连接宿主 / 独立演示）、键盘操作说明；
// 正式模式额外提供“卸载衡策”入口，并说明卸载会删除安装目录、数据与快捷方式。
function help(){modal('使用衡策工作台','准备数据、发现问题、跟踪处理、形成报告。',`<ol class="checklist"><li>在数据工作区导入预算基础与实时经营工作簿。</li><li>确认主体、分析周期和期间，按需要调整分析参数。</li><li>运行分析，查看经营总览和科目差异。</li><li>打开风险事项，记录整改状态或发起预算修订。</li><li>生成报告，预览并导出 PDF、HTML、Markdown 或 JSON。</li></ol><div class="form-section">关于当前预览</div><p class="detail-text">${isLive?'当前页面已连接宿主插件。文件导入、分析、报告和 AI 问答均经宿主接口执行。':'当前是独立 UI 演示。数据、人物和事项均为虚构，交互只保留在页面内存，刷新会恢复初始演示。真实文件校验、预算重算、知识库检索和模型调用将在接入插件后启用。'}</p><div class="form-section">键盘操作</div><p class="detail-text">Tab 移动焦点，Enter 执行操作，Esc 关闭弹窗。助手输入框用 Enter 发送，Shift + Enter 换行。</p>${isLive?'<div class="form-section">卸载</div><p class="detail-text">从本机移除衡策：应用会先退出，再启动卸载向导；安装目录、导入的数据与分析记录、桌面快捷方式都会删除。</p>'+btn('uninstall','卸载衡策…','trash','danger'):''}`,btn('close-dialog','知道了'));
}
// 卸载确认：把后果写全（退出应用、删除安装目录与数据、删除桌面快捷方式、不可恢复），
// 确认按钮走 uninstall-confirm，取消走关闭弹窗。
function uninstallDialog(){modal('卸载衡策','此操作会退出衡策并启动卸载向导：安装目录（含你导入的数据与分析记录）与桌面快捷方式都会被删除，不可恢复。','',`${btn('close-dialog','取消')}<button type="button" class="btn danger" data-action="uninstall-confirm">确认卸载</button>`);}
// 执行卸载：请求宿主 app.uninstall；失败时只 toast 错误原文，
// 不猜测原因、不重试——卸载属于不可逆操作，失败必须让用户看到真实报错。
async function doUninstall(){try{await request('app.uninstall',{});closeModal();toast('衡策即将退出并启动卸载向导…');}catch(error){toast(error.message,true);}}

// 表单与输入绑定：每次 render 后重新绑定（节点是新创建的，旧监听随之释放）。
// 部门选择、搜索、预警筛选、文件选择、拖放、助手授权、对话输入与 Enter 发送都在这里；
// 搜索与筛选只重绘 #variance-table 并重置页码，不整页重绘，输入焦点才不会丢。
function bindForms(){
  $('#entity-select')?.addEventListener('change',e=>{S.entity=e.target.value;S.pageNo=1;S.askRow=null;S.search='';S.module='全部';render();});
  $('#row-search')?.addEventListener('input',e=>{S.search=e.target.value;S.pageNo=1;$('#variance-table').innerHTML=varianceTable(S.page==='overview');});
  $('#risk-filter')?.addEventListener('change',e=>{S.risk=e.target.value;S.pageNo=1;$('#variance-table').innerHTML=varianceTable(S.page==='overview');});
  $('#file-input')?.addEventListener('change',e=>importFiles(e.target.files).catch(error=>toast(error.message,true)));
  const drop=$('#dropzone');if(drop){drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover');});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');importMode='append';importCategory=null;importFiles(e.dataTransfer.files).catch(error=>toast(error.message,true));});}
  $('#data-access')?.addEventListener('change',e=>{S.access=e.target.checked;S.draft=$('#chat-input')?.value||'';render();});
  $('#chat-input')?.addEventListener('input',e=>{S.draft=e.target.value;});
  $('#chat-input')?.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();ask(e.target.value);}});
  $('#assistant-form')?.addEventListener('submit',e=>{e.preventDefault();ask($('#chat-input').value);});
}
// 全局点击委托：所有按钮靠 data-action 分发，整页重绘后无需重新绑定。
// 先排除禁用按钮；分析进行中时拦下一组会改工作区的 action 并给提示；
// 分发表里每个 case 只做一件事，异步操作统一 try/catch 后把错误 toast 出来。
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
  event.preventDefault();const {action,id,page,category,format,chart}=button.dataset;
  if(S.busy&&['settings','import','choose-files','confirm-remove','background','revise','reset-demo','task-detail','generate-report','open-history'].includes(action)){toast('正在分析，请完成后再修改工作区。');return;}
  try{
    switch(action){
// 导航：切页面（内部会重置筛选与滚动位置，并写 hash）。
      case 'nav': navigate(page);break;
// 移动端汉堡：开合抽屉（同时切换 inert 与焦点）。
      case 'menu':setNavigation(!S.navOpen);break;
// 点在遮罩上关闭移动端抽屉。
      case 'close-menu':setNavigation(false);break;
// 顶栏助手按钮：展开/收起侧栏（Esc 也可关闭）。
      case 'assistant':S.ai=!S.ai;render();break;
// 打开分析设置弹窗（周期、门限、档位、密钥）。
      case 'settings':settings();break;
// 保存或清除 AI 密钥：空白即清除；成功/失败都只提示，不阻断其它功能。
      case 'save-key':{const kuang=$('[name="apikey"]');const zhi=(kuang?kuang.value:'').trim();try{const zt=await request('hosting.apiKey',{key:zhi});toast(zt.configured?`密钥已保存（${zt.masked}），AI 服务即时生效。`:'密钥已清除。');if(kuang)kuang.value='';shuaxin_miyao();}catch(e){toast(e.message,true);}break;}
// 打开使用帮助弹窗。
      case 'help':help();break;
// 切换经营总览图表类型（非法的值回落到走势图）。
      case 'chart':S.chartType=chart||'trend';render();break;
// 先弹确认框再执行卸载。
      case 'uninstall':uninstallDialog();break;
// 确认卸载：请求宿主退出并启动卸载向导。
      case 'uninstall-confirm':doUninstall();break;
// 关闭当前弹窗（走关闭动画与焦点恢复）。
      case 'close-dialog':closeModal();break;
// 打开导入弹窗（模板下载、导入方式）。
      case 'import':importDialog();break;
// 从数据卡或拖放区进入文件选择，带上类别与当前导入方式。
      case 'choose-files':chooseFiles(category);break;
// 下载空白模板：正式模式由宿主生成并保存，演示模式会报“未提供此操作”。
      case 'template':await saveResponse(await request('templates.download',{category}));break;
// 载入演示数据并把所有报告写入快照表，供之后的预览与导出。
      case 'reset-demo':await mutate('demo.reset',{},'已恢复演示数据。');for(const r of S.data.reports)reportSnapshots.set(r.id,structuredClone(S.data));break;
// 先弹确认框，只从工作区移除，不删磁盘原文件。
      case 'remove-file':modal('移除工作簿','仅从本次工作区移除，不删除磁盘上的原文件。',`<p class="detail-text">${esc(S.data.files.find(f=>f.id===id)?.name)}</p>`,`${btn('close-dialog','取消')}${btn('confirm-remove','移除文件','trash','danger',`data-id="${esc(id)}"`)}`);break;
// 确认移除单个工作簿并关闭弹窗。
      case 'confirm-remove':await mutate('files.remove',{id},'工作簿已从当前工作区移除。');closeModal();break;
// 清空全部工作簿前先确认，并说明历史运行记录仍保留。
      case 'clear-all':modal('清空全部工作簿','将移除全部 '+S.data.files.length+' 份已导入工作簿，当前分析结果一并解除；历史运行记录保留，可随时回看。磁盘上的原文件不受影响。','',`${btn('close-dialog','取消')}<button type="button" class="btn danger" data-action="confirm-clear">确认清空</button>`);break;
// 确认清空（连带解除当前分析结果）。
      case 'confirm-clear':await mutate('files.clear',{},'已清空全部工作簿。');closeModal();break;
// 查看工作簿详情（校验项数、入库行数）。
      case 'file-detail':fileDetail(id);break;
// 打开经营背景弹窗（经营变更确认）。
      case 'background':background();break;
// 运行前的界面级保护：分析中（S.busy）时全局点击委托已统一拦下该 action 并提示“正在分析”，
// 因此这里不必重复判断；成功后由 runAnalysis 负责跳转与置灰，失败时按钮会随 finally 重绘恢复可用，
// 不会出现“点了没反应且按钮永久禁用”的状态。
// 按当前主体运行分析。
      case 'run':await runAnalysis();break;
// 按全公司运行分析（忽略当前选中的部门）。
      case 'run-all':await runAnalysis(true);break;
// 切换差异表模块筛选并重置页码。
      case 'module':S.module=button.dataset.value;S.pageNo=1;render();break;
// 差异表翻页：页码合法才更新，只重绘表格。
      case 'page':{const v=Number(button.dataset.value);if(Number.isFinite(v)&&v>0){S.pageNo=v;$('#variance-table').innerHTML=varianceTable(S.page==='overview');}break;}
// 切换差额排序方向，只重绘表格。
      case 'sort':S.ascending=!S.ascending;S.pageNo=1;$('#variance-table').innerHTML=varianceTable(S.page==='overview');break;
// 打开差异详情抽屉。
      case 'detail':detail(id);break;
// 点趋势图数据点：打开该期间（或整段）的数据表。
      case 'trend-detail':trendDetail(button.dataset.index==null?null:Number(button.dataset.index));break;
// 部门对比点击：切到该部门并跳到差异分析。
      case 'department':S.entity=id;S.askRow=null;navigate('analysis');break;
// 关闭弹窗并跳到风险与整改。
      case 'go-risks':closeModal();navigate('risks');break;
// 打开整改事项详情（可改状态）。
      case 'task-detail':taskDetail(id);break;
// 对双环纠错行发起预算修订。
      case 'revise':revise(id);break;
// 查看预算修订记录。
      case 'revision-log':revisionLog();break;
// 在设置弹窗里追加一个预警档位。
      case 'add-tier':$('#tier-fields').insertAdjacentHTML('beforeend',tierFields());break;
// 删除该档位行（至少两档的校验在提交时做）。
      case 'remove-tier':button.closest('.tier-row').remove();break;
// 打开生成报告弹窗（未就绪或数据已变更会先被拦下）。
      case 'generate-report':generateReportDialog();break;
// 预览报告：正式模式用插件导出的 html，演示模式用快照渲染。
      case 'preview-report':await previewReport(id);break;
// 打开发出格式菜单（PDF/HTML/Markdown/JSON）。
      case 'export-report':exportDialog(id);break;
// 下载分支参数：按钮上带 data-format 与 data-id，两者都由 btn() 的 extra 拼进属性；
// 这里只读取不校验业务含义（格式白名单在 exportDialog 生成菜单时已收敛为四种），
// 真正决定生成方式的是 downloadReport 内部的 isLive 判断，所以同一个按钮在两种模式下都可用。
// 按所选格式导出；JSON 在演示模式由前端按 schema 合成。
      case 'download-report':await downloadReport(id,format);break;
// 调用浏览器打印（演示模式的 PDF 路径）。
      case 'print-report':window.print();break;
// 请宿主打开输出文件夹（正式模式的宿主能力）。
      case 'open-output':await request('reports.openFolder',{id});break;
// 加载某次分析的历史快照，回到经营总览。
      case 'open-history':await mutate('history.open',{id},'已打开该次分析快照。');S.entity='all';navigate('overview');break;
// 导出当前筛选范围的差异明细 CSV。
      case 'export-table':exportTable();break;
// 把该差异带入助手：展开侧栏、预填问题、聚焦输入框。
      case 'ask-row':S.askRow=id;S.ai=true;closeModal();S.draft=`请解释「${S.data.rows.find(r=>r.id===id).subject}」的差异原因和处理建议。`;render();$('#chat-input')?.focus();break;
// 预设问题：填入草稿并直接发送。
      case 'ask-preset':S.draft=button.dataset.question;render();await ask(S.draft);break;
    }
  }catch(error){toast(error.message,true);}
});
// 全局键盘约定：Esc 依次关闭弹窗 → 移动端抽屉 → 助手；
// Tab 在弹窗内与移动端抽屉内循环（把焦点锁在当前上下文里，不跑到背景内容）；
// 图表数据点支持 Enter 触发（等价点击），让键盘也能看具体数值。
document.addEventListener('keydown',event=>{
  if(event.defaultPrevented)return;
  if(event.key==='Escape'){if($('#overlay').children.length)closeModal();else if(S.navOpen)setNavigation(false);else if(S.ai){S.ai=false;render();}}
  const dialog=$('[role="dialog"]');
  if(dialog&&event.key==='Tab'){const focusables=[...dialog.querySelectorAll('button:not([disabled]),input,select,textarea,a[href],[tabindex="0"]')].filter(e=>e.offsetParent!==null);const first=focusables[0],last=focusables.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  if(!dialog&&S.navOpen&&event.key==='Tab'&&window.matchMedia('(max-width:760px)').matches){const controls=[...$('.sidebar').querySelectorAll('button:not([disabled]),a[href]')];const first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  if(event.key==='Enter'&&event.target.classList.contains('chart-point'))event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));
});
// hash 是唯一的外部路由：浏览器前进/后退或手改地址时同步页面，
// 只在合法页面键上生效，非法 hash 忽略（render 内部还会兜底成经营总览）。
window.addEventListener('hashchange',()=>{const page=location.hash.slice(1);if(pages[page]&&page!==S.page){S.page=page;render();}});
// 窗口尺寸变化时重算移动端导航状态（跨过 760px 断点要切换 inert）。
// passive 监听不阻断滚动，缩放与旋转时不会掉帧。
window.addEventListener('resize',syncNavigation,{passive:true});
// 启动流程：先取工作区快照（workspace.load），演示模式把所有报告存进快照表，
// 再首绘并订阅宿主推送：工作区变更 → 接受新快照重绘；分析进度 → 更新进度条；
// 助手消息 → 追加到对话。订阅回调里的异常只 toast，不能让一条坏消息停掉整个推送。
// 启动失败时把整页换成错误页并提供“重新连接”按钮，而不是留白屏。
async function start(){try{acceptData(await request('workspace.load'));if(!isLive)for(const r of S.data.reports)reportSnapshots.set(r.id,structuredClone(S.data));render();subscribe(event=>{try{if(event.type==='workspace.changed'){acceptData(event.data);render();}if(event.type==='analysis.progress'){S.progress=event.data.message;if(S.busy)render();}if(event.type==='assistant.message'){S.messages.push({role:'assistant',text:event.data.text});render();}}catch(error){toast(error.message,true);}});}catch(error){$('#app').innerHTML=`<div class="boot"><div style="text-align:center;max-width:480px;padding:24px"><h1>工作区暂时无法打开</h1><p class="detail-text spacer-top">${esc(error.message)}</p><button class="btn primary spacer-top" id="retry-start">重新连接</button></div></div>`;$('#retry-start').onclick=start;}}
// 安装动效（水波纹、布局过渡、减少动效监听），返回的 disposer 由 pagehide 触发释放。
// 只装一次，放在启动阶段。
installMotion();
// 安装全局下拉监听（点外面关闭、Esc、滚动/缩放时收起），同样只装一次。
installSelects();
// 入口：所有模块与监听就绪后再启动，保证首帧不会出现“点了没反应”的状态。
start();
