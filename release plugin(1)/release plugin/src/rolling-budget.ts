// ======================================================================
// 滚动预算重算模块 —— 方案B 步骤 2 的确定性核心（定稿 #1：全额替换制）
// ======================================================================
//
// 转写自 D:\AppProject\algo\rolling_budget.py（Python 版为唯一行为准绳；
// 拼音标识符逐字保留，期望值以 algo/tests/test_rolling_budget.py 为准，
// 对应本插件 tests/rolling-budget.test.ts，测试数字逐字对应）。
//
// 命名规范（2026-08-23 用户指令）：本模块所有标识符（变量/函数/类型/常量/
// 字典键）一律用【无声调拼音】，数据值用中文；文件名保持英文（Windows 规范）。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/textbook/finagent-算法核对文档-定稿.md  v2.1  §1
//     docs/10-待核对问题定稿摘要.md  #1（队友定稿：全额替换模式）
//
// 核心规则（定稿 #1；剩余期链式读法 2026-09-03 队友拍板）：
//     1. 已届满周期：用实际经营数据【全额替换】原预算（机械动作，每次数据
//        更新必做，与单双环判定无关——判定是步骤 4 的治理决策，见
//        loop_decision 模块）。
//     2. 剩余周期（链法①，2026-09-03 重开 T-23 并拍板）：
//        首个剩余期 = 自身年初预算 × (1+g)；此后每期 = 上一期【滚动值】×
//        (1+g)，逐期接力舍入。注意：不接上一期【实际数】（链法②已否）；
//        接力从首个剩余期起，届满期实际数不进接力链。
//        背景：Broad Co 例题各期等额，链式与非链式数值恰同，例题无法区分；
//        2026-09-03 队友按教材滚动编制直觉改拍链式①，非等额场景季节轮廓
//        随之淡化为渐近线。
//     3. 季度滚动可叠加"行业对标修正系数"（口径 A：增长率差值法，差值达
//        阈值才启用；口径 B：不修正）。月度滚动【不叠加】行业修正
//        （定稿 #1：月度纯企业内部修正）。
//
// 数值纪律（docs/02 架构 ADR / docs/06 路线 2）：
//     - 金额单位 = 「分」的整数（int），全程整数运算，杜绝浮点误差；
//       Python int 无上限，TS number 只有 53 位安全整数——金额×基点的
//       中间量统一走 ./int-math.ts 的 BigInt 半进位助手，
//       禁止裸 `*` 后 `Math.round`。
//     - 增长率单位 = 基点 jidian（1% = 100 基点），整数；
//     - 乘法舍入：四舍五入（half-up），逐期累进舍入（与例题数字一致）。
//
// 与 Python 的对应关系（转写说明）：
//     `_cheng_jidian`  → 公共库 cheng_jidian（./int-math.ts，逐式对应）；
//     `fen_zhuan_yuan` → 公共库 fen_zhuan_yuan（本文件转出，模块面一致）；
//     其余标识符与 Python 逐字同名。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     QijianJine                期间金额（一行预算/实际数据）
//     GunDongShezhi             滚动设置（周期、增长率、行业修正参数）
//     DanqiJieguo               单期结果（一个期间的重算明细）
//     GunDongJieguo             滚动结果（整体输出）
//     GunDongCuowu              滚动错误（校验失败异常）
//     gengxin_gundong_yusuan    更新滚动预算（主函数）
//     fen_zhuan_yuan            分转元（展示用换算）
//     jine_fen / shuzhi_fen     金额分 / 数值分
//     zhouqi / zengzhanglv_jidian   周期 / 增长率基点
//     hangye_xiuzheng           行业修正（'A' 差值法 / 'B' 不修正）
//     qijian / kemu / laiyuan   期间 / 科目 / 来源
//     zhuangtai                 状态（'已届满' / '剩余期'）
//
// 口径依据与建立：2026-08-22 建立，2026-08-23 v0.4 拼音化 ｜ TS 转写 2026-09-05
// ======================================================================

import { cheng_jidian, fen_zhuan_yuan } from './int-math.ts'

// fen_zhuan_yuan 已收录于公共库（分 → 元字符串，两位小数）；此处转出，
// 使 `from './rolling-budget.ts'` 的导入面与 Python
// `from rolling_budget import fen_zhuan_yuan` 完全一致。
export { fen_zhuan_yuan }

