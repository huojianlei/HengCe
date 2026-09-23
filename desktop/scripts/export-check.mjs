// Packaged-payload check for the teacher-facing CSV export workflow, without installing:
// starts the payload's own node + server, then replays exactly what the presenter does.
// Run from the project root: node desktop/scripts/export-check.mjs [payloadDir]
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const payload=path.resolve(process.argv[2]||'dist/FinAgent');
const qa=`desktop/qa/export-${Date.now()}`;await fs.mkdir(qa,{recursive:true});
const server=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'desktop/server.mjs')],{env:{...process.env,FINAGENT_PORT:'0',FINAGENT_DATA_DIR:path.resolve(qa)},stdio:['ignore','pipe','pipe']});
server.stderr.resume();const [ready]=await once(server.stdout,'data');const base=JSON.parse(String(ready)).url;
const boot=await(await fetch(base+'/api/bootstrap')).json();
const post=async(name,data)=>{const r=await fetch(base+'/api/'+name,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':boot.token},body:JSON.stringify(data)});return {status:r.status,body:await r.json()};};
try{
 const demo=JSON.parse(await fs.readFile(path.join(payload,'desktop/experimental/demo.json'),'utf8'));
 const {recordsCSV}=await import(pathToFileURL(path.join(payload,'desktop/web/import-data.mjs')).href);
 // 1. The presenter clicks "导出演示数据文件": a real CSV lands in the output folder.
 const exported=await post('export-csv',{name:'演示数据-青禾制造2026',text:recordsCSV(demo.records)});
 assert.equal(exported.status,200);assert.ok(exported.body.file.endsWith('演示数据-青禾制造2026.csv'));
 const bytes=await fs.readFile(exported.body.file);
 assert.equal(bytes[0],0xEF);assert.equal(bytes[1],0xBB);assert.equal(bytes[2],0xBF,'导出文件需带 BOM 供 Excel/WPS 直接打开');
 const text=bytes.toString('utf8');
 assert.ok(text.includes('营业收入')&&text.includes('2026-Q1'));
 assert.equal(text.trim().split(/\r\n/).length,26,'1 行表头 + 25 行演示数据');
 // 2. The teacher reviews it; the presenter drags the same file back into the import zone.
 const reimport=await post('import',{name:'演示数据-青禾制造2026.csv',base64:bytes.toString('base64')});
 assert.equal(reimport.status,200);assert.equal(reimport.body.records.ruku_shu,25);assert.equal(reimport.body.records.jujue.length,0);
 // 3. Analysis still runs the full pipeline with the imported records.
 const analysis=await post('analyze',{...demo,records:reimport.body.records,subjects:reimport.body.subjects});
 assert.equal(analysis.status,200);assert.equal(analysis.body.result.variance.xiang.length,5);
 assert.ok(analysis.body.result.variance.xiang.some(x=>x.kemu==='直接材料'&&x.yujing==='红'));
 // 4. Unsafe names cannot escape the output folder.
 const unsafe=await post('export-csv',{name:'../越界',text:'a,b'});
 assert.ok(unsafe.body.file.includes('演示数据.csv'));
 // 5. Packaged random generator + verification probe: every packaged generation must be
 //    demonstrable (demo payload only; a production payload has no experimental modules).
 const generatorPath=path.join(payload,'desktop/experimental/generator.mjs');
 let randomGenerations=null;
 if(await fs.stat(generatorPath).then(()=>true,()=>false)){
  const {generate}=await import(pathToFileURL(generatorPath).href);
  const ready=r=>r.warnings.length===0
   &&r.variance.xiang.some(x=>x.yujing==='红')&&r.variance.xiang.some(x=>x.yujing==='黄')
   &&r.decisions.some(d=>d.panduan==='双环'&&d.shenpi)&&r.decisions.some(d=>d.panduan==='单环')
   &&r.bsc&&Object.values(r.kpi).every(v=>v!=null)&&r.correction.zong_shu>0
   &&r.trace&&r.trace.zhengxiang_top3.length>0&&r.trace.fuxiang_top3.length>0;
  const reportsBefore=(await fs.readdir(path.join(boot.settings.outputDir))).length;
  for(let seed=1;seed<=8;seed++){
   const input=generate(seed);
   const probe=await post('analyze',{...input,probe:true});
   assert.equal(probe.status,200,`seed ${seed} 核验调用失败`);
   assert.ok(ready(probe.body.result),`seed ${seed} 未达演示标准`);
  }
  assert.equal((await fs.readdir(path.join(boot.settings.outputDir))).length,reportsBefore,'核验探针不得写入报告文件');
  randomGenerations=8;
 }
 await fs.writeFile(qa+'/result.json',JSON.stringify({payload,exportFile:exported.body.file,bom:true,rows:25,reimport:true,analysis:true,pathSafety:true,randomGenerations,probeWritesNothing:randomGenerations!==null},null,2));
 console.log(qa);
}finally{server.kill();}
