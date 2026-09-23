import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';
const root=fileURLToPath(new URL('../../',import.meta.url));
const target=path.join(root,'desktop/qa/audited-tests');await fs.mkdir(target,{recursive:true});
const files=(await fs.readdir(path.join(root,'fin-agent-verify/tests'))).filter(x=>x.endsWith('.test.ts'));
for(const file of files){let text=await fs.readFile(path.join(root,'fin-agent-verify/tests',file),'utf8');text=text.replaceAll('../../plugins/fin-agent/src/',pathToFileURL(path.join(root,'release plugin(1)/release plugin/src/')).href);await fs.writeFile(path.join(target,file),text);}
const p=spawn(process.execPath,['--test',...files.map(x=>path.join(target,x))],{stdio:'inherit'});p.on('exit',code=>process.exitCode=code??1);
