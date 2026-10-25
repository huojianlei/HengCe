# -*- coding: utf-8 -*-
"""衡策全流程：演示件 → 输入端口 → 十五步分析 → 计算报告 → PDF / JSON。

一条命令串起三段真实程序（不手搓中间数据）：
    1) ingest_v11.import_excel_v11      读 xlsx（v2/v1.1/v1.2 三轨道自动分派）
    2) houtai_hexin_python.yinqing.fenxi  十五步分析（滚动/差异/预警/BSC/KPI/整改）
    3) 报告组装.baogao_liuxian.compute_report_pipeline  计算报告 md + html + json
    4) 本机 Chrome/Edge headless 打印 → PDF

用法：
    python -B 跑衡策全流程.py                          # 默认取最新实时经营册，出 md/html/pdf
    python -B 跑衡策全流程.py --xlsx 路径 --out 目录
    python -B 跑衡策全流程.py --no-pdf                  # 只出 md/html（老开关，仍在用）
    python -B 跑衡策全流程.py --format md,html,json     # 精确要求产物，缺哪个报哪个
    python -B 跑衡策全流程.py --ai                      # 加模型经营解读（需 DEEPSEEK_API_KEY）
    python -B 跑衡策全流程.py --json                    # 结果 JSON 写 stdout，进度写 stderr

退出码：0 成功 ｜ 1 业务失败（中文原因写 stderr）｜ 2 参数错误（--format 写错等）。
定位：本脚本是「一条命令跑通演示链路的驱动程序」，业务口径全部在后端，它只做
搬运与打印；要给人和 AI 用的统一入口是 衡策CLI.py（子命令 import/analyze/report/all…）。
新增选项时两个脚本一起看，避免行为分叉。
"""
import argparse                                        # 命令行选项解析
import json                                            # --json 信封输出
import os                                              # 环境变量（HENGCE_ALGO_DIR 覆盖算法目录）
import subprocess                                      # 调本机浏览器打印 PDF
import sys                                             # 标准输入输出、退出码、sys.path
import time                                            # 阶段/总耗时
import traceback                                       # 未预期异常不吞：完整堆栈给 stderr
from datetime import datetime                          # 信封 generatedAt
from pathlib import Path


# ----------------------------------------------------------------------
# 数据流：一条命令里的五个阶段（全部调用真实程序，不手搓中间数据）
# ----------------------------------------------------------------------
#   ① 输入：xlsx → ingest_v11.import_excel_v11（契约校验）→ 八字段记录
#   ② 载荷：八字段合并 CSV → houtai_hexin_python.yinqing.fenxi（十五步分析）
#   ③ 报告：compute_report_pipeline → md（正文）/ html（派生）/ json（结构化）
#   ④ PDF：本机 Chrome/Edge headless 从 html 打印
#   ⑤ 输出：文本进度（或 --json 信封）+ 产物路径清单
# 本脚本只做「搬运 + 打印」，业务口径全在后端；要给人/AI 的统一入口是 衡策CLI.py
# （子命令 import/analyze/report/all），新增选项时两个脚本一起看，避免行为分叉。

GEN = Path(__file__).resolve().parent                            # 开发分支_1.1.1
INGEST = GEN / 'ingest_v11'                                      # 输入端口
HOUTAI = GEN / 'houtai_hexin_python'                             # 分析引擎
BAOGAO = GEN / '报告组装'                                         # 报告组装
for p in (INGEST, HOUTAI, BAOGAO):                               # 三段程序入路径
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# 浏览器候选：Chrome 优先（headless 打印对中文更稳），其次 Edge 的两个常见安装位；
# 顺序改了会影响 PDF 的字体与分页，改动前先跑一次 --format md,html,pdf 对比。

RENDER = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
          r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
          r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')

#: --json 开关（模块级）：进度行据此分流到 stderr，保证 stdout 上只有一个 JSON 对象。
#: 用模块级而不是层层传参——打印点散布在 4 个函数里，传参会把签名弄脏。

