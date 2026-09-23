// ======================================================================
// 平衡计分卡 BSC 四维评分 —— 方案B 步骤 5b 的【加权评分】确定性核心
// ======================================================================
//
// 转写自 D:\AppProject\algo\bsc.py（Python 版为唯一行为准绳；
// 拼音标识符逐字保留，期望值以 algo/tests/test_bsc.py 为准，
// 对应本插件 tests/bsc.test.ts，测试数字逐字对应）。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
//     专有缩写可保留（BSC、KPI 等）。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/textbook/finagent-算法核对文档-定稿.md v2.1 §6（加权评分 + 例题）
//     docs/proposal-full-extract.txt 行 69~71（完整版：折算规则/权重标准/等级体系）
//     TODO.md T-05（队友拍板 2026-08-23：**BSC 不封顶**——favorable 即实际超预算
//         保留得分并鼓励持续，佐证 = ACCA-PM 讲义 P234-238）
//     01-需求说明 v2.0 FR-9（P0；权重默认 40/30/20/10；不封顶；五档等级）
//
// 四个维度（完整版权重标准，竞赛通用专业配比）：
//     财务 40%（caijing）/ 客户 30%（kehu）/ 内部流程 20%（neibu）/
//     学习成长 10%（xuexi）；权重可人工自定义微调，**合计必须 = 100%**。
//
// 计算公式（定稿 §6 + 完整版 §2.3.2，全部整数化）：
//     维度得分 = 该维度 KPI 达成率 × 100（达成率输入 = 整数基点，
//         10000 基点 = 100%）——half-up 舍入为整数分；
//     总分 = Σ（权重% × 维度得分）÷ 100——half-up 舍入为整数分；
//     等级 = 总分五档：90~100 优秀 / 80~89 良好 / 70~79 合格 /
//         60~69 预警 / 60 以下 严重不合格。
//
// 【不封顶口径（T-05 拍板，答辩要点）】：
//     达成率 > 100% 时维度得分 > 100 原样保留、不裁剪到 100——超预算完成
//     是 favorable，保留得分以鼓励持续（教材 PM 讲义 234-238 四维分类框架
//     与 142 页预算偏差可控性佐证）。注意：输入侧仍设合理性上限 1,000,000
//     基点（10,000%）——那是防脏数据的校验，不是得分封顶，两者不混淆。
//
// 数值纪律：达成率/权重 = 整数基点与整数百分比；得分/总分 = 整数分；
//     全程整数运算零浮点（half-up 用乘除实现，中间量最大 8×10^6，
//     远在 number 安全整数 2^53 之内，无需 BigInt 公共库）；纯函数
//     （无 I/O、无全局状态）。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     BscShuru            BSC 输入（四维 KPI 达成率 + 可选自定义权重）
//     BscJieguo           BSC 结果（四维得分 + 权重回显 + 总分 + 等级）
//     BscCuowu            BSC 错误（校验失败异常）
//     jisuan_bsc          计算 BSC（主函数）
//     QUANZHONG_MOREN     默认权重（40, 30, 20, 10）——完整版标准配比
//     caijing/kehu/neibu/xuexi_bps    财务/客户/内部流程/学习成长 达成率（基点）
//     caijing/kehu/neibu/xuexi_defen  四维得分（整数分，不封顶可 >100）
//     zongfen             总分（整数分，half-up）
//     dengji              等级（优秀/良好/合格/预警/严重不合格）
//
// 与上下游的关系：
//     上游：KPI 指标库（FR-11，随步骤 1b 数据入库刷新——定稿 §9 E1 修正）、
//           data_ingest（四类数据供 KPI 计算）；
//     下游：看板（步骤 7 BSC 四维得分雷达图）、整改方案（步骤 8 综合评级）。
//
// 建立：2026-08-23 ｜ TS 转写 2026-09-05
// ======================================================================

// ----------------------------------------------------------------------
// 常量区（数据值用中文——等级五档；权重为整数百分比）
// ----------------------------------------------------------------------

/** 四元组类型：权重/得分四维的定长数组（对应 Python tuple[int, int, int, int]） */
export type SiYuanzu = readonly [number, number, number, number]

/** 默认权重（财务, 客户, 内部流程, 学习成长）——完整版 §2.3.2 标准配比 */
export const QUANZHONG_MOREN: SiYuanzu = [40, 30, 20, 10]

/** 等级五档（完整版 §2.3.2：90-100 优秀 / 80-89 良好 / 70-79 合格 /
 *  60-69 预警 / 60 以下 严重不合格） */
