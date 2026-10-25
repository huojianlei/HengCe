# -*- coding: utf-8 -*-
"""版式档案提取（开发期一次性）：把参照的版式读出来，落 _版式档案/*.json。

参照（各司其职）：
    九表版式源  ingest_v11/模板/演示底稿-v1.2-{预算基础,实时经营}.xlsx
    外部两册    _vendor/desktop_模板/templates/{行业对标,经营变更}输入模板.xlsx

每张表存档：dims / 列宽 / 行高 / 合并 / 冻结 / 表级默认 / 全部非空格（含类型与值）
             / 样式表（去重后的字体·填充·边框·对齐·数字格式）+ 每格的样式索引

用途：这些 JSON 是"开发期图纸"，用来生成程序里的版式常量；运行时程序不读它们。
      jiaoyan.py 仅导入其中的 yang_shi_qian（纯函数，不读任何文件）。
用法：python -B _tiqu_banshi.py

为什么要有这一步:
    运行时的演示件必须长得跟用户拿到的模板一模一样（表头/列宽/行高/合并/数字格式），
    但程序里不可能运行时去读参照档案——参照档案不能随产品发给用户，而且读一遍几百毫秒。
    所以做成"开发期提取一次 → 落 JSON → 再用 _sheng_banshi.py 生成 Python 版式常量"，
    运行时只带常量、不带参照文件。

为什么样式要单独去重成样式表:
    一张表几千个非空格，80% 的格共用同样的字体填充边框。如果每格都存全量样式，JSON 会
    膨胀到几十 MB。这里先算样式签名、去重成 ``styles`` 数组，格子里只存整数下标，
    同一样式全表只留一份。这也是 git diff 友好的结构：改一处样式只动一行。

口径:
    本模块只搬运版式（位置、尺寸、样式、原始值），不做任何金额/比率换算；值按原样
    以字符串存（'k' 区分 公式f/文本t/布尔b/数值n），因此不涉及"金额=分"的换算。
    注意：存档里的数值是**参照档案的原始展示值**，不是千分位的内部整数分。

边界:
    提取是只读的：打开工作簿用 data_only=False（要拿到公式原文而不是缓存值），
    全程不 save，finally 里 close，确保不回写参照文件。

依赖与失败模式:
    参照路径不存在时打印"缺参照：…"并返回 False，main() 转成退出码 1（不抛栈）；
    参照表里的颜色/边框为 None 时有专门分支，不会 AttributeError。
"""
import json
import sys
from pathlib import Path

from openpyxl import load_workbook

MU = Path(__file__).resolve().parent          # 本模块目录（演示生成器v2/）
DANG_AN = MU / '_版式档案'                    # 提取结果的落点（开发期图纸，不进运行时）
GU_JIA_MU = MU.parent / 'ingest_v11' / '模板'  # 九表版式源目录
GU_JIA = ('演示底稿-v1.2-预算基础.xlsx', '演示底稿-v1.2-实时经营.xlsx')  # 两份共用 12 表版式
WAI_BU_MU = MU.parents[1] / '_vendor' / 'desktop_模板' / 'templates'   # 外部两册模板目录
WAI_BU = ('行业对标输入模板.xlsx', '经营变更输入模板.xlsx')
GUAN_FANG_MU = MU.parents[1] / '_vendor' / 'desktop_模板' / 'templates'
GUAN_FANG = ('利润表', '资产负债表', '现金流量表')   # 财会2019-6号空白模板（三个文件）


def yan_se(x):
    """颜色 → 可重建且可哈希的签名。

    openpyxl 的 Color 对象不可哈希（含 theme/tint 等属性），所以先降级成元组：
    rgb 存颜色串、theme 存主题号+tint、indexed 存调色板下标，其余落到 (类型, 值)。
    None 直接返回 None——大量格子没有颜色，这一步顺带省掉 JSON 体积。
    """
    if x is None:
        return None
    zhong = x.type          # 'rgb' / 'theme' / 'indexed' / 'auto' 等
    if zhong == 'rgb':
        return ('rgb', str(x.rgb))
    if zhong == 'theme':
        return ('theme', int(x.theme), x.tint)      # 主题色必须带 tint，否则深浅分不出来
    if zhong == 'indexed':
        return ('indexed', int(x.indexed))
    return (zhong, str(x.value))


def bian(side):
    """边框单边 → (线型, 颜色)。

    side 为 None（该边没画线）时返回 (None, None)，保证四边结构一致、可比较。
    """
    if side is None:
        return (None, None)
    return (side.style, yan_se(side.color))


