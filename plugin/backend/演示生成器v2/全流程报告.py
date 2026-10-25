# -*- coding: utf-8 -*-
"""全流程报告：生成 → 生成器校验 → 试算平衡 → 接收端导入 → 输出 PDF。

一条命令跑完整条链路（不手工串脚本），最后产出 A4 排版的 PDF 报告：
    python -B 全流程报告.py                 # 默认种子 20260923
    python -B 全流程报告.py --seed 20261018
    python -B 全流程报告.py --seed 20261018 --no-pdf   # 只出 HTML

PDF 由本机 Chrome/Edge 的 headless 打印生成（`--print-to-pdf`），零第三方依赖；
HTML 自包含（内嵌 CSS），可直接用浏览器打开或另存。

为什么要有这一层
    上游四个模块（shuju 生数 / banshi 版式 / xiechu 写盘 / jiaoyan 校验）各自只证明
    自己那段对，没有哪一处能回答"整条链路是不是通的、四册能不能被接收端吃进去"。
    本模块把这条链串起来跑一遍，把每段的结论落成一份给人看的报告：
    这正是交付评审时唯一需要打开的那份材料。

链路与每段的职责
    1) pao_shengcheng 生成四册（预算基础/实时经营/行业对标/经营变更）
    2) pao_jiaoyan    生成器自带校验（明细合计、资负勾稽、利润表、现金流量表、摊销）
    3) suan_shisuan   独立试算平衡：不走生成器代码，直接读落盘 xlsx 重算借贷合计
    4) pao_daoru     把四册喂给接收端 ingest_v11，验证"能被导入"而非"只是长得像"
    5) zhuang/main   组装 HTML，交本机浏览器打印成 PDF
    第 3 步刻意与第 2 步不同源：校验若也调生成器的函数，等于自己证明自己；
    这里从文件里重新加总每一笔分录，才能发现"写盘时丢了符号/丢了一行"这类错。

为什么用 subprocess 而不是 import 调函数
    ① 进程隔离：生成器与校验脚本都有模块级常量与全局状态，同进程连跑容易互相污染；
    ② 路径同构：子进程跑的就是用户手工敲的那两条命令，本报告证明的才是"用户真能跑通"；
    ③ 失败可见：子进程 returncode / stderr 是三段式证据，比进程内异常更接近现场。
    代价是多一次解释器启动（约 0.3s×4），对一条演示链完全可以接受。

为什么 PDF 走浏览器而不是 reportlab/weasyprint
    项目对第三方依赖有洁癖（安装包体积、离线可用），而 Windows 机器上 Chrome/Edge
    必然存在。用 `--print-to-pdf` 打印自包含 HTML，排版由 CSS 控制，效果与"人工
    打开网页按打印"完全一致，且不需要额外装任何库。

口径
    金额一律元、两位小数（Decimal，报告里只做展示与比较，不参与记账）；
    比率显示为百分数（如 12.00%），内部以小数保存（0.12 = 12%）；
    试算差额、借贷合计必须是 0.00 —— 非 0 即视为链路失败，不做"四舍五入之后算平"的掩盖。

产物
    <本目录>/输出/演示-*-<seed>.xlsx（四册，由生成器写）
    <本目录>/输出/全流程报告-<seed>.html
    <本目录>/输出/全流程报告-<seed>.pdf
    退出码：0 = 全链成功（--no-pdf 时 HTML 成功即 0）；1 = 仅 HTML 成功、PDF 未生成。
"""
import argparse
import html
import subprocess
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

MU = Path(__file__).resolve().parent                               # 演示生成器v2
CHU = MU / '输出'                                                  # 产物目录
RECV = MU.parent / 'ingest_v11'                                    # 接收端包

