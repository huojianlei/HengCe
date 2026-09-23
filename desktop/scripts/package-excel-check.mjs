import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
const pkg=path.resolve(process.argv[2]);const dataDir=path.join(path.dirname(path.dirname(pkg)),'desktop/qa/包内运行验证-'+path.basename(pkg));await fs.mkdir(dataDir,{recursive:true});
const child=spawn(path.join(pkg,'runtime/node.exe'),['desktop/server.mjs'],{cwd:pkg,env:{...process.env,FINAGENT_DATA_DIR:dataDir,FINAGENT_PYTHON:path.join(pkg,'runtime/python/python.exe'),TEMP:dataDir,TMP:dataDir,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
child.stderr.resume();const [ready]=await once(child.stdout,'data');const url=JSON.parse(String(ready)).url;
try{
 const token=(await(await fetch(url+'/api/bootstrap')).json()).token;
 async function api(name,data){const r=await fetch(url+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(name+': '+body.error);return body;}
 const template=await fs.readFile(path.join(pkg,'desktop/templates/唯一输入模板.xlsx'));
 const imported=await api('import',{name:'唯一输入模板.xlsx',base64:template.toString('base64')});
 if(imported.checks!==452||imported.records.ruku_shu!==1710)throw Error('包内导入结果不符');
 const demo=await api('demo-excel',{seed:19,entity:'包内主体',scenario:'基础情景',grain:'季度'});
 if(demo.checks!==452||demo.input.config.cycle!=='季度')throw Error('包内种子生成失败');
 const run=await api('analyze',{...demo.input,probe:true});
 if(!run.result?.meta?.simulation)throw Error('包内计算未完成');
 console.log(JSON.stringify({ok:true,package:pkg,checks:imported.checks,rows:imported.records.ruku_shu,quarter:true}));
}finally{child.kill();}
