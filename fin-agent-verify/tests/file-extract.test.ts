// ======================================================================
// file_extract 文件文本提取层的测试（转写自
// D:\AppProject\algo\tests\test_file_extract.py，全部离线、期望值手算写死）。
// ======================================================================
//
// 口径依据：algo/file_extract.py 模块头（用户指令 2026-08-30 新增口径：
// 步骤 1 前置解包，PDF/Word/CSV/TXT → 文本，供 llm_clean 智能分流消费）。
//
// 用例目录（四大组，对应模块的四个公开行为）：
//     TestFenfa    ×5  按扩展名分发：csv/txt 直读三级解码、坏类型/旧版
//                      .doc/.xlsx 的诚实拒绝
//     TestDocx     ×5  表格还原、段落混排、引号转义、制表符转逗号、坏 zip
//     TestPdf      ×7  六角串(BOM)、同行碎片拼行、Td/T*/TL 换行、字面串
//                      转义、TJ 数组、多流(Flate+裸流)、无内容流(扫描件)拒绝
//     TestJicheng  ×1  与 data_ingest 接缝：提取文本直接入库零拒绝
//   （Python 测试文件头写的"14 用例"是旧版计数，实际 18 条用例全部转写。）
//
// 夹具策略：全部夹具在测试内【手工构造】（自拼 zip 成 docx、bytes 拼 PDF
// 内容流）——不依赖任何外部生成器（依赖方向纪律：主体永不引用生成器）；
// 期望值全部手工推演写死，禁止现算自证。
// 十六进制夹具速查（UTF-16BE，含 FEFF BOM）：测=6D4B 试=8BD5 实=5B9E。
// ======================================================================

import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { crc32, deflateSync } from 'node:zlib'

import { daoru_csv } from '../../plugins/fin-agent/src/data-ingest.ts' // 集成断言用：提取文本应能直接入库
import {
  JiequCuowu,
  cong_docx_jiequ,
  cong_pdf_jiequ,
  jiequ_wenben,
} from '../../plugins/fin-agent/src/file-extract.ts'

/** 最小 docx 的 document.xml 样板（表格两行 × 两列，首行当表头）——
 *  解包器只认 w:body/w:tbl/w:tr/w:tc/w:t 结构，不要求 tblPr 等装饰节点 */
const DOC_XML = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
  + '<w:body><w:tbl><w:tr>'
  + '<w:tc><w:p><w:r><w:t>数据类别</w:t></w:r></w:p></w:tc>'
  + '<w:tc><w:p><w:r><w:t>统计周期</w:t></w:r></w:p></w:tc>'
  + '</w:tr><w:tr>'
  + '<w:tc><w:p><w:r><w:t>预算基础</w:t></w:r></w:p></w:tc>'
  + '<w:tc><w:p><w:r><w:t>2026-Q1</w:t></w:r></w:p></w:tc>'
  + '</w:tr></w:tbl></w:body></w:document>')

/** 八列规范表头（TestJicheng 用）——与 data_ingest.BIXU_LIE 逐字一致 */
const BIAOTOU_8LIE = ['数据类别', '统计周期', '数据科目', '数值', '单位',
  '数据来源', '更新时间', '备注'] as const

// ----------------------------------------------------------------------
// 夹具工具：最小 zip 写包器（对应 Python 测试里的 zipfile.writestr）
// ----------------------------------------------------------------------

/** 单成员档案描述：成员名 + 内容字节。 */
interface ChengYuan {
  ming: string
  nei: Uint8Array
}

/** 手工拼一个 zip 字节（成员一律 stored 存储 + 正确 CRC32——自产自读足够，
 *  也符合 Python zipfile.ZipFile 默认 ZIP_STORED 的产物形态）。 */
