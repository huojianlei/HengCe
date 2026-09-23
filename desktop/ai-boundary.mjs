// Financial data crosses this boundary only as a newly constructed result DTO.
export const AI_ACCESS_DENIED = '数据访问权限当前关闭，AI 无法读取或解释本次财务数据。工作簿解析、勾稽校验与数值计算均在本机完成；开启“数据访问”后，模型仅接收本次已核验的科目、期间、金额与判定结果，原始工作簿始终不上传。';
const modules = new Set(['收入模块','成本模块','费用模块','采购模块']);
const decisions = new Set(['不触发','单环','双环','混合纠错模式','复核提示','待确认','待补充经营变更']);
const period = x => typeof x === 'string' && /^\d{4}-(?:0[1-9]|1[0-2]|Q[1-4])$/.test(x) ? x : '';
const amount = x => Number.isSafeInteger(x) ? x : null;
const direction = x => ['A','F','N'].includes(x) ? x : '';
export function prepareAiRequest(result, {dataAccess = false, op = 'chat', question = ''} = {}) {
  // Do not even dereference result before the permission gate.
  if (dataAccess !== true) return {allowed:false,response:{answer:AI_ACCESS_DENIED,status:'权限关闭',references:[],failures:[]}};
  if (!['chat','enrich'].includes(op)) throw new Error('不支持的 AI 操作');
  if (!Array.isArray(result?.variance?.xiang)) throw new Error('请先完成本次本机分析');
  const bySubject = new Map((result.subjects ?? []).map(x=>[x.kemu,x.module]));
  const byDecision = new Map((result.decisions ?? []).map(x=>[`${x.kemu}\0${x.period}`,x]));
  const data = {schemaVersion:'ai-results/1',period:period(result.meta?.period),units:{amount:'分',rate:'基点'},
    variance:result.variance.xiang.map(row=>{
      if(typeof row.kemu !== 'string' || row.kemu.length > 180) throw new Error('科目名称不符合模型结果契约');
      const d=byDecision.get(`${row.kemu}\0${row.qijian}`), module=row.module ?? bySubject.get(row.kemu);
      return {subject:row.kemu,period:period(row.qijian),module:modules.has(module)?module:'',
        budgetAmount:amount(row.chushi_fen),baselineAmount:amount(row.jizhun_fen),actualAmount:amount(row.shiji_fen),
        deltaAmount:amount(row.chae_fen),varianceRate:amount(row.chalv_bps),direction:direction(row.fa),
        decision:decisions.has(d?.panduan)?d.panduan:'待确认',requiresApproval:d?.shenpi===true};
    }),modules:(result.moduleSummary ?? []).filter(x=>modules.has(x.module)).map(row=>({
      module:row.module,deltaAmount:amount(row.netDeltaFen),direction:row.direction==='有利'?'F':row.direction==='不利'?'A':'N',shareRate:amount(row.shareBps)}))};
  return {allowed:true,request:{op,dataAccess:true,data,question:typeof question==='string'?question.slice(0,8000):''}};
}
