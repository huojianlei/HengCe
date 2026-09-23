// The audited release remains read-only. This adapter owns input validation and orchestration.
import { daoru_csv } from '../release plugin(1)/release plugin/src/data-ingest.ts';
import { shitu_jiexi } from '../release plugin(1)/release plugin/src/report-parse.ts';
import { gengxin_gundong_yusuan, GunDongShezhi } from '../release plugin(1)/release plugin/src/rolling-budget.ts';
import { jisuan_chayi } from '../release plugin(1)/release plugin/src/variance.ts';
import { chai_fen } from '../release plugin(1)/release plugin/src/planning-split.ts';
import { panduan_huanlu } from '../release plugin(1)/release plugin/src/loop-decision.ts';
import { chai_jimu, cong_chayi_xiang, yingshe_mokuai } from '../release plugin(1)/release plugin/src/building-blocks.ts';
import { jisuan_bsc } from '../release plugin(1)/release plugin/src/bsc.ts';
import { jisuan_kpi } from '../release plugin(1)/release plugin/src/kpi.ts';
import { jisuan_suyuan } from '../release plugin(1)/release plugin/src/suyuan.ts';
import { shengcheng_zhenggai } from '../release plugin(1)/release plugin/src/zhenggai.ts';
import { shengcheng_kanban } from '../release plugin(1)/release plugin/src/kanban.ts';
import { shengcheng_xishu } from '../release plugin(1)/release plugin/src/xishu.ts';
import { cheng_jidian } from '../release plugin(1)/release plugin/src/int-math.ts';