# 模块级开关：打印点散布在 4 个函数里，层层传参会把签名弄脏；
# 只在 main 解析完参数后置一次，进程内只读。

_JSON_MOSHI = False

#: --format 允许的格式（md/html 是报告流水线固有产物，pdf/json 按需生成）

# 允许的格式集合：md/html 是流水线固有产物，pdf 依赖浏览器，json 由后端结构化输出现成给；
# 这里只用来校验 --format，不作为「能不能出」的承诺（能不能出由实际生成结果判定）。

GESHI_QUAN = ('md', 'html', 'pdf', 'json')



# 两类异常对应两种退出码，与 衡策CLI.py 完全同口径：
# _CanShu(2) = 命令写错了（改参数即可）；_YiWu(1) = 环境或数据不对（要改输入/环境）。

class _CanShu(Exception):
    """参数错误（用法不对）：main 转成中文提示 + 退出码 2，与 衡策CLI.py 同口径。"""


class _YiWu(Exception):
    """业务失败（环境/密钥/产物不齐）：中文原因写 stderr，退出码 1，不打堆栈。"""



# 进度分流：--json 时 stdout 必须只有一个 JSON 对象，所以进度改走 stderr；
# 非 --json 时沿用原脚本习惯（stdout），老的调用方与管道不受影响。

def _shuo(wen):
    """打印一行进度：默认 stdout（保持原脚本的输出习惯）；--json 时改走 stderr。

    规范要求长步骤进度可见，所以每个阶段都打一行；但 --json 的契约是
    「stdout 只有一个 JSON」，进度必须让路到 stderr，否则程序侧解析会失败。
    """
    print(wen, file=sys.stderr if _JSON_MOSHI else sys.stdout, flush=True)



# 引擎结果块有的是 dataclass、有的是 dict/list，len() 会抛 TypeError；
# 这里统一兜一层，只用于打印统计，不影响任何计算。

def _changdu(x):
    """结果块的长度：数据类 / dict / 列表 / None 都能数（数不出来记 0）。

    引擎返回块有的是 dataclass、有的是 dict、有的是 list，直接 len() 会抛
    TypeError，所以这里统一兜一层，只用于打印统计、不影响任何计算。
    """
    if x is None:
        return 0
    try:
        return len(x)
    except TypeError:
        return len(getattr(x, '__dict__', {}) or {})



# 格式解析：--no-pdf 拥有最高优先级（历史调用方式必须保持有效），
# 其余按 --format 的逗号列表；空值或未知格式给中文参数错误（退出码 2）。

def _jie_geshi(wen, wu_pdf=False):
    """解析 --format（逗号分隔，只认 md/html/pdf/json），并兼容旧的 --no-pdf。

    规则：
      · 不给 --format → 默认 md,html,pdf（与历史行为一致，老命令原样能跑）；
      · --no-pdf 优先级最高：不管 --format 写没写 pdf，一律去掉（旧用法照旧有效）；
      · 未知格式直接报错，不猜——否则用户以为出了某格式，其实盘上没有。
    """
    if wen is None:
        yao = ['md', 'html', 'pdf']
    else:
        yao = [x.strip().lower() for x in str(wen).split(',') if x.strip()]
        if not yao:
            raise _CanShu('--format 不能为空：请给 md / html / pdf / json 之一或多个')
        cuo = [x for x in yao if x not in GESHI_QUAN]
        if cuo:
            raise _CanShu(f'--format 取值无效：{"、".join(cuo)}'
                          f'（只支持 md、html、pdf、json，逗号分隔）')
    if wu_pdf and 'pdf' in yao:
        yao.remove('pdf')
    return yao



# --json 信封（hengce.cli/1）：与 衡策CLI.py 同协议，程序侧一套解析逻辑通吃两个入口。
# 进度与阶段行在 json 模式走 stderr，stdout 只留这一个对象。

