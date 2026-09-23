import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {analyze} from '../engine.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const fixture=JSON.parse(await fs.readFile(new URL('../experimental/demo.json',import.meta.url)));
test('missing change ledger remains unknown in governance decisions',()=>{
  const input=structuredClone(fixture);input.events=[];
  const result=analyze(input);
  assert.equal(result.meta.changeStatus,'unknown');
  assert.ok(result.decisions.every(x=>x.requiresChangeConfirmation&&x.panduan==='复核提示'&&x.yiju['结构变更登记']===null));
  input.changeStatus='none';assert.ok(analyze(input).decisions.every(x=>!x.requiresChangeConfirmation));
});
test('module totals reconcile, labor maps to cost, company and scenario follow metadata',()=>{
  const input=structuredClone(fixture);input.metadata={'主体名称':'甲主体','情景名称':'审慎情景'};
  const labor=input.subjects.find(x=>/人工|工资/.test(x.kemu));assert.ok(labor);labor.module='费用模块';
  const result=analyze(input);
  assert.equal(result.meta.entityName,'甲主体');assert.equal(result.meta.scenarioName,'审慎情景');
  assert.equal(result.moduleSummary.length,4);
  assert.equal(result.variance.xiang.find(x=>x.kemu===labor.kemu).module,'成本模块');
  assert.equal(result.moduleSummary.reduce((s,x)=>s+x.netDeltaFen,0),result.variance.xiang.reduce((s,x)=>s+x.chae_fen,0));
  assert.ok(result.moduleSummary.every(x=>Number.isSafeInteger(x.shareBps)&&Number.isSafeInteger(x.budgetFen)));
});
let child,url,token;
before(async()=>{
  child=spawn(process.execPath,[root+'/desktop/server.mjs'],{cwd:root,env:{...process.env,FINAGENT_DATA_DIR:root+'/desktop/qa/ui-contract-'+Date.now(),FINAGENT_PORT:'0'},stdio:['ignore','pipe','pipe']});
  child.stderr.on('data',x=>process.stderr.write(x));
  const [ready]=await once(child.stdout,'data');url=JSON.parse(String(ready)).url;
  token=(await(await fetch(url+'/api/bootstrap')).json()).token;
});
after(()=>child?.kill());
async function api(name,data={}){const r=await fetch(url+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});return {status:r.status,body:await r.json()};}
test('intake asks only when missing ledger is not explicitly confirmed absent',async()=>{
  const unknown=(await api('intake',{categories:['预算基础','实时经营'],firstPass:true})).body;
  assert.equal(unknown.changeStatus,'unknown');assert.equal(unknown.questions.length,2);
  assert.equal((await api('intake',{categories:['经营变更']})).body.changeStatus,'provided');
  assert.equal((await api('intake',{categories:[],changeStatus:'none'})).body.requiresChangeConfirmation,false);
  assert.equal((await api('intake',{categories:[],changeStatus:'pending'})).body.requiresChangeConfirmation,true);
});
test('default-off chat, stream and enrich refuse before reading session or spawning model',async()=>{
  for(const name of ['chat','enrich']){
    const response=await api(name,{question:'本期收入是多少',apiKey:'must-never-be-saved',endpoint:'https://unreachable.invalid'});
    assert.equal(response.status,200);assert.match(response.body.answer,/关闭|未开启/);
  }
  const r=await fetch(url+'/api/chat-stream',{method:'POST',headers:{'X-Finagent-Token':token,'Content-Type':'application/json'},body:JSON.stringify({question:'收入'})});
  assert.match(await r.text(),/done/);
  assert.equal((await api('normalize',{text:'raw workbook'})).status,400);
});
test('new metadata and confirmation survive persistence, clear resets current session',async()=>{
  const data={...fixture,metadata:{'主体名称':'动态主体','情景名称':'乐观'},changeStatus:'provided',apiKey:'never-persist-this-secret'};
  const result=(await api('analyze',data)).body.result;assert.equal(result.meta.entityName,'动态主体');
  const boot=await(await fetch(url+'/api/bootstrap')).json();assert.equal(boot.input.metadata['情景名称'],'乐观');
  assert.ok(!JSON.stringify(boot).includes('never-persist-this-secret'));
  assert.equal((await api('chat',{dataAccess:true,endpoint:'http://127.0.0.1:8080',question:'收入'})).status,400);
  await api('clear');assert.equal((await(await fetch(url+'/api/bootstrap')).json()).result,null);
});
