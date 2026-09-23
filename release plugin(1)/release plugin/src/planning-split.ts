// ======================================================================
// 规划/执行差异拆分模块 —— 方案B 步骤 3c（总量恒等式铁律 + 四项细分归因）
// ======================================================================
// 转写自 D:\AppProject\algo\planning_operational.py（Python 版为唯一行为准绳）。
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs\textbook\finagent-算法核对文档-定稿.md v2.1 §3（T-01 修复后的拆分口径）
//     docs\10-待核对问题定稿摘要.md  #4（队友定稿：以修订标准为基准的拆分）
//
// 【铁律】总量恒等式——总量按恒等式计算与展示，永不由四项细分相加：
//     原标准总差异 = 规划总差异 + 执行总差异
//       规划总差异 = 修订标准成本 − 原标准成本（不可控，不归责执行部门）
//       执行总差异 = 实际成本   − 修订标准成本（可控，纳入绩效）
//     恒等式天然成立（数学事实），代码内仍显式校验并输出成立标志（防回归）。
//
// 四项细分（仅作归因参考，含交叉残差——v2.1 §3 对 #4 硬伤的处理）：
//     价格规划 =（标准单价 − 修订单价）× 实际用量
//     价格执行 =  修订单价 × 实际用量 − 实际成本        （等价 (修订−实际价)×用量）
//     用量规划 =（标准用量 − 修订用量）× 实际产量 × 标准单价
//     用量执行 =（修订用量 × 实际产量 − 实际用量）× 修订单价
//     细分合计 ≠ 总差异（差额即残差）——展示时须注明"以总量恒等式为准"。
//
// 残差公式（与总量恒等式的解析关系，代码内校验）：
//     残差 =（修订用量 × 实际产量 − 实际用量）×（标准单价 − 修订单价）
//
// 【符号口径——两套并存，字段上一一配对 FA，绝不裸用（v2.1 §0.5 精神）】
//     三个总量（yuandan/guihua/zhixing_zong）：展示口径，正 = 超支 = 不利 A；
//     四个细分（jiage/yongliang_guihua/zhixing）：ACCA 公式符号，正 = 节省 = 有利 F；
//     原因：总量按"贵了为正"贴合报表直觉；细分公式天然"节省为正"（标准−实际方向）。
//
// 数值纪律：单价/成本 = 整数分；用量/产量 = 整数（基本单位：kg、工时等）；
//     全程整数运算——四项公式全部改写为乘减形式，【零除法】（无舍入误差源）。
//
// BigInt 纪律（TS 转写特有，等价补齐 Python 任意精度整数）：
//     合法输入下 产量×用量×单价 最大可达 1e9 × 1e9 × 9e11 = 9e29，远超 2^53——
//     所有乘减中间量（含两道内部自检）一律在 BigInt 域内精确完成，仅在结果
//     对象构造时转回 number。极端上限输入下 number 会损失精度（测试锚定值
//     均在安全范围），但绝不会因浮点误差误触发"恒等式不成立"。
//
// 与上下游的关系：
//     上游：variance（步骤 3a 提供差异触发场景）、data_ingest（修订标准参数）；
//     下游：loop_decision（步骤 4 单双环判定的归因线索——
//           执行差异显著 → 单环线索；规划差异显著 → 双环线索，见 v2.1 §3 挂钩）。
//
// 使用示例（知识点速览，v0.1 2026-08-23；数字例题 = 定稿 v2.1 §3 的 Holmes Ltd
//     案例（标准 7kg×$4 → 修订 8kg×$3.80；产量 1,400，耗用 11,000kg，
//     成本 $41,500），期望值全部手工验算写死，金额乘 100 转分）：
//
//     知识点 1 · Holmes 例题：三个总量 + 恒等式
//     chai_fen({ biaozhun_danjia_fen: 400, biaozhun_yongliang: 7,
//       xiuding_danjia_fen: 380, xiuding_yongliang: 8, shiji_chanliang: 1400,
//       shiji_yongliang: 11000, shiji_chengben_fen: 4_150_000 })
//     → 原标准总 = 4,150,000 − 1,400×7×400 = +230,000 分（2,300 元，超支 → A）
//     → 规划总 +336,000（A）；执行总 −106,000（F）；恒等式 336,000 + (−106,000) = 230,000 ✓
//
//     知识点 2 · 四项细分（ACCA 符号：正 = 有利 F）+ 残差
//     → 价格规划 (400−380)×11,000 = +220,000 分（F）；价格执行 380×11,000 − 4,150,000 = +30,000（F）
//     → 用量规划 −560,000（A）；用量执行 +76,000（F）
//     → 残差 4,000 分（40 元）= (8×1400−11000)×(400−380)——细分合计≠总量的部分
//
//     知识点 3 · 无结构变更（修订 = 标准）：规划差异归零，全归执行
//     → guihua_zong_fen = 0；zhixing_zong_fen = 230,000
//
// 命名对照表（拼音标识符 → 中文含义）：
//     ChaifenShuru      拆分输入（标准/修订参数 + 实际三数）
//     ChaifenJieguo     拆分结果（三总量+四细分+残差+恒等式标志，各金额配 FA）
//     ChaifenCuowu      拆分错误（校验失败异常）
//     chai_fen          拆分（主函数）
//     biaozhun_danjia_fen / biaozhun_yongliang   标准单价（分）/ 标准用量
//     xiuding_danjia_fen / xiuding_yongliang     修订单价（分）/ 修订用量
//     shiji_chanliang / shiji_yongliang / shiji_chengben_fen
//                       实际产量 / 实际总用量 / 实际总成本（分）
//     yuandan_zong_*    原标准总差异（金额分 + FA）
//     guihua_zong_*     规划总差异（不可控）
//     zhixing_zong_*    执行总差异（可控）
//     jiage_guihua_* / jiage_zhixing_*     价格规划/价格执行（细分）
//     yongliang_guihua_* / yongliang_zhixing_*  用量规划/用量执行（细分）
//     cancha_fen        残差（细分合计与总量的解析差额）
//     hengdengshi_chengli  恒等式成立（自检标志，恒 true；false 即代码有 bug）
//
// 建立：2026-08-23 ｜ Python 原版：ZCode（GLM-5.3）｜ TS 转写：2026-09-05
// ======================================================================