def _xie_bao(ok, shuju, kaishi, cuowu=None):
    """--json 时往 stdout 写一个 JSON 信封（与 衡策CLI.py 同 schema，程序侧一套解析）。

    非 --json 时什么都不做（人看的是 _shuo 打出来的中文行）。
    """
    if not _JSON_MOSHI:
        return
    bao = {'schema': 'hengce.cli/1', 'command': 'flow', 'ok': bool(ok),
           'elapsedMs': int((time.perf_counter() - kaishi) * 1000),
           'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
           'data': shuju}
    if cuowu:
        bao['error'] = cuowu
    sys.stdout.write(json.dumps(bao, ensure_ascii=False, indent=2) + '\n')
    sys.stdout.flush()



# 输入选择：默认演示件一对（同种子），也可 --xlsx 指定
# 演示件命名规律 演示-<类别>-<种子>.xlsx：预算基础与实时经营必须同种子配对，
# 混配会让差异分析对不上账。找不到就中文报错要求显式 --xlsx，绝不生成假数据。

def zhao_shuru():
    """默认输入：生成器v2 输出目录里最新的「预算基础 + 实时经营」一对。"""
    mu = GEN / '演示生成器v2' / '输出'
    yu = sorted(mu.glob('演示-预算基础-*.xlsx'), key=lambda p: p.stat().st_mtime)
    shi = sorted(mu.glob('演示-实时经营-*.xlsx'), key=lambda p: p.stat().st_mtime)
    if not yu or not shi:
        raise SystemExit(f'没找到演示件：{mu}（先跑 python -B shengcheng.py）')
    seed = yu[-1].stem.split('-')[-1]                     # 同一个种子的一对
    return (mu / f'演示-预算基础-{seed}.xlsx', mu / f'演示-实时经营-{seed}.xlsx')



# 输入端口：契约校验 + 八字段入库
# 两本工作簿分别走自己的导入轨道（excel_ingest_v2.import_v2），再合并成一份
# 八字段 CSV 交给 data_ingest.daoru_csv；返回的 tongji 记录每本校验项数/入库行数
# 与合并后的预算/实际/拒绝行数，用于过程可见（规范第七节：每完成一文件一行）。

def pao_daoru(lu_yu, lu_shi):
    """① 输入端口：两本各自校验导入，八字段行合并后走权威清洗链。

    为什么要合并成一份 CSV：引擎的 daoru_csv 是唯一权威清洗链（去重/口径/科目
    归并都在里面），预算与实际必须在同一次清洗里对齐，否则差异分析对不上账。
    返回的 records/subjects/metadata 就是引擎需要的三块输入，不经二次加工。
    """
    from excel_ingest_v2 import import_v2
    r1 = import_v2(lu_yu.read_bytes(), lu_yu.name)        # 预算基础（12 个月）
    r2 = import_v2(lu_shi.read_bytes(), lu_shi.name)      # 实时经营（已结账 6 个月）
    tongji = []                                           # 供 --json 汇总（不参与计算）
    for r, lu in ((r1, lu_yu), (r2, lu_shi)):
        _shuo(f'  {lu.name}：轨道 {r["contract_version"]} ｜ 类别 {r["category"]}'
              f' ｜ 校验 {r["checks"]} 项 ｜ 入库 {r["ruku_shu"]} 行')
        tongji.append({'name': lu.name, 'contractVersion': r['contract_version'],
                       'category': r['category'], 'checks': r['checks'],
                       'rows': r['ruku_shu']})
    # 合并八字段 CSV（第二份去掉表头）→ 交给 algo 权威清洗链
    wen = r1['text'] + '\n' + '\n'.join(r2['text'].splitlines()[1:])
    algo = os.environ.get('HENGCE_ALGO_DIR') or str(GEN / '_vendor' / 'algo')  # _vendor 自足
    if algo not in sys.path:
        sys.path.insert(0, algo)
    from data_ingest import daoru_csv
    jilu = daoru_csv(wen)
    _shuo(f'  合并：预算 {len(jilu.yusuan)} 行 ｜ 实际 {len(jilu.shishi)} 行'
          f' ｜ 拒绝 {len(jilu.jujue)} 行')
    return {'records': jilu, 'subjects': r1['subjects'],
            'metadata': {**r1['metadata'], '已结账截至': r2['metadata']['已结账截至']},
            # 统计只为 --json 回报留痕；口径与上面打印的完全同源，不另算一遍
            'tongji': {'inputs': tongji,
                       'merged': {'budgetRows': len(jilu.yusuan),
                                  'actualRows': len(jilu.shishi),
                                  'rejected': len(jilu.jujue)}}}



