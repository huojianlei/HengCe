// ======================================================================
// 报表模板解析层 —— 方案B 步骤 1 前置二段：把"长得像预算报告"的文本
// 还原成标准 8 列。
// 转写自 D:\AppProject\algo\report_parse.py（Python 版为唯一行为准绳）。
// ======================================================================
//
// 新增口径（用户指令 2026-08-30："我们的目标是把预算报告输入进去，预算报告
// 肯定不长【平表】那个样子……预算数据和真实数据，都放进去，分表放"）：
// 真实预算报告是"文档"不是"数据表"——报告头 + 编制说明 + 分节小标题 +
// "科目×期间"矩阵表（预算一张表、实际一张表）+ 登记表（变更/业务量/行业对标）。
// 本模块把这种骨架【离线、确定性地】解析回标准 8 列文本，接在 file_extract
// 之后、与 llm_clean 智能分流形成"两级识别"：
//
//     文件 → file_extract（解包成文本行）
//          → report_parse（像预算报告？→ 模板解析成 8 列）──命中──▶ data_ingest
//                        └────不像（交回分流）──▶ llm_clean（直解/LLM 归一化）▶ data_ingest
//
// 模板骨架假设（中式预算报告的常见排法，2026-08-30 与用户对齐）：
//     报告头：公司/报告名称（含"XXXX年度"字样）、编制单位、编制日期；
//     分节标题：短行，含"预算表/实际/业务量/变更…登记/行业对标"+"表"字，
//               常带"（单位：元）"注记；
//     预算/实际表：首列"科目（项目）"，其余列为期间列（可混"合计""完成率"
//                 等非期间列），可有"合计"行；
//     业务量表：科目,统计期间,数量,单位；变更登记表：变更事项,发生期间,
//               登记时间,说明；行业对标表：指标,数值,单位,备注。
//
// 职责边界（与 llm_clean 的分界——两级识别各管一段）：
//     本模块只吃【文本形态】、只认【模板骨架】：识别不了一点就返回
//     shibie=false，调用方交回 llm_clean 智能分流（直解或 LLM 归一化）——
//     绝不硬解、绝不猜列语义。数值合法性不在此判（'abc' 原样透传，
//     由 data_ingest 的拒绝清单处理——链路诚实，坏行仍走人工复核）。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
//     数据值用中文。零第三方依赖（正则 + 字符串处理）。
//
// 数值纪律：本模块不换算数值（"185000.00"原样透传，换算归 data_ingest）；
//     只做"外衣清理"——剥掉单元格首尾空白与"元/%"后缀；纯函数（无 I/O）。
//
// 使用示例（知识点速览，v0.1 2026-08-30；原 Python 为 doctest 守护，
//     TS 侧对应行为由 tests/report-parse.test.ts 的用例逐条锁定）：
//
//     知识点 1 · 一份迷你预算报告 → 标准 8 列（合计行/完成率列自动跳过）
//         报告头 + 预算表（科目,2026年第一季度,2026年第二季度,合计）+
//         实际表（科目,2026年第一季度,完成率）→ 三条记录 + 8 列表头。
//     知识点 2 · 期间写法五花八门也能规范
//         ('2026年第一季度','一季度','2026-Q1','2026年1月','3月') 规范为
//         '2026-Q1'×4 + '2026-03'。
//     知识点 3 · 不像预算报告 → 诚实交回（shibie=false，调用方走 llm_clean）
//     知识点 4 · 有分表但缺编制日期 → 拒绝识别（记录缺台账字段，宁可不认）
//
// 命名对照表（拼音标识符 → 中文含义）：
//     shitu_jiexi         识别解析（总入口：像报告就解析成 8 列，不像就交回）
//     guifan_qijian       规范期间（五花八门的期间写法 → '2026-Q1'/'2026-01'）
//     JieXiJieguo         解析结果（shibie 是否识别 / wenben_8lie 标准文本 / beizhu 说明）
//     _fenjie_hang        分解行（文本 → 去空白行清单）
//     _zhao_fenjie        找分节（按关键词定位各分表的表头行位置）
//     _fenjie_lie         分解列（矩阵表头 → 期间列清单）
//     _biaotou_wei        表头位（从分节标题向后找第一个含逗号的行）
//     _jie_matrix         解矩阵表（科目×期间 → 逐格展开成记录；跳合计行/列）
//     _jie_danyebiao      解单页表（业务量/变更/行业对标等固定四列小表）
//     _shuzhi_qingxi      数值清理（剥空白与元/%后缀；'—'等占位 → 跳过）
//     _hanzi_shuzi        汉字数字（一二三四 → 1~4）
//     shibie / wenben_8lie / beizhu   是否识别 / 标准 8 列文本 / 交回原因或备注
//
// 口径依据：用户指令 2026-08-30（预算报告分表输入）；data_ingest 8 列规范
//          （解析出口必须与其表头逐字一致）；llm_clean 两级识别分工（模板
//          命中不惊动模型；识别失败交回分流，不重复造轮子）。
// 建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）｜ 转写 TS：2026-09-05
// ======================================================================