// ======================================================================
// 常量区
// ======================================================================

/** 单期金额上限（分）= 90 亿元/期。超出视为脏数据直接拒绝（合理性校验，
 *  Python int 本身无溢出风险；TS 侧的 2^53 安全域由 int-math 的 BigInt
 *  助手守护，本常量只负责拦截明显的录入错误）。 */
export const ZUIDA_JINE_FEN: number = 9 * 10 ** 11 // = 900000000000

/** 基点换算基数（"万分制"：金额 × (10000 + 基点) / 10000）。 */
export const JIDIAN_JISHU: number = 10_000

/** 口径 A 的默认启用阈值（基点）：|企业增长率 - 行业增长率| ≥ 50 基点
 *  （0.5 个百分点）才施加行业修正，避免微小差值引发预算抖动
 *  （建议值，待会计复核）。 */
export const MOREN_HANGYE_YUZHI_JIDIAN: number = 50

// ======================================================================
// 数据结构区（Python frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** 一个期间的金额记录（预算行或实际行）。
 *
 *  字段说明：
 *      qijian:   期间键，月度 '2026-01' / 季度 '2026-Q1'。
 *                仅作匹配与透传——本模块【不解析】期间语义，
 *                顺序完全以 guding_yusuan 的传入顺序为准。
 *      jine_fen: 金额，单位分，非负整数，上限 ZUIDA_JINE_FEN。
 */
export interface QijianJine {
  readonly qijian: string
  readonly jine_fen: number
}

/** 滚动重算设置。
 *
 *  字段说明：
 *      zhouqi:                 滚动周期，'月度' 或 '季度'（定稿 #1 两模式）。
 *      zengzhanglv_jidian:     最新经营增长率（企业口径），基点，[-10000, 10000]。
 *                              演示期由管理员/LLM 外生给定（T-22-③）。
 *      hangye_xiuzheng:        【T-02 已拍板 2026-08-23】行业对标修正口径：
 *                              'A' = 增长率差值法（默认——用户拍板；仅季度生效，
 *                              季度场景必须提供 hangye_zengzhanglv_jidian）；
 *                              'B' = 不修正（可显式传参选择）。
 *      hangye_zengzhanglv_jidian: 口径 A 必填：行业平均增长率，基点。
 *      hangye_yuzhi_jidian:    口径 A 的启用阈值，基点，默认 50。
 *
 *  Python dataclass 的默认值（'A' / None / 50）由下方同名构造助手承载——
 *  这不是工厂类，只是把 dataclass 缺省字段语义原样搬过来，并让
 *  「默认口径回归」用例（hangye_xiuzheng 缺省 == 'A'）可逐字断言。
 */
export interface GunDongShezhi {
  readonly zhouqi: string
  readonly zengzhanglv_jidian: number
  readonly hangye_xiuzheng: string // 缺省 'A'（口径 A 为默认，用户拍板 2026-08-23）
  readonly hangye_zengzhanglv_jidian: number | null // 缺省 null
  readonly hangye_yuzhi_jidian: number // 缺省 MOREN_HANGYE_YUZHI_JIDIAN
}

/** GunDongShezhi 构造助手：对应 Python `GunDongShezhi(zhouqi=..., ...)`，
 *  可选参数按 dataclass 默认值补齐（hangye_xiuzheng='A'、行业增长率=null、
 *  行业阈值=50）。 */
export function GunDongShezhi(
  zhouqi: string,
  zengzhanglv_jidian: number,
  ke_xuan: {
    readonly hangye_xiuzheng?: string
    readonly hangye_zengzhanglv_jidian?: number | null
    readonly hangye_yuzhi_jidian?: number
  } = {},
): GunDongShezhi {
  return {
    zhouqi,
    zengzhanglv_jidian,
    hangye_xiuzheng: ke_xuan.hangye_xiuzheng ?? 'A', // 口径 A 为默认（用户拍板 2026-08-23，T-02）
    hangye_zengzhanglv_jidian: ke_xuan.hangye_zengzhanglv_jidian ?? null,
    hangye_yuzhi_jidian: ke_xuan.hangye_yuzhi_jidian ?? MOREN_HANGYE_YUZHI_JIDIAN,
  }
}