# 分析载荷：配置口径与界面默认档位一致（周期/期间/增长/阈值/噪声/显著性/色阶）；
# 只有 --cycle/--period/--growth 会覆盖，其余保持默认——同一份输入不管从界面还是
# 从脚本跑，结果都一样（可复现是量化分析的前提）。

def zao_zaihe(r, gongsi=None):
    """② 组装 fenxi 载荷（与桌面 API 同形）。

    载荷形状必须和界面/CLI 走的后端完全一致：主体、情景、records、subjects、
    config（周期/期间/增长/行业校正/预警阈值/显著性）缺一项引擎就会按默认值跑，
    出来的是另一套口径。这里所有默认值都照抄桌面默认档位，不做「本地优化」。
    """
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



# 十五步分析：结果键数、滚动期数、整改条数、BSC 得分都打印出来供核对；
# 这些数字后面会出现在报告总览与统计里，先看一眼比事后翻报告快。

def pao_fenxi(zaihe):
    """③ 十五步分析（结果原样返回，交给报告组装；中间不落盘、不改写）。"""
    from yinqing import fenxi
    jieguo = fenxi(zaihe)
    g = jieguo
    _shuo(f'  周期 {zaihe["config"]["cycle"]} ｜ 期间 {zaihe["config"]["period"]}'
          f' ｜ 科目 {len(g.get("subjects", []))} 个')
    def duo(x):                                              # 结果块可能是数据类/dict/列表
        if x is None:
            return 0
        try:
            return len(x)
        except TypeError:
            return len(getattr(x, '__dict__', {}) or {})

    _shuo(f'  分析结果键 {len(g)} 个 ｜ 滚动 {duo(g.get("rolling"))} 期'
          f' ｜ 整改 {duo(g.get("decisions"))} 条 ｜ BSC {duo(g.get("bsc"))}')
    return jieguo



# --ai：复用后端 _ai_bao_wencai（复用同一套文案生成，不另写一份 prompt）；
# 无密钥时直接中文报错退出 1——用户明确要了 AI 解读，静默降级等于骗人。

def pao_ai(jieguo):
    """可选：接入 DeepSeek 经营解读（与界面「加入 AI 经营解读」同一实现）。

    为什么复用 桥接入口 而不是自己写：密钥发现（环境变量 → DSH_HOME/.credentials.yaml）
    与三个钩子（逐模块解读 wencai、总结 zongjie、整改回填 _ai_zhenggai）都在那里，
    另写一份必然和界面口径分叉（而且模型提示词也要两处维护）。
    桥接入口带 `if __name__ == '__main__'` 保护，import 不会启动标准输入循环。
    """
    if str(GEN) not in sys.path:                              # 脚本目录正常已在路径，兜底再插一次
        sys.path.insert(0, str(GEN))
    import importlib
    q = importlib.import_module('桥接入口')
    miyao = q._du_miyao()                                     # 两级查找：环境变量 → 凭据文件
    if not miyao:
        raise _YiWu('未配置 DeepSeek API 密钥：请设置环境变量 DEEPSEEK_API_KEY'
                    '（或 DSH_HOME/.credentials.yaml 的 DEEPSEEK_API_KEY 行）；'
                    '不加 --ai 仍可生成纯计算报告')
    _shuo('  --ai 启用：逐模块调用 DeepSeek 写解读（约 3-8 分钟，失败会如实报错）…')
    wencai, zongjie = q._ai_bao_wencai(miyao)
    return {'wencai': wencai, 'zongjie': zongjie, 'miyao': miyao, 'q': q}



