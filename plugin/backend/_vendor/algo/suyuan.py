# -*- coding: utf-8 -*-
"""经营变更双维溯源 —— 方案B 步骤 6 的【KPI 变动影响量化】确定性核心（FR-12）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    专有缩写可保留（KPI 等）。

口径依据（权威文件，修改本模块前必读）：
    docs/textbook/finagent-算法核对文档-定稿.md v2.1 §8.3（定稿#10）：
        KPI_Change_Rate =（变更后数值 − 变更前数值）÷ 原始预算数值 × 100%
    docs/proposal-full-extract.txt 行 105~115（完整版 §2.4：分母=原始预算数值；
        财务 9 + 非财务 6 全量覆盖；输出=影响幅度、正向/负向作用、影响占比）
    docs/01-需求说明.md v2.0 §3 FR-12（P1）

模块定位：本模块量化【一个经营变更事件】对 15 项 KPI 的影响——输入是
    "变更前 → 变更后"的 KPI 数值对照（结构化字段，来自变更登记与 KPI 库），
    输出影响率/作用方向/影响占比/TOP3。这是纯计算层：变更事件的【语义判定】
    （是不是结构变更）属 AI 层（loop_decision 注入接口），本模块只算数。

三个口径决策（实现口径，docstring 显式声明）：
    ① 影响率单位 = 整数基点（1% = 100 基点），带符号——正 = 数值上升；
    ② 作用方向 = 15 项 KPI 偏好表判定：'越高越好'（上升=正向作用）与
       '越低越好'（上升=负向作用）；KPI 名不在 15 项清单 → 整行拒绝
       （溯源是结构化流程，KPI 名必须来自 KPI 库，防脏名混入）；
    ③ 影响占比分母 = Σ|各 KPI 净影响率|（影响量占比，正负分列——
       与积木模块 D2 同款口径，占比合计恒 10000 基点）。

缺数纪律：原始预算基准缺失（None）或 ≤ 0 → 该行影响率/占比 None
    （交人工，不臆造），该行不参与占比分母。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；数字例题 = 构造的变更事件"原材料涨价
    + 订单延迟 + 产能提升"，期望值全部手工验算写死）：

    知识点 1 · 变更事件影响量化：影响率/作用方向/占比
    >>> from suyuan import SuyuanHang, jisuan_suyuan
    >>> hang_lie = [
    ...     SuyuanHang('采购成本变动率', 100_000, 108_000, 100_000),
    ...     SuyuanHang('交付周期', 5, 8, 5),
    ...     SuyuanHang('产能利用率', 800, 850, 800),
    ... ]
    >>> jg = jisuan_suyuan(hang_lie)
    >>> [(x.kpi_mingcheng, x.yingxianglv_bps, x.zuoyong) for x in jg.xiang]
    [('采购成本变动率', 800, '负向作用'), ('交付周期', 6000, '负向作用'), ('产能利用率', 625, '正向作用')]
    >>> # 占比分母 = 800+6000+625 = 7425；三行占比合计恒 10000
    >>> sum(x.zhanbi_bps for x in jg.xiang)
    10000

    知识点 2 · TOP3：正向/负向作用各取影响率绝对值前三
    >>> (jg.zhengxiang_top3, jg.fuxiang_top3)
    (['产能利用率'], ['交付周期', '采购成本变动率'])

    知识点 3 · 原始预算基准缺失 → 该行 None（交人工）
    >>> jg2 = jisuan_suyuan([SuyuanHang('交付周期', 5, 8, None)])
    >>> (jg2.xiang[0].yingxianglv_bps, jg2.xiang[0].zhanbi_bps)
    (None, None)

命名对照表（拼音标识符 → 中文含义）：
    SuyuanHang          溯源行（KPI 名 + 变更前/后数值 + 原始预算基准）
    SuyuanXiang         溯源项（影响率/数值方向/作用方向/影响占比）
    SuyuanJieguo        溯源结果（逐项 + 正向/负向 TOP3 + 占比分母）
    SuyuanCuowu         溯源错误（校验失败异常）
    jisuan_suyuan       计算溯源（主函数）
    yingxianglv_bps     影响率（基点，带符号——正=数值上升）
    shuzhi_fangxiang    数值方向（上升/下降/持平）
    zuoyong             作用方向（正向作用/负向作用/无作用）
    zhanbi_bps          影响占比（基点，非负；分母 0 时 None）
    zhengxiang_top3 / fuxiang_top3   正向/负向作用 TOP3（KPI 名列表）
    yingxiang_fenmu_bps 影响占比分母（Σ|净影响率|）

与上下游的关系：
    上游：kpi（15 项 KPI 数值）、data_ingest（经营变更登记——变更前/后
          数值与原始预算基准的取数装配在端到端层做）；
    下游：看板数据接口（溯源分析区：影响排名/正负向 TOP3）、整改数据底座。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区（数据值用中文——KPI 名、偏好、方向枚举）
# ======================================================================

#: 数值方向枚举
FANGXIANG_SHANGSHENG = '上升'
FANGXIANG_XIAJIANG = '下降'
FANGXIANG_CHIPING = '持平'

#: 作用方向枚举
ZUOYONG_ZHENGXIANG = '正向作用'
ZUOYONG_FUXIANG = '负向作用'
ZUOYONG_WU = '无作用'

#: 偏好一：越高越好（数值上升 = 正向作用）
PIANHAO_YUEGAO = '越高越好'
#: 偏好二：越低越好（数值上升 = 负向作用）
PIANHAO_YUEDI = '越低越好'

#: 15 项 KPI 偏好表（定稿 §8 清单；方向语义见模块头口径决策②）：
#: 成本控制率=实际÷预算，越低越好（成本控制得好 <100%）；
#: 费用偏差率/采购变动率越低越好；交付周期/异常事项数越低越好
KPI_PIANHAO = {
    '营收达成率': PIANHAO_YUEGAO,
    '成本控制率': PIANHAO_YUEDI,
    '费用偏差率': PIANHAO_YUEDI,
    '毛利率': PIANHAO_YUEGAO,
    '净利润率': PIANHAO_YUEGAO,
    '销售利润率': PIANHAO_YUEGAO,
    '资产周转率': PIANHAO_YUEGAO,
    '资金周转率': PIANHAO_YUEGAO,
    '采购成本变动率': PIANHAO_YUEDI,
    '供应链履约率': PIANHAO_YUEGAO,
    '产能利用率': PIANHAO_YUEGAO,
    '交付周期': PIANHAO_YUEDI,
    '客户满意度': PIANHAO_YUEGAO,
    '业务完成进度': PIANHAO_YUEGAO,
    '异常事项数量': PIANHAO_YUEDI,
}

#: 影响率计算公式（定稿 #10 口径文本——报告/溯源表逐行展示，T-29#4）
GONGSHI = '影响率 =（变更后数值 − 变更前数值）÷ 原始预算数值 × 100%'
#: 单字段数值上限（分/件/天/次）——防脏数据的合理性校验
ZUIDA_ZHI = 9 * 10**11


class SuyuanCuowu(ValueError):
    """溯源输入校验失败（KPI 名非法 / 字段非法 / 重复行）。

    继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class SuyuanHang:
    """溯源行：一个 KPI 在变更事件前后的数值对照 + 原始预算基准。

    字段说明：
        kpi_mingcheng: KPI 名（必须是 15 项清单之一——来自 KPI 库，防脏名）；
        bianhua_qian:  变更前数值（非负整数；单位随 KPI：分/件/天/次）；
        bianhua_hou:   变更后数值（非负整数）；
        yuan_yusuan:   原始预算基准（定稿 #10 的分母；非负整数；None = 缺数，
                       该行影响率无法计算 → None 交人工）。
    """

    kpi_mingcheng: str
    bianhua_qian: int
    bianhua_hou: int
    yuan_yusuan: int | None = None


