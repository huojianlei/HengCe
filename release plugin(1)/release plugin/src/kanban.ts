// ======================================================================
// kanban（看板数据接口）—— 方案B 步骤 7 的【纯结构化输出】聚合层
//（FR-13 计算前置）
// ======================================================================
// 转写自 D:\AppProject\algo\kanban.py（Python 版为唯一行为准绳；
// 对应测试 algo/tests/test_kanban.py → 插件 tests/kanban.test.ts）。
//
// 口径依据（权威文件，修改本模块前必读）：
//     docs/01-需求说明.md v2.0 §3 FR-13（用户拍板：与 UI 合并最后做；
//         计算侧先备"看板数据接口"纯结构化输出，[043]/T-28）
//     docs/proposal-full-extract.txt 行 80~88（看板五区清单：预算基准对比区/
//         风险预警高亮区/模型分析展示区/溯源分析区/整改闭环区）
//
// 模块定位（[043] 分层拆分后的职责边界）：
//     本模块是【纯组装层】——把上游各模块的既有输出（variance/滚动/积木/
//     BSC/KPI/溯源/判定/整改）打包成看板五区的结构化数据（对象/数组），
//     供未来 UI 层与 AI 层直接消费。本模块【不重算任何数值】、不含任何
//     界面/绘图逻辑——数值口径全部由上游模块负责，这里只做形态转换。
//
// 五区输出（对应完整版看板清单）：
//     ① 预算基准对比区 → duibi_biao（variance 逐行：固定/滚动/实际/差额/率/FA/预警）；
//     ② 风险预警高亮区 → yujing_huizong（四档预警计数）+ 各行 yujing 字段
//        + relitu（期间×科目 差异率矩阵）；
//     ③ 模型分析展示区 → bingtu（积木四模块+未归属占比）+ zhexian（滚动趋势）
//        + bsc_block（四维得分/总分/等级）+ kpi_block（15 项指标）；
//     ④ 溯源分析区 → suyuan_block（逐项影响+正负向 TOP3）；
//     ⑤ 整改闭环区 → zhenggai_block（整改清单+整改进度）+ panduan_block（判定）。
//
// 容错纪律（聚合层）：任一上游缺失（null）→ 对应块为空结构（空数组/空对象），
//     不抛错——端到端脚本任何阶段缺料都能拿到合法输出（看板显示"—"）。
//
// 鸭子类型接线（本批核心）：上游对象在 Python 里不 import、凭属性名消费；
//     TS 侧为每个上游定义【最小结构 interface】（字段名与所有权模块导出的
//     interface 逐字一致），TS 结构类型天然兼容——无需 import 上游模块。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     KanbanShuru         看板输入（八个上游结果，鸭子类型，均可 null）
//     KanbanShuju         看板数据（五区结构化输出）
//     shengcheng_kanban   生成看板数据（主函数，纯组装）
//     duibi_biao          预算基准对比区（variance 逐行对象数组）
//     yujing_huizong      风险预警高亮区（四档计数）
//     bingtu              积木差异占比饼图数据（四模块+未归属）
//     zhexian             滚动预算趋势折线数据（逐期）
//     relitu              风险热力图数据（期间×科目 差异率矩阵）
//     bsc_block           BSC 四维得分/总分/等级
//     kpi_block           KPI 15 项指标
//     suyuan_block        溯源分析区（逐项影响+TOP3）
//     panduan_block       判定结果区
//     zhenggai_block      整改闭环区（清单+进度）
//
// 与上下游的关系：
//     上游：variance / rolling_budget / building_blocks / bsc / kpi / suyuan /
//           loop_decision / zhenggai（全部鸭子类型契约——最小结构 interface）；
//     下游：UI 层（最后与看板界面一起做）、AI 层（报告生成读同一份数据）。
//
// 建立：2026-08-23（Python）｜ TS 转写：2026-09-05 ｜ FinAgent dsh 插件批次F
// ======================================================================

// ======================================================================
// 常量区
// ======================================================================

/** KPI 15 项：KpiJieguo 字段名 → 中文名（kpi_block 展示名；顺序 = 定稿 §8 清单，
 *  财务 9 项 + 非财务 6 项——顺序即看板 KPI 区的展示顺序，防漂移写死）。
 *  每项 = [KpiJieguo 字段名（ziming）, 中文展示名（mingcheng）]。 */
