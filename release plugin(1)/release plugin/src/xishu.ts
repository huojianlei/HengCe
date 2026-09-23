// ======================================================================
// xishu（判定系数输出）—— 算法层与分析层（M5）之间的【系数包】桥梁
//（TODO T-32）
// ======================================================================
// 转写自 D:\AppProject\algo\xishu.py（Python 版为唯一行为准绳；
// 对应测试 algo/tests/test_xishu.py → 插件 tests/xishu.test.ts）。
//
// 新增口径（TODO T-32，用户 2026-08-27 提出"本地程序需要能生成相应系数"）：
// 计算主线跑完后，把分散在各模块的结果汇总成一份【判定系数包】——
// 预警级别分布、红行明细、整体完成率、单双环结论、核心问题模块、BSC 评级、
// 整改优先级计数——并按【系数 → 检索提示词】映射表生成 kb2 检索查询串。
//
// 定位（RAG 方案 v2.0 §6："algo 算完 → 判定系数（T-32）→ 提示词映射 → 检索"）：
//     计算层（本模块上游）──系数包──▶ 分析层 M5（检索 + LLM 报告）
//     本模块是两层之间【唯一的接缝】：只做汇总与映射，不做任何分析。
//
// 分层纪律的边界声明（[043]，诚实口径）：
//     本模块生成的"提示词"是【检索查询串】——由确定性映射表从系数机械
//     翻译而来（如"红色预警+采购模块"→"采购成本控制 制度"），不是分析
//     文案；自然语言分析归 AI 层（M5/dsh）。映射表当前为建议默认值
//     【TODO T-32】，M5 层研究后可调整——改映射不改结构。
//
// 汇总口径（全部来自上游既有输出，本模块不重算任何差异/评级）：
//     · 预警级别分布与红行明细 ← variance（红行按差异率降序）；
//     · 整体完成率 = Σ实际 ÷ Σ基准（基点，half-up；无行/基准为 0 → null）；
//     · 单双环结论与审批标志 ← loop_decision；
//     · 核心问题模块 ← building_blocks（高亮模块）；
//     · BSC 总分与等级 ← bsc；整改优先级计数 ← zhenggai。
//     上游缺哪块，系数包对应字段为 null/空——缺数不臆造（全项目纪律）。
//
// 数值纪律：金额 = 整数分；比率 = 整数基点（1% = 100 基点），half-up
//     整数舍入；纯函数（无 I/O、无全局状态）。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     XishuShuru         系数输入（五个上游结果，鸭子类型，均可 null）
//     XishuBao           系数包（汇总字段 + 提示词元组）
//     XishuTishi         提示词项（laiyuan 来源系数 + chaxun_ciyu 查询串）
//     shengcheng_xishu   生成系数（主函数：汇总 + 映射）
//     shengcheng_tishi   生成提示词（系数 → 检索查询串的映射表，T-32 建议默认值）
//     hong_shu / huang_shu / wu_shu       预警红/黄/无计数
//     hong_hang_lie      红行明细（qijian/kemu/chalv_bps/fa，差异率降序）
//     wanchenglv_bps     整体完成率（Σ实际 ÷ Σ基准，基点；无数据 → null）
//     panduan_jielun / shenpi             单双环结论 / 是否需人工审批
//     hexin_mokuai       核心问题模块（积木高亮）
//     bsc_zongfen / bsc_dengji            BSC 总分 / 等级
//     zhenggai_gao_shu / zhenggai_zhong_shu   整改高/中优先级计数
//     tishi_lie          检索提示词元组（去重、上限 TISHI_SHANGXIAN 条）
//
// 口径依据：TODO.md T-32（判定系数输出）；kb2/RAG部署与使用方案.md §6
//          （系数→提示词→驱动检索）与 §4（引用/数字校验闸门的输入端）；
//          docs/01 需求说明 [043] 分层纪律（提示词=检索查询串，非分析文案）。
// 建立：2026-08-30（Python）｜ TS 转写：2026-09-05 ｜ FinAgent dsh 插件批次F
// ======================================================================

