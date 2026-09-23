import {test,after,before} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url));let child,url,token;
before(async()=>{
 const dataDir=path.join(root,'desktop/qa/四类模板接口验收');await fs.mkdir(dataDir,{recursive:true});
 child=spawn(process.execPath,[path.join(root,'desktop/server.mjs')],{cwd:root,env:{...process.env,FINAGENT_DATA_DIR:dataDir,FINAGENT_DEBUG_CSV:'',FINAGENT_PYTHON:'D:/dev-env/Python312/python.exe'},stdio:['ignore','pipe','pipe']});
 child.stderr.resume();const [data]=await once(child.stdout,'data');url=JSON.parse(data).url;token=(await(await fetch(url+'/api/bootstrap')).json()).token;
});
after(()=>child?.kill());
async function api(name,data){const r=await fetch(url+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});return {status:r.status,body:await r.json()};}
test('old file formats and free text are rejected',async()=>{
 for(const name of ['a.csv','a.pdf','a.docx','a.txt'])assert.equal((await api('import',{name,base64:Buffer.from('a,b').toString('base64')})).status,400);
 assert.equal((await api('import',{text:'a,b'})).status,400);
});
test('budget and actual use same 12-sheet shape but map separately',async()=>{
 for(const [kind,key,other,count] of [['预算基础','yusuan','shishi',1140],['实时经营','shishi','yusuan',570]]){
  const bytes=await fs.readFile(path.join(root,`algo/fixtures/月度主体甲-${kind}.xlsx`));
  const r=await api('import',{name:`${kind}.xlsx`,base64:bytes.toString('base64')});
  assert.equal(r.status,200,JSON.stringify(r.body));assert.equal(r.body.category,kind);
  assert.equal(r.body.records[key].length,count);assert.equal(r.body.records[other].length,0);assert.equal(r.body.checks,226);
 }
});
test('download templates must be filled before business import',async()=>{
 for(const kind of ['预算基础','实时经营','行业对标','经营变更']){
  const bytes=await fs.readFile(path.join(root,`desktop/templates/${kind}输入模板.xlsx`));
  const r=await api('import',{name:`${kind}.xlsx`,base64:bytes.toString('base64')});
  assert.equal(r.status,400,kind+' empty template must not imply zero business activity');
 }
});
test('all four seeded workbooks reimport and complete one analysis',async()=>{
 const r=await api('demo-excel',{seed:73,entity:'主体丙',scenario:'扩展情景',grain:'季度'});
 assert.equal(r.status,200,JSON.stringify(r.body));assert.equal(r.body.files.length,4);assert.equal(r.body.checks,452);
 const categories=[];const counts={};for(const x of r.body.files){
  const raw=await fs.readFile(x.file);const imported=await api('import',{name:path.basename(x.file),base64:raw.toString('base64')});
  assert.equal(imported.status,200,JSON.stringify(imported.body));categories.push(imported.body.category);counts[x.category]=imported.body.records.ruku_shu;
 }
 assert.deepEqual(categories,['预算基础','实时经营','行业对标','经营变更']);
 assert.deepEqual(counts,{'预算基础':380,'实时经营':190,'行业对标':5,'经营变更':1});
 const probe=await api('analyze',{...r.body.input,probe:true});assert.equal(probe.status,200,JSON.stringify(probe.body));
 assert.equal(probe.body.result.meta.simulation,true);
});
test('four template downloads are served; old one-book route is absent',async()=>{
 for(const route of ['budget','actual','industry','change']){
  const r=await fetch(url+`/template-${route}.xlsx`);assert.equal(r.status,200);assert.match(r.headers.get('content-type'),/spreadsheetml/);
 }
 assert.equal((await fetch(url+'/template.xlsx')).status,404);
 assert.equal((await fetch(url+'/template.csv')).status,404);
});
