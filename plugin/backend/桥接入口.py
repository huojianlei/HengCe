# -*- coding: utf-8 -*-
"""衡策插件 · Python 桥接入口（hengceHost 协议的服务端实现）。

与 Node 适配器（../adapter/）的契约：
    1. stdio JSON 行协议——适配器每行发一个请求 {"id","action","payload"}，
       本进程逐行回 {"id","ok":true,"data":...} 或 {"id","ok":false,"error":"中文"}；
       常驻进程（导入/分析模块只加载一次），文件字节一律 base64 编码进 JSON。
    2. 13 个 action 全部落到 1.1.1 权威三函数（import_excel_v11 / fenxi /
       compute_report_pipeline），本层只做编排与归一化，不重写任何算法。
    3. workspace 归一化按 docs/接入说明.md §5/§6.2 与 ui/src/演示数据.mjs 的
       形状：金额=整数分、比率=整数基点、缺数=null 不臆造、枚举显式映射。
    4. 持久化：../数据/状态.json（工作区状态+历史快照）与 ../数据/报告/
       （md/html/pdf 落盘）；重启后文件/历史/报告仍在，报告再生成仅限
       本进程内做过的运行（诚实报错，不悄悄换数据）。

纪律：零 C 盘写；原始工作簿不出本进程；错误文案中文原样上抛。
建立：2026-10-18 ｜ Agent：ZCode（GLM-5.3）
"""
import base64          # 文件字节 ↔ JSON 字符串
import dataclasses     # fenxi 结果里的 dataclass 摊平
import json            # 行协议与状态读写
import os              # 环境变量（AI 密钥 / DSH_HOME）
import re              # PDF 页数统计
import subprocess      # 报告 PDF 打印 + 打开目录
import sys             # stdio 重配置与路径引导
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

# ---- 路径引导：backend 三段程序 + _vendor 算法树（全部相对本文件，自足包）----
BEN_MU = Path(__file__).resolve().parent                  # backend 根
for _lu in (BEN_MU / 'ingest_v11',                        # 输入端口
            BEN_MU / 'houtai_hexin_python',               # 分析引擎
            BEN_MU / '报告组装',                           # 报告组装
            BEN_MU / '_vendor' / 'algo'):                  # 权威清洗链（data_ingest 等）
    if str(_lu) not in sys.path:
        sys.path.insert(0, str(_lu))

SHUJU_MU = BEN_MU.parent / '数据'                          # 运行时数据目录
BAOGAO_MU = SHUJU_MU / '报告'                              # 报告产物目录
ZHUANGTAI_LU = SHUJU_MU / '状态.json'                       # 工作区状态文件
MOBAN_MU = BEN_MU / '_vendor' / '空白模板'                  # 四类官方空白模板

# Chrome/Edge headless 打印 PDF 的候选（只读执行，不写 C 盘）
LIULANQI = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')

#: 预警名 → UI risk 枚举（红/黄之外一律 normal，含"无/无法"）
FENGXIAN = {'红': 'high', '黄': 'watch'}
#: 引擎模块名 → UI 模块名（去"模块"后缀；接入说明 §5 的显式映射）
MOKUAI_JIAN = {'收入模块': '收入', '成本模块': '成本',
               '费用模块': '费用', '采购模块': '采购'}
#: 整改优先级 → UI 枚举（高→high，其余按关注档）
YOUXIANJI = {'高': 'high'}
#: 引擎整改状态 → UI 枚举（接入说明 actions.status 口径）
ZHUANGTAI_MAP = {'待整改': 'pending', '进行中': 'doing', '已完成': 'done'}

_RUNS = {}            # runId → fenxi 原始结果对象（进程内存；报告再生成用）
_ZT = None            # 工作区状态（main 里加载；每个请求后落盘）


# ======================================================================
# 基础工具：时间 / 状态读写 / 序列化
# ======================================================================

def xianzai():
    """当前时刻 ISO 8601（北京时间，带时区，秒精度）。"""
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def kong_zhuangtai():
    """空状态骨架：全部字段就位，避免 UI 读到 undefined。"""
    return {
        'schemaVersion': '1.0',
        'files': [],                # 已导入工作簿（含八字段 CSV 原文，供分析合并）
        'config': None,             # 最近一次配置（UI 形状）
        'background': {'changeStatus': 'unknown', 'text': ''},
        'actionStatus': {},         # 整改状态人工覆盖（actionId → pending/doing/done）
        'revisions': [],            # 已批准修订（UI 彂状，金额=分）
        'currentRunId': None,       # 当前展示的运行
        'runs': [],                 # 历史：{id,period,createdAt,company,status,riskCount,快照}
        'reports': [],              # 报告登记：{id,title,...,mdPath,htmlPath,pdfPath,pages}
        'dirty': False,             # 输入/背景/配置相对最近一次运行的变更标记
    }


