# -*- coding: utf-8 -*-
r"""分类结果演示 —— 测试文件全链跑一次：计算结果 + kb2 检索，收入/成本两张表。

运行环境：**系统 Python**（解析/计算用 algo 标准库模块；Word/PDF 用
python-docx + COM；检索内核经子进程跑在 kb\env——那里才有向量依赖）。

链路（用户指令 2026-08-30："根据测试文件跑一次，带上计算程序的计算结果，
收入类和成本类拆成两个表格，输出 JSON 和 PDF，不上真模型"）：
    ① 预算报告-季度.docx → 解包 → 模板解析 → 清洗入库（真测试文件）
    ② 差异计算逐科目（收入类 / 成本类拆开）
    ③ 拆分（Holmes 口径）→ 单双环判定 → 积木 → BSC（计算结果的一部分）
    ④ 全量提示词（shangxian 放开）→ 子进程调 kb\env 检索内核 → kb2 原样片段
    ⑤ 计算结果与检索条文按类合并 → 检索结果-分类.json（全文，无省略）
    ⑥ 两张大表（收入类 / 成本类，计算列 + 条文列，跨行合并）→ Word → PDF

产物（shuchu\流水线结果\）：检索结果-分类.json / .docx / .pdf
零模型声明：检索与全部产物不含任何 LLM 内容。
用法：D:/dev-env/Python312/python.exe fenbiao_yanshi.py
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BEN_MU = Path(__file__).resolve().parent
SHUCHU = BEN_MU.parent / 'testgen' / 'shuchu'
JIEGUO = SHUCHU / '流水线结果'
KB_PY = r'D:\AppProject\kb\env\Scripts\python.exe'

sys.path.insert(0, str(BEN_MU.parent / 'algo'))     # algo 计算模块（stdlib 纯函数）
sys.path.insert(0, str(BEN_MU))                     # 本目录（retrieval 常量等）

from analysis_generator import json_dumps           # noqa: E402
from bsc import BscShuru, jisuan_bsc                # noqa: E402
from building_blocks import chai_jimu, cong_chayi_xiang  # noqa: E402
from data_ingest import daoru_csv                   # noqa: E402
from file_extract import jiequ_wenben               # noqa: E402
from loop_decision import PanDuanShuru, panduan_huanlu  # noqa: E402
from planning_operational import ChaifenShuru, chai_fen  # noqa: E402
from report_parse import shitu_jiexi                # noqa: E402
from rolling_budget import GunDongShezhi, QijianJine, gengxin_gundong_yusuan  # noqa: E402
from variance import ChayiShuru, jisuan_chayi       # noqa: E402
from xishu import shengcheng_tishi                  # noqa: E402

SHOURU_KEMU = ('营收', '服务收入', '其他收入')       # 收入类科目（表一）
KB_LIE = ('科目 / 来源', '预算(元)', '实际(元)', '差额(元)', '差异率',
          'F/A', '预警', '条文定位', '命中路', 'RRF 分', '条文原文（全文）')
KB_KUAN = (1900, 1250, 1250, 1250, 900, 650, 650, 1450, 1100, 850, 3888)


def _yuan(fen: int) -> str:
    """整数分 → '元'千分位两位小数字符串（仅显示层转换，计算层不动）。"""
    return f'{fen / 100:,.2f}'


def zhukong() -> int:
    """入口：全链跑一次 → 合并两表数据 → JSON → Word → PDF。"""
    sys.stdout.reconfigure(encoding='utf-8')

    # ---- ① 真测试文件：解析 → 入库 ----
    wenjian = SHUCHU / '预算报告-季度.docx'
    jg = jiequ_wenben(wenjian.name, wenjian.read_bytes())
    jiexi = shitu_jiexi(jg.wenben)
    if not jiexi.shibie:
        print('报告解析未命中，中止')
        return 1
    ruku = daoru_csv(jiexi.wenben_8lie)
    print(f'[1] 录入：{wenjian.name} → 入库 {ruku.ruku_shu} 行（拒绝 {len(ruku.jujue)}）')

    # ---- ② 逐科目差异计算（基准=固定预算；方向按科目性质）----
    yusuan: dict[str, dict[str, int]] = {}
    shiji: dict[str, dict[str, int]] = {}
    for t in ruku.yusuan:
        if t.danwei == '元':
            yusuan.setdefault(t.kemu, {})[t.qijian] = t.shuzhi
    for t in ruku.shishi:
        if t.danwei == '元':
            shiji.setdefault(t.kemu, {})[t.qijian] = t.shuzhi
    qi_shi = sorted({q for hang in shiji.values() for q in hang})
    shuru_lie = []
    for kemu, hang in shiji.items():
        if kemu not in yusuan:
            continue
        for q in qi_shi:
            if q in yusuan[kemu]:
                fangxiang = '收入类' if kemu in SHOURU_KEMU else '成本类'
                shuru_lie.append(ChayiShuru(q, kemu, fangxiang,
                                            chushi_fen=yusuan[kemu][q],
                                            gundong_fen=None, shiji_fen=hang[q]))
    chayi = jisuan_chayi(shuru_lie)
    hong = [x for x in chayi.xiang if x.yujing == '红']
    print(f'[2] 差异：{len(shuru_lie)} 行（红 {chayi.hong_shu} / 黄 {chayi.huang_shu}）')

    # ---- ③ 拆分 + 判定 + 积木 + BSC（口径与 run_pipeline 一致）----
    chaifen = chai_fen(ChaifenShuru(biaozhun_danjia_fen=400, biaozhun_yongliang=7,
                                    xiuding_danjia_fen=380, xiuding_yongliang=8,
                                    shiji_chanliang=1400, shiji_yongliang=11000,
                                    shiji_chengben_fen=4_150_000))
    panduan = panduan_huanlu(PanDuanShuru(
        chalv_bps=hong[0].chalv_bps if hong else None,
        guihua_zong_fen=chaifen.guihua_zong_fen, zhixing_zong_fen=chaifen.zhixing_zong_fen,
        yuandan_cbf_fen=3_920_000,
        jie_gou_biangeng=any(t.kemu == '供应商涨价' for t in ruku.biangeng),
        bianma='供应商涨价，已登记'))
    jimu = chai_jimu([cong_chayi_xiang(x) for x in chayi.xiang])
    yjs = next(x for x in chayi.xiang if x.kemu == '营收')
    caijing = (yjs.shiji_fen * 10000 + yjs.chushi_fen // 2) // yjs.chushi_fen
    bsc = jisuan_bsc(BscShuru(caijing, 8000, 7000, 6000))
    print(f'[3] 判定 {panduan.panduan}｜积木核心 {jimu.hexin_mokuai}｜BSC {bsc.zongfen} {bsc.dengji}')

    # ---- ④ 全量提示词（放开上限）→ 子进程 kb\env 检索内核 ----
    tishi_lie = shengcheng_tishi(chayi, panduan, jimu, bsc, shangxian=999)
    linshi_lu = JIEGUO / '检索提示词-全量.json'
    linshi_lu.write_text(json_dumps({'tishi_lie': [
        {'laiyuan': t.laiyuan, 'chaxun_ciyu': t.chaxun_ciyu} for t in tishi_lie]}),
        encoding='utf-8')
    neijian = BEN_MU / 'jiansuo_neihe.py'
    wan = subprocess.run([KB_PY, str(neijian), str(linshi_lu),
                          str(JIEGUO / '检索结果-分类.json')],
                         capture_output=True, text=True, encoding='utf-8',
                         errors='replace', timeout=600)
    print(wan.stdout.strip())
    if wan.returncode != 0:
        print(f'检索内核失败：{wan.stderr[-300:]}')
        return 1
    fenlei = json.loads((JIEGUO / '检索结果-分类.json').read_text(encoding='utf-8'))

    # ---- ⑤ 计算结果 × 检索条文 合并（按来源科目回挂差异行）----
    chayi_jian = {(x.qijian, x.kemu): x for x in chayi.xiang}
    hebing: dict[str, list] = {}
    for leibie in ('收入类', '成本类'):
        kuai_lie = []
        for zu in fenlei.get(leibie, []):
            kemu = zu['laiyuan'].split('-', 1)[1] if '-' in zu['laiyuan'] else None
            x = chayi_jian.get(('2026-Q1', kemu)) if kemu else None
            jisuan_qu = (None if x is None else {
                'yusuan_yuan': _yuan(x.chushi_fen), 'shiji_yuan': _yuan(x.shiji_fen),
                'chae_yuan': _yuan(x.chae_fen), 'chalv_bps': x.chalv_bps,
                'fa': x.fa, 'yujing': x.yujing})
            kuai_lie.append({'laiyuan': zu['laiyuan'], 'kemu': kemu,
                             'jisuan': jisuan_qu, 'chaxun': zu['chaxun'],
                             'tiaowen': zu['tiaowen']})
        hebing[leibie] = kuai_lie
    zong_lu = JIEGUO / '检索结果-分类.json'
    zong_lu.write_text(json_dumps(hebing), encoding='utf-8')
    print(f'[4] 合并落盘：{zong_lu.name}（计算结果 + 检索条文全文，无省略）')

    # ---- ⑥ Word 两张大表（计算列跨行合并）+ PDF ----
    xie_docx(hebing, JIEGUO / '检索结果-分类.docx')
    print(f'[5] 落盘：{JIEGUO / "检索结果-分类.docx"}（收入类 / 成本类 两张大表）')
    from jiansuo_fenbiao import zhuan_pdf
    if zhuan_pdf(JIEGUO / '检索结果-分类.docx', JIEGUO / '检索结果-分类.pdf'):
        print(f'[6] 落盘：{JIEGUO / "检索结果-分类.pdf"}（Word 转换件）')

    # ---- [7] 排版级 PDF：pdf-creator 引擎（cjk-auto 主题 + Chrome 渲染）----
    # 与 [6] 的区别：[6] 是 Word 排版的转换件；[7] 走主题化 HTML→PDF——
    # 中文正式文档排版（宋体正文/黑体标题/表格斑马线/表头跨页重复），
    # 技能来源：daymade-docs/pdf-creator（本地已装，Chrome 后端零 pip 依赖）
    try:
        pdf_lu = JIEGUO / '检索结果-分类-排版.pdf'
        xie_pdf_chrome(hebing, chayi, pdf_lu)
        print(f'[7] 落盘：{pdf_lu}（pdf-creator 排版版）')
    except Exception as cuo:                        # 排版失败不阻断——[6] 的 PDF 仍在
        print(f'[7] 排版版失败（{cuo}）——[6] 的 Word 转换件仍可用')
    return 0


def xie_pdf_chrome(hebing: dict, chayi, pdf_lu: Path) -> None:
    """用 pdf-creator 技能的引擎出排版级 PDF：cjk-auto 主题 + headless Chrome。

    技能分工（借引擎不造轮子）：本函数只构建 HTML（两张类 × 计算结果表
    + 检索条文表，条文原文全文），主题 CSS 与 Chrome 渲染交给
    daymade-docs/pdf-creator 的 _build_full_html / _render_chrome。
    """
    # 技能装在 First 工作区（跨工作区引用，路径固定）
    mdf_scripts = Path(r'D:\public\First\.agents\skills\claude-code-skills'
                       r'\daymade-docs\pdf-creator\scripts')
    sys.path.insert(0, str(mdf_scripts))
    import md_to_pdf as mdf

    def _biao(biaotou_lie: list[str], hang_lie: list[list[str]],
              kuan_lie: list[int] | None = None) -> str:
        tou = ''.join(f'<th>{w}</th>' for w in biaotou_lie)
        if kuan_lie:
            lie_qun = ('<colgroup>'
                       + ''.join(f'<col style="width:{k}%">' for k in kuan_lie)
                       + '</colgroup>')
        else:
            lie_qun = ''
        ti = ''.join(
            '<tr>' + ''.join(f'<td>{w}</td>' for w in hang) + '</tr>' for hang in hang_lie)
        return (f'<table>{lie_qun}<thead><tr>{tou}</tr></thead>'
                f'<tbody>{ti}</tbody></table>')

    html_kuai: list[str] = []
    #: 列宽预算（%）——cjk-auto 在 Chrome 下的已知问题：表格右缘出血 2~6pt
    #: （pdf-creator 文档自认，正常应路由 WeasyPrint；本机无 WeasyPrint 走
    #: Chrome），修复三板斧：版心左右放宽 + 显式列宽 + 任意断行保护
    js_kuan = [22, 13, 13, 13, 13, 13, 13]          # 计算结果表（7 列）
    suo_kuan = [20, 13, 12, 9, 46]                  # 检索条文表（5 列，原文给大头）
    for xu, leibie in enumerate(('收入类', '成本类')):
        html_kuai.append(f'<h2>表{"一" if xu == 0 else "二"} · {leibie}</h2>')
        # 计算结果表：该类全部科目（计算程序的完整输出）
        js_hang = [[x.kemu, f'{x.chushi_fen / 100:,.2f}', f'{x.shiji_fen / 100:,.2f}',
                    f'{x.chae_fen / 100:,.2f}', f'{x.chalv_bps / 100:.2f}%',
                    x.fa, x.yujing]
                   for x in chayi.xiang if x.fangxiang == leibie]
        html_kuai.append('<h3>计算结果</h3>')
        html_kuai.append(_biao(['科目', '预算(元)', '实际(元)', '差额(元)',
                                '差异率', 'F/A', '预警'], js_hang, js_kuan))
        # 检索条文表：向量库直出（原文全文，无省略）
        suo_lie: list[list[str]] = []
        for zu in hebing.get(leibie, []):
            for t in zu['tiaowen']:
                suo_lie.append([zu['laiyuan'], t['dingwei'], t['laiyuan_lu'],
                                f"{t['zongfen']:.4f}", t['neirong']])
        html_kuai.append('<h3>kb2 检索条文（向量库直出，全文）</h3>')
        html_kuai.append(_biao(['来源提示词', '条文定位', '命中路', 'RRF 分',
                                '条文原文（全文）'], suo_lie, suo_kuan))
    css = (mdf.THEMES_DIR / 'cjk-auto.css').read_text(encoding='utf-8')
    css += ('\n/* 本文档覆盖（压过主题的 nowrap !important） */\n'
            '@page { margin: 2cm 1.2cm 2cm 1.2cm; }\n'
            'table { width: calc(100% - 10pt) !important; table-layout: fixed !important; }\n'
            'table td, table th { white-space: normal !important; '
            'word-break: break-all !important; overflow-wrap: normal !important; }\n')
    full = mdf._build_full_html(''.join(html_kuai), css, 'kb2 检索结果分表')
    mdf._render_chrome(full, str(pdf_lu))


def xie_docx(hebing: dict, lujing: Path) -> None:
    """两张大表 → Word：计算列对同来源跨行合并（vMerge），条文原文全文。

    行角色模型（防写乱的关键）：每行带角色——'表头' / '组首'（计算列
    有值，若后随续行则 vMerge restart）/ '组续'（计算列 vMerge continue，
    只有条文四列有值）/ '单行'（无检索命中或孤条，普通单元格）。
    条文原文【全文】进表格——没有省略号（用户明确要求）。
    """
    import zipfile

    def _zhuan_yi(wen: str) -> str:
        return wen.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    kuai = [_duanluo('kb2 检索结果分表 · 计算结果 + 条文全文（零模型）', 28)]
    for xu, leibie in enumerate(('收入类', '成本类')):
        kuai.append(_duanluo(f'表{"一" if xu == 0 else "二"} · {leibie}', 24))

        # ---- 组装行（角色, 11 列文本）：表头 + 每来源一组 ----
        rows: list[tuple[str, list[str]]] = [('表头', list(KB_LIE))]
        for zu in hebing.get(leibie, []):
            js = zu.get('jisuan')
            ming = (f"{zu['kemu']}（预警 {js['yujing']}）" if js else zu['laiyuan'])
            suan = ([js['yusuan_yuan'], js['shiji_yuan'], js['chae_yuan'],
                     f"{js['chalv_bps'] / 100:.2f}%", js['fa'], js['yujing']]
                    if js else ['—', '—', '—', '—', '—', '—'])
            if not zu['tiaowen']:
                rows.append(('单行', [ming] + suan + ['—', '—', '—', '（无命中）']))
                continue
            for di, t in enumerate(zu['tiaowen']):
                shuju = [t['dingwei'], t['laiyuan_lu'],
                         f"{t['zongfen']:.4f}", t['neirong']]
                if di == 0:
                    rows.append(('组首', [ming] + suan + shuju))
                else:
                    rows.append(('组续', [''] * 7 + shuju))

        # ---- 渲染：'组首'后随'组续' → restart；'组续' → continue；其余普通 ----
        hang_xml: list[str] = []
        for i, (juese, hang) in enumerate(rows):
            xia_yi_xu = rows[i + 1][0] if i + 1 < len(rows) else '末尾'
            ge_lie = []
            for j, ziduan in enumerate(hang):
                ku = KB_KUAN[j]
                he = ''
                if juese == '组首' and j <= 6 and xia_yi_xu == '组续':
                    he = '<w:vMerge w:val="restart"/>'
                elif juese == '组续' and j <= 6:
                    he = '<w:vMerge/>'
                jia = '<w:b/><w:bCs/>' if juese == '表头' else ''
                didao = ('<w:shd w:val="clear" w:fill="D9E2F3"/>'
                         if juese == '表头' else '')
                duiqi = ('center' if juese == '表头' or j in (4, 5, 6, 8, 9)
                         else 'left')
                ge_lie.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{ku}" w:type="dxa"/>{didao}{he}'
                    f'<w:vAlign w:val="center"/></w:tcPr>'
                    f'<w:p><w:pPr><w:jc w:val="{duiqi}"/></w:pPr>'
                    f'<w:r><w:rPr>{jia}<w:sz w:val="16"/><w:szCs w:val="16"/></w:rPr>'
                    f'<w:t xml:space="preserve">{_zhuan_yi(ziduan)}</w:t></w:r></w:p></w:tc>')
            hang_xml.append('<w:tr>' + ''.join(ge_lie) + '</w:tr>')
        wangge = '<w:tblGrid>' + ''.join(f'<w:gridCol w:w="{k}"/>' for k in KB_KUAN) + '</w:tblGrid>'
        biankuang = '<w:tblBorders>' + ''.join(
            f'<w:{bian} w:val="single" w:sz="4" w:space="0"/>'
            for bian in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>'
        kuai.append('<w:tbl><w:tblPr><w:tblW w:w="15138" w:type="dxa"/>'
                    '<w:tblLayout w:type="fixed"/>' + biankuang + '</w:tblPr>'
                    + wangge + ''.join(hang_xml) + '</w:tbl>')
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(kuai)
        + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
          '<w:pgMar w:top="850" w:bottom="850" w:left="850" w:right="850"/></w:sectPr>'
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
    with zipfile.ZipFile(lujing, 'w', zipfile.ZIP_DEFLATED) as yasuo:
        yasuo.writestr('[Content_Types].xml', leixing)
        yasuo.writestr('_rels/.rels', rels)
        yasuo.writestr('word/document.xml', document)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + ''.join(kuai)
        + '<w:sectPr><w:pgSz w:w="16838" w:h="11906" w:orient="landscape"/>'
          '<w:pgMar w:top="850" w:bottom="850" w:left="850" w:right="850"/></w:sectPr>'
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
    with zipfile.ZipFile(lujing, 'w', zipfile.ZIP_DEFLATED) as yasuo:
        yasuo.writestr('[Content_Types].xml', leixing)
        yasuo.writestr('_rels/.rels', rels)
        yasuo.writestr('word/document.xml', document)


def _duanluo(wen: str, daxiao: int) -> str:
    """标题段落（黑体居中）。"""
    return (f'<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
            f'<w:r><w:rPr><w:b/><w:bCs/><w:rFonts w:eastAsia="黑体"/>'
            f'<w:sz w:val="{daxiao}"/><w:szCs w:val="{daxiao}"/></w:rPr>'
            f'<w:t xml:space="preserve">{wen}</w:t></w:r></w:p>')


if __name__ == '__main__':
    sys.exit(zhukong())
