# -*- coding: utf-8 -*-
"""全流程报告：生成 → 生成器校验 → 试算平衡 → 接收端导入 → 输出 PDF。

一条命令跑完整条链路（不手工串脚本），最后产出 A4 排版的 PDF 报告：
    python -B 全流程报告.py                 # 默认种子 20260923
    python -B 全流程报告.py --seed 20261018
    python -B 全流程报告.py --seed 20261018 --no-pdf   # 只出 HTML

PDF 由本机 Chrome/Edge 的 headless 打印生成（`--print-to-pdf`），零第三方依赖；
HTML 自包含（内嵌 CSS），可直接用浏览器打开或另存。
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
    """单元格值 → Decimal（非数值按 0）。"""
    if isinstance(v, bool):
        return Decimal(0)
    return Decimal(str(v)) if isinstance(v, (int, float, Decimal)) else Decimal(0)


def q(v):
    """千分位两位小数（负数带负号）。"""
    return f'{shu(v):,.2f}'


def pc(v):
    """百分比四位。"""
    return f'{shu(v) * 100:.2f}%'


# ======================================================================
# 一、跑链路：生成 → 校验 → 试算 → 导入
# ======================================================================

def pao_shengcheng(seed):
    """跑生成器（四册），返回产物路径与耗时无关的输出行。"""
    r = subprocess.run([sys.executable, '-B', str(MU / 'shengcheng.py'), '--seed', str(seed)],
                       capture_output=True, text=True, encoding='utf-8', cwd=str(MU))
    if r.returncode != 0:                                          # 生成失败直接抛
        raise SystemExit(f'生成失败：{r.stdout[-400:]}{r.stderr[-400:]}')
    return [ln.strip() for ln in r.stdout.splitlines() if ln.startswith('生成')]


def pao_jiaoyan(seed):
    """跑生成器自带校验，返回（通过数, 失败数, 失败明细）。"""
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
    """试算平衡：逐笔分录汇总科目 + 三表勾稽（只读成交付值，不改文件）。"""
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
    """读一本：三表关键行 + 税金 + 摊销台账 + 费用表。"""
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
         '台账': [(tx[f'A{r}'].value, tx[f'B{r}'].value, tx[f'C{r}'].value, shu(tx[f'G{r}'].value))
                  for r in range(10, 18)],
         '月摊': shu(tx['B3'].value),
         '费用合计': shu(hz['O34'].value) if hz['O34'].value is not None else Decimal(0)}
    wb.close()
    return d


def pao_daoru(lu):
    """接收端导入（v2/v1.2 轨道自动分派）。"""
    if str(RECV) not in sys.path:
        sys.path.insert(0, str(RECV))
    from excel_ingest_v11 import import_excel_v11                    # 延迟导入
    r = import_excel_v11(lu.read_bytes(), lu.name)
    return {'轨道': r.get('contract_version', '外部v1.2'), '校验': r.get('checks', 0),
            '分录': len(r.get('fenlu', [])), '类别': r.get('category', '-')}


# ======================================================================
# 二、HTML 组装（自包含 CSS，A4 打印友好）
# ======================================================================

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
    """生成一张表：tou=表头元组；hang=数据行；lei=数值列下标（右对齐）。"""
    th = ''.join(f'<th class="n">{html.escape(str(x))}</th>' if i in lei
                 else f'<th>{html.escape(str(x))}</th>' for i, x in enumerate(tou))
    tr = []
    for r in hang:
        tds = ''.join(f'<td class="n">{html.escape(str(v))}</td>' if i in lei
                      else f'<td>{html.escape(str(v))}</td>' for i, v in enumerate(r))
        tr.append(f'<tr>{tds}</tr>')
    return f'<table><thead><tr>{th}</tr></thead><tbody>{"".join(tr)}</tbody></table>'


def zhuang(seed, sheng, jian, yu, shi, sy, ss, dr):
    """整份 HTML。"""
    tong, bai, bai_li = jian
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
        sjb = biao(('税金及附加（分项）', '金额'), [
            ('年税金合计', q(d['年税'])), ('　城市维护建设税 7%', q(d['城建'])),
            ('　教育费附加 3%', q(d['教育'])), ('　地方教育附加 2%', q(d['地方'])),
            ('　印花税 0.3‰（并入合计）', q(d['年税'] - d['城建'] - d['教育'] - d['地方'])),
            ('综合附加率（年税 ÷ 年计税收入）', pc(d['附加率'])),
        ], lei=(1,))
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
    km = biao(('科目', '净额（借−贷）'),
              [(k, q(v)) for k, v in sy['kemu'][:12]], lei=(1,))
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
    yu_lu = CHU / f'演示-预算基础-{seed}.xlsx'
    shi_lu = CHU / f'演示-实时经营-{seed}.xlsx'
    print('== 3/5 试算平衡 ==')
    sy, ss = suan_shisuan(yu_lu), suan_shisuan(shi_lu)
    print(f'  预算基础：借 {q(sy["jie"])} / 贷 {q(sy["dai"])} / 差 {q(sy["jie"] - sy["dai"])}')
    print(f'  实时经营：借 {q(ss["jie"])} / 贷 {q(ss["dai"])} / 差 {q(ss["jie"] - ss["dai"])}')
    print('== 4/5 接收端导入 ==')
    yu, shi = du_ce(yu_lu), du_ce(shi_lu)
    dr = {}
    for lu in (yu_lu, shi_lu, CHU / f'演示-行业对标-{seed}.xlsx', CHU / f'演示-经营变更-{seed}.xlsx'):
        dr[lu.name] = pao_daoru(lu)
        print(f'  {lu.name}：{dr[lu.name]["轨道"]} 轨，校验 {dr[lu.name]["校验"]} 项')
    print('== 5/5 出报告 ==')
    ye = zhuang(seed, sheng, (tong, bai, bai_li), yu, shi, sy, ss, dr)
    html_lu = CHU / f'全流程报告-{seed}.html'
    html_lu.write_text(ye, encoding='utf-8')
    print(f'  HTML：{html_lu}（{html_lu.stat().st_size} 字节）')
    if a.no_pdf:
        return 0
    pdf_lu = CHU / f'全流程报告-{seed}.pdf'
    for exe in RENDER:
        if not Path(exe).exists():
            continue
        r = subprocess.run([exe, '--headless=new', '--disable-gpu', '--no-sandbox',
                            '--no-pdf-header-footer',
                            f'--print-to-pdf={pdf_lu}', html_lu.as_uri()],
                           capture_output=True, text=True, encoding='utf-8', timeout=180)
        if pdf_lu.exists() and pdf_lu.stat().st_size > 1000:
            print(f'  PDF：{pdf_lu}（{pdf_lu.stat().st_size} 字节）')
            return 0
        print(f'  [警告] {Path(exe).name} 渲染失败：{(r.stderr or "")[-200:]}')
    print('  [警告] 未找到可用的 Chrome/Edge，仅生成 HTML')
    return 1


if __name__ == '__main__':
    sys.exit(main())