@dataclass(frozen=True)
class SuyuanXiang:
    """溯源项：单 KPI 的影响量化结果。

    字段说明：
        kpi_mingcheng:   KPI 名（回显）。
        yingxianglv_bps: 影响率（基点，带符号——正 = 数值上升；
                         原始预算缺失/≤0 时 None）。
        shuzhi_fangxiang: 数值方向（上升/下降/持平）。
        zuoyong:          作用方向（正向作用/负向作用/无作用——偏好表判定）。
        zhanbi_bps:       影响占比（基点，非负；分母 0 时 None）。
    """

    kpi_mingcheng: str
    yingxianglv_bps: int | None
    shuzhi_fangxiang: str
    zuoyong: str
    zhanbi_bps: int | None


@dataclass(frozen=True)
class SuyuanJieguo:
    """溯源结果：逐项影响 + 正负向 TOP3 + 占比分母（看板溯源区数据源）。

    字段说明：
        xiang:               逐项结果（顺序 = 输入顺序）。
        zhengxiang_top3:     正向作用 KPI 名 TOP3（按 |影响率| 降序；并列取先）。
        fuxiang_top3:        负向作用 KPI 名 TOP3（同上）。
        yingxiang_fenmu_bps: 影响占比分母 = Σ|各 KPI 净影响率|（基点）。
    """

    xiang: list[SuyuanXiang]
    zhengxiang_top3: list[str]
    fuxiang_top3: list[str]
    yingxiang_fenmu_bps: int
    gongshi: str = GONGSHI   # 计算公式文本（T-29#4：报告新增【计算公式】列）


