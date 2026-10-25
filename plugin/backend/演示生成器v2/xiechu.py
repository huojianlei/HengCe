# -*- coding: utf-8 -*-
"""写出器：从零新建工作簿（openpyxl），把版式 + 数值落成 xlsx。

纪律：
    - 不读任何模板/参照文件；版式全来自 banshi.py（程序里定死）。
    - 零公式：只写标签文本与数字，绝不写 '=' 开头的公式。
    - 尺寸定死：列宽/行高/表级默认行高/合并区/冻结窗格，全部显式写出。
    - 样式复刻：字体/填充/边框/对齐 按参照的样式表逐格还原；
      参照里没有的格（程序新增：分录区/台账区/外部册表体等）取本列默认样式。

--------------------------------------------------------------
这个模块在整条链上的位置
--------------------------------------------------------------
    shuju.ShuJu → {表名: {格位: Decimal}}      （数值层，只算数）
    banshi.*    → {表名: {dims/hebing/lie_kuan/hang_gao/biaoqian/ge_ys/...}}（版式层）
                 ↑ 本文下面统一叫 ban（版式字典）
    xiechu.xie_shu(ji, tihuan, lu) → 落盘 xlsx 的 Path  （写出层）
本模块只做三件事：建表并按版式摆好骨架 → 把标签文本里的占位符替换掉 → 把数值逐格填进去。
不做任何计算、不做取整、不做"补算"——数值怎么算出来的全在 shuju.py，这里只是搬运工。
这样分层的理由：生成器要可复现，就必须让"数字"与"版式"解耦；版式改了不影响数值，
数值种子换了不影响版式，两边可以分别回归。

输入约定
    ji      {表名: {格位: 值}}；值可以是 Decimal（金额/比率）、str（文本）或 int/float。
            金额单位 = 元；比率已在数值层量化好，这里原样写。
    tihuan  {占位符: 文本}，用于替换标签里的 {主体名}、{报表日} 等花括号占位。
    lu      输出 Path。
    leibie  '预算基础' / '实时经营'，用于把标签里的"预算基础"字样就地改写。
    biao_ji 可选的版式覆盖（外部两册 waibu.py 会传 WAI_BIAO 进来）。

输出与副作用
    返回实际落盘的 Path（若目标被占用则返回"另存"后的新 Path）。
    副作用：建一个全新 Workbook，最后 save 到磁盘；不修改入参字典。

口径（与数值层一致，不许在这里二次换算）
    - 金额：元、两位小数；#,##0.00 格式，零显示"—"或 0.00（三表用后者，同官方表样）。
    - 比率：百分数格（'0.00%'）直接写小数（0.35 显示 35.00%）。
    - 每股收益：四位小数（'0.0000'）。
    - 摊销月数：整数（'0'），写成 12.00 会让台账看起来不像月数。

与其他模块的契约
    banmian.xin(ming, ref) 负责"平移表"的格位换算（原始格位 → 落盘格位），
        本文对 PIAN_BIAO 里的表统一走它，其余表格位原样使用。
    banshi.SHEETS 决定十二表的表名与顺序（顺序 = 工作簿里 sheet 的顺序）。
    jiaoyan.py 校验的是**落盘后的文件**，所以本文的"补空格/补零"行为会直接进入校验口径：
        _bu_kong 给三表空格补 0/— 是为了让"格格有内容"（导入器不认空串），
        但也意味着校验器必须把"—"当空值处理，两边口径要一起看。
"""
from copy import copy          # 目前仅在个别路径使用；保留导入以兼容后续样式复制
from decimal import Decimal    # 用于判断"是不是数值"，金额本身不做运算

from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell     # 合并区非锚点是只读的，必须跳过
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter  # 列号 1→'A'，版式里存的是数字列序

from banshi import JIU_BIAO, SAN_BIAO, SHEETS
from banmian import PIAN_BIAO, xin

#: 金额格式（照旧版骨架的数值格格式：两位小数、千分位、零显示"—"）
QIAN = '#,##0.00;(#,##0.00);"—"'
#: 三表金额格式（负数用负号、零显示 0.00 —— 与财会2019-6号表样一致）
QIAN_SAN = '#,##0.00;[Red]-#,##0.00;0.00'
#: 三表数据列（其余列的空格补"—"）
#: 注意资产负债表的 E/F 列也在这份名单里：右栏（负债权益）的数据列是 E、F，
#: 只列 B/C 会让右栏数字全被当成"空格"补成 —。
SAN_LIE = {'利润表': ('B', 'C'), '资产负债表': ('B', 'C', 'E', 'F'), '现金流量表': ('B', 'C')}
#: 打开文件时的初始定位（数据已平移到 A1，无需定位）
#: 这份字典目前为空：摊销明细/分录的数据区已在 banmian 层平移到 A1，
#: 留着它是给"将来某张表不想平移、但要定位到数据区"留的扩展点（键=表名，值=格位）。
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
    """数字显示格式（按格位规则定死，不读任何文件）。

    参数 ming: 表名；ref: 落盘后的格位（已过 banmian.xin 平移）。
    返回: openpyxl number_format 字符串。

    为什么格式要在这里定死、而不是沿用参照样式表的格式:
        参照表（老师件）里很多数字格的自定义格式是 `#,##0.00;(#,##0.00);""`——
        第三段（零值段）是空串，于是"0"会显示成空白。演示件大量出现 0（未生效月），
        落成空白会被导入器当成"缺失"而不是"零"，校验就过不了。故统一改成显式 0。
    """
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
    """颜色签名 → openpyxl 颜色。

    参数 qian: 颜色签名，来自 banshi.py 的样式表，四种形态：
        ("rgb", "FF000000")       直接给 ARGB
        ("theme", n, tint)        Office 主题色 + 明暗
        ("indexed", n)            旧调色板索引
        ("auto",)                 自动色（一般用于边框）
    返回: openpyxl Color / 字符串 / None。
    """
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
    """(线型, 颜色) → Side。

    参数 b: 形如 ('thin', ("rgb", "FF000000")) 或 None。
    返回: openpyxl Side；None/无线型时返回空 Side()（无边框），
          而不是 None——Border 的四个方向不接受 None。
    """
    if b is None or b[0] is None:
        return Side()
    return Side(style=b[0], color=_yan(b[1]))


