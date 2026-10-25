# -*- coding: utf-8 -*-
"""衡策 CLI —— 统一命令行入口（供人和 AI 用命令行驱动全流程）。

一条命令串起真实程序，不手搓中间数据：
    import   读 .xlsx 工作簿 → 契约校验 → 八字段入库 → 落 CLI 独立状态
    analyze  十五步分析（滚动/差异/单双环/积木/BSC/KPI/整改…）
    report   计算报告组装（md / html / pdf / json）
    all      import → analyze → report 一条龙
    serve    起独立 HTTP 服务（127.0.0.1:端口/hengce/，液态玻璃工作台）
    doctor   环境自检（解释器/依赖/检索库/浏览器/密钥/Node）→ 中文修复建议
    version  版本信息（程序版本 / JSON 协议 / 解释器 / 后端动作数）

口径纪律（与桌面程序一致，任何子命令都不得违反）：
    · 金额一律整数分，比率一律整数基点；CLI 只做搬运与格式化，不二次取整；
    · 只引用检索到的《管理会计应用指引》条文，检索不到就如实写「未检索到」；
    · 演示数据全部来自固定种子，不虚构真实企业；
    · 契约校验失败时把后端的中文报错原样转出，不臆测原因、不吞异常。

退出码：0 成功 ｜ 1 业务失败（中文原因写 stderr）｜ 2 参数错误（用法不对）。

JSON 协议（--json）：stdout 只写一个 JSON 信封，形如
    {"schema":"hengce.cli/1","ok":true,"command":"all","elapsedMs":1203,
     "stages":[{"stage":"…","seconds":0.23}],"data":{…}}
工作期间的任何进度/提示/后端打印全部改走 stderr，保证程序侧可以直接 json.loads

路径纪律（安装后必须能跑）：
    · 一切路径都以 Path(__file__).resolve() 反推，不依赖当前工作目录、不写死开发机路径；
      CLI 位于 <插件根>/backend/，故插件根 = __file__ 的上两级目录；
    · 状态文件独立为 <插件根>/数据/cli-状态.json，绝不覆盖 UI 的 <插件根>/数据/状态.json；
    · 输出默认落 <插件根>/数据/cli-输出/，可用 --out 覆盖；
    · 临时件只落 <插件根>/数据/临时/，禁写 C 盘（用户铁律）。

安装后用法（启动器 衡策CLI.cmd 转发到本文件，当前目录不限）：
    衡策CLI.cmd doctor
    衡策CLI.cmd version
    衡策CLI.cmd all --xlsx "D:\\某目录\\预算基础.xlsx" --xlsx "D:\\某目录\\实时经营.xlsx"
    衡策CLI.cmd all --xlsx "D:\\某目录\\预算基础.xlsx" --format md,html,pdf,json --out D:\\某目录\\报告
    衡策CLI.cmd report --format md,html,json
    衡策CLI.cmd serve --port 4180

开发期用法（源码目录，解释器换成随包 Python 即可）：
    python -B 衡策CLI.py import --xlsx 预算基础.xlsx --xlsx 实时经营.xlsx
    python -B 衡策CLI.py analyze --cycle 月度 --period 2027-06 --growth 0
    python -B 衡策CLI.py report --format md,html,pdf,json
    python -B 衡策CLI.py all --format md,html,json

写作用域：本文件只做命令行入口，不修改后端任何模块；后端行为完全由
桥接入口.py 的动作表 DONGZUO 决定（与 UI 调同一套代码，最不容易分叉）。
"""

import argparse                      # 子命令与选项解析（报错已翻成中文）
import ast                           # 检查桥接入口是否有 __main__ 保护
import base64                        # 工作簿字节 → 动作表要求的 bytesB64
import contextlib                    # 阶段计时与 stdout 重定向上下文
import decimal                       # 额度换算（元 → 分、百分比 → 基点）用十进制避免浮点误差
import importlib                     # 惰性载入后端（桥接入口）
import json                          # JSON 信封、读 package.json、写兜底 JSON 报告
import os                            # 环境变量、原子替换、进程号
import pickle                        # 跨进程保存分析原始结果（保住 dataclass 属性访问）
import platform                      # doctor/version 报告系统信息
import re                            # 文件名种子、参数格式、markdown 解析
import shutil                        # 定位 node（serve 用）
import socket                        # serve 前探测端口占用
import subprocess                    # 起独立 HTTP 服务 / 收键
import sys                           # 标准输入输出、解释器路径、退出码
import time                          # 阶段耗时
import traceback                     # 未预期异常不吞：完整栈给 stderr
import urllib.request                # 轮询等后台服务就绪
from datetime import datetime
from pathlib import Path

# ======================================================================
# 〇、读代码前先看这页：数据流、进程边界与三个「不」
# ======================================================================
#
# 【一条 all 命令内部发生了什么】
#   ① 读文件：--xlsx 指向的 .xlsx 按字节读入，base64 编码成 bytesB64，
#      组装成 DONGZUO['files.import'] 要求的 payload——不落地临时文件、不改用户原件；
#   ② 契约校验：后端 import_excel_v11 逐表核表名/顺序/科目/元字段/公式，
#      通过才解析成八字段记录；任一本不过就整批失败，中文原因原样转出（不吞异常）；
#   ③ 入库：八字段记录以 CSV 文本形态挂在状态 files[].text 上（状态文件是唯一真身），
#      同时记 category/rows/checks/entity，供后续分析与 doctor 展示；
#   ④ 分析：DONGZUO['analysis.run'] 用状态里的 CSV 组装引擎载荷 → yinqing.fenxi 十五步；
#   ⑤ 快照：后端把引擎结果折算成「工作区快照」kuai（rows/actions/kpis/trend/warnings），
#      CLI 只从快照读计数用于打印，不自己二次计算；
#   ⑥ 缓存：引擎原始结果 jieguo 落 pickle（见 _cun_yunxing 的说明），因为 report 往往是
#      另一次进程调用，而它必须拿到带 dataclass 属性的原始对象；
#   ⑦ 报告：compute_report_pipeline(jieguo) 出 md（正文）、html（由 md 转）、json（结构化）；
#      pdf 由本机 Chrome/Edge headless 从 html 打印，CLI 不内置排版引擎；
#   ⑧ 摘要：模块 9 个、检索条文 N 处、AI 是否启用，全部照后端返回值打印，不四舍五入。
#
# 【进程边界】analyze 与 report 默认是两次独立进程：状态文件负责「输入与配置」，
#   cli-运行.pkl 负责「引擎原始结果」，两者必须成对（report 会校验 runId 一致）。
#
# 【三个「不」】
#   · 不覆盖界面数据：状态文件固定是 数据/cli-状态.json，界面用的是 数据/状态.json；
#   · 不二次取整：金额只做「元 → 整数分」的格式化搬运，绝不在 CLI 里算业务数；
#   · 不冒充生成：AI 未启用时报告里就是占位文案，CLI 不会替模型编解读。
#
# 【报告格式矩阵】md 必有 ｜ html 由 md 派生 ｜ json 权威来自后端 zucheng_json，
#   缺失时才由 CLI 从 md 提取并在 JSON 里写 fallback 说明 ｜ pdf 依赖本机浏览器。
#
# 【失败口径】业务失败 exit 1（中文原因 stderr）｜参数错误 exit 2｜意外异常打出完整栈，
#   绝不把异常吞成「成功」——用户要能一眼定位是哪一本工作簿、哪一项参数出的问题。


# ======================================================================
# 一、路径与常量（全部相对本文件反推，安装到任意目录都能跑）
# ======================================================================

BEN_MU = Path(__file__).resolve().parent          # <插件根>/backend（本文件所在目录）
PLUGIN_MU = BEN_MU.parent                         # <插件根>（backend 的上一级）
SHUJU_MU = PLUGIN_MU / '数据'                      # 运行时数据目录（安装目录下可写）
ZT_LU = SHUJU_MU / 'cli-状态.json'                 # CLI 独立状态（绝不碰 UI 的 状态.json）
YUNXING_LU = SHUJU_MU / 'cli-运行.pkl'             # 最近一次 analyze 的原始结果（跨进程复用）
SHUCHU_MU = SHUJU_MU / 'cli-输出'                  # 默认输出目录（--out 可覆盖）
LINSHI_MU = SHUJU_MU / '临时'                      # CLI 自己的临时目录（禁写 C 盘）
FUWU_LU = PLUGIN_MU / 'adapter' / '独立服务.mjs'    # serve 用的 Node 服务入口

# ----------------------------------------------------------------------
# 常量口径（改这里的值等于改对外契约，务必同步文档与测试）
# ----------------------------------------------------------------------
# · BANBEN 唯一来源是插件包 package.json：CLI 不写死版本号，打包换版本自动跟随；
#   读不到（安装不完整）才回退内置 1.1.5，避免「打印版本就崩」。
# · SHIXING 是「信封协议号」：程序侧按它判断能不能解析；字段语义变了就换号，
#   不要偷偷加字段让老调用方误判。
# · BAO_GAO_SHIXING 与规范第四节一致（hengce.report/1），必须和后端 zucheng_json 同值。
# · AI_NOTICE 是统一 AI 标注文案，规范第三节要求一字不改（合规用，不美化）。
# · LIULANQI 顺序：Chrome 在前——Edge 的 headless 打印对中文与分页更挑剔，
#   有 Chrome 优先用 Chrome；两者都没有时 PDF 降级跳过并在 stderr 告警。
# · ZHONG_WEN 只覆盖报告里会出现的 1-19（模块一…模块九、第十…），超范围返回 0 表示
#   「识别不了」，让上层按顺序号兜底，不猜。

def _du_banben():
    """插件包版本（package.json）；读不到就用 CLI 内置兜底版本，绝不猜。"""
    try:
        bao = json.loads((PLUGIN_MU / 'package.json').read_text(encoding='utf-8'))
        return str(bao.get('version') or '1.1.5')
    except (OSError, ValueError):
        return '1.1.5'


BANBEN = _du_banben()                             # CLI 版本跟随插件包（单一来源）
SHIXING = 'hengce.cli/1'                          # JSON 信封协议号（升级口径就换号）
BAO_GAO_SHIXING = 'hengce.report/1'               # 报告 JSON 协议号（与规范第四节一致）
AI_NOTICE = '内容为AI生成，仅供参考'                # AI 标注统一文案（一字不改）
DUAN_KOU = 4180                                   # serve 默认端口（与程序内嵌服务一致）

#: 退出码 → 中文含义（回报与文档都用这套口径）

# 退出码是 CLI 与调用方之间最硬的契约，写死在常量表里并同时印进 --help：
#   0 = 成功（含「可选项有缺项但已降级」的 doctor）
#   1 = 业务失败（校验不通过、后端抛错、状态不一致…，报错正文在 stderr）
#   2 = 参数错误（子命令/选项写错，改命令即可）
# 脚本判断成功只看退出码，不要解析中文文案。

TUI_CHU = {0: '成功', 1: '业务失败', 2: '参数错误'}

#: Chrome/Edge 候选：PDF 由本机浏览器 headless 打印，CLI 不内置排版引擎。
#: 与后端 LIULANQI 同值——doctor 在后端载入失败时也要能检查浏览器。

# 浏览器候选路径必须与 桥接入口.py、跑衡策全流程.py 保持一致：
# 三处各存一份是既有事实（避免 CLI 反向依赖后端常量），改一处要同步另两处。

LIULANQI = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')

#: 中文数字（模块序号解析用；报告里是「模块一…模块九」）

# 中文数字只用于解析报告标题（模块一…模块九），覆盖到十九即可：
# 未来模块数变多由「按出现顺序编号」兜底，不需要无限扩张这张表。

ZHONG_WEN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
             '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}


# ======================================================================
# 二、异常：业务失败(1) / 参数错误(2) 分开，中文信息可定位
# ======================================================================

# 异常分两层，是为了让调用方（脚本 / AI）不看文本也能判断该不该重试：
#   · CuoWu(1)：环境或数据不对（缺依赖、工作簿不合契约、状态脏、密钥缺）——重试无用，
#     要人去改输入或环境；
#   · CanShuCuoWu(2)：命令行写法不对（选项取值、缺参数）——改命令即可，程序没问题。
# 后端的 RuntimeError 由主入口单独映射为 1 并在信封里标 source=后端，避免把
# 「后端契约校验失败」误报成 CLI 自身错误（排障时要能分清是谁拒的）。
# 主入口统一兜底：不捕获 BaseException，Ctrl+C 单独处理（用户主动中断不算失败原因）。