// ----------------------------------------------------------------------
// 常量与数据结构区
// ----------------------------------------------------------------------

/** 标准 8 列表头——解析出口必须与此逐字一致（下游 data_ingest 的入口契约）。
 *  按批次纪律：此处用独立字符串字面量照抄，不从 data-ingest import
 *  （两边各自持有同一契约文本，测试负责锁死一致性）。 */
export const BIAOTOU_8LIE = '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'

/** 矩阵表首列的合法叫法（科目/项目——两种叫法都收） */
const SHOULIE_MING: readonly string[] = ['科目', '项目', '科目名称']

/** 分节识别关键词表：(分节类型, 标题必须同时含的关键词组)。
 *  顺序即优先级——"预算表"先于"实际"判（防"实际经营预算表"这类混合标题串台） */
const FENJIE_JIAN = [
  ['yusuan', ['预算', '表']],
  ['shiji', ['实际', '表']],
  ['yewuliang', ['业务量', '表']],
  ['biangeng', ['变更', '登记']],
  ['hangye', ['行业', '对标']],
] as const

/** 分节标题长度上限——报告正文叙述里也可能出现"预算""表"字样，
 *  真正的分节标题都是短行；超长的当叙述跳过（防误判的便宜闸门）。
 *  （行长按 UTF-16 码元计，与 Python len() 在全部 BMP 中文文本上等价。） */
const FENJIE_CHANGDU = 40

/** 矩阵行/列的跳过词：行首含"合计"整行跳过；列头含"合计/完成率"整列跳过。
 *  与 Python 版一致的文档化常量：行跳过在解析处内联判定（'合计/小计/总计'）、
 *  列跳过由期间规范化失败兜底（'完成率'等认不出期间 → 非期间列），保留以逐字对应源码。 */
const TIAOGUO_LIE = ['合计', '小计', '总计', '完成率', '占比', '差异率', '备注'] as const

/** 单元格占位符——出现即视为空格（跳过该格，不生成记录） */
const ZHANWEI_fu = ['—', '–', '-', '/'] as const

/** 解析结果：识别成功与否 + 标准 8 列文本 + 说明（frozen dataclass → readonly interface）。
 *
 *  shibie=false 时 wenben_8lie 恒为空串、beizhu 写明交回原因——调用方
 *  （端到端层/未来界面）据此把原文转交 llm_clean 智能分流，两级衔接。 */
export interface JieXiJieguo {
  readonly shibie: boolean      // 是否识别为预算报告模板
  readonly wenben_8lie: string  // 标准 8 列文本（shibie=false 时为空串）
  readonly beizhu: string       // 交回原因（失败时）或解析摘要（成功时）
}

/** 一条解析记录：对应 Python 的 tuple[str, ...]——矩阵/业务量 5 元、变更/行业 8 元。 */
type Jilu = readonly string[]