export const KPI_MING: readonly (readonly [string, string])[] = [
  ['yingshou_dachenglv_bps', '营收达成率'],
  ['chengben_kongzhilv_bps', '成本控制率'],
  ['feiyong_pianchalv_bps', '费用偏差率'],
  ['maolilv_bps', '毛利率'],
  ['jinglirunlv_bps', '净利润率'],
  ['xiaoshou_lirunlv_bps', '销售利润率'],
  ['zichan_zhouzhuanlv_bps', '资产周转率'],
  ['zijin_zhouzhuanlv_bps', '资金周转率'],
  ['caigou_chengben_bian_donglv_bps', '采购成本变动率'],
  ['gongyinglian_lvyuelv_bps', '供应链履约率'],
  ['channeng_liyonglv_bps', '产能利用率'],
  ['jiaofu_zhouqi_tian', '交付周期'],
  ['kehu_manyilv_bps', '客户满意度'],
  ['yewu_jindu_bps', '业务完成进度'],
  ['yichang_shijian_shu', '异常事项数量'],
]

// ======================================================================
// 鸭子类型上游接口区（最小结构形状，字段名与所有权模块导出 interface 逐字一致）
// ======================================================================

/** variance.ChayiXiang 的最小结构形状（鸭子类型）。
 *
 *  对比区需要【全字段透传】（键 = ChayiXiang 字段名），故这里列全 11 键——
 *  字段名与 variance.ts 导出的 ChayiXiang 逐字一致；热力图只取其中 3 键
 *  （qijian/kemu/chalv_bps）。 */
export interface ChayiXiangYang {
  readonly qijian: string              // 期间键（2026-01 / 2026-Q1）
  readonly kemu: string                // 指标科目名
  readonly fangxiang: string           // 方向（'成本类' / '收入类'）
  readonly chushi_fen: number          // 初始（固定）预算额（分）——三重对比第一列
  readonly gundong_fen: number | null  // 滚动/弹性预算额（分）——null 同固定
  readonly shiji_fen: number           // 实际发生额（分）——第三列
  readonly jizhun_fen: number          // 基准额（分）= 滚动（缺省退化初始）
  readonly chae_fen: number            // 差额（分）= 实际 − 基准（展示口径）
  readonly chalv_bps: number | null    // 差异率（基点，非负；基准 0 → null）
  readonly fa: string                  // 'F' 有利 / 'A' 不利 / '—' 零差额
  readonly yujing: string              // 档位名称（'无'/'黄'/'红'/'—'）
}

/** variance.ChayiJieguo 的最小结构形状：逐行 + 四档预警计数（预警汇总区来源）。 */
export interface ChayiJieguoYang {
  readonly xiang: readonly ChayiXiangYang[] // 逐项差异（顺序与输入一致）
  readonly hong_shu: number                 // 红色预警行数
  readonly huang_shu: number                // 黄色预警行数
  readonly wu_shu: number                   // 无预警行数
  readonly wufa_shu: number                 // 无法定级行数（基准 0 → '—'）
}

/** rolling_budget.DanqiJieguo 的最小结构形状（折线逐期四键透传）。 */
export interface DanqiJieguoYang {
  readonly qijian: string            // 期间键（同输入）
  readonly zhuangtai: string         // '已届满' / '剩余期'
  readonly shuzhi_fen: number        // 重算后的值（分）：届满期=实际、剩余期=重算
  readonly chushi_yusuan_fen: number // 该期初始预算金额（分）
}

/** rolling_budget.GunDongJieguo 的最小结构形状：须有 .qijian_mingxi（折线来源）。 */
export interface GunDongJieguoYang {
  readonly qijian_mingxi: readonly DanqiJieguoYang[] // 逐期结果（顺序与输入一致）
}

/** building_blocks.MokuaiXiang 的最小结构形状（饼图模块五键透传）。 */
export interface MokuaiXiangYang {
  readonly mokuai: string             // 模块名（收入/成本/费用/采购模块）
  readonly chae_fen: number           // 模块差异额 = Σ该模块各行差额（净额）
  readonly fa: string                 // 模块级 F/A（按模块方向从差额符号推得）
  readonly zhanbi_bps: number | null  // 占比（基点）；分母 0 → null
  readonly hang_shu: number           // 归属行数（明细行数，便于下钻）
}

