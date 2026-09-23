// ======================================================================
// LLM 格式归一化前置层 —— 方案B 4.3 第二步"AI 智能数据清洗"的安全落地。
// 转写自 D:\AppProject\algo\llm_clean.py（Python 版为唯一行为准绳）。
// ======================================================================
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。
//
// 设计定位（用户提议 + 方案批准 2026-08-23）：
//     程序擅长"已知格式的严格校验"，大模型擅长"未知格式的结构识别"——
//     本模块把两者分层互补：先程序直解（零 token），直解不动了才请模型
//     把乱格式"翻译"成统一 8 列 CSV，翻译结果仍要走 data_ingest 的
//     全套确定性校验。DeepSeek V4 Flash 适合干这种结构翻译杂活
//     （docs\06 路线 3 分层路由：快模型干杂活、贵模型干分析）。
//
// 三条红线（不可协商）：
//     1. 【数字原样照抄】模型只做格式翻译，数值字符串逐字复制，
//        禁止四舍五入 / 换算 / 补全 / 编造——由 shuzi_yuansu_jiaoyan
//        强制校验（输出中每个数字必须能在原文找到，凭空数字 = 幻觉，
//        整批拒绝），呼应 FR-8 与 docs\06 路线 5 确定性护栏。
//     2. 【不豁免校验】模型输出走 daoru_csv 既有全套规则（校验/去重/
//        换算/拒绝清单），模型不获得任何特权。
//     3. 【可降级】模型函数未提供或调用失败 → 系统仍可用（返回合成
//        拒绝结果 + 人工修格式建议），呼应风险 R-03 的降级精神。
//
// 纯函数纪律：本模块【无网络 I/O】——真实模型调用以函数参数
// moxing_hanshu: (wenben: string) => string 注入（同步返回字符串，对应
// Python 的 Callable[[str], str]）；插件层后续把 dsh 原生 llm 适配成此
// 接缝（转写裁决 #11：model_api/moxing_peizhi 不移植，llm 由 dsh 承担）。
//
// 格式范围（用户选定 2026-08-23）：CSV / TXT / 粘贴的表格文本；
// .xlsx 为二进制压缩包，约定"Excel 里另存为 CSV"再导入（提示词中
// 同样告知模型遇到二进制内容要提示用户另存）。
//
// 使用示例（知识点速览，v0.1 2026-08-23；原 Python 为 doctest 守护，
//     TS 侧对应行为由 tests/llm-clean.test.ts 的用例逐条锁定）：
//
//     知识点 1 · 直解成功：不花一个 token（模型函数根本不会被调用）
//     知识点 2 · 乱格式走模型归一化（两列脏表 → 标准 8 列）
//     知识点 3 · 模型编造数字 → 幻觉防线整批拒绝
//     知识点 4 · 没有模型函数 → 降级（附人工修格式建议）
//
// 命名对照表（拼音标识符 → 中文含义）：
//     zhineng_fenliu       智能分流（总入口：直解→模型→降级 三级路由）
//     zhijie_changshi      直接尝试（调 daoru_csv 程序直解）
//     gouzao_tishi         构造提示（拼装给模型的归一化指令）
//     llm_guiyihua         LLM归一化（调用注入的模型函数并剥离代码块）
//     shuzi_yuansu_jiaoyan 数字溯源校验（幻觉防线：输出数字必须源于原文）
//     moxing_hanshu        模型函数（(wenben: string) => string，注入式）
//     FenLiuJieguo         分流结果（导入结果 + 路径 + 是否用模型）
//     _tiqu_shuzi          提取数字（全角转半角、千分位剥离、去前导零）
//     _quchu_daimakuai     去除代码块（模型爱用 ```csv 包裹，防御性剥离）
//     _bu_biaotou          补表头（模型漏表头时的确定性兜底）
//     _hecheng_jujue       合成拒绝（降级/幻觉时的占位导入结果）
//     lujing               路径（'直解' / '模型归一化' / '降级'）
//
// 已知边界（诚实声明，答辩可能被问）：
//     溯源校验只覆盖【数字】——科目名、单位等文字字段无法逐一溯源
//     （模型可能改写表述），兜底靠拒绝清单人工复核（用户既定策略：
//     产出数据甩会计挑毛病）。期间改写（如月度改季度）会被确定性层
//     的格式校验放行、数字层校验难察觉，属已知残余风险。
//
// 口径依据：docs\proposal-full-extract.txt 行 154~157（4.3 第二步 AI 清洗）；
//          docs\06-LLM预算能力提升技术路线.md 路线 2/3/5；
//          docs\textbook\finagent-算法核对文档-定稿.md v2.1 §9 步骤 1。
// 建立：2026-08-23 ｜ Agent：ZCode（GLM-5.3）｜ 转写 TS：2026-09-05
// ======================================================================

