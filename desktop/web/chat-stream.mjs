// TextDecoder preserves Chinese characters even when network chunks split UTF-8 bytes.
export async function readChatStream(response,onEvent){
  if(!response.ok){const data=await response.json();throw new Error(data.error||'问答请求失败');}
  if(!response.body)throw new Error('浏览器不支持流式读取');
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='',done=false;
  const line=text=>{if(!text.trim())return;if(done)throw new Error('问答结束后收到异常数据');const event=JSON.parse(text);if(event.type==='error')throw new Error(event.message||'问答生成失败');if(event.type==='done')done=true;onEvent(event);};
  try{
    while(true){const chunk=await reader.read();pending+=decoder.decode(chunk.value,{stream:!chunk.done});let i;while((i=pending.indexOf('\n'))!==-1){line(pending.slice(0,i));pending=pending.slice(i+1);}if(pending.length>2e6)throw new Error('问答响应过大');if(chunk.done)break;}
    if(pending.trim())line(pending);
    if(!done)throw new Error('连接已中断，回答尚未完成核验，请重试');
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
