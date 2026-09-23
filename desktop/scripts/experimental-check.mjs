import {spawn} from 'node:child_process';import {once} from 'node:events';import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);const {chromium}=require('C:/Users/LeiZhiBo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const qa=`desktop/qa/experimental-${Date.now()}`;await fs.mkdir(qa,{recursive:true});
const server=spawn(process.execPath,[process.env.FINAGENT_SERVER_FILE||'desktop/server.mjs'],{env:{...process.env,FINAGENT_PORT:'0',FINAGENT_DATA_DIR:qa},stdio:['ignore','pipe','pipe']});server.stderr.resume();const [ready]=await once(server.stdout,'data');const base=JSON.parse(String(ready)).url;
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const done=async()=>{await page.waitForFunction(()=>!document.querySelector('#analyze').disabled);};
const analyze=async()=>{await page.locator('#analyze').click();await page.getByText('分析完成，JSON 已保存到输出文件夹。可进入报告中心生成解读与 PDF。',{exact:true}).waitFor();await done();};
try{
 // One-click random demo: fresh random dataset, verified against the engine, auto analysis.
 await page.goto(base);await page.locator('[data-tab=inputs]').click();
 await page.locator('#demo-panel').evaluate(el=>el.open=true);await page.locator('#demo-run').click();
 await page.locator('#message').filter({hasText:'演示完成：分析总览、复核与整改、报告中心均已生成'}).waitFor();
 let boot=await(await fetch(base+'/api/bootstrap')).json();
 // 季度（1 个已届满期）→ 5 行；月度（3 个已届满期）→ 15 行。
 assert.ok(boot.result.variance.xiang.length>=5&&boot.result.variance.xiang.length%5===0);
 assert.ok(boot.result.variance.xiang.some(x=>x.yujing==='红'));
 assert.ok(boot.result.variance.xiang.some(x=>x.yujing==='黄'));
 assert.ok(boot.result.decisions.some(x=>x.panduan==='双环'&&x.shenpi));
 assert.ok(boot.result.decisions.some(x=>x.panduan==='单环'));
 assert.ok(Object.values(boot.result.kpi).every(v=>v!=null));
 assert.ok(boot.result.trace.zhengxiang_top3.length>0&&boot.result.trace.fuxiang_top3.length>0);
 assert.ok(boot.result.correction.zong_shu>0);
 assert.match(await page.locator('#message').innerText(),/本次为随机生成/);
 const firstRecords=boot.result.records;
 await page.screenshot({path:qa+'/random-demo.png',fullPage:true});
 // A second click must produce different data (randomness is real, not canned).
 await page.locator('[data-tab=inputs]').click();await page.locator('#demo-run').click();
 await page.locator('#message').filter({hasText:'演示完成'}).waitFor();await done();
 const secondBoot=await(await fetch(base+'/api/bootstrap')).json();
 assert.notDeepEqual(secondBoot.result.records,firstRecords);
 // Real CSV file export for the teacher: BOM file lands in the output folder.
 await page.locator('[data-tab=inputs]').click();
 await page.locator('#demo-export').click();
 await page.locator('#message').filter({hasText:'已导出：'}).waitFor();await done();
 const exportedName=(await fs.readdir(qa+'/输出报告')).find(f=>f.startsWith('演示数据-'));
 assert.ok(exportedName&&exportedName.endsWith('.csv'));
 const exported=await fs.readFile(qa+'/输出报告/'+exportedName);
 assert.equal(exported[0],0xEF);assert.equal(exported[1],0xBB);assert.equal(exported[2],0xBF);
 assert.ok(exported.toString('utf8').includes('营业收入'));
 assert.equal(await page.locator('#keep-analysis-params').isChecked(),true);
 // Fixed script dataset stays available for rehearsals.
 await page.locator('#demo-fixed').click();
 await page.locator('#message').filter({hasText:'已载入固定脚本数据'}).waitFor();await done();
 boot=await(await fetch(base+'/api/bootstrap')).json();
 assert.equal(boot.result.meta.company,'青禾制造有限公司');
 // Real server-side parse path with professional parameters preserved.
 await page.locator('[data-tab=inputs]').click();await page.locator('#demo-import').click();
 await page.locator('#message').filter({hasText:'已填入演示 CSV'}).waitFor();
 assert.equal(await page.locator('#keep-analysis-params').isChecked(),true);
 await page.locator('#parse-text').click();await page.getByText('数据已解析并替换，请核对结果。',{exact:true}).waitFor();await done();
 assert.equal(await page.locator('#splits .repeat-item').count(),1);
 assert.equal(await page.locator('[data-field=bsc-0]').inputValue(),'85');
 await analyze();boot=await(await fetch(base+'/api/bootstrap')).json();assert.ok(boot.result.bsc);
 // Duplicate append import is rejected atomically and keeps the current dataset.
 await page.locator('[data-tab=inputs]').click();await page.locator('#import-mode').selectOption('append');
 await page.locator('#files').setInputFiles('desktop/experimental/reference.csv');
 await page.locator('#message').filter({hasText:'重复记录'}).waitFor();await done();
 assert.match(await page.locator('#import-summary').innerText(),/已接收 25 行/);
 await page.reload();await page.locator('[data-tab=inputs]').click();
 assert.equal(await page.locator('#period').inputValue(),'2026-Q1');
 assert.equal(await page.locator('#splits .repeat-item').count(),1);
 assert.match(await page.locator('#import-summary').innerText(),/已接收 25 行/);
 assert.deepEqual(errors,[]);
 await fs.writeFile(qa+'/result.json',JSON.stringify({randomDemo:true,randomnessVaries:true,csvExportFile:true,alertsAndDecisions:true,fixedScriptData:true,realImportKeepsParams:true,duplicateAppendAtomic:true,sessionRestore:true,pageErrors:errors},null,2));console.log(qa);
}finally{await browser.close();server.kill();}
