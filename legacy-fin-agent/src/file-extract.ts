// ======================================================================
// 文件文本提取层 —— 方案B 步骤 1 的【前置解包】：PDF/Word/CSV/TXT → 文本。
// 转写自 D:\AppProject\algo\file_extract.py（Python 版为唯一行为准绳）。
// ======================================================================
//
// 新增口径（用户指令 2026-08-30："工作流第一步是清洗数据，应该可以把 word
// 和 pdf 转换为可以处理的 csv……如果没有就加上"）：主体原本只吃 CSV/文本，
// 本模块补上"文件 → 文本"这一段，接在 llm_clean 智能分流【之前】——
//
//     文件(pdf/docx/csv/txt 字节) → file_extract.jiequ_wenben → 文本行
//                                 → llm_clean.zhineng_fenliu → data_ingest
//
// 职责边界（只做"解包"，不做"清洗"）：
//     1. 按扩展名分发格式（csv/txt 直读解码；docx 解 zip 读表格；pdf 解内容流）；
//     2. 把文档还原成"一行一行"的文本（docx 表格行 → 逗号分隔行；
//        PDF 的每个文本显示操作 → 一行）——格式归一化仍归 llm_clean
//        （程序直解或模型翻译），本模块不猜列语义、不补字段。
//     3. 【诚实边界（答辩可能被问）】只支持"文本型"文档：
//        · PDF：支持文本层 PDF（文字可选中复制）；【扫描件图片 PDF 不支持】
//         （需要 OCR，属 M5/AI 层未来工作）；
//        · Word：支持 .docx（OpenXML）；旧版二进制 .doc 不支持（提示另存）；
//        · .xlsx：按 2026-08-23 既定约定"Excel 里另存为 CSV"再导入。
//
// 命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
//     数据值用中文。零第三方依赖：zip 解包 / zlib / XML 解析均为 Node 原生
//     或本文件内自带的确定性实现（对应 Python 的 zipfile/ElementTree/zlib）。
//
// 数值纪律：本模块不做任何数值换算（文本原样透传，换算归 data_ingest）；
//     纯函数（无 I/O、无全局状态——字节进、文本出）。
//
// 命名对照表（拼音标识符 → 中文含义）：
//     jiequ_wenben        截取文本（总入口：按扩展名分发格式）
//     cong_docx_jiequ     从docx截取（解 zip + document.xml → 表格行文本）
//     cong_pdf_jiequ      从pdf截取（解内容流 → 文本显示操作 → 行文本）
//     JiequJieguo         截取结果（wenben 文本 + geshi 格式来源）
//     JiequCuowu          截取错误（坏文件/不支持类型，附人工建议）
//     _zijie_zhuan_wenben 字节转文本（utf-8 → gbk → latin-1 三级兜底）
//     _liu_jie            六角解（十六进制文本串解码，FEFF=BOM 优先）
//     _zifuchuan_jie      字符串解（PDF 字面串：转义还原 + 编码兜底）
//     qu_ming             去命名空间（XML 标签取本地名）
//     gui_fan             规范化单元格（含逗号/引号的单元格加 CSV 引号）
//     wenben / geshi      文本 / 格式（'csv' / 'txt' / 'docx' / 'pdf'）
//
// 口径依据：用户指令 2026-08-30（Word/PDF 转可处理文本）；docs\06 路线 3
//          （分层路由：解包是确定性程序活，翻译归 LLM）；llm_clean 既定
//          约定（.xlsx 另存为 CSV；扫描件/旧版 .doc 明确不支持）。
// ======================================================================

import { inflateRawSync, inflateSync } from 'node:zlib'

// ======================================================================
// 数据结构与异常区
// ======================================================================

/**
 * 截取错误（坏文件 / 不支持的类型）——附中文人工建议。
 *
 * 与逐行拒绝的区别（对齐 data_ingest 的两层失败观）：
 * 文件本身解不开 = 整文件问题，调用方拿到异常后应提示用户换格式；
 * 文本层的内容问题（坏行）由下游 data_ingest 逐行处理，与本模块无关。
 */
export class JiequCuowu extends Error {}

/** 截取结果：还原出的文本 + 格式来源（台账追溯用）。 */
export interface JiequJieguo {
  readonly wenben: string // 还原出的文本（一行一条记录，\n 分隔；末尾带换行）
  readonly geshi: string  // 格式来源（'csv' / 'txt' / 'docx' / 'pdf'）
}