/** 单期重算结果。
 *
 *  字段说明：
 *      qijian:            期间键（同输入）。
 *      chushi_yusuan_fen: 该期初始预算金额（分）。
 *      zhuangtai:         '已届满' / '剩余期'。
 *      shuzhi_fen:        重算后的值（分）：届满期 = 实际数；剩余期 = 累进重算值。
 *      laiyuan:           '实际'（实际替换）/ '重算'（累进重算）。
 */
export interface DanqiJieguo {
  readonly qijian: string
  readonly chushi_yusuan_fen: number
  readonly zhuangtai: string
  readonly shuzhi_fen: number
  readonly laiyuan: string
}

/** 滚动预算整体结果。
 *
 *  字段说明：
 *      qijian_mingxi:         逐期结果，顺序与 guding_yusuan 一致。
 *      chushi_zonge_fen:      初始年度预算总额（分）。
 *      gundong_zonge_fen:     更新后年度滚动预算总额（分）——核心输出，
 *                             定稿公式：已届满实际合计 + 剩余修正后预算合计。
 *      chae_fen:              展示口径差额 = 滚动总额 - 初始总额
 *                             （正 = 滚动后超出原预算；符号口径见定稿 §0.5）。
 *      hangye_xiuzheng_qiyong: 行业修正是否实际启用（口径 A 且达阈值）。
 */
export interface GunDongJieguo {
  readonly qijian_mingxi: DanqiJieguo[]
  readonly chushi_zonge_fen: number
  readonly gundong_zonge_fen: number
  readonly chae_fen: number
  readonly hangye_xiuzheng_qiyong: boolean
}

/** 滚动预算输入/设置校验失败。
 *
 *  语义：调用方（数据导入层或 LLM 工具壳）传入的参数违反口径或数据纪律。
 *  Python 侧继承 ValueError 以便上层按"脏数据"统一捕获；TS 侧按插件
 *  约定统一 extends Error，中文报错文案与 Python 逐字一致。
 */
export class GunDongCuowu extends Error {}

// ======================================================================
// 内部工具函数区
// ======================================================================

/** Python f-string `{x!r}`（repr）的 TS 对应：字符串/对象走 JSON 化，
 *  其余 String 化。仅用于报错文案里的非法值回显。 */
function _repr(x: unknown): string {
  if (typeof x === 'string') return JSON.stringify(x)
  if (typeof x === 'object' && x !== null) return JSON.stringify(x)
  return String(x)
}

/** isinstance(tiao, QijianJine) 的鸭子对应：frozen dataclass 转普通对象
 *  字面量后没有类可查，改查结构键（随后逐字段校验补足类型判定）。 */
function _shi_qijian_jine(x: unknown): boolean {
  return typeof x === 'object' && x !== null && 'qijian' in x && 'jine_fen' in x
}

/** 校验金额字段：非负整数且不超过 ZUIDA_JINE_FEN，否则抛 GunDongCuowu。 */
function _jianyan_jine(shuzhi: unknown, biaoshi: string): void {
  // isinstance(bool) 也是 int 的子类，先排除 bool 防止 True/False 混入；
  // TS 的 number 天然不含 bool，Number.isInteger 一步挡住浮点与非数。
  if (typeof shuzhi !== 'number' || !Number.isInteger(shuzhi)) {
    throw new GunDongCuowu(`${biaoshi} 必须为整数（分）：${_repr(shuzhi)}`)
  }
  if (shuzhi < 0 || shuzhi > ZUIDA_JINE_FEN) {
    throw new GunDongCuowu(`${biaoshi} 必须在 [0, ${ZUIDA_JINE_FEN}] 内（分）：${shuzhi}`)
  }
}

/** 校验基点字段：[-10000, 10000] 内的整数（即 ±100% 封顶）。 */
function _jianyan_jidian(shuzhi: unknown, biaoshi: string): void {
  if (typeof shuzhi !== 'number' || !Number.isInteger(shuzhi)) {
    throw new GunDongCuowu(`${biaoshi} 必须为整数（基点）：${_repr(shuzhi)}`)
  }
  if (shuzhi < -JIDIAN_JISHU || shuzhi > JIDIAN_JISHU) {
    throw new GunDongCuowu(`${biaoshi} 必须在 [-10000, 10000] 内（基点）：${shuzhi}`)
  }
}

/** 校验并复制期间序列：结构合法、期间键唯一且非空、金额合法。
 *
 *  说明：
 *      返回【复制】而非原数组引用——纯函数纪律，避免调用方后续修改
 *      影响已传入的数据（readonly interface 只保证字段不可变）。
 */
