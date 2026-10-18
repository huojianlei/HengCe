# -*- coding: utf-8 -*-
"""积木模块拆解 —— 方案B 步骤 5a 的【四模块聚合】确定性核心。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    专有缩写可保留（F/A 等）。

口径依据（权威文件，修改本模块前必读）：
    docs/01-需求说明.md v2.0 §3 FR-8（四模块，队友拍板 T-21）
    docs/textbook/finagent-算法核对文档-定稿.md v2.1 §5（五模块表作组成参考，
        模块数按拍板改为四；§0.5 符号口径与 F/A 唯一真源）
    docs/proposal-full-extract.txt 行 60~66（占比与高亮输出要求）
    TODO.md T-05（采购差异取消自定义公式——本模块不发明任何公式）、
        T-21（四模块，人力归成本，消灭重复计算）、
        T-22⑤（科目→模块映射表随本模块落地）

四模块（队友拍板 2026-08-23，权威顺序）：
    收入模块 / 成本模块（含人力）/ 费用模块 / 采购模块。
    人力归成本模块——人工薪酬/效率/配置不再单列，杜绝同一笔直接人工
    差异被成本、人力两个模块重复统计。

模块定位（本模块是什么、不是什么）：
    本模块是【聚合层】——吃 variance 的逐科目差异行（展示口径差额，
    已带 F/A 与预警），按"科目→模块"映射聚合成四模块差异额/占比/高亮，
    输出模块溯源明细。本模块【不重算】任何微观差异公式（MPV/MUV/LRV/LEV
    已在 planning_operational 覆盖）——四模块口径因此统一为
    "展示口径差额聚合"，无自定义公式、无重复计算，天然满足 T-05/T-21。

三个口径决策点（2026-08-23 用户批准按建议默认值落地）：
    D1 采购模块 = 采购类科目的展示口径差额聚合（默认关键词映射判定，
        不发明任何公式——T-05 取消采购自定义公式后的落地口径）；
    D2 占比分母 = Σ|各模块净差额| + |未归属净差额|（"各桶净差额"绝对值
        合计，F/A 正负分列）——占比合计恒为 10000 基点（不变量，见
        知识点 2 与随机检验 P2）；模块内部 F/A 冲抵反映在净差额里，
        行级明细可下钻；净总差异另列（避免正负抵消导致占比失真）；
    D3 核心问题模块 = 不利（A）模块中 |差额| 最大者；全部有利时 None
        （展示层显示"无"）；并列时取四模块顺序靠前者。

符号口径（定稿 §0.5）：差额 = 实际 − 基准（展示口径）；F/A 是唯一真源。
    模块级 F/A 按模块方向从差额符号推得（与 variance 同规则）：
        收入模块：正 = 超额 = F；负 = 未达标 = A；
        成本/费用/采购模块：正 = 超支 = A；负 = 节约 = F；零 = '—'。

数值纪律：金额 = 整数分；占比 = 整数基点（1% = 100 基点），half-up 整数
    舍入；全程整数运算零浮点；纯函数（无 I/O、无全局状态）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；数字例题 = 教材 04 章应用题，
    按展示口径转写：材料价格超支 8,000 元 → +800,000 分 A，
    期望值全部手工验算写死）：

    知识点 1 · 教材 04 章应用题：四模块聚合 + 占比 + 高亮
    >>> from building_blocks import JimuHang, chai_jimu
    >>> hang_lie = [
    ...     JimuHang('2026-Q1', '材料价格差异', 800000, 'A', '红', 800),
    ...     JimuHang('2026-Q1', '人工效率差异', -100000, 'F', '黄', 500),
    ...     JimuHang('2026-Q1', '销量差异', 300000, 'F', '无', 120),
    ...     JimuHang('2026-Q1', '制造费用差异', 600000, 'A', '红', 1000),
    ... ]
    >>> jg = chai_jimu(hang_lie)
    >>> [(x.mokuai, x.chae_fen, x.fa) for x in jg.mokuai_lie]
    [('收入模块', 300000, 'F'), ('成本模块', 500000, 'A'), ('费用模块', 0, '—'), ('采购模块', 800000, 'A')]
    >>> # 占比（基点，分母=Σ|模块净差额|=1,600,000 分）：采购 50%、成本 31.25%、收入 18.75%
    >>> [x.zhanbi_bps for x in jg.mokuai_lie]
    [1875, 3125, 0, 5000]
    >>> # 净总差异 = 实际合计超基准 16,000 元（+1,600,000 分）；高亮 = 采购模块
    >>> (jg.jing_heji_fen, jg.hexin_mokuai)
    (1600000, '采购模块')

    知识点 2 · 未归属科目不静默丢弃（进清单、占分母，交人工补映射）
    >>> jg2 = chai_jimu(hang_lie + [JimuHang('2026-Q1', '其他业务', 200000, 'A', '黄', 300)])
    >>> (len(jg2.weiguishu_lie), jg2.weiguishu_zhanbi_bps)
    (1, 1111)
    >>> # 200,000 ÷ 1,800,000 = 11.11% → 1111 基点；四模块 8889 + 未归属 1111 = 10000（不变量）
    >>> sum(x.zhanbi_bps for x in jg2.mokuai_lie) + jg2.weiguishu_zhanbi_bps
    10000

    知识点 3 · 全部有利 → 无核心问题模块（高亮为 None，展示层显示"无"）
    >>> jg3 = chai_jimu([JimuHang('2026-Q1', '营收', 500000, 'F', '黄', 300)])
    >>> jg3.hexin_mokuai is None, jg3.mokuai_lie[0].fa
    (True, 'F')

    知识点 4 · 自定义映射注入（覆盖默认：把"材料价格"归到成本模块）
    >>> jg4 = chai_jimu(hang_lie, zidingyi_yingshe=lambda k: '成本模块' if '材料价格' in k else None)
    >>> [(x.mokuai, x.chae_fen) for x in jg4.mokuai_lie]
    [('收入模块', 300000), ('成本模块', 1300000), ('费用模块', 0), ('采购模块', 0)]

命名对照表（拼音标识符 → 中文含义）：
    JimuHang            积木输入行（一个科目一行的展示口径差额）
    MokuaiXiang         模块项（一个模块的聚合结果 + 溯源明细）
    JimuJieguo          积木结果（四模块 + 未归属清单 + 合计/占比/高亮）
    JimuCuowu           积木错误（校验失败异常）
    chai_jimu           拆积木（主函数）
    yingshe_mokuai      映射模块（默认关键词映射，公开可测）
    cong_chayi_xiang    从差异项转换（variance.ChayiXiang 的鸭子类型适配器）
    chae_fen            差额（分，展示口径，可负可零）
    zhanbi_bps          占比（基点，非负；分母为 0 时 None）
    jing_heji_fen       净总差异（Σ全部行差额，含未归属）
    zhanbi_fenmu_fen    占比分母（分）= Σ|各模块净差额| + |未归属净差额|
    hexin_mokuai        核心问题模块（不利模块中 |差额| 最大者；无则 None）
    weiguishu_*         未归属（科目映射不中的行——不静默丢弃）

与上下游的关系：
    上游：variance（步骤 3a/3b 逐科目差异行——经 cong_chayi_xiang 适配）；
    下游：看板（步骤 7 积木差异占比饼图/核心问题模块高亮）、
          BSC（步骤 5b 双模型并列）、整改方案（步骤 8 按模块定责）。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# ======================================================================
# 常量区（数据值用中文——四模块名与 F/A、预警枚举）
# ======================================================================

#: 四模块名（定稿 §5 权威顺序：收入、成本、费用、采购——人力已并入成本）
MOKUAI_SHOURU = '收入模块'
MOKUAI_CHENGBEN = '成本模块'
MOKUAI_FEIYONG = '费用模块'
MOKUAI_CAIGOU = '采购模块'

#: 四模块展示顺序（输出 mokuai_lie 的固定次序）
MOKUAI_SHUNXU = (MOKUAI_SHOURU, MOKUAI_CHENGBEN, MOKUAI_FEIYONG, MOKUAI_CAIGOU)

#: 采购模块关键词——先匹配（"材料价格"须先于"材料"被采购捕获，防串模块）
CAIGOU_GUANJIANZI = ('采购', '供应商', '议价', '物流', '材料价格')
#: 成本模块关键词（材料/人工/人力/制造费用等生产端科目；人力在此——T-21）
CHENGBEN_GUANJIANZI = ('制造费用', '生产成本', '材料', '人工', '人力', '薪酬',
                       '工时', '闲置', '电力', '水电', '燃料', '动力', '维修', '折旧',
                       '成本')  # 通用兜底（可控成本等；采购成本已被采购模块先命中）
#: 费用模块关键词（期间费用；"销售费"排在收入模块的"销售"之前——顺序保证；
#: 办公费 = 通用期间费用科目，单列关键词防漏）
FEIYONG_GUANJIANZI = ('费用', '期间', '管理费', '销售费', '财务费', '办公费')
#: 收入模块关键词（营收/销量/毛利等经营成果类科目）
SHOURU_GUANJIANZI = ('收入', '营收', '销量', '销售', '毛利', '利润', '净利', '收益', '价格')

#: F/A 合法取值（'—' 表示零差额）
HEFA_FA = ('F', 'A', '—')
#: 预警合法取值（与 variance 三档 + 无法定级一致）
HEFA_YUJING = ('无', '黄', '红', '—')

#: 单行差额绝对值上限（分）——与 variance 同口径的合理性校验
ZUIDA_CHAE_FEN = 9 * 10**11


class JimuCuowu(ValueError):
    """积木输入校验失败（空输入 / 非法字段 / 重复行）。

    继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class JimuHang:
    """积木输入行：一个科目（一行）的展示口径差额（variance 产物的精简形态）。

    字段说明：
        qijian:      期间键（2026-01 / 2026-Q1；透传，本模块不解析语义）。
        kemu:        科目名（映射到四模块的依据；关键词不中 → 未归属）。
        chae_fen:    差额（分）= 实际 − 基准（展示口径，可负可零）。
        fa:          行级 F/A（来自 variance 唯一真源；仅随明细透传，
                     模块级 F/A 按方向规则重推——不信任行级值）。
        yujing:      预警（'无' / '黄' / '红' / '—'，随明细透传）。
        chalv_bps:   差异率（基点，非负；可为 None 表示无法定级）。
    """

    qijian: str
    kemu: str
    chae_fen: int
    fa: str
    yujing: str
    chalv_bps: int | None