// ----------------------------------------------------------------------
// 常量区
// ----------------------------------------------------------------------

/** 金额字段上限（分）——与全项目一致的合理性校验（Python int 无溢出，防脏数据） */
export const ZUIDA_JINE_FEN = 9 * 10 ** 11

/** 数量字段上限（基本单位）——kg / 工时等，同样只为拦截录入事故 */
export const ZUIDA_SHULIANG = 10 ** 9

/**
 * 拆分输入校验失败（字段非法 / 产量为零等）。
 * 继承 Error：调用方按脏数据统一捕获（全项目异常约定）。报错文案与 Python 逐字一致。
 */
export class ChaifenCuowu extends Error {}

// ----------------------------------------------------------------------
// 数据结构区（Python frozen dataclass → readonly interface + 对象字面量）
// ----------------------------------------------------------------------

/** 拆分输入：标准参数、修订参数（结构变更后重估）与实际三数。 */
export interface ChaifenShuru {
  /** 标准单价（分）。 */
  readonly biaozhun_danjia_fen: number
  /** 标准用量/单位（基本单位的整数）。 */
  readonly biaozhun_yongliang: number
  /** 修订单价（分）——事后重估的"应该价格"。 */
  readonly xiuding_danjia_fen: number
  /** 修订用量/单位——事后重估的"应该用量"。 */
  readonly xiuding_yongliang: number
  /** 实际产量（必须 > 0：单位成本要有分母）。 */
  readonly shiji_chanliang: number
  /** 实际总用量（允许 0：没用料但花了钱的场景）。 */
  readonly shiji_yongliang: number
  /** 实际总成本（分）。 */
  readonly shiji_chengben_fen: number
}

/**
 * 拆分结果：三总量 + 四细分 + 残差 + 恒等式标志（每个金额配 FA）。
 *
 * 符号口径（见模块头"符号口径"节，两套并存、字段配对防误用）：
 *     三个 *_zong_*：正 = 超支 = A；四个细分：正 = 有利 = F。
 */
export interface ChaifenJieguo {
  readonly yuandan_zong_fen: number       // 原标准总差异 = 实际 − 原标准
  readonly yuandan_zong_fa: string
  readonly guihua_zong_fen: number        // 规划总差异 = 修订标准 − 原标准（不可控）
  readonly guihua_zong_fa: string
  readonly zhixing_zong_fen: number       // 执行总差异 = 实际 − 修订标准（可控）
  readonly zhixing_zong_fa: string
  readonly jiage_guihua_fen: number       // 价格规划细分（F 为正）
  readonly jiage_guihua_fa: string
  readonly jiage_zhixing_fen: number      // 价格执行细分（F 为正）
  readonly jiage_zhixing_fa: string
  readonly yongliang_guihua_fen: number   // 用量规划细分（F 为正）
  readonly yongliang_guihua_fa: string
  readonly yongliang_zhixing_fen: number  // 用量执行细分（F 为正）
  readonly yongliang_zhixing_fa: string
  readonly cancha_fen: number             // 残差（细分合计与总量的解析差额，展示用）
  readonly hengdengshi_chengli: boolean   // 恒等式自检标志（恒 true；false = 代码缺陷）
}

