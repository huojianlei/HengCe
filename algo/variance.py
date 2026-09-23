# -*- coding: utf-8 -*-
"""差异计算模块 —— 方案B 步骤 3 的【3a 三重对比 + 3b 预警分级】（确定性核心）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

口径依据（权威文件，修改本模块前必读）：
    docs\\textbook\\finagent-算法核对文档-定稿.md v2.1 §2（含 §0.5 符号口径）
    docs\\10-待核对问题定稿摘要.md  #2（差异率分母）/ #3（预警三档）

三重对比（定稿 §2.3）：每个指标一个期间一行——
    【固定预算】 VS 【滚动/弹性预算】 VS 【实际】
    对比基准 = 滚动预算额（未提供滚动时退化为固定预算额）；
    差异额 = 实际 − 基准（展示口径，§0.5）。

F/A 判定（§0.5 方向规则，系统唯一真源）：
    成本类（含费用/采购）：差额为正 = 超支 = A（不利）；负 = 节约 = F（有利）；
    收入类：差额为正 = 超额 = F（有利）；负 = 未达标 = A（不利）；
    差额为零 = '—'。

差异率（定稿 #2）：差异率 = |差额| ÷ 对比基准额，存整数基点（1% = 100 基点），
    四舍五入 half-up。基准为 0 时差异率无法定义 → None，预警记 '—'
    （【口径说明·待会计复核】除零场景定稿未定义，我们选择交人工而非臆造）。

预警分级（三档体系；2026-09-03 起档位完全可配置——用户接口）：
    【阈值口径变更记录】定稿 #3 原口径 1% → T-29#5 调 5%/10%（2026-08-24）→
    【2026-09-03 用户拍板】15%/30% 分割（低线 15% 黄、高线 30% 红）；
    阈值以模块常量承载——后台配置 = 修改常量（HUANG_YUZHI_BPS/HONG_YUZHI_BPS）。

    默认体系（不传配置时）：
    |差异率| < 15%（1500 基点）        → '无'（数据正常波动）
    15% ≤ |差异率| < 30%（3000 基点） → '黄'（关注，无需强制整改）
    |差异率| ≥ 30%                    → '红'（强制整改 + 风险溯源）

    【用户自定义接口（jisuan_chayi 可选参数）】：
    dang_lie       —— 默认档位序列（全部科目）：每档 YujingDang(名称, 颜色, 阈值基点)，
                      档数不限、阈值不限、颜色不限（含色号）；从阈值最高的档往下匹配。
    kemu_dang_lie  —— 按科目覆盖：{科目名: 档位序列}，做"每科目独立阈值/档数/颜色"。
    兼容性：ChayiXiang.yujing = 档位名称——自定义档名时下游按 '红'/'黄' 字面
    过滤的链路将落空，自定义请保留最高档名 '红'、次档 '黄'，或自行适配下游；
    颜色不受此限（ChayiXiang.yan_se / ChayiJieguo.dang_tongji 随意定制）。

数值纪律：金额 = 整数分；差异率 = 整数基点；全程整数运算，除法仅在
    差异率一步且用 half-up 整数实现（与全项目一致，杜绝浮点）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests\\test_demos.py 守护，示例过时测试即红；数字例题 = 定稿
    v2.1 §2.3 的 E&G Co 弹性预算案例，期望值全部手工验算写死）：

    知识点 1 · 单个成本类指标：差额 / 差异率 / F-A / 预警
    >>> from variance import ChayiShuru, jisuan_chayi
    >>> jg = jisuan_chayi([ChayiShuru('2026-01', '直接材料', '成本类',
    ...     chushi_fen=9_000_000, gundong_fen=10_500_000, shiji_fen=11_000_000)])
    >>> x = jg.xiang[0]
    >>> # 基准=弹性 105,000 元；超支 5,000 元（A 不利）；率 4.76% → 476 基点
    >>> # （< 5% 新阈值 → 无预警；T-29#5 阈值调整后本例降档）
    >>> (x.jizhun_fen, x.chae_fen, x.chalv_bps, x.fa, x.yujing)
    (10500000, 500000, 476, 'A', '无')

    知识点 2 · 收入类方向相反：超额是好事（F）
    >>> jg2 = jisuan_chayi([ChayiShuru('2026-Q1', '营收', '收入类',
    ...     chushi_fen=5_000_000, gundong_fen=5_200_000, shiji_fen=5_350_000)])
    >>> jg2.xiang[0].fa, jg2.xiang[0].yujing
    ('F', '无')

    知识点 3 · 黄色预警：差异率过 15%（E&G 电力行；15%/30% 分割后原红降黄）
    >>> jg3 = jisuan_chayi([ChayiShuru('2026-01', '电力', '成本类',
    ...     chushi_fen=1_500_000, gundong_fen=1_750_000, shiji_fen=1_480_000)])
    >>> # 节约也是 F（有利），但波动 15.43% 过大 → 黄（预警看幅度、F/A 看方向）
    >>> jg3.xiang[0].fa, jg3.xiang[0].yujing, jg3.xiang[0].chalv_bps
    ('F', '黄', 1543)

    知识点 4 · 未提供滚动预算：基准退化为固定预算
    >>> jg4 = jisuan_chayi([ChayiShuru('2026-02', '办公费', '成本类',
    ...     chushi_fen=3_000_000, gundong_fen=None, shiji_fen=3_100_000)])
    >>> jg4.xiang[0].jizhun_fen, jg4.xiang[0].chae_fen
    (3000000, 100000)

    知识点 5 · 自定义档位：三档 + 自定义颜色 + 科目专属阈值（用户接口）
    >>> from variance import YujingDang
    >>> san_dang = (YujingDang('红', '红', 1500),          # ≥15% 红
    ...             YujingDang('橙', '#FF8800', 800),      # ≥8% 橙（色号）
    ...             YujingDang('黄', '黄', 300))           # ≥3% 黄
    >>> ke_mu = {'办公费': (YujingDang('红', '红', 100),)}  # 办公费专属：单档 ≥1% 即红
    >>> jg5 = jisuan_chayi(
    ...     [ChayiShuru('2026-Q1', '办公费', '成本类',
    ...                 chushi_fen=1_000_000, gundong_fen=None, shiji_fen=1_020_000),
    ...      ChayiShuru('2026-Q1', '水电费', '成本类',
    ...                 chushi_fen=1_000_000, gundong_fen=None, shiji_fen=1_010_000)],
    ...     dang_lie=san_dang, kemu_dang_lie=ke_mu)
    >>> # 办公费 +2%（专属单档阈值 1%）→ '红'；水电费 +1%（默认三档 3% 起步）→ '无'
    >>> jg5.xiang[0].yujing, jg5.xiang[0].yan_se
    ('红', '红')
    >>> jg5.xiang[1].yujing
    '无'
    >>> jg5.dang_tongji['红']
    1

命名对照表（拼音标识符 → 中文含义）：
    ChayiShuru        差异输入（一个指标一个期间的一行三数）
    ChayiXiang        差异项（输出：输入 + 基准/差额/差异率/F-A/预警）
    ChayiJieguo       差异结果（全部差异项 + 合计 + 预警计数）
    ChayiCuowu        差异错误（校验失败异常）
    jisuan_chayi      计算差异（主函数）
    chushi_fen        初始预算额（分）——"固定预算"列
    gundong_fen       滚动预算额（分）——"滚动/弹性预算"列，可为 None
    shiji_fen         实际额（分）——"实际"列
    jizhun_fen        基准额（分）= 滚动预算（缺省退化为初始预算）
    chae_fen          差额（分）= 实际 − 基准（展示口径）
    chalv_bps         差异率（基点，非负；基准为 0 时为 None）
    fa                F/A 判定（F 有利 / A 不利 / '—' 零差额）
    yujing            预警（'无' / '黄' / '红' / '—' 无法定级）
    fangxiang         方向（'成本类' / '收入类'——决定 F-A 映射）

与上下游的关系：
    上游：data_ingest（四类归档供数）、rolling_budget（滚动预算额供数）；
    下游：planning_operational（步骤 3c 规划/执行拆分）、看板预警着色。

建立：2026-08-23 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ======================================================================
# 常量区
# ======================================================================

#: 方向一：成本类（含费用、采购——差额为正 = 超支 = 不利 A）
FANGXIANG_CHENGBEN = '成本类'
#: 方向二：收入类（差额为正 = 超额 = 有利 F）
FANGXIANG_SHOURU = '收入类'

#: 合法方向集合（输入行的 fangxiang 必须是其一）
HEFA_FANGXIANG = (FANGXIANG_CHENGBEN, FANGXIANG_SHOURU)

#: 预警档位（定稿 #3 三档 + 无法定级）
YUJING_WU = '无'      # |差异率| < 5%：正常波动
YUJING_HUANG = '黄'   # 5% ≤ |差异率| < 10%：关注
YUJING_HONG = '红'    # |差异率| ≥ 10%：强制整改
YUJING_WUFA = '—'     # 基准为 0 无法定级（交人工，见模块头"口径说明"）

#: 黄色阈值（基点）：|差异率| ≥ 1500（即 15%）进入黄色及以上
#: 【阈值变更记录】定稿 #3 原口径 100 基点（1%）→ T-29#5 调 500 基点（5%）→
#: 【2026-09-03 用户拍板】→ 1500 基点（15%）——三档分割 15%/30% 中的低线；
#: 「支持后台配置」= 修改本常量即可回退/微调（如改回 500 即恢复 T-29#5 口径）
HUANG_YUZHI_BPS = 1500
#: 红色阈值（基点）：|差异率| ≥ 3000（即 30%）进入红色
#: 【2026-09-03 用户拍板】三档分割 15%/30% 中的高线（原 1000 基点/10% 保留版本历史）
HONG_YUZHI_BPS = 3000

#: 单期金额上限（分）——与 rolling_budget 同口径的合理性校验
ZUIDA_JINE_FEN = 9 * 10**11


@dataclass(frozen=True)
class YujingDang:
    """一个预警档位（用户可自定义：名称/颜色/阈值，档数不限）。

    字段：
        ming_cheng: 档位名称——落入本档时 ChayiXiang.yujing 的取值。
                    默认体系 = '红'/'黄'；保留名 '无' 与 '—' 禁用（防计数混淆）。
        yan_se:     颜色——展示层着色用（可中文色名 '橙' 或 '#FF8800' 式色号）。
        yu_fen:     阈值（基点，非负整数）：|差异率| ≥ yu_fen 落入本档。
                    1% = 100 基点。匹配规则：从阈值最高的档往下找第一个达标的。
    """

    ming_cheng: str
    yan_se: str
    yu_fen: int


#: 默认档位（定稿 #3 体系：≥10% 红、≥5% 黄、其余无——不传配置时自动使用，
#: 下游 xishu/zhenggai/kanban 按 '红'/'黄' 档名消费，默认体系下全部兼容）
MOREN_DANG_LIE = (
    YujingDang(ming_cheng=YUJING_HONG, yan_se='红', yu_fen=HONG_YUZHI_BPS),
    YujingDang(ming_cheng=YUJING_HUANG, yan_se='黄', yu_fen=HUANG_YUZHI_BPS),
)


class ChayiCuowu(ValueError):
    """差异计算输入校验失败（方向非法 / 金额非法 / 结构非法）。

    继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class ChayiShuru:
    """差异输入：一个指标在一个期间的三数（固定预算 / 滚动预算 / 实际）。

    字段说明：
        qijian:      期间键（2026-01 / 2026-Q1；透传，本模块不解析语义）。
        kemu:        指标科目名（营收、直接材料、电力……）。
        fangxiang:   方向（'成本类' / '收入类'）——决定 F-A 映射方向。
        chushi_fen:  初始（固定）预算额，非负整数分。
        gundong_fen: 滚动/弹性预算额；None = 未提供（基准退化用初始预算）。
        shiji_fen:   实际发生额，非负整数分。
    """

    qijian: str
    kemu: str
    fangxiang: str
    chushi_fen: int
    gundong_fen: int | None
    shiji_fen: int


