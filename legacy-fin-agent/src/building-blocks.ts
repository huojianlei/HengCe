// ======================================================================
// 积木四模块聚合（方案B 步骤 5a）—— 种子文件：常量区 + 默认映射
// ======================================================================
// 由主控预置（2026-09-05）：zhenggai 模块静态依赖 yingshe_mokuai，
// 为解除并行转写的文件竞态，先把「常量 + 默认映射」落盘；
// 转写批次须在此文件上【扩展】（保留既有导出逐字不动），追加数据结构、
// chai_jimu 主函数、适配器与内部工具。
//
// 权威依据：D:\AppProject\algo\building_blocks.py（Python 版为唯一行为准绳）
// ======================================================================

// ----------------------------------------------------------------------
// 常量区（与 Python 逐字一致）
// ----------------------------------------------------------------------

/** 收入模块（科目关键词映射的模块名） */
export const MOKUAI_SHOURU = '收入模块'
/** 成本模块 */
export const MOKUAI_CHENGBEN = '成本模块'
/** 费用模块 */
export const MOKUAI_FEIYONG = '费用模块'
/** 采购模块 */
export const MOKUAI_CAIGOU = '采购模块'

/** 四模块权威顺序（T-21 拍板：人力并入成本，故只有四模块） */
export const MOKUAI_SHUNXU: readonly string[] = [
  MOKUAI_SHOURU, MOKUAI_CHENGBEN, MOKUAI_FEIYONG, MOKUAI_CAIGOU,
]

/** 采购模块关键词（先匹配——'材料价格' 必须先于成本模块的 '材料' 命中） */
export const CAIGOU_GUANJIANZI: readonly string[] = [
  '采购', '供应商', '议价', '物流', '材料价格',
]

/** 成本模块关键词（通用兜底，可控成本等；采购成本已被采购模块先命中） */
export const CHENGBEN_GUANJIANZI: readonly string[] = [
  '制造费用', '生产成本', '材料', '人工', '人力', '薪酬',
  '工时', '闲置', '电力', '水电', '燃料', '动力', '维修', '折旧',
  '成本',
]

/** 费用模块关键词（期间费用；'销售费' 排在收入模块 '销售' 之前——顺序保证） */
export const FEIYONG_GUANJIANZI: readonly string[] = [
  '费用', '期间', '管理费', '销售费', '财务费', '办公费',
]

/** 收入模块关键词 */
export const SHOURU_GUANJIANZI: readonly string[] = [
  '收入', '营收', '销量', '销售', '毛利', '利润', '净利', '收益', '价格',
]

// ----------------------------------------------------------------------
// 默认科目 → 模块映射
// ----------------------------------------------------------------------

/**
 * 默认科目→模块映射（关键词匹配，先命中先得）。
 *
 * 匹配顺序即四组关键词的注册顺序：采购 → 成本 → 费用 → 收入。
 * 顺序刻意如此：'材料价格' 必须在 '材料' 之前（否则材料价格差异会
 * 误入成本模块）；'销售费' 必须在 '销售' 之前（否则销售费用会误入
 * 收入模块）。不命中任何关键词 → null（未归属，交人工补映射）。
 */
export function yingshe_mokuai(kemu: string): string | null {
  const zu_he: ReadonlyArray<readonly [string, readonly string[]]> = [
    [MOKUAI_CAIGOU, CAIGOU_GUANJIANZI],
    [MOKUAI_CHENGBEN, CHENGBEN_GUANJIANZI],
    [MOKUAI_FEIYONG, FEIYONG_GUANJIANZI],
    [MOKUAI_SHOURU, SHOURU_GUANJIANZI],
  ]
  for (const [mokuai, guanjianzi] of zu_he) {
    if (guanjianzi.some((zi) => kemu.includes(zi))) {
      return mokuai
    }
  }
  return null
}