/** building_blocks.JimuJieguo 的最小结构形状（饼图来源：模块列/未归属/净合计/高亮）。 */
export interface JimuJieguoYang {
  readonly mokuai_lie: readonly MokuaiXiangYang[] // 四模块结果（顺序固定）
  readonly weiguishu_lie: readonly unknown[]      // 未归属行（映射不中，交人工）
  readonly jing_heji_fen: number                  // 净总差异 = Σ全部行差额（正负可抵消）
  readonly hexin_mokuai: string | null            // 核心问题模块（全部有利时 null）
  readonly weiguishu_zhanbi_bps: number | null    // 未归属占比（基点）
}

/** bsc.BscJieguo 的最小结构形状（BSC 块四维得分/权重/总分/等级透传）。 */
export interface BscJieguoYang {
  readonly caijing_defen: number  // 财务维度得分（整数分，不封顶）
  readonly kehu_defen: number     // 客户维度得分
  readonly neibu_defen: number    // 内部流程维度得分
  readonly xuexi_defen: number    // 学习成长维度得分
  readonly quanzhong: readonly [number, number, number, number] // 生效权重（回显）
  readonly zongfen: number        // 总分 = Σ（权重 × 维度得分）÷ 100，half-up
  readonly dengji: string         // 等级（优秀/良好/合格/预警/严重不合格）
}

/** kpi.KpiJieguo 的最小结构形状（15 项指标，字段名与 kpi.py 逐字一致；缺数 null）。 */
export interface KpiJieguoYang {
  readonly yingshou_dachenglv_bps: number | null            // 营收达成率
  readonly chengben_kongzhilv_bps: number | null            // 成本控制率
  readonly feiyong_pianchalv_bps: number | null             // 费用偏差率（可负）
  readonly maolilv_bps: number | null                       // 毛利率
  readonly jinglirunlv_bps: number | null                   // 净利润率
  readonly xiaoshou_lirunlv_bps: number | null              // 销售利润率
  readonly zichan_zhouzhuanlv_bps: number | null            // 资产周转率（次→基点）
  readonly zijin_zhouzhuanlv_bps: number | null             // 资金周转率（次→基点）
  readonly caigou_chengben_bian_donglv_bps: number | null   // 采购成本变动率（可负）
  readonly gongyinglian_lvyuelv_bps: number | null          // 供应链履约率
  readonly channeng_liyonglv_bps: number | null             // 产能利用率
  readonly jiaofu_zhouqi_tian: number | null                // 交付周期（天）
  readonly kehu_manyilv_bps: number | null                  // 客户满意度
  readonly yewu_jindu_bps: number | null                    // 业务完成进度
  readonly yichang_shijian_shu: number | null               // 异常事项数量（次）
}

/** suyuan.SuyuanXiang 的最小结构形状（溯源逐项五键透传）。 */
export interface SuyuanXiangYang {
  readonly kpi_mingcheng: string       // KPI 名（15 项清单之一）
  readonly yingxianglv_bps: number | null // 影响率（基点，带符号）
  readonly shuzhi_fangxiang: string    // 数值方向（上升/下降/持平）
  readonly zuoyong: string             // 作用方向（正向作用/负向作用/无作用）
  readonly zhanbi_bps: number | null   // 影响占比（基点；分母 0 → null）
}

/** suyuan.SuyuanJieguo 的最小结构形状（溯源块来源）。 */
export interface SuyuanJieguoYang {
  readonly xiang: readonly SuyuanXiangYang[] // 逐项结果（顺序 = 输入顺序）
  readonly zhengxiang_top3: readonly string[] // 正向作用 KPI 名 TOP3
  readonly fuxiang_top3: readonly string[]    // 负向作用 KPI 名 TOP3
  readonly yingxiang_fenmu_bps: number        // 影响占比分母 = Σ|各 KPI 净影响率|
}

/** loop_decision.PanDuanJieguo 的最小结构形状（判定块三键透传）。 */
export interface PanDuanJieguoYang {
  readonly qingxing: number // 情形编号（1~5，定稿 §4.4 行号）
  readonly panduan: string  // 判定取值（'不触发'/'单环'/'双环'/'混合纠错模式'/'复核提示'）
  readonly shenpi: boolean  // 是否必须人工审批（双环/混合纠错模式 true）
}