// 完成率 = Σ实际 ÷ Σ基准（half-up 整数基点）——统一走 int-math 的 BigInt
// 半进位助手（乘 10000 的中间量可超 2^53，禁止裸 * 后 Math.round）。
import { bili_bps } from './int-math.ts'

// ======================================================================
// 常量区（映射表 = T-32 建议默认值，M5 层研究后只改此处不改结构）
// ======================================================================

/** 检索提示词上限（条）——控制 M5 提示词长度，超限按优先级截断 */
export const TISHI_SHANGXIAN = 8

/** 判定结论 → 检索查询串（单双环维度的固定映射） */
export const PANDUAN_TISHI: Record<string, string> = {
  单环: '预算执行 偏差 整改',
  双环: '预算调整 审批程序',
  混合纠错模式: '预算调整 审批程序',
}

/** 核心问题模块 → 检索查询串（积木模块维度的固定映射） */
export const MOKUAI_TISHI: Record<string, string> = {
  收入模块: '收入管理 制度',
  成本模块: '成本管理 制度',
  费用模块: '费用管控 制度',
  采购模块: '采购成本控制 制度',
}

/** BSC 等级 → 检索查询串（仅预警/严重不合格触发——达标不查） */
export const DENGJI_TISHI: Record<string, string> = {
  预警: '平衡计分卡 绩效评价',
  严重不合格: '绩效改进 制度',
}

// ======================================================================
// 鸭子类型上游接口区（最小结构形状，字段名与所有权模块导出 interface 逐字一致）
// ======================================================================

/** variance.ChayiXiang 的最小结构形状（鸭子类型；本模块消费的六个字段）。
 *
 *  字段名与 variance.ts 导出的 ChayiXiang 逐字一致——TS 结构类型天然
 *  兼容，无需 import variance。 */
export interface ChayiXiangYang {
  readonly qijian: string
  readonly kemu: string
  readonly yujing: string
  readonly chalv_bps: number | null
  readonly jizhun_fen: number | null
  readonly shiji_fen: number | null
}

/** variance.ChayiJieguo 的最小结构形状：须有 .xiang 列表。 */
export interface ChayiJieguoYang {
  readonly xiang: readonly ChayiXiangYang[]
}

/** loop_decision.PanDuanJieguo 的最小结构形状（单双环结论 + 审批标志）。 */
export interface PanDuanJieguoYang {
  readonly panduan: string
  readonly shenpi: boolean
}

/** building_blocks.JimuJieguo 的最小结构形状（核心问题模块）。 */
export interface JimuJieguoYang {
  readonly hexin_mokuai: string | null
}

/** bsc.BscJieguo 的最小结构形状（总分 + 等级）。 */
export interface BscJieguoYang {
  readonly zongfen: number
  readonly dengji: string
}

/** zhenggai.ZhenggaiJieguo 的最小结构形状（整改高/中优先级计数）。 */
export interface ZhenggaiJieguoYang {
  readonly gao_shu: number
  readonly zhong_shu: number
}

// ======================================================================
// 数据结构区（frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** 一条检索提示词：来源系数标签 + 查询串（给 M5 的检索驱动指令）。 */
export interface XishuTishi {
  readonly laiyuan: string     // 来源系数（'红预警-科目' / '单双环判定' / '核心问题模块' / 'BSC评级'）
  readonly chaxun_ciyu: string // 检索查询串（kb2 jiansuo 的输入）
}

/** 系数输入：五个上游结果对象（鸭子类型；null/缺省 = 该来源缺失）。
 *
 *  Python dataclass 五字段均缺省 None；TS 侧以可选字段 + null 表达。 */
export interface XishuShuru {
  readonly chayi?: ChayiJieguoYang | null    // variance.ChayiJieguo（预警计数/红行/完成率来源）
  readonly panduan?: PanDuanJieguoYang | null // loop_decision.PanDuanJieguo（单双环结论）
  readonly jimu?: JimuJieguoYang | null      // building_blocks.JimuJieguo（核心问题模块）
  readonly bsc?: BscJieguoYang | null        // bsc.BscJieguo（总分/等级）
  readonly zhenggai?: ZhenggaiJieguoYang | null // zhenggai.ZhenggaiJieguo（整改优先级计数）
}

