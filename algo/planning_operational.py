# -*- coding: utf-8 -*-
"""规划/执行差异拆分模块 —— 方案B 步骤 3c（总量恒等式铁律 + 四项细分归因）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

口径依据（权威文件，修改本模块前必读）：
    docs\\textbook\\finagent-算法核对文档-定稿.md v2.1 §3（T-01 修复后的拆分口径）
    docs\\10-待核对问题定稿摘要.md  #4（队友定稿：以修订标准为基准的拆分）

【铁律】总量恒等式——总量按恒等式计算与展示，永不由四项细分相加：
    原标准总差异 = 规划总差异 + 执行总差异
      规划总差异 = 修订标准成本 − 原标准成本（不可控，不归责执行部门）
      执行总差异 = 实际成本   − 修订标准成本（可控，纳入绩效）
    恒等式天然成立（数学事实），代码内仍显式校验并输出成立标志（防回归）。

四项细分（仅作归因参考，含交叉残差——v2.1 §3 对 #4 硬伤的处理）：
    价格规划 =（标准单价 − 修订单价）× 实际用量
    价格执行 =  修订单价 × 实际用量 − 实际成本           （等价 (修订−实际价)×用量）
    用量规划 =（标准用量 − 修订用量）× 实际产量 × 标准单价
    用量执行 =（修订用量 × 实际产量 − 实际用量）× 修订单价
    细分合计 ≠ 总差异（差额即残差）——展示时须注明"以总量恒等式为准"。

残差公式（与总量恒等式的解析关系，代码内校验）：
    残差 =（修订用量 × 实际产量 − 实际用量）×（标准单价 − 修订单价）

【符号口径——两套并存，字段上一一配对 FA，绝不裸用（v2.1 §0.5 精神）】
    三个总量（yuandan/guihua/zhixing_zong）：展示口径，正 = 超支 = 不利 A；
    四个细分（jiage/yongliang_guihua/zhixing）：ACCA 公式符号，正 = 节省 = 有利 F；
    原因：总量按"贵了为正"贴合报表直觉；细分公式天然"节省为正"（标准−实际方向）。

数值纪律：单价/成本 = 整数分；用量/产量 = 整数（基本单位：kg、工时等）；
    全程整数运算——四项公式全部改写为乘减形式，【零除法】（无舍入误差源）。

与上下游的关系：
    上游：variance（步骤 3a 提供差异触发场景）、data_ingest（修订标准参数）；
    下游：loop_decision（步骤 4 单双环判定的归因线索——
          执行差异显著 → 单环线索；规划差异显著 → 双环线索，见 v2.1 §3 挂钩）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests\\test_demos.py 守护；数字例题 = 定稿 v2.1 §3 的 Holmes Ltd
    案例（标准 7kg×$4 → 修订 8kg×$3.80；产量 1,400，耗用 11,000kg，
    成本 $41,500），期望值全部手工验算写死，金额乘 100 转分）：

    知识点 1 · Holmes 例题：三个总量 + 恒等式
    >>> from planning_operational import ChaifenShuru, chai_fen
    >>> jg = chai_fen(ChaifenShuru(biaozhun_danjia_fen=400, biaozhun_yongliang=7,
    ...     xiuding_danjia_fen=380, xiuding_yongliang=8,
    ...     shiji_chanliang=1400, shiji_yongliang=11000, shiji_chengben_fen=4_150_000))
    >>> # 原标准总 = 4,150,000 − 1,400×7×400 = +2,300 元，超支 → A
    >>> (jg.yuandan_zong_fen, jg.yuandan_zong_fa)
    (230000, 'A')
    >>> # 规划总 +3,360 元（A）；执行总 −1,060 元（F）
    >>> (jg.guihua_zong_fen, jg.zhixing_zong_fen)
    (336000, -106000)
    >>> # 恒等式：336,000 + (−106,000) = 230,000 ✓
    >>> jg.hengdengshi_chengli
    True

    知识点 2 · 四项细分（ACCA 符号：正 = 有利 F）+ 残差
    >>> # 价格规划 = (400−380)×11,000 = +2,200 元，修订单价更低 → F
    >>> (jg.jiage_guihua_fen, jg.jiage_guihua_fa)
    (220000, 'F')
    >>> # 用量规划 −5,600（A）；用量执行 +760（F）
    >>> (jg.yongliang_guihua_fen, jg.yongliang_zhixing_fen)
    (-560000, 76000)
    >>> # 残差 40 元 = (8×1400−11000)×(400−380)——细分合计≠总量的部分
    >>> jg.cancha_fen
    4000

    知识点 3 · 无结构变更（修订 = 标准）：规划差异归零，全归执行
    >>> jg2 = chai_fen(ChaifenShuru(400, 7, 400, 7, 1400, 11000, 4_150_000))
    >>> (jg2.guihua_zong_fen, jg2.zhixing_zong_fen)
    (0, 230000)

命名对照表（拼音标识符 → 中文含义）：
    ChaifenShuru      拆分输入（标准/修订参数 + 实际三数）
    ChaifenJieguo     拆分结果（三总量+四细分+残差+恒等式标志，各金额配 FA）
    ChaifenCuowu      拆分错误（校验失败异常）
    chai_fen          拆分（主函数）
    biaozhun_danjia_fen / biaozhun_yongliang   标准单价（分）/ 标准用量
    xiuding_danjia_fen / xiuding_yongliang     修订单价（分）/ 修订用量
    shiji_chanliang / shiji_yongliang / shiji_chengben_fen
                      实际产量 / 实际总用量 / 实际总成本（分）
    yuandan_zong_*    原标准总差异（金额分 + FA）
    guihua_zong_*     规划总差异（不可控）
    zhixing_zong_*    执行总差异（可控）
    jiage_guihua_* / jiage_zhixing_*     价格规划/价格执行（细分）
    yongliang_guihua_* / yongliang_zhixing_*  用量规划/用量执行（细分）
    cancha_fen        残差（细分合计与总量的解析差额）
    hengdengshi_chengli  恒等式成立（自检标志，恒 True；False 即代码有 bug）

建立：2026-08-23 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区
# ======================================================================

#: 金额字段上限（分）——与全项目一致的合理性校验（Python int 无溢出，防脏数据）
ZUIDA_JINE_FEN = 9 * 10**11

#: 数量字段上限（基本单位）——kg / 工时等，同样只为拦截录入事故
ZUIDA_SHULIANG = 10**9


class ChaifenCuowu(ValueError):
    """拆分输入校验失败（字段非法 / 产量为零等）。

    继承 ValueError：调用方按脏数据统一捕获（全项目异常约定）。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class ChaifenShuru:
    """拆分输入：标准参数、修订参数（结构变更后重估）与实际三数。

    字段说明：
        biaozhun_danjia_fen:   标准单价（分）。
        biaozhun_yongliang:    标准用量/单位（基本单位的整数）。
        xiuding_danjia_fen:    修订单价（分）——事后重估的"应该价格"。
        xiuding_yongliang:     修订用量/单位——事后重估的"应该用量"。
        shiji_chanliang:       实际产量（必须 > 0：单位成本要有分母）。
        shiji_yongliang:       实际总用量（允许 0：没用料但花了钱的场景）。
        shiji_chengben_fen:    实际总成本（分）。
    """

    biaozhun_danjia_fen: int
    biaozhun_yongliang: int
    xiuding_danjia_fen: int
    xiuding_yongliang: int
    shiji_chanliang: int
    shiji_yongliang: int
    shiji_chengben_fen: int


