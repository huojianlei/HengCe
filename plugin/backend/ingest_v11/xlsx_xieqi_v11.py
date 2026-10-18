# -*- coding: utf-8 -*-
"""受限 XML 手术写出器 v1.1——fork 自 演示生成器/xlsx_patch.py（同仓库）。

与原版的唯一行为差异：公式格缓存【可缺省】——骨架文件里存在"输入为空时
不可求值"的固化公式（如每股收益除以空股数）；原版一律 Book 重算缓存，
遇不可求值即抛错。本版求值失败时只写 <f> 不写 <v>（导入器按需惰性求值，
从不无故触碰这些格），保证骨架底稿可生成。

其余红线约束与原版逐条一致：不增删行列（A1:AY480 网格内插入）、样式/
列宽/合并区原样保留、新格继承邻格样式、共享串全量 inline 化、拒 DTD/
实体扩展、固定 ZIP 时间戳（同参数逐字节复现）。
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）
"""
import io  # 内存字节流
import os  # 环境变量覆盖 algo 路径（自足包）
import posixpath  # zip 内路径规整
import sys  # 引导 algo 只读树
import zipfile  # zip 重写
from decimal import Decimal  # 数值精确格式化
from pathlib import Path  # _vendor 路径解析（自足包）
from xml.etree import ElementTree as ET  # XML 解析/序列化

sys.dont_write_bytecode = True                     # 引 algo 只读树，不留编译副产物
# 自足包：algo 树已 vendor 进 backend/_vendor/algo（HENGCE_ALGO_DIR 可覆盖）
ALGO = os.environ.get('HENGCE_ALGO_DIR') or str(Path(__file__).resolve().parents[1] / '_vendor' / 'algo')
if ALGO not in sys.path:  # 幂等判断
    sys.path.insert(0, ALGO)  # 插入搜索路径
from xlsx_reader import Book, ExcelError, NS       # noqa: E402

TAG = '{' + NS['s'] + '}'  # 名字空间标签前缀
MAX_GRID_ROWS = 480                                # 底稿网格行规模（A1:AY480）
MAX_GRID_COLS = 51                                 # AY=51
MAX_XML_BYTES = 28_000_000                         # 单个 XML 部件上限（与 Book 同量级）


def safe_xml(data):  # XML 防御入口
    """解析前防御：拒绝 DTD/实体扩展，限制部件大小。"""
    # 部件上限：与 Book 引擎同量级，防解压炸弹撑爆内存
    if len(data) > MAX_XML_BYTES:  # 超上限
        raise ValueError('XML 部件过大')  # 拒绝过大部件
    head = data[:4096].lstrip()  # 取头部探测
    # DTD/内部实体三种形态全拦（XXE 与实体膨胀的入口）
    if head.startswith(b'<!') or b'<!DOCTYPE' in data or b'<!ENTITY' in data:  # 三种实体形态
        raise ValueError('拒绝含 DTD/实体定义的 XML')  # 拒绝 DTD/实体
    return ET.fromstring(data)  # 安全解析


def col_index(ref):  # 格位解析
    """'C12' → (12, 3)；列字母转列号（1 起）。"""
    # 字母段逐位 26 进制累加（A=1 … Z=26, AA=27 …）
    n = 0  # 列号累加器
    for ch in ''.join(x for x in ref if x.isalpha()):  # 字母段逐位
        n = n * 26 + ord(ch.upper()) - 64  # 26 进制累加
    # 数字段直接取整（行号）
    row = int(''.join(x for x in ref if x.isdigit()))  # 数字段取行号
    return row, n  # 返回 (行, 列)


def _load_shared_strings(zin):  # 共享串读取
    """共享字符串表 → 文本列表（写出前全量 inline 化用）。"""
    # 无共享串部件（底稿理论上都有，防御分支）→ 空表
    if 'xl/sharedStrings.xml' not in zin.namelist():  # 无部件防御
        return []  # 空表
    root = safe_xml(zin.read('xl/sharedStrings.xml'))  # 解析共享串
    # si 节点内全部文本拼接（含 rich text 分段 r/t）
    return [''.join(s.itertext()) for s in root.findall('s:si', NS)]  # 全文本拼接


def _sheet_parts(zin):  # 表名→部件映射
    """工作表名 → zip 部件路径映射（不动 workbook 结构）。"""
    # 关系表：rId → Target（相对 xl/ 的路径）
    rel = {r.attrib['Id']: r.attrib['Target']  # rId→Target
           for r in safe_xml(zin.read('xl/_rels/workbook.xml.rels'))}
    wb = safe_xml(zin.read('xl/workbook.xml'))  # workbook 部件
    parts = {}  # 映射桶
    # 逐 sheet 取其 rId 对应部件；绝对路径去斜杠、相对路径按 xl/ 规整
    for s in wb.find('s:sheets', NS):  # 逐 sheet
        target = rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]  # 取 Target
        part = posixpath.normpath(posixpath.join('xl', target)) if not target.startswith('/') else target.lstrip('/')  # 路径规整
        parts[part] = s.attrib['name']  # 部件→表名
    return parts  # 返回映射


