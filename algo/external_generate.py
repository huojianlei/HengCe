"""为行业对标与经营变更固定模板填入有标签的确定性演示行。"""
import io
import json
import posixpath
import random
import hashlib
import zipfile
from decimal import Decimal
from xml.etree import ElementTree as ET

from excel_contract import col
from external_templates import METRICS
from xlsx_reader import NS,Book,ExcelError

TAG='{'+NS['s']+'}'

def populate(raw,changes):
    """仅修改模板中指定值单元格；标准 OOXML 元件与格式其余部分保留。"""
    source=Book(raw)
    if set(changes)-set(source.cells):raise ExcelError('模板工作表不匹配')
    with zipfile.ZipFile(io.BytesIO(raw)) as zin:
        rel={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))}
        wb=ET.fromstring(zin.read('xl/workbook.xml'));parts={}
        for s in wb.find('s:sheets',NS):
            target=rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            part=posixpath.normpath(posixpath.join('xl',target)) if not target.startswith('/') else target.lstrip('/')
            parts[part]=s.attrib['name']
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as zout:
            for name in sorted(zin.namelist()):
                data=zin.read(name)
                if name in parts and parts[name] in changes:
                    sheet=parts[name];tree=ET.fromstring(data);grid=tree.find('s:sheetData',NS)
                    for ref,value in changes[sheet].items():
                        row_number=int(''.join(c for c in ref if c.isdigit()))
                        row=next((r for r in grid.findall('s:row',NS) if int(r.attrib['r'])==row_number),None)
                        if row is None:row=ET.SubElement(grid,TAG+'row',{'r':str(row_number)})
                        cell=next((c for c in row.findall('s:c',NS) if c.attrib['r']==ref),None)
                        if cell is None:cell=ET.SubElement(row,TAG+'c',{'r':ref})
                        for child in list(cell):
                            if child.tag in (TAG+'v',TAG+'f',TAG+'is'):cell.remove(child)
                        cell.attrib.pop('t',None)
                        if isinstance(value,(int,float,Decimal)):
                            ET.SubElement(cell,TAG+'v').text=str(value)
                        elif value is not None and str(value)!='':
                            cell.set('t','inlineStr');ET.SubElement(ET.SubElement(cell,TAG+'is'),TAG+'t').text=str(value)
                    # Keep rows/cells sorted for readers that assume physical A1 ordering.
                    for row in grid.findall('s:row'):
                        cells=row.findall('s:c')
                        for c in cells:row.remove(c)
                        def index(ref):
                            n=0
                            for ch in ''.join(x for x in ref if x.isalpha()):n=n*26+ord(ch)-64
                            return n
                        for cell in sorted(cells,key=lambda c:index(c.attrib['r'])):row.append(cell)
                    rows=grid.findall('s:row')
                    for row in rows:grid.remove(row)
                    for row in sorted(rows,key=lambda r:int(r.attrib['r'])):grid.append(row)
                    data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
                info=zipfile.ZipInfo(name,(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                zout.writestr(info,data)
        return output.getvalue()

def metadata(entity_code,entity,scenario_code,scenario,year,grain,seed):
    return {'B2':entity_code,'B3':entity,'B4':scenario_code,'B5':scenario,'B6':str(year),'B7':grain,
            'B8':'演示占位-v1','B9':'模拟权责发生制','B10':f'{year}-01','B11':f'{year}-06',
            'B12':'无','B13':'无','B14':'占位','B15':f'固定种子 {seed}；不代表真实业务'}

def random_value(rng,low,high,blacklist_hashes=()):
    blocked=set(blacklist_hashes)
    for _ in range(200):
        v=Decimal(rng.randrange(low,high+1))/100
        if hashlib.sha256(str(v.normalize()).encode()).hexdigest() not in blocked:return v
    raise ExcelError('构造值无法避开原始数值黑名单')

def industry_demo(template,seed,entity_code,entity,scenario_code,scenario,year,grain,blacklist_hashes=()):
    rng=random.Random(f'{seed}|{entity_code}|{scenario_code}|行业对标')
    rows={};period=f'{year}-06' if grain=='月度' else f'{year}-Q2';day=f'{year}-06-30'
    limits={'GROSS_MARGIN':(1537,3121),'PROCUREMENT_COST_CHANGE':(307,1469),
            'CAPACITY_UTILIZATION':(6321,8679),'EXPENSE_THRESHOLD':(1501,3007),
            'RAW_MATERIAL_INDEX':(9341,10679)}
    for i,(code,name) in enumerate(METRICS.items(),2):
        values=(code,name,period,random_value(rng,*limits[code],blacklist_hashes),'%',
                '构造参考值','影视投资示意（非统计总体）','无真实样本','演示参数；不得用作真实阈值',
                '本地演示生成器','本地构造，无外部真实出处',day,'仅用于流程演示',entity_code,scenario_code,'是',day,'固定种子模拟')
        for c,v in enumerate(values,1):rows[f'{col(c)}{i}']=v
    return populate(template,{'批次信息':metadata(entity_code,entity,scenario_code,scenario,year,grain,seed),'基准指标':rows})

def change_demo(template,seed,entity_code,entity,scenario_code,scenario,year,grain,blacklist_hashes=()):
    rng=random.Random(f'{seed}|{entity_code}|{scenario_code}|经营变更')
    event_id=f'EVT{seed:010d}';period=f'{year}-03' if grain=='月度' else f'{year}-Q1';day=f'{year}-03-01'
    event=(event_id,'采购条件变化',day,period,'','待审批','本地演示生成器',day,
           '模拟采购条件变化，等待人工审批','','','','','待审批','')
    impact=(event_id,'EXP1.004',period,'增加',random_value(rng,11001,29001,blacklist_hashes),'元','是','固定种子模拟')
    return populate(template,{'批次信息':metadata(entity_code,entity,scenario_code,scenario,year,grain,seed),
                              '事件台账':{f'{col(c)}2':v for c,v in enumerate(event,1) if v!=''},
                              '科目影响':{f'{col(c)}2':v for c,v in enumerate(impact,1)}})
