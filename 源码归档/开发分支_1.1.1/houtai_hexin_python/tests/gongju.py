# -*- coding: utf-8 -*-
"""tests.gongju —— 测试夹具工具（构建桌面 API 同形的标准输入 dict）。

设计原则：
    1. 记录一律经 algo data_ingest.daoru_csv 真实导入（不手搓 DaoruJieguo，
       让导入链的清洗/换算一起被冒烟到）；
    2. 期望值全部手工验算写死（engine.mjs 口径），禁止用实现反推；
    3. 夹具默认数据（可按用例覆盖）：
           预算：营业收入 100.00 元/月 × 12 个月（=10000 分/月）；
           实际：2025-01 = 110.00 元、2025-02 = 90.00 元；
           增长率 0 基点、月度、分析期间 2025-02；
           预警档位 黄 500 / 红 1000 基点（区别于 algo 默认 1500/3000，
           以证明档位真正来自页面配置）。
"""

import sys
from pathlib import Path

# 防御性引导：无论从哪个目录起跑，包根（houtai_hexin_python/）都在搜索路径上
BAO_GEN = Path(__file__).resolve().parents[1]
if str(BAO_GEN) not in sys.path:
    sys.path.insert(0, str(BAO_GEN))

from yinqing import daoru_biaoge  # noqa: E402  复用导入回退链的正路

#: 标准 8 列表头（与 algo data_ingest.BIXU_LIE 逐字一致）
BIAOTOU = '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'


def _hang(leibie, qijian, kemu, shuzhi, danwei='元'):
    """拼一行标准 8 列 CSV 文本（数值按单位写两位小数）。"""
    return f'{leibie},{qijian},{kemu},{shuzhi},{danwei},测试夹具,2025-12-31,'


def biaozhun_jilu(kemu='营业收入', yusuan_yue=100.00, shiji=None):
    """构建标准记录：12 个月预算 + 已届满月份实际（默认 1 月 110 / 2 月 90 元）。

    返回 daoru_biaoge() 的产物（DaoruJieguo 实例）——刻意走真实导入链，
    测试因此同时冒烟 data_ingest 的清洗与换算。
    """
    shiji = shiji if shiji is not None else {'2025-01': 110.00, '2025-02': 90.00}
    hang = [BIAOTOU]
    for yue in range(1, 13):
        hang.append(_hang('预算基础', f'2025-{yue:02d}', kemu, f'{yusuan_yue:.2f}'))
    for qijian, zhi in sorted(shiji.items()):
        hang.append(_hang('实时经营', qijian, kemu, f'{zhi:.2f}'))
    return daoru_biaoge('\n'.join(hang))


def biaozhun_shuru(**gaixie):
    """构建 fenxi() 的标准输入 dict（任何字段可用关键字覆盖）。

    默认口径见模块头注；subjects 只登记一个收入科目。
    """
    shuru = {
        'company': '测试公司',
        'metadata': {'主体名称': '测试公司/财务部', '主体编码': 'CS-001',
                     '情景名称': '基础情景', '情景编码': 'QJ-001'},
        'records': biaozhun_jilu(),
        'subjects': [{'kemu': '营业收入', 'module': '收入模块', 'direction': '收入类'}],
        'config': {'cycle': '月度', 'period': '2025-02', 'growth': 0,
                   'industry': None, 'industryCorrection': False,
                   'industryThreshold': 50, 'noise': 2500, 'significance': 2500,
                   'tiers': [{'ming_cheng': '黄', 'yan_se': '#FFAA00', 'yu_fen': 500},
                             {'ming_cheng': '红', 'yan_se': '#FF0000', 'yu_fen': 1000}]},
        'bsc': None, 'kpi': {}, 'traces': [], 'splits': [], 'events': [],
        'baselines': [], 'changeStatus': None,
    }
    shuru.update(gaixie)
    return shuru
