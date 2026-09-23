import {readChatStream} from './chat-stream.mjs';
import {combineImports,inferScope,recordsCSV} from './import-data.mjs';
import {kpiFields,splitFields,scaled} from './fields.mjs';
import {esc,money,dashboard,reportHTML,decisionsTable,correctionTable,progress} from './report.mjs';
const $=id=>document.getElementById(id);
const emptyDashboard=$('dashboard-content').innerHTML;
let token='',result=null,records=null,subjectRows=[],reportUrl=null,confirmAction=null;
let savedHtml='';
let excelGroups=[];
function composeExcelGroup(files){
 const by=Object.fromEntries(files.map(f=>[f.category,f]));
 if(Object.keys(by).length!==files.length)throw new Error('同一主体与情景的数据类别重复，请先替换对应文件。');
 const ref=by['预算基础']??by['实时经营']??files[0],meta=ref.metadata;
 for(const f of files)for(const k of ['数据版本号','口径标记','生效周期','已结账截至'])if(f.metadata[k]!==meta[k])throw new Error(`四类文件的${k}不一致`);
 const records=Object.fromEntries(['yusuan','shishi','hangye','biangeng','jujue'].map(k=>[k,files.flatMap(f=>f.records[k])]));
 records.ruku_shu=['yusuan','shishi','hangye','biangeng'].reduce((n,k)=>n+records[k].length,0);
 const events=new Map();for(const x of by['经营变更']?.events??[]){const key=x.kemu+'\0'+x.period,old=events.get(key);if(old){old.reason+='；'+x.reason;old.structural||=x.structural;}else events.set(key,{...x});}
 return {groupKey:ref.groupKey,files,metadata:meta,records,subjects:(by['预算基础']??by['实时经营'])?.subjects??[],
  scope:(by['实时经营']??ref).scope,simulation:files.some(f=>f.simulation),events:[...events.values()],
  benchmarks:by['行业对标']?.benchmarks??[],procurement:files.flatMap(f=>f.procurement??[]),
  checks:files.reduce((n,f)=>n+(f.checks??0),0),categories:files.map(f=>f.category)};
}
function excelInput(g){return {company:g.metadata['主体名称']+' / '+g.metadata['情景名称'],simulation:g.simulation,records:g.records,subjects:g.subjects,config:{...g.scope,growth:0,industry:null,industryCorrection:false,industryThreshold:50,noise:2500,significance:2500,tiers:[{ming_cheng:'黄',yu_fen:1500,yan_se:'#ebbf69'},{ming_cheng:'红',yu_fen:3000,yan_se:'#e68b8e'}]},bsc:null,kpi:{},splits:[],events:g.events,traces:[],baselines:[]};}
function selectExcelGroup(index){
 const g=excelGroups[index];if(!g)return;
 setInput(excelInput(g));
 $('excel-context').textContent=`已导入：${g.categories.join('、')}。${g.metadata['数据版本号']} · ${g.metadata['口径标记']} · 勾稽 ${g.checks} 项通过。行业参考 ${g.benchmarks.length} 项，采购明细 ${g.procurement.length} 行。${g.categories.includes('实时经营')?'':'运行分析前还需导入同版式的实时经营文件。'}`;
}
function acceptExcelBatch(batch,append=false){
 const files=[...(append?excelGroups.flatMap(g=>g.files):[]),...batch];const grouped=new Map();
 for(const item of files){if(!item.groupKey||!item.category)throw new Error('文件缺少主体、情景或数据类别');const list=grouped.get(item.groupKey)??[];list.push(item);grouped.set(item.groupKey,list);}
 const next=[...grouped.values()].map(composeExcelGroup);
 excelGroups=next;$('excel-group').replaceChildren(...next.map((g,i)=>{const o=document.createElement('option');o.value=i;o.textContent=g.metadata['主体名称']+' / '+g.metadata['情景名称']+' / '+g.metadata['期间粒度'];return o;}));
 selectExcelGroup(0);
}
$('excel-group').onchange=()=>selectExcelGroup(Number($('excel-group').value));
$('analyze-batch').onclick=()=>work('正在分别分析全部主体与情景…',async()=>{
 for(const g of excelGroups)if(!g.categories.includes('预算基础')||!g.categories.includes('实时经营'))throw new Error(`${g.metadata['主体名称']} / ${g.metadata['情景名称']} 缺少预算基础或实时经营文件`);
 const r=await api('analyze-batch',{inputs:excelGroups.map(excelInput)});
 $('batch-results').replaceChildren(...r.results.map(x=>{const p=document.createElement('p');p.textContent=x.result.meta.company+'：'+x.file;return p;}));show(`已分别完成 ${r.results.length} 组分析，结果已保存。`);
});
const groups={splits:[],events:[],traces:[],baselines:[]};
const show=(text,error=false)=>{const box=$('message');box.hidden=false;box.className=error?'error':'';box.textContent=text;};
const hide=()=>{$('message').hidden=true;};
async function api(name,data={}){const r=await fetch('/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});const body=await r.json();if(!r.ok||body.error&&!body.needsEditing)throw new Error(body.error||'操作失败');return body;}
async function work(label,fn){show(label);document.querySelectorAll('button').forEach(x=>x.disabled=true);try{await fn();}catch(e){show(e.message,true);}finally{document.querySelectorAll('button').forEach(x=>x.disabled=false);}}
function tab(name){document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===name));document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x.dataset.tab===name));$('page-label').textContent=document.querySelector(`[data-tab="${name}"]`).textContent.trim();window.scrollTo({top:0});}
document.querySelectorAll('[data-tab]').forEach(x=>x.onclick=()=>tab(x.dataset.tab));document.querySelectorAll('[data-goto]').forEach(x=>x.onclick=()=>tab(x.dataset.goto));
function numberField(key,label,unit,value=null){return `<label>${esc(label)}（${unit}）<input data-field="${esc(key)}" type="number" step="${['元','%','数值'].includes(unit)?'0.01':'1'}" value="${value==null?'':value}" placeholder="未提供"></label>`;}
$('kpi-fields').innerHTML=kpiFields.map(x=>numberField(...x)).join('');
$('bsc-fields').innerHTML='<div class="form-grid two">'+['财务','客户','内部流程','学习成长'].map((name,i)=>numberField(`bsc-${i}`,`${name}达成率`,'%')+numberField(`weight-${i}`,`${name}权重`,'%', [40,30,20,10][i])).join('')+'</div>';
function tierRow(t={ming_cheng:'',yu_fen:1500,yan_se:'#e3aa4b'}){const row=document.createElement('div');row.className='tier-row';row.innerHTML=`<label>档位名称<input data-tier="name" value="${esc(t.ming_cheng)}" placeholder="例如：关注"></label><label>阈值（%）<input data-tier="value" type="number" step="0.01" value="${t.yu_fen/100}"></label><label>颜色<input data-tier="color" type="color" value="${t.yan_se}"></label><button class="remove" aria-label="删除预警档位">×</button>`;row.querySelector('button').onclick=()=>row.remove();return row;}
function fillTiers(container,rows){container.replaceChildren(...rows.map(tierRow));}
function readTiers(container){return [...container.querySelectorAll('.tier-row')].map(row=>({ming_cheng:row.querySelector('[data-tier=name]').value.trim(),yu_fen:scaled(row.querySelector('[data-tier=value]').value,'档位阈值',100,true),yan_se:row.querySelector('[data-tier=color]').value}));}
fillTiers($('global-tiers'),[{ming_cheng:'黄',yu_fen:1500,yan_se:'#ebbf69'},{ming_cheng:'红',yu_fen:3000,yan_se:'#e68b8e'}]);
$('add-tier').onclick=()=>$('global-tiers').append(tierRow());
function renderSubjects(){
 $('subjects').innerHTML=subjectRows.map((s,i)=>`<details data-subject="${i}"><summary>${esc(s.kemu)} · 科目口径与专属档位</summary><div class="form-grid"><label>方向<select data-sub="direction">${['','收入类','成本类'].map(v=>`<option ${s.direction===v?'selected':''} value="${v}">${v||'请选择方向'}</option>`).join('')}</select></label><label>归属模块<select data-sub="module">${['','收入模块','成本模块','费用模块','采购模块'].map(v=>`<option ${s.module===v?'selected':''} value="${v}">${v||'请选择模块'}</option>`).join('')}</select></label><label>专属增长率（%，留空使用全局）<input data-sub="growth" type="number" step="0.01" value="${s.growth==null?'':s.growth/100}"></label></div><div class="subject-tiers"></div><button data-sub="add" class="text-button">＋ 增加科目专属档位</button></details>`).join('');
 $('subjects').querySelectorAll('[data-subject]').forEach(el=>{const s=subjectRows[el.dataset.subject],container=el.querySelector('.subject-tiers');fillTiers(container,s.tiers??[]);el.querySelector('[data-sub=add]').onclick=()=>container.append(tierRow());});
 $('revision-subject').innerHTML=subjectRows.map(x=>`<option>${esc(x.kemu)}</option>`).join('');
}
function readSubjects(){return [...$('subjects').querySelectorAll('[data-subject]')].map(el=>({...subjectRows[el.dataset.subject],direction:el.querySelector('[data-sub=direction]').value,module:el.querySelector('[data-sub=module]').value,growth:scaled(el.querySelector('[data-sub=growth]').value,'科目增长率'),tiers:readTiers(el.querySelector('.subject-tiers'))}));}
function addGroup(kind,value={}){
 const el=document.createElement('div');el.className='repeat-item';
 const subject=`<label>科目<input data-field="kemu" value="${esc(value.kemu??'')}" placeholder="与导入表科目一致"></label><label>期间<input data-field="period" value="${esc(value.period??$('period').value)}"></label>`;
 let fields='';
 if(kind==='splits')fields=subject+splitFields.map(([key,name,unit])=>numberField(key,name,unit,value.values?.[key]==null?null:value.values[key]/(unit==='元'?100:1))).join('');
 if(kind==='events')fields=subject+`<label class="span-all">原因与相关数据<textarea data-field="reason" rows="2">${esc(value.reason??'')}</textarea></label><label class="check span-all"><input data-field="structural" type="checkbox" ${value.structural?'checked':''}>已核对并登记为结构性变更</label>`;
 if(kind==='baselines')fields=subject+numberField('amount','届满前滚动基准','元',value.amount==null?null:value.amount/100);
 if(kind==='traces')fields=`<label>指标名称<input data-field="kpi_mingcheng" value="${esc(value.kpi_mingcheng??'')}" placeholder="例如：毛利率 / 交付周期"></label>`+[['bianhua_qian','变更前'],['bianhua_hou','变更后'],['yuan_yusuan','原预算']].map(([k,n])=>numberField(k,n,'数值',value[k]==null?null:value[k]/100)).join('');
 el.innerHTML=`<div class="form-grid">${fields}</div><button class="remove">删除此项</button>`;el.querySelector('button').onclick=()=>el.remove();$(kind).append(el);
}
document.querySelectorAll('[data-add]').forEach(x=>x.onclick=()=>addGroup(x.dataset.add));
function readGroups(kind){return [...$(kind).querySelectorAll('.repeat-item')].map(el=>{
 const val=key=>el.querySelector(`[data-field="${key}"]`).value.trim();
 const id=()=>{if(!val('kemu')||!val('period'))throw new Error('请填写分析明细的科目和期间');return {kemu:val('kemu'),period:val('period')};};
 if(kind==='splits')return {...id(),values:Object.fromEntries(splitFields.map(([k,n,u])=>[k,scaled(val(k),n,u==='元'?100:1,true)]))};
 if(kind==='events')return {...id(),reason:val('reason'),structural:el.querySelector('[data-field=structural]').checked};
 if(kind==='baselines')return {...id(),amount:scaled(val('amount'),'届满前预算基准',100,true)};
 if(!val('kpi_mingcheng'))throw new Error('请填写溯源指标名称');
 return {kpi_mingcheng:val('kpi_mingcheng'),...Object.fromEntries(['bianhua_qian','bianhua_hou','yuan_yusuan'].map(k=>[k,scaled(val(k),'溯源数值',100,k!=='yuan_yusuan')]))};
 });}