function da_bao_zip(cheng_yuan: readonly ChengYuan[]): Uint8Array {
  const ben_di_kuai: Buffer[] = []
  const zhong_yang_kuai: Buffer[] = []
  let pian_yi = 0
  for (const { ming, nei } of cheng_yuan) {
    const ming_buf = Buffer.from(ming, 'utf-8')
    const jiao_yan = crc32(nei) as number
    // —— 本地文件头（30 字节 + 名字 + 数据）——
    const ben_di = Buffer.alloc(30)
    ben_di.writeUInt32LE(0x04034b50, 0) // 本地头签名
    ben_di.writeUInt16LE(20, 4)         // 解压所需版本
    ben_di.writeUInt16LE(0, 6)          // 通用标志（无数据描述符）
    ben_di.writeUInt16LE(0, 8)          // 压缩方法：stored
    ben_di.writeUInt16LE(0, 10)         // 时间
    ben_di.writeUInt16LE(0x21, 12)      // 日期（1980-01-01，合法占位）
    ben_di.writeUInt32LE(jiao_yan, 14)  // CRC32
    ben_di.writeUInt32LE(nei.length, 18) // 压缩后大小
    ben_di.writeUInt32LE(nei.length, 22) // 原始大小
    ben_di.writeUInt16LE(ming_buf.length, 26)
    ben_di.writeUInt16LE(0, 28)         // 扩展字段长
    ben_di_kuai.push(ben_di, ming_buf, Buffer.from(nei))
    // —— 中央目录记录（46 字节 + 名字）——
    const zhong = Buffer.alloc(46)
    zhong.writeUInt32LE(0x02014b50, 0) // 中央目录签名
    zhong.writeUInt16LE(20, 4)         // 打包版本
    zhong.writeUInt16LE(20, 6)         // 解压版本
    zhong.writeUInt16LE(0, 10)         // 压缩方法
    zhong.writeUInt16LE(0x21, 14)      // 日期（同上）
    zhong.writeUInt32LE(jiao_yan, 16)  // CRC32
    zhong.writeUInt32LE(nei.length, 20)
    zhong.writeUInt32LE(nei.length, 24)
    zhong.writeUInt16LE(ming_buf.length, 28)
    zhong.writeUInt32LE(pian_yi, 42)   // 本地头偏移
    zhong_yang_kuai.push(zhong, ming_buf)
    pian_yi += 30 + ming_buf.length + nei.length
  }
  const zhong_yang_qu = Buffer.concat(zhong_yang_kuai)
  // —— EOCD 结束记录（22 字节）——
  const eocd = Buffer.alloc(22)
  eocd.writeUInt32LE(0x06054b50, 0) // EOCD 签名
  eocd.writeUInt16LE(cheng_yuan.length, 8) // 本盘成员数
  eocd.writeUInt16LE(cheng_yuan.length, 10) // 总成员数
  eocd.writeUInt32LE(zhong_yang_qu.length, 12) // 中央目录大小
  eocd.writeUInt32LE(pian_yi, 16) // 中央目录偏移
  return Buffer.concat([...ben_di_kuai, zhong_yang_qu, eocd])
}

/** 手工拼一个最小 docx 字节（只有 document.xml 一个成员——解包器宽容）。 */
function _zao_docx(xml_wen: string): Uint8Array {
  return da_bao_zip([{ ming: 'word/document.xml', nei: Buffer.from(xml_wen, 'utf-8') }])
}

/** 拼一个单元格 XML 片段：<w:tc><w:p><w:r><w:t>文本</w:t>…… */
function _zao_danyuan(wen: string): string {
  return `<w:tc><w:p><w:r><w:t>${wen}</w:t></w:r></w:p></w:tc>`
}

// ======================================================================

