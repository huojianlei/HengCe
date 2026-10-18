// ======================================================================
// 步骤7/8 输出工具层：KPI 指标库 → 看板 → 整改 → 报告 → KB 检索提示词
// ======================================================================
// 对应架构图正式版v1 底部输出行：整改清单与预警 → 完整分析报告导出（PDF+JSON）
// → 可视化图表看板 → 自然语言提问。KB 站点（4 个"知识库检索提示词"）由
// xishu（判定系数包）生成检索词清单——本次交付"提示词生成"，检索执行
// 对接 kb2 检索库为后续工作（裁决 #13）。
// ======================================================================

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { jisuan_kpi } from '../src/kpi.ts'
import { shengcheng_zhenggai } from '../src/zhenggai.ts'
import { shengcheng_kanban } from '../src/kanban.ts'
import { shengcheng_xishu } from '../src/xishu.ts'
import { shengcheng_baogao_md } from '../src/baogao.ts'

/** 注册步骤7/8 全部工具（由插件入口调用）。 */
export function zhu_ce(ctx: Context): void {
  // ----------------------------------------------------------------------
  // fin_kpi：15 项 KPI 指标库（步骤1b，看板前置）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_kpi',
    description:
      '【KPI 指标库·15项】输入显式取数字段（缺数不填，【绝不臆造】），' +
      '输出 15 项指标（比率全为基点，1次=10000bps；交付周期=天、异常数=次直传）。' +
      '缺数或分母≤0 → 对应项 null 交人工。字段名见参数描述。' +
      '结果可直接喂 fin_kanban 的 kpi 入口与 fin_baogao。',
    parameters: {
      shuru: {
        type: 'json',
        required: true,
        description:
          'KpiShuru 对象，26 个可选取数字段（全 int|null）：' +
          'shouru_shiji_fen/shouru_yusuan_fen, kekong_chengben_shiji_fen/kekong_chengben_yusuan_fen, ' +
          'feiyong_shiji_fen/feiyong_yusuan_fen, maoli_fen/jingshui_fen/pbit_fen/ziben_zhanyong_fen, ' +
          'liudong_zichan_qichu_fen/liudong_zichan_qimo_fen, liudong_fuzhai_qichu_fen/liudong_fuzhai_qimo_fen, ' +
          'caigou_benqi_fen/caigou_shangqi_fen, shiji_chanchu/qianzai_channeng, dingdan_zongshu/lvyue_dingdan_shu, ' +
          'jiaofu_zhouqi_tian_shu, manyi_keshu/shoufang_keshu, jihua_yewu_liang/wancheng_yewu_liang, yichang_shijian_shu',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return jisuan_kpi((args.shuru ?? {}) as never)
    },
  }))

  // ----------------------------------------------------------------------
  // fin_zhenggai：整改清单（步骤8 计算）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_zhenggai',
    description:
      '【步骤8·整改数据底座】由判定指令 + 差异预警行 + 积木高亮 生成整改清单：' +
      '双环/混合→预算修订案(高·需审批)；单环→行为整改指令(中)；复核提示→人工复核(中)；' +
      '红→强制整改(高)；黄→关注整改(中)；高亮无同模块强制整改时追加关注项。' +
      '排序 高→中→低 稳定。三个上游参数均为对应工具的输出对象（可null）。',
    parameters: {
      chayi: { type: 'json', description: 'fin_chayi 输出（ChayiJieguo）' },
      jimu: { type: 'json', description: 'fin_jimu 输出（JimuJieguo）' },
      panduan: { type: 'json', description: 'fin_panduan 输出（PanDuanJieguo）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return shengcheng_zhenggai({
        chayi: (args.chayi ?? null) as never,
        jimu: (args.jimu ?? null) as never,
        panduan: (args.panduan ?? null) as never,
      })
    },
  }))

  // ----------------------------------------------------------------------
  // fin_kanban：看板数据接口（步骤7）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_kanban',
    description:
      '【步骤7·看板数据】八路上游（chayi/gundong/jimu/bsc/kpi/suyuan/panduan/zhenggai）' +
      '纯组装成看板结构数据（零重算）：核心对比表、预警汇总、饼图、折线（滚动趋势）、' +
      '热力矩阵、BSC/KPI/溯源/判定/整改块。缺料块输出空结构不抛错。' +
      '此即「可视化图表看板」的 JSON 数据源。',
    parameters: {
      chayi: { type: 'json', description: 'fin_chayi 输出' },
      gundong: { type: 'json', description: 'fin_gundong 输出' },
      jimu: { type: 'json', description: 'fin_jimu 输出' },
      bsc: { type: 'json', description: 'fin_bsc 输出' },
      kpi: { type: 'json', description: 'fin_kpi 输出' },
      suyuan: { type: 'json', description: 'fin_suyuan 输出' },
      panduan: { type: 'json', description: 'fin_panduan 输出' },
      zhenggai: { type: 'json', description: 'fin_zhenggai 输出' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return shengcheng_kanban({
        chayi: (args.chayi ?? null) as never,
        gundong: (args.gundong ?? null) as never,
        jimu: (args.jimu ?? null) as never,
        bsc: (args.bsc ?? null) as never,
        kpi: (args.kpi ?? null) as never,
        suyuan: (args.suyuan ?? null) as never,
        panduan: (args.panduan ?? null) as never,
        zhenggai: (args.zhenggai ?? null) as never,
      })
    },
  }))

  // ----------------------------------------------------------------------
  // fin_baogao：完整分析报告（步骤8 输出，md+JSON）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_baogao',
    description:
      '【步骤8·报告导出】把全部上游结果组装成 12 块结构（总览+八单元+三附表）' +
      '并渲染 Markdown（对应架构图"完整分析报告导出"——md 即报告文本、' +
      'JSON 结构数据由 fin_kanban 提供；PDF/Word 转换由外层另行处理，零依赖纪律不内嵌）。' +
      '缺料块自动置（缺料）占位。返回 { md }。',
    parameters: {
      ruku: { type: 'json', description: 'fin_daoru_csv 输出（DaoruJieguo）' },
      gundong: { type: 'json', description: 'fin_gundong 输出；多科目时传数组并另传 gundong_lie' },
      chayi: { type: 'json', description: 'fin_chayi 输出' },
      chaifen: { type: 'json', description: 'fin_chaifen 输出' },
      panduan: { type: 'json', description: 'fin_panduan 输出' },
      panduan_shuru: { type: 'json', description: 'fin_panduan 的输入快照（判定输入变量表用）' },
      jimu: { type: 'json', description: 'fin_jimu 输出' },
      bsc: { type: 'json', description: 'fin_bsc 输出' },
      suyuan: { type: 'json', description: 'fin_suyuan 输出' },
      kpi: { type: 'json', description: 'fin_kpi 输出' },
      zhenggai: { type: 'json', description: 'fin_zhenggai 输出' },
      kanban: { type: 'json', description: 'fin_kanban 输出（附表C 用）' },
      gundong_lie: {
        type: 'json',
        description: '多科目滚动二维表 [{科目名, GunDongJieguo}]（T-29#1；单科目直传 gundong 即可）',
      },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return {
        md: shengcheng_baogao_md({
          ruku: (args.ruku ?? null) as never,
          gundong: (args.gundong ?? null) as never,
          chayi: (args.chayi ?? null) as never,
          chaifen: (args.chaifen ?? null) as never,
          panduan: (args.panduan ?? null) as never,
          panduan_shuru: (args.panduan_shuru ?? null) as never,
          jimu: (args.jimu ?? null) as never,
          bsc: (args.bsc ?? null) as never,
          suyuan: (args.suyuan ?? null) as never,
          kpi: (args.kpi ?? null) as never,
          zhenggai: (args.zhenggai ?? null) as never,
          kanban: (args.kanban ?? null) as never,
          gundong_lie: (args.gundong_lie ?? null) as never,
        } as never),
      }
    },
  }))

  // ----------------------------------------------------------------------
  // fin_xishu：KB 检索提示词生成（4 个 KB 站点的统一出口）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_xishu',
    description:
      '【KB检索提示词·统一生成】从判定/积木/BSC/差异/整改 生成知识库检索词包' +
      '（≤8条去重）：判定结论→制度查询词、核心模块→领域查询词、BSC预警评级→绩效查询词、' +
      '红黄行→科目管控查询词。对应架构图 4 个"知识库检索提示词"站点；' +
      '拿到词条后【你】再去检索知识库（kb2 对接为后续工作）。',
    parameters: {
      chayi: { type: 'json', description: 'fin_chayi 输出' },
      panduan: { type: 'json', description: 'fin_panduan 输出' },
      jimu: { type: 'json', description: 'fin_jimu 输出' },
      bsc: { type: 'json', description: 'fin_bsc 输出' },
      zhenggai: { type: 'json', description: 'fin_zhenggai 输出' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return shengcheng_xishu({
        chayi: (args.chayi ?? null) as never,
        panduan: (args.panduan ?? null) as never,
        jimu: (args.jimu ?? null) as never,
        bsc: (args.bsc ?? null) as never,
        zhenggai: (args.zhenggai ?? null) as never,
      })
    },
  }))
}
