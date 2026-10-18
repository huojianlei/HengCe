# -*- coding: utf-8 -*-
"""KPI 指标库 —— 方案B 步骤 1b 的【15 项指标计算】确定性核心（FR-11）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    专有缩写可保留（KPI、PBIT、BSC 等）。

口径依据（权威文件，修改本模块前必读）：
    docs/textbook/finagent-算法核对文档-定稿.md v2.1 §8（15 项公式表，定稿#9/#10）
    docs/textbook/06-kpi-dictionary.md（财务 9 项 + 非财务 6 项的公式/口径/来源）
    docs/01-需求说明.md v2.0 §3 FR-11（P1；公式按定稿口径）
    docs/proposal-full-extract.txt 行 105~112（财务 9 + 非财务 6 清单）

15 项清单（财务 9 + 非财务 6）：
    财务：营收达成率 / 成本控制率 / 费用偏差率 / 毛利率 / 净利润率 /
          销售利润率 / 资产周转率 / 资金周转率 / 采购成本变动率；
    非财务：供应链履约率 / 产能利用率 / 交付周期 / 客户满意度 /
          业务完成进度 / 异常事项数量。

单位与整数纪律（全系统统一）：
    比率/达成率类输出【整数基点】（1% = 100 基点；100% = 10000 基点）；
    周转率按"次"计——1 次 = 10000 基点（与比率统一，答辩口径在 docstring 声明）；
    交付周期输出【天】（整数）；异常事项数量输出【次】（整数）；
    全部 half-up 整数舍入、零浮点；纯函数（无 I/O、无全局状态）。

缺数纪律（除零/缺数 → None，交人工——与全项目除零纪律一致）：
    分子/分母任一缺失 → 该项 None；分母 ≤ 0 → 该项 None；
    费用偏差率 / 采购成本变动率 分子可负（节约为负），输出保留符号。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；数字例题 = 教材 06 章验算例，
    期望值全部手工验算写死）：

    知识点 1 · 教材验算例：毛利率 60%、费用偏差率 +10%、产能利用率 80%
    >>> from kpi import KpiShuru, jisuan_kpi
    >>> jg = jisuan_kpi(KpiShuru(
    ...     shouru_shiji_fen=15_000_000, shouru_yusuan_fen=14_000_000,
    ...     maoli_fen=9_000_000, jingshui_fen=3_000_000, pbit_fen=4_500_000,
    ...     ziben_zhanyong_fen=7_500_000,
    ...     liudong_zichan_qichu_fen=5_000_000, liudong_zichan_qimo_fen=6_000_000,
    ...     liudong_fuzhai_qichu_fen=2_000_000, liudong_fuzhai_qimo_fen=2_500_000,
    ...     feiyong_shiji_fen=11_000_000, feiyong_yusuan_fen=10_000_000,
    ...     kekong_chengben_shiji_fen=9_500_000, kekong_chengben_yusuan_fen=10_000_000,
    ...     caigou_benqi_fen=10_800_000, caigou_shangqi_fen=10_000_000,
    ...     shiji_chanchu=800, qianzai_channeng=1000,
    ... ))
    >>> # 毛利率 = 90,000/150,000 = 60%；费用偏差率 = +10%；产能利用率 = 80%
    >>> (jg.maolilv_bps, jg.feiyong_pianchalv_bps, jg.channeng_liyonglv_bps)
    (6000, 1000, 8000)
    >>> # 营收达成率 = 150,000/140,000 = 107.14%；资产周转率 = 2 次 = 20000 基点
    >>> (jg.yingshou_dachenglv_bps, jg.zichan_zhouzhuanlv_bps)
    (10714, 20000)

    知识点 2 · 缺数 → None（交人工，不臆造）
    >>> jg2 = jisuan_kpi(KpiShuru(shouru_shiji_fen=15_000_000, shouru_yusuan_fen=14_000_000))
    >>> (jg2.maolilv_bps, jg2.yingshou_dachenglv_bps)
    (None, 10714)

命名对照表（拼音标识符 → 中文含义）：
    KpiShuru            KPI 输入（15 项指标的显式取数字段，缺数填 None）
    KpiJieguo           KPI 结果（15 项指标输出，bps/天/次，缺数 None）
    KpiCuowu            KPI 错误（校验失败异常）
    jisuan_kpi          计算 KPI（主函数）
    yingshou_dachenglv_bps       营收达成率（基点，非负）
    chengben_kongzhilv_bps       成本控制率（基点，非负）
    feiyong_pianchalv_bps        费用偏差率（基点，可负——正=超支）
    maolilv_bps / jinglirunlv_bps / xiaoshou_lirunlv_bps   毛利率/净利率/销售利润率
    zichan_zhouzhuanlv_bps / zijin_zhouzhuanlv_bps         资产/资金周转率（1 次=10000 基点）
    caigou_chengben_bian_donglv_bps  采购成本变动率（基点，可负）
    gongyinglian_lvyuelv_bps     供应链履约率（基点）
    channeng_liyonglv_bps        产能利用率（基点）
    jiaofu_zhouqi_tian           交付周期（天）
    kehu_manyilv_bps             客户满意度（基点）
    yewu_jindu_bps               业务完成进度（基点）
    yichang_shijian_shu          异常事项数量（次）

与上下游的关系：
    上游：data_ingest（四类数据供数——取数装配在端到端层/看板数据接口做，
          本模块是纯公式层，输入显式字段）；
    下游：bsc（四维达成率取自本模块对应指标）、suyuan（变更溯源吃 15 项）、
          看板数据接口（KPI 展示）。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区
# ======================================================================

#: 单字段金额/计数上限（分/件/天/次）——防脏数据的合理性校验
ZUIDA_ZHI = 9 * 10**11


class KpiCuowu(ValueError):
    """KPI 输入校验失败（字段形态非法）。

    继承 ValueError：调用方按脏数据统一捕获（与全项目异常约定一致）。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class KpiShuru:
    """KPI 输入：15 项指标的显式取数字段（缺数填 None，不臆造）。

    字段说明（单位：金额=整数分；计数=整数件/单/天/次）：
        shouru_shiji_fen / shouru_yusuan_fen        实际/预算 收入（不含税）
        kekong_chengben_shiji_fen / _yusuan_fen     实际/预算 可控成本
        feiyong_shiji_fen / feiyong_yusuan_fen      实际/预算 期间费用
        maoli_fen / jingshui_fen / pbit_fen         实际 毛利/税后净利/息税前利润
        ziben_zhanyong_fen                          平均资本占用（非流动负债+权益）
        liudong_zichan_qichu_fen / _qimo_fen        期初/期末 流动资产
        liudong_fuzhai_qichu_fen / _qimo_fen        期初/期末 流动负债
        caigou_benqi_fen / caigou_shangqi_fen       本期/上期 采购成本
        shiji_chanchu / qianzai_channeng            实际产出/潜在产能（件）
        dingdan_zongshu / lvyue_dingdan_shu         订单总数/按期足额交付订单数
        jiaofu_zhouqi_tian_shu                      平均下单→交付天数
        manyi_keshu / shoufang_keshu                满意客户数/受访客户数
        jihua_yewu_liang / wancheng_yewu_liang      计划业务量/已完成业务量
        yichang_shijian_shu                         异常事项数量（次）
    """

    # ---- 财务 9 项取数 ----
    shouru_shiji_fen: int | None = None
    shouru_yusuan_fen: int | None = None
    kekong_chengben_shiji_fen: int | None = None
    kekong_chengben_yusuan_fen: int | None = None
    feiyong_shiji_fen: int | None = None
    feiyong_yusuan_fen: int | None = None
    maoli_fen: int | None = None
    jingshui_fen: int | None = None
    pbit_fen: int | None = None
    ziben_zhanyong_fen: int | None = None
    liudong_zichan_qichu_fen: int | None = None
    liudong_zichan_qimo_fen: int | None = None
    liudong_fuzhai_qichu_fen: int | None = None
    liudong_fuzhai_qimo_fen: int | None = None
    caigou_benqi_fen: int | None = None
    caigou_shangqi_fen: int | None = None
    # ---- 非财务 6 项取数 ----
    shiji_chanchu: int | None = None
    qianzai_channeng: int | None = None
    dingdan_zongshu: int | None = None
    lvyue_dingdan_shu: int | None = None
    jiaofu_zhouqi_tian_shu: int | None = None
    manyi_keshu: int | None = None
    shoufang_keshu: int | None = None
    jihua_yewu_liang: int | None = None
    wancheng_yewu_liang: int | None = None
    yichang_shijian_shu: int | None = None