class CuoWu(Exception):
    """业务失败：中文原因写 stderr，退出码 1（输入不对、状态不对、环境缺件等）。"""

    ma = 1                                   # 默认退出码：业务失败



# 继承 CuoWu 但只改退出码：上层按 `except CuoWu` 统一处理、按 e.ma 决定退出码，
# 不必写两套异常分支（少一处漏处理的机会）。

class CanShuCuoWu(CuoWu):
    """参数错误：用法/取值不对，退出码 2（与业务失败区分，便于脚本判断）。"""

    ma = 2


# 翻译表覆盖 argparse 最常见的四类报错：无法识别参数、缺必需参数、单个参数取值错、
# 枚举取值不在候选里。翻不动的保留原文并加「参数错误：」前缀——宁可中英混排，
# 也不要把真实原因丢掉（那会让用户无从搜索）。

def _fan_yi_wen_ti(miao):
    """把 argparse 的英文报错翻成中文；翻不动的保留原文并加中文前缀（仍可定位）。"""
    ju = (miao or '').strip()
    if ju.startswith('unrecognized arguments:'):
        return '无法识别的参数：' + ju.split(':', 1)[1].strip()
    m = re.match(r'^the following arguments are required: (.+)$', ju)
    if m:
        return '缺少必需参数：' + m.group(1)
    m = re.match(r'^argument (--?[\w-]+): (.*)$', ju)
    if m:
        can, shuoming = m.group(1), m.group(2)
        shuoming = shuoming.replace('invalid choice', '取值无效')
        shuoming = shuoming.replace('expected one argument', '缺少取值')
        return f'参数 {can}：{shuoming}'
    if 'invalid choice' in ju:               # 兜底：选项取值不在枚举里
        return ju.replace('invalid choice', '取值无效')
    return '参数错误：' + ju


# argparse 的英文报错统一在这里翻中文：子类化后 error() 抛 CanShuCuoWu(2)，
# 于是「参数不对」永远是退出码 2，且信息一定中文——脚本侧可据此区分「该改命令」
# 还是「该改数据」。不覆盖 exit()：正常路径我们从不调用它，保持单一路径。

class HengCeParser(argparse.ArgumentParser):
    """参数解析器：argparse 的英文报错统一翻成中文并抛参数错误（退出码 2）。"""

    def error(self, message):
        raise CanShuCuoWu(_fan_yi_wen_ti(message))


# ======================================================================
# 三、运行上下文：输出分流、阶段计时、真实 stdout 句柄
# ======================================================================

# 三通道约定（--json 场景尤其重要）：
#   · stdout：结果正文（非 --json），或唯一一个 JSON 信封（--json）——程序只读这里；
#   · stderr：进度、阶段耗时、警告、错误——人看不污染机器；
#   · zhen_stdout：进入 --json 前把真 stdout 存下来，最后信封直接写它，
#     因为工作期 sys.stdout 已被指向 stderr（见 _biao_zhuan），避免任何 print 掉进信封。
# --quiet 只压「进度」，不压「错误与警告」：脚本调用要安静，但出错必须能看见。
# 阶段计时（jieduan）写入 jieduan_lu，最后进信封 stages 字段，便于定位是哪一步慢。

class Yunxing:
    """一次命令运行的上下文（输出开关 + 计时 + 真实 stdout 句柄）。

    · shuo()   进度/提示 → stderr（--quiet 时静默）；--json 时也走 stderr，绝不污染 stdout；
    · shuchu() 结果正文 → 非 --json 走 stdout（给人看、可重定向），--json 走 stderr；
    · zhen_stdout 永远指向真正的 stdout，供最后写 JSON 信封。
    """

    def __init__(self, json_mode=False, quiet=False, out=None):
        self.json = bool(json_mode)               # --json：stdout 只留一个 JSON 信封
        self.quiet = bool(quiet)                  # --quiet：不打印进度（错误照旧）
        self.out = out                            # --out 覆盖输出目录（可以是 None）
        self.mingling = ''                        # 当前子命令名（写进 JSON 信封）
        self.zhen_stdout = sys.stdout             # 真身句柄（--json 期间 sys.stdout 会被改）
        self.kaishi = time.perf_counter()         # 总计时（信封 elapsedMs）
        self.jieduan_lu = []                      # 阶段耗时清单（信封 stages 字段）

    def shuo(self, wen):
        """进度/提示一行 → stderr。--quiet 时静默：脚本调用不想要噪声。"""
        if not self.quiet:
            print(wen, file=sys.stderr, flush=True)

    def shuchu(self, wen):
        """结果正文一行：非 --json 走 stdout；--json 时改走 stderr（保住 stdout 纯净）。"""
        if self.json:
            print(wen, file=sys.stderr, flush=True)
        else:
            print(wen, flush=True)

    def haoshi_ms(self):
        """本次命令已经跑掉多少毫秒（整数，写进信封）。"""
        return int((time.perf_counter() - self.kaishi) * 1000)


@contextlib.contextmanager

# 阶段行格式固定为「▸ 标题 …」→「✔/✘ 标题（秒）」：
# 便于人眼扫、也便于日志被脚本按前缀抓取；失败打 ✘ 而不是沉默（不掩盖问题）。
# 计时写进 jieduan_lu（四舍五入到 0.01 秒），最终进 JSON 信封的 stages。

def jieduan(yun, biaoti):
    """阶段计时：进入打一行标题，结束打「✔/✘ 标题（秒）」。

    规范第七节要求长步骤进度可见——导入、分析、报告、PDF 都包在这里，
    失败时打 ✘ 而不是假装完成（不掩盖问题）。
    """
    yun.shuo(f'▸ {biaoti} …')
    qi = time.perf_counter()
    ok = False
    try:
        yield
        ok = True
    finally:
        hao = time.perf_counter() - qi
        yun.jieduan_lu.append({'stage': biaoti, 'seconds': round(hao, 2)})
        yun.shuo(f'  {"✔" if ok else "✘"} {biaoti}（{hao:.2f} 秒）')


@contextlib.contextmanager

# 上下文管理器而非全局替换：退出时一定恢复 sys.stdout（含异常路径），
# 否则出错后信封会写进 stderr、用户看不到 JSON。flush 两次是为了让缓冲期
# 残留的输出不会串到信封后面。

def _biao_zhuan(yun):
    """--json 期间把 sys.stdout 指向 stderr：任何意外打印都不会破坏 JSON 信封。"""
    if not yun.json:
        yield
        return
    zhen = sys.stdout
    try:
        sys.stdout.flush()
        sys.stdout = sys.stderr
        yield
    finally:
        try:
            sys.stdout.flush()
        except Exception:                     # noqa: BLE001 关闭期刷洗失败不该影响结果
            pass
        sys.stdout = zhen



# 信封与报告 JSON 的 generatedAt 都用本地时区 ISO 8601（秒精度）：
# 不要用 UTC——用户在国内看报告，抬头写 03:00 会让人误以为跑错了时段。

def _xianzai():
    """当前时刻 ISO 8601（带本地时区，秒精度）——信封与 JSON 报告的 generatedAt。"""
    return datetime.now().astimezone().isoformat(timespec='seconds')


# 信封统一在这里落笔：indent=2 + 末尾换行，既方便人眼核对，也让 diff 稳定；
# ensure_ascii=False 保证中文原样输出（程序侧 json.loads 与编码无关）。

def _xie_json(liu, bao):
    """往真正的 stdout 写一个 JSON 信封（UTF-8 中文不转义，程序侧可直接解析）。"""
    liu.write(json.dumps(bao, ensure_ascii=False, indent=2) + '\n')
    liu.flush()



# 信封字段刻意保持少而稳：schema / ok / command / elapsedMs / generatedAt /
# stages / data|error。加字段可以，改语义要换 SHIXING 号——调用方按号兼容。

def _feng_bao(yun, ok, shuju=None, cuowu=None):
    """组装 JSON 信封：状态、命令名、耗时、阶段、数据或错误，一次给全。"""
    bao = {'schema': SHIXING, 'ok': bool(ok), 'command': yun.mingling,
           'elapsedMs': yun.haoshi_ms(), 'generatedAt': _xianzai(),
           'stages': yun.jieduan_lu}
    if shuju is not None:
        bao['data'] = shuju
    if cuowu:
        bao['error'] = cuowu
    return bao


# ======================================================================
# 四、后端载入：复用动作表 DONGZUO，但把状态文件重定向到 CLI 自己的一份
# ======================================================================

_BEIJING = {}                            # 进程内缓存：{'q': 桥接入口模块, 'zt': 状态}


# ----------------------------------------------------------------------
# 载入后端的三条硬约束（任何一条不满足都直接中文报错，不做「尽力而为」）
# ----------------------------------------------------------------------
#   ① 必须有 __main__ 保护：桥接入口的 main 会阻塞读 stdin（它是给桌面程序做 RPC 的），
#      import 一个没有保护的模块等于让 CLI 卡死在等输入；用 ast 静态检查而不是字符串
#      匹配，是因为注释里出现该字样不该被当成保护；
#   ② 必须有动作表 DONGZUO 且含 files.import：导入是整条链的入口，没有它无法确定
#      契约校验走哪套实现（不同版本后端接口不同）；
#   ③ 状态文件必须重定向：先改 q.ZHUANGTAI_LU 再读，顺序反了就会先读界面的 状态.json
#      （哪怕随后不写，读到的 currentRunId 也会和 CLI 自己那份对不上）。
#
# 重定向之后，本进程里任何后端代码写状态都落到 cli-状态.json：
#   · files.import → dirty=True（输入变了，之前的分析作废）
#   · analysis.run → dirty=False + currentRunId 更新
#   · report 只读状态不写（报告文件落 --out，不登记进界面报告历史）
#
# _BEIJING 是进程内缓存：一次命令里 import/analyze/report 反复要后端对象，
# 只载一次（约 0.05-0.07 秒）；进程结束即失效，不存在跨命令的陈旧状态问题。

def _you_zhu_baohu(wenjian):
    """用 ast 判断模块顶层是否有 `if __name__ == '__main__':`（比字符串匹配稳）。

    CLI 会 import 桥接入口；若它没有这个保护，import 会直接启动读 stdin 的主循环，
    CLI 就会卡死等输入。这里先做静态检查，没有保护就如实拒绝并给出替代方案。
    """
    try:
        shu = ast.parse(Path(wenjian).read_text(encoding='utf-8'))
    except (OSError, SyntaxError):
        return False
    for jie in shu.body:
        if not isinstance(jie, ast.If):
            continue
        ce = jie.test
        if not isinstance(ce, ast.Compare) or len(ce.comparators) != 1:
            continue
        zuo, you = ce.left, ce.comparators[0]

        def ming(x):                       # 取 Name.id 或 Constant.value，其它给 None
            if isinstance(x, ast.Name):
                return x.id
            if isinstance(x, ast.Constant):
                return x.value
            return None

        if ming(zuo) == '__name__' and ming(you) == '__main__':
            return True
    return False



# 载入失败的三类原因分开报：①模块导入异常（缺依赖/文件不完整）；②无 __main__ 保护
# （会启动 stdin 循环）；③动作表缺项（版本不匹配）。分开写是为了让用户一次就知道
# 该补文件、该换版本，还是该找开发支持，而不是一句「加载失败」。

