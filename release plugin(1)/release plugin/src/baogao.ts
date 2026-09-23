// ======================================================================
// 报告组装与 Markdown 排版 —— 计算层【数据计算测试报告】的数据组装层
// ======================================================================
//
// 转写自 D:\AppProject\algo\baogao.py（781 行；Python 版为唯一行为准绳；
// 拼音标识符逐字保留，期望值以 algo/tests/test_baogao.py 为准，
// 对应本插件验证区 tests/baogao.test.ts，测试数字逐字对应）。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/01-需求说明.md v2.0 §3 FR-14（报告一键导出——计算部分：数据排版）
//     TODO.md T-28（计算层/AI 层拆分：本模块只做确定性表格排版，
//         **不产出一句分析文案**——文案起草归 AI 层）
//     docs/11-算法计算层说明.md §2（八单元串联主图）
//
// 模块定位（[046] 拆分后）：
//     本模块 = **数据组装层**——把八个计算单元的既有输出组装成 BiaoKuai
//     （标题 + 表头 + 数据行），并对所有数值做显示转换（金额→元、比率→
//     百分比、周转率→次、布尔→是/否、缺数→"—"）。
//     渲染层：Markdown 渲染 shengcheng_baogao_md（本模块）；
//     Word 渲染 baogao_docx 不移植（转写设计裁决 #12——md + JSON 双导出，
//     Word 二进制生成需第三方库、违反零依赖纪律，由智能体层另行转换）。
//     显示转换只发生在组装层且全部整数运算实现（计算层数据不动一分一毫）。
//
// 八单元 + 附表（表格清单，一个分析项目对应一张数据表）：
//     单元 1 数据录入（四类归档明细 + 拒绝清单）
//     单元 2 滚动预算（逐期 + 年度合计 + 滚动差异）
//     单元 3 差异计算（三重对比：固定/滚动/实际/差额/差异率/F-A/预警）
//     单元 4 规划/执行拆分（三总量 + 四细分 + 残差 + 恒等式）
//     单元 5 单双环判定（判定要素 + 归因依据 + 纠错动作）
//     单元 6 积木拆解（四模块 + 未归属 + 净总差异 + 高亮）
//     单元 7 平衡计分卡（四维得分/权重 + 总分/等级）
//     单元 8 变更溯源（逐 KPI 影响率/方向/作用/占比 + TOP3）
//     附表 A KPI 指标库（15 项——BSC/溯源的取数源）
//     附表 B 整改清单（类型/优先级/责任模块/审批/进度）
//     附表 C 预警汇总（四档计数）
//
// 容错纪律（与看板数据接口同款）：任一上游缺省（null）→ 对应节输出
//     "（缺料）"占位，不抛错——端到端任何阶段缺料报告仍完整可读。
//
// 排版原则（四条，全部可测试）：
//     ① 不重算——所有数值直接取上游输出，排版层只做显示转换；
//     ② 不缺列——表头列数 = 数据行列数（渲染层保证）；
//     ③ 不藏数——缺数以 "—" 显式占位、未归属明细单列、拒绝清单必列；
//     ④ 不作文——零自然语言文案，AI 层在数据表之上追加解读。
//
// 上游鸭子类型（转写约定）：本模块只定义【最小结构 interface】消费上游，
//     字段名与上游所有权模块的 dataclass 逐字一致（chayi 的 ChayiJieguo/
//     ChayiXiang、gundong 的 GunDongJieguo、chaifen 的 ChaifenJieguo、
//     panduan 的 PanDuanJieguo/PanDuanShuru、jimu 的 JimuJieguo、bsc 的
//     BscJieguo、suyuan 的 SuyuanJieguo、kpi 的 KpiJieguo、zhenggai 的
//     ZhenggaiJieguo、kanban 的 KanbanShuju、ruku 的 DaoruJieguo）。
//     TS 结构类型天然兼容——不 import 上游模块，只消费形状。
//
// TS 差异说明：总差异率一步除法（|Σ差额|÷Σ基准）的中间量可超 2^53 →
//     统一走公共库 int-math 的 dai_fuhao_bps（half-up 带符号，与 Python
//     原式 (abs(a)*10000*2+b)//(2*b) 补符号逐式对应）；其余显示转换全部
//     整数 divmod 实现，禁浮点。
//
// 建立对应：2026-08-23（Python）｜ 转写：2026-09-05（TS 批次G）
// ======================================================================

// 除法求比率只有总差异率一处——走公共库 BigInt 半进位助手（带符号 half-up）
import { dai_fuhao_bps } from './int-math.ts'

// ======================================================================
// 常量区
// ======================================================================

/** KPI 15 项显示元数据：（字段名, 中文名, 显示类别）。
 *
 * pct = 百分比 / ci = 周转率（次）/ tian = 天 / ci_shu = 次数；
 * 顺序 = 定稿 §8 清单（财务 9 + 非财务 6）——与 kpi.py 输出字段一一对应。
 * 首元直接用 keyof KpiJieguo 收紧——拼错字段名在编译期即报错。
 */
export const KPI_XIANSHI: readonly (readonly [
  keyof KpiJieguo, string, string,
])[] = [
  ['yingshou_dachenglv_bps', '营收达成率', 'pct'],
  ['chengben_kongzhilv_bps', '成本控制率', 'pct'],
  ['feiyong_pianchalv_bps', '费用偏差率', 'pct'],
  ['maolilv_bps', '毛利率', 'pct'],
  ['jinglirunlv_bps', '净利润率', 'pct'],
  ['xiaoshou_lirunlv_bps', '销售利润率', 'pct'],
  ['zichan_zhouzhuanlv_bps', '资产周转率', 'ci'],
  ['zijin_zhouzhuanlv_bps', '资金周转率', 'ci'],
  ['caigou_chengben_bian_donglv_bps', '采购成本变动率', 'pct'],
  ['gongyinglian_lvyuelv_bps', '供应链履约率', 'pct'],
  ['channeng_liyonglv_bps', '产能利用率', 'pct'],
  ['jiaofu_zhouqi_tian', '交付周期', 'tian'],
  ['kehu_manyilv_bps', '客户满意度', 'pct'],
  ['yewu_jindu_bps', '业务完成进度', 'pct'],
  ['yichang_shijian_shu', '异常事项数量', 'ci_shu'],
]

/** 报告抬头（版本与说明行——纯文本，无自然语言文案）；元信息行
 * 应 T-29#11 要求：版本/模拟数据集标记/财年/金额单位四项齐备。
 * 逐字对齐 Python BAOGAO_TAITOU（含全角竖线与半角引号）。
 */
export const BAOGAO_TAITOU =
  '# 数据计算测试报告（FinAgent 八单元串联）\n' +
  '\n' +
  '> 说明：输入数据依次经过八个计算单元处理；一个分析项目对应一张数据表。\n' +
  '> 显示口径：金额 = 元（两位小数、千分位）；比率 = 百分比；周转率 = 次。\n' +
  '> 计算口径：内部全程整数分 / 基点；缺数显示 "—"；上游缺料显示 "（缺料）"。\n' +
  '> 元信息：版本 V1.1 ｜ 数据集 = 模拟（is_simulation=true）｜ 财年 2026 ｜ 金额单位 = 元。\n'