/** zhenggai.ZhenggaiXiang 的最小结构形状（整改清单逐项八键透传）。 */
export interface ZhenggaiXiangYang {
  readonly leixing: string       // 整改类型（预算修订案/行为整改指令/人工复核/强制整改/关注整改）
  readonly youxianji: string     // 优先级（高/中/低）
  readonly zeren_mokuai: string  // 责任模块（四模块名/未归属/无）
  readonly kemu: string          // 科目名（差异行来源；判定项为 ''）
  readonly qijian: string        // 期间键（差异行来源；判定项为 ''）
  readonly miaoshu: string       // 结构化描述（无自然语言——文案由 AI 层起草）
  readonly shenpi: boolean       // 是否需人工审批（预算修订案必 true）
  readonly zhuangtai: string     // 进度状态（待整改/进行中/已完成）
}

/** zhenggai.ZhenggaiJieguo 的最小结构形状（整改块来源：清单+七计数）。 */
export interface ZhenggaiJieguoYang {
  readonly qingdan: readonly ZhenggaiXiangYang[] // 整改项列表（高 → 中 → 低）
  readonly gao_shu: number                       // 高优先级计数
  readonly zhong_shu: number                     // 中优先级计数
  readonly di_shu: number                        // 低优先级计数
  readonly zong_shu: number                      // 清单总数
  readonly daizhenggai_shu: number               // 待整改计数
  readonly jinxingzhong_shu: number              // 进行中计数
  readonly wancheng_shu: number                  // 已完成计数
}

// ======================================================================
// 数据结构区（frozen dataclass → readonly interface + 对象字面量）
// ======================================================================

/** 看板输入：八个上游结果对象（鸭子类型；null/缺省 = 该块缺料）。
 *
 *  字段说明：
 *      chayi:   variance.ChayiJieguo（对比表/热力图/预警汇总来源）。
 *      gundong: rolling_budget.GunDongJieguo（折线来源）。
 *      jimu:    building_blocks.JimuJieguo（饼图来源）。
 *      bsc:     bsc.BscJieguo（BSC 块来源）。
 *      kpi:     kpi.KpiJieguo（KPI 块来源）。
 *      suyuan:  suyuan.SuyuanJieguo（溯源块来源）。
 *      panduan: loop_decision.PanDuanJieguo（判定块来源）。
 *      zhenggai: zhenggai.ZhenggaiJieguo（整改块来源）。
 *
 *  Python dataclass 八字段均缺省 None；TS 侧以可选字段 + null 表达，
 *  调用方按 Python 关键字风格传子集（如 `{ chayi, jimu }`）。 */
export interface KanbanShuru {
  readonly chayi?: ChayiJieguoYang | null
  readonly gundong?: GunDongJieguoYang | null
  readonly jimu?: JimuJieguoYang | null
  readonly bsc?: BscJieguoYang | null
  readonly kpi?: KpiJieguoYang | null
  readonly suyuan?: SuyuanJieguoYang | null
  readonly panduan?: PanDuanJieguoYang | null
  readonly zhenggai?: ZhenggaiJieguoYang | null
}

// —— 五区输出的行/块形状（KanbanShuju 内部结构；Python list[dict]/dict 的具名化） ——

/** ① 对比表行：variance.ChayiXiang 全字段透传（11 键，UI 层翻译成中文列名）。 */
export interface DuibiXing {
  readonly qijian: string             // 期间键
  readonly kemu: string               // 科目名
  readonly fangxiang: string          // 方向（成本类/收入类）
  readonly chushi_fen: number         // 初始（固定）预算（分）
  readonly gundong_fen: number | null // 滚动预算（分）
  readonly shiji_fen: number          // 实际额（分）
  readonly jizhun_fen: number         // 基准额（分）
  readonly chae_fen: number           // 差额（分，展示口径）
  readonly chalv_bps: number | null   // 差异率（基点）
  readonly fa: string                 // F/A/—（有利/不利/零差额）
  readonly yujing: string             // 预警档名
}

/** ③ 饼图：积木四模块 + 未归属 + 净合计 + 高亮。 */
export interface BingtuShuju {
  readonly mokuai_lie: readonly {
    readonly mokuai: string          // 模块名
    readonly chae_fen: number        // 模块差异额（分，净额）
    readonly fa: string              // 模块级 F/A
    readonly zhanbi_bps: number | null // 占比（基点）
    readonly hang_shu: number        // 归属行数
  }[]
  readonly weiguishu: { readonly zhanbi_bps: number | null; readonly hang_shu: number }
  // 未归属：占比（基点）+ 行数（映射不中——交人工补映射的展示出口）
  readonly jing_heji_fen: number     // 净合计 = Σ全部行差额（含未归属）
  readonly hexin_mokuai: string | null // 核心问题模块（高亮；全部有利时 null）
}

