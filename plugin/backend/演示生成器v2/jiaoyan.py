# -*- coding: utf-8 -*-
"""校验器：对生成产物做数值级验收（读回 xlsx 逐条核对）。

六道门：
    1) 零公式      —— 全簿无一格以 '=' 开头
    2) 全填        —— 三表科目行 × 数据列、九表数字位，全部是数字
    3) 恒等式      —— 收入/成本/税金/三费/摊销/现金链/资负平衡/分录借贷/对照
    4) 尺寸回读    —— 列宽/行高/合并区/冻结窗格与版式常量逐项一致
    5) 名称        —— 占位符已渲染、禁词零残留
    6) 确定性      —— 同种子两次生成逐格一致

用法：python -B jiaoyan.py [--seed 20260923]
"""
import argparse
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from banshi import JIU_BIAO, SAN_BIAO, SHEETS, WAI_BIAO
from mingcheng import JIN_CI
from shuju import YUE_LIE

MU = Path(__file__).resolve().parent
RONG_CHA = Decimal('0.005')          # 分币容差
TONG, YI = [], []


def rd2(v):
    """四舍五入到分（与模型同口径：HALF_UP）。"""
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def rd4(v):
    """四舍五入到四位小数（与模型同口径）。"""
    return Decimal(v).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def jian(ming, hao, xi=''):
    """登记一项断言结果。"""
    (TONG if hao else YI).append(f'{ming}{("：" + xi) if xi else ""}')
    print(f'  [{"PASS" if hao else "FAIL"}] {ming}' + (f'：{xi}' if xi else ''))
    return hao


def deng(a, b):
    """数值比较（容忍分币尾差）。"""
    return abs(Decimal(str(a or 0)) - Decimal(str(b or 0))) <= RONG_CHA


def shu(v):
    """格值 → Decimal（None → 0）。"""
    return Decimal(str(v)) if isinstance(v, (int, float)) else Decimal(0)


def san_biao_wei(ming):
    """三表"科目行 × 数据列"格位清单（分区标题行不算）。

    财会2019-6号版式：利润表/现金流量表 B=本期金额 C=上期金额；
    资产负债表 左 B=期末余额 C=上年年末余额，右 E=期末余额 F=上年年末余额。
    """
    bq = SAN_BIAO[ming]['biaoqian']
    if ming == '利润表':
        hang = [r for r in range(5, 48) if isinstance(bq.get(f'A{r}'), str)
                and not bq[f'A{r}'].strip().endswith('：')]
        return [f'{x}{r}' for r in hang for x in 'BC']
    if ming == '资产负债表':
        ge = []
        for r in range(5, 46):
            for zhu, lie in (('A', 'BC'), ('D', 'EF')):
                v = bq.get(f'{zhu}{r}')
                if isinstance(v, str) and not v.strip().endswith('：'):
                    ge += [f'{x}{r}' for x in lie]
        return ge
    hang = [r for r in range(5, 43) if isinstance(bq.get(f'A{r}'), str)
            and not bq[f'A{r}'].strip().endswith('：')]
    return [f'{x}{r}' for r in hang for x in 'BC']


def men_ling_gongshi(ws_all):
    """1) 零公式。"""
    ji = [f'{s}!{c.coordinate}' for s, ws in ws_all.items()
          for row in ws.iter_rows() for c in row
          if isinstance(c.value, str) and c.value.startswith('=')]
    return jian('零公式（全簿无一格公式）', not ji, str(ji[:4]))


def men_quantian(ws_all, biao_ji=None, san_biao=True, yao_shuzi=True):
    """2) 全填：三表科目行（可选）+ 版式里登记的全部数值位。

    yao_shuzi=True（十二表）：数值位必须是数字；
    yao_shuzi=False（外部册）：数值位允许文本（编码/日期等），但不得为空。
    """
    def you_xiao(v):
        if v is None:
            return False
        if isinstance(v, str):
            return (not yao_shuzi) and bool(v.strip())
        return isinstance(v, (int, float))

    que = []
    biao_ji = biao_ji if biao_ji is not None else JIU_BIAO
    if san_biao:
        for ming in ('利润表', '资产负债表', '现金流量表'):
            ws = ws_all[ming]
            for ref in san_biao_wei(ming):
                if not isinstance(ws[ref].value, (int, float)):
                    que.append(f'{ming}!{ref}')
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for ref in ban['shuzhi_wei']:
            if not you_xiao(ws[ref].value):
                que.append(f'{ming}!{ref}')
    return jian('全填（科目行/数值位全部有数）', not que, f'缺 {len(que)}：{que[:4]}')


