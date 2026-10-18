// ======================================================================
// 步骤1 录入链工具层：文件提取 → 报表解析 → 标准录入 → LLM 归一化接缝
// ======================================================================
// 对应架构图正式版v1 的「数据清洗与处理」容器：
//   用户输入原文件(word、PDF、csv) → 数据清洗提取 → 汇总画表；
//   ocr识别失败路径 = 算法层"不支持的文件类型/扫描件"报错，
//   解释错误并询问用户由外层智能体（LLM 站点）承担。
//
// LLM 归一化接缝的设计（见 docs/转写设计裁决.md 裁决 #11 修订）：
//   Python 里 llm_clean 把同步模型函数注入 zhineng_fenliu 内嵌循环；
//   TS 无阻塞 IO，且 dsh 的外层智能体循环本身就是可靠的"模型调用方"。
//   故拆成三件工具：fin_guiyihua_tishi（出提示词+直解尝试）、
//   外层智能体自己生成归一化文本、fin_daoru_csv（收口）+
//   fin_huanjue_jiaoyan（幻觉防线自检）。三条红线不变：
//   数字原样照抄 / 不豁免校验 / 可降级。
// ======================================================================

import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { daoru_csv } from '../src/data-ingest.ts'
import { jiequ_wenben } from '../src/file-extract.ts'
import { shitu_jiexi } from '../src/report-parse.ts'
import {
  gouzao_tishi,
  shuzi_yuansu_jiaoyan,
  zhijie_changshi,
} from '../src/llm-clean.ts'

/** 注册步骤1 全部工具（由插件入口调用）。 */
export function zhu_ce(ctx: Context): void {
  // ----------------------------------------------------------------------
  // fin_jiequ_wenben：文件字节 → 文本（word/PDF/csv/txt 四格式）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_jiequ_wenben',
    description:
      '【步骤1·录入前置】从上传文件提取文本。支持 csv/txt/docx/pdf；' +
      '扫描件图片 PDF 不支持（返回错误信息，请提示用户改用可复制文本的文件）。' +
      '参数：ming=文件名（含扩展名，用于分派）；zijie_base64=文件内容的 Base64 编码。' +
      '返回 { wenben, geshi }——wenben 为提取文本（docx 表格行已转 CSV 行），' +
      'geshi ∈ csv/txt/docx/pdf。后续应交给 fin_baobiao_jiexi 或 fin_daoru_csv。',
    parameters: {
      ming: { type: 'string', required: true, description: '文件名，含扩展名（如 预算.csv、快报.docx）' },
      zijie_base64: { type: 'string', required: true, description: '文件二进制内容的 Base64 编码' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      const zijie = Buffer.from(args.zijie_base64, 'base64')
      return jiequ_wenben(args.ming, new Uint8Array(zijie))
    },
  }))

  // ----------------------------------------------------------------------
  // fin_baobiao_jiexi：中式预算报告骨架 → 标准 8 列 CSV
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_baobiao_jiexi',
    description:
      '【步骤1·报表解析】把中式预算报告文本（含 预算表/实际表/业务量表/变更登记/行业对标 分节）' +
      '解析为标准 8 列 CSV。离线确定、不用模型。返回 { shibie, wenben_8lie, beizhu }：' +
      'shibie=false 表示不像标准报告（wenben_8lie 为空，请改走 fin_daoru_csv 直录或归一化路径）。',
    parameters: {
      wenben: { type: 'json', required: true, description: '报告全文文本（字符串）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return shitu_jiexi(String(args.wenben))
    },
  }))

  // ----------------------------------------------------------------------
  // fin_daoru_csv：标准 8 列 CSV → 清洗归档（录入收口）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_daoru_csv',
    description:
      '【步骤1·录入收口】把标准 8 列 CSV（表头：数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注）' +
      '清洗归档为四类标准记录（预算基础/实时经营/行业对标/经营变更）。' +
      '数值自动换算整数：元→分、%→基点、计数→个。' +
      '返回 { yusuan, shishi, hangye, biangeng, jujue }——jujue 为拒绝行清单（原因+原文），' +
      '【缺数必须向用户询问，不得臆造或填 0】。全文件表头不符/空文本会抛错。',
    parameters: {
      wenben: { type: 'json', required: true, description: '标准 8 列 CSV 全文（字符串，可含 BOM）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return daoru_csv(String(args.wenben))
    },
  }))

  // ----------------------------------------------------------------------
  // fin_guiyihua_tishi：归一化提示词 + 直解尝试（LLM 站点接缝·第一段）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_guiyihua_tishi',
    description:
      '【步骤1·智能归一化·第一段】脏表格（列序混乱/中文表头/粘贴文本）无法直解时使用。' +
      '返回 { zhijie_chenggong, zhijie_jieguo, tishi }：若 zhijie_chenggong=true 说明程序已直解成功，' +
      '直接采用 zhijie_jieguo，无需模型；否则【你自己】按 tishi（含标准表头与"数字原样照抄"铁律）' +
      '把原文转成标准 8 列 CSV，再调 fin_daoru_csv 收口；被拒时按拒绝原因自纠错重试。' +
      '幻觉自检用 fin_huanjue_jiaoyan。',
    parameters: {
      wenben: { type: 'json', required: true, description: '原始脏表格全文（字符串）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      const yuanwen = String(args.wenben)
      const zhijie = zhijie_changshi(yuanwen)
      // 与 Python 分流规则一致：入库>0 或仅表头的空文件 = 直解成功
      const zhijie_chenggong =
        zhijie.ruku_shu > 0 || zhijie.jujue.length === 0
      return {
        zhijie_chenggong,
        zhijie_jieguo: zhijie_chenggong ? zhijie : null,
        tishi: gouzao_tishi(yuanwen),
      }
    },
  }))

  // ----------------------------------------------------------------------
  // fin_huanjue_jiaoyan：幻觉防线（LLM 站点接缝·第二段，零容忍）
  // ----------------------------------------------------------------------
  ctx.tools.register(defineTool({
    name: 'fin_huanjue_jiaoyan',
    description:
      '【步骤1·幻觉防线】校验归一化文本里的每个数字是否都在原文出现过（全角/千分位/前导零等价）。' +
      '返回凭空数字清单：空数组=通过；非空=存在幻觉嫌疑，【整批拒绝、不得重试该输出】，' +
      '必须重新逐字核对原文数字后重新生成。',
    parameters: {
      yuanwen: { type: 'json', required: true, description: '原始文本（字符串）' },
      guiyi_wenben: { type: 'json', required: true, description: '归一化输出文本（字符串）' },
    },
    output: {
      schema: { type: 'json' },
      render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
    },
    async execute(args) {
      return shuzi_yuansu_jiaoyan(String(args.yuanwen), String(args.guiyi_wenben))
    },
  }))
}
