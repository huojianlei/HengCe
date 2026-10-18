// ======================================================================
// 数据录入模块 —— 方案B 八步流程【步骤 1：基础数据录入】的确定性核心。
// 转写自 D:\AppProject\algo\data_ingest.py（Python 版为唯一行为准绳）。
// ======================================================================
//
// 命名规范（2026-08-23 用户指令）：本模块所有标识符（变量/函数/类/常量/
// 字典键）一律用【无声调拼音】，数据值用中文；文件名保持英文（Windows 规范）。
//
// 职责边界（本模块只做三件事，多一件都不做）：
//     1. 解析：把 CSV 文本拆成一行行原始数据（表头必须符合统一 8 列规范）；
//     2. 清洗：逐行校验 + 数值换算（去重 / 纠错 / 缺失标记；有问题的行
//        【不静默丢弃】，而是进入"拒绝清单"交人工复核——对应方案B 4.3
//        第二步"标记异常待人工复核"）；
//     3. 归类：把合法行按【数据类别】归入四大档案（对应 4.3 第三步）。
//
// 数据四大类（方案B 4.1，中文常量）：
//     预算基础（年初一次性）、实时经营（按月/季）、行业对标（外部）、
//     经营变更（事件式随时）。
//
// 统一 8 列表头（方案B 4.2 的 7 个基础字段 + 1 个类别列）：
//     数据类别, 统计周期, 数据科目, 数值, 单位, 数据来源, 更新时间, 备注
//     （类别列是我们对方案的增强：显式声明比自动猜测可靠；
//       让 LLM 智能归类属于 M5 智能体层，不在本确定性模块。）
//
// 数值纪律（与全项目一致，杜绝浮点误差）：
//     - 金额「元」→ 整数「分」（字符串直接解析，全程不经浮点）；
//     - 百分比「%」→ 整数「基点」（1% = 100 基点）；
//     - 计数（个/次/天…）→ 整数（本身必须就是整数）。
//     【口径分歧·待会计复核】方案B 4.2 写"空值统一填充 0"——我们认为
//     缺失 ≠ 0（3 月没录数 ≠ 3 月花销为 0），故空值一律进拒绝清单。
//
// 本模块【不含数据库】：输出的是内存中的标准记录，入库（fin-store /
// SQLite，见 docs\10 §四 与 ADR-04）属后续单独模块，届时按 TODO 立项。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     daoru_csv / jiexi_csv / qingxi_bing_guilei   导入CSV / 解析CSV / 清洗并归类
//     JiexiCuowu            解析错误（表头不符等整文件问题）
//     BiaozhunJilu          标准记录（一条清洗后的数据）
//     JuJueHang             拒绝行（被拒原始行 + 原因）
//     DaoruJieguo           导入结果（四类归档 + 拒绝清单）
//     LEIBIE_YUSUAN 等      四个类别常量（预算基础/实时经营/行业对标/经营变更）
//     BIXU_LIE              必需的 8 列表头
//     hanghao / leibie / qijian / kemu    行号 / 类别 / 期间 / 科目
//     shuzhi / danwei / laiyuan / beizhu  数值 / 单位 / 来源 / 备注
//     ruku_shu              入库数（合法行合计）
//
// 口径依据：docs\textbook\finagent-算法核对文档-定稿.md v2.1 §9 步骤 1；
//          docs\proposal-full-extract.txt 行 147~186（完整版第四章投喂体系）。
// ======================================================================

// ----------------------------------------------------------------------
// 常量区（全部中文取值，数据里直接写中文类别与单位）
// ----------------------------------------------------------------------

/** 类别一：预算基础（年初定稿的年度预算表等，一次性录入） */
export const LEIBIE_YUSUAN = '预算基础'
/** 类别二：实时经营（月度/季度的实际发生额，周期性录入） */
export const LEIBIE_SHISHI = '实时经营'
/** 类别三：行业对标（外部行业参考值，队友正在找的数据走这类） */
export const LEIBIE_HANGYE = '行业对标'
/** 类别四：经营变更（供应商更换等结构性事件，随时触发录入） */
export const LEIBIE_BIANGENG = '经营变更'

/** 四类的合法取值集合（录入行的「数据类别」列必须是其中之一） */
export const HEFA_LEIBIE = [LEIBIE_YUSUAN, LEIBIE_SHISHI, LEIBIE_HANGYE, LEIBIE_BIANGENG] as const

/** 统一表头：8 列、顺序固定（第一行必须与此完全一致） */
export const BIXU_LIE = [
  '数据类别', '统计周期', '数据科目', '数值', '单位', '数据来源', '更新时间', '备注',
] as const