// ----------------------------------------------------------------------
// 内部工具函数区
// ----------------------------------------------------------------------

/**
 * 值 → 文本（对齐 Python f-string 的 str()/!r 渲染习惯：
 * bool 显示为 True/False、字符串带单引号）——保证报错文案与 Python 逐字一致。
 */
function _zhi_wenben(zhi: unknown): string {
  if (typeof zhi === 'boolean') return zhi ? 'True' : 'False'
  if (typeof zhi === 'string') return `'${zhi}'`
  return String(zhi)
}

/** 通用校验：非负整数且不超上限（bool 排除——Python 里 True 也是 int 子类）。 */
function _jianyan(shuzhi: unknown, shangxian: number, biaoshi: string): void {
  if (typeof shuzhi === 'boolean' || typeof shuzhi !== 'number' || !Number.isInteger(shuzhi)) {
    throw new ChaifenCuowu(`${biaoshi} 必须为整数：${_zhi_wenben(shuzhi)}`)
  }
  if (shuzhi < 0 || shuzhi > shangxian) {
    throw new ChaifenCuowu(`${biaoshi} 必须在 [0, ${shangxian}] 内：${_zhi_wenben(shuzhi)}`)
  }
}

/** 总量 F/A：展示口径——正 = 超支 = 'A'，负 = 'F'，零 = '—'。 */
function _fa_zong(fen: bigint): string {
  if (fen === 0n) return '—'
  return fen > 0n ? 'A' : 'F'
}

/** 细分 F/A：ACCA 口径——正 = 节省 = 'F'，负 = 'A'，零 = '—'。 */
function _fa_xiangxi(fen: bigint): string {
  if (fen === 0n) return '—'
  return fen > 0n ? 'F' : 'A'
}

/** 运行时结构识别（Python isinstance(ChaifenShuru) 的 TS 对应物：七字段齐备即认，逐字段值校验交给 _jianyan）。 */
function _shi_ChaifenShuru(shuru: unknown): shuru is ChaifenShuru {
  if (typeof shuru !== 'object' || shuru === null) return false
  const ziduan: readonly string[] = [
    'biaozhun_danjia_fen', 'biaozhun_yongliang', 'xiuding_danjia_fen',
    'xiuding_yongliang', 'shiji_chanliang', 'shiji_yongliang', 'shiji_chengben_fen',
  ]
  return ziduan.every((ming) => (shuru as Record<string, unknown>)[ming] !== undefined)
}

// ----------------------------------------------------------------------
// 对外接口区（唯一的计算入口）
// ----------------------------------------------------------------------

/**
 * 规划/执行差异拆分（方案B 步骤 3c；纯函数、全程整数、零除法）。
 *
 * 计算顺序：
 *     ① 校验 → ② 三个总量（恒等式成员）→ ③ 恒等式自检 →
 *     ④ 四项细分（乘减改写，无除法无舍入）→ ⑤ 残差公式核对。
 *
 * BigInt 纪律：产量×用量×单价 合法输入乘积可达 9e29（>> 2^53），
 * 乘减中间量全程 BigInt，两道内部自检也在 BigInt 域内精确完成，
 * 仅结果对象构造时转回 number（见模块头"BigInt 纪律"节）。
 */