def houduan(yun):
    """载入后端桥接入口（进程内只载一次），并把状态文件重定向到 CLI 独立状态。

    为什么要走 DONGZUO：它是 UI 与独立服务唯一的动作表，import/analyze 用同一套
    处理函数，行为才和界面完全一致（换一条实现等于埋一个分叉）。
    为什么要重定向：桥接入口默认读写 <插件根>/数据/状态.json——那是用户界面的
    工作区，CLI 直接复用会把用户正在看的数据覆盖掉，所以先改 ZHUANGTAI_LU，
    再读自己的 cli-状态.json。
    """
    if 'q' in _BEIJING:
        return _BEIJING['q'], _BEIJING['zt']
    if str(BEN_MU) not in sys.path:            # backend 根入路径，才能 import 桥接入口
        sys.path.insert(0, str(BEN_MU))
    yun.shuo('▸ 载入后端（桥接入口）…')
    qi = time.perf_counter()
    try:
        q = importlib.import_module('桥接入口')
    except Exception as e:                     # noqa: BLE001 载入失败要把原始原因给用户
        raise CuoWu(f'载入桥接入口失败：{type(e).__name__}: {e}'
                    f'（请确认 backend 目录完整、依赖已装：{BEN_MU}）')
    if not _you_zhu_baohu(Path(q.__file__)):
        raise CuoWu('桥接入口.py 缺少 `if __name__ == "__main__":` 保护：'
                    'CLI 不能安全 import 它（会启动标准输入循环）。'
                    '替代方案：直接调用 import_excel_v11 / yinqing.fenxi / compute_report_pipeline')
    dong = getattr(q, 'DONGZUO', None)
    if not isinstance(dong, dict) or 'files.import' not in dong:
        raise CuoWu('桥接入口.py 没有可用的动作表 DONGZUO（版本不匹配？）：'
                    '无法确定导入/分析接口，请核对插件 backend 是否为 1.1.5 及以后')
    q.ZHUANGTAI_LU = ZT_LU                     # 关键一行：状态落到 CLI 专文件
    try:
        zt = q.du_zhuangtai()
    except Exception as e:                     # noqa: BLE001
        raise CuoWu(f'读取 CLI 状态文件失败：{ZT_LU}（{e}）')
    q._ZT = zt                                 # 后端若直接用 _ZT，也指向同一份 CLI 状态
    _BEIJING['q'], _BEIJING['zt'] = q, zt
    yun.shuo(f'  ✔ 后端载入（动作 {len(dong)} 个，{time.perf_counter() - qi:.2f} 秒）')
    return q, zt



# 为什么要显式落盘：后端动作函数只改内存里的状态字典，真正写文件的是桌面程序的
# 标准输入主循环（_huifu）。CLI 直调 DONGZUO 后不写，下一条命令就看不到本次导入/分析。

def cun_zt(q):
    """把状态落盘。动作处理函数本身不落盘（只有标准输入主循环会落盘），
    CLI 直调 DONGZUO 之后必须显式调用，否则下一条命令看不到本次结果。"""
    try:
        q.xie_zhuangtai()                      # 后端负责原子写（.tmp → replace）
    except Exception as e:                     # noqa: BLE001
        raise CuoWu(f'写 CLI 状态文件失败：{ZT_LU}（{e}）；请检查 <插件根>/数据 目录权限')


# ======================================================================
# 五、小工具：参数校验、种子/期间推导、JSON 报告兜底提取
# ======================================================================

# ----------------------------------------------------------------------
# 参数校验统一手写（不用 argparse 的 type=），原因有两个：
# ----------------------------------------------------------------------
#   · 英文报错对用户不友好，这里全部给中文可定位提示（规范：报错必须中文且能定位）；
#   · 校验失败要能区分「参数错误(2)」与「业务失败(1)」——argparse 的 type 抛的是
#     ArgumentTypeError，最终都会被翻成 2，反而分不清是谁的问题。
# 校验口径速查：
#   --cycle   月度 / 季度（引擎只实现这两种粒度，其它值没有对应汇总口径）
#   --period  YYYY-MM 或 YYYY-Q1…Q4（拒绝 2027-6、2027/06 这类变体，避免歧义）
#   --growth  整数基点，上限 ±100000（=±1000%，再大一定是手滑），缺省 0
#   --port    1-65535 整数（先校验再用 socket，避免抛英文 OSError）
#   --format  逗号分隔 md/html/pdf/json，大小写与空格容错；空值报错而不是默认
#   --xlsx    至少一本；后缀必须是 .xlsx（四类模板都是 xlsx，不收 csv/pdf/旧 xls）

def _jie_zhouqi(wen):
    """--cycle：只认「月度」「季度」（引擎按粒度汇总，其它值没有对应口径）。"""
    zq = (wen or '').strip()
    if not zq:
        return None
    if zq not in ('月度', '季度'):
        raise CanShuCuoWu(f'--cycle 取值无效：{zq}（只支持 月度 / 季度）')
    return zq



# 期间只校验「形状」，不校验「合理性」：2027-06 是不是未来期间、是不是已结账，
# 由分析引擎与锁止规则判断（CLI 不该替业务口径拍板）；这里只挡住明显写错的输入。

def _jie_qijian(wen):
    """--period：YYYY-MM（如 2027-06）或 YYYY-Q1…Q4（季度）；格式不对中文报错。"""
    qj = (wen or '').strip()
    if not qj:
        return None
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2]|Q[1-4])', qj):
        raise CanShuCuoWu(f'--period 格式应为 YYYY-MM（如 2027-06）或 YYYY-Q1…Q4，收到 {qj!r}')
    return qj



# 增长率用百分数输入（--growth 5 表示 5%），在这里统一折成整数基点（+500）传给引擎：
# 引擎内部只认整数基点，浮点在跨模块传参会丢精度；±100000（即 ±1000%）只是挡住明显
# 手滑的量级，不是业务上限——真实上限由引擎的指标口径决定。

def _jie_zengzhang(wen):
    """--growth：基点整数（正数上调、负数下调）。界定范围防手滑写出天文数字。"""
    if wen is None:
        return None
    try:
        zhi = int(str(wen).strip())
    except (TypeError, ValueError):
        raise CanShuCuoWu(f'--growth 需要整数基点（如 0 / 50 / -120），收到 {wen!r}')
    if abs(zhi) > 100000:                      # 100000 基点 = 1000%，再大必是输入错误
        raise CanShuCuoWu(f'--growth 绝对值过大（上限 100000 基点 = 1000%）：{zhi}')
    return zhi



# 端口先在这里校验再用：socket 层抛的是英文 OSError，用户看不懂；
# 范围检查（1-65535）也能挡住「--port 70000」这类明显手滑。

def _jie_duankou(wen):
    """--port：1-65535 整数；用中文自校验，避免 argparse 的英文整数报错。"""
    try:
        duan = int(str(wen).strip())
    except (TypeError, ValueError):
        raise CanShuCuoWu(f'--port 需要整数端口（如 4180），收到 {wen!r}')
    if not 1 <= duan <= 65535:
        raise CanShuCuoWu(f'--port 超出范围（1-65535）：{duan}')
    return duan



# 格式列表做小写归一与去空格（--format "MD, HTML" 也能用），但空值必须报错：
# 静默回退默认格式会让「我要 json 却没生成」变成难查的问题。

def _jie_geshi(wen):
    """--format：逗号分隔，只认 md/html/pdf/json；大小写与空格容错，空值报错。"""
    yao = [x.strip().lower() for x in (wen or '').split(',') if x.strip()]
    he = {'md', 'html', 'pdf', 'json'}
    cuo = [x for x in yao if x not in he]
    if cuo:
        raise CanShuCuoWu(f'--format 取值无效：{"、".join(cuo)}'
                          f'（只支持 md、html、pdf、json，逗号分隔）')
    if not yao:
        raise CanShuCuoWu('--format 不能为空：请给 md / html / pdf / json 之一或多个')
    return yao


# ----------------------------------------------------------------------
# 种子与期间的推导规则（都只影响「标注」与「默认值」，不参与业务计算）
# ----------------------------------------------------------------------
#   · 种子：演示件文件名形如 演示-预算基础-20261025.xlsx，末尾 6 位以上数字即种子。
#     它写进报告抬头「数据口径 演示件（种子 …）」，用来证明「这组数是可复现的演示数据」；
#     真实业务文件没有种子 → 返回空串 → 报告不写种子行，绝不编造。
#   · 期间：优先取工作簿元字段「已结账截至」（2027-06-30 → 2027-06，只取到月），
#     其次「生效周期」；都推不出就要求用户显式 --period，不猜一个期间糊过去。
#   · all 不给 --xlsx 时用的默认演示件必须是同种子的一对：预算基础与实时经营
#     混配不同种子会导致差异分析对不上账。

def _tui_zhong(zt):
    """从演示件文件名推种子：演示-预算基础-20261025.xlsx → '20261025'。

    种子只影响报告抬头的「数据口径」标注；真实业务文件没有种子，返回空串，
    报告就不写「种子 …」——不冒充、不编造。
    """
    for wenjian in zt.get('files') or []:
        if wenjian.get('category') != '预算基础':
            continue
        gen = Path(wenjian.get('name') or '').stem      # 去掉扩展名
        gen = re.sub(r'（[^）]*）$', '', gen)             # 去「（某部门）」后缀
        m = re.search(r'-(\d{6,})$', gen)
        if m:
            return m.group(1)
    return ''



# 默认期间与 跑衡策全流程.py 同口径：演示件的「实时经营」带已结账截至元字段，
# 取它所在月；真实工作簿若没这两个字段，就让用户显式 --period，不猜期间。

def _moren_qijian(zt):
    """期间默认值：已结账截至优先（月度取前 7 位），其次生效周期；推不出返回空串。

    与 跑衡策全流程.py 同口径：演示件「实时经营」带已结账截至，分析期间取它。
    """
    for wenjian in zt.get('files') or []:
        md = wenjian.get('metadata') or {}
        for jian in ('已结账截至', '生效周期'):
            zhi = str(md.get(jian) or '').strip()
            if not zhi:
                continue
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', zhi):   # 2027-06-30 → 2027-06
                return zhi[:7]
            if re.fullmatch(r'\d{4}-\d{2}', zhi):
                return zhi
    return ''



# 单位换算只服务于「md 兜底提取」：md 里金额是「2,846,489.66」（元），
# 换算成整数分用 decimal 走 ROUND_HALF_UP，避免 float 累加误差；
# 带 % 或「—」等占位符一律给 None——宁可缺字段也不把占位符当 0。

def _zhuan_fen(wen):
    """「2,846,489.66」（元）→ 284648966 分（整数）；带 % 或不可解析给 None（不强转）。"""
    s = (wen or '').replace(',', '').strip()
    if not s or s.endswith('%') or s in ('—', '-', '无'):
        return None
    try:
        shi = decimal.Decimal(s)
    except decimal.InvalidOperation:
        return None
    return int((shi * 100).to_integral_value(rounding=decimal.ROUND_HALF_UP))



# 「-1.64%」→ -164 基点（1 基点 = 0.01%）。只认带 % 的字符串：
# 项数、天数这类非比率数值不该被误当基点，所以不是百分比一律 None。

def _zhuan_bps(wen):
    """「-1.64%」→ -164 基点（整数）；不是百分比就给 None（不强转）。"""
    s = (wen or '').replace(',', '').strip()
    if not s.endswith('%'):
        return None
    try:
        shi = decimal.Decimal(s[:-1])
    except decimal.InvalidOperation:
        return None
    return int((shi * 100).to_integral_value(rounding=decimal.ROUND_HALF_UP))



# 报告里模块序号是中文（模块一…模块九，未来可能到十/十一），这里支持 1-19；
# 识别不了返回 0，调用方随后会退回「按出现顺序编号」，不抛异常中断报告解析。

def _zhong_wen_shu(wen):
    """「九」→ 9（支持 1-19 的常用写法；识别不了给 0，不猜）。"""
    s = (wen or '').strip()
    if not s:
        return 0
    if s == '十':
        return 10
    if '十' in s:
        qian, _, hou = s.partition('十')
        return (ZHONG_WEN.get(qian, 1) if qian else 1) * 10 + (ZHONG_WEN.get(hou, 0) if hou else 0)
    return ZHONG_WEN.get(s, 0)


# ----------------------------------------------------------------------
# 兜底 JSON 的三段解析（只在后端没有结构化输出时才走，代码要能自证可信）
# ----------------------------------------------------------------------
#   ① 总览表：markdown 表格 → items[{item, valueText, valueFen, valueBps}]；
#      金额/比率在 md 里已排版成「元 / 百分比」，所以同时给原文与换算值，
#      换算失败给 None——宁可缺字段也不强行 round 出一个假数字；
#   ② 九模块：按「## 模块X · 名称」切段，段内按 **数据表** / **分析内容** / **依据条例**
#      三段收集；表格只保留通用结构（表头 + 行 + 行数），不同模块列含义不同，
#      统一强转语义会失真，因此不做列级解释；
#   ③ 依据与整改：条文正文来自 kb2 检索原文，整段照搬（不摘要、不改写）；
#      整改条目同时兼容「（占位）未回填」与「建议：… 已回填」两种形状，
#      并用 aiGenerated 标记是否真的由模型生成，避免占位文案被当成 AI 结论。
# 兜底产出必须带 fallback 字段：写明来源、原因、数值口径与提取函数，
# 让读到 JSON 的程序能判断「这份结构是权威的还是从排版文本反推的」。

