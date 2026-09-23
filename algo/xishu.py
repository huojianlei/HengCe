# -*- coding: utf-8 -*-
"""判定系数输出 —— 算法层与分析层（M5）之间的【系数包】桥梁（TODO T-32）。

新增口径（TODO T-32，用户 2026-08-27 提出"本地程序需要能生成相应系数"）：
计算主线跑完后，把分散在各模块的结果汇总成一份【判定系数包】——
预警级别分布、红行明细、整体完成率、单双环结论、核心问题模块、BSC 评级、
整改优先级计数——并按【系数 → 检索提示词】映射表生成 kb2 检索查询串。

定位（RAG 方案 v2.0 §6："algo 算完 → 判定系数（T-32）→ 提示词映射 → 检索"）：
    计算层（本模块上游）──系数包──▶ 分析层 M5（检索 + LLM 报告）
    本模块是两层之间【唯一的接缝】：只做汇总与映射，不做任何分析。

分层纪律的边界声明（[043]，诚实口径）：
    本模块生成的"提示词"是【检索查询串】——由确定性映射表从系数机械
    翻译而来（如"红色预警+采购模块"→"采购成本控制 制度"），不是分析
    文案；自然语言分析归 AI 层（M5/dsh）。映射表当前为建议默认值
    【TODO T-32】，M5 层研究后可调整——改映射不改结构。

汇总口径（全部来自上游既有输出，本模块不重算任何差异/评级）：
    · 预警级别分布与红行明细 ← variance（红行按差异率降序）；
    · 整体完成率 = Σ实际 ÷ Σ基准（基点，half-up；无行/基准为 0 → None）；
    · 单双环结论与审批标志 ← loop_decision；
    · 核心问题模块 ← building_blocks（高亮模块）；
    · BSC 总分与等级 ← bsc；整改优先级计数 ← zhenggai。
    上游缺哪块，系数包对应字段为 None/空——缺数不臆造（全项目纪律）。

数值纪律：金额 = 整数分；比率 = 整数基点（1% = 100 基点），half-up
    整数舍入；纯函数（无 I/O、无全局状态）。

使用示例（知识点速览，v0.1 2026-08-30；doctest 格式——可直接复制到
    交互环境运行，也可用 `python -m doctest xishu.py` 自动验证，并由
    tests\\test_demos.py 纳入常规测试守护，示例过时测试即红）：

    知识点 1 · 一条红预警 + 双环判定 → 系数包与提示词
    >>> from xishu import XishuShuru, shengcheng_xishu
    >>> from variance import ChayiShuru, YujingDang, jisuan_chayi
    >>> from loop_decision import PanDuanShuru, panduan_huanlu
    >>> from building_blocks import JimuHang, chai_jimu
    >>> chayi = jisuan_chayi([
    ...     ChayiShuru('2026-Q1', '采购成本', '成本类',
    ...                chushi_fen=10_000_000, gundong_fen=None,
    ...                shiji_fen=11_500_000)],
    ...     dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
    >>> # 门限注入口：示例差异率 1500 基点低于 25% 新默认门限，传 100 沿用原口径
    >>> panduan = panduan_huanlu(PanDuanShuru(
    ...     chalv_bps=1500, guihua_zong_fen=900_000, zhixing_zong_fen=250_000,
    ...     yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
    >>> jimu = chai_jimu([JimuHang('2026-Q1', '采购成本', 1_500_000, 'A', '红', 1500)])
    >>> bao = shengcheng_xishu(XishuShuru(chayi=chayi, panduan=panduan, jimu=jimu))
    >>> (bao.hong_shu, bao.huang_shu, bao.wanchenglv_bps)
    (1, 0, 11500)
    >>> bao.panduan_jielun, bao.shenpi
    ('混合纠错模式', True)
    >>> bao.hexin_mokuai
    '采购模块'
    >>> [(t.laiyuan, t.chaxun_ciyu) for t in bao.tishi_lie]
    [('单双环判定', '预算调整 审批程序'), ('核心问题模块', '采购成本控制 制度'), ('红预警-采购成本', '采购成本 预算超支 管控措施')]

    知识点 2 · 空输入 → 空系数包（缺数不臆造，无提示词）
    >>> kong = shengcheng_xishu(XishuShuru())
    >>> (kong.hong_shu, kong.wanchenglv_bps, kong.panduan_jielun, len(kong.tishi_lie))
    (0, None, None, 0)

命名对照表（拼音标识符 → 中文含义）：
    XishuShuru         系数输入（五个上游结果，鸭子类型，均可 None）
    XishuBao           系数包（汇总字段 + 提示词元组）
    XishuTishi         提示词项（laiyuan 来源系数 + chaxun_ciyu 查询串）
    shengcheng_xishu   生成系数（主函数：汇总 + 映射）
    shengcheng_tishi   生成提示词（系数 → 检索查询串的映射表，TODO T-32 建议默认值）
    hong_shu / huang_shu / wu_shu       预警红/黄/无计数
    hong_hang_lie      红行明细（差异率降序：qijian/kemu/chalv_bps/fa）
    wanchenglv_bps     整体完成率（Σ实际 ÷ Σ基准，基点；无数据 → None）
    panduan_jielun / shenpi             单双环结论 / 是否需人工审批
    hexin_mokuai       核心问题模块（积木高亮）
    bsc_zongfen / bsc_dengji            BSC 总分 / 等级
    zhenggai_gao_shu / zhenggai_zhong_shu   整改高/中优先级计数
    tishi_lie          检索提示词元组（去重、上限 TISHI_SHANGXIAN 条）

口径依据：TODO.md T-32（判定系数输出）；kb2/RAG部署与使用方案.md §6
         （系数→提示词→驱动检索）与 §4（引用/数字校验闸门的输入端）；
         docs/01 需求说明 [043] 分层纪律（提示词=检索查询串，非分析文案）。
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区（映射表 = T-32 建议默认值，M5 层研究后只改此处不改结构）
# ======================================================================

#: 检索提示词上限（条）——控制 M5 提示词长度，超限按优先级截断
TISHI_SHANGXIAN = 8

#: 判定结论 → 检索查询串（单双环维度的固定映射）
PANDUAN_TISHI = {
    '单环': '预算执行 偏差 整改',
    '双环': '预算调整 审批程序',
    '混合纠错模式': '预算调整 审批程序',
}

#: 核心问题模块 → 检索查询串（积木模块维度的固定映射）
MOKUAI_TISHI = {
    '收入模块': '收入管理 制度',
    '成本模块': '成本管理 制度',
    '费用模块': '费用管控 制度',
    '采购模块': '采购成本控制 制度',
}

#: BSC 等级 → 检索查询串（仅预警/严重不合格触发——达标不查）
DENGJI_TISHI = {'预警': '平衡计分卡 绩效评价', '严重不合格': '绩效改进 制度'}


@dataclass(frozen=True)
class XishuTishi:
    """一条检索提示词：来源系数标签 + 查询串（给 M5 的检索驱动指令）。"""

    laiyuan: str        # 来源系数（'红预警-科目' / '单双环判定' / '核心问题模块' / 'BSC评级'）
    chaxun_ciyu: str    # 检索查询串（kb2 jiansuo 的输入）


@dataclass(frozen=True)
class XishuShuru:
    """系数输入：五个上游结果对象（鸭子类型；None = 该来源缺失）。"""

    chayi: object = None     # variance.ChayiJieguo（预警计数/红行/完成率来源）
    panduan: object = None   # loop_decision.PanDuanJieguo（单双环结论）
    jimu: object = None      # building_blocks.JimuJieguo（核心问题模块）
    bsc: object = None       # bsc.BscJieguo（总分/等级）
    zhenggai: object = None  # zhenggai.ZhenggaiJieguo（整改优先级计数）


@dataclass(frozen=True)
class XishuBao:
    """判定系数包：M5 分析层的全部输入事实（缺数字段为 None/空，不臆造）。"""

    hong_shu: int                       # 红色预警行数（无 chayi → 0）
    huang_shu: int                      # 黄色预警行数
    wu_shu: int                         # 无预警行数
    hong_hang_lie: tuple                # 红行明细 (qijian, kemu, chalv_bps, fa)，差异率降序
    wanchenglv_bps: int | None          # 整体完成率（基点；无行或基准为 0 → None）
    panduan_jielun: str | None          # 单双环结论（'不触发'/'单环'/'双环'/'混合纠错模式'/'复核提示'）
    shenpi: bool | None                 # 是否需人工审批
    hexin_mokuai: str | None            # 核心问题模块
    bsc_zongfen: int | None             # BSC 总分
    bsc_dengji: str | None              # BSC 等级
    zhenggai_gao_shu: int | None        # 整改高优先级条数
    zhenggai_zhong_shu: int | None      # 整改中优先级条数
    tishi_lie: tuple                    # 检索提示词（XishuTishi 元组，去重 + 限长）


# ======================================================================
# 提示词映射区（系数 → 检索查询串；T-32 建议默认值）
# ======================================================================


def shengcheng_tishi(chayi, panduan, jimu, bsc,
                     shangxian: int = TISHI_SHANGXIAN) -> tuple:
    """按映射表把系数翻成检索查询串：判定 → 核心模块 → BSC 评级 → 红/黄行。

    shangxian：条数上限（默认 TISHI_SHANGXIAN=8，服务 M5 提示词长度）；
    传更大的值可取全量提示词（如检索分表演示要覆盖每一条预警行）。

    生成规则（建议默认值，【TODO T-32】随 M5 研究调整；按优先级排序——
    结构性结论先于逐行明细，逐行明细再多也不许挤掉判定/模块提示词）：
    · 单双环判定：双环/混合 → '预算调整 审批程序'；单环 → '预算执行 偏差 整改'；
    · 核心问题模块 → 模块领域词（MOKUAI_TISHI）；
    · BSC 等级仅预警/严重不合格触发（达标不查——没有要查的问题）；
    · 红/黄预警行（按差异率降序）：不利(A) → '{科目} 预算超支 管控措施'；
      有利(F)但波动过大 → '{科目} 预算差异 分析方法'。
    同串去重、超限截断——提示词列表是给 M5 拼提示词用的，
    条目失控会撑爆上下文。
    """
    lie_lie: list[XishuTishi] = []
    if panduan is not None:
        ciyu = PANDUAN_TISHI.get(panduan.panduan)
        if ciyu:
            lie_lie.append(XishuTishi('单双环判定', ciyu))
    if jimu is not None and jimu.hexin_mokuai:
        ciyu = MOKUAI_TISHI.get(jimu.hexin_mokuai)
        if ciyu:
            lie_lie.append(XishuTishi('核心问题模块', ciyu))
    if bsc is not None:
        ciyu = DENGJI_TISHI.get(bsc.dengji)
        if ciyu:
            lie_lie.append(XishuTishi('BSC评级', ciyu))
    if chayi is not None:
        # 红黄行按差异率降序——最刺眼的先查（预警级别优先序）
        yichang = sorted((x for x in chayi.xiang if x.yujing in ('红', '黄')),
                         key=lambda x: -x.chalv_bps)
        for x in yichang:
            if x.fa == 'A':
                ciyu = f'{x.kemu} 预算超支 管控措施'
            else:
                ciyu = f'{x.kemu} 预算差异 分析方法'   # 有利但波动过大——查分析方法
            lie_lie.append(XishuTishi(f"{x.yujing}预警-{x.kemu}", ciyu))
    # 去重（同查询串只留首条——不同系数可能映射到同一查询）+ 限长
    chongfu: set[str] = set()
    jieguo: list[XishuTishi] = []
    for t in lie_lie:
        if t.chaxun_ciyu in chongfu:
            continue
        chongfu.add(t.chaxun_ciyu)
        jieguo.append(t)
        if len(jieguo) >= shangxian:
            break
    return tuple(jieguo)


# ======================================================================
# 对外入口区
# ======================================================================


def shengcheng_xishu(shuru: XishuShuru) -> XishuBao:
    """生成判定系数包：汇总五路上游 + 生成检索提示词（纯汇总，零重算）。

    汇总纪律：所有字段直接取上游既有输出；本模块唯一的"计算"是整体
    完成率（Σ实际 ÷ Σ基准，half-up 整数基点）与红行排序（差异率降序）。
    """
    hong_shu = huang_shu = wu_shu = 0
    hong_hang: list[tuple[str, str, int, str]] = []
    he_shiji = he_jizhun = 0
    you_shuju = False
    if shuru.chayi is not None:
        for x in shuru.chayi.xiang:
            if x.yujing == '红':
                hong_shu += 1
                hong_hang.append((x.qijian, x.kemu, x.chalv_bps, x.fa))
            elif x.yujing == '黄':
                huang_shu += 1
            elif x.yujing == '无':
                wu_shu += 1
            if x.jizhun_fen is not None and x.shiji_fen is not None:
                you_shuju = True
                he_shiji += x.shiji_fen
                he_jizhun += x.jizhun_fen
    hong_hang.sort(key=lambda h: -h[2])             # 红行按差异率降序
    wanchenglv = (2 * he_shiji * 10000 + he_jizhun) // (2 * he_jizhun) \
        if you_shuju and he_jizhun > 0 else None    # half-up 整数基点；零基准交 None
    return XishuBao(
        hong_shu=hong_shu, huang_shu=huang_shu, wu_shu=wu_shu,
        hong_hang_lie=tuple(hong_hang), wanchenglv_bps=wanchenglv,
        panduan_jielun=getattr(shuru.panduan, 'panduan', None),
        shenpi=getattr(shuru.panduan, 'shenpi', None),
        hexin_mokuai=getattr(shuru.jimu, 'hexin_mokuai', None),
        bsc_zongfen=getattr(shuru.bsc, 'zongfen', None),
        bsc_dengji=getattr(shuru.bsc, 'dengji', None),
        zhenggai_gao_shu=getattr(shuru.zhenggai, 'gao_shu', None),
        zhenggai_zhong_shu=getattr(shuru.zhenggai, 'zhong_shu', None),
        tishi_lie=shengcheng_tishi(shuru.chayi, shuru.panduan, shuru.jimu, shuru.bsc))