def men_hengdeng(ws_all):
    """3) 恒等式（数值级）。"""
    ok = True
    fei, xj, zf = ws_all['费用表月度汇总'], ws_all['现金流量表'], ws_all['资产负债表']
    sj, tx, fl, lr = (ws_all['税金及附加'], ws_all['摊销明细'],
                      ws_all['分录'], ws_all['利润表'])
    # 3.1 税金及附加：城建7%/教育3%/地方2%/文化0（按增值税应纳额）+ 印花税并入合计
    ci = []
    lie_fen31 = ('Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB')
    for i, m in enumerate(YUE_LIE):
        x = lie_fen31[i]                                 # Z3 分档区的月列是 Q..AB
        tong = shu(sj[f'{m}33'].value)
        a, b, c, d = (shu(sj[f'{x}{r}'].value) for r in (123, 124, 125, 126))
        if tong < 0:
            ci.append(f'{m}33')
        if not deng(d, 0):
            ci.append(f'{m}126')
        if a and abs(b - rd2(a * Decimal('3') / Decimal('7'))) > Decimal('0.05'):
            ci.append(f'{m}124')
        if a and abs(c - rd2(a * Decimal('2') / Decimal('7'))) > Decimal('0.05'):
            ci.append(f'{m}125')
        if tong < a + b + c + d:                        # 印花税并入后合计不得小于四税之和
            ci.append(f'{m}印花税为负')
        # 老区行映射（05 文档 §4.1）：B6=合计、B7..B10=四税、B4=0、B3=增值税应纳额
        if not deng(sj[f'{m}6'].value, tong):
            ci.append(f'{m}6≠{m}33')
        for hang, v in ((7, a), (8, b), (9, c), (10, d)):
            if not deng(sj[f'{m}{hang}'].value, v):
                ci.append(f'{m}{hang}')
        if not deng(sj[f'{m}4'].value, 0):
            ci.append(f'{m}4')
        zeng = shu(sj[f'{m}3'].value)
        if zeng < 0 or not deng(a, rd2(zeng * Decimal('0.07'))):
            ci.append(f'{m}3')
        if zeng and abs((a + b + c) - rd2(zeng * Decimal('0.12'))) > Decimal('0.02'):
            ci.append(f'{m}附加合计12%')
    nian_shou = sum((shu(sj[f'{m}32'].value) for m in YUE_LIE), Decimal(0))
    nian_shui = sum((shu(sj[f'{m}33'].value) for m in YUE_LIE), Decimal(0))
    if nian_shou and not deng(sj['C31'].value, rd4(nian_shui / nian_shou)):
        ci.append('C31')
    ok &= jian('税金及附加：城建7%/教育3%/地方2%/文化0 + 印花税并入', not ci, str(ci[:4]))
    # 3.3 分档税：逐月合计 = 税金及附加；年合计 = 12 月之和
    lie_fen = ('Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB')
    ci = []
    for i, x in enumerate(lie_fen):
        if not deng(sj[f'{x}127'].value, sj[f'{YUE_LIE[i]}33'].value):
            ci.append(f'{x}127')
    for j in range(4):
        if not deng(sj[f'AC{123 + j}'].value,
                    sum(shu(sj[f'{x}{123 + j}'].value) for x in lie_fen)):
            ci.append(f'AC{123 + j}')
    ok &= jian('分档税合计 = 税金及附加（逐月 + 年合计）', not ci, str(ci[:4]))
    # 3.4 三费：合计行 = 明细之和；三费及税金 = 合计 + 附加；汇总 = 三表之和
    ci = []
    for s in ('销售费用', '管理费用'):
        ws = ws_all[s]
        for m in YUE_LIE:
            if not deng(ws[f'{m}34'].value,
                        sum(shu(ws[f'{m}{r}'].value) for r in range(4, 34))):
                ci.append(f'{s}!{m}34')
            if not deng(ws[f'{m}36'].value, shu(ws[f'{m}34'].value) + shu(ws[f'{m}35'].value)):
                ci.append(f'{s}!{m}36')
        for m in YUE_LIE:
            if not deng(ws[f'{m}35'].value, sj[f'{m}33'].value):
                ci.append(f'{s}!{m}35')
    for m in YUE_LIE:
        for r in range(4, 37):
            he = sum(shu(ws_all[s][f'{m}{r}'].value) for s in ('销售费用', '管理费用'))
            if not deng(fei[f'{m}{r}'].value, he):
                ci.append(f'费用表月度汇总!{m}{r}')
    ok &= jian('费用：合计/含税合计/月度汇总（两表之和）逐月', not ci, str(ci[:6]))
    # 3.5 摊销：本月摊销 = ROUND(原值/月数)；矩阵合计 = 本月摊销；累计 + 尚未 = 原值
    ci = []
    yue_lie = {m: chr(ord(m) - 1) for m in YUE_LIE}       # 平移后月份列 C..N → B..M
    for m, x in yue_lie.items():
        if not deng(tx[f'{x}3'].value, rd2(shu(tx['B1'].value) / shu(tx['B2'].value))):
            ci.append(f'{x}3')
        if not deng(tx[f'{x}5'].value, shu(tx[f'{x}1'].value) - shu(tx[f'{x}4'].value)):
            ci.append(f'{x}5')
    for x in ('B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M'):
        if not deng(tx[f'{x}29'].value, shu(tx['B3'].value)):
            ci.append(f'{x}29')
    for i in range(8):
        if not deng(tx[f'G{10 + i}'].value,
                    rd2(shu(tx[f'E{10 + i}'].value) / max(shu(tx[f'F{10 + i}'].value), 1))):
            ci.append(f'G{10 + i}')
    # 三表行 20（折旧及摊销）= 摊销明细当月矩阵合计，按台账归属到各费用表（17-T2 口径）
    for m, x in yue_lie.items():
        he20 = sum((shu(ws_all[s][f'{m}20'].value) for s in ('销售费用', '管理费用')),
                   Decimal(0))
        if he20 > 0 and not deng(he20, shu(tx[f'{x}3'].value)):
            ci.append(f'{m}行20')
    ok &= jian('摊销：本月摊销/尚未摊销/矩阵合计/台账归属行20', not ci, str(ci[:4]))
    # 3.6 现金链（本期 B / 上期 C）+ 与资负货币资金衔接
    ci = []
    for x in ('B', 'C'):
        if not deng(xj[f'{x}9'].value, sum(shu(xj[f'{x}{r}'].value) for r in (6, 7, 8))):
            ci.append(f'{x}9')
        if not deng(xj[f'{x}14'].value,
                    sum(shu(xj[f'{x}{r}'].value) for r in (10, 11, 12, 13))):
            ci.append(f'{x}14')
        if not deng(xj[f'{x}15'].value, shu(xj[f'{x}9'].value) - shu(xj[f'{x}14'].value)):
            ci.append(f'{x}15')
        if not deng(xj[f'{x}22'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(17, 22))):
            ci.append(f'{x}22')
        if not deng(xj[f'{x}27'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(23, 27))):
            ci.append(f'{x}27')
        if not deng(xj[f'{x}28'].value, shu(xj[f'{x}22'].value) - shu(xj[f'{x}27'].value)):
            ci.append(f'{x}28')
        if not deng(xj[f'{x}33'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(30, 33))):
            ci.append(f'{x}33')
        if not deng(xj[f'{x}37'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(34, 37))):
            ci.append(f'{x}37')
        if not deng(xj[f'{x}38'].value, shu(xj[f'{x}33'].value) - shu(xj[f'{x}37'].value)):
            ci.append(f'{x}38')
        if not deng(xj[f'{x}40'].value,
                    sum(shu(xj[f'{x}{r}'].value) for r in (15, 28, 38, 39))):
            ci.append(f'{x}40')
        if not deng(xj[f'{x}42'].value, shu(xj[f'{x}40'].value) + shu(xj[f'{x}41'].value)):
            ci.append(f'{x}42')
    if not deng(xj['B42'].value, zf['B6'].value):
        ci.append('本期期末↔资负货币资金期末')
    if not deng(xj['B41'].value, zf['C6'].value):
        ci.append('本期期初↔资负货币资金上年年末')
    if not deng(xj['C42'].value, xj['B41'].value):
        ci.append('上期期末↔本期期初')
    ok &= jian('现金链：小计/净额/净增加/期末，且与资负货币资金衔接', not ci, str(ci[:4]))
    # 3.7 资负：两栏小计合计 + 平衡（左 B/C、右 E/F）
    ci = []
    for x in ('B', 'C'):
        if not deng(zf[f'{x}19'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(6, 19))):
            ci.append(f'{x}19')
        if not deng(zf[f'{x}39'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(21, 39))):
            ci.append(f'{x}39')
        if not deng(zf[f'{x}40'].value, shu(zf[f'{x}19'].value) + shu(zf[f'{x}39'].value)):
            ci.append(f'{x}40')
    for x in ('E', 'F'):
        if not deng(zf[f'{x}19'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(6, 19))):
            ci.append(f'{x}19')
        if not deng(zf[f'{x}31'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(21, 31))):
            ci.append(f'{x}31')
        if not deng(zf[f'{x}32'].value, shu(zf[f'{x}19'].value) + shu(zf[f'{x}31'].value)):
            ci.append(f'{x}32')
        if not deng(zf[f'{x}44'].value,
                    sum(shu(zf[f'{x}{r}'].value) for r in (34, 35, 38, 39, 40, 41, 42, 43))):
            ci.append(f'{x}44')
        if not deng(zf[f'{x}45'].value, shu(zf[f'{x}32'].value) + shu(zf[f'{x}44'].value)):
            ci.append(f'{x}45')
    if not deng(zf['B40'].value, zf['E45'].value):
        ci.append('期末不平衡')
    if not deng(zf['C40'].value, zf['F45'].value):
        ci.append('上年年末不平衡')
    ok &= jian('资负：小计/合计/两栏平衡（期末 + 上年年末）', not ci, str(ci[:4]))
    # 3.8 利润表：行间关系（本期 B / 上期 C）
    ci = []
    for x in ('B', 'C'):
        if not deng(lr[f'{x}23'].value,
                    sum(shu(lr[f'{x}{r}'].value) * k for r, k in
                        ((5, 1), (6, -1), (7, -1), (8, -1), (9, -1), (10, -1), (11, -1),
                         (14, 1), (15, 1), (17, 1), (18, 1), (19, 1), (20, 1), (21, 1),
                         (22, 1)))):
            ci.append(f'{x}23')
        if not deng(lr[f'{x}26'].value,
                    shu(lr[f'{x}23'].value) + shu(lr[f'{x}24'].value) - shu(lr[f'{x}25'].value)):
            ci.append(f'{x}26')
        if not deng(lr[f'{x}28'].value, shu(lr[f'{x}26'].value) - shu(lr[f'{x}27'].value)):
            ci.append(f'{x}28')
        if shu(lr[f'{x}26'].value) > 0 and not deng(
                lr[f'{x}27'].value, rd2(shu(lr[f'{x}26'].value) * Decimal('0.25'))):
            ci.append(f'{x}27')
        if not deng(lr[f'{x}32'].value,
                    sum(shu(lr[f'{x}{r}'].value) for r in (33, 34, 35, 36))):
            ci.append(f'{x}32')
        if not deng(lr[f'{x}37'].value,
                    sum(shu(lr[f'{x}{r}'].value) for r in range(38, 44))):
            ci.append(f'{x}37')
        if not deng(lr[f'{x}31'].value, shu(lr[f'{x}32'].value) + shu(lr[f'{x}37'].value)):
            ci.append(f'{x}31')
        if not deng(lr[f'{x}44'].value, shu(lr[f'{x}28'].value) + shu(lr[f'{x}31'].value)):
            ci.append(f'{x}44')
        if not deng(lr[f'{x}29'].value, shu(lr[f'{x}28'].value)):
            ci.append(f'{x}29')
        if not deng(lr[f'{x}46'].value, rd4(shu(lr[f'{x}28'].value) / Decimal('1000000'))):
            ci.append(f'{x}46')
        if not deng(lr[f'{x}47'].value,
                    rd4(shu(lr[f'{x}28'].value) * Decimal('0.98') / Decimal('1000000'))):
            ci.append(f'{x}47')
    ok &= jian('利润表：营业利润/利润总额/净利润/综合收益/每股收益', not ci, str(ci[:4]))
    # 3.9 分录：借贷平衡 + 对照合计 = 现金流量表同位
    ci = []
    # 合计行由写出器按数据末尾落位 → 按标签动态定位
    he_hang = {}
    for r in range(2, fl.max_row + 1):
        v = fl[f'A{r}'].value
        if v in ('全部借方合计', '全部贷方合计', '借贷差额（应为0）'):
            he_hang[v] = r
    jie_r = he_hang.get('全部借方合计', 0)
    dai_r = he_hang.get('全部贷方合计', 0)
    cha_r = he_hang.get('借贷差额（应为0）', 0)
    if not (jie_r and dai_r and cha_r):
        ci.append('缺合计行')
    if jie_r and dai_r and not deng(fl[f'E{jie_r}'].value, fl[f'F{dai_r}'].value):
        ci.append('借贷不平衡')
    if cha_r and not deng(fl[f'G{cha_r}'].value, 0):
        ci.append('差额≠0')
    jie = {}
    for r in range(2, jie_r or 2):
        dui = fl[f'G{r}'].value
        if isinstance(dui, (int, float)):
            jie[int(dui)] = jie.get(int(dui), Decimal(0)) + shu(fl[f'E{r}'].value)
    for hang, he in jie.items():
        if not deng(he, xj[f'B{hang}'].value):
            ci.append(f'对照{hang}行')
    # 对照须覆盖现金流量表全部"取数行"（有数就必须有分录兜着）
    qu_shu_hang = (6, 7, 8, 10, 11, 12, 13, 17, 18, 19, 20, 21, 23, 24, 25, 26,
                   30, 31, 32, 34, 35, 36)
    lou = [r for r in qu_shu_hang if shu(xj[f'B{r}'].value) != 0 and r not in jie]
    if lou:
        ci.append(f'未覆盖行{lou}')
    ok &= jian('分录：借贷平衡 + 对照覆盖并等于现金流量表', not ci, str(ci[:6]))
    return ok