def du_zhuangtai():
    """读状态文件；不存在或损坏则回空骨架（状态可重建，不值得硬失败）。"""
    if ZHUANGTAI_LU.exists():
        try:
            return json.loads(ZHUANGTAI_LU.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return kong_zhuangtai()


def xie_zhuangtai():
    """状态落盘（原子写：先临时文件再替换，避免半截 JSON）。"""
    if _ZT is None:
        return
    SHUJU_MU.mkdir(parents=True, exist_ok=True)
    linshi = ZHUANGTAI_LU.with_suffix('.tmp')
    linshi.write_text(json.dumps(_ZT, ensure_ascii=False, indent=1),
                      encoding='utf-8')
    linshi.replace(ZHUANGTAI_LU)


def tanping(x):
    """fenxi 结果对象 → 纯 JSON 结构（dataclass/SimpleNamespace 递归摊平）。

    归一化与回包共用；Decimal/Path 等罕见类型转 str 兜底，保证可落盘可回传。
    """
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {k: tanping(v) for k, v in dataclasses.asdict(x).items()}
    if isinstance(x, SimpleNamespace):
        return {k: tanping(v) for k, v in vars(x).items()}
    if isinstance(x, dict):
        return {str(k): tanping(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [tanping(v) for v in x]
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    return str(x)


def renlei(n):
    """字节数 → 人类可读（KB/MB，与 UI 演示口径一致）。"""
    if n < 1024:
        return f'{n} 字节'
    if n < 1024 * 1024:
        return f'{round(n / 1024)} KB'
    return f'{round(n / 1024 / 1024, 1)} MB'


def wenjian_zhaiyao(zt):
    """状态里的文件清单 → UI files 条目（只带展示字段）。"""
    return [{k: f.get(k) for k in ('id', 'name', 'category', 'status',
                                   'checks', 'rows', 'size', 'entity')}
            for f in zt.get('files', [])]


def baogao_zhaiyao(zt):
    """状态里的报告登记 → UI reports 条目（不带盘上路径）。"""
    return [{k: r.get(k) for k in ('id', 'title', 'period', 'createdAt',
                                   'status', 'format', 'pages', 'includeAI')}
            for r in zt.get('reports', [])]


def lishi_zhaiyao(zt):
    """状态里的运行历史 → UI history 条目（不带快照本体）。"""
    return [{k: r.get(k) for k in ('id', 'period', 'createdAt',
                                   'company', 'status', 'riskCount')}
            for r in zt.get('runs', [])]


# ======================================================================
# workspace 归一化（fenxi 19 键 → UI normalized workspace）
# ======================================================================

def guiyi(jieguo, zt):
    """当前运行 + 状态覆盖层 → 完整 normalized workspace（UI 唯一数据源）。

    jieguo 可以是 fenxi 原始对象（本进程内）或其摊平 dict（形状同名）。
    """
    qu = tanping(jieguo)                           # 统一成 dict 视图
    meta = qu.get('meta') or {}
    pei = qu.get('config') or {}
    subjects = qu.get('subjects') or []
    kemu_mokuai = {s['kemu']: MOKUAI_JIAN.get(s['module'], s['module'])
                   for s in subjects}               # 科目 → UI 模块名
    kemu_leibie = {s['kemu']: s.get('direction', '') for s in subjects}

    # 预警名 → UI risk：按档位阈值排序，最高档=high、其余档=watch、未命中=normal
    # （引擎 yujing 取配置档位名；老口径 红/黄 作无档位时的兜底映射）
    ming_risk = {}
    for t in sorted(pei.get('tiers') or [], key=lambda x: x.get('yu_fen') or 0):
        ming_risk[t.get('ming_cheng')] = 'watch'
    if ming_risk:
        zui_gao = max(pei['tiers'], key=lambda x: x.get('yu_fen') or 0)
        ming_risk[zui_gao.get('ming_cheng')] = 'high'
    ming_risk.update(FENGXIAN)
    ming_se = {t.get('ming_cheng'): t.get('yan_se')
               for t in (pei.get('tiers') or [])}

    # ---- rows：差异明细（科目 × 期间）----
    chayi = (qu.get('variance') or {}).get('xiang') or []
    panduan = {(d.get('kemu'), d.get('period')): d
               for d in (qu.get('decisions') or [])}
    # 来源定位：实际行优先，其次预算行（hanghao 来自八字段入库序）
    laiyuan = {}
    for lei in ('shishi', 'yusuan'):
        for r in ((qu.get('records') or {}).get(lei) or []):
            laiyuan.setdefault((r.get('kemu'), r.get('qijian')),
                               f'{r.get("leibie")} · 行{r.get("hanghao")}')
    rows = []
    for i, x in enumerate(chayi):
        kem, qj = x.get('kemu'), x.get('qijian')
        chae, shiji = x.get('chae_fen'), x.get('shiji_fen')
        pand = panduan.get((kem, qj)) or {}
        # 方向映射：F=有利 / A=不利 / N=中性（中性按"收入类顺差即有利"的
        # 展示口径归到二值枚举——接入说明 §5 的显式映射约定）
        if x.get('fa') == 'F':
            fang = 'favorable'
        elif x.get('fa') == 'A':
            fang = 'unfavorable'
        else:
            shun = (chae >= 0) if kemu_leibie.get(kem) == '收入类' else (chae <= 0)
            fang = 'favorable' if shun else 'unfavorable'
        rows.append({
            'id': f'r{i:03d}', 'subject': kem,
            'module': kemu_mokuai.get(kem, ''), 'department': '', 'departmentId': 'all',
            'period': qj, 'budget': x.get('jizhun_fen'), 'actual': shiji,
            'variance': chae if shiji is not None else None,
            'rate': x.get('chalv_bps') if shiji is not None else None,
            'risk': ming_risk.get(x.get('yujing'), 'normal'),
            'tierName': x.get('yujing') if x.get('yujing') in ming_risk else None,
            'tierColor': ming_se.get(x.get('yujing')) or x.get('yan_se'),
            'direction': fang,
            'decision': pand.get('panduan') or '',
            'reason': pand.get('jiuzheng') or pand.get('beizhu') or '',
            'source': laiyuan.get((kem, qj), '标准Excel模板'),
        })
    rowid = {(r['subject'], r['period']): r['id'] for r in rows}

    # ---- trend：营业收入（无则空序列）逐月 预算/实际/滚动 ----
    qushi = []
    for gd in (qu.get('rolling') or []):
        if gd.get('kemu') == '营业收入':
            for mx in gd.get('qijian_mingxi') or []:
                shuzhi = mx.get('shuzhi_fen')
                weilai = mx.get('qijian') > (pei.get('period') or '')
                qushi.append({'period': mx.get('qijian'),
                              'budget': mx.get('chushi_yusuan_fen'),
                              'actual': shuzhi if mx.get('laiyuan') == '实际' else None,
                              'rolling': shuzhi if weilai and mx.get('laiyuan') != '实际' else None})
            break

    # ---- actions：整改清单（correction.qingdan）+ 人工状态覆盖 ----
    qingdan = ((qu.get('correction') or {}).get('qingdan')
               or (qu.get('dashboard') or {}).get('zhenggai_block', {}).get('qingdan')
               or [])
    actions = []
    for it in qingdan:
        aid = f'a-{it.get("kemu", "")}-{it.get("qijian", "")}'
        yuan = it.get('zhuangtai') or '待整改'
        actions.append({
            'id': aid, 'rowId': rowid.get((it.get('kemu'), it.get('qijian'))),
            'title': f'{it.get("leixing", "整改")}：{it.get("kemu", "")}',
            'department': it.get('zeren_mokuai', ''),
            # 引擎清单不带责任人与截止日——占位字符串而非 null（UI 卡片对两者调 .slice）
            'owner': '未指派', 'due': '',
            'status': zt['actionStatus'].get(aid, ZHUANGTAI_MAP.get(yuan, 'pending')),
            'priority': YOUXIANJI.get(it.get('youxianji'), 'watch'),
            'type': 'revision' if '修订' in (it.get('leixing') or '') else 'execution',
            'description': it.get('miaoshu', ''),
        })

    # ---- kpis：系数包实算值优先，KPI 库按名册补 null（缺数不臆造）----
    yinzi = qu.get('factors') or {}
    kpis = []
    if yinzi.get('wanchenglv_bps') is not None:
        kpis.append({'name': '预算完成率', 'value': yinzi['wanchenglv_bps'],
                     'unit': '%', 'note': '系数包实算（分/基点口径）'})
    for k in ((qu.get('dashboard') or {}).get('kpi_block') or []):
        kpis.append({'name': k.get('mingcheng', ''), 'value': k.get('zhi'),
                     'unit': '%', 'note': ''})

    # ---- config 回显：引擎形状 → UI 形状（档位字段名反转）----
    tiers = [{'name': t.get('ming_cheng'), 'color': t.get('yan_se'),
              'threshold': t.get('yu_fen')} for t in (pei.get('tiers') or [])]
    dangqian = dangqian_run(zt)

    return {
        'schemaVersion': '1.0',
        'demo': False,
        'dirty': bool(zt.get('dirty')),
        'meta': {'company': meta.get('company', ''), 'period': meta.get('period', ''),
                 'scenario': meta.get('scenarioName', ''),
                 'generatedAt': meta.get('generatedAt', ''),
                 'runId': dangqian['id'] if dangqian else ''},
        'config': {'cycle': pei.get('cycle', '月度'), 'period': pei.get('period', ''),
                   'growth': pei.get('growth', 0), 'industry': pei.get('industry'),
                   'industryCorrection': pei.get('industryCorrection', False),
                   'industryThreshold': pei.get('industryThreshold', 50),
                   'noise': pei.get('noise', 2500),
                   'significance': pei.get('significance', 2500),
                   'tiers': tiers},
        'entities': [{'id': 'all', 'name': '全部部门'}],   # 当前数据无部门维度，诚实单选
        'files': wenjian_zhaiyao(zt),
        'rows': rows,
        'trend': qushi,
        'actions': actions,
        'revisions': zt.get('revisions', []),
        'reports': baogao_zhaiyao(zt),
        'history': lishi_zhaiyao(zt),
        'kpis': kpis,
        'background': zt.get('background') or {'changeStatus': 'unknown', 'text': ''},
        'warnings': list(qu.get('warnings') or []),
    }


def dangqian_run(zt):
    """状态里的当前运行条目（无则 None）。"""
    rid = zt.get('currentRunId')
    for r in zt.get('runs', []):
        if r.get('id') == rid:
            return r
    return None


def fang_kuaizhao(zt):
    """按当前运行出 workspace：内存原始对象 → 归一化；否则回放历史快照。

    快照回放会把文件清单换成最新状态并叠加 dirty/提醒，保证 UI 与实际
    导入状态一致（快照里的 rows/actions 等仍是当时的计算结果）。
    """
    if zt.get('currentRunId') in _RUNS:
        return guiyi(_RUNS[zt['currentRunId']], zt)
    run = dangqian_run(zt)
    if run and run.get('快照'):
        kuai = json.loads(json.dumps(run['快照'], ensure_ascii=False))
        kuai['dirty'] = bool(zt.get('dirty'))
        kuai['files'] = wenjian_zhaiyao(zt)
        kuai['reports'] = baogao_zhaiyao(zt)
        kuai['history'] = lishi_zhaiyao(zt)
        return kuai
    return kong_gongzuoqu(zt)


def kong_gongzuoqu(zt):
    """无任何运行时的空工作区（各数组就位，UI 全部空态渲染）。"""
    if not zt.get('files'):
        tixing = ['尚未导入工作簿：请先下载空白模板，填好后导入「预算基础」与「实时经营」两册']
    else:
        tixing = ['已导入工作簿，尚未运行分析']
    return {'schemaVersion': '1.0', 'demo': False, 'dirty': bool(zt.get('dirty')),
            'meta': {'company': '', 'period': '', 'scenario': '',
                     'generatedAt': '', 'runId': ''},
            'config': zt.get('config') or moren_config(),
            'entities': [{'id': 'all', 'name': '全部部门'}],
            'files': wenjian_zhaiyao(zt),
            'rows': [], 'trend': [], 'actions': [], 'revisions': [],
            'reports': baogao_zhaiyao(zt),
            'history': lishi_zhaiyao(zt),
            'kpis': [], 'background': zt.get('background'),
            'warnings': tixing}


def moren_config():
    """默认分析配置（与引擎拍板口径一致：黄 15%/红 30%、门限 25%）。"""
    return {'cycle': '月度', 'period': '', 'growth': 0, 'industry': None,
            'industryCorrection': False, 'industryThreshold': 50,
            'noise': 2500, 'significance': 2500,
            'tiers': [{'name': '关注', 'color': '#b7791f', 'threshold': 1500},
                      {'name': '高风险', 'color': '#c54d57', 'threshold': 3000}]}


# ======================================================================
# 分析主链（选册 → 合并清洗 → fenxi → 登记运行）
# ======================================================================

def zuhe_peizhi(ui_cfg):
    """UI 配置 → 引擎 config（档位字段名映射 + 整数闸）。"""
    c = ui_cfg or {}
    try:
        return {'cycle': c.get('cycle', '月度'), 'period': c.get('period', ''),
                'growth': int(c.get('growth', 0) or 0),
                'industry': (int(c['industry'])
                             if c.get('industry') is not None else None),
                'industryCorrection': bool(c.get('industryCorrection', False)),
                'industryThreshold': int(c.get('industryThreshold', 50) or 0),
                'noise': int(c.get('noise', 2500) or 0),
                'significance': int(c.get('significance', 2500) or 0),
                'tiers': [{'ming_cheng': t['name'], 'yan_se': t['color'],
                           'yu_fen': int(t['threshold'])}
                          for t in (c.get('tiers') or [])]}
    except (KeyError, TypeError, ValueError) as e:
        raise RuntimeError(f'分析配置不完整或类型不对：{e}') from e


def pao_fenxi(zt, ui_cfg=None):
    """组载荷并跑十五步分析；成功登记运行与历史，返回 (runId, jieguo)。

    选册口径：每类取最新一册（多册时如实提醒）；两册主体不一致即拒绝。
    """
    from data_ingest import daoru_csv               # 权威清洗链（_vendor algo）
    from yinqing import fenxi

    def zuixin(leibie):
        mingdan = [f for f in zt['files']
                   if f['category'] == leibie and f['status'] == 'valid']
        return mingdan[-1] if mingdan else None, len(mingdan)

    yu, yu_shu = zuixin('预算基础')
    shi, shi_shu = zuixin('实时经营')
    if not yu or not shi:
        raise RuntimeError('请先导入「预算基础」与「实时经营」两本工作簿后再分析')
    if yu['entity'] != shi['entity']:
        raise RuntimeError(f'两本工作簿主体不一致（{yu["entity"]} / {shi["entity"]}），'
                           '请按主体分批导入，不要跨主体混算')
    tixing = []
    if yu_shu > 1:
        tixing.append(f'预算基础已导入 {yu_shu} 册，本次分析采用最新一册：{yu["name"]}')
    if shi_shu > 1:
        tixing.append(f'实时经营已导入 {shi_shu} 册，本次分析采用最新一册：{shi["name"]}')

    # 合并八字段 CSV（第二册去表头）→ 权威清洗链；拒绝清单非空即中止
    wen = yu['text'] + '\n' + '\n'.join(shi['text'].splitlines()[1:])
    jilu = daoru_csv(wen)
    if getattr(jilu, 'jujue', None):
        shou = '；'.join(str(j) for j in jilu.jujue[:3])
        raise RuntimeError(f'合并清洗拒绝了 {len(jilu.jujue)} 行，不能继续分析：{shou}')

    # 载荷组装（与 跑衡策全流程.zao_zaihe 同形；配置来自 UI）
    md_yu = yu.get('metadata', {})
    md_shi = shi.get('metadata', {})
    pei = zuhe_peizhi(ui_cfg or zt.get('config'))
    if not pei.get('period'):
        # 期间缺省口径与 zao_zaihe 一致：实时经营「已结账截至」→ 预算「生效周期」；
        # 月度取前 7 位（YYYY-MM），季度由 UI 传入（YYYY-Qn）
        zhou = md_shi.get('已结账截至') or md_yu.get('生效周期') or ''
        if pei.get('cycle') == '月度' and len(zhou) > 7:
            zhou = zhou[:7]
        if zhou:
            pei['period'] = zhou
    zaihe = {
        'company': md_yu.get('主体名称', yu['entity']),
        'metadata': {'主体名称': md_yu.get('主体名称', yu['entity']),
                     '主体编码': md_yu.get('主体编码', 'ENT-001'),
                     '情景名称': md_yu.get('情景名称', '基础情景'),
                     '情景编码': md_yu.get('情景编码', 'S-BASE')},
        'records': jilu,
        'subjects': yu.get('subjects', []),
        'config': pei,
        'bsc': None, 'kpi': {}, 'traces': [], 'splits': [], 'events': [],
        'baselines': [],
        # 经营变更：UI yes → 有经营变更册则 provided，否则 pending（接入说明口径）
        'changeStatus': biangeng_yinqing(zt),
    }
    # 已批准修订 → 引擎修订案（kemu/period/amount，金额=分）
    xiuding = [{'kemu': r['subject'], 'period': r['period'], 'amount': r['amount']}
               for r in zt.get('revisions', []) if r.get('approved')]

    jieguo = fenxi(zaihe, xiuding or None)
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(zt['runs']) + 1}"
    _RUNS[run_id] = jieguo                          # 内存留原始对象（报告再生成用）

    yinzi = tanping(jieguo.get('factors'))
    fengxian_shu = (yinzi.get('hong_shu') or 0) + (yinzi.get('huang_shu') or 0)
    zt['runs'].insert(0, {'id': run_id, 'period': zaihe['config']['period'],
                          'createdAt': xianzai(), 'company': zaihe['company'],
                          'status': 'done', 'riskCount': fengxian_shu, '快照': None})
    zt['currentRunId'] = run_id
    zt['dirty'] = False
    if ui_cfg:
        zt['config'] = json.loads(json.dumps(ui_cfg, ensure_ascii=False))
    if tixing:                                       # 多册提示如实进 warnings
        yuan = list(jieguo.get('warnings') or [])
        yuan.extend(tixing)
        jieguo['warnings'] = yuan
    return run_id, jieguo


def biangeng_yinqing(zt):
    """UI 变更状态（yes/none/unknown）→ 引擎口径（provided/pending/none/unknown）。"""
    yuan = (zt.get('background') or {}).get('changeStatus', 'unknown')
    if yuan == 'yes':
        you = any(f['category'] == '经营变更' and f['status'] == 'valid'
                  for f in zt.get('files', []))
        return 'provided' if you else 'pending'
    return yuan if yuan in ('none', 'unknown') else 'unknown'


def baocun_kuaizhao(zt, kuai):
    """把归一化结果写进当前运行条目（历史回放的依据）。"""
    run = dangqian_run(zt)
    if run is not None:
        run['快照'] = json.loads(json.dumps(kuai, ensure_ascii=False))


# ======================================================================
# 报告：生成（md+html+PDF）与页数
# ======================================================================

def zhuan_pdf(html_lu, pdf_lu):
    """html → PDF：本机 Chrome/Edge headless 打印（与 跑衡策全流程 同法）。"""
    html_lu, pdf_lu = Path(html_lu), Path(pdf_lu)   # 入参兼容 str
    for exe in LIULANQI:
        if not Path(exe).exists():
            continue
        subprocess.run([exe, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--no-pdf-header-footer', f'--print-to-pdf={pdf_lu}',
                        Path(html_lu).as_uri()],
                       capture_output=True, timeout=300)
        if pdf_lu.exists() and pdf_lu.stat().st_size > 2000:
            return True
    return False


def shu_yeshu(pdf_lu):
    """PDF 页数：统计 /Type /Page 对象（轻量正则，不引第三方）。"""
    try:
        return max(1, len(re.findall(rb'/Type\s*/Page[^s]', pdf_lu.read_bytes())))
    except OSError:
        return None


# ======================================================================
# action 分发（13 个，与 接入说明 §3 的表逐行对齐）
# ======================================================================

DONGZUO = {}                                        # action 名 → 处理函数


def dongzuo(ming):
    """注册装饰器：收集 action 处理函数。"""
    def bao(f):
        DONGZUO[ming] = f
        return f
    return bao


@dongzuo('workspace.load')
def _(zt, payload):
    """读取当前工作区（UI 启动即调；无运行时给空态骨架）。"""
    return fang_kuaizhao(zt)


@dongzuo('files.import')
def _(zt, payload):
    """导入工作簿：逐文件走三轨道校验；类别以解析结果为准（不信任文件名）。"""
    from excel_ingest_v11 import import_excel_v11
    wenjian = (payload or {}).get('files') or []
    if not wenjian:
        raise RuntimeError('没有收到文件')
    if (payload.get('mode') or 'append') == 'replace' and payload.get('category'):
        # 替换模式：先清同类旧册（含其八字段文本）
        zt['files'] = [f for f in zt['files']
                       if f['category'] != payload['category']]
    for w in wenjian:
        ming = w.get('name', '')
        if not ming.lower().endswith('.xlsx'):
            raise RuntimeError(f'{ming}：只接受 .xlsx 工作簿')
        # 字节两形状兼容：顶层 bytesB64（桥已打平）或 bytes:{bytesB64}（旧形状）
        b64 = w.get('bytesB64') or ''
        if not b64 and isinstance(w.get('bytes'), dict):
            b64 = w['bytes'].get('bytesB64') or ''
        zjie = base64.b64decode(b64)                  # 空字节会在契约层如实报错
        jie = import_excel_v11(zjie, ming)                    # 抛 ExcelError（中文文案）
        md = jie.get('metadata', {})
        # 同类同主体旧册让位（一类一主体一册；旧文本不再参与分析）
        zt['files'] = [f for f in zt['files']
                       if not (f['category'] == jie['category']
                               and f['entity'] == md.get('主体名称', ''))]
        zt['files'].append({
            'id': f'f{len(zt["files"]) + 1:03d}-{int(datetime.now().timestamp()) % 100000}',
            'name': ming, 'category': jie['category'], 'status': 'valid',
            'checks': jie.get('checks'), 'rows': jie.get('ruku_shu'),
            'size': renlei(len(zjie)), 'entity': md.get('主体名称', ''),
            'groupKey': jie.get('groupKey', ''), 'text': jie.get('text', ''),
            'subjects': jie.get('subjects', []), 'metadata': md,
            'importedAt': xianzai(),
        })
    zt['dirty'] = True
    return fang_kuaizhao(zt)


@dongzuo('files.remove')
def _(zt, payload):
    """移除一册导入（按 id）；移除后输入不再参与分析。"""
    rid = (payload or {}).get('id')
    zt['files'] = [f for f in zt['files'] if f['id'] != rid]
    zt['dirty'] = True
    return fang_kuaizhao(zt)


@dongzuo('templates.download')
def _(zt, payload):
    """四类官方空白模板（1.0.5 交付件原样下发，黑白空白可填）。"""
    lei = (payload or {}).get('category', '')
    lu = MOBAN_MU / f'{lei}输入模板.xlsx'
    if not lu.exists():
        raise RuntimeError(f'{lei}模板尚未随插件提供（文件缺失：{lu.name}）')
    return {'name': lu.name,
            'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'bytesB64': base64.b64encode(lu.read_bytes()).decode('ascii')}


@dongzuo('analysis.run')
def _(zt, payload):
    """十五步分析（配置来自 UI；未带配置时用默认档位，杜绝空档位拒绝）。"""
    _, jieguo = pao_fenxi(zt, (payload or {}).get('config') or moren_config())
    kuai = guiyi(jieguo, zt)
    baocun_kuaizhao(zt, kuai)
    return kuai


@dongzuo('background.save')
def _(zt, payload):
    """保存经营背景与变更状态（值未变化时不置脏——避免无感保存锁报告）。"""
    b = payload or {}
    xin = {'changeStatus': b.get('changeStatus', 'unknown'),
           'text': b.get('text', '')}
    if xin != (zt.get('background') or {}):
        zt['background'] = xin
        zt['dirty'] = True
    return fang_kuaizhao(zt)


@dongzuo('actions.update')
def _(zt, payload):
    """整改状态人工变更（pending/doing/done；计数回算由归一化层完成）。"""
    if not zt.get('currentRunId'):
        raise RuntimeError('请先运行分析，再处理整改事项')
    aid, xin = (payload or {}).get('id'), (payload or {}).get('status')
    if xin not in ('pending', 'doing', 'done'):
        raise RuntimeError(f'未知的整改状态：{xin}')
    zt['actionStatus'][aid] = xin
    kuai = fang_kuaizhao(zt)
    baocun_kuaizhao(zt, kuai)
    return kuai


@dongzuo('revisions.approve')
def _(zt, payload):
    """批准未来期间预算修订并真重算（届满期拒绝；金额整数分）。"""
    b = payload or {}
    if not b.get('approved'):
        raise RuntimeError('修订须勾选人工确认后才能批准')
    if not (b.get('reason') or '').strip():
        raise RuntimeError('修订原因不能为空')
    fen = b.get('amount')
    if not isinstance(fen, int) or isinstance(fen, bool) or fen < 0:
        raise RuntimeError('修订金额必须是非负整数（分）')
    if not zt.get('currentRunId'):
        raise RuntimeError('请先运行分析，再提请预算修订')
    cankao = fang_kuaizhao(zt)                       # 当前行/配置（快照或归一化）
    row = next((r for r in cankao['rows'] if r['id'] == b.get('rowId')), None)
    if row is None:
        raise RuntimeError(f'找不到对应差异行：{b.get("rowId")}')
    if (b.get('period') or '') <= (cankao['config'] or {}).get('period', ''):
        raise RuntimeError(f'期间 {b.get("period")} 已届满，预算与实际不可修订')
    zt['revisions'].append({'id': f'rv{len(zt["revisions"]) + 1:03d}',
                            'rowId': b['rowId'], 'period': b['period'],
                            'amount': fen, 'reason': b['reason'].strip(),
                            'approved': True, 'subject': row['subject'],
                            'createdAt': xianzai()})
    _, jieguo = pao_fenxi(zt, zt.get('config'))     # 修订后真重算
    kuai = guiyi(jieguo, zt)
    baocun_kuaizhao(zt, kuai)
    return kuai


# ======================================================================
# AI 文案（DeepSeek 官方 API）。密钥纪律：只从环境变量或 dsh 凭据服务
# 读取，源码/示例/测试零密钥字面量；调用失败如实抛错，不用占位冒充。
# SSRF 边界（固端请求）：目标域名写死于本模块，不接收调用方 URL；
# 用 http.client 直连（不跟随重定向）；TLS 默认上下文校验域名证书；
# 握手后核对实际对端 IP 必须为公网地址（阻断私网/环回/链路本地与
# DNS rebinding 指向内网的情形）。
# ======================================================================

import http.client
import ipaddress
import socket
import ssl
import urllib.error

AI_ZHUJI = 'api.deepseek.com'
AI_DIZHI = f'https://{AI_ZHUJI}/chat/completions'
_AI_MOXING_HUANCUN = []


def _du_miyao():
    """密钥两级：环境变量 DEEPSEEK_API_KEY → 凭据文件 refs 节（只读）。"""
    huan = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if huan:
        return huan
    jia = os.environ.get('DSH_HOME')
    if jia:
        wen = Path(jia) / '.credentials.yaml'
        if wen.exists():
            for hang in wen.read_text(encoding='utf-8').splitlines():
                m = re.match(r'^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$', hang)
                if m:
                    return m.group(1)
    return None


def _qing_ai(ti, miyao):
    """固端 HTTPS 请求（http.client 直连，无重定向跟随）。"""
    lian = http.client.HTTPSConnection(
        AI_ZHUJI, 443, context=ssl.create_default_context(), timeout=180)
    lian.connect()
    dui_duan = lian.sock.getpeername()[0]        # 实际连接 IP（握手后）
    if not ipaddress.ip_address(dui_duan).is_global:
        lian.close()
        raise RuntimeError(f'AI 端点解析到非公网地址 {dui_duan}，拒绝请求')
    lian.request('POST', '/chat/completions', body=ti, headers={
        'Host': AI_ZHUJI,
        'Authorization': 'Bearer ' + miyao,
        'Content-Type': 'application/json'})
    xiang = lian.getresponse()
    ma, ti = xiang.status, xiang.read()
    lian.close()
    return ma, ti


def _wen_ai(tishi, miyao, juese='', zui_da=4096):
    """单次文案调用。模型取环境 HENGCE_AI_MODEL，默认依次试官方别名与
    v4-flash（推理模型 content/reasoning_content 分离，只取 content）；
    zui_da 为输出上限（批量清单类调用可放大）。"""
    moxing_lie = _AI_MOXING_HUANCUN or [
        os.environ.get('HENGCE_AI_MODEL', ''),
        'deepseek-chat', 'deepseek-v4-flash']
    zui_hou = None
    for moxing in [m for m in moxing_lie if m]:
        ti = json.dumps({
            'model': moxing,
            'messages': [
                {'role': 'system', 'content':
                 '你是管理会计经营分析师。铁律：只使用用户材料中的数字，'
                 '禁止编造或推算新材料之外的数字；用简体中文，语气克制'
                 '专业，直接输出正文，不要寒暄与复述结构。' + juese},
                {'role': 'user', 'content': tishi}],
            'temperature': 0.3, 'max_tokens': zui_da,
        }).encode('utf-8')
        try:
            ma, hui_ti = _qing_ai(ti, miyao)
        except urllib.error.HTTPError as e:
            zui_hou = f'HTTP {e.code}'
            if e.code in (400, 404):            # 模型名不识别 → 试下一个
                continue
            raise RuntimeError(f'AI 调用失败（{moxing}）：{zui_hou}')
        if ma in (400, 404):
            zui_hou = f'HTTP {ma}：{hui_ti[:160].decode("utf-8", "replace")}'
            continue                            # 模型名不识别 → 试下一个
        if ma != 200:
            raise RuntimeError(f'AI 调用失败（{moxing}）：HTTP {ma} '
                               f'{hui_ti[:160].decode("utf-8", "replace")}')
        hui = json.loads(hui_ti.decode('utf-8'))
        wen = (hui['choices'][0]['message'].get('content') or '').strip()
        if not wen:
            raise RuntimeError(f'AI 返回空文案（{moxing}）')
        if not _AI_MOXING_HUANCUN:
            _AI_MOXING_HUANCUN.append(moxing)   # 首个可用模型缓存给后续调用
        return wen
    raise RuntimeError(f'AI 调用失败（无可用模型）：{zui_hou or "未配置模型"}')


def _ai_bao_wencai(miyao):
    """构造报告流水线的两个文案钩子（模块解读 / 总体解读）。"""
    def wencai(zhanshi, shuju_kuai):
        tishi = (f'本期「{zhanshi}」模块的数据表如下（预算 vs 实际；金额单位为分，'
                 f'比率单位为基点）。\n---\n{shuju_kuai}\n---\n'
                 '写一段 3-5 句的经营解读：整体表现如何、最值得注意的一到两项差异'
                 '（必须引用表中数字）、给管理者的一个行动方向。')
        return _wen_ai(tishi, miyao)

    def zongjie(jieguo):
        bao = jieguo['factors']
        meta = jieguo['meta']
        tishi = (f'主体 {meta["company"]}，期间 {meta["period"]}。整体判定包：'
                 f'完成率 {bao.wanchenglv_bps} 基点；预警分布 红 {bao.hong_shu} / '
                 f'黄 {bao.huang_shu} / 无 {bao.wu_shu}；单双环结论 {bao.panduan_jielun}'
                 f'（需审批{"是" if bao.shenpi else "否"}）；核心问题模块 {bao.hexin_mokuai}；'
                 f'BSC 总分 {bao.bsc_zongfen}（{bao.bsc_dengji or "未评级"}）；'
                 f'整改优先级 高 {bao.zhenggai_gao_shu} / 中 {bao.zhenggai_zhong_shu}。\n'
                 '写总体解读：先用 2-3 句概括本期经营全貌，再给管理层建议优先处理的'
                 '三件事（每件事一句并点出对应数字）。共 150-300 字。')
        return _wen_ai(tishi, miyao)
    return wencai, zongjie


def _ai_zhenggai(run, miyao, md_lu):
    """整改建议批量回填：一次调用生成全部条目建议，逐条替换（占位）行。
    解析不到的条目保持占位（诚实边界：宁可占位不冒充）。"""
    from baogao_liuxian import zhuan_html
    # correction 在引擎原始结果里是对象（zucheng_md 用属性访问），兼容两种形态
    jiao = run.get('correction') if isinstance(run, dict) else None
    if jiao is None:
        return False
    if isinstance(jiao, dict):
        qing = jiao.get('qingdan') or []
    else:
        qing = getattr(jiao, 'qingdan', None) or []
    tiao_mu = list(qing)
    if not tiao_mu:
        return False
    lie_biao = '\n'.join(f'{xu}. [{t.leixing}｜{t.zeren_mokuai}] {t.miaoshu}'
                         for xu, t in enumerate(tiao_mu, start=1))
    hui = _wen_ai(f'本期整改清单：\n{lie_biao}\n---\n'
                  '对每一条给出一句具体的处理建议（可点数字），按编号输出，'
                  '一行一条，格式严格为：编号. 建议（纯文本，不要加粗、'
                  '列表符号或代码块），不要多余内容。',
                  miyao, juese='每条一句，共输出与清单相同的条数。', zui_da=8192)
    jian_yi = {}
    for hang in hui.splitlines():
        # 容忍模型加的 markdown 修饰（**、-、>、[] 等）再取编号
        m = re.match(r'^[\s\-\*#>\[\|]*(?:\**)?\s*(\d{1,3})\s*\]*[\].、:：)]\s*(.+?)\s*\**\s*$', hang.strip())
        if m:
            jian_yi[int(m.group(1))] = m.group(2).strip()
    lu = Path(md_lu)
    wen = lu.read_text(encoding='utf-8')
    for xu, t in enumerate(tiao_mu, start=1):
        yuan = (f'**{xu}. [{t.leixing}｜{t.zeren_mokuai}]（占位）** '
                f'{t.miaoshu}——待 DSH 宿主 agent 回填。')
        if yuan in wen and jian_yi.get(xu):
            wen = wen.replace(yuan, f'**{xu}. [{t.leixing}｜{t.zeren_mokuai}]** '
                              f'{t.miaoshu}\n\n建议：{jian_yi[xu]}')
    lu.write_text(wen, encoding='utf-8')
    Path(str(md_lu).replace('.md', '.html')).write_text(
        zhuan_html(wen), encoding='utf-8')
    return True


@dongzuo('reports.generate')
def _(zt, payload):
    """对指定运行组装计算报告（md+html）并打印 PDF。"""
    from baogao_liuxian import compute_report_pipeline
    if zt.get('dirty'):
        raise RuntimeError('输入或配置已变更：请先重新运行分析，再生成报告')
    rid = (payload or {}).get('runId') or zt.get('currentRunId')
    if rid not in _RUNS:
        raise RuntimeError('该运行的原始结果已不在本进程（重启或更早的运行）：'
                           '请重新运行分析后再生成报告')
    run = next((r for r in zt['runs'] if r['id'] == rid), None)
    # ---- AI 解读（includeAI）：真实模型调用逐节回填；未配密钥如实报错 ----
    yao_ai = bool((payload or {}).get('includeAI'))
    wencai_hanshu = zongjie_hanshu = None
    if yao_ai:
        miyao = _du_miyao()
        if not miyao:
            raise RuntimeError('未配置 DeepSeek API 密钥：请先在 分析设置 → '
                               'AI 服务 保存密钥，或以 DEEPSEEK_API_KEY 环境'
                               '变量提供；不选"加入 AI 经营解读"仍可生成纯计算报告')
        print('[hengce] AI 解读启用：逐模块调用 DeepSeek（约 3-8 分钟）…',
              file=sys.stderr, flush=True)
        wencai_hanshu, zongjie_hanshu = _ai_bao_wencai(miyao)
    BAOGAO_MU.mkdir(parents=True, exist_ok=True)
    bao = compute_report_pipeline(_RUNS[rid], wencai_hanshu=wencai_hanshu,
                                  zongjie_hanshu=zongjie_hanshu,
                                  shuchu_mu=str(BAOGAO_MU))
    bao_id = f'report-{datetime.now().strftime("%Y%m%d-%H%M%S")}-{len(zt["reports"]) + 1}'
    # 流水线输出固定文件名（幂等设计）；复制成按报告 id 命名的存档，历史互不覆盖
    cun_md = BAOGAO_MU / f'{bao_id}.md'
    cun_html = BAOGAO_MU / f'{bao_id}.html'
    cun_md.write_bytes(Path(bao['md']).read_bytes())
    cun_html.write_bytes(Path(bao['html']).read_bytes())
    if yao_ai:
        try:                                    # 整改建议批量回填（md+html 重写）
            _ai_zhenggai(_RUNS[rid], miyao, str(cun_md))
        except Exception as e:                  # noqa: BLE001 建议失败不毁报告
            print(f'[hengce] 整改建议 AI 回填失败（保留占位）：{e}',
                  file=sys.stderr, flush=True)
    pdf_linshi = Path(bao['html']).with_suffix('.pdf')
    you_pdf = zhuan_pdf(str(cun_html), str(BAOGAO_MU / f'{bao_id}.pdf'))
    cun_pdf = BAOGAO_MU / f'{bao_id}.pdf'
    zt['reports'].insert(0, {
        'id': bao_id,
        'title': f'{(run or {}).get("period", "")} 计算报告'
                 + ('（含AI解读）' if yao_ai else ''),
        'period': (run or {}).get('period', ''), 'createdAt': xianzai(),
        'status': 'ready', 'format': 'PDF',
        'pages': shu_yeshu(cun_pdf) if you_pdf else None,
        'includeAI': yao_ai,           # True=模型逐节回填；False=纯计算+占位标注
        'mdPath': str(cun_md), 'htmlPath': str(cun_html),
        'pdfPath': str(cun_pdf) if you_pdf else None,
    })
    return fang_kuaizhao(zt)


@dongzuo('reports.export')
def _(zt, payload):
    """导出报告（md/html/pdf 真实字节；pdf 缺失时如实报错）。"""
    b = payload or {}
    bao = next((r for r in zt['reports'] if r['id'] == b.get('id')), None)
    if not bao:
        raise RuntimeError(f'找不到报告：{b.get("id")}')
    biaozhun = {'md': ('mdPath', 'text/markdown; charset=utf-8', '.md'),
                'html': ('htmlPath', 'text/html; charset=utf-8', '.html'),
                'pdf': ('pdfPath', 'application/pdf', '.pdf')}
    if b.get('format') not in biaozhun:
        raise RuntimeError(f'不支持的导出格式：{b.get("format")}')
    jian, mime, houzhui = biaozhun[b['format']]
    lu = bao.get(jian)
    if not lu or not Path(lu).exists():
        raise RuntimeError(f'报告文件不存在（{b["format"]}）：'
                           'PDF 依赖本机 Chrome/Edge 打印，可能未生成')
    return {'name': f'{bao["title"]}{houzhui}', 'mime': mime,
            'bytesB64': base64.b64encode(Path(lu).read_bytes()).decode('ascii')}


@dongzuo('reports.openFolder')
def _(zt, payload):
    """在资源管理器中定位报告文件（Windows）。"""
    bao = next((r for r in zt['reports'] if r['id'] == (payload or {}).get('id')), None)
    if not bao:
        raise RuntimeError(f'找不到报告：{(payload or {}).get("id")}')
    lu = Path(bao.get('pdfPath') or bao.get('htmlPath') or bao.get('mdPath') or '')
    if not lu.exists():
        raise RuntimeError('报告文件不存在，无法打开所在目录')
    subprocess.run(['explorer', '/select,', str(lu)], capture_output=True)
    return {'handled': True}


@dongzuo('history.open')
def _(zt, payload):
    """载入历史运行快照（保留完整历史列表与最新文件清单）。"""
    rid = (payload or {}).get('id')
    run = next((r for r in zt['runs'] if r['id'] == rid), None)
    if not run or not run.get('快照'):
        raise RuntimeError(f'找不到可回放的历史运行：{rid}')
    zt['currentRunId'] = rid
    kuai = json.loads(json.dumps(run['快照'], ensure_ascii=False))
    kuai['dirty'] = bool(zt.get('dirty'))
    kuai['files'] = wenjian_zhaiyao(zt)
    kuai['reports'] = baogao_zhaiyao(zt)
    kuai['history'] = lishi_zhaiyao(zt)
    return kuai


@dongzuo('assistant.ask')
def _(zt, payload):
    """助手提问由宿主对话承担（诚实拒绝，不用占位文案冒充模型回答）。"""
    raise RuntimeError('衡策助手在插件版由 DeepSeek Harness 宿主对话承担：'
                       '请回到主对话窗口提问；插件侧可用 hengce_import / '
                       'hengce_analyze / hengce_report 工具驱动同一条链路')


@dongzuo('hosting.apiKey')
def _(zt, payload):
    """AI 密钥：不带 key=查状态；带 key=写入/清除 dsh 官方凭据（热生效）。

    凭据文件 <DSH_HOME>/.credentials.yaml 的 refs 节是 dsh 官方机制
    （存储文件优先级最高，watch 自动热载，无需重启）。处理方式为"分节
    重建"：只动 version/refs 两节，refs 节里只动 DEEPSEEK_API_KEY 一行，
    records 节（账号登录态等）逐字保留。零 C 盘纪律：DSH_HOME 未设时
    拒绝写入（避免落到 C 盘默认家目录）。
    """
    import os
    jia = Path(os.environ['DSH_HOME']) if os.environ.get('DSH_HOME') else None
    wen = jia / '.credentials.yaml' if jia else None
    MIYAO_HANG = re.compile(r'^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$')

    def chai_hang(yuan):
        """按顶层键把文件拆成 [标题行, [子行...]] 的节列表（其余原样）。"""
        jie = []
        for hang in yuan.splitlines():
            if hang and not hang[0].isspace() and re.match(r'^[A-Za-z_][\w-]*:', hang):
                jie.append([hang, []])
            elif jie:
                jie[-1][1].append(hang)
        return jie

    def cha():
        """当前密钥状态：文件优先，其次启动环境变量；只回掩码不回原文。"""
        if wen and wen.exists():
            for hang in wen.read_text(encoding='utf-8').splitlines():
                m = MIYAO_HANG.match(hang)
                if m:
                    k = m.group(1)
                    return {'configured': True, 'source': 'file',
                            'masked': f'{k[:3]}***{k[-4:]}'}
        huan = os.environ.get('DEEPSEEK_API_KEY', '')
        if huan:
            return {'configured': True, 'source': 'env',
                    'masked': f'{huan[:3]}***{huan[-4:]}'}
        return {'configured': False, 'source': '', 'masked': ''}

    b = payload or {}
    if 'key' not in b:
        return cha()                                  # 查询：不动文件
    if wen is None:
        raise RuntimeError('未检测到 DSH_HOME（独立服务模式不落盘）：'
                           '请从衡策启动器或 dsh 客户端内使用本功能')
    xin = str(b.get('key') or '').strip()
    if xin and (len(xin) < 8 or re.search(r'\s', xin)):
        raise RuntimeError('密钥格式不对：应为 sk- 开头的连续字符串')

    yuan = wen.read_text(encoding='utf-8') if wen.exists() else 'version: 1\n'
    jie = chai_hang(yuan)
    ban = next((j for j in jie if j[0].startswith('version:')), None)
    tou = ban[0] if ban else 'version: 1'
    # refs 节里除本密钥外的其他子键原样保留（未来官方扩展不丢）
    refs_yu = [h for j in jie if j[0].startswith('refs:')
               for h in j[1] if h.strip() and not MIYAO_HANG.match(h)]
    qita = [h for j in jie
            if not j[0].startswith(('version:', 'refs:'))
            for h in [j[0]] + j[1]]

    xin_hang = ([tou, 'refs:'] + refs_yu
                + ([f'  DEEPSEEK_API_KEY: {xin}'] if xin else [])) \
        if (xin or refs_yu) else [tou]
    jia.mkdir(parents=True, exist_ok=True)
    linshi = wen.with_suffix('.tmp')
    linshi.write_text('\n'.join(xin_hang + qita) + '\n', encoding='utf-8')
    linshi.replace(wen)                               # 原子替换，watch 即刻热载
    return cha()


# ======================================================================
# 行协议主循环
# ======================================================================

def main():
    """stdin 逐行读请求 → 分发 → stdout 逐行回包（UTF-8，行 flush）。"""
    sys.stdin.reconfigure(encoding='utf-8')         # Windows 管道默认 GBK，必须重配
    sys.stdout.reconfigure(encoding='utf-8')
    sys.dont_write_bytecode = True                  # 不留 __pycache__ 副产物
    global _ZT
    _ZT = du_zhuangtai()
    for hang in sys.stdin:
        hang = hang.strip()
        if not hang:
            continue
        try:
            qing = json.loads(hang)
        except ValueError:
            _huifu({'id': None, 'ok': False, 'error': '请求不是合法 JSON'})
            continue
        hanshu = DONGZUO.get(qing.get('action'))
        if hanshu is None:
            _huifu({'id': qing.get('id'), 'ok': False,
                    'error': f'未知的 action：{qing.get("action")}'})
            continue
        try:
            data = hanshu(_ZT, qing.get('payload') or {})
            da = {'id': qing.get('id'), 'ok': True, 'data': tanping(data)}
        except Exception as e:                      # noqa: BLE001 业务错误统一回中文文案
            da = {'id': qing.get('id'), 'ok': False, 'error': str(e)}
        _huifu(da)


def _huifu(da):
    """回包 + 状态落盘（每个请求后持久化，崩溃不丢工作区）。"""
    sys.stdout.write(json.dumps(da, ensure_ascii=False) + '\n')
    sys.stdout.flush()
    try:
        xie_zhuangtai()
    except OSError:
        pass                                        # 状态写失败不阻断回包


if __name__ == '__main__':
    main()
