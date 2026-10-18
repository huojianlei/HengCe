# -*- coding: utf-8 -*-
"""整改数据底座 —— 方案B 步骤 8 的【整改清单结构化】确定性核心（FR-14 计算部分）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

口径依据（权威文件，修改本模块前必读）：
    docs/01-需求说明.md v2.0 §3 FR-14（分部门分模块整改方案——用户拍板拆分：
        【整改数据底座 = 计算层】本模块先做；文案起草 = AI 层后接，[043]/T-28）
    docs/textbook/finagent-算法核对文档-定稿.md v2.1 §4（判定输出→纠错指令）
        / §9 步骤 8（整改方案 + 双环预算修订案人工审批闭环）
    docs/proposal-full-extract.txt 行 60~66（整改闭环区输出清单）

模块定位（[043] 分层拆分后的职责边界）：
    本模块把【确定性规则】可推出的整改事项全部结构化——红/黄预警行、
    单双环判定指令、核心问题模块责任定位——输出"整改清单"（问题、
    责任模块、整改类型、优先级、审批标志、进度状态）。AI 层（dsh 部署后）
    只负责把 qingdan 喂给 LLM 起草整改文案——本模块不产出一句自然语言。

整改规则（确定性，全部可测试）：
    ① 判定 ∈ {双环, 双轨} → 预算修订案（优先级高、必人工审批）；
    ② 判定 = 单环 → 行为整改指令（优先级中）；
    ③ 判定 = 复核提示 → 人工复核项（优先级中）；
    ④ 差异红预警行（|差异率| ≥ 10%）→ 强制整改（优先级高）；
    ⑤ 差异黄预警行（1% ≤ |差异率| < 10%）→ 关注整改（优先级中）；
    ⑥ 责任模块 = 科目→模块映射（复用 building_blocks 默认映射）+ 核心
       问题模块（积木高亮）；映射不中 → '未归属'；
    ⑦ 清单按优先级排序（高 → 中 → 低），同优先级按生成顺序。

进度状态：所有条目初始 '待整改'；整改进度 = 四状态计数（供看板进度字段）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；例题 = 一个红预警差异 + 双环判定，
    期望值手工验算写死）：

    知识点 1 · 红预警行 → 强制整改；双环 → 预算修订案
    >>> from variance import ChayiShuru, YujingDang, jisuan_chayi
    >>> from loop_decision import PanDuanShuru, panduan_huanlu
    >>> from building_blocks import JimuHang, chai_jimu
    >>> chayi = jisuan_chayi([
    ...     ChayiShuru('2026-Q1', '材料价格差异', '成本类',
    ...                10_000_000, 10_000_000, 11_000_000),
    ... ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
    >>> jimu = chai_jimu([JimuHang('2026-Q1', '材料价格差异', 1_000_000, 'A', '红', 1000)])
    >>> # 示例差异率 1000 基点低于 25% 新默认门限，传 100 沿用原定稿口径
    >>> panduan = panduan_huanlu(PanDuanShuru(
    ...     chalv_bps=1000, guihua_zong_fen=900_000, zhixing_zong_fen=100_000,
    ...     yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True, bianma='供应商涨价'),
    ...     menjian_bps=100, xianzhu_bps=100)
    >>> jg = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi, jimu=jimu, panduan=panduan))
    >>> [(x.leixing, x.youxianji, x.zeren_mokuai) for x in jg.qingdan]
    [('预算修订案', '高', '采购模块'), ('强制整改', '高', '采购模块')]
    >>> (jg.gao_shu, jg.daizhenggai_shu)
    (2, 2)

    知识点 2 · 只有黄预警 → 关注整改（中）
    >>> chayi2 = jisuan_chayi([
    ...     ChayiShuru('2026-Q1', '办公费', '成本类',
    ...                10_000_000, 10_000_000, 10_500_000),
    ... ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
    >>> jg2 = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi2))
    >>> [(x.leixing, x.youxianji) for x in jg2.qingdan]
    [('关注整改', '中')]

命名对照表（拼音标识符 → 中文含义）：
    ZhenggaiShuru       整改输入（差异结果/积木结果/判定结果，可缺省 None）
    ZhenggaiXiang       整改项（类型/优先级/责任模块/描述/审批/进度）
    ZhenggaiJieguo      整改结果（清单 + 优先级计数 + 整改进度计数）
    shengcheng_zhenggai 生成整改（主函数）
    leixing             整改类型（预算修订案/行为整改指令/人工复核/强制整改/关注整改）
    youxianji           优先级（高/中/低）
    zeren_mokuai        责任模块（四模块名/未归属/无）
    shenpi              是否需人工审批（预算修订案必 True）
    zhuangtai           进度状态（待整改/进行中/已完成）
    gao_shu / zhong_shu / di_shu       高/中/低优先级计数
    daizhenggai_shu / jinxingzhong_shu / wancheng_shu   整改进度三态计数

与上下游的关系：
    上游：variance（红/黄预警行）、loop_decision（判定指令）、
          building_blocks（核心问题模块 + 科目→模块映射）；
    下游：看板数据接口（整改闭环区/整改进度）、AI 层（清单→LLM 文案起草）。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区（数据值用中文——整改类型/优先级/进度状态）
# ======================================================================

#: 整改类型（③②①④⑤ 规则对应的五种，见模块头）
LEIXING_YUSUAN_XIUDING = '预算修订案'
LEIXING_XINGWEI_ZHENGGAI = '行为整改指令'
LEIXING_RENGONG_FUHE = '人工复核'
LEIXING_QIANGZHI = '强制整改'
LEIXING_GUANZHU = '关注整改'

#: 优先级
YOUXIANJI_GAO = '高'
YOUXIANJI_ZHONG = '中'
YOUXIANJI_DI = '低'

#: 进度状态
ZHUANGTAI_DAI = '待整改'
ZHUANGTAI_JINXING = '进行中'
ZHUANGTAI_WANCHENG = '已完成'

#: 责任模块兜底（科目映射不中——交人工补映射）
ZEREN_WEIGUISHU = '未归属'
#: 责任模块缺省（无积木结果时的占位）
ZEREN_WU = '无'


@dataclass(frozen=True)
class ZhenggaiShuru:
    """整改输入：上游结果对象（鸭子类型；缺省 None = 该来源不参与）。

    字段说明：
        chayi:   variance.ChayiJieguo（红/黄预警行来源；须有 .xiang 列表，
                 行须有 qijian/kemu/chae_fen/fa/yujing/chalv_bps 属性）。
        jimu:    building_blocks.JimuJieguo（核心问题模块；须有 .hexin_mokuai）。
        panduan: loop_decision.PanDuanJieguo（判定指令；须有 .panduan 属性）。
    """

    chayi: object | None = None
    jimu: object | None = None
    panduan: object | None = None


@dataclass(frozen=True)
class ZhenggaiXiang:
    """整改项：一条结构化整改指令（AI 层文案起草的输入行）。

    字段说明：
        leixing:       整改类型（五种枚举，见模块头）。
        youxianji:     优先级（高/中/低）。
        zeren_mokuai:  责任模块（四模块名/未归属/无）。
        kemu:          科目名（差异行来源；判定项为 ''）。
        qijian:        期间键（差异行来源；判定项为 ''）。
        miaoshu:       结构化描述（"期间 科目 差额分 预警档"拼接，
                       无自然语言——文案由 AI 层起草）。
        shenpi:        是否需人工审批（预算修订案必 True，其余 False）。
        zhuangtai:     进度状态（初始 '待整改'）。
    """

    leixing: str
    youxianji: str
    zeren_mokuai: str
    kemu: str
    qijian: str
    miaoshu: str
    shenpi: bool
    zhuangtai: str


@dataclass(frozen=True)
class ZhenggaiJieguo:
    """整改结果：清单（按优先级排序）+ 优先级计数 + 整改进度计数。

    字段说明：
        qingdan:          整改项列表（高 → 中 → 低）。
        gao_shu / zhong_shu / di_shu:  优先级计数。
        zong_shu:         清单总数。
        daizhenggai_shu / jinxingzhong_shu / wancheng_shu:  进度三态计数。
    """

    qingdan: list[ZhenggaiXiang]
    gao_shu: int
    zhong_shu: int
    di_shu: int
    zong_shu: int
    daizhenggai_shu: int
    jinxingzhong_shu: int
    wancheng_shu: int


# ======================================================================
# 内部工具函数区
# ======================================================================


def _yuan_xianshi(fen: int) -> str:
    """分 → 元显示（两位小数 + 千分位；整数运算实现，零浮点）。"""
    # T-29#8 应用：对外报告统一主单位元——描述文本不再出现"分"
    fu = fen < 0
    v = -fen if fu else fen
    zheng, xiao = divmod(v, 100)
    s = f'{zheng:,}.{xiao:02d}'
    return f'-{s}' if fu else s


def _zeren_mokuai(kemu: str) -> str:
    """科目 → 责任模块（复用 building_blocks 默认关键词映射，契约式）。

    映射不中 → '未归属'（不静默丢弃，交人工补映射——与积木模块同纪律）。
    """
    try:
        from building_blocks import yingshe_mokuai
        mokuai = yingshe_mokuai(kemu)
    except ImportError:
        mokuai = None  # 环境缺失时降级未归属（本模块可在无积木模块时独立跑）
    return mokuai if mokuai is not None else ZEREN_WEIGUISHU


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def shengcheng_zhenggai(shuru: ZhenggaiShuru) -> ZhenggaiJieguo:
    """生成整改清单（方案B 步骤 8 的计算部分；纯函数）。

    参数：shuru —— ZhenggaiShuru（差异/积木/判定结果，均可缺省 None）。

    返回：ZhenggaiJieguo（按优先级排序的整改清单 + 计数 + 整改进度）。

    处理顺序：
        ① 判定指令项（预算修订案/行为整改指令/人工复核）→ ② 差异预警项
        （红=强制/黄=关注）→ ③ 责任模块定位 → ④ 优先级排序 → ⑤ 计数。
    """
    if not isinstance(shuru, ZhenggaiShuru):
        raise TypeError(f'输入必须是 ZhenggaiShuru：{shuru!r}')

    qingdan: list[ZhenggaiXiang] = []

    # ① 判定指令项（loop_decision 输出 → 纠错指令，定稿 §4/§9 步骤 8）
    hexin = getattr(shuru.jimu, 'hexin_mokuai', None) if shuru.jimu is not None else None
    if shuru.panduan is not None:
        panduan = getattr(shuru.panduan, 'panduan', '')
        zeren = hexin if hexin is not None else ZEREN_WU
        if panduan in ('双环', '混合纠错模式'):  # 混合纠错模式（原名双轨，T-29#3 更名）
            # 预算修订案：必人工审批（定稿 §9 步骤 8 人工审批环节）
            qingdan.append(ZhenggaiXiang(
                leixing=LEIXING_YUSUAN_XIUDING, youxianji=YOUXIANJI_GAO,
                zeren_mokuai=zeren, kemu='', qijian='',
                miaoshu=f'判定 {panduan}：预算修订案（人工审批后下周期生效）',
                shenpi=True, zhuangtai=ZHUANGTAI_DAI,
            ))
        elif panduan == '单环':
            # 行为整改指令：不修改预算基准，仅纠正当下业务执行动作
            qingdan.append(ZhenggaiXiang(
                leixing=LEIXING_XINGWEI_ZHENGGAI, youxianji=YOUXIANJI_ZHONG,
                zeren_mokuai=zeren, kemu='', qijian='',
                miaoshu='判定 单环：输出行为整改指令（不改预算基准）',
                shenpi=False, zhuangtai=ZHUANGTAI_DAI,
            ))
        elif panduan == '复核提示':
            # 复核提示：疑似结构变动交人工确认（护栏 FR-8 的落地出口）
            qingdan.append(ZhenggaiXiang(
                leixing=LEIXING_RENGONG_FUHE, youxianji=YOUXIANJI_ZHONG,
                zeren_mokuai=zeren, kemu='', qijian='',
                miaoshu='判定 复核提示：疑似结构变动，交人工确认补录',
                shenpi=False, zhuangtai=ZHUANGTAI_DAI,
            ))

    # ② 差异预警项（红=强制整改、黄=关注整改——定稿 #3 三档预警的落地出口）
    if shuru.chayi is not None:
        for x in shuru.chayi.xiang:
            if x.yujing == '红':
                qingdan.append(ZhenggaiXiang(
                    leixing=LEIXING_QIANGZHI, youxianji=YOUXIANJI_GAO,
                    zeren_mokuai=_zeren_mokuai(x.kemu), kemu=x.kemu,
                    qijian=x.qijian,
                    miaoshu=f'{x.qijian} {x.kemu} 差额 {_yuan_xianshi(x.chae_fen)} 元 预警 红',
                    shenpi=False, zhuangtai=ZHUANGTAI_DAI,
                ))
            elif x.yujing == '黄':
                qingdan.append(ZhenggaiXiang(
                    leixing=LEIXING_GUANZHU, youxianji=YOUXIANJI_ZHONG,
                    zeren_mokuai=_zeren_mokuai(x.kemu), kemu=x.kemu,
                    qijian=x.qijian,
                    miaoshu=f'{x.qijian} {x.kemu} 差额 {_yuan_xianshi(x.chae_fen)} 元 预警 黄',
                    shenpi=False, zhuangtai=ZHUANGTAI_DAI,
                ))

    # ③ 核心问题模块追加高亮提示（积木 D3 高亮 ≠ 预警行——单独一条）
    if hexin is not None and not any(
        x.leixing == LEIXING_QIANGZHI and x.zeren_mokuai == hexin for x in qingdan
    ):
        qingdan.append(ZhenggaiXiang(
            leixing=LEIXING_GUANZHU, youxianji=YOUXIANJI_ZHONG,
            zeren_mokuai=hexin, kemu='', qijian='',
            miaoshu=f'积木核心问题模块：{hexin}（不利差异最大，优先整改）',
            shenpi=False, zhuangtai=ZHUANGTAI_DAI,
        ))

    # ④ 优先级排序（高 → 中 → 低；同优先级保持生成顺序——排序稳定）
    youxian_xu = {YOUXIANJI_GAO: 0, YOUXIANJI_ZHONG: 1, YOUXIANJI_DI: 2}
    qingdan.sort(key=lambda x: youxian_xu[x.youxianji])

    # ⑤ 计数（优先级 + 整改进度三态——初始全为待整改）
    return ZhenggaiJieguo(
        qingdan=qingdan,
        gao_shu=sum(1 for x in qingdan if x.youxianji == YOUXIANJI_GAO),
        zhong_shu=sum(1 for x in qingdan if x.youxianji == YOUXIANJI_ZHONG),
        di_shu=sum(1 for x in qingdan if x.youxianji == YOUXIANJI_DI),
        zong_shu=len(qingdan),
        daizhenggai_shu=sum(1 for x in qingdan if x.zhuangtai == ZHUANGTAI_DAI),
        jinxingzhong_shu=sum(1 for x in qingdan if x.zhuangtai == ZHUANGTAI_JINXING),
        wancheng_shu=sum(1 for x in qingdan if x.zhuangtai == ZHUANGTAI_WANCHENG),
    )
