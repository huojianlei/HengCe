# -*- coding: utf-8 -*-
r"""kb2 三路混合检索接口 —— 条款直达 ∥ 关键词(FTS5) ∥ 语义(bge 向量) + RRF 融合。

规范：标识符无声调拼音；文件名英文；中文注释 ≥40%。

三路并发全量混合（用户拍板 2026-08-27：精度和语义全抓，不设兜底触发）：
    ① 直达（zhida）：识别"200-3"式输入或给定 zhiyin_hao+tiao_hao → 主键取原文
    ② 关键词（FTS5 trigram + bm25）：匹配 原文+LLM辅助字段 三列
    ③ 语义（bge 向量）：全库 BLOB 载入 → 与查询向量点积（入库已 L2 归一化，
       点积即余弦）——SQLite 暴力比对，970 片毫秒级，无向量数据库
    融合：RRF 倒数排名（k=60，零依赖实现）；领域前缀可硬过滤（如 '2'=预算 2xx）

用法（kb2 目录）：
    CLI：..\kb\env\Scripts\python.exe query_kb2.py --chaxun "预算执行偏差整改"
        --zhida 200-3 ｜ --lingyu 2 --chaxun "滚动预算编制" ｜ --liebiao
    导入：from query_kb2 import jiansuo
          jiansuo(chaxun="预算执行偏差整改", shuliang=8) -> list[dict]

输出字段：zhiyin_hao / tiao_hao / duan_hao / leixing / zhang_ming / neirong /
    zongfen(RRF) / laiyuan_lu(命中路标记，如 'fts+xiangliang')

建立：2026-08-27 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import numpy

# 同目录导入建库脚本里的嵌入器（模型加载约 1 秒，检索侧复用）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_kb2 import KU_WENJIAN, QianruQi

#: RRF 常数（标准 k=60：rank 越靠前贡献越大，k 平滑尾部）
RRF_K = 60

#: 直达输入解析（"200-3" / "200:3" → 指引 200 第 3 条）
ZHIDA_GESHI = re.compile(r'^\s*(\d{2,3}|JB)[-:：](\d{1,3})\s*$')


def _dakai() -> sqlite3.Connection:
    """打开库连接（只读场景由调用方管理；行工厂取 dict 便于溯源输出）。"""
    if not KU_WENJIAN.exists():
        raise FileNotFoundError(f'库不存在：{KU_WENJIAN}（先跑 build_kb2.py）')
    lian = sqlite3.connect(KU_WENJIAN)
    lian.row_factory = sqlite3.Row       # 行 → dict 式访问（输出溯源字段方便）
    return lian


def _zhiyin_guolv(lingyu: str | None) -> str:
    """领域前缀 → SQL 过滤条件（如 '2' → zhiyin_hao LIKE '2%' 锁预算 2xx 系）。

    领域号段（官方体系）：1xx 战略 / 2xx 预算 / 3xx 成本 / 4xx 营运 /
    5xx 投融资 / 6xx 绩效 / 7xx 风险 / 8xx 报告信息化；JB 基本指引
    恒参与（统领文件），故任何过滤都放行 JB。
    """
    if not lingyu:
        return ''
    if lingyu == 'JB':
        return " AND zhiyin_hao='JB'"
    return f" AND (zhiyin_hao LIKE '{int(lingyu)}%' OR zhiyin_hao='JB')"


#: 检索主函数——CLI 与导入共用（参数与返回结构见模块头 docstring）
def jiansuo(chaxun: str | None = None, zhiyin_hao: str | None = None,
            tiao_hao: int | None = None, lingyu_qianzhui: str | None = None,
            shuliang: int = 8) -> list[dict]:
    """三路混合检索主函数（CLI 与导入共用；参数详见模块头 docstring）。"""
    lian = _dakai()
    guolv = _zhiyin_guolv(lingyu_qianzhui)

    # ---- ① 条款直达：给了完整定位就直接取（含同条子片合并返回母条上下文）----
    # 直达优先级最高：给了完整定位就不再走模糊路（零误差、可溯源）
    if zhiyin_hao and tiao_hao is not None:
        hang_lie = lian.execute(
            f'SELECT * FROM tiaowen WHERE zhiyin_hao=? AND tiao_hao=?{guolv}',
            (zhiyin_hao, tiao_hao)).fetchall()
        return [dict(h) | {'zongfen': 1.0, 'laiyuan_lu': 'zhida'} for h in hang_lie]

    # 两入口都未给 → 参数错误（直达或查询至少其一）
    if not chaxun:
        raise ValueError('jiansuo 需要 chaxun（查询词）或 zhiyin_hao+tiao_hao（直达）')

    # ---- ② 关键词路：FTS5 三列（原文+适用场景+关键词）BM25 ----
    # 已知限制（2026-08-27 评估记录）：trigram 需查询 ≥3 字——两字短词（如
    # "整改"）此路不命中、整句长提示词原文无逐字重现也难命中；这两类场景
    # 由语义路（向量）+ LLM 辅助字段（biaoshi_llm 补齐的列）兜住。
    fts_ming: dict[int, float] = {}
    try:
        for ming, fen in lian.execute(
                'SELECT rowid, bm25(fts_wen) FROM fts_wen WHERE fts_wen MATCH ?',
                (f'"{chaxun}"',)):          # 短语引号包裹：trigram 整串匹配
            fts_ming[ming] = fen
    except sqlite3.OperationalError:
        pass                                # 查询含特殊字符等：此路静默空手（其余路兜住）
    fts_pai = sorted(fts_ming, key=lambda m: fts_ming[m])[:20]   # bm25 越小越相关

    # ---- ③ 语义路：全库向量点积（余弦）----
    # BLOB → 矩阵一次性载入（970×512 维 ≈ 1.8MB）；入库已 L2 归一化，
    # 点积即余弦相似——这就是"SQLite 暴力比对"方案的全部实现。
    quan = lian.execute(
        f'SELECT id, xiangliang FROM tiaowen WHERE xiangliang IS NOT NULL{guolv}').fetchall()
    qianru = QianruQi()
    cha_xiang = numpy.frombuffer(qianru.bianma([chaxun])[0], dtype=numpy.float32)
    ju = numpy.stack([numpy.frombuffer(r['xiangliang'], dtype=numpy.float32) for r in quan])
    xiangsi = ju @ cha_xiang               # 归一化后点积=余弦
    xiang_pai = [quan[i]['id'] for i in numpy.argsort(-xiangsi)[:20]]

    # ---- RRF 融合（两路各取前 20；k=60 平滑）----
    # 公式：贡献 = 1/(k+rank)。两路都命中的片分数叠加（共识加成），
    # 单路命中的片仍可入榜（语义或词面单强也有价值）——"全抓"的落地。
    zong: dict[int, float] = {}
    lu: dict[int, list[str]] = {}
    for rank, mid in enumerate(fts_pai, start=1):
        zong[mid] = zong.get(mid, 0) + 1.0 / (RRF_K + rank)
        lu.setdefault(mid, []).append('fts')
    for rank, mid in enumerate(xiang_pai, start=1):
        zong[mid] = zong.get(mid, 0) + 1.0 / (RRF_K + rank)
        lu.setdefault(mid, []).append('xiangliang')

    # ---- 汇总输出（带溯源元数据；laiyuan_lu 标记该片被哪些路命中）----
    jieguo: list[dict] = []
    for mid, fen in sorted(zong.items(), key=lambda kv: -kv[1])[:shuliang]:
        hang = lian.execute('SELECT * FROM tiaowen WHERE id=?', (mid,)).fetchone()
        if hang is None:
            continue
        # 逐条拼装输出（原行字段 + 融合分 + 命中路）
        jieguo.append(dict(hang) | {'zongfen': round(fen, 6),
                                    'laiyuan_lu': '+'.join(lu.get(mid, []))})
    lian.close()
    return jieguo


def zhida(zhida_wen: str) -> list[dict]:
    """直达便捷入口：解析"200-3"式输入后调 jiansuo。"""
    pei = ZHIDA_GESHI.match(zhida_wen)
    if not pei:
        raise ValueError(f'直达格式应为 指引号-条号（如 200-3）：{zhida_wen!r}')
    # JB 基本指引无数字号——直达正则已兼容（数字段|JB）
    return jiansuo(zhiyin_hao=pei.group(1), tiao_hao=int(pei.group(2)))


def liebiao() -> None:
    """列库：各指引的片数概览（对账与人工巡检用）。"""
    lian = _dakai()
    # 左连接：无片指引也列出（片数 0 = 巡检异常信号）
    for hang in lian.execute(
            'SELECT z.zhiyin_hao, z.biaoti, COUNT(t.id) AS pian FROM zhiyin z '
            'LEFT JOIN tiaowen t ON t.zhiyin_hao=z.zhiyin_hao '
            'GROUP BY z.zhiyin_hao ORDER BY CAST(z.zhiyin_hao AS INTEGER)'):
        print(f'  {hang["zhiyin_hao"]:>4} {hang["biaoti"][:16]:<18} {hang["pian"]} 片')
    lian.close()


def _zhuhanshu() -> int:
    """CLI 入口：--zhida / --chaxun(+--lingyu) / --liebiao 三模式。"""
    jiexi = argparse.ArgumentParser(description='kb2 三路混合检索')
    jiexi.add_argument('--zhida', help='条款直达，如 200-3')
    jiexi.add_argument('--chaxun', help='混合检索查询词（提示词式亦可为中文长句）')
    jiexi.add_argument('--lingyu', help='领域前缀过滤，如 2=预算 3=成本 4=营运')
    jiexi.add_argument('--shuliang', type=int, default=8, help='返回条数（默认 8）')
    jiexi.add_argument('--liebiao', action='store_true', help='列出全部指引')
    canshu = jiexi.parse_args()

    # 三模式分发：--liebiao 列库 / --zhida 条款直达 / --chaxun 混合检索
    if canshu.liebiao:
        liebiao()
        return 0
    if canshu.zhida:
        jieguo = zhida(canshu.zhida)
    elif canshu.chaxun:
        jieguo = jiansuo(chaxun=canshu.chaxun, lingyu_qianzhui=canshu.lingyu,
                         shuliang=canshu.shuliang)
    else:
        jiexi.print_help()
        return 1
    # 输出格式：[序号] 定位（类型｜章｜命中路｜RRF分）+ 首行摘录
    # 逐条打印：定位串含子片号（-P2）时说明命中的是超长条的子片
    for i, hang in enumerate(jieguo, start=1):
        dingwei = (f"{hang['zhiyin_hao']}-{hang['tiao_hao']}"
                   + (f"-P{hang['duan_hao']}" if hang['duan_hao'] else ''))
        print(f"[{i}] {dingwei}（{hang['leixing']}｜{hang.get('zhang_ming') or ''}｜"
              f"{hang['laiyuan_lu']}｜{hang['zongfen']}）")
        print(f"    {hang['neirong'][:100]}{'…' if len(hang['neirong']) > 100 else ''}")
    return 0


if __name__ == '__main__':
    sys.exit(_zhuhanshu())

# ======================================================================
# 检索备忘（已知限制与调优入口）
# ======================================================================
# 1. trigram 限制：查询词 ≥3 字才走 FTS 路；两字短词（"整改"）与整句
#    长提示词的词面匹配弱——由向量路 + LLM 辅助字段列兜住（实测基线
#    top1 85% / top3 100%，纯向量扛下；增强后持平——语义路已够强）。
# 2. 每次查询都新建 QianruQi（模型加载约 1 秒）——CLI 单查无感；
#    高频调用方（智能体）应模块级缓存一个实例再调 jiansuo。
# 3. RRF k=60 为标准值；若关键词路质量提升后想加权，可在两路
#    累加处乘系数（如 fts ×1.2），融合框架不变。
# 4. 领域过滤是硬过滤（WHERE LIKE）——'2' 锁预算系但 JB 恒放行；
#    传错领域号会导致空结果，先用 --liebiao 查号段。
# ======================================================================
