// ======================================================================
// 差异计算模块 —— 方案B 步骤 3 的【3a 三重对比 + 3b 预警分级】（确定性核心）
// ======================================================================
//
// 转写自 D:\AppProject\algo\variance.py（Python 版为唯一行为准绳；
// 拼音标识符逐字保留，期望值以 algo/tests/test_variance.py 为准，
// 对应本插件 tests/variance.test.ts，测试数字逐字对应）。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/textbook/finagent-算法核对文档-定稿.md v2.1 §2（含 §0.5 符号口径）
//     docs/10-待核对问题定稿摘要.md  #2（差异率分母）/ #3（预警三档）
//
// 三重对比（定稿 §2.3）：每个指标一个期间一行——
//     【固定预算】 VS 【滚动/弹性预算】 VS 【实际】
//     对比基准 = 滚动预算额（未提供滚动时退化为固定预算额）；
//     差异额 = 实际 − 基准（展示口径，§0.5）。
//
// F/A 判定（§0.5 方向规则，系统唯一真源）：
//     成本类（含费用/采购）：差额为正 = 超支 = A（不利）；负 = 节约 = F（有利）；
//     收入类：差额为正 = 超额 = F（有利）；负 = 未达标 = A（不利）；
//     差额为零 = '—'。
//
// 差异率（定稿 #2）：差异率 = |差额| ÷ 对比基准额，存整数基点（1% = 100 基点），
//     四舍五入 half-up。基准为 0 时差异率无法定义 → null，预警记 '—'
//     （【口径说明·待会计复核】除零场景定稿未定义，我们选择交人工而非臆造）。
//
// 预警分级（三档体系；2026-09-03 起档位完全可配置——用户接口）：
//     【阈值口径变更记录】定稿 #3 原口径 1% → T-29#5 调 5%/10%（2026-08-24）→
//     【2026-09-03 用户拍板】15%/30% 分割（低线 15% 黄、高线 30% 红）；
//     阈值以模块常量承载——后台配置 = 修改常量（HUANG_YUZHI_BPS/HONG_YUZHI_BPS）。
//
//     默认体系（不传配置时）：
//     |差异率| < 15%（1500 基点）        → '无'（数据正常波动）
//     15% ≤ |差异率| < 30%（3000 基点） → '黄'（关注，无需强制整改）
//     |差异率| ≥ 30%                    → '红'（强制整改 + 风险溯源）
//
//     【用户自定义接口（jisuan_chayi 可选参数）】：
//     dang_lie       —— 默认档位序列（全部科目）：每档 YujingDang(名称, 颜色, 阈值基点)，
//                       档数不限、阈值不限、颜色不限（含色号）；从阈值最高的档往下匹配。
//     kemu_dang_lie  —— 按科目覆盖：{科目名: 档位序列}，做"每科目独立阈值/档数/颜色"。
//     兼容性：ChayiXiang.yujing = 档位名称——自定义档名时下游按 '红'/'黄' 字面
//     过滤的链路将落空，自定义请保留最高档名 '红'、次档 '黄'，或自行适配下游；
//     颜色不受此限（ChayiXiang.yan_se / ChayiJieguo.dang_tongji 随意定制）。
//
// 数值纪律：金额 = 整数分；差异率 = 整数基点；全程整数运算，除法仅在
//     差异率一步且用 half-up 整数实现（与全项目一致，杜绝浮点）。
//     TS 差异：|差额|×10000 的中间量可超 2^53 → 差异率统一走公共库
//     bili_bps_ban_jian（半分母变体，与 Python 原式逐式对应，勿混用 bili_bps）。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     ChayiShuru        差异输入（一个指标一个期间的一行三数）
//     ChayiXiang        差异项（输出：输入 + 基准/差额/差异率/F-A/预警）
//     ChayiJieguo       差异结果（全部差异项 + 合计 + 预警计数）
//     ChayiCuowu        差异错误（校验失败异常）
//     jisuan_chayi      计算差异（主函数）
//     chushi_fen        初始预算额（分）——"固定预算"列
//     gundong_fen       滚动预算额（分）——"滚动/弹性预算"列，可为 null
//     shiji_fen         实际额（分）——"实际"列
//     jizhun_fen        基准额（分）= 滚动预算（缺省退化为初始预算）
//     chae_fen          差额（分）= 实际 − 基准（展示口径）
//     chalv_bps         差异率（基点，非负；基准为 0 时为 null）
//     fa                F/A 判定（F 有利 / A 不利 / '—' 零差额）
//     yujing            预警（'无' / '黄' / '红' / '—' 无法定级）
//     fangxiang         方向（'成本类' / '收入类'——决定 F-A 映射）
//
// 与上下游的关系：
//     上游：data_ingest（四类归档供数）、rolling_budget（滚动预算额供数）；
//     下游：planning_operational（步骤 3c 规划/执行拆分）、看板预警着色。
//
// 建立：2026-08-23 ｜ TS 转写 2026-09-05
// ======================================================================