export function chai_fen(shuru: ChaifenShuru): ChaifenJieguo {
  // ---- ① 校验 ----
  if (!_shi_ChaifenShuru(shuru)) {
    throw new ChaifenCuowu(`shuru 必须为 ChaifenShuru 实例：${_zhi_wenben(shuru)}`)
  }
  _jianyan(shuru.biaozhun_danjia_fen, ZUIDA_JINE_FEN, 'biaozhun_danjia_fen')
  _jianyan(shuru.xiuding_danjia_fen, ZUIDA_JINE_FEN, 'xiuding_danjia_fen')
  _jianyan(shuru.shiji_chengben_fen, ZUIDA_JINE_FEN, 'shiji_chengben_fen')
  for (const [mingzi, zhi] of [
    ['biaozhun_yongliang', shuru.biaozhun_yongliang],
    ['xiuding_yongliang', shuru.xiuding_yongliang],
    ['shiji_yongliang', shuru.shiji_yongliang],
  ] as const) {
    _jianyan(zhi, ZUIDA_SHULIANG, mingzi)
  }
  _jianyan(shuru.shiji_chanliang, ZUIDA_SHULIANG, 'shiji_chanliang')
  if (shuru.shiji_chanliang <= 0) {
    // 产量为 0 时单位成本失去意义（拆分的数学前提），明确拒绝
    throw new ChaifenCuowu('shiji_chanliang 必须大于 0（单位成本要有分母）')
  }

  // ---- ② 三个总量（原标准 / 修订标准的"单位成本 × 产量"展开式；BigInt 域内精确）----
  const yuandan_biaozhun_fen =
    BigInt(shuru.shiji_chanliang) * BigInt(shuru.biaozhun_yongliang) * BigInt(shuru.biaozhun_danjia_fen)
  const xiuding_biaozhun_fen =
    BigInt(shuru.shiji_chanliang) * BigInt(shuru.xiuding_yongliang) * BigInt(shuru.xiuding_danjia_fen)

  const yuandan_zong = BigInt(shuru.shiji_chengben_fen) - yuandan_biaozhun_fen   // 实际 − 原标准
  const guihua_zong = xiuding_biaozhun_fen - yuandan_biaozhun_fen                // 修订 − 原标准
  const zhixing_zong = BigInt(shuru.shiji_chengben_fen) - xiuding_biaozhun_fen   // 实际 − 修订

  // ---- ③ 恒等式自检（数学上恒成立；false 即代码缺陷，直接抛错暴露）----
  if (yuandan_zong !== guihua_zong + zhixing_zong) {
    throw new ChaifenCuowu('内部错误：恒等式不成立（原标准总 ≠ 规划总 + 执行总）')
  }

  // ---- ④ 四项细分（乘减改写：等价于教材公式但零除法、零舍入）----
  const jiage_guihua =
    BigInt(shuru.biaozhun_danjia_fen - shuru.xiuding_danjia_fen) * BigInt(shuru.shiji_yongliang)
  const jiage_zhixing =
    BigInt(shuru.xiuding_danjia_fen) * BigInt(shuru.shiji_yongliang) - BigInt(shuru.shiji_chengben_fen)
  const yongliang_guihua =
    BigInt(shuru.biaozhun_yongliang - shuru.xiuding_yongliang) * BigInt(shuru.shiji_chanliang) * BigInt(shuru.biaozhun_danjia_fen)
  const yongliang_zhixing =
    (BigInt(shuru.xiuding_yongliang) * BigInt(shuru.shiji_chanliang) - BigInt(shuru.shiji_yongliang)) * BigInt(shuru.xiuding_danjia_fen)

  // ---- ⑤ 残差公式（解析核对：细分合计与总量的差额必等于此式）----
  const cancha =
    (BigInt(shuru.xiuding_yongliang) * BigInt(shuru.shiji_chanliang) - BigInt(shuru.shiji_yongliang)) * BigInt(shuru.biaozhun_danjia_fen - shuru.xiuding_danjia_fen)
  // 残差自检：细分合计换到总量口径（取负）减残差 == 原标准总。
  // 代数依据：−Σ细分 − 残差 = 原标准总（展开式可证；Holmes 例：
  // +234,000 − 4,000 = 230,000 ✓）——符号方向由 P3 性质测试再守一道。
  if (-(jiage_guihua + jiage_zhixing + yongliang_guihua + yongliang_zhixing) - cancha !== yuandan_zong) {
    throw new ChaifenCuowu('内部错误：残差关系不成立（−细分合计 − 残差 ≠ 原标准总）')
  }
  return {
    yuandan_zong_fen: Number(yuandan_zong), yuandan_zong_fa: _fa_zong(yuandan_zong),
    guihua_zong_fen: Number(guihua_zong), guihua_zong_fa: _fa_zong(guihua_zong),
    zhixing_zong_fen: Number(zhixing_zong), zhixing_zong_fa: _fa_zong(zhixing_zong),
    jiage_guihua_fen: Number(jiage_guihua), jiage_guihua_fa: _fa_xiangxi(jiage_guihua),
    jiage_zhixing_fen: Number(jiage_zhixing), jiage_zhixing_fa: _fa_xiangxi(jiage_zhixing),
    yongliang_guihua_fen: Number(yongliang_guihua), yongliang_guihua_fa: _fa_xiangxi(yongliang_guihua),
    yongliang_zhixing_fen: Number(yongliang_zhixing), yongliang_zhixing_fa: _fa_xiangxi(yongliang_zhixing),
    cancha_fen: Number(cancha),
    hengdengshi_chengli: true,  // 到这里恒等式已校验通过
  }
}
