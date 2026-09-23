import http from 'node:http';
import fs from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import {randomBytes,randomUUID} from 'node:crypto';
import {createInterface} from 'node:readline';
import {parseText,subjects,analyze,integer,recount} from './engine.mjs';
import {prepareAiRequest} from './ai-boundary.mjs';
import {jiequ_wenben} from '../release plugin(1)/release plugin/src/file-extract.ts';

const here=path.dirname(fileURLToPath(import.meta.url)), root=path.dirname(here);
const token=randomBytes(24).toString('hex');
const distribution=JSON.parse(await fs.readFile(path.join(here,'distribution.json'),'utf8'));
const dataDir=process.env.FINAGENT_DATA_DIR || path.join('D:/衡策数据/1.0.5',distribution.dataFolder);
if(!/^D:[\\/]/i.test(path.resolve(dataDir)))throw new Error('数据与缓存目录必须位于 D 盘');
await fs.mkdir(dataDir,{recursive:true});
let settings={outputDir:path.join(dataDir,'输出报告')};
try {settings={...settings,...JSON.parse(await fs.readFile(path.join(dataDir,'settings.json'),'utf8'))};} catch {}
settings={outputDir:/^D:[\\/]/i.test(path.resolve(settings.outputDir || ''))?path.resolve(settings.outputDir):path.join(dataDir,'输出报告')};
const state={input:null,result:null,runId:null,revisions:[]};
try {Object.assign(state,JSON.parse(await fs.readFile(path.join(dataDir,'last-session.json'),'utf8')));} catch {}
let busy=false;
let activeChat=null;
function python(req, onEvent, signal) {
  const packaged=path.join(root,'runtime','python','python.exe');
  const exe=process.env.FINAGENT_PYTHON || (existsSync(packaged)?packaged:path.join(root,'kb','env','Scripts','python.exe'));
  return new Promise((resolve,reject)=>{
    const child=spawn(exe,['-B','-X','utf8',path.join(here,'bridge.py')],{cwd:root,windowsHide:true,env:{...process.env,TEMP:dataDir,TMP:dataDir,PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
    child.stdout.setEncoding('utf8');
    let out='',finalResult,size=0,settled=false;
    const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timeout);signal?.removeEventListener('abort',abort);if(error){child.kill();reject(error);}else resolve(value);};
    const abort=()=>finish(new Error('回答已停止'));
    const timeout=setTimeout(()=>finish(new Error('检索或模型调用超时，请稍后重试')),240000);
    signal?.addEventListener('abort',abort,{once:true});
    if(signal?.aborted)abort();
    child.stdout.on('data',x=>{size+=x.length;if(size>24e6)finish(new Error('响应过大'));if(!onEvent)out+=x;});
    if(onEvent){
      const lines=createInterface({input:child.stdout,crlfDelay:Infinity});
      lines.on('line',line=>{if(settled||!line.trim())return;try{const event=JSON.parse(line);if(typeof event.ok==='boolean')finalResult=event;else onEvent(event);}catch{finish(new Error('问答流数据格式异常'));}});
    }
    child.stderr.resume();child.on('error',e=>finish(e));
    child.on('close',()=>{try{const r=onEvent?finalResult:JSON.parse(out);if(!r)throw new Error('问答连接中断，未收到完整回答');if(!r.ok)throw new Error(r.error);finish(null,r);}catch(e){finish(e);}});
    child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(req));
  });
}
async function streamChat(data,res){
  if(data.dataAccess!==true){const permission=prepareAiRequest(null,{dataAccess:false});res.writeHead(200,{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify({type:'done',ok:true,...permission.response})+'\n');return;}
  if(!state.result)throw new Error('请先运行预算分析');
  if(data.runId && data.runId!==state.runId)throw new Error('报告已更新，请刷新后操作');
  const question=String(data.question??'').trim().slice(0,4000);
  if(!question)throw new Error('请填写问题');
  const request={...prepareAiRequest(state.result,{dataAccess:data.dataAccess,op:'chat',question}).request,stream:true,...modelSettings(data)};
  const controller=new AbortController();
  activeChat={id:data.requestId,controller};
  const closed=()=>controller.abort();res.on('close',closed);
  if(res.destroyed)controller.abort();
  res.writeHead(200,{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store','X-Accel-Buffering':'no'});
  res.flushHeaders();
  const send=event=>{if(!res.destroyed&&!res.writableEnded){res.write(JSON.stringify(event)+'\n');if(res.writableLength>2e6)controller.abort();}};
  try {const result=await python(request,send,controller.signal);send({type:'done',...result});}
  catch(error){send({type:'error',message:error.message});}
  finally{if(activeChat?.controller===controller)activeChat=null;res.off('close',closed);res.end();}
}
async function body(req) {
  let bytes=0;const parts=[];
  for await(const chunk of req){bytes+=chunk.length;if(bytes>40e6)throw new Error('单次输入超过 30 MB，请拆分文件');parts.push(chunk);}
  return JSON.parse(Buffer.concat(parts).toString('utf8')||'{}');
}
function modelSettings(data){
  const endpoint=new URL(data.endpoint || 'https://api.deepseek.com');
  if(endpoint.protocol!=='https:' || ['127.0.0.1','localhost','[::1]'].includes(endpoint.hostname))throw new Error('本版本仅接入 HTTPS 云端模型接口，本地模型接入暂不提供');
  return {apiKey:data.apiKey || '',endpoint:endpoint.href,model:data.model || 'deepseek-chat'};
}
async function saveResult(){
  await fs.mkdir(settings.outputDir,{recursive:true});
  const file=path.join(settings.outputDir,`${state.runId}.json`);
  await fs.writeFile(file,JSON.stringify(state.result,null,2),'utf8');
  await fs.writeFile(path.join(dataDir,'last-session.json'),JSON.stringify(state),'utf8');
  return file;
}
async function route(url,data) {
  if(url==='/api/clear'){
    Object.assign(state,{input:null,result:null,runId:null,revisions:[]});
    await fs.writeFile(path.join(dataDir,'last-session.json'),JSON.stringify(state),'utf8');
    return {cleared:true};
  }
  if(url==='/api/intake'){
    const provided=Array.isArray(data.categories)&&data.categories.includes('经营变更');
    const changeStatus=provided?'provided':data.changeStatus==='none'?'none':data.changeStatus==='pending'?'pending':'unknown';
    const questions=[];
    if(changeStatus==='unknown')questions.push({id:'operating-change',question:'本期是否发生过经营变更？答“无”可跳过；答“有”请先登记事件台账与科目影响，再导入经营变更输入模板。'});
    let source='本机输入核验';
    if(data.firstPass===true){
      let question='是否有经营变更台账未覆盖的宏观环境变化或其他特殊事项需要说明？没有可跳过；叙述不能代替台账与审批。';
      if(data.apiKey){try{const generated=await python({op:'intake',...modelSettings(data)});question=generated.question;source=generated.status;}catch{source='模型追问不可用，采用本机必要问题';}}
      questions.push({id:'narrative-context',question});
    }
    return {changeStatus,requiresChangeConfirmation:changeStatus==='unknown'||changeStatus==='pending',questions,source};
  }
  if(['/api/chat','/api/enrich'].includes(url)&&data.dataAccess!==true){
    return {ok:true,...prepareAiRequest(null,{dataAccess:false}).response};
  }
  if(url==='/api/settings'){
    if(data.outputDir){if(!path.isAbsolute(data.outputDir)||!/^D:[\\/]/i.test(path.resolve(data.outputDir)))throw new Error('输出目录必须是 D 盘绝对路径');settings.outputDir=path.resolve(data.outputDir);await fs.mkdir(settings.outputDir,{recursive:true});await fs.writeFile(path.join(dataDir,'settings.json'),JSON.stringify(settings));}
    return settings;
  }
  if(url==='/api/open-output'){
    await fs.mkdir(settings.outputDir,{recursive:true});
    spawn('explorer.exe',[settings.outputDir],{windowsHide:true,stdio:'ignore'}).on('error',()=>{});
    return {outputDir:settings.outputDir};
  }
  if(url==='/api/choose-output'){
    const picker=path.join(root,'FinAgent.exe');
    if(!existsSync(picker))return {path:null,message:'开发模式下请直接输入输出目录路径'};
    return new Promise((resolve,reject)=>{const child=spawn(picker,['--pick-folder'],{windowsHide:true,stdio:['ignore','pipe','ignore']});let out='';child.stdout.on('data',x=>out+=x);child.on('error',reject);child.on('close',()=>resolve({path:out.trim()||null}));});
  }
  if(url==='/api/import'){
    if(data.base64 && /\.xlsx$/i.test(data.name??''))return python({op:'import_excel',data:data.base64,name:data.name});
    if(process.env.FINAGENT_DEBUG_CSV!=='1')throw new Error('只接收 1.0.5 唯一标准 Excel 模板（.xlsx）；其他格式一律退回');
    let text=data.text;
    if(data.base64){
      if(/\.pdf$/i.test(data.name))text=(await python({op:'extract',data:data.base64})).text;
      else text=jiequ_wenben(data.name,Buffer.from(data.base64,'base64')).wenben;
    }
    if(typeof text!=='string')throw new Error('请提供文件或文本');
    let records;
    try{records=parseText(text);}catch(error){return {needsEditing:true,text,error:error.message};}
    return {records,subjects:subjects(records),text};
  }
  if(url==='/api/normalize'){
    throw new Error('工作簿仅在本机解析，不提供向模型上传原始数据的格式适配');
  }
  if(url==='/api/demo-excel'){
    if(distribution.dataFolder!=='FinAgent-Experimental')throw new Error('固定种子演示仅在演示版提供');
    const r=await python({op:'generate_excel',seed:data.seed,entity:data.entity,scenario:data.scenario,grain:data.grain});
    const result=analyze(r.input); // 用真实引擎预跑；失败不得导出。
    await fs.mkdir(settings.outputDir,{recursive:true});
    const files=[];
    for(const item of r.files){
      const file=path.join(settings.outputDir,`${item.category}-演示输入-种子${data.seed}-${randomUUID().slice(0,8)}.xlsx`);
      await fs.writeFile(file,Buffer.from(item.base64,'base64'));files.push({category:item.category,file});
    }
    return {files,imported:r.imported,input:r.input,verified:true,checks:r.checks};
  }
  if(url==='/api/analyze-batch'){
    if(!Array.isArray(data.inputs)||!data.inputs.length)throw new Error('批次不能为空');
    const computed=data.inputs.map(input=>analyze(input));
    const results=[];await fs.mkdir(settings.outputDir,{recursive:true});
    for(const r of computed){r.id=`批次预算分析-${randomUUID()}`;const file=path.join(settings.outputDir,r.id+'.json');await fs.writeFile(file,JSON.stringify(r,null,2));results.push({result:r,file});}
    return {results};
  }
  if(url==='/api/analyze'){
    const result=analyze(data); // Validate completely before replacing the current report.
    // Verification probe (demo generator self-check): compute only, keep state and output files untouched.
    if(data.probe===true)return {result};
    const {company,simulation,records,subjects,config,bsc,kpi,splits,events,traces,baselines,metadata,changeStatus}=data;
    state.input=structuredClone({company,simulation,records,subjects,config,bsc,kpi,splits,events,traces,baselines,metadata,changeStatus});state.result=result;state.revisions=[];
    state.runId=`预算分析-${new Date().toISOString().replace(/[:.]/g,'-')}-${randomUUID().slice(0,8)}`;
    state.result.id=state.runId;await saveResult();return {result:state.result,outputDir:settings.outputDir};
  }
  if(url==='/api/search')return python({op:'search',query:String(data.query).slice(0,2000)});
  if(url==='/api/export-csv'){
    // A real CSV file the presenter can hand to the teacher and later drag back into the import zone.
    if(typeof data.text!=='string'||!data.text.trim()||data.text.length>4e6)throw new Error('导出内容无效');
    const name=/^[\u4e00-\u9fa5A-Za-z0-9_-]{1,40}$/.test(data.name||'')?data.name:'演示数据';
    await fs.mkdir(settings.outputDir,{recursive:true});
    const body='\uFEFF'+data.text.replace(/\r?\n/g,'\r\n');
    let file;
    try{file=path.join(settings.outputDir,name+'.csv');await fs.writeFile(file,body,'utf8');}
    catch{file=path.join(settings.outputDir,name+'-'+Date.now()+'.csv');await fs.writeFile(file,body,'utf8');} // teacher may still hold it open in Excel
    return {file};
  }
  if(!state.result)throw new Error('请先运行预算分析');
  if(data.runId && data.runId!==state.runId)throw new Error('报告已更新，请刷新后操作');
  if(url==='/api/enrich'){
    const extra=await python({...prepareAiRequest(state.result,{dataAccess:data.dataAccess,op:'enrich'}).request,...modelSettings(data)});
    Object.assign(state.result,{analysis:extra.analysis,references:extra.references,retrievalFailures:extra.failures});await saveResult();return {result:state.result};
  }
  if(url==='/api/chat')return python({...prepareAiRequest(state.result,{dataAccess:data.dataAccess,op:'chat',question:String(data.question??'').slice(0,4000)}).request,...modelSettings(data)});
  if(url==='/api/action'){
    if(!['待整改','进行中','已完成'].includes(data.status))throw new Error('整改状态无效');
    const action=state.result.correction.qingdan.find(x=>x.id===data.id);if(!action)throw new Error('整改项不存在');
    if(action.shenpi && data.status==='已完成' && !state.revisions.some(x=>x.kemu===action.kemu))throw new Error('预算修订项须先在复核区批准具体修订数值');
    action.zhuangtai=data.status;recount(state.result.correction);
    state.result.dashboard.zhenggai_block=state.result.correction;
    state.result.audit??=[];state.result.audit.push({type:'整改状态',id:data.id,status:data.status,at:new Date().toISOString()});await saveResult();return {result:state.result};
  }
  if(url==='/api/revise'){
    if(data.confirmed!==true)throw new Error('请确认具体预算修订案');
    const cfg=state.input.config;
    if(data.period<=cfg.period)throw new Error('只能修订分析期间之后的预算，已届满期间锁定');
    if(!state.result.rolling.some(x=>x.kemu===data.kemu&&x.qijian_mingxi.some(y=>y.qijian===data.period)))throw new Error('修订期间或科目不存在');
    if(!String(data.reason||'').trim())throw new Error('请在页面填写预算修订原因');
    const revision={kemu:data.kemu,period:data.period,amount:integer(data.amount,'修订预算金额'),reason:data.reason,at:new Date().toISOString(),approved:true};
    const revisions=[...state.revisions,revision];const updated=analyze(state.input,revisions);
    updated.id=state.runId;updated.audit=[...(state.result.audit||[]),{type:'批准修订',...revision}];
    updated.previousVersion={rolling:state.result.rolling};
    // Preserve completed actions through a forecast-only recalculation.
    updated.correction=state.result.correction;updated.dashboard.zhenggai_block=updated.correction;
    state.result=updated;state.revisions=revisions;await saveResult();return {result:state.result};
  }
  if(url==='/api/export-html'){
    if(typeof data.html!=='string' || data.html.length>15e6)throw new Error('报告 HTML 无效');
    const file=path.join(settings.outputDir,`${state.runId}.html`);await saveResult();await fs.writeFile(file,data.html,'utf8');return {file,json:path.join(settings.outputDir,`${state.runId}.json`)};
  }
  throw new Error('接口不存在');
}
const staticFiles=JSON.parse(await fs.readFile(path.join(here,'assets.json'),'utf8'));
const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://127.0.0.1');
    const host=`127.0.0.1:${server.address().port}`;
    if(req.headers.host!==host){res.writeHead(403);return res.end();}
    if(url.pathname==='/api/bootstrap' && req.method==='GET'){res.setHeader('Content-Type','application/json; charset=utf-8');res.setHeader('Cache-Control','no-store');return res.end(JSON.stringify({token,settings,result:state.result,input:state.input,version:'1.0.5'}));}
    if(url.pathname.startsWith('/api/')){
      if(req.method!=='POST'||req.headers['x-finagent-token']!==token||req.headers.origin && req.headers.origin!==`http://${host}`){res.writeHead(403);return res.end();}
      if(url.pathname==='/api/chat-stop'){
        const data=await body(req);
        if(typeof data.requestId==='string' && activeChat?.id===data.requestId)activeChat.controller.abort();
        res.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify({ok:true}));return;
      }
      if(busy){res.writeHead(409,{'Content-Type':'application/json; charset=utf-8'});return res.end(JSON.stringify({error:'上一项操作尚未完成，请等待'}));}
      busy=true;
      try{const data=await body(req);if(url.pathname==='/api/chat-stream'){await streamChat(data,res);return;}const result=await route(url.pathname,data);res.writeHead(200,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(result));}finally{busy=false;}
      return;
    }
    const file=staticFiles[url.pathname];if(!file){res.writeHead(404);return res.end();}
    const content=await fs.readFile(path.join(here,file));
    const mime=file.endsWith('.xlsx')?'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':file.endsWith('.mjs')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.json')?'application/json':file.endsWith('.csv')?'text/csv':'text/html';
    res.writeHead(200,{'Content-Type':`${mime}; charset=utf-8`,'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"});res.end(content);
  }catch(error){if(!res.headersSent)res.writeHead(400,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({error:error.message}));}
});
server.listen(Number(process.env.FINAGENT_PORT||0),'127.0.0.1',()=>{
  const url=`http://127.0.0.1:${server.address().port}`;
  process.stdout.write(JSON.stringify({url})+'\n');
});
