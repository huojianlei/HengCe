# -*- coding: utf-8 -*-
"""平衡计分卡 BSC 四维评分 —— 方案B 步骤 5b 的【加权评分】确定性核心。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    专有缩写可保留（BSC、KPI 等）。

口径依据（权威文件，修改本模块前必读）：
    docs/textbook/finagent-算法核对文档-定稿.md v2.1 §6（加权评分 + 例题）
    docs/proposal-full-extract.txt 行 69~71（完整版：折算规则/权重标准/等级体系）
    TODO.md T-05（队友拍板 2026-08-23：**BSC 不封顶**——favorable 即实际超预算
        保留得分并鼓励持续，佐证 = ACCA-PM 讲义 P234-238）
    01-需求说明 v2.0 FR-9（P0；权重默认 40/30/20/10；不封顶；五档等级）

四个维度（完整版权重标准，竞赛通用专业配比）：
    财务 40%（caijing）/ 客户 30%（kehu）/ 内部流程 20%（neibu）/
    学习成长 10%（xuexi）；权重可人工自定义微调，**合计必须 = 100%**。

计算公式（定稿 §6 + 完整版 §2.3.2，全部整数化）：
    维度得分 = 该维度 KPI 达成率 × 100（达成率输入 = 整数基点，
        10000 基点 = 100%）——half-up 舍入为整数分；
    总分 = Σ（权重% × 维度得分）÷ 100——half-up 舍入为整数分；
    等级 = 总分五档：90~100 优秀 / 80~89 良好 / 70~79 合格 /
        60~69 预警 / 60 以下 严重不合格。

【不封顶口径（T-05 拍板，答辩要点）】：
    达成率 > 100% 时维度得分 > 100 原样保留、不裁剪到 100——超预算完成
    是 favorable，保留得分以鼓励持续（教材 PM 讲义 234-238 四维分类框架
    与 142 页预算偏差可控性佐证）。注意：输入侧仍设合理性上限 1,000,000
    基点（10,000%）——那是防脏数据的校验，不是得分封顶，两者不混淆。

数值纪律：达成率/权重 = 整数基点与整数百分比；得分/总分 = 整数分；
    全程整数运算零浮点（half-up 用乘除实现）；纯函数（无 I/O、无全局状态）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；数字例题 = 定稿 v2.1 §6（40/30/20/10
    权重 × 75/80/70/60 得分 → 总分 74），期望值全部手工验算写死）：

    知识点 1 · 定稿 §6 例题：默认权重 40/30/20/10 → 总分 74 → 合格
    >>> from bsc import BscShuru, jisuan_bsc
    >>> jg = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000))
    >>> (jg.caijing_defen, jg.kehu_defen, jg.neibu_defen, jg.xuexi_defen)
    (75, 80, 70, 60)
    >>> (jg.zongfen, jg.dengji)
    (74, '合格')

    知识点 2 · 不封顶（T-05 拍板）：达成率 120% → 得分 120 原样保留
    >>> jg2 = jisuan_bsc(BscShuru(12000, 8000, 7000, 6000))
    >>> jg2.caijing_defen
    120
    >>> (jg2.zongfen, jg2.dengji)
    (92, '优秀')

    知识点 3 · 自定义权重（合计必须 = 100%）
    >>> jg3 = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000, quanzhong=(20, 30, 30, 20)))
    >>> (jg3.zongfen, jg3.dengji)
    (72, '合格')

    知识点 4 · 权重非法 → 拒绝（合计 ≠ 100%）
    >>> from bsc import BscCuowu
    >>> try:
    ...     jisuan_bsc(BscShuru(7500, 8000, 7000, 6000, quanzhong=(40, 30, 20, 5)))
    ... except BscCuowu:
    ...     print('权重合计必须等于 100')
    权重合计必须等于 100

命名对照表（拼音标识符 → 中文含义）：
    BscShuru            BSC 输入（四维 KPI 达成率 + 可选自定义权重）
    BscJieguo           BSC 结果（四维得分 + 权重回显 + 总分 + 等级）
    BscCuowu            BSC 错误（校验失败异常）
    jisuan_bsc          计算 BSC（主函数）
    QUANZHONG_MOREN     默认权重（40, 30, 20, 10）——完整版标准配比
    caijing/kehu/neibu/xuexi_bps    财务/客户/内部流程/学习成长 达成率（基点）
    caijing/kehu/neibu/xuexi_defen  四维得分（整数分，不封顶可 >100）
    zongfen             总分（整数分，half-up）
    dengji              等级（优秀/良好/合格/预警/严重不合格）

与上下游的关系：
    上游：KPI 指标库（FR-11，随步骤 1b 数据入库刷新——定稿 §9 E1 修正）、
          data_ingest（四类数据供 KPI 计算）；
    下游：看板（步骤 7 BSC 四维得分雷达图）、整改方案（步骤 8 综合评级）。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区（数据值用中文——等级五档；权重为整数百分比）
# ======================================================================

#: 默认权重（财务, 客户, 内部流程, 学习成长）——完整版 §2.3.2 标准配比
QUANZHONG_MOREN = (40, 30, 20, 10)

#: 等级五档（完整版 §2.3.2：90-100 优秀 / 80-89 良好 / 70-79 合格 /
#: 60-69 预警 / 60 以下 严重不合格）
DENGJI_YOUXIU = '优秀'
DENGJI_LIANGHAO = '良好'
DENGJI_HEGE = '合格'
DENGJI_YUJING = '预警'
DENGJI_YANZHONG = '严重不合格'

#: 等级判定表（阈值降序）——总分 >= 阈值即命中该档；全部不中 = 严重不合格
DENGJI_YUZHI = (
    (90, DENGJI_YOUXIU),
    (80, DENGJI_LIANGHAO),
    (70, DENGJI_HEGE),
    (60, DENGJI_YUJING),
)

#: 达成率合理性上限（基点）= 10,000%——防脏数据校验，**不是**得分封顶
#: （不封顶口径见模块头：得分本身允许 >100）
ZUIDA_DACHENGLV_BPS = 1_000_000


class BscCuowu(ValueError):
    """BSC 输入校验失败（达成率非法 / 权重非法）。

    继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class BscShuru:
    """BSC 输入：四维 KPI 达成率（基点）+ 可选自定义权重。

    字段说明：
        caijing_bps:  财务维度 KPI 达成率（基点，10000 = 100%；非负整数）。
        kehu_bps:     客户维度 KPI 达成率（基点）。
        neibu_bps:    内部流程维度 KPI 达成率（基点）。
        xuexi_bps:    学习成长维度 KPI 达成率（基点）。
        quanzhong:    自定义权重（财务, 客户, 内部流程, 学习成长），
                      整数百分比、合计必须 = 100；None = 用默认 40/30/20/10。
    """

    caijing_bps: int
    kehu_bps: int
    neibu_bps: int
    xuexi_bps: int
    quanzhong: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class BscJieguo:
    """BSC 结果：四维得分 + 权重回显 + 总分 + 等级（看板雷达图数据源）。

    字段说明：
        caijing_defen / kehu_defen / neibu_defen / xuexi_defen:
            四维得分（整数分；不封顶——达成率 >100% 时得分 >100 保留）。
        quanzhong:  生效权重（默认或自定义，回显供报告展示）。
        zongfen:    总分 = Σ（权重 × 维度得分）÷ 100，half-up 整数。
        dengji:     等级（优秀/良好/合格/预警/严重不合格——按总分五档）。
    """

    caijing_defen: int
    kehu_defen: int
    neibu_defen: int
    xuexi_defen: int
    quanzhong: tuple[int, int, int, int]
    zongfen: int
    dengji: str
    caijing_bps: int      # 财务达成率回显（基点）——得分溯源用（T-29#7）
    kehu_bps: int         # 客户达成率回显（基点）
    neibu_bps: int        # 内部流程达成率回显（基点）
    xuexi_bps: int        # 学习成长达成率回显（基点）