@dataclass(frozen=True)
class MokuaiXiang:
    """模块项：一个模块的聚合结果 + 溯源明细（看板饼图/定责的数据源）。

    字段说明：
        mokuai:      模块名（'收入模块' / '成本模块' / '费用模块' / '采购模块'）。
        chae_fen:    模块差异额 = Σ该模块各行差额（展示口径净额）。
        fa:          模块级 F/A——按模块方向从差额符号推得（见模块头规则）。
        zhanbi_bps:  占比（基点）= |chae_fen| ÷ 占比分母 × 10000，half-up；
                     分母为 0 时 None（无法定义，交人工）。
        hang_shu:    归属行数（明细行数，便于看板下钻）。
        mingxi:      归属的输入行列表（溯源明细，顺序 = 输入顺序）。
    """

    mokuai: str
    chae_fen: int
    fa: str
    zhanbi_bps: int | None
    hang_shu: int
    mingxi: list[JimuHang]


@dataclass(frozen=True)
class JimuJieguo:
    """积木拆解总结果（四模块 + 未归属 + 合计 + 高亮）。

    字段说明：
        mokuai_lie:         四模块结果（顺序固定 = MOKUAI_SHUNXU）。
        weiguishu_lie:      未归属行（科目映射不中——不静默丢弃，交人工补映射）。
        jing_heji_fen:      净总差异 = Σ全部行差额（含未归属；正负可抵消）。
        zhanbi_fenmu_fen:   占比分母（分）= Σ|各模块净差额| + |未归属净差额|
                            （D2 口径：占比合计恒为 10000 基点；为 0 时
                            各占比为 None，交人工）。
        hexin_mokuai:       核心问题模块名（不利模块中 |差额| 最大者；
                            全部有利/零差额时 None）。
        weiguishu_zhanbi_bps: 未归属占比（基点）= |未归属净差额| ÷ 占比分母。
    """

    mokuai_lie: list[MokuaiXiang]
    weiguishu_lie: list[JimuHang]
    jing_heji_fen: int
    zhanbi_fenmu_fen: int
    hexin_mokuai: str | None
    weiguishu_zhanbi_bps: int | None


