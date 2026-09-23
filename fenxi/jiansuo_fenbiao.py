# -*- coding: utf-8 -*-
"""检索结果分表演示入口 —— 编排：调检索内核（kb/env）→ Word 两张表 → PDF。

运行环境：**系统 Python**（需要 python-docx 出 Word，并经 COM 转 PDF）。
分工：检索（含 kb2 向量依赖）在 jiansuo_neihe.py 内核完成（kb/env），
本脚本只消费它落盘的 检索结果-分类.json 做排版——两个运行时各司其职。

产出（shuchu\流水线结果\）：
    检索结果-分类.json   检索内核落盘（kb2 原样输出，全文）
    检索结果-分类.docx   两张表（收入类 / 成本类，真 Word 表格）
    检索结果-分类.pdf    Word 转换件（观感一致）

零模型声明：三份产物里没有任何 LLM 内容——全部是 kb2 三路混合检索
（条款直达 ∥ 关键词 FTS5 ∥ bge 向量 + RRF）的原样输出。
用法：D:/dev-env/Python312/python.exe jiansuo_fenbiao.py
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BEN_MU = Path(__file__).resolve().parent
JIEGUO = BEN_MU.parent / 'testgen' / 'shuchu' / '流水线结果'
KB_PY = r'D:\AppProject\kb\env\Scripts\python.exe'      # kb2 检索的专用运行时

#: 表格列宽（缇，总 10200 = A4 版心）：来源提示词/条文定位/命中路/RRF分/条文摘录
LIE_KUAN = (2400, 1300, 1300, 900, 4300)

#: 条文摘录长度（PDF/Word 表格里的原文截断——全文看 JSON）
ZHAILU_CHANGDU = 60


def _zhuan_yi(wen: str) -> str:
    """XML 转义（& < >）——条文原文里的符号不能破坏 document.xml。"""
    return wen.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _biaoge_xml(hang_lie: list[list[str]]) -> str:
    """一张表：表头底纹加粗 + 数据行（列宽按 LIE_KUAN 预算）。"""
    danyuan_lie = []
    for i, hang in enumerate(hang_lie):
        didao = ('<w:shd w:val="clear" w:fill="D9E2F3"/>' if i == 0 else '')
        jia = '<w:b/><w:bCs/>' if i == 0 else ''
        ge_lie = []
        for j, ziduan in enumerate(hang):
            duiqi = 'center' if i == 0 else ('left' if j in (0, 4) else 'center')
            ge_lie.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{LIE_KUAN[j]}" w:type="dxa"/>{didao}'
                f'<w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr><w:jc w:val="{duiqi}"/></w:pPr>'
                f'<w:r><w:rPr>{jia}<w:sz w:val="18"/><w:szCs w:val="18"/></w:rPr>'
                f'<w:t xml:space="preserve">{_zhuan_yi(ziduan)}</w:t></w:r></w:p></w:tc>')
        danyuan_lie.append('<w:tr>' + ''.join(ge_lie) + '</w:tr>')
    wangge = '<w:tblGrid>' + ''.join(f'<w:gridCol w:w="{k}"/>' for k in LIE_KUAN) + '</w:tblGrid>'
    biankuang = '<w:tblBorders>' + ''.join(
        f'<w:{bian} w:val="single" w:sz="4" w:space="0"/>'
        for bian in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>'
    return ('<w:tbl><w:tblPr><w:tblW w:w="10200" w:type="dxa"/>'
            '<w:tblLayout w:type="fixed"/>' + biankuang + '</w:tblPr>'
            + wangge + ''.join(danyuan_lie) + '</w:tbl>')


def _duanluo_xml(wen: str, jiacu: bool = False, daxiao: int = 24) -> str:
    """段落 XML：黑体标题 / 宋体正文，居中由调用方定。"""
    jia = '<w:b/><w:bCs/>' if jiacu else ''
    ziti = '黑体' if jiacu else '宋体'
    return (f'<w:p><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
            f'<w:r><w:rPr>{jia}<w:rFonts w:eastAsia="{ziti}"/>'
            f'<w:sz w:val="{daxiao}"/><w:szCs w:val="{daxiao}"/></w:rPr>'
            f'<w:t xml:space="preserve">{_zhuan_yi(wen)}</w:t></w:r></w:p>')


def xie_docx(shuchu: dict, lujing: Path) -> None:
    """两表 → Word：标题 + 表一（收入类）+ 表二（成本类）。"""
    kuai = [_duanluo_xml('kb2 检索结果 · 收入类 / 成本类分表（向量库直出，零模型）',
                         jiacu=True, daxiao=28)]
    biaotou = ['来源提示词', '条文定位', '命中路', 'RRF 分', '条文摘录']
    for leibie in ('收入类', '成本类'):
        kuai.append(_duanluo_xml(f'表{"一" if leibie == "收入类" else "二"} · {leibie}',
                                 jiacu=True, daxiao=24))
        hang_lie = [biaotou]
        for zu in shuchu.get(leibie, []):
            if not zu['tiaowen']:                   # 该提示词检索无命中也如实成行
                hang_lie.append([zu['laiyuan'], '—', '—', '—', '（无命中）'])
                continue
            for t in zu['tiaowen']:
                zhai = t['neirong'][:ZHAILU_CHANGDU] + ('…' if len(t['neirong']) > ZHAILU_CHANGDU else '')
                hang_lie.append([zu['laiyuan'], t['dingwei'], t['laiyuan_lu'],
                                 f"{t['zongfen']:.4f}", zhai])
        kuai.append(_biaoge_xml(hang_lie))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(kuai)
        + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/></w:sectPr>'
        '</w:body></w:document>')
    leixing = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
               '<Default Extension="xml" ContentType="application/xml"/>'
               '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
               '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')
    import zipfile
    with zipfile.ZipFile(lujing, 'w', zipfile.ZIP_DEFLATED) as yasuo:
        yasuo.writestr('[Content_Types].xml', leixing)
        yasuo.writestr('_rels/.rels', rels)
        yasuo.writestr('word/document.xml', document)


def zhuan_pdf(docx_lu: Path, pdf_lu: Path) -> bool:
    """Word → PDF（COM：Word 优先、WPS 兜底——与 zhuan_pdf 同一手法）。"""
    for chengxu in ('Word.Application', 'KWPS.Application'):
        jiaoben = (
            "try {\n"
            f"  $app = New-Object -ComObject {chengxu}\n"
            "  $app.Visible = $false\n"
            f"  $doc = $app.Documents.Open('{docx_lu}')\n"
            f"  $doc.SaveAs([ref]'{pdf_lu}', [ref]17)\n"
            "  $doc.Close($false)\n"
            "  $app.Quit()\n"
            "  exit 0\n"
            "} catch { exit 1 }")
        try:
            subprocess.run(['powershell', '-NoProfile', '-Command', jiaoben],
                           capture_output=True, timeout=120, check=False)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if pdf_lu.exists() and pdf_lu.stat().st_size > 1000:
            return True
        if pdf_lu.exists():
            pdf_lu.unlink()
    return False


def zhukong() -> int:
    """入口：跑检索内核（kb/env 子进程）→ 读 JSON → Word 两表 → PDF。"""
    sys.stdout.reconfigure(encoding='utf-8')
    # ---- 第一步：检索内核（kb/env 子进程——kb2 向量依赖在那边）----
    neijian = BEN_MU / 'jiansuo_neihe.py'
    wan = subprocess.run([KB_PY, str(neijian)], capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=300)
    print(wan.stdout.strip())
    if wan.returncode != 0:
        print(f'检索内核失败（exit {wan.returncode}）：{wan.stderr[-300:]}')
        return 1

    # ---- 第二步：读 JSON → Word 两表 → PDF ----
    shuchu = json.loads((JIEGUO / '检索结果-分类.json').read_text(encoding='utf-8'))
    docx_lu = JIEGUO / '检索结果-分类.docx'
    xie_docx(shuchu, docx_lu)
    print(f'落盘：{docx_lu}（两张真 Word 表格）')
    pdf_lu = JIEGUO / '检索结果-分类.pdf'
    if zhuan_pdf(docx_lu, pdf_lu):
        print(f'落盘：{pdf_lu}（Word 转换件）')
    else:
        print('PDF：未生成（本机需装有 Word/WPS 供 COM 转换）')
    return 0


if __name__ == '__main__':
    sys.exit(zhukong())