def _biao(md_hang):
    """解析一段 markdown 表格 → {'header': [...], 'rows': [[...]], 'rowCount': n}。

    只认以 | 开头的连续行；跳过 |---| 分隔行；单元格去首尾空白。
    没有表格返回 None（不同模块表结构不同，这里只做通用搬运）。
    """
    hang = [x.strip() for x in md_hang if x.strip().startswith('|')]
    if not hang:
        return None

    def fen(x):
        return [c.strip() for c in x.strip().strip('|').split('|')]

    head = fen(hang[0])
    rows = []
    for x in hang[1:]:
        cells = fen(x)
        if all(re.fullmatch(r':?-{1,}:?', c) for c in cells):   # |---| 分隔行
            continue
        rows.append(cells)
    return {'header': head, 'rows': rows, 'rowCount': len(rows)}



# 条文块形状：**出处 N：《管理会计应用指引第201号——滚动预算》第十三条**（定位 201-13 ｜ 检索提示词：…）
# 后面空一行接检索原文。这里只做「结构解析」：把标题、定位、提示词、正文分开，
# 正文一个字都不改——它不是模型写的，是检索库原文，改写就等于伪造引用。

def _yao_tiaoli(md_hang):
    """解析「**出处 N：《…》第X条**（定位 … ｜ 检索提示词：…）」块 → 引用清单。

    条文正文来自检索库真文本（不是模型生成），所以整段照搬、不改写；
    解析不到就留空串，绝不补写条文。
    """
    chu = []
    dangqian = None
    for x in md_hang:
        s = x.strip()
        m = re.match(r'^\*\*出处\s*\d+：(.+?)\*\*（(.*?)）\s*$', s)
        if m:
            dangqian = {'no': len(chu) + 1, 'title': m.group(1).strip(),
                        'source': 'kb2 检索原文', 'locate': '', 'prompt': '', 'text': ''}
            can = m.group(2)
            mm = re.search(r'定位\s*([^｜|]+)', can)
            if mm:
                dangqian['locate'] = mm.group(1).strip()
            mp = re.search(r'检索提示词：(.+)$', can)
            if mp:
                dangqian['prompt'] = mp.group(1).strip()
            chu.append(dangqian)
            continue
        if dangqian is not None and s and not s.startswith('**依据'):
            dangqian['text'] = (dangqian['text'] + ('\n' if dangqian['text'] else '') + s)
    return chu



# 整改条目的两种形状都要认（决定 JSON 里 aiGenerated 是否可信）：
#   · 未回填：**3. [关注整改｜收入模块]（占位）** 描述——待 DSH 宿主 agent 回填。
#   · 已回填：**3. [关注整改｜收入模块]** 描述 + 空行 + 「建议：…」
# placeholder 字段保留占位标记，宁可让程序看到「这条是占位」，也不粉饰成 AI 结论。

def _yao_zhenggai(md_hang):
    """解析「逐条整改建议」条目。

    两种形状都要认：
      · 未回填：**3. [关注整改｜收入模块]（占位）** 2027-06 营业收入 差额 …——待…回填。
      · 已回填：**3. [关注整改｜收入模块]** 2027-06 营业收入 差额 …  + 空行 + 「建议：…」
    """
    qing = []
    dangqian = None
    for x in md_hang:
        s = x.strip()
        m = re.match(r'^\*\*(\d{1,4})\.\s*\[([^｜\]]+)｜([^\]]+)\]\s*(（占位）)?\*\*\s*(.*)$', s)
        if m:
            dangqian = {'no': int(m.group(1)), 'type': m.group(2).strip(),
                        'owner': m.group(3).strip(), 'desc': m.group(5).strip(),
                        'suggestion': None, 'aiGenerated': False,
                        'placeholder': bool(m.group(4))}
            qing.append(dangqian)
            continue
        if dangqian is not None and s:
            if s.startswith('建议：'):
                dangqian['suggestion'] = s.split('：', 1)[1].strip()
                dangqian['aiGenerated'] = True
            else:
                dangqian['desc'] = (dangqian['desc'] + ' ' + s).strip()
    return qing



# 这是最后一条路（后端结构化输出没有、或 --ai 让旧 JSON 过期时才用）：
#   1) 抬头：一级标题里的「（主体 · 期间）」+ 引用行「> 主体 X｜情景 Y｜…」；
#   2) 总览表 → items[{item, valueText, valueFen, valueBps}]（换算失败给 None）；
#   3) 九模块 → table（通用表格结构）+ analysis（原文本）+ citations（条文原文）；
#   4) AI 解读 → conclusion + actions[{no,type,owner,desc,suggestion}]；
#   5) 预警分布从总体解读里正则提取，提不到就不写（不编预警数）。
# 幂等：同一份 md 反复提取得到同一份 JSON（时间戳是唯一变量）。

def _cong_md_ti_json(md_lu, json_lu, yao_ai=False):
    """兜底：从计算报告 md 提取结构化 JSON（后端还没有结构化输出时用）。

    诚实边界（必须写进产出里）：
      · md 里金额已排版成「元」、比率已排版成「百分比」，因此总览表同时给
        valueText（原文）、valueFen（换算成整数分，能换算才给）、valueBps（换算成
        整数基点，能换算才给）；九模块数据表列结构各不相同，只保留原文文本，
        强转会失真；
      · 条文正文是检索原文照搬，不是生成内容；
      · JSON 里带 fallback 字段说明来源与换算口径，程序侧据此判断可用性。
    """
    md_lu = Path(md_lu)
    wen = md_lu.read_text(encoding='utf-8')
    hang = wen.splitlines()

    # ---- 抬头：一级标题「（主体 · 期间）」+ 口径行「> 主体 X｜情景 Y｜…」----
    biaoti = hang[0].lstrip('#').strip() if hang else ''
    m = re.match(r'^(.+?)（(.+?)\s*·\s*(.+?)）\s*$', biaoti)
    gongsi = m.group(2).strip() if m else ''
    qijian = m.group(3).strip() if m else ''
    kou = next((x[1:].strip() for x in hang if x.startswith('> ')), '')
    xinxi = {}
    for kuai in kou.split('｜'):
        kuai = kuai.strip()
        if ' ' in kuai:
            k, v = kuai.split(' ', 1)
            xinxi[k] = v.strip()
    zhong = ''
    m = re.search(r'种子\s*([0-9A-Za-z_-]+)', xinxi.get('数据口径', ''))
    if m:
        zhong = m.group(1)

    # ---- 按二级标题切段（模块/AI 解读各自成段）----
    duan = []
    dang = None
    for x in hang:
        if x.startswith('## '):
            dang = {'title': x[3:].strip(), 'lines': []}
            duan.append(dang)
        elif x.startswith('# '):                # 一级标题只出现在抬头，结束当前段
            dang = None
        elif dang is not None:
            dang['lines'].append(x)

    # ---- 总览：表格转结构化，同时给换算后的整数分/基点 ----
    zong = {'title': '总览', 'items': [], 'note': ''}
    for du in duan:
        if du['title'] != '总览':
            continue
        biao = _biao(du['lines'])
        if biao:
            for row in biao['rows']:
                if len(row) >= 2:
                    zong['items'].append({'item': row[0], 'valueText': row[1],
                                          'valueFen': _zhuan_fen(row[1]),
                                          'valueBps': _zhuan_bps(row[1])})
        zong['note'] = next((x.strip() for x in du['lines']
                             if x.strip() and not x.strip().startswith('|')), '')
        break

    # ---- 九模块：数据表 + 分析内容 + 依据条例 ----
    mokuai = []
    for du in duan:
        if not du['title'].startswith('模块'):
            continue
        m = re.match(r'^模块([一二三四五六七八九十]+)', du['title'])
        ming = du['title'].split('·', 1)[-1].strip() if '·' in du['title'] else du['title']
        zi = {'数据表': [], '分析内容': [], '依据': []}
        dangqian = None
        for x in du['lines']:
            if x.strip() == '**数据表**':
                dangqian = '数据表'
                continue
            if x.strip() == '**分析内容**':
                dangqian = '分析内容'
                continue
            if x.strip().startswith('**依据条例'):
                dangqian = '依据'
                continue
            if dangqian:
                zi[dangqian].append(x)
        fenxi = '\n'.join(x.strip() for x in zi['分析内容'] if x.strip()).strip()
        mokuai.append({
            'no': _zhong_wen_shu(m.group(1)) if m else len(mokuai) + 1,
            'name': ming,
            'table': _biao(zi['数据表']),
            'analysis': fenxi,
            # AI 解读回填后，模块分析内容就不再是占位文案
            'aiGenerated': bool(yao_ai and 'DSH 宿主 agent 回填' not in fenxi),
            'citations': _yao_tiaoli(zi['依据']),
        })

    # ---- AI 分析解读：总体解读 + 逐条整改建议 ----
    ai = {'conclusion': '', 'actions': [], 'aiGenerated': bool(yao_ai)}
    for du in duan:
        if du['title'] != 'AI 分析解读':
            continue
        zi = {'总体解读': [], '逐条整改建议': []}
        dangqian = None
        for x in du['lines']:
            if x.strip() == '### 总体解读':
                dangqian = '总体解读'
                continue
            if x.strip() == '### 逐条整改建议':
                dangqian = '逐条整改建议'
                continue
            if dangqian:
                zi[dangqian].append(x)
        ai['conclusion'] = '\n'.join(x.strip() for x in zi['总体解读'] if x.strip()).strip()
        ai['actions'] = _yao_zhenggai(zi['逐条整改建议'])
        ai['aiGenerated'] = bool(yao_ai or '占位' not in ai['conclusion'])
        break

    # ---- 预警：从总体解读里的「预警分布 红 X / 黄 Y / 无 Z」提取，提不到就不写 ----
    jing = []
    m = re.search(r'预警分布\s*红\s*(\d+)\s*/\s*黄\s*(\d+)\s*/\s*无\s*(\d+)', ai['conclusion'])
    if m:
        jing.append(f'预警分布：红色 {m.group(1)} 项 / 黄色 {m.group(2)} 项 / 无预警 {m.group(3)} 项')
    if '占位' in ai['conclusion']:
        jing.append('AI 分析解读为确定性占位文案（未启用 --ai，不冒充模型生成）')

    bao = {
        'schema': BAO_GAO_SHIXING,
        'generatedAt': _xianzai(),
        'aiGenerated': bool(yao_ai),
        'aiNotice': AI_NOTICE,                       # 与程序内 AI 标注统一文案
        'meta': {
            'company': gongsi,
            'period': qijian,
            'scenarioName': xinxi.get('情景', ''),
            'seed': zhong,
            # 兜底口径如实写：md 是排版文本，不是整数分/基点
            'unit': '金额=元、比率=百分比（md 排版文本提取）',
        },
        'overview': zong,
        'modules': mokuai,
        'aiAnalysis': ai,
        'warnings': jing,
        'fallback': {
            'source': 'md',
            'reason': '计算报告流水线未返回结构化 JSON（后端 zucheng_json 未落地或本次启用了 --ai），'
                      '由 CLI 从最终 md 提取',
            'valueUnit': '模块表为排版文本；总览另给 valueFen/valueBps 换算值，换不出给 null',
            'extractor': '衡策CLI.py::_cong_md_ti_json',
            'md': str(md_lu),
        },
    }
    json_lu = Path(json_lu)
    json_lu.parent.mkdir(parents=True, exist_ok=True)
    json_lu.write_text(json.dumps(bao, ensure_ascii=False, indent=2), encoding='utf-8')
    return json_lu



# 三路径顺序不能乱：权威 JSON 优先，同目录同名 .json 次之，最后才从 md 提取。
# --ai 时强制走提取：AI 回填会改写 md 的分析内容与整改建议，后端那次 JSON 已过期，
# 拿它当结果等于给用户一份「没 AI 解读的 JSON + 有 AI 解读的 md」，自相矛盾。

