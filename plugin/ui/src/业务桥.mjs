// 业务桥：界面与宿主之间的唯一通道。live 模式把所有请求原样转发给 window.hengceHost（衡策插件），
// 演示模式（没有宿主）则用 演示数据.mjs 的固定种子数据在浏览器内存里模拟同一套 action。
// 两条路径返回同样的数据结构，界面代码不必判断自己跑在哪种模式下，isLive 只用于文案与导出路径的差异。
import { createDemoData } from './演示数据.mjs';

// 宿主桥对象：由插件启动时注入；直接用浏览器打开 index.html 时为 undefined，即进入演示模式。
const host = window.hengceHost;
// 是否接真实后端：界面用它切换「演示数据 / 正式分析结果」文案，以及导出走宿主文件还是浏览器下载。
export const isLive = !!host;
// 演示模式的单例工作区：惰性初始化（第一次请求时才创建），之后所有写操作都改这一份内存数据。
let demo;
// 深拷贝：每个 action 都返回独立副本，否则界面拿到的是内部引用，后续修改会「隔空」改掉桥里的状态。
const copy = value => structuredClone(value);
// 模拟耗时：让演示模式的分析与报告生成也有可见等待，避免用户以为按钮没反应；真实耗时由宿主决定。
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
// 分析前置条件：必须同时存在「预算基础」和「实时经营」两类且 status === 'valid' 的文件，缺一类就不放行。
const required = data => ['预算基础', '实时经营'].every(category => data.files.some(f => f.category === category && f.status === 'valid'));
// 历史快照表：记录 id → 当时的完整工作区副本，供 history.open 回溯，不会覆盖当前 demo。
const snapshots = new Map();
// 基线工厂：每次首次加载或重置都用固定种子重建工作区，保证演示可复现（同一次构建对应同一批数值）。
// 顺手把基线里的历史记录逐条登记进 snapshots，使「分析记录」页的每条历史都能打开对应快照。
// 返回值本身就是 demoData 的深拷贝，所以重置不会污染下一轮演示。
const baseline = () => {
  const data = createDemoData();
// 登记基线快照：这些历史记录在演示数据里就存在，打开它们必须能拿到当时的完整工作区。
  for (const item of data.history) snapshots.set(item.id, copy(data));
// 返回基线数据本身（已是深拷贝），调用方再 copy() 一次给界面。
  return data;
};

// 订阅宿主推送：live 模式转发宿主的 subscribe；演示模式返回空函数，界面无需判空即可调用。
// 退订函数的契约与宿主一致：调用它即解除订阅。
export function subscribe(callback) {
// 宿主不提供 subscribe 时降级为空退订，避免界面启动时抛错。
  return typeof host?.subscribe === 'function' ? host.subscribe(callback) : () => {};
}