def yang_shi_qian(c):
    """单元格样式签名（字体/填充/边框/对齐/数字格式）→ 可去重的元组。

    这个元组就是"样式指纹"：两个格子指纹相同，渲染出来一定一样，可以共用一份样式记录。
    字段顺序固定，**新增或调整字段会让旧 JSON 的 styles 下标全部失效**，需要重新提取。

    为什么数字格式也算样式: 金额格是 '#,##0.00'、比率格可能是 '0.00%'，两者长得像但
    语义不同，不能合并成一份样式，否则演示件里的金额会显示成百分比。
    """
    f, fl, b, a = c.font, c.fill, c.border, c.alignment
    return (
        f.name, f.size, bool(f.bold), bool(f.italic), bool(f.underline), yan_se(f.color),
        fl.patternType, yan_se(fl.fgColor), yan_se(fl.bgColor),      # 填充：图案类型 + 前景/背景色
        bian(b.left), bian(b.right), bian(b.top), bian(b.bottom),   # 四边分别签名
        a.horizontal, a.vertical, bool(a.wrap_text), c.number_format,
    )


def ge_wei(c, yang_shi_dian):
    """单元格 → 存档记录（None 表示空）。

    记录结构: ``{'k': 类型, 'v': 值字符串, 's': 样式下标}``
      k='f' 公式（保留 '=' 开头的原文，不取缓存值）；'t' 文本；'b' 布尔；'n' 数值。
    值统一转字符串存，避免 JSON 对 Decimal/日期等特殊类型的序列化差异。

    参数:
        c:           openpyxl 单元格。
        yang_shi_dian: 样式签名 → 下标的字典（**会被本函数就地写入**，是共享累加器）。
    返回:
        记录 dict；空格子返回 None。
    """
    v = c.value
    if v is None:
        return None
    if isinstance(v, str) and v.startswith('='):
        k, wen = 'f', v          # 公式：存原文，重放时直接写回就是活公式
    elif isinstance(v, str):
        k, wen = 't', v
    elif isinstance(v, bool):
        k, wen = 'b', str(v)     # bool 必须先判，否则会被当成数值 True/False
    else:
        k, wen = 'n', str(v)
    qian = yang_shi_qian(c)
    if qian not in yang_shi_dian:
        yang_shi_dian[qian] = len(yang_shi_dian)     # 首次出现的样式分配新下标
    return {'k': k, 'v': wen, 's': yang_shi_dian[qian]}


def lie_kuan(ws):
    """列宽：原始区间条目 [[起始列号, 结束列号, 宽度], ...]。

    存"区间"而不是逐列展开，是因为 openpyxl 本身就是按区间存的（如 A:D 同宽）；
    展开成逐列会让 JSON 翻好几倍。宽度保留 4 位小数，Excel 的列宽精度到 1/256 字符。
    """
    out = []
    for _, dim in ws.column_dimensions.items():
        if dim.width is None:
            continue
        out.append([dim.min or 1, dim.max or (dim.min or 1), round(float(dim.width), 4)])
    return sorted(out, key=lambda x: (x[0], x[1]))     # 按列号排序，保证多次提取结果稳定


def hang_gao(ws):
    """行高：{行号: 高度}（只收显式设过的）。

    没显式设行高的行不进档案——它们跟随表级默认行高（sheet_format.defaultRowHeight），
    逐行存反而会把"默认"变成"定值"，改表级默认时旧行不跟着变。
    """
    out = {}
    for r, dim in ws.row_dimensions.items():
        if dim.height is None:
            continue
        out[str(r)] = round(float(dim.height), 4)      # 键转 str：JSON 的对象键只能是字符串
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))   # 行号是字符串，排序要转 int


def ti_qu_biao(ws):
    """单表版式：dims / 尺寸 / 合并 / 冻结 / 表级默认 / 全部非空格 / 样式表。

    返回:
        dict，键：dims（[最大行, 最大列]）、col_widths、row_heights、merges（'A1:B2' 字符串
        列表，已排序）、freeze（冻结窗格格位或 None）、fmt（表级默认行高/列宽）、
        styles（样式签名数组，下标即格子里 's' 的值）、cells（{格位: 记录}）。

    注意:
        ``cells`` 只收非空格；空格的样式（比如整列加了底色）这里不保留——演示件用不到，
        而且会把档案体积做爆。若将来要还原"空但带样式"的行列，需要另加一层。
    """
    yang_shi_dian, cells = {}, {}          # 样式池 / 格子记录（顺序遍历保证下标稳定）
    for row in ws.iter_rows():
        for c in row:
            ji = ge_wei(c, yang_shi_dian)
            if ji is not None:
                cells[c.coordinate] = ji
    # 样式池是 dict（签名→下标），这里翻成"下标→签名"的数组，供重放时按下标取用
    fan = [None] * len(yang_shi_dian)
    for qian, i in yang_shi_dian.items():
        fan[i] = list(qian)               # 元组转 list：JSON 里数组比元组自然
    return {
        'dims': [ws.max_row, ws.max_column],
        'col_widths': lie_kuan(ws),
        'row_heights': hang_gao(ws),
        'merges': sorted(str(m) for m in ws.merged_cells.ranges),   # 合并区用字符串最省
        'freeze': str(ws.freeze_panes) if ws.freeze_panes else None,
        'fmt': {
            # 表级默认：这三项决定"没显式设过的行列"长什么样，必须存
            'defaultRowHeight': getattr(ws.sheet_format, 'defaultRowHeight', None),
            'baseColWidth': getattr(ws.sheet_format, 'baseColWidth', None),
            'defaultColWidth': getattr(ws.sheet_format, 'defaultColWidth', None),
        },
        'styles': fan,
        'cells': cells,
    }