/** 判定系数包：M5 分析层的全部输入事实（缺数字段为 null/空，不臆造）。 */
export interface XishuBao {
  readonly hong_shu: number        // 红色预警行数（无 chayi → 0）
  readonly huang_shu: number       // 黄色预警行数
  readonly wu_shu: number          // 无预警行数
  readonly hong_hang_lie: readonly (readonly [string, string, number | null, string])[]
                                   // 红行明细 (qijian, kemu, chalv_bps, fa)，差异率降序
  readonly wanchenglv_bps: number | null   // 整体完成率（基点；无行或基准为 0 → null）
  readonly panduan_jielun: string | null   // 单双环结论（'不触发'/'单环'/'双环'/'混合纠错模式'/'复核提示'）
  readonly shenpi: boolean | null          // 是否需人工审批
  readonly hexin_mokuai: string | null     // 核心问题模块
  readonly bsc_zongfen: number | null      // BSC 总分
  readonly bsc_dengji: string | null       // BSC 等级
  readonly zhenggai_gao_shu: number | null // 整改高优先级条数
  readonly zhenggai_zhong_shu: number | null // 整改中优先级条数
  readonly tishi_lie: readonly XishuTishi[] // 检索提示词（去重 + 限长）
}

// ======================================================================
// 提示词映射区（系数 → 检索查询串；T-32 建议默认值）
// ======================================================================

/** 按映射表把系数翻成检索查询串：判定 → 核心模块 → BSC 评级 → 红/黄行。
 *
 *  shangxian：条数上限（默认 TISHI_SHANGXIAN=8，服务 M5 提示词长度）；
 *  传更大的值可取全量提示词（如检索分表演示要覆盖每一条预警行）。
 *
 *  生成规则（建议默认值，【TODO T-32】随 M5 研究调整；按优先级排序——
 *  结构性结论先于逐行明细，逐行明细再多也不许挤掉判定/模块提示词）：
 *  · 单双环判定：双环/混合 → '预算调整 审批程序'；单环 → '预算执行 偏差 整改'；
 *  · 核心问题模块 → 模块领域词（MOKUAI_TISHI）；
 *  · BSC 等级仅预警/严重不合格触发（达标不查——没有要查的问题）；
 *  · 红/黄预警行（按差异率降序）：不利(A) → '{科目} 预算超支 管控措施'；
 *    有利(F)但波动过大 → '{科目} 预算差异 分析方法'。
 *  同串去重、超限截断——提示词列表是给 M5 拼提示词用的，
 *  条目失控会撑爆上下文。 */
