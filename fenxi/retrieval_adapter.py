# -*- coding: utf-8 -*-
"""检索适配层 —— M5 分析层的第②步：判定系数提示词 → kb2 条文片段（TODO 计划②）。

定位（分析层六步计划 2026-08-30 用户拍板"执行"）：算法层产出判定系数包
（algo/xishu.py，已含"系数→检索提示词"映射），本模块把每条提示词真正
喂给 kb2 三路混合检索，把返回的库行归一化为【条文片段】并做条号预校验——
给分析生成器（analysis_generator）递料。

注入式依赖（与 algo/llm_clean 的模型注入同一手法，可离线测试）：
    检索函数由调用方注入——生产接线（pipeline_m5）注入 kb2 的
    query_kb2.jiansuo（需 kb/env 的 numpy+onnxruntime）；测试注入假函数。
    本模块【不 import kb2】，运行环境与 kb2 解耦。

归一化口径：
    · 片段定位串 = '指引号-条号'（子片加 '-P段号'）——这是全链路的
      条号引用格式，分析生成的引用校验以此为准；
    · 同一定位串去重（不同提示词可能命中同一条文，首见者保留并记全部
      来源查询）；
    · 单条查询检索失败（库缺失/网络/参数）不中断——记入失败清单继续，
      全部失败时调用方按"未检索到"口径降级（RAG 方案 §4 第 3 条）。

命名规范：标识符无声调拼音；文件名英文；数据值中文。
纯函数：无 I/O、无全局状态（检索函数是注入的参数）。

使用示例（知识点速览；doctest 格式，tests 守护）：

    知识点 1 · 两条提示词 → 六条片段 → 同条文去重
    >>> from retrieval_adapter import jiansuo_xishu
    >>> def jia_jiansuo(chaxun, shuliang=8):
    ...     return [{'zhiyin_hao': '200', 'tiao_hao': 3, 'duan_hao': None,
    ...              'zhang_ming': '预算执行', 'neirong': '企业应当建立预算执行分析制度。'}]
    >>> jieguo = jiansuo_xishu(['预算调整 审批程序', '采购成本控制 制度'], jia_jiansuo)
    >>> len(jieguo.tiaowen_lie)
    1
    >>> jieguo.tiaowen_lie[0].dingwei
    '200-3'
    >>> jieguo.tiaowen_lie[0].laiyuan_ciyu
    ['预算调整 审批程序', '采购成本控制 制度']

    知识点 2 · 检索函数抛异常 → 记入失败清单，不中断
    >>> def huai_jiansuo(chaxun, shuliang=8):
    ...     raise FileNotFoundError('库不存在')
    >>> jieguo2 = jiansuo_xishu(['预算调整 审批程序'], huai_jiansuo)
    >>> (len(jieguo2.tiaowen_lie), jieguo2.shibai_lie[0][0])
    (0, '预算调整 审批程序')

命名对照表（拼音标识符 → 中文含义）：
    jiansuo_xishu       检索系数（主函数：提示词列表 → 条文片段）
    TiaowenXiang        条文片段（定位/出处/原文/来源查询）
    JianSuoJieguo       检索结果（片段元组 + 失败清单）
    _guifan_dingwei     规范定位（'指引-条' + 可选 '-P段'）
    chaxun_lie          查询串列表（来自判定系数包 tishi_lie）
    jiansuo_hanshu      检索函数（Callable 注入；生产=kb2.jiansuo）
    mei_ci_shuliang     每次查询返回条数（默认 3——top 片段够拼依据）
    shibai_lie          失败清单（查询串, 原因）——降级韧性的事实记录

口径依据：分析层六步计划②（用户拍板 2026-08-30）；kb2/RAG部署与使用方案.md
         §6（系数→提示词→驱动检索）与 §4（引用条号必须存在的预校验端）；
         algo/xishu.py（提示词的上游生产者）。
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

from dataclasses import dataclass


def _guifan_dingwei(zhiyin_hao: str, tiao_hao: int, duan_hao) -> str:
    """规范定位串：'指引-条'，超长条的子片加 '-P段号'——全链路条号引用格式。"""
    dingwei = f'{zhiyin_hao}-{tiao_hao}'
    if duan_hao:
        dingwei += f'-P{duan_hao}'
    return dingwei


@dataclass(frozen=True)
class TiaowenXiang:
    """一条检索到的条文片段（分析生成器【依据】区的最小单元）。"""

    laiyuan_ciyu: list   # 命中本片段的查询串列表（首见者在前）
    dingwei: str         # 规范定位串（'200-3' / '200-3-P2'）——引用校验的键
    zhiyin_hao: str      # 指引号
    tiao_hao: int        # 条号
    duan_hao: int | None  # 子片段号（超长条切分；无子片为 None）
    zhang_ming: str      # 章名（出处的可读描述）
    neirong: str         # 条文原文（进提示词【依据】区，数字溯源的允许源）


@dataclass(frozen=True)
class JianSuoJieguo:
    """检索适配结果：归一化片段 + 逐查询失败清单（全失败 = 调用方降级）。"""

    tiaowen_lie: tuple            # TiaowenXiang 元组（按首次命中顺序、去重）
    shibai_lie: tuple             # (查询串, 失败原因) 元组


def jiansuo_xishu(chaxun_lie: list[str], jiansuo_hanshu, mei_ci_shuliang: int = 3) -> JianSuoJieguo:
    """检索系数主函数：逐条提示词调注入的检索函数，归一化去重。

    流程：每条查询串 → jiansuo_hanshu(chaxun=查询串, shuliang=每次数) →
    库行字典 → TiaowenXiang（定位串去重，同片段累计来源查询）；
    单条失败记入 shibai_lie 继续——检索是"尽力而为"，失败的事实
    留给降级链路，不让一条查询炸掉整个分析。
    """
    pian_lie: list[TiaowenXiang] = []
    shibai_lie: list[tuple[str, str]] = []
    suoyin: dict[str, int] = {}           # 定位串 → 片段下标（去重用）
    for ciyu in chaxun_lie:
        try:
            ku_hang_lie = jiansuo_hanshu(chaxun=ciyu, shuliang=mei_ci_shuliang)
        except Exception as cuo:          # 库缺失/模型加载失败/参数问题——一律降级记录
            shibai_lie.append((ciyu, str(cuo)))
            continue
        for hang in ku_hang_lie:
            dingwei = _guifan_dingwei(hang['zhiyin_hao'], hang['tiao_hao'],
                                      hang.get('duan_hao'))
            if dingwei in suoyin:         # 同片段：只累计来源查询，不重复收录
                pian_lie[suoyin[dingwei]].laiyuan_ciyu.append(ciyu)
                continue
            xiang = TiaowenXiang(
                laiyuan_ciyu=[ciyu], dingwei=dingwei,
                zhiyin_hao=hang['zhiyin_hao'], tiao_hao=hang['tiao_hao'],
                duan_hao=hang.get('duan_hao'), zhang_ming=hang.get('zhang_ming') or '',
                neirong=hang['neirong'])
            suoyin[dingwei] = len(pian_lie)
            pian_lie.append(xiang)
    return JianSuoJieguo(tiaowen_lie=tuple(pian_lie), shibai_lie=tuple(shibai_lie))
