# -*- coding: utf-8 -*-
r"""kb2 分类检索内核 —— 收入类 / 成本类提示词分表检索，落盘 JSON（v1）。

运行环境（注意）：必须用 kb\env 的 Python（kb/env/Scripts/python.exe）——
三路混合检索需要 numpy + onnxruntime（bge 向量）。

职责（用户指令 2026-08-30："收入类和成本类拆成两个表格……不用上真模型，
给我看向量库直接出来的"）：读判定系数包的提示词 → 按【来源科目的方向】
分成收入类/成本类两组 → 逐条真查 kb2（三路混合+RRF，原样保留命中路与
融合分）→ 落盘 检索结果-分类.json。排版（Word/PDF）由编排脚本完成。

分类口径（诚实声明）：
    · 红黄预警行：按来源科目方向——营收/服务收入/其他收入 = 收入类，
      其余（成本/费用/采购科目）= 成本类；
    · 结构性提示词（核心问题模块 = 采购模块）归入成本类表（来源列保留
      原始标签，透明可查）；单双环判定为综合语境，同样归入成本类表。
零模型：本脚本不触碰任何 LLM——表里的全部内容都是 kb2 检索原样输出。

用法：
    D:\AppProject\kb\env\Scripts\python.exe jiansuo_neihe.py
输出：..\testgen\shuchu\流水线结果\检索结果-分类.json
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CE_SHI_GEN = Path(__file__).resolve().parent.parent / 'testgen'
JIEGUO = CE_SHI_GEN / 'shuchu' / '流水线结果'

sys.path.insert(0, str(Path(__file__).resolve().parent))            # retrieval_adapter（本脚本未用，保持目录一致）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'kb2'))   # query_kb2

#: 收入类科目清单（与 algo/run_pipeline 的方向判定同一口径）
SHOURU_KEMU = ('营收', '服务收入', '其他收入')


def fenlei_laiyuan(laiyuan: str) -> str:
    """来源标签 → 分类（'红预警-办公费'→成本类；'核心问题模块'→成本类）。"""
    if '-' in laiyuan:                          # 预警行：看科目方向
        kemu = laiyuan.split('-', 1)[1]
        return '收入类' if kemu in SHOURU_KEMU else '成本类'
    return '成本类'                             # 结构性提示词（判定/核心模块）：综合语境归成本侧


def zhukong() -> int:
    """主流程：读系数包 → 分类 → 逐条直查 kb2（原样保留 RRF/命中路）→ 两表 JSON。

    可选参数：argv[1] = 系数包 JSON 路径（默认 判定系数-季度.json）；
              argv[2] = 输出 JSON 路径（默认 检索结果-分类.json）。
    """
    sys.stdout.reconfigure(encoding='utf-8')
    shuru_lu = Path(sys.argv[1]) if len(sys.argv) > 1 else JIEGUO / '判定系数-季度.json'
    shuchu_lu = Path(sys.argv[2]) if len(sys.argv) > 2 else JIEGUO / '检索结果-分类.json'
    xishu_miyao = json.loads(shuru_lu.read_text(encoding='utf-8'))
    chaxun_lie = [(t['laiyuan'], t['chaxun_ciyu']) for t in xishu_miyao['tishi_lie']]

    # 分类分组（保持系数包顺序——结构性在前、按严重度在后）
    fen_zu: dict[str, list[tuple[str, str]]] = {'收入类': [], '成本类': []}
    for laiyuan, ciyu in chaxun_lie:
        fen_zu[fenlei_laiyuan(laiyuan)].append((laiyuan, ciyu))

    from query_kb2 import jiansuo
    shuchu: dict[str, list] = {}
    zong_tiaoshu = 0
    for leibie, zu in fen_zu.items():
        hang_lie = []
        for laiyuan, ciyu in zu:
            # 逐条直查、原样保留 kb2 返回（zongfen/laiyuan_lu/neirong 一字不改）
            # ——本脚本是"向量库直出"演示，不做去重/融合，检索器给什么给什么
            ku_hang = jiansuo(chaxun=ciyu, shuliang=3)
            tiaowen = [{'dingwei': (f"{h['zhiyin_hao']}-{h['tiao_hao']}"
                                    + (f"-P{h['duan_hao']}" if h['duan_hao'] else '')),
                        'zhang_ming': h.get('zhang_ming') or '',
                        'laiyuan_lu': h['laiyuan_lu'], 'zongfen': h['zongfen'],
                        'neirong': h['neirong']} for h in ku_hang]
            hang_lie.append({'laiyuan': laiyuan, 'chaxun': ciyu, 'tiaowen': tiaowen})
            zong_tiaoshu += len(tiaowen)
        shuchu[leibie] = hang_lie
        print(f'[{leibie}] {len(zu)} 条提示词 → {zong_tiaoshu} 条片段（累计）')

    lu = shuchu_lu
    lu.write_text(json.dumps(shuchu, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'落盘：{lu}（两表共 {zong_tiaoshu} 条片段，kb2 检索原样输出，零模型）')
    return 0


if __name__ == '__main__':
    sys.exit(zhukong())