import { bili_bps_ban_jian } from './int-math.ts'

// ======================================================================
// 常量区
// ======================================================================

/** 方向一：成本类（含费用、采购——差额为正 = 超支 = 不利 A） */
export const FANGXIANG_CHENGBEN = '成本类'
/** 方向二：收入类（差额为正 = 超额 = 有利 F） */
export const FANGXIANG_SHOURU = '收入类'

/** 合法方向集合（输入行的 fangxiang 必须是其一） */
export const HEFA_FANGXIANG: readonly string[] = [FANGXIANG_CHENGBEN, FANGXIANG_SHOURU]

/** 预警档位（定稿 #3 三档 + 无法定级） */
export const YUJING_WU = '无' // |差异率| < 黄阈：正常波动
export const YUJING_HUANG = '黄' // 黄阈 ≤ |差异率| < 红阈：关注
export const YUJING_HONG = '红' // |差异率| ≥ 红阈：强制整改
export const YUJING_WUFA = '—' // 基准为 0 无法定级（交人工，见模块头"口径说明"）

/** 黄色阈值（基点）：|差异率| ≥ 1500（即 15%）进入黄色及以上
 *  【阈值变更记录】定稿 #3 原口径 100 基点（1%）→ T-29#5 调 500 基点（5%）→
 *  【2026-09-03 用户拍板】→ 1500 基点（15%）——三档分割 15%/30% 中的低线；
 *  「支持后台配置」= 修改本常量即可回退/微调（如改回 500 即恢复 T-29#5 口径） */
export const HUANG_YUZHI_BPS = 1500
/** 红色阈值（基点）：|差异率| ≥ 3000（即 30%）进入红色
 *  【2026-09-03 用户拍板】三档分割 15%/30% 中的高线（原 1000 基点/10% 保留版本历史） */
export const HONG_YUZHI_BPS = 3000

/** 单期金额上限（分）——与 rolling_budget 同口径的合理性校验 */
export const ZUIDA_JINE_FEN = 9 * 10 ** 11 // = 900000000000

// ======================================================================
// 数据结构区（Python frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** 一个预警档位（用户可自定义：名称/颜色/阈值，档数不限）。
 *
 *  字段：
 *      ming_cheng: 档位名称——落入本档时 ChayiXiang.yujing 的取值。
 *                  默认体系 = '红'/'黄'；保留名 '无' 与 '—' 禁用（防计数混淆）。
 *      yan_se:     颜色——展示层着色用（可中文色名 '橙' 或 '#FF8800' 式色号）。
 *      yu_fen:     阈值（基点，非负整数）：|差异率| ≥ yu_fen 落入本档。
 *                  1% = 100 基点。匹配规则：从阈值最高的档往下找第一个达标的。
 */
export interface YujingDang {
  readonly ming_cheng: string
  readonly yan_se: string
  readonly yu_fen: number
}

/** 默认档位（定稿 #3 体系：≥红阈 红、≥黄阈 黄、其余无——不传配置时自动使用，
 *  下游 xishu/zhenggai/kanban 按 '红'/'黄' 档名消费，默认体系下全部兼容） */
export const MOREN_DANG_LIE: readonly [YujingDang, YujingDang] = [
  { ming_cheng: YUJING_HONG, yan_se: '红', yu_fen: HONG_YUZHI_BPS },
  { ming_cheng: YUJING_HUANG, yan_se: '黄', yu_fen: HUANG_YUZHI_BPS },
]

