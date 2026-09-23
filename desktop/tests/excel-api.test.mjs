import {test,after,before} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url));let child,url,token;
before(async()=>{
 const dataDir=path.join(root,'desktop/qa/模板接口验收');await fs.mkdir(dataDir,{recursive:true});
 child=spawn(process.execPath,[path.join(root,'desktop/server.mjs')],{cwd:root,env:{...process.env,FINAGENT_DATA_DIR:dataDir,FINAGENT_DEBUG_CSV:'',FINAGENT_PYTHON:'D:/dev-env/Python312/python.exe'},stdio:['ignore','pipe','pipe']});
 const [data]=await once(child.stdout,'data');url=JSON.parse(data).url;token=(await(await fetch(url+'/api/bootstrap')).json()).token;
});
after(()=>child?.kill());
async function api(name,data){const r=await fetch(url+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});return {status:r.status,body:await r.json()};}
test('only XLSX import is exposed by default',async()=>{
 for(const name of ['a.csv','a.pdf','a.docx','a.txt'])assert.equal((await api('import',{name,base64:Buffer.from('a,b').toString('base64')})).status,400);
 assert.equal((await api('import',{text:'a,b'})).status,400);
 assert.equal((await api('normalize',{text:'a,b'})).status,400);
});
test('strict workbook imports and returns independent scope',async()=>{
 const bytes=await fs.readFile(path.join(root,'desktop/templates/唯一输入模板.xlsx'));
 const r=await api('import',{name:'标准模板.xlsx',base64:bytes.toString('base64')});
 assert.equal(r.status,200);assert.equal(r.body.checks,452);assert.equal(r.body.records.ruku_shu,1710);
});
test('seeded Excel exports then reimports through production API',async()=>{
 const r=await api('demo-excel',{seed:73,entity:'主体丙',scenario:'扩展情景',grain:'季度'});
 assert.equal(r.status,200,JSON.stringify(r.body));assert.equal(r.body.verified,true);
 const bytes=await fs.readFile(r.body.file);const imported=await api('import',{name:'演示.xlsx',base64:bytes.toString('base64')});
 assert.equal(imported.status,200);assert.equal(imported.body.metadata['主体名称'],'主体丙');
 assert.deepEqual(imported.body.records,r.body.input.records);
 const batch=await api('analyze-batch',{inputs:[r.body.input,{...r.body.input,company:'主体丁'}]});
 assert.equal(batch.status,200);assert.equal(batch.body.results.length,2);
 assert.notEqual(batch.body.results[0].file,batch.body.results[1].file);
});
test('template download returns an XLSX and old CSV URL is absent',async()=>{
 const r=await fetch(url+'/template.xlsx');assert.equal(r.status,200);assert.match(r.headers.get('content-type'),/spreadsheetml/);
 assert.equal((await fetch(url+'/template.csv')).status,404);
});