def zao_yangshi(qian):
    """样式签名 → openpyxl 样式四件套。

    参数 qian: 17+ 元组，字段序见 banshi.py 文件头
        （0 字体名 1 字号 2 粗体 3 斜体 4 下划线 5 字色 6-8 填充 9-12 四边框 13-15 对齐 16 数字格式）。
    返回: {'font','fill','border','alignment'} 四件，可直接赋给单元格。
    说明: 下划线在 openpyxl 里只认 'single'/'double' 这类枚举，故把布尔降级为 'single'；
          数字格式不在这里返回（样式缓存要跨表复用，格式另在 geshi() 定）。
    """
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
    """给一格套样式：参照里有样式用参照的，没有就用本列默认样式。

    参数:
        c    目标单元格。
        ban  该表版式字典（含 ge_ys 逐格样式索引、lie_ys 逐列默认、yangshi 样式表）。
        ref  格位（用于查 ge_ys）。
        dian 样式缓存 {样式签名: 四件套}，跨表跨格共用 —— 这是性能关键：
             不缓存的话，几千个格各建一次 Font/Fill/Border，openpyxl 会慢一个数量级。
    查找顺序: ge_ys[格位] → lie_ys[列字母] → lie_ys['*']（兜底列）→ 无样式（直接返回）。
    副作用: 命中样式则写 c.font/fill/border/alignment，且**只在参照显式给了数字格式时**
            才写 c.number_format（避免用一堆 'General' 把 geshi() 定好的格式覆盖掉）。
    """
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

    为什么要补: 三表要"格格有内容"。用户/导入器看到一大片空白，无法区分
        "这项业务没发生（应为 0）"与"程序漏算了"；补 0 让零值有明示。
        非数据列（如左侧科目名列的空格子、跨栏留白）补"—"，是财会表样的常见做法，
        比空白更能说明"此处无内容"。
    参数:
        ws   工作表。
        ban  该表版式（取 dims 作为遍历边界）。
        ming 表名（决定是否补、补哪几列、补到第几行）。
        dian 样式缓存（补充的格也要套上本列默认样式，否则会以默认宋体黑框出现）。
    副作用: 就地改单元格值与格式；不碰已有值、不碰合并区非锚点。
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

    参数:
        ws   分录工作表（已写完数据）。
        ban  版式（用于给补的"—"套样式；可缺省）。
        dian 样式缓存（同上）。
    返回: None。
    副作用: ①把缺现金流对照的行补"—"；②在数据下方写三行合计（借方/贷方/差额）。
    为什么合计放在文件里而不是只在内存里算: 这是给人工核对用的"审计痕迹"——
        借贷差额那一行应为 0，用户打开就能看见账平不平，不用信口头承诺。
        数值仍与 shuju.fenlu_heji 的断言一致（两处独立计算，互为校验）。
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
    """ji: {表名: {格位: 值}}；biao_ji: {表名: 版式}（缺省 = 十二表）。

    完整参数:
        ji     数值层产出（见 shuju.ShuJu.biao）；值类型决定写入方式——
               Decimal/int/float → 写数字并定格式；str → 写文本（标签/占位符）。
        tihuan 占位符替换表，如 {'主体名': '示例科技', '报表日': '2027-12-31'}。
        lu     输出路径（Path）。
        leibie 数据类别，用于把标签文本里的"预算基础"改写成实际类别
               （实时经营件里表头不能还写"预算基础"）。
        biao_ji 版式覆盖：外部两册（行业对标/经营变更）走 waibu.WAI_BIAO。
    返回: 实际落盘 Path（占用时是"另存"的新路径）。
    副作用: 写磁盘；目标被 Excel 占用时**不抛异常**，改为另存 `名字-新.xlsx` 并提示。
    异常边界:
        PermissionError —— 已捕获并降级另存；
        其余 I/O 异常（磁盘满/路径不存在）照常上抛，由命令行入口打印。
    构建顺序（有依赖，不能乱）:
        建 sheet → 默认行高 → 列宽 → 行高 → 合并区 → 冻结 → 视口 → 标签 → 数值 → 补空 → 分录合计
        合并必须在写值之前：合并后再写非锚点格会抛异常，且合并会清掉被合并格的值。
    """
    if biao_ji is None:
        # 三表用老师件版式（SAN_BIAO），其余九表用旧版骨架（JIU_BIAO）；
        # 这样同一份工作簿里既有"像官方的三表"，也有"带明细的九表"。
        biao_ji = {m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    wb = Workbook()
    wb.remove(wb.active)          # 删掉 openpyxl 默认的空 Sheet，保证顺序以 SHEETS 为准
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