# ======================================================================
# 映射区（科目 → 模块：默认关键词映射 + 可注入自定义覆盖）
# ======================================================================


def yingshe_mokuai(kemu: str) -> str | None:
    """默认科目→模块映射（关键词匹配，先命中先得）。

    匹配顺序即四组关键词的注册顺序：采购 → 成本 → 费用 → 收入。
    顺序刻意如此：'材料价格' 必须在 '材料' 之前（否则材料价格差异会
    误入成本模块）；'销售费' 必须在 '销售' 之前（否则销售费用会误入
    收入模块）。不命中任何关键词 → None（未归属，交人工补映射）。
    """
    for mokuai, guanjianzi in (
        (MOKUAI_CAIGOU, CAIGOU_GUANJIANZI),
        (MOKUAI_CHENGBEN, CHENGBEN_GUANJIANZI),
        (MOKUAI_FEIYONG, FEIYONG_GUANJIANZI),
        (MOKUAI_SHOURU, SHOURU_GUANJIANZI),
    ):
        if any(zi in kemu for zi in guanjianzi):
            return mokuai
    return None


def cong_chayi_xiang(xiang) -> JimuHang:
    """适配器：把 variance.ChayiXiang（鸭子类型）转成本模块输入行。

    刻意不 import variance——只要对象带有 qijian/kemu/chae_fen/fa/yujing/
    chalv_bps 六个同名属性即可，模块间保持低耦合（契约式接线）。
    """
    return JimuHang(
        qijian=xiang.qijian,
        kemu=xiang.kemu,
        chae_fen=xiang.chae_fen,
        fa=xiang.fa,
        yujing=xiang.yujing,
        chalv_bps=xiang.chalv_bps,
    )