function readInput(){
 const bscValues=[0,1,2,3].map(i=>scaled(document.querySelector(`[data-field="bsc-${i}"]`).value,'BSC 达成率'));
 let bsc=null;if(bscValues.some(x=>x!==null)){if(bscValues.some(x=>x===null))throw new Error('BSC 四个维度须全部填写');bsc={caijing_bps:bscValues[0],kehu_bps:bscValues[1],neibu_bps:bscValues[2],xuexi_bps:bscValues[3],quanzhong:[0,1,2,3].map(i=>scaled(document.querySelector(`[data-field="weight-${i}"]`).value,'BSC 权重',1,true))};}
 return {company:$('company').value,simulation:$('simulation').checked,records,subjects:readSubjects(),config:{cycle:$('cycle').value,period:$('period').value.trim(),growth:scaled($('growth').value,'企业增长率',100,true),industry:scaled($('industry').value,'行业增长率'),industryCorrection:$('industry-correction').checked,industryThreshold:scaled($('industry-threshold').value,'行业修正门限',100,true),noise:scaled($('noise').value,'噪声门限',100,true),significance:scaled($('significance').value,'显著性门限',100,true),tiers:readTiers($('global-tiers'))},bsc,kpi:Object.fromEntries(kpiFields.map(([k,n,u])=>[k,scaled(document.querySelector(`[data-field="${k}"]`).value,n,u==='元'?100:1)])),...Object.fromEntries(Object.keys(groups).map(kind=>[kind,readGroups(kind)]))};
}
function importSummary(){
 if(!records)return;
 $('import-summary').innerHTML=`<p class="muted">已接收 ${records.ruku_shu} 行：预算 ${records.yusuan.length} · 实际 ${records.shishi.length} · 行业 ${records.hangye.length} · 变更 ${records.biangeng.length}</p>`+(records.jujue.length?`<div class="warn">${records.jujue.map(x=>`第 ${x.hanghao} 行：${esc(x.yuanyin)}`).join('<br>')}</div>`:'');
 $('dataset-badge').textContent=`${records.ruku_shu} 行已导入`;
}
function acceptImport(r,append=false){
 if(r.needsEditing){$('raw-text').value=r.text;$('raw-text').closest('details').open=true;throw new Error(r.error);}
 const merged=combineImports(append&&records?[{records,subjects:readSubjects()},r]:[r]);
 records=merged.records;subjectRows=merged.subjects;
 if(!append){
  if(!$('keep-analysis-params').checked)clearProfessionalInputs();
  const scope=inferScope(records);if(scope){$('cycle').value=scope.cycle;$('period').value=scope.period;}
  const rows=[...records.yusuan,...records.shishi];$('simulation').checked=rows.length>0&&rows.every(x=>/模拟|演示/.test(x.laiyuan+' '+x.beizhu));
 }
 clearResult();$('raw-text').value=records.jujue.length?(r.text??''):recordsCSV(records);renderSubjects();importSummary();
}
async function readFiles(files){await work('正在提取并校验文件…',async()=>{
 const batch=[],loaded=[];
 for(const file of files){if(!/\.xlsx$/i.test(file.name))throw new Error('只接收唯一标准 Excel 模板（.xlsx）');if(file.size>28e6)throw new Error('文件超过 28 MB，请拆分导入');
 const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
 const response=await api('import',{name:file.name,base64:data});if(response.needsEditing){$('raw-text').value=response.text;$('raw-text').closest('details').open=true;throw new Error(response.error);}batch.push(response);loaded.push(file);}
 if(!batch.length)return;
 const append=$('import-mode').value==='append';acceptExcelBatch(batch,append);
 if(!append)$('file-list').replaceChildren();
 for(const file of loaded){const line=document.createElement('p');line.textContent=`✓ ${file.name} · ${(file.size/1024).toFixed(1)} KB`;$('file-list').append(line);}
 show('文件已导入。请核对科目映射、分析期间与参数后运行分析。');tab('inputs');});$('files').value='';}