# ======================================================================
# 内部工具函数区
# ======================================================================


def _dacheng_bps_defen(bps: int) -> int:
    """维度得分 = 达成率（基点）÷ 100，half-up 整数实现。

    不封顶（T-05）：达成率 > 10000 基点时得分 > 100，原样保留。
    实现：(2×bps + 100) // 200 即 half-up（÷100 后四舍五入），全程无浮点。
    """
    return (bps * 2 + 100) // 200


def _zongfen(defen: tuple[int, int, int, int], quanzhong: tuple[int, int, int, int]) -> int:
    """总分 = Σ（权重% × 维度得分）÷ 100，half-up 整数实现。

    实现：(2×Σ + 100) // 200 即 half-up（÷100 后四舍五入），全程无浮点。
    """
    jiaquan_he = sum(w * d for w, d in zip(quanzhong, defen))
    return (jiaquan_he * 2 + 100) // 200


def _dengji(zongfen: int) -> str:
    """等级五档判定：按阈值降序查表，全部不中 = 严重不合格。"""
    for yuzhi, mingcheng in DENGJI_YUZHI:
        if zongfen >= yuzhi:
            return mingcheng
    return DENGJI_YANZHONG


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def jisuan_bsc(shuru: BscShuru) -> BscJieguo:
    """BSC 四维加权评分（方案B 步骤 5b；纯函数）。

    参数：shuru —— BscShuru（四维达成率 + 可选权重）。

    返回：BscJieguo（四维得分 + 生效权重 + 总分 + 等级）。

    处理顺序：
        ① 校验（类型/达成率形态/权重形态与合计）→ ② 维度得分（half-up，
        不封顶）→ ③ 总分（half-up）→ ④ 等级五档。
    """
    if not isinstance(shuru, BscShuru):
        raise BscCuowu(f'输入必须是 BscShuru：{shuru!r}')

    # ① 达成率校验：非负整数、不超合理性上限（bool 是 int 子类须排除）
    def _jianyan_bps(bps: int, biaoshi: str) -> None:
        if isinstance(bps, bool) or not isinstance(bps, int):
            raise BscCuowu(f'{biaoshi} 必须为整数（基点）：{bps!r}')
        if bps < 0 or bps > ZUIDA_DACHENGLV_BPS:
            raise BscCuowu(f'{biaoshi} 必须在 [0, {ZUIDA_DACHENGLV_BPS}] 内（基点）：{bps}')

    for bps, biaoshi in (
        (shuru.caijing_bps, 'caijing_bps'),
        (shuru.kehu_bps, 'kehu_bps'),
        (shuru.neibu_bps, 'neibu_bps'),
        (shuru.xuexi_bps, 'xuexi_bps'),
    ):
        _jianyan_bps(bps, biaoshi)

    # ① 权重校验：None → 默认配比；否则四项 0~100 整数且合计 = 100
    quanzhong = QUANZHONG_MOREN if shuru.quanzhong is None else shuru.quanzhong
    if not isinstance(quanzhong, tuple) or len(quanzhong) != 4:
        raise BscCuowu(f'quanzhong 必须为四项元组：{quanzhong!r}')
    for w in quanzhong:
        if isinstance(w, bool) or not isinstance(w, int):
            raise BscCuowu(f'权重必须为整数：{w!r}')
        if w < 0 or w > 100:
            raise BscCuowu(f'权重必须在 [0, 100] 内：{w}')
    if sum(quanzhong) != 100:
        raise BscCuowu(f'权重合计必须等于 100：{quanzhong}（合计 {sum(quanzhong)}）')

    # ② 维度得分：half-up(达成率 ÷ 100)；不封顶——>100% 时得分 >100 保留
    defen = (
        _dacheng_bps_defen(shuru.caijing_bps),
        _dacheng_bps_defen(shuru.kehu_bps),
        _dacheng_bps_defen(shuru.neibu_bps),
        _dacheng_bps_defen(shuru.xuexi_bps),
    )

    # ③ 总分 + ④ 等级
    zongfen = _zongfen(defen, quanzhong)
    return BscJieguo(
        caijing_defen=defen[0],
        kehu_defen=defen[1],
        neibu_defen=defen[2],
        xuexi_defen=defen[3],
        quanzhong=quanzhong,
        zongfen=zongfen,
        dengji=_dengji(zongfen),
        caijing_bps=shuru.caijing_bps,
        kehu_bps=shuru.kehu_bps,
        neibu_bps=shuru.neibu_bps,
        xuexi_bps=shuru.xuexi_bps,
    )
