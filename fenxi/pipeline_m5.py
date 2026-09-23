# -*- coding: utf-8 -*-
r"""M5 分析层接线 —— 第⑥步：读判定系数包 → 真·kb2 检索 → 分析生成 → 落盘文案。

运行环境（注意）：**必须用 kb\env 的 Python**（kb/env/Scripts/python.exe）——
kb2 检索需要 numpy + onnxruntime（bge 向量）；本脚本自身零第三方依赖。

输入（run_pipeline.py 的落盘产物，两级流水线的接缝文件）：
    ..\testgen\shuchu\流水线结果\判定系数-季度.json   ← algo/xishu 的系数包
    ..\testgen\shuchu\流水线结果\看板数据-季度.json   ← 整改清单来源
输出：
    ..\testgen\shuchu\流水线结果\分析文案-季度.json   ← 结构化（程序可读）
    ..\testgen\shuchu\流水线结果\分析文案-季度.md     ← 渲染版（人可读）

模型模式（自动判断）：
    环境变量 FINAGENT_API_KEY 存在 → 真模型（algo/model_api，DeepSeek）
    不存在 → moxing_hanshu=None → 分析生成器自动降级（'— 待 AI 分析'），
    但【检索是真实的】——系数→kb2 查询→条文片段整条链路照样验证。

用法（kb2 环境下）：
    D:\AppProject\kb\env\Scripts\python.exe pipeline_m5.py
    FINAGENT_API_KEY=sk-xxx D:\AppProject\kb\env\Scripts\python.exe pipeline_m5.py
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CE_SHI_GEN = Path(__file__).resolve().parent.parent / 'testgen'
JIEGUO = CE_SHI_GEN / 'shuchu' / '流水线结果'

sys.path.insert(0, str(Path(__file__).resolve().parent))            # fenxi 本目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'kb2'))   # query_kb2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'algo'))  # model_api

from analysis_generator import shengcheng_fenxi                     # noqa: E402
from retrieval_adapter import jiansuo_xishu                         # noqa: E402


def zhukong() -> int:
    """M5 主流程：系数包 → 检索适配（真 kb2）→ 分析生成（真模型或降级）→ 落盘。"""
    sys.stdout.reconfigure(encoding='utf-8')

    # ---- [1] 读接缝文件：系数包 + 整改清单 ----
    xishu_miyao = json.loads((JIEGUO / '判定系数-季度.json').read_text(encoding='utf-8'))
    kanban = json.loads((JIEGUO / '看板数据-季度.json').read_text(encoding='utf-8'))
    zhenggai_lie = kanban['zhenggai_block']['qingdan']
    chaxun_lie = [t['chaxun_ciyu'] for t in xishu_miyao['tishi_lie']]
    print(f'[1] 读接缝文件：系数包 {len(chaxun_lie)} 条提示词、整改清单 {len(zhenggai_lie)} 条')

    # ---- [2] 检索适配：真 kb2 三路混合检索（注入 jiansuo）----
    from query_kb2 import jiansuo
    jian = jiansuo_xishu(chaxun_lie, jiansuo, mei_ci_shuliang=3)
    print(f'[2] 检索适配：命中 {len(jian.tiaowen_lie)} 条片段、失败 {len(jian.shibai_lie)} 条查询')
    for t in jian.tiaowen_lie[:5]:
        print(f'    [{t.dingwei}] {t.neirong[:48]}…' if len(t.neirong) > 48
              else f'    [{t.dingwei}] {t.neirong}')
    if len(jian.tiaowen_lie) > 5:
        print(f'    …（其余 {len(jian.tiaowen_lie) - 5} 条见落盘 JSON）')

    # ---- [3] 分析生成：真模型（有 Key）或自动降级（无 Key）----
    import os
    miyao = os.environ.get('FINAGENT_API_KEY')
    if miyao:
        from model_api import chuangjian_moxing_hanshu
        moxing = chuangjian_moxing_hanshu(api_miyao=miyao)
        print('[3] 分析生成：真模型模式（DeepSeek，密钥来自环境变量）')
    else:
        moxing = None
        print('[3] 分析生成：降级模式（未设置 FINAGENT_API_KEY——检索真实、文案占位）')
    fenxi = shengcheng_fenxi(xishu_miyao, [t.__dict__ if hasattr(t, '__dict__')
                                           else t for t in jian.tiaowen_lie],
                             zhenggai_lie, moxing)
    # TiaowenXiang 是 frozen dataclass——转 dict 供生成器按字典取字段
    print(f'[4] 校验闸门：状态 {fenxi.zhuangtai}｜解读 {fenxi.jiedu_jiaoyan}｜'
          f"文案 {sum(1 for w in fenxi.wenan_lie if w.jiaoyan == '通过')}"
          f'/{len(fenxi.wenan_lie)} 通过')

    # ---- [5] 落盘：结构化 JSON + 渲染 md（中文名，人机两份） ----
    shuchu = {
        'zhuangtai': fenxi.zhuangtai,
        'jiedu': fenxi.jiedu,
        'jiedu_jiaoyan': fenxi.jiedu_jiaoyan,
        'wenan_lie': [{'xuhao': w.xuhao, 'leixing': w.leixing,
                       'zeren_mokuai': w.zeren_mokuai, 'wenan': w.wenan,
                       'jiaoyan': w.jiaoyan, 'weijin_lie': list(w.weijin_lie)}
                      for w in fenxi.wenan_lie],
    }
    json_lu = JIEGUO / '分析文案-季度.json'
    json_lu.write_text(json.dumps(shuchu, ensure_ascii=False, indent=2), encoding='utf-8')
    md_hang = [f'# 分析文案（M5 分析层 · 状态 {fenxi.zhuangtai}）', '',
               '## 报告解读', '', fenxi.jiedu, '', '## 整改建议', '']
    for w in fenxi.wenan_lie:
        md_hang.append(f"### {w.xuhao}. [{w.leixing}｜{w.zeren_mokuai}]（{w.jiaoyan}）")
        md_hang += ['', w.wenan, '']
    md_lu = JIEGUO / '分析文案-季度.md'
    md_lu.write_text('\n'.join(md_hang), encoding='utf-8')
    print(f'[5] 落盘：{json_lu.name} + {md_lu.name}（分析层产物，中文名）')

    # ---- [6] 接入计算报告：真模型模式下把解读层贴到报告 md 末尾 ----
    # （降级模式不贴——'— 待 AI 分析'进正式报告是噪声；Word 版重生成由
    #   run_pipeline 全链承担，此处只补 md 的解读层演示接入闭环）
    if fenxi.zhuangtai != '降级':
        baogao_lu = JIEGUO / '计算报告-季度.md'
        if baogao_lu.exists():
            baogao_wen = baogao_lu.read_text(encoding='utf-8')
            if 'AI 分析解读' not in baogao_wen:      # 幂等：重跑不重复贴
                baogao_wen += ('\n\n---\n\n# AI 分析解读（M5 分析层）\n\n'
                               + fenxi.jiedu + '\n\n## 逐条整改建议\n\n'
                               + '\n\n'.join(f"**{w.xuhao}. [{w.leixing}｜"
                                             f"{w.zeren_mokuai}]（{w.jiaoyan}）**\n\n{w.wenan}"
                                             for w in fenxi.wenan_lie) + '\n')
                baogao_lu.write_text(baogao_wen, encoding='utf-8')
                print(f'[6] 接入：解读层已追加至 {baogao_lu.name}')
            else:
                print('[6] 接入：报告已含解读层（幂等跳过）')
    else:
        print('[6] 接入：降级模式跳过（真模型运行后自动贴入报告）')
    return 0


if __name__ == '__main__':
    sys.exit(zhukong())