/** 缺料占位行（上游 null 时输出，保证报告结构完整）。
 * 占位与数据 "—" 的分工：占位 = 整节缺上游；"—" = 表内单格缺数。
 */
export const QUE_LIAO = '（缺料）'

/** 【转写设计裁决·第三节修正1】单元 3 脚注的预警阈值改为由常量动态生成：
 * Python 版硬编码「≥ 5% 黄色、≥ 10% 红色」是历史残留（阈值演变
 * 1%/10% → 5%/10% → 15%/30%），TS 版从常量拼出、杜绝再次漂移。
 * 数值与 variance 模块的黄/红阈值常量同口径（1500/3000 基点）。
 */
export const HUANG_YUZHI_BPS = 1500
export const HONG_YUZHI_BPS = 3000

/** 表行元组类型别名（小节标题或 null, 表头, 数据行）——逐字沿用 Python `_BIaoXiang`。 */
export type _BIaoXiang = [string | null, string[], string[][]]

// ======================================================================
// 数据结构区（上游最小结构 interface + 本模块两个数据块）
// ======================================================================
// 以下 *Jieguo/*Xiang/Shuju 全部是【鸭子类型消费契约】：字段名与上游
// 所有权模块的 dataclass 逐字一致，只保留本模块实际消费的字段子集
// （未消费字段省略——上游对象天然兼容，多传字段无害）。
// ======================================================================

/** data_ingest.BiaozhunJilu 最小消费契约（hanghao/gengxin_shijian 本模块不消费）。 */
export interface BiaozhunJilu {
  leibie: string
  qijian: string
  kemu: string
  shuzhi: number
  danwei: string
  laiyuan: string
  beizhu: string
}

/** data_ingest.JuJueHang 最小消费契约（yuanwen 本模块不消费）。 */
export interface JuJueHang {
  hanghao: number
  yuanyin: string
}

/** data_ingest.DaoruJieguo：四类归档清单 + 拒绝清单（单元 1 数据源）。 */
export interface DaoruJieguo {
  yusuan: BiaozhunJilu[]
  shishi: BiaozhunJilu[]
  hangye: BiaozhunJilu[]
  biangeng: BiaozhunJilu[]
  jujue: JuJueHang[]
}

/** rolling_budget.QijianMingxi 最小消费契约（laiyuan 本模块不消费）。 */
export interface QijianMingxi {
  qijian: string
  zhuangtai: string
  chushi_yusuan_fen: number
  shuzhi_fen: number
}

/** rolling_budget.GunDongJieguo：逐期滚动（单元 2 数据源）。 */
export interface GunDongJieguo {
  qijian_mingxi: QijianMingxi[]
  chushi_zonge_fen: number
  gundong_zonge_fen: number
  chae_fen: number
}

/** variance.ChayiXiang 最小消费契约（yan_se 本模块不消费）。 */
export interface ChayiXiang {
  qijian: string
  kemu: string
  fangxiang: string
  chushi_fen: number
  gundong_fen: number | null
  shiji_fen: number
  jizhun_fen: number
  chae_fen: number
  chalv_bps: number
  fa: string
  yujing: string
}

/** variance.ChayiJieguo：三重对比结果（单元 3 + 总览 + 附表 C 数据源）。 */
export interface ChayiJieguo {
  xiang: ChayiXiang[]
  heji_chae_fen: number
  heji_fa: string
  hong_shu: number
  huang_shu: number
  wu_shu: number
  wufa_shu: number
}

/** planning_operational.ChaifenJieguo：规划/执行拆分（单元 4 数据源）。 */
export interface ChaifenJieguo {
  yuandan_zong_fen: number
  yuandan_zong_fa: string
  guihua_zong_fen: number
  guihua_zong_fa: string
  zhixing_zong_fen: number
  zhixing_zong_fa: string
  jiage_guihua_fen: number
  jiage_guihua_fa: string
  jiage_zhixing_fen: number
  jiage_zhixing_fa: string
  yongliang_guihua_fen: number
  yongliang_guihua_fa: string
  yongliang_zhixing_fen: number
  yongliang_zhixing_fa: string
  cancha_fen: number
  hengdengshi_chengli: boolean
}

/** loop_decision.PanDuanShuru：判定输入快照源（T-29#3，5.1 快照表数据源）。 */
export interface PanDuanShuru {
  chalv_bps: number
  guihua_zong_fen?: number | null
  zhixing_zong_fen?: number | null
  yuandan_cbf_fen?: number | null
  jie_gou_biangeng?: boolean | null
  bianma?: string | null
}

/** loop_decision.PanDuanJieguo：判定 + 依据 + 纠错（单元 5 数据源）。
 * yiju = 归因依据字典快照（键序 = Python dict 插入序，JS 对象同序保证）。
 */
export interface PanDuanJieguo {
  qingxing: number
  panduan: string
  jiuzheng: string
  yiju: Record<string, boolean | number | string | null>
  shenpi: boolean
  beizhu: string | null
}

/** building_blocks.MokuaiXiang 最小消费契约（mingxi 本模块不消费）。 */
export interface MokuaiXiang {
  mokuai: string
  chae_fen: number
  fa: string
  zhanbi_bps: number
  hang_shu: number
}

/** building_blocks.WeiguiXiang（未归属行）：科目映射不中的差额明细。 */
export interface WeiguiXiang {
  qijian: string
  kemu: string
  chae_fen: number
}

/** building_blocks.JimuJieguo：四模块聚合（单元 6 数据源；
 * zhanbi_fenmu_fen 本模块不消费）。
 */
export interface JimuJieguo {
  mokuai_lie: MokuaiXiang[]
  weiguishu_lie: WeiguiXiang[]
  jing_heji_fen: number
  hexin_mokuai: string | null
  weiguishu_zhanbi_bps: number
}

/** bsc.BscJieguo：四维评分（单元 7 数据源）。
 * 四个 *_bps 达成率回显字段 = bsc v0.2+ 新增，旧结果对象可缺省
 * （Python 用 getattr(…, None) 容错，TS 用可选字段同型表达）。
 */
export interface BscJieguo {
  caijing_defen: number
  kehu_defen: number
  neibu_defen: number
  xuexi_defen: number
  quanzhong: readonly number[] | null
  zongfen: number
  dengji: string
  caijing_bps?: number | null
  kehu_bps?: number | null
  neibu_bps?: number | null
  xuexi_bps?: number | null
}

/** suyuan.SuyuanXiang：逐 KPI 溯源影响行。 */
export interface SuyuanXiang {
  kpi_mingcheng: string
  yingxianglv_bps: number
  shuzhi_fangxiang: string
  zuoyong: string
  zhanbi_bps: number
}

/** suyuan.SuyuanJieguo：变更溯源（单元 8 数据源；gongshi 公式文本可缺省）。 */
export interface SuyuanJieguo {
  xiang: SuyuanXiang[]
  zhengxiang_top3: string[]
  fuxiang_top3: string[]
  gongshi?: string | null
}

