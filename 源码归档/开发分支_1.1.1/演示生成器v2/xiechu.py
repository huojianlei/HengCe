# -*- coding: utf-8 -*-
"""写出器：从零新建工作簿（openpyxl），把版式 + 数值落成 xlsx。

纪律：
    - 不读任何模板/参照文件；版式全来自 banshi.py（程序里定死）。
    - 零公式：只写标签文本与数字，绝不写 '=' 开头的公式。
    - 尺寸定死：列宽/行高/表级默认行高/合并区/冻结窗格，全部显式写出。
    - 样式复刻：字体/填充/边框/对齐 按参照的样式表逐格还原；
      参照里没有的格（程序新增：分录区/台账区/外部册表体等）取本列默认样式。
"""
from copy import copy
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from banshi import JIU_BIAO, SAN_BIAO, SHEETS
from banmian import PIAN_BIAO, xin

#: 金额格式（照旧版骨架的数值格格式：两位小数、千分位、零显示"—"）
QIAN = '#,##0.00;(#,##0.00);"—"'
#: 三表金额格式（负数用负号、零显示 0.00 —— 与财会2019-6号表样一致）
QIAN_SAN = '#,##0.00;[Red]-#,##0.00;0.00'
#: 三表数据列（其余列的空格补"—"）
SAN_LIE = {'利润表': ('B', 'C'), '资产负债表': ('B', 'C', 'E', 'F'), '现金流量表': ('B', 'C')}
#: 打开文件时的初始定位（数据已平移到 A1，无需定位）
SHI_TU = {}
#: 三表补空范围（列, 起行, 止行）：各栏只在自己的项目范围内补，
#: 资产栏到 40 行「资产总计」为止，41-45 行属负债权益栏，左侧留空（同官方表样）
SAN_FAN_WEI = {
    '利润表': (('A', 5, 47), ('B', 5, 47), ('C', 5, 47)),
    '现金流量表': (('A', 5, 42), ('B', 5, 42), ('C', 5, 42)),
    '资产负债表': (('A', 5, 40), ('B', 5, 40), ('C', 5, 40),
                   ('D', 5, 45), ('E', 5, 45), ('F', 5, 45)),
}


def geshi(ming, ref):
    """数字显示格式（按格位规则定死，不读任何文件）。"""
    hang = int(''.join(c for c in ref if c.isdigit()) or 0)
    lie = ''.join(c for c in ref if c.isalpha())
    if ming == '利润表' and hang in (46, 47):                    # 每股收益保四位
        return '0.0000'
    if ming == '税金及附加' and (ref == 'C31' or (lie == 'P' and 123 <= hang <= 126)):
        return '0.00%'                                           # 综合附加率 / 分档率
    if ming == '摊销明细' and (hang == 2 or (lie == 'F' and 10 <= hang <= 17)):
        return '0'                                               # 摊销月数（整数）
    if ming == '基准指标':                                       # 外部册：参考值保两位
        return '0.00'
    return QIAN_SAN if ming in SAN_LIE else QIAN


def _yan(qian):
    """颜色签名 → openpyxl 颜色。"""
    if qian is None:
        return None
    if qian[0] == 'rgb':
        return qian[1]
    if qian[0] == 'theme':
        from openpyxl.styles import Color
        return Color(theme=qian[1], tint=qian[2] or 0)
    if qian[0] == 'indexed':
        from openpyxl.styles import Color
        return Color(indexed=qian[1])
    if qian[0] == 'auto':                       # 自动色（边框默认色）
        from openpyxl.styles import Color
        return Color(auto=True)
    return None


def _bian(b):
    """(线型, 颜色) → Side。"""
    if b is None or b[0] is None:
        return Side()
    return Side(style=b[0], color=_yan(b[1]))


def zao_yangshi(qian):
    """样式签名 → openpyxl 样式四件套。"""
    return {
        'font': Font(name=qian[0], size=qian[1], bold=qian[2], italic=qian[3],
                     underline='single' if qian[4] else None, color=_yan(qian[5])),
        'fill': PatternFill(patternType=qian[6] or None, fgColor=_yan(qian[7]),
                            bgColor=_yan(qian[8])),
        'border': Border(left=_bian(qian[9]), right=_bian(qian[10]),
                         top=_bian(qian[11]), bottom=_bian(qian[12])),
        'alignment': Alignment(horizontal=qian[13], vertical=qian[14],
                               wrap_text=bool(qian[15])),
    }


def _tiao(c, ban, ref, dian):
    """给一格套样式：参照里有样式用参照的，没有就用本列默认样式。"""
    idx = ban['ge_ys'].get(ref)
    if idx is None:
        lie = ''.join(ch for ch in ref if ch.isalpha())
        idx = ban['lie_ys'].get(lie, ban['lie_ys'].get('*'))
    if idx is None:
        return
    qian = ban['yangshi'][idx]
    if qian not in dian:                    # 按样式签名缓存（跨表可共用）
        dian[qian] = zao_yangshi(qian)
    yang = dian[qian]
    c.font = yang['font']
    c.fill = yang['fill']
    c.border = yang['border']
    c.alignment = yang['alignment']
    if qian[16] and qian[16] != 'General':       # 参照自带数字格式则沿用
        c.number_format = qian[16]