export function integer(value, label, min = 0, max = 9e11) {
  if (!Number.isSafeInteger(value) || value < min || value > max) throw new Error(`${label} 必须为 ${min} 至 ${max} 的整数`);
  return value;
}
export function parseText(text) {
  text = text.replace(/^\uFEFF/, '');
  let result;
  try { result = daoru_csv(text); } catch {
    const parsed = shitu_jiexi(text);
    if (!parsed.shibie) throw new Error('无法识别表格，请在导入区核对或编辑标准 CSV。' + parsed.beizhu);
    result = daoru_csv(parsed.wenben_8lie);
  }
  return result;
}
export function subjects(records) {
  return [...new Set(records.yusuan.filter(x => x.danwei === '元').map(x => x.kemu))].map(kemu => {
    const module = yingshe_mokuai(kemu);
    return { kemu, module: module ?? '', direction: module === '收入模块' ? '收入类' : module ? '成本类' : '' };
  });
}
function tiers(list) {
  if (!Array.isArray(list) || !list.length) throw new Error('至少配置一个预警档位');
  for (const x of list) { integer(x.yu_fen, '预警阈值', 0, 1000000); if (!/^#[0-9a-f]{6}$/i.test(x.yan_se)) throw new Error('预警颜色需为六位色号'); }
  return list;
}
export function analyze(input, revisions = []) {
  const records = input.records;
  if (!records?.yusuan?.length) throw new Error('请先导入年度预算');
  if (records.jujue?.length) throw new Error(`有 ${records.jujue.length} 行未通过校验，请先修正后重新导入`);
  const config = input.config;
  if (!['月度','季度'].includes(config.cycle)) throw new Error('请选择滚动周期');
  const format = config.cycle === '季度' ? /^\d{4}-Q[1-4]$/ : /^\d{4}-(0[1-9]|1[0-2])$/;
  if (!format.test(config.period)) throw new Error('分析期间格式与滚动周期不一致');
  integer(config.growth, '企业增长率', -10000, 10000);
  if (config.industry !== null) integer(config.industry, '行业增长率', -10000, 10000);
  if(config.cycle==='季度' && config.industryCorrection && config.industry===null)throw new Error('已启用季度行业修正：请填写“行业增长率（%）”，或取消勾选“启用季度行业增长率差值修正”。');
  integer(config.industryThreshold, '行业修正门限', 0, 10000);
  integer(config.noise, '噪声门限', 0, 1000000); integer(config.significance, '显著性门限', 0, 1000000);
  tiers(config.tiers);
  const bySubject = Object.fromEntries((input.subjects ?? []).map(x => [x.kemu, x]));
  const overrides = Object.fromEntries((input.subjects ?? []).filter(x => x.tiers?.length).map(x => [x.kemu, tiers(x.tiers)]));
  const budget = records.yusuan.filter(x => x.danwei === '元');
  const actual = records.shishi.filter(x => x.danwei === '元' && x.qijian <= config.period);
  for (const list of [budget, actual]) {
    const seen = new Set();
    for (const x of list) {
      if (!format.test(x.qijian) || x.qijian.slice(0,4) !== config.period.slice(0,4)) throw new Error(`期间不属于当前财年或周期：${x.qijian}`);
      integer(x.shuzhi, `${x.kemu} 金额（分）`);
      const key = `${x.qijian}\0${x.kemu}`;
      if (seen.has(key)) throw new Error(`重复记录：${x.qijian} ${x.kemu}，请核对后合并`);
      seen.add(key);
    }
  }
  if (!actual.length) throw new Error('当前分析期间内没有实际经营数据');
  const warnings = [];
  const rolling = []; const comparison = [];
  for (const name of [...new Set(budget.map(x => x.kemu))]) {
    const mapping = bySubject[name];
    if (!mapping || !['成本类','收入类'].includes(mapping.direction) || !['收入模块','成本模块','费用模块','采购模块'].includes(mapping.module)) throw new Error(`请填写 ${name} 的科目方向与模块归属`);
    if ((mapping.module === '收入模块') !== (mapping.direction === '收入类')) throw new Error(`${name} 的方向与模块不一致`);
    const original = budget.filter(x => x.kemu === name).sort((a,b) => a.qijian.localeCompare(b.qijian));
    const observed = actual.filter(x => x.kemu === name);
    for (const row of original.filter(x => x.qijian <= config.period)) {
      if (!observed.some(x => x.qijian === row.qijian)) throw new Error(`${name} ${row.qijian} 已届满但缺实际数，请在数据区补齐`);
    }
    const settings = GunDongShezhi(config.cycle, mapping.growth ?? config.growth, {
      hangye_xiuzheng: config.industryCorrection ? 'A' : 'B',
      hangye_zengzhanglv_jidian: config.industry, hangye_yuzhi_jidian: config.industryThreshold,
    });
    const fixed = original.map(x => ({ qijian:x.qijian, jine_fen:x.shuzhi }));
    const result = gengxin_gundong_yusuan(fixed, observed.map(x => ({qijian:x.qijian,jine_fen:x.shuzhi})), settings);
    // Approved revisions change future forecast only; original and closed actuals are immutable.
    let revisedSeed=null;
    for (const target of result.qijian_mingxi) {
      const revision=revisions.findLast(x=>x.kemu===name && x.period===target.qijian);
      if (target.qijian<=config.period) continue;
      if (revision) {target.shuzhi_fen=integer(revision.amount,'修订金额');target.laiyuan='人工批准的预算修订';revisedSeed=target.shuzhi_fen;}
      else if (revisedSeed!==null) {
        target.shuzhi_fen=cheng_jidian(revisedSeed,settings.zengzhanglv_jidian);
        if(result.hangye_xiuzheng_qiyong)target.shuzhi_fen=cheng_jidian(target.shuzhi_fen,settings.zengzhanglv_jidian-config.industry);
        target.laiyuan='已批准修订后链式重算';revisedSeed=target.shuzhi_fen;
      }
    }
    result.gundong_zonge_fen = result.qijian_mingxi.reduce((a,x) => a+x.shuzhi_fen,0);
    result.chae_fen = result.gundong_zonge_fen-result.chushi_zonge_fen;
    rolling.push({kemu:name, ...result});
    for (const row of observed) {
      const initial = original.find(x => x.qijian === row.qijian);
      if (!initial) throw new Error(`${name} ${row.qijian} 的实际数缺对应预算`);
      const baseline = input.baselines?.find(x => x.kemu === name && x.period === row.qijian);
      // Never compare a closed period with its replaced actual, which would erase all variances.
      comparison.push({qijian:row.qijian,kemu:name,fangxiang:mapping.direction,chushi_fen:initial.shuzhi,
        gundong_fen:baseline ? integer(baseline.amount,'届满前预算基准') : null,shiji_fen:row.shuzhi});
    }
  }
  if (actual.some(x => !budget.some(y => x.kemu === y.kemu && x.qijian === y.qijian))) throw new Error('实际数据中存在无对应预算的科目或期间');
  const variance = jisuan_chayi(comparison, config.tiers, overrides);
  for(const group of ['splits','events','baselines']){
    const seen=new Set();
    for(const item of input[group]??[]){
      const key=`${item.kemu}\0${item.period}`;
      if(seen.has(key))throw new Error(`${item.kemu} ${item.period} 存在重复的${{splits:'拆分参数',events:'变更登记',baselines:'预算基准'}[group]}`);
      seen.add(key);
      if(!comparison.some(x=>x.kemu===item.kemu&&x.qijian===item.period))throw new Error(`${item.kemu} ${item.period} 不属于本次已届满科目，无法使用其${{splits:'拆分参数',events:'变更登记',baselines:'预算基准'}[group]}`);
      if(group==='events' && item.structural && !String(item.reason||'').trim())throw new Error('结构性变更登记需要填写原因');
    }
  }
  const splits = (input.splits ?? []).map(x => ({kemu:x.kemu,period:x.period,input:x.values,result:chai_fen(x.values)}));
  const decisions = variance.xiang.map(row => {
    const split = splits.find(x => x.kemu === row.kemu && x.period === row.qijian);
    const event = input.events?.find(x => x.kemu === row.kemu && x.period === row.qijian);
    const params = {chalv_bps:row.chalv_bps,jie_gou_biangeng:event?.structural === true,bianma:event?.reason ?? '',
      guihua_zong_fen:split?.result.guihua_zong_fen ?? null,zhixing_zong_fen:split?.result.zhixing_zong_fen ?? null,
      yuandan_cbf_fen:split ? integer(split.input.shiji_chanliang*split.input.biaozhun_yongliang*split.input.biaozhun_danjia_fen,'原标准成本') : null};
    const result = panduan_huanlu(params, config.noise, config.significance);
    return {kemu:row.kemu,period:row.qijian,input:params,...result};
  });
  // Legacy block validation knows four alert names; map the display-only field at this boundary.
  const blocks = chai_jimu(variance.xiang.map(x=>cong_chayi_xiang({...x,yujing:['无','—','黄','红'].includes(x.yujing)?x.yujing:'黄'})), name => bySubject[name]?.module ?? null);
  for(const block of blocks.mokuai_lie)for(const row of block.mingxi)row.yujing=variance.xiang.find(x=>x.kemu===row.kemu&&x.qijian===row.qijian).yujing;
  const bsc = input.bsc ? jisuan_bsc(input.bsc) : null;
  if (!bsc) warnings.push('BSC 四维达成率未填写，暂不评分');
  const kpi = jisuan_kpi(input.kpi ?? {});
  const trace = input.traces?.length ? jisuan_suyuan(input.traces) : null;
  if (!trace) warnings.push('未填写变更前后指标，暂不计算双维溯源');
  if (!splits.length) warnings.push('未提供规划/执行拆分参数，判定表将标明缺失线索');
  const correction = shengcheng_zhenggai({chayi:variance,jimu:blocks,panduan:null});
  // Custom warning names still create actions; the audited tool recognizes only 红/黄.
  for (const row of variance.xiang.filter(x => !['无','—','红','黄'].includes(x.yujing))) {
    correction.qingdan.push({leixing:'关注整改',youxianji:'中',zeren_mokuai:bySubject[row.kemu].module,kemu:row.kemu,qijian:row.qijian,miaoshu:`${row.kemu} 触发 ${row.yujing} 档位，请复核并整改`,shenpi:false,zhuangtai:'待整改'});
  }
  for (const decision of decisions) {
    const item = shengcheng_zhenggai({panduan:decision,chayi:null,jimu:null});
    correction.qingdan.push(...item.qingdan.map(x => ({...x,kemu:decision.kemu,qijian:decision.period,zeren_mokuai:bySubject[decision.kemu].module})));
  }
  correction.qingdan = correction.qingdan.map((x,i) => ({...x,id:`action-${i+1}`,zhuangtai:'待整改'}));
  recount(correction);
  const dashboard = shengcheng_kanban({chayi:variance,jimu:blocks,bsc,kpi,suyuan:trace,zhenggai:correction});
  const factors = shengcheng_xishu({chayi:variance,jimu:blocks,bsc,zhenggai:correction,panduan:decisions.find(x=>x.shenpi) ?? decisions[0]});
  return {schemaVersion:'1.0',meta:{company:input.company || '企业预算',period:config.period,cycle:config.cycle,simulation:input.simulation===true,generatedAt:new Date().toISOString(),moneyUnit:'分',rateUnit:'基点'},config,
    records,subjects:input.subjects,rolling,variance,splits,decisions,blocks,bsc,kpi,trace,correction,dashboard,factors,warnings,revisions};
}
export function recount(c) {
  c.zong_shu=c.qingdan.length;
  for (const [field,value] of [['gao_shu','高'],['zhong_shu','中'],['di_shu','低']]) c[field]=c.qingdan.filter(x=>x.youxianji===value).length;
  for (const [field,value] of [['daizhenggai_shu','待整改'],['jinxingzhong_shu','进行中'],['wancheng_shu','已完成']]) c[field]=c.qingdan.filter(x=>x.zhuangtai===value).length;
}
