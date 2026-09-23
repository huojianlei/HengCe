# -*- coding: utf-8 -*-
"""file_extract 文件文本提取层的测试（14 用例，全部离线、期望值手算写死）。

口径依据：algo/file_extract.py 模块头（用户指令 2026-08-30 新增口径：
步骤 1 前置解包，PDF/Word/CSV/TXT → 文本，供 llm_clean 智能分流消费）。

用例目录（四大组，对应模块的四个公开行为）：
    TestFenfa    ×5  按扩展名分发：csv/txt 直读三级解码、坏类型/旧版
                     .doc/.xlsx 的诚实拒绝
    TestDocx     ×5  表格还原、段落混排、引号转义、制表符转逗号、坏 zip
    TestPdf      ×5  六角串(BOM)、字面串转义、TJ 数组、多流(Flate+裸流)、
                     无内容流(扫描件)拒绝
    TestJicheng  ×1  与 data_ingest 接缝：提取文本直接入库零拒绝

夹具策略：全部夹具在测试内【手工构造】（zipfile 拼 docx、bytes 拼 PDF
内容流）——不依赖 testgen（依赖方向纪律：主体永不引用 testgen）；
期望值全部手工推演写死，禁止现算自证。
十六进制夹具速查（UTF-16BE，含 FEFF BOM）：测=6D4B 试=8BD5 实=5B9E。
"""

from __future__ import annotations

import io
import unittest
import zipfile
import zlib

from data_ingest import daoru_csv          # 集成断言用：提取文本应能直接入库
from file_extract import (JiequCuowu, JiequJieguo, cong_docx_jiequ,
                          cong_pdf_jiequ, jiequ_wenben)

#: 最小 docx 的 document.xml 样板（表格两行 × 两列，首行当表头）——
#: 解包器只认 w:body/w:tbl/w:tr/w:tc/w:t 结构，不要求 tblPr 等装饰节点
DOC_XML = (
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:body><w:tbl><w:tr>'
    '<w:tc><w:p><w:r><w:t>数据类别</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>统计周期</w:t></w:r></w:p></w:tc>'
    '</w:tr><w:tr>'
    '<w:tc><w:p><w:r><w:t>预算基础</w:t></w:r></w:p></w:tc>'
    '<w:tc><w:p><w:r><w:t>2026-Q1</w:t></w:r></w:p></w:tc>'
    '</w:tr></w:tbl></w:body></w:document>'
)

#: 八列规范表头（TestJicheng 用）——与 data_ingest.BIXU_LIE 逐字一致
BIAOTOU_8LIE = ('数据类别', '统计周期', '数据科目', '数值', '单位',
                '数据来源', '更新时间', '备注')


def _zao_docx(xml_wen: str) -> bytes:
    """手工拼一个最小 docx 字节（只有 document.xml 一个成员——解包器宽容）。"""
    huanchong = io.BytesIO()
    with zipfile.ZipFile(huanchong, 'w') as yasuo:
        yasuo.writestr('word/document.xml', xml_wen)
    return huanchong.getvalue()


def _zao_danyuan(wen: str) -> str:
    """拼一个单元格 XML 片段：<w:tc><w:p><w:r><w:t>文本</w:t>……"""
    return f'<w:tc><w:p><w:r><w:t>{wen}</w:t></w:r></w:p></w:tc>'


class TestFenfa(unittest.TestCase):
    """jiequ_wenben 按扩展名分发：csv/txt 直读、坏类型/不支持类型拒绝。"""

    def test_csv_bom_boduan(self) -> None:
        """CSV + UTF-8 BOM：BOM 剥掉、内容原样（utf-8 优先解码）。

        输入字节 = EF BB BF + utf-8 编码正文；期望值手抄自 data_ingest
        演示方言首行（BOM 由本模块剥，正文逐字保留）。
        """
        zijie = '\ufeff数据类别,统计周期\n预算基础,2026-Q1\n'.encode('utf-8')
        jg = jiequ_wenben('a.csv', zijie)
        self.assertIsInstance(jg, JiequJieguo)          # 返回结构而非裸字符串
        self.assertEqual(jg.geshi, 'csv')               # 格式来源留台账
        self.assertEqual(jg.wenben, '数据类别,统计周期\n预算基础,2026-Q1\n')

    def test_txt_gbk_doudi(self) -> None:
        """TXT + GBK 字节：utf-8 解不开自动落到 gbk（Excel/记事本旧文件常见）。"""
        jg = jiequ_wenben('b.txt', '预算基础,营收\n'.encode('gbk'))
        self.assertEqual(jg.geshi, 'txt')
        self.assertEqual(jg.wenben, '预算基础,营收\n')

    def test_buming_leixing_jujue(self) -> None:
        """不认识的扩展名整件拒绝，信息里列出支持类型（人工可自助）。

        断言点：异常类型 + 报错信息含支持清单——拒绝要"拒绝得明白"，
        不能只抛一句空泛的"格式错误"。
        """
        with self.assertRaises(JiequCuowu) as duizhao:
            jiequ_wenben('c.zip7', b'whatever')
        self.assertIn('csv/txt/docx/pdf', str(duizhao.exception))

    def test_doc_lingcun_jianyi(self) -> None:
        """旧版 .doc：诚实拒绝并给出"另存为 .docx"建议（不硬解二进制）。

        .doc 是 OLE 复合文档（非 zip），硬解成本高收益低——按诚实边界
        拒绝并给自助路径，比悄悄输出乱码文本更负责。
        """
        with self.assertRaises(JiequCuowu) as duizhao:
            jiequ_wenben('lao.doc', b'whatever')
        self.assertIn('另存为 .docx', str(duizhao.exception))

    def test_xlsx_jianding_koujing(self) -> None:
        """.xlsx：按 2026-08-23 既定约定拒绝（另存为 CSV），口径不漂移。

        这条守住的是"约定一致性"：llm_clean 早已把"Excel 另存为 CSV"
        写进提示词约定，本模块新增后不得悄悄扩大口径。
        """
        with self.assertRaises(JiequCuowu) as duizhao:
            jiequ_wenben('biao.xlsx', b'whatever')
        self.assertIn('另存为 CSV', str(duizhao.exception))


