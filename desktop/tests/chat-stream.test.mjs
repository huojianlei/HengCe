import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readChatStream} from '../web/chat-stream.mjs';
test('stream reader decodes split Chinese bytes and delivers before completion',async()=>{
 let controller;const events=[];const response=new Response(new ReadableStream({start(c){controller=c;}}));
 const reading=readChatStream(response,e=>events.push(e));
 const bytes=new TextEncoder().encode('{"type":"delta","text":"预算分析"}\n');
 for(const byte of bytes)controller.enqueue(Uint8Array.of(byte));
 await new Promise(r=>setTimeout(r,20));assert.equal(events[0].text,'预算分析');
 controller.enqueue(new TextEncoder().encode('{"type":"done","answer":"预算分析"}\n'));controller.close();await reading;
 assert.equal(events.length,2);
});
test('stream reader rejects interrupted, malformed and error streams',async()=>{
 for(const [text,pattern] of [['{"type":"delta","text":"半截"}\n',/中断/],['bad\n',/JSON/],['{"type":"error","message":"接口失败"}\n',/接口失败/]]){
  await assert.rejects(()=>readChatStream(new Response(text),()=>{}),pattern);
 }
});
