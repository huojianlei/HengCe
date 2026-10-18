// ======================================================================
// 步骤2/3 计算工具层：滚动预算 → 多维差异 → Holmes 拆分
// ======================================================================
// 对应架构图正式版v1 的「滚动预算」「多维差异分析」两个容器：
//   汇总画表 → [用户输入自定义增长率 → 计算表格] → [阈值档位 → 计算表格]；
//   两个"程序计算表格"节点都是纯计算站点，不接 KB。
// ======================================================================

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import {
  GunDongShezhi,
  gengxin_gundong_yusuan,
} from '../src/rolling-budget.ts'
import { jisuan_chayi } from '../src/variance.ts'
import { chai_fen } from '../src/planning-split.ts'

/** 注册步骤2/3 全部工具（由插件入口调用）。 */
export function zhu_ce(ctx: Context): void {
  // ----------------------------------------------------------------------
  // fin_gundong：滚动预算（步骤2）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_gundong',
    description:
      '【步骤2·滚动预算】全额替换制滚动更新：届满期用实际数全额替换，' +
      '剩余期按最新增长率链法①逐期重算（逐期舍入接力）。' +
      '口径 A（默认）季度可叠加行业修正：|企业g−行业g|≥阈值(默认50基点)时启用，' +
      '月度永不生效。金额单位=分，增长率单位=基点（1%=100）。' +
      '返回逐期明细（届满=实际/剩余=重算）+ 初始总额/滚动总额/差额。',
    parameters: {
      guding_yusuan: {
        type: 'json',
        required: true,
        description: '年初固定预算，逐期数组 [{ qijian: "2026-Q1", jine_fen: 金额分 }, ...]',
      },
      shiji_shuju: {
        type: 'json',
        required: true,
        description: '已发生的实际数据，同上结构；期间必须存在于预算表',
      },
      shezhi: {
        type: 'json',
        required: true,
        description:
          '设置 { zhouqi: "月度"|"季度", zengzhanglv_jidian: 企业增长率基点, ' +
          'hangye_xiuzheng?: "A"|"B"（默认A）, hangye_zengzhanglv_jidian?: 行业增长率基点（口径A季度必填）, ' +
          'hangye_yuzhi_jidian?: 启用阈值（默认50） }',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      const shezhi = GunDongShezhi(
        args.shezhi.zhouqi,
        args.shezhi.zengzhanglv_jidian,
        {
          hangye_xiuzheng: args.shezhi.hangye_xiuzheng,
          hangye_zengzhanglv_jidian: args.shezhi.hangye_zengzhanglv_jidian ?? null,
          hangye_yuzhi_jidian: args.shezhi.hangye_yuzhi_jidian,
        },
      )
      return gengxin_gundong_yusuan(args.guding_yusuan, args.shiji_shuju, shezhi)
    },
  }))

  // ----------------------------------------------------------------------
  // fin_chayi：多维差异计算（步骤3a/3b）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_chayi',
    description:
      '【步骤3·多维差异】三重对比（初始预算 VS 滚动预算 VS 实际）：' +
      '基准=滚动额（缺省退化固定预算额），差额=实际−基准，差异率=|差额|÷基准，' +
      'F/A 标志（成本类正差=超支A；收入类正差=超额F；零差—），' +
      '预警配档默认 黄15%(1500基点)/红30%(3000基点)，可按科目自定义档位。' +
      '返回逐行明细 + 合计 + 预警计数。(期间,科目) 重复即抛错——防双计。',
    parameters: {
      shuru: {
        type: 'json',
        required: true,
        description:
          '逐行数组 [{ qijian, kemu, fangxiang: "成本类"|"收入类", ' +
          'chushi_fen, gundong_fen(可null), shiji_fen }]，金额单位分',
      },
      dang_lie: {
        type: 'json',
        description:
          '可选自定义档位 [{ ming_cheng, yan_se, yu_fen }]（阈值基点，降序配档）；' +
          '缺省 = 红3000/黄1500',
      },
      kemu_dang_lie: {
        type: 'json',
        description: '可选科目专属档位 { 科目名: 档位数组 }，优先于全局档位',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return jisuan_chayi(
        args.shuru,
        args.dang_lie ?? undefined,
        args.kemu_dang_lie ?? undefined,
      )
    },
  }))

  // ----------------------------------------------------------------------
  // fin_chaifen：Holmes 规划/执行拆分（步骤3c）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_chaifen',
    description:
      '【步骤3c·规划/执行拆分】把总差异拆成 不可控规划差异（修订标准−原标准）' +
      '与 可控执行差异（实际−修订标准），含价格/用量四细分与交叉残差，' +
      '总量恒等式自检（规划+执行=原标准总）。零除法纯乘减。' +
      '判定 fin_panduan 依赖本工具的 guihua_zong_fen / zhixing_zong_fen 作为线索。',
    parameters: {
      shuru: {
        type: 'json',
        required: true,
        description:
          '{ biaozhun_danjia_fen, biaozhun_yongliang, xiuding_danjia_fen, xiuding_yongliang, ' +
          'shiji_chanliang(>0), shiji_yongliang, shiji_chengben_fen }——单价分、用量单位个',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return chai_fen(args.shuru)
    },
  }))
}