def ti_qu_wen_jian(p, tag):
    """整本提取：{表名: 版式}；顺带打印摘要。

    参数:
        p:   参照 xlsx 路径。
        tag: 打印用的标签（同时决定 cun() 的存档文件名）。

    返回:
        dict，键是 sheet 名，值是 :func:`ti_qu_biao` 的结果。

    副作用:
        打印每表的 dims/非空数/类型计数/列宽行高合并样式数，供人工核对提取是否完整。
        finally 里 close 工作簿，异常路径也不漏句柄。
    """
    wb = load_workbook(p, data_only=False, read_only=False)   # data_only=False：要公式原文
    out = {}
    try:
        print(f'== {tag} :: {p} ==')
        for ws in wb.worksheets:
            ban = ti_qu_biao(ws)
            out[ws.title] = ban
            ji = {}                                     # 类型计数：f/t/b/n 各多少格
            for _, v in ban['cells'].items():
                ji[v['k']] = ji.get(v['k'], 0) + 1
            print(f'  [{ws.title}] dims={ban["dims"]} 非空={len(ban["cells"])} {ji} '
                  f'列宽={len(ban["col_widths"])} 行高={len(ban["row_heights"])} '
                  f'合并={len(ban["merges"])} 样式={len(ban["styles"])}')
    finally:
        wb.close()
    return out


def cun(p, tag):
    """提取 + 落盘。

    存档路径固定为 ``_版式档案/{tag}.json``，UTF-8、indent=1（体积小又便于 diff）。
    返回 False 表示参照缺失（调用方据此中止整轮提取），不抛异常。
    """
    if not p.exists():
        print(f'缺参照：{p}')
        return False
    jieguo = ti_qu_wen_jian(p, tag)
    lu = DANG_AN / f'{tag}.json'
    lu.write_text(json.dumps(jieguo, ensure_ascii=False, indent=1),
                  encoding='utf-8')
    print(f'  → {lu.name}（{lu.stat().st_size} 字节）\n')
    return True


def cun_guan():
    """官方三表：三个文件合成一份档案（键为表名）。

    财会2019-6号的三张空白模板是分三个文件给的，但运行时我们要按表名索引，
    所以这里合并成一个字典写进 ``官方三表.json``；三表 sheet 名不重复，直接 update 安全。
    """
    zong = {}
    for ming in GUAN_FANG:
        p = GUAN_FANG_MU / f'三表空白模板_财会2019-6号_{ming}.xlsx'
        if not p.exists():
            print(f'缺参照：{p}')
            return False
        zong.update(ti_qu_wen_jian(p, f'官方-{ming}'))
    lu = DANG_AN / '官方三表.json'
    lu.write_text(json.dumps(zong, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'  → {lu.name}（{lu.stat().st_size} 字节）\n')
    return True


def main():
    """提取全部参照 → 落 _版式档案/*.json。

    返回:
        0 = 全部成功；1 = 任一参照缺失（第一个缺失就停，不继续跑）。
    顺序:
        先官方三表（最稳），再九表旧骨架，最后按 WAI_BU 顺序提两册外部模板。
    """
    DANG_AN.mkdir(exist_ok=True)          # 目录不存在时建出来（excel 存在也不报错）
    if not cun_guan():
        return 1
    if not cun(GU_JIA_MU / '演示底稿-v1.2-预算基础.xlsx', '旧版骨架-v1.2-预算基础'):
        return 1
    for ming in WAI_BU:
        # tag 取文件名前 4 字（'行业对标' / '经营变更'），与 cun 的存档名约定保持一致
        if not cun(WAI_BU_MU / ming, f'外部-{ming[:4]}'):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