@dataclass(frozen=True)
class ChayiXiang:
    """差异项输出：输入三数 + 五项计算结果（一个指标一个期间一行）。"""

    qijian: str
    kemu: str
    fangxiang: str
    chushi_fen: int           # 初始预算额（分）——三重对比第一列
    gundong_fen: int | None   # 滚动预算额（分）——第二列（None 同固定）
    shiji_fen: int            # 实际额（分）——第三列
    jizhun_fen: int           # 基准额（分）= 滚动（缺省退化初始）
    chae_fen: int             # 差额（分）= 实际 − 基准（展示口径）
    chalv_bps: int | None     # 差异率（基点，非负；基准 0 → None）
    fa: str                   # 'F' 有利 / 'A' 不利 / '—' 零差额
    yujing: str               # 档位名称（默认体系 '无'/'黄'/'红'/'—'；自定义档 = 用户命名）
    yan_se: str = ''          # 本档颜色（自定义档位的展示层着色；'无'/'—' 为空）


@dataclass(frozen=True)
class ChayiJieguo:
    """差异结果：全部差异项 + 合计差额 + 预警计数（看板/报告用）。

    字段说明：
        xiang:        逐项差异（顺序与输入一致）。
        heji_chae_fen: 合计差额 = Σ差额（展示口径）。
        heji_fa:      合计判定——全部行同方向时按该方向判 F/A，
                      方向混合或零差额时 '—'（合计的意义见口径说明）。
        hong_shu / huang_shu / wu_shu / wufa_shu: 四档预警计数。
    """

    xiang: list[ChayiXiang]
    heji_chae_fen: int
    heji_fa: str
    hong_shu: int
    huang_shu: int
    wu_shu: int
    wufa_shu: int
    dang_tongji: dict = field(default_factory=dict, compare=False)
    # 档名 → 行数（含'无'/'—'）——自定义档位时的通用计数（hong/huang_shu 只认
    # 默认档名，自定义档名时请读本字段；compare=False：计数可由 xiang 推出）