def _bu_kong(ws, ban, ming, dian):
    """三表补空格：数据列补 0（显示 0.00），其余列补"—"。

    合并区非锚点在 Excel 里是只读的（MergedCell），物理上写不进值，跳过。
    """
    fan = SAN_FAN_WEI.get(ming)
    if not fan:
        return
    lie = SAN_LIE[ming]
    zai = {c for c, lo, hi in fan}
    for row in ws.iter_rows(min_row=1, max_row=ban['dims'][0], max_col=ban['dims'][1]):
        for c in row:
            if isinstance(c, MergedCell) or c.value is not None:
                continue
            if c.column_letter not in zai:
                continue                                     # 范围外的空块保持空白
            if not any(c.column_letter == x and lo <= c.row <= hi for x, lo, hi in fan):
                continue
            _tiao(c, ban, c.coordinate, dian)
            if c.column_letter in lie:
                c.value = 0
                c.number_format = QIAN_SAN
            else:
                c.value = '—'


def _fenlu_heji(ws, ban=None, dian=None):
    """分录表：紧跟数据写「全部借方合计 / 全部贷方合计 / 借贷差额」。

    数据行数随月份数变化（预算基础 516 行、实时经营 258 行），所以合计行不能写死，
    这里按最后一条有摘要的行动态落位。
    """
    mo = 1
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 2).value not in (None, ''):
            mo = r
    # 非现金分录没有现金流对照行 → 补"—"，避免出现大片空格
    for r in range(2, mo + 1):
        c = ws.cell(r, 7)
        if c.value is None and ws.cell(r, 2).value:
            if ban is not None:                      # 套上该格应有的样式
                _tiao(c, ban, f'G{r}', dian)
                c.number_format = 'General'
            c.value = '—'
    jie = sum((ws.cell(r, 5).value or 0) for r in range(2, mo + 1))
    dai = sum((ws.cell(r, 6).value or 0) for r in range(2, mo + 1))
    hang = mo + 2
    for i, (wen, lie, zhi) in enumerate((('全部借方合计', 5, jie),
                                        ('全部贷方合计', 6, dai),
                                        ('借贷差额（应为0）', 7, jie - dai))):
        r = hang + i
        c = ws.cell(r, 1)
        c.value = wen
        c.font = Font(bold=True)
        v = ws.cell(r, lie)
        v.value = float(zhi)
        v.number_format = QIAN_SAN
        v.font = Font(bold=True)


def xie_shu(ji, tihuan, lu, leibie='预算基础', biao_ji=None):
    """ji: {表名: {格位: 值}}；biao_ji: {表名: 版式}（缺省 = 十二表）。"""
    if biao_ji is None:
        biao_ji = {m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    wb = Workbook()
    wb.remove(wb.active)
    dian = {}
    for ming, ban in biao_ji.items():
        ws = wb.create_sheet(ming)
        if ban['hang_gao_mo_ren']:
            ws.sheet_format.defaultRowHeight = float(ban['hang_gao_mo_ren'])
        for i, kuan in ban['lie_kuan'].items():
            ws.column_dimensions[get_column_letter(int(i))].width = float(kuan)
        for r, gao in ban['hang_gao'].items():
            ws.row_dimensions[int(r)].height = float(gao)
        for ref in ban['hebing']:
            ws.merge_cells(ref)
        if ban.get('freeze'):
            ws.freeze_panes = ban['freeze']
        # 打开即定位到数据功能区（摊销明细/分录的左上角是 1.0.5 遗留空白表头，
        # 数据在第 121 行 O 列起；不定位的话打开看到的是空区）
        ding = SHI_TU.get(ming)
        if ding:
            ws.sheet_view.topLeftCell = ding
            if ws.sheet_view.pane is not None:
                ws.sheet_view.pane.topLeftCell = ding
            ws.sheet_view.selection[0].activeCell = ding
            ws.sheet_view.selection[0].sqref = ding
        for ref, v in ban['biaoqian'].items():                      # 静态标签
            c = ws[ref]
            c.value = (v.replace('预算基础', leibie).format(**tihuan)
                       if isinstance(v, str) else v)
            _tiao(c, ban, ref, dian)
        for ref0, v in ji.get(ming, {}).items():                    # 数值层
            ref = xin(ming, ref0) if ming in PIAN_BIAO else ref0    # 平移表的格位换算
            if ref is None:
                continue
            c = ws[ref]
            if isinstance(v, (Decimal, int, float)):
                c.value = float(v)
                _tiao(c, ban, ref, dian)
                # 数值格式一律按规则定死（参照格式里零段常为 ""，会把 0 显示成空白）
                c.number_format = geshi(ming, ref)
            else:
                c.value = v
                _tiao(c, ban, ref, dian)
        _bu_kong(ws, ban, ming, dian)                               # 三表：格格有内容
        if ming == '分录':                                          # 分录：对照列补"—" + 末尾合计行
            _fenlu_heji(ws, ban, dian)
    try:
        wb.save(lu)
    except PermissionError:                     # 目标被 Excel 占用：另存，不中断
        lu_new = lu.with_name(f'{lu.stem}-新{lu.suffix}')
        wb.save(lu_new)
        print(f'  [提示] {lu.name} 被占用（多半是 Excel 开着），已另存为 {lu_new.name}')
        lu = lu_new
    wb.close()
    return lu
