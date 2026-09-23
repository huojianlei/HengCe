import {spawn} from 'node:child_process';import {once} from 'node:events';import fs from 'node:fs/promises';import path from 'node:path';import assert from 'node:assert/strict';import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);const {chromium}=require('C:/Users/LeiZhiBo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const payload=path.resolve('dist/FinAgent-Production');const qa=`desktop/qa/production-${Date.now()}`;await fs.mkdir(qa,{recursive:true});
const files=await fs.readdir(path.join(payload,'desktop'),{recursive:true});assert.ok(!files.some(x=>/experimental|demo\.json/.test(x)));
for(const name of ['server.mjs','web/app.mjs','web/index.html','assets.json'])assert.doesNotMatch(await fs.readFile(path.join(payload,'desktop',name),'utf8'),/experimental|load-demo|generate-experiment|demo-run|随机生成实验数据/i);
assert.equal((await fs.readFile(path.join(payload,'desktop/web/template.csv'),'utf8')).trim().split(/\r?\n/).length,1);
assert.equal(JSON.parse(await fs.readFile(path.join(payload,'desktop/distribution.json'),'utf8')).dataFolder,'FinAgent');
const server=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'desktop/server.mjs')],{env:{...process.env,FINAGENT_PORT:'0',FINAGENT_DATA_DIR:path.resolve(qa),FINAGENT_EXPERIMENTAL:'1'},stdio:['ignore','pipe','pipe']});server.stderr.resume();const [ready]=await once(server.stdout,'data');const base=JSON.parse(String(ready)).url;
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 for(const url of ['/demo.json','/reference.csv','/experimental/entry.mjs','/experimental/generator.mjs'])assert.equal((await fetch(base+url)).status,404);
 await page.goto(base+'/?experimental=true');assert.equal(await page.locator('#open-demo,#demo-panel,#demo-run').count(),0);
 await page.locator('[data-tab=inputs]').click();await page.locator('#files').setInputFiles('dist/测试文件/预算差异测试_2026Q1_模拟数据.csv');await page.locator('#message').filter({hasText:'文件已导入。'}).waitFor();await page.locator('#analyze').click();await page.locator('#message').filter({hasText:'分析完成，JSON 已保存'}).waitFor();
 const boot=await(await fetch(base+'/api/bootstrap')).json();assert.equal(boot.result.variance.xiang.length,5);assert.equal(boot.result.variance.xiang.find(x=>x.kemu==='直接材料').chalv_bps,3500);
 await page.screenshot({path:qa+'/production.png',fullPage:true});assert.deepEqual(errors,[]);
 await fs.writeFile(qa+'/result.json',JSON.stringify({experimentalFilesAbsent:true,entryCodeAbsent:true,routes404:true,envCannotEnable:true,blankTemplate:true,csvImportAndAnalysis:true,pageErrors:errors},null,2));console.log(qa);
}finally{await browser.close();server.kill();}
