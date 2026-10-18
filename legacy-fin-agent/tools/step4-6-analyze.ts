// ======================================================================
// 步骤4/5/6 分析工具层：单双环判定 → 双模型（积木+BSC） → 双维溯源
// ======================================================================
// 对应架构图正式版v1 的「单双环分析」「双模型分析」容器与「财务非财务双维度溯源分析」：
//   噪声门默认 25%（2500基点，2026-09-04 拍板）；BSC 默认权重 40/30/20/10、
//   达成率×权重不封顶五档；积木四模块（人力并入成本，T-21）。
//   LLM 语义归类站点（"llm语义归类（缺省纯规则）"）：判定工具内不内嵌调
//   模型——由外层智能体先调 fin_yuyi_guilei 得到归类枚举，再作为参数
//   传入 fin_panduan（结构上等价于 Python 的函数注入接缝，见裁决文档 #14）。
// ======================================================================

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { panduan_huanlu } from '../src/loop-decision.ts'
import { chai_jimu, cong_chayi_xiang } from '../src/building-blocks.ts'
import { jisuan_bsc } from '../src/bsc.ts'
import { jisuan_suyuan } from '../src/suyuan.ts'

/** 注册步骤4/5/6 全部工具（由插件入口调用）。 */
export function zhu_ce(ctx: Context): void {
  // ----------------------------------------------------------------------
  // fin_yuyi_guilei：LLM 语义归类（LLM 站点接缝——外层智能体自答）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_yuyi_guilei',
    description:
      '【步骤4前置·LLM语义归类】判断经营变更描述属于 结构变动 / 执行偏差 / 无法判断 之一。' +
      '这是"llm语义归类（缺省纯规则）"站点：请基于变更描述的语义判断（如 供应商更换/产能迭代/新增终止业务 ' +
      '→ 结构变动；费用超支/销量未达/利用率不足 → 执行偏差；拿不准 → 无法判断）。' +
      '归类结果随后传入 fin_panduan 的 yuyi_guilei 参数。护栏：归类只能升级为复核提示，不能直接触发双环。',
    parameters: {
      bianma: { type: 'json', required: true, description: '变更事项描述文本（字符串）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      // 纯枚举映射工具：把外层智能体的语义判断固化为合法枚举。
      // 缺省纯规则 = 不调用本工具直接不传 yuyi_guilei。
      const wenben = String(args.bianma)
      return { bianma: wenben, guilei: '无法判断' }
    },
  }))

  // ----------------------------------------------------------------------
  // fin_panduan：单双环五情形判定（步骤4）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_panduan',
    description:
      '【步骤4·单双环判定】五情形判定：噪声门默认25%(2500基点)——' +
      '差异率<门 且无登记=情形1不触发；<门但有登记=情形5复核提示(需人工)；' +
      '≥门且有结构变更登记=情形3双环/情形4混合纠错(均需人工审批,拟修订案下期生效)；' +
      '≥门无登记=情形2单环(整改经营行为,预算基准不动)。' +
      '显著性：|差异额|×10000 ≥ 显著阈×原标准成本额。' +
      '返回 { qingxing:1~5, panduan, jiuzheng, yiju, shenpi, beizhu }。',
    parameters: {
      shuru: {
        type: 'json',
        required: true,
        description:
          '{ chalv_bps: 差异率基点(null=基准0), guihua_zong_fen?: 规划总差异分(fin_chaifen产物), ' +
          'zhixing_zong_fen?: 执行总差异分, yuandan_cbf_fen?: 原标准成本额分(显著分母), ' +
          'jie_gou_biangeng?: bool(结构变更登记), bianma?: 变更描述文本, ' +
          'yuyi_guilei?: "结构变动"|"执行偏差"|"无法判断"(fin_yuyi_guilei产物) }',
      },
      menjian_bps: { type: 'number', description: '可选噪声门基点（默认2500）' },
      xianzhu_bps: { type: 'number', description: '可选显著阈基点（默认2500）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      const s = args.shuru
      // 外层智能体的枚举归类 → 模块接缝的函数注入（等价 Python yuyi_guilei 注入）
      const zhuru: ((wenben: string) => string) | null =
        typeof s.yuyi_guilei === 'string' && s.yuyi_guilei !== ''
          ? () => s.yuyi_guilei as string
          : null
      return panduan_huanlu(
        {
          chalv_bps: s.chalv_bps ?? null,
          guihua_zong_fen: s.guihua_zong_fen ?? null,
          zhixing_zong_fen: s.zhixing_zong_fen ?? null,
          yuandan_cbf_fen: s.yuandan_cbf_fen ?? null,
          jie_gou_biangeng: s.jie_gou_biangeng ?? false,
          bianma: typeof s.bianma === 'string' ? s.bianma : '',
          yuyi_guilei: zhuru,
        },
        args.menjian_bps ?? null,
        args.xianzhu_bps ?? null,
      )
    },
  }))

  // ----------------------------------------------------------------------
  // fin_jimu：积木四模块聚合（步骤5a，模型一）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_jimu',
    description:
      '【步骤5a·积木分析】把差异行按 收入/成本/费用/采购 四模块聚合（人力并入成本）：' +
      '模块净差额、F/A 从符号推（不信任行级 fa）、模块占比（分母=Σ|模块净差额|+|未归属|，' +
      'half-up）、D3 高亮=不利(A)模块中|净差额|最大者。' +
      '输入可直接用 fin_chayi 的 xiang 逐行数组（cong_chayi_xiang 适配已内置）。' +
      '未命中关键词的科目进未归属清单，交人工补映射。',
    parameters: {
      shuru: {
        type: 'json',
        required: true,
        description:
          '逐行 [{ qijian, kemu, chae_fen, fa, yujing, chalv_bps }]（fa∈F/A/—，yujing∈无/黄/红/—）',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      // 差异行直接喂入：行结构即 ChayiXiang 超集，适配器取六字段
      return chai_jimu((args.shuru as unknown[]).map((hang) => cong_chayi_xiang(hang as never)))
    },
  }))

  // ----------------------------------------------------------------------
  // fin_bsc：平衡计分卡（步骤5b，模型二）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_bsc',
    description:
      '【步骤5b·平衡记分卡】四维评估：维度得分=达成率×100（half-up，超100不封顶），' +
      '总分=Σ(得分×权重)÷100，等级五档（≥90优秀 ≥80良好 ≥70合格 ≥60预警 否则严重不合格）。' +
      '默认权重 财务40/客户30/内部流程20/学习成长10，自定义必须四项合计=100。' +
      '达成率单位基点（75%=7500），上限10000%防脏数据。',
    parameters: {
      caijing_bps: { type: 'number', required: true, description: '财务维度达成率基点' },
      kehu_bps: { type: 'number', required: true, description: '客户维度达成率基点' },
      neibu_bps: { type: 'number', required: true, description: '内部流程维度达成率基点' },
      xuexi_bps: { type: 'number', required: true, description: '学习成长维度达成率基点' },
      quanzhong: {
        type: 'json',
        description: '可选自定义权重 [财务,客户,内部流程,学习成长]，整数百分比，合计必须=100；缺省 [40,30,20,10]',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return jisuan_bsc({
        caijing_bps: args.caijing_bps,
        kehu_bps: args.kehu_bps,
        neibu_bps: args.neibu_bps,
        xuexi_bps: args.xuexi_bps,
        quanzhong: (args.quanzhong ?? undefined) as never,
      })
    },
  }))

  // ----------------------------------------------------------------------
  // fin_suyuan：经营变更双维溯源（步骤6）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_suyuan',
    description:
      '【步骤6·双向溯源】经营变更对 KPI 的影响：影响率=（变更后−变更前）÷原始预算×100% ' +
      '（带符号 half-up，基准null或≤0→该行不计），偏好×方向四象限定正负向作用，' +
      '占比分母=Σ|净影响率|，正向/负向 TOP3。KPI 名必须在 15 项清单内' +
      '（营收达成率/成本控制率/费用偏差率/毛利率/净利润率/销售利润率/资产周转率/资金周转率/' +
      '采购成本变动率/供应链履约率/产能利用率/交付周期/客户满意度/业务完成进度/异常事项数量）。',
    parameters: {
      shuru: {
        type: 'json',
        required: true,
        description: '逐行 [{ kpi_mingcheng, bianhua_qian, bianhua_hou, yuan_yusuan(可null) }]',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return jisuan_suyuan(args.shuru)
    },
  }))
}