def _set_cell(cell, kind, value, cache=None):  # 单元格写入
    """把 <c> 内容替换为指定类型值；公式附缓存（cache 为 None 时只写 <f>）。"""
    # 先清旧载荷（v/f/is 三种子节点），属性 t 一并重置
    for child in list(cell):  # 清旧载荷
        if child.tag in (TAG + 'v', TAG + 'f', TAG + 'is'):  # 三种子节点
            cell.remove(child)  # 移除
    cell.attrib.pop('t', None)  # 清类型属性
    if kind == 'number':  # 数值分支
        # 数值：Decimal 全文写出（无科学计数，规避 Excel 精度歧义）
        text = format(Decimal(str(value)), 'f')     # 与原版同口径：十进制全文
        if text in ('-0', '-0.0', '-0.00'):  # 负零归一
            text = '0'                              # 负零归一（避免 -0 缓存）
        ET.SubElement(cell, TAG + 'v').text = text  # 写 <v>
    elif kind == 'text':  # 文本分支
        # 文本：inlineStr 形态（共享串将被清空，杜绝旧串残留）
        cell.set('t', 'inlineStr')  # 置 inlineStr
        ET.SubElement(ET.SubElement(cell, TAG + 'is'), TAG + 't').text = str(value)  # 写 <is><t>
    elif kind == 'formula':  # 公式分支
        # 公式：只写 <f> 契约文本；缓存可缺省（v1.1 骨架不可求值格）
        ET.SubElement(cell, TAG + 'f').text = str(value)  # 写 <f>
        if cache is not None:                      # v1.1：缓存可缺省（骨架不可求值格）
            ET.SubElement(cell, TAG + 'v').text = format(cache, 'f')  # 缓存可缺省写 <v>
    else:  # 未知类型
        # 未知类型：直接抛错（防误写破坏版面）
        raise ValueError(f'不支持的单元格类型: {kind}')  # 拒绝误写


def _ensure_cell(grid, ref):  # 格子定位/插入
    """在 sheetData 中定位或按序插入格子，返回 (cell, 是否新建)。"""
    row_n, col_n = col_index(ref)  # 拆行列
    # 网格硬界：A1:AY480 之外拒绝插入（不增删行列红线的代码化）
    if row_n > MAX_GRID_ROWS or col_n > MAX_GRID_COLS:  # 网格硬界
        raise ValueError(f'{ref} 超出底稿网格范围')  # 拒绝越界
    rows = grid.findall('s:row', NS)  # 全部行
    row = next((r for r in rows if int(r.attrib['r']) == row_n), None)  # 找目标行
    created = False  # 新建标记
    if row is None:  # 行不存在
        # 行不存在：按行号升序插入新 <row>（保持物理有序）
        row = ET.Element(TAG + 'row', {'r': str(row_n)})  # 新建 <row>
        nexts = [r for r in rows if int(r.attrib['r']) > row_n]  # 后续行
        if nexts:  # 有后续
            grid.insert(list(rows).index(nexts[0]), row)  # 前插
        else:  # 无后续
            grid.append(row)  # 末尾追加
        rows = grid.findall('s:row', NS)  # 重取行集
    cells = row.findall('s:c', NS)  # 行内格子
    cell = next((c for c in cells if c.attrib['r'] == ref), None)  # 找目标格
    if cell is None:  # 格不存在
        # 格不存在：按列号升序插入新 <c>
        cell = ET.Element(TAG + 'c', {'r': ref})  # 新建 <c>
        nexts = [c for c in cells if col_index(c.attrib['r'])[1] > col_n]  # 后续格
        if nexts:  # 有后续
            row.insert(list(cells).index(nexts[0]), cell)  # 前插
        else:  # 无后续
            row.append(cell)  # 末尾追加
        created = True  # 标记新建
    return cell, created  # 返回格+标记


def _neighbor_style(grid, ref):  # 邻格样式
    """新格继承样式：优先同行左邻，其次同列上邻。"""
    row_n, col_n = col_index(ref)  # 拆行列
    rows = {int(r.attrib['r']): r for r in grid.findall('s:row', NS)}  # 行号→行
    row = rows.get(row_n)  # 本行
    # 左邻：同行内列号更小且带样式索引的最近一格
    if row is not None:  # 行在册
        lefts = [c for c in row.findall('s:c', NS)  # 候选左邻
                 if col_index(c.attrib['r'])[1] < col_n and 's' in c.attrib]  # 列更小带样式
        if lefts:  # 有候选
            return lefts[-1].attrib['s']  # 取最近左邻
    # 上邻：同列上一行带样式的第一格
    upper = rows.get(row_n - 1)  # 上一行
    if upper is not None:  # 行在册
        ups = [c for c in upper.findall('s:c', NS)  # 候选上邻
               if col_index(c.attrib['r'])[1] == col_n and 's' in c.attrib]  # 同列带样式
        if ups:  # 有候选
            return ups[0].attrib['s']  # 取上邻
    return None  # 无邻可继


