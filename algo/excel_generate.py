"""离线确定性演示生成器：模板为载体，输入层随机，公式按 Decimal 重算。"""
import hashlib,io,json,random,re,zipfile
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree as ET
from excel_contract import META,SHEETS
from xlsx_reader import Book,NS,ExcelError
from excel_ingest import import_excel

TAG='{'+NS['s']+'}'
def number_hash(v):return hashlib.sha256(str(Decimal(v).normalize()).encode()).hexdigest()

def _generate_once(template,seed,entity='主体甲',scenario='基础情景',grain='月度',blacklist_hashes=()):
    if type(seed)!=int or not 0<=seed<=2**32-1:raise ExcelError('种子必须为 0 到 4294967295 的整数')
    if grain not in ('月度','季度'):raise ExcelError('期间粒度非法')
    if any(not isinstance(s,str) or not 1<=len(s)<=40 or re.search(r'[<>\x00-\x1f]',s) for s in (entity,scenario)):raise ExcelError('主体/情景名称须为 1 至 40 个普通字符')
    book=Book(template);category=book.value('利润表','AY16')
    if category not in ('预算基础','实时经营'):raise ExcelError('演示生成只接受预算基础或实时经营十二表')
    rng=random.Random(f'{seed}|{entity}|{scenario}|{category}')
    blocked=set(blacklist_hashes)
    updates={'主体编码':'E-'+hashlib.sha256(entity.encode()).hexdigest()[:10],'主体名称':entity,
        '情景编码':'S-'+hashlib.sha256(scenario.encode()).hexdigest()[:10],'情景名称':scenario,
        '期间粒度':grain,'生成种子':'种子-'+str(seed)}
    for sheet,cells in book.cells.items():
        for ref,(kind,v) in list(cells.items()):
            if kind=='number':
                # 模板所有硬编码数值均为基础输入参数，不含推导合计。
                quantum=Decimal('0.00001') if abs(v)<1 else Decimal('0.01')
                if sheet=='摊销明细' and re.fullmatch(r'C(32|92)',ref):quantum=Decimal(1)
                for attempt in range(200):
                    x=(v*Decimal(rng.randrange(85001,115000))/100000).quantize(quantum,rounding=ROUND_HALF_UP)
                    if number_hash(x) not in blocked and x>0:break
                else:raise ExcelError('生成输入参数无法避开原始数值黑名单')
                cells[ref]=('number',x)
        for i,key in enumerate(META,1):
            if key in updates:cells[f'AY{i}']=('text',updates[key])
    book.cells['利润表']['C2']=('text',entity+' / '+scenario)
    # Evaluate all formulas before exporting; no stale Excel caches survive generation.
    for sheet,cells in book.cells.items():
        for ref,(kind,v) in cells.items():
            if kind=='formula':book.number(sheet,ref)
    raw=rewrite(template,book)
    result=import_excel(raw)
    return raw,result

def generate(template,seed,entity='主体甲',scenario='基础情景',grain='月度',blacklist_hashes=()):
    """演示失败时按确定性顺序换种子，直到公式与勾稽均通过。"""
    if type(seed)!=int or not 0<=seed<=2**32-1:raise ExcelError('种子必须为 0 到 4294967295 的整数')
    last=None
    for attempt in range(5):
        candidate=(seed+attempt)%(2**32)
        try:return _generate_once(template,candidate,entity,scenario,grain,blacklist_hashes)
        except ExcelError as e:
            # 结构性输入错误无法靠重试修复。
            if not any(word in str(e) for word in ('勾稽','计算','公式除以零','无法避开')):raise
            last=e
    raise ExcelError('五次换种子后仍未通过公式与勾稽') from last