@dataclass(frozen=True)
class KpiJieguo:
    """KPI 结果：15 项指标（缺数 None；单位见各字段注释）。

    字段说明：
        比率/达成率/周转率类：整数基点（100% = 10000；1 次 = 10000）；
        费用偏差率 / 采购成本变动率：可负（负 = 节约）；
        交付周期：天；异常事项数量：次。
    """

    yingshou_dachenglv_bps: int | None        # 营收达成率
    chengben_kongzhilv_bps: int | None        # 成本控制率
    feiyong_pianchalv_bps: int | None         # 费用偏差率（可负）
    maolilv_bps: int | None                   # 毛利率
    jinglirunlv_bps: int | None               # 净利润率
    xiaoshou_lirunlv_bps: int | None          # 销售利润率
    zichan_zhouzhuanlv_bps: int | None        # 资产周转率（次→基点）
    zijin_zhouzhuanlv_bps: int | None         # 资金周转率（次→基点）
    caigou_chengben_bian_donglv_bps: int | None   # 采购成本变动率（可负）
    gongyinglian_lvyuelv_bps: int | None      # 供应链履约率
    channeng_liyonglv_bps: int | None         # 产能利用率
    jiaofu_zhouqi_tian: int | None            # 交付周期（天）
    kehu_manyilv_bps: int | None              # 客户满意度
    yewu_jindu_bps: int | None                # 业务完成进度
    yichang_shijian_shu: int | None           # 异常事项数量（次）


