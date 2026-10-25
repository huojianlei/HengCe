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
本轮改造（2026-10-25 · T2）追加说明——遵守「只加注释与新增字段、不改既有行为」：
  ① action 协议：13 个 action 全部登记在 DONGZUO，处理函数签名统一 (zt, payload)
     -> dict/list；失败一律 raise RuntimeError(中文)，由 main() 捕获成
     {'id','ok':false,'error'} 回包，**绝不把堆栈或英文异常直接甩给用户**。
  ② 口径纪律（全链路不得违反，评论与代码同等对待）：
     · 金额一律整数分（fen），不做元/万元换算；比率一律整数基点（bps，1%=100）；
     · 缺数一律 None，不用 0 或空串冒充，前端按「缺数不臆造」渲染占位；
     · 已结账期间锁止：期间 ≤ 当前分析期间的预算/实际不可修订（届满期拒绝）；
     · Σ部门 ≡ 公司：v3 表内部门由读取器逐分勾稽，桥接层只做分组与展示。
  ③ AI 标注纪律：确定性计算（十五步）不标注；只有模型产出自然语言的地方
     （模块解读、总体解读、整改建议回填、助手问答）才标注，统一文案
     「内容为AI生成，仅供参考」，一字不改，且标注本身不得影响既有字段。
  ④ 报告 JSON：与 md/html/pdf 同批落盘，数字保持整数分/整数基点原值（不做换算）。
  ⑤ 本文件不含任何密钥字面量：AI 密钥只从环境变量或 dsh 凭据服务读取。