/** 差异计算输入校验失败（方向非法 / 金额非法 / 结构非法）。
 *
 *  Python 继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）；
 *  TS 侧按插件约定统一 extends Error，中文报错文案与 Python 逐字一致。
 */
export class ChayiCuowu extends Error {}

/** 差异输入：一个指标在一个期间的三数（固定预算 / 滚动预算 / 实际）。
 *
 *  字段说明：
 *      qijian:      期间键（2026-01 / 2026-Q1；透传，本模块不解析语义）。
 *      kemu:        指标科目名（营收、直接材料、电力……）。
 *      fangxiang:   方向（'成本类' / '收入类'）——决定 F-A 映射方向。
 *      chushi_fen:  初始（固定）预算额，非负整数分。
 *      gundong_fen: 滚动/弹性预算额；null = 未提供（基准退化用初始预算）。
 *      shiji_fen:   实际发生额，非负整数分。
 */
export interface ChayiShuru {
  readonly qijian: string
  readonly kemu: string
  readonly fangxiang: string
  readonly chushi_fen: number
  readonly gundong_fen: number | null
  readonly shiji_fen: number
}

/** 差异项输出：输入三数 + 五项计算结果（一个指标一个期间一行）。 */
export interface ChayiXiang {
  readonly qijian: string
  readonly kemu: string
  readonly fangxiang: string
  readonly chushi_fen: number // 初始预算额（分）——三重对比第一列
  readonly gundong_fen: number | null // 滚动预算额（分）——第二列（null 同固定）
  readonly shiji_fen: number // 实际额（分）——第三列
  readonly jizhun_fen: number // 基准额（分）= 滚动（缺省退化初始）
  readonly chae_fen: number // 差额（分）= 实际 − 基准（展示口径）
  readonly chalv_bps: number | null // 差异率（基点，非负；基准 0 → null）
  readonly fa: string // 'F' 有利 / 'A' 不利 / '—' 零差额
  readonly yujing: string // 档位名称（默认体系 '无'/'黄'/'红'/'—'；自定义档 = 用户命名）
  readonly yan_se: string // 本档颜色（自定义档位的展示层着色；'无'/'—' 为空）
}

/** 差异结果：全部差异项 + 合计差额 + 预警计数（看板/报告用）。
 *
 *  字段说明：
 *      xiang:         逐项差异（顺序与输入一致）。
 *      heji_chae_fen: 合计差额 = Σ差额（展示口径）。
 *      heji_fa:       合计判定——全部行同方向时按该方向判 F/A，
 *                     方向混合或零差额时 '—'（合计的意义见口径说明）。
 *      hong_shu / huang_shu / wu_shu / wufa_shu: 四档预警计数。
 *      dang_tongji:   档名 → 行数（含'无'/'—'）——自定义档位时的通用计数
 *                     （hong/huang_shu 只认默认档名，自定义档名时请读本字段）。
 */
export interface ChayiJieguo {
  readonly xiang: ChayiXiang[]
  readonly heji_chae_fen: number
  readonly heji_fa: string
  readonly hong_shu: number
  readonly huang_shu: number
  readonly wu_shu: number
  readonly wufa_shu: number
  readonly dang_tongji: Record<string, number>
}

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

/** isinstance(tiao, ChayiShuru) 的鸭子对应：结构含全部六键即可进入逐字段校验。 */
function _shi_chayi_shuru(x: unknown): boolean {
  return (
    typeof x === 'object' &&
    x !== null &&
    'qijian' in x &&
    'kemu' in x &&
    'fangxiang' in x &&
    'chushi_fen' in x &&
    'gundong_fen' in x &&
    'shiji_fen' in x
  )
}

/** isinstance(dang, YujingDang) 的鸭子对应：结构含三键即可进入逐字段校验。 */
function _shi_yujing_dang(x: unknown): boolean {
  return typeof x === 'object' && x !== null && 'ming_cheng' in x && 'yan_se' in x && 'yu_fen' in x
}

