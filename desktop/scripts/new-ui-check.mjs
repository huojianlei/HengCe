import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import path from 'node:path';
const require=createRequire(import.meta.url);
const {chromium}=require('C:/Users/LeiZhiBo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve('.'),dataDir=path.join(root,'desktop/qa/三栏前端验收');await fs.mkdir(dataDir,{recursive:true});
const server=spawn(process.execPath,['desktop/server.mjs'],{cwd:root,env:{...process.env,FINAGENT_DATA_DIR:dataDir,FINAGENT_PYTHON:'D:/dev-env/Python312/python.exe',TEMP:dataDir,TMP:dataDir,PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
let stderr='';server.stderr.on('data',x=>stderr+=x);const[ready]=await once(server.stdout,'data');const base=JSON.parse(String(ready)).url;
const context=await chromium.launchPersistentContext(path.join(dataDir,'浏览器缓存'),{headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',viewport:{width:1440,height:1000}});const page=context.pages()[0],errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);await page.locator('#output-dir').waitFor({state:'attached'});await page.waitForTimeout(500);
 if(await page.locator('#ai-data-access').innerText()!=='数据访问 关闭⌄'&&!(await page.locator('#ai-data-access').innerText()).includes('关闭'))throw Error('数据访问未默认关闭');
 for(const route of['budget','actual','industry','change'])if(await page.locator(`a[href="/template-${route}.xlsx"]`).count()!==1)throw Error('下载入口不完整');
 if((await page.locator('body').innerText()).includes('青禾制造'))throw Error('残留界面示例数据');
 await page.locator('#fileInput').setInputFiles(['预算基础','实时经营'].map(x=>path.join(root,`algo/fixtures/月度主体甲-${x}.xlsx`)));
 await page.locator('#import-summary').getByText('已接收 1710 行',{exact:false}).waitFor({timeout:45000});
 await page.locator('#ai-chat-log').getByText('本期是否发生过经营变更',{exact:false}).waitFor({timeout:15000});
 if(await page.locator('#intake-dialog').isVisible())await page.locator('#intake-dialog button[value="skip"]').click();
 await page.locator('#ai-chat-log').getByRole('button',{name:'无',exact:true}).click();
 await page.locator('#analyze').click();await page.locator('#message').getByText('本机分析完成',{exact:false}).waitFor({timeout:45000});
 if(!(await page.locator('#company-context').innerText()).includes('主体甲'))throw Error('主体未动态更新');
 await page.locator('[data-metric="cost"]').click();await page.locator('[data-subtab="decline"]').click();await page.locator('[data-subtab="structure"]').click();
 await page.locator('#ai-question').fill('本期实际收入是多少？');await page.locator('#ai-send').click();await page.locator('#ai-chat-log').getByText('数据访问', {exact:false}).last().waitFor({timeout:15000});
 await page.locator('#fileInput').setInputFiles(['预算基础','实时经营','行业对标','经营变更'].map(x=>path.join(root,`algo/fixtures/季度主体乙-${x}.xlsx`)));
 await page.locator('#excel-group option').nth(1).waitFor({state:'attached',timeout:45000});if(await page.locator('#intake-dialog').isVisible())await page.locator('#intake-dialog button[value="skip"]').click();
 await page.locator('#excel-group').selectOption('1');if(!(await page.locator('#company-context').innerText()).includes('主体乙'))throw Error('切换主体未同步');
 await page.locator('#analyze-batch').click();await page.locator('#message').getByText('已分别完成 2 组分析',{exact:false}).waitFor({timeout:45000});
 await page.locator('#sec-export').evaluate(el=>el.open=true);await page.locator('#btn-generate').click();await page.locator('#report-dialog').waitFor();await page.locator('#close-report').click();
 await page.screenshot({path:path.join(dataDir,'三栏主体乙.png'),fullPage:true});
 await page.setViewportSize({width:1024,height:768});await page.waitForTimeout(300);if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('1024px 横向溢出');
 await page.screenshot({path:path.join(dataDir,'三栏1024.png'),fullPage:true});
 if(errors.length)throw Error(errors.join('；'));
 console.log(JSON.stringify({ok:true,templates:4,groups:2,batch:2,missingChangeConfirmation:true,permissionDefaultOff:true,reportPreview:true,viewport1024:true,pageErrors:0}));
}finally{await context.close();server.kill();if(stderr)console.error(stderr.slice(-1000));}