export const DENGJI_YOUXIU = '优秀'
export const DENGJI_LIANGHAO = '良好'
export const DENGJI_HEGE = '合格'
export const DENGJI_YUJING = '预警'
export const DENGJI_YANZHONG = '严重不合格'

/** 等级判定表（阈值降序）——总分 >= 阈值即命中该档；全部不中 = 严重不合格 */
export const DENGJI_YUZHI: readonly [number, string][] = [
  [90, DENGJI_YOUXIU],
  [80, DENGJI_LIANGHAO],
  [70, DENGJI_HEGE],
  [60, DENGJI_YUJING],
]

/** 达成率合理性上限（基点）= 10,000%——防脏数据校验，**不是**得分封顶
 *  （不封顶口径见文件头：得分本身允许 >100） */
export const ZUIDA_DACHENGLV_BPS = 1_000_000

/** BSC 输入校验失败（达成率非法 / 权重非法）。
 *
 *  Python 继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）；
 *  TS 侧按插件约定统一 extends Error，中文报错文案与 Python 逐字一致。 */
export class BscCuowu extends Error {}

// ----------------------------------------------------------------------
// 数据结构区（frozen dataclass → readonly interface + 对象字面量，不写工厂类）
// ----------------------------------------------------------------------

/** BSC 输入：四维 KPI 达成率（基点）+ 可选自定义权重。
 *
 *  字段说明：
 *      caijing_bps:  财务维度 KPI 达成率（基点，10000 = 100%；非负整数）。
 *      kehu_bps:     客户维度 KPI 达成率（基点）。
 *      neibu_bps:    内部流程维度 KPI 达成率（基点）。
 *      xuexi_bps:    学习成长维度 KPI 达成率（基点）。
 *      quanzhong:    自定义权重（财务, 客户, 内部流程, 学习成长），
 *                    整数百分比、合计必须 = 100；null = 用默认 40/30/20/10。
 */
export interface BscShuru {
  readonly caijing_bps: number
  readonly kehu_bps: number
  readonly neibu_bps: number
  readonly xuexi_bps: number
  readonly quanzhong: SiYuanzu | null
}

/** BSC 结果：四维得分 + 权重回显 + 总分 + 等级（看板雷达图数据源）。
 *
 *  字段说明：
 *      caijing_defen / kehu_defen / neibu_defen / xuexi_defen:
 *          四维得分（整数分；不封顶——达成率 >100% 时得分 >100 保留）。
 *      quanzhong:  生效权重（默认或自定义，回显供报告展示）。
 *      zongfen:    总分 = Σ（权重 × 维度得分）÷ 100，half-up 整数。
 *      dengji:     等级（优秀/良好/合格/预警/严重不合格——按总分五档）。
 *      caijing_bps / kehu_bps / neibu_bps / xuexi_bps:
 *          四维达成率回显（基点）——得分溯源用（T-29#7）。
 */