/** 金额校验：非负整数且不超上限（bool 排除——True 也是 int 子类）。 */
function _jianyan_jine(shuzhi: unknown, biaoshi: string): void {
  if (typeof shuzhi !== 'number' || !Number.isInteger(shuzhi)) {
    throw new ChayiCuowu(`${biaoshi} 必须为整数（分）：${_repr(shuzhi)}`)
  }
  if (shuzhi < 0 || shuzhi > ZUIDA_JINE_FEN) {
    throw new ChayiCuowu(`${biaoshi} 必须在 [0, ${ZUIDA_JINE_FEN}] 内（分）：${shuzhi}`)
  }
}

/** 差异率（基点）= |差额|/基准 × 10000，half-up 整数实现。
 *
 *  基准为 0 → null（无法定义；预警将记 '—' 交人工——见模块头口径说明）。
 *  实现说明：Python 原式 (a*10000 + j//2) // j 即整数 half-up，全程无浮点；
 *  TS 侧走公共库 bili_bps_ban_jian（半分母变体）逐式对应，杜绝 2^53 溢出。 */
function _jisuan_chalv(chae_fen: number, jizhun_fen: number): number | null {
  if (jizhun_fen === 0) {
    return null
  }
  return bili_bps_ban_jian(Math.abs(chae_fen), jizhun_fen)
}

/** 按方向判 F/A：成本类正差=超支 A、收入类正差=超额 F；零差 '—'。 */
function _pan_fa(chae_fen: number, fangxiang: string): string {
  if (chae_fen === 0) {
    return '—'
  }
  if (fangxiang === FANGXIANG_CHENGBEN) {
    return chae_fen > 0 ? 'A' : 'F' // 成本：正=超支(不利)
  }
  return chae_fen > 0 ? 'F' : 'A' // 收入：正=超额(有利)
}

/** 按档位序列定级：从阈值最高的档往下找第一个达标的，返回（档名, 颜色）。
 *
 *  |差异率| ≥ 档阈值即落入；全部不达 → ('无', '')；无法定级 → ('—', '')。
 *  调用方保证 dang_lie 已通过 _jianyan_dang_lie 校验（阈值非负、档名合法）。
 *  排序稳定性：JS sort 稳定且等值保持原序，与 Python sorted(reverse=True) 一致。 */
function _pei_dang(chalv_bps: number | null, dang_lie: readonly YujingDang[]): readonly [string, string] {
  if (chalv_bps === null) {
    return [YUJING_WUFA, '']
  }
  const jian_xu = [...dang_lie].sort((a, b) => b.yu_fen - a.yu_fen) // 阈值降序
  for (const dang of jian_xu) {
    if (chalv_bps >= dang.yu_fen) {
      return [dang.ming_cheng, dang.yan_se]
    }
  }
  return [YUJING_WU, '']
}

/** 默认体系的预警档名（向后兼容的薄壳——等价于默认档位下的 _pei_dang）。 */
export function _pan_yujing(chalv_bps: number | null): string {
  return _pei_dang(chalv_bps, MOREN_DANG_LIE)[0]
}

/** 校验一份档位配置（结构/阈值/档名），返回规整后的数组。
 *
 *  Python 版先 isinstance(YujingDang) 包单档、再 tuple(dang_lie)（TypeError →
 *  '必须为 YujingDang 序列'）；TS 侧以鸭子判定覆盖同批错误路径。 */
function _jianyan_dang_lie(dang_lie: readonly YujingDang[] | YujingDang, can_ming: string): readonly YujingDang[] {
  if (!Array.isArray(dang_lie) && (typeof dang_lie !== 'object' || dang_lie === null)) {
    // 对应 Python tuple(dang_lie) 的 TypeError 路径
    throw new ChayiCuowu(`${can_ming} 必须为 YujingDang 序列`)
  }
  const lie = (Array.isArray(dang_lie) ? dang_lie : [dang_lie]) as readonly unknown[]
  if (lie.length === 0) {
    throw new ChayiCuowu(`${can_ming} 不能为空（至少一个档位；不想预警请把阈值设为极高）`)
  }
  const ming_ji = new Set<string>()
  for (const yuan of lie) {
    if (!_shi_yujing_dang(yuan)) {
      throw new ChayiCuowu(`${can_ming} 含非法元素（须为 YujingDang）：${_repr(yuan)}`)
    }
    const dang = yuan as YujingDang
    if (dang.ming_cheng === '' || dang.ming_cheng.trim() === '') {
      throw new ChayiCuowu(`${can_ming} 存在空档名`)
    }
    if (dang.ming_cheng === YUJING_WU || dang.ming_cheng === YUJING_WUFA) {
      throw new ChayiCuowu(`${can_ming} 档名 '${dang.ming_cheng}' 为保留名（不可用作自定义档名）`)
    }
    if (ming_ji.has(dang.ming_cheng)) {
      throw new ChayiCuowu(`${can_ming} 档名重复：${dang.ming_cheng}`)
    }
    ming_ji.add(dang.ming_cheng)
    if (!Number.isInteger(dang.yu_fen) || dang.yu_fen < 0) {
      throw new ChayiCuowu(`${can_ming} 档 '${dang.ming_cheng}' 阈值必须为非负整数基点`)
    }
    if (dang.yan_se === '') {
      throw new ChayiCuowu(`${can_ming} 档 '${dang.ming_cheng}' 颜色为空（可填与档名相同的中文色）`)
    }
  }
  return lie as readonly YujingDang[]
}