// ======================================================================
// 内部工具区（编码兜底 / 解码 / 规范化）
// ======================================================================

/** 字节 → ISO-8859-1 串（字符码 = 字节值，无损桥接）。
 *  不用 TextDecoder('latin-1')：该标签在 Node 实际按 windows-1252 解码，
 *  0x80~0x9F 段与 Python 的 latin-1 不一致——这里手工逐字节映射保证逐字一致。 */
function latin1_zhuan_wenben(zijie: Uint8Array): string {
  const kuai: string[] = []
  let ben = ''
  for (let i = 0; i < zijie.length; i++) {
    ben += String.fromCharCode(zijie[i])
    if (ben.length >= 8192) {
      kuai.push(ben)
      ben = ''
    }
  }
  kuai.push(ben)
  return kuai.join('')
}

/** ISO-8859-1 串 → 字节（latin1_zhuan_wenben 的逆运算；超 0xFF 的字符回绕）。 */
function wenben_zhuan_latin1(wen: string): Uint8Array {
  const zijie = new Uint8Array(wen.length)
  for (let i = 0; i < wen.length; i++) zijie[i] = wen.charCodeAt(i) & 0xff
  return zijie
}

/** 剥掉开头所有 \ufeff（对应 Python 的 lstrip('\ufeff')）。 */
function bo_diao_bom(wen: string): string {
  return wen.replace(/^\ufeff+/, '')
}

// 严格模式解码器（非法字节序列即抛错 → 落到下一级兜底）
const _UTF8_YAN = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true })
const _GBK_YAN = new TextDecoder('gbk', { fatal: true, ignoreBOM: true })

/**
 * 文件字节 → 文本：utf-8 优先 → gbk 兜底 → latin-1 最后保底。
 *
 * BOM（\ufeff）在这里剥掉——"文件进来即干净文本"是本模块的契约；
 * 下游 data_ingest 的 BOM 剥除保留不动（双保险，口径不变）。
 */
function _zijie_zhuan_wenben(zijie: Uint8Array): string {
  for (const jie_ma_qi of [_UTF8_YAN, _GBK_YAN]) {
    try {
      return bo_diao_bom(jie_ma_qi.decode(zijie))
    } catch {
      continue // UnicodeDecodeError → 试下一级编码
    }
  }
  return bo_diao_bom(latin1_zhuan_wenben(zijie)) // latin-1 永不失败
}

/** 单个字节是否为 Python bytes \s（[ \t\n\v\f\r]）。 */
function _shi_baifujian_bai(fu: number): boolean {
  return fu === 0x20 || fu === 0x09 || fu === 0x0a || fu === 0x0b || fu === 0x0c || fu === 0x0d
}

/** ASCII 十六进制字符 → 0~15；非法返回 null。 */
function _shiliu_zhi(fu: number): number | null {
  if (fu >= 0x30 && fu <= 0x39) return fu - 0x30
  if (fu >= 0x41 && fu <= 0x46) return fu - 0x41 + 10
  if (fu >= 0x61 && fu <= 0x66) return fu - 0x61 + 10
  return null
}

// utf-16 解码器（非严格 → 解不开的字符给替换符 U+FFFD，对应 errors='replace'）
const _UTF16BE = new TextDecoder('utf-16be', { ignoreBOM: true })
const _UTF16LE = new TextDecoder('utf-16le', { ignoreBOM: true })

/**
 * PDF 十六进制文本串解码（<FEFF...> 形态）。
 *
 * 规则：带 FEFF/FFFE BOM → 按剩余字节 utf-16-be 解；无 BOM 但字节里
 * 有一半是 \x00（ASCII 文本的 utf-16 特征）→ 也按 utf-16-be 解；
 * 其余按 latin-1 保底（WinAnsi 旧字体）。解不开的字符用替换符，不抛。
 */