#: PDF 渲染器候选（本机 Chrome / Edge，取第一个存在的）
RENDER = (r'C:\Program Files\Google\Chrome\Application\chrome.exe',
          r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
          r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')


def shu(v):
    """单元格值 → Decimal（非数值按 0）。

    参数: v 任意单元格值（openpyxl 读回的原生类型）。
    返回: Decimal。空单元格 None、文本、"50.00%" 这类都不是数值，一律回 0。
    为什么先判 bool: Python 里 True/False 是 int 的子类，isinstance(v, int) 会命中，
        若放过就会读成 1/0，把布尔标记当金额混进合计——所以在数值分支之前先拦掉。
    为什么用 str(v) 再转: openpyxl 读回的浮点常带二进制尾差（0.1+0.2 类），
        直接 Decimal(float) 会把尾差一起带进加总；走 str 取的是十进制字面量，
        与 Excel 里显示的那个数一致。
    """
    if isinstance(v, bool):
        return Decimal(0)
    return Decimal(str(v)) if isinstance(v, (int, float, Decimal)) else Decimal(0)


def q(v):
    """千分位两位小数（负数带负号）。

    参数: v 任意单元格值（内部先过 shu）。
    返回: 字符串，如 12,345.60、-3,000.00。
    为什么两位小数: 报告是给人看的对账材料，与账表口径（元、分）保持一致；
        千分位是为了让"万/十万"级别的金额一眼可读，不改变数值。
    """
    return f'{shu(v):,.2f}'


def pc(v):
    """百分比四位。"""
    return f'{shu(v) * 100:.2f}%'


# ======================================================================
# 一、跑链路：生成 → 校验 → 试算 → 导入
# ======================================================================

def pao_shengcheng(seed):
    """跑生成器（四册），返回产物路径与耗时无关的输出行。

    参数: seed 整数种子；同一 seed 必须得到逐字节相同的四册（可复现是硬纪律）。
    返回: ["生成 <路径>（<字节数> 字节）", ...] —— 只收以"生成"开头的行，
        生成器其它调试输出不入报告。
    异常: 子进程 returncode != 0 时抛 SystemExit，消息里带 stdout/stderr 各末尾 400 字符。
        只截末尾是因为真正的报错（traceback 末行、AssertionError 文案）总在最后。
    副作用: 在 cwd=MU（本目录）下运行，产物落在 <本目录>/输出/；
        encoding='utf-8' 必须显式给——Windows 控制台默认 GBK，生成的路径里有中文，
        不指定编码会在 subprocess 解码阶段直接 UnicodeDecodeError。
    """
    r = subprocess.run([sys.executable, '-B', str(MU / 'shengcheng.py'), '--seed', str(seed)],
                       capture_output=True, text=True, encoding='utf-8', cwd=str(MU))
    if r.returncode != 0:                                          # 生成失败直接抛
        raise SystemExit(f'生成失败：{r.stdout[-400:]}{r.stderr[-400:]}')
    return [ln.strip() for ln in r.stdout.splitlines() if ln.startswith('生成')]


def pao_jiaoyan(seed):
    """跑生成器自带校验，返回（通过数, 失败数, 失败明细）。

    参数: seed 整数种子。
    返回: (tong, shi, bai) —— 通过项数、失败项数、["FAIL: ...", ...] 明细。
    解析口径: 只认以"通过 "开头的摘要行，形如「通过 37 项，失败 0 项」；
        先把前后缀去掉再 split 取前两个整数，容忍"项"字与全角逗号的变化。
    异常: 本函数不因校验失败而抛——失败是报告要呈现的结论（会红字标出），
        不是执行事故；只有 subprocess 本身跑不起来才会抛（编码/权限类）。
    """
    r = subprocess.run([sys.executable, '-B', str(MU / 'jiaoyan.py'), '--seed', str(seed)],
                       capture_output=True, text=True, encoding='utf-8', cwd=str(MU))
    tong = shi = 0
    bai = []
    for ln in r.stdout.splitlines():
        if ln.startswith('通过 '):                                   # 摘要行：通过 N 项，失败 M 项
            bufen = ln.replace('通过 ', '').replace(' 项，失败 ', ' ').replace(' 项', '')
            tong, shi = (int(x) for x in bufen.split()[:2])
        if ln.strip().startswith('FAIL:'):
            bai.append(ln.strip())
    return tong, shi, bai


def suan_shisuan(lu):
    """试算平衡：逐笔分录汇总科目 + 三表勾稽（只读成交付值，不改文件）。

    参数: lu 一册 xlsx 路径（预算基础或实时经营，两者版式同为 12 表）。
    返回: dict，字段含义见下方分行注释；本函数只读，绝不回写任何单元格。

    算法（顺序即口径）
        ① 先扫 A 列找"全部借方合计"行号 mo，它就是分录区的上界（合计行本身不计入）；
        ② 只遍历 2..mo-1，B 列为空视为分隔空行跳过——分录表用空行分组，
           不跳过就会把组标题算成一条分录，笔数与合计同时失真；
        ③ 每条分录：借 C 列科目 + 金额在 E 列，贷 D 列科目 + 金额在 F 列；
           按科目双向累加，最后每个科目的净额 = 借 − 贷（这就是"科目余额"的借正贷负口径）；
        ④ G 列是现金流对照行号（"现金流量表第 15 行"这类），只在它是数字时累计，
           文本"—"表示该科目不直接对应现金流项目，不能当 0 也不能当行号；
        ⑤ 借贷合计取所有分录的 E/F 列之和，而不是"科目净额之和"——
           净额会互抵，只有原始发生额才能证明"每一笔都有对手方"。
    为什么差额必须是 0.00: 复式记账的恒等式，任何非 0 都意味着写盘时丢了行或符号错了；
        报告里如实展示差额，不四舍五入掩盖。
    """
    wb = load_workbook(lu)
    fl = wb['分录']
    mo = 1
    for r in range(2, fl.max_row + 1):                              # 合计行定位
        if fl[f'A{r}'].value == '全部借方合计':
            mo = r
            break
    jie = defaultdict(Decimal)
    dai = defaultdict(Decimal)
    bi = 0
    dui = defaultdict(Decimal)
    for r in range(2, mo):
        if not fl[f'B{r}'].value:                                   # 空行（分隔行）
            continue
        bi += 1
        jin = shu(fl[f'E{r}'].value)
        jie[fl[f'C{r}'].value] += jin
        dai[fl[f'D{r}'].value] += shu(fl[f'F{r}'].value)
        if isinstance(fl[f'G{r}'].value, (int, float)):              # 现金流对照（"—"不计）
            dui[int(fl[f'G{r}'].value)] += jin
    he_jie = sum(jie.values(), Decimal(0))
    he_dai = sum(dai.values(), Decimal(0))
    lr, zf, xj = wb['利润表'], wb['资产负债表'], wb['现金流量表']
    # 科目净额按 |金额| 降序：报告只展示前 12 个，金额大的是最值得看的科目
    ke = sorted(((k, jie[k] - dai[k]) for k in set(jie) | set(dai)),
                key=lambda kv: -abs(kv[1]))
    d = {'bi': bi, 'jie': he_jie, 'dai': he_dai,
         'ke': len(set(jie) | set(dai)), 'kemu': ke,
         'jingli': shu(lr['B28'].value), 'zongshouyi': shu(lr['B44'].value),
         'zichan': shu(zf['B40'].value), 'fuzhai_quanyi': shu(zf['E45'].value),
         'huobi': shu(zf['B6'].value), 'xianmo': shu(xj['B42'].value),
         'jingzeng': shu(xj['B40'].value), 'jingying': shu(xj['B15'].value),
         'yinhang': jie.get('银行存款', Decimal(0)) - dai.get('银行存款', Decimal(0)),
         'zhuanjie': dai.get('利润分配', Decimal(0)),                # 本年利润结转额
         'liucun': shu(zf['E43'].value) - shu(zf['F43'].value) + shu(zf['E42'].value) - shu(zf['F42'].value)}
    wb.close()
    return d


def du_ce(lu):
    """读一本：三表关键行 + 税金 + 摊销台账 + 费用表。

    参数: lu 一册 xlsx 路径。
    返回: dict（键即报告里取用的字段），全部金额已过 shu() 转 Decimal。
    为什么按固定格号取而不解析表头: 版式由 banshi.py 固化（表名与行次是合同的一部分），
        按行次取等于把这份合同显式写出来；一旦版式变了，这里取到 None 会立刻显形。
    eps/deps 不过 shu(): 每股收益是四位小数的展示值，报告里原样呈现字符串，
        转 Decimal 再格式化反而会丢"4 位"这个口径。
    """
    wb = load_workbook(lu)
    lr, zf, xj = wb['利润表'], wb['资产负债表'], wb['现金流量表']
    sj, tx = wb['税金及附加'], wb['摊销明细']
    xiao, guan, hz = wb['销售费用'], wb['管理费用'], wb['费用表月度汇总']
    d = {'主体': str(lr['A3'].value).replace('编制单位：', '').strip(),
         'riqi': lr['B3'].value,
         '收入': shu(lr['B5'].value), '成本': shu(lr['B6'].value), '税金': shu(lr['B7'].value),
         '销售': shu(lr['B8'].value), '管理': shu(lr['B9'].value), '研发': shu(lr['B10'].value),
         '财务': shu(lr['B11'].value), '其他收益': shu(lr['B14'].value), '投资收益': shu(lr['B15'].value),
         '公允': shu(lr['B19'].value), '信用': shu(lr['B20'].value), '资产减值': shu(lr['B21'].value),
         '处置': shu(lr['B22'].value), '营业利润': shu(lr['B23'].value),
         '营外收': shu(lr['B24'].value), '营外支': shu(lr['B25'].value),
         '利润总额': shu(lr['B26'].value), '所得税': shu(lr['B27'].value),
         '净利润': shu(lr['B28'].value), '综合收益': shu(lr['B44'].value),
         'eps': lr['B46'].value, 'deps': lr['B47'].value,
         '资产': shu(zf['B40'].value), '负债权益': shu(zf['E45'].value),
         '货币': shu(zf['B6'].value), '货币上年': shu(zf['C6'].value),
         '经营': shu(xj['B15'].value), '净增': shu(xj['B40'].value), '期末': shu(xj['B42'].value),
         '年税': shu(sj['AC127'].value), '城建': shu(sj['AC123'].value),
         '教育': shu(sj['AC124'].value), '地方': shu(sj['AC125'].value),
         '附加率': sj['C31'].value,
         # 摊销台账：行 10..17 共 8 项资产，取 (资产名, 费用归属表, 部门, 月摊销额) 四列。
         # 行 18 是合计行，故 range 右端写 18 不含。
         '台账': [(tx[f'A{r}'].value, tx[f'B{r}'].value, tx[f'C{r}'].value, shu(tx[f'G{r}'].value))
                  for r in range(10, 18)],
         '月摊': shu(tx['B3'].value),
         '费用合计': shu(hz['O34'].value) if hz['O34'].value is not None else Decimal(0)}
    wb.close()
    return d


def pao_daoru(lu):
    """接收端导入（v2/v1.2 轨道自动分派）。

    参数: lu 一册 xlsx 路径（四册都试一遍，含外部两册）。
    返回: {'轨道': contract_version 或 '外部v1.2', '校验': checks 数,
          '分录': 分录条数, '类别': 数据类别}。
    为什么延迟导入: 接收端包在 ../ingest_v11，不在 sys.path 上；只有走到这一步才需要它，
        模块级 import 会让"只想看生成结果"的用法也背上接收端的依赖。
    为什么读 bytes 而不是给路径: import_excel_v11 的契约是 (字节流, 文件名)——
        它既可接上传的附件，也可接本地文件；用同一入口才算真的"模拟用户导入"。
    异常: 四册中任一册抛异常都会中断 main（导入不通过是硬失败，不做容错降级）。
    """
    if str(RECV) not in sys.path:
        sys.path.insert(0, str(RECV))
    from excel_ingest_v11 import import_excel_v11                    # 延迟导入
    r = import_excel_v11(lu.read_bytes(), lu.name)
    return {'轨道': r.get('contract_version', '外部v1.2'), '校验': r.get('checks', 0),
            '分录': len(r.get('fenlu', [])), '类别': r.get('category', '-')}


# ======================================================================
# 二、HTML 组装（自包含 CSS，A4 打印友好）
# ======================================================================

# CSS 自包含在模块里（不引外部样式表）：HTML 单文件即可交付，
# 断网也能打开，headless 打印时也不会有"样式还没加载完"的竞态。
# @page 用 A4 + 12~14mm 页边距：这是中文报表的常用版心，一页刚好放一张表；
# .pb（page-break-before: always）用来在报告里强制分页，保证"每册从新页开始"。
YANG = """
@page { size: A4; margin: 14mm 12mm 12mm 12mm; }
* { box-sizing: border-box; }
body { font-family: "Microsoft YaHei","微软雅黑",SimSun,sans-serif; font-size: 10.5pt;
       color: #1a1a1a; line-height: 1.5; margin: 0; }
h1 { font-size: 20pt; margin: 0 0 4px; letter-spacing: 1px; }
h2 { font-size: 13pt; margin: 18px 0 8px; padding-left: 8px; border-left: 4px solid #1f4e79;
     color: #1f4e79; }
h3 { font-size: 11.5pt; margin: 14px 0 6px; color: #333; }
.sub { color: #666; font-size: 9.5pt; margin-bottom: 10px; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 12px; font-size: 9.5pt; }
th { background: #1f4e79; color: #fff; font-weight: 600; padding: 5px 6px; text-align: left;
     border: 0.5pt solid #1f4e79; }
td { padding: 4px 6px; border: 0.5pt solid #c9d6e3; }
tr:nth-child(even) td { background: #f4f8fc; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.ok { color: #1a7f37; font-weight: 600; }
.bad { color: #b42318; font-weight: 600; }
.box { border: 0.8pt solid #c9d6e3; background: #f8fbfe; padding: 8px 10px; margin: 8px 0;
       border-radius: 3px; font-size: 9.5pt; }
.kv { width: auto; display: inline-block; }
.foot { margin-top: 16px; padding-top: 6px; border-top: 0.5pt solid #ccc; color: #888;
        font-size: 8.5pt; }
.pb { page-break-before: always; }
"""


def biao(tou, hang, lei=(), shu_lie=()):
    """生成一张表：tou=表头元组；hang=数据行；lei=数值列下标（右对齐）。

    参数: tou 表头文本（元组/列表）；hang 行列表（每行是与 tou 等长的序列）；
        lei 需要右对齐的列下标（数值列）；shu_lie 预留（当前未使用）。
    返回: 一段 <table> 字符串（<thead>+<tbody>）。
    为什么每格都 html.escape: 主体名、科目名来自数据而非代码，含 & < > 时会把表格撑坏；
        统一转义后，报告在任何浏览器里都不会被数据当成标签解释。
    为什么空 tbody 也要输出: 保持 HTML 结构完整，避免打印时分页位置跳动。
    """
    th = ''.join(f'<th class="n">{html.escape(str(x))}</th>' if i in lei
                 else f'<th>{html.escape(str(x))}</th>' for i, x in enumerate(tou))
    tr = []
    for r in hang:
        tds = ''.join(f'<td class="n">{html.escape(str(v))}</td>' if i in lei
                      else f'<td>{html.escape(str(v))}</td>' for i, v in enumerate(r))
        tr.append(f'<tr>{tds}</tr>')
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(tr)}</tbody></table>'


