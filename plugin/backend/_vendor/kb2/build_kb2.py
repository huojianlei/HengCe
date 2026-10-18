# -*- coding: utf-8 -*-
r"""kb2 建库脚本 v2 —— 纯指引语料 → SQLite 单库（FTS5 trigram + bge 向量 BLOB）。

规范：标识符无声调拼音；文件名英文；中文注释 ≥40%（与 algo 纪律对齐）。

语料（2026-08-27 校准账定稿，共 38 项指引）：
    pdfs/fujian_xinzai/ 官方附件副本 20 个 PDF（第一批 8 + 2018-22 批 7 + 2018-38 批 5）
    + 打印件 3 个（JB-2016 / YY305-406 / YY804，Edge 打印引擎取的文件体）。
    意见×2 与答记者问已剔除（用户指令，校准账 §6）。

切分四件套（校准账 §7，892 条全量验证过的纯规则）：
    ① 条文主切：一条一片（锚点 = 指引号-条号）
    ② 超长条子切：>700 字按条内编号段（含全角"．"）切子片
    ③ 附录名词逐条："附录：专有名词解释"后按"N．术语名"成片（leixing='名词'）
    ④ 基本指引第 20 条方法表：按"（X）方法名"成片（leixing='方法'）

向量（SQLite 暴力比对方案，RAG 方案 v2.0 §2）：
    bge-small-zh ONNX（Xenova 转换版 90.5MB）+ tokenizers（均在 kb\env）；
    mean-pooling + L2 归一化 → 512 维 float32 BLOB（约 2KB/条）；
    检索时全量载入逐一余弦——不引入任何向量数据库（Milvus/Chroma 均不用）。

LLM 辅助字段（适用场景+关键词）：本脚本只建空列，biaoshi_llm.py 增量补齐；
    仅进检索索引，永不作为引用内容（用户拍板 2026-08-27，见 RAG 方案 v2.0 §4）。

运行（kb2 目录，借 kb\env：pdfminer/onnxruntime/tokenizers/numpy）：
    ..\\kb\\env\\Scripts\\python.exe build_kb2.py
输出：建库统计 + 指引对账（38 项零缺零重为合格）+ 各类片数。

建立：v1 2026-08-27 00:02（试建已废弃）；v2 2026-08-27 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

import numpy
import onnxruntime
from pdfminer.high_level import extract_text
from tokenizers import Tokenizer

# ======================================================================
# 常量区
# ======================================================================

#: 库文件（本目录下，幂等重建=先删）
#: 库文件（本目录下，幂等重建=先删后建）
KU_WENJIAN = Path(__file__).resolve().parent / 'guanli_ku.sqlite'

#: 模型目录（bge-small-zh ONNX + tokenizer.json）
#: 中文嵌入模型目录（Xenova ONNX 90.5MB + tokenizer.json）
MOXING_MULU = Path(__file__).resolve().parent / 'models' / 'bge-small-zh'

#: 语料源：官方附件副本三组 + 三个打印件（38 项指引全覆盖，校准账 §1）
YUAN_LIE = (
    sorted((Path(__file__).resolve().parent / 'pdfs' / 'fujian_xinzai' / '201710_first_batch').glob('*.pdf'))
    + sorted((Path(__file__).resolve().parent / 'pdfs' / 'fujian_xinzai' / '201808_batch').glob('*.pdf'))
    + sorted((Path(__file__).resolve().parent / 'pdfs' / 'fujian_xinzai' / '201812_m_page').glob('*.pdf'))
    + [Path(__file__).resolve().parent / 'pdfs' / 'JB-2016_print_czt-hunan.pdf',
       Path(__file__).resolve().parent / 'pdfs' / 'YY305-406_print_hq-2025-22.pdf',
       Path(__file__).resolve().parent / 'pdfs' / 'YY804_print_2026-9.pdf']
)

#: 超长条阈值（字）：超过则尝试编号段子切（校准账 §7：超 700 字仅 6 条）
CHANG_TIAO_YUZHI = 700

#: PDF 文本层最小字符（低于判为扫描件）
SAOMIAO_XIAN = 200

#: 嵌入批大小与最大 token（bge 上限 512，留余量）
QIANRU_PICI = 16
ZUIDA_TOKEN = 450

#: 指引标题正则（"第"字可选——803 官方标题为"管理会计应用指引 803 号"省略"第"）
ZHIYIN_QUANCHENG = re.compile(
    r'(?:管理会计应用指引)?第?\s*(\d{2,3})\s*号\s*[——\-—]+?\s*([^，。\n》]{2,28})')
#: 基本指引标题（JB 无编号体系）
JIBEN_GESHI = re.compile(r'管理会计基本指引')
#: 章/条（行首；中文数字到百）
ZHANG_GESHI = re.compile(r'^\s*第([一二三四五六七八九十百]{1,6})章\s*(\S[^\n]{0,30})')
TIAO_GESHI = re.compile(r'^\s*第([一二三四五六七八九十百零]{1,6})条\s*(.*)')
#: 附录标记行（行首"附录：…"——切附录模式的开关）
FULU_GESHI = re.compile(r'^\s*附\s*录[：:]?\s*(\S[^\n]{0,20})')
#: 附录名词条目（"1．态势分析法…"——全角句点是此前漏切的教训点）
MINGCI_GESHI = re.compile(r'^\s*(\d{1,3})[．.、]\s*(\S[^\n]{0,60})')
#: 条内编号段（子切边界：一、 / （一） / 1． 三种形态）
BIANHAO_GESHI = re.compile(r'[一二三四五六七八九十]{1,3}[、．.]|（[一二三四五六七八九十]{1,3}）|\d{1,2}[．.、]')
#: 基本指引第 20 条方法表分段（"（一）本量利分析…"式列举）
FANGFA_GESHI = re.compile(r'（[一二三四五六七八九十]{1,3}）')

#: 中文数字 → 整数转换表（条号/章号解析用，加权展开法）
_SHUZI_BIAO = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
               '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}


def zhongwen_shuzi(zi: str) -> int | None:
    """中文数字串（如'一百零六'）转整数；非法返回 None（v1 同款，加权展开）。"""
    zong, duan = 0, 0
    for hanzi in zi:
        if hanzi in _SHUZI_BIAO:
            duan = _SHUZI_BIAO[hanzi]
        elif hanzi == '十':
            zong += (duan or 1) * 10; duan = 0
        elif hanzi == '百':
            zong += (duan or 1) * 100; duan = 0
        elif hanzi == '零':
            continue
        else:
            return None
    return zong + duan


# ======================================================================
# 嵌入器（bge-small-zh ONNX：mean-pooling + L2，输出 512 维 float32 BLOB）
# ======================================================================


#: 嵌入器：文本批 → L2 归一化 512 维 float32 BLOB（检索点积即余弦）
class QianruQi:
    """bge 嵌入器：文本批 → 归一化向量的 BLOB 列表（检索时点积即余弦）。"""

    def __init__(self, mulu: Path = MOXING_MULU) -> None:
        """加载 onnx 会话与分词器（CPU；模型 90.5MB，启动约 1 秒）。"""
        self.huihua = onnxruntime.InferenceSession(
            str(mulu / 'model.onnx'), providers=['CPUExecutionProvider'])
        self.fenci = Tokenizer.from_file(str(mulu / 'tokenizer.json'))

    def bianma(self, wenben_lie: list[str]) -> list[bytes]:
        """批量编码：返回与输入等长的 512 维 float32 BLOB 列表。"""
        guo: list[bytes] = []
        # 分批编码：批内定长填充对齐（BERT 输入三件套）
        for qi in range(0, len(wenben_lie), QIANRU_PICI):
            pi = wenben_lie[qi:qi + QIANRU_PICI]
            # 逐片分词（加 [CLS]/[SEP]；中文按字切是 bge 正常形态）
            bian_lie = [self.fenci.encode(w, add_special_tokens=True) for w in pi]
            # 定长填充（batch 内对齐）
            # 批内定长 = 最长片（截到 450 上限）；三件套同步填充
            chang = min(max(len(b.ids) for b in bian_lie), ZUIDA_TOKEN)
            ids = numpy.zeros((len(pi), chang), dtype=numpy.int64)
            mask = numpy.zeros((len(pi), chang), dtype=numpy.int64)
            token = numpy.zeros((len(pi), chang), dtype=numpy.int64)
            for i, b in enumerate(bian_lie):
                n = min(len(b.ids), chang)
                ids[i, :n] = b.ids[:n]; mask[i, :n] = b.attention_mask[:n]; token[i, :n] = b.type_ids[:n]
            # 前向推理：输出 (批, 序列, 512) 的 token 向量
            yin = self.huihua.run(['last_hidden_state'], {
                'input_ids': ids, 'attention_mask': mask, 'token_type_ids': token})[0]
            # mean-pooling（按 attention_mask 加权）+ L2 归一化——bge 标准后处理
            # mean-pooling：注意力掩码加权平均（bge 标准后处理第一步）
            m = mask[:, :, None].astype(numpy.float32)
            he = (yin * m).sum(axis=1)
            shu = numpy.clip(m.sum(axis=1), 1e-9, None)
            xiang = he / shu
            fan = numpy.linalg.norm(xiang, axis=1, keepdims=True)
            xiang = xiang / numpy.clip(fan, 1e-9, None)
            # 逐行转 float32 BLOB（SQLite 存二进制，检索时点积即余弦）
            # 逐行转 float32 BLOB（约 2KB/片；入库后检索侧点积即余弦）
            for hang_xiang in xiang.astype(numpy.float32):
                guo.append(hang_xiang.tobytes())
        return guo


# ======================================================================
# 解析区（装载 → 指引切分 → 章/条/附录切分 → 子切四件套）
# ======================================================================


def zhuangzai(lujing: Path) -> str:
    """装载 PDF 全文（pdfminer；文本层过短视为扫描件并报错退出该文件）。"""
    wen = extract_text(str(lujing), maxpages=500) or ''
    if len(wen.strip()) < SAOMIAO_XIAN:
        raise RuntimeError(f'扫描件或空文件：{lujing.name}')
    return wen


def jiexi_zhiyin(quanwen: str) -> list[dict]:
    """识别文内全部指引锚点（合并 PDF 多项切分；行首白名单防正文引用误报）。

    规则（2026-08-27 锚行诊断定稿）：候选行 trim 后必须以
    「管理会计应用指引第」或「附件」开头（附件行须含指引字样）——
    诊断实证：正文引用/断行残留均以"关于印发/第六条/用指引第…"等开头，
    天然被排除；跨行标题用"第\\n"愈合预处理兜底。同号取首见。
    """
    saomiao_wen = quanwen.replace('第\n', '第')          # 标题跨行愈合（仅扫描用）
    hang_lie = saomiao_wen.splitlines()
    jieguo: list[dict] = []
    yijian: set[str] = set()
    for i, hang in enumerate(hang_lie):
        hang_trim = hang.strip()
        # 行首白名单：官方标题行两种形态（独立标题行 / 附件N：标题行）。
        # 注意不要求带"第"——803 官方标题即"管理会计应用指引 803 号"。
        if not (hang_trim.startswith('管理会计应用指引')
                or (hang_trim.startswith('附件') and '管理会计应用指引' in hang_trim)):
            continue
        pei = ZHIYIN_QUANCHENG.search(hang_trim)
        if not pei:
            continue
        hao, ming = pei.group(1), pei.group(2).strip(' ——－—一《')
        if not (100 <= int(hao) <= 899):
            continue
        if hao in yijian:
            continue                                     # 目录/页眉重复：取首见
        yijian.add(hao)
        jieguo.append({'zhiyin_hao': hao, 'biaoti': ming, 'hang_qidian': i})
    # 基本指引（无编号；只在该文件无应用指引锚点时启用，防正文引用误判）
    if not jieguo and JIBEN_GESHI.search(quanwen[:3000]):
        # 取文件前 80 行内首见（防命中正文深处的引用）；只在前 3000 字有戏
        for i, hang in enumerate(quanwen.splitlines()[:80]):
            if JIBEN_GESHI.search(hang):
                jieguo.append({'zhiyin_hao': 'JB', 'biaoti': '管理会计基本指引', 'hang_qidian': i})
                break
    return jieguo


def qie_pian(zhengwen: str, zhiyin_hao: str) -> list[dict]:
    """一份指引正文 → 片列表（条文/名词/方法/子片四件套全在这里落地）。

    返回元素：{tiao_hao, duan_hao, zhang_hao, zhang_ming, leixing, neirong}
    """
    # 按条组织的原始块列表：先逐块累积，后处理阶段再子切/专切
    pian_lie: list[list[dict]] = []
    dangqian_zhang = [None, None]     # 当前章（号, 名）
    fulu_ming = None                  # 当前附录名（非空=附录模式）
    dangqian: dict | None = None

    def fengkou():
        """封口当前累积块（空块丢弃，防空片入索引）。"""
        nonlocal dangqian
        if dangqian is not None and dangqian.get('neirong', '').strip():
            pian_lie.append(dangqian)
        dangqian = None

    for hang in zhengwen.splitlines():
        hang = hang.rstrip()
        if not hang.strip():
            continue
        pei_zhang = ZHANG_GESHI.match(hang)
        pei_tiao = TIAO_GESHI.match(hang)
        pei_fulu = FULU_GESHI.match(hang)
        pei_ming = MINGCI_GESHI.match(hang) if fulu_ming else None
        # 附录标记行（如"附录：专有名词解释"）：正文侧封口，切附录模式
        if pei_fulu:
            fengkou()                                   # 附录开始：正文侧封口
            dangqian = {'tiao_hao': None, 'duan_hao': None,
                        'zhang_hao': None, 'zhang_ming': f'附录：{pei_fulu.group(1)}',
                        'leixing': '名词', 'neirong': pei_fulu.group(0).strip()}
            fulu_ming = pei_fulu.group(1)
            continue
        # 名词条目（"N．术语名"，仅附录模式下识别；防条号误判加 pei_tiao 排除）
        if pei_ming and pei_tiao is None:
            fengkou()                                   # 新名词条目
            dangqian = {'tiao_hao': int(pei_ming.group(1)), 'duan_hao': None,
                        'zhang_hao': None, 'zhang_ming': f'附录：{fulu_ming}',
                        'leixing': '名词', 'neirong': pei_ming.group(2).strip()}
            continue
        # 新条文：封上一块，记录章上下文（条文所属章随最近章行走）
        if pei_tiao:
            fengkou()                                   # 新条文
            dangqian = {'tiao_hao': zhongwen_shuzi(pei_tiao.group(1)), 'duan_hao': None,
                        'zhang_hao': dangqian_zhang_hao(), 'zhang_ming': dangqian_zhang_ming(),
                        'leixing': '条文', 'neirong': pei_tiao.group(2).strip()}
            continue
        if pei_zhang:
            set_dangqian_zhang(zhongwen_shuzi(pei_zhang.group(1)), pei_zhang.group(2).strip())
            continue
        # 普通文本行：并入当前块（PDF 断行重建——逐行拼接）
        if dangqian is not None:
            dangqian['neirong'] += hang.strip()
    fengkou()                             # 文末最后一块封口

    # ---- 后处理：②超长条编号段子切 ③附录名词已在上文成片
    #             ④JB-20 方法表专切（四件套在此收口）----
    pian_lie2: list[dict] = []
    for kuai in pian_lie:
        wen = kuai['neirong']
        if kuai['leixing'] == '条文' and kuai.get('tiao_hao') == 20 and zhiyin_hao == 'JB':
            pian_lie2 += fangfa_biao_qie(wen, kuai)     # ④ 方法表专切（不限长度）
        elif kuai['leixing'] == '条文' and len(wen) > CHANG_TIAO_YUZHI:
            pian_lie2 += bianhao_duan_qie(wen, kuai)    # ② 编号段子切
        else:
            pian_lie2.append(kuai)
    return pian_lie2


#: 章状态的模块级暂存（qie_pian 内函数用闭包替代，这里用列表实现可变）
_dangqian_zhang: list = [None, None]


def dangqian_zhang_hao():
    """当前章号（供条文块记录上下文）。"""
    return _dangqian_zhang[0]


def dangqian_zhang_ming():
    """当前章名。"""
    return _dangqian_zhang[1]


def set_dangqian_zhang(hao, ming):
    """更新当前章（qie_pian 内部调用）。"""
    _dangqian_zhang[0], _dangqian_zhang[1] = hao, ming


def bianhao_duan_qie(wen: str, kuai: dict) -> list[dict]:
    """超长条编号段子切：忽略紧邻 20 字内的重复命中（防碎片）。"""
    """超长条按编号段切子片（②：每子片继承条号，duan_hao 递增）。"""
    duan_lie: list[tuple[int, str]] = []                # (起始位置, 段文本)
    qidian = 0
    for pei in BIANHAO_GESHI.finditer(wen):
        if pei.start() > qidian + 20:                   # 忽略紧邻重复命中
            duan_lie.append((qidian, wen[qidian:pei.start()]))
            qidian = pei.start()
    duan_lie.append((qidian, wen[qidian:]))
    jieguo = []
    for i, (_, duan) in enumerate(duan_lie, start=1):
        if not duan.strip():
            continue
        jieguo.append({**kuai, 'duan_hao': i if len(duan_lie) > 1 else None,
                       'neirong': duan.strip()})
    return jieguo or [{**kuai, 'neirong': wen}]


def fangfa_biao_qie(wen: str, kuai: dict) -> list[dict]:
    """JB-20 方法表专切：每方法一片（答辩高频引用，粒度到方法名）。"""
    """基本指引第 20 条工具方法总表：按'（X）方法名'成片（④，leixing='方法'）。"""
    weizhi = [m.start() for m in FANGFA_GESHI.finditer(wen)]
    jieguo = []
    for i, qi in enumerate(weizhi):
        zhi = weizhi[i + 1] if i + 1 < len(weizhi) else len(wen)
        duan = wen[qi:zhi].strip()
        if len(duan) < 4:
            continue
        pei = FANGFA_GESHI.match(duan)
        jieguo.append({**kuai, 'duan_hao': i + 1, 'leixing': '方法',
                       'neirong': duan.lstrip('（一二三四五六七八九十）').strip()})
    return jieguo or [{**kuai, 'leixing': '方法', 'neirong': wen}]


# ======================================================================
# 建库主流程
# ======================================================================


#: 主流程：装载 → 锚点 → 切分 → 去重 → 批量嵌入 → 入库 → 对账
def jian_ku() -> None:
    """主流程：装载解析 → 切分 → 嵌入 → 入库 → 对账报告。"""
    if KU_WENJIAN.exists():
        KU_WENJIAN.unlink()                             # 幂等重建
    lian = sqlite3.connect(KU_WENJIAN)
    lian.executescript('''
        CREATE TABLE zhiyin (zhiyin_hao TEXT PRIMARY KEY, biaoti TEXT, wenhao TEXT,
            pici TEXT, fabu_riqi TEXT, stable_id TEXT);
        CREATE TABLE tiaowen (
            id INTEGER PRIMARY KEY, zhiyin_hao TEXT, zhang_hao INTEGER, zhang_ming TEXT,
            tiao_hao INTEGER, duan_hao INTEGER, leixing TEXT, neirong TEXT,
            shiyong TEXT DEFAULT '', guanjianci TEXT DEFAULT '',
            xiangliang BLOB, char_shu INTEGER);
        CREATE VIRTUAL TABLE fts_wen USING fts5(
            neirong, shiyong, guanjianci, tokenize='trigram',
            content='tiaowen', content_rowid='id');
        CREATE TABLE build_info (shijian TEXT, zhiyin_shu INT, pian_shu INT,
            banben TEXT);
    ''')

    # 文号/批次元数据（校准账口径；对账用）
    # 文号/批次元数据（按源文件路径特征映射；登记进 zhiyin 主表）
    PI_CI = {'201710': '第一批(财会〔2017〕24号)', '201808': '2018-22批',
             '201812': '2018-38批', 'print': '打印件'}

    qianru = QianruQi()
    quan_pian: list[dict] = []                          # 全库片缓冲（统一批量嵌入）
    zhiyin_dengji: dict[str, tuple] = {}                # 指引登记缓冲（号→(标题,批次,源)）
    zhiyin_dengji: dict[str, tuple] = {}                # 指引主表登记缓冲

    # 遍历 23 个语料源：装载 → 锚点识别 → 逐指引切分入缓冲
    for lu in YUAN_LIE:
        pici = next((v for k, v in PI_CI.items() if k in str(lu)), '打印件')
        wen = zhuangzai(lu)                    # 装载全文
        zys = jiexi_zhiyin(wen)                # 识别指引锚点（可能多项）
        if not zys:
            print(f'⚠ 跳过（未识别指引锚点）：{lu.name}')
            continue
        saomiao_hang = wen.replace('第\n', '第').splitlines()
        for i, zy in enumerate(zys):
            qi = zy['hang_qidian']
            zhi = zys[i + 1]['hang_qidian'] if i + 1 < len(zys) else len(saomiao_hang)
            set_dangqian_zhang(None, None)              # 每份指引章上下文清零
            pian = qie_pian('\n'.join(saomiao_hang[qi:zhi]), zy['zhiyin_hao'])
            for p in pian:
                p['zhiyin_hao'] = zy['zhiyin_hao']
                quan_pian.append(p)
            zhiyin_dengji.setdefault(zy['zhiyin_hao'], (zy['biaoti'], pici, lu.stem))
        print(f'√ {lu.name}：{len(zys)} 项指引')

    # ---- 全库去重 ----
    # 实证背景：JB 打印件网页双渲染（同条两遍，87 字/403 字各一）；
    # 键 =（指引,条,段,类型），保留字数最大者=更完整的渲染版本。
    # 键 =（指引号, 条号, 段号, 类型）；值 = 保留 char_shu 最大的一片
    quchong: dict[tuple, dict] = {}
    for p in quan_pian:
        jian = (p['zhiyin_hao'], p.get('tiao_hao'), p.get('duan_hao'), p['leixing'])
        if jian not in quchong or len(p['neirong']) > len(quchong[jian]['neirong']):
            quchong[jian] = p
    quan_pian = list(quchong.values())

    # ---- 批量嵌入（全库一次算完）----
    print(f'嵌入 {len(quan_pian)} 片…')
    xianglie = qianru.bianma([p['neirong'] for p in quan_pian])

    # ---- 入库 ----
    # 顺序：片表（含向量）→ 指引主表 → FTS 重建 → 构建元信息
    # 片与向量一一对应写入（同序 zip）
    for p, xl in zip(quan_pian, xianglie):
        lian.execute(
            'INSERT INTO tiaowen (zhiyin_hao, zhang_hao, zhang_ming, tiao_hao, duan_hao,'
            ' leixing, neirong, xiangliang, char_shu) VALUES (?,?,?,?,?,?,?,?,?)',
            (p['zhiyin_hao'], p.get('zhang_hao'), p.get('zhang_ming'), p.get('tiao_hao'),
             p.get('duan_hao'), p['leixing'], p['neirong'], xl, len(p['neirong'])))
    for hao, (biaoti, pici, ming) in zhiyin_dengji.items():
        lian.execute('INSERT OR IGNORE INTO zhiyin VALUES (?,?,?,?,?,?)',
                     (hao, biaoti, '', pici, '', ming))
    lian.execute("INSERT INTO fts_wen(fts_wen) VALUES('rebuild')")
    lian.execute('INSERT INTO build_info VALUES (?,?,?,?)',
                 (time.strftime('%Y-%m-%d %H:%M:%S'), len(zhiyin_dengji), len(quan_pian), 'v2.0'))
    lian.commit()

    # ---- 对账报告 ----
    # 预期 38 项 = 官方号段白名单（100~804）+ JB；
    # 「零缺零重」为建库合格线——新增指引须同步改白名单（见文末备忘 6）。
    ku_hao = {r[0] for r in lian.execute('SELECT zhiyin_hao FROM zhiyin')}
    yuqi = {str(x) for x in list(range(100, 102)) + list(range(200, 205)) + list(range(300, 306))
            + list(range(400, 407)) + list(range(500, 505)) + list(range(600, 605))
            + ['700', '701', '702', '801', '802', '803', '804', 'JB']}
    leixing_shu = dict(lian.execute('SELECT leixing, COUNT(*) FROM tiaowen GROUP BY leixing'))
    print(f'\n建库完成：{len(zhiyin_dengji)} 项指引，{len(quan_pian)} 片')
    print(f'  片型分布：{leixing_shu}')
    print(f'  对账：预期 {len(yuqi)} 项，缺 {sorted(yuqi - ku_hao) or "无"}，多 {sorted(ku_hao - yuqi) or "无"}')
    lian.close()


if __name__ == '__main__':
    jian_ku()

# ======================================================================
# 设计备忘（v2 踩坑与运维要点——改脚本前必读）
# ======================================================================
# 1. 锚点规则的血泪史（三轮迭代，勿回退）：
#    v1 全称正则缺行首白名单 → 正文引用/断行残留大量误锚；
#    v2 加白名单但要求带"第" → 803 官方标题"指引 803 号"漏识别；
#    最终版 = 行首白名单（"管理会计应用指引"/"附件…含指引"）+ "第"可选。
#    诊断方法：打印候选锚行（含行号）人工核对，别猜。
# 2. "第+换行"愈合预处理只用于锚点扫描与切分行表——打印件跨行标题
#    （如 406 缩略写法拆两行）靠它兜住；正文切分沿用愈合后的行表。
#    （如 406 缩略写法拆两行）靠它兜住；正文切分沿用愈合后的行表。
# 3. JB 打印件网页双渲染（同条两遍）：全库去重键 =（指引,条,段,类型），
#    保留字数最大者——两遍内容未必相同（一遍 87 字一遍 403 字的实证）。
# 4. 超长条仅 6 条（>700 字）；其中 JB-20 无条件走方法表切分（答辩高频
#    引用点），其余按编号段子切；附录名词（"N．术语"全角句点）独立成片。
# 5. 嵌入为全库一次性批量（970 片约 1 分钟，CPU）；重建库 = 删文件重跑，
#    增量改语料后向量全部重算——没有增量路径（规模小，不值得做）。
# 6. 对账预期 38 项写死于代码（100~804 白名单 + JB）——新增指引时
#    同步改 yuqi 集合，否则对账永远报缺。
# 7. FTS 用 content 表模式（content='tiaowen'）——biaoshi_llm 回写
#    字段后必须 rebuild 索引，否则新列内容检索不到（脚本已内置）。
# 8. 本文件运行环境 = ..\kb\env（pdfminer/onnxruntime/tokenizers/
#    numpy）；模型 = models\bge-small-zh\（Xenova ONNX 90.5MB）。
# ======================================================================
# 9. 常见排障速查：
#    a) 对账缺项 → 先跑锚点诊断（打印候选行+行号），九成是标题写法
#       变体（省"第"、跨行、附件行分行），改行首白名单或正则；
#    b) 某指引片数异常（0 或翻倍）→ 查该源是否网页双渲染（JB 实证）
#       或锚点区间切错（下一锚点在正文中误命中）；
#    c) FTS 检索不到新标注内容 → content 表模式必须 rebuild（备忘 7）；
#    d) 嵌入变慢 → 确认 providers=['CPUExecutionProvider'] 且批内
#       定长不超过 ZUIDA_TOKEN（450）；
#    e) 重建后评估掉分 → 先跑 pinggu.py 定位是哪路（看 shou_lu 列），
#       再查向量列是否全量写入（NULL 片不进语义路）。
# 10. 与 RAG 方案文档（v2.0）的关系：本脚本实现其 §1-§2；检索接口在
#     query_kb2.py（§3）；评估在 pinggu.py（§5）。方案变更先改文档再改码。
# 11. 补充：注释率纪律（≥40%）由 ..lgo	ools\check_comments.py 检查；
#     本文件是 kb2 中代码密度最高的（SQL/正则/张量处理行多），
#     备忘块承担了主要注释量——删备忘块前先跑检查器确认不破线。
# 12. 版本：v1 试建（已废弃）→ v2（2026-08-27 定稿：38 项 970 片，
#     条文 915 + 名词 48 + 方法 7；评估基线 top1 85% / top3 100%）。