// ======================================================================
// 对外接口区（唯一的计算入口）
// ======================================================================

/** 三重对比差异计算 + 预警分级（方案B 步骤 3a/3b；纯函数）。
 *
 *  参数：shuru —— 每个指标每个期间一行 ChayiShuru（重复的
 *        （期间, 科目）组合会被拒绝——防双计）。
 *        dang_lie —— 默认预警档位（全部科目生效；缺省 = 定稿 #3 体系
 *        '红'≥红阈 / '黄'≥黄阈）。每档 = YujingDang(名称, 颜色, 阈值基点)，
 *        档数不限、阈值大小不限——用户自定义接口（也接受单个 YujingDang）。
 *        kemu_dang_lie —— 按科目覆盖档位：{科目名: 档位序列}；未覆盖的
 *        科目用 dang_lie。科目专属阈值/档数/颜色（如办公费设三档）在此配。
 *
 *  返回：ChayiJieguo（逐项 + 合计 + 预警计数 + 全档计数 dang_tongji）。
 *
 *  兼容性注意（下游消费方必读）：ChayiXiang.yujing = 档位名称。自定义档名时
 *  下游按 '红'/'黄' 字面过滤的链路（xishu 系数包 / zhenggai 分级 / kanban）
 *  将匹配不到——自定义请保留最高档名为 '红'、次档为 '黄'，或自行适配下游。
 *
 *  计算规则（口径全部见模块头注释，此处只列顺序）：
 *      ① 校验（输入 + 档位配置） → ② 定基准（滚动优先，缺省退化初始） →
 *      ③ 差额（实际−基准） → ④ 差异率（half-up 基点） →
 *      ⑤ F/A（按方向） → ⑥ 预警（按科目档位，从高到低匹配） → ⑦ 合计与计数。
 */
