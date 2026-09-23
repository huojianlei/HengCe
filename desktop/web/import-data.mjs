const groups=['yusuan','shishi','hangye','biangeng','jujue'];
export function combineImports(items){
 const records=Object.fromEntries(groups.map(k=>[k,[]]));records.ruku_shu=0;const subjects=[];
 for(const item of items){for(const k of groups)records[k].push(...item.records[k]);records.ruku_shu+=item.records.ruku_shu;for(const row of item.subjects)if(!subjects.some(x=>x.kemu===row.kemu))subjects.push(structuredClone(row));}
 for(const group of ['yusuan','shishi']){const seen=new Set();for(const row of records[group]){const key=[row.qijian,row.kemu,row.danwei].join('\0');if(seen.has(key))throw new Error(`重复记录：${row.qijian} ${row.kemu}。当前数据未更改；导入完整文件请选择“替换当前数据”，分文件追加时请移除重叠记录。`);seen.add(key);}}
 return {records,subjects};
}
export function inferScope(records){
 const rows=[...records.yusuan,...records.shishi].filter(x=>x.danwei==='元');
 if(!rows.length || new Set(rows.map(x=>x.qijian.slice(0,4))).size!==1)return null;
 const cycle=rows.every(x=>/^\d{4}-Q[1-4]$/.test(x.qijian))?'季度':rows.every(x=>/^\d{4}-(0[1-9]|1[0-2])$/.test(x.qijian))?'月度':null;
 if(!cycle)return null;
 const actual=records.shishi.filter(x=>x.danwei==='元').map(x=>x.qijian).sort();
 return {cycle,period:actual.at(-1)||rows.map(x=>x.qijian).sort()[0]};
}
export function recordsCSV(records){
 const quote=x=>{const text=String(x??'');return /[",\r\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text;};
 const rows=[['数据类别','统计周期','数据科目','数值','单位','数据来源','更新时间','备注']];
 for(const key of ['yusuan','shishi','hangye','biangeng'])for(const r of records[key])rows.push([r.leibie,r.qijian,r.kemu,['元','%'].includes(r.danwei)?r.shuzhi/100:r.shuzhi,r.danwei,r.laiyuan,r.gengxin_shijian,r.beizhu]);
 return rows.map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
}