# ======================================================================
# 内部工具函数区
# ======================================================================


def _jianyan_feifu(shuzhi, biaoshi: str) -> None:
    """非负整数校验：None 放行（缺数），非 None 必须是非负 int（排除 bool）。"""
    if shuzhi is None:
        return
    if isinstance(shuzhi, bool) or not isinstance(shuzhi, int):
        raise KpiCuowu(f'{biaoshi} 必须为整数或 None：{shuzhi!r}')
    if shuzhi < 0 or shuzhi > ZUIDA_ZHI:
        raise KpiCuowu(f'{biaoshi} 必须在 [0, {ZUIDA_ZHI}] 内：{shuzhi}')


def _bili_bps(fenzi: int | None, fenmu: int | None) -> int | None:
    """非负比率（基点）= 分子 ÷ 分母 × 10000，half-up 整数实现。

    分子/分母任一缺数或分母 ≤ 0 → None（缺数纪律，交人工）；
    实现：(2×分子×10000 + 分母) // (2×分母) 即 half-up，全程无浮点。
    """
    if fenzi is None or fenmu is None or fenmu <= 0:
        return None
    return (fenzi * 10_000 * 2 + fenmu) // (2 * fenmu)


def _daifuhao_bps(fenzi: int | None, fenmu: int | None) -> int | None:
    """带符号偏差率（基点）= (分子−分母) ÷ 分母 × 10000，half-up。

    用于费用偏差率/采购成本变动率：分子是实际（本期）、分母是预算（上期），
    正 = 超支/上涨（不利），负 = 节约/下降（有利）；符号保留。
    分母 ≤ 0 或任一缺数 → None（缺数纪律，交人工）。
    """
    if fenzi is None or fenmu is None or fenmu <= 0:
        return None
    chae = fenzi - fenmu
    bps = (abs(chae) * 10_000 * 2 + fenmu) // (2 * fenmu)
    return bps if chae >= 0 else -bps


