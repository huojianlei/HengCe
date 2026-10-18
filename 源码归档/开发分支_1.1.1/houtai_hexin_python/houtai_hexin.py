# -*- coding: utf-8 -*-
"""后端核心 Python 版（houtai_hexin）—— 1.0.7 桌面版后端核心的可通读移植包。

包定位（与桌面运行时的关系）：
    本包只移植【编排层与 AI 边界层】两块桌面运行时里没有 Python 权威实现的代码：
        yinqing.py    ← desktop/engine.mjs（analyze 输入校验链、逐科目编排、
                        修订链式重算、组织单元识别/汇总、整改计数回算）
        ai_bianjie.py ← desktop/ai-boundary.mjs（AI 白名单结果 DTO 构造器）
    其余全部计算【不重写】：经 sys.path 引导直接 import
    D:/AppProject/开发分支_1.0.5/algo 的权威模块（rolling_budget/variance/
    planning_operational/loop_decision/building_blocks/bsc/kpi/suyuan/
    zhenggai/kanban/xishu/data_ingest/report_parse/zuzhi）。
    server.mjs 的 HTTP 壳层（路由/会话/文件落盘）不在本包范围。

总入口 analyze_subjects()（对应 server.mjs L208-216 /api/analyze-batch）：
    逐主体 fenxi() → zuzhi_huizong() 批次汇总，顺序与桌面版一致；
    一份输入工作簿 = 一个主体，主体名称写「机构/部门」时按层级归并。

使用示例（知识点速览，doctest 格式但需真实数据，故标记 SKIP）：

    >>> from houtai_hexin import fenxi, analyze_subjects, zhunbei_ai_qingqiu  # doctest: +SKIP
    >>> pici = analyze_subjects([shuru])      # 一份工作簿一个主体  # doctest: +SKIP
    >>> pici['zuzhi']['heji']['bumenShu']     # 批次内组织单元数      # doctest: +SKIP
    1

命名规范：标识符全拼音、数据值中文、文件名英文；金额=整数分、比率=整数基点。
建立：2026-10-11 ｜ 移植：ZCode（GLM-5.3）
"""

import sys
from pathlib import Path

# ======================================================================
# sys.path 引导（唯一一处）：把 algo 权威实现挂进搜索路径（幂等）
# ======================================================================
# 本包位于 开发分支_1.1.1/houtai_hexin_python/；algo 位于 开发分支_1.0.5/algo。
# 只做插入、不做写入；algo 目录全程只读。
ALGO_LUJING = Path(__file__).resolve().parents[2] / '开发分支_1.0.5' / 'algo'
if str(ALGO_LUJING) not in sys.path:
    sys.path.insert(0, str(ALGO_LUJING))

# ---- 编排层与 AI 边界层（本包新写的两个模块）----
from yinqing import (                                     # noqa: E402,F401
    YinqingCuowu, chongji, daoru_biaoge, fenxi, kemu_guilei,
    zhengshu, zuzhi_huizong, zuzhi_shibie,
)
from ai_bianjie import AI_JUJUE_WENAN, zhunbei_ai_qingqiu  # noqa: E402,F401


def analyze_subjects(shuru_lie):
    """批次总入口：逐主体分析 + 组织单元汇总（对齐桌面版 analyze()+zuzhi_huizong()）。

    对应 server.mjs L208-216 /api/analyze-batch 的计算主干：
        1. 逐份输入各跑一次 fenxi()（校验完全通过才产出结果——
           任何一份不合格整批抛错，与桌面"先验证后替换"同一纪律）；
        2. 全部结果交 zuzhi_huizong() 汇总组织单元层（部门行/机构小计/
           绝对偏差排行/期间分组）。

    参数：shuru_lie —— fenxi() 输入 dict 的列表（每份工作簿一个主体，不可为空）。

    返回：{'results': [fenxi() 结果…], 'zuzhi': zuzhi_huizong() 汇总}
        ——键名与 server.mjs L215 的 {results, zuzhi} 同名同义。
    """
    if not isinstance(shuru_lie, list) or not shuru_lie:
        # 文案对应 server.mjs L209（批次为空在入口即拒绝）
        raise YinqingCuowu('批次不能为空')
    jieguo_lie = [fenxi(shuru) for shuru in shuru_lie]
    return {'results': jieguo_lie, 'zuzhi': zuzhi_huizong(jieguo_lie)}
