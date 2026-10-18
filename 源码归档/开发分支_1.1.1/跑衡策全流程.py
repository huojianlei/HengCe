# -*- coding: utf-8 -*-
"""衡策全流程：演示件 → 输入端口 → 十五步分析 → 计算报告 → PDF。

一条命令串起三段真实程序（不手搓中间数据）：
    1) ingest_v11.import_excel_v11      读 xlsx（v2/v1.1/v1.2 三轨道自动分派）
    2) houtai_hexin_python.yinqing.fenxi  十五步分析（滚动/差异/预警/BSC/KPI/整改）
    3) 报告组装.baogao_liuxian.compute_report_pipeline  计算报告 md + html
    4) 本机 Chrome/Edge headless 打印 → PDF

用法：
    python -B 跑衡策全流程.py                          # 默认取最新实时经营册
    python -B 跑衡策全流程.py --xlsx 路径 --out 目录
    python -B 跑衡策全流程.py --no-pdf                  # 只出 md/html
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

GEN = Path(__file__).resolve().parent                            # 开发分支_1.1.1
INGEST = GEN / 'ingest_v11'                                      # 输入端口
HOUTAI = GEN / 'houtai_hexin_python'                             # 分析引擎
BAOGAO = GEN / '报告组装'                                         # 报告组装
for p in (INGEST, HOUTAI, BAOGAO):                               # 三段程序入路径
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

RENDER = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
          r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
          r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')


def zhao_shuru():
    """默认输入：生成器v2 输出目录里最新的「预算基础 + 实时经营」一对。"""
    mu = GEN / '演示生成器v2' / '输出'
    yu = sorted(mu.glob('演示-预算基础-*.xlsx'), key=lambda p: p.stat().st_mtime)
    shi = sorted(mu.glob('演示-实时经营-*.xlsx'), key=lambda p: p.stat().st_mtime)
    if not yu or not shi:
        raise SystemExit(f'没找到演示件：{mu}（先跑 python -B shengcheng.py）')
    seed = yu[-1].stem.split('-')[-1]                     # 同一个种子的一对
    return (mu / f'演示-预算基础-{seed}.xlsx', mu / f'演示-实时经营-{seed}.xlsx')


def pao_daoru(lu_yu, lu_shi):
    """① 输入端口：两本各自校验导入，八字段行合并后走权威清洗链。"""
    from excel_ingest_v2 import import_v2
    r1 = import_v2(lu_yu.read_bytes(), lu_yu.name)        # 预算基础（12 个月）
    r2 = import_v2(lu_shi.read_bytes(), lu_shi.name)      # 实时经营（已结账 6 个月）
    for r, lu in ((r1, lu_yu), (r2, lu_shi)):
        print(f'  {lu.name}：轨道 {r["contract_version"]} ｜ 类别 {r["category"]}'
              f' ｜ 校验 {r["checks"]} 项 ｜ 入库 {r["ruku_shu"]} 行')
    # 合并八字段 CSV（第二份去掉表头）→ 交给 algo 权威清洗链
    wen = r1['text'] + '\n' + '\n'.join(r2['text'].splitlines()[1:])
    algo = r'D:\AppProject\开发分支_1.0.5\algo'
    if algo not in sys.path:
        sys.path.insert(0, algo)
    from data_ingest import daoru_csv
    jilu = daoru_csv(wen)
    print(f'  合并：预算 {len(jilu.yusuan)} 行 ｜ 实际 {len(jilu.shishi)} 行'
          f' ｜ 拒绝 {len(jilu.jujue)} 行')
    return {'records': jilu, 'subjects': r1['subjects'],
            'metadata': {**r1['metadata'], '已结账截至': r2['metadata']['已结账截至']}}


def zao_zaihe(r, gongsi=None):
    """② 组装 fenxi 载荷（与桌面 API 同形）。"""
    md = r.get('metadata', {})
    cycle = md.get('期间粒度') or '月度'
    jiezhi = md.get('已结账截至') or ''
    period = jiezhi or md.get('生效周期') or ''
    if cycle == '月度' and len(period) > 7:                      # 已结账截至 → 分析末档
        period = period[:7]
    return {
        'company': gongsi or md.get('主体名称', '演示主体'),
        'metadata': {'主体名称': md.get('主体名称', '演示主体'),
                     '主体编码': md.get('主体编码', 'DEMO-001'),
                     '情景名称': md.get('情景名称', '基础情景'),
                     '情景编码': md.get('情景编码', 'S-BASE')},
        'records': r['records'],                                 # 八字段导入结果（含拒绝清单）
        'subjects': r.get('subjects', []),                       # 科目清单（模块/方向）
        'config': {'cycle': cycle, 'period': period, 'growth': 0,
                   'industry': None, 'industryCorrection': False,
                   'industryThreshold': 50, 'noise': 2500, 'significance': 2500,
                   'tiers': [{'ming_cheng': '黄', 'yan_se': '#FFAA00', 'yu_fen': 1500},
                             {'ming_cheng': '红', 'yan_se': '#FF0000', 'yu_fen': 3000}]},
        'bsc': None, 'kpi': {}, 'traces': [], 'splits': [], 'events': [],
        'baselines': [], 'changeStatus': None,
    }


def pao_fenxi(zaihe):
    """③ 十五步分析。"""
    from yinqing import fenxi
    jieguo = fenxi(zaihe)
    g = jieguo
    print(f'  周期 {zaihe["config"]["cycle"]} ｜ 期间 {zaihe["config"]["period"]}'
          f' ｜ 科目 {len(g.get("subjects", []))} 个')
    def duo(x):                                              # 结果块可能是数据类/dict/列表
        if x is None:
            return 0
        try:
            return len(x)
        except TypeError:
            return len(getattr(x, '__dict__', {}) or {})

    print(f'  分析结果键 {len(g)} 个 ｜ 滚动 {duo(g.get("rolling"))} 期'
          f' ｜ 整改 {duo(g.get("decisions"))} 条 ｜ BSC {duo(g.get("bsc"))}')
    return jieguo


def pao_baogao(jieguo, mu):
    """④ 计算报告（md + html）。"""
    from baogao_liuxian import compute_report_pipeline
    # jiansuo_hanshu 缺省 = 自动懒加载 kb2 真检索；运行时缺 onnx 时按占位如实落文
    r = compute_report_pipeline(jieguo, shuchu_mu=str(mu))
    print(f'  md {Path(r["md"]).name}（{Path(r["md"]).stat().st_size} 字节）'
          f' ｜ html（{Path(r["html"]).stat().st_size} 字节）'
          f' ｜ 模块 {r["mokuai_shu"]} ｜ 条例 {r["tiaoli_shu"]}')
    return r


def zhuan_pdf(html_lu, pdf_lu):
    """⑤ HTML → PDF（本机 Chrome/Edge headless 打印）。"""
    for exe in RENDER:
        if not Path(exe).exists():
            continue
        subprocess.run([exe, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--no-pdf-header-footer', f'--print-to-pdf={pdf_lu}',
                        Path(html_lu).as_uri()],
                       capture_output=True, text=True, encoding='utf-8', timeout=300)
        if pdf_lu.exists() and pdf_lu.stat().st_size > 2000:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description='衡策全流程：演示件 → 分析 → 计算报告 → PDF')
    ap.add_argument('--xlsx', default=None, help='输入工作簿（默认取最新实时经营册）')
    ap.add_argument('--out', default=None, help='输出目录（默认 报告组装/输出）')
    ap.add_argument('--no-pdf', action='store_true')
    a = ap.parse_args()
    lu_yu, lu_shi = (Path(a.xlsx), Path(a.xlsx)) if a.xlsx else zhao_shuru()
    mu = Path(a.out) if a.out else (BAOGAO / '输出')
    print(f'== 输入：{lu_yu.name} + {lu_shi.name}')
    print('== ① 输入端口（契约校验 + 八字段入库）')
    r = pao_daoru(lu_yu, lu_shi)
    print('== ② 组装分析载荷')
    zaihe = zao_zaihe(r)
    print(f'  主体 {zaihe["company"]} ｜ 期间 {zaihe["config"]["period"]}')
    print('== ③ 十五步分析')
    jieguo = pao_fenxi(zaihe)
    print('== ④ 计算报告')
    jieguo['meta']['seed'] = lu_yu.stem.split('-')[-1]        # 抬头写本次种子
    bao = pao_baogao(jieguo, mu)
    if a.no_pdf:
        print(f'\n完成：{bao["md"]}\n      {bao["html"]}')
        return 0
    print('== ⑤ 打印 PDF')
    pdf = mu / '计算报告-月度.pdf'
    if zhuan_pdf(bao['html'], pdf):
        print(f'  PDF：{pdf}（{pdf.stat().st_size} 字节）')
    else:
        print('  [警告] 未找到可用的 Chrome/Edge，仅出 md/html')
        return 1
    print(f'\n完成：\n  md   {bao["md"]}\n  html {bao["html"]}\n  pdf  {pdf}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