# 报告组装（与界面同一个 compute_report_pipeline）：
# md 是正文，html 由 md 派生，json 由后端 zucheng_json 产出；
# --ai 时把解读函数传进去，回填失败只告警不毁报告（报告本身是计算产物）。

def pao_baogao(jieguo, mu, geshi, ai=None):
    """④ 计算报告：流水线一次产出 md + html + json（同源同次，保证可逐项对账）。

    --format 只决定「本次要求哪些产物并打印/登记」：md、html、json 是流水线固有
    产物（想不出也难，它们共用同一次汇总），pdf 才是真正的可选步骤。
    """
    from baogao_liuxian import compute_report_pipeline
    # jiansuo_hanshu 缺省 = 自动懒加载 kb2 真检索；运行时缺 onnx 时按占位如实落文
    r = compute_report_pipeline(jieguo,
                                wencai_hanshu=(ai or {}).get('wencai'),
                                zongjie_hanshu=(ai or {}).get('zongjie'),
                                shuchu_mu=str(mu))
    if ai:
        try:
            ai['q']._ai_zhenggai(jieguo, ai['miyao'], r['md'])    # 逐条整改建议回填
            _shuo('  整改建议已按 AI 结果回填（md + html 同步重写）')
        except Exception as e:                                # noqa: BLE001
            # 回填失败不毁报告：占位文案保留，如实告警（不掩盖、不伪造建议）
            _shuo(f'  [警告] 整改建议 AI 回填失败（占位保留）：{e}')
    bufen = []                                                # 只打印本次要求的格式
    if 'md' in geshi:
        bufen.append(f'md {Path(r["md"]).name}（{Path(r["md"]).stat().st_size} 字节）')
    if 'html' in geshi:
        bufen.append(f'html（{Path(r["html"]).stat().st_size} 字节）')
    _shuo('  ' + ' ｜ '.join(bufen + [f'模块 {r["mokuai_shu"]}', f'条例 {r["tiaoli_shu"]}']))
    return r



# PDF 由本机 Chrome/Edge headless 打印：依次试候选，成功判据是「>2000 字节」；
# 全失败返回 False 由调用方降级告警——PDF 只是可选格式，不该让整条流程失败。

def zhuan_pdf(html_lu, pdf_lu):
    """⑤ HTML → PDF（本机 Chrome/Edge headless 打印）。

    判定口径：PDF 大于 2000 字节才算成功——headless 打印失败时浏览器常留下
    一个几十字节的残件，只判「文件存在」会把失败当成功（界面侧同口径）。
    """
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



# 汇总信封的 data 段：输入、入库统计、分析概况、报告产物、格式与 AI 开关一次给全；
# 字段名与 衡策CLI.py 的 all 尽量对齐，便于脚本无差别处理两个入口的输出。

def _gaishu(lu_yu, lu_shi, r, zaihe, jieguo, bao, geshi, chan, yao_ai):
    """汇总 --json 的 data 块：输入、导入统计、分析规模、报告产物、本次格式。

    只报「实际发生的事实」：行数/条数来自本次运行，产物路径来自流水线返回值，
    不补算、不估算（口径以报告为准）。
    """
    return {
        'input': {'预算基础': str(lu_yu), '实时经营': str(lu_shi)},
        'import': r.get('tongji') or {},
        'analyze': {
            'cycle': zaihe['config']['cycle'],
            'period': zaihe['config']['period'],
            'subjects': _changdu(zaihe.get('subjects')),
            'resultKeys': _changdu(jieguo),
            'rolling': _changdu(jieguo.get('rolling')),
            'decisions': _changdu(jieguo.get('decisions')),
            'bsc': _changdu(jieguo.get('bsc')),
            'seed': (jieguo.get('meta') or {}).get('seed'),
        },
        'report': {'mokuaiShu': bao.get('mokuai_shu'),
                   'tiaoliShu': bao.get('tiaoli_shu'),
                   'md': bao.get('md'), 'html': bao.get('html'), 'json': bao.get('json')},
        'format': geshi,
        'files': chan,
        'includeAI': bool(yao_ai),
    }