/** 金额单位：元（录入两位小数 → 存为整数分） */
export const DANWEI_YUAN = '元'
/** 百分比单位：%（录入两位小数 → 存为整数基点） */
export const DANWEI_BAIFENBI = '%'
/** 计数单位：这些单位下数值必须是纯整数（不允许小数） */
export const JISHU_DANWEI = ['个', '次', '天', '单', '人'] as const

/** 月度期间格式：2026-01 ~ 2026-12（四位年 + 两位月） */
const _YUEDU_QIJIAN_GESHI = /^\d{4}-(0[1-9]|1[0-2])$/
/** 季度期间格式：2026-Q1 ~ 2026-Q4（四位年 + Q + 一位季） */
const _JIDU_QIJIAN_GESHI = /^\d{4}-Q[1-4]$/

// ----------------------------------------------------------------------
// 数据结构与异常区
// ----------------------------------------------------------------------

/**
 * 解析级错误：表头不符、文件为空等"整个文件的问题"。
 *
 * 与逐行拒绝（JuJueHang）的区别：
 * 解析级错误意味着文件本身不合格，一行都处理不了，必须整文件重做；
 * 逐行拒绝只是个别行有问题，其余行照常入库。
 */
export class JiexiCuowu extends Error {}

/** 一条清洗后的标准数据记录（后续入库的基本单位）。
 *  字段与 8 列一一对应（外加行号）；shuzhi 已换算为整数
 *  （元→分 / %→基点 / 计数→个），全链路不再出现小数。 */
export interface BiaozhunJilu {
  readonly hanghao: number         // 原始行号（数据行从 2 起；台账追溯与复核定位用）
  readonly leibie: string          // 数据类别（四类之一）
  readonly qijian: string          // 统计期间（2026-01 / 2026-Q1）
  readonly kemu: string            // 数据科目（营收、材料成本、毛利率……）
  readonly shuzhi: number          // 数值（整数：分 / 基点 / 个）
  readonly danwei: string          // 单位（元 / % / 计数单位）
  readonly laiyuan: string         // 数据来源（哪个系统/哪份表——答辩可溯源）
  readonly gengxin_shijian: string // 更新时间（台账追溯）
  readonly beizhu: string          // 备注（唯一允许为空的字段）
}

/** 一条被拒绝的行：原始内容 + 拒绝原因（人工复核清单的条目）。 */
export interface JuJueHang {
  readonly hanghao: number              // 行号（定位到具体行）
  readonly yuanyin: string              // 拒绝原因（中文，可能含多项，分号分隔）
  readonly yuanwen: readonly string[]   // 原始行内容（8 列原文，供复核时对照）
}

/** 导入结果：四大类归档清单 + 拒绝清单。
 *  用法约定：调用方先看 jujue（有则提示人工处理），
 *  再取四个类别清单做后续运算（滚动预算取"预算基础+实时经营"等）。 */
export interface DaoruJieguo {
  readonly yusuan: readonly BiaozhunJilu[]    // 预算基础类归档
  readonly shishi: readonly BiaozhunJilu[]    // 实时经营类归档
  readonly hangye: readonly BiaozhunJilu[]    // 行业对标类归档
  readonly biangeng: readonly BiaozhunJilu[]  // 经营变更类归档
  readonly jujue: readonly JuJueHang[]        // 拒绝清单（交人工复核）
  readonly ruku_shu: number                   // 合法入库总行数（四类之和）——getter 实时计算
}

/** 解析出的原始行：正常行 = 8 个「列名→去空白值」键值 + '__hanghao__'；
 *  列数不齐的行 = '__huaihang__' 存原始单元格数组（移交清洗阶段进拒绝清单）。 */
export interface JiexiHang {
  readonly __hanghao__: number
  readonly __huaihang__?: readonly string[]
  readonly [lie_ming: string]: string | number | readonly string[] | undefined
}

// ----------------------------------------------------------------------
// 内部工具函数区
// ----------------------------------------------------------------------

/**
 * Python repr(str) 的近似实现——报错文案里 {wenben!r} 的逐字对应：
 * 默认单引号包裹；字符串含单引号且不含双引号时改用双引号包裹（同 Python 取向）；
 * 反斜杠 / 引号 / 换行回车制表做转义。
 */
