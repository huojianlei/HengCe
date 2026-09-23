import {test} from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {analyze,parseText} from '../engine.mjs';
import {generate} from '../experimental/generator.mjs';
import {combineImports,recordsCSV} from '../web/import-data.mjs';
const demo=JSON.parse(await fs.readFile(new URL('../experimental/demo.json',import.meta.url)));
// 与前端同一套达标口径：全流程零告警 + 红黄预警 + 双环（必审）+ 单环 + BSC/KPI/溯源/整改全出。
const ready=r=>r.warnings.length===0
 &&r.variance.xiang.some(x=>x.yujing==='红')&&r.variance.xiang.some(x=>x.yujing==='黄')
 &&r.decisions.some(d=>d.panduan==='双环'&&d.shenpi)&&r.decisions.some(d=>d.panduan==='单环')
 &&r.bsc&&Object.values(r.kpi).every(v=>v!=null)&&r.correction.zong_shu>0
 &&r.trace&&r.trace.zhengxiang_top3.length>0&&r.trace.fuxiang_top3.length>0;
test('every random generation runs the full showcase with zero warnings',()=>{
 for(let seed=1;seed<=40;seed++)assert.ok(ready(analyze(generate(seed))),`seed ${seed} 未达演示标准`);
});
test('random generation covers both cycles, both industry-correction states and rotating story subjects',()=>{
 const seen={cycle:new Set(),correction:new Set(),story:new Set()};
 for(let seed=1;seed<=120;seed++){
  const input=generate(seed);seen.cycle.add(input.config.cycle);seen.correction.add(String(input.config.industryCorrection));
  seen.story.add(input.events[0].kemu);
  assert.ok(['季度','月度'].includes(input.config.cycle));
  assert.equal(input.simulation,true);
  assert.equal(input.splits[0].kemu,input.events[0].kemu); // 拆分与结构登记同一科目
  assert.equal(input.records.jujue.length,0);
 }
 assert.equal(seen.cycle.size,2);assert.ok(seen.cycle.has('季度')&&seen.cycle.has('月度'));
 assert.equal(seen.correction.size,2);assert.ok(seen.correction.has('true')&&seen.correction.has('false'));
 assert.ok(seen.story.size>=2,'故事科目应在多个成本科目间轮换');
});
test('same seed reproduces the dataset; an unseeded call does not',()=>{
 assert.deepEqual(generate(20260911),generate(20260911));
 assert.notDeepEqual(generate(),generate());
});
test('randomly generated dataset survives a CSV round-trip through the real importer',()=>{
 const input=generate(777);
 const parsed=parseText(recordsCSV(input.records));
 assert.equal(parsed.jujue.length,0);
 assert.equal(parsed.ruku_shu,input.records.ruku_shu);
 const replay=analyze({...input,records:parsed,subjects:input.subjects});
 assert.ok(ready(replay),'CSV 往返后仍须满足演示标准');
});
test('fixed script dataset stays reproducible and fully demonstrative',()=>{
 assert.ok(ready(analyze(demo)));
 assert.equal(demo.records.jujue.length,0);
 assert.deepEqual(analyze(demo).warnings,[]);
});
test('duplicate demo import is rejected atomically; generated CSV round-trips',()=>{
 const item={records:structuredClone(demo.records),subjects:structuredClone(demo.subjects)};
 assert.throws(()=>combineImports([item,item]),/替换当前数据/);
 assert.equal(combineImports([item]).records.ruku_shu,25);
 const csv=parseText(recordsCSV(demo.records));
 assert.equal(csv.ruku_shu,25);assert.equal(csv.jujue.length,0);
});