// ----------------------------------------------------------------------
// 内部工具区（期间规范 / 数值清理 / 汉字数字）
// ----------------------------------------------------------------------

/** 汉字数字 → 阿拉伯数字（一二三四 → 1~4；其余返回 null）。
 *  用 Map 而非对象字面量：避免原型链键（如 'toString'）污染查表结果，
 *  语义与 Python dict.get（查不到返回 None）逐字对应。 */
function _hanzi_shuzi(zifu: string): number | null {
  const yingshe = new Map<string, number>([['一', 1], ['二', 2], ['三', 3], ['四', 4]])
  const zhi = yingshe.get(zifu)
  return zhi === undefined ? null : zhi
}

/** 五花八门的期间写法 → 规范期间（'2026-Q1' / '2026-01'；认不出 → null）。
 *
 *  收录写法（按尝试顺序）：
 *      2026-Q1 ｜ 2026年第一季度/2026年1季度 ｜ 一季度（年从报告取）｜
 *      Q1（年从报告取）｜ 2026-01 ｜ 2026年1月 ｜ 1月（年从报告取）。
 *  认不出返回 null——调用方据此把该列当"非期间列"（完成率/合计）跳过。
 *  防误咬：季度/月份数字后都带负向断言 (?!\d)——'2026-13' 不会被咬成
 *  2026-01（对应开发期真实修过的一个 bug，测试锁死）。 */
export function guifan_qijian(zifuchuan: string, nianfen: string | null): string | null {
  const s = zifuchuan.trim()
  if (!s) {
    return null
  }
  let du = /(20\d{2})\s*[-年]\s*Q\s*([1-4])(?!\d)/.exec(s)   // 2026-Q1 / 2026年Q1
  if (du) {
    return `${du[1]}-Q${du[2]}`
  }
  du = /(20\d{2})年第?([一二三四1-4])季度(?!\d)/.exec(s)     // 2026年第一季度
  if (du) {
    // 汉字季度优先、阿拉伯季度兜底（对应 Python `_hanzi_shuzi(...) or int(...)` 短路）
    const ji = _hanzi_shuzi(du[2]) ?? parseInt(du[2], 10)
    return `${du[1]}-Q${ji}`
  }
  du = /第?([一二三四1-4])季度/.exec(s)                      // 一季度（年从报告取）
  if (du && nianfen) {
    const ji = _hanzi_shuzi(du[1]) ?? parseInt(du[1], 10)
    return `${nianfen}-Q${ji}`
  }
  du = /^Q\s*([1-4])$/.exec(s)                               // Q1（年从报告取）
  if (du && nianfen) {
    return `${nianfen}-Q${du[1]}`
  }
  du = /(20\d{2})-(0?[1-9]|1[0-2])(?!\d)/.exec(s)            // 2026-01（防 2026-13 咬成 1 月）
  if (du) {
    // Python f'{int(group):02d}' 的等价：先转数值再去前导零、补足两位
    return `${du[1]}-${parseInt(du[2], 10).toString().padStart(2, '0')}`
  }
  du = /(20\d{2})年(0?[1-9]|1[0-2])(?!\d)月/.exec(s)         // 2026年1月
  if (du) {
    return `${du[1]}-${parseInt(du[2], 10).toString().padStart(2, '0')}`
  }
  du = /^(0?[1-9]|1[0-2])月$/.exec(s)                        // 1月（年从报告取）
  if (du && nianfen) {
    return `${nianfen}-${parseInt(du[1], 10).toString().padStart(2, '0')}`
  }
  return null
}

/** 单元格数值清理：剥首尾空白与"元/%"后缀；'—'等占位 → null（跳过该格）。
 *
 *  只清"外衣"不判合法——'abc' 原样返回，合法性归 data_ingest 的拒绝清单
 *  （链路诚实：坏行仍进人工复核，而不是在解析层悄悄消失）。 */
