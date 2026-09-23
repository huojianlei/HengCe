# -*- coding: utf-8 -*-
"""滚动预算重算模块 —— 方案B 步骤 2 的确定性核心（定稿 #1：全额替换制）。

命名规范（2026-08-23 用户指令）：本模块所有标识符（变量/函数/类/常量/
字典键）一律用【无声调拼音】，数据值用中文；文件名保持英文（Windows 规范）。

口径依据（权威文件，修改本模块前必读）：
    docs\\textbook\\finagent-算法核对文档-定稿.md  v2.1  §1
    docs\\10-待核对问题定稿摘要.md  #1（队友定稿：全额替换模式）

核心规则（定稿 #1；剩余期链式读法 2026-09-03 队友拍板）：
    1. 已届满周期：用实际经营数据【全额替换】原预算（机械动作，每次数据更新必做，
       与单双环判定无关——判定是步骤 4 的治理决策，见 loop_decision 模块）。
    2. 剩余周期（链法①，2026-09-03 重开 T-23 并拍板）：
       首个剩余期 = 自身年初预算 × (1+g)；此后每期 = 上一期【滚动值】× (1+g)
       逐期接力舍入。注意：不接上一期【实际数】（链法②已否）；
       接力从首个剩余期起，届满期实际数不进接力链。
       背景：Broad Co 例题各期等额，链式与非链式数值恰同，例题无法区分；
       随机数据（fuzz）暴露歧义后原拍非链式（保季节轮廓）——2026-09-03
       队友按教材滚动编制直觉改拍链式①，非等额场景季节轮廓随之淡化为渐近线。
    3. 季度滚动可叠加"行业对标修正系数"（口径 A：增长率差值法，需显式开启；
       口径 B：不修正，为当前默认，与例题一致）。月度滚动【不叠加】行业修正
       （定稿 #1：月度纯企业内部修正）。

数值纪律（docs\\02 架构 ADR / docs\\06 路线 2）：
    - 金额单位 = 「分」的整数（int），全程整数运算，杜绝浮点误差；
      Python int 无上限，但仍保留单期金额上限校验（数据合理性，非溢出防护）。
    - 增长率单位 = 基点 jidian（1% = 100 基点），整数。
    - 乘法舍入：四舍五入（half-up），逐期累进舍入（与例题数字一致）。

使用示例（知识点速览，v0.4 2026-08-23 拼音化；doctest 格式——可直接复制
    到交互环境运行，也可用 `python -m doctest rolling_budget.py` 自动验证，
    并由 tests\\test_demos.py 纳入常规测试守护，示例过时测试即红）：

    知识点 1 · 构造期间金额（QijianJine）——金额一律写"分"
    >>> from rolling_budget import QijianJine
    >>> q1 = QijianJine(qijian='2026-Q1', jine_fen=22_000_000)   # 22 万元
    >>> q1.jine_fen // 100                       # 换回"元"核对
    220000

    知识点 2 · 滚动重算（gengxin_gundong_yusuan）——Broad Co 例题
    >>> from rolling_budget import GunDongShezhi, gengxin_gundong_yusuan
    >>> yusuan = [QijianJine(f'2026-Q{i}', 22_000_000) for i in range(1, 5)]
    >>> shiji = [QijianJine('2026-Q1', 21_000_000)]             # Q1 实际 21 万
    >>> # 季度+增长1%；行业增速同为 1%（差值 0 → 口径A不修正，例题数字保持）
    >>> jg = gengxin_gundong_yusuan(yusuan, shiji,
    ...     GunDongShezhi(zhouqi='季度', zengzhanglv_jidian=100,
    ...                    hangye_zengzhanglv_jidian=100))
    >>> [q.shuzhi_fen for q in jg.qijian_mingxi]     # 逐期滚动值（分）
    [21000000, 22220000, 22442200, 22666622]
    >>> jg.gundong_zonge_fen - jg.chushi_zonge_fen   # 年度差额（分）
    328822

    知识点 3 · 金额展示（fen_zhuan_yuan）——分 → 元字符串（两位小数）
    >>> from rolling_budget import fen_zhuan_yuan
    >>> fen_zhuan_yuan(22_666_622)
    '226666.22'

    知识点 4 · 季度 + 口径 A（行业对标修正：差值达阈值才启用）
    >>> shezhi = GunDongShezhi(zhouqi='季度', zengzhanglv_jidian=100,
    ...     hangye_xiuzheng='A', hangye_zengzhanglv_jidian=50)   # 差值恰达 50 基点阈值
    >>> jg2 = gengxin_gundong_yusuan(yusuan, shiji, shezhi)
    >>> jg2.hangye_xiuzheng_qiyong
    True

拍板记录（2026-08-23 更新，取代原"待定项"）：
    - 【已拍板 T-02】行业对标修正：口径 A（增长率差值法）为【默认】
      （用户拍板 2026-08-23）；口径 B（不修正）仍可显式传参选择。
      注意：季度场景用默认构造时必须提供 hangye_zengzhanglv_jidian
      （行业增长率），否则按脏配置拒绝；月度不受影响。
    - 【已拍板 T-23】剩余期累进基准："各期自身初始预算 × (1+g)^期距"
      ——队友拍板按行业区分（强季节性服务业保轮廓，其他行业用等额预算，
      两读法在等额下等价）；当前实现天然兼容两种场景，不改代码。
    - 【待定 T-22-③】修正增长率来源：演示期取管理员/LLM 外生输入
      （zengzhanglv_jidian 参数），不从历史数据自动推导。

命名对照表（拼音标识符 → 中文含义）：
    QijianJine                期间金额（一行预算/实际数据）
    GunDongShezhi             滚动设置（周期、增长率、行业修正参数）
    DanqiJieguo               单期结果（一个期间的重算明细）
    GunDongJieguo             滚动结果（整体输出）
    GunDongCuowu              滚动错误（校验失败异常）
    gengxin_gundong_yusuan    更新滚动预算（主函数）
    fen_zhuan_yuan            分转元（展示用换算）
    jine_fen / shuzhi_fen     金额分 / 数值分
    zhouqi / zengzhanglv_jidian   周期 / 增长率基点
    hangye_xiuzheng           行业修正（'A' 差值法 / 'B' 不修正）
    qijian / kemu / laiyuan   期间 / 科目 / 来源
    zhuangtai                 状态（'已届满' / '剩余期'）

转写说明：
    本模块为 Python 参考实现（权威）；最终阶段按 TODO 计划逐模块转写为
    TypeScript（plugins\\fin-tools\\），转写时以本文件的测试为准绳。

口径依据与建立：2026-08-22 建立，2026-08-23 v0.4 拼音化 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区
# ======================================================================

#: 单期金额上限（分）= 90 亿元/期。超出视为脏数据直接拒绝（合理性校验，
#: Python int 本身无溢出风险，此上限只为拦截明显的录入错误）。
ZUIDA_JINE_FEN: int = 9 * 10**11

#: 基点换算基数（"万分制"：金额 × (10000 + 基点) / 10000）。
JIDIAN_JISHU: int = 10_000

#: 口径 A 的默认启用阈值（基点）：|企业增长率 - 行业增长率| ≥ 50 基点
#: （0.5 个百分点）才施加行业修正，避免微小差值引发预算抖动（建议值，待会计复核）。
MOREN_HANGYE_YUZHI_JIDIAN: int = 50


# ======================================================================
# 数据结构区（frozen = 不可变，纯函数纪律）
# ======================================================================


@dataclass(frozen=True)
class QijianJine:
    """一个期间的金额记录（预算行或实际行）。

    字段说明：
        qijian:   期间键，月度 '2026-01' / 季度 '2026-Q1'。
                  仅作匹配与透传——本模块【不解析】期间语义，
                  顺序完全以 guding_yusuan 的传入顺序为准。
        jine_fen: 金额，单位分，非负整数，上限 ZUIDA_JINE_FEN。
    """

    qijian: str
    jine_fen: int


@dataclass(frozen=True)
class GunDongShezhi:
    """滚动重算设置。

    字段说明：
        zhouqi:                 滚动周期，'月度' 或 '季度'（定稿 #1 两模式）。
        zengzhanglv_jidian:     最新经营增长率（企业口径），基点，[-10000, 10000]。
                                演示期由管理员/LLM 外生给定（T-22-③）。
        hangye_xiuzheng:        【T-02 已拍板 2026-08-23】行业对标修正口径：
                                'A' = 增长率差值法（默认——用户拍板；仅季度生效，
                                默认构造的季度场景必须给 hangye_zengzhanglv_jidian）；
                                'B' = 不修正（可显式传参选择）。
        hangye_zengzhanglv_jidian: 口径 A 必填：行业平均增长率，基点。
        hangye_yuzhi_jidian:    口径 A 的启用阈值，基点，默认 50。
    """

    zhouqi: str
    zengzhanglv_jidian: int
    hangye_xiuzheng: str = 'A'  # 口径 A 为默认（用户拍板 2026-08-23，T-02）
    hangye_zengzhanglv_jidian: int | None = None
    hangye_yuzhi_jidian: int = MOREN_HANGYE_YUZHI_JIDIAN


@dataclass(frozen=True)
class DanqiJieguo:
    """单期重算结果。

    字段说明：
        qijian:          期间键（同输入）。
        chushi_yusuan_fen: 该期初始预算金额（分）。
        zhuangtai:       '已届满' / '剩余期'。
        shuzhi_fen:      重算后的值（分）：届满期 = 实际数；剩余期 = 累进重算值。
        laiyuan:         '实际'（实际替换）/ '重算'（累进重算）。
    """

    qijian: str
    chushi_yusuan_fen: int
    zhuangtai: str
    shuzhi_fen: int
    laiyuan: str


@dataclass(frozen=True)
class GunDongJieguo:
    """滚动预算整体结果。

    字段说明：
        qijian_mingxi:        逐期结果，顺序与 guding_yusuan 一致。
        chushi_zonge_fen:     初始年度预算总额（分）。
        gundong_zonge_fen:    更新后年度滚动预算总额（分）——核心输出，
                              定稿公式：已届满实际合计 + 剩余修正后预算合计。
        chae_fen:             展示口径差额 = 滚动总额 - 初始总额
                              （正 = 滚动后超出原预算；符号口径见定稿 §0.5）。
        hangye_xiuzheng_qiyong: 行业修正是否实际启用（口径 A 且达阈值）。
    """

    qijian_mingxi: list[DanqiJieguo]
    chushi_zonge_fen: int
    gundong_zonge_fen: int
    chae_fen: int
    hangye_xiuzheng_qiyong: bool


class GunDongCuowu(ValueError):
    """滚动预算输入/设置校验失败。

    语义：调用方（数据导入层或 LLM 工具壳）传入的参数违反口径或数据纪律。
    继承 ValueError 以便上层按"脏数据"统一捕获。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 内部工具函数区
