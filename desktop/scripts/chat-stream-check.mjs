import http from 'node:http';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('C:/Users/LeiZhiBo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const qa=`desktop/qa/chat-stream-${Date.now()}`;await fs.mkdir(qa,{recursive:true});
let release,mode='pass',disconnected=false,requests=0;
const model=http.createServer(async(req,res)=>{
 const chunks=[];for await(const x of req)chunks.push(x);const body=JSON.parse(Buffer.concat(chunks));
 assert.equal(body.stream,true);assert.equal(req.headers.authorization,'Bearer local-test-only');requests++;
 if(mode==='http-error'){res.writeHead(401);res.end('do not expose upstream details');return;}
 res.writeHead(200,{'Content-Type':'text/event-stream'});
 const event=text=>res.write('data: '+JSON.stringify({choices:[{delta:{content:text},finish_reason:null}]})+'\r\n\r\n');
 // Split a Chinese code point at the TCP write boundary.
 const first=Buffer.from('data: '+JSON.stringify({choices:[{delta:{content:'建议复核'},finish_reason:null}]})+'\n\n');
 const split=first.indexOf(Buffer.from('建'))+1;res.write(first.subarray(0,split));res.write(first.subarray(split));
 res.on('close',()=>{disconnected=true;});
 if(mode==='disconnect'){res.end();return;}
 if(mode==='cancel'){const heartbeat=setInterval(()=>res.write(': keep-alive\n\n'),100);res.on('close',()=>clearInterval(heartbeat));return;}
 await new Promise(r=>{release=r;});
 event(mode==='reject'?'不存在的指标为98765432123456789。':'预算执行偏差。');
 res.write('data: '+JSON.stringify({choices:[{delta:{},finish_reason:'stop'}]})+'\n\n');res.end('data: [DONE]\n\n');
});
model.listen(0,'127.0.0.1');await once(model,'listening');
const server=spawn(process.execPath,[process.env.FINAGENT_SERVER_FILE||'desktop/server.mjs'],{env:{...process.env,FINAGENT_PORT:'0',FINAGENT_DATA_DIR:qa,FINAGENT_PYTHON:process.cwd()+'/dist/FinAgent/runtime/python/python.exe',PYTHONDONTWRITEBYTECODE:'1'},stdio:['ignore','pipe','pipe']});
server.stderr.resume();const [ready]=await once(server.stdout,'data');const base=JSON.parse(String(ready)).url;
const token=(await(await fetch(base+'/api/bootstrap')).json()).token;
const post=(route,data)=>fetch(base+'/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Finagent-Token':token},body:JSON.stringify(data)});
const fixture=JSON.parse(await fs.readFile('desktop/experimental/demo.json','utf8'));assert.equal((await post('analyze',fixture)).status,200);
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);
 await page.locator('[data-tab=settings]').click();
 await page.locator('#api-key').fill('local-test-only',{force:true});
 await page.locator('#endpoint').fill(`http://127.0.0.1:${model.address().port}`,{force:true});
 // Activate the question's existing page through the navigation.
 const pageId=await page.locator('#question').evaluate(el=>el.closest('.page').id);
 await page.locator(`[data-tab="${pageId}"]`).click();
 const ask=async(m)=>{mode=m;release=null;disconnected=false;await page.locator('#question').fill('请解释预算执行分析');await page.locator('#ask').click();};
 const bubble=()=>page.locator('#chat-log > .chat-message:not(.user)').last();
 await ask('pass');await bubble().getByText('建议复核',{exact:true}).waitFor({timeout:120000});
 assert.match(await bubble().innerText(),/尚未完成/);assert.equal(await page.locator('#ask').isDisabled(),true);
 await page.screenshot({path:qa+'/streaming.png',fullPage:true});release();
 await bubble().getByText('回答已完成 · 通过',{exact:true}).waitFor();assert.match(await bubble().innerText(),/建议复核预算执行偏差。/);
 await ask('reject');await bubble().getByText('建议复核',{exact:true}).waitFor({timeout:120000});release();
 await bubble().getByText('回答已完成 · 拒绝',{exact:true}).waitFor();assert.doesNotMatch(await bubble().innerText(),/98765432123456789/);
 await ask('disconnect');await bubble().getByText('本次回答未完成，未保留尚未核验的内容。',{exact:true}).waitFor({timeout:120000});
 await ask('http-error');await bubble().getByText('本次回答未完成，未保留尚未核验的内容。',{exact:true}).waitFor({timeout:120000});assert.match(await bubble().innerText(),/HTTP 401/);
 await ask('cancel');await bubble().getByText('建议复核',{exact:true}).waitFor({timeout:120000});await bubble().getByRole('button',{name:'停止生成'}).click();
 await bubble().getByText('已停止生成，可修改问题后重新提问。',{exact:true}).waitFor();
 for(let i=0;i<100&&!disconnected;i++)await new Promise(r=>setTimeout(r,50));assert.ok(disconnected,'stop closes model socket');
 let unlocked=false;for(let i=0;i<100;i++){const r=await post('settings',{});if(r.status===200){unlocked=true;break;}await new Promise(r=>setTimeout(r,50));}assert.ok(unlocked,'stop releases server operation lock');
 // No key: retain local retrieval, never call the remote model.
 const calls=requests;await page.locator('[data-tab=settings]').click();await page.locator('#api-key').fill('');await page.locator('[data-tab=assistant]').click();await ask('unused');await bubble().getByText('回答已完成 · 未配置模型',{exact:true}).waitFor({timeout:120000});assert.equal(requests,calls);
 assert.deepEqual(errors,[]);await page.screenshot({path:qa+'/completed.png',fullPage:true});
 await fs.writeFile(qa+'/result.json',JSON.stringify({streamBeforeCompletion:true,utf8:true,validationRejection:true,disconnect:true,httpError:true,cancelSocket:true,busyReleased:true,noKey:true,pageErrors:errors},null,2));console.log(qa);
}finally{release?.();await browser.close();server.kill();model.closeAllConnections();model.close();}