function _guifanhua_qijian(xiang: unknown, biaoshi: string, yunxu_wei_kong: boolean): QijianJine[] {
  if (!Array.isArray(xiang)) {
    throw new GunDongCuowu(`${biaoshi} 必须是列表`)
  }
  if (xiang.length === 0) {
    if (yunxu_wei_kong) return [] // 实际数据允许为空（尚未有任何实际数据）
    throw new GunDongCuowu(`${biaoshi} 不能为空`)
  }

  const yijian = new Set<string>()
  for (const tiao of xiang as unknown[]) {
    if (!_shi_qijian_jine(tiao)) {
      throw new GunDongCuowu(`${biaoshi} 含非法元素（须为 QijianJine）：${_repr(tiao)}`)
    }
    const t = tiao as QijianJine
    if (typeof t.qijian !== 'string' || t.qijian === '') {
      throw new GunDongCuowu(`${biaoshi} 含非法期间键：${_repr(t.qijian)}`)
    }
    if (yijian.has(t.qijian)) {
      throw new GunDongCuowu(`${biaoshi} 期间重复：${t.qijian}`)
    }
    yijian.add(t.qijian)
    _jianyan_jine(t.jine_fen, `${biaoshi}[${t.qijian}].jine_fen`)
  }
  return (xiang as QijianJine[]).map((t) => ({ qijian: t.qijian, jine_fen: t.jine_fen }))
}

// ======================================================================
// 核心算法区
// ======================================================================

/** 滚动预算重算（方案B 步骤 2；纯函数，无副作用、无 I/O）。
 *
 *  参数：
 *      guding_yusuan: 年度固定预算（各期），顺序即期间顺序，不可为空。
 *      shiji_shuju:   已届满期的实际数据，可为空数组；期间必须存在于预算表。
 *      shezhi:        GunDongShezhi，见其注释。
 *
 *  返回：
 *      GunDongJieguo（含逐期明细与总额）。
 *
 *  剩余期算法（链法①，2026-09-03 队友拍板 T-23 重开定案）：
 *      首个剩余期 = 自身年初预算 × (1+g)；此后每期 = 上一期滚动值 × (1+g)，
 *      逐期舍入（half-up）接力；届满期实际数不进接力链。
 *      例题佐证：Broad Co 等额 220,000 → 222,200 / 224,422 / 226,666.22
 *      （等额下链式与非链式同值，例题数字不变）。
 *
 *  口径 A（仅季度）：
 *      各剩余期累进结果再乘一次 (1 + (g_corp - g_ind))——定稿公式
 *      「×行业对标修正系数」的【一次性乘子】解读（非累进复利）；
 *      该解读方式待会计复核（用户策略：产出数据交会计挑毛病）。
 *      启用条件：|g_corp - g_ind| >= 阈值（默认 50 基点，边界即启用）。
 */