/** ③ 折线行：滚动预算逐期（届满=实际、剩余=重算）。 */
export interface ZhexianXing {
  readonly qijian: string            // 期间键
  readonly zhuangtai: string         // '已届满' / '剩余期'
  readonly shuzhi_fen: number        // 展示值（分）
  readonly chushi_yusuan_fen: number // 初始预算（分）
}

/** ③ KPI 展示行：中文名 + 值（缺数 null）。 */
export interface KpiXing {
  readonly mingcheng: string   // 中文名（KPI_MING 顺序）
  readonly zhi: number | null  // 指标值（缺数 null——显示"无"，不填 0）
}

/** ⑤ 整改闭环区：清单逐项 + 优先级与进度计数（键与 zhenggai.ZhenggaiJieguo 一致）。 */
export interface ZhenggaiKuai {
  readonly qingdan: readonly ZhenggaiXiangYang[] // 整改清单（高 → 中 → 低）
  readonly gao_shu: number           // 高优先级计数
  readonly zhong_shu: number         // 中优先级计数
  readonly di_shu: number            // 低优先级计数
  readonly zong_shu: number          // 清单总数
  readonly daizhenggai_shu: number   // 待整改计数
  readonly jinxingzhong_shu: number  // 进行中计数
  readonly wancheng_shu: number      // 已完成计数
}

/** 看板数据：五区结构化输出（全部对象/数组，零 UI、零重算）。
 *
 *  字段说明（各区结构见模块头"五区输出"与上方各 Xing/Kuai interface）：
 *      duibi_biao:     对比表行数组（variance.ChayiXiang 全字段透传）。
 *      yujing_huizong: {hong_shu, huang_shu, wu_shu, wufa_shu}。
 *      bingtu:         {mokuai_lie, weiguishu, jing_heji_fen, hexin_mokuai}。
 *      zhexian:        折线行数组（滚动逐期）。
 *      relitu:         {qijian_lie, kemu_lie, juzhen}（差异率矩阵，缺组合 null）。
 *      bsc_block:      {caijing_defen, kehu_defen, neibu_defen, xuexi_defen,
 *                       quanzhong, zongfen, dengji}。
 *      kpi_block:      {mingcheng, zhi} 15 项（缺数 null）。
 *      suyuan_block:   {xiang, zhengxiang_top3, fuxiang_top3, yingxiang_fenmu_bps}。
 *      panduan_block:  {panduan, qingxing, shenpi}。
 *      zhenggai_block: {qingdan, gao_shu, zhong_shu, di_shu, zong_shu,
 *                       daizhenggai_shu, jinxingzhong_shu, wancheng_shu}。 */
export interface KanbanShuju {
  readonly duibi_biao: readonly DuibiXing[]
  readonly yujing_huizong: {
    readonly hong_shu: number   // 红色预警行数
    readonly huang_shu: number  // 黄色预警行数
    readonly wu_shu: number     // 无预警行数
    readonly wufa_shu: number   // 无法定级行数
  }
  readonly bingtu: BingtuShuju
  readonly zhexian: readonly ZhexianXing[]
  readonly relitu: {
    readonly qijian_lie: string[]       // 期间轴（排序去重）
    readonly kemu_lie: string[]         // 科目轴（排序去重）
    readonly juzhen: (number | null)[][] // 差异率矩阵（行=期间、列=科目；缺组合 null）
  }
  readonly bsc_block: {
    readonly caijing_defen: number | null  // 财务维度得分
    readonly kehu_defen: number | null     // 客户维度得分
    readonly neibu_defen: number | null    // 内部流程维度得分
    readonly xuexi_defen: number | null    // 学习成长维度得分
    readonly quanzhong: readonly [number, number, number, number] | null // 生效权重
    readonly zongfen: number | null        // 总分
    readonly dengji: string | null         // 等级
  }
  readonly kpi_block: readonly KpiXing[]
  readonly suyuan_block: {
    readonly xiang: readonly SuyuanXiangYang[]  // 逐项影响
    readonly zhengxiang_top3: readonly string[] // 正向 TOP3
    readonly fuxiang_top3: readonly string[]    // 负向 TOP3
    readonly yingxiang_fenmu_bps: number        // 影响占比分母（基点）
  }
  readonly panduan_block: {
    readonly panduan: string | null  // 判定取值
    readonly qingxing: number | null // 情形编号
    readonly shenpi: boolean | null  // 审批标志
  }
  readonly zhenggai_block: ZhenggaiKuai
}

