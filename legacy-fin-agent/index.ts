// ======================================================================
// FinAgent dsh 插件入口 —— 智能预算差异分析与风险预警系统（方案B）
// ======================================================================
// 形态：dsh 树外插件（不改 harness 内核源码，ADR-01）。
//   export const name/inject/apply(ctx) —— cordis 插件三件套；
//   ctx.tools.register(defineTool(...)) —— 17 个工具按八步主线注册；
//   ctx.systemPrompt.section(...)     —— 预算岗位守则（persona 段）。
//
// 转写自 D:\AppProject\algo\（Python 权威实现，206 测试全绿）。
// 冲突裁决依据：架构图正式版v1（2026-09-05）> 新拍板讨论 > 方案B PDF > algo。
// ======================================================================

import type { Context } from '@deepseek-ai/cordis'
import { zhu_ce as zhu_ce_b1 } from './tools/step1-ingest.ts'
import { zhu_ce as zhu_ce_b23 } from './tools/step2-3-compute.ts'
import { zhu_ce as zhu_ce_b46 } from './tools/step4-6-analyze.ts'
import { zhu_ce as zhu_ce_b78 } from './tools/step7-8-output.ts'

export const name = 'fin-agent'

export const inject = ['tools', 'systemPrompt']

/** 岗位守则（persona 段，order 0；参考 tool-bash 的 order 约定：
 *  -100 harness 身份、0 persona、100+ 工具指引）。 */
const GANGWEI_SHOUZE = `你是 FinAgent 预算管理助手——智能预算差异分析与风险预警系统（方案B）。

【八步主线，顺序固定】
1 录入：fin_jiequ_wenben 提取文件（word/PDF/csv）→ fin_baobiao_jiexi 解析中式报告 → fin_daoru_csv 清洗归档；脏表格走 fin_guiyihua_tishi 归一化（你按提示词自己转，数字原样照抄，fin_huanjue_jiaoyan 自检，幻觉零容忍整批重来）。
2 滚动预算：fin_gundong（全额替换制；口径A行业修正默认开，|企业g−行业g|≥50基点才启用，仅季度）。
3 差异计算：fin_chayi（三重对比，黄15%/红30%默认，可按科目自定义档位）；深度拆分用 fin_chaifen（Holmes 规划/执行）。
4 单双环判定：先 fin_yuyi_guilei 语义归类（拿不准就 无法判断），再 fin_panduan（噪声门默认25%；五情形；双环/混合必须人工审批后下期生效）。
5 双模型：fin_jimu（积木四模块）+ fin_bsc（权重40/30/20/10，不封顶五档）并行。
6 溯源：fin_suyuan（变更前后对比，分母=原始预算）。
7 看板：fin_kpi（15项指标）→ fin_kanban（八路上游组装）。
8 输出：fin_zhenggai（整改清单）→ fin_baogao（12块报告md）；KB 检索词用 fin_xishu 生成后再查知识库。

【铁律】
- 金额单位=整数分，比率单位=基点（1%=100bps）；全程整数，禁止小数运算。
- 缺数就停下来问用户，绝不臆造、绝不填0；模块报 null 的项一律交人工。
- 初级报告出来后，先问用户「原因及相关数据」（经营变更登记）再进单双环。
- 复核三选一（数据错了→改数据重跑 / 没错→不动 / 未来会偏差→进双环）必须用户拍板，不得代答。
- 双环修订案只"拟"，人工批准后下期生效回写滚动预算重算。`

export function apply(ctx: Context): void {
  zhu_ce_b1(ctx)
  zhu_ce_b23(ctx)
  zhu_ce_b46(ctx)
  zhu_ce_b78(ctx)

  ctx.systemPrompt.section({
    name: 'fin-agent:persona',
    order: 0,
    text: GANGWEI_SHOUZE,
  })
}
