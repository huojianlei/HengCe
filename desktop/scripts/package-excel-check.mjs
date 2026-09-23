import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
const source=fileURLToPath(new URL('../../',import.meta.url));
const pkg=path.resolve(process.argv[2]);const dataDir=path.join(path.dirname(path.dirname(pkg)),'desktop/qa/包内运行验证-'+path.basename(pkg));await fs.mkdir(dataDir,{recursive:true});
const child=spawn(path.join(pkg,'runtime/node.exe'),['desktop/server.mjs'],{cwd:pkg,env:{...process.env,FINAGENT_DATA_DIR:dataDir,FINAGENT_PYTHON:path.join(pkg,'runtime/python/python.exe'),TEMP:dataDir,TMP:dataDir,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
child.stderr.resume();const [ready]=await once(child.stdout,'data');const url=JSON.parse(String(ready)).url;
try{
 const token=(await(await fetch(url+'/api/bootstrap')).json()).token;
 async function api(name,data){const r=await fetch(url+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(name+': '+body.error);return body;}
 const kinds=['预算基础','实时经营','行业对标','经营变更'];const items=[];
 for(const kind of kinds){
  const template=await fs.readFile(path.join(pkg,`desktop/templates/${kind}输入模板.xlsx`));
  let rejected=false;try{await api('import',{name:kind+'.xlsx',base64:template.toString('base64')});}catch{rejected=true;}
  if(!rejected)throw Error('空模板被误作业务数据');
  const fixture=await fs.readFile(path.join(source,`algo/fixtures/季度主体乙-${kind}.xlsx`));
  items.push(await api('import',{name:kind+'.xlsx',base64:fixture.toString('base64')}));
 }
 const records=Object.fromEntries(['yusuan','shishi','hangye','biangeng','jujue'].map(k=>[k,items.flatMap(x=>x.records[k]??[])]));records.ruku_shu=items.reduce((s,x)=>s+x.records.ruku_shu,0);
 const input={company:'包内主体',metadata:items[0].metadata,changeStatus:'provided',simulation:true,records,subjects:items[0].subjects,config:{...items[1].scope,growth:0,industry:null,industryCorrection:false,industryThreshold:50,noise:2500,significance:2500,tiers:[{ming_cheng:'黄',yu_fen:1500,yan_se:'#eebb66'}]},events:[],splits:[],kpi:{}};
 const run=await api('analyze',{...input,probe:true});
 if(!run.result?.meta?.simulation)throw Error('包内计算未完成');
 const flavor=(await fs.readFile(path.join(pkg,'build-flavor.txt'),'utf8')).trim();
 if(flavor==='Experimental'){
  const demo=await api('demo-excel',{seed:19,entity:'包内主体',scenario:'基础情景',grain:'季度'});
  if(demo.files.length!==4||demo.checks!==452)throw Error('演示生成失败');
 }else{
  let denied=false;try{await api('demo-excel',{seed:19});}catch{denied=true;}if(!denied)throw Error('正式版误放行演示生成');
  if((await fetch(url+'/experimental/entry.mjs')).status!==404)throw Error('正式版演示资源泄露');
 }
 const refusal=await api('chat',{question:'收入是多少'});if(!refusal.answer.includes('关闭'))throw Error('包内权限默认关闭未生效');
 console.log(JSON.stringify({ok:true,package:pkg,flavor,templates:4,checks:items.reduce((s,x)=>s+x.checks,0),rows:records.ruku_shu,quarter:true,permissionDenied:true}));
}finally{child.kill();}