// 统一请求入口：action 名与 payload 结构是与后端约定的契约，界面不直接读文件、也不做财务计算。
// live 分支永远优先：只要宿主存在就绝不落到演示逻辑，防止真实环境里悄悄返回假数据。
export async function request(action, payload = {}) {
  if (isLive) {
// 宿主接口版本校验：version 不是 '1.0' 立即报错，避免用旧接口静默跑出错数。
    if (host.version !== '1.0' || typeof host.request !== 'function') throw new Error('宿主接口版本不兼容，请检查衡策插件接入。');
// 转发给宿主：返回对象或二进制响应，由界面按 action 自行解释（例如 reports.export 返回文件字节）。
    return host.request(action, payload);
  }
// 首次请求时建立演示工作区；之后一直复用这份内存状态，直到 demo.reset。
  if (!demo) demo = baseline();
  switch (action) {
// 加载工作区：返回当前演示数据的深拷贝，界面 acceptData() 会整体替换本地状态并重绘。
    case 'workspace.load': return copy(demo);
// 重置演示环境：重建基线并清掉导入、分析、报告等痕迹，对应界面上的「载入演示数据」。
    case 'demo.reset': demo = baseline(); return copy(demo);
// 导入文件：只做扩展名与体积的前置校验（与后端口径一致：.xlsx、单文件 ≤ 28MB），不做真解析。
// 演示模式不具备解析能力，所以新文件一律标 pending，直到用户移除或重置演示数据。
    case 'files.import': {
// 扩展名白名单：四类模板都是 .xlsx，CSV、旧版 .xls 一律拒绝，与后端「整本退回」口径保持一致。
      if (payload.files.some(f => !/\.xlsx$/i.test(f.name))) throw new Error('请选择 .xlsx 工作簿。');
// 体积上限 28MB：与后端一致，防止拖入超大文件把浏览器卡死。
      if (payload.files.some(f => f.size > 28 * 1024 * 1024)) throw new Error('单个工作簿不能超过 28 MB。');
// 生成待校验条目：category 优先用调用方传入，其次按文件名猜（模板名里通常含「预算基础」等类别名）。
// status:'pending' 是关键：它会让 canAnalyze 与「开始分析」保持禁用，直到校验通过或重置。
      const selected = payload.files.map((f, i) => ({ id:`selected-${Date.now()}-${i}`, name:f.name, size:f.size, category:payload.category || ['预算基础','实时经营','行业对标','经营变更'].find(c=>f.name.includes(c)) || '待识别', status:'pending', checks:0, rows:0, entity:'待校验' }));
// 追加或替换：mode === 'replace' 时清掉旧列表，否则合并（append 是导入弹窗的默认行为）。
      demo.files = payload.mode === 'replace' ? selected : [...demo.files, ...selected];
// 标记 dirty：数据已变，旧报告随之失效，reports.generate 会据此拒绝生成。
      demo.dirty = true;
      return copy(demo);
    }
// 移除文件：按 id 过滤并标记 dirty（同样会让已生成的报告失效）。
    case 'files.remove': demo.files = demo.files.filter(f=>f.id!==payload.id); demo.dirty=true; return copy(demo);
// 模板下载：演示模式不附带标准工作簿，直接给出可执行的下一步提示，而不是假装下载成功。
    case 'templates.download': throw new Error('演示预览未附带标准工作簿。接入衡策插件后可下载正式空白模板。');
// 运行分析：演示模式只支持 2027-06 月度，且要求两个必填类别都校验通过、没有 pending 文件。
// 重算只做风险分级（按当前 tiers 与 |偏差率|），财务数值仍是固定种子的演示数，绝不假装重算。
    case 'analysis.run': {
// 前置校验一：两类必填工作簿必须齐备且校验通过，与界面 canAnalyze 的判断完全一致。
      if (!required(demo)) throw new Error('请先准备校验通过的预算基础和实时经营工作簿。');
// 前置校验二：存在未校验文件时拒绝分析，并给出两条可执行的出路（移除或重置）。
      if (demo.files.some(f=>f.status==='pending')) throw new Error('所选本地文件尚未通过后端校验。可移除这些文件，或重新载入演示数据。');
// 期间与周期白名单：演示数据只有 2027 年 6 月月度，其他期间必须明确拒绝并说明接入后可用。
      if (payload.config.period !== '2027-06' || payload.config.cycle !== '月度') throw new Error('演示数据仅包含 2027 年 6 月月度分析。其他期间与季度分析将在接入后端后可用。');
// 模拟 900ms 分析耗时：比报告生成的 650ms 略长，反映分析确实更重。
      await pause(900);
// 保存本次分析参数：后续阈值调整会直接影响风险等级与档位标签的展示。
      demo.config = copy(payload.config);
// 按新阈值重算每一行的风险等级与档位，只改 risk / tierName / tierColor 三个展示字段。
      demo.rows.forEach(row => {
// 档位表按阈值升序排列，最后一档是最严格的「高风险」。
        const tiers = demo.config.tiers;
// 只有不利差异才计入风险：有利差异偏差再大也不该进「高风险」，方向判断由 演示数据.mjs 给出。
        const magnitude = row.direction === 'unfavorable' ? Math.abs(row.rate) : 0;
// 风险分级：达到最高档阈值记 high，达到最低档记 watch，其余 normal。
        row.risk = magnitude >= tiers[tiers.length-1].threshold ? 'high' : magnitude >= tiers[0].threshold ? 'watch' : 'normal';
// 取命中的最高档位（反转后 find 第一个满足阈值的），用于「关注 / 高风险」标签文字与颜色。
        const tier = [...tiers].reverse().find(t => magnitude >= t.threshold);
// 档位名：未命中任何档位时为 undefined，界面按 normal 展示。
        row.tierName = tier?.name;
// 档位颜色：由配置决定，界面直接内联到标签样式，不在前端写死色值。
        row.tierColor = tier?.color;
      });
// 分析完成后清除 dirty：此时数据与参数一致，允许生成报告。
      demo.dirty=false;
// 记录生成时间戳：报告、历史与界面上的「生成于」都读这个字段。
      demo.meta.generatedAt = new Date().toISOString();
// runId 每次运行都换（时间戳）：历史记录靠它区分，也保证同一 id 不会被两次运行覆盖。
      demo.meta.runId = `demo-${Date.now()}`;
// 历史摘要：只存期间、公司、时间与风险数量等列表字段，完整快照另存 snapshots，避免列表过重。
      const record = {id:demo.meta.runId,period:demo.meta.period,company:demo.meta.company,createdAt:demo.meta.generatedAt,status:'done',riskCount:demo.rows.filter(r=>r.risk!=='normal').length};
// 新记录插到最前：界面「分析记录」按时间倒序展示，最新一次运行永远在最上面。
      demo.history.unshift(record);
// 为本次运行存快照（深拷贝）：history.open 打开它时能还原当时的行、动作与报告。
      snapshots.set(record.id, copy(demo));
      return copy(demo);
    }
// 保存经营背景：自由文本与关键假设，后续 AI 解读会把它作为上下文（演示模式只做存储）。
    case 'background.save': demo.background=copy(payload); demo.dirty=true; return copy(demo);
// 整改事项状态流转：只允许 pending / doing / done 三态，其他值直接拒绝。
    case 'actions.update': {
// 状态白名单：防止界面传错值把看板列弄乱。
      if (!['pending','doing','done'].includes(payload.status)) throw new Error('整改状态无效。');
// 按 id 找整改事项：演示数据里 a01–a05 是固定种子，找不到说明 id 过期。
      const item=demo.actions.find(a=>a.id===payload.id);
// 找不到就明确报错，不静默忽略，否则界面会以为更新成功但不显示变化。
      if(!item) throw new Error('未找到该整改事项。');
// 写入新状态：三栏看板按 status 分组渲染，改完立刻移动卡片。
      item.status=payload.status;
      return copy(demo);
    }
// 预算修订批准：要求人工确认 + 原因 + 未来期间 + 非负整数分，缺一项就拒绝。
// 金额全程用整数分传输，这里用 Number.isSafeInteger 卡住小数与精度溢出。
    case 'revisions.approve': {
// 批准前置：必须勾选人工批准且填写原因，系统不代替人做审批。
      if (!payload.approved || !payload.reason?.trim()) throw new Error('请填写修订原因并确认人工批准。');
// 修订只能落在 2027 年 7—12 月的未来预算：已发生的月份不允许「改历史」。
      if (!/^2027-(07|08|09|10|11|12)$/.test(payload.period)) throw new Error('演示修订仅支持 2027 年 7—12 月的未来预算。');
// 金额校验：非负安全整数（单位：分），小数/负数/超精度一律拒绝。
      if(!Number.isSafeInteger(payload.amount) || payload.amount<0) throw new Error('修订金额必须为非负金额，最多两位小数。');
// 校验科目存在：修订必须挂在真实差异行上，否则台账会出现悬空记录。
      const row=demo.rows.find(r=>r.id===payload.rowId);
// 科目不存在直接报错，避免产生无法追溯的修订。
      if(!row) throw new Error('科目不存在。');
// 写入修订台账：补上科目名与创建时间，并标 demo:true，导出报告时能追溯这是演示修订。
      demo.revisions.unshift({...copy(payload), id:`rev-${Date.now()}`,subject:row.subject,createdAt:new Date().toISOString(),demo:true});
      return copy(demo);
    }
// 生成报告：数据必须是干净状态（dirty 为 false），否则先要求重新分析。
// includeAI 原样记录到报告条目：报告中心据此显示「AI 解读」标签与统一标注。
    case 'reports.generate': {
// dirty 检查：数据或参数改过之后旧结论不再成立，先分析再生成是硬约束。
      if (demo.dirty) throw new Error('数据或参数已变更，请先重新分析。');
      await pause(650);
// 插入报告条目：格式默认 PDF、页数未知（null）、demo:true 标明这是演示产物。
      demo.reports.unshift({id:`report-${Date.now()}`,title:'2027 年 6 月经营分析报告',period:demo.meta.period,createdAt:new Date().toISOString(),status:'ready',format:'PDF',pages:null,includeAI:payload.includeAI,demo:true});
      return copy(demo);
    }
// 打开历史记录：用 snapshots 里的旧快照替换当前 demo，但保留 history 数组本身。
// 这样回溯历史时「分析记录」列表不会缩水，用户仍能跳到其他记录。
    case 'history.open': {
// 取快照：只有本次会话里跑过的记录才有快照，演示数据自带的历史在 baseline 时已登记。
      const previous=snapshots.get(payload.id);
// 找不到快照直接报错：演示模式不伪造历史，也不拿当前数据冒充过去的状态。
      if(!previous) throw new Error('该记录未附带演示快照，请选择本次运行生成的记录。');
// 先保存当前 history 数组引用，下面替换 demo 时要把它接回去。
      const history=demo.history;
// 切换到旧快照（深拷贝），后续所有请求都基于这份数据。
      demo=copy(previous);
// 把当前（更新过的）历史列表接回快照，避免打开历史后记录变少。
      demo.history=history;
      return copy(demo);
    }
// 助手问答：必须先获得「允许访问当前分析结果」的授权，然后基于选中科目或风险最高科目作答。
// 回答由模板拼接（演示解读，未调用真实模型），末尾按规范追加 AI 生成标注，返回体同时带 aiGenerated / aiNotice。
    case 'assistant.ask': {
// 授权闸门：没勾选授权就拒绝，避免助手在用户不知情时读取分析结果。
// 同时模拟 650ms 延迟（见下一行 await pause），让回答有「正在思考」的过程感。
      if(!payload.dataAccess) throw new Error('请先允许访问当前分析结果。');
      await pause(650);
// 取作答依据：优先用界面传来的 rowId（当前选中的差异行），没有就退到风险最高的一行。
      const row=demo.rows.find(r=>r.id===payload.context?.rowId) || demo.rows.find(r=>r.risk==='high');
// 返回结构 {text, sources, aiGenerated, aiNotice}：界面把它渲染成助手气泡 + 引用来源 + 标注小字。
// sources 明确写「演示数据来源，不是法规依据」，避免引用被误读成条文。
      return {text:`这是演示解读，未调用真实模型。\n\n${row.subject}的预算为 ${(row.budget/100).toLocaleString('zh-CN',{minimumFractionDigits:2})} 元，实际为 ${(row.actual/100).toLocaleString('zh-CN',{minimumFractionDigits:2})} 元，偏差率为 ${(row.rate/100).toFixed(2)}%。\n\n${row.reason}\n\n建议先核对来源记录与经营变更，再根据「${row.decision}」处理。你可以从差异明细打开此项，查看来源或发起预算修订。\n\n内容为AI生成，仅供参考`,aiGenerated:true,aiNotice:'内容为AI生成，仅供参考',sources:[{title:'本次演示分析结果',excerpt:`${row.source}；该引用为演示数据来源，不是法规依据。`}]};
    }
// 打开输出文件夹：浏览器预览由浏览器管理下载位置，接入宿主后可真正打开落盘目录。
    case 'reports.openFolder': throw new Error('浏览器预览由浏览器管理下载位置；宿主接入后可直接打开输出文件夹。');
// 未实现的 action 一律显式报错，不返回 undefined，免得界面拿到空数据后误判成「没有结果」。
    default: throw new Error(`当前预览未提供此操作：${action}`);
  }
}

// 分析按钮可用性：两类必填工作簿齐备且没有 pending 文件时为 true。
// 判断口径与 analysis.run 的前置校验逐条对应，避免「按钮能点但请求被拒」的割裂体验。
export function canAnalyze(data) { return required(data) && !data.files.some(f=>f.status==='pending'); }