/** kpi.KpiJieguo：KPI 指标库 15 项（附表 A 数据源；缺数以 null 承载）。 */
export interface KpiJieguo {
  yingshou_dachenglv_bps: number | null
  chengben_kongzhilv_bps: number | null
  feiyong_pianchalv_bps: number | null
  maolilv_bps: number | null
  jinglirunlv_bps: number | null
  xiaoshou_lirunlv_bps: number | null
  zichan_zhouzhuanlv_bps: number | null
  zijin_zhouzhuanlv_bps: number | null
  caigou_chengben_bian_donglv_bps: number | null
  gongyinglian_lvyuelv_bps: number | null
  channeng_liyonglv_bps: number | null
  jiaofu_zhouqi_tian: number | null
  kehu_manyilv_bps: number | null
  yewu_jindu_bps: number | null
  yichang_shijian_shu: number | null
}

/** zhenggai.ZhenggaiXiang 最小消费契约（八列表头与字段一一对应）。 */
export interface ZhenggaiXiang {
  leixing: string
  youxianji: string
  zeren_mokuai: string
  qijian: string
  kemu: string
  miaoshu: string
  shenpi: boolean
  zhuangtai: string
}

/** zhenggai.ZhenggaiJieguo 最小消费契约（状态三计数本模块不消费）。 */
export interface ZhenggaiJieguo {
  qingdan: ZhenggaiXiang[]
  zong_shu: number
  gao_shu: number
  zhong_shu: number
  di_shu: number
}

/** kanban.KanbanShuju 最小消费契约：附表 C 只消费预警汇总四档计数
 * （Python dict 访问 hz['hong_shu'] 等——保持 Record 形状）。
 */
export interface KanbanShuju {
  yujing_huizong?: Record<string, number> | null
}

/** 报告输入：十一个上游结果对象（鸭子类型；null = 该节缺料）。
 *
 * 字段说明（按八单元顺序）：
 *     ruku:     data_ingest.DaoruJieguo（四类归档 + 拒绝清单）。
 *     gundong:  rolling_budget.GunDongJieguo（逐期滚动）。
 *     chayi:    variance.ChayiJieguo（三重对比）。
 *     chaifen:  planning_operational.ChaifenJieguo（规划/执行拆分）。
 *     panduan:  loop_decision.PanDuanJieguo（判定 + 依据 + 纠错）。
 *     jimu:     building_blocks.JimuJieguo（四模块聚合）。
 *     bsc:      bsc.BscJieguo（四维评分）。
 *     suyuan:   suyuan.SuyuanJieguo（变更溯源）。
 *     kpi:      kpi.KpiJieguo（附表 A）。
 *     zhenggai: zhenggai.ZhenggaiJieguo（附表 B）。
 *     kanban:   kanban.KanbanShuju（附表 C 预警汇总；缺省时退回 chayi 计数）。
 *
 * 三个补充字段（T-29 增强）：
 *     panduan_shuru:        判定输入快照源（PanDuanShuru，T-29#3）；
 *     gundong_lie:          多科目滚动结果 [(科目名, GunDongJieguo)]（T-29#1）；
 *     jimu_guihua_yingshe:  模块 →（规划差异分, 执行差异分）（T-29#6）。
 * 全部字段可缺省——缺省即该节缺料（对应 Python dataclass 的 None 默认值）。
 */
export interface BgShuru {
  ruku?: DaoruJieguo | null
  gundong?: GunDongJieguo | null
  chayi?: ChayiJieguo | null
  chaifen?: ChaifenJieguo | null
  panduan?: PanDuanJieguo | null
  jimu?: JimuJieguo | null
  bsc?: BscJieguo | null
  suyuan?: SuyuanJieguo | null
  kpi?: KpiJieguo | null
  zhenggai?: ZhenggaiJieguo | null
  kanban?: KanbanShuju | null
  panduan_shuru?: PanDuanShuru | null
  gundong_lie?: readonly (readonly [string, GunDongJieguo])[] | null
  jimu_guihua_yingshe?: Record<string, readonly [number, number]> | null
}

/** 数据块：节标题 + 表列表 + 节尾注记（组装层产出，渲染层消费）。
 *
 * 字段说明：
 *     biaoti:   节标题（如 '单元 1 · 数据录入（步骤 1）'）。
 *     biao_lie: 表列表——每项 =（小节标题或 null, 表头, 数据行）；
 *               小节标题非 null 时在表前渲染 "### 小节标题"（md）。
 *               上游缺料时缺省（等价 Python 空列表）。
 *     zhu:      节尾注记（缺料占位 QUE_LIAO / 合计行等；缺省为空）。
 *
 * 渲染契约：md 渲染器消费同一结构——新增渲染目标零改组装层；
 * mingxi 行列表顺序 = 输入顺序（溯源/审计要求稳定可引用）。
 */
export interface BiaoKuai {
  biaoti: string
  biao_lie?: _BIaoXiang[]
  zhu?: string
}

// ======================================================================
// 显示转换助手区（全部整数运算实现——计算层数据不动）
// ======================================================================

/** 千分位分组（整数部分）：f'{zheng:,}' 的 TS 整数实现（禁浮点、禁 toLocaleString
 * 的区域设置不确定性——纯字符串插入逗号）。
 */
function _qianfenwei(zheng: number): string {
  let s = String(zheng)
  let i = s.length - 3
  while (i > 0) {
    s = s.slice(0, i) + ',' + s.slice(i)
    i -= 3
  }
  return s
}

/** 分 → 元显示：两位小数 + 千分位（负号前置）；null → "—"。 */
function _yuan(fen?: number | null): string {
  // 整数运算实现（divmod 拆元/分）——排版层不用浮点，计算层数据不动
  if (fen == null) {
    return '—'
  }
  // 负号只前置一次；千分位由 _qianfenwei 完成（显示层特权）
  const fu = fen < 0
  const v = fu ? -fen : fen
  const zheng = Math.floor(v / 100)
  const xiao = v % 100
  const s = `${_qianfenwei(zheng)}.${String(xiao).padStart(2, '0')}`
  return fu ? `-${s}` : s
}

/** 基点 → 百分比显示（476 基点 → 4.76%）；null → "—"。 */
function _pct(bps?: number | null, weishu = 2): string {
  // 1% = 100 基点：整数 divmod 拆整百分比与小数两位（half-up 已在计算层做完）
  if (bps == null) {
    return '—'
  }
  // 负号前置；weishu=0 用于权重这类整数百分比（40% 而非 40.00%）
  const fu = bps < 0
  const v = fu ? -bps : bps
  const zheng = Math.floor(v / 100)
  const xiao = v % 100
  const s = weishu === 2 ? `${zheng}.${String(xiao).padStart(2, '0')}` : `${zheng}`
  return fu ? `-${s}%` : `${s}%`
}

