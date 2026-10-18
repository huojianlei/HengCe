# -*- coding: utf-8 -*-
"""版式档案提取（开发期一次性）：把参照的版式读出来，落 _版式档案/*.json。

参照（各司其职）：
    九表版式源  ingest_v11/模板/演示底稿-v1.2-{预算基础,实时经营}.xlsx
    外部两册    1.0.5 desktop/templates/{行业对标,经营变更}输入模板.xlsx

每张表存档：dims / 列宽 / 行高 / 合并 / 冻结 / 表级默认 / 全部非空格（含类型与值）
             / 样式表（去重后的字体·填充·边框·对齐·数字格式）+ 每格的样式索引

用途：这些 JSON 是"开发期图纸"，用来生成程序里的版式常量；运行时程序不读它们。
用法：python -B _tiqu_banshi.py
"""
import json
import sys
from pathlib import Path

from openpyxl import load_workbook

MU = Path(__file__).resolve().parent
DANG_AN = MU / '_版式档案'
GU_JIA_MU = MU.parent / 'ingest_v11' / '模板'
GU_JIA = ('演示底稿-v1.2-预算基础.xlsx', '演示底稿-v1.2-实时经营.xlsx')
WAI_BU_MU = Path(r'D:\AppProject\开发分支_1.0.5\desktop\templates')
WAI_BU = ('行业对标输入模板.xlsx', '经营变更输入模板.xlsx')
GUAN_FANG_MU = Path(r'D:\public\First\财报格式调研')
GUAN_FANG = ('利润表', '资产负债表', '现金流量表')   # 财会2019-6号空白模板（三个文件）


def yan_se(x):
    """颜色 → 可重建且可哈希的签名。"""
    if x is None:
        return None
    zhong = x.type
    if zhong == 'rgb':
        return ('rgb', str(x.rgb))
    if zhong == 'theme':
        return ('theme', int(x.theme), x.tint)
    if zhong == 'indexed':
        return ('indexed', int(x.indexed))
    return (zhong, str(x.value))


def bian(side):
    """边框单边 → (线型, 颜色)。"""
    if side is None:
        return (None, None)
    return (side.style, yan_se(side.color))


def yang_shi_qian(c):
    """单元格样式签名（字体/填充/边框/对齐/数字格式）→ 可去重的元组。"""
    f, fl, b, a = c.font, c.fill, c.border, c.alignment
    return (
        f.name, f.size, bool(f.bold), bool(f.italic), bool(f.underline), yan_se(f.color),
        fl.patternType, yan_se(fl.fgColor), yan_se(fl.bgColor),
        bian(b.left), bian(b.right), bian(b.top), bian(b.bottom),
        a.horizontal, a.vertical, bool(a.wrap_text), c.number_format,
    )


def ge_wei(c, yang_shi_dian):
    """单元格 → 存档记录（None 表示空）。"""
    v = c.value
    if v is None:
        return None
    if isinstance(v, str) and v.startswith('='):
        k, wen = 'f', v
    elif isinstance(v, str):
        k, wen = 't', v
    elif isinstance(v, bool):
        k, wen = 'b', str(v)
    else:
        k, wen = 'n', str(v)
    qian = yang_shi_qian(c)
    if qian not in yang_shi_dian:
        yang_shi_dian[qian] = len(yang_shi_dian)
    return {'k': k, 'v': wen, 's': yang_shi_dian[qian]}


def lie_kuan(ws):
    """列宽：原始区间条目 [[起始列号, 结束列号, 宽度], ...]。"""
    out = []
    for _, dim in ws.column_dimensions.items():
        if dim.width is None:
            continue
        out.append([dim.min or 1, dim.max or (dim.min or 1), round(float(dim.width), 4)])
    return sorted(out, key=lambda x: (x[0], x[1]))


def hang_gao(ws):
    """行高：{行号: 高度}（只收显式设过的）。"""
    out = {}
    for r, dim in ws.row_dimensions.items():
        if dim.height is None:
            continue
        out[str(r)] = round(float(dim.height), 4)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def ti_qu_biao(ws):
    """单表版式：dims / 尺寸 / 合并 / 冻结 / 表级默认 / 全部非空格 / 样式表。"""
    yang_shi_dian, cells = {}, {}
    for row in ws.iter_rows():
        for c in row:
            ji = ge_wei(c, yang_shi_dian)
            if ji is not None:
                cells[c.coordinate] = ji
    fan = [None] * len(yang_shi_dian)
    for qian, i in yang_shi_dian.items():
        fan[i] = list(qian)
    return {
        'dims': [ws.max_row, ws.max_column],
        'col_widths': lie_kuan(ws),
        'row_heights': hang_gao(ws),
        'merges': sorted(str(m) for m in ws.merged_cells.ranges),
        'freeze': str(ws.freeze_panes) if ws.freeze_panes else None,
        'fmt': {
            'defaultRowHeight': getattr(ws.sheet_format, 'defaultRowHeight', None),
            'baseColWidth': getattr(ws.sheet_format, 'baseColWidth', None),
            'defaultColWidth': getattr(ws.sheet_format, 'defaultColWidth', None),
        },
        'styles': fan,
        'cells': cells,
    }


def ti_qu_wen_jian(p, tag):
    """整本提取：{表名: 版式}；顺带打印摘要。"""
    wb = load_workbook(p, data_only=False, read_only=False)
    out = {}
    try:
        print(f'== {tag} :: {p} ==')
        for ws in wb.worksheets:
            ban = ti_qu_biao(ws)
            out[ws.title] = ban
            ji = {}
            for _, v in ban['cells'].items():
                ji[v['k']] = ji.get(v['k'], 0) + 1
            print(f'  [{ws.title}] dims={ban["dims"]} 非空={len(ban["cells"])} {ji} '
                  f'列宽={len(ban["col_widths"])} 行高={len(ban["row_heights"])} '
                  f'合并={len(ban["merges"])} 样式={len(ban["styles"])}')
    finally:
        wb.close()
    return out


def cun(p, tag):
    """提取 + 落盘。"""
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
    """官方三表：三个文件合成一份档案（键为表名）。"""
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
    DANG_AN.mkdir(exist_ok=True)
    if not cun_guan():
        return 1
    if not cun(GU_JIA_MU / '演示底稿-v1.2-预算基础.xlsx', '旧版骨架-v1.2-预算基础'):
        return 1
    for ming in WAI_BU:
        if not cun(WAI_BU_MU / ming, f'外部-{ming[:4]}'):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