# ======================================================================


def _cheng_jidian(fen: int, jidian: int) -> int:
    """金额乘以 (10000 + 基点) / 10000，四舍五入到分（half-up）。

    实现说明：
        (fen * (JIDIAN_JISHU + jidian) + JIDIAN_JISHU // 2) // JIDIAN_JISHU
        —— 整数地板除天然实现 half-up 舍入（加半法）。
    """
    return (fen * (JIDIAN_JISHU + jidian) + JIDIAN_JISHU // 2) // JIDIAN_JISHU


def _jianyan_jine(shuzhi: int, biaoshi: str) -> None:
    """校验金额字段：非负整数且不超过 ZUIDA_JINE_FEN，否则抛 GunDongCuowu。"""
    # isinstance(bool) 也是 int 的子类，先排除 bool 防止 True/False 混入。
    if isinstance(shuzhi, bool) or not isinstance(shuzhi, int):
        raise GunDongCuowu(f'{biaoshi} 必须为整数（分）：{shuzhi!r}')
    if shuzhi < 0 or shuzhi > ZUIDA_JINE_FEN:
        raise GunDongCuowu(f'{biaoshi} 必须在 [0, {ZUIDA_JINE_FEN}] 内（分）：{shuzhi}')


def _jianyan_jidian(shuzhi: int, biaoshi: str) -> None:
    """校验基点字段：[-10000, 10000] 内的整数（即 ±100% 封顶）。"""
    if isinstance(shuzhi, bool) or not isinstance(shuzhi, int):
        raise GunDongCuowu(f'{biaoshi} 必须为整数（基点）：{shuzhi!r}')
    if shuzhi < -JIDIAN_JISHU or shuzhi > JIDIAN_JISHU:
        raise GunDongCuowu(f'{biaoshi} 必须在 [-10000, 10000] 内（基点）：{shuzhi}')


def _guifanhua_qijian(xiang: object, biaoshi: str, yunxu_wei_kong: bool) -> list[QijianJine]:
    """校验并复制期间序列：结构合法、期间键唯一且非空、金额合法。

    说明：
        返回【复制】而非原列表引用——纯函数纪律，避免调用方后续修改
        影响已传入的数据（frozen dataclass 只保证字段不可变）。
    """
    if not isinstance(xiang, list):
        raise GunDongCuowu(f'{biaoshi} 必须是列表')
    if not xiang:
        if yunxu_wei_kong:
            return []  # 实际数据允许为空（尚未有任何实际数据）
        raise GunDongCuowu(f'{biaoshi} 不能为空')

    yijian: set[str] = set()
    for tiao in xiang:
        if not isinstance(tiao, QijianJine):
            raise GunDongCuowu(f'{biaoshi} 含非法元素（须为 QijianJine）：{tiao!r}')
        if not isinstance(tiao.qijian, str) or not tiao.qijian:
            raise GunDongCuowu(f'{biaoshi} 含非法期间键：{tiao.qijian!r}')
        if tiao.qijian in yijian:
            raise GunDongCuowu(f'{biaoshi} 期间重复：{tiao.qijian}')
        yijian.add(tiao.qijian)
        _jianyan_jine(tiao.jine_fen, f'{biaoshi}[{tiao.qijian}].jine_fen')
    return [QijianJine(t.qijian, t.jine_fen) for t in xiang]


# ======================================================================
# 核心算法区
# ======================================================================


def gengxin_gundong_yusuan(
    guding_yusuan: list[QijianJine],
    shiji_shuju: list[QijianJine],
    shezhi: GunDongShezhi,
) -> GunDongJieguo:
    """滚动预算重算（方案B 步骤 2；纯函数，无副作用、无 I/O）。

    参数：
        guding_yusuan: 年度固定预算（各期），顺序即期间顺序，不可为空。
        shiji_shuju:   已届满期的实际数据，可为空列表；期间必须存在于预算表。
        shezhi:        GunDongShezhi，见其 docstring。

    返回：
        GunDongJieguo（含逐期明细与总额）。

    剩余期算法（链法①，2026-09-03 队友拍板 T-23 重开定案）：
        首个剩余期 = 自身年初预算 × (1+g)；此后每期 = 上一期滚动值 × (1+g)，
        逐期舍入（half-up）接力；届满期实际数不进接力链。
        例题佐证：Broad Co 等额 220,000 → 222,200 / 224,422 / 226,666.22
        （等额下链式与非链式同值，doctest 数字不变）。

    口径 A（仅季度）：
        各剩余期累进结果再乘一次 (1 + (g_corp - g_ind))——定稿公式
        「×行业对标修正系数」的【一次性乘子】解读（非累进复利）；
        该解读方式待会计复核（用户策略：产出数据交会计挑毛病）。
        启用条件：|g_corp - g_ind| >= 阈值（默认 50 基点）。
    """
    # ---- 输入规范化与基础校验 ----
    yusuan = _guifanhua_qijian(guding_yusuan, 'guding_yusuan', yunxu_wei_kong=False)
    shiji_liebiao = _guifanhua_qijian(shiji_shuju, 'shiji_shuju', yunxu_wei_kong=True)

    if not isinstance(shezhi, GunDongShezhi):
        raise GunDongCuowu('shezhi 必须为 GunDongShezhi 实例')
    if shezhi.zhouqi not in ('月度', '季度'):
        raise GunDongCuowu('shezhi.zhouqi 必须为 "月度" 或 "季度"')
    _jianyan_jidian(shezhi.zengzhanglv_jidian, 'shezhi.zengzhanglv_jidian')
    if shezhi.hangye_xiuzheng not in ('A', 'B'):
        raise GunDongCuowu('shezhi.hangye_xiuzheng 必须为 "A" 或 "B"')

    # 实际数据建索引；期间必须存在于预算表（防脏数据错位）
    shiji_suoyin: dict[str, int] = {}
    for tiao in shiji_liebiao:
        if not any(y.qijian == tiao.qijian for y in yusuan):
            raise GunDongCuowu(f'实际数据期间不在预算表中：{tiao.qijian}')
        shiji_suoyin[tiao.qijian] = tiao.jine_fen

    # ---- 口径 A 参数校验与启用判定（仅季度；月度纯企业内部修正——定稿 #1）----
    hangye_yinzi_jidian = 0  # 修正乘子的基点增量；0 = 不修正
    hangye_qiyong = False
    if shezhi.hangye_xiuzheng == 'A' and shezhi.zhouqi == '季度':
        if shezhi.hangye_zengzhanglv_jidian is None:
            raise GunDongCuowu('口径 A 需要提供 hangye_zengzhanglv_jidian')
        _jianyan_jidian(shezhi.hangye_zengzhanglv_jidian, 'shezhi.hangye_zengzhanglv_jidian')
        yuzhi = shezhi.hangye_yuzhi_jidian
        if isinstance(yuzhi, bool) or not isinstance(yuzhi, int) or not (0 <= yuzhi <= JIDIAN_JISHU):
            raise GunDongCuowu('shezhi.hangye_yuzhi_jidian 必须为 [0, 10000] 内整数')
        chazhi = shezhi.zengzhanglv_jidian - shezhi.hangye_zengzhanglv_jidian
        if abs(chazhi) >= yuzhi:  # 达阈值才启用，防微小差值抖动
            hangye_yinzi_jidian = chazhi
            hangye_qiyong = True

    # ---- 逐期重算主循环（链法①：首个剩余期起于自身年初数，此后接力上一期滚动值）----
    qijian_mingxi: list[DanqiJieguo] = []
    qiju = 0  # 期距：距上一个届满期（或序列起点）；届满期后归零重计
    qian_yi_gundong = None  # 上一期滚动值（链法①接力种子；届满期后清空）
    for y in yusuan:
        if y.qijian in shiji_suoyin:
            # 已届满：实际数据全额替换（定稿 #1 机械动作）
            qijian_mingxi.append(
                DanqiJieguo(y.qijian, y.jine_fen, '已届满', shiji_suoyin[y.qijian], '实际')
            )
            qiju = 0  # 重新起算期距
            qian_yi_gundong = None
        else:
            # 剩余期（链法①，2026-09-03 队友拍板，T-23 重开定案）：
            #   首个剩余期 = 自身年初预算 × (1+g)；
            #   之后每期 = 上一期滚动值 × (1+g)，逐期舍入接力。
            qiju += 1
            if qiju == 1 or qian_yi_gundong is None:
                shuzhi = y.jine_fen
            else:
                shuzhi = qian_yi_gundong
            shuzhi = _cheng_jidian(shuzhi, shezhi.zengzhanglv_jidian)
            if hangye_qiyong:
                # 口径 A：一次性乘子，作用在当期滚动结果之上（随接力链自然延续）
                shuzhi = _cheng_jidian(shuzhi, hangye_yinzi_jidian)
            qian_yi_gundong = shuzhi
            qijian_mingxi.append(
                DanqiJieguo(y.qijian, y.jine_fen, '剩余期', shuzhi, '重算')
            )

    # ---- 汇总输出 ----
    chushi_zonge = sum(y.jine_fen for y in yusuan)
    gundong_zonge = sum(q.shuzhi_fen for q in qijian_mingxi)
    return GunDongJieguo(
        qijian_mingxi=qijian_mingxi,
        chushi_zonge_fen=chushi_zonge,
        gundong_zonge_fen=gundong_zonge,
        chae_fen=gundong_zonge - chushi_zonge,
        hangye_xiuzheng_qiyong=hangye_qiyong,
    )


def fen_zhuan_yuan(fen: int) -> str:
    """分 → 元字符串（两位小数），仅供展示层/演示脚本使用。

    纪律：模块间传值一律用整数分；元单位字符串只允许出现在
    面向人的输出（看板/报告/会计复核清单）。
    """
    fuhao = '-' if fen < 0 else ''
    jue_dui = abs(fen)
    return f'{fuhao}{jue_dui // 100}.{jue_dui % 100:02d}'