def men_chicun(ws_all, biao_ji=None):
    """4) 尺寸回读：列宽/行高/合并/冻结。"""
    ci = []
    biao_ji = biao_ji if biao_ji is not None else {
        m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for i, kuan in ban['lie_kuan'].items():
            zhi = ws.column_dimensions[get_column_letter(int(i))].width
            if zhi is None or abs(float(zhi) - float(kuan)) > 0.01:
                ci.append(f'{ming}!列{i}')
        for r, gao in ban['hang_gao'].items():
            zhi = ws.row_dimensions[int(r)].height
            if zhi is None or abs(float(zhi) - float(gao)) > 0.01:
                ci.append(f'{ming}!行{r}')
        if ban['hang_gao_mo_ren'] and (
                ws.sheet_format.defaultRowHeight is None
                or abs(float(ws.sheet_format.defaultRowHeight)
                       - float(ban['hang_gao_mo_ren'])) > 0.01):
            ci.append(f'{ming}!默认行高')
        if sorted(str(m) for m in ws.merged_cells.ranges) != sorted(ban['hebing']):
            ci.append(f'{ming}!合并区')
        if (str(ws.freeze_panes) if ws.freeze_panes else None) != (ban.get('freeze') or None):
            ci.append(f'{ming}!冻结')
    return jian('尺寸回读：列宽/行高/默认行高/合并区/冻结', not ci, str(ci[:6]))


def men_mingcheng(ws_all):
    """5) 名称：占位符清零 + 禁词零残留。"""
    liu = [f'{s}!{c.coordinate}' for s, ws in ws_all.items()
           for row in ws.iter_rows() for c in row
           if isinstance(c.value, str) and ('{' in c.value or any(j in c.value for j in JIN_CI))]
    return jian('名称：占位符已渲染、禁词零残留', not liu, str(liu[:4]))


def men_heimingdan(ws_all, biao_ji=None):
    """黑名单：非零数值零命中（豁免：零值 / 三表行次 / 分录对照代码列）。"""
    from shuju import ming_zhong
    ci = []
    biao_ji = biao_ji if biao_ji is not None else {
        m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not isinstance(v, (int, float)) or v == 0:
                    continue
                if ming == '分录' and c.column_letter == 'G':       # 对照行号代码（非金额）
                    continue
                bq = ban['biaoqian'].get(c.coordinate)
                if isinstance(bq, (int, float)):                    # 版式自带结构数（三表行次）
                    continue
                if ming_zhong(Decimal(str(v))):
                    ci.append(f'{ming}!{c.coordinate}')
    return jian('黑名单：非零数值零命中（豁免零值/行次/对照列）', not ci, str(ci[:6]))


def men_yangshi(ws_all, biao_ji=None):
    """样式复刻：逐格比对（字体/填充/边框/对齐；数字格式另按规则，不参与比对）。"""
    from _tiqu_banshi import yang_shi_qian
    ci = []
    biao_ji = biao_ji if biao_ji is not None else {
        m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for ref, idx in ban['ge_ys'].items():
            if ws[ref].value is None and ref not in ban['biaoqian']:
                continue
            if tuple(yang_shi_qian(ws[ref]))[:16] != ban['yangshi'][idx][:16]:
                ci.append(f'{ming}!{ref}')
                if len(ci) >= 8:
                    break
    return jian('样式复刻（字体/填充/边框/对齐逐格一致）', not ci, str(ci[:8]))


def du_qu(lu):
    """读回十二表产物：{表名: 工作表}。"""
    wb = load_workbook(lu)
    return wb, {s: wb[s] for s in SHEETS}


def du_qu_wai(lu):
    """读回外部册：按实际表名取。"""
    wb = load_workbook(lu)
    return wb, {s: wb[s] for s in wb.sheetnames}


def _ge_ji(ws_all):
    """全簿格值快照（确定性比对用）。"""
    return {s: {c.coordinate: c.value for row in ws.iter_rows() for c in row}
            for s, ws in ws_all.items()}


def main():
    ap = argparse.ArgumentParser(description='演示工作簿校验器（十二表两册 + 外部两册）')
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--out', default=None, help='产物目录（默认 ./输出）')
    ap.add_argument('--hangye', default=None, help='强制行业词（多行业回归用）')
    ap.add_argument('--zhuti', default=None, help='强制主体名（多行业回归用）')
    a = ap.parse_args()
    import shengcheng
    chu = Path(a.out) if a.out else (MU / '输出')
    print('== 生成四册 ==')
    si_ce = shengcheng.sheng_si_ce(a.seed, chu, a.hangye, a.zhuti)
    for p in si_ce:
        print(f'  {p.name}（{p.stat().st_size} 字节）')
    # ---- 十二表两册 ----
    for leibie in shengcheng.SHI_ER:
        print(f'== 校验：十二表 / {leibie} ==')
        lu = next(p for p in si_ce if p.stem.startswith(f'演示-{leibie}-{a.seed}'))
        wb, ws_all = du_qu(lu)
        men_ling_gongshi(ws_all)
        men_quantian(ws_all)
        men_hengdeng(ws_all)
        men_chicun(ws_all)
        men_heimingdan(ws_all)
        men_yangshi(ws_all)
        men_mingcheng(ws_all)
        ge1 = _ge_ji(ws_all)
        wb.close()
        wb2, ws2 = du_qu(shengcheng.sheng(a.seed, leibie, chu, a.hangye, a.zhuti))
        ge2 = _ge_ji(ws2)
        wb2.close()
        bu = [f'{s}!{k}' for s in ge1 for k in ge1[s] if ge1[s][k] != ge2[s].get(k)]
        jian(f'[{leibie}] 确定性：同种子两次生成逐格一致', not bu, str(bu[:4]))
    # ---- 外部两册 ----
    for zhong in shengcheng.WAI:
        print(f'== 校验：外部册 / {zhong} ==')
        lu = next(p for p in si_ce if p.stem.startswith(f'演示-{zhong}-{a.seed}'))
        ban = WAI_BIAO[zhong]
        wb, ws_all = du_qu_wai(lu)
        men_ling_gongshi(ws_all)
        men_quantian(ws_all, ban, san_biao=False, yao_shuzi=False)
        men_chicun(ws_all, ban)
        men_heimingdan(ws_all, ban)
        men_yangshi(ws_all, ban)
        men_mingcheng(ws_all)
        ge1 = _ge_ji(ws_all)
        wb.close()
        wb2, ws2 = du_qu_wai(shengcheng.sheng_wai(a.seed, zhong, chu, a.hangye, a.zhuti))
        ge2 = _ge_ji(ws2)
        wb2.close()
        bu = [f'{s}!{k}' for s in ge1 for k in ge1[s] if ge1[s][k] != ge2[s].get(k)]
        jian(f'[{zhong}] 确定性：同种子两次生成逐格一致', not bu, str(bu[:4]))
    print()
    print('==== 摘要 ====')
    print(f'通过 {len(TONG)} 项，失败 {len(YI)} 项')
    for f in YI:
        print('  FAIL:', f)
    return 0 if not YI else 1


if __name__ == '__main__':
    sys.exit(main())