describe('TestFenfa', () => {
  // jiequ_wenben 按扩展名分发：csv/txt 直读、坏类型/不支持类型拒绝。

  it('test_csv_bom_boduan', () => {
    // CSV + UTF-8 BOM：BOM 剥掉、内容原样（utf-8 优先解码）。
    // 输入字节 = EF BB BF + utf-8 编码正文；期望值手抄自 data_ingest
    // 演示方言首行（BOM 由本模块剥，正文逐字保留）。
    const zijie = Buffer.from('\ufeff数据类别,统计周期\n预算基础,2026-Q1\n', 'utf-8')
    const jg = jiequ_wenben('a.csv', zijie)
    assert.equal(typeof jg.wenben, 'string') // 返回结构而非裸字符串
    assert.equal(jg.geshi, 'csv')            // 格式来源留台账
    assert.equal(jg.wenben, '数据类别,统计周期\n预算基础,2026-Q1\n')
  })

  it('test_txt_gbk_doudi', () => {
    // TXT + GBK 字节：utf-8 解不开自动落到 gbk（Excel/记事本旧文件常见）。
    // GBK 字节硬编码（预=D4A4 算=CBE3 基=BBF9 础=B4A1 营=D3AA 收=CAD5）
    const gbk_zijie = Uint8Array.from(
      [0xd4, 0xa4, 0xcb, 0xe3, 0xbb, 0xf9, 0xb4, 0xa1, 0x2c, 0xd3, 0xaa, 0xca, 0xd5, 0x0a])
    const jg = jiequ_wenben('b.txt', gbk_zijie)
    assert.equal(jg.geshi, 'txt')
    assert.equal(jg.wenben, '预算基础,营收\n')
  })

  it('test_buming_leixing_jujue', () => {
    // 不认识的扩展名整件拒绝，信息里列出支持类型（人工可自助）。
    // 断言点：异常类型 + 报错信息含支持清单——拒绝要"拒绝得明白"，
    // 不能只抛一句空泛的"格式错误"。
    assert.throws(() => {
      jiequ_wenben('c.zip7', Buffer.from('whatever'))
    }, (cuo: unknown) => {
      assert.ok(cuo instanceof JiequCuowu)
      assert.ok((cuo as Error).message.includes('csv/txt/docx/pdf'))
      return true
    })
  })

  it('test_doc_lingcun_jianyi', () => {
    // 旧版 .doc：诚实拒绝并给出"另存为 .docx"建议（不硬解二进制）。
    // .doc 是 OLE 复合文档（非 zip），硬解成本高收益低——按诚实边界
    // 拒绝并给自助路径，比悄悄输出乱码文本更负责。
    assert.throws(() => {
      jiequ_wenben('lao.doc', Buffer.from('whatever'))
    }, (cuo: unknown) => {
      assert.ok(cuo instanceof JiequCuowu)
      assert.ok((cuo as Error).message.includes('另存为 .docx'))
      return true
    })
  })

  it('test_xlsx_jianding_koujing', () => {
    // .xlsx：按 2026-08-23 既定约定拒绝（另存为 CSV），口径不漂移。
    // 这条守住的是"约定一致性"：llm_clean 早已把"Excel 另存为 CSV"
    // 写进提示词约定，本模块新增后不得悄悄扩大口径。
    assert.throws(() => {
      jiequ_wenben('biao.xlsx', Buffer.from('whatever'))
    }, (cuo: unknown) => {
      assert.ok(cuo instanceof JiequCuowu)
      assert.ok((cuo as Error).message.includes('另存为 CSV'))
      return true
    })
  })
})