/** 带符号百分比显示（+8.00% / -37.50% / 0.00%）——溯源影响率用。 */
function _dai_fuhao_pct(bps?: number | null): string {
  // 影响率正负都有业务含义（数值上升/下降），显式带符号避免歧义
  if (bps == null) {
    return '—'
  }
  // 三条分支：正显 +、负显 -、零显 0.00%——方向语义在符号上
  if (bps > 0) {
    return `+${_pct(bps)}`
  }
  if (bps < 0) {
    return `-${_pct(-bps)}`
  }
  return '0.00%'
}

/** 基点 → 周转率"次"显示（20000 基点 → 2 次；9767 → 0.9767 次）。 */
function _ci(bps?: number | null): string {
  // 1 次 = 10000 基点（kpi 模块单位约定）；去尾零（2.0000 次 → 2 次）
  if (bps == null) {
    return '—'
  }
  // floor divmod（Python divmod 语义，负数时商向 -∞ 取整）；
  // 去尾零：去尾 '0' 再去尾 '.'——2.0000 次 → 2 次、0.9767 保持
  const zheng = Math.floor(bps / 10000)
  const xiao = bps - zheng * 10000
  const s = `${zheng}.${String(xiao).padStart(4, '0')}`
    .replace(/0+$/, '')
    .replace(/\.$/, '')
  return `${s} 次`
}

/** 布尔 → 是/否显示（null → "—"）。 */
function _shifou(boo?: boolean | null): string {
  // 判定表/整改表共用——审批标志、显著标志、登记标志统一是/否
  if (boo == null) {
    return '—'
  }
  return boo ? '是' : '否'
}

/** 录入行数值显示：按单位分派（元→分转元；%→基点转百分比；其余原值）。 */
function _zhi_xianshi(shuzhi: number, danwei: string): string {
  // 录入行单位只有三类：元 / % / 计数（个·次·天·单·人）——分派即完备
  if (danwei === '元') {
    return _yuan(shuzhi)
  }
  if (danwei === '%') {
    return _pct(shuzhi)
  }
  return `${shuzhi} ${danwei}`
}

/** Markdown 表格组装：表头 + 分隔行 + 数据行（空数据 → 一行"—"）。
 *
 * 本函数是 md 渲染层的表格组装器（全模块唯一的表格组装器——
 * 列数由表头决定，数据行缺列即数据层 bug）。
 */
function _biao(toubu: string[], hang_lie: string[][]): string {
  const lie = '| ' + toubu.join(' | ') + ' |\n'
  const fen_ge = '| ' + toubu.map(() => '---').join(' | ') + ' |\n'
  // 空数据：补一行全 "—"（表格结构保持，一眼看出"有表无数据"）
  const hang2 = hang_lie.length > 0 ? hang_lie : [toubu.map(() => '—')]
  const neirong = hang2.map((h) => '| ' + h.join(' | ') + ' |\n').join('')
  return lie + fen_ge + neirong
}

// ======================================================================
// 各单元组装函数区（每个单元一个 BiaoKuai——见模块头表格清单）
// ======================================================================

/** 总览节：三重对比汇总表（T-29#12 应用——快速查看整体执行情况）。
 *
 * 位置：报告第一节——评委/会计先看整体、再下钻各单元；
 * 五行结构 = 固定总额 / 滚动总额 / 实际总额 / 总差额 / 总差异率；
 * 汇总口径：对差异表各行求和；滚动总额仅含已生成滚动的科目。
 */