function _shuzhi_qingxi(danyuan: string): string | null {
  let s = danyuan.trim()
  if (!s || (ZHANWEI_fu as readonly string[]).includes(s)) {
    return null
  }
  if (s.endsWith('元') || s.endsWith('%')) {
    s = s.slice(0, -1).trim() // Python s[:-1].strip() 的等价（'元'/'%' 均为单码元字符）
  }
  return s || null // 剥完变空串（如值为纯'元'）也按无数据处理
}

/** 文本 → 行清单：去首尾空白、丢全空行（与 file_extract 输出形态对齐）。 */
function _fenjie_hang(wenben: string): string[] {
  return wenben.split('\n').map((hang) => hang.trim()).filter((hang) => hang !== '')
}

/** 找分节：扫描行清单，按关键词表定位各分表【标题行】的位置。
 *
 *  返回 {分节类型: 标题行下标}；同一类型只记首次出现（报告里同类表
 *  不重复）。判定条件 = 三条同时成立：含该组全部关键词、含"表"字
 *  （分节标题都以"……表"收尾；叙述行即便出现"变更登记"等字样、
 *  只要不含"表"就不会误判）、行长 ≤ FENJIE_CHANGDU。 */
function _zhao_fenjie(hang_lie: readonly string[]): Record<string, number> {
  const jieguo: Record<string, number> = {}
  for (let i = 0; i < hang_lie.length; i++) {
    const hang = hang_lie[i]
    if (hang.length > FENJIE_CHANGDU) {
      continue
    }
    for (const [leixing, jian] of FENJIE_JIAN) {
      if (leixing in jieguo) {
        continue
      }
      if (jian.every((zifu) => hang.includes(zifu)) && hang.includes('表')) {
        jieguo[leixing] = i
        break
      }
    }
  }
  return jieguo
}

/** 矩阵表头 → 期间列清单 [(列下标, 规范期间)]——非期间列（合计/完成率）跳过。 */
function _fenjie_lie(cells: readonly string[], nianfen: string | null): Array<[number, string]> {
  const lie_lie: Array<[number, string]> = []
  for (let xia = 0; xia < cells.length; xia++) {
    const danyuan = cells[xia]
    if (xia === 0) {
      continue // 首列 = 科目列
    }
    const qi = guifan_qijian(danyuan, nianfen)
    if (qi !== null) {
      lie_lie.push([xia, qi])
    }
  }
  return lie_lie
}

/** 从分节标题向后找【表头行】（第一个含逗号的行，最多看 3 行）。
 *
 *  分节定位记录的是标题行下标；真正的表头（"科目,一季度,…"）在标题
 *  下一两行——中间允许夹一行"单位：元"之类的注记。找不到返回 null。 */
function _biaotou_wei(hang_lie: readonly string[], biaotou_i: number): number | null {
  for (let i = biaotou_i + 1; i < Math.min(biaotou_i + 4, hang_lie.length); i++) {
    if (hang_lie[i].includes(',')) {
      return i
    }
  }
  return null
}

/** 矩阵表 → 逐格展开的记录（类别,期间,科目,数值,'元'）——合计行/列与空格跳过。
 *
 *  表头行 = 分节标题后第一个含逗号的行（首格须是"科目/项目"族）；
 *  其后含逗号的行都是数据行，遇到不含逗号的行即出表（分节标题/叙述
 *  都没有逗号——天然的表格边界）。 */
function _jie_matrix(hang_lie: readonly string[], biaotou_i: number, nianfen: string | null,
                     leibie: string): Jilu[] {
  const biaotou_hang = _biaotou_wei(hang_lie, biaotou_i)
  if (biaotou_hang === null) {
    return []
  }
  const cells = hang_lie[biaotou_hang].split(',').map((x) => x.trim())
  if (cells.length === 0 || !SHOULIE_MING.includes(cells[0])) {
    return []
  }
  const lie_lie = _fenjie_lie(cells, nianfen)
  const jilu: Jilu[] = []
  for (const hang of hang_lie.slice(biaotou_hang + 1)) {
    if (!hang.includes(',')) {
      break // 出表（空行/下一个分节标题）
    }
    const danyuan_lie = hang.split(',').map((x) => x.trim())
    const kemu = danyuan_lie[0]
    if (!kemu || ['合计', '小计', '总计'].some((t) => kemu.includes(t))) {
      continue // 合计行整行跳过
    }
    for (const [xia, qi] of lie_lie) {
      if (xia >= danyuan_lie.length) {
        continue // 短行容错：缺格不炸
      }
      const zhi = _shuzhi_qingxi(danyuan_lie[xia])
      if (zhi === null) {
        continue // 空格/'—'：该格无数据
      }
      jilu.push([leibie, qi, kemu, zhi, '元'])
    }
  }
  return jilu
}

