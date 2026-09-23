# -*- coding: utf-8 -*-
r"""模块整合报告 —— 按算法模块三段式：数据表 · 分析内容 · 依据条例。

模块口径（用户拍板 2026-08-31 二次修正）：模块 = FinAgent 算法链的那
"一大堆"——滚动预算、差异分析、多专业分析、单双环分析、积木分析、
平衡计分卡、KPI、经营变更双向溯源、整改清单与预警；收入与成本分开
（数据表原样带方向列；依据条例每模块分【收入类】【成本类】两组）。
PDF 最末尾注明"内容为 AI 生成，仅供参考"。

每节固定三段：
    数据表   = run_pipeline 计算报告对应单元的原样块（忠实计算输出，不重算）
    分析内容 = DeepSeek 按该模块数据现写（数字溯源校验：只许照抄数据表数字；
               未设 FINAGENT_API_KEY 时整段降级占位）
    依据条例 = 模块主题提示词（收入类/成本类各一）真查 guanli_ku v3.0，
               每条独立成段，出处行统一：出处 N：《指引全称》第Y条（定位 …）

运行环境：kb\env（检索向量依赖 + model_api）。测试运行走
testgen\真模型测试启动器.py（Key 注入环境变量，正式程序只认输入口）：
    kb\env\Scripts\python.exe testgen\真模型测试启动器.py zhenghe_baogao.py
产物：shuchu\流水线结果\模块分析报告-季度.md / .pdf
建立：2026-08-31 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

BEN_MU = Path(__file__).resolve().parent
APP = BEN_MU.parent
JIEGUO = APP / 'testgen' / 'shuchu' / '流水线结果'
KU_LU = APP / 'kb2' / 'guanli_ku.sqlite'
XT_PY = r'D:\dev-env\Python312\python.exe'          # 系统 Python（有 python-docx）

sys.path.insert(0, str(APP / 'algo'))
sys.path.insert(0, str(APP / 'kb2'))
sys.path.insert(0, str(BEN_MU))

from analysis_generator import _QIANFEN_ZE, _SHUZI_ZE, _shuzi_guifan   # noqa: E402
from model_api import chuangjian_moxing_hanshu                          # noqa: E402
from query_kb2 import jiansuo                                           # noqa: E402

#: 模块定义（计算报告提取前缀, 展示名, (收入类提示词, 成本类提示词)）
MO_KUAI = [
    (('单元 2',), '滚动预算',
     ('滚动预算 预算编制 收入 目标 预测', '滚动预算 预算调整 成本 费用 控制')),
    (('单元 3',), '差异分析',
     ('收入 预算差异 分析 报告 评价', '成本差异 计算 分析 标准 成本控制')),
    (('单元 4',), '多专业分析（规划/执行拆分）',
     ('预算 目标分解 规划 指标 分配', '预算执行 控制 成本中心 责任')),
    (('单元 5',), '单双环分析',
     ('预算管理 纠偏 机制 闭环 审批', '预算控制 偏差 纠正 措施 预警')),
    (('单元 6',), '积木分析（价差/量差）',
     ('收入 差异 价格 数量 销售 分析', '标准成本 价格差异 数量差异 直接材料')),
    (('单元 7',), '平衡计分卡（BSC）',
     ('平衡计分卡 财务维度 指标 评价', '平衡计分卡 客户 内部流程 学习成长 维度')),
    (('附表 A',), 'KPI 指标分析',
     ('关键绩效指标 考核 评价 目标', '绩效 考核 指标 责任中心 管理')),
    (('单元 8',), '经营变更双向溯源分析',
     ('预算调整 审批 权限 程序 条件', '成本 变动 原因 追溯 分析')),
    (('附表 B', '附表 C'), '整改清单与预警',
     ('预算 偏差 整改 改进 措施', '超预算 预算外 审批 管控 风险')),
]
SHU = '零一二三四五六七八九'


def _tiaohao_zh(n: int) -> str:
    """条号数字 → 公文汉字（1-99）。"""
    if n < 10:
        return SHU[n]
    if n < 20:
        return '十' + (SHU[n - 10] if n > 10 else '')
    shi, ge = divmod(n, 10)
    return SHU[shi] + '十' + (SHU[ge] if ge else '')


def du_zhiyin() -> dict[str, str]:
    """zhiyin 表 → {指引号: 指引名}（文号库中未填，出处不硬编）。"""
    lian = sqlite3.connect(str(KU_LU))
    jie = dict(lian.execute('SELECT zhiyin_hao, biaoti FROM zhiyin'))
    lian.close()
    return jie


def ti_kuai(wen: str, qianzhui_lie: tuple[str, ...]) -> str:
    """从计算报告 md 提取 '## 前缀' 块（到下一个标题为止），多前缀合并。

    坑（2026-08-31）：此正则不能写在 f-string 里——`{1,2}` 会被 f-string
    当占位符求值成字面 '1,2'，前瞻失效，块一路吃到文末污染下游全部模块。
    """
    kuai_lie = []
    for qianzhui in qianzhui_lie:
        zheng = re.compile('^## ' + re.escape(qianzhui)
                           + r'[^\n]*\n(.*?)(?=^#{1,2} |\Z)', re.M | re.S)
        m = zheng.search(wen)
        kuai_lie.append(m.group(1).strip() if m else f'（计算报告中未找到「{qianzhui}」）')
    return '\n\n'.join(kuai_lie)


def jiao_yan_shuzi(wenben: str, shuju_kuai: str) -> tuple[str, tuple]:
    """模块解读的数字溯源：文案数字 ⊆ 数据表数字（模块解读不引条文）。"""
    yunxu = {_shuzi_guifan(s) for s in _SHUZI_ZE.findall(_QIANFEN_ZE.sub('', shuju_kuai))}
    weijin = [s for s in _SHUZI_ZE.findall(_QIANFEN_ZE.sub('', wenben))
              if _shuzi_guifan(s) not in yunxu]
    return ('拒绝', tuple(f'未溯源数字 {s}' for s in weijin)) if weijin else ('通过', ())


def mo_tishi(zhanshi: str, shuju_kuai: str) -> str:
    """单模块分析提示词：只依据模块数据、只照抄数字、不引条文。"""
    return ('你是企业预算管理分析师。只依据下方【模块数据】作答，'
            '禁止使用任何外部知识，禁止引用任何条文条号。\n\n'
            f'【模块】{zhanshi}\n【模块数据】\n{shuju_kuai[:2200]}\n\n'
            '【任务】结合数据写一段分析解读（3-6 句）：点出关键数字与结论，'
            '指出需要关注的风险或下一步动作。\n'
            '铁律：数字必须原样照抄【模块数据】，禁止换算、四舍五入、编造；'
            '不引用条文条号；数据缺失的维度明确写"缺数"。')


def zhenghe() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    baogao_lu = JIEGUO / '计算报告-季度.md'
    if not baogao_lu.exists():
        print('缺 计算报告-季度.md（先跑 testgen/run_pipeline.py）')
        return 1
    baogao = baogao_lu.read_text(encoding='utf-8')
    zhiyin_ming = du_zhiyin()
    miyao = os.environ.get('FINAGENT_API_KEY')
    moxing = (chuangjian_moxing_hanshu(api_miyao=miyao, chaozhi_miao=120)
              if miyao else None)
    print(f"[0] 模型模式：{'真模型（DeepSeek）' if moxing else '降级（未设 FINAGENT_API_KEY）'}")

    # ---- [1] 逐模块：数据块 → 检索（收入/成本两组）→ AI 分析 ----
    jie_lie = []
    for qianzhui_lie, zhanshi, (t_shouru, t_chengben) in MO_KUAI:
        shuju_kuai = ti_kuai(baogao, qianzhui_lie)
        tiao_zu = {}
        for leiming, cha in (('收入类', t_shouru), ('成本类', t_chengben)):
            pian_jian = {}
            for pian in jiansuo(chaxun=cha, shuliang=4):
                dingwei = (f"{pian['zhiyin_hao']}-{pian['tiao_hao']}"
                           + (f"-P{pian['duan_hao']}" if pian.get('duan_hao') else ''))
                pian_jian.setdefault(dingwei, (pian, cha))
            tiao_zu[leiming] = pian_jian
        if moxing:
            raw = None
            for chong in range(3):                  # 网络抖动重试（超时/断连不拖垮全链）
                try:
                    raw = moxing(mo_tishi(zhanshi, shuju_kuai))
                    break
                except Exception as cuo:
                    print(f'    [重试 {chong + 1}/3] {zhanshi}：{cuo}')
            if raw is None:
                fenxi_wen = '— 待 AI 分析（模型调用失败，已重试 3 次）'
            else:
                zhuangtai, weijin = jiao_yan_shuzi(raw.strip(), shuju_kuai)
                fenxi_wen = (raw.strip() if zhuangtai == '通过'
                             else f'— 待 AI 分析（解读未通过校验：{"；".join(weijin)}）')
        else:
            fenxi_wen = '— 待 AI 分析（未配置模型）'
        jie_lie.append({'zhanshi': zhanshi, 'shuju': shuju_kuai,
                        'tiao_zu': tiao_zu, 'wenan': fenxi_wen})
        print(f"[1] {zhanshi}：数据块 {len(shuju_kuai)} 字，"
              f"条文 收入 {len(tiao_zu['收入类'])}/成本 {len(tiao_zu['成本类'])}，"
              f"分析 {fenxi_wen[:12]}…")

    # ---- [2] 组装 md ----
    hang = ['# 预算模块分析报告（数据 · 分析 · 依据）', '',
            '> 报告期 2026-Q1 ｜ 模块口径 = FinAgent 算法链 ｜ '
            '检索库 guanli_ku v3.0（38 指引 1008 片）｜ '
            f"分析 = {'DeepSeek（数字经溯源校验）' if moxing else '未配置（占位）'}", '',
            '## 总览 · 全科目差异', '', ti_kuai(baogao, ('单元 3',)), '',
            '## 模块分析', '']
    for xu, jie in enumerate(jie_lie, start=1):
        hang += [f'### {xu}. {jie["zhanshi"]}', '',
                 '**数据表**', '', jie['shuju'], '',
                 '**分析内容**', '', jie['wenan'], '']
        for leiming in ('收入类', '成本类'):
            hang += [f'**依据条例（{leiming}）**', '']
            pian_jian = jie['tiao_zu'][leiming]
            if not pian_jian:
                hang += ['— 未检索到直接依据。', '']
            for chu_xu, (dingwei, (pian, cha)) in enumerate(pian_jian.items(), start=1):
                kuai = dingwei.split('-')
                ming = zhiyin_ming.get(kuai[0], kuai[0])
                tiao_wen = f'第{_tiaohao_zh(int(kuai[1]))}条' + (
                    f'第{kuai[2][1]}片' if len(kuai) > 2 else '')
                hang += [f'**出处 {chu_xu}：《管理会计应用指引第{kuai[0]}号——{ming}》'
                         f'{tiao_wen}**（定位 {dingwei} ｜ 检索提示词：{cha}）', '',
                         pian['neirong'], '']
    hang += ['---', '', '**声明：本报告分析内容为 AI 生成，仅供参考。**', '']
    md_lu = JIEGUO / '模块分析报告-季度.md'
    md_lu.write_text('\n'.join(hang), encoding='utf-8')
    print(f'[2] 落盘：{md_lu}（{len(hang)} 行）')

    # ---- [3] PDF（系统 Python 跑 md转PDF.py）----
    zhuan = subprocess.run([XT_PY, str(APP / 'testgen' / 'md转PDF.py'), str(md_lu)],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=180)
    print(zhuan.stdout.strip())
    if md_lu.with_suffix('.pdf').exists():
        print(f'[3] 落盘：{md_lu.with_suffix(".pdf")}')
        return 0
    print(f'[3] PDF 失败：{zhuan.stderr[-300:]}')
    return 1


if __name__ == '__main__':
    sys.exit(zhenghe())