function _zong_lan(shuru: BgShuru): BiaoKuai {
  const biaoti = '总览 · 三重对比汇总'
  const chayi = shuru.chayi
  if (chayi == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // 三项总额直接对差异表行求和（不重算上游公式）
  const he_chushi = chayi.xiang.reduce((he, x) => he + x.chushi_fen, 0)
  const he_jizhun = chayi.xiang.reduce((he, x) => he + x.jizhun_fen, 0)
  const he_shiji = chayi.xiang.reduce((he, x) => he + x.shiji_fen, 0)
  const zong_chae = chayi.heji_chae_fen // 上游合计字段透传
  // 总差异率 = 总差额 ÷ Σ基准（half-up，带符号——负 = 整体节约）。
  // TS：中间量 |差额|×10000×2 可超 2^53 → 走公共库 dai_fuhao_bps
  // （与 Python (abs(zong_chae)*10000*2 + he_jizhun) // (2*he_jizhun) 补符号逐式对应；
  //  he_jizhun == 0 → null（无法定义比率），he_jizhun ≤ 0 场景不在测试域）
  const zong_lv = he_jizhun === 0 ? null : dai_fuhao_bps(zong_chae, he_jizhun)
  // 滚动总额只累计「已生成滚动」的行——未生成滚动的科目在单元 3 以 "—" 展示
  const gun_he = chayi.xiang
    .filter((x) => x.gundong_fen != null)
    .reduce((he, x) => he + (x.gundong_fen as number), 0)
  const hang_lie: string[][] = [
    ['固定预算总额', _yuan(he_chushi)],
    ['滚动预算总额（仅含已生成滚动的科目）', _yuan(gun_he)],
    ['实际总额', _yuan(he_shiji)],
    ['总差额（实际 − 基准合计）', _yuan(zong_chae)],
    ['总差异率', _dai_fuhao_pct(zong_lv)],
  ]
  return {
    biaoti,
    biao_lie: [[null, ['项目', '金额（元）/ 比率'], hang_lie]],
  }
}

/** 单元 1 数据录入：四类归档明细 + 拒绝清单（两张表）。
 *
 * 明细表列：类别/期间/科目/数值/单位/来源/备注——录入层 8 列去掉更新时间
 * （更新时间在报告语境冗余，保留会影响表格宽度）。
 */
function _jie_1(ruku?: DaoruJieguo | null): BiaoKuai {
  const biaoti = '单元 1 · 数据录入（步骤 1）'
  // 缺料时 zhu 承载占位——渲染层统一渲染 zhu，缺料与正常路径同构
  if (ruku == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // 四类按固定顺序遍历（预算基础→实时经营→行业对标→经营变更）——
  // 表内顺序即录入档案顺序，审计友好
  const hang_lie: string[][] = []
  for (const leibie of ['yusuan', 'shishi', 'hangye', 'biangeng'] as const) {
    // getattr(ruku, leibie, []) 的容错对应：缺字段按空列表处理
    for (const t of (ruku[leibie] ?? []) as BiaozhunJilu[]) {
      // T-29#10 应用：经营变更行备注显式补布尔标签——
      // 登记即 true（T-24 字段落地后以真字段为准，此处为展示注记）
      // 注记拼接策略：已有备注则分号续接，否则直接写入——
      // 保证「登记即 true」的语义在报告上可见（T-24 后改读真字段）
      let beizhu = t.beizhu
      if (t.leibie === '经营变更') {
        beizhu = (beizhu ? beizhu + '；' : '') + 'is_structural_change=true'
      }
      hang_lie.push([
        t.leibie, t.qijian, t.kemu,
        _zhi_xianshi(t.shuzhi, t.danwei), t.danwei,
        t.laiyuan, beizhu,
      ])
    }
  }
  // 拒绝清单（无拒绝行 → 一行"无"）；拒绝行交人工复核——不静默丢弃的展示出口
  const jujue = (ruku.jujue ?? []) as JuJueHang[]
  const jujue_hang: string[][] = jujue.length > 0
    ? jujue.map((x) => [String(x.hanghao), x.yuanyin])
    : [['—', '无']]
  return {
    biaoti,
    biao_lie: [
      ['1.1 归档明细',
        ['数据类别', '期间', '科目', '数值', '单位', '来源', '备注'], hang_lie],
      ['1.2 拒绝清单（交人工复核）', ['行号', '原因'], jujue_hang],
    ],
  }
}

/** 单元 2 滚动预算：多科目 → 科目×期间二维表；单科目 → 逐期表。
 *
 * 组装说明：md/docx 渲染层共用同一份行数据（docx 不移植，见裁决 #12）。
 */
function _jie_2(
  gundong?: GunDongJieguo | null,
  gundong_lie?: readonly (readonly [string, GunDongJieguo])[] | null,
): BiaoKuai {
  const biaoti = '单元 2 · 滚动预算（步骤 2）'
  if (gundong_lie != null && gundong_lie.length > 0) {
    // T-29#1 应用：科目×期间二维表——每科目一行，列为各期间滚动额；
    // 期间列按首次出现序排列；末列 = 该科目滚动总额
    // 期间列并集（首次出现序）——多科目期间天然对齐，缺期显式 "—"
    const qi_lie: string[] = []
    for (const [, g] of gundong_lie) {
      for (const t of g.qijian_mingxi) {
        if (!qi_lie.includes(t.qijian)) {
          qi_lie.push(t.qijian)
        }
      }
    }
    const hang_lie: string[][] = []
    for (const [kemu, g] of gundong_lie) {
      const shuzhi = new Map<string, number>()
      for (const t of g.qijian_mingxi) {
        shuzhi.set(t.qijian, t.shuzhi_fen)
      }
      // shuzhi.get(q) 缺期 → undefined → _yuan 输出 "—"（同 Python dict.get）
      const hang = [kemu, ...qi_lie.map((q) => _yuan(shuzhi.get(q)))]
      hang.push(_yuan(g.gundong_zonge_fen))
      hang_lie.push(hang)
    }
    const toubu = ['科目', ...qi_lie, '合计（元）']
    // T-29#1 应用：累进基数说明（以年初原始分期预算为基数、非链式）
    // 基数说明即 T-29#1 第二问的答案：非链式、保季节轮廓（答辩口径）
    return {
      biaoti,
      biao_lie: [[null, toubu, hang_lie]],
      zhu: '滚动基数说明：以年初原始分期预算为基数、非链式滚动，保留季节波动轮廓（T-23 口径）。',
    }
  }
  if (gundong == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // 单科目回退路径：逐期行 + 合计 + 滚动差异（旧形态，兼容保留）
  const hang_lie = gundong.qijian_mingxi.map((t) => [
    t.qijian, t.zhuangtai,
    _yuan(t.chushi_yusuan_fen), _yuan(t.shuzhi_fen),
  ])
  hang_lie.push(['年度合计', '—',
    _yuan(gundong.chushi_zonge_fen), _yuan(gundong.gundong_zonge_fen)])
  hang_lie.push(['滚动差异（滚动 − 初始）', '—', '—', _yuan(gundong.chae_fen)])
  return {
    biaoti,
    biao_lie: [[null, ['期间', '状态', '初始预算（元）', '滚动额（元）'], hang_lie]],
  }
}

/** 单元 3 差异计算：三重对比表（固定/滚动/实际/基准/差额/率/F-A/预警）。
 *
 * 11 列表头——报告中最宽的表；
 * 列语义：差额 = 实际 − 基准（展示口径）；差异率 = |差额|÷基准（half-up）；
 * 预警三档（无/黄/红）与 F/A 方向规则均来自 variance，本层只排版。
 */
function _jie_3(chayi?: ChayiJieguo | null): BiaoKuai {
  const biaoti = '单元 3 · 差异计算（步骤 3a/3b）'
  if (chayi == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // 滚动预算列缺省（null）显式 "—"——基准退化固定预算的事实可见；
  // 基准列即方差行 jizhun_fen（滚动优先、缺省退化）
  const hang_lie = chayi.xiang.map((x) => [
    x.qijian, x.kemu, x.fangxiang, _yuan(x.chushi_fen),
    x.gundong_fen != null ? _yuan(x.gundong_fen) : '—',
    _yuan(x.shiji_fen), _yuan(x.jizhun_fen), _yuan(x.chae_fen),
    _pct(x.chalv_bps), x.fa, x.yujing,
  ])
  // 合计行：差额求和；F/A 混合方向时上游已判 '—'（口径不在此层重定）
  hang_lie.push(['合计', '—', '—', '—', '—', '—', '—',
    _yuan(chayi.heji_chae_fen), '—', chayi.heji_fa, '—'])
  return {
    biaoti,
    biao_lie: [[null,
      ['期间', '科目', '方向', '固定预算（元）', '滚动预算（元）',
        '实际（元）', '对比基准（元）', '差额（元）', '差异率', 'F/A', '预警'],
      hang_lie]],
    // T-29#5 应用：脚注解释 "—" 与阈值（阈值随常量走，可后台配置）。
    // 【转写设计裁决·修正1】Python 硬编码「≥ 5% 黄色、≥ 10% 红色」为历史
    // 残留——TS 版由 HUANG_YUZHI_BPS/HONG_YUZHI_BPS 常量动态拼出（15%/30%）。
    zhu: '注：① "—"表示该科目本期未生成滚动预算（对比基准退化为固定预算）；'
      + `② 预警阈值：黄档 ${HUANG_YUZHI_BPS / 100}% / 红档 ${HONG_YUZHI_BPS / 100}%（可后台配置）。`,
  }
}

/** 单元 4 规划/执行拆分：三总量 + 四细分 + 残差 + 恒等式。
 *
 * 行序即审计序：总量（恒等式成员）在前、细分（归因）在后、残差收尾。
 */
function _jie_4(chaifen?: ChaifenJieguo | null): BiaoKuai {
  const biaoti = '单元 4 · 规划/执行拆分（步骤 3c）'
  if (chaifen == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // 恒等式行直接展示布尔——规划 + 执行 = 原标准总 的成立性是审计要点
  const hang_lie: string[][] = [
    ['原标准总差异', _yuan(chaifen.yuandan_zong_fen), chaifen.yuandan_zong_fa],
    ['规划总差异（不可控）', _yuan(chaifen.guihua_zong_fen), chaifen.guihua_zong_fa],
    ['执行总差异（可控）', _yuan(chaifen.zhixing_zong_fen), chaifen.zhixing_zong_fa],
    ['恒等式成立（规划 + 执行 = 原标准总）', _shifou(chaifen.hengdengshi_chengli), '—'],
    ['价格规划（细分）', _yuan(chaifen.jiage_guihua_fen), chaifen.jiage_guihua_fa],
    ['价格执行（细分）', _yuan(chaifen.jiage_zhixing_fen), chaifen.jiage_zhixing_fa],
    ['用量规划（细分）', _yuan(chaifen.yongliang_guihua_fen), chaifen.yongliang_guihua_fa],
    ['用量执行（细分）', _yuan(chaifen.yongliang_zhixing_fen), chaifen.yongliang_zhixing_fa],
    // 残差 = 细分合计与总量的解析差额（v2.1 §3：以总量恒等式为准）
    ['残差（价格×用量交叉项解析差额）', _yuan(chaifen.cancha_fen), '—'],
  ]
  // T-29#2 应用：残差来源与处理规则注记（整数运算无浮点噪声——
  // 残差本质是交叉项，规则为小额不参与业务判定、不下游传导）
  const zhu = '注：残差为价格×用量交叉项的解析差额（非计算误差）；处理规则：'
    + `|残差| ≤ ${_yuan(10_000)} 元不参与业务判定、不下游传导`
    + `（本例 ${_yuan(chaifen.cancha_fen)} 元）。`
  return {
    biaoti,
    biao_lie: [[null, ['项目', '金额（元）', 'F/A'], hang_lie]],
    zhu,
  }
}

/** 单元 5 单双环判定：判定要素 + 归因依据 + 纠错动作 + 输入快照。
 *
 * 依据行数可变（yiju 键数稳定为 6）——渲染层按行列表自适应；
 * 判定值即方案 B 输出变量 Loop_Decision；情形编号对应定稿 §4.4 表。
 */
function _jie_5(
  panduan?: PanDuanJieguo | null,
  panduan_shuru?: PanDuanShuru | null,
): BiaoKuai {
  const biaoti = '单元 5 · 单双环判定（步骤 4）'
  if (panduan == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // 判定要素四行固定顺序——后续依据行数可变（yiju 键数稳定为 6）
  const hang_lie: string[][] = [
    ['判定', String(panduan.panduan)],
    ['情形', String(panduan.qingxing)],
    ['需人工审批', _shifou(panduan.shenpi)],
    ['纠错动作', String(panduan.jiuzheng)],
  ]
  // 归因依据（yiju 字典快照——答辩可溯源）；布尔显式是/否、null 显式 "—"
  for (const [jian, zhi] of Object.entries(panduan.yiju)) {
    hang_lie.push([jian,
      typeof zhi === 'boolean' ? _shifou(zhi)
        : (zhi == null ? '—' : String(zhi))])
  }
  // 备注只在非空时列出（留白边界/建议默认口径声明——诚实展示）
  // 情形释义随备注/纠错动作自然带入（如情形 4 = 结构变更与执行偏差并存）
  // 备注行承载定稿留白与更名声明——诚实展示原则的最后一环
  if (panduan.beizhu) {
    hang_lie.push(['备注', String(panduan.beizhu)])
  }
  const biao_lie: _BIaoXiang[] = [[null, ['项目', '值'], hang_lie]]
  // T-29#3 应用：判定输入变量快照表（数值经显示转换；缺项 "—"）
  if (panduan_shuru != null) {
    // 快照六要素与 loop_decision.PanDuanShuru 字段一一对应——
    // 判定可完整复算是「数字零幻觉」承诺在报告侧的体现
    const kuai_zhao: string[][] = [
      ['差异率（基点）', String(panduan_shuru.chalv_bps)],
      ['规划总差异（元）', _yuan(panduan_shuru.guihua_zong_fen)],
      ['执行总差异（元）', _yuan(panduan_shuru.zhixing_zong_fen)],
      ['原标准成本额（元）', _yuan(panduan_shuru.yuandan_cbf_fen)],
      ['结构变更登记', _shifou(panduan_shuru.jie_gou_biangeng)],
      // 变更文本：空串/缺省 → "—"（诚实展示：无登记不留空话）
      ['变更文本', String(panduan_shuru.bianma || '—')],
    ]
    // 快照作为第二张表挂在单元 5 节内
    biao_lie.push(['5.1 判定输入变量快照', ['输入变量', '值'], kuai_zhao])
  }
  return { biaoti, biao_lie }
}

/** 单元 6 积木拆解：四模块表 + 未归属 + 净总差异 + 高亮。
 *
 * 四模块顺序固定（收入/成本/费用/采购——T-21 拍板口径）。
 */
function _jie_6(
  jimu?: JimuJieguo | null,
  jimu_guihua_yingshe?: Record<string, readonly [number, number]> | null,
): BiaoKuai {
  const biaoti = '单元 6 · 积木拆解（步骤 5a）'
  if (jimu == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // T-29#6 应用：规划/执行两列承接单元 4 输出（映射由调用方注入，
  // 无映射的模块显式 "—"——不虚构分摊数据）
  const yingshe = jimu_guihua_yingshe ?? {}
  // 演示注入：采购模块 ← Holmes 拆分结果（材料价格属采购环节）
  const liang_lie = (mokuai: string): [string, string] => {
    // 影子式取值：命中映射 → 双元显示；否则双 "—"（宁缺毋滥）
    const ying = yingshe[mokuai]
    return ying != null ? [_yuan(ying[0]), _yuan(ying[1])] : ['—', '—']
  }

  // 主行循环：四模块逐行展开为七列（含两列规划/执行拆分承接值）
  const hang_lie: string[][] = []
  for (const x of jimu.mokuai_lie) {
    const [guihua, zhixing] = liang_lie(x.mokuai)
    hang_lie.push([
      x.mokuai, _yuan(x.chae_fen), x.fa, _pct(x.zhanbi_bps),
      String(x.hang_shu), guihua, zhixing,
    ])
  }
  // 未归属净额 = 净总差异 − 四模块合计（行级明细见 6.1）；
  // 减法重算即账实勾稽——不为零差异留隐藏空间
  const weigui_jing = jimu.jing_heji_fen
    - jimu.mokuai_lie.reduce((he, x) => he + x.chae_fen, 0)
  hang_lie.push(['未归属', _yuan(weigui_jing), '—',
    _pct(jimu.weiguishu_zhanbi_bps),
    String(jimu.weiguishu_lie.length), '—', '—'])
  // 汇总行/高亮行的新增两列恒为 "—"——它们不是模块，无规划执行拆分可言
  hang_lie.push(['净总差异（实际合计 − 基准合计）', _yuan(jimu.jing_heji_fen),
    '—', '—', '—', '—', '—'])
  hang_lie.push(['核心问题模块',
    jimu.hexin_mokuai ? jimu.hexin_mokuai : '无',
    '—', '—', '—', '—', '—'])
  const biao_lie: _BIaoXiang[] = [
    [null,
      ['模块', '差异额（元）', 'F/A', '占比', '行数',
        '其中规划差异（元）', '其中执行差异（元）'],
      hang_lie],
  ]
  // 未归属明细只在存在时列出——不静默丢弃、也不无病呻吟
  // 未归属行的规划/执行两列为 "—"——拆分结果未按科目下钻前无法归属
  if (jimu.weiguishu_lie.length > 0) {
    const weigui = jimu.weiguishu_lie.map((x) =>
      [x.qijian, x.kemu, _yuan(x.chae_fen)])
    biao_lie.push(['6.1 未归属明细（科目映射不中，交人工补映射）',
      ['期间', '科目', '差额（元）'], weigui])
  }
  return { biaoti, biao_lie }
}

/** 单元 7 平衡计分卡：四维得分/权重 + 总分/等级。
 *
 * 权重来自 quanzhong 元组——逐维对应四行，null 权重显式 "—"；
 * 权重显示整数百分比（40% 风格）；得分列不封顶——>100 原样展示（T-05）。
 */
function _jie_7(bsc?: BscJieguo | null): BiaoKuai {
  const biaoti = '单元 7 · 平衡计分卡（步骤 5b）'
  if (bsc == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // T-29#7 应用：新增达成率列——BSC 得分溯源（得分 = 达成率 × 100 线性折算）
  // 达成率四元组：优先读回显字段（bsc v0.2+）；旧结果对象缺字段时 "—"
  const dcl = [bsc.caijing_bps, bsc.kehu_bps, bsc.neibu_bps, bsc.xuexi_bps]
  const qz = bsc.quanzhong != null && bsc.quanzhong.length > 0
    ? bsc.quanzhong
    : [null, null, null, null]
  const hang_lie: string[][] = [
    ['财务', _pct(dcl[0]), String(bsc.caijing_defen),
      qz[0] != null ? _pct(qz[0] * 100, 0) : '—'],
    ['客户', _pct(dcl[1]), String(bsc.kehu_defen),
      qz[1] != null ? _pct(qz[1] * 100, 0) : '—'],
    ['内部流程', _pct(dcl[2]), String(bsc.neibu_defen),
      qz[2] != null ? _pct(qz[2] * 100, 0) : '—'],
    ['学习成长', _pct(dcl[3]), String(bsc.xuexi_defen),
      qz[3] != null ? _pct(qz[3] * 100, 0) : '—'],
    // 总分与等级两行收尾——五档等级按总分整数判定（完整版行 69-71）
    ['总分', '—', String(bsc.zongfen), '—'],
    ['等级', '—', String(bsc.dengji), '—'],
  ]
  return {
    biaoti,
    biao_lie: [[null, ['维度', 'KPI 达成率', '得分', '权重'], hang_lie]],
    zhu: '维度得分 = KPI 达成率 × 100（线性折算 0–100 分，超 100 不封顶——T-05）；'
      + '总分 = Σ(权重 × 维度得分)。',
  }
}

/** 单元 8 变更溯源：逐 KPI 影响表 + 正负向 TOP3。
 *
 * 影响率列用带符号百分比（方向一目了然）；TOP3 作第二张表；
 * 影响率带符号 = 数值方向；作用列 = 偏好表语义——两列不可混读。
 */
function _jie_8(suyuan?: SuyuanJieguo | null): BiaoKuai {
  const biaoti = '单元 8 · 变更溯源（步骤 6）'
  if (suyuan == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  // T-29#4 应用：新增【计算公式】列——公式文本来自 suyuan 结果字段
  // 公式文本整列相同（同一口径）——列存在本身即「可手工验算」的声明
  const gongshi = suyuan.gongshi || ''
  const hang_lie = suyuan.xiang.map((x) => [
    x.kpi_mingcheng, gongshi, _dai_fuhao_pct(x.yingxianglv_bps),
    x.shuzhi_fangxiang, x.zuoyong, _pct(x.zhanbi_bps),
  ])
  // TOP3 两列表：横向并排一表（同结构双列），空列表显式 "—"
  const top3 = [[
    (suyuan.zhengxiang_top3.join(', ') || '—'),
    (suyuan.fuxiang_top3.join(', ') || '—'),
  ]]
  return {
    biaoti,
    biao_lie: [
      [null,
        ['KPI', '计算公式', '影响率', '数值方向', '作用', '影响占比'],
        hang_lie],
      ['8.1 作用方向 TOP3', ['正向作用 TOP3', '负向作用 TOP3'], top3],
    ],
  }
}

/** 附表 A：KPI 指标库 15 项（BSC/溯源取数源）。
 *
 * 15 行固定——KPI_XIANSHI 元数据即本表的行生成器（三类单位分派显示）；
 * 附表定位：BSC/溯源共同取数源的完整快照——15 项缺数以 "—" 显示。
 */
function _fubiao_a(kpi?: KpiJieguo | null): BiaoKuai {
  const biaoti = '附表 A · KPI 指标库（步骤 1b）'
  if (kpi == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  const hang_lie: string[][] = []
  // 三类分派：pct→百分比 / ci→次（去尾零）/ tian·ci_shu→原值+单位后缀
  for (const [ziming, mingcheng, leibie] of KPI_XIANSHI) {
    const zhi = kpi[ziming]
    // 缺数一律 "—"——附表是「取数源快照」，缺什么一目了然
    let xianshi: string
    if (leibie === 'pct') {
      xianshi = _pct(zhi)
    } else if (leibie === 'ci') {
      xianshi = _ci(zhi)
    } else if (leibie === 'tian') {
      xianshi = zhi != null ? `${zhi} 天` : '—'
    } else {
      xianshi = zhi != null ? `${zhi} 次` : '—'
    }
    hang_lie.push([mingcheng, xianshi])
  }
  // 两列表：KPI 名 + 显示值——15 行顺序即定稿清单顺序
  return {
    biaoti,
    biao_lie: [[null, ['KPI', '数值'], hang_lie]],
  }
}

/** 附表 B：整改清单（AI 层文案起草的输入）。
 *
 * 八列表头与 zhenggai.ZhenggaiXiang 字段一一对应——透传完整性；
 * 本表即 AI 层文案起草的输入——表格完整性与优先级排序在此锁定。
 */
function _fubiao_b(zhenggai?: ZhenggaiJieguo | null): BiaoKuai {
  const biaoti = '附表 B · 整改清单（步骤 8 计算底座）'
  if (zhenggai == null) {
    return { biaoti, zhu: QUE_LIAO }
  }
  let hang_lie = zhenggai.qingdan.map((x) => [
    x.leixing, x.youxianji, x.zeren_mokuai,
    x.qijian || '—', x.kemu || '—',
    x.miaoshu, _shifou(x.shenpi), x.zhuangtai,
  ])
  // 空清单补一行 "—"（上游无整改项是合法状态——报告照常出）；
  // 期间/科目对判定类条目为空，显式 "—" 对齐八列
  if (hang_lie.length === 0) {
    hang_lie = [Array<string>(8).fill('—')]
  }
  // 合计行：总数与三档计数——优先级分布一眼可读
  const zhu = `\n合计：${zhenggai.zong_shu} 条`
    + `（高 ${zhenggai.gao_shu} / 中 ${zhenggai.zhong_shu} / 低 ${zhenggai.di_shu}）\n`
  return {
    biaoti,
    biao_lie: [[null,
      ['类型', '优先级', '责任模块', '期间', '科目', '描述', '需审批', '状态'],
      hang_lie]],
    zhu,
  }
}

/** 附表 C：预警汇总（四档计数）+ 预警科目定位明细（T-29#9 应用）。
 *
 * 本表同时服务多种渲染——数据与展示彻底分离的证据；
 * kanban 优先（看板同源）；缺省退回 chayi 计数——两条路同一组数；
 * 阈值语义：红 ≥30% / 黄 ≥15%（修正1 后口径）/ 无 <15% / 无法定级 = 基准 0。
 */
function _fubiao_c(shuru: BgShuru): BiaoKuai {
  const biaoti = '附表 C · 预警汇总'
  // 计数来源两级回退：kanban 汇总 → chayi 计数 → 全 "—" 占位。
  // Python `if kanban.yujing_huizong:` 空字典为假——TS 用键数判空同型对应
  const kanban = shuru.kanban
  const hz = kanban != null ? kanban.yujing_huizong : null
  let hang_lie: string[][]
  if (hz != null && Object.keys(hz).length > 0) {
    hang_lie = [[String(hz['hong_shu']), String(hz['huang_shu']),
      String(hz['wu_shu']), String(hz['wufa_shu'])]]
  } else if (shuru.chayi != null) {
    hang_lie = [[String(shuru.chayi.hong_shu), String(shuru.chayi.huang_shu),
      String(shuru.chayi.wu_shu), String(shuru.chayi.wufa_shu)]]
  } else {
    // 全缺料 → 一行 "—"（四档计数的空形态）——注意本节**不**输出"（缺料）"
    hang_lie = [['—', '—', '—', '—']]
  }
  const biao_lie: _BIaoXiang[] = [
    [null, ['红色预警', '黄色预警', '无预警', '无法定级'], hang_lie],
  ]
  // T-29#9 应用：预警科目定位——红/黄行逐行列出
  // （报告位置 = 单元 3 差异表的第几数据行，可直接回查）
  // 定位明细只列红/黄两档——无预警行不占表（与计数口径一致）
  if (shuru.chayi != null) {
    const dingwei: string[][] = []
    let xuhao = 1
    for (const x of shuru.chayi.xiang) {
      if (x.yujing === '红' || x.yujing === '黄') {
        dingwei.push([`${x.yujing}色预警`, x.kemu, `单元 3 第 ${xuhao} 行`])
      }
      xuhao += 1
    }
    if (dingwei.length > 0) {
      // 报告位置格式「单元 3 第 N 行」——N 即差异表第 N 条数据行
      biao_lie.push(['C.1 预警科目定位', ['档位', '科目', '报告位置'], dingwei])
    }
  }
  return { biaoti, biao_lie }
}

// ======================================================================
// 组装层入口（数据块列表——渲染层（md/JSON）的共同输入）
// ======================================================================

/** 组装数据块（总览 + 八单元 + 三附表；纯函数，零自然语言文案）。
 *
 * 参数：shuru —— BgShuru（十一个上游结果，均可缺省 null）。
 *
 * 返回：12 个 BiaoKuai（顺序 = 总览 + 方案 B 步骤顺序 + 三附表）；
 * 任一上游缺省 → 对应块 biao_lie 为空、zhu = "（缺料）"。
 */
export function shengcheng_baogao_kuai(shuru: BgShuru): BiaoKuai[] {
  // 类型门禁与全项目一致（Python isinstance 的鸭子对应——结构类型下
  // 只挡"根本不是对象形状"的调用，字段级容错交给各消费处的 null 透传）
  if (shuru == null || typeof shuru !== 'object') {
    throw new TypeError(`输入必须是 BgShuru：${String(shuru)}`)
  }

  // 十二块按方案 B 步骤顺序组装（总览→录入→滚动→差异→拆分→判定→积木→BSC→溯源）；
  // 返回列表即渲染层的共同输入——多渲染目标内容必然一致
  return [
    _zong_lan(shuru),
    _jie_1(shuru.ruku),
    _jie_2(shuru.gundong, shuru.gundong_lie),
    _jie_3(shuru.chayi),
    _jie_4(shuru.chaifen),
    _jie_5(shuru.panduan, shuru.panduan_shuru),
    _jie_6(shuru.jimu, shuru.jimu_guihua_yingshe),
    _jie_7(shuru.bsc),
    _jie_8(shuru.suyuan),
    _fubiao_a(shuru.kpi),
    _fubiao_b(shuru.zhenggai),
    _fubiao_c(shuru),
  ]
}

// ======================================================================
// 渲染层：Markdown（标准库能力，零依赖）
// ======================================================================
// 渲染规则（与不移植的 docx 渲染层保持语义一致）：
//   节标题 → '## '；小节标题 → '### '；数据块 → 管道表格；
//   缺料节 → 标题后跟占位行；节尾注记（zhu）紧随表格之后。
// ======================================================================

/** 生成数据计算测试报告（Markdown 全文；纯函数，零自然语言文案）。
 *
 * 参数：shuru —— BgShuru（十一个上游结果，均可缺省 null）。
 *
 * 返回：完整 Markdown 文本——总览 + 八单元各一节一表 + 三个附表；
 * 任一上游缺省 → 对应节输出"（缺料）"占位，不抛错。
 */
export function shengcheng_baogao_md(shuru: BgShuru): string {
  // 组装与渲染分离：本函数只消费 BiaoKuai，不再触碰任何上游对象——
  // 新增渲染目标（JSON/HTML）时组装层零改动
  const kuai_lie = shengcheng_baogao_kuai(shuru)
  // md 渲染：同一份 BiaoKuai 列表
  const suipian: string[] = []
  for (const kuai of kuai_lie) {
    // 每个单元一节一表——「一个分析项目对应一张数据表」即此结构
    suipian.push(`## ${kuai.biaoti}\n\n`)
    const biao_lie = kuai.biao_lie ?? []
    // 缺料占位：报告结构完整，节内只有占位行——与看板容错同款纪律
    if (biao_lie.length === 0) {
      suipian.push(QUE_LIAO + '\n\n')
      continue
    }
    // 小节标题（1.1/1.2/5.1/6.1/8.1/C.1）渲染为三级标题；主表无小节标题
    for (let i = 0; i < biao_lie.length; i++) {
      const [zi_biaoti, toubu, hang_lie] = biao_lie[i]
      if (zi_biaoti != null) {
        suipian.push(`### ${zi_biaoti}\n\n`)
      }
      suipian.push(_biao(toubu, hang_lie))
      if (i < biao_lie.length - 1) {
        suipian.push('\n')
      }
    }
    if (kuai.zhu) {
      suipian.push(kuai.zhu)
    }
    suipian.push('\n')
  }
  // 抬头 + 十一节拼接；rstrip 去尾部空白——文件末尾恰好一个换行
  // 抬头（含元信息行）在前、各节依序拼接——文件可直接被渲染器消费
  return BAOGAO_TAITOU + '\n' + suipian.join('').replace(/\s+$/, '') + '\n'
}
