# -*- coding: utf-8 -*-
"""格位平移：把「分录」「摊销明细」从旧骨架的"功能区"（121 行 / O 列起）搬到 A1 起。

旧骨架把这两张表的数据放在 E121 起的功能区，左上角是 1.0.5 遗留的空白表头；
演示件不需要那套位置，直接平移到 A1，打开就能看到数据。
"""
import re

#: 每张表的平移规则（行, 列）→ (新行, 新列)；None 表示丢弃该格
def _fan(ming, row, col):
    if ming == '分录':
        # 表头 122 → 1；明细 124-540 → 2-418；汇总 543-545 → 421-423；O..V → A..H
        if col < 15 or row < 122:
            return None
        if row == 122:                     # 表头移到第 1 行
            return 1, col - 14
        return row - 122, col - 14
    if ming == '摊销明细':
        # 参数/月度区 31-36 行、B..O → 1-6 行、A..N
        if 31 <= row <= 36 and col <= 15:
            return row - 30, col - 1
        # 台账区 121-130 → 8-17；矩阵区 132-142 → 19-29；O.. 列 → A..
        if 121 <= row <= 130 and col >= 15:
            return row - 113, col - 14
        if 132 <= row <= 142 and col >= 15:
            return row - 113, col - 14
        return None
    return row, col


def xin(ming, ref):
    """旧格位 → 新格位（返回 None 表示这格不保留）。"""
    m = re.fullmatch(r'([A-Z]+)(\d+)', ref)
    if not m:
        return None
    lie, hang = m.group(1), int(m.group(2))
    zhi = _fan(ming, hang, _lie_hao(lie))
    if zhi is None:
        return None
    return f'{_lie_ming(zhi[1])}{zhi[0]}'


def _lie_hao(lie):
    n = 0
    for ch in lie:
        n = n * 26 + (ord(ch) - 64)
    return n


def _lie_ming(n):
    s = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


#: 需要平移的表
PIAN_BIAO = ('分录', '摊销明细')
