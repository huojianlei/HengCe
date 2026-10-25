/** UI 自定义接入协议。不是 DeepSeek Harness 官方 SDK 声明。 */
//
// ---------------------------------------------------------------------------
// 【这份文件在链路里的位置】
//   ui/（页面）  ↔  window.hengceHost（adapter/宿主桥.js）
//                ↔  HTTP POST /hengce/api {action, payload}（adapter/服务核心.mjs）
//                ↔  Python 桥（adapter/桥接.mjs ↔ backend/桥接入口.py）
//   本文件是这条链两端的**类型契约**：字段名、取值范围、单位都在这里写死。
//   改字段 = 改协议，必须同时改 backend/桥接入口.py 的 DONGZUO 分发表与
//   adapter/宿主桥.js 的负载转换（二进制 +B64），三者版本号 1.0 一起升。
//
// 【口径纪律（全链路统一，前端显示层才换算）】
//   · 金额一律整数分（MoneyFen）：1 元 = 100 分，显示时 ÷100，禁止传浮点元；
//   · 比率一律整数基点（BasisPoints）：10000 bp = 100%，100% 显示时 ÷100，
//     即 2500 = 25%、-1500 = -15%；禁止传 0.25 这种小数形式的百分比；
//   · 缺失值用 null（不用 0 冒充「没有数据」——0 是有效的财务数字）；
//   · 期间为 YYYY-MM（月度）或 YYYY-Qn（季度，n=1..4），必须与 cycle 一致；
//   · id 必须能稳定定位（同一对象跨请求不变），前端按键合并/定位都靠它。
//
// 【失败语义】
//   本文件只描述「成功形状」。任何 action 都可能失败，失败一律表现为
//   宿主桥 reject 的中文 Error（见 宿主桥.js）：页面层不需要在这里声明
//   错误联合类型，catch 到的 message 就是 Python 侧写好的中文原文。
// ---------------------------------------------------------------------------
// 金额：整数分。为什么不用 float 元：0.1+0.2 的二进制误差会让对账差一分，
// 财务口径必须整数运算；后端、行协议、本契约全程分，只有 UI 呈现才 ÷100。
export type MoneyFen = number;
// 比率：整数基点（basis point，缩写 bp；1 bp = 万分之一 = 0.01%）。
// 10000 bp = 100%。选基点的理由：百分比小数在传输与比较时仍有浮点问题，
// 整数基点同时避免「25 还是 0.25」的歧义——本项目里 25 就是 0.25%。
export type BasisPoints = number;
// 报表模块名（九模块里的四个金额模块；另五个为指标/表格类，不参与差异行）。
export type ModuleName = '收入' | '成本' | '费用' | '采购';
// 四类输入工作簿（用户拍板的固定四类）。类别由后端解析器判定：
// 前端传的 category 只作为提示/校验期望，不信任文件名与用户口述。
export type Category = '预算基础' | '实时经营' | '行业对标' | '经营变更';
// 整改任务状态机：待办 → 进行中 → 已完成；界面不改写，原样回传。
export type TaskStatus = 'pending' | 'doing' | 'done';
// 分析配置：可由界面「参数区」修改，随 analysis.run 一起下发；
// 每一项都参与十五步分析，缺一项后端就用默认值——默认值在 Python 侧定义，
// 本契约只描述形状（不在前端硬编码默认数，避免两处默认值分叉）。
export interface AnalysisConfig {
  // 周期粒度：决定 period 的解析与聚合方式（月度按期间、季度按期间末/汇总）。
  cycle: '月度' | '季度';
  /** 月度 YYYY-MM；季度 YYYY-Qn。 */
  // 分析末档（工作区期间窗口的右端），格式必须与 cycle 匹配，否则后端报错。
  period: string;
  // 企业增长率（基点）：2500 = 25%；用于把预算基数推演到分析期间。
  growth: BasisPoints;
  // 行业基准增长率（基点）；null = 未导入行业对标册，不参与对标修正。
  industry: BasisPoints | null;
  // 是否启用行业基准修正（布尔开关；关闭时 industry/threshold 不参与计算）。
  industryCorrection: boolean;
  // 触发行业修正的偏离阈值（基点）：偏差超过它才按行业值修正。
  industryThreshold: BasisPoints;
  // 噪声容忍带（基点）：落在带内的差异视为正常波动，不生成预警。
  noise: BasisPoints;
  // 显著性水平（基点）：统计显著性判定用（10000 bp = 100%）。
  // 注意此项虽用基点表示，但语义是概率而非变化率）。
  significance: BasisPoints;
  // 预警分档：阈值升序，后端按 basisPoints 比较后给出 row.risk 与档位名/颜色；
  // color 是前端可直接用的颜色串（不在这里约束具体色值格式）。
  tiers: Array<{ name: string; color: string; threshold: BasisPoints }>;
}
// 差异分析行：十五步分析的直接产物，也是界面主表格的一行。
// 一行 = 一个「科目 × 部门 × 期间」的预算/实际/差异三元组。
export interface VarianceRow {
  // 行 id（稳定）：前端 selection、整改任务 rowId、审批记录 rowId 都引用它。
  id: string;
  // 科目名（取自输入模板的固定科目，与后端科目表一致）。
  subject: string;
  // 所属金额模块（收入/成本/费用/采购），决定界面分组与汇总口径。
  module: ModuleName;
  // 部门中文名（展示用）；departmentId 才是稳定键。
  department: string;
  // 部门 id（稳定键，跨期不变，用于筛选与合并）。
  departmentId: string;
  // 所属期间：YYYY-MM 或 YYYY-Qn，与 AnalysisConfig.period 同格式。
  period: string;
  // 预算金额（整数分）。
  budget: MoneyFen;
  // 实际金额（整数分）；缺失时后端给 null 语义由 rows 层体现在什么位置——
  // 差异行的 actual 若无可比实际，后端以相等值填充并在 warnings 说明。
  actual: MoneyFen;
  // 差异金额（整数分）= actual - budget（后端口径，前端不自行重算）。
  variance: MoneyFen;
  // 差异率（基点）= |variance| / budget 的后端口径；预算为 0 时的处理由后端定。
  rate: BasisPoints;
  /** 使用后端判定，不根据有利/不利自行重判。 */
  // 风险级别：high=超阈值高优先级、watch=观察、normal=正常。
  risk: 'high' | 'watch' | 'normal';
  // 命中档位名（AnalysisConfig.tiers 里的 name）；未命中档位时缺省。
  tierName?: string;
  // 命中档位颜色（与 tierName 同来同去；缺省表示不着色）。
  tierColor?: string;
  // 差异方向：favorable=有利（如成本下降）、unfavorable=不利（收入下降）；
  // 方向与金额正负不同义——成本类科目正差异通常是有利的。
  direction: 'favorable' | 'unfavorable';
  // 建议决策动作（后端生成的短句，如「核实」「调整预算」「追责到人」）。
  decision: string;
  // 差异原因（后端推导/归因文本，界面原文展示，不做润色）。
  reason: string;
  // 数据来源标注（预算/实际/对标哪一册贡献了本行，用于追溯）。
  source: string;
}
// 工作区：所有查询型 action 的统一返回体。
// 设计取向：**整包返回**而不是增量 patch —— 每次请求拿到的都是完整一致的状态，
// 前端无需合并逻辑，也不会出现「半个新状态」；代价是包体较大（本版可接受）。
export interface Workspace {
  // 协议版本：字段增删时升版号，前端可据它做兼容分支（当前仅 '1.0'）。
  schemaVersion: '1.0';
  // 是否演示数据（固定种子生成）。true 时页面必须显著标注「演示」，
  // 不得让演示数字看起来像真实企业账目。
  demo: boolean;
  // 输入已变更但分析未重跑时为 true：界面应提示「请重新运行分析」，
  // 报告/导出的入口据此禁用（避免把旧结果包装成新报告）。
  dirty?: boolean;
  // 元信息：company=主体名；period=当前分析期间；scenario=情景名；
  // generatedAt=本包生成时间（ISO 字符串，仅供展示与陈旧判断）；
  // runId=本次分析运行号，是「报告绑定哪次分析」的关联键，必须原样回传。
  meta: { company: string; period: string; scenario: string; generatedAt: string; runId: string };
  // 当前生效的分析配置（analysis.run 之后以官方返回为准，前端不本地累加）。
  config: AnalysisConfig;
  // 可选主体/部门清单：id 是稳定键，name 用于展示与下拉。
  entities: Array<{ id: string; name: string }>;
  // 已导入的工作簿（一次导入一本；四类可分别追加）：
  //   category = 解析出的类别（'待识别' 表示校验未完成/未通过）；
  //   status   = 'valid' 通过契约校验，'pending' 待校验；
  //   checks   = 通过的校验项数（界面上显示「校验 N 项」）；
  //   rows     = 入库业务行数（不含分录/摊销明细等内部底稿）；
  //   size     = 字节数或后端给的描述串（两种形态都存在，展示时按类型处理）；
  //   entity   = 该册对应的主体名（多主体批次里用于区分）。
  files: Array<{
    id: string; name: string; category: Category | '待识别';
    status: 'valid' | 'pending'; checks: number; rows: number;
    size: number | string; entity: string;
  }>;
  // 全部差异行（界面主表数据源；可按 module/department 筛选，数据不重算）。
  rows: VarianceRow[];
  /** 使用实际期间数；支持月/季、空序列及 null 实际值。 */
  // 趋势序列：每期一条；budget/actual/rolling 均为整数分，null=该期无此数据
  // （不补 0，否则图表会把「没数」画成「零」）。rolling=滚动预算值。
  trend: Array<{ period: string; budget: MoneyFen | null; actual: MoneyFen | null; rolling: MoneyFen | null }>;
  // 整改清单（由分析生成，也可由 actions.update 改状态）：
  //   rowId 指向差异行；type='revision' 预算修订 / 'execution' 执行整改；
  //   due 为截止日期字符串；priority 与差异行风险口径一致。
  actions: Array<{
    id: string; rowId: string; title: string; department: string; owner: string;
    due: string; status: TaskStatus; priority: 'high' | 'watch';
    type: 'revision' | 'execution'; description: string;
  }>;
  // 预算修订记录（审批流）：amount 为整数分（修订后金额或修订差额，
  // 由后端口径决定，本层不换算）；approved=true 表示已审批通过；
  // demo=true 表示该条来自演示数据，需在界面标注。
  revisions: Array<{
    id: string; rowId: string; subject: string; period: string; amount: MoneyFen;
    reason: string; approved: boolean; createdAt: string; demo?: boolean;
  }>;
  // 已生成的计算报告：status='ready' 表示文件已落盘可导出；
  // format 为生成的主格式；pages=PDF 页数（未真实生成时 null，界面显示 '?'）；
  // includeAI=true 仅表示「本次请求了 AI 解读」，完成状态以内容为准，不冒充已生成。
  reports: Array<{
    id: string; title: string; period: string; createdAt: string;
    status: 'ready'; format: string; pages: number | null; includeAI?: boolean; demo?: boolean;
  }>;
  // 历史运行快照（每次分析一条）：riskCount=该次预警行数（整数条，不是金额）；
  // status 目前只有 'done'；id 可用于 history.open 回看。
  history: Array<{ id: string; period: string; createdAt: string; company: string; status: 'done'; riskCount: number }>;
  // 指标卡：value 为基点（BasisPoints）——unit 恒为 '%'，显示时 value÷100；
  // value=null 表示该指标本期无数据（界面显示「—」，不显示 0%）。
  kpis: Array<{ name: string; value: BasisPoints | null; unit: '%'; note: string }>;
  // 经营变更背景：changeStatus 三态（yes=有变更 / none=无 / unknown=未判定），
  // text 为用户填写的说明文本（原文回显，不加工）。
  background: { changeStatus: 'yes' | 'none' | 'unknown'; text: string };
  // 非致命提示（如「条例检索降级为占位」「某册期间与其他册不一致」）：
  // 两种形状都接受（纯字符串或 {message}），前端统一取文本原样展示。
  warnings?: Array<string | { message: string }>;
}
// 下载类 action 的返回：两种形状二选一。
//   ① 文件内容：name=建议文件名，mime=内容类型，bytes=文件字节（ArrayBuffer，
//      经宿主桥从 base64 还原）；前端用 Blob 落盘。
//   ② 目录类操作（如打开报告所在文件夹）：{handled:true} 表示后端已处理，
//      没有文件可下载——前端不应再尝试保存 Blob。
export type DownloadResult = { name: string; mime: string; bytes: ArrayBuffer | Uint8Array } | { handled: true };
// 全部业务 action 的「入参 → 出参」映射；key 必须与 Python DONGZUO 分发表一致。
// 约定：除标注外，每个 action 的 output 都是完整 Workspace（整包刷新）。
export interface ActionMap {
  // 读工作区：无入参（Record<string, never> 保证前端不会误传字段）。
  'workspace.load': { input: Record<string, never>; output: Workspace };
  // 导入工作簿：bytes 是 ArrayBuffer，宿主桥会自动改名 bytesB64 并转 base64
  // （见 宿主桥.js 的 yuchu —— 直接 JSON.stringify(ArrayBuffer) 会丢字节）；
  // category 是期望类别（null=交给后端判定，不信任文件名）；
  // mode：append 追加（保留已导入册）/ replace 整批替换。
  'files.import': { input: { files: Array<{ name: string; size: number; bytes: ArrayBuffer }>; mode: 'append' | 'replace'; category: Category | null }; output: Workspace };
  // 移除一本已导入工作簿：按文件 id 删，随后返回刷新后的工作区。
  'files.remove': { input: { id: string }; output: Workspace };
  // 下载空白输入模板：category 决定下发哪一套版式（四类三版式），
  // 返回 DownloadResult（xlsx 字节）；模板本身不含任何演示业务数值。
  'templates.download': { input: { category: Category }; output: DownloadResult };
  // 运行十五步分析：entityId='all' 表示全部主体/部门一起算；
  // config 为全量配置（通常由 workspace.load 的 config 覆盖工具参数后传入）；
  // 返回刷新后的 Workspace（rows/actions/trend/kpis 都在其中）。
  'analysis.run': { input: { entityId: string; config: AnalysisConfig }; output: Workspace };
  // 保存经营变更背景：入参即 Workspace['background'] 结构，回整包。
  'background.save': { input: Workspace['background']; output: Workspace };
  // 更新整改任务状态：按任务 id 改 status（状态机见 TaskStatus），回整包。
  'actions.update': { input: { id: string; status: TaskStatus }; output: Workspace };
  // 预算修订审批：按差异行 rowId+期间定位，amount 为整数分；
  // approved 当前只接受 true（拒绝/退回路径未开放，故字面量类型锁定）。
  'revisions.approve': { input: { rowId: string; period: string; amount: MoneyFen; reason: string; approved: true }; output: Workspace };
  // 生成计算报告：runId 必须指向「最近一次分析」（旧 runId 会被后端拒绝，
  // 防止把过期结果包装成新报告）；includeAI=true 只表达「请求 AI 解读」，
  // 真实完成状态以 reports[].includeAI 与内容为准，不得假设已生成。
  'reports.generate': { input: { runId: string; includeAI: boolean }; output: Workspace };
  // 导出报告：format 白名单 pdf/html/md/json（与生成本地文件四格式同源同数）；
  // 返回 DownloadResult（文件字节），由前端落盘。
  'reports.export': { input: { id: string; format: 'pdf' | 'html' | 'md' | 'json' }; output: DownloadResult };
  // 打开报告所在文件夹：交由后端（本机）执行，返回 {handled:true}，无文件体。
  'reports.openFolder': { input: { id: string }; output: { handled: true } };
  // 回看历史运行快照：按 history[].id 载入那一次的工作区（整包替换当前视图）。
  'history.open': { input: { id: string }; output: Workspace };
  // 向 AI 助手提问：context 提供定位（主体/期间/可选差异行/运行号），
  // dataAccess 是**明确的布尔授权**——不能因为「上下文里有数据」就默认为
  // 已授权读取明细；false 时后端只答常识与指引，不碰业务数字。
  // output 两种：正常回答（text + 可选引用 sources）或 {handled:true}（后端自行处理）。
  'assistant.ask': {
    input: { question: string; context: { entityId: string; period: string; rowId?: string; runId: string }; dataAccess: boolean };
    output: { text: string; sources?: Array<{ title: string; excerpt: string }> } | { handled: true };
  };
}
// 推送事件（宿主桥 subscribe 的回调数据）。本版宿主桥无推送（subscribe 为空实现），
// 形状先定好是为了后续接入推送时前端无需改代码：
//   workspace.changed = 工作区被别处改动（导入/分析/审批），前端应整包替换；
//   analysis.progress = 分析进度（percent 0-100 的百分比，不是基点）；
//   assistant.message = 助手消息（增量文本，用于流式展示）。
export type HostEvent =
  | { type: 'workspace.changed'; data: Workspace }
  | { type: 'analysis.progress'; data: { message: string; percent?: number } }
  | { type: 'assistant.message'; data: { text: string } };
// 页面侧全局对象 window.hengceHost 的形状（实现在 adapter/宿主桥.js，
// 由服务核心注入到 index.html，见 服务核心.mjs 的 du_index）。
export interface HengceHost {
  // 协议版本，与 Workspace.schemaVersion 同步演进（当前均 '1.0'）。
  version: '1.0';
  // 统一请求入口：action 必须是 ActionMap 的键（类型层已约束），
  // payload 对应 action 的 input；返回 Promise<该 action 的 output>。
  // 失败 reject 中文 Error；二进制字段在传输层自动转 base64（调用方无感）。
  request<K extends keyof ActionMap>(action: K, payload: ActionMap[K]['input']): Promise<ActionMap[K]['output']>;
  // 可选的事件订阅：返回取消函数。实现方若无可推送内容（本版即如此），
  // 应提供空实现并返回合法的取消函数，而不是让这个成员变成 undefined。
  subscribe?(callback: (event: HostEvent) => void): () => void;
}
// 全局声明：页面脚本通过 window.hengceHost 访问上面的接口；
// 可选（?）是有意的——脱离衡策服务直接打开 ui/ 时它不存在（演示模式）。
declare global { interface Window { hengceHost?: HengceHost; } }