def _sheng_json(yun, r, mu, yao_ai):
    """产出报告 JSON：优先后端权威实现，退而用 md 提取兜底。

    判断顺序（T1 的 zucheng_json 落地前后都能跑）：
      ① 流水线返回 'json' 键（规范第四节约定）→ 直接用；
      ② 与 md 同名的 .json（流水线自己写的）→ 直接用；
      ③ 都没有（或本次 --ai 改了 md 内容，旧 JSON 已过期）→ CLI 从最终 md 提取。
    返回 (json 路径, 是否走了兜底)。
    """
    if not yao_ai:
        jian = r.get('json') or ''
        if jian and Path(jian).exists():
            return Path(jian), False
        tong = Path(r['md']).with_suffix('.json')
        if tong.exists():
            return tong, False
    json_lu = Path(mu) / (Path(r['md']).stem + '.json')
    yun.shuo('  [说明] 后端未提供结构化 JSON（或已启用 --ai 使旧 JSON 过期）→ '
             '由 CLI 从 md 提取兜底，JSON 内 fallback 字段标注来源与换算口径')
    return _cong_md_ti_json(r['md'], json_lu, yao_ai), True


# ======================================================================
# 六、子命令实现（每个函数返回可 JSON 化的 dict，正文由 yun.shuchu 打印）
# ======================================================================

# ----------------------------------------------------------------------
# import：契约校验与入库
# ----------------------------------------------------------------------
# 要点：
#   · payload 一次给全批：{files:[{name, bytesB64}]}——后端先全部校验再替换状态，
#     中途失败不会留下「一半新一半旧」的工作区；
#   · 类别由后端解析内容判定（不认文件名），所以 CLI 只负责把文件读进来；
#   · 部门册会被后端展开成「公司/部门」多册，CLI 逐册打印，数目以状态为准；
#   · 落盘必须显式 cun_zt：动作函数本身不写文件（只有桌面程序的主循环写）；
#   · 成功后状态 dirty=True：提醒用户「输入变了，要重新分析」。
# 失败边界：路径不存在、后缀不是 .xlsx、契约校验不过——都原样转出后端中文原因，
# CLI 不追加猜测性解释（规范：校验失败原样转告，不臆测原因）。

def _ming_import(yun, a):
    """import 子命令：读工作簿 → 契约校验 → 八字段入库 → 落 CLI 独立状态。"""
    lu = list(getattr(a, 'xlsx', None) or [])
    if not lu:
        raise CanShuCuoWu('缺少 --xlsx：至少给一本 .xlsx 工作簿'
                          '（可重复传；预算基础与实时经营各一本）')
    wenjian = []
    for yi in lu:
        p = Path(yi).expanduser()
        if not p.exists():
            raise CuoWu(f'找不到输入工作簿：{p}（请检查路径；路径含空格时用引号包住）')
        if p.suffix.lower() != '.xlsx':
            raise CuoWu(f'{p.name}：只接受 .xlsx 工作簿'
                        f'（四类模板均为 xlsx，不接受 csv/word/pdf/旧 xls）')
        wenjian.append({'name': p.name,
                        'bytesB64': base64.b64encode(p.read_bytes()).decode('ascii')})
    q, zt = houduan(yun)
    with jieduan(yun, f'契约校验与入库（{len(wenjian)} 本工作簿）'):
        # 走 UI 同一个动作：批量先全部校验、成功后才替换，失败不留半批状态
        q.DONGZUO['files.import'](zt, {'files': wenjian})
        cun_zt(q)
    # 逐册一行（规范第七节：每完成一文件一行）；数值来自后端契约校验结果，不是估的
    for f in zt.get('files') or []:
        yun.shuchu(f'  ✔ {f.get("name")} ｜ 类别 {f.get("category")}'
                   f' ｜ 入库 {f.get("rows")} 行 ｜ 校验 {f.get("checks")} 项'
                   f' ｜ 主体 {f.get("entity") or "—"}')
    yun.shuchu(f'  当前工作区共 {len(zt.get("files") or [])} 册'
               f'（状态文件 {ZT_LU.name}，与界面 状态.json 互不影响）')
    shuju = [{'id': f.get('id'), 'name': f.get('name'), 'category': f.get('category'),
              'rows': f.get('rows'), 'checks': f.get('checks'),
              'entity': f.get('entity')} for f in zt.get('files') or []]
    return {'count': len(shuju), 'files': shuju, 'stateFile': str(ZT_LU)}


# ----------------------------------------------------------------------
# analyze：十五步分析 + 原始结果缓存
# ----------------------------------------------------------------------
# 要点：
#   · 配置基线取后端 moren_config()（与界面默认档位同源），再叠加用户显式参数；
#     不自己拼 config 字典，避免界面与 CLI 的默认值悄悄分叉；
#   · 期间优先级：--period > 工作簿元字段推导 > 报错；空期间直接报错，
#     绝不用「今天」冒充分析期间（那会让报告抬头写错月份还看不出来）；
#   · 快照计数只从后端返回的 kuai 读（rows/actions/kpis/trend/warnings），
#     CLI 不重新数一遍，否则两份数字会对不上；
#   · 原始结果 jieguo 只在后端进程内存 _RUNS[runId] 里——必须当场 pickle 落盘，
#     否则下一条 report 命令（新进程）就拿不到；
#   · 种子在分析后写进 jieguo['meta']['seed']，让报告抬头与 JSON 的 meta 一致。

def _ming_analyze(yun, a):
    """analyze 子命令：跑十五步分析，原始结果落 pickle 供 report / --ai 跨进程复用。"""
    q, zt = houduan(yun)
    if not zt.get('files'):
        raise CuoWu('还没有导入任何工作簿：请先运行 '
                    '`衡策CLI.py import --xlsx 预算基础.xlsx --xlsx 实时经营.xlsx`')
    # 配置口径与界面默认档位一致（cycle/period/growth/阈值/优先级），只覆盖用户显式给的
    cfg = q.moren_config()
    zq = _jie_zhouqi(getattr(a, 'cycle', None))
    qj = _jie_qijian(getattr(a, 'period', None))
    zz = _jie_zengzhang(getattr(a, 'growth', None))
    if zq:
        cfg['cycle'] = zq
    if qj:
        cfg['period'] = qj
    if zz is not None:
        cfg['growth'] = zz
    if not cfg.get('period'):
        cfg['period'] = _moren_qijian(zt)      # 演示件取「已结账截至」所在月
    if not cfg.get('period'):
        raise CuoWu('无法从工作簿推出分析期间：请用 --period YYYY-MM 指定（例如 --period 2027-06）')
    with jieduan(yun, f'十五步分析（{cfg["cycle"]} ｜ 期间 {cfg["period"]}'
                      f' ｜ 增长 {cfg["growth"]} 基点）'):
        kuai = q.DONGZUO['analysis.run'](zt, {'config': cfg})
        cun_zt(q)
    rid = zt.get('currentRunId') or ''
    jieguo = q._RUNS.get(rid)                  # 原始结果只在后端进程内存里存了一份
    if jieguo is None:
        raise CuoWu(f'分析已完成但取不到原始结果（runId={rid or "空"}）：'
                    '后端 _RUNS 未登记，请重跑 analyze')
    zhong = _tui_zhong(zt)
    if zhong and isinstance(jieguo.get('meta'), dict):
        jieguo['meta']['seed'] = zhong         # 报告抬头口径：种子来自文件名
    bao = _cun_yunxing(rid, jieguo, kuai, cfg, zhong)
    meta = kuai.get('meta') or {}
    shu = bao['gaishu']
    yun.shuchu(f'  ✔ 运行 {rid} ｜ 主体 {meta.get("company") or "（未解析）"}'
               f' ｜ 期间 {meta.get("period") or cfg["period"]}'
               f' ｜ 情景 {meta.get("scenario") or "—"}')
    yun.shuchu(f'    行 {shu.get("rows", 0)} ｜ 整改 {shu.get("actions", 0)} 条'
               f' ｜ KPI {shu.get("kpis", 0)} ｜ 预警 {shu.get("warnings", 0)}'
               f' ｜ 趋势 {shu.get("trend", 0)} 期')
    yun.shuchu(f'    原始结果缓存：{YUNXING_LU}（供 report / --ai 复用）')
    return {'runId': rid, 'config': cfg, 'meta': meta, 'counts': shu, 'seed': zhong,
            'stateFile': str(ZT_LU), 'runFile': str(YUNXING_LU)}



# pickle 缓存格式（hengce.cli.run/1）：
#   runId      当前运行号，report 用它和状态的 currentRunId 对齐，防止「分析 A 却出 B 的报告」
#   createdAt  落盘时刻（ISO 带时区），排障时看它判断缓存新旧
#   seed       演示件种子（可空），报告抬头与 JSON meta 取它
#   config     实际生效的配置（cycle/period/growth/阈值…），前端可回放
#   meta/gaishu 主体、期间、情景与计数摘要，便于不反序列化 jieguo 也能看概况
#   jieguo     引擎原始结果（保留对象形状：报告模块用属性访问读 factors 等）
# 为什么 protocol=4：Python 3.8+ 都能读，且比默认协议更稳地兼容复杂对象图；
# 原子写（.pkl.tmp → os.replace）保证崩溃时不会留下半个文件让下一条命令报「缓存损坏」。

def _cun_yunxing(run_id, jieguo, kuai, cfg, zhong):
    """把分析原始结果落 pickle（原子替换）。

    为什么必须 pickle：报告模块用属性访问读引擎结果（如 factors.wanchenglv_bps），
    JSON 往返会把 dataclass/SimpleNamespace 变成 dict 而失效；pickle 保住对象形状。
    """
    bao = {'schema': 'hengce.cli.run/1', 'runId': run_id, 'createdAt': _xianzai(),
           'seed': zhong, 'config': cfg,
           'meta': (kuai or {}).get('meta') or {},
           'gaishu': {k: len((kuai or {}).get(k) or [])
                      for k in ('rows', 'actions', 'kpis', 'trend', 'warnings')},
           'jieguo': jieguo}
    YUNXING_LU.parent.mkdir(parents=True, exist_ok=True)
    lin = YUNXING_LU.with_suffix('.pkl.tmp')
    with open(lin, 'wb') as f:                 # 先写临时文件再原子替换，崩溃不留半个文件
        pickle.dump(bao, f, protocol=4)
    os.replace(lin, YUNXING_LU)
    return bao



# 只读缓存、不校验新鲜度：新鲜度由 report 拿 runId 和状态比对完成——
# 校验集中在一处，避免两个地方各有一套「算不算过期」的判断。

def _du_yunxing():
    """读最近一次 analyze 的原始结果；文件不存在返回 None，损坏则中文报错。"""
    if not YUNXING_LU.exists():
        return None
    try:
        with open(YUNXING_LU, 'rb') as f:
            return pickle.load(f)
    except Exception as e:                     # noqa: BLE001 损坏要给可操作的提示
        raise CuoWu(f'CLI 运行缓存损坏（{YUNXING_LU.name}）：{e}；'
                    '请删除该文件后重跑 `衡策CLI.py analyze`')


# ----------------------------------------------------------------------
# report：按格式精确产出，可选 AI 解读
# ----------------------------------------------------------------------
# 前置条件全部显式校验，不靠运气：
#   ① 必须有 cli-运行.pkl（没有就提示先 analyze）；
#   ② 状态 dirty 必须为假：输入/配置变了，旧结果不再代表当前输入（与界面同口径）；
#   ③ 缓存 runId 必须等于状态 currentRunId：防止「重新导入但没重分析」时拿旧结果出报告；
#   ④ --ai 需要密钥：环境变量优先，其次 DSH_HOME/.credentials.yaml；缺密钥直接失败，
#      不静默降级成「纯计算报告」（用户明确要了 AI 解读，偷偷降级等于骗人）；
#   ⑤ 组装走 compute_report_pipeline（与界面同一函数），但**不用** reports.generate：
#      后者强制 md+html+pdf 三件套、要求 _RUNS 在本进程内存、还会把报告登记进界面历史——
#      三点都不符合「CLI 精确控制格式、不改界面数据」的目标；
#   ⑥ 格式精确：--format 里没写的格式不产出；写了却产不出（如无浏览器出 pdf）
#      就报错说明缺什么，不返回「成功但少一个文件」；
#   ⑦ json 三路径：流水线返回 'json' → 同名 .json → CLI 从 md 提取（带 fallback 说明）；
#   ⑧ --ai 失败（网络/额度/模型报错）时报告仍保留占位并告警：报告本身是计算产物，
#      不该因为模型不可用而丢失。