# ======================================================================
# 内部工具函数区
# ======================================================================


def _zhanbi_bps(chae_fen: int, fenmu: int) -> int | None:
    """占比（基点）= |差额| ÷ 分母 × 10000，half-up 整数实现。

    分母为 0 → None（占比无法定义——与 variance 差异率的除零纪律一致，
    交人工）；实现：(2×|差额|×10000 + 分母) // (2×分母) 即整数 half-up，
    全程无浮点。
    """
    if fenmu == 0:
        return None
    return (abs(chae_fen) * 10_000 * 2 + fenmu) // (2 * fenmu)


def _pan_mokuai_fa(chae_fen: int, mokuai: str) -> str:
    """模块级 F/A：按模块方向从差额符号推得（定稿 §0.5 方向规则）。

    收入模块：正 = 超额 = F、负 = 未达标 = A；
    成本/费用/采购模块：正 = 超支 = A、负 = 节约 = F；零 = '—'。
    """
    if chae_fen == 0:
        return '—'
    if mokuai == MOKUAI_SHOURU:
        return 'F' if chae_fen > 0 else 'A'
    return 'A' if chae_fen > 0 else 'F'


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def chai_jimu(
    shuru: list[JimuHang],
    zidingyi_yingshe: Callable[[str], str | None] | None = None,
) -> JimuJieguo:
    """四模块聚合拆解（方案B 步骤 5a；纯函数）。

    参数：
        shuru —— 每行一个科目的展示口径差额（JimuHang 列表，须非空）；
        zidingyi_yingshe —— 可选自定义映射（Callable：科目名 → 模块名或
            None）。返回非 None 时覆盖默认映射；返回 None 时回落默认。
            典型用法（T-24 科目唯一编码落地后）：按编码字典映射。

    返回：JimuJieguo（四模块 + 未归属清单 + 净合计 + 占比 + 高亮）。

    处理顺序：
        ① 校验（行类型/字段/重复键）→ ② 映射科目（自定义优先，默认兜底）
        → ③ 按模块聚合差额与明细 → ④ 模块 F/A → ⑤ 占比（分母 = Σ|模块净|+
        |未归属净|，D2 口径）→ ⑥ 净合计与核心问题模块高亮。
    """
    if not isinstance(shuru, list) or not shuru:
        raise JimuCuowu('shuru 必须为非空列表（至少一行差异输入）')

    # ① 校验 + （期间, 科目）去重键——同一科目同一期间只允许一行，防双计
    yijian: set[tuple[str, str]] = set()
    jianyan_hou: list[JimuHang] = []
    for tiao in shuru:
        if not isinstance(tiao, JimuHang):
            raise JimuCuowu(f'输入含非法元素（须为 JimuHang）：{tiao!r}')
        if not tiao.kemu or not tiao.qijian:
            raise JimuCuowu('科目与期间必须非空')
        if isinstance(tiao.chae_fen, bool) or not isinstance(tiao.chae_fen, int):
            raise JimuCuowu(f'chae_fen 必须为整数（分）：{tiao.chae_fen!r}')
        if abs(tiao.chae_fen) > ZUIDA_CHAE_FEN:
            raise JimuCuowu(f'chae_fen 超出合理范围（分）：{tiao.chae_fen}')
        if tiao.fa not in HEFA_FA:
            raise JimuCuowu(f'fa 非法：{tiao.fa}（应为 {list(HEFA_FA)}）')
        if tiao.yujing not in HEFA_YUJING:
            raise JimuCuowu(f'yujing 非法：{tiao.yujing}（应为 {list(HEFA_YUJING)}）')
        if tiao.chalv_bps is not None and (
            isinstance(tiao.chalv_bps, bool)
            or not isinstance(tiao.chalv_bps, int)
            or tiao.chalv_bps < 0
        ):
            raise JimuCuowu(f'chalv_bps 非法：{tiao.chalv_bps!r}（None 或非负整数）')
        jian = (tiao.qijian, tiao.kemu)
        if jian in yijian:
            raise JimuCuowu(f'差异输入重复（期间+科目）：{jian}——防双计')
        yijian.add(jian)
        jianyan_hou.append(tiao)

    # ② 归属判定：自定义映射优先（返回非 None 即采用），否则默认关键词映射
    def guishu(tiao: JimuHang) -> str | None:
        if zidingyi_yingshe is not None:
            zhi = zidingyi_yingshe(tiao.kemu)
            if zhi is not None:
                return zhi
        return yingshe_mokuai(tiao.kemu)

    fen_zu: dict[str, list[JimuHang]] = {m: [] for m in MOKUAI_SHUNXU}
    weiguishu: list[JimuHang] = []
    for tiao in jianyan_hou:
        mokuai = guishu(tiao)
        if mokuai in fen_zu:
            fen_zu[mokuai].append(tiao)
        else:
            # 不静默丢弃：映射不中的行进"未归属"清单，交人工补映射（D1 兜底）
            weiguishu.append(tiao)

    # ③ 聚合（顺序固定 = MOKUAI_SHUNXU）；模块 F/A 由差额符号推得；
    #    占比需等分母算出后统一回填（先占位 None）
    mokuai_lie: list[MokuaiXiang] = []
    for mokuai in MOKUAI_SHUNXU:
        hang_lie = fen_zu[mokuai]
        chae = sum(t.chae_fen for t in hang_lie)
        mokuai_lie.append(
            MokuaiXiang(
                mokuai=mokuai,
                chae_fen=chae,
                fa=_pan_mokuai_fa(chae, mokuai),
                zhanbi_bps=None,  # 分母算出后回填
                hang_shu=len(hang_lie),
                mingxi=hang_lie,
            )
        )

    # ⑤ 占比分母（D2 口径）：Σ|各模块净差额| + |未归属净差额|——
    #    保证占比合计恒为 10000 基点（随机检验 P2 的数学基础）
    weiguishu_jing = sum(t.chae_fen for t in weiguishu)
    fenmu = sum(abs(x.chae_fen) for x in mokuai_lie) + abs(weiguishu_jing)

    # 回填占比（dataclass 冻结——重建列表回填，保持输出不可变）
    mokuai_lie = [
        MokuaiXiang(
            mokuai=x.mokuai,
            chae_fen=x.chae_fen,
            fa=x.fa,
            zhanbi_bps=_zhanbi_bps(x.chae_fen, fenmu),
            hang_shu=x.hang_shu,
            mingxi=x.mingxi,
        )
        for x in mokuai_lie
    ]
    weiguishu_zhanbi = _zhanbi_bps(weiguishu_jing, fenmu)

    # ⑥ 净总差异（全部行，含未归属——正负可抵消，另列不与占比混用）
    jing_heji = sum(t.chae_fen for t in jianyan_hou)

    # 核心问题模块：不利（A）模块中 |差额| 最大者；并列取顺序靠前者（D3）
    hexin: MokuaiXiang | None = None
    for x in mokuai_lie:
        if x.fa == 'A' and (hexin is None or abs(x.chae_fen) > abs(hexin.chae_fen)):
            hexin = x

    return JimuJieguo(
        mokuai_lie=mokuai_lie,
        weiguishu_lie=weiguishu,
        jing_heji_fen=jing_heji,
        zhanbi_fenmu_fen=fenmu,
        hexin_mokuai=hexin.mokuai if hexin else None,
        weiguishu_zhanbi_bps=weiguishu_zhanbi,
    )
