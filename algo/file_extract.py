# -*- coding: utf-8 -*-
"""文件文本提取层 —— 方案B 步骤 1 的【前置解包】：PDF/Word/CSV/TXT → 文本。

新增口径（用户指令 2026-08-30："工作流第一步是清洗数据，应该可以把 word
和 pdf 转换为可以处理的 csv……如果没有就加上"）：主体原本只吃 CSV/文本，
本模块补上"文件 → 文本"这一段，接在 llm_clean 智能分流【之前】——

    文件(pdf/docx/csv/txt 字节) → file_extract.jiequ_wenben → 文本行
                                → llm_clean.zhineng_fenliu → data_ingest

职责边界（只做"解包"，不做"清洗"）：
    1. 按扩展名分发格式（csv/txt 直读解码；docx 解 zip 读表格；pdf 解内容流）；
    2. 把文档还原成"一行一行"的文本（docx 表格行 → 逗号分隔行；
       PDF 的每个文本显示操作 → 一行）——格式归一化仍归 llm_clean
       （程序直解或模型翻译），本模块不猜列语义、不补字段。
    3. 【诚实边界（答辩可能被问）】只支持"文本型"文档：
       · PDF：支持文本层 PDF（文字可选中复制）；【扫描件图片 PDF 不支持】
        （需要 OCR，属 M5/AI 层未来工作）；
       · Word：支持 .docx（OpenXML）；旧版二进制 .doc 不支持（提示另存）；
       · .xlsx：按 2026-08-23 既定约定"Excel 里另存为 CSV"再导入。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    数据值用中文。零第三方依赖：zipfile/ElementTree/zlib 均为标准库。

数值纪律：本模块不做任何数值换算（文本原样透传，换算归 data_ingest）；
    纯函数（无 I/O、无全局状态——字节进、文本出）。

使用示例（知识点速览，v0.1 2026-08-30；doctest 格式——可直接复制到交互
    环境运行，也可用 `python -m doctest file_extract.py` 自动验证，并由
    tests\\test_demos.py 纳入常规测试守护，示例过时测试即红）：

    知识点 1 · CSV/TXT 直通（utf-8 优先，BOM 自动剥掉）
    >>> from file_extract import jiequ_wenben
    >>> jg = jiequ_wenben('a.csv', '\\ufeff数据类别,统计周期\\n预算基础,2026-Q1\\n'.encode('utf-8'))
    >>> (jg.geshi, jg.wenben)
    ('csv', '数据类别,统计周期\\n预算基础,2026-Q1\\n')

    知识点 2 · GBK 兜底解码（Excel 记事本旧文件常见）
    >>> jg2 = jiequ_wenben('b.txt', '预算基础,营收\\n'.encode('gbk'))
    >>> jg2.wenben
    '预算基础,营收\\n'

    知识点 3 · Word (.docx) 表格提取：一行表格 → 一行 CSV 文本
    >>> import io, zipfile
    >>> xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    ...        '<w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>数据类别</w:t></w:r></w:p></w:tc>'
    ...        '<w:tc><w:p><w:r><w:t>预算基础</w:t></w:r></w:p></w:tc></w:tr>'
    ...        '<w:tr><w:tc><w:p><w:r><w:t>统计周期</w:t></w:r></w:p></w:tc>'
    ...        '<w:tc><w:p><w:r><w:t>2026-Q1</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    >>> huanchong = io.BytesIO()
    >>> with zipfile.ZipFile(huanchong, 'w') as yasuo:
    ...     yasuo.writestr('word/document.xml', xml)
    >>> cong_docx_jiequ(huanchong.getvalue())
    '数据类别,预算基础\\n统计周期,2026-Q1\\n'

    知识点 4 · PDF 文本提取：UTF-16BE 十六进制文本串（文本型 PDF 常见形态）
    >>> liu = (b'%PDF-1.4\\n1 0 obj\\n<</Length 30>>\\nstream\\nBT\\n'
    ...        b'<FEFF98847B970032003000320036002D00510031> Tj\\nET\\nendstream\\nendobj\\n%%EOF')
    >>> cong_pdf_jiequ(liu)
    '预算2026-Q1\\n'

    知识点 5 · 不认识的类型整件拒绝（附人工建议，不静默猜格式）
    >>> from file_extract import JiequCuowu
    >>> try:
    ...     jiequ_wenben('c.docx', b'zhe bu shi zip')
    ... except JiequCuowu as cuo:
    ...     print('拒绝：', str(cuo)[:5])
    拒绝： 不是有效的

命名对照表（拼音标识符 → 中文含义）：
    jiequ_wenben        截取文本（总入口：按扩展名分发格式）
    cong_docx_jiequ     从docx截取（解 zip + document.xml → 表格行文本）
    cong_pdf_jiequ      从pdf截取（解内容流 → 文本显示操作 → 行文本）
    JiequJieguo         截取结果（wenben 文本 + geshi 格式来源）
    JiequCuowu          截取错误（坏文件/不支持类型，附人工建议）
    _zijie_zhuan_wenben 字节转文本（utf-8 → gbk → latin-1 三级兜底）
    _liu_jie            六角解（十六进制文本串解码，FEFF=BOM 优先）
    _zifuchuan_jie      字符串解（PDF 字面串：转义还原 + 编码兜底）
    qu_ming             去命名空间（XML 标签取本地名）
    gui_fan             规范化单元格（含逗号/引号的单元格加 CSV 引号）
    wenben / geshi      文本 / 格式（'csv' / 'txt' / 'docx' / 'pdf'）

口径依据：用户指令 2026-08-30（Word/PDF 转可处理文本）；docs\\06 路线 3
         （分层路由：解包是确定性程序活，翻译归 LLM）；llm_clean 既定
         约定（.xlsx 另存为 CSV；扫描件/旧版 .doc 明确不支持）。
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# ======================================================================
# 数据结构与异常区
# ======================================================================


class JiequCuowu(ValueError):
    """截取错误（坏文件 / 不支持的类型）——附中文人工建议。

    与逐行拒绝的区别（对齐 data_ingest 的两层失败观）：
    文件本身解不开 = 整文件问题，调用方拿到异常后应提示用户换格式；
    文本层的内容问题（坏行）由下游 data_ingest 逐行处理，与本模块无关。
    """

    pass  # 无附加行为，仅作类型标识（继承 ValueError 方便统一捕获）


@dataclass(frozen=True)
class JiequJieguo:
    """截取结果：还原出的文本 + 格式来源（台账追溯用）。"""

    wenben: str   # 还原出的文本（一行一条记录，\\n 分隔；末尾带换行）
    geshi: str    # 格式来源（'csv' / 'txt' / 'docx' / 'pdf'）


# ======================================================================
# 内部工具区（编码兜底 / 解码 / 规范化）
# ======================================================================


def _zijie_zhuan_wenben(zijie: bytes) -> str:
    """文件字节 → 文本：utf-8 优先 → gbk 兜底 → latin-1 最后保底。

    BOM（\\ufeff）在这里剥掉——"文件进来即干净文本"是本模块的契约；
    下游 data_ingest 的 BOM 剥除保留不动（双保险，口径不变）。
    """
    for bianma in ('utf-8', 'gbk'):
        try:
            return zijie.decode(bianma).lstrip('\ufeff')
        except UnicodeDecodeError:
            continue
    return zijie.decode('latin-1', errors='replace').lstrip('\ufeff')


def _liu_jie(liu_zijie: bytes) -> str:
    """PDF 十六进制文本串解码（<FEFF...> 形态）。

    规则：带 FEFF/FFFE BOM → 按剩余字节 utf-16-be 解；无 BOM 但字节里
    有一半是 \\x00（ASCII 文本的 utf-16 特征）→ 也按 utf-16-be 解；
    其余按 latin-1 保底（WinAnsi 旧字体）。解不开的字符用替换符，不抛。
    """
    ganjing = re.sub(rb'\s+', b'', liu_zijie)
    if not ganjing:
        return ''
    try:
        yuan = bytes.fromhex(ganjing.decode('ascii'))
    except ValueError:
        return ''
    if yuan[:2] == b'\xfe\xff':
        return yuan[2:].decode('utf-16-be', errors='replace')
    if yuan[:2] == b'\xff\xfe':
        return yuan[2:].decode('utf-16-le', errors='replace')
    if len(yuan) % 2 == 0 and b'\x00' in yuan:
        return yuan.decode('utf-16-be', errors='replace')
    return yuan.decode('latin-1', errors='replace')


def _zifuchuan_jie(zifu_zijie: bytes) -> str:
    """PDF 字面字符串解码：( ... ) 形态——先还原转义，再挑编码。

    转义表：\\( \\) \\\\ \\n \\r \\t \\b \\f 与八进制 \\ddd；未知转义丢弃。
    编码挑选与 _liu_jie 同思路（含 \\x00 特征 → utf-16-be，否则 latin-1）。
    """
    tuoyi = {b'(': b'(', b')': b')', b'\\': b'\\', b'n': b'\n', b'r': b'\r',
             b't': b'\t', b'b': b'\b', b'f': b'\f'}
    yuan = bytearray()
    i = 0
    while i < len(zifu_zijie):
        if zifu_zijie[i:i + 1] == b'\\':
            xia = zifu_zijie[i + 1:i + 2]
            if xia in tuoyi:
                yuan += tuoyi[xia]
                i += 2
                continue
            if xia.isdigit():                       # 八进制 \\ddd（最多三位）
                n = 0
                k = 0
                while k < 3 and zifu_zijie[i + 1 + k:i + 2 + k].isdigit():
                    n = n * 8 + int(zifu_zijie[i + 1 + k:i + 2 + k])
                    k += 1
                yuan.append(n)
                i += 1 + k
                continue
            i += 1                                  # 未知转义：丢弃反斜杠
            continue
        yuan.append(zifu_zijie[i])
        i += 1
    zijie = bytes(yuan)
    if len(zijie) % 2 == 0 and b'\x00' in zijie:
        return zijie.decode('utf-16-be', errors='replace')
    return zijie.decode('latin-1', errors='replace')


def qu_ming(tag: str) -> str:
    """XML 标签取本地名（'\\{命名空间\\}tbl' → 'tbl'）——对命名空间宽容。"""
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def gui_fan(cells: list[str]) -> str:
    """单元格列表 → 一行 CSV 文本：逗号拼接；含逗号/引号/换行的加引号。

    引号转义 = CSV 标准规则（内部双引号翻倍）——下游 csv.reader 能解回，
    与 data_ingest 的解析口径天然互逆。
    """
    gui_lie = []
    for dange in cells:
        if any(fu in dange for fu in (',', '"', '\n')):
            dange = '"' + dange.replace('"', '""') + '"'
        gui_lie.append(dange)
    return ','.join(gui_lie)


# ======================================================================
# docx 提取区（标准库 zipfile + ElementTree，零第三方依赖）
# ======================================================================


def _duan_wenben(danyuan) -> str:
    """一个段落/单元格容器 → 纯文本：收集全部 w:t，制表符当逗号。

    w:tab → ','：Word 里"用 Tab 分列"的段落（老报表常见）能直接变成
    可解析的 CSV 行；w:br/w:cr 忽略（单元格内换行不作分行依据）。
    """
    bujian: list[str] = []
    for yuansu in danyuan.iter():
        ming = qu_ming(yuansu.tag)
        if ming == 't':
            bujian.append(yuansu.text or '')
        elif ming == 'tab':
            bujian.append(',')
    return ''.join(bujian)


def cong_docx_jiequ(zijie: bytes) -> str:
    """Word (.docx) 字节 → 文本：顶层块顺序还原，表格行 → CSV 行。

    还原规则：body 顶层按出现顺序遍历——w:tbl 的每个 w:tr 一行（单元格
    逗号分隔、必要时加引号）；w:p 一行（段落文本）。空行保留（下游
    data_ingest 本就跳过全空行）。
    """
    try:
        yasuo = zipfile.ZipFile(io.BytesIO(zijie))
        xml_zijie = yasuo.read('word/document.xml')
    except (zipfile.BadZipFile, KeyError) as cuo:
        raise JiequCuowu(
            f'不是有效的 .docx（{cuo}）；旧版 .doc 请先另存为 .docx 再导入') from cuo
    try:
        gen = ET.fromstring(xml_zijie)
    except ET.ParseError as cuo:
        raise JiequCuowu(f'document.xml 解析失败（{cuo}）——文件可能已损坏') from cuo
    body = next((e for e in gen.iter() if qu_ming(e.tag) == 'body'), None)
    if body is None:
        raise JiequCuowu('document.xml 缺少 body——不是 Word 正文文档')
    hang_lie: list[str] = []
    for kuai in body:                               # 只走顶层，嵌套表随外层单元格走
        ming = qu_ming(kuai.tag)
        if ming == 'tbl':
            for hang in kuai:                       # 直接子元素 = w:tr
                if qu_ming(hang.tag) != 'tr':
                    continue
                danyuan_lie = [ _duan_wenben(dan) for dan in hang
                               if qu_ming(dan.tag) == 'tc' ]
                hang_lie.append(gui_fan(danyuan_lie))
        elif ming == 'p':
            hang_lie.append(_duan_wenben(kuai))
    return '\n'.join(hang_lie) + '\n'


# ======================================================================
# pdf 提取区（zlib 解流 + 文本显示操作扫描）
# ======================================================================

#: 内容流定位：stream ... endstream 之间全部视为候选内容（不解析 xref，
#: 不依赖 /Length——宽容换取对"生成器各异的 PDF"的兼容面）
_LIU_ZE = re.compile(rb'stream[\r\n]+(.*?)endstream', re.DOTALL)

#: 内容流词法：六角串 / 字面串 / 数字 / 运算符（四类记号按出现顺序扫）
#: ——定位跟踪需要"数字+运算符"的原始顺序，故用一个总正则顺序消费
_CIXU_ZE = re.compile(
    rb'<([0-9A-Fa-f\s]*)>'
    rb'|\(((?:[^()\\]|\\.)*)\)'
    rb'|([-+]?\d*\.?\d+)'
    rb"|([A-Za-z'\"*]+)")

#: 行分组的 y 容差（pt）：同一视觉行的片段 y 理论相同，
#: 浮点累积可能有 ±0.05 级漂移，容差内视为同行
_HANG_RONGCHA = 0.05


def _liuxing_zhui_zong(neibu: bytes) -> list[tuple[float, str]]:
    """一个内容流 → (y 坐标, 文本) 片段序列——带定位跟踪的词法扫描。

    为什么需要跟踪 y：真实 PDF 的一行文字经常被拆成多个显示片段
    （逐格排版的表格、字体切换、字距调整都会拆）——只按"一个显示
    操作一行"还原会把一行撕成碎片。这里按出现顺序消费词法记号，
    跟踪文本纵坐标（Tm 绝对 / Td 相对 / TD·T*·TL 行距体系），
    把每个显示操作记在它自己的 y 上；同 y 的片段由调用方拼回一行。

    操作数语义（关键，防串味）：数字先进【操作数栈】，每个算子只取
    自己需要的操作数、用完即清栈——字号（Tf 的 9）、字距（TJ 的调整
    值）绝不会污染下一条定位算子的 y。支持算子：Tm/Td/TD/T*/TL/'/";
    TJ 数组内的字符串顺序保留、调整数字丢弃。BT/ET 不重置 y（绝对
    定位的排版器跨块共用坐标系；相对定位的排版器自会用 Td 归位）。
    """
    pian: list[tuple[float, str]] = []
    y = 0.0
    xingju = 0.0                       # TL 行距（T* 每次上移一行）
    dengdai: list[str] = []            # 待显示的字符串（TJ 数组会攒多个）
    shu_zhan: list[float] = []         # 操作数栈（数字进、算子取、取完清）
    for pipei in _CIXU_ZE.finditer(neibu):
        liu_zi, zifu_zi, shu_zi, yunsuan = pipei.groups()
        if liu_zi is not None:
            dengdai.append(_liu_jie(liu_zi))
        elif zifu_zi is not None:
            dengdai.append(_zifuchuan_jie(zifu_zi))
        elif shu_zi is not None:
            shu_zhan.append(float(shu_zi))   # 数字只进栈——清栈是算子的职责
        else:                                # 运算符记号：消费操作数后清栈
            if yunsuan == b'Tm':             # 文本矩阵：六个操作数，末个 = 绝对 y
                if shu_zhan:
                    y = shu_zhan[-1]
            elif yunsuan == b'Td':           # 相对移动：y += ty（操作数栈顶）
                if shu_zhan:
                    y += shu_zhan[-1]
            elif yunsuan == b'TD':           # 设行距并移动：tl = -ty；y += ty
                if shu_zhan:
                    xingju = -shu_zhan[-1]
                    y += shu_zhan[-1]
            elif yunsuan == b'TL':           # 设行距
                if shu_zhan:
                    xingju = shu_zhan[-1]
            elif yunsuan in (b'T*', b"'", b'"'):
                y -= xingju                  # 上移一行；'/" 顺带显示（字符串已在待显区）
                if yunsuan != b'T*' and dengdai:
                    pian.append((y, ''.join(dengdai)))
                    dengdai.clear()
            elif yunsuan in (b'Tj', b'TJ'):
                if dengdai:
                    pian.append((y, ''.join(dengdai)))
                    dengdai.clear()
            shu_zhan.clear()                 # 算子消费完毕清栈（数字不清——栈是它家）
    if dengdai:                        # 流尾悬挂的字符串（病态流，容错收编）
        pian.append((y, ''.join(dengdai)))
    return pian


def cong_pdf_jiequ(zijie: bytes) -> str:
    """PDF 字节 → 文本：逐流解压 → 定位跟踪扫描 → 同行片段拼回一行。

    诚实边界：只处理"文本型 PDF"。解不出任何内容流（典型如扫描件
    图片 PDF）时抛 JiequCuowu 并说明原因——绝不输出空文本假装成功。
    行还原规则：同一视觉行（y 相同，容差 _HANG_RONGCHA）的多个显示
    片段按出现顺序拼成一行——这既兼容"一行拆多片"的真实 PDF
    （逐格排版的表格/字体切换都会拆），也让逐格排版的表格文档
    解包后恰好还原出逗号分隔行。
    """
    liu_lie: list[bytes] = []
    for pipei in _LIU_ZE.finditer(zijie):
        neibu = pipei.group(1).rstrip(b'\r\n')
        try:
            neibu = zlib.decompress(neibu)          # FlateDecode 流
        except zlib.error:
            pass                                    # 未压缩流原样使用
        liu_lie.append(neibu)
    if not liu_lie:
        raise JiequCuowu('PDF 中没有内容流——可能是扫描件图片 PDF（不支持，'
                         '需要 OCR）；请改用文本型 PDF 或另存为 CSV/Word')
    hang_lie: list[str] = []
    for neibu in liu_lie:
        pian = _liuxing_zhui_zong(neibu)
        if not pian:
            continue
        # 同 y 分组拼行（顺序保持；y 差在容差内视为同一行）
        dang_qian_y, dang_qian_wen = pian[0]
        for y, wen in pian[1:]:
            if abs(y - dang_qian_y) <= _HANG_RONGCHA:
                dang_qian_wen += wen                # 同一行：顺序拼接
            else:
                hang_lie.append(dang_qian_wen)
                dang_qian_y, dang_qian_wen = y, wen
        hang_lie.append(dang_qian_wen)
    hang_lie = [hang for hang in hang_lie if hang.strip()]
    return '\n'.join(hang_lie) + '\n'


# ======================================================================
# 对外入口区（按扩展名分发）
# ======================================================================


def jiequ_wenben(ming: str, zijie: bytes) -> JiequJieguo:
    """文件（名字 + 字节）→ 截取结果：按扩展名分发到对应解包器。

    分发表：csv/txt 直读解码；docx/pdf 走专用解包器；doc/xls/xlsx 给
    "另存为"建议（诚实拒绝，不静默硬解）；其余类型整件拒绝。
    """
    houzhui = ming.lower().rsplit('.', 1)[-1] if '.' in ming else ''
    if houzhui in ('csv', 'txt'):
        return JiequJieguo(_zijie_zhuan_wenben(zijie), houzhui)
    if houzhui == 'docx':
        return JiequJieguo(cong_docx_jiequ(zijie), 'docx')
    if houzhui == 'pdf':
        return JiequJieguo(cong_pdf_jiequ(zijie), 'pdf')
    if houzhui == 'doc':
        raise JiequCuowu('旧版 .doc 暂不支持：请用 Word/WPS 另存为 .docx 再导入')
    if houzhui in ('xls', 'xlsx'):
        raise JiequCuowu('Excel 文件按既定约定请先"另存为 CSV"再导入'
                         '（与 llm_clean 2026-08-23 口径一致）')
    raise JiequCuowu(f'不认识的文件类型：{ming!r}（支持 csv/txt/docx/pdf）')