// ======================================================================
// 各区组装函数区（每区一个函数——只做形态转换，不重算）
// ======================================================================

/** Python f-string `{x!r}`（repr）的 TS 对应：字符串/对象走 JSON 化，
 *  其余 String 化。仅用于报错文案里的非法值回显。 */
function _repr(x: unknown): string {
  if (typeof x === 'string') return JSON.stringify(x)
  if (typeof x === 'object' && x !== null) return JSON.stringify(x)
  return String(x)
}

/** ① 预算基准对比区 + ② 预警汇总：variance 逐行透传 + 四档计数。
 *
 *  返回 { duibi, huizong }：duibi = 对比表行（11 键全字段透传，
 *  UI/AI 层直接消费）；huizong = 四档预警计数（键与 ChayiJieguo 四档
 *  字段同名——hong/huang/wu/wufa_shu，看板直接读）。 */
function _zhuang_duibi(chayi: ChayiJieguoYang | null | undefined): {
  duibi: DuibiXing[]
  huizong: KanbanShuju['yujing_huizong']
} {
  // 容错：上游缺省 → 空表 + 全零计数（合法输出，不抛错）
  if (chayi == null) {
    return {
      duibi: [],
      huizong: { hong_shu: 0, huang_shu: 0, wu_shu: 0, wufa_shu: 0 },
    }
  }
  const duibi: DuibiXing[] = []
  for (const x of chayi.xiang) {
    // 全字段透传（键 = ChayiXiang 字段名）——组装层不重算、不失真
    duibi.push({
      qijian: x.qijian, kemu: x.kemu, fangxiang: x.fangxiang,
      chushi_fen: x.chushi_fen, gundong_fen: x.gundong_fen,
      shiji_fen: x.shiji_fen, jizhun_fen: x.jizhun_fen,
      chae_fen: x.chae_fen, chalv_bps: x.chalv_bps,
      fa: x.fa, yujing: x.yujing,
    })
  }
  // 四档计数来自 variance.ChayiJieguo 的四档字段——直接透传
  const huizong = {
    hong_shu: chayi.hong_shu,
    huang_shu: chayi.huang_shu,
    wu_shu: chayi.wu_shu,
    wufa_shu: chayi.wufa_shu,
  }
  return { duibi, huizong }
}

/** ③ 模型分析区·饼图：积木四模块 + 未归属（占比直接透传）。
 *
 *  缺料 → 空模块列 + 未归属占位（null/0）+ 净合计 0 + 高亮 null。 */
function _zhuang_bingtu(jimu: JimuJieguoYang | null | undefined): BingtuShuju {
  if (jimu == null) {
    return {
      mokuai_lie: [],
      weiguishu: { zhanbi_bps: null, hang_shu: 0 },
      jing_heji_fen: 0,
      hexin_mokuai: null,
    }
  }
  return {
    // 模块列五键逐项透传（顺序 = 积木 MOKUAI_SHUNXU，UI 按序取扇区）
    mokuai_lie: jimu.mokuai_lie.map((x) => ({
      mokuai: x.mokuai, chae_fen: x.chae_fen, fa: x.fa,
      zhanbi_bps: x.zhanbi_bps, hang_shu: x.hang_shu,
    })),
    // 未归属 = 占比 + 行数（Python len(jimu.weiguishu_lie)）
    weiguishu: {
      zhanbi_bps: jimu.weiguishu_zhanbi_bps,
      hang_shu: jimu.weiguishu_lie.length,
    },
    jing_heji_fen: jimu.jing_heji_fen, // 净合计透传（正负可抵消的展示口径）
    hexin_mokuai: jimu.hexin_mokuai,   // 高亮模块透传（全部有利 → null）
  }
}

/** ③ 模型分析区·折线：滚动预算逐期透传（缺料 → 空数组）。 */
function _zhuang_zhexian(gundong: GunDongJieguoYang | null | undefined): ZhexianXing[] {
  if (gundong == null) {
    return []
  }
  // 逐期四键透传——届满期取实际、剩余期取重算值（口径在滚动模块）
  return gundong.qijian_mingxi.map((t) => ({
    qijian: t.qijian, zhuangtai: t.zhuangtai,
    shuzhi_fen: t.shuzhi_fen, chushi_yusuan_fen: t.chushi_yusuan_fen,
  }))
}