function yuan_wen_dai_yinhao(s: string): string {
  const zhuan_yi = (b: string): string =>
    b.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t')
  if (s.includes("'") && !s.includes('"')) {
    return `"${zhuan_yi(s).replace(/"/g, '\\"')}"`
  }
  return `'${zhuan_yi(s).replace(/'/g, "\\'")}'`
}

/** Python list([...]) 的打印形态：['a', 'b'] —— 表头报错文案逐字对应用。 */
function lie_biao_da_yinhao(xiang: readonly string[]): string {
  return `[${xiang.map((zifu) => yuan_wen_dai_yinhao(zifu)).join(', ')}]`
}

/**
 * 把十进制数字符串解析为"放大整数"，全程字符串操作、不经浮点。
 *
 * 规则（以 fangda_wei=2 为例，即元→分、%→基点）：
 *     '123.45' → 12345   （两位小数，直接拼接）
 *     '123.4'  → 12340   （一位小数，补零到两位）
 *     '123'    → 12300   （无小数，补两个零）
 * 拒绝情形（抛 JiexiCuowu）：
 *     空值（缺失不填 0，见模块头"口径分歧"）、负数、含字母、
 *     小数位超过 fangda_wei 位。
 */
function _jiexi_fangda_zhengshu(wenben: string, fangda_wei: number): number {
  const s = wenben.trim() // 容忍首尾空白（Excel 导出常见）
  if (!s) {
    throw new JiexiCuowu('数值缺失（空值不填 0，标记待人工复核）')
  }
  if (s.startsWith('-')) {
    throw new JiexiCuowu('负数不允许（正负方向由指标性质表达，不由录入符号表达）')
  }
  // 按小数点切分（只切第一个点，'1.2.3' 会因后半段非数字被拒）
  const dian_wei = s.indexOf('.')
  const zhengshu_bu = dian_wei === -1 ? s : s.slice(0, dian_wei)
  const xiaoshu_bu = dian_wei === -1 ? '' : s.slice(dian_wei + 1)
  // Python str.isdigit()：全数字且非空 —— 与 /^\d+$/ 等价（ASCII 数字）
  if (!/^\d+$/.test(zhengshu_bu) || (xiaoshu_bu !== '' && !/^\d+$/.test(xiaoshu_bu))) {
    throw new JiexiCuowu(`数值不是合法数字：${yuan_wen_dai_yinhao(wenben)}`)
  }
  if (xiaoshu_bu.length > fangda_wei) {
    throw new JiexiCuowu(`小数位超过 ${fangda_wei} 位：${yuan_wen_dai_yinhao(wenben)}`)
  }
  const bu_ling = xiaoshu_bu.padEnd(fangda_wei, '0') // 不足位补零
  return Number(zhengshu_bu + bu_ling) // 字符串拼接后必为纯数字串（零浮点）
}

// ----------------------------------------------------------------------
// CSV 词法（对应 Python csv.reader 默认方言：逗号分隔、双引号包裹、
// 引号内换行合法、"" 转义引号、\r/\n/\r\n 均为行结束符、非 strict 宽容）
// ----------------------------------------------------------------------

/**
 * CSV 文本 → 逐条记录（字符串数组）的生成器。
 * 逐字符状态机，语义对齐 Python csv.reader（默认方言）：
 *   - 空白行产出空记录 []（上层 any() 过滤掉，与 Python 行为一致）；
 *   - 引号字段可跨行；"" 还原为一个引号；引号后散字宽容拼接；
 *   - 引号仅在字段首字符处开启（'a"b' 的引号按字面处理）。
 */
function* csv_du_qu(wenben: string): Generator<string[]> {
  let i = 0
  const zong_chang = wenben.length
  let hang: string[] = [] // 当前记录里已完成的字段（分隔符前收下的）
  let dange = ''          // 当前字段累计内容
  let yinhao_nei = false  // 处于 "..." 引号字段内部
  let you_zifu = false    // 当前记录以来是否出现过非换行字符（空白行判定）
  while (i < zong_chang) {
    const fu = wenben[i]
    if (!yinhao_nei && (fu === '\n' || fu === '\r')) {
      // 行结束符（\r\n 视作一个）：收尾当前记录
      if (you_zifu || dange !== '' || hang.length > 0) {
        yield [...hang, dange] // 正常行：最后一个字段在此收进
      } else {
        yield [] // 全空白行：csv.reader 产出空记录（上层过滤）
      }
      hang = []
      dange = ''
      yinhao_nei = false
      you_zifu = false
      i += fu === '\r' && wenben[i + 1] === '\n' ? 2 : 1
      continue
    }
    you_zifu = true // 其余任何字符都算"本行有内容"
    if (yinhao_nei) {
      if (fu === '"') {
        if (wenben[i + 1] === '"') {
          dange += '"' // "" → 一个引号
          i += 2
        } else {
          yinhao_nei = false // 引号闭合（其后散字宽容拼接）
          i += 1
        }
      } else {
        dange += fu // 引号内的换行/逗号都是字段内容
        i += 1
      }
      continue
    }
    if (fu === '"' && dange === '') {
      yinhao_nei = true // 字段首字符的引号 → 开启引号字段
      i += 1
      continue
    }
    if (fu === ',') {
      hang.push(dange) // 字段分隔
      dange = ''
      i += 1
      continue
    }
    dange += fu // 普通字符
    i += 1
  }
  if (you_zifu || dange !== '' || hang.length > 0) {
    yield [...hang, dange] // 流尾悬挂的无换行记录（csv.reader 同样收尾产出）
  }
}