# 主执行：① 输入 ② 载荷 ③ 分析 ④ 报告（可选 AI 回填）⑤ PDF ⑥ 汇总输出。
# 各阶段都用 _shuo 打一行「做了什么 + 耗时」，失败让异常往上抛给 main 统一翻译，
# 不在中间吞掉——用户要能看到是哪一步出的问题。

def _zhu(a, kaishi):
    """主流程（main 只负责参数/异常/退出码，业务在这里按阶段推进）。"""
    geshi = _jie_geshi(a.format, a.no_pdf)                     # 先校验格式，错就别开跑
    lu_yu, lu_shi = (Path(a.xlsx), Path(a.xlsx)) if a.xlsx else zhao_shuru()
    mu = Path(a.out) if a.out else (BAOGAO / '输出')
    _shuo(f'== 输入：{lu_yu.name} + {lu_shi.name}')
    _shuo(f'== 格式：{"、".join(geshi)}' + ('（--no-pdf 覆盖）' if a.no_pdf and a.format else ''))
    _shuo('== ① 输入端口（契约校验 + 八字段入库）')
    r = pao_daoru(lu_yu, lu_shi)
    _shuo('== ② 组装分析载荷')
    zaihe = zao_zaihe(r)
    _shuo(f'  主体 {zaihe["company"]} ｜ 期间 {zaihe["config"]["period"]}')
    _shuo('== ③ 十五步分析')
    jieguo = pao_fenxi(zaihe)
    _shuo('== ④ 计算报告')
    jieguo['meta']['seed'] = lu_yu.stem.split('-')[-1]        # 抬头写本次种子
    ai = pao_ai(jieguo) if a.ai else None                     # 密钥缺失在这里中文报错
    bao = pao_baogao(jieguo, mu, geshi, ai)
    chan = {}
    for ge in ('md', 'html', 'json'):                         # 流水线固有产物：有就登记
        lu = bao.get(ge)
        if ge in geshi and lu and Path(lu).exists():
            chan[ge] = str(lu)
    que = []                                                  # 本次要求但没生成出来的格式
    if 'pdf' in geshi:
        _shuo('== ⑤ 打印 PDF')
        pdf = mu / '计算报告-月度.pdf'
        if zhuan_pdf(bao['html'], pdf):
            _shuo(f'  PDF：{pdf}（{pdf.stat().st_size} 字节）')
            chan['pdf'] = str(pdf)
        else:
            _shuo('  [警告] 未找到可用的 Chrome/Edge，仅出 md/html')
            que.append('pdf')
    if 'json' in geshi:
        # 后端 1.1.5 起 compute_report_pipeline 返回 'json' 键；旧后端退回同名文件
        jian = bao.get('json') or str(Path(bao['md']).with_suffix('.json'))
        if Path(jian).exists():
            _shuo(f'  JSON：{jian}（{Path(jian).stat().st_size} 字节）')
            chan['json'] = str(jian)
        else:
            _shuo('  [警告] 后端未提供结构化 JSON（报告流水线未返回 json 键）')
            que.append('json')
    shuju = _gaishu(lu_yu, lu_shi, r, zaihe, jieguo, bao, geshi, chan, bool(ai))
    if que:
        _shuo(f'✘ 以下格式未生成：{"、".join(que)}（已完成 {len(chan)} 项）')
        _xie_bao(False, shuju, kaishi,
                 cuowu={'code': 1, 'kind': '业务失败',
                        'message': f'以下格式未生成：{"、".join(que)}'})
        return 1
    _shuo('\n完成：')
    for ge in ('md', 'html', 'pdf', 'json'):
        if ge in chan:
            _shuo(f'  {ge:4s} {chan[ge]}')
    _xie_bao(True, shuju, kaishi)
    return 0



