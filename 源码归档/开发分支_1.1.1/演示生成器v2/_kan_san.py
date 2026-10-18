# -*- coding: utf-8 -*-
"""三表体检（开发期查看）：按财会2019-6号版式打印关键行。

用法：python -B _kan_san.py [产物路径]
"""
import sys
from pathlib import Path

from openpyxl import load_workbook

MU = Path(__file__).resolve().parent


def s(v):
    return f'{v:,.2f}' if isinstance(v, (int, float)) else '—'


def kan(lu):
    wb = load_workbook(lu)
    print(f'== {Path(lu).name} ==')
    lr = wb['利润表']
    print('-- 利润表（B=本期 C=上期）')
    for r in range(5, 48):
        a = lr[f'A{r}'].value
        if a is None:
            continue
        print(f'  {r:>2} {str(a)[:30]:<32}{s(lr[f"B{r}"].value):>16}{s(lr[f"C{r}"].value):>16}')
    zf = wb['资产负债表']
    print('-- 资产负债表（左 期末B/上年C；右 期末E/上年F）')
    for r in range(5, 46):
        a, d = zf[f'A{r}'].value, zf[f'D{r}'].value
        if a is None and d is None:
            continue
        print(f'  {r:>2} {str(a or "")[:20]:<22}{s(zf[f"B{r}"].value):>14}{s(zf[f"C{r}"].value):>14}'
              f'   {str(d or "")[:20]:<22}{s(zf[f"E{r}"].value):>14}{s(zf[f"F{r}"].value):>14}')
    xj = wb['现金流量表']
    print('-- 现金流量表（B=本期 C=上期）')
    for r in range(5, 43):
        a = xj[f'A{r}'].value
        if a is None:
            continue
        print(f'  {r:>2} {str(a)[:34]:<36}{s(xj[f"B{r}"].value):>16}{s(xj[f"C{r}"].value):>16}')
    wb.close()


if __name__ == '__main__':
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        MU / '输出' / '演示-预算基础-20260923.xlsx')
    kan(p)