# ======================================================================
# 内部工具函数区
# ======================================================================


def _jianyan_jine(shuzhi: int, biaoshi: str) -> None:
    """金额校验：非负整数且不超上限（bool 排除——True 也是 int 子类）。"""
    if isinstance(shuzhi, bool) or not isinstance(shuzhi, int):
        raise ChayiCuowu(f'{biaoshi} 必须为整数（分）：{shuzhi!r}')
    if shuzhi < 0 or shuzhi > ZUIDA_JINE_FEN:
        raise ChayiCuowu(f'{biaoshi} 必须在 [0, {ZUIDA_JINE_FEN}] 内（分）：{shuzhi}')


def _jisuan_chalv(chae_fen: int, jizhun_fen: int) -> int | None:
    """差异率（基点）= |差额|/基准 × 10000，half-up 整数实现。

    基准为 0 → None（无法定义；预警将记 '—' 交人工——见模块头口径说明）。
    实现说明：(a*10000 + j//2) // j 即整数 half-up，全程无浮点。
    """
    if jizhun_fen == 0:
        return None
    return (abs(chae_fen) * 10_000 + jizhun_fen // 2) // jizhun_fen


def _pan_fa(chae_fen: int, fangxiang: str) -> str:
    """按方向判 F/A：成本类正差=超支 A、收入类正差=超额 F；零差 '—'。"""
    if chae_fen == 0:
        return '—'
    if fangxiang == FANGXIANG_CHENGBEN:
        return 'A' if chae_fen > 0 else 'F'  # 成本：正=超支(不利)
    return 'F' if chae_fen > 0 else 'A'      # 收入：正=超额(有利)


def _pei_dang(chalv_bps: int | None, dang_lie: tuple[YujingDang, ...]) -> tuple[str, str]:
    """按档位序列定级：从阈值最高的档往下找第一个达标的，返回（档名, 颜色）。

    |差异率| ≥ 档阈值即落入；全部不达 → ('无', '')；无法定级 → ('—', '')。
    调用方保证 dang_lie 已通过 _jianyan_dang_lie 校验（阈值非负、档名合法）。
    """
    if chalv_bps is None:
        return YUJING_WUFA, ''
    for dang in sorted(dang_lie, key=lambda d: d.yu_fen, reverse=True):
        if chalv_bps >= dang.yu_fen:
            return dang.ming_cheng, dang.yan_se
    return YUJING_WU, ''


def _pan_yujing(chalv_bps: int | None) -> str:
    """默认体系的预警档名（向后兼容的薄壳——等价于默认档位下的 _pei_dang）。"""
    return _pei_dang(chalv_bps, MOREN_DANG_LIE)[0]


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def _jianyan_dang_lie(dang_lie, can_ming: str) -> tuple[YujingDang, ...]:
    """校验一份档位配置（结构/阈值/档名），返回规整后的元组。"""
    if isinstance(dang_lie, YujingDang):
        dang_lie = (dang_lie,)
    try:
        lie = tuple(dang_lie)
    except TypeError:
        raise ChayiCuowu(f'{can_ming} 必须为 YujingDang 序列') from None
    if not lie:
        raise ChayiCuowu(f'{can_ming} 不能为空（至少一个档位；不想预警请把阈值设为极高）')
    ming_ji: set[str] = set()
    for dang in lie:
        if not isinstance(dang, YujingDang):
            raise ChayiCuowu(f'{can_ming} 含非法元素（须为 YujingDang）：{dang!r}')
        if not dang.ming_cheng or not dang.ming_cheng.strip():
            raise ChayiCuowu(f'{can_ming} 存在空档名')
        if dang.ming_cheng in (YUJING_WU, YUJING_WUFA):
            raise ChayiCuowu(f"{can_ming} 档名 '{dang.ming_cheng}' 为保留名（不可用作自定义档名）")
        if dang.ming_cheng in ming_ji:
            raise ChayiCuowu(f'{can_ming} 档名重复：{dang.ming_cheng}')
        ming_ji.add(dang.ming_cheng)
        if isinstance(dang.yu_fen, bool) or not isinstance(dang.yu_fen, int) or dang.yu_fen < 0:
            raise ChayiCuowu(f'{can_ming} 档 \'{dang.ming_cheng}\' 阈值必须为非负整数基点')
        if not dang.yan_se:
            raise ChayiCuowu(f'{can_ming} 档 \'{dang.ming_cheng}\' 颜色为空（可填与档名相同的中文色）')
    return lie


def jisuan_chayi(
    shuru: list[ChayiShuru],
    dang_lie: tuple[YujingDang, ...] = MOREN_DANG_LIE,
    kemu_dang_lie: dict[str, tuple[YujingDang, ...]] | None = None,
) -> ChayiJieguo:
    """三重对比差异计算 + 预警分级（方案B 步骤 3a/3b；纯函数）。

    参数：shuru —— 每个指标每个期间一行 ChayiShuru（重复的
          （期间, 科目）组合会被拒绝——防双计）。
          dang_lie —— 默认预警档位（全部科目生效；缺省 = 定稿 #3 体系
          '红'≥10% / '黄'≥5%）。每档 = YujingDang(名称, 颜色, 阈值基点)，
          档数不限、阈值大小不限——用户自定义接口。
          kemu_dang_lie —— 按科目覆盖档位：{科目名: 档位序列}；未覆盖的
          科目用 dang_lie。科目专属阈值/档数/颜色（如办公费设三档）在此配。

    返回：ChayiJieguo（逐项 + 合计 + 预警计数 + 全档计数 dang_tongji）。

    兼容性注意（下游消费方必读）：ChayiXiang.yujing = 档位名称。自定义档名时
    下游按 '红'/'黄' 字面过滤的链路（xishu 系数包 / zhenggai 分级 / kanban）
    将匹配不到——自定义请保留最高档名为 '红'、次档为 '黄'，或自行适配下游。

    计算规则（口径全部见模块头 docstring，此处只列顺序）：
        ① 校验（输入 + 档位配置） → ② 定基准（滚动优先，缺省退化初始） →
        ③ 差额（实际−基准） → ④ 差异率（half-up 基点） →
        ⑤ F/A（按方向） → ⑥ 预警（按科目档位，从高到低匹配） → ⑦ 合计与计数。
    """
    if not isinstance(shuru, list) or not shuru:
        raise ChayiCuowu('shuru 必须为非空列表（至少一行差异输入）')
    mo_ren = _jianyan_dang_lie(dang_lie, 'dang_lie')
    kemu_dang: dict[str, tuple[YujingDang, ...]] = {}
    if kemu_dang_lie:
        if not isinstance(kemu_dang_lie, dict):
            raise ChayiCuowu('kemu_dang_lie 必须为 {科目名: 档位序列} 字典')
        for kemu, lie in kemu_dang_lie.items():
            kemu_dang[kemu] = _jianyan_dang_lie(lie, f'kemu_dang_lie[{kemu}]')

    yijian: set[tuple[str, str]] = set()  # （期间, 科目）去重键
    xiang_lie: list[ChayiXiang] = []
    for tiao in shuru:
        if not isinstance(tiao, ChayiShuru):
            raise ChayiCuowu(f'输入含非法元素（须为 ChayiShuru）：{tiao!r}')
        if not tiao.qijian or not tiao.kemu:
            raise ChayiCuowu('期间与科目必须非空')
        if tiao.fangxiang not in HEFA_FANGXIANG:
            raise ChayiCuowu(f'方向非法：{tiao.fangxiang}（应为 {list(HEFA_FANGXIANG)}）')
        _jianyan_jine(tiao.chushi_fen, 'chushi_fen')
        _jianyan_jine(tiao.shiji_fen, 'shiji_fen')
        if tiao.gundong_fen is not None:
            _jianyan_jine(tiao.gundong_fen, 'gundong_fen')
        # （期间, 科目）唯一：同一指标同一期间只允许一行，防双计
        jian = (tiao.qijian, tiao.kemu)
        if jian in yijian:
            raise ChayiCuowu(f'差异输入重复（期间+科目）：{jian}')
        yijian.add(jian)

        # ② 基准：滚动预算优先；None → 退化初始（固定）预算
        jizhun = tiao.gundong_fen if tiao.gundong_fen is not None else tiao.chushi_fen
        chae = tiao.shiji_fen - jizhun          # ③ 差额（展示口径）
        chalv = _jisuan_chalv(chae, jizhun)     # ④ 差异率（基点）
        ben_ke_mu_dang = kemu_dang.get(tiao.kemu, mo_ren)   # ⑥ 科目专属档位优先
        yujing, yan_se = _pei_dang(chalv, ben_ke_mu_dang)
        xiang_lie.append(
            ChayiXiang(
                qijian=tiao.qijian, kemu=tiao.kemu, fangxiang=tiao.fangxiang,
                chushi_fen=tiao.chushi_fen, gundong_fen=tiao.gundong_fen,
                shiji_fen=tiao.shiji_fen, jizhun_fen=jizhun, chae_fen=chae,
                chalv_bps=chalv, fa=_pan_fa(chae, tiao.fangxiang),
                yujing=yujing, yan_se=yan_se,
            )
        )

    # ⑦ 合计差额与合计判定（方向全部一致才有合计 F/A 意义）
    heji_chae = sum(x.chae_fen for x in xiang_lie)
    fangxiang_ji = {x.fangxiang for x in xiang_lie}
    if len(fangxiang_ji) == 1:
        heji_fa = _pan_fa(heji_chae, fangxiang_ji.pop())
    else:
        heji_fa = '—'  # 成本/收入混算的合计 F/A 无意义，交人看明细

    return ChayiJieguo(
        xiang=xiang_lie,
        heji_chae_fen=heji_chae,
        heji_fa=heji_fa,
        hong_shu=sum(1 for x in xiang_lie if x.yujing == YUJING_HONG),
        huang_shu=sum(1 for x in xiang_lie if x.yujing == YUJING_HUANG),
        wu_shu=sum(1 for x in xiang_lie if x.yujing == YUJING_WU),
        wufa_shu=sum(1 for x in xiang_lie if x.yujing == YUJING_WUFA),
        dang_tongji={ming: sum(1 for x in xiang_lie if x.yujing == ming)
                     for ming in {x.yujing for x in xiang_lie}},
    )
