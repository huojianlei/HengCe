import fs from 'node:fs/promises';import path from 'node:path';import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const target=path.resolve(process.argv[2]||'');const flavor=process.argv[3]||'Production';
if(!target.startsWith(path.join(root,'dist')+path.sep)||!['Production','Experimental'].includes(flavor))throw new Error('Invalid build destination or flavor');
const here=path.join(target,'desktop');await fs.mkdir(here,{recursive:true});
// Delete only verified, builder-owned web/extension directories inside the chosen dist payload.
for(const name of ['web','experimental']){const dir=path.resolve(here,name);if(!dir.startsWith(target+path.sep))throw new Error('Unsafe build cleanup path');await fs.rm(dir,{recursive:true,force:true});}
const source=JSON.parse(await fs.readFile(path.join(root,'desktop/assets.json'),'utf8'));
const assets=Object.fromEntries(Object.entries(source).filter(([,file])=>flavor==='Experimental'||!file.startsWith('experimental/')));
for(const file of Object.values(assets)){const dest=path.join(here,file);await fs.mkdir(path.dirname(dest),{recursive:true});await fs.copyFile(path.join(root,'desktop',file),dest);}
const html=path.join(here,'web/index.html');let text=await fs.readFile(html,'utf8');
if(flavor==='Production')text=text.replace(/<!-- EXPERIMENTAL_BEGIN -->[\s\S]*?<!-- EXPERIMENTAL_END -->/g,'');
await fs.writeFile(html,text);
await fs.writeFile(path.join(here,'assets.json'),JSON.stringify(assets,null,2));
await fs.writeFile(path.join(here,'distribution.json'),JSON.stringify({dataFolder:flavor==='Experimental'?'FinAgent-Experimental':'FinAgent',mutexName:flavor==='Experimental'?'FinAgent105.Experimental.Desktop.Running':'FinAgent105.Desktop.Running'}));
await fs.writeFile(path.join(target,'build-flavor.txt'),flavor+'\n');
if(flavor==='Production'){
 const files=await fs.readdir(path.join(here,'web'));
 for(const f of files){if(/demo|experimental/i.test(f))throw new Error('Experimental file leaked');const body=await fs.readFile(path.join(here,'web',f),'utf8');if(/experimental|load-demo|generate-experiment|随机生成实验数据/i.test(body))throw new Error(`Experimental code leaked: ${f}`);}
}
console.log(`Prepared ${flavor} desktop assets`);