class TestDocx(unittest.TestCase):
    """cong_docx_jiequ：表格还原 / 段落混排 / 引号转义 / 制表符 / 坏文件。

    五条用例对应还原规则的五个决定性细节：顺序、混排、转义、Tab、容错。
    """

    def test_biaoge_huanyuan(self) -> None:
        """两行两列表格 → 两行逗号文本（出现顺序保持，无多余空白）。

        期望值手抄 DOC_XML 的内容顺序——"顺序保持"是台账可信的前提。
        """
        self.assertEqual(cong_docx_jiequ(_zao_docx(DOC_XML)),
                         '数据类别,统计周期\n预算基础,2026-Q1\n')

    def test_duanyu_biaoge_hunpai(self) -> None:
        """段落与表格混排：按出现顺序还原，段落一行为一行。

        夹具顺序 = 段落、表格(1行)、段落——验证遍历不重排、不丢段。
        """
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>老板发来的Q1快报：</w:t></w:r></w:p>'
               '<w:tbl><w:tr>' + _zao_danyuan('营收') + _zao_danyuan('210000.00')
               + '</w:tr></w:tbl>'
               '<w:p><w:r><w:t>单位都是元。</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(cong_docx_jiequ(_zao_docx(xml)),
                         '老板发来的Q1快报：\n营收,210000.00\n单位都是元。\n')

    def test_danyuan_douhao_yinhao(self) -> None:
        """单元格含逗号 → CSV 引号包裹（csv.reader 可解回，口径互逆）。

        期望值手写：'"备注,带逗号",普通'——引号包裹是 CSV 标准转义，
        data_ingest 底层用 csv.reader 解析，能原样解回单元格。
        """
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:tbl><w:tr>' + _zao_danyuan('备注,带逗号')
               + _zao_danyuan('普通') + '</w:tr></w:tbl></w:body></w:document>')
        self.assertEqual(cong_docx_jiequ(_zao_docx(xml)),
                         '"备注,带逗号",普通\n')

    def test_tab_dang_douhao(self) -> None:
        """段落里的制表符当逗号（"Tab 分列"的老报表直接变可解析行）。"""
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:r><w:t>营收</w:t></w:r><w:tab/>'
               '<w:r><w:t>210000.00</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(cong_docx_jiequ(_zao_docx(xml)), '营收,210000.00\n')

    def test_huai_zip_jujue(self) -> None:
        """坏 zip / 缺 document.xml：整件拒绝 + 人工建议（两层都断）。"""
        with self.assertRaises(JiequCuowu):                     # 不是 zip
            cong_docx_jiequ(b'zhe bu shi zip')
        kong = io.BytesIO()                                     # 是 zip 但缺正文
        with zipfile.ZipFile(kong, 'w') as yasuo:
            yasuo.writestr('qita.txt', 'x')
        with self.assertRaises(JiequCuowu):
            cong_docx_jiequ(kong.getvalue())


