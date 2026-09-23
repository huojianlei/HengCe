import fs from 'node:fs/promises';import path from 'node:path';import {pathToFileURL} from 'node:url';
// Public knowledge-base embeddings remain; local generative models do not ship.
export function forbiddenLocalModel(file){
 const name=file.replaceAll('\\','/');
 return /(^|\/)(local[-_]llm|llama(?:[._-]cpp|[._-]cpp[-_]python)?|llamacpp|llama_cpp|ollama|vllm|lm[-_]?studio)(\/|[._-]|$)|(^|\/)(?:qwen|chatglm|glm[-_]?\d|deepseek[-_](?:r1|v\d))[^/]*(?:\/|$)|\.(?:gguf|ggml)$/i.test(name);
}
export async function assertNoLocalModels(root){
 const files=await fs.readdir(root,{recursive:true});
 const forbidden=files.filter(forbiddenLocalModel);
 if(forbidden.length)throw new Error('正式包仍含本地生成模型组件，拒绝封装：'+forbidden.slice(0,5).join('、'));
}
export async function assertProduction(root){
 await assertNoLocalModels(root);
 const desktop=path.join(root,'desktop');const files=await fs.readdir(desktop,{recursive:true});
 if(files.some(name=>/(^|[\\/])experimental([\\/]|$)|(^|[\\/])demo\.json$/i.test(name)))throw new Error('正式包仍含实验目录或演示数据，拒绝封装');
 const assets=JSON.parse(await fs.readFile(path.join(desktop,'assets.json'),'utf8'));
 const expectedTemplates={'/template-budget.xlsx':'templates/预算基础输入模板.xlsx','/template-actual.xlsx':'templates/实时经营输入模板.xlsx',
  '/template-industry.xlsx':'templates/行业对标输入模板.xlsx','/template-change.xlsx':'templates/经营变更输入模板.xlsx'};
 if(Object.entries(assets).some(([url,file])=>/demo|experimental/i.test(url)||!(file.startsWith('web/')||expectedTemplates[url]===file)))throw new Error('正式包资源清单仍含实验入口，拒绝封装');
 for(const file of ['web/index.html','web/app.mjs'])if(/experimental|load-demo|generate-experiment|随机生成实验数据/i.test(await fs.readFile(path.join(desktop,file),'utf8')))throw new Error(`正式包入口仍含实验代码：${file}`);
 const server=await fs.readFile(path.join(desktop,'server.mjs'),'utf8');
 if(server.includes("url==='/api/demo-excel'")&&!server.includes("if(distribution.dataFolder!=='FinAgent-Experimental')throw"))throw new Error('正式包演示API未执行版本隔离');
 for(const file of Object.values(expectedTemplates)){
  const template=await fs.readFile(path.join(desktop,file));
  if(template.subarray(0,2).toString()!=='PK')throw new Error(`正式 Excel 模板损坏：${file}`);
 }
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){await assertProduction(path.resolve(process.argv[2]));console.log('Production isolation OK');}