# 入口：参数 → 执行 → 退出码（0 成功 / 1 业务失败 / 2 参数错误）
# 原脚本只有 --xlsx/--out/--no-pdf 且只输出人看文本；本轮新增 --format/--ai/--json。
# 向后兼容：--no-pdf 优先级最高，原有调用方式行为不变。

def main():
    """命令行入口：解析参数 → 跑 _zhu → 按中文口径转退出码。"""
    ap = argparse.ArgumentParser(
        description='衡策全流程：演示件 → 分析 → 计算报告 → PDF/JSON',
        epilog='示例：\n'
               '  python -B 跑衡策全流程.py --no-pdf\n'
               '  python -B 跑衡策全流程.py --format md,html,json --out D:\\某目录\n'
               '  python -B 跑衡策全流程.py --ai --json\n'
               '退出码：0 成功 ｜ 1 业务失败 ｜ 2 参数错误',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--xlsx', default=None,
                    help='输入工作簿（默认取最新一对演示件；只给一本时预算与实际都用它）')
    ap.add_argument('--out', default=None, help='输出目录（默认 报告组装/输出）')
    ap.add_argument('--format', default=None,
                    help='输出格式，逗号分隔：md,html,pdf,json（默认 md,html,pdf）')
    ap.add_argument('--no-pdf', action='store_true',
                    help='不出 PDF（等价于 --format 里去掉 pdf，保留旧用法）')
    ap.add_argument('--ai', action='store_true',
                    help='加入 DeepSeek 模型经营解读（需 DEEPSEEK_API_KEY）')
    ap.add_argument('--json', action='store_true',
                    help='结果 JSON 写 stdout（进度写 stderr，便于程序调用）')
    a = ap.parse_args()
    global _JSON_MOSHI                                     # 打印分流开关（模块级）
    _JSON_MOSHI = a.json
    kaishi = time.perf_counter()
    try:
        return _zhu(a, kaishi)
    except _CanShu as e:                                   # 参数错误：不抛栈，中文一行
        print(f'参数错误：{e}', file=sys.stderr, flush=True)
        _xie_bao(False, None, kaishi,
                 cuowu={'code': 2, 'kind': '参数错误', 'message': f'参数错误：{e}'})
        return 2
    except _YiWu as e:                                     # 业务失败：密钥/产物不齐等
        print(f'✘ {e}', file=sys.stderr, flush=True)
        _xie_bao(False, None, kaishi,
                 cuowu={'code': 1, 'kind': '业务失败', 'message': str(e)})
        return 1
    except KeyboardInterrupt:                              # Ctrl+C：明确说没出完整结果
        sys.stderr.write('\n✘ 已中断（Ctrl+C）：本次未产出完整结果\n')
        return 1
    except Exception as e:                                 # noqa: BLE001 不吞异常
        traceback.print_exc(file=sys.stderr)               # 完整堆栈给能定位的人
        print(f'✘ 未预期的内部错误：{type(e).__name__}: {e}（完整堆栈见上）',
              file=sys.stderr, flush=True)
        _xie_bao(False, None, kaishi,
                 cuowu={'code': 1, 'kind': '业务失败',
                        'message': f'{type(e).__name__}: {e}'})
        return 1



# 直接运行才执行 main：被 import（如测试或 衡策CLI.py 复用函数）时不会有副作用。
# 退出码原样交给 shell：0 成功 / 1 业务失败 / 2 参数错误。


# 用法速记：python -B 跑衡策全流程.py --no-pdf ｜ --format md,html,json --out 目录 ｜
# --json 给程序读 ｜ --ai 让模型回填解读（需密钥）。这一行同时是「被 import 时不执行」的
# 保险：CLI 或测试复用上面的函数不会触发一次完整流水线。

if __name__ == '__main__':
    sys.exit(main())