def _ming_report(yun, a):
    """report 子命令：按 --format 精确产出 md/html/pdf/json，可选 --ai 模型解读。"""
    q, zt = houduan(yun)
    geshi = _jie_geshi(getattr(a, 'format', 'md,html,pdf'))
    bao = _du_yunxing()
    if bao is None:
        raise CuoWu('找不到 CLI 运行结果：请先运行 `衡策CLI.py analyze`（或 `all`）'
                    '生成分析结果，再生成报告')
    if zt.get('dirty'):
        # 与界面同口径：输入或配置变了，旧结果不再代表当前输入
        raise CuoWu('输入或配置已变更（状态 dirty=true）：请重新运行 `衡策CLI.py analyze`，再生成报告')
    rid = zt.get('currentRunId') or ''
    if bao.get('runId') != rid:
        raise CuoWu(f'运行对不上：CLI 缓存的是 {bao.get("runId") or "（空）"}，'
                    f'当前状态是 {rid or "（空）"}；请重新运行 analyze')
    jieguo = bao['jieguo']
    zhong = bao.get('seed') or ''
    if zhong and isinstance(jieguo.get('meta'), dict):
        jieguo['meta']['seed'] = zhong         # 抬头口径：种子写进报告
    yao_ai = bool(getattr(a, 'ai', False))
    miyao = wencai = zongjie = None
    if yao_ai:
        miyao = q._du_miyao()                  # 环境变量 → DSH_HOME 凭据文件，两级都试
        if not miyao:
            raise CuoWu('未配置 DeepSeek API 密钥：请设置环境变量 DEEPSEEK_API_KEY'
                        '（或 DSH_HOME/.credentials.yaml 的 DEEPSEEK_API_KEY 行）；'
                        '不带 --ai 仍可生成纯计算报告')
        yun.shuo('▸ --ai 启用：逐模块调用 DeepSeek 写解读（约 3-8 分钟，失败会如实报错）…')
        wencai, zongjie = q._ai_bao_wencai(miyao)
    mu = Path(getattr(a, 'out', None) or SHUCHU_MU)
    mu.mkdir(parents=True, exist_ok=True)
    from baogao_liuxian import compute_report_pipeline   # 报告组装目录由桥接入口入 sys.path
    with jieduan(yun, f'计算报告组装（模块 9 ／ 检索条文）→ {mu}'):
        r = compute_report_pipeline(jieguo, wencai_hanshu=wencai,
                                    zongjie_hanshu=zongjie, shuchu_mu=str(mu))
    if yao_ai:
        try:
            with jieduan(yun, '整改建议 AI 回填（md + html 重写）'):
                q._ai_zhenggai(jieguo, miyao, str(Path(r['md'])))
        except Exception as e:                 # noqa: BLE001 回填失败不毁报告（保留占位并告警）
            yun.shuo(f'  [警告] 整改建议 AI 回填失败（占位保留）：{e}')
    chan = {'md': Path(r['md']), 'html': Path(r['html'])}
    if 'pdf' in geshi:
        pdf = mu / (Path(r['html']).stem + '.pdf')
        with jieduan(yun, 'HTML → PDF（本机 Chrome/Edge headless）'):
            cheng = q.zhuan_pdf(str(chan['html']), str(pdf))
        if cheng:
            chan['pdf'] = pdf
        else:
            yun.shuo('  [警告] 未找到可用的 Chrome/Edge，本次不出 PDF')
    zou_json = False
    if 'json' in geshi:
        chan['json'], zou_json = _sheng_json(yun, r, mu, yao_ai)
    # 逐格式一行（规范第七节：每完成一项一行，带字节数，便于核对是不是空文件）
    for ge in ('md', 'html', 'pdf', 'json'):
        if ge in chan:
            yun.shuchu(f'  ✔ {ge.upper():4s} {chan[ge]}（{chan[ge].stat().st_size} 字节）')
    que = [ge for ge in geshi if ge not in chan]
    if que:
        raise CuoWu(f'以下格式未生成：{"、".join(que)}'
                    f'（已生成：{"、".join(chan) or "无"}）；'
                    'PDF 需要本机安装 Chrome 或 Edge，其余请检查输出目录权限')
    yun.shuchu(f'  模块 {r.get("mokuai_shu")} 个 ｜ 检索条文 {r.get("tiaoli_shu")} 处'
               f' ｜ AI 解读 {"已启用" if yao_ai else "未启用（占位如实标注）"}')
    return {'outDir': str(mu), 'format': geshi, 'includeAI': yao_ai, 'runId': rid,
            'files': {k: str(v) for k, v in chan.items()},
            'mokuaiShu': r.get('mokuai_shu'), 'tiaoliShu': r.get('tiaoli_shu'),
            'jsonFromMd': zou_json, 'seed': zhong}



# 默认输入只用于「没给 --xlsx 的 all」，规则：
#   · 目录固定 backend/演示生成器v2/输出（演示件随包收，真实用户不依赖它）；
#   · 取最新一对（按 mtime 排序后按种子拼同名文件），保证「同一份种子」；
#   · 找不到就报错要求显式 --xlsx，绝不生成假数据顶上。

def _zhao_moren_shi_jian(yun):
    """默认输入：演示生成器v2/输出 里最新的一对「预算基础 + 实时经营」（同种子）。

    只在 all 没给 --xlsx 时用；找不到就中文报错要求显式给输入，不编造数据。
    """
    mu = BEN_MU / '演示生成器v2' / '输出'
    yu = sorted(mu.glob('演示-预算基础-*.xlsx'), key=lambda p: p.stat().st_mtime)
    shi = sorted(mu.glob('演示-实时经营-*.xlsx'), key=lambda p: p.stat().st_mtime)
    if not yu or not shi:
        raise CuoWu(f'没找到演示件：{mu}（请用 --xlsx 指定输入，'
                    '或先跑 演示生成器v2 生成演示工作簿）')
    zhong = yu[-1].stem.split('-')[-1]         # 同一份种子的一对，不能混配
    lu = [mu / f'演示-预算基础-{zhong}.xlsx', mu / f'演示-实时经营-{zhong}.xlsx']
    yun.shuo(f'▸ 未给 --xlsx，默认用演示件一对（种子 {zhong}）：{lu[0].name} + {lu[1].name}')
    return lu



# all = import → analyze → report 的串联，三个子命令共用同一进程与同一份状态：
#   · 好处：省掉两次进程启动与一次状态读写，且 analyze 的 jieguo 还在内存里，
#     report 仍然会走 pickle（保持与单独调用 report 完全一样的路径，行为不分叉）；
#   · 空 --xlsx 时用演示件一对（见 _zhao_moren_shi_jian）；
#   · 返回结构按 steps 顺序带三段结果，--json 时调用方可以逐段检查。

def _ming_all(yun, a):
    """all 子命令：import → analyze → report 一条龙（同进程共享状态，少一次反序列化）。"""
    if not getattr(a, 'xlsx', None):
        a.xlsx = [str(p) for p in _zhao_moren_shi_jian(yun)]
    d1 = _ming_import(yun, a)
    d2 = _ming_analyze(yun, a)
    d3 = _ming_report(yun, a)
    yun.shuchu(f'\n✔ 全流程完成：报告在 {d3["outDir"]}'
               f'（{"、".join(d3["files"])}）')
    return {'steps': ['import', 'analyze', 'report'],
            'import': d1, 'analyze': d2, 'report': d3}


# ----------------------------------------------------------------------
# serve / doctor / version
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# serve 生命周期（Node 起独立服务，Python 只当启动器）
# ----------------------------------------------------------------------
#   · 端口：默认 4180，--port 覆盖；启动前先 connect 探测——提前探测比让 Node 抛
#     EADDRINUSE 再解析英文栈要友好得多；
#   · 环境变量：HENGCE_PORT 传端口，HENGCE_PYTHON 传当前解释器——
#     保证服务里的 Python 与 CLI 是同一个（否则随包依赖可能对不上）；
#   · 前台模式（默认）：subprocess.call 直连 stdio，Ctrl+C 原样传给子进程，
#     日志直接流到用户终端；
#   · --detach：后台启动，stdout/stderr 重定向到 数据/临时/独立服务-<端口>.log，
#     再用 HTTP 轮询最多 25 秒确认就绪；不就绪就把日志尾部贴出来（含 pid），
#     让用户能直接看到 Node 的报错，而不是干等；
#   · 服务只绑 127.0.0.1，不做对外暴露——它是本机工作台，不是公网服务。

def _zhao_node():
    """定位 Node（只有 serve 需要）：环境变量 HENGCE_NODE → PATH 上的 node。"""
    huan = os.environ.get('HENGCE_NODE', '').strip()
    if huan and Path(huan).exists():
        return huan
    for ming in ('node', 'node.exe'):
        lu = shutil.which(ming)
        if lu:
            return lu
    return None