建立：2026-10-18 ｜ Agent：ZCode（GLM-5.3）
"""
import base64          # 文件字节 ↔ JSON 字符串
import dataclasses     # fenxi 结果里的 dataclass 摊平
import hashlib         # v3 表内部门的分册主体编码（与生成器 --bumen 推导一致）
import json            # 行协议与状态读写
import os              # 环境变量（AI 密钥 / DSH_HOME）
import re              # PDF 页数统计
import subprocess      # 报告 PDF 打印 + 打开目录
import sys             # stdio 重配置与路径引导
# 时间口径：对外时间戳一律北京时间（ISO 8601 带 +08:00），不用 UTC——
# 状态与报告里的「运行于/生成于」要和人看到的时钟一致，差 8 小时会被当成 bug。
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

# ---- 路径引导：backend 三段程序 + _vendor 算法树（全部相对本文件，自足包）----
# 四段程序各自维护相对导入（ingest_v11 的 excel_ingest_v11、houtai_hexin_python 的
# yinqing、报告组装的 baogao_liuxian、_vendor/algo 的 data_ingest 等清洗链），
# 这里统一前置进 sys.path，打包时无需改 import 语句。
# 注意 sys.path.insert(0) 是「后插者更靠前」：循环里 _vendor/algo 最后插入因而优先级
# 最高——这是刻意的，权威清洗链(daoru_csv)必须覆盖 backend 内的同名模块。
BEN_MU = Path(__file__).resolve().parent                  # backend 根
for _lu in (BEN_MU / 'ingest_v11',                        # 输入端口
            BEN_MU / 'houtai_hexin_python',               # 分析引擎
            BEN_MU / '报告组装',                           # 报告组装
            BEN_MU / '_vendor' / 'algo'):                  # 权威清洗链（data_ingest 等）
    if str(_lu) not in sys.path:
        sys.path.insert(0, str(_lu))

# 运行时数据全部落在 plugin\数据\（零 C 盘纪律）：状态文件、报告产物、
# 卸载引导脚本。目录本身按需创建，不随安装包预置空目录。
SHUJU_MU = BEN_MU.parent / '数据'                          # 运行时数据目录
BAOGAO_MU = SHUJU_MU / '报告'                              # 报告产物目录
ZHUANGTAI_LU = SHUJU_MU / '状态.json'                       # 工作区状态文件
MOBAN_MU = BEN_MU / '_vendor' / '空白模板'                  # 四类官方空白模板

# Chrome/Edge headless 打印 PDF 的候选（只读执行，不写 C 盘）
# 打印 PDF 只借用本机浏览器只读执行（headless），不安装依赖、不写 C 盘：
# 依次探测 Chrome → Edge(x86) → Edge，命中第一个可用者即返回；
# 全都没有时 PDF 缺省为 None，md/html 照常可用（降级而非失败）。
LIULANQI = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')

#: 预警名 → UI risk 枚举（红/黄之外一律 normal，含"无/无法"）
# ---- 枚举映射表：引擎中文枚举 → UI 英文枚举（接入说明 §5 的显式映射）----
# 纪律：只翻译、不改判定。任何未命中映射的值都落到中性档并保留原值字段，
# 不报错、不猜测——引擎新增枚举时 UI 最多显示成 normal，不会白屏。
FENGXIAN = {'红': 'high', '黄': 'watch'}
#: 引擎模块名 → UI 模块名（去"模块"后缀；接入说明 §5 的显式映射）
MOKUAI_JIAN = {'收入模块': '收入', '成本模块': '成本',
               '费用模块': '费用', '采购模块': '采购'}
#: 整改优先级 → UI 枚举（高→high，其余按关注档）
YOUXIANJI = {'高': 'high'}
#: 引擎整改状态 → UI 枚举（接入说明 actions.status 口径）
ZHUANGTAI_MAP = {'待整改': 'pending', '进行中': 'doing', '已完成': 'done'}

# 进程内存态（不落盘）：
#   _RUNS 存 fenxi 原始结果对象——报告再生成必须复用同一份计算，重算会让
#         报告数字与界面看到的漂移（同一 run 两个结果 = 不可解释）；
#   _ZT   是工作区状态的**唯一**内存副本，每个请求结束由 _huifu() 落盘。
# 重启后 _RUNS 清空，此时 reports.generate 会如实报「原始结果已不在本进程」，
# 而不是悄悄拿快照凑一份数字对不上的报告。
_RUNS = {}            # runId → fenxi 原始结果对象（进程内存；报告再生成用）
_ZT = None            # 工作区状态（main 里加载；每个请求后落盘）


# ======================================================================
# 基础工具：时间 / 状态读写 / 序列化
# ======================================================================

# ---- 时间工具 ----
# xianzai() 是**唯一时间源**：状态的 createdAt、报告登记、导入时间全用它，
# 保证同一请求内产生的多个时间戳格式/时区/精度一致、可直接字符串比较。
def xianzai():
    """当前时刻 ISO 8601（北京时间，带时区，秒精度）。"""
    # timespec='seconds'：秒精度足够展示，且去掉微秒后历史快照可逐字节比对（幂等）。
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


# ---- 状态骨架与读写 ----
# 空骨架的意义：UI 首次启动就直接读 files/rows/reports 等键，缺键会让前端拿到
# undefined 而渲染失败。所以宁可给空数组也不省略任何键——这是一份"形状契约"。
def kong_zhuangtai():
    """空状态骨架：全部字段就位，避免 UI 读到 undefined。"""
    return {
        'schemaVersion': '1.0',
        # 字段总览（写入方 = 各 action，读取方 = 归一化层）：
        #   files        已导入工作簿：含 text（八字段 CSV 原文）与 subjects/metadata，
        #                分析时把「最新预算册 + 最新实时册」两段 CSV 合并再清洗；
        #   config       最近一次分析配置（UI 形状），重启后回显用户上次设置；
        #   background   经营背景文本 + 变更状态（yes/none/unknown → 引擎 provided/pending）；
        #   actionStatus 整改状态人工覆盖：actionId → pending/doing/done（覆盖引擎原值）；
        #   revisions    已批准修订（金额=整数分）；带 departmentId 时按部门折算进公司汇总；
        #   currentRunId 当前展示运行号；runs 为历史列表（含快照，可回放）；
        #   reports      报告登记：md/html/pdf/json 四路径 + 页数 + includeAI + aiNotice；
        #   dirty        输入/背景/配置相对最近一次运行的变更标记：True 时禁止生成报告与问答。
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


# 读状态：文件不存在 = 首次启动；JSON 损坏 = 被外部改坏或写了一半。
# 两类都回空骨架——状态是可重建的派生数据，为它硬失败只会让 UI 打不开。
def du_zhuangtai():
    """读状态文件；不存在或损坏则回空骨架（状态可重建，不值得硬失败）。"""
    if ZHUANGTAI_LU.exists():
        try:
            return json.loads(ZHUANGTAI_LU.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    return kong_zhuangtai()


# 写状态：先写 .tmp 再原子 replace。Windows 上直接覆盖写若中途断电会留半截
# JSON，下次启动就丢工作区；临时文件放同目录才保证 replace 是同卷原子操作。
def xie_zhuangtai():
    """状态落盘（原子写：先临时文件再替换，避免半截 JSON）。"""
    if _ZT is None:
        return
    SHUJU_MU.mkdir(parents=True, exist_ok=True)
    linshi = ZHUANGTAI_LU.with_suffix('.tmp')
    linshi.write_text(json.dumps(_ZT, ensure_ascii=False, indent=1),
                      encoding='utf-8')
    linshi.replace(ZHUANGTAI_LU)


# 摊平：fenxi 返回里含 dataclass（判定包/报告包等）与 SimpleNamespace，
# 直接 json.dumps 会抛 TypeError。这里递归转成纯 dict/list/标量，
# 供「回包 + 状态落盘 + 归一化」三处共用，是唯一的序列化入口。
def tanping(x):
    """fenxi 结果对象 → 纯 JSON 结构（dataclass/SimpleNamespace 递归摊平）。

    归一化与回包共用；Decimal/Path 等罕见类型转 str 兜底，保证可落盘可回传。
    """
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        # dataclass 判断要在 dict 之前，且必须排除 isinstance(x, type)——
        # dataclasses.is_dataclass() 对「类对象本身」也返回 True，但不该被 asdict()。
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


# 展示用大小：与 UI 演示数据口径一致（1 KB = 1024 字节，KB/MB 取整）。
# 只用于列表里给人看，不参与任何计算或校验。
def renlei(n):
    """字节数 → 人类可读（KB/MB，与 UI 演示口径一致）。"""
    if n < 1024:
        return f'{n} 字节'
    if n < 1024 * 1024:
        return f'{round(n / 1024)} KB'
    return f'{round(n / 1024 / 1024, 1)} MB'


# 三个「摘要」函数：状态里的完整记录 → UI 需要的展示字段**白名单**。
# 关键是白名单而非整条透传：text（八字段 CSV 原文，几十 KB）与 subjects
# 结构体只在分析时用，进 workspace 回包会让每一帧都多传好几 MB。
def wenjian_zhaiyao(zt):
    """状态里的文件清单 → UI files 条目（只带展示字段）。"""
    return [{k: f.get(k) for k in ('id', 'name', 'category', 'status',
                                   'checks', 'rows', 'size', 'entity')}
            for f in zt.get('files', [])]


# 报告摘要**刻意不带盘上路径**（mdPath/htmlPath/pdfPath）：
# UI 只需要展示标题/期间/页数/是否含 AI；路径属于本机信息，
# 导出时按 id 反查，避免前端拿到绝对路径后自行拼文件。
def baogao_zhaiyao(zt):
    """状态里的报告登记 → UI reports 条目（不带盘上路径）。"""
    # 白名单式投影：只把 UI 需要的字段送出去，mdPath/htmlPath/pdfPath/jsonPath
    # 这类磁盘路径一律不出后端（前端也不该知道本机目录布局）。
    # aiGenerated/aiNotice 是 1.1.5 新增的 AI 标注契约：UI 用 aiNotice 原文渲染
    # 标签，用 aiGenerated 判断要不要渲染（纯计算报告两字段为 False/空）。
    return [{k: r.get(k) for k in ('id', 'title', 'period', 'createdAt',
                                   'status', 'format', 'pages', 'includeAI',
                                   'aiGenerated', 'aiNotice')}
            for r in zt.get('reports', [])]


# 历史摘要不带「快照」本体（那是完整归一化 workspace，几十 KB～MB）：
# 回放时才按 id 取快照，列表接口保持轻量。
def lishi_zhaiyao(zt):
    """状态里的运行历史 → UI history 条目（不带快照本体）。"""
    return [{k: r.get(k) for k in ('id', 'period', 'createdAt',
                                   'company', 'status', 'riskCount')}
            for r in zt.get('runs', [])]


# 分组：按 (主体编码, 情景编码, 年度, 期间粒度) 四元组归组——正是导入契约的
# 原生分组键 groupKey。分组决定「一次分析算哪些册」，所以对冲突零容忍：
# 同组两个值不一致直接抛中文错，让用户按年度/期间分批导入，绝不静默合并。
def wenjian_fenzu(wenjian):
    """按导入契约的完整分组键归档，并阻止同一组混入冲突元数据。"""
    fenzu = {}
    bianma = {}
    for f in wenjian:
        if f.get('status') != 'valid':
            continue
        md = f.get('metadata') or {}
        try:
            jian = tuple(json.loads(f.get('groupKey') or '[]'))
        except (ValueError, TypeError):
            jian = ()
        # 老数据 / 没有 groupKey 的册：用 metadata 四字段兜底重建（缺省情景 S-BASE、
        # 粒度月度）——与生成器默认口径一致，保证升级前写的状态文件仍能打开。
        if len(jian) != 4:
            jian = (md.get('主体编码') or f.get('entity', ''),
                    md.get('情景编码') or 'S-BASE', md.get('年度', ''),
                    md.get('期间粒度', '月度'))
        # zu_id 只取「主体 + 情景」：年度/粒度不同属于同名主体的配置冲突，
        # 用 zu_id 做冲突检测键，报错文案才能指明是哪个分组出的问题。
        zu_id = f'{jian[0]}::{jian[1]}'
        if zu_id in bianma and bianma[zu_id] != jian:
            raise RuntimeError(f'{zu_id} 的年度或期间粒度不一致，请按年度和周期分别分析')
        bianma[zu_id] = jian
        ming = md.get('主体名称') or f.get('entity', '')
        zu = fenzu.setdefault(jian, {'id': zu_id, 'name': ming.rsplit('/', 1)[-1],
                                     'title': ming, 'scenario': jian[1],
                                     'scenarioName': md.get('情景名称', jian[1]),
                                     'metadata': md, 'files': []})
        for zi in ('主体编码', '主体名称', '情景编码', '情景名称', '年度', '期间粒度'):
            yuan, xin = zu['metadata'].get(zi), md.get(zi)
            if yuan and xin and yuan != xin:
                raise RuntimeError(f'分组 {zu_id} 的「{zi}」不一致（{yuan} / {xin}），请核对工作簿')
        if zu['title'] != ming:
            raise RuntimeError(f'分组 {zu_id} 的主体名称不一致，请核对工作簿')
        zu['files'].append(f)
    return list(fenzu.values())


# 部门下拉（UI entities）：入参是分组列表，出参是下拉选项。
# 口径（用户 2026-09 拍板）：单公司单册时只给「全部部门」，保持旧载荷不变；
# 有部门册时公司总册并入「全部部门」——两者口径完全相同，单列会出现重复项。
def bumen_xuanxiang(fenzu):
    """单公司保持旧载荷；有部门时公司总册并入「全部部门」，不再单列
    （两者口径完全相同，下拉里会重复）。"""
    quanbu = [{'id': 'all', 'name': '全部部门'}]
    you_bumen = any('/' in z['title'] for z in fenzu)
    if not you_bumen and len(fenzu) == 1:
        return quanbu
    for zu in fenzu:
        if you_bumen and '/' not in zu['title']:
            continue
        tongming = [z for z in fenzu if z['name'] == zu['name']]
        ming = zu['name']
        if len(tongming) > 1:
            ming += f' · {zu["scenarioName"]}'
            if len({z['title'] for z in tongming}) > 1:
                ming = f'{zu["title"]} · {zu["scenarioName"]}'
        quanbu.append({'id': zu['id'], 'name': ming,
                       'title': f'{zu["title"]} · {zu["scenarioName"]}'})
    return quanbu


# 量价拆分摘要：引擎字段名是 元/分 混杂（yuandan_zong_fen 等），这里逐一映射
# 成 UI 驼峰名，**数值原样搬运**（金额=分、比率=基点），只改键名不改值。
# identityOk 直接透传引擎恒等式判定，前端据此显示「量价恒等式成立/不成立」。
def chaifen_zhaiyao(qu_splits):
    """量价拆分结果 → 界面摘要（科目 × 规划/执行两栏 + 四项细分 + 恒等式）。"""
    lie = []
    for x in (qu_splits or []):
        r = x.get('result') or {}
        lie.append({
            'subject': x.get('kemu'), 'period': x.get('period'),
            'total': r.get('yuandan_zong_fen'), 'totalFa': r.get('yuandan_zong_fa'),
            'planning': r.get('guihua_zong_fen'), 'planningFa': r.get('guihua_zong_fa'),
            'execution': r.get('zhixing_zong_fen'), 'executionFa': r.get('zhixing_zong_fa'),
            'pricePlanning': r.get('jiage_guihua_fen'),
            'priceExecution': r.get('jiage_zhixing_fen'),
            'usagePlanning': r.get('yongliang_guihua_fen'),
            'usageExecution': r.get('yongliang_zhixing_fen'),
            'residual': r.get('cancha_fen'),
            'identityOk': r.get('hengdengshi_chengli'),
        })
    return lie or None


# 积木（building_blocks）摘要：四模块差额 + 未归属行 + 净总差异。
# unassigned 由未归属行差额求和（金额=分），用于提示「有成本没归到模块」；
# 分母 denominator 一并透传，前端才好在同一口径下算占比。
def jimu_zhaiyao(qu_blocks):
    """积木四模块结果 → 界面摘要（差额/占比/方向/行数 + 未归属 + 净总差异）。"""
    b = qu_blocks or {}
    lie = b.get('mokuai_lie') or []
    if not lie:
        return None
    wei = b.get('weiguishu_lie') or []
    return {
        'modules': [{'name': k.get('mokuai'), 'variance': k.get('chae_fen'),
                     'fa': k.get('fa'), 'ratioBps': k.get('zhanbi_bps'),
                     'rows': k.get('hang_shu')} for k in lie],
        'unassigned': sum((h.get('chae_fen') or 0) for h in wei),
        'unassignedRows': len(wei),
        'unassignedBps': b.get('weiguishu_zhanbi_bps'),
        'netTotal': b.get('jing_heji_fen'),
        'denominator': b.get('zhanbi_fenmu_fen'),
        'core': b.get('hexin_mokuai'),
    }


# ======================================================================
# workspace 归一化（fenxi 19 键 → UI normalized workspace）
# ======================================================================

# ============================================================================
# guiyi() 是全文件最复杂的一段：把引擎 19 键结果翻译成 UI 可直接渲染的
# normalized workspace。它必须同时满足三条硬约束（改这里前先读这三条）：
#   ① 只翻译不计算——比值/差额全部用引擎算好的分/基点值，桥接层绝不重算；
#   ② 缺数不臆造——引擎没有的字段给 None/空串，由前端渲染占位；
#   ③ 叠加状态层——整改状态覆盖、文件清单、报告登记、历史来自 zt 而非引擎。
# 输出形状由 ui/src/演示数据.mjs 与 docs/接入说明.md §5 双重约束：
# 加字段可以（向前兼容），改字段名或语义 = 改契约，必须同步改 UI。
# ============================================================================
def guiyi(jieguo, zt):
    """当前运行 + 状态覆盖层 → 完整 normalized workspace（UI 唯一数据源）。

    jieguo 可以是 fenxi 原始对象（本进程内）或其摊平 dict（形状同名）。
    """
    # 统一视图：入参可能是 fenxi 原始对象（本进程刚跑完）或快照里的摊平 dict
    # （历史回放）。tanping 后两者形状同名，后续取值逻辑只需写一份。
    qu = tanping(jieguo)                           # 统一成 dict 视图
    meta = qu.get('meta') or {}
    pei = qu.get('config') or {}
    subjects = qu.get('subjects') or []
    # 科目 → 模块只做名字收敛（收入模块→收入）；未登记的模块原样透传，
    # 保证引擎将来新增模块时 UI 顶多显示英文名，不会变成空串。
    kemu_mokuai = {s['kemu']: MOKUAI_JIAN.get(s['module'], s['module'])
                   for s in subjects}               # 科目 → UI 模块名
    kemu_leibie = {s['kemu']: s.get('direction', '') for s in subjects}

    # 预警名 → UI risk：按档位阈值排序，最高档=high、其余档=watch、未命中=normal
    # （引擎 yujing 取配置档位名；老口径 红/黄 作无档位时的兜底映射）
    # 档位 → risk 口径：引擎按预警阈值给档位名（关注/高风险…）。归一化按阈值升序，
    # 最高档 = high、其余 = watch、未命中 = normal；
    # FENGXIAN 的 红/黄 是 1.1.0 老口径兜底，仅在引擎没给 tiers 时起作用。
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
    # ---- rows：差异明细（一行 = 一个科目 × 一个期间）----
    # 数据来源三处：variance.xiang 是差异表主体；decisions 给「是否需要审批」判定；
    # records 给「这条数来自哪本册第几行」的来源定位（UI 悬浮提示用）。
    chayi = (qu.get('variance') or {}).get('xiang') or []
    # 判定键 = (科目, 期间)。引擎可能对同一组合给多条判定（单双环 + 行业修正），
    # dict 覆盖为后者——与 UI「一行只显示一条判定」的展示口径一致。
    panduan = {(d.get('kemu'), d.get('period')): d
               for d in (qu.get('decisions') or [])}
    # 来源定位：实际行优先，其次预算行（hanghao 来自八字段入库序）
    # 来源定位：先放实际行、再放预算行（setdefault 保证实际优先），
    # 文案「实时经营 · 行37」直接给人看，行号来自八字段入库序（1 基）。
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
        # 方向映射 F/A/N：F=有利、A=不利；N=中性时按「收入类顺差算有利、成本类逆差算有利」
        # 归入二值枚举——接入说明 §5 要求 UI 只认 favorable/unfavorable，不设第三态。
        if x.get('fa') == 'F':
            fang = 'favorable'
        elif x.get('fa') == 'A':
            fang = 'unfavorable'
        else:
            shun = (chae >= 0) if kemu_leibie.get(kem) == '收入类' else (chae <= 0)
            fang = 'favorable' if shun else 'unfavorable'
        # 行字段口径：budget/actual/variance 金额=整数分；rate=整数基点；
        # 实际缺失时 variance/rate 给 None（不写成 0，避免「0 差异=无问题」的误读）；
        # 部门与 departmentId 先给 '' 和 'all'，部门行在函数末尾统一覆盖。
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
    # 行 id 索引：整改条目要靠 (科目, 期间) 反查对应的差异行，供 UI 点击跳转。
    rowid = {(r['subject'], r['period']): r['id'] for r in rows}

    # ---- trend：营业收入（无则空序列）逐月 预算/实际/滚动 ----
    # ---- trend：营业收入趋势（首页折线只画营业收入）----
    # 规则：已发生期间只给实际，未来期间只给滚动预测，初始预算始终给；
    # 「未来」按期间字符串比较（'YYYY-MM' 的字典序与时间序一致，无需解析日期）。
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
    # ---- actions：整改清单 + 人工状态覆盖 ----
    # 两个来源：correction.qingdan 是引擎整改清单；老版本或部门视图可能只出
    # dashboard.zhenggai_block.qingdan，故按此顺序兜底。
    qingdan = ((qu.get('correction') or {}).get('qingdan')
               or (qu.get('dashboard') or {}).get('zhenggai_block', {}).get('qingdan')
               or [])
    actions = []
    yi_aid = {}
    for it in qingdan:
        # actionId 规则：'a-{科目}-{期间}'，稳定可复现——人工状态覆盖以它为键，
        # 换规则会让历史状态全部作废。同一组合重复出现时追加序号保唯一。
        aid = f'a-{it.get("kemu", "")}-{it.get("qijian", "")}'
        # 引擎会对同一科目+期间出多条整改（如"关注整改"+"人工复核"）；
        # 追加序号保唯一。首次保持原 id，老数据（无重复）逐字节不变。
        if aid in yi_aid:
            yi_aid[aid] += 1
            aid = f'{aid}-{yi_aid[aid]}'
        else:
            yi_aid[aid] = 1
        yuan = it.get('zhuangtai') or '待整改'
        actions.append({
            'id': aid, 'rowId': rowid.get((it.get('kemu'), it.get('qijian'))),
            'title': f'{it.get("leixing", "整改")}：{it.get("kemu", "")}',
            'department': it.get('zeren_mokuai', ''),
            # 引擎清单不带责任人与截止日——占位字符串而非 null（UI 卡片对两者调 .slice）
            # 责任人与截止日：引擎清单不带这两项，给占位字符串而非 None——
            # UI 卡片会对 owner 调 .slice()，null 会直接崩（既有展示契约，别改成 null）。
            'owner': '未指派', 'due': '',
            'status': zt['actionStatus'].get(aid, ZHUANGTAI_MAP.get(yuan, 'pending')),
            'priority': YOUXIANJI.get(it.get('youxianji'), 'watch'),
            'type': 'revision' if '修订' in (it.get('leixing') or '') else 'execution',
            'description': it.get('miaoshu', ''),
        })

    # ---- kpis：系数包实算值优先，KPI 库按名册补 null（缺数不臆造）----
    # ---- kpis：KPI 卡片 ----
    # 顺序口径：系数包实算值在前（完成率），KPI 库名册在后且只给引擎已算出的值；
    # 名册里有但算不出的指标不补 0——缺数给 null，前端显示「—」。
    yinzi = qu.get('factors') or {}
    kpis = []
    if yinzi.get('wanchenglv_bps') is not None:
        kpis.append({'name': '预算完成率', 'value': yinzi['wanchenglv_bps'],
                     'unit': '%', 'note': '系数包实算（分/基点口径）'})
    for k in ((qu.get('dashboard') or {}).get('kpi_block') or []):
        kpis.append({'name': k.get('mingcheng', ''), 'value': k.get('zhi'),
                     'unit': '%', 'note': ''})

    # ---- config 回显：引擎形状 → UI 形状（档位字段名反转）----
    # 配置回显：引擎 tier 用中文键（ming_cheng/yan_se/yu_fen），UI 用
    # name/color/threshold；只做键名反转，阈值单位仍是基点。
    tiers = [{'name': t.get('ming_cheng'), 'color': t.get('yan_se'),
              'threshold': t.get('yu_fen')} for t in (pei.get('tiers') or [])]
    dangqian = dangqian_run(zt)

    gongzuoqu = {
        'schemaVersion': '1.0',
        # schemaVersion 是 UI 的数据版本号；demo 是演示标志位——插件版恒为 False
        #（演示数据只走独立的演示生成器，不混进真实工作区）。
        'demo': False,
        'dirty': bool(zt.get('dirty')),
        # meta.runId 取状态里的当前运行号而非引擎的：引擎不产运行号，
        # 运行号是桥接层「一次分析的标识」，报告与助手问答都靠它对齐版本。
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
        # entities 来自分析时算好的部门下拉（_entities）；无部门时只有 all 一项，
        # 保证 UI 下拉永远至少有一个可渲染项。
        'entities': qu.get('_entities') or [{'id': 'all', 'name': '全部部门'}],
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
        'blocks': jimu_zhaiyao(qu.get('blocks')),
        'splits': chaifen_zhaiyao(qu.get('splits')),
    }
    # ---- 部门行合成：一次分析同时返回公司汇总 + 各部门视图 ----
    # 部门结果递归复用 guiyi()（_departmentGroups 的 result 是同一形状），
    # 但传 actionStatus={} 防止部门状态污染公司汇总，随后再单独叠加。
    if qu.get('_departmentGroups'):
        for a in actions:
            a['departmentId'] = 'all'
    for zu in qu.get('_departmentGroups') or []:
        # 行 id 与 actionId 一律加「部门组id:」前缀：UI 用 id 做唯一键，
        # 不加前缀会让公司与部门的同名差异行互相覆盖。
        bumen = guiyi(zu['result'], {**zt, 'actionStatus': {}})
        for r in bumen['rows']:
            r.update(id=f'{zu["id"]}:{r["id"]}', departmentId=zu['id'],
                     department=zu['name'])
            rows.append(r)
        for a in bumen['actions']:
            yuan_id = a['id']
            a.update(id=f'{zu["id"]}:{yuan_id}', department=zu['name'],
                     departmentId=zu['id'],
                     rowId=f'{zu["id"]}:{a["rowId"]}' if a['rowId'] else None)
            a['status'] = zt['actionStatus'].get(a['id'], a['status'])
            actions.append(a)
    return gongzuoqu


# 当前运行条目：currentRunId 可能指向一条已不在 runs 里的旧 id（状态被外部改过），
# 此时返回 None，调用方按「无当前运行」处理，而不是抛异常。
def dangqian_run(zt):
    """状态里的当前运行条目（无则 None）。"""
    rid = zt.get('currentRunId')
    for r in zt.get('runs', []):
        if r.get('id') == rid:
            return r
    return None


# 对外统一出口：UI 每次看到的 workspace 都从这里出。三条路径——
#   ① 本进程内跑过 → 用原始对象归一化（最新结果，可再生成报告）；
#   ② 只有快照   → 回放快照，并叠加最新文件/报告/历史清单；
#   ③ 都没有     → 空工作区（首次启动 / 清空之后）。
def fang_kuaizhao(zt):
    """按当前运行出 workspace：内存原始对象 → 归一化；否则回放历史快照。

    快照回放会把文件清单换成最新状态并叠加 dirty/提醒，保证 UI 与实际
    导入状态一致（快照里的 rows/actions 等仍是当时的计算结果）。
    """
    if zt.get('currentRunId') in _RUNS:
        return guiyi(_RUNS[zt['currentRunId']], zt)
    run = dangqian_run(zt)
    if run and run.get('快照'):
        # 深拷贝快照再改：run['快照'] 是历史存档，绝不能就地修改——
        # 否则历史会被当前文件清单覆盖，回放出来的就不是「当时的结果」了。
        # （history.open 里有同款一行，这里打第 1 处 = 快照出口）
        # 深拷贝快照再改：直接改 run['快照'] 会污染历史（回放一次就把当时的
        # dirty/files/reports 固化进去，下次回放看到的就不是当时的现场了）。
        # 用 json 往返是最省事且足够深的拷贝（快照本身就是 JSON 可序列化结构）。
        kuai = json.loads(json.dumps(run['快照'], ensure_ascii=False))
        # 回放视图里 dirty 取「当前状态」而不是快照里的旧值：用户回放历史后
        # 如果输入已改动，报告按钮仍然必须锁住，否则会拿旧快照出一份新报告。
        # files/reports/history 三个摘要同样取当前值——它们描述的是"工作区现状"，
        # 只有 rows/trend/actions 等分析结论来自那份历史快照。
        kuai['dirty'] = bool(zt.get('dirty'))
        kuai['files'] = wenjian_zhaiyao(zt)
        kuai['reports'] = baogao_zhaiyao(zt)
        kuai['history'] = lishi_zhaiyao(zt)
        return kuai
    return kong_gongzuoqu(zt)


# 空工作区也要给完整骨架 + 一句可执行的引导：warnings 直接写「下一步该做什么」，
# 前端的空态提示就读 warnings，不再自己拼文案（文案只有一处，改起来才不遗漏）。
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
            'entities': bumen_xuanxiang(wenjian_fenzu(zt.get('files', []))),
            'files': wenjian_zhaiyao(zt),
            'rows': [], 'trend': [], 'actions': [], 'revisions': [],
            'reports': baogao_zhaiyao(zt),
            'history': lishi_zhaiyao(zt),
            'kpis': [], 'background': zt.get('background'),
            'blocks': None, 'splits': None, 'warnings': tixing}


# 默认配置与引擎拍板口径一致：关注档 1500 基点(15%)、高风险档 3000 基点(30%)，
# 显著性/噪声门限各 2500 基点(25%)。UI 未带配置时用它，杜绝「空档位」被引擎拒绝。
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

# ---- 配置翻译与载荷组装 ----
# UI 配置（tiers: name/color/threshold）→ 引擎配置（ming_cheng/yan_se/yu_fen）。
# 全部数值过 int() 闸：UI 输入框可能给 "2500" 字符串或 null，引擎只认 int。
def zuhe_peizhi(ui_cfg):
    """UI 配置 → 引擎 config（档位字段名映射 + 整数闸）。"""
    c = ui_cfg or {}
    try:
        # 逐字段闸门：growth 缺省 0；industry 允许 None（未设对标）；
        # 阈值缺省值与 moren_config 保持一致（50/2500/2500），三处口径只能有一个来源。
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
    # 只捕获这三类（都是 UI 值的形状问题）。其他异常让它冒出去——
    # 真正的程序 bug 不该被包成「分析配置不完整」而掩盖。
    except (KeyError, TypeError, ValueError) as e:
        raise RuntimeError(f'分析配置不完整或类型不对：{e}') from e


#: 非财务指标字段名 → KPI 百分比字段的换算（表值 0-100 → 0-10000 基点由 kpi.py 定；
#: 这里只做"表值即比率分子分母已除"的直传，字段名与 KpiShuru 一致）
# 量价拆分：v3s 册 liangjia 表 → 引擎 splits 输入。
# 字段名差异：读取层无后缀（biaozhun_danjia），ChaifenShuru 要 _fen 后缀；
# 期间统一取分析期间（=已结账月），引擎判定表按当期行取拆分线索。
def liangjia_splits(shi, jilu, pei):
    """量价拆分参数（v3s 册 liangjia）→ 引擎 splits 输入。

    引擎口径：splits 挂到（科目, 期间）——判定表按当期行取拆分线索；
    期间取分析期间（结账月）；金额字段已在读取层转分。"""
    lj = (shi or {}).get('liangjia') or []
    if not lj:
        return []
    qijian = pei.get('period') or ''
    # 读取层字段名（无后缀）→ ChaifenShuru 字段名（金额带 _fen 后缀）
    # 映射表只覆盖金额三项：数量、单价等其余字段两边同名，直传即可。
    duizhao = {'biaozhun_danjia': 'biaozhun_danjia_fen',
               'xiuding_danjia': 'xiuding_danjia_fen',
               'shiji_chengben': 'shiji_chengben_fen'}
    return [{'kemu': x['kemu'], 'period': qijian, 'values': {
        duizhao.get(k, k): v for k, v in x.items() if k != 'kemu'}} for x in lj]


# 经营变更：只取「最近一本有效」的经营变更册，把已批准事件投成引擎 events。
# 两道过滤（都是引擎硬要求）：① 编码能映射到本期科目；② 期间在本期实际记录里
#（事件必须挂在已届满的科目×期间上，否则引擎判为无效事件）。
# 映射不到的计入 diu 并不上抛——诚实边界：跳过，不硬塞一个猜的科目。
def biangeng_shijian(zt, subjects, jilu, pei):
    """经营变更册的已批准事件 → 判定链 events 输入。

    经营变更的科目影响用 12 表科目编码（EXP1.021 等），而 9 表轨道的记录科目
    是两级名（销售费用/差旅费）。这里按读取器登记的 accountCode
    （EXP.销售费用.021）做编码→科目名映射；映射不到或期间不在本期差异行内的
    事件跳过（引擎要求事件必须挂在已届满的科目×期间上）。"""
    bg = next((f for f in reversed(_biangeng_lie(zt))
               if f.get('category') == '经营变更' and f.get('status') == 'valid'), None)
    if not bg:
        return []
    # 编码 → 科目名映射：读取器给每个科目登记了 accountCode（EXP.销售费用.021），
    # 用它把 12 表科目编码翻成九表轨道的两级科目名（销售费用/差旅费）。
    ke = {s.get('accountCode'): s['kemu'] for s in (subjects or [])
          if s.get('accountCode')}
    ming = {s['kemu'] for s in (subjects or [])}
    # 12 表编码 EXP1.021 → EXP.销售费用.021：第二位数字是费用大类，
    # 按大类表还原读取器登记的形状后再查科目名。
    bian = {1: '销售费用', 2: '管理费用', 3: '其他主体费用'}
    # 本期已发生期间集合：取「实际」记录的期间，不取预算记录的——
    # 预算可以填未来月份，实际不会；用预算期间会把未来事件误判成已届满。
    qijian_ji = {getattr(r, 'qijian', None) for r in (getattr(jilu, 'shishi', None) or [])}
    out, diu = [], 0
    for e in bg.get('events') or []:
        code = str(e.get('code') or '')
        kem = ke.get(code)
        if not kem:
            ma = re.fullmatch(r'EXP([123])\.(\d{3})', code)
            if ma:
                kem = ke.get(f'EXP.{bian[int(ma.group(1))]}.{ma.group(2)}')
        if not kem:
            kem = e.get('kemu') if e.get('kemu') in ming else None
        if not kem or e.get('period') not in qijian_ji:
            diu += 1
            continue
        out.append({'kemu': kem, 'period': e['period'],
                    'structural': bool(e.get('structural')),
                    'reason': e.get('reason') or ''})
    return out


# KPI 取数：财务 9 项由八字段记录 + 三表快照推导，非财务 6 项由 v3k 册直取。
# 派生口径一律「能算才算」：算不出就是 None（缺数纪律），绝不拿 0 顶替，
# 否则 KPI 得分会被大量 0 值稀释成假象。
def kpi_shuru(jilu, shi):
    """从既有记录推导财务 9 项 + 从实时经营册读非财务 6 项 → KpiShuru 字段 dict。

    财务推导口径（期间 = 本期已结账月）：
        收入/费用实际与预算：八字段记录按科目类汇总（分）；
        期初期末流动资产/负债：资产负债表三表快照（v2 轨 three）；
        资本占用：非流动负债+权益合计（缺数 None）；
        采购成本：科目含"采购"的实际数（无则 None）。
    非财务：shi 册带 kpi_input（v3k 十一表）时按字段直取。"""
    from decimal import Decimal
    from excel_ingest_v3_kpi import LV_ZHUAN as _LV_ZHUAN
    # 按科目类汇总（只认单位=元的记录，读取层已把金额转成整数分）：
    # 同一科目出现多期只保留最后一期——KPI 取「本期」口径，不取累计。
    lei = {'yusuan': {}, 'shishi': {}}
    for fen_lei in ('yusuan', 'shishi'):
        for r in getattr(jilu, fen_lei) or []:
            dan = getattr(r, 'danwei', None) or r.get('danwei')
            kem = getattr(r, 'kemu', None) or r.get('kemu')
            shu = getattr(r, 'shuzhi', None)
            if shu is None:
                shu = r.get('shuzhi')
            if dan == '元' and kem:
                lei[fen_lei][kem] = shu or 0
    # 费用 = 销售费用 + 管理费用（前缀匹配，含二级科目）；预算侧同法。
    # 两侧必须同口径，否则完成率会因分子分母口径错位而系统性偏高或偏低。
    shou_shi = lei['shishi'].get('营业收入')
    fei_shi = sum(v for k, v in lei['shishi'].items()
                  if k.startswith(('销售费用', '管理费用')))
    fei_yu = sum(v for k, v in lei['yusuan'].items()
                 if k.startswith(('销售费用', '管理费用')))
    kuai = {}
    if shou_shi is not None:
        kuai['shouru_shiji_fen'] = int(shou_shi)
        kuai['shouru_yusuan_fen'] = int(lei['yusuan'].get('营业收入') or 0) or None
    if fei_shi:
        kuai['feiyong_shiji_fen'] = int(fei_shi)
    if fei_yu:
        kuai['feiyong_yusuan_fen'] = int(fei_yu)
    # 可控成本：科目名含「成本」或「直接」，且不属于销售/管理费用。
    # 演示轨没有成本科目时这个键根本不会出现 → 引擎按缺数处理，不补 0。
    # 可控成本：科目含"成本"或"直接"类（演示轨无成本科目时保持 None，缺数纪律）
    cheng_shi = sum(v for k, v in lei['shishi'].items()
                    if ('成本' in k or '直接' in k) and not k.startswith(('销售', '管理')))
    cheng_yu = sum(v for k, v in lei['yusuan'].items()
                   if ('成本' in k or '直接' in k) and not k.startswith(('销售', '管理')))
    if cheng_shi:
        kuai['kekong_chengben_shiji_fen'] = int(cheng_shi)
    if cheng_yu:
        kuai['kekong_chengben_yusuan_fen'] = int(cheng_yu)
    # 三表快照（v2 轨）：资产负债表期初期末（thre 值由 import 返回体存 shi 文件里没有——
    # 从文件记录的 three 字段读；缺数 None）
    # 三表快照（v2 轨 three：{表名: {格位: 值}}）——资产负债表只有期末列（B）；
    # 期初取不到（模板单列），如实置 None；期末用「流动资产/负债合计」行。
    # 三表快照（v2 轨 three）：{表名: {单元格: 值}}，由导入层原样登记，值均为 str。
    # 注意：模板是单列版式，资产负债表只有期末列 → 期初取不到（如实 None）。
    san = (shi or {}).get('three') or {}
    import re as _re

    def _he_ji(biao, biaoqian):
        zhi = None
        for g, v in (san.get(biao) or {}).items():
            biao_q = (biaoqian,)
            if v not in (None, '') and str(v).replace(',', '').replace('.', '', 1).isdigit():
                try:
                    fen = int(Decimal(str(v)) * 100)
                except Exception:
                    continue
                zhi = fen  # 快照按格位序，最后命中的合计行即所需
        return zhi
    # 行定位：解析 three 需要行标签；快照只存数值格 → 用 v2 返回的 three 键序不可靠。
    # 简化取数：流动资产合计 = 资产负债表 B19（固定版式），流动负债合计 = B列「流动负债合计」。
    zc = san.get('资产负债表') or {}
    def _fen(ge):
        try:
            v = zc.get(ge)
            return int(Decimal(str(v)) * 100) if v not in (None, '') else None
        except Exception:
            return None
    # 流动资产合计取固定行 B19（模板版式固定，不随主体变化）；
    # 流动负债合计行号因版式而异、快照又无行标签 → 如实 None，
    # 不从资产负债表恒等式反推（反推出来的期初期末是无源之数）。
    kuai['liudong_zichan_qimo_fen'] = _fen('B19')   # 流动资产合计（固定行）
    # 流动负债合计行号因版式而异：扫 B 列找「负债合计」上方最近合计不可行（无标签），
    # 改从资产负债表恒等式反推不可靠 → 如实置 None（缺数纪律）。
    kuai['liudong_zichan_qichu_fen'] = None
    kuai['liudong_fuzhai_qichu_fen'] = None
    kuai['liudong_fuzhai_qimo_fen'] = None
    # 非财务六项（v3k）：率字段（0-100）→ 分子分母（分母 100，保数值等价）；
    # 交付周期/异常数量原值直传
    from decimal import Decimal as _D
    # 非财务六项换算：率字段（0-100 的百分比）→ 分子 = 率×100、分母 = 10000，
    # 数值等价且满足 KpiShuru「只收整数」的要求；计数类（天数/件数）四舍五入取整。
    for ziduan, zhi in ((shi or {}).get('kpi_input') or {}).items():
        if ziduan in _LV_ZHUAN:
            fen_zi, fen_mu = _LV_ZHUAN[ziduan]
            kuai[fen_zi] = int((_D(str(zhi)) * 100).to_integral_value())   # 分子=率×100
            kuai[fen_mu] = 10000
        else:
            kuai[ziduan] = int(_D(str(zhi)).quantize(_D('1'), rounding='ROUND_HALF_UP'))
    # KpiShuru 拒绝非 int/None → Decimal 全部量化为 int 后再交引擎；同时确保无 Decimal 残留
    # 收口：KpiShuru 拒绝非 int/None（Decimal 直接报错），
    # 这里把所有 Decimal 量化成 int，确保交出去的 dict 里没有 Decimal 残留。
    kuai = {k: (int(v) if isinstance(v, _D) else v) for k, v in kuai.items()}
    return kuai


# ---------------------------------------------------------------------------
# 分析编排三段：pao_danzu（单组）→ pao_fenxi（多组汇总）→ dengji_fenxi（登记）
# 分工：pao_danzu 负责「选册 + 合并清洗 + 组载荷 + 调引擎」；
#       pao_fenxi 负责多部门/多情景的取舍与公司级汇总；
#       dengji_fenxi 负责运行号、快照与状态字段。
# 三层合计只调一次引擎（单组一次、多组两次：各组一次 + 公司汇总一次），
# 不做「每换个下拉就重算」这种浪费。
# ---------------------------------------------------------------------------
def pao_danzu(zt, ui_cfg=None):
    """单组内选最新预算/实际册，复用原有全链，返回原始结果与输入载荷。"""
    from data_ingest import daoru_csv               # 权威清洗链（_vendor algo）
    from yinqing import fenxi

    # 选册口径：同类别多册时取**最后导入**的一册（files 按导入序追加），
    # 并把「已导入 N 册、本次用最新」写进 warnings——让用户知道自己算的是哪本。
    def zuixin(leibie):
        mingdan = [f for f in zt['files']
                   if f['category'] == leibie and f['status'] == 'valid']
        return mingdan[-1] if mingdan else None, len(mingdan)

    # 缺册即中止：两册齐备是十五步分析的最小输入条件；
    # 缺一册还硬算，只会得到一张「预算 vs 空」的假差异表。
    yu, yu_shu = zuixin('预算基础')
    shi, shi_shu = zuixin('实时经营')
    if not yu or not shi:
        raise RuntimeError('请先导入「预算基础」与「实时经营」两本工作簿后再分析')
    # 跨主体混算零容忍：两册主体名不同直接中止。这类错误若放过，
    # 出来的差异表完全无意义，比报错更伤人。
    if yu['entity'] != shi['entity']:
        raise RuntimeError(f'两本工作簿主体不一致（{yu["entity"]} / {shi["entity"]}），'
                           '请按主体分批导入，不要跨主体混算')
    tixing = []
    if yu_shu > 1:
        tixing.append(f'预算基础已导入 {yu_shu} 册，本次分析采用最新一册：{yu["name"]}')
    if shi_shu > 1:
        tixing.append(f'实时经营已导入 {shi_shu} 册，本次分析采用最新一册：{shi["name"]}')

    # 合并八字段 CSV（第二册去表头）→ 权威清洗链；拒绝清单非空即中止
    # 合并八字段 CSV：第二册去表头再拼，交给权威清洗链一次解析
    #（daoru_csv 在 _vendor/algo，负责结构校验/期间规范化/金额转分/勾稽）。
    # 桥接层不重复实现任何清洗逻辑——两处实现必然漂移。
    wen = yu['text'] + '\n' + '\n'.join(shi['text'].splitlines()[1:])
    jilu = daoru_csv(wen)
    if getattr(jilu, 'jujue', None):
        # 只回前 3 条拒绝原因：全量几百条会把回包撑爆，也要保证用户看懂第一条错在哪。
        # 拒绝非空说明数据本身违反输入契约，继续算等于用脏数出报告。
        shou = '；'.join(str(j) for j in jilu.jujue[:3])
        raise RuntimeError(f'合并清洗拒绝了 {len(jilu.jujue)} 行，不能继续分析：{shou}')

    # 载荷组装（与 跑衡策全流程.zao_zaihe 同形；配置来自 UI）
    md_yu = yu.get('metadata', {})
    md_shi = shi.get('metadata', {})
    pei = zuhe_peizhi(ui_cfg or zt.get('config'))
    # 期间缺省口径（与 跑衡策全流程.zao_zaihe 完全一致）：
    # 实时经营「已结账截至」优先，其次预算「生效周期」；
    # 月度截前 7 位（YYYY-MM），季度由 UI 直接传 YYYY-Qn。
    if not pei.get('period'):
        # 期间缺省口径与 zao_zaihe 一致：实时经营「已结账截至」→ 预算「生效周期」；
        # 月度取前 7 位（YYYY-MM），季度由 UI 传入（YYYY-Qn）
        zhou = md_shi.get('已结账截至') or md_yu.get('生效周期') or ''
        if pei.get('cycle') == '月度' and len(zhou) > 7:
            zhou = zhou[:7]
        if zhou:
            pei['period'] = zhou
    shi_jian = biangeng_shijian(zt, yu.get('subjects', []), jilu, pei)
    if shi_jian:
        tixing.append(f'经营变更已接入判定链：{len(shi_jian)} 条已批准科目影响')
    # 载荷与 跑衡策全流程.zao_zaihe 同名同义（19 键）：CLI 与插件两条入口
    # 必须能算出逐字节一致的结果，任何一边加字段都要同步另一边。
    zaihe = {
        'company': md_yu.get('主体名称', yu['entity']),
        'metadata': {'主体名称': md_yu.get('主体名称', yu['entity']),
                     '主体编码': md_yu.get('主体编码', 'ENT-001'),
                     '情景名称': md_yu.get('情景名称', '基础情景'),
                     '情景编码': md_yu.get('情景编码', 'S-BASE')},
        'records': jilu,
        'subjects': yu.get('subjects', []),
        'config': pei,
        # KPI 15 项取数：财务 9 项由现有数据推导（收入/费用/资产负债表三表）；
        # 非财务 6 项取「实时经营·非财务指标」表（v3k 十一表；九表/十表无此表=如实缺数）
        # KPI 15 项：财务 9 项由既有数据推导，非财务 6 项读实时经营册的非财务指标表。
        # bsc/traces/baselines 目前不喂（None/空列表），引擎按缺数处理，不假装有。
        'bsc': None, 'kpi': kpi_shuru(jilu, shi), 'traces': [],
        'splits': liangjia_splits(shi, jilu, pei), 'events': shi_jian,
        'baselines': [],
        # 经营变更：UI yes → 有经营变更册则 provided，否则 pending（接入说明口径）
        # 经营变更接入状态：UI 说 yes 且真有有效册 = provided；说 yes 无册 = pending；
        # 说 no = none；未表态 = unknown。引擎据此区分「变更未确认」和「本无变更」。
        'changeStatus': biangeng_yinqing(zt),
    }
    # 已批准修订 → 引擎修订案（kemu/period/amount，金额=分）
    # 已批准修订 → 引擎修订案：只透传 (科目, 期间, 金额=整数分)。
    # 修订对同环比与判定的影响由引擎内部重算，桥接层不加总、不改判定。
    xiuding = [{'kemu': r['subject'], 'period': r['period'], 'amount': r['amount']}
               for r in zt.get('revisions', []) if r.get('approved')]

    # 单组场景的唯一引擎调用点：十五步分析全部在这里完成。
    # 无修订时传 None（而不是 []），与引擎「没有修订」的默认分支对齐。
    jieguo = fenxi(zaihe, xiuding or None)
    if tixing:
        # 桥接层提示追加在引擎 warnings 之后：顺序稳定（引擎在前、桥接在后），
        # 前端按数组序展示；每次分析都是新结果，不会出现重复条目。
        jieguo['warnings'] = list(jieguo.get('warnings') or []) + tixing
    return jieguo, zaihe


# 登记运行：原始结果存进程内存 _RUNS（报告再生成要复用同一份计算），
# 状态里只存摘要 + 快照（快照由调用方随后 baocun_kuaizhao 写入）。
def dengji_fenxi(zt, jieguo, zaihe, ui_cfg):
    """登记一次完整分析，原始公司汇总结果可直接用于原报告流水线。"""
    # 运行号 = run-YYYYmmdd-HHMMSS-序号：同秒内多次分析靠序号区分；
    # 序号取「当前历史条数 + 1」，重启清空历史后也不会与进程内旧号冲突。
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{len(zt['runs']) + 1}"
    _RUNS[run_id] = jieguo
    # 风险计数 = 红 + 黄（引擎系数包给的数量），供历史列表的风险徽标；
    # 不拿 rows 再数一遍——两处口径迟早会算出不同数字。
    yinzi = tanping(jieguo.get('factors'))
    fengxian_shu = (yinzi.get('hong_shu') or 0) + (yinzi.get('huang_shu') or 0)
    zt['runs'].insert(0, {'id': run_id, 'period': zaihe['config']['period'],
                          'createdAt': xianzai(), 'company': zaihe['company'],
                          'status': 'done', 'riskCount': fengxian_shu, '快照': None})
    # dirty 置 False：此刻输入与本次计算一致，允许生成报告与助手问答；
    # 之后任何输入变更（导入/移除/背景/配置）都必须重新置 True。
    zt['currentRunId'] = run_id
    zt['dirty'] = False
    if ui_cfg:
        zt['config'] = json.loads(json.dumps(ui_cfg, ensure_ascii=False))
    return run_id, jieguo


# 多组分析：单组（无部门、title 不含 '/'）直接走 pao_danzu；
# 有部门时逐组分析，再把各部门结果汇总成公司级载荷算一次，
# 最后把各组结果挂到 _departmentGroups 一起下发——下拉切换无需重算。
def pao_fenxi(zt, ui_cfg=None):
    """全组一次分析；部门行与公司汇总同时返回，下拉切换无需重新计算。"""
    from yinqing import fenxi
    fenzu = wenjian_fenzu(zt.get('files', []))
    # 快路径：只有一个公司组时不必汇总，省一次全量引擎计算（约 1-2 秒）。
    if not fenzu or (len(fenzu) == 1 and '/' not in fenzu[0]['title']):
        jieguo, zaihe = pao_danzu(zt, ui_cfg)
        return dengji_fenxi(zt, jieguo, zaihe, ui_cfg)

    # 逐组独立分析：一组失败不拖垮其他组（失败组进 warnings），
    # 只有一组都不成功时才抛错——用户至少能看到能算的那几组。
    chenggong, tixing = [], []
    for zu in fenzu:
        leibie = {f['category'] for f in zu['files']}
        # 缺册的组直接跳过并记提示：多部门场景常见「某部门只报费用不报收入」，
        # 这类组算不出完整判定，跳过比强行算出一个半成品更有意义。
        queshi = [lei for lei in ('预算基础', '实时经营') if lei not in leibie]
        if queshi:
            tixing.append(f'{zu["title"]}（{zu["scenarioName"]}）缺少「{"、".join(queshi)}」，本次跳过该组')
            continue
        # 部门组用临时状态跑：文件只留本组、修订只留本部门；
        # 其余（config/background）继承公司级设置，保证各组口径一致。
        linshi = {**zt, 'files': zu['files'], 'revisions': [
            r for r in zt.get('revisions', []) if r.get('departmentId') == zu['id']]}
        # 部门分组继承公司级经营变更册：判定链的事件登记是全公司口径，
        # 不随部门拆分而消失（否则部门视图永远是"变更未确认"）。
        # 部门组继承公司级经营变更册：变更登记本来就是全公司口径，
        # 不随拆册而消失，否则部门视图永远是「变更未确认」。
        gong = zu['title'].split('/', 1)[0]
        # 只继承**同一公司**的变更册（title 前缀相同）：跨公司混用变更册，
        # 等于把别家的审批事件算进本部门，是口径事故。
        linshi['_biangeng'] = [f for f in zt.get('files', [])
                               if f.get('category') == '经营变更'
                               and f.get('entity') == gong]
        try:
            jieguo, zaihe = pao_danzu(linshi, ui_cfg)
        except Exception as e:
            # 组内异常一律包成「哪个组失败 + 原始中文原因」：
            # 不包装直接冒上去，用户只会看到一句「缺册」，不知道是哪一组缺。
            raise RuntimeError(f'{zu["title"]}（{zu["scenarioName"]}）分析失败：{e}') from e
        chenggong.append({**zu, 'result': jieguo, 'input': zaihe})
    if not chenggong:
        raise RuntimeError('没有预算基础与实时经营齐备的分组：' + '；'.join(tixing))

    # 不叠加互斥情景；基础情景优先，其余情景仍完整保留在部门选择中。
    # 情景取舍：基础情景 S-BASE 优先，没有就取第一个成功组的情景。
    # 不同情景**不叠加**汇总——那是把互斥假设相加，得到的总数没有业务含义。
    qingjing = next((z['scenario'] for z in chenggong if z['scenario'] == 'S-BASE'),
                    chenggong[0]['scenario'])
    tongjing = [z for z in chenggong if z['scenario'] == qingjing]
    # 口径：收入留在公司级、部门只承载成本费用（费用中心）。公司总册存在时，
    # 「全部部门」直接取公司总册（它已含收入与全部成本费用），部门册只是分视图，
    # 不再按部门相加（否则收入会归零、成本会重复）。
    # 汇总口径（关键决策，别改）：公司总册存在时，「全部部门」直接取公司总册，
    # 部门册只作为分视图；不按部门相加——否则收入会归零、成本会重复计算。
    # 只有在完全没有公司总册时，才用本情景下所有组做加总。
    gongsi_zu = [z for z in tongjing if '/' not in z['title']]
    huizong = gongsi_zu[:1] if gongsi_zu else tongjing
    if len({z['scenario'] for z in chenggong}) > 1:
        tixing.append(f'全部部门按「{tongjing[0]["scenarioName"]}」汇总；其他情景请在部门选择中单独查看')
    if gongsi_zu and len(tongjing) > 1:
        tixing.append('全部部门取公司总册口径：收入仅公司级，部门按费用中心展示')
    # 汇总一致性闸：所有参与汇总的组，期间/周期必须完全相同。
    # 否则「公司汇总」是拿不同期间的数据相加——这种口径错误绝不能放过。
    peizhi = huizong[0]['input']['config']
    if any(z['input']['config'] != peizhi for z in huizong[1:]):
        raise RuntimeError('各部门分析期间或周期不一致，请在分析设置中统一期间后重试')

    # 部门加总容器：预算/实际两条轨分别按 (科目, 期间) 累加，金额=整数分。
    jilu = {'yusuan': [], 'shishi': [], 'hangye': [], 'biangeng': [], 'jujue': []}
    # 科目配置必须逐字段一致（同名科目在各部门的模块/方向/口径不能不同），
    # 不一致就报错点名科目——静默取其一会让汇总失去可解释性。
    kemu = {}
    for zu in huizong:
        for s in zu['input']['subjects']:
            if s['kemu'] in kemu and kemu[s['kemu']] != s:
                raise RuntimeError(f'{s["kemu"]} 在各部门的科目配置不一致，请核对后汇总')
            kemu[s['kemu']] = s
    for lei in ('yusuan', 'shishi'):
        leiji = {}
        for zu in huizong:
            # 只有单位=元的记录可加（danwei='元' 表示金额、已转分）：
            # 比率、天数、件数不是可加量，相加只会得到无意义的数字，
            # 这些指标在部门视图里单独看。
            for r in tanping(zu['input']['records'])[lei]:
                if r['danwei'] != '元':
                    continue  # 比率和计数指标不按金额相加
                jian = (r['kemu'], r['qijian'])
                if jian not in leiji:
                    leiji[jian] = {**r, 'shuzhi': 0, 'laiyuan': '部门工作簿汇总'}
                leiji[jian]['shuzhi'] += r['shuzhi']
        jilu[lei] = list(leiji.values())
    # 公司名去重：取所有组「公司/部门」前缀的唯一值。
    # 只有一个才是具名主体；多个一律写「多主体汇总」，不臆造一个公司名。
    gongsi = list(dict.fromkeys(z['title'].split('/', 1)[0] for z in huizong))
    # 公司级载荷 = 首个汇总组的配置骨架 + 加总后的记录与科目表；
    # 其余键（kpi/events/splits/changeStatus）沿用该组，保证与单组分析同形。
    zaihe = {**huizong[0]['input'], 'records': jilu, 'subjects': list(kemu.values()),
             'company': gongsi[0] if len(gongsi) == 1 else '多主体汇总'}
    zaihe['metadata'] = {**zaihe['metadata'], '主体名称': zaihe['company']}
    # 修订计入公司汇总：公司级（all）修订原样透传；部门级修订按
    # Σ(该组最新修订值，未修订组取原预算值) 折算成等价公司级修订，
    # 已有公司级修订的科目+期间不重复折算（公司意图优先）。
    # 修订折算（公司口径）：公司级（departmentId='all'）修订原样透传；
    # 部门级修订按 Σ(该组修订值，未修订组取原预算值) 折成等价公司级修订；
    # 已被公司级修订占住的 (科目,期间) 不再折算——公司意图优先。
    shenpi = [r for r in zt.get('revisions', []) if r.get('approved')]
    xiuding, zhanwei = [], set()
    for r in shenpi:
        if r.get('departmentId', 'all') == 'all':
            xiuding.append({'kemu': r['subject'], 'period': r['period'],
                            'amount': r['amount']})
            zhanwei.add((r['subject'], r['period']))
    zu_ids = {z['id'] for z in huizong}
    # 两张索引：部门修订 {(科目,期间): {组id: 金额}}；
    # 组原预算 {(科目,期间): {组id: 金额}}——用来补「没提修订的那几个部门」。
    bu_xiu, zu_yuan = {}, {}
    for r in shenpi:
        if r.get('departmentId') in zu_ids:
            bu_xiu.setdefault((r['subject'], r['period']), {})[r['departmentId']] = \
                r['amount']
    for zu in huizong:
        for r in tanping(zu['input']['records'])['yusuan']:
            if r.get('danwei') == '元':
                zu_yuan.setdefault((r['kemu'], r['qijian']), {})[zu['id']] = r['shuzhi']
    # 折算公式：等价公司级修订 = Σ(组修订值 ?? 组原预算值)。
    # sorted 只为输出顺序稳定，保证同输入同输出（幂等，便于逐字节比对）。
    for jian, gai in sorted(bu_xiu.items()):
        if jian in zhanwei:
            continue
        he = sum(gai.get(z['id'], zu_yuan.get(jian, {}).get(z['id'], 0))
                 for z in huizong)
        if he:
            xiuding.append({'kemu': jian[0], 'period': jian[1], 'amount': he})
    # 多组场景的唯一引擎调用点：用公司级加总载荷 + 折算后的修订再算一次。
    # 各部门的差异表在 pao_danzu 里已各自算好，此处只算公司汇总，不重复算部门。
    jieguo = fenxi(zaihe, xiuding or None)
    # 私有键（下划线开头）只在本进程内传递，不直接进 UI 回包：
    # _entities 给部门下拉，_departmentGroups 给部门视图，都由 guiyi() 消费。
    jieguo['_entities'] = bumen_xuanxiang(fenzu)
    # 公司总册已由「全部部门」承载，不再作为独立部门行重复输出
    # 有部门册时，公司总册已由「全部部门」承载，不再作为独立部门行重复输出，
    # 否则下拉里会出现「公司」「全部部门」两个口径完全相同的选项。
    you_bumen = any('/' in z['title'] for z in chenggong)
    jieguo['_departmentGroups'] = [
        {'id': z['id'], 'name': z['name'], 'result': z['result']}
        for z in chenggong if not (you_bumen and '/' not in z['title'])]
    for zu in chenggong:
        for t in zu['result'].get('warnings') or []:
            if t not in (jieguo.get('warnings') or []):
                # 部门级 warnings 加部门名前缀后并入公司汇总：不加前缀就分不清是哪一组的问题。
                tixing.append(f'{zu["name"]}：{t}')
    # 公司级结果收尾：引擎 warnings 在前、桥接提示（含各部门提示）在后。
    jieguo['warnings'] = list(jieguo.get('warnings') or []) + tixing
    return dengji_fenxi(zt, jieguo, zaihe, ui_cfg)


# 经营变更候选册：部门分组时由 pao_fenxi 注入 _biangeng（全公司口径），
# 否则从状态文件里筛——保证部门视图不会因为拆册而「看不见」公司级变更。
def _biangeng_lie(zt):
    """经营变更候选册：部门分组继承公司级变更册（在 pao_fenxi 注入 _biangeng）。"""
    return zt.get('_biangeng') or [f for f in zt.get('files', [])
                                   if f.get('category') == '经营变更']


# 变更状态翻译：UI 的 yes 要看到真册子才落成 provided，没册子就是 pending
#（用户说有、但没导入）——不许把 pending 说成 provided，那是谎报口径。
def biangeng_yinqing(zt):
    """UI 变更状态（yes/none/unknown）→ 引擎口径（provided/pending/none/unknown）。"""
    yuan = (zt.get('background') or {}).get('changeStatus', 'unknown')
    if yuan == 'yes':
        you = any(f['category'] == '经营变更' and f['status'] == 'valid'
                  for f in _biangeng_lie(zt))
        return 'provided' if you else 'pending'
    return yuan if yuan in ('none', 'unknown') else 'unknown'


# 快照写回：归一化结果整体深拷贝进当前运行条目。
# 历史回放（history.open）与重启后恢复都靠它；不写快照 = 历史列表点了只能报错。
def baocun_kuaizhao(zt, kuai):
    """把归一化结果写进当前运行条目（历史回放的依据）。"""
    run = dangqian_run(zt)
    if run is not None:
        run['快照'] = json.loads(json.dumps(kuai, ensure_ascii=False))


# ======================================================================
# 报告：生成（md+html+PDF）与页数
# ======================================================================

# ---------------------------------------------------------------------------
# 报告产物工具：PDF 打印与页数统计
# PDF 走本机浏览器 headless 打印（不引 wkhtmltopdf / weasyprint，零新增依赖）；
# 打印失败不算致命错误：md/html/json 仍可用，状态里 pdfPath=None 如实反映。
# ---------------------------------------------------------------------------
def zhuan_pdf(html_lu, pdf_lu):
    """html → PDF：本机 Chrome/Edge headless 打印（与 跑衡策全流程 同法）。"""
    # 入参兼容 str（状态里存的就是字符串路径）与 Path，统一成 Path 再用。
    html_lu, pdf_lu = Path(html_lu), Path(pdf_lu)   # 入参兼容 str
    # 依次试浏览器：第一个能生成 >2000 字节 PDF 的就返回成功，后面的不再试。
    # 全都不行就返回 False，由调用方决定「无 PDF 也照常登记报告」。
    for exe in LIULANQI:
        if not Path(exe).exists():
            continue
        subprocess.run([exe, '--headless=new', '--disable-gpu', '--no-sandbox',
                        # --no-pdf-header-footer：去掉浏览器默认页眉页脚（URL / 日期），
                        # 报告的页眉页脚由 baogao_liuxian 的 HTML 自己给，双份会很难看。
                        # timeout=300：打印是同步阻塞的，超时就放弃 PDF，不能让整个请求卡死。
                        '--no-pdf-header-footer', f'--print-to-pdf={pdf_lu}',
                        Path(html_lu).as_uri()],
                       capture_output=True, timeout=300)
        # 2000 字节判据：打印失败时浏览器仍会留下一个近乎空的 PDF（只有文件头），
        # 用它区分「真生成」和「假成功」，避免页数统计读到 0 页文件。
        if pdf_lu.exists() and pdf_lu.stat().st_size > 2000:
            return True
    return False


# 页数统计：正则数 /Type /Page 对象数（排除 /Pages），不引 PyPDF2 之类的重依赖。
# 读文件失败返回 None——UI 显示「—」，而不是骗人的 0。
def shu_yeshu(pdf_lu):
    """PDF 页数：统计 /Type /Page 对象（轻量正则，不引第三方）。"""
    try:
        # 正则口径：/Type /Page 后面不能紧跟 s（排除 /Pages 目录对象）；
        # 至少返回 1——退化的目录结构也算 1 页，避免 UI 出现「0 页」。
        return max(1, len(re.findall(rb'/Type\s*/Page[^s]', pdf_lu.read_bytes())))
    except OSError:
        return None


# ======================================================================
# action 分发（13 个，与 接入说明 §3 的表逐行对齐）
# ======================================================================

# ---------------------------------------------------------------------------
# action 分发表（13 个，与 docs/接入说明.md §3 的表逐行对齐）
# 契约：处理函数签名统一 (zt, payload) -> dict / list
#   zt      可变的工作区状态（每个请求共享同一份，改它就是改状态）
#   payload 请求体，可能为 None —— 函数内一律 (payload or {}) 兜底
#   返回    由 main() 摊平后回包 {'id','ok':true,'data':...}
#   报错    raise RuntimeError(中文)；main() 回 ok:false 并把中文原样带给用户
# 纪律：不改 action 名、不改既有入参语义、返回结构只增不改（UI 依赖既有字段）。
# ---------------------------------------------------------------------------
DONGZUO = {}                                        # action 名 → 处理函数


# 注册装饰器：@dongzuo('名字') 把处理函数收进 DONGZUO。
# 用注册表而不是 if/elif 链，是为了让 action 清单可枚举——测试、文档、
# 前端调用表能直接对齐；新增 action 只需多写一个函数。
def dongzuo(ming):
    """注册装饰器：收集 action 处理函数。"""
    def bao(f):
        DONGZUO[ming] = f
        return f
    return bao


# 入参：payload 忽略（UI 会带 entityId 之类，服务端不依赖它）。
# 出参：完整 normalized workspace（字段语义见 guiyi 的注释）。
# 错误：不报错——没有运行就回空态骨架。UI 启动即调这个 action，
#       它一旦失败整个界面就打不开，所以任何情况都必须给可用结果。
@dongzuo('workspace.load')
def _(zt, payload):
    """读取当前工作区（UI 启动即调；无运行时给空态骨架）。"""
    return fang_kuaizhao(zt)


# 入参：{files:[{name, bytesB64 | bytes:{bytesB64}}], mode:'append'|'replace',
#        category?(替换模式下要替换的类别)}
# 出参：导入后的 workspace（新文件清单 + 空 rows）。
# 错误：非 .xlsx / 空字节 / 契约校验不过 → 中文报错原样给用户（不包装引擎文案）。
# 批处理语义：先全部校验成功，再整体替换状态——后一本失败不会留下半批状态。
@dongzuo('files.import')
def _(zt, payload):
    """导入工作簿：逐文件走三轨道校验；类别以解析结果为准（不信任文件名）。"""
    from excel_ingest_v11 import import_excel_v11
    # 空清单直接报错，而不是回「成功导入 0 个」：
    # UI 传空说明前端把文件丢了，静默成功会让用户以为文件已经进去了。
    wenjian = (payload or {}).get('files') or []
    if not wenjian:
        raise RuntimeError('没有收到文件')
    # 批量导入先全部校验，成功后再替换，避免后一本失败留下半批状态。
    # 在副本上操作：整批校验成功后才写回 zt['files']；
    # 中途任何一本抛错，状态保持原样（all-or-nothing，不留半批）。
    daoru_hou = list(zt['files'])
    # 替换模式：先剔除同类别旧册（含其八字段文本），再导入新册。
    # 只替换指定类别——不传 category 就不替换，避免误清其他三类。
    if (payload.get('mode') or 'append') == 'replace' and payload.get('category'):
        # 替换模式：先清同类旧册（含其八字段文本）
        daoru_hou = [f for f in daoru_hou if f['category'] != payload['category']]
    for w in wenjian:
        ming = w.get('name', '')
        # 扩展名闸：只收 .xlsx（四类模板都是 xlsx）。旧 .xls / .csv 一律拒绝，
        # 不做「尽力兼容」——格式不符就是不符合输入契约，硬兼容只会读出脏数。
        if not ming.lower().endswith('.xlsx'):
            raise RuntimeError(f'{ming}：只接受 .xlsx 工作簿')
        # 字节两形状兼容：顶层 bytesB64（桥已打平）或 bytes:{bytesB64}（旧形状）
        # 字节有两种形状：顶层 bytesB64（MJS 桥打平后的形状）与 bytes:{bytesB64}
        #（旧形状 / 直连调用）。两者都兼容；空字节不在这里造错，交给契约层如实报。
        b64 = w.get('bytesB64') or ''
        if not b64 and isinstance(w.get('bytes'), dict):
            b64 = w['bytes'].get('bytesB64') or ''
        zjie = base64.b64decode(b64)                  # 空字节会在契约层如实报错
        # 统一读取入口（v11）：按内容识别类别（**不信任文件名**），逐表校验固定版式、
        # 固定科目与公式骨架，返回 metadata/subjects/text/kpi_input/three/departments。
        # 校验失败抛 ExcelError，中文文案由 main() 原样转给用户，桥接层不改写。
        jie = import_excel_v11(zjie, ming)                    # 抛 ExcelError（中文文案）
        md = jie.get('metadata', {})
        # 状态里的文件记录：既含展示字段（name/size/entity/importedAt），
        # 也含分析所需的 text（八字段 CSV 原文）与 subjects（科目配置）——
        # 后两者只在分析时用，绝不进 UI 回包（wenjian_zhaiyao 是白名单）。
        xin_wenjian = {
            # id 规则：f{序号3位}-{时间戳后5位}。序号保证可读，时间戳后缀保证同一批里
            # 重复导入同名册也不会撞 id（撞 id 会让 files.remove 删错册）。
            'id': f'f{len(daoru_hou) + 1:03d}-{int(datetime.now().timestamp()) % 100000}',
            'name': ming, 'category': jie['category'], 'status': 'valid',
            'checks': jie.get('checks'), 'rows': jie.get('ruku_shu'),
            'size': renlei(len(zjie)), 'entity': md.get('主体名称', ''),
            'groupKey': jie.get('groupKey', ''), 'text': jie.get('text', ''),
            'subjects': jie.get('subjects', []), 'metadata': md,
            # v3k：非财务指标六项随册登记（分析时 KpiShuru 取数）；
            # three 快照同步登记（资产负债表取数用）——数值统一 str，防 Decimal 进 JSON 落盘
            'kpi_input': jie.get('kpi_input'),
            'liangjia': jie.get('liangjia'),
            'events': jie.get('events') or [],
            # three 快照的数值统一转 str：从 xlsx 读出的是 Decimal，直接进状态 JSON 会
            # 序列化失败；转字符串后落盘稳定，取数时再 Decimal 还原（金额仍按整数分换算）。
            'three': {biao: {ge: (str(zhi) if zhi not in (None, '') else zhi)
                             for ge, zhi in (kuai or {}).items()}
                      for biao, kuai in (jie.get('three') or {}).items()},
            'importedAt': xianzai(),
        }
        # v3 表内部门：一册展开成 公司分册 + 各部门虚拟分册（读取器已逐分勾稽，
        # Σ部门 ≡ 公司）。部门编码推导与 生成器 --bumen 模式严格一致（同公司同
        # 部门跨模式落同一分组）；下游分组分析/实体下拉全部复用分组机制。
        # v3 表内部门展开：一册 → 公司分册 + 各部门虚拟分册。
        # 读取器已逐分勾稽（Σ部门 ≡ 公司），桥接层只负责登记成独立「文件」；
        # 下游的分组/实体下拉/部门分析全部复用既有分组机制，不需要任何特判。
        pi_liang = [xin_wenjian]
        gong_si = md.get('主体名称', '')
        for bu_ming, bu_xi in (jie.get('departments') or {}).items():
            quan_ming = f'{gong_si}/{bu_ming}'
            # 部门主体编码 = ENT-{年度}-D{哈希前12位}，哈希取「公司/部门」全名，
            # 与演示生成器 --bumen 模式同一规则：同公司同部门跨模式落到同一分组。
            ma = hashlib.sha256(quan_ming.encode('utf-8')).hexdigest()[:12].upper()
            bu_md = dict(md)
            bu_md.update({'主体名称': quan_ming,
                          '主体编码': f'ENT-{md.get("年度", "")}-D{ma}'})
            # 部门分册的八字段文本由读取器按部门切分好，这里原样存下供分析合并；
            # 行数按文本行数（去表头）估算，只用于列表展示，不参与计算。
            bu_text = bu_xi.get('text', '')
            pi_liang.append({
                'id': f'f{len(daoru_hou) + len(pi_liang) + 1:03d}-'
                      f'{int(datetime.now().timestamp() * 1000) % 100000000}',
                'name': f'{ming}（{bu_ming}）', 'category': jie['category'],
                'status': 'valid', 'checks': jie.get('checks'),
                'rows': max(len(bu_text.splitlines()) - 1, 0),
                'size': xin_wenjian['size'], 'entity': quan_ming,
                'groupKey': json.dumps([bu_md['主体编码'], md.get('情景编码', 'S-BASE'),
                                        md.get('年度', ''), md.get('期间粒度', '月度')],
                                       ensure_ascii=False),
                'text': bu_text, 'subjects': jie.get('subjects', []),
                'metadata': bu_md, 'importedAt': xianzai(),
            })
        # 逐条换册：先校验分组一致性再写——同分组改名不能悄悄覆盖旧册
        #（wenjian_fenzu 遇冲突会抛错），不同情景（groupKey 不同）互不替换。
        for tiao_mu in pi_liang:
            # 先验一致性再换册：同分组改名不能悄悄覆盖旧册，多情景互不替换。
            wenjian_fenzu(daoru_hou + [tiao_mu])
            xin_jian = tuple(json.loads(tiao_mu.get('groupKey') or '[]'))
            daoru_hou = [f for f in daoru_hou
                         if not (f['category'] == tiao_mu['category']
                                 and tuple(json.loads(f.get('groupKey') or '[]')) == xin_jian)]
            # id 撞车兜底：追加毫秒时间戳后缀。宁可 id 难看，也不能重复——
            # id 是 UI 的唯一键，重复会让移除操作删错册。
            if any(f['id'] == tiao_mu['id'] for f in daoru_hou):
                tiao_mu['id'] += '-' + datetime.now().strftime('%f')
            daoru_hou.append(tiao_mu)
    # 提交：整批写回状态并置 dirty。
    # dirty=True 意味着「输入相对上次分析已变更」，此时生成报告会被拒并提示重跑。
    zt['files'] = daoru_hou
    zt['dirty'] = True
    return fang_kuaizhao(zt)


# 入参：无。出参：空态 workspace。
# 副作用：清空 files、置 dirty、解除 currentRunId 绑定；
#        runs 历史保留（可回看，但不再参与任何新分析）。
# 错误：不报错（清空是幂等操作）。
@dongzuo('files.clear')
def _(zt, payload):
    """清空全部已导入工作簿（UI 二次确认后调用）。

    与逐个 files.remove 同语义：输入清空后当前运行解除绑定、工作区回到
    空态（部门列表随之消失）；历史运行记录保留，可回看不再参与新分析。"""
    zt['files'] = []
    zt['dirty'] = True
    zt['currentRunId'] = None
    return fang_kuaizhao(zt)


# 入参：{id}。出参：workspace。
# 错误：id 不存在时不报错——删除按幂等语义处理（UI 可能重复点/连点）。
# 细节：全部册移除后解除当前运行绑定，避免旧快照冒充新输入的结果。
@dongzuo('files.remove')
def _(zt, payload):
    """移除一册导入（按 id）；移除后输入不再参与分析。
    全部移除时解除当前运行绑定——旧快照不再代表任何输入，下一次
    导入立即按新文件呈现部门列表与空态（历史运行记录仍完整保留）。"""
    rid = (payload or {}).get('id')
    zt['files'] = [f for f in zt['files'] if f['id'] != rid]
    zt['dirty'] = True
    if not zt['files']:
        zt['currentRunId'] = None
    return fang_kuaizhao(zt)


# 入参：{category} ∈ 预算基础 / 实时经营 / 行业对标 / 经营变更。
# 出参：{name, mime(xlsx), bytesB64}——安装包内模板原样下发，空白可填。
# 错误：模板文件缺失 → 中文报错，明确说是「文件缺失」，
#       不让用户怀疑是自己点错了按钮。
@dongzuo('templates.download')
def _(zt, payload):
    """四类官方空白模板（1.0.5 交付件原样下发，黑白空白可填）。"""
    # 类别直接拼文件名（{类别}输入模板.xlsx）：四份模板命名固定，
    # 不做模糊匹配——拼不上就是没有，报错比猜一个近似文件名安全。
    lei = (payload or {}).get('category', '')
    lu = MOBAN_MU / f'{lei}输入模板.xlsx'
    if not lu.exists():
        raise RuntimeError(f'{lei}模板尚未随插件提供（文件缺失：{lu.name}）')
    return {'name': lu.name,
            'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'bytesB64': base64.b64encode(lu.read_bytes()).decode('ascii')}


# 入参：{config?}（UI 配置形状，见 zuhe_peizhi）。
# 出参：workspace（rows/trend/actions/kpis/blocks/splits/warnings 全齐）。
# 错误：缺册 / 跨主体 / 清洗拒绝 / 配置类型错 → 中文报错，不动已有状态。
# 副作用：登记运行号 + 写快照（历史回放的依据）+ dirty 置 False。
@dongzuo('analysis.run')
def _(zt, payload):
    """十五步分析（配置来自 UI；未带配置时用默认档位，杜绝空档位拒绝）。"""
    # 配置优先级：本次请求带的 config → 状态里的 config → moren_config()。
    # 最后一道兜底是刻意的：老 UI 不带配置时也不能让分析失败（默认档位可用）。
    _, jieguo = pao_fenxi(zt, (payload or {}).get('config') or moren_config())
    kuai = guiyi(jieguo, zt)
    baocun_kuaizhao(zt, kuai)
    return kuai


# 入参：{changeStatus:'yes'|'none'|'unknown', text:经营背景文本}。
# 出参：workspace。错误：不报错。
# 细节：值未变化时不置 dirty——避免「打开设置页随手点保存」就把已有报告锁住。
@dongzuo('background.save')
def _(zt, payload):
    """保存经营背景与变更状态（值未变化时不置脏——避免无感保存锁报告）。"""
    b = payload or {}
    # 只保留这两个字段并做等值比较：多余的键（如前端的时间戳）会让"未变化"
    # 永远判成变化，从而把报告无谓地锁掉。
    xin = {'changeStatus': b.get('changeStatus', 'unknown'),
           'text': b.get('text', '')}
    if xin != (zt.get('background') or {}):
        zt['background'] = xin
        zt['dirty'] = True
    return fang_kuaizhao(zt)


# 入参：{id: actionId, status:'pending'|'doing'|'done'}。出参：workspace。
# 错误：未分析先改（无 currentRunId）/ 未知状态值 → 中文报错。
# 细节：人工状态存 actionStatus（actionId → 状态），不写进引擎结果，
#       所以重算分析后人工处理进度仍然保留（这是用户可见的承诺）。
@dongzuo('actions.update')
def _(zt, payload):
    """整改状态人工变更（pending/doing/done；计数回算由归一化层完成）。"""
    if not zt.get('currentRunId'):
        raise RuntimeError('请先运行分析，再处理整改事项')
    aid, xin = (payload or {}).get('id'), (payload or {}).get('status')
    # 白名单校验：状态只允许这三值。放行任意字符串会让 UI 的三态按钮
    # 渲染出一个没有对应样式的状态。
    if xin not in ('pending', 'doing', 'done'):
        raise RuntimeError(f'未知的整改状态：{xin}')
    zt['actionStatus'][aid] = xin
    kuai = fang_kuaizhao(zt)
    baocun_kuaizhao(zt, kuai)
    return kuai


# 入参：{approved:true, reason, amount(整数分), rowId, period}。
# 出参：重算后的 workspace（修订**立即生效**，不是"标记待生效"）。
# 错误口径（逐条校验，顺序不可颠倒，全部中文）：
#   ① 未勾选人工确认 ② 原因为空 ③ 金额非「非负整数（分）」
#   ④ 未先运行分析 ⑤ 找不到差异行 ⑥ 期间已届满（≤ 当前分析期间）
# 口径要点：金额一律整数分；已结账期间锁止（届满期的预算/实际不可修订）。
@dongzuo('revisions.approve')
def _(zt, payload):
    """批准未来期间预算修订并真重算（届满期拒绝；金额整数分）。"""
    b = payload or {}
    if not b.get('approved'):
        raise RuntimeError('修订须勾选人工确认后才能批准')
    if not (b.get('reason') or '').strip():
        raise RuntimeError('修订原因不能为空')
    fen = b.get('amount')
    # 布尔是 int 的子类，必须单独排除（True 会被当成 1 分）；
    # 不接受 float：1.5 元这种"看起来像分"的值是真金额错误的高发点。
    if not isinstance(fen, int) or isinstance(fen, bool) or fen < 0:
        raise RuntimeError('修订金额必须是非负整数（分）')
    if not zt.get('currentRunId'):
        raise RuntimeError('请先运行分析，再提请预算修订')
    # 用归一化结果做校验依据：rowId 与 period 都取自 UI 当前看到的视图，
    # 拿状态里的原始数据校验会和用户眼前的行对不上（尤其是回放历史时）。
    cankao = fang_kuaizhao(zt)                       # 当前行/配置（快照或归一化）
    row = next((r for r in cankao['rows'] if r['id'] == b.get('rowId')), None)
    if row is None:
        raise RuntimeError(f'找不到对应差异行：{b.get("rowId")}')
    # 期间比较用字符串字典序：'YYYY-MM' 的字典序与时间序一致，无需解析日期。
    # ≤ 当前分析期间 = 已届满（含当月）→ 已结账期间锁止，拒绝修订。
    if (b.get('period') or '') <= (cankao['config'] or {}).get('period', ''):
        raise RuntimeError(f'期间 {b.get("period")} 已届满，预算与实际不可修订')
    zt['revisions'].append({'id': f'rv{len(zt["revisions"]) + 1:03d}',
                            'rowId': b['rowId'], 'period': b['period'],
                            'amount': fen, 'reason': b['reason'].strip(),
                            'approved': True, 'subject': row['subject'],
                            'createdAt': xianzai()})
    # 有多个部门时把修订记到该行所属部门（departmentId），
    # 汇总时才能折算成等价公司级修订；单部门时不记部门键，保持旧数据形状。
    if len(cankao['entities']) > 1:
        zt['revisions'][-1]['departmentId'] = row.get('departmentId', 'all')
    # 修订后**真重算**（不是打补丁改数字）：新预算会影响同环比、预警档位、
    # 单双环判定与整改清单，只有重跑引擎才能保证所有派生结论自洽。
    _, jieguo = pao_fenxi(zt, zt.get('config'))     # 修订后真重算
    kuai = guiyi(jieguo, zt)
    baocun_kuaizhao(zt, kuai)
    return kuai


# 入参：无（UI 已二次确认）。出参：{ok:True, root:安装根目录}。
# 机制：写一个分离进程的 cmd 引导脚本——先等 3 秒让本次回包送达界面，
#       再 taskkill 应用、拉起 unins000.exe，最后自删。
# 这样绕开「直接双击 unins000.exe 时 Electron 文件被占用导致卸载失败」的老问题。
# 错误：找不到安装根目录 / 没有 unins000.exe（绿色包）→ 中文报错 + 替代做法。
@dongzuo('app.uninstall')
def _(zt, payload):
    """软件内卸载（帮助页入口，UI 已二次确认）：先退出应用再启动卸载向导。

    背景：直接双击 unins000.exe 时应用往往在运行，Electron 文件被锁导致
    卸载中途失败。做法：分离进程的引导脚本等 3 秒（让本次请求的响应先
    回到界面）→ 强制退出 DeepSeek Harness.exe → 拉起 unins000.exe 向导。
    引导脚本放安装目录 数据\\ 下（零 C 盘），自删除收尾。"""
    # 反查安装根目录：向上找含「应用/DeepSeek Harness.exe」的目录。
    # 用文件存在性判断而不写死盘符（用户可能装在任意盘），
    # 但也绝不回落到某个默认路径——找不到就报错，不猜。
    gen = None
    for lu in Path(__file__).resolve().parents:
        if (lu / '应用' / 'DeepSeek Harness.exe').exists():
            gen = lu
            break
    if gen is None:
        raise RuntimeError('未找到安装根目录，请运行安装目录内的卸载程序')
    xie = gen / 'unins000.exe'
    if not xie.exists():
        raise RuntimeError('本安装没有卸载向导（unins000.exe）；绿色包请运行目录内 卸载.bat')
    # 引导脚本落在安装目录的 数据\ 下（零 C 盘）：位于应用目录之外、
    # 不被 Electron 占用的位置；脚本最后 del 自己，不留残留文件。
    zhu = gen / '数据' / '卸载引导.tmp.cmd'
    zhu.write_text(
        '@echo off\r\n'
        'ping -n 4 127.0.0.1 >nul\r\n'
        'taskkill /IM "DeepSeek Harness.exe" /F >nul 2>&1\r\n'
        'ping -n 2 127.0.0.1 >nul\r\n'
        'start "" "' + str(xie) + '"\r\n'
        'del /q "%~f0" >nul 2>&1\r\n',
        encoding='gbk')
    # 0x00000008 = DETACHED_PROCESS，0x00000200 = CREATE_NEW_PROCESS_GROUP。
    # 分离进程的意义是「父进程被 taskkill 之后子进程仍活着」，
    # 否则卸载向导会跟着应用一起被杀，卸载永远走不完。
    subprocess.Popen(['cmd', '/c', str(zhu)],
                     creationflags=0x00000008 | 0x00000200,   # 分离进程：应用退出后仍存活
                     close_fds=True)
    return {'ok': True, 'root': str(gen)}


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

#: AI 生成内容统一标注文案（改造规范第三节：**一字不改**）。
#: 落点四处：整改建议回填（md 引用块）、状态里报告条目的 aiNotice、
#: assistant.ask 返回体的 aiNotice 与回答文本末尾。
#: 与报告组装模块的 AI_BIAOZHU 同值，但这里独立定义——两个模块各自可单测，
#: 不互相 import（桥接层是服务端入口，不该被渲染层反向依赖）。
AI_BIAOZHU = '内容为AI生成，仅供参考'


# 密钥读取的唯一入口（全模块只在这里取明文，别处一律拿它的返回值）。
# 两级来源，顺序不可颠倒：环境变量是运维显式注入、优先级最高；
# 凭据文件是 dsh 官方机制（本应用给用户填密钥的落点）。
# 只读不写——写入走 hosting.apiKey，两者职责分开：读路径不能有副作用。
def _du_miyao():
    """密钥两级：环境变量 DEEPSEEK_API_KEY → 凭据文件 refs 节（只读）。"""
    # 环境变量优先且要求非空（strip 后）：容器/CI 里用 env 注入密钥是标准做法，
    # 也让用户可以在不改凭据文件的情况下临时换 key。
    huan = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    if huan:
        return huan
    # 凭据文件定位 <DSH_HOME>/.credentials.yaml。DSH_HOME 未设时直接返回 None，
    # 绝不回落到 C 盘默认家目录（零 C 盘纪律，也避免读到别人机器上的密钥）。
    jia = os.environ.get('DSH_HOME')
    if jia:
        wen = Path(jia) / '.credentials.yaml'
        if wen.exists():
            for hang in wen.read_text(encoding='utf-8').splitlines():
                m = re.match(r'^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$', hang)
                if m:
                    return m.group(1)
    return None


# 固端 HTTPS 客户端：目标域名写死在本模块常量里，函数不接受 URL 参数，
# 调用方无法把请求引到别的主机（这条是 SSRF 边界，不是风格偏好）。
# 三种防护与各自挡的威胁：
#   ① 用 http.client 直连、不跟随重定向 —— 挡住 302 跳到内网地址；
#   ② ssl.create_default_context() —— 校验证书链与域名（防中间人）；
#   ③ 握手后核对**实际对端 IP** 必须是公网地址 —— 挡住内网域名解析与
#      DNS rebinding（域名第一次解析到公网、握手时换成 127.0.0.1 的手法）。
# 返回 (HTTP 状态码, 响应体字节)，把状态判断留给调用方（模型名回退需要它）。
def _qing_ai(ti, miyao):
    """固端 HTTPS 请求（http.client 直连，无重定向跟随）。"""
    # 443 端口 + 默认 SSL 上下文；超时 180 秒是给长文案留的余量
    # （整篇 9 模块解读逐次调用，单次慢一点也要能跑完，而不是 30 秒就断）。
    lian = http.client.HTTPSConnection(
        AI_ZHUJI, 443, context=ssl.create_default_context(), timeout=180)
    lian.connect()
    dui_duan = lian.sock.getpeername()[0]        # 实际连接 IP（握手后）
    # 只认 is_global：私网、环回、链路本地、组播、保留段一律拒绝。
    # 这里用的是「握手后 socket 的对端地址」，不是再解析一次域名——
    # 重新解析会被 rebinding 骗过，拿已建立的连接的 IP 才可靠。
    # 报错带上 IP 便于用户自查代理/VPN 配置，而不是含糊地说"网络错误"。
    if not ipaddress.ip_address(dui_duan).is_global:
        lian.close()
        raise RuntimeError(f'AI 端点解析到非公网地址 {dui_duan}，拒绝请求')
    # 手写 Host / Authorization / Content-Type：不用 requests 等第三方库，
    # 是为了让「域名固定、无重定向、无自动重试」这三件事由代码结构保证，
    # 而不是依赖库的默认行为（默认行为会跟随重定向、会自动重试）。
    lian.request('POST', '/chat/completions', body=ti, headers={
        'Host': AI_ZHUJI,
        'Authorization': 'Bearer ' + miyao,
        'Content-Type': 'application/json'})
    xiang = lian.getresponse()
    ma, ti = xiang.status, xiang.read()
    lian.close()
    return ma, ti


# 单次文案调用 = 一次对话请求。职责边界：只负责「发提示词、拿一段中文正文」，
# 不做业务拼装、不写文件、不判断报告结构（那些在调用方）。
# 三个入参各有用途：tishi=用户消息正文；juese=追加到系统提示的角色补充；
# zui_da=输出上限（批量清单类调用要放大，否则模型会写一半被截断）。
def _wen_ai(tishi, miyao, juese='', zui_da=4096):
    """单次文案调用。模型取环境 HENGCE_AI_MODEL，默认依次试官方别名与
    v4-flash（推理模型 content/reasoning_content 分离，只取 content）；
    zui_da 为输出上限（批量清单类调用可放大）。"""
    # 模型名回退链：HENGCE_AI_MODEL 环境覆盖 → 官方对话别名 deepseek-chat →
    # v4-flash。之所以要「试下一个」而不是写死一个：官方别名会随版本演进
    # （模型下线/改名时返回 400/404），固定名字会让程序在某个时间点整体失效。
    moxing_lie = _AI_MOXING_HUANCUN or [
        os.environ.get('HENGCE_AI_MODEL', ''),
        'deepseek-chat', 'deepseek-v4-flash']
    zui_hou = None
    for moxing in [m for m in moxing_lie if m]:
        ti = json.dumps({
            'model': moxing,
            'messages': [
                {'role': 'system', 'content':
                 # 系统提示的三条铁律，每条都对应一个真实风险：
                 #   ① 只用材料里的数字 —— 财务场景编造数字比答不出来更严重；
                 #   ② 简体中文、语气克制专业 —— 用户是企业财务，不要营销腔；
                 #   ③ 直接输出正文 —— 避免"好的，以下是我的分析："这类客套占满版面。
                 # juese 追加在其后，用于「每条一句」「共输出 N 条」这类调用点专属约束。
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
        # 400/404 = 模型名不被识别（含参数不合法），换成下一个候选继续试；
        # 其余非 200（401 鉴权、429 限流、5xx 服务端）立即抛错——
        # 那些换了模型也没用，继续重试只会把错误信息变得更难懂。
        # 截断响应体 160 字节：够看清原因，又不会把整页 HTML 错误页灌进日志。
        if ma in (400, 404):
            zui_hou = f'HTTP {ma}：{hui_ti[:160].decode("utf-8", "replace")}'
            continue                            # 模型名不识别 → 试下一个
        if ma != 200:
            raise RuntimeError(f'AI 调用失败（{moxing}）：HTTP {ma} '
                               f'{hui_ti[:160].decode("utf-8", "replace")}')
        hui = json.loads(hui_ti.decode('utf-8'))
        # 只取 content，**不取 reasoning_content**：推理模型的思考过程不是成品文案，
        # 混进报告会污染正文（且用户要的是结论，不是模型的草稿）。
        # 空文案按失败处理（不许用空串糊过去，否则报告会出现空章节还显示"已生成"）。
        wen = (hui['choices'][0]['message'].get('content') or '').strip()
        if not wen:
            raise RuntimeError(f'AI 返回空文案（{moxing}）')
        # 首次成功即缓存模型名：同一进程内后续调用直接用可用模型，
        # 不必每次都先撞一次 400/404（报告要调十几次，省下的往返很可观）。
        if not _AI_MOXING_HUANCUN:
            _AI_MOXING_HUANCUN.append(moxing)   # 首个可用模型缓存给后续调用
        return wen
    # 候选全部失败才到这里：把最后一次失败原因带出，用户/维护者能据此判断
    # 是密钥问题还是模型名问题；一个候选都没配置时明说"未配置模型"。
    raise RuntimeError(f'AI 调用失败（无可用模型）：{zui_hou or "未配置模型"}')


# 报告流水线的文案钩子工厂：把「取文案」这件事作为两个闭包注入报告组装模块，
# 组装模块不关心 AI 怎么调、密钥在哪，桥接层也不关心报告怎么排版——
# 两边只通过 (模块名, 数据块) → str 这一个契约耦合（便于各自单测）。
def _ai_bao_wencai(miyao):
    """构造报告流水线的两个文案钩子（模块解读 / 总体解读）。"""
    # 逐模块解读：把该模块的数据表原文塞进提示词，并明确要求「必须引用表中数字」。
    # 单位口径写在提示词里（金额=分、比率=基点）——不写清楚模型会把分当元来说，
    # 介绍出的结论金额会差 100 倍。
    def wencai(zhanshi, shuju_kuai):
        tishi = (f'本期「{zhanshi}」模块的数据表如下（预算 vs 实际；金额单位为分，'
                 f'比率单位为基点）。\n---\n{shuju_kuai}\n---\n'
                 '写一段 3-5 句的经营解读：整体表现如何、最值得注意的一到两项差异'
                 '（必须引用表中数字）、给管理者的一个行动方向。')
        return _wen_ai(tishi, miyao)

    # 总体解读：只喂「判定包」而不是全部明细——完成率/预警分布/单双环结论/
    # BSC 总分/整改优先级这些已经是引擎算好的结论，让模型去总结结论比让它
    # 从几千行明细里重新归纳更稳，也更省 token。
    # 输出要求 150-300 字：太短没有信息量，太长会盖过报告本身的表格。
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


# 整改建议批量回填。为什么是「一次调用生成全部条目」而不是逐条调用：
# 十几条逐条调会把等待时间放大到十几倍，且每条都缺少「全局优先级」的视野；
# 一次调用让模型在同一个上下文里排优先级，建议之间不会互相矛盾。
# 为什么是「改 md 再重写 html」而不是重跑流水线：只换文案、不动结构，
# 重跑流水线会重新检索、重新取数，既慢又可能引入无关差异。
def _ai_zhenggai(run, miyao, md_lu):
    """整改建议批量回填：一次调用生成全部条目建议，逐条替换（占位）行。
    解析不到的条目保持占位（诚实边界：宁可占位不冒充）。

    返回：成功回填的 [{no, desc, suggestion}] 列表——md/html 之外还要把同一批
    建议写进 {bao_id}.json（见 _tian_json_jianyi），调用方据此做三者对账；
    无清单/清单为空时返回 []（不是 False，空列表天然可迭代，少一层判断）。
    """
    from baogao_liuxian import zhuan_html
    # correction 在引擎原始结果里是对象（zucheng_md 用属性访问），兼容两种形态
    jiao = run.get('correction') if isinstance(run, dict) else None
    if jiao is None:
        return []                       # 无清单：回空映射（调用方据此跳过 JSON 同步）
    if isinstance(jiao, dict):
        qing = jiao.get('qingdan') or []
    else:
        qing = getattr(jiao, 'qingdan', None) or []
    tiao_mu = list(qing)
    if not tiao_mu:
        return []                       # 清单为空：回空映射（调用方据此跳过 JSON 同步）
    # 编号清单只给模型三样东西：序号、类型｜责任模块、描述。
    # 不带金额明细是刻意的——建议要指向"该做什么"，而不是再算一遍数；
    # 序号是回填时的唯一对应键（模型按编号回，程序按编号匹配）。
    lie_biao = '\n'.join(f'{xu}. [{t.leixing}｜{t.zeren_mokuai}] {t.miaoshu}'
                         for xu, t in enumerate(tiao_mu, start=1))
    # zui_da 放大到 8192：清单一多（十几条 × 每条一句）4096 会被截断，
    # 截断的后果是后半段条目回填不上（只能保持占位），用户会以为 AI 没干活。
    # 提示词禁用加粗/列表符号/代码块：回填目标是 md 的段落，多余标记会破坏排版。
    hui = _wen_ai(f'本期整改清单：\n{lie_biao}\n---\n'
                  '对每一条给出一句具体的处理建议（可点数字），按编号输出，'
                  '一行一条，格式严格为：编号. 建议（纯文本，不要加粗、'
                  '列表符号或代码块），不要多余内容。',
                  miyao, juese='每条一句，共输出与清单相同的条数。', zui_da=8192)
    jian_yi = {}
    # 宽容解析：模型经常无视"纯文本"要求，擅自加 **、-、>、[] 或全角冒号，
    # 这里把这些修饰都吃掉再取编号；宁可多认几种写法，也不让用户看到
    # 「AI 明明给了建议、报告里却还是占位」这种自相矛盾的结果。
    for hang in hui.splitlines():
        # 容忍模型加的 markdown 修饰（**、-、>、[] 等）再取编号
        m = re.match(r'^[\s\-\*#>\[\|]*(?:\**)?\s*(\d{1,3})\s*\]*[\].、:：)]\s*(.+?)\s*\**\s*$', hang.strip())
        if m:
            jian_yi[int(m.group(1))] = m.group(2).strip()
    # 读整篇 → 逐条字符串替换 → 整篇写回。之所以字符串替换可行：
    # 占位行的文案是报告组装模块固定生成的（`（占位）** 描述——待 DSH 宿主
    # agent 回填。`），格式稳定；换成结构化改 md 反而要重写渲染层。
    # 幂等由「占位串是否存在」天然保证：已回填过的条目不再匹配，重跑不会叠加。
    lu = Path(md_lu)
    wen = lu.read_text(encoding='utf-8')
    # 回填成功的条目收集成映射：reason=md/html/json 三者必须同源同数，
    # 调用方拿它把同一批建议写进 {bao_id}.json 的 aiAnalysis.actions[].suggestion。
    tian = []
    for xu, t in enumerate(tiao_mu, start=1):
        yuan = (f'**{xu}. [{t.leixing}｜{t.zeren_mokuai}]（占位）** '
                f'{t.miaoshu}——待 DSH 宿主 agent 回填。')
        if yuan in wen and jian_yi.get(xu):
            # 每条建议文本**前**加统一标注（AI_BIAOZHU，一字不改）：
            # 「哪一段是模型写的」要和建议本身同屏可见，所以标注紧贴建议之前，
            # 而不是只靠报告抬头那一行总的免责声明。
            wen = wen.replace(yuan, f'**{xu}. [{t.leixing}｜{t.zeren_mokuai}]** '
                              f'{t.miaoshu}\n\n'
                              f'> {AI_BIAOZHU}\n\n建议：{jian_yi[xu]}')
            # no=md 里的编号（1 起）；desc=引擎原文，供 JSON 侧在编号口径
            # 万一漂移时按描述兜底匹配，避免「建议写了却没对上条」。
            tian.append({'no': xu, 'desc': str(t.miaoshu),
                         'suggestion': jian_yi[xu]})
    lu.write_text(wen, encoding='utf-8')
    # md / html 必须同源重写：zhuan_html 会把上面插入的 `> {AI_BIAOZHU}`
    # 转成 <blockquote>，并在 </body> 前补统一页脚标注（报告组装模块已实现）。
    # 只写 md 不写 html 会得到「md 有 AI 标注、html 还是占位」的错版报告。
    Path(str(md_lu).replace('.md', '.html')).write_text(
        zhuan_html(wen), encoding='utf-8')
    return tian


def _tian_json_jianyi(json_lu, tian):
    """把已回填进 md 的 AI 建议同步写进报告 JSON（md/html/json 三者同源同数）。

    背景：报告流水线先生成 JSON（纯计算模式下 actions[].suggestion 为空串），
    桥接层随后把 AI 建议回填进 md/html。若不把同一批建议写回 JSON，
    用户「导出 JSON」拿到的机读副本就会是"有报告没建议"的残版，
    与眼前看到的报告不一致——对机读消费方（CLI/BI）尤其危险。

    匹配策略：编号（no）优先——md 的编号与流水线 actions 的编号同源，
    都是整改清单的 1 起序号；描述（desc）兜底——万一某一侧编号口径漂移，
    仍能按引擎原文对上条，不至于整批丢失。
    返回 True=至少写回一条；False=无建议/无文件/对不上（不抛错、不改文件）。
    """
    if not tian:
        return False
    lu = Path(json_lu)
    if not lu.exists():                        # 理论上不该发生，兜底不报错
        return False
    shu = json.loads(lu.read_text(encoding='utf-8'))
    fen_xi = shu.get('aiAnalysis')
    if not isinstance(fen_xi, dict):
        return False
    dong_zuo = fen_xi.get('actions') or []
    # 两张索引：编号表（主）+ 描述表（兜底）。no 可能是 int 或数字串，统一成 int。
    an_hao = {int(x['no']): x for x in dong_zuo
              if str(x.get('no', '')).strip().isdigit()}
    an_miao = {str(x.get('desc') or '').strip(): x
               for x in dong_zuo if x.get('desc')}
    xie = 0
    for xiang in tian:
        mu_biao = an_hao.get(xiang['no']) or an_miao.get(xiang['desc'].strip())
        if mu_biao is None:
            continue
        mu_biao['suggestion'] = xiang['suggestion']
        xie += 1
    if not xie:                                # 一条都没对上：保持原样更好
        return False
    # 顶层标注随建议一起置真：JSON 里既然有了 AI 文案，
    # aiGenerated/aiNotice 就必须与 md 抬头、状态条目、UI 标签口径一致。
    shu['aiGenerated'] = True
    shu['aiNotice'] = AI_BIAOZHU
    # 与流水线同一写法（ensure_ascii=False + indent=2 + 末尾换行）：
    # 保证「T1 写 → 我改」两段产出的格式逐字节同风格，diff 只出现在 suggestion 上。
    lu.write_text(json.dumps(shu, ensure_ascii=False, indent=2) + '\n',
                  encoding='utf-8')
    return True


@dongzuo('reports.generate')
def _(zt, payload):
    """对指定运行组装计算报告（md+html）并打印 PDF。"""
    # 延迟 import：报告组装模块要读 kb2 指引库、可选依赖较重，
    # 桥接进程启动时不需要它（workspace.load / 导入都不碰报告），
    # 放到 action 里 import 能让冷启动和只做导入的用户少等。
    from baogao_liuxian import compute_report_pipeline
    if zt.get('dirty'):
        raise RuntimeError('输入或配置已变更：请先重新运行分析，再生成报告')
    # runId 两级来源：UI 显式指定（历史回放时对准某一版）→ 当前运行号。
    # 优先 payload 是为了让"回放旧版再出报告"能出对的那一版。
    rid = (payload or {}).get('runId') or zt.get('currentRunId')
    # _RUNS 是「进程内」的引擎结果缓存（快照只够回放视图，不含全部派生对象）。
    # 三种情况会走到这里：桥接进程重启过、运行号来自更早的会话、被并发清理。
    # 报错要说清"结果不在本进程"而不是笼统的"找不到"，用户才知道该重跑分析。
    if rid not in _RUNS:
        raise RuntimeError('该运行的原始结果已不在本进程（重启或更早的运行）：'
                           '请重新运行分析后再生成报告')
    run = next((r for r in zt['runs'] if r['id'] == rid), None)
    # ---- AI 解读（includeAI）：真实模型调用逐节回填；未配密钥如实报错 ----
    # includeAI 的语义（UI 上就是「加入 AI 经营解读」勾选框）：
    #   False = 纯计算报告，零模型调用、零 token 消耗、章节用确定性占位文案；
    #   True  = 逐模块 + 总体都调模型，报告标题追加「（含AI解读）」。
    # 默认 False：不给用户"偷偷花钱调模型"的意外。
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
        # 两个钩子注入后，报告组装模块在遇到「需要 AI 文案」的位置回调它们；
        # 桥接层不参与排版，组装模块也不需要知道密钥/端点/重试策略。
        wencai_hanshu, zongjie_hanshu = _ai_bao_wencai(miyao)
    BAOGAO_MU.mkdir(parents=True, exist_ok=True)
    bao = compute_report_pipeline(_RUNS[rid], wencai_hanshu=wencai_hanshu,
                                  zongjie_hanshu=zongjie_hanshu,
                                  shuchu_mu=str(BAOGAO_MU))
    # 报告 id = report-时间戳-序号。时间戳保证跨天不撞，序号保证同一秒内连出
    # 两份也不撞（UI 显示"第 N 份"，插到列表头部即最新在前）。
    # 注意 id 里的序号取的是「生成前的报告数 + 1」，历史被清理后可能回退，
    # 所以外部引用报告一律用 id 全串，不能靠序号推算。
    bao_id = f'report-{datetime.now().strftime("%Y%m%d-%H%M%S")}-{len(zt["reports"]) + 1}'
    # 流水线输出固定文件名（幂等设计）；复制成按报告 id 命名的存档，历史互不覆盖
    cun_md = BAOGAO_MU / f'{bao_id}.md'
    cun_html = BAOGAO_MU / f'{bao_id}.html'
    # 流水线按固定文件名（计算报告-月度.md）输出以保证幂等；
    # 这里复制成按报告 id 命名的存档，历史报告互不覆盖。
    # 用 write_bytes 而不是文本写入：md/html 已是 UTF-8 字节，二次转码只会引入偏差。
    cun_md.write_bytes(Path(bao['md']).read_bytes())
    cun_html.write_bytes(Path(bao['html']).read_bytes())
    tian_jianyi = []                            # 回填成功的 AI 建议（供 JSON 同步）
    if yao_ai:
        try:                                    # 整改建议批量回填（md+html 重写）
            # 整改建议回填失败**不毁报告**：单条建议回填是附加项，
            # 失败就保留占位（报告里会明确写"待 DSH 宿主 agent 回填"），
            # 绝不因为一次模型调用失败就把整份已经算好的报告作废。
            # 异常只打到 stderr，让 UI 用户无感、维护者能查到原因。
            tian_jianyi = _ai_zhenggai(_RUNS[rid], miyao, str(cun_md))
        except Exception as e:                  # noqa: BLE001 建议失败不毁报告
            print(f'[hengce] 整改建议 AI 回填失败（保留占位）：{e}',
                  file=sys.stderr, flush=True)
    pdf_linshi = Path(bao['html']).with_suffix('.pdf')
    # PDF 走本机 Chrome/Edge 的打印功能（headless --print-to-pdf），
    # 因此它依赖用户机器上装了浏览器：失败时 md/html 仍然可用，
    # 状态里 pdfPath 记 None、pages 记 None（UI 据此禁用"导出 PDF"而不是报一个假页数）。
    you_pdf = zhuan_pdf(str(cun_html), str(BAOGAO_MU / f'{bao_id}.pdf'))
    cun_pdf = BAOGAO_MU / f'{bao_id}.pdf'
    # ---- 报告 JSON：与 md/html/pdf 同批落盘（改造规范第四节接口约定）----
    # 数据来源优先用报告流水线返回的 'json'（计算报告-月度.json：与 md 用同一次
    # 汇总生成，不重复检索、不重复取数）；流水线不给路径时退到「与 md 同名的
    # .json」兜底。JSON 失败不毁报告：md/html/pdf 才是主产物，机读副本缺失时
    # 只记 stderr 并让 jsonPath=None（UI 据此禁用「导出 JSON」）。
    cun_json = BAOGAO_MU / f'{bao_id}.json'
    json_ok = False
    try:
        yuan_json = Path(bao.get('json')
                         or Path(bao['md']).with_suffix('.json'))
        if yuan_json.exists():
            cun_json.write_bytes(yuan_json.read_bytes())
            json.loads(cun_json.read_text(encoding='utf-8'))   # 校验可解析
            json_ok = True
        else:
            raise FileNotFoundError(f'报告流水线未产出 JSON：{yuan_json}')
    except Exception as e:                  # noqa: BLE001 JSON 副本不阻断出报告
        cun_json.unlink(missing_ok=True)     # 半截/非法 JSON 不留盘，免得被导出
        print(f'[hengce] 报告 JSON 落盘失败（md/html/pdf 不受影响）：{e}',
              file=sys.stderr, flush=True)
    # ---- AI 建议回写 JSON：md / html / json 三者同源同数 ----
    # 上面 _ai_zhenggai 已把建议写进 md（并重写 html），但 JSON 是流水线在
    # 「AI 回填之前」生成的，aiAnalysis.actions[].suggestion 此刻还是空串。
    # 不同步的话，用户导出 JSON 会拿到一份"有报告没建议"的机读残版，
    # 与眼前看到的报告不一致——对 CLI/BI 这类机读消费方尤其危险。
    # 匹配与写回失败都只在 stderr 留痕：JSON 仍是合法文件，只是缺 AI 建议。
    if json_ok and tian_jianyi:
        try:
            if _tian_json_jianyi(cun_json, tian_jianyi):
                print(f'[hengce] AI 建议已同步进 {cun_json.name}'
                      f'（{len(tian_jianyi)} 条）', file=sys.stderr, flush=True)
        except Exception as e:              # noqa: BLE001 同步失败不毁报告
            print(f'[hengce] AI 建议写进 JSON 失败（JSON 保持无建议）：{e}',
                  file=sys.stderr, flush=True)
    # 报告登记插入列表头部（UI 按顺序渲染，最新在最前）。
    # 字段纪律：只新增字段、不改既有字段语义——
    #   format 仍是 'PDF'（UI 报告卡片按它显示徽标，改了会整列错位）；
    #   includeAI 保留（历史报告的回看逻辑依赖它）；
    #   新增 aiGenerated/aiNotice（AI 标注契约）与 jsonPath（机读版路径）。
    zt['reports'].insert(0, {
        'id': bao_id,
        'title': f'{(run or {}).get("period", "")} 计算报告'
                 + ('（含AI解读）' if yao_ai else ''),
        'period': (run or {}).get('period', ''), 'createdAt': xianzai(),
        'status': 'ready', 'format': 'PDF',
        'pages': shu_yeshu(cun_pdf) if you_pdf else None,
        'includeAI': yao_ai,           # True=模型逐节回填；False=纯计算+占位标注
        # AI 标注契约（规范第三节）：只有真接了模型才挂标注；
        # 未启用 AI 的纯计算报告 aiGenerated=False、aiNotice 为空，
        # 绝不为了好看给确定性计算贴上「AI 生成」。
        'aiGenerated': yao_ai,
        'aiNotice': AI_BIAOZHU if yao_ai else '',
        'mdPath': str(cun_md), 'htmlPath': str(cun_html),
        'pdfPath': str(cun_pdf) if you_pdf else None,
        # format 仍是 'PDF'（UI 报告卡片按它显示徽标，不动）；
        # JSON 只作为附加能力登记在 jsonPath 上，供 reports.export 导出。
        'jsonPath': str(cun_json) if json_ok else None,
    })
    return fang_kuaizhao(zt)


@dongzuo('reports.export')
def _(zt, payload):
    """导出报告（md/html/pdf 真实字节；pdf 缺失时如实报错）。

    1.1.5 起多支持 json（机读版，规范第四节）：四格式走同一张白名单，
    出参仍是 {name, mime, bytesB64}，调用方（UI/CLI）无需区分格式。
    """
    b = payload or {}
    bao = next((r for r in zt['reports'] if r['id'] == b.get('id')), None)
    if not bao:
        raise RuntimeError(f'找不到报告：{b.get("id")}')
    # 白名单三元组 = (状态里的路径键, mime, 下载文件名后缀)。
    # json 用 RFC 8259 规定的字符集参数写法，Windows 记事本/浏览器都能按 UTF-8 打开。
    biaozhun = {'md': ('mdPath', 'text/markdown; charset=utf-8', '.md'),
                'html': ('htmlPath', 'text/html; charset=utf-8', '.html'),
                'pdf': ('pdfPath', 'application/pdf', '.pdf'),
                'json': ('jsonPath', 'application/json; charset=utf-8', '.json')}
    if b.get('format') not in biaozhun:
        raise RuntimeError(f'不支持的导出格式：{b.get("format")}')
    # 三元组解包：路径键 → 状态字段名，mime → 回包声明的类型，后缀 → 下载文件名。
    # 出参固定 {name, mime, bytesB64}，前端/CLI 拿同一份结构写文件，
    # 不需要为每种格式写分支（这是"协议面收敛"的意思）。
    jian, mime, houzhui = biaozhun[b['format']]
    lu = bao.get(jian)
    if not lu or not Path(lu).exists():
        # 报错口径与既有格式一致（同一前缀、同一中文句式），
        # 只把末尾提示换成本格式的真实原因，不误导用户去修浏览器。
        tishi = ('JSON 与 md/html 同批生成，文件可能已被清理'
                 if b['format'] == 'json'
                 else 'PDF 依赖本机 Chrome/Edge 打印，可能未生成')
        raise RuntimeError(f'报告文件不存在（{b["format"]}）：{tishi}')
    return {'name': f'{bao["title"]}{houzhui}', 'mime': mime,
            'bytesB64': base64.b64encode(Path(lu).read_bytes()).decode('ascii')}


@dongzuo('reports.openFolder')
def _(zt, payload):
    """在资源管理器中定位报告文件（Windows）。"""
    bao = next((r for r in zt['reports'] if r['id'] == (payload or {}).get('id')), None)
    if not bao:
        raise RuntimeError(f'找不到报告：{(payload or {}).get("id")}')
    # 定位优先级 pdf → html → md：优先选中用户最想看的最终成品；
    # 三者都没有时用空串构造 Path（不会抛错），交给下一行的 exists 统一报错。
    lu = Path(bao.get('pdfPath') or bao.get('htmlPath') or bao.get('mdPath') or '')
    if not lu.exists():
        raise RuntimeError('报告文件不存在，无法打开所在目录')
    # explorer /select 选中文件并打开所在目录。capture_output 是必须的：
    # explorer.exe 即使成功也常返回非 0 退出码，把输出丢掉才不会污染 stdio 协议流
    # （本进程的 stdout 是 JSON 行协议通道，任何第三方输出漏进去都会让宿主解析失败）。
    subprocess.run(['explorer', '/select,', str(lu)], capture_output=True)
    return {'handled': True}


@dongzuo('history.open')
def _(zt, payload):
    """载入历史运行快照（保留完整历史列表与最新文件清单）。"""
    rid = (payload or {}).get('id')
    run = next((r for r in zt['runs'] if r['id'] == rid), None)
    # 快照是回放的唯一数据源：没有快照的历史只能看列表、不能回放（明确报错，
    # 不拿"当前结果"冒充那份历史——那是财务口径上不可接受的替换）。
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
    """仅把用户授权的本次运行、所选部门结果发送给既有 AI 服务。

    数据纪律：只发 runId + 所选部门 + 期间 + 该部门的差异行，不含八字段原文、
    不含其他部门、不含磁盘路径；金额仍是整数分、比率仍是整数基点。
    """
    b = payload or {}
    # 授权闸用 `is not True` 而不是 `not b.get(...)`：只有显式布尔 True 才算同意，
    # 字符串 'false'、1、非空对象这些"真值"都不算——数据外发必须是一次明确的勾选，
    # 不能因为前端传了个真值就默认用户同意了。
    if b.get('dataAccess') is not True:
        raise RuntimeError('请先勾选「允许访问当前分析结果」，再向助手提问')
    wenti = str(b.get('question') or '').strip()
    if not wenti:
        raise RuntimeError('请输入要询问的问题')
    # dirty=True 表示「输入或配置相对上次分析已变更」，此时报告内容会对不上
    # 用户刚导入的数据。这里必须锁死：宁可让用户多点一次"运行分析"，
    # 也不能生成一份数字过期的报告（财务报告一旦发出就难以收回）。
    if zt.get('dirty'):
        raise RuntimeError('输入或配置已变更，请先重新运行分析，再询问当前结果')
    kuai = fang_kuaizhao(zt)
    shangwen = b.get('context') or {}
    # 版本一致性校验：UI 发来的上下文带 runId，必须与当前结果完全一致。
    # 不一致说明用户看到的是旧页面（分析已重跑过），此时回答会基于新材料
    # 却指着旧界面上的行——财务问答里这种错位比不回答更危险，所以直接让用户刷新。
    if not kuai['meta']['runId'] or shangwen.get('runId') != kuai['meta']['runId']:
        raise RuntimeError('分析版本已变化，请刷新当前结果后重新提问')
    bumen_id = shangwen.get('entityId') or 'all'
    bumen = next((e for e in kuai['entities'] if e['id'] == bumen_id), None)
    if bumen is None:
        raise RuntimeError('找不到所选部门，请刷新当前分析结果')
    if shangwen.get('period') and shangwen['period'] != kuai['meta']['period']:
        raise RuntimeError('分析期间已变化，请刷新当前结果后重新提问')
    # 部门隔离：只取所选部门的差异行（公司级行的 departmentId 是 'all'）。
    # 这是权限边界——用户只授权了"当前所选部门"，混进其他部门的行就是越权外发。
    hang = [r for r in kuai['rows'] if r.get('departmentId', 'all') == bumen_id]
    row_id = shangwen.get('rowId')
    if row_id:
        hang = [r for r in hang if r['id'] == row_id]
        if not hang:
            raise RuntimeError('关注的差异行不属于当前部门，请重新选择')
    if not hang:
        raise RuntimeError('所选部门暂无可解读的分析结果，请补齐工作簿并运行分析')
    miyao = _du_miyao()
    if not miyao:
        raise RuntimeError('未配置 DeepSeek API 密钥：请先在「分析设置 → AI 服务」保存密钥')
    # 外发材料做最小化：运行号 + 部门信息 + 期间 + 该部门差异行。
    # 不含八字段原文（那是用户的账，模型不需要）、不含磁盘路径、不含其他部门。
    # 金额仍是整数分、比率仍是整数基点——不在这一层换算，免得和界面数字对不上。
    cailiao = {'runId': kuai['meta']['runId'], 'department': bumen,
               'period': kuai['meta']['period'], 'rows': hang}
    # 提示词把口径和边界同时写死：单位（分/基点）+ 只解释所选部门、不推断其他部门、
    # 不加材料外的数值。模型越界时用户会看到一个"编出来的部门结论"，
    # 这比答不出来严重得多，所以约束放在 user 消息开头而不是结尾。
    tishi = ('以下是用户授权的当前分析材料，金额单位为分、比率单位为基点。'
              '只解释材料中的所选部门，勿推断其他部门或添加材料外的数值。\n'
              + json.dumps(cailiao, ensure_ascii=False)
              + '\n用户问题：' + wenti)
    hui_da = _wen_ai(tishi, miyao)
    # AI 标注三件套（规范第三节）：
    #   text 末尾附一行纯文本标注——聊天记录被复制/导出时也不丢标注；
    #   aiGenerated=True——UI 据此决定是否渲染标注；本 action 的正文恒为模型输出；
    #   aiNotice=统一文案原文——UI 直接渲染该字符串，不在前端拼文案（避免走样）。
    # 用纯文本而不是 md 引用块（“> ”）：聊天气泡按纯文本渲染，“>”会当正文露出来。
    return {'text': f'{hui_da}\n\n{AI_BIAOZHU}', 'sources': [
        {'title': f'{bumen["name"]} · {kuai["meta"]["period"]}',
         'excerpt': f'分析版本 {kuai["meta"]["runId"]}，共 {len(hang)} 条差异记录'}],
        'aiGenerated': True, 'aiNotice': AI_BIAOZHU}


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

    # 按「顶格、形如 key:」的行切节：yaml 顶层键一定不缩进，这种极简解析
    # 足以处理 dsh 的凭据文件，且**未知节原样保留**（官方后续加新键也不会丢）。
    # 用完整 yaml 库反而有风险：不同版本的序列化风格会改写用户文件的其他部分。
    def chai_hang(yuan):
        """按顶层键把文件拆成 [标题行, [子行...]] 的节列表（其余原样）。"""
        jie = []
        for hang in yuan.splitlines():
            if hang and not hang[0].isspace() and re.match(r'^[A-Za-z_][\w-]*:', hang):
                jie.append([hang, []])
            elif jie:
                jie[-1][1].append(hang)
        return jie

    # 查询态：文件优先（用户最近一次保存的值就是生效值），其次进程启动时的环境变量。
    # 只回掩码（前 3 + 后 4）——界面要能看出"配没配、是不是这把"，
    # 但明文密钥一旦进了前端就能被截图/日志带走，所以永不出后端。
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
    # 一个 action 两种语义：不带 key 就是查状态（UI 打开设置页时调），
    # 带 key 才是写入/清除（key='' 表示清除）。用"键是否存在"而不是"值是否为空"
    # 来区分，是为了让"清除密钥"这个明确意图不被误判成查询。
    if 'key' not in b:
        return cha()                                  # 查询：不动文件
    # DSH_HOME 未设 → 没有可信的落盘位置 → 拒绝写入。
    # 绝不回落到 ~/.credentials.yaml（那是 C 盘家目录）：零 C 盘纪律 +
    # 写错文件比不写更糟（可能污染其他 dsh 实例的密钥）。
    if wen is None:
        raise RuntimeError('未检测到 DSH_HOME（独立服务模式不落盘）：'
                           '请从衡策启动器或 dsh 客户端内使用本功能')
    xin = str(b.get('key') or '').strip()
    # 格式校验故意宽松（只有长度和空白两条），目的是挡住"把手机号/密码/
    # 带引号的整行 yaml 粘进来"这类明显错误，而不是替用户验 deepseek 的密钥规则
    # （官方规则会变，验太严会把合法密钥拒之门外）。
    if xin and (len(xin) < 8 or re.search(r'\s', xin)):
        raise RuntimeError('密钥格式不对：应为 sk- 开头的连续字符串')

    # 文件不存在时用最小初始内容（只有 version 节），
    # 这样首次保存密钥不会产生一个缺 version 的文件（dsh 侧会判为损坏）。
    yuan = wen.read_text(encoding='utf-8') if wen.exists() else 'version: 1\n'
    jie = chai_hang(yuan)
    ban = next((j for j in jie if j[0].startswith('version:')), None)
    tou = ban[0] if ban else 'version: 1'
    # refs 节里除本密钥外的其他子键原样保留（未来官方扩展不丢）
    # refs 节里「除本密钥外的其他子键」原样保留并放回：
    # 凭据文件是 dsh 的公共资产（可能还存着别的服务密钥），
    # 本功能只拥有 DEEPSEEK_API_KEY 这一行，多改一行都是越权。
    refs_yu = [h for j in jie if j[0].startswith('refs:')
               for h in j[1] if h.strip() and not MIYAO_HANG.match(h)]
    # 其余各节（records/账号登录态等）逐字保留、顺序不变：
    # 这些是 dsh 登录态，改一个字符就可能让用户被登出——
    # 本功能必须做到"只动该动的一行"。
    qita = [h for j in jie
            if not j[0].startswith(('version:', 'refs:'))
            for h in [j[0]] + j[1]]

    xin_hang = ([tou, 'refs:'] + refs_yu
                + ([f'  DEEPSEEK_API_KEY: {xin}'] if xin else [])) \
        if (xin or refs_yu) else [tou]
    jia.mkdir(parents=True, exist_ok=True)
    linshi = wen.with_suffix('.tmp')
    # 先写 .tmp 再原子 replace：dsh 用 watch 热载凭据文件，
    # 直接覆盖会有"读到半截文件"的窗口（表现为密钥突然失效）。
    # 原子替换保证 watch 要么看到旧内容、要么看到完整新内容。
    linshi.write_text('\n'.join(xin_hang + qita) + '\n', encoding='utf-8')
    linshi.replace(wen)                               # 原子替换，watch 即刻热载
    # 写入后回查询态（掩码）：让 UI 用同一份结构刷新显示，
    # 不需要前端自己再猜"保存成功后该显示什么"。
    return cha()


# ======================================================================
# 行协议主循环
# ======================================================================

# stdio 行协议的单一入口：一行一个 JSON 请求 → 一行一个 JSON 回包。
# 设计约束（宿主 adapter/桥接.mjs 依赖，不可改）：
# ① 只读 stdin、只写 stdout，日志一律走 stderr；
# ② 每个请求都必须有回包（含坏 JSON / 未知 action），否则宿主会一直等；
# ③ 进程生命周期 = 宿主插件的生命周期，请求之间共享同一份 _ZT 状态。
def main():
    """stdin 逐行读请求 → 分发 → stdout 逐行回包（UTF-8，行 flush）。"""
    # Windows 管道默认用 GBK 编解码，中文 action/内容会直接抛 UnicodeDecodeError；
    # 显式重配成 UTF-8，与宿主 Node 侧的 UTF-8 写入对齐（这是跨语言协议的基本前提）。
    sys.stdin.reconfigure(encoding='utf-8')         # Windows 管道默认 GBK，必须重配
    sys.stdout.reconfigure(encoding='utf-8')
    # 不写 __pycache__：安装目录可能只读（Program Files）或被卸载器整目录删除，
    # 留字节码缓存只会制造"卸载后仍有残留文件"的假象。
    sys.dont_write_bytecode = True                  # 不留 __pycache__ 副产物
    global _ZT
    # 全进程唯一的状态对象（模块级 _ZT）。单进程串行处理请求，
    # 因此不需要锁；这也意味着本服务不支持多客户端并发（宿主侧的约定）。
    # 启动即读盘：工作区是"上次退出时的样子"，不需要用户重新导入。
    _ZT = du_zhuangtai()
    for hang in sys.stdin:
        hang = hang.strip()
        if not hang:
            continue
        try:
            qing = json.loads(hang)
        except ValueError:
            # 坏 JSON 也要回包（id 未知就给 None）：宿主按 id 匹配回包，
            # 不回包会让该请求永远挂起，比给一个错误更糟。
            _huifu({'id': None, 'ok': False, 'error': '请求不是合法 JSON'})
            continue
        # 未知 action 同样回 ok:false 的中文错误并继续循环——
        # 协议层不能因为"前端版本比后端新"就整条流断掉（版本错配是常态）。
        hanshu = DONGZUO.get(qing.get('action'))
        if hanshu is None:
            _huifu({'id': qing.get('id'), 'ok': False,
                    'error': f'未知的 action：{qing.get("action")}'})
            continue
        try:
            # payload 统一兜底成 {}：handler 内部就可以直接 .get 而不必层层判 None。
            # tanping(data) 把不可 JSON 序列化的对象（Decimal/日期等）摊平成字符串，
            # 保证回包一定能 json.dumps 成功——协议层不允许"数据里混了 Decimal 就整包失败"。
            data = hanshu(_ZT, qing.get('payload') or {})
            da = {'id': qing.get('id'), 'ok': True, 'data': tanping(data)}
        except Exception as e:                      # noqa: BLE001 业务错误统一回中文文案
            # 业务错误统一收敛成中文文案（str(e) 原样，不做英文包装、不改写措辞）：
            # UI 会把这句话直接展示给用户，桥接层改写反而会让用户看不懂问题出在哪个文件。
            da = {'id': qing.get('id'), 'ok': False, 'error': str(e)}
        _huifu(da)


# 回包与落盘的顺序是刻意的：先写 stdout 并 flush（宿主立刻拿到结果、界面不卡），
# 再持久化状态。反过来的话，一次慢磁盘写入就会让每个请求都多等几百毫秒。
def _huifu(da):
    """回包 + 状态落盘（每个请求后持久化，崩溃不丢工作区）。"""
    sys.stdout.write(json.dumps(da, ensure_ascii=False) + '\n')
    sys.stdout.flush()
    try:
        xie_zhuangtai()
    except OSError:
        pass                                        # 状态写失败不阻断回包


# 导入保护：质检脚本、CLI、测试都要 import 本模块拿 DONGZUO 却
# 不能启动 stdio 主循环（那会阻塞在 stdin 上）。这条守卫是它们的前提。
if __name__ == '__main__':
    main()