def _pingjun_yunying_zijin(qichu_zichan: int | None, qimo_zichan: int | None,
                           qichu_fuzhai: int | None, qimo_fuzhai: int | None) -> int | None:
    """平均营运资金 =（期初营运资金 + 期末营运资金）÷ 2，half-up。

    营运资金 = 流动资产 − 流动负债（定稿 #9 口径：平均 =（期初+期末）÷2）。
    四个输入任一缺数 → None；half-up 整数实现 (a+b+1)//2（a、b 为两个
    期末净营运资金，可为负——负数说明营运资金为负，交调用方按分母处理）。
    """
    if qichu_zichan is None or qimo_zichan is None or qichu_fuzhai is None or qimo_fuzhai is None:
        return None
    qichu_jing = qichu_zichan - qichu_fuzhai   # 期初营运资金（可为负）
    qimo_jing = qimo_zichan - qimo_fuzhai      # 期末营运资金（可为负）
    # half-up：(a+b) 可能为负——负数场景除以 2 向零舍入（与正数规则同构）
    he = qichu_jing + qimo_jing
    if he >= 0:
        return (he + 1) // 2
    return -((-he + 1) // 2)


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def jisuan_kpi(shuru: KpiShuru) -> KpiJieguo:
    """15 项 KPI 计算（方案B 步骤 1b；纯函数）。

    参数：shuru —— KpiShuru（显式取数字段，缺数填 None）。

    返回：KpiJieguo（15 项指标；缺数/分母 ≤ 0 → 对应项 None）。

    处理顺序：
        ① 全字段形态校验 → ② 财务 9 项 → ③ 非财务 6 项 → ④ 组装输出。
    """
    if not isinstance(shuru, KpiShuru):
        raise KpiCuowu(f'输入必须是 KpiShuru：{shuru!r}')

    # ① 全字段形态校验（None 放行——缺数交人工，不臆造）
    for zhi, biaoshi in (
        (shuru.shouru_shiji_fen, 'shouru_shiji_fen'),
        (shuru.shouru_yusuan_fen, 'shouru_yusuan_fen'),
        (shuru.kekong_chengben_shiji_fen, 'kekong_chengben_shiji_fen'),
        (shuru.kekong_chengben_yusuan_fen, 'kekong_chengben_yusuan_fen'),
        (shuru.feiyong_shiji_fen, 'feiyong_shiji_fen'),
        (shuru.feiyong_yusuan_fen, 'feiyong_yusuan_fen'),
        (shuru.maoli_fen, 'maoli_fen'),
        (shuru.jingshui_fen, 'jingshui_fen'),
        (shuru.pbit_fen, 'pbit_fen'),
        (shuru.ziben_zhanyong_fen, 'ziben_zhanyong_fen'),
        (shuru.liudong_zichan_qichu_fen, 'liudong_zichan_qichu_fen'),
        (shuru.liudong_zichan_qimo_fen, 'liudong_zichan_qimo_fen'),
        (shuru.liudong_fuzhai_qichu_fen, 'liudong_fuzhai_qichu_fen'),
        (shuru.liudong_fuzhai_qimo_fen, 'liudong_fuzhai_qimo_fen'),
        (shuru.caigou_benqi_fen, 'caigou_benqi_fen'),
        (shuru.caigou_shangqi_fen, 'caigou_shangqi_fen'),
        (shuru.shiji_chanchu, 'shiji_chanchu'),
        (shuru.qianzai_channeng, 'qianzai_channeng'),
        (shuru.dingdan_zongshu, 'dingdan_zongshu'),
        (shuru.lvyue_dingdan_shu, 'lvyue_dingdan_shu'),
        (shuru.jiaofu_zhouqi_tian_shu, 'jiaofu_zhouqi_tian_shu'),
        (shuru.manyi_keshu, 'manyi_keshu'),
        (shuru.shoufang_keshu, 'shoufang_keshu'),
        (shuru.jihua_yewu_liang, 'jihua_yewu_liang'),
        (shuru.wancheng_yewu_liang, 'wancheng_yewu_liang'),
        (shuru.yichang_shijian_shu, 'yichang_shijian_shu'),
    ):
        _jianyan_feifu(zhi, biaoshi)

    # ② 财务 9 项（公式见模块头；比率统一基点、half-up）
    # 1 营收达成率 = 实际收入 ÷ 预算收入
    yingshou = _bili_bps(shuru.shouru_shiji_fen, shuru.shouru_yusuan_fen)
    # 2 成本控制率 = 实际可控成本 ÷ 预算可控成本
    chengben_kongzhi = _bili_bps(shuru.kekong_chengben_shiji_fen, shuru.kekong_chengben_yusuan_fen)
    # 3 费用偏差率 =（实际 − 预算）÷ 预算（带符号）
    feiyong_piancha = _daifuhao_bps(shuru.feiyong_shiji_fen, shuru.feiyong_yusuan_fen)
    # 4 毛利率 = 毛利 ÷ 收入
    maolilv = _bili_bps(shuru.maoli_fen, shuru.shouru_shiji_fen)
    # 5 净利润率 = 税后净利 ÷ 收入
    jinglirunlv = _bili_bps(shuru.jingshui_fen, shuru.shouru_shiji_fen)
    # 6 销售利润率 = PBIT ÷ 收入
    xiaoshou_lirunlv = _bili_bps(shuru.pbit_fen, shuru.shouru_shiji_fen)
    # 7 资产周转率 = 收入 ÷ 平均资本占用（1 次 = 10000 基点）
    zichan = _bili_bps(shuru.shouru_shiji_fen, shuru.ziben_zhanyong_fen)
    # 8 资金周转率 = 收入 ÷ 平均营运资金（定稿 #9 补：平均=（期初+期末）÷2）
    pingjun_yingyun = _pingjun_yunying_zijin(
        shuru.liudong_zichan_qichu_fen, shuru.liudong_zichan_qimo_fen,
        shuru.liudong_fuzhai_qichu_fen, shuru.liudong_fuzhai_qimo_fen,
    )
    zijin = _bili_bps(shuru.shouru_shiji_fen, pingjun_yingyun)
    # 9 采购成本变动率 =（本期 − 上期）÷ 上期（带符号）
    caigou = _daifuhao_bps(shuru.caigou_benqi_fen, shuru.caigou_shangqi_fen)

    # ③ 非财务 6 项
    # 10 供应链履约率 = 按期足额交付订单数 ÷ 订单总数
    gongyinglian = _bili_bps(shuru.lvyue_dingdan_shu, shuru.dingdan_zongshu)
    # 11 产能利用率 = 实际产出 ÷ 潜在产能
    channeng = _bili_bps(shuru.shiji_chanchu, shuru.qianzai_channeng)
    # 12 交付周期 = 平均下单→交付天数（直接值，缺数 None）
    jiaofu_zhouqi = shuru.jiaofu_zhouqi_tian_shu
    # 13 客户满意度 = 满意客户数 ÷ 受访客户数
    kehu_manyi = _bili_bps(shuru.manyi_keshu, shuru.shoufang_keshu)
    # 14 业务完成进度 = 已完成业务量 ÷ 计划业务量
    yewu_jindu = _bili_bps(shuru.wancheng_yewu_liang, shuru.jihua_yewu_liang)
    # 15 异常事项数量 = 期内异常事件计数（直接值）
    yichang = shuru.yichang_shijian_shu

    # ④ 组装输出（字段顺序 = 15 项清单顺序）
    return KpiJieguo(
        yingshou_dachenglv_bps=yingshou,
        chengben_kongzhilv_bps=chengben_kongzhi,
        feiyong_pianchalv_bps=feiyong_piancha,
        maolilv_bps=maolilv,
        jinglirunlv_bps=jinglirunlv,
        xiaoshou_lirunlv_bps=xiaoshou_lirunlv,
        zichan_zhouzhuanlv_bps=zichan,
        zijin_zhouzhuanlv_bps=zijin,
        caigou_chengben_bian_donglv_bps=caigou,
        gongyinglian_lvyuelv_bps=gongyinglian,
        channeng_liyonglv_bps=channeng,
        jiaofu_zhouqi_tian=jiaofu_zhouqi,
        kehu_manyilv_bps=kehu_manyi,
        yewu_jindu_bps=yewu_jindu,
        yichang_shijian_shu=yichang,
    )