// 复用数据录入模块的成品：导入主函数、结果结构、拒绝行、解析错误、表头。
// 注意：DaoruJieguo/JuJueHang 是纯类型（interface），必须带 inline `type`
// 修饰符导入——Node 原生类型剥离只擦类型、不搬运行时绑定，否则
// "does not provide an export named ..." 直接炸。
import { BIXU_LIE, JiexiCuowu, daoru_csv, type DaoruJieguo, type JuJueHang } from './data-ingest.ts'

// ----------------------------------------------------------------------
// 常量区
// ----------------------------------------------------------------------

/** 幻觉拒绝原因的前缀标记（拒绝清单里一眼可辨） */
export const HUANJUE_BIAOJI = 'LLM幻觉嫌疑'

/** 提示词模板（{yuanwen} 为占位符）——铁律全部写死在提示里。
 *  中文全文与 Python 源逐字一致（含换行与缩进，已与源文件 repr 比对）。 */
export const TISHI_MOUBAN = `你是数据格式归一化器。把下面给的任意表格数据（列序混乱、多余列、中文表头变体、分隔符不统一的 CSV/TXT/粘贴表格）转成标准 8 列 CSV。

铁律（违反即整批作废）：
1. 数值列的数字必须原样照抄（含小数位与千分位写法），禁止四舍五入、换算、补全、编造；
2. 只输出 CSV 正文（第一行必须是标准表头），不要输出任何解释、代码块标记或其他文字；
3. 原文缺失的字段按以下方式诚实补齐（只补文字，禁止补任何数字）：
   - 更新时间：取原文中出现过的日期（一个都没有则留空）；
   - 数据来源：填「LLM归一化」（诚实标注翻译产物，便于审计）；
   - 数据类别：按语义判断（出现"预算/计划"等字样→预算基础；"实际/发生"等→实时经营）；
     无法判断时填「实时经营」，并在备注列写「类别待人工确认」；
4. 若内容是二进制（如 xlsx），直接回复一行：仅支持文本，请另存为 CSV。

标准表头（8 列，顺序固定）：
数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注

数据类别枚举：预算基础 / 实时经营 / 行业对标 / 经营变更
单位枚举：元 / % / 个、次、天、单、人
期间格式：月度 2026-01；季度 2026-Q1

待归一化数据：
<<<原文开始
{yuanwen}
原文结束>>>`

/** 数字提取正则：千分位整数（1,234 / 1,234,567.89）优先，普通数字次之。
 *  对应 Python re.compile(...)；/g 版配合 String.match 做 findall。 */
const _SHUZI_GESHI = /\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?/g

/** 全角数字/小数点/逗号 → 半角的转换表（模型或原文常用全角）。
 *  对应 Python str.maketrans('０１２３４５６７８９．，', '0123456789.,')。 */
const _QUANJIAO_ZHUAN: ReadonlyMap<string, string> = new Map([
  ['０', '0'], ['１', '1'], ['２', '2'], ['３', '3'], ['４', '4'],
  ['５', '5'], ['６', '6'], ['７', '7'], ['８', '8'], ['９', '9'],
  ['．', '.'], ['，', ','],
])

// ----------------------------------------------------------------------
// 数据结构区
// ----------------------------------------------------------------------

