// ======================================================================
// 整数运算公共库（BigInt 半进位助手）—— FinAgent dsh 插件
// ======================================================================
//
// 为什么需要这个文件：
//   Python 的整数是任意精度，algo 各模块的中间量（金额×基点、差额×2万）
//   天然不会溢出；TypeScript 的 number 只有 53 位安全整数，
//   金额上限 9×10^11 乘以 (10000+基点) ≈ 9.09×10^15 就已越过 2^53 = 9.007×10^15。
//   因此所有「乘基点 / 求比率」的中间运算一律走 BigInt，结果转回 number。
//   输出值均 < 9×10^15，落在 number 安全范围内。
//
// 纪律：
//   - 禁止在任何计算模块里裸写 `* 10000` 后 `Math.round` —— 必须经本库；
//   - 全程整数运算，禁止 float / decimal 类库进入金额与比率；
//   - 舍入只有 half-up（四舍五入）一种，各函数与 algo Python 逐式对应。
// ======================================================================

/** 1 个百分点 = 100 基点；100% = 10000 基点。与 algo JIDIAN_JISHU 一致。 */
export const JIDIAN_JISHU = 10_000

/**
 * 金额乘以 (10000 + 基点) / 10000，四舍五入到分（half-up）。
 *
 * 对应 algo/rolling_budget.py `_cheng_jidian`：
 *     (fen * (JIDIAN_JISHU + jidian) + JIDIAN_JISHU // 2) // JIDIAN_JISHU
 * —— 整数地板除天然实现 half-up（加半法）。
 *
 * 用途：滚动预算剩余期逐期重算（链法①逐期舍入接力）、行业修正一次性乘子。
 * 参数：fen 金额（整数分，上限 9×10^11）；jidian 增长率基点（[-10000, 10000]）。
 */
export function cheng_jidian(fen: number, jidian: number): number {
  const bei_fen = BigInt(fen) * BigInt(JIDIAN_JISHU + jidian) + BigInt(JIDIAN_JISHU >> 1)
  return Number(bei_fen / BigInt(JIDIAN_JISHU))
}

/**
 * 非负比率：fenzi / fenmu × 10000，half-up。
 *
 * 对应 algo/kpi.py `_bili_bps`、algo/suyuan 影响率、algo/xishu 完成率的统一写法：
 *     (fenzi * 10_000 * 2 + fenmu) // (2 * fenmu)
 * —— 乘 2 加分母等价于加半个分母，奇数分母时与「半分母」写法结果一致。
 *
 * 用途：达成率、占比、影响率、完成率等所有「除法求基点」场合。
 * 约束：fenzi ≥ 0 且 fenmu > 0（分母校验归调用方，这里不重复校验）。
 */
export function bili_bps(fenzi: number, fenmu: number): number {
  const bei = BigInt(fenzi) * BigInt(JIDIAN_JISHU) * 2n + BigInt(fenmu)
  return Number(bei / (2n * BigInt(fenmu)))
}

/**
 * 比率（半分母变体）：fenzi / fenmu × 10000，half-up。
 *
 * 对应 algo/variance.py 差异率的原始写法：
 *     (abs(chae_fen) * 10_000 + jizhun_fen // 2) // jizhun_fen
 * —— 与 bili_bps 在偶数分母时恒等；奇数分母且分子恰好压线时可能有 1 基点差，
 *    为与 Python 测试期望值逐字一致，差异率专用此变体，不得混用 bili_bps。
 *
 * 约束：fenzi ≥ 0 且 fenmu > 0。
 */
export function bili_bps_ban_jian(fenzi: number, fenmu: number): number {
  const bei = BigInt(fenzi) * BigInt(JIDIAN_JISHU) + BigInt(fenmu >> 1)
  return Number(bei / BigInt(fenmu))
}

/**
 * 带符号比率：chae / fenmu × 10000，half-up（先取绝对值算，再补符号）。
 *
 * 对应 algo/kpi.py 带符号公式（费用偏差率、采购成本变动率）与
 * algo/suyuan.py 影响率：
 *     bps = (abs(chae) * 10_000 * 2 + fenmu) // (2 * fenmu)；chae < 0 时取负。
 *
 * chae 为 0 时返回 0（正零，不带 -0）。
 */
export function dai_fuhao_bps(chae: number, fenmu: number): number {
  const jue_dui = bili_bps(Math.abs(chae), fenmu)
  return chae < 0 ? -jue_dui : jue_dui
}

/**
 * half-up 平分：求 he 的「除以 2 四舍五入」；负数向零舍入。
 *
 * 对应 algo/kpi.py 平均营运资金：
 *     he >= 0: (he + 1) // 2
 *     he <  0: -((-he + 1) // 2)
 * —— 加 1 再地板除即 half-up；负数场景与正数规则同构（向零舍入）。
 *
 * 用途：资金周转率的平均营运资金 =（期初净额 + 期末净额）÷ 2。
 */
export function pingjun_half_up(he: number): number {
  if (he >= 0) return Math.floor((he + 1) / 2)
  return -Math.floor((-he + 1) / 2)
}

/**
 * 分 → 元字符串（两位小数，无千分位），仅供展示层/演示脚本。
 *
 * 对应 algo/rolling_budget.py `fen_zhuan_yuan`：
 *     f'{fuhao}{jue_dui // 100}.{jue_dui % 100:02d}'
 * —— 负号前置；模块间传值一律用整数分，元字符串只允许出现在面向人的输出。
 */
export function fen_zhuan_yuan(fen: number): string {
  const fu_hao = fen < 0 ? '-' : ''
  const jue_dui = Math.abs(fen)
  const yuan_zhengshu = Math.floor(jue_dui / 100)
  const fen_liangwei = String(jue_dui % 100).padStart(2, '0')
  return `${fu_hao}${yuan_zhengshu}.${fen_liangwei}`
}