/** 单页小表 → 记录（业务量/变更登记/行业对标三种固定列法，按表头名映射）。
 *
 *  小表与矩阵表的分野：矩阵是"科目×期间"二维展开（一格一条记录），
 *  小表是"一行一条记录"——三类小表的列名 → 8 列字段映射按 leixing 硬编码，
 *  台账字段来源：登记时间当更新时间（变更）、编制日期兜底（行业）。 */
function _jie_danyebiao(hang_lie: readonly string[], biaotou_i: number, nianfen: string | null,
                        leixing: string, shou_qijian: string | null,
                        bianzhi_riqi: string): Jilu[] {
  const biaotou_hang = _biaotou_wei(hang_lie, biaotou_i)
  if (biaotou_hang === null) {
    return []
  }
  const cells = hang_lie[biaotou_hang].split(',').map((x) => x.trim())
  // 注：与 Python 版一致，cells 取出后不参与小表判定（列法按 leixing 硬编码映射）
  void cells
  const jilu: Jilu[] = []
  for (const hang of hang_lie.slice(biaotou_hang + 1)) {
    if (!hang.includes(',')) {
      break // 出表
    }
    const danyuan = hang.split(',').map((x) => x.trim())
    if (['合计', '小计', '总计'].some((t) => danyuan[0].includes(t))) {
      continue // 合计行整行跳过
    }
    if (leixing === 'yewuliang') { // 科目,统计期间,数量,单位
      if (danyuan.length < 4) {
        continue
      }
      const qi = guifan_qijian(danyuan[1], nianfen)
      const zhi = _shuzhi_qingxi(danyuan[2])
      if (qi !== null && zhi !== null) {
        jilu.push(['实时经营', qi, danyuan[0], zhi, danyuan[3]])
      }
    } else if (leixing === 'biangeng') { // 变更事项,发生期间,登记时间,说明
      if (danyuan.length < 4) {
        continue
      }
      const qi = guifan_qijian(danyuan[1], nianfen)
      if (qi !== null) {
        // 数值恒 1 次——变更登记是"事件"，登记时间做台账更新时间
        jilu.push(['经营变更', qi, danyuan[0], '1', '次',
                   '预算报告', danyuan[2] || bianzhi_riqi, danyuan[3]])
      }
    } else if (leixing === 'hangye') { // 指标,数值,单位,备注
      if (danyuan.length < 3) {
        continue
      }
      const zhi = _shuzhi_qingxi(danyuan[1])
      if (zhi !== null && shou_qijian !== null) {
        const danwei = danyuan.length > 2 ? danyuan[2] : ''
        const beizhu = danyuan.length > 3 ? danyuan[3] : ''
        jilu.push(['行业对标', shou_qijian, danyuan[0], zhi, danwei,
                   '预算报告', bianzhi_riqi, beizhu])
      }
    }
  }
  return jilu
}

// ----------------------------------------------------------------------
// 对外入口区
// ----------------------------------------------------------------------

/** 识别解析总入口：像预算报告 → 标准 8 列文本；不像 → 诚实交回。
 *
 *  流程：找年度与编制日期 → 找各分节表头 → 预算/实际走矩阵解析、
 *  业务量/变更/行业走单页表解析 → 组装 8 列文本（来源统一"预算报告"，
 *  更新时间统一编制日期——台账字段齐了才放行）。
 *  识别失败的三种情形（beizhu 写明原因，调用方交回 llm_clean）：
 *      ① 一个分节都没认出（根本不是报告骨架）；
 *      ② 认出了分表但全文缺"编制日期"（记录缺台账字段，宁可不认）；
 *      ③ 分表里一张"科目×期间"矩阵都没有且没有可映射的小表。 */
