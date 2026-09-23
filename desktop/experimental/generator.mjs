// Demo-only randomized generator (experimental flavor; production builds never copy this file).
//
// Numbers change on every call; pass an explicit seed for a reproducible dataset.
// Every dataset is constrained so the showcase pipeline always completes end to end:
//   · exactly one cost subject carries the structural story -> 红 + 双环（必审）,
//     built so 执行差异 stays below the significance threshold while 结构变更登记 = true
//     (loop-decision 情形 3 must be reached, never 情形 4 混合纠错模式);
//   · one subject sits in the 26%–29% band without a change registration -> 黄 + 单环;
//   · an optional subject in the 16%–23% band -> 黄 but 不触发（噪声对比）;
//   · remaining subjects stay inside ±11% so no extra alert appears;
//   · BSC / KPI / 溯源 inputs are fully populated so no module reports 缺数.
// The UI still verifies each generation against the real engine and retries before falling
// back to the fixed script dataset, so a presenter never sees an error screen.
const SUBJECTS=[
 ['营业收入','收入模块','收入类',120000000],
 ['直接材料','成本模块','成本类',38000000],
 ['直接人工','成本模块','成本类',21000000],
 ['销售费用','费用模块','成本类',9500000],
 ['采购成本','采购模块','成本类',12000000],
];
const COMPANIES=['青禾制造有限公司','明远建材有限公司','汇川食品有限公司','恒盛机械有限公司','安泰纺织有限公司','瑞禾食品有限公司'];
const STORY_SUBJECTS=['直接材料','直接人工','采购成本'];
const STORY_REASONS=['模拟：供应商更换导致采购单价上升，耗用同步增加。','模拟：工艺调整后单位耗用上升，采购价格同期上涨。','模拟：订单结构变化，规格升级推高单位成本。','模拟：区域供应紧张，采购单价上浮且用量增加。'];
const TRACE_UP='客户满意度';
export function generate(seed){
 const state0=Number.isSafeInteger(seed)&&seed>0?seed:Math.floor(Math.random()*2147483646)+1;
 let s=state0;
 const rnd=()=>{s=(Math.imul(1664525,s)+1013904223)>>>0;return s/4294967296;};
 const int=(min,max)=>min+Math.floor(rnd()*(max-min+1));
 const pick=list=>list[Math.floor(rnd()*list.length)];
 const company=pick(COMPANIES);
 const year=int(2026,2027);
 const cycle=rnd()<0.7?'季度':'月度';
 const total=cycle==='季度'?4:12;
 const closed=cycle==='季度'?1:3;
 const period=n=>cycle==='季度'?`${year}-Q${n}`:`${year}-${String(n).padStart(2,'0')}`;
 // 行业差值修正仅季度适用（月度取值会让引擎拒绝启用）；增长率差值保持在门限之上。
 const industryCorrection=cycle==='季度'&&rnd()<0.65;
 const industry=industryCorrection?int(25,90):null;
 const growth=int(60,150);
 const story=pick(STORY_SUBJECTS);
 const others=SUBJECTS.map(([k])=>k).filter(k=>k!==story);
 const loop=pick(others);
 const noiseCandidate=pick(others.filter(k=>k!==loop));
 const withNoise=rnd()<0.7;
 // 角色 → 差异率（基点，绝对值）：红=32%~48%；单环=26%~29%；噪声黄=16%~23%；其余 ≤11%
 const devBps=kemu=>{
  if(kemu===story)return int(3200,4800);
  if(kemu===loop)return int(2600,2950);
  if(withNoise&&kemu===noiseCandidate)return int(1600,2300);
  return int(200,1100);
 };
 const rows={yusuan:[],shishi:[]};
 let line=2;
 const push=(group,leibie,qijian,kemu,shuzhi,beizhu)=>rows[group].push({hanghao:line++,leibie,qijian,kemu,shuzhi,danwei:'元',laiyuan:'演示数据',gengxin_shijian:`${year}-12-31`,beizhu});
 const budgetOf={},actualOf={};
 for(const [kemu,,direction,base] of SUBJECTS){
  for(let n=1;n<=total;n++){
   // 逐期温和上浮 + 科目各自波动；金额保持整数分。
   const trend=10000+int(0,60)*(n-1);
   const jitter=int(8800,11200);
   const value=Math.max(100000,Math.round(base*(trend/10000)*(jitter/10000)/1000)*1000);
   budgetOf[`${kemu}|${n}`]=value;
   push('yusuan','预算基础',period(n),kemu,value,'明确标注模拟数据');
  }
  // 已届满期间必须有实际数；符号按科目方向（收入类 = 缺口，成本类 = 超支）
  for(let n=1;n<=closed;n++){
   const dev=devBps(kemu);
   const signed=direction==='收入类'?-dev:dev;
   const value=Math.round(budgetOf[`${kemu}|${n}`]*(10000+signed)/10000/100)*100;
   actualOf[`${kemu}|${n}`]=value;
   push('shishi','实时经营',period(n),kemu,value,'模拟已结账数据');
  }
 }
 const records={...rows,hangye:[],biangeng:[],jujue:[],ruku_shu:rows.yusuan.length+rows.shishi.length};
 // 规划/执行拆分 + 结构变更登记：只给故事科目首期，且执行差异率 < 显著阈值 → 情形 3 双环。
 const storyBudget=budgetOf[`${story}|1`],storyActual=actualOf[`${story}|1`];
 const chanliang=pick([8000,10000,12000,15000]);
 const biaozhunDanjia=Math.max(1,Math.round(storyBudget/chanliang));
 const yuandan=chanliang*biaozhunDanjia;
 const totalRate=Math.round((storyActual-yuandan)/yuandan*10000);       // 总差异率（基点）
 const zhixingRate=Math.round(totalRate*int(20,35)/100);               // 执行分量（< 25% 安全）
 const xiudingDanjia=Math.max(1,Math.round(yuandan*(10000+totalRate-zhixingRate)/10000/chanliang));
 const shijiYongliang=Math.round(chanliang*(10000+int(-600,900))/10000);
 const splits=[{kemu:story,period:period(1),values:{biaozhun_danjia_fen:biaozhunDanjia,biaozhun_yongliang:1,xiuding_danjia_fen:xiudingDanjia,xiuding_yongliang:1,shiji_chanliang:chanliang,shiji_yongliang:shijiYongliang,shiji_chengben_fen:storyActual}}];
 const events=[{kemu:story,period:period(1),reason:pick(STORY_REASONS),structural:true}];
 const baselines=[]; // 届满前滚动基准留空：不改变已核对的差异率口径
 // 双维溯源：一条正向（满意度升）+ 两条负向（毛利率降、交付周期升），量级随机。
 const traces=[
  {kpi_mingcheng:TRACE_UP,bianhua_qian:int(8600,9200),bianhua_hou:0,yuan_yusuan:int(8500,9000)},
  {kpi_mingcheng:'毛利率',bianhua_qian:int(3000,3600),bianhua_hou:0,yuan_yusuan:int(3100,3700)},
  {kpi_mingcheng:'交付周期',bianhua_qian:int(420,560),bianhua_hou:0,yuan_yusuan:int(450,600)},
 ];
 traces[0].bianhua_hou=traces[0].bianhua_qian+int(150,450);
 traces[1].bianhua_hou=traces[1].bianhua_qian-int(180,600);
 traces[2].bianhua_hou=traces[2].bianhua_qian+int(80,260);
 // BSC：四维达成率 70%~115%，权重为和恰为 100 的整数（模块强校验）。
 let quanzhong;
 do{const a=int(25,45),b=int(15,35),c=int(8,25);quanzhong=[a,b,c,100-a-b-c];}while(quanzhong[3]<5||quanzhong[3]>40);
 const bsc={caijing_bps:int(7600,10400),kehu_bps:int(8200,11400),neibu_bps:int(7800,10800),xuexi_bps:int(8800,11800),quanzhong};
 // KPI：营收/成本沿用生成记录（口径自洽），其余在合理区间取随机整数。
 const revB=budgetOf['营业收入|1'],revA=actualOf['营业收入|1'];
 const cailiaoA=actualOf['直接材料|1'],rengongA=actualOf['直接人工|1'],xiaoshouA=actualOf['销售费用|1'];
 const cailiaoB=budgetOf['直接材料|1'],rengongB=budgetOf['直接人工|1'],xiaoshouB=budgetOf['销售费用|1'];
 const maoli=Math.max(1,revA-cailiaoA-rengongA),dingdan=int(320,680);
 const wancheng=Math.round(dingdan*int(8800,9800)/10000);
 const kpi={
  shouru_shiji_fen:revA,shouru_yusuan_fen:revB,
  kekong_chengben_shiji_fen:cailiaoA+rengongA,kekong_chengben_yusuan_fen:cailiaoB+rengongB,
  feiyong_shiji_fen:xiaoshouA,feiyong_yusuan_fen:xiaoshouB,maoli_fen:maoli,
  jingshui_fen:Math.round(maoli*int(22,42)/100),pbit_fen:Math.round(maoli*int(35,60)/100),
  ziben_zhanyong_fen:Math.round(revB*int(240,360)/100),
  liudong_zichan_qichu_fen:Math.round(revB*int(120,170)/100),liudong_zichan_qimo_fen:Math.round(revB*int(130,180)/100),
  liudong_fuzhai_qichu_fen:Math.round(revB*int(45,70)/100),liudong_fuzhai_qimo_fen:Math.round(revB*int(50,75)/100),
  caigou_benqi_fen:actualOf['采购成本|1'],caigou_shangqi_fen:budgetOf['采购成本|1'],
  shiji_chanchu:chanliang,qianzai_channeng:Math.round(chanliang*int(105,130)/100),
  dingdan_zongshu:dingdan,lvyue_dingdan_shu:wancheng,jiaofu_zhouqi_tian_shu:int(4,12),
  manyi_keshu:Math.round(dingdan*int(8500,9700)/100),shoufang_keshu:dingdan,
  jihua_yewu_liang:chanliang,wancheng_yewu_liang:Math.round(chanliang*int(8500,9600)/100),
  yichang_shijian_shu:int(2,14),
 };
 return {company:`${company}（随机演示）`,simulation:true,records,
  subjects:SUBJECTS.map(([kemu,module,direction])=>({kemu,module,direction})),
  config:{cycle,period:period(closed),growth,industry,industryThreshold:50,industryCorrection,noise:2500,significance:2500,
   tiers:[{ming_cheng:'黄',yu_fen:1500,yan_se:'#ebbf69'},{ming_cheng:'红',yu_fen:3000,yan_se:'#e68b8e'}]},
  bsc,kpi,splits,events,traces,baselines};
}