// ----------------------------------------------------------------------
// 对外接口区（三个函数，自上而下组合）
// ----------------------------------------------------------------------

/**
 * 第一步：解析 CSV 文本 → 原始行字典列表。
 *
 * - 自动剥掉 Windows 记事本/Excel 常见的 UTF-8 BOM 头（\ufeff）；
 * - 跳过整行全空的行（表格里常见的装饰性空行）；
 * - 第一行必须与 BIXU_LIE 完全一致（8 列、同顺序），
 *   否则抛 JiexiCuowu（整文件问题，见该异常的说明）；
 * - 列数不齐的行【不在此报错】——打上 '__huaihang__' 标记交给清洗阶段
 *   进拒绝清单（与"逐行标记"的口径一致）；
 * - 每行字典附带 '__hanghao__' 行号（数据行从 2 起）。
 */
export function jiexi_csv(wenben: string): JiexiHang[] {
  const ganjing = wenben.replace(/^\ufeff+/, '') // BOM 只可能出现在文件最开头
  // 过滤全空行（所有单元格都是空白的不算数据）
  const hang_liebiao: string[][] = []
  for (const hang of csv_du_qu(ganjing)) {
    if (hang.some((dange) => dange.trim() !== '')) hang_liebiao.push(hang)
  }
  if (hang_liebiao.length === 0) {
    throw new JiexiCuowu('CSV 为空（连表头都没有）')
  }

  const biaotou = hang_liebiao[0].map((dange) => dange.trim())
  if (biaotou.join('\u0000') !== BIXU_LIE.join('\u0000') || biaotou.length !== BIXU_LIE.length) {
    throw new JiexiCuowu(`表头不符：${lie_biao_da_yinhao(biaotou)}（应为 ${lie_biao_da_yinhao(BIXU_LIE)}）`)
  }

  const jiexi_hao: JiexiHang[] = []
  for (let xia = 1; xia < hang_liebiao.length; xia++) {
    const hanghao = xia + 1 // 行号从 2 起（1 是表头）
    const hang = hang_liebiao[xia]
    if (hang.length !== BIXU_LIE.length) {
      // 列数不齐：打标移交清洗阶段（保证解析阶段不因单行失败而中断）
      jiexi_hao.push({ __hanghao__: hanghao, __huaihang__: [...hang] })
      continue
    }
    // 列名 → 去空白后的单元格值
    const jilu: Record<string, string> = {}
    for (let lie = 0; lie < BIXU_LIE.length; lie++) {
      jilu[BIXU_LIE[lie]] = hang[lie].trim()
    }
    jiexi_hao.push({ ...jilu, __hanghao__: hanghao })
  }
  return jiexi_hao
}

/**
 * 第二步：清洗 + 归类（逐行校验，合法进四档，非法进拒绝清单）。
 *
 * 校验顺序（先廉价后昂贵，问题全部收集后再决定去留）：
 *     列数 → 类别 → 期间格式 → 科目非空 → 单位合法 →
 *     来源/时间非空 → 数值换算 → 跨行去重。
 * 去重键 =（数据类别, 统计周期, 数据科目）——同一类别同一期间同一科目
 * 只允许一条，后到的重复行被拒（保留先到者，台账可追溯）。
 */
