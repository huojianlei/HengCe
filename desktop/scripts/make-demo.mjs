// Single source of truth for the fixed demo dataset (no randomness).
// Writes experimental/demo.json (full input incl. professional parameters) and
// experimental/reference.csv (the same records as a standard 8-column CSV).
// Run: node desktop/scripts/make-demo.mjs   from the project root or desktop/.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {parseText,subjects} from '../engine.mjs';
// Budget rows are 元-level integers; the parser converts them to 分 internally.
const entries=[['营业收入',[1200000,1300000,1400000,1600000],1020000],['直接材料',[380000,420000,460000,520000],520000],['直接人工',[210000,220000,230000,240000],226800],['销售费用',[95000,100000,105000,115000],118750],['采购成本',[120000,130000,140000,150000],135600]];
const rows=[['数据类别','统计周期','数据科目','数值','单位','数据来源','更新时间','备注']];
for(const [name,budget,actual] of entries){budget.forEach((value,i)=>rows.push(['预算基础',`2026-Q${i+1}`,name,value,'元','演示数据','2026-04-01','明确标注模拟数据']));rows.push(['实时经营','2026-Q1',name,actual,'元','演示数据','2026-04-01','模拟已结账数据']);}
const csv=rows.map(r=>r.join(',')).join('\r\n')+'\r\n';
const records=parseText(csv);
if(records.jujue.length)throw new Error('演示 CSV 未通过校验：'+records.jujue.map(x=>x.yuanyin).join('；'));
const demo={company:'青禾制造有限公司',simulation:true,records,subjects:subjects(records),config:{cycle:'季度',period:'2026-Q1',growth:100,industry:50,industryThreshold:50,industryCorrection:true,noise:2500,significance:2500,tiers:[{ming_cheng:'黄',yu_fen:1500,yan_se:'#ebbf69'},{ming_cheng:'红',yu_fen:3000,yan_se:'#e68b8e'}]},
 bsc:{caijing_bps:8500,kehu_bps:9200,neibu_bps:8800,xuexi_bps:11000,quanzhong:[40,30,20,10]},
 kpi:{shouru_shiji_fen:102000000,shouru_yusuan_fen:120000000,kekong_chengben_shiji_fen:74680000,kekong_chengben_yusuan_fen:59000000,feiyong_shiji_fen:11875000,feiyong_yusuan_fen:9500000,maoli_fen:27320000,jingshui_fen:8500000,pbit_fen:11445000,ziben_zhanyong_fen:380000000,liudong_zichan_qichu_fen:180000000,liudong_zichan_qimo_fen:210000000,liudong_fuzhai_qichu_fen:70000000,liudong_fuzhai_qimo_fen:78000000,caigou_benqi_fen:13560000,caigou_shangqi_fen:12000000,shiji_chanchu:8800,qianzai_channeng:10000,dingdan_zongshu:500,lvyue_dingdan_shu:470,jiaofu_zhouqi_tian_shu:7,manyi_keshu:460,shoufang_keshu:500,jihua_yewu_liang:10000,wancheng_yewu_liang:8800,yichang_shijian_shu:5},
 splits:[{kemu:'直接材料',period:'2026-Q1',values:{biaozhun_danjia_fen:3800,biaozhun_yongliang:1,xiuding_danjia_fen:4500,xiuding_yongliang:1,shiji_chanliang:10000,shiji_yongliang:11000,shiji_chengben_fen:52000000}}],
 events:[{kemu:'直接材料',period:'2026-Q1',reason:'模拟：供应商更换导致采购单价上升，材料耗用同步增加。',structural:true}],
 traces:[{kpi_mingcheng:'毛利率',bianhua_qian:3000,bianhua_hou:2678,yuan_yusuan:3200},{kpi_mingcheng:'交付周期',bianhua_qian:500,bianhua_hou:700,yuan_yusuan:500},{kpi_mingcheng:'客户满意度',bianhua_qian:9200,bianhua_hou:9500,yuan_yusuan:9000}],baselines:[]};
await fs.writeFile(fileURLToPath(new URL('../experimental/demo.json',import.meta.url)),JSON.stringify(demo,null,2)+'\n');
await fs.writeFile(fileURLToPath(new URL('../experimental/reference.csv',import.meta.url)),'\uFEFF'+csv);
console.log('演示数据已生成：experimental/demo.json + experimental/reference.csv');