// ======================================================================
// 批次D 转写扩展区（2026-09-05）——在种子之上追加，既有导出逐字未动
// ======================================================================
//
// 转写自 D:\AppProject\algo\building_blocks.py（Python 版为唯一行为准绳；
// 对应测试 algo/tests/test_building_blocks.py → 本插件 tests/building-blocks.test.ts）。
//
// 模块定位：本模块是【聚合层】——吃 variance 的逐科目差异行（展示口径差额，
//     已带 F/A 与预警），按"科目→模块"映射聚合成四模块差异额/占比/高亮，
//     输出模块溯源明细。本模块【不重算】任何微观差异公式（MPV/MUV/LRV/LEV
//     已在 planning_operational 覆盖）——四模块口径因此统一为"展示口径差额
//     聚合"，无自定义公式、无重复计算，天然满足 T-05/T-21。
//
// 三个口径决策点（2026-08-23 用户批准按建议默认值落地）：
//     D1 采购模块 = 采购类科目的展示口径差额聚合（默认关键词映射判定，
//         自定义映射优先——返回非法模块名时该行进未归属，不发明任何公式）；
//     D2 占比分母 = Σ|各模块净差额| + |未归属净差额|（"各桶净差额"绝对值
//         合计，F/A 正负分列）——占比合计恒为 10000 基点（不变量）；模块内部
//         F/A 冲抵只反映在净差额里（行级 |差额| 不进分母），行级明细可下钻；
//         净总差异另列（避免正负抵消导致占比失真）；
//     D3 核心问题模块 = 不利（A）模块中 |差额| 最大者；全部有利时 null
//         （展示层显示"无"）；并列时取四模块顺序靠前者。
//
// 符号口径（定稿 §0.5）：差额 = 实际 − 基准（展示口径）；F/A 是唯一真源。
//     模块级 F/A 按模块方向从差额符号推得（与 variance 同规则）：
//         收入模块：正 = 超额 = F；负 = 未达标 = A；
//         成本/费用/采购模块：正 = 超支 = A；负 = 节约 = F；零 = '—'。
//     【行级 fa 不被信任】：模块级 F/A 只看净差额符号——行级 fa/yujing 仅随
//     明细透传（上游字段被污染也不影响模块判定，测试有专例锁定）。
//
// 数值纪律：金额 = 整数分；占比 = 整数基点（1% = 100 基点），half-up 整数
//     舍入；全程整数运算零浮点——占比除法走公共库 bili_bps（BigInt 半进位，
//     与 Python 原式 (2×|净|×10000 + 分母) // (2×分母) 逐式对应）；纯函数
//     （无 I/O、无全局状态）。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     JimuHang            积木输入行（一个科目一行的展示口径差额）
//     MokuaiXiang         模块项（一个模块的聚合结果 + 溯源明细）
//     JimuJieguo          积木结果（四模块 + 未归属清单 + 合计/占比/高亮）
//     JimuCuowu           积木错误（校验失败异常）
//     chai_jimu           拆积木（主函数）
//     cong_chayi_xiang    从差异项转换（variance.ChayiXiang 的鸭子类型适配器）
//     chae_fen            差额（分，展示口径，可负可零）
//     zhanbi_bps          占比（基点，非负；分母为 0 时 null）
//     jing_heji_fen       净总差异（Σ全部行差额，含未归属）
//     zhanbi_fenmu_fen    占比分母（分）= Σ|各模块净差额| + |未归属净差额|
//     hexin_mokuai        核心问题模块（不利模块中 |差额| 最大者；无则 null）
//     weiguishu_*         未归属（科目映射不中的行——不静默丢弃）
//
// 与上下游的关系：
//     上游：variance（步骤 3a/3b 逐科目差异行——经 cong_chayi_xiang 适配）；
//     下游：看板（步骤 7 积木差异占比饼图/核心问题模块高亮）、
//           BSC（步骤 5b 双模型并列）、整改方案（步骤 8 按模块定责）。

import { bili_bps } from './int-math.ts'

// ----------------------------------------------------------------------
// 常量补充区（校验口径，与 Python 逐字一致）
// ----------------------------------------------------------------------

/** F/A 合法取值（'—' 表示零差额） */
export const HEFA_FA: readonly string[] = ['F', 'A', '—']

/** 预警合法取值（与 variance 三档 + 无法定级一致） */
export const HEFA_YUJING: readonly string[] = ['无', '黄', '红', '—']

/** 单行差额绝对值上限（分）——与 variance 同口径的合理性校验 */
export const ZUIDA_CHAE_FEN = 9 * 10 ** 11

/** 积木输入校验失败（空输入 / 非法字段 / 重复行）。
 *
 *  Python 继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）；
 *  TS 侧按插件约定统一 extends Error，中文报错文案与 Python 逐字一致。 */
export class JimuCuowu extends Error {}

// ----------------------------------------------------------------------
// 数据结构区（frozen dataclass → readonly interface + 对象字面量，不写工厂类）
// ----------------------------------------------------------------------

/** 积木输入行：一个科目（一行）的展示口径差额（variance 产物的精简形态）。
 *
 *  字段说明：
 *      qijian:      期间键（2026-01 / 2026-Q1；透传，本模块不解析语义）。
 *      kemu:        科目名（映射到四模块的依据；关键词不中 → 未归属）。
 *      chae_fen:    差额（分）= 实际 − 基准（展示口径，可负可零）。
 *      fa:          行级 F/A（来自 variance 唯一真源；仅随明细透传，
 *                   模块级 F/A 按方向规则重推——不信任行级值）。
 *      yujing:      预警（'无' / '黄' / '红' / '—'，随明细透传）。
 *      chalv_bps:   差异率（基点，非负；null 表示无法定级）。
 */
