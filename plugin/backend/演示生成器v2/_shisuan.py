# -*- coding: utf-8 -*-
"""试算平衡（开发期体检）：分录逐笔汇总到科目 + 三表勾稽。

用法：python -B _shisuan.py [产物路径]
"""
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

MU = Path(__file__).resolve().parent


def shu(v):
    return Decimal(str(v)) if isinstance(v, (int, float)) else Decimal(0)


def s(v):
    return f'{v:,.2f}'


def kan(lu):
    wb = load_workbook(lu)
    fl = wb['分录']
    print(f'== 试算平衡：{Path(lu).name} ==')
    # ---- 逐笔取分录 ----
    jie = defaultdict(lambda: Decimal(0))
    dai = defaultdict(lambda: Decimal(0))
    zhang, hang_shu, bu_ping = 0, 0, []
    mo = 1
    for r in range(2, fl.max_row + 1):
        if fl[f'A{r}'].value == '全部借方合计':
            mo = r
            break
    for r in range(2, mo):
        j_ke, d_ke = fl[f'C{r}'].value, fl[f'D{r}'].value
        j_qian, d_qian = shu(fl[f'E{r}'].value), shu(fl[f'F{r}'].value)
        if not j_ke and not d_ke:
            continue
        zhang += 1
        hang_shu += 2
        jie[j_ke] += j_qian
        dai[d_ke] += d_qian
        if j_qian != d_qian:
            bu_ping.append(r)
    he_jie = sum(jie.values(), Decimal(0))
    he_dai = sum(dai.values(), Decimal(0))
    print(f'凭证 {zhang} 张 / 分录 {hang_shu} 行')
    print(f'借方发生额合计 {s(he_jie)}')
    print(f'贷方发生额合计 {s(he_dai)}')
    print(f'差额           {s(he_jie - he_dai)}   '
          f'{"✓ 平衡" if he_jie == he_dai else "✗ 不平"}')
    if bu_ping:
        print(f'  单张不平的行：{bu_ping[:5]}')
    print()
    # ---- 科目试算平衡表 ----
    ke_mu = sorted(set(jie) | set(dai), key=lambda k: -(jie[k] + dai[k]))
    print(f'{"科目":<22}{"借方发生额":>18}{"贷方发生额":>18}{"净额(借-贷)":>18}')
    print('-' * 78)
    jing_he = Decimal(0)
    for k in ke_mu:
        jing = jie[k] - dai[k]
        jing_he += jing
        print(f'{str(k):<22}{s(jie[k]):>18}{s(dai[k]):>18}{s(jing):>18}')
    print('-' * 78)
    print(f'{"合计":<22}{s(he_jie):>18}{s(he_dai):>18}{s(jing_he):>18}   '
          f'{"✓" if jing_he == 0 else "✗"}')
    print()
    # ---- 三表勾稽 ----
    zf, lr, xj = wb['资产负债表'], wb['利润表'], wb['现金流量表']
    zi, fu, qu = shu(zf['B40'].value), shu(zf['E32'].value), shu(zf['E44'].value)
    print('-- 三表勾稽 --')
    print(f'资产总计 {s(zi)} = 负债合计 {s(fu)} + 所有者权益合计 {s(qu)} '
          f'{"✓" if zi == fu + qu else "✗"}')
    print(f'期末现金 {s(shu(xj["B42"].value))} = 货币资金期末 {s(shu(zf["B6"].value))} '
          f'{"✓" if shu(xj["B42"].value) == shu(zf["B6"].value) else "✗"}')
    print(f'期初现金 {s(shu(xj["B41"].value))} = 货币资金上年年末 {s(shu(zf["C6"].value))} '
          f'{"✓" if shu(xj["B41"].value) == shu(zf["C6"].value) else "✗"}')
    print(f'现金净增加 {s(shu(xj["B40"].value))} = 期末 − 期初 '
          f'{s(shu(xj["B42"].value) - shu(xj["B41"].value))} '
          f'{"✓" if shu(xj["B40"].value) == shu(xj["B42"].value) - shu(xj["B41"].value) else "✗"}')
    jing_li = shu(lr['B28'].value)
    zeng_yu = (shu(zf['E43'].value) - shu(zf['F43'].value)      # 未分配利润：期末 − 上年年末
               + shu(zf['E42'].value) - shu(zf['F42'].value))   # 盈余公积：期末 − 上年年末
    fen_hong = shu(xj['B35'].value)                              # 本期分红（分配股利行）
    print(f'净利润 {s(jing_li)} = 留存增加 {s(zeng_yu)} + 分红 {s(fen_hong)} '
          f'{s(zeng_yu + fen_hong)} {"✓" if jing_li == zeng_yu + fen_hong else "✗"}')
    print(f'营业利润 {s(shu(lr["B23"].value))} + 营业外收入 {s(shu(lr["B24"].value))} '
          f'− 营业外支出 {s(shu(lr["B25"].value))} = 利润总额 {s(shu(lr["B26"].value))} '
          f'{"✓" if shu(lr["B23"].value) + shu(lr["B24"].value) - shu(lr["B25"].value) == shu(lr["B26"].value) else "✗"}')
    zhuan = dai.get('利润分配', Decimal(0))                      # 本年利润 → 利润分配 的结转额
    print(f'账面结转净利 {s(zhuan)} = 报表净利润 {s(jing_li)} '
          f'{"✓" if zhuan == jing_li else "✗"}')
    yin_jing = jie.get('银行存款', Decimal(0)) - dai.get('银行存款', Decimal(0))
    print(f'银行存款净额 {s(yin_jing)} = 现金净增加 {s(shu(xj["B40"].value))} '
          f'{"✓" if yin_jing == shu(xj["B40"].value) else "✗"}')
    print(f'综合收益 {s(shu(lr["B44"].value))} = 净利润 {s(jing_li)} + 其他综合收益 '
          f'{s(shu(lr["B31"].value))} '
          f'{"✓" if shu(lr["B44"].value) == jing_li + shu(lr["B31"].value) else "✗"}')
    wb.close()


if __name__ == '__main__':
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        MU / '输出' / '演示-预算基础-20260923.xlsx')
    kan(p)