# ======================================================================
# 内部工具函数区
# ======================================================================


def _yingxianglv_bps(qian: int, hou: int, yuan: int | None) -> int | None:
    """影响率（基点）=（变更后 − 变更前）÷ 原始预算 × 10000，half-up 带符号。

    原始预算缺失或 ≤ 0 → None（缺数纪律，交人工）；
    实现：(2×|差值|×10000 + 分母) // (2×分母)，符号随差值。
    """
    if yuan is None or yuan <= 0:
        return None
    chae = hou - qian
    bps = (abs(chae) * 10_000 * 2 + yuan) // (2 * yuan)
    return bps if chae >= 0 else -bps


def _zuoyong(kpi_mingcheng: str, chae: int) -> str:
    """作用方向：数值方向 × 偏好表（15 项 KPI 的固定语义）。

    持平（chae=0）→ '无作用'；偏好越高越好 → 上升=正向、下降=负向；
    偏好越低越好 → 上升=负向、下降=正向。
    """
    if chae == 0:
        return ZUOYONG_WU
    pianhao = KPI_PIANHAO[kpi_mingcheng]
    if pianhao == PIANHAO_YUEGAO:
        return ZUOYONG_ZHENGXIANG if chae > 0 else ZUOYONG_FUXIANG
    return ZUOYONG_FUXIANG if chae > 0 else ZUOYONG_ZHENGXIANG