def _duan_zhan(duan):
    """端口占用探测：能连上就说明已被占用（否则 serve 会直接 EADDRINUSE）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(('127.0.0.1', duan)) == 0



# 就绪判定用「HTTP 能返回任何 <500 的响应」，而不是「端口能连」：
# 连上端口但服务还没初始化完时，前者能继续等，后者会误报成功。

def _deng_cheng(url, miao=25.0):
    """轮询等 HTTP 就绪（--detach 后台服务用）：返回 True/False，不抛异常。"""
    guo = time.perf_counter() + miao
    while time.perf_counter() < guo:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as fan:
                if fan.status < 500:           # 任何 <500 的响应都算服务起来了
                    return True
        except Exception:                      # noqa: BLE001 连不上就继续等
            time.sleep(0.3)
    return False



# 前台运行是默认：用户能直接看到服务日志、Ctrl+C 即停；
# --detach 是给「先起服务再跑别的命令」的场景，返回 pid 与日志路径便于收尾。


# 三条前置检查都在起进程之前：服务脚本在不在、Node 有没有、端口占不占——
# 任何一条不满足都立刻中文报错，不留给 Node 抛英文栈。

def _ming_serve(yun, a):
    """serve 子命令：起独立 HTTP 服务（127.0.0.1:端口/hengce/，与界面同后端）。"""
    duan = _jie_duankou(getattr(a, 'port', DUAN_KOU))
    if not FUWU_LU.exists():
        raise CuoWu(f'找不到独立服务脚本：{FUWU_LU}（插件包应含 adapter/独立服务.mjs）')
    node = _zhao_node()
    if not node:
        raise CuoWu('找不到 Node（serve 需要 Node 22+）：请安装 Node，'
                    '或设置环境变量 HENGCE_NODE 指向 node.exe')
    if _duan_zhan(duan):
        raise CuoWu(f'端口 {duan} 已被占用：请换端口（--port {duan + 1}）或先关掉占用进程')
    huan = os.environ.copy()
    huan['HENGCE_PORT'] = str(duan)            # 服务从环境变量取端口（默认 4180）
    huan['HENGCE_PYTHON'] = sys.executable     # 让服务的 Python 与 CLI 同一个解释器
    url = f'http://127.0.0.1:{duan}/hengce/'
    if getattr(a, 'detach', False):
        LINSHI_MU.mkdir(parents=True, exist_ok=True)
        rizhi = LINSHI_MU / f'独立服务-{duan}.log'
        with open(rizhi, 'wb') as f:
            p = subprocess.Popen([node, str(FUWU_LU)], cwd=str(FUWU_LU.parent),
                                 env=huan, stdout=f, stderr=subprocess.STDOUT)
        if not _deng_cheng(url):
            wei = ''
            try:
                wei = rizhi.read_text(encoding='utf-8', errors='replace')[-800:]
            except OSError:
                pass
            raise CuoWu(f'后台服务未在 25 秒内就绪（pid {p.pid}）：日志 {rizhi}\n'
                        f'--- 日志尾部 ---\n{wei}')
        yun.shuchu(f'  ✔ 已在后台启动（pid {p.pid}）：{url}')
        yun.shuchu(f'    日志：{rizhi}')
        return {'url': url, 'port': duan, 'pid': p.pid, 'detached': True, 'log': str(rizhi)}
    yun.shuchu(f'▸ 独立服务前台运行（Ctrl+C 退出）：{url}')
    ma = subprocess.call([node, str(FUWU_LU)], cwd=str(FUWU_LU.parent), env=huan)
    return {'url': url, 'port': duan, 'exitCode': ma, 'detached': False}


# ----------------------------------------------------------------------
# doctor：环境自检（安装后能不能用的分界线）
# ----------------------------------------------------------------------
# 分级口径：
#   必需（不过就退出 1）：Python 3.9+、openpyxl（契约校验）、numpy（检索向量）、
#                        后端动作表（files.import/analysis.run/reports.generate 三项齐）、
#                        数据目录可写（状态与报告都落这里）；
#   可选（缺了只降级，退出 0）：onnxruntime/tokenizers/pdfminer（kb2 真检索与建库）、
#                        kb2 指引库、Chrome/Edge（仅 PDF）、DeepSeek 密钥（仅 --ai）、
#                        Node（仅 serve）、演示工作簿（仅默认输入）；
#   · 每条检查都给「修复建议」，且建议必须可执行（写清路径或环境变量名）；
#   · 密钥只说「已配置 / 未配置」，绝不回显内容；
#   · --json 时输出 checks[{id,name,level,ok,detail,fix}] 与结论布尔，便于安装脚本判断。
# 为什么必需项卡这么少：CLI 的定位是「能算就能跑」——kb2 检索不到条文时报告如实
# 写占位（不冒充），PDF/AI/serve 都是可选增强，不该因为它们缺失就判定程序坏了。

def _ming_doctor(yun, a):
    """doctor 子命令：逐项自检并给中文修复建议；必需项不过 → 退出码 1。

    检查项就是「安装后能不能用」的全部分界线：解释器、核心依赖、后端动作表、
    数据目录可写是必需；检索库、PDF 浏览器、API 密钥、Node、演示件是可选
    （缺了会降级或只是少一个功能，CLI 照常能跑计算报告）。
    """
    xiang = []                                 # 有序列：[{id,name,level,ok,detail,fix}]

    def ji(bianhao, ming, dengji, ok, xiangqing, xiufu=''):
        """登记一条检查结果（失败时必带中文修复建议）。"""
        xiang.append({'id': bianhao, 'name': ming, 'level': dengji, 'ok': bool(ok),
                      'detail': xiangqing, 'fix': xiufu if not ok else ''})

    # ① Python 解释器：低于 3.9 语法就过不去（本文件用了若干 3.8+ 写法）
    ban = f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
    ji('python', 'Python 解释器', '必需', sys.version_info >= (3, 9),
       f'{sys.executable}（{ban}）',
       '需要 Python 3.9+：请用程序自带的随包 Python 运行'
       '（dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe）')
    # ② 核心依赖：openpyxl 做契约校验，numpy 给检索向量
    for bao, yongtu in (('openpyxl', 'Excel 工作簿读写（契约校验必需）'),
                        ('numpy', 'kb2 检索向量计算')):
        try:
            __import__(bao)
            ji(f'dep.{bao}', f'依赖 {bao}', '必需', True, f'已安装 {bao}')
        except Exception as e:                 # noqa: BLE001 缺依赖要报原始异常
            ji(f'dep.{bao}', f'依赖 {bao}', '必需', False, f'导入 {bao} 失败：{e}',
               f'缺少 {bao}（{yongtu}）：请让 PYTHONPATH 指向程序自带的 site 目录，'
               f'或用随包 Python 重跑')
    # ③ 满血依赖：检索链路要 onnxruntime+tokenizers；pdfminer 用于指引库建库
    for bao, yongtu in (('onnxruntime', '向量模型推理（kb2 真检索必需）'),
                        ('tokenizers', '文本切分（kb2 真检索必需）'),
                        ('pdfminer', 'PDF 文本抽取（指引库建库用）')):
        try:
            __import__(bao)
            ji(f'site.{bao}', f'满血依赖 {bao}', '可选', True, f'已安装 {bao}')
        except Exception:                      # noqa: BLE001 可选依赖缺了只降级
            ji(f'site.{bao}', f'满血依赖 {bao}', '可选', False, f'未安装 {bao}',
               f'缺少 {bao}（{yongtu}）：报告将按「占位」如实落文，不冒充检索到条文；'
               f'请把程序自带 衡策\\运行时\\site 加入 PYTHONPATH')
    # ④ 后端与动作表：没有它连导入都做不了（必需）
    q = zt = None
    try:
        q, zt = houduan(yun)
        dong = list(getattr(q, 'DONGZUO', {}) or {})
        bixu = [x for x in ('files.import', 'analysis.run', 'reports.generate') if x in dong]
        ji('backend', '后端与动作分发', '必需', len(bixu) == 3,
           f'桥接入口已载入，动作 {len(dong)} 个（关键动作 {len(bixu)}/3）',
           '桥接入口.py 未载入或动作表缺项：请确认 backend 目录完整'
           '（桥接入口.py / ingest_v11 / houtai_hexin_python / 报告组装）')
    except CuoWu as e:
        ji('backend', '后端与动作分发', '必需', False, str(e),
           '按上面的提示补全 backend 目录后重跑 doctor')
    # ⑤ 数据目录可写：状态、报告、临时件都落这里（必需）
    try:
        LINSHI_MU.mkdir(parents=True, exist_ok=True)
        shi = LINSHI_MU / f'doctor-{os.getpid()}.txt'
        shi.write_text('ok', encoding='utf-8')
        shi.unlink()
        ji('data', '数据目录可写', '必需', True, f'{SHUJU_MU} 可写')
    except OSError as e:
        ji('data', '数据目录可写', '必需', False, f'写入失败：{e}',
           f'请给 {SHUJU_MU} 写权限（或用 --out 指定可写目录）')
    # ⑥ kb2 指引检索库：有它报告才会写「出处」条文（可选，缺了如实占位）
    try:
        from baogao_liuxian import chuangjian_kb2_jiansuo
        jian = chuangjian_kb2_jiansuo()
        ku = BEN_MU / '_vendor' / 'kb2' / 'guanli_ku.sqlite'
        if jian is not None:
            ji('kb2', 'kb2 指引检索库', '可选', True,
               f'检索器可用（库文件 {ku.stat().st_size if ku.exists() else 0} 字节）')
        else:
            ji('kb2', 'kb2 指引检索库', '可选', False,
               '检索器不可用：报告按占位如实落文（不冒充检索到条文）',
               '确认 backend\\_vendor\\kb2 完整（guanli_ku.sqlite + models），'
               '并让 onnxruntime/tokenizers 可导入')
    except Exception as e:                     # noqa: BLE001
        ji('kb2', 'kb2 指引检索库', '可选', False, f'加载失败：{e}',
           '确认 backend\\_vendor\\kb2 完整；检索不可用时报告仍会生成，但条文位置写占位')
    # ⑦ 浏览器：只有 PDF 需要（可选）
    zhao = next((Path(x) for x in LIULANQI if Path(x).exists()), None)
    ji('browser', 'Chrome 或 Edge（导出 PDF）', '可选', zhao is not None,
       f'使用 {zhao}' if zhao else '未找到 Chrome/Edge',
       '安装 Chrome 或 Edge（或把浏览器装到默认路径）；'
       '没有浏览器时 --format 里去掉 pdf 仍可出 md/html/json')
    # ⑧ DeepSeek 密钥：只有 --ai 需要（可选，绝不回显密钥内容）
    miyao = None
    if q is not None:
        try:
            miyao = q._du_miyao()
        except Exception:                      # noqa: BLE001 取密钥失败按未配置处理
            miyao = None
    ji('apiKey', 'DeepSeek API 密钥（--ai 解读）', '可选', bool(miyao),
       '已配置（内容不回显）' if miyao else '未配置',
       '设置环境变量 DEEPSEEK_API_KEY，或在 DSH_HOME/.credentials.yaml 写 '
       'DEEPSEEK_API_KEY 行；不带 --ai 时不需要它')
    # ⑨ Node：只有 serve 需要（可选）
    node = _zhao_node()
    ji('node', 'Node（serve 独立服务）', '可选', bool(node),
       node or '未找到 node',
       '安装 Node 22+，或设置环境变量 HENGCE_NODE 指向 node.exe；'
       '不用 serve 时可以忽略这一项')
    # ⑩ 演示件：只有 all 不给 --xlsx 时用（可选）
    shi_jian = sorted((BEN_MU / '演示生成器v2' / '输出').glob('演示-*.xlsx'))
    ji('demo', '演示工作簿（默认输入）', '可选', bool(shi_jian),
       f'{len(shi_jian)} 本：{BEN_MU / "演示生成器v2" / "输出"}' if shi_jian else '未找到演示件',
       '不影响真实输入：用 --xlsx 指定自己的四类模板即可；'
       '需要演示件就先跑 演示生成器v2 生成')

    yun.shuchu(f'衡策 CLI {BANBEN} · 环境自检（{_xianzai()}）')
    for it in xiang:
        yun.shuchu(f'  {"✔" if it["ok"] else "✘"} [{it["level"]}] {it["name"]}：{it["detail"]}')
        if it['fix']:
            yun.shuchu(f'      修复：{it["fix"]}')
    bixu_guo = all(it['ok'] for it in xiang if it['level'] == '必需')
    ke_guo = all(it['ok'] for it in xiang if it['level'] == '可选')
    yun.shuchu(f'\n结论：必需项 {"全部通过" if bixu_guo else "有未通过（CLI 不能正常跑）"}'
               f' ｜ 可选项 {"全部就绪" if ke_guo else "有缺项（按提示降级使用）"}')
    data = {'ok': bixu_guo, 'optionalAllOk': ke_guo, 'checks': xiang,
            'python': ban, 'pythonExe': sys.executable,
            'stateFile': str(ZT_LU), 'outDir': str(SHUCHU_MU)}
    if not bixu_guo:
        raise CuoWu('环境自检未通过：必需项有缺失，请按上面的「修复」逐项处理后重跑 doctor')
    return data



# 只做只读输出：即使后端载入失败也要能报版本（诊断交给 doctor），
# 因此这里捕获 CuoWu 并把动作数写成「未载入：原因」，不抛异常。

def _ming_version(yun, a):
    """version 子命令：程序版本 / JSON 协议 / 解释器 / 后端动作数 / 关键路径。"""
    xin = {'cli': BANBEN, 'schema': SHIXING, 'pluginVersion': _du_banben(),
           'python': sys.version.split()[0], 'pythonExe': sys.executable,
           'platform': platform.platform(), 'backendActions': None,
           'stateFile': str(ZT_LU), 'runFile': str(YUNXING_LU), 'outDir': str(SHUCHU_MU)}
    try:
        q, _ = houduan(yun)                    # 后端坏了也要能报版本（诊断交给 doctor）
        xin['backendActions'] = len(getattr(q, 'DONGZUO', {}) or {})
    except CuoWu as e:
        xin['backendActions'] = f'未载入：{e}'
    yun.shuchu(f'衡策 CLI {BANBEN}（JSON 协议 {SHIXING}）')
    yun.shuchu(f'  插件包版本 {xin["pluginVersion"]}')
    yun.shuchu(f'  Python {xin["python"]} ｜ {xin["pythonExe"]}')
    yun.shuchu(f'  平台 {xin["platform"]}')
    yun.shuchu(f'  后端动作 {xin["backendActions"]}')
    yun.shuchu(f'  状态文件 {xin["stateFile"]}')
    yun.shuchu(f'  运行缓存 {xin["runFile"]}')
    yun.shuchu(f'  默认输出 {xin["outDir"]}')
    return xin


# ----------------------------------------------------------------------
# 子命令表：新增子命令的三步
# ----------------------------------------------------------------------
#   ① 写 _ming_xxx(yun, a)：返回可 JSON 化的 dict（--json 时就是信封的 data），
#      人看的正文一律用 yun.shuchu 打印——这样「给人看」和「给程序看」天然分离；
#   ② 在 FENPAI 登记；③ 在 _zao_canshuqi 里加 parser（帮助文本写清默认值与边界）。
# 不需要写「命令不存在」的分支：argparse 的 choices 已经挡住了。

#: 子命令 → 实现（新增子命令只改这里和 _zao_canshuqi）

# 子命令 → 实现函数：参数解析在 _zao_canshuqi，执行在这里，两边靠子命令名对齐。
# 新增子命令要同时改三处（_zao_canshuqi 注册、FENPAI 绑定、SHILI 示例），
# 否则会出现「帮助里有、跑起来报未知命令」这种最难查的错位。
# 所有 _ming_* 统一签名 (yun, a) → int：yun 是输出与状态上下文，a 是解析好的参数名空间。

FENPAI = {'import': _ming_import, 'analyze': _ming_analyze, 'report': _ming_report,
          'all': _ming_all, 'serve': _ming_serve, 'doctor': _ming_doctor,
          'version': _ming_version}


# ======================================================================
# 七、参数解析（中文帮助 + 安装后用法示例）
# ======================================================================

#: --help 尾部示例块：源码目录用法 + 安装后启动器用法（用户自检先看这里）

# 帮助文本就是第一手文档：示例同时给「源码目录」和「安装后启动器」两套写法，
# 因为安装后用户手上只有 衡策CLI.cmd，照抄 python 命令会找不到文件；
# 退出码与状态文件位置也写在这里——排查时用户第一眼看的就是 --help。

SHILI = """用法示例（源码目录，解释器换成随包 Python 也可）：
  衡策CLI.py doctor
  衡策CLI.py version
  衡策CLI.py import --xlsx 预算基础.xlsx --xlsx 实时经营.xlsx
  衡策CLI.py analyze --cycle 月度 --period 2027-06 --growth 0
  衡策CLI.py report --format md,html,pdf,json --out D:\\某个输出目录
  衡策CLI.py all --xlsx 预算基础.xlsx --xlsx 实时经营.xlsx --format md,html,json
  衡策CLI.py serve --port 4180

