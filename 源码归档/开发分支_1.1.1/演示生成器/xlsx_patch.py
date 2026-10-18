# -*- coding: utf-8 -*-
"""受限 XML 手术写出器：以底稿 xlsx 字节为版面，仅更新/插入指定单元格。

红线约束的实现：
- 不增删行列（只在既有网格 A1:AY480 内插入格子，行/列物理顺序保持有序）；
- 样式（styles.xml）、列宽、合并区原样保留；新插入格继承同行左邻或同列上邻的样式索引；
- 公式格写入 <f> 契约文本 + <v> 由 Book 引擎按 Decimal 重算的缓存值；
- 全部共享字符串转为 inlineStr 并清空 sharedStrings，杜绝旧标识文本残留；
- 解析前拒绝 DTD/实体扩展并限制部件大小（防 XML 实体膨胀）；
- 固定 ZIP 时间戳，保证同参数逐字节复现。
"""
import io
import posixpath
import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

import sys
sys.dont_write_bytecode = True  # 只读引用 1.0.5，不留编译副产物
ALGO = r'D:\AppProject\开发分支_1.0.5\algo'
if ALGO not in sys.path:
    sys.path.insert(0, ALGO)
from xlsx_reader import Book, NS  # noqa: E402

TAG = '{' + NS['s'] + '}'
MAX_GRID_ROWS = 480          # 底稿网格行规模（A1:AY480），插入不允许越界
MAX_GRID_COLS = 51           # AY=51
MAX_XML_BYTES = 28_000_000   # 单个 XML 部件上限（与 Book 的整本上限一致量级）


def safe_xml(data):
    """解析前防御：拒绝 DTD/实体扩展，限制部件大小。"""
    if len(data) > MAX_XML_BYTES:
        raise ValueError('XML 部件过大')
    head = data[:4096].lstrip()
    if head.startswith(b'<!') or b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise ValueError('拒绝含 DTD/实体定义的 XML')
    return ET.fromstring(data)


def col_index(ref):
    n = 0
    for ch in ''.join(x for x in ref if x.isalpha()):
        n = n * 26 + ord(ch.upper()) - 64
    row = int(''.join(x for x in ref if x.isdigit()))
    return row, n


def _load_shared_strings(zin):
    if 'xl/sharedStrings.xml' not in zin.namelist():
        return []
    root = safe_xml(zin.read('xl/sharedStrings.xml'))
    return [''.join(s.itertext()) for s in root.findall('s:si', NS)]


def _sheet_parts(zin):
    rel = {r.attrib['Id']: r.attrib['Target']
           for r in safe_xml(zin.read('xl/_rels/workbook.xml.rels'))}
    wb = safe_xml(zin.read('xl/workbook.xml'))
    parts = {}
    for s in wb.find('s:sheets', NS):
        target = rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        part = posixpath.normpath(posixpath.join('xl', target)) if not target.startswith('/') else target.lstrip('/')
        parts[part] = s.attrib['name']
    return parts


def _set_cell(cell, kind, value, cache=None):
    """把 <c> 元素内容替换为指定类型值；公式附缓存。"""
    for child in list(cell):
        if child.tag in (TAG + 'v', TAG + 'f', TAG + 'is'):
            cell.remove(child)
    cell.attrib.pop('t', None)
    if kind == 'number':
        d = Decimal(value)
        text = format(d, 'f')
        if text in ('-0', '-0.0', '-0.00'):
            text = '0'
        ET.SubElement(cell, TAG + 'v').text = text
    elif kind == 'text':
        cell.set('t', 'inlineStr')
        ET.SubElement(ET.SubElement(cell, TAG + 'is'), TAG + 't').text = str(value)
    elif kind == 'formula':
        ET.SubElement(cell, TAG + 'f').text = str(value)
        ET.SubElement(cell, TAG + 'v').text = format(Decimal(cache), 'f')
    else:
        raise ValueError(f'不支持的单元格类型: {kind}')