export function shengcheng_tishi(
  chayi: ChayiJieguoYang | null | undefined,
  panduan: PanDuanJieguoYang | null | undefined,
  jimu: JimuJieguoYang | null | undefined,
  bsc: BscJieguoYang | null | undefined,
  shangxian: number = TISHI_SHANGXIAN,
): XishuTishi[] {
  const lie_lie: XishuTishi[] = []
  // ① 单双环判定（结构性结论最先）
  if (panduan != null) {
    const ciyu = PANDUAN_TISHI[panduan.panduan]
    if (ciyu) {
      lie_lie.push({ laiyuan: '单双环判定', chaxun_ciyu: ciyu })
    }
  }
  // ② 核心问题模块（积木高亮 → 模块领域词）
  if (jimu != null && jimu.hexin_mokuai) {
    const ciyu = MOKUAI_TISHI[jimu.hexin_mokuai]
    if (ciyu) {
      lie_lie.push({ laiyuan: '核心问题模块', chaxun_ciyu: ciyu })
    }
  }
  // ③ BSC 评级（仅预警/严重不合格——达标没有要查的问题）
  if (bsc != null) {
    const ciyu = DENGJI_TISHI[bsc.dengji]
    if (ciyu) {
      lie_lie.push({ laiyuan: 'BSC评级', chaxun_ciyu: ciyu })
    }
  }
  // ④ 红/黄预警行（按差异率降序——最刺眼的先查；预警级别优先序）
  if (chayi != null) {
    // filter 先复制再排序——不改动上游 chayi.xiang 的原始顺序
    const yichang = chayi.xiang
      .filter((x) => x.yujing === '红' || x.yujing === '黄')
      .sort((a, b) => (b.chalv_bps ?? 0) - (a.chalv_bps ?? 0))
    for (const x of yichang) {
      let ciyu: string
      if (x.fa === 'A') {
        ciyu = `${x.kemu} 预算超支 管控措施`
      } else {
        ciyu = `${x.kemu} 预算差异 分析方法` // 有利但波动过大——查分析方法
      }
      lie_lie.push({ laiyuan: `${x.yujing}预警-${x.kemu}`, chaxun_ciyu: ciyu })
    }
  }
  // ⑤ 去重（同查询串只留首条——不同系数可能映射到同一查询）+ 限长
  const chongfu = new Set<string>()
  const jieguo: XishuTishi[] = []
  for (const t of lie_lie) {
    if (chongfu.has(t.chaxun_ciyu)) {
      continue
    }
    chongfu.add(t.chaxun_ciyu)
    jieguo.push(t)
    if (jieguo.length >= shangxian) {
      break
    }
  }
  return jieguo
}

// ======================================================================
// 对外入口区
// ======================================================================

/** 生成判定系数包：汇总五路上游 + 生成检索提示词（纯汇总，零重算）。
 *
 *  汇总纪律：所有字段直接取上游既有输出；本模块唯一的"计算"是整体
 *  完成率（Σ实际 ÷ Σ基准，half-up 整数基点）与红行排序（差异率降序）。 */
export function shengcheng_xishu(shuru: XishuShuru): XishuBao {
  let hong_shu = 0
  let huang_shu = 0
  let wu_shu = 0
  const hong_hang: [string, string, number | null, string][] = []
  let he_shiji = 0
  let he_jizhun = 0
  let you_shuju = false
  if (shuru.chayi != null) {
    for (const x of shuru.chayi.xiang) {
      if (x.yujing === '红') {
        hong_shu += 1
        hong_hang.push([x.qijian, x.kemu, x.chalv_bps, x.fa])
      } else if (x.yujing === '黄') {
        huang_shu += 1
      } else if (x.yujing === '无') {
        wu_shu += 1
      }
      if (x.jizhun_fen != null && x.shiji_fen != null) {
        you_shuju = true
        he_shiji += x.shiji_fen
        he_jizhun += x.jizhun_fen
      }
    }
  }
  // 红行按差异率降序（本模块唯一重排；Array.sort 稳定，与 Python 一致）
  hong_hang.sort((a, b) => (b[2] ?? 0) - (a[2] ?? 0))
  // 整体完成率：half-up 整数基点；零基准/无数据交 null（缺数不臆造）
  const wanchenglv = you_shuju && he_jizhun > 0 ? bili_bps(he_shiji, he_jizhun) : null
  return {
    hong_shu, huang_shu, wu_shu,
    hong_hang_lie: hong_hang,
    wanchenglv_bps: wanchenglv,
    panduan_jielun: shuru.panduan != null ? shuru.panduan.panduan : null,
    shenpi: shuru.panduan != null ? shuru.panduan.shenpi : null,
    hexin_mokuai: shuru.jimu != null ? shuru.jimu.hexin_mokuai : null,
    bsc_zongfen: shuru.bsc != null ? shuru.bsc.zongfen : null,
    bsc_dengji: shuru.bsc != null ? shuru.bsc.dengji : null,
    zhenggai_gao_shu: shuru.zhenggai != null ? shuru.zhenggai.gao_shu : null,
    zhenggai_zhong_shu: shuru.zhenggai != null ? shuru.zhenggai.zhong_shu : null,
    tishi_lie: shengcheng_tishi(shuru.chayi, shuru.panduan, shuru.jimu, shuru.bsc),
  }
}