export function jisuan_chayi(
  shuru: readonly ChayiShuru[],
  dang_lie: readonly YujingDang[] | YujingDang = MOREN_DANG_LIE,
  kemu_dang_lie: Record<string, readonly YujingDang[] | YujingDang> | null = null,
): ChayiJieguo {
  if (!Array.isArray(shuru) || shuru.length === 0) {
    throw new ChayiCuowu('shuru 必须为非空列表（至少一行差异输入）')
  }
  const mo_ren = _jianyan_dang_lie(dang_lie, 'dang_lie')
  const kemu_dang: Record<string, readonly YujingDang[]> = {}
  // Python `if kemu_dang_lie:`（None/空字典均跳过）；非字典且有内容 → 报错
  if (kemu_dang_lie != null && typeof kemu_dang_lie === 'object') {
    const shi_zidian = !Array.isArray(kemu_dang_lie)
    const you_nei_rong = shi_zidian
      ? Object.keys(kemu_dang_lie).length > 0
      : (kemu_dang_lie as readonly unknown[]).length > 0
    if (you_nei_rong && !shi_zidian) {
      throw new ChayiCuowu('kemu_dang_lie 必须为 {科目名: 档位序列} 字典')
    }
    if (shi_zidian) {
      for (const [kemu, lie] of Object.entries(kemu_dang_lie)) {
        kemu_dang[kemu] = _jianyan_dang_lie(lie, `kemu_dang_lie[${kemu}]`)
      }
    }
  }

  const yijian = new Set<string>() // （期间, 科目）去重键（tuple 的无碰撞编码）
  const xiang_lie: ChayiXiang[] = []
  for (const yuan of shuru) {
    if (!_shi_chayi_shuru(yuan)) {
      throw new ChayiCuowu(`输入含非法元素（须为 ChayiShuru）：${_repr(yuan)}`)
    }
    const tiao = yuan as ChayiShuru
    if (!tiao.qijian || !tiao.kemu) {
      throw new ChayiCuowu('期间与科目必须非空')
    }
    if (tiao.fangxiang !== FANGXIANG_CHENGBEN && tiao.fangxiang !== FANGXIANG_SHOURU) {
      // 报错中的合法方向列表与 Python list(HEFA_FANGXIANG) 的 repr 同形
      throw new ChayiCuowu(`方向非法：${tiao.fangxiang}（应为 [${HEFA_FANGXIANG.map((f) => `'${f}'`).join(', ')}]）`)
    }
    _jianyan_jine(tiao.chushi_fen, 'chushi_fen')
    _jianyan_jine(tiao.shiji_fen, 'shiji_fen')
    if (tiao.gundong_fen != null) {
      _jianyan_jine(tiao.gundong_fen, 'gundong_fen')
    }
    // （期间, 科目）唯一：同一指标同一期间只允许一行，防双计
    const jian = `${tiao.qijian}\u0000${tiao.kemu}`
    if (yijian.has(jian)) {
      // 报错格式与 Python tuple repr (('2026-01', 'x')) 同形
      throw new ChayiCuowu(`差异输入重复（期间+科目）：('${tiao.qijian}', '${tiao.kemu}')`)
    }
    yijian.add(jian)

    // ② 基准：滚动预算优先；null → 退化初始（固定）预算
    const jizhun = tiao.gundong_fen != null ? tiao.gundong_fen : tiao.chushi_fen
    const chae = tiao.shiji_fen - jizhun // ③ 差额（展示口径）
    const chalv = _jisuan_chalv(chae, jizhun) // ④ 差异率（基点）
    const ben_ke_mu_dang = kemu_dang[tiao.kemu] ?? mo_ren // ⑥ 科目专属档位优先
    const [yujing, yan_se] = _pei_dang(chalv, ben_ke_mu_dang)
    xiang_lie.push({
      qijian: tiao.qijian,
      kemu: tiao.kemu,
      fangxiang: tiao.fangxiang,
      chushi_fen: tiao.chushi_fen,
      gundong_fen: tiao.gundong_fen,
      shiji_fen: tiao.shiji_fen,
      jizhun_fen: jizhun,
      chae_fen: chae,
      chalv_bps: chalv,
      fa: _pan_fa(chae, tiao.fangxiang),
      yujing,
      yan_se,
    })
  }

  // ⑦ 合计差额与合计判定（方向全部一致才有合计 F/A 意义）
  const heji_chae = xiang_lie.reduce((he, x) => he + x.chae_fen, 0)
  const fangxiang_ji = new Set(xiang_lie.map((x) => x.fangxiang))
  let heji_fa: string
  if (fangxiang_ji.size === 1) {
    heji_fa = _pan_fa(heji_chae, xiang_lie[0]!.fangxiang) // 唯一方向（pop() 的等价读法）
  } else {
    heji_fa = '—' // 成本/收入混算的合计 F/A 无意义，交人看明细
  }

  const dang_tongji: Record<string, number> = {}
  for (const ming of new Set(xiang_lie.map((x) => x.yujing))) {
    dang_tongji[ming] = xiang_lie.filter((x) => x.yujing === ming).length
  }

  return {
    xiang: xiang_lie,
    heji_chae_fen: heji_chae,
    heji_fa,
    hong_shu: xiang_lie.filter((x) => x.yujing === YUJING_HONG).length,
    huang_shu: xiang_lie.filter((x) => x.yujing === YUJING_HUANG).length,
    wu_shu: xiang_lie.filter((x) => x.yujing === YUJING_WU).length,
    wufa_shu: xiang_lie.filter((x) => x.yujing === YUJING_WUFA).length,
    dang_tongji,
  }
}