export interface JimuHang {
  readonly qijian: string
  readonly kemu: string
  readonly chae_fen: number
  readonly fa: string
  readonly yujing: string
  readonly chalv_bps: number | null
}

/** 模块项：一个模块的聚合结果 + 溯源明细（看板饼图/定责的数据源）。
 *
 *  字段说明：
 *      mokuai:      模块名（'收入模块' / '成本模块' / '费用模块' / '采购模块'）。
 *      chae_fen:    模块差异额 = Σ该模块各行差额（展示口径净额）。
 *      fa:          模块级 F/A——按模块方向从差额符号推得（见扩展区头规则）。
 *      zhanbi_bps:  占比（基点）= |chae_fen| ÷ 占比分母 × 10000，half-up；
 *                   分母为 0 时 null（无法定义，交人工）。
 *      hang_shu:    归属行数（明细行数，便于看板下钻）。
 *      mingxi:      归属的输入行列表（溯源明细，顺序 = 输入顺序）。
 */
export interface MokuaiXiang {
  readonly mokuai: string
  readonly chae_fen: number
  readonly fa: string
  readonly zhanbi_bps: number | null
  readonly hang_shu: number
  readonly mingxi: readonly JimuHang[]
}

/** 积木拆解总结果（四模块 + 未归属 + 合计 + 高亮）。
 *
 *  字段说明：
 *      mokuai_lie:         四模块结果（顺序固定 = MOKUAI_SHUNXU）。
 *      weiguishu_lie:      未归属行（科目映射不中——不静默丢弃，交人工补映射）。
 *      jing_heji_fen:      净总差异 = Σ全部行差额（含未归属；正负可抵消）。
 *      zhanbi_fenmu_fen:   占比分母（分）= Σ|各模块净差额| + |未归属净差额|
 *                          （D2 口径：占比合计恒为 10000 基点；为 0 时
 *                          各占比为 null，交人工）。
 *      hexin_mokuai:       核心问题模块名（不利模块中 |差额| 最大者；
 *                          全部有利/零差额时 null）。
 *      weiguishu_zhanbi_bps: 未归属占比（基点）= |未归属净差额| ÷ 占比分母。
 */
export interface JimuJieguo {
  readonly mokuai_lie: readonly MokuaiXiang[]
  readonly weiguishu_lie: readonly JimuHang[]
  readonly jing_heji_fen: number
  readonly zhanbi_fenmu_fen: number
  readonly hexin_mokuai: string | null
  readonly weiguishu_zhanbi_bps: number | null
}

// ----------------------------------------------------------------------
// 适配器区（variance → 本模块输入；契约式接线，刻意不 import variance）
// ----------------------------------------------------------------------

/** variance.ChayiXiang 的最小结构形状（鸭子类型）。
 *
 *  只要对象带有 qijian/kemu/chae_fen/fa/yujing/chalv_bps 六个同名属性即可——
 *  字段名与 variance 导出的 ChayiXiang 逐字一致，模块间保持低耦合。 */
export interface ChayiXiangYang {
  readonly qijian: string
  readonly kemu: string
  readonly chae_fen: number
  readonly fa: string
  readonly yujing: string
  readonly chalv_bps: number | null
}

/** 适配器：把 variance.ChayiXiang（鸭子类型）转成本模块输入行。
 *
 *  刻意不 import variance——只依赖上面的最小结构形状（契约式接线）；
 *  六字段逐一透传，不做任何重算。 */
export function cong_chayi_xiang(xiang: ChayiXiangYang): JimuHang {
  return {
    qijian: xiang.qijian,
    kemu: xiang.kemu,
    chae_fen: xiang.chae_fen,
    fa: xiang.fa,
    yujing: xiang.yujing,
    chalv_bps: xiang.chalv_bps,
  }
}

// ----------------------------------------------------------------------
// 内部工具函数区
// ----------------------------------------------------------------------

/** 未知值的简短展示（报错文案用；对象/字符串走 JSON，其余 String()）。 */
function _repr(x: unknown): string {
  if (typeof x === 'string') return JSON.stringify(x)
  if (typeof x === 'object' && x !== null) return JSON.stringify(x)
  return String(x)
}