/** 智能分流的最终结果（frozen dataclass → readonly interface）。
 *
 *  字段说明：
 *      jieguo:              导入结果（任何路径都有值；降级/幻觉时为
 *                           "四类全空 + 单条拒绝"的合成结果，保持类型统一）。
 *      shifou_yongle_moxing: 是否实际调用了模型（token 成本关注点）。
 *      lujing:              走了哪条路：'直解' / '模型归一化' / '降级'。
 *      guiyi_wenben:        模型归一化产出的标准 CSV 文本（其余路径为空串，
 *                           留作审计对照：原文 vs 翻译文）。
 *      chenggong:           是否成功入库（派生属性，见 _fenliu 构造助手）。 */
export interface FenLiuJieguo {
  readonly jieguo: DaoruJieguo
  readonly shifou_yongle_moxing: boolean
  readonly lujing: string
  readonly guiyi_wenben: string
  readonly chenggong: boolean
}

/** FenLiuJieguo 的构造助手——chenggong 是 lujing 的派生属性（对应 Python
 *  @property：降级路径 = False；拒绝清单详情看 jieguo.jujue）。 */
function _fenliu(jieguo: DaoruJieguo, shifou_yongle_moxing: boolean,
                 lujing: string, guiyi_wenben: string): FenLiuJieguo {
  return {
    jieguo,
    shifou_yongle_moxing,
    lujing,
    guiyi_wenben,
    get chenggong(): boolean {
      return this.lujing !== '降级'
    },
  }
}

// ----------------------------------------------------------------------
// 内部工具函数区
// ----------------------------------------------------------------------

/** 提取文本中全部数字 token 并规范化（溯源比对的原子操作）。
 *
 *  规范化三步（两侧同样处理，只比"数学值"不比"写法"）：
 *      ① 全角数字/小数点/千分位逗号 → 半角；
 *      ② 千分位写法剥离逗号（'1,234.56' → '1234.56'）；
 *      ③ 去前导零（'01' → '1'；'0.5' → '.5'，两侧一致即可比对）。 */
function _tiqu_shuzi(wenben: string): string[] {
  const banjiao = wenben.replace(/[０-９．，]/g, (fu) => _QUANJIAO_ZHUAN.get(fu) ?? fu) // ① 全角转半角
  const token_lie = banjiao.match(_SHUZI_GESHI) ?? [] // Python findall（无匹配 → 空清单）
  // ②③：剥千分位逗号、去前导零；全零剥空后回落 '0'（Python `... or '0'`）
  return token_lie.map((t) => t.replace(/,/g, '').replace(/^0+/, '') || '0')
}

/** 剥离模型惯用的 ```csv ... ``` 代码块包裹（防御性，不改内容）。
 *
 *  只剥首尾的包裹行；正文里的任何字符一律不动（数字照抄铁律）。 */
function _quchu_daimakuai(wenben: string): string {
  let jingguo = wenben.trim()
  if (jingguo.startsWith('```')) { // 首行是 ``` 或 ```csv 之类
    // Python `split('\n', 1)[1] if '\n' in wenben else ''`：丢弃首行包裹标记
    jingguo = jingguo.includes('\n') ? jingguo.slice(jingguo.indexOf('\n') + 1) : ''
    const weibu = jingguo.replace(/\s+$/, '') // rstrip（尾部包裹行探测）
    if (weibu.endsWith('```')) {
      jingguo = weibu.slice(0, -3) // Python [:-3]：砍掉末尾三个反引号
    }
  }
  return jingguo.trim()
}

/** 翻译产物缺表头时自动补上标准表头（确定性兜底，真模型实测发现）。
 *
 *  场景：模型偶尔只回数据行、漏掉表头行（2026-08-23 真跑实测）。
 *  规则：首行不是标准表头、但列数恰为 8 → 前插标准表头；
 *  补的是【常量字符串】，不碰任何数据内容——零幻觉风险。 */
function _bu_biaotou(wenben: string): string {
  const hang_lie = wenben.split('\n').filter((hang) => hang.trim() !== '')
  if (hang_lie.length === 0) {
    return wenben // 空文本不处理（后续校验自会降级）
  }
  const biaotou_wenben = BIXU_LIE.join(',')
  if (hang_lie[0].trim() === biaotou_wenben) {
    return wenben // 表头已在，无需补
  }
  if (hang_lie[0].split(',').length === BIXU_LIE.length) {
    return biaotou_wenben + '\n' + wenben // 列数对得上 → 补头
  }
  return wenben // 列数都对不上 → 原样交回（后续校验给"格式不合格"降级）
}

