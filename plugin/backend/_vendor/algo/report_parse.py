# -*- coding: utf-8 -*-
"""报表模板解析层 —— 方案B 步骤 1 前置二段：把"长得像预算报告"的文本还原成标准 8 列。

新增口径（用户指令 2026-08-30："我们的目标是把预算报告输入进去，预算报告
肯定不长【平表】那个样子……预算数据和真实数据，都放进去，分表放"）：
真实预算报告是"文档"不是"数据表"——报告头 + 编制说明 + 分节小标题 +
"科目×期间"矩阵表（预算一张表、实际一张表）+ 登记表（变更/业务量/行业对标）。
本模块把这种骨架【离线、确定性地】解析回标准 8 列文本，接在 file_extract
之后、与 llm_clean 智能分流形成"两级识别"：

    文件 → file_extract（解包成文本行）
         → report_parse（像预算报告？→ 模板解析成 8 列）──命中──▶ data_ingest
                       └────不像（交回分流）──▶ llm_clean（直解/LLM 归一化）▶ data_ingest

模板骨架假设（中式预算报告的常见排法，2026-08-30 与用户对齐）：
    报告头：公司/报告名称（含"XXXX年度"字样）、编制单位、编制日期；
    分节标题：短行，含"预算表/实际/业务量/变更…登记/行业对标"+"表"字，
              常带"（单位：元）"注记；
    预算/实际表：首列"科目（项目）"，其余列为期间列（可混"合计""完成率"
                等非期间列），可有"合计"行；
    业务量表：科目,统计期间,数量,单位；变更登记表：变更事项,发生期间,
              登记时间,说明；行业对标表：指标,数值,单位,备注。

职责边界（与 llm_clean 的分界——两级识别各管一段）：
    本模块只吃【文本形态】、只认【模板骨架】：识别不了一点就返回
    shibie=False，调用方交回 llm_clean 智能分流（直解或 LLM 归一化）——
    绝不硬解、绝不猜列语义。数值合法性不在此判（'abc' 原样透传，
    由 data_ingest 的拒绝清单处理——链路诚实，坏行仍走人工复核）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    数据值用中文。零第三方依赖（正则 + 字符串处理，标准库）。

数值纪律：本模块不换算数值（"185000.00"原样透传，换算归 data_ingest）；
    只做"外衣清理"——剥掉单元格首尾空白与"元/%"后缀；纯函数（无 I/O）。

使用示例（知识点速览，v0.1 2026-08-30；doctest 格式——可直接复制到交互
    环境运行，也可用 `python -m doctest report_parse.py` 自动验证，并由
    tests\\test_demos.py 纳入常规测试守护，示例过时测试即红）：

    知识点 1 · 一份迷你预算报告 → 标准 8 列（合计行/完成率列自动跳过）
    >>> from report_parse import shitu_jiexi
    >>> yangli = (
    ...     '华衡科技有限公司\\n2026年度预算报告\\n编制单位：财务部\\n编制日期：2026-01-15\\n'
    ...     '\\n一、编制说明\\n本报告按季度列示全年预算，作为滚动调整的基准。\\n'
    ...     '\\n二、年度分季度预算表（单位：元）\\n'
    ...     '科目,2026年第一季度,2026年第二季度,合计\\n'
    ...     '营收,100000.00,110000.00,210000.00\\n'
    ...     '合计,100000.00,110000.00,210000.00\\n'
    ...     '\\n三、实际经营数据表（单位：元）\\n'
    ...     '科目,2026年第一季度,完成率\\n'
    ...     '营收,105000.00,105.00%\\n'
    ... )
    >>> jg = shitu_jiexi(yangli)
    >>> jg.shibie
    True
    >>> print(jg.wenben_8lie, end='')
    数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注
    预算基础,2026-Q1,营收,100000.00,元,预算报告,2026-01-15,
    预算基础,2026-Q2,营收,110000.00,元,预算报告,2026-01-15,
    实时经营,2026-Q1,营收,105000.00,元,预算报告,2026-01-15,

    知识点 2 · 期间写法五花八门也能规范（报告里常混用多种写法）
    >>> from report_parse import guifan_qijian
    >>> [guifan_qijian(x, '2026') for x in
    ...  ('2026年第一季度', '一季度', '2026-Q1', '2026年1月', '3月')]
    ['2026-Q1', '2026-Q1', '2026-Q1', '2026-01', '2026-03']

    知识点 3 · 不像预算报告 → 诚实交回（shibie=False，调用方走 llm_clean）
    >>> jg2 = shitu_jiexi('老板说：这个月花多了，下个月注意。\\n')
    >>> (jg2.shibie, jg2.wenben_8lie)
    (False, '')

    知识点 4 · 有分表但缺编制日期 → 拒绝识别（记录缺台账字段，宁可不认）
    >>> jg3 = shitu_jiexi('2026年度预算报告\\n二、预算表（单位：元）\\n'
    ...                   '科目,一季度\\n营收,1000.00\\n')
    >>> (jg3.shibie, '编制日期' in jg3.beizhu)
    (False, True)

命名对照表（拼音标识符 → 中文含义）：
    shitu_jiexi         识别解析（总入口：像报告就解析成 8 列，不像就交回）
    guifan_qijian       规范期间（五花八门的期间写法 → '2026-Q1'/'2026-01'）
    JieXiJieguo         解析结果（shibie 是否识别 / wenben_8lie 标准文本 / beizhu 说明）
    _fenjie_hang        分解行（文本 → 去空白行清单）
    _zhao_fenjie        找分节（按关键词定位各分表的表头行位置）
    _jie_matrix         解矩阵表（科目×期间 → 逐格展开成记录；跳合计行/列）
    _jie_danyebiao      解单页表（业务量/变更/行业对标等固定四列小表）
    _shuzhi_qingxi      数值清理（剥空白与元/%后缀；'—'等占位 → 跳过）
    _hanzi_shuzi        汉字数字（一二三四 → 1~4）
    shibie / wenben_8lie / beizhu   是否识别 / 标准 8 列文本 / 交回原因或备注

口径依据：用户指令 2026-08-30（预算报告分表输入）；data_ingest 8 列规范
         （解析出口必须与其表头逐字一致）；llm_clean 两级识别分工（模板
         命中不惊动模型；识别失败交回分流，不重复造轮子）。
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ======================================================================
# 常量与数据结构区
# ======================================================================

#: 标准 8 列表头——解析出口必须与此逐字一致（下游 data_ingest 的入口契约）
BIAOTOU_8LIE = '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'

#: 矩阵表首列的合法叫法（科目/项目——两种叫法都收）
SHOULIE_MING = ('科目', '项目', '科目名称')

#: 分节识别关键词表：(分节类型, 标题必须同时含的关键词组)
#: 顺序即优先级——"预算表"先于"实际"判（防"实际经营预算表"这类混合标题串台）
FENJIE_JIAN = (
    ('yusuan', ('预算', '表')),
    ('shiji', ('实际', '表')),
    ('yewuliang', ('业务量', '表')),
    ('biangeng', ('变更', '登记')),
    ('hangye', ('行业', '对标')),
)

#: 分节标题长度上限——报告正文叙述里也可能出现"预算""表"字样，
#: 真正的分节标题都是短行；超长的当叙述跳过（防误判的便宜闸门）
FENJIE_CHANGDU = 40

#: 矩阵行/列的跳过词：行首含"合计"整行跳过；列头含"合计/完成率"整列跳过
TIAOGUO_LIE = ('合计', '小计', '总计', '完成率', '占比', '差异率', '备注')

#: 单元格占位符——出现即视为空格（跳过该格，不生成记录）
ZHANWEI_fu = ('—', '–', '-', '/')


@dataclass(frozen=True)
class JieXiJieguo:
    """解析结果：识别成功与否 + 标准 8 列文本 + 说明。

    shibie=False 时 wenben_8lie 恒为空串、beizhu 写明交回原因——调用方
    （端到端层/未来界面）据此把原文转交 llm_clean 智能分流，两级衔接。
    """

    shibie: bool        # 是否识别为预算报告模板
    wenben_8lie: str    # 标准 8 列文本（shibie=False 时为空串）
    beizhu: str         # 交回原因（失败时）或解析摘要（成功时）


# ======================================================================
# 内部工具区（期间规范 / 数值清理 / 汉字数字）
# ======================================================================


def _hanzi_shuzi(zifu: str) -> int | None:
    """汉字数字 → 阿拉伯数字（一二三四 → 1~4；其余返回 None）。"""
    yingshe = {'一': 1, '二': 2, '三': 3, '四': 4}
    return yingshe.get(zifu)


def guifan_qijian(zifuchuan: str, nianfen: str | None) -> str | None:
    """五花八门的期间写法 → 规范期间（'2026-Q1' / '2026-01'；认不出 → None）。

    收录写法（按尝试顺序）：
        2026-Q1 ｜ 2026年第一季度/2026年1季度 ｜ 一季度（年从报告取）｜
        Q1（年从报告取）｜ 2026-01 ｜ 2026年1月 ｜ 1月（年从报告取）。
    认不出返回 None——调用方据此把该列当"非期间列"（完成率/合计）跳过。
    """
    s = zifuchuan.strip()
    if not s:
        return None
    du = re.search(r'(20\d{2})\s*[-年]\s*Q\s*([1-4])(?!\d)', s)    # 2026-Q1 / 2026年Q1
    if du:
        return f'{du.group(1)}-Q{du.group(2)}'
    du = re.search(r'(20\d{2})年第?([一二三四1-4])季度(?!\d)', s)   # 2026年第一季度
    if du:
        ji = _hanzi_shuzi(du.group(2)) or int(du.group(2))
        return f'{du.group(1)}-Q{ji}'
    du = re.search(r'第?([一二三四1-4])季度', s)                    # 一季度（年从报告取）
    if du and nianfen:
        ji = _hanzi_shuzi(du.group(1)) or int(du.group(1))
        return f'{nianfen}-Q{ji}'
    du = re.search(r'^Q\s*([1-4])$', s)                             # Q1（年从报告取）
    if du and nianfen:
        return f'{nianfen}-Q{du.group(1)}'
    du = re.search(r'(20\d{2})-(0?[1-9]|1[0-2])(?!\d)', s)          # 2026-01（防 2026-13 咬成 1 月）
    if du:
        return f'{du.group(1)}-{int(du.group(2)):02d}'
    du = re.search(r'(20\d{2})年(0?[1-9]|1[0-2])(?!\d)月', s)       # 2026年1月
    if du:
        return f'{du.group(1)}-{int(du.group(2)):02d}'
    du = re.search(r'^(0?[1-9]|1[0-2])月$', s)                      # 1月（年从报告取）
    if du and nianfen:
        return f'{nianfen}-{int(du.group(1)):02d}'
    return None


def _shuzhi_qingxi(danyuan: str) -> str | None:
    """单元格数值清理：剥首尾空白与"元/%"后缀；'—'等占位 → None（跳过该格）。

    只清"外衣"不判合法——'abc' 原样返回，合法性归 data_ingest 的拒绝清单
    （链路诚实：坏行仍进人工复核，而不是在解析层悄悄消失）。
    """
    s = danyuan.strip()
    if not s or s in ZHANWEI_fu:
        return None
    if s.endswith('元') or s.endswith('%'):
        s = s[:-1].strip()
    return s or None


def _fenjie_hang(wenben: str) -> list[str]:
    """文本 → 行清单：去首尾空白、丢全空行（与 file_extract 输出形态对齐）。"""
    return [hang.strip() for hang in wenben.split('\n') if hang.strip()]


def _zhao_fenjie(hang_lie: list[str]) -> dict[str, int]:
    """找分节：扫描行清单，按关键词表定位各分表【标题行】的位置。

    返回 {分节类型: 标题行下标}；同一类型只记首次出现（报告里同类表
    不重复）。判定条件 = 三条同时成立：含该组全部关键词、含"表"字
    （分节标题都以"……表"收尾；叙述行即便出现"变更登记"等字样、
    只要不含"表"就不会误判）、行长 ≤ FENJIE_CHANGDU。
    """
    jieguo: dict[str, int] = {}
    for i, hang in enumerate(hang_lie):
        if len(hang) > FENJIE_CHANGDU:
            continue
        for leixing, jian in FENJIE_JIAN:
            if leixing in jieguo:
                continue
            if all(x in hang for x in jian) and '表' in hang:
                jieguo[leixing] = i
                break
    return jieguo


def _fenjie_lie(cells: list[str], nianfen: str | None) -> list[tuple[int, str]]:
    """矩阵表头 → 期间列清单 [(列下标, 规范期间)]——非期间列（合计/完成率）跳过。"""
    lie_lie: list[tuple[int, str]] = []
    for xia, danyuan in enumerate(cells):
        if xia == 0:                                # 首列 = 科目列
            continue
        qi = guifan_qijian(danyuan, nianfen)
        if qi:
            lie_lie.append((xia, qi))
    return lie_lie


def _biaotou_wei(hang_lie: list[str], biaotou_i: int) -> int | None:
    """从分节标题向后找【表头行】（第一个含逗号的行，最多看 3 行）。

    分节定位记录的是标题行下标；真正的表头（"科目,一季度,…"）在标题
    下一两行——中间允许夹一行"单位：元"之类的注记。找不到返回 None。
    """
    for i in range(biaotou_i + 1, min(biaotou_i + 4, len(hang_lie))):
        if ',' in hang_lie[i]:
            return i
    return None


def _jie_matrix(hang_lie: list[str], biaotou_i: int, nianfen: str | None,
                leibie: str) -> list[tuple[str, ...]]:
    """矩阵表 → 逐格展开的记录（类别,期间,科目,数值,'元'）——合计行/列与空格跳过。

    表头行 = 分节标题后第一个含逗号的行（首格须是"科目/项目"族）；
    其后含逗号的行都是数据行，遇到不含逗号的行即出表（分节标题/叙述
    都没有逗号——天然的表格边界）。
    """
    biaotou_hang = _biaotou_wei(hang_lie, biaotou_i)
    if biaotou_hang is None:
        return []
    cells = [x.strip() for x in hang_lie[biaotou_hang].split(',')]
    if not cells or cells[0] not in SHOULIE_MING:
        return []
    lie_lie = _fenjie_lie(cells, nianfen)
    jilu: list[tuple[str, ...]] = []
    for hang in hang_lie[biaotou_hang + 1:]:
        if ',' not in hang:
            break                                   # 出表（空行/下一个分节标题）
        danyuan_lie = [x.strip() for x in hang.split(',')]
        kemu = danyuan_lie[0]
        if not kemu or any(t in kemu for t in ('合计', '小计', '总计')):
            continue                                # 合计行整行跳过
        for xia, qi in lie_lie:
            if xia >= len(danyuan_lie):
                continue                            # 短行容错：缺格不炸
            zhi = _shuzhi_qingxi(danyuan_lie[xia])
            if zhi is None:
                continue                            # 空格/'—'：该格无数据
            jilu.append((leibie, qi, kemu, zhi, '元'))
    return jilu


def _jie_danyebiao(hang_lie: list[str], biaotou_i: int, nianfen: str | None,
                   leixing: str, shou_qijian: str | None,
                   bianzhi_riqi: str) -> list[tuple[str, ...]]:
    """单页小表 → 记录（业务量/变更登记/行业对标三种固定列法，按表头名映射）。"""
    biaotou_hang = _biaotou_wei(hang_lie, biaotou_i)
    if biaotou_hang is None:
        return []
    cells = [x.strip() for x in hang_lie[biaotou_hang].split(',')]
    jilu: list[tuple[str, ...]] = []
    for hang in hang_lie[biaotou_hang + 1:]:
        if ',' not in hang:
            break
        danyuan = [x.strip() for x in hang.split(',')]
        if any(t in danyuan[0] for t in ('合计', '小计', '总计')):
            continue
        if leixing == 'yewuliang':                  # 科目,统计期间,数量,单位
            if len(danyuan) < 4:
                continue
            qi = guifan_qijian(danyuan[1], nianfen)
            zhi = _shuzhi_qingxi(danyuan[2])
            if qi and zhi:
                jilu.append(('实时经营', qi, danyuan[0], zhi, danyuan[3]))
        elif leixing == 'biangeng':                 # 变更事项,发生期间,登记时间,说明
            if len(danyuan) < 4:
                continue
            qi = guifan_qijian(danyuan[1], nianfen)
            if qi:
                # 数值恒 1 次——变更登记是"事件"，登记时间做台账更新时间
                jilu.append(('经营变更', qi, danyuan[0], '1', '次',
                             '预算报告', danyuan[2] or bianzhi_riqi, danyuan[3]))
        elif leixing == 'hangye':                   # 指标,数值,单位,备注
            if len(danyuan) < 3:
                continue
            zhi = _shuzhi_qingxi(danyuan[1])
            if zhi and shou_qijian:
                danwei = danyuan[2] if len(danyuan) > 2 else ''
                beizhu = danyuan[3] if len(danyuan) > 3 else ''
                jilu.append(('行业对标', shou_qijian, danyuan[0], zhi, danwei,
                             '预算报告', bianzhi_riqi, beizhu))
    return jilu


# ======================================================================
# 对外入口区
# ======================================================================


def shitu_jiexi(wenben: str) -> JieXiJieguo:
    """识别解析总入口：像预算报告 → 标准 8 列文本；不像 → 诚实交回。

    流程：找年度与编制日期 → 找各分节表头 → 预算/实际走矩阵解析、
    业务量/变更/行业走单页表解析 → 组装 8 列文本（来源统一"预算报告"，
    更新时间统一编制日期——台账字段齐了才放行）。
    识别失败的三种情形（beizhu 写明原因，调用方交回 llm_clean）：
        ① 一个分节都没认出（根本不是报告骨架）；
        ② 认出了分表但全文缺"编制日期"（记录缺台账字段，宁可不认）；
        ③ 分表里一张"科目×期间"矩阵都没有且没有可映射的小表。
    """
    hang_lie = _fenjie_hang(wenben)
    fenjie = _zhao_fenjie(hang_lie)
    if not fenjie:
        return JieXiJieguo(False, '', '未识别出预算报告模板的任何分节（交回智能分流）')

    # 年度：优先"XXXX年度"字样；编制日期：报告头台账行（记录必需）
    nianfen: str | None = None
    bianzhi_riqi: str | None = None
    for hang in hang_lie:
        du = re.search(r'(20\d{2})年度', hang)
        if du and nianfen is None:
            nianfen = du.group(1)
        du = re.search(r'编制日期[:：]\s*(20\d{2}-\d{2}-\d{2})', hang)
        if du and bianzhi_riqi is None:
            bianzhi_riqi = du.group(1)
    if nianfen is None and bianzhi_riqi:
        nianfen = bianzhi_riqi[:4]                  # 编制日期的年兜底
    if bianzhi_riqi is None:
        return JieXiJieguo(False, '', '分表已识别但全文缺"编制日期"，'
                                     '记录缺台账字段——宁可不认（交回智能分流）')

    # 预算/实际矩阵先行——顺带拿"首个期间"给行业对标行当归属期间
    jilu: list[tuple[str, ...]] = []
    shou_qijian: str | None = None
    for leixing in ('yusuan', 'shiji'):
        if leixing in fenjie:
            kuai = _jie_matrix(hang_lie, fenjie[leixing], nianfen,
                               '预算基础' if leixing == 'yusuan' else '实时经营')
            if kuai and shou_qijian is None:
                shou_qijian = kuai[0][1]
            jilu.extend(kuai)
    for leixing in ('yewuliang', 'biangeng', 'hangye'):
        if leixing in fenjie:
            jilu.extend(_jie_danyebiao(hang_lie, fenjie[leixing], nianfen,
                                       leixing, shou_qijian, bianzhi_riqi))
    if not jilu:
        return JieXiJieguo(False, '', '分节已识别但未解析出任何记录（交回智能分流）')

    # 组装标准 8 列：矩阵记录 5 元组补台账三字段（来源/时间/备注空）
    hang_lie_out = [BIAOTOU_8LIE]
    for jilu_xiang in jilu:
        if len(jilu_xiang) == 5:                    # 矩阵/业务量记录：补来源时间备注
            leibie, qi, kemu, zhi, danwei = jilu_xiang
            hang_lie_out.append(f'{leibie},{qi},{kemu},{zhi},{danwei},'
                                f'预算报告,{bianzhi_riqi},')
        else:                                       # 变更/行业记录：自带台账三字段
            hang_lie_out.append(','.join(jilu_xiang))
    return JieXiJieguo(True, '\n'.join(hang_lie_out) + '\n',
                       f'识别 {len(jilu)} 条记录（模板解析，零 LLM）')