/** 鸭子判定：是否具备 JimuHang 的六个字段（对应 Python isinstance 检查）。 */
function _shi_jimu_hang(x: unknown): boolean {
  return (
    typeof x === 'object' &&
    x !== null &&
    'qijian' in x &&
    'kemu' in x &&
    'chae_fen' in x &&
    'fa' in x &&
    'yujing' in x &&
    'chalv_bps' in x
  )
}

/** 占比（基点）= |差额| ÷ 分母 × 10000，half-up 整数实现。
 *
 *  分母为 0 → null（占比无法定义——与 variance 差异率的除零纪律一致，
 *  交人工）；实现走公共库 bili_bps（BigInt 半进位）：
 *      (2×|差额|×10000 + 分母) // (2×分母) 即整数 half-up，全程无浮点。
 */
export function _zhanbi_bps(chae_fen: number, fenmu: number): number | null {
  if (fenmu === 0) {
    return null
  }
  return bili_bps(Math.abs(chae_fen), fenmu)
}

/** 模块级 F/A：按模块方向从差额符号推得（定稿 §0.5 方向规则）。
 *
 *  收入模块：正 = 超额 = F、负 = 未达标 = A；
 *  成本/费用/采购模块：正 = 超支 = A、负 = 节约 = F；零 = '—'。
 */
export function _pan_mokuai_fa(chae_fen: number, mokuai: string): string {
  if (chae_fen === 0) {
    return '—'
  }
  if (mokuai === MOKUAI_SHOURU) {
    return chae_fen > 0 ? 'F' : 'A'
  }
  return chae_fen > 0 ? 'A' : 'F'
}

// ----------------------------------------------------------------------
// 对外接口区（唯一的计算入口）
// ----------------------------------------------------------------------

/** 四模块聚合拆解（方案B 步骤 5a；纯函数）。
 *
 *  参数：
 *      shuru —— 每行一个科目的展示口径差额（JimuHang 列表，须非空）；
 *      zidingyi_yingshe —— 可选自定义映射（函数：科目名 → 模块名或
 *          null）。返回非 null 时覆盖默认映射（返回值不在四模块内时该行
 *          进未归属——宁可交人工，也不猜测归属）；返回 null 时回落默认。
 *          典型用法（T-24 科目唯一编码落地后）：按编码字典映射。
 *
 *  返回：JimuJieguo（四模块 + 未归属清单 + 净合计 + 占比 + 高亮）。
 *
 *  处理顺序：
 *      ① 校验（行类型/字段/重复键）→ ② 映射科目（自定义优先，默认兜底）
 *      → ③ 按模块聚合差额与明细 → ④ 模块 F/A → ⑤ 占比（分母 = Σ|模块净|+
 *      |未归属净|，D2 口径）→ ⑥ 净合计与核心问题模块高亮。
 */