export function gengxin_gundong_yusuan(
  guding_yusuan: readonly QijianJine[],
  shiji_shuju: readonly QijianJine[],
  shezhi: GunDongShezhi,
): GunDongJieguo {
  // ---- 输入规范化与基础校验 ----
  const yusuan = _guifanhua_qijian(guding_yusuan, 'guding_yusuan', false)
  const shiji_liebiao = _guifanhua_qijian(shiji_shuju, 'shiji_shuju', true)

  if (typeof shezhi !== 'object' || shezhi === null) {
    throw new GunDongCuowu('shezhi 必须为 GunDongShezhi 实例')
  }
  if (shezhi.zhouqi !== '月度' && shezhi.zhouqi !== '季度') {
    throw new GunDongCuowu('shezhi.zhouqi 必须为 "月度" 或 "季度"')
  }
  _jianyan_jidian(shezhi.zengzhanglv_jidian, 'shezhi.zengzhanglv_jidian')
  if (shezhi.hangye_xiuzheng !== 'A' && shezhi.hangye_xiuzheng !== 'B') {
    throw new GunDongCuowu('shezhi.hangye_xiuzheng 必须为 "A" 或 "B"')
  }

  // 实际数据建索引；期间必须存在于预算表（防脏数据错位）
  const shiji_suoyin = new Map<string, number>()
  for (const tiao of shiji_liebiao) {
    if (!yusuan.some((y) => y.qijian === tiao.qijian)) {
      throw new GunDongCuowu(`实际数据期间不在预算表中：${tiao.qijian}`)
    }
    shiji_suoyin.set(tiao.qijian, tiao.jine_fen)
  }

  // ---- 口径 A 参数校验与启用判定（仅季度；月度纯企业内部修正——定稿 #1）----
  let hangye_yinzi_jidian = 0 // 修正乘子的基点增量；0 = 不修正
  let hangye_qiyong = false
  if (shezhi.hangye_xiuzheng === 'A' && shezhi.zhouqi === '季度') {
    if (shezhi.hangye_zengzhanglv_jidian === null) {
      throw new GunDongCuowu('口径 A 需要提供 hangye_zengzhanglv_jidian')
    }
    _jianyan_jidian(shezhi.hangye_zengzhanglv_jidian, 'shezhi.hangye_zengzhanglv_jidian')
    const yuzhi = shezhi.hangye_yuzhi_jidian
    // bool 排除 + 非负整数 + 上限 10000（= ±100%），与 Python 同款
    if (!Number.isInteger(yuzhi) || yuzhi < 0 || yuzhi > JIDIAN_JISHU) {
      throw new GunDongCuowu('shezhi.hangye_yuzhi_jidian 必须为 [0, 10000] 内整数')
    }
    const chazhi = shezhi.zengzhanglv_jidian - shezhi.hangye_zengzhanglv_jidian
    if (Math.abs(chazhi) >= yuzhi) {
      // 达阈值才启用，防微小差值抖动（差值恰等于阈值即启用——边界即启用）
      hangye_yinzi_jidian = chazhi
      hangye_qiyong = true
    }
  }

  // ---- 逐期重算主循环（链法①：首个剩余期起于自身年初数，此后接力上一期滚动值）----
  const qijian_mingxi: DanqiJieguo[] = []
  let qiju = 0 // 期距：距上一个届满期（或序列起点）；届满期后归零重计
  let qian_yi_gundong: number | null = null // 上一期滚动值（链法①接力种子；届满期后清空）
  for (const y of yusuan) {
    if (shiji_suoyin.has(y.qijian)) {
      // 已届满：实际数据全额替换（定稿 #1 机械动作）
      qijian_mingxi.push({
        qijian: y.qijian,
        chushi_yusuan_fen: y.jine_fen,
        zhuangtai: '已届满',
        shuzhi_fen: shiji_suoyin.get(y.qijian) as number,
        laiyuan: '实际',
      })
      qiju = 0 // 重新起算期距
      qian_yi_gundong = null // 链种子重置：届满期实际数不进接力链
    } else {
      // 剩余期（链法①，2026-09-03 队友拍板，T-23 重开定案）：
      //   首个剩余期 = 自身年初预算 × (1+g)；
      //   之后每期 = 上一期滚动值 × (1+g)，逐期舍入接力。
      qiju += 1
      let shuzhi: number
      if (qiju === 1 || qian_yi_gundong === null) {
        shuzhi = y.jine_fen
      } else {
        shuzhi = qian_yi_gundong
      }
      shuzhi = cheng_jidian(shuzhi, shezhi.zengzhanglv_jidian)
      if (hangye_qiyong) {
        // 口径 A：一次性乘子，作用在当期滚动结果之上（随接力链自然延续）
        shuzhi = cheng_jidian(shuzhi, hangye_yinzi_jidian)
      }
      qian_yi_gundong = shuzhi
      qijian_mingxi.push({
        qijian: y.qijian,
        chushi_yusuan_fen: y.jine_fen,
        zhuangtai: '剩余期',
        shuzhi_fen: shuzhi,
        laiyuan: '重算',
      })
    }
  }

  // ---- 汇总输出 ----
  // 逐期金额 ≤ 9×10^11、年化期数 ≤ 12，reduce 求和远在 2^53 安全区内。
  const chushi_zonge = yusuan.reduce((he, y) => he + y.jine_fen, 0)
  const gundong_zonge = qijian_mingxi.reduce((he, q) => he + q.shuzhi_fen, 0)
  return {
    qijian_mingxi,
    chushi_zonge_fen: chushi_zonge,
    gundong_zonge_fen: gundong_zonge,
    chae_fen: gundong_zonge - chushi_zonge,
    hangye_xiuzheng_qiyong: hangye_qiyong,
  }
}
