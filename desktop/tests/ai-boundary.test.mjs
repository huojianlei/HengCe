import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {prepareAiRequest} from '../ai-boundary.mjs';
import {analyze} from '../engine.mjs';
import {forbiddenLocalModel} from '../../packaging/assert-production.mjs';
test('permission gate never touches result and requires literal boolean true',()=>{
 const poison=new Proxy({}, {get(){throw Error('must not read financial data');}});
 for(const value of [undefined,false,'on','true',1])assert.equal(prepareAiRequest(poison,{dataAccess:value}).allowed,false);
});
test('outbound DTO excludes workbook, notes, paths, credentials and arbitrary model fields',async()=>{
 const input=JSON.parse(await fs.readFile(new URL('../experimental/demo.json',import.meta.url)));
 const result=analyze(input);result.records.secret='RAW_SECRET';result.meta.apiKey='KEY_SECRET';result.paths=['FILE_SECRET'];
 result.variance.xiang[0].notes='NOTE_SECRET';result.decisions[0].input.bianma='LEDGER_SECRET';
 const {request}=prepareAiRequest(result,{dataAccess:true,op:'chat',question:'解释差异'});
 assert.equal(request.data.variance.length,result.variance.xiang.length);
 assert.equal(request.data.modules.length,4);
 assert.ok(!JSON.stringify(request).includes('SECRET'));
 assert.deepEqual(Object.keys(request.data).sort(),['modules','period','schemaVersion','units','variance']);
 assert.equal(request.data.variance[0].baselineAmount,result.variance.xiang[0].jizhun_fen);
});
test('formal package exclusion detects local generative runtimes and weights but retains public KB embeddings',()=>{
 for(const name of ['local-llm/panel/serve.py','runtime/llama_cpp/a.py','models/Qwen3-8B/weights.bin','models/GLM-4.6/a','a/weights.gguf','a/llama-server.exe'])assert.ok(forbiddenLocalModel(name),name);
 assert.equal(forbiddenLocalModel('kb2/models/bge-small-zh-v1.5/model.safetensors'),false);
});