class TestPdf(unittest.TestCase):
    """cong_pdf_jiequ：六角串 / 字面串 / TJ 数组 / 多流 / 无内容流。"""

    def test_liuchuan_liujinjie(self) -> None:
        """十六进制文本串（带 FEFF BOM）：UTF-16BE 解码成中文+ASCII。

        夹具换算：预=9884 算=7B97；'2026-Q1' 的 UTF-16BE 每字符前补 00。
        /Length 故意写错——提取器不解析 xref/Length（宽容设计）仍须解出。
        """
        liu = (b'%PDF-1.4\n1 0 obj\n<</Length 30>>\nstream\nBT\n'
               b'<FEFF98847B970032003000320036002D00510031> Tj\nET\n'
               b'endstream\nendobj\n%%EOF')
        self.assertEqual(cong_pdf_jiequ(liu), '预算2026-Q1\n')

    def test_tonghang_fensui_pinjie(self) -> None:
        """同一视觉行（y 相同）的多个片段拼回一行——逐格排版的表格能还原。

        场景：'营收' '，' '100000.00' 三段各在固定列位（Tm 定位、同 y），
        解包后应拼回 '营收,100000.00'——真实 PDF 的一行常被排版器拆成
        多个片段，这是 v4 新增的定位跟踪能力的核心回归。
        手算：营=8425 收=6536；逗号与数字走字面串（latin-1）。
        """
        liu = (b'stream\nBT\n'
               b'1 0 0 1 40 700 Tm <FEFF84256536> Tj\n'
               b'1 0 0 1 120 700 Tm (,) Tj\n'
               b'1 0 0 1 160 700 Tm (100000.00) Tj\n'
               b'ET\nendstream')
        self.assertEqual(cong_pdf_jiequ(liu), '营收,100000.00\n')

    def test_Td_TX_huanhang(self) -> None:
        """Td + T* + TL 行距体系：每个 T* 换一行（v2 平表 PDF 的排法）。

        手算：Td 后 y=800；TL=12 → 每个 T* 上移 12 → 两行 y=800/788，
        两行不同行 → 各自成行。这是向后兼容的回归用例。
        """
        liu = (b'stream\nBT\n/F1 9 Tf\n12 TL\n40 800 Td\n'
               b'(a) Tj\nT*\n(b) Tj\nET\nendstream')
        self.assertEqual(cong_pdf_jiequ(liu), 'a\nb\n')

    def test_zimian_zhuanyi(self) -> None:
        """字面串：转义 \\( \\) 还原成括号本身；ASCII 按 latin-1 落地。"""
        liu = b'stream\n(a \\(b\\) c) Tj\nendstream'
        self.assertEqual(cong_pdf_jiequ(liu), 'a (b) c\n')

    def test_shuzu_TJ_pinjie(self) -> None:
        """TJ 数组：内部多个六角记号按顺序拼接成一行（实=5B9E 测=6D4B 点=70B9）。

        数组里的 2/4 是字距数字——提取器只取字符串记号，数字自动丢弃。
        """
        liu = b'stream\n[(<FEFF5B9E> 2 <FEFF6D4B> 4 <FEFF70B9>] TJ\nendstream'
        self.assertEqual(cong_pdf_jiequ(liu), '实测点\n')

    def test_duoliu_shunxu(self) -> None:
        """多个内容流（FlateDecode + 未压缩混合）：按流顺序拼接行。

        流 1 = zlib 压缩的 <FEFF6D4B8BD5>（测=6D4B 试=8BD5）——须先解压
        再扫描；流 2 = 未压缩字面串 (csv)。期望顺序 = 解压流在前。
        """
        ya_suo = zlib.compress(b'BT\n<FEFF6D4B8BD5> Tj\nET\n')
        liu = (b'stream\n' + ya_suo + b'\nendstream\n'
               b'stream\nBT\n(csv) Tj\nET\nendstream')
        self.assertEqual(cong_pdf_jiequ(liu), '测试\ncsv\n')

    def test_wu_liuchu_saomiaojian(self) -> None:
        """解不出任何内容流（扫描件图片 PDF 的典型形态）：诚实拒绝不装成功。"""
        with self.assertRaises(JiequCuowu) as duizhao:
            cong_pdf_jiequ(b'%PDF-1.4\n%%EOF')
        self.assertIn('扫描件', str(duizhao.exception))


class TestJicheng(unittest.TestCase):
    """与 data_ingest 的接缝：提取出的文本应能直接入库（零拒绝）。"""

    def test_docx_wenben_neng_ruku(self) -> None:
        """docx 八列表格 → 文本 → daoru_csv：一行合法数据应全部入库。

        期望值手算：220000.00 元 → 22000000 分（录入侧 ×100 换算）；
        归档类别 = 预算基础（yusuan 清单恰好 1 条）。
        """
        hang_lie = [BIAOTOU_8LIE,
                    ('预算基础', '2026-Q1', '营收', '220000.00', '元',
                     '预算表V3', '2026-01-15', '年初定稿')]
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:tbl><w:tr>'
               + ''.join(_zao_danyuan(z) for z in hang_lie[0]) + '</w:tr><w:tr>'
               + ''.join(_zao_danyuan(z) for z in hang_lie[1])
               + '</w:tr></w:tbl></w:body></w:document>')
        wenben = cong_docx_jiequ(_zao_docx(xml))
        jg = daoru_csv(wenben)
        self.assertEqual(jg.ruku_shu, 1)                    # 合法行 1 条
        self.assertEqual(len(jg.jujue), 0)                  # 零拒绝
        self.assertEqual(jg.yusuan[0].shuzhi, 22_000_000)   # 22 万元 → 22000000 分


if __name__ == '__main__':
    unittest.main()