export function qingxi_bing_guilei(yuanshi_hang: readonly JiexiHang[]): DaoruJieguo {
  const yusuan: BiaozhunJilu[] = []
  const shishi: BiaozhunJilu[] = []
  const hangye: BiaozhunJilu[] = []
  const biangeng: BiaozhunJilu[] = []
  const jujue: JuJueHang[] = []
  const chongfu_jian = new Set<string>() // 去重键集合（JSON 串承载三元组，等价 Python 集合）

  for (const yuanshi of yuanshi_hang) {
    const hanghao = yuanshi.__hanghao__ ?? 0
    // —— 列数不齐（解析阶段打的标）——
    if ('__huaihang__' in yuanshi && yuanshi.__huaihang__ !== undefined) {
      jujue.push({
        hanghao,
        yuanyin: `列数不符（应为 ${BIXU_LIE.length} 列）`,
        yuanwen: yuanshi.__huaihang__,
      })
      continue
    }

    // —— 逐项校验，问题累积（一行可能有多处问题，一次报全）——
    const wenti: string[] = []
    const leibie = yuanshi['数据类别'] as string
    if (!(HEFA_LEIBIE as readonly string[]).includes(leibie)) {
      wenti.push(`未知类别：${leibie}`)
    }
    const qijian = yuanshi['统计周期'] as string
    if (!(_YUEDU_QIJIAN_GESHI.test(qijian) || _JIDU_QIJIAN_GESHI.test(qijian))) {
      wenti.push(`期间格式非法：${qijian}（应为 2026-01 或 2026-Q1）`)
    }
    const kemu = yuanshi['数据科目'] as string
    if (!kemu) {
      wenti.push('科目为空')
    }
    const danwei = yuanshi['单位'] as string
    if (danwei !== DANWEI_YUAN && danwei !== DANWEI_BAIFENBI
        && !(JISHU_DANWEI as readonly string[]).includes(danwei)) {
      wenti.push(`未知单位：${danwei}`)
    }
    for (const ziduan of ['数据来源', '更新时间'] as const) { // 台账追溯两字段必须非空
      if (!(yuanshi[ziduan] as string)) {
        wenti.push(`${ziduan}为空`)
      }
    }
    if (wenti.length > 0) {
      jujue.push({
        hanghao,
        yuanyin: wenti.join('；'),
        yuanwen: BIXU_LIE.map((c) => yuanshi[c] as string),
      })
      continue
    }

    // —— 数值换算（格式全对才值得换算；单位决定放大位数）——
    let shuzhi: number
    try {
      if (danwei === DANWEI_YUAN || danwei === DANWEI_BAIFENBI) {
        shuzhi = _jiexi_fangda_zhengshu(yuanshi['数值'] as string, 2) // 元→分 / %→基点，都是放大 100
      } else {
        shuzhi = _jiexi_fangda_zhengshu(yuanshi['数值'] as string, 0) // 计数：必须纯整数
      }
    } catch (cuo) {
      if (!(cuo instanceof JiexiCuowu)) throw cuo
      jujue.push({ hanghao, yuanyin: cuo.message, yuanwen: BIXU_LIE.map((c) => yuanshi[c] as string) })
      continue
    }

    // —— 跨行去重（同类别+同期间+同科目只留先到者）——
    const jian = JSON.stringify([leibie, qijian, kemu])
    if (chongfu_jian.has(jian)) {
      jujue.push({
        hanghao,
        yuanyin: `重复数据（${leibie}/${qijian}/${kemu} 已存在，保留先到者）`,
        yuanwen: BIXU_LIE.map((c) => yuanshi[c] as string),
      })
      continue
    }
    chongfu_jian.add(jian)

    // —— 构造标准记录并归档到对应类别 ——
    const jilu: BiaozhunJilu = {
      hanghao,
      leibie,
      qijian,
      kemu,
      shuzhi,
      danwei,
      laiyuan: yuanshi['数据来源'] as string,
      gengxin_shijian: yuanshi['更新时间'] as string,
      beizhu: yuanshi['备注'] as string,
    }
    if (leibie === LEIBIE_YUSUAN) {
      yusuan.push(jilu)
    } else if (leibie === LEIBIE_SHISHI) {
      shishi.push(jilu)
    } else if (leibie === LEIBIE_HANGYE) {
      hangye.push(jilu)
    } else {
      biangeng.push(jilu)
    }
  }

  // ruku_shu 用 getter 实时计算（对应 Python 的 @property）
  return {
    yusuan,
    shishi,
    hangye,
    biangeng,
    jujue,
    get ruku_shu(): number {
      return yusuan.length + shishi.length + hangye.length + biangeng.length
    },
  }
}

/** 组合便捷入口：解析 + 清洗归类一步到位（大多数调用方只用这个）。 */
export function daoru_csv(wenben: string): DaoruJieguo {
  return qingxi_bing_guilei(jiexi_csv(wenben))
}