安装后用法（启动器 衡策CLI.cmd 转发，当前目录不限）：
  衡策CLI.cmd doctor
  衡策CLI.cmd all --xlsx D:\\某目录\\预算基础.xlsx --xlsx D:\\某目录\\实时经营.xlsx --format md,html,pdf,json
  衡策CLI.cmd report --format md,html,json --out D:\\某目录\\报告

退出码：0 成功 ｜ 1 业务失败（中文原因写 stderr）｜ 2 参数错误
全局选项：--json 结果为 JSON 信封写 stdout ｜ --quiet 不打印进度 ｜ --out 目录
状态文件：<插件根>\\数据\\cli-状态.json（与界面的 状态.json 相互独立）
"""



# 全局选项要在顶层和每个子命令都注册（这样 `衡策CLI.py --json report …` 与
# `衡策CLI.py report --json …` 两种写法都成立）；子命令那份用 SUPPRESS，
# 否则子解析器的默认 False 会把顶层已解析的 True 覆盖掉——argparse 的经典坑。

def _jia_quanju(p, yinmo=False):
    """加全局选项 --json / --quiet / --out。

    yinmo=True 用于子命令：default=SUPPRESS，避免子解析器的默认值把顶层已解析的
    值覆盖回 False/None（argparse 常见坑）。
    """
    kw = {'default': argparse.SUPPRESS} if yinmo else {}
    p.add_argument('--json', action='store_true',
                   help='结果以 JSON 信封写 stdout（进度与提示走 stderr，便于程序调用）', **kw)
    p.add_argument('--quiet', action='store_true',
                   help='不打印进度（错误仍写 stderr）', **kw)
    p.add_argument('--out', metavar='目录',
                   help='输出目录（默认 <插件根>\\数据\\cli-输出，仅 report/all 用）', **kw)



# 两套全局选项：顶层带真默认值，子命令用 SUPPRESS（防止默认值回写覆盖顶层结果）；
# 每个子命令的 help 写「一句话用途」，description 写「默认值与边界」——用户 90% 的问题
# 在 --help 里就能自答。返回 (解析器, 子命令名表) 供自检与文档核对。

def _zao_canshuqi():
    """构造参数解析器：顶层全局选项 + 7 个子命令，--help 带安装后用法示例。"""
    quan = argparse.ArgumentParser(add_help=False)
    _jia_quanju(quan)                          # 顶层：带真默认值
    quan_yin = argparse.ArgumentParser(add_help=False)
    _jia_quanju(quan_yin, yinmo=True)          # 子命令：SUPPRESS，不覆盖顶层值

    p = HengCeParser(
        prog='衡策CLI.py',
        description='衡策财务智能体 · 统一命令行入口：导入四类 Excel → 十五步分析 → 计算报告',
        epilog=SHILI,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[quan])
    z = p.add_subparsers(dest='mingling', metavar='<子命令>')

    q = z.add_parser('import', parents=[quan_yin],
                     help='导入工作簿（--xlsx 可多次）→ 契约校验 → 落 CLI 状态',
                     description='导入四类固定 Excel 工作簿：逐本走契约校验，通过后入库八字段。'
                                 '类别以解析结果为准（不信任文件名），失败整本退回并给中文原因。')
    q.add_argument('--xlsx', action='append', metavar='路径',
                   help='工作簿路径（.xlsx，可重复：预算基础 + 实时经营各一本）')

    q = z.add_parser('analyze', parents=[quan_yin],
                     help='跑十五步分析（--cycle / --period / --growth）',
                     description='在已导入的工作簿上跑十五步分析（滚动/差异/单双环/积木/BSC/KPI/整改）。'
                                 '原始结果落 数据\\cli-运行.pkl，供 report 与 --ai 跨进程复用。')
    q.add_argument('--cycle', metavar='粒度',
                   help='期间粒度：月度（默认）或 季度')
    q.add_argument('--period', metavar='期间',
                   help='分析期间：YYYY-MM（如 2027-06）或 YYYY-Q1…Q4；缺省取已结账截至')
    q.add_argument('--growth', metavar='基点',
                   help='增长假设，整数基点（0=不增长；正数上调、负数下调）')

    q = z.add_parser('report', parents=[quan_yin],
                     help='生成报告（--format md,html,pdf,json ／ --ai 模型解读）',
                     description='对最近一次 analyze 的结果生成计算报告。格式精确可控：'
                                 '--format 里写哪个就出哪个；json 优先用后端结构化输出，'
                                 '没有则由 CLI 从 md 提取并标注 fallback。')
    q.add_argument('--format', metavar='格式', default='md,html,pdf',
                   help='输出格式，逗号分隔：md,html,pdf,json（默认 md,html,pdf）')
    q.add_argument('--ai', action='store_true',
                   help='启用 DeepSeek 模型解读（需要 DEEPSEEK_API_KEY；约 3-8 分钟）')

    q = z.add_parser('all', parents=[quan_yin],
                     help='一条龙：import → analyze → report',
                     description='不给 --xlsx 时默认取 演示生成器v2/输出 里最新的一对演示件'
                                 '（固定种子，可复现）。')
    q.add_argument('--xlsx', action='append', metavar='路径',
                   help='工作簿路径（.xlsx，可重复；缺省用演示件一对）')
    q.add_argument('--cycle', metavar='粒度', help='期间粒度：月度（默认）或 季度')
    q.add_argument('--period', metavar='期间', help='分析期间：YYYY-MM 或 YYYY-Q1…Q4')
    q.add_argument('--growth', metavar='基点', help='增长假设，整数基点')
    q.add_argument('--format', metavar='格式', default='md,html,pdf',
                   help='输出格式，逗号分隔：md,html,pdf,json（默认 md,html,pdf）')
    q.add_argument('--ai', action='store_true', help='启用 DeepSeek 模型解读（需要密钥）')

    q = z.add_parser('serve', parents=[quan_yin],
                     help='起独立 HTTP 服务（127.0.0.1:4180/hengce/）',
                     description='用 Node 起独立服务（adapter/独立服务.mjs），与界面同一后端。'
                                 '前台运行时按 Ctrl+C 退出；--detach 后台启动并打印地址与 pid。')
    q.add_argument('--port', metavar='端口', default=str(DUAN_KOU),
                   help=f'监听端口（默认 {DUAN_KOU}，仅绑 127.0.0.1）')
    q.add_argument('--detach', action='store_true', help='后台启动（打印地址与 pid，日志落 数据\\临时）')

    z.add_parser('doctor', parents=[quan_yin],
                 help='环境自检（解释器/依赖/检索库/浏览器/密钥/Node）',
                 description='安装后的自检入口：逐项 ✔/✘ 并给中文修复建议；'
                             '必需项不过退出码 1，可选项缺只降级。')

    z.add_parser('version', parents=[quan_yin],
                 help='版本信息（程序版本 / JSON 协议 / 解释器 / 后端动作数）',
                 description='打印版本与关键路径，便于排障时贴给支持人员。')
    return p, ['import', 'analyze', 'report', 'all', 'serve', 'doctor', 'version']



# 只为「参数错误时也能给出 command」：从原始 argv 里找已知子命令名，
# 找不到给空串——参数解析都失败了，不能指望 argparse 的 namespace。

def _ming_ling_cai(argv):
    """从原始 argv 里猜子命令名（只为参数错误时把 command 写进信封）。"""
    for x in argv:
        if x in FENPAI:
            return x
    return ''


# ======================================================================
# 八、主入口：解析 → 执行 → JSON 信封 / 中文错误 / 退出码
# ======================================================================

# ----------------------------------------------------------------------
# 主流程与退出码映射（顺序有讲究）
# ----------------------------------------------------------------------
#   ① 先解析参数：失败 exit 2；--json 时也给一个 ok=false 的信封（脚本不用解析 stderr 文本）；
#   ② 没给子命令：help 写 stderr（stdout 留给机器），exit 2；
#   ③ 正常执行外包 _biao_zhuan：--json 期间 stdout 全部改道 stderr，保证信封是唯一输出；
#   ④ 异常分层：CuoWu → 自身退出码（1/2）；后端 RuntimeError → 1 且信封标 source=后端；
#      Ctrl+C → 1（用户中断，不必打印栈）；其它异常 → 完整栈给 stderr + 1（绝不吞）；
#   ⑤ 成功且有 data：--json 写信封；非 --json 时正文早已由各子命令实时打印（进度可见）。

def pao(argv=None):
    """CLI 主流程：返回进程退出码（0 成功 / 1 业务失败 / 2 参数错误）。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    zhen = sys.stdout                           # 真 stdout（--json 时 sys.stdout 会被改）
    ap, _ = _zao_canshuqi()
    try:
        a = ap.parse_args(argv)
    except CanShuCuoWu as e:
        # 参数错误：不抛栈，中文一行到 stderr；--json 时仍给机器一个信封
        print(f'参数错误：{e}', file=sys.stderr, flush=True)
        if '--json' in argv:
            yun = Yunxing(json_mode=True)
            yun.mingling = _ming_ling_cai(argv)
            _xie_json(zhen, _feng_bao(yun, False, cuowu={
                'code': 2, 'kind': TUI_CHU[2], 'message': f'参数错误：{e}'}))
        return 2
    yun = Yunxing(json_mode=getattr(a, 'json', False),
                  quiet=getattr(a, 'quiet', False),
                  out=getattr(a, 'out', None))
    ming = getattr(a, 'mingling', None)
    yun.mingling = ming or ''
    if not ming:
        # 没给子命令：用法写 stderr（stdout 留给程序解析），中文说明原因
        ap.print_help(sys.stderr)
        print('\n参数错误：缺少子命令（可用：import / analyze / report / all / serve / doctor / version）',
              file=sys.stderr, flush=True)
        if yun.json:
            _xie_json(zhen, _feng_bao(yun, False, cuowu={
                'code': 2, 'kind': TUI_CHU[2],
                'message': '缺少子命令（可用：import / analyze / report / all / serve / doctor / version）'}))
        return 2
    try:
        with _biao_zhuan(yun):                  # --json：工作期 stdout 全部改道 stderr
            shuju = FENPAI[ming](yun, a)
    except CuoWu as e:
        # 业务失败 / 参数错误（子命令内部校验）：中文原因一行给用户，退出码照实
        yun.shuo(f'✘ {e}')
        if yun.json:
            _xie_json(zhen, _feng_bao(yun, False, cuowu={
                'code': e.ma, 'kind': TUI_CHU.get(e.ma, '失败'), 'message': str(e)}))
        return e.ma
    except RuntimeError as e:
        # 后端动作抛的中文 RuntimeError（契约校验、密钥缺失、runId 失效等）原样转出
        yun.shuo(f'✘ {e}')
        if yun.json:
            _xie_json(zhen, _feng_bao(yun, False, cuowu={
                'code': 1, 'kind': TUI_CHU[1], 'message': str(e), 'source': '后端'}))
        return 1
    except KeyboardInterrupt:
        sys.stderr.write('\n✘ 已中断（Ctrl+C）：本次未产出完整结果\n')
        return 1
    except Exception as e:                      # noqa: BLE001 不吞异常：栈给 stderr
        traceback.print_exc(file=sys.stderr)
        wen = f'未预期的内部错误：{type(e).__name__}: {e}（完整堆栈见上）'
        yun.shuo(f'✘ {wen}')
        if yun.json:
            _xie_json(zhen, _feng_bao(yun, False, cuowu={
                'code': 1, 'kind': TUI_CHU[1], 'message': wen}))
        return 1
    if yun.json:
        _xie_json(zhen, _feng_bao(yun, True, shuju=shuju))
    return 0


if __name__ == '__main__':
    sys.exit(pao())