describe('TestDocx', () => {
  // cong_docx_jiequ：表格还原 / 段落混排 / 引号转义 / 制表符 / 坏文件。
  // 五条用例对应还原规则的五个决定性细节：顺序、混排、转义、Tab、容错。

  it('test_biaoge_huanyuan', () => {
    // 两行两列表格 → 两行逗号文本（出现顺序保持，无多余空白）。
    // 期望值手抄 DOC_XML 的内容顺序——"顺序保持"是台账可信的前提。
    assert.equal(cong_docx_jiequ(_zao_docx(DOC_XML)),
      '数据类别,统计周期\n预算基础,2026-Q1\n')
  })

  it('test_duanyu_biaoge_hunpai', () => {
    // 段落与表格混排：按出现顺序还原，段落一行为一行。
    // 夹具顺序 = 段落、表格(1行)、段落——验证遍历不重排、不丢段。
    const xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
      + '<w:body><w:p><w:r><w:t>老板发来的Q1快报：</w:t></w:r></w:p>'
      + '<w:tbl><w:tr>' + _zao_danyuan('营收') + _zao_danyuan('210000.00')
      + '</w:tr></w:tbl>'
      + '<w:p><w:r><w:t>单位都是元。</w:t></w:r></w:p></w:body></w:document>')
    assert.equal(cong_docx_jiequ(_zao_docx(xml)),
      '老板发来的Q1快报：\n营收,210000.00\n单位都是元。\n')
  })

  it('test_danyuan_douhao_yinhao', () => {
    // 单元格含逗号 → CSV 引号包裹（下游 csv 解析器可解回，口径互逆）。
    // 期望值手写：'"备注,带逗号",普通'——引号包裹是 CSV 标准转义，
    // data_ingest 底层用 csv 解析，能原样解回单元格。
    const xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
      + '<w:body><w:tbl><w:tr>' + _zao_danyuan('备注,带逗号')
      + _zao_danyuan('普通') + '</w:tr></w:tbl></w:body></w:document>')
    assert.equal(cong_docx_jiequ(_zao_docx(xml)),
      '"备注,带逗号",普通\n')
  })

  it('test_tab_dang_douhao', () => {
    // 段落里的制表符当逗号（"Tab 分列"的老报表直接变可解析行）。
    const xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
      + '<w:body><w:p><w:r><w:t>营收</w:t></w:r><w:tab/>'
      + '<w:r><w:t>210000.00</w:t></w:r></w:p></w:body></w:document>')
    assert.equal(cong_docx_jiequ(_zao_docx(xml)), '营收,210000.00\n')
  })

  it('test_huai_zip_jujue', () => {
    // 坏 zip / 缺 document.xml：整件拒绝 + 人工建议（两层都断）。
    assert.throws(() => {
      cong_docx_jiequ(Buffer.from('zhe bu shi zip')) // 不是 zip
    }, JiequCuowu)
    const kong = da_bao_zip([{ ming: 'qita.txt', nei: Buffer.from('x') }]) // 是 zip 但缺正文
    assert.throws(() => {
      cong_docx_jiequ(kong)
    }, JiequCuowu)
  })
})

