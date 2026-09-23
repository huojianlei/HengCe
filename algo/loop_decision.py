# -*- coding: utf-8 -*-
"""单双环判定模块 —— 方案B 步骤 4（治理决策：是否修订预算方案本身）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

口径依据（权威文件，修改本模块前必读）：
    docs\\textbook\\finagent-算法核对文档-定稿.md v2.1 §4（判定表五情形，
    E5/E6/E7 的修复设计）+ §9 八步流程（判定位置=差异计算之后、双模型分析之前）
    docs\\10-待核对问题定稿摘要.md  #5（Gate-0 噪声门 1%）
    TODO T-22⑨（LLM 不可用时判定降级纯规则——本模块默认即纯规则）
    TODO T-25（Environment_Change 产生机制挂起中——本模块以"结构变更登记"
            布尔为确定性入口，人工标签/混合案均兼容，拍板后无需改判定逻辑）

概念正位（§4.1，防 E5 复发）：
    单环 = 预算假设不动，修正经营执行行为（费用超支、销量未达……可控）；
    双环 = 结构条件已变（换供应商、市场剧变、产能迭代……不可控），
           修订预算假设与指标本身，须人工审批后于下一周期回到步骤 2 重算；
    滚动重算（步骤 2）是计算机制，不是双环——本模块只做治理判定。

判定流程（§4.3）：
    Gate-0：|Diff_Rate| ≥ 默认门限 25%（2500 基点，2026-09-04 用户拍板；
    原定稿 #5 = 1% 留痕）？——否 → 不触发（噪声）
      ↓ 是
    归因：规划/执行拆分线索 × 结构变更登记 ×（可选）LLM 语义归类
      ↓
    查 §4.4 判定表五情形 → 输出判定 + 纠错指令（先于步骤 5 双模型分析）

判定表（§4.4，情形编号与定稿一致，测试据此回归）：
    情形 1：差异率 < 1% 且无结构变更登记            → 不触发
    情形 2：≥1%，执行差异显著，无结构变更            → 单环
    情形 3：≥1%，规划差异显著且有结构变更登记        → 双环（必人工审批）
    情形 4：执行与规划差异均显著（混合）             → 混合纠错模式（必人工审批）
    【命名说明（2026-08-24 应用队友意见 T-29#3）】：情形 4 原名「双轨」
    更名为「混合纠错模式」——业务规则：结构性变更与显著执行偏差同时
    发生时，双环流程优先（预算修订案需人工审批），同步下发单环行为
    整改，本周期不修改预算基准。
    情形 5：<1% 但有结构变更登记                     → 复核提示（建议口径，
                                                      随 T-05 请队友确认）

【建议默认值·显式标注】（定稿留白处的工程默认，拍板即改参数不改结构）：
    a) "显著"量化口径：|规划总差异| 或 |执行总差异| ÷ 原标准成本额 ≥ 2500 基点
       （【2026-09-04 拍板】与门限同为 25%；原建议 100 基点留痕，分母缺省/
       为 0 时退化为"非零即显著"）；
    b) 规划差异显著但无变更登记 → 仍判单环，备注提示"规划差异显著但无
       变更登记，建议补录后复判"（定稿情形 2/3 之间的未定义带）；
    c) 差异率无法定级（基准为 0，variance 产出 None）→ 不触发 + 备注
       交人工（与 variance 模块"除零交人工"的诚实口径一致）；
    d) 拆分线索缺失（规划/执行总量为 None）→ 退化按"执行偏差假设"走单环。

LLM 角色边界（§4.4 + 护栏 FR-8，硬约束）：
    金额、差异、拆分、判定全部来自确定性计算；LLM 仅对变更描述文本做
    语义归类（'结构变动'/'执行偏差'/'无法判断'），且归类结果只能把
    单环【升级为复核提示】（疑似结构变动，交人工确认），绝不直接触发
    双环——双环必须人工审批。函数通过参数注入（Callable），不联网，
    缺省 None 即纯规则模式（T-22⑨ 降级路径，零外部依赖）。

数值纪律：金额 = 整数分；差异率/显著性 = 整数基点（1% = 100 基点）；
    本模块无除法舍入（比率仅做整数比较，分母为 0 走退化分支）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests\\test_demos.py 守护，示例过时测试即红；数字例题 = 定稿
    v2.1 §3 的 Holmes Ltd 案例（原标准成本 1,400×7×$4 = $39,200，
    规划总 +$3,360 / 执行总 −$1,060，整体差异率 587 基点），期望值
    全部手工验算写死，金额乘 100 转分）：

    知识点 1 · 情形 1：差异率不足默认门限 25%（噪声门拦截），无变更登记
    >>> from loop_decision import PanDuanShuru, panduan_huanlu
    >>> jg = panduan_huanlu(PanDuanShuru(chalv_bps=50))
    >>> (jg.qingxing, jg.panduan)
    (1, '不触发')

    知识点 2 · 情形 2：差异率过门 + 执行差异显著 + 无结构变更 → 单环
    >>> # Holmes 整体差异率 587 基点（5.87%）低于默认门限 25%——
    >>> # 演示自定义门限注入口（沿用原定稿 100 基点口径，例题数字不变）
    >>> jg2 = panduan_huanlu(PanDuanShuru(chalv_bps=587,
    ...     guihua_zong_fen=0, zhixing_zong_fen=2_300_000,
    ...     yuandan_cbf_fen=39_200_000, jie_gou_biangeng=False), menjian_bps=100, xianzhu_bps=100)
    >>> jg2.panduan
    '单环'
    >>> # 执行整改指令已生成（预算方案不动）
    >>> jg2.jiuzheng[:4]
    '输出行为'

    知识点 3 · 情形 4：Holmes 拆分下规划/执行均显著 + 有变更登记 → 混合纠错模式
    >>> # 规划 3,360/39,200 = 857 基点 ≥ 100（注入值）显著；执行 270 基点同判显著
    >>> jg3 = panduan_huanlu(PanDuanShuru(chalv_bps=587,
    ...     guihua_zong_fen=3_360_000, zhixing_zong_fen=-1_060_000,
    ...     yuandan_cbf_fen=39_200_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
    >>> (jg3.panduan, jg3.shenpi)
    ('混合纠错模式', True)

    知识点 4 · 情形 3：规划显著、执行不显著、有变更登记 → 双环（必审）
    >>> jg4 = panduan_huanlu(PanDuanShuru(chalv_bps=300,
    ...     guihua_zong_fen=2_000_000, zhixing_zong_fen=100_000,
    ...     yuandan_cbf_fen=39_200_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
    >>> jg4.panduan
    '双环'
    >>> jg4.jiuzheng[:4]
    '生成预算'

    知识点 5 · 情形 5：差异率低于门限但有结构变更登记 → 复核提示
    >>> jg5 = panduan_huanlu(PanDuanShuru(chalv_bps=80, jie_gou_biangeng=True))
    >>> jg5.panduan
    '复核提示'

    知识点 6 · LLM 语义归类（注入假函数，离线）：疑似结构变动 → 升级复核
    >>> jiaren = lambda wenben: '结构变动'   # 假 LLM：文本读出结构变动
    >>> jg6 = panduan_huanlu(PanDuanShuru(chalv_bps=587,
    ...     zhixing_zong_fen=2_300_000, yuandan_cbf_fen=39_200_000,
    ...     jie_gou_biangeng=False, bianma='永久更换核心供应商',
    ...     yuyi_guilei=jiaren), menjian_bps=100, xianzhu_bps=100)
    >>> jg6.panduan
    '复核提示'
    >>> # LLM 只能提示、不能直接触发双环（护栏 FR-8；T-25 拍板前的保守设计）

    知识点 7 · 默认门限 25% 下的过门示例（2026-09-04 拍板的新默认）
    >>> jg7 = panduan_huanlu(PanDuanShuru(chalv_bps=3000,
    ...     guihua_zong_fen=0, zhixing_zong_fen=2_300_000,
    ...     yuandan_cbf_fen=39_200_000, jie_gou_biangeng=False))
    >>> jg7.panduan
    '单环'
    >>> jg7.yiju['门检基点']
    2500

命名对照表（拼音标识符 → 中文含义）：
    PanDuanShuru       判定输入（差异率 + 拆分线索 + 变更登记 + 文本 + LLM 函数）
    PanDuanJieguo      判定结果（情形编号 + 判定 + 纠错动作 + 依据 + 审批标志 + 备注）
    PanDuanCuowu       判定错误（校验失败异常）
    panduan_huanlu     判定环路（主函数：Gate-0 → 归因 → 查判定表）
    chalv_bps          差异率（基点，来自 variance；None = 无法定级）
    guihua_zong_fen    规划总差异（分，来自 planning_operational；None = 缺失）
    zhixing_zong_fen   执行总差异（分，来自 planning_operational；None = 缺失）
    yuandan_cbf_fen    原标准成本额（分，显著性分母；None/0 → 非零即显著）
    jie_gou_biangeng   结构变更登记（布尔；对应 Change_Factor ≠ 0 /
                        is_structural_change=true——T-24 字段拍板后的落地入口）
    bianma             变更（描述文本，喂给 LLM 语义归类；可空）
    yuyi_guilei        语义归类（LLM 函数：文本 → '结构变动'/'执行偏差'/'无法判断'）
    qingxing           情形（编号 1~5，与定稿 §4.4 判定表行号一致）
    panduan            判定（'不触发'/'单环'/'双环'/'混合纠错模式'/'复核提示'
                        即方案 B 输出变量 Loop_Decision 的取值域）
    jiuzheng           纠正（纠错动作指令文本，先于步骤 5 双模型分析输出）
    yiju               依据（归因明细：Gate-0/规划显著/执行显著/登记/归类）
    shenpi             审批（布尔——双环/混合纠错模式必审，本模块只标必审项）
    beizhu             备注（建议默认口径与留白边界的诚实声明）
    MENJIAN_BPS        门检基点（Gate-0 噪声门默认 = 2500 基点 = 25%，
                       2026-09-04 拍板；自定义经 panduan_huanlu 注入）
    XIANZHU_BPS        显著基点（分量显著阈值默认 = 2500 基点 = 25%，
                       2026-09-04 拍板；自定义经 panduan_huanlu 注入）

与上下游的关系：
    上游：variance（步骤 3a 差异率基点）、planning_operational（步骤 3c
          规划/执行总差异）、data_ingest（经营变更登记——T-24 字段扩展后
          由 is_structural_change 直接供给 jie_gou_biangeng）、M5 层
          （LLM 语义归类函数经 yuyi_guilei 注入）；
    下游：步骤 5 双模型分析（积木/BSC，判定与纠错指令先行输出）、
          步骤 8 整改方案（双环修订案随其提交人工审批）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ======================================================================
# 常量区（口径参数集中，拍板改这里不改逻辑）
# ======================================================================

#: Gate-0 噪声门（【2026-09-04 用户拍板】默认 2500 基点 = 25%；
#: 原定稿 #5 = 100 基点（1%）留痕——自定义经 panduan_huanlu(menjian_bps=) 注入）
MENJIAN_BPS: int = 2500

#: 分量显著阈值（【2026-09-04 用户拍板】默认 2500 基点 = 25%，两口并存可注入；
#: 原建议默认 100 基点（1%）留痕——定稿 §4.4 只写"显著"未量化）
XIANZHU_BPS: int = 2500

#: LLM 语义归类的合法返回值（注入函数必须落在其中之一，否则按'无法判断'处理）
GUILEI_HEFA: tuple[str, ...] = ('结构变动', '执行偏差', '无法判断')


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class PanDuanShuru:
    """单双环判定的一路输入（一个指标 × 一个期间的归因快照）。

    字段来源（谁生产谁负责，本模块只消费不重算——金额与拆分
    全部来自上游确定性计算，满足 §4.4 "LLM 角色边界"硬约束）：
        chalv_bps        ← variance.ChayiXiang.chalv_bps
        guihua_zong_fen  ← planning_operational.Jieguo.guihua_zong_fen
        zhixing_zong_fen ← planning_operational.Jieguo.zhixing_zong_fen
        yuandan_cbf_fen  ← 产量 × 标准用量 × 标准单价（分）
        jie_gou_biangeng ← data_ingest 经营变更登记（T-24 后 = is_structural_change）
        bianma / yuyi_guilei ← M5 层语义归类（可选，缺省纯规则）
    """

    chalv_bps: int | None                 # 差异率（基点）；None = 基准为 0 无法定级
    guihua_zong_fen: int | None = None    # 规划总差异（分）；None = 拆分线索缺失
    zhixing_zong_fen: int | None = None   # 执行总差异（分）；None = 拆分线索缺失
    yuandan_cbf_fen: int | None = None    # 原标准成本额（分）；显著性分母
    jie_gou_biangeng: bool = False        # 结构变更登记（Change_Factor ≠ 0）
    bianma: str = ''                      # 变更事项描述文本（喂 LLM 归类；可空）
    yuyi_guilei: object = None            # LLM 语义归类函数（Callable 或 None）


@dataclass(frozen=True)
class PanDuanJieguo:
    """单双环判定的输出（判定 + 纠错指令 + 依据 + 审批标志 + 备注）。

    panduan 即方案 B 输出变量 Loop_Decision 的取值（'不触发'/'单环'/
    '双环'/'混合纠错模式'/'复核提示'——'混合纠错模式'（原名双轨，T-29#3 更名）与'复核提示'为 v2.1 对混合与
    边界情形的补齐，见定稿 §4.4 表）。
    """

    qingxing: int                     # 情形编号（1~5，定稿 §4.4 行号）
    panduan: str                      # 判定（Loop_Decision 取值）
    jiuzheng: str                     # 纠错动作指令（输出给步骤 5/8）
    yiju: dict = field(default_factory=dict)   # 依据明细（归因线索快照）
    shenpi: bool = False              # 是否必须人工审批（双环/混合纠错模式 True）
    beizhu: str = ''                  # 备注（建议默认口径 / 留白边界声明）


class PanDuanCuowu(ValueError):
    """判定输入校验失败（差率为负数、归类函数返回非法值等）。"""


# ======================================================================
# 内部工具函数区
# ======================================================================


def _jueding_xianzhu(fen: int | None, yuandan_fen: int | None,
                     xianzhu_bps: int | None = None) -> bool | None:
    """判断单个分量（规划或执行总差异）是否【显著】。

    口径（【建议默认值】定稿未量化"显著"）：
        分母可用：|分量| ÷ 原标准成本额 ≥ 显著阈值基点（缺省 XIANZHU_BPS，可注入）；
        分母缺失或为 0：退化为"非零即显著"（保守——宁报不漏）；
        分量本身缺失（None）：返回 None（线索缺失，不参与归因）。
    只做整数乘法比较（|分量| × 10000 ≥ 阈值基点 × 分母），零除法零舍入。
    """
    if fen is None:
        return None                     # 拆分线索缺失——留给调用方走退化分支
    if not yuandan_fen:
        # 分母缺失/为 0：非零即显著（退化口径，备注里向用户声明）
        return fen != 0
    # 整数比较：|分量|/分母 ≥ 阈值/10000  ⇔  |分量|×10000 ≥ 阈值基点×分母
    xian = XIANZHU_BPS if xianzhu_bps is None else xianzhu_bps
    return abs(fen) * 10_000 >= xian * yuandan_fen


def _diaoyong_guilei(shuru: PanDuanShuru) -> str:
    """安全调用 LLM 语义归类函数（若注入），任何异常都降级为'无法判断'。

    降级依据 T-22⑨（LLM 不可用时判定降级纯规则）——归类函数抛错、
    返回非法值、根本没注入，一律视同"没有这条线索"，绝不中断判定。
    """
    if shuru.yuyi_guilei is None or not shuru.bianma.strip():
        return '无法判断'               # 没有函数或没有文本——无线索可归类
    try:
        jieguo = shuru.yuyi_guilei(shuru.bianma)
    except Exception:                   # noqa: BLE001  LLM 故障=降级，不是崩溃
        return '无法判断'
    # 返回值不在合法枚举里（幻觉/跑题）→ 同样按无法判断处理
    return jieguo if jieguo in GUILEI_HEFA else '无法判断'


def _jiaoyan(shuru: PanDuanShuru) -> None:
    """输入校验（失败抛 PanDuanCuowu）——防御性入口，纯函数纪律的一部分。"""
    # 差异率是"率"，不允许负数（variance 产出的就是非负基点）
    if shuru.chalv_bps is not None and shuru.chalv_bps < 0:
        raise PanDuanCuowu(f'差异率基点不能为负数：{shuru.chalv_bps}')
    # 原标准成本额是"额"，非负（0 合法——触发退化口径）
    if shuru.yuandan_cbf_fen is not None and shuru.yuandan_cbf_fen < 0:
        raise PanDuanCuowu(f'原标准成本额不能为负数：{shuru.yuandan_cbf_fen}')


# ======================================================================
# 主函数区
# ======================================================================


def panduan_huanlu(shuru: PanDuanShuru, *, menjian_bps: int | None = None,
                   xianzhu_bps: int | None = None) -> PanDuanJieguo:
    """单双环判定主函数：Gate-0 噪声门 → 归因 → 查 §4.4 判定表。

    menjian_bps：自定义门限注入口（基点）；None = 默认 MENJIAN_BPS（25%）。
    xianzhu_bps：自定义显著阈值注入口（基点）；None = 默认 XIANZHU_BPS（25%）。
    演示/复核需沿用原定稿 1% 口径时两个口都传 100——默认与自定义两口并存。

    确定性保证：同样的输入永远得到同样的输出（无随机、无 I/O、
    无全局状态）；LLM 只经注入函数影响"复核提示"这一条保守出口。
    """
    _jiaoyan(shuru)
    # 自定义注入口（门限/显著阈值）：None=默认；阈值是下限，负数非法
    men = MENJIAN_BPS if menjian_bps is None else menjian_bps
    xian = XIANZHU_BPS if xianzhu_bps is None else xianzhu_bps
    if men < 0 or xian < 0:
        raise PanDuanCuowu(f'自定义门限/显著阈值不能为负：{menjian_bps} / {xianzhu_bps}')

    # ---- 第一步：归因线索快照（先算全，判定表只查不算）----
    guihua_xianzhu = _jueding_xianzhu(shuru.guihua_zong_fen, shuru.yuandan_cbf_fen,
                                      xianzhu_bps=xian)
    zhixing_xianzhu = _jueding_xianzhu(shuru.zhixing_zong_fen, shuru.yuandan_cbf_fen,
                                       xianzhu_bps=xian)
    guilei = _diaoyong_guilei(shuru)

    yiju = {                          # 依据明细：答辩可溯源的归因快照
        '门检基点': men,
        '差异率基点': shuru.chalv_bps,
        '规划差异显著': guihua_xianzhu,
        '执行差异显著': zhixing_xianzhu,
        '结构变更登记': shuru.jie_gou_biangeng,
        '语义归类': guilei,
    }

    # ---- 第二步：Gate-0 噪声门（定稿 #5）----
    # 差异率无法定级（基准为 0，上游 None）：交人工而非臆造（建议默认口径 c）
    if shuru.chalv_bps is None:
        return PanDuanJieguo(
            qingxing=1, panduan='不触发',
            jiuzheng='无（差异率无法定级——基准为 0，建议人工复核口径）',
            yiju=yiju, shenpi=False,
            beizhu='差异率 None（基准 0）按不触发处理并交人工（与 variance 除零口径一致）')

    if shuru.chalv_bps < men:
        # ---- 门检不通过：低于门限，只剩"有没有结构变更登记"这一条分支 ----
        if shuru.jie_gou_biangeng:
            # 情形 5：数字上是噪声，但登记了结构变更 → 提示人工评估（建议口径，T-05）
            return PanDuanJieguo(
                qingxing=5, panduan='复核提示',
                jiuzheng='提示人工评估是否启动双环（差异未超门但存在结构变更登记）',
                yiju=yiju, shenpi=True,
                beizhu='情形 5 为 v2.1 建议口径，随 T-05 请队友确认')
        # 情形 1：纯噪声，不触发
        return PanDuanJieguo(
            qingxing=1, panduan='不触发', jiuzheng='无（噪声，差异率低于门限）',
            yiju=yiju, shenpi=False)

    # ---- 第三步：门检通过（≥门限）——查判定表 ----
    # 结构信号 = 登记标签（确定性入口；T-25 拍板后人工/混合案都汇到这里）
    jiegou_xinhao = shuru.jie_gou_biangeng

    if jiegou_xinhao:
        if zhixing_xianzhu:
            # 情形 4：执行+规划均显著（混合）→ 混合纠错模式
            # 业务规则（T-29#3 应用）：双环流程优先需人工审批，同步下发
            # 单环行为整改；本周期不修改预算基准
            return PanDuanJieguo(
                qingxing=4, panduan='混合纠错模式',
                jiuzheng='混合纠错模式：双环流程优先——预算修订案提交人工审批，'
                         '同步下发单环行为整改；本周期不修改预算基准',
                beizhu='情形 4 = 结构性变更与显著执行偏差同时发生',
                yiju=yiju, shenpi=True)
        # 情形 3：规划差异显著 + 有登记 → 双环（拆分缺失时非零即显著，同样落此）
        return PanDuanJieguo(
            qingxing=3, panduan='双环',
            jiuzheng='生成预算修订案（新假设/新指标）→ 随步骤 8 提交人工审批 → '
                     '通过后下一周期回到步骤 2 按新指标重算（闭环跨周期）',
            yiju=yiju, shenpi=True)

    # ---- 无结构变更登记：单环带（含两处留白边界的建议默认口径）----
    if guilei == '结构变动':
        # LLM 疑似结构变动但【没有】登记 → 保守升级为复核提示，绝不直接双环
        # （护栏 FR-8：双环必须人工审批；T-25 未决期间的最稳落地）
        return PanDuanJieguo(
            qingxing=5, panduan='复核提示',
            jiuzheng='LLM 疑似结构变动，建议人工确认并补录变更登记后复判',
            yiju=yiju, shenpi=True,
            beizhu='语义归类仅提示不判定（§4.4 LLM 角色边界）')

    # 情形 2：执行差异显著、无结构变更 → 单环（行为整改，预算方案不动）
    beizhu = ''
    if guihua_xianzhu:
        # 留白边界 b：规划显著但没登记——仍按单环，但把线索亮给人工
        beizhu = '规划差异显著但无变更登记【建议默认口径】——建议补录变更后复判'
    elif zhixing_xianzhu is None and guihua_xianzhu is None:
        # 留白边界 d：拆分线索整体缺失——执行偏差假设（单环）+ 诚实声明
        beizhu = '拆分线索缺失，按执行偏差假设判单环【建议默认口径】'
    return PanDuanJieguo(
        qingxing=2, panduan='单环',
        jiuzheng='输出行为整改指令；预算方案不动（步骤 2 滚动更新结果维持），'
                 '年度目标不变',
        yiju=yiju, shenpi=False, beizhu=beizhu)
