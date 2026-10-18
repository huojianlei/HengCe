import { createDemoData } from './演示数据.mjs';

const host = window.hengceHost;
export const isLive = !!host;
let demo;
const copy = value => structuredClone(value);
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const required = data => ['预算基础', '实时经营'].every(category => data.files.some(f => f.category === category && f.status === 'valid'));
const snapshots = new Map();
const baseline = () => {
  const data = createDemoData();
  for (const item of data.history) snapshots.set(item.id, copy(data));
  return data;
};

export function subscribe(callback) {
  return typeof host?.subscribe === 'function' ? host.subscribe(callback) : () => {};
}

export async function request(action, payload = {}) {
  if (isLive) {
    if (host.version !== '1.0' || typeof host.request !== 'function') throw new Error('宿主接口版本不兼容，请检查衡策插件接入。');
    return host.request(action, payload);
  }
  if (!demo) demo = baseline();
  switch (action) {
    case 'workspace.load': return copy(demo);
    case 'demo.reset': demo = baseline(); return copy(demo);
    case 'files.import': {
      if (payload.files.some(f => !/\.xlsx$/i.test(f.name))) throw new Error('请选择 .xlsx 工作簿。');
      if (payload.files.some(f => f.size > 28 * 1024 * 1024)) throw new Error('单个工作簿不能超过 28 MB。');
      const selected = payload.files.map((f, i) => ({ id:`selected-${Date.now()}-${i}`, name:f.name, size:f.size, category:payload.category || ['预算基础','实时经营','行业对标','经营变更'].find(c=>f.name.includes(c)) || '待识别', status:'pending', checks:0, rows:0, entity:'待校验' }));
      demo.files = payload.mode === 'replace' ? selected : [...demo.files, ...selected];
      demo.dirty = true;
      return copy(demo);
    }
    case 'files.remove': demo.files = demo.files.filter(f=>f.id!==payload.id); demo.dirty=true; return copy(demo);
    case 'templates.download': throw new Error('演示预览未附带标准工作簿。接入衡策插件后可下载正式空白模板。');
    case 'analysis.run': {
      if (!required(demo)) throw new Error('请先准备校验通过的预算基础和实时经营工作簿。');
      if (demo.files.some(f=>f.status==='pending')) throw new Error('所选本地文件尚未通过后端校验。可移除这些文件，或重新载入演示数据。');
      if (payload.config.period !== '2027-06' || payload.config.cycle !== '月度') throw new Error('演示数据仅包含 2027 年 6 月月度分析。其他期间与季度分析将在接入后端后可用。');
      await pause(900);
      demo.config = copy(payload.config);
      demo.rows.forEach(row => {
        const tiers = demo.config.tiers;
        const magnitude = row.direction === 'unfavorable' ? Math.abs(row.rate) : 0;
        row.risk = magnitude >= tiers[tiers.length-1].threshold ? 'high' : magnitude >= tiers[0].threshold ? 'watch' : 'normal';
        const tier = [...tiers].reverse().find(t => magnitude >= t.threshold);
        row.tierName = tier?.name;
        row.tierColor = tier?.color;
      });
      demo.dirty=false;
      demo.meta.generatedAt = new Date().toISOString();
      demo.meta.runId = `demo-${Date.now()}`;
      const record = {id:demo.meta.runId,period:demo.meta.period,company:demo.meta.company,createdAt:demo.meta.generatedAt,status:'done',riskCount:demo.rows.filter(r=>r.risk!=='normal').length};
      demo.history.unshift(record);
      snapshots.set(record.id, copy(demo));
      return copy(demo);
    }
    case 'background.save': demo.background=copy(payload); demo.dirty=true; return copy(demo);
    case 'actions.update': {
      if (!['pending','doing','done'].includes(payload.status)) throw new Error('整改状态无效。');
      const item=demo.actions.find(a=>a.id===payload.id);
      if(!item) throw new Error('未找到该整改事项。');
      item.status=payload.status;
      return copy(demo);
    }
    case 'revisions.approve': {
      if (!payload.approved || !payload.reason?.trim()) throw new Error('请填写修订原因并确认人工批准。');
      if (!/^2027-(07|08|09|10|11|12)$/.test(payload.period)) throw new Error('演示修订仅支持 2027 年 7—12 月的未来预算。');
      if(!Number.isSafeInteger(payload.amount) || payload.amount<0) throw new Error('修订金额必须为非负金额，最多两位小数。');
      const row=demo.rows.find(r=>r.id===payload.rowId);
      if(!row) throw new Error('科目不存在。');
      demo.revisions.unshift({...copy(payload), id:`rev-${Date.now()}`,subject:row.subject,createdAt:new Date().toISOString(),demo:true});
      return copy(demo);
    }
    case 'reports.generate': {
      if (demo.dirty) throw new Error('数据或参数已变更，请先重新分析。');
      await pause(650);
      demo.reports.unshift({id:`report-${Date.now()}`,title:'2027 年 6 月经营分析报告',period:demo.meta.period,createdAt:new Date().toISOString(),status:'ready',format:'PDF',pages:null,includeAI:payload.includeAI,demo:true});
      return copy(demo);
    }
    case 'history.open': {
      const previous=snapshots.get(payload.id);
      if(!previous) throw new Error('该记录未附带演示快照，请选择本次运行生成的记录。');
      const history=demo.history;
      demo=copy(previous);
      demo.history=history;
      return copy(demo);
    }
    case 'assistant.ask': {
      if(!payload.dataAccess) throw new Error('请先允许访问当前分析结果。');
      await pause(650);
      const row=demo.rows.find(r=>r.id===payload.context?.rowId) || demo.rows.find(r=>r.risk==='high');
      return {text:`这是演示解读，未调用真实模型。\n\n${row.subject}的预算为 ${(row.budget/100).toLocaleString('zh-CN',{minimumFractionDigits:2})} 元，实际为 ${(row.actual/100).toLocaleString('zh-CN',{minimumFractionDigits:2})} 元，偏差率为 ${(row.rate/100).toFixed(2)}%。\n\n${row.reason}\n\n建议先核对来源记录与经营变更，再根据「${row.decision}」处理。你可以从差异明细打开此项，查看来源或发起预算修订。`,sources:[{title:'本次演示分析结果',excerpt:`${row.source}；该引用为演示数据来源，不是法规依据。`}]};
    }
    case 'reports.openFolder': throw new Error('浏览器预览由浏览器管理下载位置；宿主接入后可直接打开输出文件夹。');
    default: throw new Error(`当前预览未提供此操作：${action}`);
  }
}

export function canAnalyze(data) { return required(data) && !data.files.some(f=>f.status==='pending'); }
