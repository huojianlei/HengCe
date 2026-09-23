import {test,after,before} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url));
const fixture=JSON.parse(await fs.readFile(new URL('../experimental/demo.json',import.meta.url)));
let server,url,token,result;
before(async()=>{
 const dataDir=path.join(root,'desktop/qa/api-test');await fs.mkdir(dataDir,{recursive:true});
 server=spawn(process.execPath,[path.join(root,'desktop/server.mjs')],{cwd:root,env:{...process.env,FINAGENT_DATA_DIR:dataDir,FINAGENT_PORT:'0'},stdio:['ignore','pipe','pipe']});
 server.stderr.resume();const [ready]=await once(server.stdout,'data');url=JSON.parse(String(ready)).url;token=(await(await fetch(url+'/api/bootstrap')).json()).token;
});
after(()=>server?.kill());
async function api(name,data={}){const response=await fetch(url+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});return {status:response.status,body:await response.json()};}
test('local APIs reject cross-site requests and missing capability token',async()=>{const a=await fetch(url+'/api/settings',{method:'POST',body:'{}'});assert.equal(a.status,403);const b=await fetch(url+'/api/settings',{method:'POST',headers:{'X-Finagent-Token':token,Origin:'https://untrusted.invalid'},body:'{}'});assert.equal(b.status,403);});
test('file contents use the audited importer',async()=>{const csv=await fs.readFile(new URL('../experimental/reference.csv',import.meta.url));const r=await api('import',{name:'预算.csv',base64:csv.toString('base64')});assert.equal(r.status,200);assert.equal(r.body.records.ruku_shu,25);});
test('JSON calculation saves a reproducible independent result',async()=>{const r=await api('analyze',fixture);assert.equal(r.status,200);result=r.body.result;const file=path.join(r.body.outputDir,result.id+'.json');assert.deepEqual(JSON.parse(await fs.readFile(file)),result);});
test('invalid BSC cannot replace the last successful report',async()=>{const bad=structuredClone(fixture);bad.bsc.quanzhong=[1,1,1,1];assert.equal((await api('analyze',bad)).status,400);const boot=await(await fetch(url+'/api/bootstrap')).json();assert.equal(boot.result.id,result.id);});
test('revision requires explicit confirmation, future period and reason',async()=>{const base={kemu:'直接材料',period:'2026-Q2',amount:45000000,reason:'供应商结构变化'};assert.equal((await api('revise',base)).status,400);assert.equal((await api('revise',{...base,confirmed:true,period:'2026-Q1'})).status,400);assert.equal((await api('revise',{...base,confirmed:true,reason:''})).status,400);});
test('approved future revision propagates through the chain and preserves closed data',async()=>{const r=await api('revise',{confirmed:true,kemu:'直接材料',period:'2026-Q2',amount:45000000,reason:'已审核供应商合同'});assert.equal(r.status,200);const rows=r.body.result.rolling.find(x=>x.kemu==='直接材料').qijian_mingxi;assert.equal(rows[0].shuzhi_fen,52000000);assert.equal(rows[1].shuzhi_fen,45000000);assert.equal(rows[2].shuzhi_fen,45677250);});
test('output folder can contain spaces and Chinese, and HTML bytes come from frontend',async()=>{const folder=path.join(root,'desktop/qa/api-test/自定义 输出');assert.equal((await api('settings',{outputDir:folder})).status,200);const html='<!doctype html><title>前端报告</title><p>核验成品</p>';const r=await api('export-html',{html});assert.equal(await fs.readFile(r.body.file,'utf8'),html);assert.ok(r.body.file.startsWith(folder));});
test('verification probe computes without touching the stored report or writing files',async()=>{
 const before=(await(await fetch(url+'/api/bootstrap')).json()).result.id;
 const filesBefore=(await fs.readdir(path.join(root,'desktop/qa/api-test/自定义 输出'))).length;
 const probe=await api('analyze',{...fixture,probe:true});
 assert.equal(probe.status,200);assert.equal(probe.body.result.variance.xiang.length,5);
 assert.equal((await(await fetch(url+'/api/bootstrap')).json()).result.id,before);
 assert.equal((await fs.readdir(path.join(root,'desktop/qa/api-test/自定义 输出'))).length,filesBefore);
});
test('demo CSV export writes a real BOM file that re-imports cleanly',async()=>{
 const text='数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注\r\n预算基础,2026-Q1,营业收入,1200000,元,演示数据,2026-04-01,模拟';
 const r=await api('export-csv',{name:'演示数据-青禾制造2026',text});
 assert.equal(r.status,200);assert.ok(r.body.file.endsWith('演示数据-青禾制造2026.csv'));
 const raw=await fs.readFile(r.body.file);
 assert.equal(raw[0]&0xFF,0xEF);assert.equal(raw[1]&0xFF,0xBB);assert.equal(raw[2]&0xFF,0xBF); // Excel-safe BOM
 assert.ok(raw.includes(Buffer.from('营业收入','utf8')));
 const reparsed=await api('import',{name:'演示数据-青禾制造2026.csv',base64:raw.toString('base64')});
 assert.equal(reparsed.body.records.ruku_shu,1);assert.equal(reparsed.body.records.jujue.length,0);
 const unsafe=await api('export-csv',{name:'../越界',text:'a,b'});
 assert.ok(unsafe.body.file.includes('演示数据.csv'));
});
test('completed correction progress is written back to JSON',async()=>{const boot=await(await fetch(url+'/api/bootstrap')).json();const action=boot.result.correction.qingdan.find(x=>!x.shenpi);const r=await api('action',{id:action.id,status:'已完成'});assert.equal(r.body.result.correction.wancheng_shu,1);assert.equal(r.body.result.dashboard.zhenggai_block.wancheng_shu,1);});