export interface BscJieguo {
  readonly caijing_defen: number
  readonly kehu_defen: number
  readonly neibu_defen: number
  readonly xuexi_defen: number
  readonly quanzhong: SiYuanzu
  readonly zongfen: number
  readonly dengji: string
  readonly caijing_bps: number // 财务达成率回显（基点）——得分溯源用（T-29#7）
  readonly kehu_bps: number // 客户达成率回显（基点）
  readonly neibu_bps: number // 内部流程达成率回显（基点）
  readonly xuexi_bps: number // 学习成长达成率回显（基点）
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

/** 维度得分 = 达成率（基点）÷ 100，half-up 整数实现。
 *
 *  不封顶（T-05）：达成率 > 10000 基点时得分 > 100，原样保留。
 *  实现：(2×bps + 100) // 200 即 half-up（÷100 后四舍五入），全程无浮点
 *  （分子最大 2,000,100，number 精确表示，Math.floor 即整数地板除）。
 */
function _dacheng_bps_defen(bps: number): number {
  return Math.floor((bps * 2 + 100) / 200)
}

/** 总分 = Σ（权重% × 维度得分）÷ 100，half-up 整数实现。
 *
 *  实现：(2×Σ + 100) // 200 即 half-up（÷100 后四舍五入），全程无浮点
 *  （加权和最大 4×100×10000 = 4×10^6，number 精确表示）。
 */
function _zongfen(defen: SiYuanzu, quanzhong: SiYuanzu): number {
  let jiaquan_he = 0
  for (let i = 0; i < 4; i++) {
    jiaquan_he += quanzhong[i]! * defen[i]!
  }
  return Math.floor((jiaquan_he * 2 + 100) / 200)
}

/** 等级五档判定：按阈值降序查表，全部不中 = 严重不合格。 */
function _dengji(zongfen: number): string {
  for (const [yuzhi, mingcheng] of DENGJI_YUZHI) {
    if (zongfen >= yuzhi) {
      return mingcheng
    }
  }
  return DENGJI_YANZHONG
}

/** 达成率单项校验：非负整数、不超合理性上限（bool 是 int 子类须排除）。 */
function _jianyan_bps(bps: unknown, biaoshi: string): void {
  if (typeof bps === 'boolean' || !Number.isInteger(bps)) {
    throw new BscCuowu(`${biaoshi} 必须为整数（基点）：${_repr(bps)}`)
  }
  if (bps < 0 || bps > ZUIDA_DACHENGLV_BPS) {
    throw new BscCuowu(`${biaoshi} 必须在 [0, ${ZUIDA_DACHENGLV_BPS}] 内（基点）：${bps}`)
  }
}

// ----------------------------------------------------------------------
// 对外接口区（唯一的计算入口）
// ----------------------------------------------------------------------

/** BSC 四维加权评分（方案B 步骤 5b；纯函数）。
 *
 *  参数：shuru —— BscShuru（四维达成率 + 可选权重）。
 *
 *  返回：BscJieguo（四维得分 + 生效权重 + 总分 + 等级）。
 *
 *  处理顺序：
 *      ① 校验（类型/达成率形态/权重形态与合计）→ ② 维度得分（half-up，
 *      不封顶）→ ③ 总分（half-up）→ ④ 等级五档。
 */
export function jisuan_bsc(shuru: BscShuru): BscJieguo {
  if (typeof shuru !== 'object' || shuru === null || Array.isArray(shuru)) {
    throw new BscCuowu(`输入必须是 BscShuru：${_repr(shuru)}`)
  }

  // ① 达成率校验：非负整数、不超合理性上限（bool 是 int 子类须排除）
  const si_bps: readonly [unknown, string][] = [
    [shuru.caijing_bps, 'caijing_bps'],
    [shuru.kehu_bps, 'kehu_bps'],
    [shuru.neibu_bps, 'neibu_bps'],
    [shuru.xuexi_bps, 'xuexi_bps'],
  ]
  for (const [bps, biaoshi] of si_bps) {
    _jianyan_bps(bps, biaoshi)
  }

  // ① 权重校验：null → 默认配比；否则四项 0~100 整数且合计 = 100
  //   （TS 运行时无法区分四元组与普通数组——同为 Array，"必须为元组"的
  //   类型检查落实为"必须为长度 4 的数组序列"，报错文案与 Python 同形）
  const quanzhong = shuru.quanzhong ?? QUANZHONG_MOREN
  if (!Array.isArray(quanzhong) || quanzhong.length !== 4) {
    throw new BscCuowu(`quanzhong 必须为四项元组：${_repr(quanzhong)}`)
  }
  for (const w of quanzhong) {
    if (typeof w === 'boolean' || !Number.isInteger(w)) {
      throw new BscCuowu(`权重必须为整数：${_repr(w)}`)
    }
    if (w < 0 || w > 100) {
      throw new BscCuowu(`权重必须在 [0, 100] 内：${w}`)
    }
  }
  const heji = quanzhong[0]! + quanzhong[1]! + quanzhong[2]! + quanzhong[3]!
  if (heji !== 100) {
    // 报错格式与 Python tuple repr ((40, 30, 20, 5)) 同形
    throw new BscCuowu(`权重合计必须等于 100：(${quanzhong.map(String).join(', ')})（合计 ${heji}）`)
  }

  // ② 维度得分：half-up(达成率 ÷ 100)；不封顶——>100% 时得分 >100 保留
  const defen: SiYuanzu = [
    _dacheng_bps_defen(shuru.caijing_bps),
    _dacheng_bps_defen(shuru.kehu_bps),
    _dacheng_bps_defen(shuru.neibu_bps),
    _dacheng_bps_defen(shuru.xuexi_bps),
  ]

  // ③ 总分 + ④ 等级
  const zongfen = _zongfen(defen, quanzhong as SiYuanzu)
  return {
    caijing_defen: defen[0],
    kehu_defen: defen[1],
    neibu_defen: defen[2],
    xuexi_defen: defen[3],
    quanzhong: quanzhong as SiYuanzu,
    zongfen,
    dengji: _dengji(zongfen),
    caijing_bps: shuru.caijing_bps,
    kehu_bps: shuru.kehu_bps,
    neibu_bps: shuru.neibu_bps,
    xuexi_bps: shuru.xuexi_bps,
  }
}