function _liu_jie(liu_zijie: Uint8Array): string {
  const ganjing: number[] = [] // re.sub(rb'\s+', b'', ...)：去全部字节空白
  for (const fu of liu_zijie) {
    if (!_shi_baifujian_bai(fu)) ganjing.push(fu)
  }
  if (ganjing.length === 0) return ''
  // bytes.fromhex：非十六进制字符 / 奇数个数字 → ValueError → 返回 ''
  if (ganjing.length % 2 !== 0) return ''
  const yuan = new Uint8Array(ganjing.length / 2)
  for (let i = 0; i < ganjing.length; i++) {
    const zhi = _shiliu_zhi(ganjing[i])
    if (zhi === null) return ''
    if (i % 2 === 0) yuan[i >> 1] = zhi << 4
    else yuan[i >> 1] |= zhi
  }
  if (yuan[0] === 0xfe && yuan[1] === 0xff) return _UTF16BE.decode(yuan.subarray(2))
  if (yuan[0] === 0xff && yuan[1] === 0xfe) return _UTF16LE.decode(yuan.subarray(2))
  if (yuan.length % 2 === 0 && yuan.includes(0)) return _UTF16BE.decode(yuan)
  return latin1_zhuan_wenben(yuan)
}

/** 转义映射表：反斜杠后单字节 → 还原字节（Python 的 tuoyi dict）。 */
const _TUOYI: Record<number, number> = {
  0x28: 0x28, // \( → (
  0x29: 0x29, // \) → )
  0x5c: 0x5c, // \\ → \
  0x6e: 0x0a, // \n → 换行
  0x72: 0x0d, // \r → 回车
  0x74: 0x09, // \t → 制表
  0x62: 0x08, // \b → 退格
  0x66: 0x0c, // \f → 换页
}

/**
 * PDF 字面字符串解码：( ... ) 形态——先还原转义，再挑编码。
 *
 * 转义表：\( \) \\ \n \r \t \b \f 与八进制 \ddd；未知转义丢弃。
 * 编码挑选与 _liu_jie 同思路（含 \x00 特征 → utf-16-be，否则 latin-1）。
 */
function _zifuchuan_jie(zifu_zijie: Uint8Array): string {
  const yuan: number[] = []
  let i = 0
  while (i < zifu_zijie.length) {
    if (zifu_zijie[i] === 0x5c) {
      // 反斜杠：看下一个字节
      const xia = i + 1 < zifu_zijie.length ? zifu_zijie[i + 1] : -1
      if (xia >= 0 && xia in _TUOYI) {
        yuan.push(_TUOYI[xia])
        i += 2
        continue
      }
      if (xia >= 0x30 && xia <= 0x39) {
        // 八进制 \ddd（最多三位）
        let n = 0
        let k = 0
        while (k < 3 && i + 1 + k < zifu_zijie.length) {
          const shu = zifu_zijie[i + 1 + k]
          if (shu < 0x30 || shu > 0x39) break
          n = n * 8 + (shu - 0x30)
          k += 1
        }
        // Python bytearray.append(n>255) 会 ValueError（\777 病态流）；
        // 这里按字节回绕容错，常规 \000~\377 行为一致
        yuan.push(n & 0xff)
        i += 1 + k
        continue
      }
      i += 1 // 未知转义：丢弃反斜杠
      continue
    }
    yuan.push(zifu_zijie[i])
    i += 1
  }
  const zijie = Uint8Array.from(yuan)
  if (zijie.length % 2 === 0 && zijie.includes(0)) return _UTF16BE.decode(zijie)
  return latin1_zhuan_wenben(zijie)
}

/** XML 标签取本地名（'{命名空间}tbl' → 'tbl'）——对命名空间宽容。
 *  ElementTree 把带命名空间的标签解析成 '{uri}本地名' 形态；本文件的
 *  迷你解析器保留 '前缀:本地名' 原文——两种形态都要剥到本地名，
 *  故在 '}' 之后再剥前缀冒号（XML 规范里 ':' 只作前缀分隔符，安全）。 */
export function qu_ming(tag: string): string {
  const ming = tag.includes('}') ? tag.slice(tag.lastIndexOf('}') + 1) : tag
  const mao_hao = ming.lastIndexOf(':')
  return mao_hao !== -1 ? ming.slice(mao_hao + 1) : ming
}

/**
 * 单元格列表 → 一行 CSV 文本：逗号拼接；含逗号/引号/换行的加引号。
 *
 * 引号转义 = CSV 标准规则（内部双引号翻倍）——下游 csv 解析器能解回，
 * 与 data_ingest 的解析口径天然互逆。
 */