@dataclass(frozen=True)
class ChaifenJieguo:
    """拆分结果：三总量 + 四细分 + 残差 + 恒等式标志（每个金额配 FA）。

    符号口径（见模块头"符号口径"节，两套并存、字段配对防误用）：
        三个 *_zong_*：正 = 超支 = A；四个细分：正 = 有利 = F。
    """

    yuandan_zong_fen: int      # 原标准总差异 = 实际 − 原标准
    yuandan_zong_fa: str
    guihua_zong_fen: int       # 规划总差异 = 修订标准 − 原标准（不可控）
    guihua_zong_fa: str
    zhixing_zong_fen: int      # 执行总差异 = 实际 − 修订标准（可控）
    zhixing_zong_fa: str
    jiage_guihua_fen: int      # 价格规划细分（F 为正）
    jiage_guihua_fa: str
    jiage_zhixing_fen: int     # 价格执行细分（F 为正）
    jiage_zhixing_fa: str
    yongliang_guihua_fen: int  # 用量规划细分（F 为正）
    yongliang_guihua_fa: str
    yongliang_zhixing_fen: int  # 用量执行细分（F 为正）
    yongliang_zhixing_fa: str
    cancha_fen: int            # 残差（细分合计与总量的解析差额，展示用）
    hengdengshi_chengli: bool  # 恒等式自检标志（恒 True；False = 代码缺陷）