def _top3(xiang_lie: list[SuyuanXiang], zuoyong: str) -> list[str]:
    """按作用方向取 TOP3：|影响率| 降序，并列取输入顺序靠前者。

    影响率为 None 的项不参与排名（无法量化即无法排名，交人工）。
    """
    houxuan = [(x.kpi_mingcheng, abs(x.yingxianglv_bps))
               for x in xiang_lie
               if x.zuoyong == zuoyong and x.yingxianglv_bps is not None]
    # 稳定排序：|影响率| 降序（Python 排序稳定，并列自动保输入顺序）
    houxuan.sort(key=lambda t: t[1], reverse=True)
    return [t[0] for t in houxuan[:3]]


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def jisuan_suyuan(shuru: list[SuyuanHang]) -> SuyuanJieguo:
    """经营变更双维溯源计算（方案B 步骤 6；纯函数）。

    参数：shuru —— 变更事件逐 KPI 行（SuyuanHang 列表，须非空）。

    返回：SuyuanJieguo（逐项影响率/方向/作用/占比 + 正负向 TOP3）。

    处理顺序：
        ① 校验（行类型/KPI 名合法/字段形态/重复键）→ ② 影响率（half-up
        带符号）→ ③ 数值方向与作用方向（偏好表）→ ④ 占比（分母 = Σ|净
        影响率|，同积木 D2）→ ⑤ 正负向 TOP3。
    """
    if not isinstance(shuru, list) or not shuru:
        raise SuyuanCuowu('shuru 必须为非空列表（至少一行溯源输入）')

    # ① 校验 + KPI 名去重键（同一 KPI 只允许一行，防双计）
    yijian: set[str] = set()
    jianyan_hou: list[SuyuanHang] = []
    for tiao in shuru:
        if not isinstance(tiao, SuyuanHang):
            raise SuyuanCuowu(f'输入含非法元素（须为 SuyuanHang）：{tiao!r}')
        if tiao.kpi_mingcheng not in KPI_PIANHAO:
            raise SuyuanCuowu(
                f'KPI 名非法：{tiao.kpi_mingcheng}（必须是 15 项清单之一）')
        if tiao.kpi_mingcheng in yijian:
            raise SuyuanCuowu(f'溯源行重复（KPI）：{tiao.kpi_mingcheng}——防双计')
        yijian.add(tiao.kpi_mingcheng)
        for zhi, biaoshi in ((tiao.bianhua_qian, 'bianhua_qian'),
                             (tiao.bianhua_hou, 'bianhua_hou')):
            if isinstance(zhi, bool) or not isinstance(zhi, int):
                raise SuyuanCuowu(f'{biaoshi} 必须为整数：{zhi!r}')
            if zhi < 0 or zhi > ZUIDA_ZHI:
                raise SuyuanCuowu(f'{biaoshi} 必须在 [0, {ZUIDA_ZHI}] 内：{zhi}')
        if tiao.yuan_yusuan is not None and (
            isinstance(tiao.yuan_yusuan, bool)
            or not isinstance(tiao.yuan_yusuan, int)
            or tiao.yuan_yusuan < 0
            or tiao.yuan_yusuan > ZUIDA_ZHI
        ):
            raise SuyuanCuowu(f'yuan_yusuan 非法：{tiao.yuan_yusuan!r}')
        jianyan_hou.append(tiao)

    # ② 影响率（带符号）+ ③ 数值方向与作用方向（偏好表）
    xiang_lie: list[SuyuanXiang] = []
    for tiao in jianyan_hou:
        chae = tiao.bianhua_hou - tiao.bianhua_qian
        if chae > 0:
            fangxiang = FANGXIANG_SHANGSHENG
        elif chae < 0:
            fangxiang = FANGXIANG_XIAJIANG
        else:
            fangxiang = FANGXIANG_CHIPING
        xiang_lie.append(SuyuanXiang(
            kpi_mingcheng=tiao.kpi_mingcheng,
            yingxianglv_bps=_yingxianglv_bps(tiao.bianhua_qian, tiao.bianhua_hou,
                                             tiao.yuan_yusuan),
            shuzhi_fangxiang=fangxiang,
            zuoyong=_zuoyong(tiao.kpi_mingcheng, chae),
            zhanbi_bps=None,  # 分母算出后回填
        ))

    # ④ 占比分母 = Σ|各 KPI 净影响率|（影响量占比，正负分列——同积木 D2）
    fenmu = sum(abs(x.yingxianglv_bps) for x in xiang_lie
                if x.yingxianglv_bps is not None)

    def _zhanbi(lv: int | None) -> int | None:
        if lv is None or fenmu == 0:
            return None
        return (abs(lv) * 10_000 * 2 + fenmu) // (2 * fenmu)

    xiang_lie = [
        SuyuanXiang(kpi_mingcheng=x.kpi_mingcheng,
                    yingxianglv_bps=x.yingxianglv_bps,
                    shuzhi_fangxiang=x.shuzhi_fangxiang,
                    zuoyong=x.zuoyong,
                    zhanbi_bps=_zhanbi(x.yingxianglv_bps))
        for x in xiang_lie
    ]

    # ⑤ 正负向 TOP3
    return SuyuanJieguo(
        xiang=xiang_lie,
        zhengxiang_top3=_top3(xiang_lie, ZUOYONG_ZHENGXIANG),
        fuxiang_top3=_top3(xiang_lie, ZUOYONG_FUXIANG),
        yingxiang_fenmu_bps=fenmu,
        gongshi=GONGSHI,
    )