export function gui_fan(cells: readonly string[]): string {
  const gui_lie: string[] = []
  for (const yuan_ge of cells) {
    let dange = yuan_ge
    if ([',', '"', '\n'].some((fu) => dange.includes(fu))) {
      dange = `"${dange.replace(/"/g, '""')}"`
    }
    gui_lie.push(dange)
  }
  return gui_lie.join(',')
}

// ======================================================================
// XML 迷你解析区（对齐 ElementTree 用到的最小语义：树结构 + .text）
// ======================================================================

/** XML 元素：原始标签名（含前缀）+ 首子元素前文本 + 子元素（对齐 ElementTree）。 */
interface XmlYuansu {
  tag: string
  text: string | null
  ziyuansu: XmlYuansu[]
}

/** 实体/字符引用解码（&amp; &lt; … 与 &#NN; &#xNN;）。 */
function _jie_ma_shiti(duan: string): string {
  if (!duan.includes('&')) return duan
  return duan.replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z][a-zA-Z0-9]*);/g, (quan, nei: string) => {
    if (nei[0] === '#') {
      const ma = nei[1] === 'x' || nei[1] === 'X'
        ? parseInt(nei.slice(2), 16)
        : parseInt(nei.slice(1), 10)
      return Number.isFinite(ma) ? String.fromCodePoint(ma) : quan
    }
    const ming_biao: Record<string, string> = { lt: '<', gt: '>', amp: '&', quot: '"', apos: "'" }
    return nei in ming_biao ? ming_biao[nei] : quan
  })
}

/** 文本归属：只收"首个子元素之前"的文本（对齐 ElementTree 的 .text 语义）。 */
function _ding_wenben(zhan: readonly XmlYuansu[], duan: string): void {
  const ding = zhan[zhan.length - 1]
  if (ding.ziyuansu.length === 0) ding.text = (ding.text ?? '') + duan
}

/**
 * XML 字节 → 元素树（虚拟根容纳唯一真根；处理 PI/注释/CDATA/DOCTYPE；
 * 标签不匹配等坏 XML 宽容吞下——坏文件拒绝主要靠 zip 层，与 ET 的
 * 严格性差异只影响病态输入，正常 docx 走不到）。
 */
function _jiexi_xml(xml_zijie: Uint8Array): XmlYuansu {
  const s = new TextDecoder('utf-8').decode(xml_zijie)
  const gen: XmlYuansu = { tag: '#xugen', text: null, ziyuansu: [] }
  const zhan: XmlYuansu[] = [gen]
  const zong = s.length
  let i = 0
  while (i < zong) {
    if (s[i] === '<') {
      if (s.startsWith('<!--', i)) { // 注释
        const zhong = s.indexOf('-->', i + 4)
        i = zhong === -1 ? zong : zhong + 3
        continue
      }
      if (s.startsWith('<![CDATA[', i)) { // CDATA：内容按字面文本收
        const zhong = s.indexOf(']]>', i + 9)
        _ding_wenben(zhan, s.slice(i + 9, zhong === -1 ? zong : zhong))
        i = zhong === -1 ? zong : zhong + 3
        continue
      }
      if (s.startsWith('<?', i)) { // 处理指令 / XML 声明
        const zhong = s.indexOf('?>', i + 2)
        i = zhong === -1 ? zong : zhong + 2
        continue
      }
      if (s.startsWith('<!', i)) { // DOCTYPE 等（不含内部子集的场景）
        const zhong = s.indexOf('>', i)
        i = zhong === -1 ? zong : zhong + 1
        continue
      }
      if (s.startsWith('</', i)) { // 结束标签：弹栈（多余闭合宽容跳过）
        const zhong = s.indexOf('>', i)
        if (zhan.length > 1) zhan.pop()
        i = zhong === -1 ? zong : zhong + 1
        continue
      }
      // 起始标签：找 '>'（属性值里引号包裹的 '>' 不算结束）
      let j = i + 1
      let yinhao = ''
      while (j < zong) {
        const fu = s[j]
        if (yinhao !== '') {
          if (fu === yinhao) yinhao = ''
        } else if (fu === '"' || fu === "'") {
          yinhao = fu
        } else if (fu === '>') {
          break
        }
        j += 1
      }
      const jian_jian = j === zong ? zong : j // '>' 下标
      const zi_bi = j > i + 1 && s[j - 1] === '/' // 自闭合（<w:tab/>）
      let ming_zhong = i + 1 // 标签名 = '<' 后到首个空白 / '/' / '>'
      while (ming_zhong < jian_jian && s[ming_zhong] !== ' ' && s[ming_zhong] !== '\t'
             && s[ming_zhong] !== '\r' && s[ming_zhong] !== '\n' && s[ming_zhong] !== '/') {
        ming_zhong += 1
      }
      const yuansu: XmlYuansu = { tag: s.slice(i + 1, ming_zhong), text: null, ziyuansu: [] }
      zhan[zhan.length - 1].ziyuansu.push(yuansu)
      if (!zi_bi) zhan.push(yuansu)
      i = jian_jian + 1
      continue
    }
    const xia = s.indexOf('<', i) // 标签间的文本
    const duan = s.slice(i, xia === -1 ? zong : xia)
    if (duan !== '') _ding_wenben(zhan, _jie_ma_shiti(duan))
    i = xia === -1 ? zong : xia
  }
  return gen
}