$('pick-files').onclick=e=>{e.stopPropagation();$('files').click();};$('dropzone').onclick=()=>$('files').click();$('dropzone').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();$('files').click();}};
$('files').onchange=()=>readFiles($('files').files);
for(const type of ['dragenter','dragover'])$('dropzone').addEventListener(type,e=>{e.preventDefault();$('dropzone').classList.add('dragover');});
for(const type of ['dragleave','drop'])$('dropzone').addEventListener(type,e=>{e.preventDefault();$('dropzone').classList.remove('dragover');});
$('dropzone').addEventListener('drop',e=>readFiles(e.dataTransfer.files));
$('parse-text').onclick=()=>work('正在核验数据…',async()=>{acceptImport(await api('import',{text:$('raw-text').value}));show('数据已解析并替换，请核对结果。');});
const model=()=>({apiKey:$('api-key').value,endpoint:$('endpoint').value.trim(),model:$('model').value.trim()});
$('normalize').onclick=()=>work('AI 正在整理表格并核验数字来源…',async()=>{acceptImport(await api('normalize',{text:$('raw-text').value,...model()}));show('归一化与数字核验完成，请核对数据。');});
function renderResult(){
 if(!result)return;
 $('dashboard-content').innerHTML=dashboard(result);$('trend-subject').onchange=()=>{const value=$('trend-subject').value;$('dashboard-content').innerHTML=dashboard(result,value);$('trend-subject').onchange=()=>renderTrend();};
 $('review-content').innerHTML=`<h2>单双环判定</h2>${decisionsTable(result)}<h2 style="margin-top:30px">整改任务</h2>${progress(result)}${correctionTable(result,true)}`;
 $('review-content').querySelectorAll('[data-action-id]').forEach(el=>el.onchange=()=>work('正在保存整改进度…',async()=>{try{result=(await api('action',{runId:result.id,id:el.dataset.actionId,status:el.value})).result;renderResult();show('整改进度已保存。');}catch(e){renderResult();throw e;}}));
 savedHtml=reportHTML(result);if(reportUrl)URL.revokeObjectURL(reportUrl);reportUrl=URL.createObjectURL(new Blob([savedHtml],{type:'text/html;charset=utf-8'}));$('report-preview').removeAttribute('srcdoc');$('report-preview').src=reportUrl;
 $('dataset-badge').textContent=`${result.meta.simulation?'演示 · ':''}${result.meta.company} / ${result.meta.period}`;
}
function renderTrend(){const value=$('trend-subject').value;$('dashboard-content').innerHTML=dashboard(result,value);$('trend-subject').onchange=renderTrend;}
async function runAnalysis(){result=(await api('analyze',readInput())).result;renderResult();tab('dashboard');show('分析完成，JSON 已保存到输出文件夹。可进入报告中心生成解读与 PDF。');}
$('analyze').onclick=()=>work('正在运行计算插件与风险判定…',runAnalysis);
function clearProfessionalInputs(){for(const field of document.querySelectorAll('#kpi-fields input,#bsc-fields input'))field.value='';[40,30,20,10].forEach((v,i)=>document.querySelector(`[data-field="weight-${i}"]`).value=v);for(const kind of Object.keys(groups))$(kind).replaceChildren();}
function clearResult(){result=null;savedHtml='';if(reportUrl)URL.revokeObjectURL(reportUrl);reportUrl=null;$('dashboard-content').innerHTML=emptyDashboard;$('review-content').textContent='数据已更新，请重新运行分析。';$('report-preview').removeAttribute('src');$('chat-log').replaceChildren();}
function setInput(input){clearResult();fillInput(input);$('raw-text').value=recordsCSV(records);$('file-list').replaceChildren();}
function fillInput(input){records=input.records;subjectRows=input.subjects;$('company').value=input.company;$('period').value=input.config.period;$('growth').value=input.config.growth/100;$('industry').value=input.config.industry==null?'':input.config.industry/100;$('simulation').checked=input.simulation===true;$('cycle').value=input.config.cycle;$('industry-correction').checked=input.config.industryCorrection;
 for(const [k,n] of [['noise','noise'],['significance','significance'],['industry-threshold','industryThreshold']])$(k).value=input.config[n]/100;
 fillTiers($('global-tiers'),input.config.tiers);renderSubjects();importSummary();
 for(const [key,name,unit] of kpiFields)document.querySelector(`[data-field="${key}"]`).value=input.kpi?.[key]==null?'':input.kpi[key]/(unit==='元'?100:1);
 for(const [i,k] of ['caijing_bps','kehu_bps','neibu_bps','xuexi_bps'].entries()){document.querySelector(`[data-field="bsc-${i}"]`).value=input.bsc?.[k]==null?'':input.bsc[k]/100;document.querySelector(`[data-field="weight-${i}"]`).value=input.bsc?.quanzhong?.[i]??[40,30,20,10][i];}
 for(const kind of Object.keys(groups)){$(kind).replaceChildren();for(const x of input[kind]??[])addGroup(kind,x);}
}
export {setInput,runAnalysis,work,show,tab};
$('enrich').onclick=()=>work('正在检索 kb2 知识库并生成解读，可能需要一至数分钟…',async()=>{result=(await api('enrich',{runId:result?.id,...model()})).result;renderResult();show($('api-key').value?'依据与解读已写入当前报告，请查看各段核验状态。':'本地依据已检索；未填写 API Key，AI 解读标记为待生成。');});
$('export-html').onclick=()=>work('正在保存前端生成的 HTML 报告…',async()=>{if(!result)throw new Error('请先运行预算分析');const r=await api('export-html',{runId:result.id,html:savedHtml});show(`已保存 HTML 与 JSON：${r.file}`);});
$('print').onclick=()=>{if(!result)return show('请先运行预算分析',true);$('report-preview').contentWindow.focus();$('report-preview').contentWindow.print();};
async function saveSettings(){const r=await api('settings',{outputDir:$('output-dir').value.trim()});$('output-dir').value=r.outputDir;show('输出位置已保存。');}
$('save-settings').onclick=()=>work('正在保存输出位置…',saveSettings);
$('choose-output').onclick=()=>work('请选择输出文件夹…',async()=>{const r=await api('choose-output');if(r.path){$('output-dir').value=r.path;await saveSettings();}else show(r.message||'已取消文件夹选择');});
for(const id of ['open-output','open-output-settings'])$(id).onclick=()=>work('正在打开输出文件夹…',async()=>{await api('open-output');hide();});
$('ask').onclick=()=>work('正在检索依据…',async()=>{
 const question=$('question').value.trim();if(!question)throw new Error('请填写问题');if(!result)throw new Error('请先运行预算分析');
 const user=document.createElement('div');user.className='chat-message user';user.textContent=question;$('chat-log').append(user);
 const answer=document.createElement('div');answer.className='chat-message';
 const status=document.createElement('div');status.className='reference';status.textContent='正在检索依据…';status.setAttribute('role','status');
 const content=document.createElement('div');
 const stop=document.createElement('button');stop.className='text-button';stop.textContent='停止生成';
 const controller=new AbortController(),requestId=crypto.randomUUID();stop.onclick=()=>{stop.disabled=true;controller.abort();void api('chat-stop',{requestId}).catch(()=>{});};
 answer.append(status,content,stop);$('chat-log').append(answer);
 try{
  const response=await fetch('/api/chat-stream',{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify({runId:result.id,requestId,question,...model()}),signal:controller.signal});
  await readChatStream(response,event=>{
   if(event.type==='status'){status.textContent=event.message;show(event.message);}
   if(event.type==='delta'){content.append(document.createTextNode(event.text));status.textContent='正在生成 · 尚未完成数字及引用核验';}
   if(event.type==='done'){
    content.textContent=event.answer;status.textContent=`回答已完成 · ${event.status}`;
    for(const ref of event.references??[]){const p=document.createElement('div');p.className='reference';p.textContent=`${ref.dingwei} · ${ref.source?.biaoti??''}\n${ref.neirong}`;answer.append(p);}
    if(event.failures?.length){const note=document.createElement('div');note.className='reference';note.textContent='部分知识库检索失败，本次依据可能不完整。';answer.append(note);}
    show(status.textContent);$('question').value='';
   }
  });
 }catch(error){
  const message=controller.signal.aborted?'已停止生成，可修改问题后重新提问。':error.message;
  content.textContent='本次回答未完成，未保留尚未核验的内容。';status.textContent=message;
  if(!controller.signal.aborted)throw error;show(message);
 }finally{stop.remove();}
});
$('revise').onclick=()=>{try{if(!result)throw new Error('请先运行分析');const data={runId:result.id,kemu:$('revision-subject').value,period:$('revision-period').value.trim(),amount:scaled($('revision-amount').value,'修订金额',100,true),reason:$('revision-reason').value.trim()};if(!data.period||!data.reason)throw new Error('请填写修订期间及原因');$('confirm-body').innerHTML=`<p><b>${esc(data.kemu)} · ${esc(data.period)}</b><br>修订预算：${money(data.amount)} 元<br>原因：${esc(data.reason)}</p><p class="muted">批准后仅更新未来预算；保留原始预算及历史实际。AI 解读需重新生成。</p>`;confirmAction=async()=>{result=(await api('revise',{...data,confirmed:true})).result;renderResult();show('预算修订已批准，未来滚动预算已更新并保存。');};$('confirm-dialog').showModal();}catch(e){show(e.message,true);}};
$('cancel-confirm').onclick=()=>$('confirm-dialog').close();$('approve-confirm').onclick=()=>{$('confirm-dialog').close();work('正在执行已批准的预算修订…',confirmAction);};
const boot=await(await fetch('/api/bootstrap')).json();token=boot.token;$('output-dir').value=boot.settings.outputDir;result=boot.result;if(boot.input)fillInput(boot.input);if(result){subjectRows=result.subjects;renderSubjects();renderResult();}else $('report-preview').srcdoc=reportHTML(null);