/** ② 风险热力图：期间 × 科目 的差异率矩阵（variance 行 → 二维表）。
 *
 *  矩阵取值 = chalv_bps（缺组合 null）——热力着色由 UI 层按预警档完成。
 *  期间/科目去重排序（Python sorted(set(...))：字符串码点序，语义稳定）。 */
function _zhuang_relitu(chayi: ChayiJieguoYang | null | undefined): KanbanShuju['relitu'] {
  // 容错：无差异行 → 三空轴（UI 显示"无"）
  if (chayi == null || chayi.xiang.length === 0) {
    return { qijian_lie: [], kemu_lie: [], juzhen: [] }
  }
  // 期间/科目去重排序（Set 去重 + 默认码点序 = Python sorted(set)）
  const qijian_lie = [...new Set(chayi.xiang.map((x) => x.qijian))].sort()
  const kemu_lie = [...new Set(chayi.xiang.map((x) => x.kemu))].sort()
  // 指针字典：Python dict[(期间, 科目)] 的 TS 对应——'\u0000' 连接做
  // 无碰撞编码（期间/科目都不含 \u0000，键唯一性等价于二元组唯一性）
  const zhizhen = new Map<string, number | null>()
  for (const x of chayi.xiang) {
    zhizhen.set(`${x.qijian}\u0000${x.kemu}`, x.chalv_bps)
  }
  // 行 = 期间、列 = 科目；缺组合 → null（UI 显示"无"，不填 0 不臆造）
  const juzhen = qijian_lie.map((q) =>
    kemu_lie.map((k) => zhizhen.get(`${q}\u0000${k}`) ?? null),
  )
  return { qijian_lie, kemu_lie, juzhen }
}

/** ③ 模型分析区·BSC：四维得分/权重/总分/等级透传（缺料 → 七键全 null）。 */
function _zhuang_bsc(bsc: BscJieguoYang | null | undefined): KanbanShuju['bsc_block'] {
  if (bsc == null) {
    return {
      caijing_defen: null, kehu_defen: null, neibu_defen: null,
      xuexi_defen: null, quanzhong: null, zongfen: null, dengji: null,
    }
  }
  return {
    caijing_defen: bsc.caijing_defen, kehu_defen: bsc.kehu_defen,
    neibu_defen: bsc.neibu_defen, xuexi_defen: bsc.xuexi_defen,
    quanzhong: bsc.quanzhong, // 权重回显（默认 40/30/20/10 或自定义）
    zongfen: bsc.zongfen,     // 总分（half-up 整数，口径在 bsc 模块）
    dengji: bsc.dengji,       // 五档等级
  }
}

/** ③ 模型分析区·KPI：15 项指标（字段名 → 中文名，缺数 null 透传）。
 *
 *  缺料 → 15 项照列、值全 null——看板 KPI 区显示"无"的数据基础。 */
function _zhuang_kpi(kpi: KpiJieguoYang | null | undefined): KpiXing[] {
  if (kpi == null) {
    return KPI_MING.map(([, ming]) => ({ mingcheng: ming, zhi: null }))
  }
  // Python getattr(kpi, ziming)：按 KPI_MING 的字段名清单逐项取值
  //（鸭子类型容忍假对象缺字段——缺 → null，与"缺数显示无"同口径）
  return KPI_MING.map(([ziming, ming]) => ({
    mingcheng: ming,
    zhi: (kpi as Record<string, number | null>)[ziming] ?? null,
  }))
}

/** ④ 溯源分析区：逐项影响 + 正负向 TOP3（透传；缺料 → 空结构 + 分母 0）。 */
function _zhuang_suyuan(suyuan: SuyuanJieguoYang | null | undefined): KanbanShuju['suyuan_block'] {
  if (suyuan == null) {
    return {
      xiang: [], zhengxiang_top3: [], fuxiang_top3: [],
      yingxiang_fenmu_bps: 0,
    }
  }
  return {
    // 逐项五键透传（顺序 = 溯源输入顺序）
    xiang: suyuan.xiang.map((x) => ({
      kpi_mingcheng: x.kpi_mingcheng, yingxianglv_bps: x.yingxianglv_bps,
      shuzhi_fangxiang: x.shuzhi_fangxiang, zuoyong: x.zuoyong,
      zhanbi_bps: x.zhanbi_bps,
    })),
    // TOP3 复制出新数组——隔离上游引用，保证看板数据 JSON 往返一致
    zhengxiang_top3: [...suyuan.zhengxiang_top3],
    fuxiang_top3: [...suyuan.fuxiang_top3],
    yingxiang_fenmu_bps: suyuan.yingxiang_fenmu_bps,
  }
}