/** 先序遍历（对齐 ElementTree 的 .iter()：先自身、再逐子树）。 */
function* _xml_bian_li(yuansu: XmlYuansu): Generator<XmlYuansu> {
  yield yuansu
  for (const zi of yuansu.ziyuansu) yield* _xml_bian_li(zi)
}

// ======================================================================
// zip 解包区（对应 Python zipfile 的最小读取路径：EOCD → 中央目录 → 本地头）
// ======================================================================

const _du_u16 = (z: Uint8Array, p: number): number => z[p] | (z[p + 1] << 8)
const _du_u32 = (z: Uint8Array, p: number): number =>
  (z[p] | (z[p + 1] << 8) | (z[p + 2] << 16) | (z[p + 3] << 24)) >>> 0

/**
 * 读 zip 档案里的单个成员（按名字，UTF-8 名字）。
 * 报错语义对齐 Python zipfile：非 zip → Error('File is not a zip file')，
 * 成员不存在 → Error("'成员名'")（KeyError 的 str 形态）。
 * 支持 stored(0) 与 deflate(8) 两种压缩方法（真实 docx 用 deflate）。
 */
function _du_zip_chengyuan(zijie: Uint8Array, ming: string): Uint8Array {
  // 找 EOCD 记录（0x06054b50）——从尾部向前扫，留足注释区/65535 搜索窗
  let eocd = -1
  const zui_xiao = Math.max(0, zijie.length - 22 - 65535 - 18)
  for (let i = zijie.length - 22; i >= zui_xiao; i--) {
    if (zijie[i] === 0x50 && zijie[i + 1] === 0x4b && zijie[i + 2] === 0x05 && zijie[i + 3] === 0x06) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('File is not a zip file')
  const chengyuan_shu = _du_u16(zijie, eocd + 10)
  let p = _du_u32(zijie, eocd + 16) // 中央目录起始偏移
  for (let x = 0; x < chengyuan_shu; x++) {
    if (p + 46 > zijie.length || _du_u32(zijie, p) !== 0x02014b50) {
      throw new Error('File is not a zip file') // 中央目录损坏
    }
    const ya_suo_fa = _du_u16(zijie, p + 10)
    const ya_suo_da_xiao = _du_u32(zijie, p + 20)
    const ming_chang = _du_u16(zijie, p + 28)
    const e_wai_chang = _du_u16(zijie, p + 30)
    const zhu_shi_chang = _du_u16(zijie, p + 32)
    const ben_di_tou = _du_u32(zijie, p + 42)
    const ming_zijie = zijie.subarray(p + 46, p + 46 + ming_chang)
    p += 46 + ming_chang + e_wai_chang + zhu_shi_chang
    if (new TextDecoder('utf-8').decode(ming_zijie) !== ming) continue
    // 命中成员：本地文件头里再跳一次名字/扩展字段才是数据起点
    if (_du_u32(zijie, ben_di_tou) !== 0x04034b50) throw new Error('File is not a zip file')
    const ben_di_ming = _du_u16(zijie, ben_di_tou + 26)
    const ben_di_e_wai = _du_u16(zijie, ben_di_tou + 28)
    const qi = ben_di_tou + 30 + ben_di_ming + ben_di_e_wai
    const shu_ju = zijie.subarray(qi, qi + ya_suo_da_xiao)
    if (ya_suo_fa === 0) return shu_ju.slice() // stored：原样
    if (ya_suo_fa === 8) return inflateRawSync(shu_ju) // deflate：裸 deflate 流
    throw new Error(`不支持的压缩方法：${ya_suo_fa}`) // Python 走 NotImplementedError（病态 docx）
  }
  throw new Error(`'${ming}'`) // KeyError 语义：档案里没有这个成员
}

// ======================================================================
// docx 提取区（标准库 zip + 自带 XML 解析，零第三方依赖）
// ======================================================================

/**
 * 一个段落/单元格容器 → 纯文本：收集全部 w:t，制表符当逗号。
 *
 * w:tab → ','：Word 里"用 Tab 分列"的段落（老报表常见）能直接变成
 * 可解析的 CSV 行；w:br/w:cr 忽略（单元格内换行不作分行依据）。
 */
function _duan_wenben(danyuan: XmlYuansu): string {
  const bujian: string[] = []
  for (const yuansu of _xml_bian_li(danyuan)) {
    const ming = qu_ming(yuansu.tag)
    if (ming === 't') bujian.push(yuansu.text ?? '')
    else if (ming === 'tab') bujian.push(',')
  }
  return bujian.join('')
}

/**
 * Word (.docx) 字节 → 文本：顶层块顺序还原，表格行 → CSV 行。
 *
 * 还原规则：body 顶层按出现顺序遍历——w:tbl 的每个 w:tr 一行（单元格
 * 逗号分隔、必要时加引号）；w:p 一行（段落文本）。空行保留（下游
 * data_ingest 本就跳过全空行）。
 */
export function cong_docx_jiequ(zijie: Uint8Array): string {
  let xml_zijie: Uint8Array
  try {
    xml_zijie = _du_zip_chengyuan(zijie, 'word/document.xml')
  } catch (cuo) {
    throw new JiequCuowu(
      `不是有效的 .docx（${(cuo as Error).message}）；旧版 .doc 请先另存为 .docx 再导入`)
  }
  let gen: XmlYuansu
  try {
    gen = _jiexi_xml(xml_zijie)
  } catch (cuo) {
    throw new JiequCuowu(`document.xml 解析失败（${(cuo as Error).message}）——文件可能已损坏`)
  }
  let body: XmlYuansu | null = null
  for (const yuansu of _xml_bian_li(gen)) {
    if (qu_ming(yuansu.tag) === 'body') {
      body = yuansu
      break
    }
  }
  if (body === null) {
    throw new JiequCuowu('document.xml 缺少 body——不是 Word 正文文档')
  }
  const hang_lie: string[] = []
  for (const kuai of body.ziyuansu) { // 只走顶层，嵌套表随外层单元格走
    const ming = qu_ming(kuai.tag)
    if (ming === 'tbl') {
      for (const hang of kuai.ziyuansu) { // 直接子元素 = w:tr
        if (qu_ming(hang.tag) !== 'tr') continue
        const danyuan_lie: string[] = []
        for (const dan of hang.ziyuansu) {
          if (qu_ming(dan.tag) === 'tc') danyuan_lie.push(_duan_wenben(dan))
        }
        hang_lie.push(gui_fan(danyuan_lie))
      }
    } else if (ming === 'p') {
      hang_lie.push(_duan_wenben(kuai))
    }
  }
  return hang_lie.join('\n') + '\n'
}

// ======================================================================
// pdf 提取区（zlib 解流 + 文本显示操作扫描）
// ======================================================================

/** 内容流定位：stream ... endstream 之间全部视为候选内容（不解析 xref，
 *  不依赖 /Length——宽容换取对"生成器各异的 PDF"的兼容面）。
 *  DOTALL 语义用 s 旗标；(.*?) 非贪婪同 Python。 */
const _LIU_ZE = /stream[\r\n]+(.*?)endstream/gs

/** 内容流词法：六角串 / 字面串 / 数字 / 运算符（四类记号按出现顺序扫）。
 *  ——定位跟踪需要"数字+运算符"的原始顺序，故用一个总正则顺序消费。
 *  字节 \s 限定为 [ \t\n\v\f\r]；\\[^\n] 对齐 Python 字节正则的 '.'（不吞 \r）。 */
const _CIXU_ZE = /<([0-9A-Fa-f \t\n\x0b\x0c\r]*)>|\(((?:[^()\\]|\\[^\n])*)\)|([-+]?\d*\.?\d+)|([A-Za-z'"*]+)/g

/** 行分组的 y 容差（pt）：同一视觉行的片段 y 理论相同，
 *  浮点累积可能有 ±0.05 级漂移，容差内视为同行 */
const _HANG_RONGCHA = 0.05

/**
 * 一个内容流 → (y 坐标, 文本) 片段序列——带定位跟踪的词法扫描。
 *
 * 为什么需要跟踪 y：真实 PDF 的一行文字经常被拆成多个显示片段
 * （逐格排版的表格、字体切换、字距调整都会拆）——只按"一个显示
 * 操作一行"还原会把一行撕成碎片。这里按出现顺序消费词法记号，
 * 跟踪文本纵坐标（Tm 绝对 / Td 相对 / TD·T*·TL 行距体系），
 * 把每个显示操作记在它自己的 y 上；同 y 的片段由调用方拼回一行。
 *
 * 操作数语义（关键，防串味）：数字先进【操作数栈】，每个算子只取
 * 自己需要的操作数、用完即清栈——字号（Tf 的 9）、字距（TJ 的调整
 * 值）绝不会污染下一条定位算子的 y。支持算子：Tm、Td、TD、T*、TL、'、"；
 * TJ 数组内的字符串顺序保留、调整数字丢弃。BT/ET 不重置 y（绝对
 * 定位的排版器跨块共用坐标系；相对定位的排版器自会用 Td 归位）。
 */
function _liuxing_zhui_zong(neibu: Uint8Array): Array<[number, string]> {
  const pian: Array<[number, string]> = []
  let y = 0
  let xingju = 0 // TL 行距（T* 每次上移一行）
  let dengdai: string[] = [] // 待显示的字符串（TJ 数组会攒多个）
  const shu_zhan: number[] = [] // 操作数栈（数字进、算子取、取完清）
  const wen = latin1_zhuan_wenben(neibu) // 字节→latin1 串：字符码=字节值，正则无损桥接
  for (const pipei of wen.matchAll(_CIXU_ZE)) {
    const [, liu_zi, zifu_zi, shu_zi, yunsuan] = pipei
    if (liu_zi !== undefined) {
      dengdai.push(_liu_jie(wenben_zhuan_latin1(liu_zi)))
    } else if (zifu_zi !== undefined) {
      dengdai.push(_zifuchuan_jie(wenben_zhuan_latin1(zifu_zi)))
    } else if (shu_zi !== undefined) {
      shu_zhan.push(parseFloat(shu_zi)) // 数字只进栈——清栈是算子的职责
    } else {
      // 运算符记号：消费操作数后清栈
      if (yunsuan === 'Tm') {
        // 文本矩阵：六个操作数，末个 = 绝对 y
        if (shu_zhan.length > 0) y = shu_zhan[shu_zhan.length - 1]
      } else if (yunsuan === 'Td') {
        // 相对移动：y += ty（操作数栈顶）
        if (shu_zhan.length > 0) y += shu_zhan[shu_zhan.length - 1]
      } else if (yunsuan === 'TD') {
        // 设行距并移动：tl = -ty；y += ty
        if (shu_zhan.length > 0) {
          xingju = -shu_zhan[shu_zhan.length - 1]
          y += shu_zhan[shu_zhan.length - 1]
        }
      } else if (yunsuan === 'TL') {
        // 设行距
        if (shu_zhan.length > 0) xingju = shu_zhan[shu_zhan.length - 1]
      } else if (yunsuan === 'T*' || yunsuan === "'" || yunsuan === '"') {
        // 上移一行；'/" 顺带显示（字符串已在待显区）
        y -= xingju
        if (yunsuan !== 'T*' && dengdai.length > 0) {
          pian.push([y, dengdai.join('')])
          dengdai = []
        }
      } else if (yunsuan === 'Tj' || yunsuan === 'TJ') {
        if (dengdai.length > 0) {
          pian.push([y, dengdai.join('')])
          dengdai = []
        }
      }
      shu_zhan.length = 0 // 算子消费完毕清栈（数字不清——栈是它家）
    }
  }
  if (dengdai.length > 0) { // 流尾悬挂的字符串（病态流，容错收编）
    pian.push([y, dengdai.join('')])
  }
  return pian
}

/**
 * PDF 字节 → 文本：逐流解压 → 定位跟踪扫描 → 同行片段拼回一行。
 *
 * 诚实边界：只处理"文本型 PDF"。解不出任何内容流（典型如扫描件
 * 图片 PDF）时抛 JiequCuowu 并说明原因——绝不输出空文本假装成功。
 * 行还原规则：同一视觉行（y 相同，容差 _HANG_RONGCHA）的多个显示
 * 片段按出现顺序拼成一行——这既兼容"一行拆多片"的真实 PDF
 * （逐格排版的表格/字体切换都会拆），也让逐格排版的表格文档
 * 解包后恰好还原出逗号分隔行。
 */
export function cong_pdf_jiequ(zijie: Uint8Array): string {
  const quan_wen = latin1_zhuan_wenben(zijie) // 字节→latin1 串做字节级正则扫描
  const liu_lie: Uint8Array[] = []
  for (const pipei of quan_wen.matchAll(_LIU_ZE)) {
    let neibu = wenben_zhuan_latin1(pipei[1].replace(/[\r\n]+$/, '')) // rstrip(b'\r\n')
    try {
      neibu = inflateSync(neibu) // FlateDecode 流
    } catch {
      // zlib.error → 未压缩流原样使用
    }
    liu_lie.push(neibu)
  }
  if (liu_lie.length === 0) {
    throw new JiequCuowu('PDF 中没有内容流——可能是扫描件图片 PDF（不支持，'
                         + '需要 OCR）；请改用文本型 PDF 或另存为 CSV/Word')
  }
  const hang_lie: string[] = []
  for (const neibu of liu_lie) {
    const pian = _liuxing_zhui_zong(neibu)
    if (pian.length === 0) continue
    // 同 y 分组拼行（顺序保持；y 差在容差内视为同一行）
    let [dang_qian_y, dang_qian_wen] = pian[0]
    for (const [y, wen] of pian.slice(1)) {
      if (Math.abs(y - dang_qian_y) <= _HANG_RONGCHA) {
        dang_qian_wen += wen // 同一行：顺序拼接
      } else {
        hang_lie.push(dang_qian_wen)
        dang_qian_y = y
        dang_qian_wen = wen
      }
    }
    hang_lie.push(dang_qian_wen)
  }
  const fei_kong = hang_lie.filter((hang) => hang.trim() !== '')
  return fei_kong.join('\n') + '\n'
}

// ======================================================================
// 对外入口区（按扩展名分发）
// ======================================================================

/**
 * 文件（名字 + 字节）→ 截取结果：按扩展名分发到对应解包器。
 *
 * 分发表：csv/txt 直读解码；docx/pdf 走专用解包器；doc/xls/xlsx 给
 * "另存为"建议（诚实拒绝，不静默硬解）；其余类型整件拒绝。
 */
export function jiequ_wenben(ming: string, zijie: Uint8Array): JiequJieguo {
  const xiaoxie = ming.toLowerCase()
  const houzhui = ming.includes('.') ? xiaoxie.slice(xiaoxie.lastIndexOf('.') + 1) : ''
  if (houzhui === 'csv' || houzhui === 'txt') {
    return { wenben: _zijie_zhuan_wenben(zijie), geshi: houzhui }
  }
  if (houzhui === 'docx') {
    return { wenben: cong_docx_jiequ(zijie), geshi: 'docx' }
  }
  if (houzhui === 'pdf') {
    return { wenben: cong_pdf_jiequ(zijie), geshi: 'pdf' }
  }
  if (houzhui === 'doc') {
    throw new JiequCuowu('旧版 .doc 暂不支持：请用 Word/WPS 另存为 .docx 再导入')
  }
  if (houzhui === 'xls' || houzhui === 'xlsx') {
    throw new JiequCuowu('Excel 文件按既定约定请先"另存为 CSV"再导入'
                         + '（与 llm_clean 2026-08-23 口径一致）')
  }
  throw new JiequCuowu(`不认识的文件类型：${yuan_wen_dai_yinhao(ming)}（支持 csv/txt/docx/pdf）`)
}

/** Python repr(str) 的近似实现——报错文案里 {ming!r} 的逐字对应。 */
function yuan_wen_dai_yinhao(s: string): string {
  const zhuan_yi = (b: string): string =>
    b.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t')
  if (s.includes("'") && !s.includes('"')) {
    return `"${zhuan_yi(s).replace(/"/g, '\\"')}"`
  }
  return `'${zhuan_yi(s).replace(/'/g, "\\'")}'`
}