export function chai_jimu(
  shuru: readonly JimuHang[],
  zidingyi_yingshe: ((kemu: string) => string | null) | null = null,
): JimuJieguo {
  if (!Array.isArray(shuru) || shuru.length === 0) {
    throw new JimuCuowu('shuru 必须为非空列表（至少一行差异输入）')
  }

  // ① 校验 + （期间, 科目）去重键——同一科目同一期间只允许一行，防双计
  const yijian = new Set<string>()
  const jianyan_hou: JimuHang[] = []
  for (const yuan of shuru) {
    if (!_shi_jimu_hang(yuan)) {
      throw new JimuCuowu(`输入含非法元素（须为 JimuHang）：${_repr(yuan)}`)
    }
    const tiao = yuan as JimuHang
    if (!tiao.kemu || !tiao.qijian) {
      throw new JimuCuowu('科目与期间必须非空')
    }
    if (typeof tiao.chae_fen === 'boolean' || !Number.isInteger(tiao.chae_fen)) {
      throw new JimuCuowu(`chae_fen 必须为整数（分）：${_repr(tiao.chae_fen)}`)
    }
    if (Math.abs(tiao.chae_fen) > ZUIDA_CHAE_FEN) {
      throw new JimuCuowu(`chae_fen 超出合理范围（分）：${tiao.chae_fen}`)
    }
    if (!HEFA_FA.includes(tiao.fa)) {
      // 合法值列表展示与 Python list(HEFA_FA) 的 repr 同形（['F', 'A', '—']）
      throw new JimuCuowu(`fa 非法：${tiao.fa}（应为 [${HEFA_FA.map((f) => `'${f}'`).join(', ')}]）`)
    }
    if (!HEFA_YUJING.includes(tiao.yujing)) {
      throw new JimuCuowu(`yujing 非法：${tiao.yujing}（应为 [${HEFA_YUJING.map((f) => `'${f}'`).join(', ')}]）`)
    }
    if (
      tiao.chalv_bps !== null &&
      (typeof tiao.chalv_bps === 'boolean' || !Number.isInteger(tiao.chalv_bps) || tiao.chalv_bps < 0)
    ) {
      throw new JimuCuowu(`chalv_bps 非法：${_repr(tiao.chalv_bps)}（None 或非负整数）`)
    }
    // （期间, 科目）去重键（tuple 的无碰撞编码，与 variance 同写法）
    const jian = `${tiao.qijian}\u0000${tiao.kemu}`
    if (yijian.has(jian)) {
      // 报错格式与 Python tuple repr (('2026-Q1', '营收')) 同形
      throw new JimuCuowu(`差异输入重复（期间+科目）：('${tiao.qijian}', '${tiao.kemu}')——防双计`)
    }
    yijian.add(jian)
    jianyan_hou.push(tiao)
  }

  // ② 归属判定：自定义映射优先（返回非 null 即采用），否则默认关键词映射
  const guishu = (tiao: JimuHang): string | null => {
    if (zidingyi_yingshe !== null) {
      const zhi = zidingyi_yingshe(tiao.kemu)
      if (zhi != null) {
        return zhi
      }
    }
    return yingshe_mokuai(tiao.kemu)
  }

  const fen_zu = new Map<string, JimuHang[]>()
  for (const mokuai of MOKUAI_SHUNXU) {
    fen_zu.set(mokuai, [])
  }
  const weiguishu: JimuHang[] = []
  for (const tiao of jianyan_hou) {
    const mokuai = guishu(tiao)
    const tong = mokuai !== null ? fen_zu.get(mokuai) : undefined
    if (tong !== undefined) {
      tong.push(tiao)
    } else {
      // 不静默丢弃：映射不中的行进"未归属"清单，交人工补映射（D1 兜底）
      weiguishu.push(tiao)
    }
  }

  // ③ 聚合（顺序固定 = MOKUAI_SHUNXU）；模块 F/A 由差额符号推得；
  //    占比需等分母算出后统一回填（先占位 null）
  const mokuai_lie: MokuaiXiang[] = []
  for (const mokuai of MOKUAI_SHUNXU) {
    const hang_lie = fen_zu.get(mokuai)!
    const chae = hang_lie.reduce((he, t) => he + t.chae_fen, 0)
    mokuai_lie.push({
      mokuai,
      chae_fen: chae,
      fa: _pan_mokuai_fa(chae, mokuai),
      zhanbi_bps: null, // 分母算出后回填
      hang_shu: hang_lie.length,
      mingxi: hang_lie,
    })
  }

  // ⑤ 占比分母（D2 口径）：Σ|各模块净差额| + |未归属净差额|——
  //    保证占比合计恒为 10000 基点（随机检验 P2 的数学基础）
  const weiguishu_jing = weiguishu.reduce((he, t) => he + t.chae_fen, 0)
  const fenmu = mokuai_lie.reduce((he, x) => he + Math.abs(x.chae_fen), 0) + Math.abs(weiguishu_jing)

  // 回填占比（Python dataclass 冻结——重建列表回填，保持输出不可变）
  const mokuai_lie_huitian: MokuaiXiang[] = mokuai_lie.map((x) => ({
    mokuai: x.mokuai,
    chae_fen: x.chae_fen,
    fa: x.fa,
    zhanbi_bps: _zhanbi_bps(x.chae_fen, fenmu),
    hang_shu: x.hang_shu,
    mingxi: x.mingxi,
  }))
  const weiguishu_zhanbi = _zhanbi_bps(weiguishu_jing, fenmu)

  // ⑥ 净总差异（全部行，含未归属——正负可抵消，另列不与占比混用）
  const jing_heji = jianyan_hou.reduce((he, t) => he + t.chae_fen, 0)

  // 核心问题模块：不利（A）模块中 |差额| 最大者；并列取顺序靠前者（D3）
  // （遍历即 MOKUAI_SHUNXU 顺序，"严格大于"保证并列时先到先得）
  let hexin: MokuaiXiang | null = null
  for (const x of mokuai_lie_huitian) {
    if (x.fa === 'A' && (hexin === null || Math.abs(x.chae_fen) > Math.abs(hexin.chae_fen))) {
      hexin = x
    }
  }

  return {
    mokuai_lie: mokuai_lie_huitian,
    weiguishu_lie: weiguishu,
    jing_heji_fen: jing_heji,
    zhanbi_fenmu_fen: fenmu,
    hexin_mokuai: hexin !== null ? hexin.mokuai : null,
    weiguishu_zhanbi_bps: weiguishu_zhanbi,
  }
}