/** 合成一个"四类全空 + 单条拒绝"的占位导入结果。
 *
 *  用途：降级 / 幻觉路径也要返回统一的 DaoruJieguo 类型，
 *  调用方无需分支处理 null（行号 0 表示非数据行问题）。 */
function _hecheng_jujue(yuanyin: string): DaoruJieguo {
  const jujue: JuJueHang[] = [{ hanghao: 0, yuanyin, yuanwen: [] }]
  return {
    yusuan: [],
    shishi: [],
    hangye: [],
    biangeng: [],
    jujue,
    get ruku_shu(): number {
      return 0 // 四类全空 → 恒 0（同 data-ingest 的 getter 口径）
    },
  }
}

// ----------------------------------------------------------------------
// 对外接口区（四个函数，按分流顺序排列）
// ----------------------------------------------------------------------

/** 直接尝试：调 data_ingest 的程序直解（不花任何 token）。
 *
 *  返回直解的导入结果；表头级问题会抛 JiexiCuowu（由上层捕获后
 *  转入模型路径）。注意：直解"部分行被拒"仍算成功——拒绝清单
 *  本来就是给人工复核看的。 */
export function zhijie_changshi(wenben: string): DaoruJieguo {
  return daoru_csv(wenben)
}

/** 构造提示词：把 8 列规范、枚举值、数字照抄铁律全部写死进去。
 *  用 split/join 而非 replace：语义对齐 Python str.replace 的"全部替换 +
 *  纯字面替换"（JS replace 的 $& 等替换模式符不会误生效）。 */
export function gouzao_tishi(yuanwen: string): string {
  return TISHI_MOUBAN.split('{yuanwen}').join(yuanwen)
}

/** 数字溯源校验（幻觉防线）——返回凭空出现的问题数字清单。
 *
 *  规则（集合语义）：归一化输出里出现过的每一个数字【值】，都必须
 *  在原文里出现过；重复出现不算幻觉（模型把一个日期拆进"期间 +
 *  更新时间"两列时，年份合法地出现两次——这是结构重排不是编造；
 *  真正的重复数据由确定性层的去重规则兜底）。
 *  两侧先经同一规范化（全角/千分位/前导零），只比数学值不比写法。 */
export function shuzi_yuansu_jiaoyan(yuanwen: string, guiyi_wenben: string): string[] {
  const yuanshi_zhi = new Set(_tiqu_shuzi(yuanwen))
  const shuchu_zhi = new Set(_tiqu_shuzi(guiyi_wenben))
  // 输出中出现、原文从未出现过的数字 = 模型自己编的（Python sorted：字典序）
  return [...shuchu_zhi].filter((s) => !yuanshi_zhi.has(s)).sort()
}

/** 调用注入的模型函数做格式归一化，返回标准 CSV 文本。
 *
 *  模型函数签名：接收完整提示词，返回字符串（网络调用由注入方实现，
 *  本模块保持纯函数纪律）。返回值先剥代码块包裹再交校验。
 *  fankui（反馈）：重试时传入上次的拒绝原因——只进【提示词】，
 *  绝不拼进原文（防止反馈里的数字污染溯源比对基准）。 */
export function llm_guiyihua(yuanwen: string, moxing_hanshu: (wenben: string) => string,
                             fankui = ''): string {
  let tishi = gouzao_tishi(yuanwen)
  if (fankui) {
    // 自纠错提示：明确要求修正且重新输出完整 CSV
    tishi += `\n\n【注意】你上次的输出被系统拒绝，原因：${fankui}\n请严格修正后重新输出完整 CSV。`
  }
  return _quchu_daimakuai(moxing_hanshu(tishi))
}