def _ensure_cell(grid, ref):
    """在 sheetData 中定位或按序插入格子，返回 (cell, 是否新建)。"""
    row_n, col_n = col_index(ref)
    if row_n > MAX_GRID_ROWS or col_n > MAX_GRID_COLS:
        raise ValueError(f'{ref} 超出底稿网格范围')
    rows = grid.findall('s:row', NS)
    row = next((r for r in rows if int(r.attrib['r']) == row_n), None)
    created = False
    if row is None:
        row = ET.Element(TAG + 'row', {'r': str(row_n)})
        nexts = [r for r in rows if int(r.attrib['r']) > row_n]
        if nexts:
            grid.insert(list(rows).index(nexts[0]), row)
        else:
            grid.append(row)
        rows = grid.findall('s:row', NS)
    cells = row.findall('s:c', NS)
    cell = next((c for c in cells if c.attrib['r'] == ref), None)
    if cell is None:
        cell = ET.Element(TAG + 'c', {'r': ref})
        nexts = [c for c in cells if col_index(c.attrib['r'])[1] > col_n]
        if nexts:
            row.insert(list(cells).index(nexts[0]), cell)
        else:
            row.append(cell)
        created = True
    return cell, created


def _neighbor_style(grid, ref):
    """新格继承样式：优先同行左邻，其次同列上邻。"""
    row_n, col_n = col_index(ref)
    rows = {int(r.attrib['r']): r for r in grid.findall('s:row', NS)}
    row = rows.get(row_n)
    if row is not None:
        lefts = [c for c in row.findall('s:c', NS)
                 if col_index(c.attrib['r'])[1] < col_n and 's' in c.attrib]
        if lefts:
            return lefts[-1].attrib['s']
    upper = rows.get(row_n - 1)
    if upper is not None:
        ups = [c for c in upper.findall('s:c', NS)
               if col_index(c.attrib['r'])[1] == col_n and 's' in c.attrib]
        if ups:
            return ups[0].attrib['s']
    return None


def patch(raw, changes):
    """raw: 底稿 xlsx 字节；changes: {sheet: {ref: (kind, value)}}。

    返回写出后的 xlsx 字节。kind: 'number'（Decimal/float/int）/'text'/'formula'（不带=的契约文本）。
    """
    book = Book(raw)
    for sheet, cells in changes.items():
        if sheet not in book.cells:
            raise ValueError(f'底稿没有工作表 {sheet}')
        for ref, (kind, value) in cells.items():
            book.cells[sheet][ref] = (kind, value)
    # 全量重算公式缓存（Book 新实例无历史缓存，逐格求值）
    caches = {}
    for sheet, cells in book.cells.items():
        for ref, (kind, _) in cells.items():
            if kind == 'formula':
                caches[(sheet, ref)] = book.number(sheet, ref)

    zin = zipfile.ZipFile(io.BytesIO(raw))
    strings = _load_shared_strings(zin)
    parts = _sheet_parts(zin)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for name in sorted(zin.namelist()):
            data = zin.read(name)
            if name in parts:
                sheet = parts[name]
                tree = safe_xml(data)
                grid = tree.find('s:sheetData', NS)
                if grid is None:
                    raise ValueError(f'{sheet} 缺少 sheetData')
                # 1) 先把既有共享字符串格全部 inline 化（sharedStrings 将被清空）
                for c in tree.findall('.//s:c', NS):
                    if c.attrib.get('t') == 's':
                        v = c.find('s:v', NS)
                        text = strings[int(v.text)] if v is not None else ''
                        for child in list(c):
                            if child.tag in (TAG + 'v', TAG + 'f', TAG + 'is'):
                                c.remove(child)
                        c.set('t', 'inlineStr')
                        ET.SubElement(ET.SubElement(c, TAG + 'is'), TAG + 't').text = text
                # 2) 应用变更
                for ref, (kind, value) in sorted(changes.get(sheet, {}).items(),
                                                 key=lambda kv: col_index(kv[0])):
                    cell, created = _ensure_cell(grid, ref)
                    if created:
                        style = _neighbor_style(grid, ref)
                        if style is not None:
                            cell.set('s', style)
                    _set_cell(cell, kind, value, caches.get((sheet, ref)))
                data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
            elif name == 'xl/sharedStrings.xml':
                data = f'<sst xmlns="{NS["s"]}" count="0" uniqueCount="0"/>'.encode()
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, data)
    return out.getvalue()


def read_book(raw):
    """供上层复用的只读 Book 构造。"""
    return Book(raw)