def rewrite(template,book):
    """保持原文件结构和样式，仅更新单元格与缓存；固定 ZIP 时间确保逐字节复现。"""
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(template)) as zin,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as zout:
        rel={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))}
        wb=ET.fromstring(zin.read('xl/workbook.xml'));parts={}
        import posixpath
        for s in wb.find('s:sheets',NS):
            target=rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            part=posixpath.normpath(posixpath.join('xl',target)) if not target.startswith('/') else target.lstrip('/')
            parts[part]=s.attrib['name']
        for name in sorted(zin.namelist()):
            data=zin.read(name)
            if name in parts:
                sheet=parts[name];tree=ET.fromstring(data)
                for c in tree.findall('.//s:c',NS):
                    ref=c.attrib['r']
                    if ref not in book.cells[sheet]:continue
                    kind,value=book.cells[sheet][ref]
                    for child in list(c):
                        if child.tag in (TAG+'v',TAG+'f',TAG+'is'):c.remove(child)
                    c.attrib.pop('t',None)
                    if kind in ('text','str'):
                        c.set('t','inlineStr');ET.SubElement(ET.SubElement(c,TAG+'is'),TAG+'t').text=value
                    elif kind=='number':ET.SubElement(c,TAG+'v').text=str(value)
                    elif kind=='formula':
                        ET.SubElement(c,TAG+'f').text=value
                        ET.SubElement(c,TAG+'v').text=str(book.number(sheet,ref))
                data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            # All shared strings are now inlined; original shared strings here are already sanitized,
            # but removing unused strings prevents old entity/scenario names surviving a new run.
            elif name=='xl/sharedStrings.xml':
                data=f'<sst xmlns="{NS["s"]}" count="0" uniqueCount="0"/>'.encode()
            info=zipfile.ZipInfo(name,(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            zout.writestr(info,data)
    return out.getvalue()

def combine_imports(items):
    """同主体、情景、年度、粒度的四种文件汇成内部旧八字段结构。"""
    if not items:raise ExcelError('导入批次不能为空')
    keys={x['groupKey'] for x in items};categories=[x['category'] for x in items]
    if len(keys)!=1 or len(categories)!=len(set(categories)):raise ExcelError('同组类别重复或主体、情景、期间不一致')
    by={x['category']:x for x in items}
    if not {'预算基础','实时经营'}<=set(by):raise ExcelError('分析须同时提供同版式的预算基础和实时经营工作簿')
    ref=by['预算基础']['metadata']
    for item in items:
        meta=item['metadata']
        for key in ('数据版本号','口径标记','生效周期','已结账截至'):
            if meta[key]!=ref[key]:raise ExcelError(f'四类文件 {key} 不一致')
    groups=('yusuan','shishi','hangye','biangeng','jujue')
    records={g:[row for item in items for row in item['records'][g]] for g in groups}
    records['ruku_shu']=sum(len(records[g]) for g in groups[:-1])
    ledger=by.get('经营变更',{}).get('events',[])
    dedup={}
    for event in ledger:
        key=(event['kemu'],event['period'])
        if key in dedup:
            dedup[key]['reason']+='；'+event['reason']
            dedup[key]['structural']=dedup[key]['structural'] or event['structural']
        else:dedup[key]=dict(event)
    return {'records':records,'metadata':ref,'scope':by['实时经营']['scope'],'subjects':by['预算基础']['subjects'],
            'simulation':any(x['simulation'] for x in items),'benchmarks':by.get('行业对标',{}).get('benchmarks',[]),
            'procurement':[x for item in items for x in item.get('procurement',[])],
            'events':list(dedup.values()),'groupKey':by['预算基础']['groupKey'],'categories':categories,
            'checks':sum(x.get('checks',0) for x in items)}

def demo_input(imported):
    """四类文件合并后沿用旧计算接口；专业评分留待用户补充。"""
    if isinstance(imported,list):imported=combine_imports(imported)
    return {'company':imported['metadata']['主体名称']+' / '+imported['metadata']['情景名称'],
        'simulation':imported['simulation'],'records':imported['records'],'subjects':imported['subjects'],
        'config':dict(imported['scope'],growth=0,industry=None,industryCorrection=False,industryThreshold=50,noise=2500,significance=2500,
            tiers=[{'ming_cheng':'黄','yu_fen':1500,'yan_se':'#ebbf69'},{'ming_cheng':'红','yu_fen':3000,'yan_se':'#e68b8e'}]),
        'bsc':None,'kpi':{},'splits':[],'events':imported.get('events',[]),'traces':[],'baselines':[]}