describe('TestPdf', () => {
  // cong_pdf_jiequ：六角串 / 字面串 / TJ 数组 / 多流 / 无内容流。
  // （ASCII 夹具直接 utf-8 编码即字节原文。）

  it('test_liuchuan_liujinjie', () => {
    // 十六进制文本串（带 FEFF BOM）：UTF-16BE 解码成中文+ASCII。
    // 夹具换算：预=9884 算=7B97；'2026-Q1' 的 UTF-16BE 每字符前补 00。
    // /Length 故意写错——提取器不解析 xref/Length（宽容设计）仍须解出。
    const liu = Buffer.from('%PDF-1.4\n1 0 obj\n<</Length 30>>\nstream\nBT\n'
      + '<FEFF98847B970032003000320036002D00510031> Tj\nET\n'
      + 'endstream\nendobj\n%%EOF', 'utf-8')
    assert.equal(cong_pdf_jiequ(liu), '预算2026-Q1\n')
  })

  it('test_tonghang_fensui_pinjie', () => {
    // 同一视觉行（y 相同）的多个片段拼回一行——逐格排版的表格能还原。
    // 场景：'营收' '，' '100000.00' 三段各在固定列位（Tm 定位、同 y），
    // 解包后应拼回 '营收,100000.00'——真实 PDF 的一行常被排版器拆成
    // 多个片段，这是 v4 新增的定位跟踪能力的核心回归。
    // 手算：营=8425 收=6536；逗号与数字走字面串（latin-1）。
    const liu = Buffer.from('stream\nBT\n'
      + '1 0 0 1 40 700 Tm <FEFF84256536> Tj\n'
      + '1 0 0 1 120 700 Tm (,) Tj\n'
      + '1 0 0 1 160 700 Tm (100000.00) Tj\n'
      + 'ET\nendstream', 'utf-8')
    assert.equal(cong_pdf_jiequ(liu), '营收,100000.00\n')
  })

  it('test_Td_TX_huanhang', () => {
    // Td + T* + TL 行距体系：每个 T* 换一行（v2 平表 PDF 的排法）。
    // 手算：Td 后 y=800；TL=12 → 每个 T* 上移 12 → 两行 y=800/788，
    // 两行不同行 → 各自成行。这是向后兼容的回归用例。
    const liu = Buffer.from('stream\nBT\n/F1 9 Tf\n12 TL\n40 800 Td\n'
      + '(a) Tj\nT*\n(b) Tj\nET\nendstream', 'utf-8')
    assert.equal(cong_pdf_jiequ(liu), 'a\nb\n')
  })

  it('test_zimian_zhuanyi', () => {
    // 字面串：转义 \( \) 还原成括号本身；ASCII 按 latin-1 落地。
    const liu = Buffer.from('stream\n(a \\(b\\) c) Tj\nendstream', 'utf-8')
    assert.equal(cong_pdf_jiequ(liu), 'a (b) c\n')
  })

  it('test_shuzu_TJ_pinjie', () => {
    // TJ 数组：内部多个六角记号按顺序拼接成一行（实=5B9E 测=6D4B 点=70B9）。
    // 数组里的 2/4 是字距数字——提取器只取字符串记号，数字自动丢弃。
    const liu = Buffer.from('stream\n[(<FEFF5B9E> 2 <FEFF6D4B> 4 <FEFF70B9>] TJ\nendstream', 'utf-8')
    assert.equal(cong_pdf_jiequ(liu), '实测点\n')
  })

  it('test_duoliu_shunxu', () => {
    // 多个内容流（FlateDecode + 未压缩混合）：按流顺序拼接行。
    // 流 1 = zlib 压缩的 <FEFF6D4B8BD5>（测=6D4B 试=8BD5）——须先解压
    // 再扫描；流 2 = 未压缩字面串 (csv)。期望顺序 = 解压流在前。
    const ya_suo = deflateSync(Buffer.from('BT\n<FEFF6D4B8BD5> Tj\nET\n', 'utf-8'))
    const liu = Buffer.concat([
      Buffer.from('stream\n', 'utf-8'), ya_suo,
      Buffer.from('\nendstream\nstream\nBT\n(csv) Tj\nET\nendstream', 'utf-8'),
    ])
    assert.equal(cong_pdf_jiequ(liu), '测试\ncsv\n')
  })

  it('test_wu_liuchu_saomiaojian', () => {
    // 解不出任何内容流（扫描件图片 PDF 的典型形态）：诚实拒绝不装成功。
    assert.throws(() => {
      cong_pdf_jiequ(Buffer.from('%PDF-1.4\n%%EOF', 'utf-8'))
    }, (cuo: unknown) => {
      assert.ok(cuo instanceof JiequCuowu)
      assert.ok((cuo as Error).message.includes('扫描件'))
      return true
    })
  })
})

describe('TestJicheng', () => {
  // 与 data_ingest 的接缝：提取出的文本应能直接入库（零拒绝）。

  it('test_docx_wenben_neng_ruku', () => {
    // docx 八列表格 → 文本 → daoru_csv：一行合法数据应全部入库。
    // 期望值手算：220000.00 元 → 22000000 分（录入侧 ×100 换算）；
    // 归档类别 = 预算基础（yusuan 清单恰好 1 条）。
    const hang_lie = [
      BIAOTOU_8LIE,
      ['预算基础', '2026-Q1', '营收', '220000.00', '元',
        '预算表V3', '2026-01-15', '年初定稿'] as const,
    ]
    const xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
      + '<w:body><w:tbl><w:tr>'
      + hang_lie[0].map((z) => _zao_danyuan(z)).join('') + '</w:tr><w:tr>'
      + hang_lie[1].map((z) => _zao_danyuan(z)).join('')
      + '</w:tr></w:tbl></w:body></w:document>')
    const wenben = cong_docx_jiequ(_zao_docx(xml))
    const jg = daoru_csv(wenben)
    assert.equal(jg.ruku_shu, 1)                 // 合法行 1 条
    assert.equal(jg.jujue.length, 0)             // 零拒绝
    assert.equal(jg.yusuan[0].shuzhi, 22_000_000) // 22 万元 → 22000000 分
  })
})