def patch(raw, changes):  # 主写出入口
    """raw: 底稿 xlsx 字节；changes: {sheet: {ref: (kind, value)}} → 写出后字节。

    kind: 'number'（Decimal/int/float）/'text'/'formula'（不带 = 的契约文本）。
    公式缓存逐格尝试求值，失败（空输入除零等）则不写缓存——见模块头差异说明。
    """
    # 第一步：变更先注入内存 Book（保证后续求值口径与最终写出一致）
    book = Book(raw)  # 内存 Book
    for sheet, cells in changes.items():  # 逐表
        if sheet not in book.cells:  # 表不存在
            raise ValueError(f'底稿没有工作表 {sheet}')  # 拒绝写
        for ref, (kind, value) in cells.items():  # 逐格注入
            book.cells[sheet][ref] = (kind, value)  # 注入内存
    # 逐格求值公式缓存：能算则算，不能算置 None（v1.1 骨架可求值性差异点）
    caches = {}  # 缓存桶
    for sheet, cells in book.cells.items():  # 逐表
        for ref, (kind, _) in cells.items():  # 逐格
            if kind == 'formula':  # 公式格
                try:  # 尝试求值
                    caches[(sheet, ref)] = book.number(sheet, ref)  # 成功记缓存
                except Exception:                   # 空输入/除零等骨架态：缓存缺省
                    caches[(sheet, ref)] = None  # 失败置 None
    # 第二步：逐部件重写 zip（非 sheet 部件原样搬运）
    zin = zipfile.ZipFile(io.BytesIO(raw))  # 打开源 zip
    strings = _load_shared_strings(zin)  # 共享串
    parts = _sheet_parts(zin)  # 表→部件
    out = io.BytesIO()  # 输出字节流
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zout:  # 目标 zip
        for name in sorted(zin.namelist()):  # 逐部件（排序稳定）
            data = zin.read(name)  # 原样读入
            if name in parts:  # sheet 部件
                # sheet 部件：三步手术（inline 化 → 应用变更 → 序列化）
                sheet = parts[name]  # 部件对应表
                tree = safe_xml(data)  # 解析
                grid = tree.find('s:sheetData', NS)  # sheetData
                if grid is None:  # 缺失防御
                    raise ValueError(f'{sheet} 缺少 sheetData')  # 拒绝
                # 1) 既有共享字符串格全部 inline 化（sharedStrings 将被清空）
                for c in tree.findall('.//s:c', NS):  # 共享串格扫描
                    if c.attrib.get('t') == 's':  # t="s" 格
                        v = c.find('s:v', NS)  # 取索引
                        # 共享串索引 → 原文（越界索引会 KeyError，防御默认空串）
                        text = strings[int(v.text)] if v is not None else ''  # 索引→原文
                        for child in list(c):  # 清旧载荷
                            if child.tag in (TAG + 'v', TAG + 'f', TAG + 'is'):  # 三种子节点
                                c.remove(child)  # 移除
                        c.set('t', 'inlineStr')  # 置 inlineStr
                        ET.SubElement(ET.SubElement(c, TAG + 'is'), TAG + 't').text = text  # 写 <is><t>
                # 2) 应用变更（公式缓存可缺省；新格继承邻格样式）
                for ref, (kind, value) in sorted(changes.get(sheet, {}).items(),  # 应用变更（列序）
                                                 key=lambda kv: col_index(kv[0])):  # 列号排序
                    cell, created = _ensure_cell(grid, ref)  # 定位/插入格
                    if created:  # 新建格
                        style = _neighbor_style(grid, ref)  # 继承样式
                        if style is not None:  # 有样式
                            cell.set('s', style)  # 设置样式
                    _set_cell(cell, kind, value, caches.get((sheet, ref)))  # 写入内容
                data = ET.tostring(tree, encoding='utf-8', xml_declaration=True)  # 序列化部件
            elif name == 'xl/sharedStrings.xml':  # 共享串部件
                # 共享串部件替换为空表（全部文本已 inline）
                data = f'<sst xmlns="{NS["s"]}" count="0" uniqueCount="0"/>'.encode()  # 置空表
            # 固定时间戳 2000-01-01：同参数逐字节复现的前提
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))  # 固定时间戳
            info.compress_type = zipfile.ZIP_DEFLATED  # 压缩方式
            zout.writestr(info, data)  # 写出部件
    return out.getvalue()  # 返回字节


def read_book(raw):  # 只读构造入口
    """供上层复用的只读 Book 构造。"""
    return Book(raw)  # Book 实例


__all__ = ['patch', 'read_book', 'col_index', 'safe_xml', 'ExcelError']  # 对外导出清单