/** 判定结果区：判定/情形/审批标志（透传；缺料 → 三键全 null）。 */
function _zhuang_panduan(panduan: PanDuanJieguoYang | null | undefined): KanbanShuju['panduan_block'] {
  if (panduan == null) {
    return { panduan: null, qingxing: null, shenpi: null }
  }
  // Python getattr(panduan, 'x', None)：三键逐项透传（鸭子缺属性 → null）
  return {
    panduan: panduan.panduan,
    qingxing: panduan.qingxing,
    shenpi: panduan.shenpi,
  }
}

/** ⑤ 整改闭环区：整改清单（逐项透传）+ 优先级与进度计数（缺料 → 空清单全零）。 */
function _zhuang_zhenggai(zhenggai: ZhenggaiJieguoYang | null | undefined): ZhenggaiKuai {
  if (zhenggai == null) {
    return {
      qingdan: [], gao_shu: 0, zhong_shu: 0, di_shu: 0,
      zong_shu: 0, daizhenggai_shu: 0, jinxingzhong_shu: 0, wancheng_shu: 0,
    }
  }
  return {
    // 清单逐项八键透传（AI 层文案起草的输入——透传完整性即验收标准）
    qingdan: zhenggai.qingdan.map((x) => ({
      leixing: x.leixing, youxianji: x.youxianji,
      zeren_mokuai: x.zeren_mokuai, kemu: x.kemu, qijian: x.qijian,
      miaoshu: x.miaoshu, shenpi: x.shenpi, zhuangtai: x.zhuangtai,
    })),
    // 七计数透传（优先级三档 + 总数 + 进度三态）
    gao_shu: zhenggai.gao_shu, zhong_shu: zhenggai.zhong_shu,
    di_shu: zhenggai.di_shu, zong_shu: zhenggai.zong_shu,
    daizhenggai_shu: zhenggai.daizhenggai_shu,
    jinxingzhong_shu: zhenggai.jinxingzhong_shu,
    wancheng_shu: zhenggai.wancheng_shu,
  }
}

// ======================================================================
// 对外接口区（唯一的组装入口）
// ======================================================================

/** 生成看板数据（方案B 步骤 7 的计算前置；纯组装函数，不重算）。
 *
 *  参数：shuru —— KanbanShuru（八个上游结果，均可缺省 null）。
 *
 *  返回：KanbanShuju（五区结构化输出；缺料块为空结构，不抛错）。
 *
 *  门禁（Python isinstance 门禁逐字保留）：非 KanbanShuru 形状 → TypeError。
 *  组装顺序与 Python 一致：对比/汇总 → 饼图 → 折线 → 热力 → BSC → KPI
 *  → 溯源 → 判定 → 整改——各区互不依赖，任一缺省不影响其他区。 */
export function shengcheng_kanban(shuru: KanbanShuru): KanbanShuju {
  if (typeof shuru !== 'object' || shuru === null || Array.isArray(shuru)) {
    throw new TypeError(`输入必须是 KanbanShuru：${_repr(shuru)}`)
  }

  // ①② 对比表 + 预警汇总（同一 variance 来源拆两份输出）
  const { duibi, huizong } = _zhuang_duibi(shuru.chayi)
  return {
    duibi_biao: duibi,
    yujing_huizong: huizong,
    bingtu: _zhuang_bingtu(shuru.jimu),       // ③ 饼图（积木）
    zhexian: _zhuang_zhexian(shuru.gundong),  // ③ 折线（滚动）
    relitu: _zhuang_relitu(shuru.chayi),      // ② 热力图（variance 派生）
    bsc_block: _zhuang_bsc(shuru.bsc),        // ③ BSC
    kpi_block: _zhuang_kpi(shuru.kpi),        // ③ KPI 15 项
    suyuan_block: _zhuang_suyuan(shuru.suyuan), // ④ 溯源
    panduan_block: _zhuang_panduan(shuru.panduan), // ⑤ 判定
    zhenggai_block: _zhuang_zhenggai(shuru.zhenggai), // ⑤ 整改闭环
  }
}