/** 智能分流总入口：直解 → 模型归一化 → 降级，三级路由。
 *
 *  路由规则：
 *      ① 直解无异常且入库数 > 0 → 直接返回（零 token）；
 *      ② 表头级异常，或"入库数为 0 且有拒绝行"（全军覆没 = 格式不对）
 *         → 请模型归一化 → 先过全套确定性校验（结构不合格即降级），
 *         再过数字溯源校验（凭空数字即幻觉拒绝）；
 *      ③ 模型未提供 / 调用失败 / 翻译不合格 / 幻觉命中 → 降级，
 *         返回合成拒绝结果（附人工修格式建议）。
 *
 *  moxing_hanshu：模型函数（Callable[[str], str] 的 TS 形态），null = 无模型。 */
export function zhineng_fenliu(wenben: string,
                               moxing_hanshu: ((wenben: string) => string) | null = null): FenLiuJieguo {
  // ---- ① 程序直解 ----
  try {
    const jieguo = zhijie_changshi(wenben)
    if (jieguo.ruku_shu > 0 || jieguo.jujue.length === 0) {
      // 入库成功，或空文件（只有表头）——都不必惊动模型
      return _fenliu(jieguo, false, '直解', '')
    }
  } catch (cuo) {
    // 只吞表头级问题（同 Python `except JiexiCuowu`），其余异常照常上抛
    if (!(cuo instanceof JiexiCuowu)) throw cuo
  }

  // ---- ② 模型归一化（自纠错重试：最多两次，第二次带首次拒绝原因）----
  if (moxing_hanshu === null) {
    return _fenliu(
      _hecheng_jujue('无法直解且未提供模型函数：请手工修成标准 8 列 CSV，或用 Excel 另存为 CSV 后重试'),
      false, '降级', '',
    )
  }

  let fankui = '' // 上次拒绝原因（喂回提示词让模型自纠；不进原文，防污染溯源）
  let zuihou_guiyi = '' // 最后一次翻译产物（降级时留审计）
  for (const _diji_ci of [1, 2]) { // 首次 + 一次重试；再多就交人工
    let guiyi: string
    try {
      guiyi = llm_guiyihua(wenben, moxing_hanshu, fankui)
    } catch (cuo) { // 模型超时/网络/接口错误一律降级（红线3）
      // Python f'{cuo}' 取 str(异常) = 消息文本，故 TS 取 .message 对齐
      const xinxi = cuo instanceof Error ? cuo.message : String(cuo)
      return _fenliu(_hecheng_jujue(`模型调用失败：${xinxi}；请手工修格式或稍后重试`),
                     true, '降级', zuihou_guiyi)
    }
    zuihou_guiyi = guiyi

    // 确定性兜底：模型漏表头时自动补（补常量字符串，不碰数据）
    guiyi = _bu_biaotou(guiyi)

    // 翻译结果过全套确定性校验（红线2：不豁免任何规则）
    let jieguo: DaoruJieguo
    try {
      jieguo = daoru_csv(guiyi)
    } catch (cuo) {
      if (!(cuo instanceof JiexiCuowu)) throw cuo
      fankui = `结构问题：${cuo.message}` // 反馈后重试
      continue
    }

    // 字段级问题（如期间留空导致全军覆没）→ 反馈后重试
    if (jieguo.ruku_shu === 0 && jieguo.jujue.length > 0) {
      fankui = jieguo.jujue.map((x) => x.yuanyin).join('；').slice(0, 300)
      continue
    }

    // 幻觉防线：输出的每个数字必须源于原文（红线1）——零容忍，不重试
    const pingsheng = shuzi_yuansu_jiaoyan(wenben, guiyi)
    if (pingsheng.length > 0) {
      return _fenliu(
        _hecheng_jujue(`${HUANJUE_BIAOJI}：输出中存在原文没有的数字（${pingsheng.join(', ')}），整批拒绝`),
        true, '降级', guiyi,
      )
    }
    return _fenliu(jieguo, true, '模型归一化', guiyi)
  }

  // 两次都不合格：降级并保留最后一次拒绝原因（交人工）
  return _fenliu(
    _hecheng_jujue(`模型两次输出仍不符合要求：${fankui}；请人工修格式或稍后重试`),
    true, '降级', zuihou_guiyi,
  )
}