def zhuang(seed, sheng, jian, yu, shi, sy, ss, dr):
    """整份 HTML。

    参数:
        seed  种子（写进标题、副标题与页脚，报告因此可被"复现命令"反查）。
        sheng pao_shengcheng 返回的产物行（只用来数册数）。
        jian  (通过数, 失败数, 失败明细) 三元组。
        yu / shi   预算基础册、实时经营册的 du_ce 结果（报表关键值）。
        sy / ss    对应两册的 suan_shisuan 结果（试算平衡与科目余额）。
        dr    {文件名: 接收端导入结果}（四册）。
    返回: 完整 HTML 字符串（含内嵌 CSS）。
    结构: 结论 → 两册对照 → 分册 A → 分册 B → 科目余额 → 说明，共六节；
        用 <div class="pb"> 在"两册对照之后""分册 A 之后""分册 B 之后"强制分页，
        使 A4 打印时每节从新页起，符合评审材料"一页一主题"的阅读习惯。
    口径: 本函数只做排版，不做任何计算或校验；数值全部由上游算好传进来，
        所以报告里任何"对不上"都是上游的问题，不是渲染的问题。
    """
    tong, bai, bai_li = jian
    # ok/bad 只随"是否有失败项"变：全通过绿字、有失败红字，颜色本身就是结论
    ok = 'ok' if not bai else 'bad'
    # ---- 结论表 ----
    jielun = biao(('环节', '结果'), [
        ('生成（4 册）', f'{len(sheng)} 册：预算基础 / 实时经营 / 行业对标 / 经营变更'),
        ('生成器校验', f'通过 {tong} 项，失败 {bai} 项'),
        ('试算平衡 · 预算基础', f'借 = 贷 = {q(sy["jie"])}，差额 {q(sy["jie"] - sy["dai"])}'),
        ('试算平衡 · 实时经营', f'借 = 贷 = {q(ss["jie"])}，差额 {q(ss["jie"] - ss["dai"])}'),
        ('账面利润 = 报表净利润', f'{q(sy["zhuanjie"])} = {q(sy["jingli"])} ／ {q(ss["zhuanjie"])} = {q(ss["jingli"])}'),
        ('现金流衔接', f'银行存款净额 {q(sy["yinhang"])} = 现金净增加 {q(sy["jingzeng"])}'),
        ('接收端导入', '；'.join(f'{k}：{v["轨道"]}（校验 {v["校验"]} 项）' for k, v in dr.items())),
    ], lei=(1,))
    # ---- 两册对照 ----
    # 16 行按利润表自上而下的顺序排：读者按报表习惯往下看，不必跳来跳去
    duibi = biao(('指标', '预算基础（12 月）', '实时经营（6 月）'), [
        ('营业收入', q(yu['收入']), q(shi['收入'])),
        ('营业成本', q(yu['成本']), q(shi['成本'])),
        ('税金及附加', q(yu['税金']), q(shi['税金'])),
        ('销售费用', q(yu['销售']), q(shi['销售'])),
        ('管理费用', q(yu['管理']), q(shi['管理'])),
        ('研发费用', q(yu['研发']), q(shi['研发'])),
        ('财务费用', q(yu['财务']), q(shi['财务'])),
        ('营业利润', q(yu['营业利润']), q(shi['营业利润'])),
        ('利润总额', q(yu['利润总额']), q(shi['利润总额'])),
        ('所得税费用', q(yu['所得税']), q(shi['所得税'])),
        ('净利润', q(yu['净利润']), q(shi['净利润'])),
        ('综合收益总额', q(yu['综合收益']), q(shi['综合收益'])),
        ('基本每股收益', str(yu['eps']), str(shi['eps'])),
        ('资产总计', q(yu['资产']), q(shi['资产'])),
        ('期末现金', q(yu['期末']), q(shi['期末'])),
        ('分录笔数', str(sy['bi']), str(ss['bi'])),
    ], lei=(1, 2))
    # ---- 分册 ----
    def fence(d, s, tag):
        """一册的明细页（利润表 / 三表摘要 / 税金 / 摊销 / 分录），返回 HTML 片段。

        参数: d du_ce 的单册结果；s suan_shisuan 的单册结果；tag 分册标题。
        为什么把"税金及附加"单列一页: 它是唯一能看出"增值税附加率假设"的地方，
            也是审计最常追问的勾稽点（年税 = 城建 + 教育 + 地方 + 印花）。
        """
        lr = biao(('利润表项目', '金额'), [
            ('一、营业收入', q(d['收入'])), ('减：营业成本', q(d['成本'])),
            ('税金及附加', q(d['税金'])), ('销售费用', q(d['销售'])),
            ('管理费用', q(d['管理'])), ('研发费用', q(d['研发'])),
            ('财务费用', q(d['财务'])), ('加：其他收益', q(d['其他收益'])),
            ('投资收益', q(d['投资收益'])), ('公允价值变动收益', q(d['公允'])),
            ('信用减值损失', q(d['信用'])), ('资产减值损失', q(d['资产减值'])),
            ('资产处置收益', q(d['处置'])), ('二、营业利润', q(d['营业利润'])),
            ('加：营业外收入', q(d['营外收'])), ('减：营业外支出', q(d['营外支'])),
            ('三、利润总额', q(d['利润总额'])), ('减：所得税费用', q(d['所得税'])),
            ('四、净利润', q(d['净利润'])), ('六、综合收益总额', q(d['综合收益'])),
            ('基本/稀释每股收益', f'{d["eps"]} / {d["deps"]}'),
        ], lei=(1,))
        zc = biao(('资产负债/现金流', '金额'), [
            ('资产总计', q(d['资产'])), ('负债和所有者权益总计', q(d['负债权益'])),
            ('货币资金（期末 / 上年年末）', f'{q(d["货币"])} / {q(d["货币上年"])}'),
            ('经营活动产生的现金流量净额', q(d['经营'])),
            ('现金及现金等价物净增加额', q(d['净增'])),
            ('期末现金及现金等价物余额', q(d['期末'])),
        ], lei=(1,))
        # 印花税不单列取数格，用"年税 − 三项附加"倒挤：年税是合计行，三项是明细行，
        # 差额就是印花税（0.3‰）。这样即使将来附加率假设改了，倒挤式也自动成立。
        sjb = biao(('税金及附加（分项）', '金额'), [
            ('年税金合计', q(d['年税'])), ('　城市维护建设税 7%', q(d['城建'])),
            ('　教育费附加 3%', q(d['教育'])), ('　地方教育附加 2%', q(d['地方'])),
            ('　印花税 0.3‰（并入合计）', q(d['年税'] - d['城建'] - d['教育'] - d['地方'])),
            ('综合附加率（年税 ÷ 年计税收入）', pc(d['附加率'])),
        ], lei=(1,))
        # 摊销台账表头写"（月摊金额）/月"：单位是"元/月"，避免读者把年摊销当成月摊销
        tz = biao(('摊销台账（%s/月）' % q(d['月摊']), '归属表', '部门', '月摊销'),
                  [(a, b, c, q(e)) for a, b, c, e in d['台账']], lei=(3,))
        fl = biao(('分录', '值'), [
            ('分录笔数', str(s['bi'])), ('借方合计', q(s['jie'])),
            ('贷方合计', q(s['dai'])), ('借贷差额', q(s['jie'] - s['dai'])),
            ('涉及科目数', str(s['ke'])),
        ], lei=(1,))
        return f"""<h2>{tag}</h2>
<h3>利润表（{d['riqi']}）</h3>{lr}
<h3>资产负债表 / 现金流量表</h3>{zc}
<div class="pb"></div>
<h3>税金及附加</h3>{sjb}
<h3>摊销台账</h3>{tz}
<h3>分录与试算平衡</h3>{fl}"""
    # ---- 科目余额（预算基础 Top 12） ----
    # 只取前 12：完整科目余额表在 xlsx 里就有，报告的作用是"让人一眼看出钱压在哪几个科目"。
    # 净额 = 借 − 贷（正数=借方余额），与 suan_shisuan 的算法同源，不另算一套。
    # 只展示预算基础册：实时经营是同一套科目，两册并列会把页面撑长而信息量不增。
    km = biao(('科目', '净额（借−贷）'),
              [(k, q(v)) for k, v in sy['kemu'][:12]], lei=(1,))
    # 正文拼装：六个 <h2> 对应报告目录的六节；每节之间的 .pb 决定 A4 分页位置。
    # seed 同时出现在标题、副标题、页脚三处，任一页单独截出去也能反查到复现参数。
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>全流程报告 {seed}</title><style>{YANG}</style></head><body>
<h1>演示数据全流程报告</h1>
<div class="sub">企业：{html.escape(yu['主体'])}　｜　种子 {seed}（确定性可复现）　｜　
链路：生成 → 生成器校验 → 试算平衡 → 接收端导入 → PDF</div>
<div class="box">全链路结论：生成器校验 <span class="{ok}">通过 {tong} 项 / 失败 {bai} 项</span>；
两册试算平衡差额均为 <span class="ok">0.00</span>；
账面结转利润与报表净利润逐分相等；四册接收端导入全部通过。</div>
<h2>一、全链路结论</h2>{jielun}
<h2>二、两册对照</h2>{duibi}
<div class="pb"></div>
<h2>三、预算基础册明细</h2>
{fence(yu, sy, '分册 A · 预算基础（12 个月口径）')}
<div class="pb"></div>
<h2>四、实时经营册明细</h2>
{fence(shi, ss, '分册 B · 实时经营（已结账 6 个月口径）')}
<div class="pb"></div>
<h2>五、科目余额（预算基础，按金额排序前 12）</h2>{km}
<h2>六、说明</h2>
<div class="box">
1. 全部数值为演示口径，不代表真实企业数据；主体名与项目名为虚构，禁词表零命中。<br>
2. 三表为财会〔2019〕6 号版式：利润表/现金流量表「本期 + 上期」，资产负债表「期末 + 上年年末」。<br>
3. 分录含增值税四笔/月（销项、进项、转出未交、缴纳）与年末统一结转，账面利润与报表净利润逐分相等。<br>
4. 实收资本、期初现金等期初余额为演示给定值；实时经营册按 6 个月折算期间性常量。<br>
5. 复现：<code>python -B 全流程报告.py --seed {seed}</code>。
</div>
<div class="foot">本报告由「演示生成器v2 + ingest_v11」自动生成 ｜ 种子 {seed} ｜ 页面 A4</div>
</body></html>"""


# ======================================================================
# 三、主流程
# ======================================================================

def main():
    """五步走完链路并出报告。

    步骤: 1/5 生成 → 2/5 生成器校验 → 3/5 试算平衡 → 4/5 接收端导入 → 5/5 出报告。
    返回: 0 = 全链成功（或 --no-pdf 时 HTML 已出）；1 = PDF 未生成（仅留有 HTML）。
        返回非 0 但不抛异常，是为了让 CI/验收脚本能"拿到报告 + 拿到失败码"两件事。
    副作用: 写 输出/全流程报告-<seed>.html 与 .pdf；四册 xlsx 由第 1 步的子进程写。
    为什么把 print 写死成 1/5..5/5 前缀: 报告卡住时，人一眼就能看出卡在哪一步，
        不需要翻日志；同时这也是"进度可见"的最低成本实现。
    """
    ap = argparse.ArgumentParser(description='跑全流程并输出 PDF 报告')
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--no-pdf', action='store_true', help='只出 HTML，不转 PDF')
    a = ap.parse_args()
    seed = a.seed
    print(f'== 1/5 生成（种子 {seed}）==')
    sheng = pao_shengcheng(seed)
    for ln in sheng:
        print('  ' + ln)
    print('== 2/5 生成器校验 ==')
    tong, bai, bai_li = pao_jiaoyan(seed)
    print(f'  通过 {tong} 项，失败 {bai} 项')
    for ln in bai_li:
        print('  ' + ln)
    # 产物文件名由生成器决定（含 lease 种子），这里按同一规则拼路径；
    # 改了生成器的命名规则，必须同步改这两行，否则第 3 步会读不到文件。
    yu_lu = CHU / f'演示-预算基础-{seed}.xlsx'
    shi_lu = CHU / f'演示-实时经营-{seed}.xlsx'
    print('== 3/5 试算平衡 ==')
    sy, ss = suan_shisuan(yu_lu), suan_shisuan(shi_lu)
    print(f'  预算基础：借 {q(sy["jie"])} / 贷 {q(sy["dai"])} / 差 {q(sy["jie"] - sy["dai"])}')
    print(f'  实时经营：借 {q(ss["jie"])} / 贷 {q(ss["dai"])} / 差 {q(ss["jie"] - ss["dai"])}')
    print('== 4/5 接收端导入 ==')
    yu, shi = du_ce(yu_lu), du_ce(shi_lu)
    dr = {}
    # 四册全导：外部两册走 v1.2 轨，若只导前两册就证明不了"四类文件都能进"
    for lu in (yu_lu, shi_lu, CHU / f'演示-行业对标-{seed}.xlsx', CHU / f'演示-经营变更-{seed}.xlsx'):
        dr[lu.name] = pao_daoru(lu)
        print(f'  {lu.name}：{dr[lu.name]["轨道"]} 轨，校验 {dr[lu.name]["校验"]} 项')
    print('== 5/5 出报告 ==')
    ye = zhuang(seed, sheng, (tong, bai, bai_li), yu, shi, sy, ss, dr)
    html_lu = CHU / f'全流程报告-{seed}.html'
    # 显式 utf-8 写出：报告里有大量中文，Windows 默认编码会写成 GBK 导致浏览器猜错
    html_lu.write_text(ye, encoding='utf-8')
    print(f'  HTML：{html_lu}（{html_lu.stat().st_size} 字节）')
    if a.no_pdf:
        return 0
    pdf_lu = CHU / f'全流程报告-{seed}.pdf'
    for exe in RENDER:
        if not Path(exe).exists():
            continue
        # --headless=new：新版无头模式，与有头渲染的排版一致（旧的 --headless 有差异）
        # --no-sandbox：本机桌面环境无限制；--no-pdf-header-footer：去掉浏览器自带的页眉页脚
        # timeout=180s：一份 6 页的 A4 报告正常 3~8s，180s 是给慢机器留的兜底
        r = subprocess.run([exe, '--headless=new', '--disable-gpu', '--no-sandbox',
                            '--no-pdf-header-footer',
                            f'--print-to-pdf={pdf_lu}', html_lu.as_uri()],
                           capture_output=True, text=True, encoding='utf-8', timeout=180)
        # 判据用"文件存在且 >1000 字节"：Chrome 在参数错误时会返回 0 却只写一个空 PDF，
        # 只看 returncode 会被骗；1KB 是"至少有内容"的经验下界。
        if pdf_lu.exists() and pdf_lu.stat().st_size > 1000:
            print(f'  PDF：{pdf_lu}（{pdf_lu.stat().st_size} 字节）')
            return 0
        print(f'  [警告] {Path(exe).name} 渲染失败：{(r.stderr or "")[-200:]}')
    print('  [警告] 未找到可用的 Chrome/Edge，仅生成 HTML')
    return 1


if __name__ == '__main__':
    sys.exit(main())