# ======================================================================
# 内部工具函数区
# ======================================================================


def _jianyan(shuzhi: int, shangxian: int, biaoshi: str) -> None:
    """通用校验：非负整数且不超上限（bool 排除——True 也是 int 子类）。"""
    if isinstance(shuzhi, bool) or not isinstance(shuzhi, int):
        raise ChaifenCuowu(f'{biaoshi} 必须为整数：{shuzhi!r}')
    if shuzhi < 0 or shuzhi > shangxian:
        raise ChaifenCuowu(f'{biaoshi} 必须在 [0, {shangxian}] 内：{shuzhi}')


def _fa_zong(fen: int) -> str:
    """总量 F/A：展示口径——正 = 超支 = 'A'，负 = 'F'，零 = '—'。"""
    if fen == 0:
        return '—'
    return 'A' if fen > 0 else 'F'


def _fa_xiangxi(fen: int) -> str:
    """细分 F/A：ACCA 口径——正 = 节省 = 'F'，负 = 'A'，零 = '—'。"""
    if fen == 0:
        return '—'
    return 'F' if fen > 0 else 'A'


# ======================================================================
# 对外接口区（唯一的计算入口）
# ======================================================================


def chai_fen(shuru: ChaifenShuru) -> ChaifenJieguo:
    """规划/执行差异拆分（方案B 步骤 3c；纯函数、全程整数、零除法）。

    计算顺序：
        ① 校验 → ② 三个总量（恒等式成员）→ ③ 恒等式自检 →
        ④ 四项细分（乘减改写，无除法无舍入）→ ⑤ 残差公式核对。
    """
    # ---- ① 校验 ----
    if not isinstance(shuru, ChaifenShuru):
        raise ChaifenCuowu(f'shuru 必须为 ChaifenShuru 实例：{shuru!r}')
    _jianyan(shuru.biaozhun_danjia_fen, ZUIDA_JINE_FEN, 'biaozhun_danjia_fen')
    _jianyan(shuru.xiuding_danjia_fen, ZUIDA_JINE_FEN, 'xiuding_danjia_fen')
    _jianyan(shuru.shiji_chengben_fen, ZUIDA_JINE_FEN, 'shiji_chengben_fen')
    for mingzi, zhi in (('biaozhun_yongliang', shuru.biaozhun_yongliang),
                        ('xiuding_yongliang', shuru.xiuding_yongliang),
                        ('shiji_yongliang', shuru.shiji_yongliang)):
        _jianyan(zhi, ZUIDA_SHULIANG, mingzi)
    _jianyan(shuru.shiji_chanliang, ZUIDA_SHULIANG, 'shiji_chanliang')
    if shuru.shiji_chanliang <= 0:
        # 产量为 0 时单位成本失去意义（拆分的数学前提），明确拒绝
        raise ChaifenCuowu('shiji_chanliang 必须大于 0（单位成本要有分母）')

    # ---- ② 三个总量（原标准 / 修订标准的"单位成本 × 产量"展开式）----
    yuandan_biaozhun_fen = shuru.shiji_chanliang * shuru.biaozhun_yongliang * shuru.biaozhun_danjia_fen
    xiuding_biaozhun_fen = shuru.shiji_chanliang * shuru.xiuding_yongliang * shuru.xiuding_danjia_fen

    yuandan_zong = shuru.shiji_chengben_fen - yuandan_biaozhun_fen   # 实际 − 原标准
    guihua_zong = xiuding_biaozhun_fen - yuandan_biaozhun_fen        # 修订 − 原标准
    zhixing_zong = shuru.shiji_chengben_fen - xiuding_biaozhun_fen   # 实际 − 修订

    # ---- ③ 恒等式自检（数学上恒成立；False 即代码缺陷，直接抛错暴露）----
    if yuandan_zong != guihua_zong + zhixing_zong:
        raise ChaifenCuowu('内部错误：恒等式不成立（原标准总 ≠ 规划总 + 执行总）')

    # ---- ④ 四项细分（乘减改写：等价于教材公式但零除法、零舍入）----
    jiage_guihua = (shuru.biaozhun_danjia_fen - shuru.xiuding_danjia_fen) * shuru.shiji_yongliang
    jiage_zhixing = shuru.xiuding_danjia_fen * shuru.shiji_yongliang - shuru.shiji_chengben_fen
    yongliang_guihua = (shuru.biaozhun_yongliang - shuru.xiuding_yongliang) * shuru.shiji_chanliang * shuru.biaozhun_danjia_fen
    yongliang_zhixing = (shuru.xiuding_yongliang * shuru.shiji_chanliang - shuru.shiji_yongliang) * shuru.xiuding_danjia_fen

    # ---- ⑤ 残差公式（解析核对：细分合计与总量的差额必等于此式）----
    cancha = (shuru.xiuding_yongliang * shuru.shiji_chanliang - shuru.shiji_yongliang) * (shuru.biaozhun_danjia_fen - shuru.xiuding_danjia_fen)
    # 残差自检：细分合计换到总量口径（取负）减残差 == 原标准总。
    # 代数依据：−Σ细分 − 残差 = 原标准总（展开式可证；Holmes 例：
    # +234,000 − 4,000 = 230,000 ✓）——符号方向由 P3 性质测试再守一道。
    if -(jiage_guihua + jiage_zhixing + yongliang_guihua + yongliang_zhixing) - cancha != yuandan_zong:
        raise ChaifenCuowu('内部错误：残差关系不成立（−细分合计 − 残差 ≠ 原标准总）')
    return ChaifenJieguo(
        yuandan_zong_fen=yuandan_zong, yuandan_zong_fa=_fa_zong(yuandan_zong),
        guihua_zong_fen=guihua_zong, guihua_zong_fa=_fa_zong(guihua_zong),
        zhixing_zong_fen=zhixing_zong, zhixing_zong_fa=_fa_zong(zhixing_zong),
        jiage_guihua_fen=jiage_guihua, jiage_guihua_fa=_fa_xiangxi(jiage_guihua),
        jiage_zhixing_fen=jiage_zhixing, jiage_zhixing_fa=_fa_xiangxi(jiage_zhixing),
        yongliang_guihua_fen=yongliang_guihua, yongliang_guihua_fa=_fa_xiangxi(yongliang_guihua),
        yongliang_zhixing_fen=yongliang_zhixing, yongliang_zhixing_fa=_fa_xiangxi(yongliang_zhixing),
        cancha_fen=cancha,
        hengdengshi_chengli=True,  # 到这里恒等式已校验通过
    )