export function shitu_jiexi(wenben: string): JieXiJieguo {
  const hang_lie = _fenjie_hang(wenben)
  const fenjie = _zhao_fenjie(hang_lie)
  if (Object.keys(fenjie).length === 0) {
    // 出口①：根本不是报告骨架
    return { shibie: false, wenben_8lie: '', beizhu: '未识别出预算报告模板的任何分节（交回智能分流）' }
  }

  // 年度：优先"XXXX年度"字样；编制日期：报告头台账行（记录必需）
  let nianfen: string | null = null
  let bianzhi_riqi: string | null = null
  for (const hang of hang_lie) {
    const du_nian = /(20\d{2})年度/.exec(hang)
    if (du_nian && nianfen === null) {
      nianfen = du_nian[1]
    }
    const du_riqi = /编制日期[:：]\s*(20\d{2}-\d{2}-\d{2})/.exec(hang)
    if (du_riqi && bianzhi_riqi === null) {
      bianzhi_riqi = du_riqi[1]
    }
  }
  // 出口②：认出了分表但全文缺"编制日期"（宁可不认）。
  // 检查次序与 Python 对调（Python 先用编制日期兜底年度、再拒绝缺日期；
  // 两条出口互不依赖，对调后行为完全等价——缺日期时两条路都通向拒绝）。
  if (bianzhi_riqi === null) {
    return { shibie: false, wenben_8lie: '',
             beizhu: '分表已识别但全文缺"编制日期"，记录缺台账字段——宁可不认（交回智能分流）' }
  }
  if (nianfen === null) {
    nianfen = bianzhi_riqi.slice(0, 4) // 编制日期的年兜底
  }

  // 预算/实际矩阵先行——顺带拿"首个期间"给行业对标行当归属期间
  const jilu: Jilu[] = []
  let shou_qijian: string | null = null
  for (const leixing of ['yusuan', 'shiji'] as const) {
    if (leixing in fenjie) {
      const kuai = _jie_matrix(hang_lie, fenjie[leixing], nianfen,
                               leixing === 'yusuan' ? '预算基础' : '实时经营')
      if (kuai.length > 0 && shou_qijian === null) {
        shou_qijian = kuai[0][1]
      }
      jilu.push(...kuai)
    }
  }
  for (const leixing of ['yewuliang', 'biangeng', 'hangye'] as const) {
    if (leixing in fenjie) {
      jilu.push(..._jie_danyebiao(hang_lie, fenjie[leixing], nianfen,
                                  leixing, shou_qijian, bianzhi_riqi))
    }
  }
  if (jilu.length === 0) {
    // 出口③：分节在但一张记录都解析不出
    return { shibie: false, wenben_8lie: '', beizhu: '分节已识别但未解析出任何记录（交回智能分流）' }
  }

  // 组装标准 8 列：矩阵记录 5 元组补台账三字段（来源/时间/备注空）
  const hang_lie_out: string[] = [BIAOTOU_8LIE]
  for (const jilu_xiang of jilu) {
    if (jilu_xiang.length === 5) { // 矩阵/业务量记录：补来源时间备注
      const [leibie, qi, kemu, zhi, danwei] = jilu_xiang
      hang_lie_out.push(`${leibie},${qi},${kemu},${zhi},${danwei},预算报告,${bianzhi_riqi},`)
    } else { // 变更/行业记录：自带台账三字段
      hang_lie_out.push(jilu_xiang.join(','))
    }
  }
  return {
    shibie: true,
    wenben_8lie: hang_lie_out.join('\n') + '\n',
    beizhu: `识别 ${jilu.length} 条记录（模板解析，零 LLM）`,
  }
}
