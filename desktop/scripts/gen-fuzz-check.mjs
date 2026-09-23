// Stress-checks the randomized demo generator against the real engine: every seed must
// produce a dataset that runs the whole showcase without warnings and hits every outcome.
import {analyze} from '../engine.mjs';
import {generate} from '../experimental/generator.mjs';
const ready=r=>r.warnings.length===0
 &&r.variance.xiang.some(x=>x.yujing==='红')
 &&r.variance.xiang.some(x=>x.yujing==='黄')
 &&r.decisions.some(d=>d.panduan==='双环'&&d.shenpi)
 &&r.decisions.some(d=>d.panduan==='单环')
 &&r.bsc&&Object.values(r.kpi).every(v=>v!=null)
 &&r.trace&&r.trace.zhengxiang_top3.length>0&&r.trace.fuxiang_top3.length>0
 &&r.correction.zong_shu>0&&r.blocks.mokuai_lie.length>0;
const rounds=Number(process.argv[2]||300);
let fail=0;const seen={cycle:{},judge:{},red:{}};
for(let i=1;i<=rounds;i++){
 try{
  const input=generate(i);
  const r=analyze(input);
  seen.cycle[input.config.cycle]=(seen.cycle[input.config.cycle]||0)+1;
  for(const d of r.decisions)seen.judge[d.panduan]=(seen.judge[d.panduan]||0)+1;
  for(const v of r.variance.xiang)if(v.yujing==='红')seen.red[v.kemu]=(seen.red[v.kemu]||0)+1;
  if(!ready(r)){fail++;console.log(`seed ${i} NOT READY`, JSON.stringify({warnings:r.warnings,roles:r.variance.xiang.map(x=>`${x.kemu}:${x.yujing}`),judge:r.decisions.map(d=>`${d.kemu}:${d.panduan}`),kpiNull:Object.values(r.kpi).filter(v=>v==null).length,trace:!!r.trace&&[r.trace.zhengxiang_top3.length,r.trace.fuxiang_top3.length]}));if(fail>3)break;}
 }catch(error){fail++;console.log(`seed ${i} ERROR ${error.message}`);if(fail>3)break;}
}
console.log(JSON.stringify({rounds,fail,seen},null,1));
if(fail)process.exitCode=1;
