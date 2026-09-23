"""严格模板导入：先整本验证，再原子映射至既有八字段记录。"""
import csv,dataclasses,io,json,re
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from excel_contract import SHEETS,META,VERSION,ACCOUNTS,EXPENSES,OFFSETS,col,BENCH_HEADERS
from xlsx_reader import Book,ExcelError
from data_ingest import daoru_csv,BIXU_LIE

def cents(v):return int((v*100).quantize(Decimal(1),rounding=ROUND_HALF_UP))

def reconcile(book):
    checks=0
    def equal(a,b,where):
        nonlocal checks
        if cents(a)!=cents(b):raise ExcelError('勾稽不通过：'+where)
        checks+=1
    for off in (0,):
        for m in range(12):
            c=col(m+3)
            for sheet in SHEETS[6:9]:
                equal(book.number(sheet,f'{c}{34+off}'),sum((book.number(sheet,f'{c}{r+off}') for r,_,_ in EXPENSES),Decimal(0)),f'{sheet}月度合计')
            equal(book.number('费用表月度汇总',f'{c}{34+off}'),sum((book.number(s,f'{c}{34+off}') for s in SHEETS[6:9]),Decimal(0)),'费用汇总与明细')
            equal(book.number('资产负债表',f'{c}{63+off}'),book.number('资产负债表',f'{c}{68+off}'),'资产=负债+权益')
            equal(book.number('现金流量表',f'{c}{68+off}'),book.number('资产负债表',f'{c}{61+off}'),'现金流量期末=资产负债表货币资金')
            equal(book.number('现金流量表',f'{c}{61+off}'),book.number('利润表',f'{c}{69+off}'),'现金流量净利润与利润表')
            prev=Decimal(0) if m==0 else book.number('资产负债表',f'{col(m+2)}{66+off}')
            equal(book.number('资产负债表',f'{c}{66+off}')-prev,book.number('利润表',f'{c}{69+off}'),'净利润与未分配利润变动')
            equal(book.number('摊销明细',f'{c}{34+off}')+book.number('摊销明细',f'{c}{35+off}'),book.number('摊销明细',f'{c}{31+off}'),'已摊销+未摊销=原值')
            equal(book.number('利润表',f'{c}{61+off}'),sum((book.number(s,f'{c}{33+off}') for s in SHEETS[3:5]),Decimal(0)),'收入明细与利润表')
            equal(book.number('利润表',f'{c}{62+off}'),sum((book.number(s,f'{c}{36+off}') for s in SHEETS[3:5]),Decimal(0)),'成本明细与利润表')
        for a in ACCOUNTS:
            if a['sheet']=='税金及附加':continue
            r=a['row']+off
            equal(book.number(a['sheet'],f'O{r}'),sum((book.number(a['sheet'],f'{col(m+3)}{r}') for m in range(12)),Decimal(0)),f'{a["code"]}年度小计')
    return checks

def import_twelve_sheet(data,name='标准模板.xlsx'):
    if not isinstance(name,str) or not name.lower().endswith('.xlsx'):raise ExcelError('只接收唯一标准 Excel 模板（.xlsx）')
    book=Book(data)
    if tuple(book.cells)!=SHEETS:raise ExcelError('工作表名称、数量或顺序不符合唯一模板：必须完整保留十二张表')
    # 同一版式根据类别选择预算或实际的固定标题契约；两本不能混成一份。
    category=book.value('利润表','AY16')
    if category not in ('预算基础','实时经营'):raise ExcelError('十二表数据类别须为预算基础或实时经营')
    contract_path=Path(__file__).resolve().parents[1]/f'desktop/templates/模板结构规范-{category}.json'
    if contract_path.exists():
        contract=json.loads(contract_path.read_text(encoding='utf-8'))
        for sheet,schema in contract.items():
            if set(book.cells[sheet])!=set(schema['cells']):raise ExcelError(f'{sheet}单元格结构不符合标准模板')
            if sorted(book.merges[sheet])!=schema['merges']:raise ExcelError(f'{sheet}合并单元格结构被修改')
            for ref,expected in schema['labels'].items():
                if book.value(sheet,ref)!=expected:raise ExcelError(f'固定表头或科目被修改：{sheet}!{ref}')
            for ref,expected in schema['formulas'].items():
                if book.cells[sheet].get(ref)!=('formula',expected):raise ExcelError(f'计算公式被修改：{sheet}!{ref}；请只修改蓝色输入参数')
    meta={}
    for i,key in enumerate(META,1):
        if book.value('利润表',f'AX{i}')!=key:raise ExcelError(f'缺失元字段：{key}')
        value=book.value('利润表',f'AY{i}')
        if not isinstance(value,str) or not value.strip():raise ExcelError(f'元字段必须为非空文本：{key}')
        meta[key]=value.strip()
    if meta['模板版本']!=VERSION:raise ExcelError('模板版本不符，请下载 1.0.5 标准模板')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',meta['主体编码']) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',meta['情景编码']):raise ExcelError('主体/情景编码只能使用字母、数字、下划线或短横线')
    if not re.fullmatch(r'20\d\d',meta['年度']) or meta['期间粒度'] not in ('月度','季度'):raise ExcelError('年度或期间粒度非法')
    if meta['数据状态'] not in ('占位','真实'):raise ExcelError('数据状态须为占位或真实')
    if meta['数据类别']!=category:raise ExcelError('十二表数据类别不一致')
    year=meta['年度'];closed=meta['已结账截至']
    if not re.fullmatch(year+r'-(0[1-9]|1[0-2])',closed):raise ExcelError('已结账截至须为本年月度 YYYY-MM')
    if not re.fullmatch(year+r'-(0[1-9]|1[0-2])',meta['生效周期']):raise ExcelError('生效周期须为本年月度 YYYY-MM')
    for s in SHEETS[1:]:
        for i,key in enumerate(META,1):
            if book.value(s,f'AX{i}')!=key or book.value(s,f'AY{i}')!=meta[key]:raise ExcelError(f'{s}元字段与利润表不一致')
    # 核验账户注册与每一行的七个元字段，禁止缺失、重码或跨版本混用。
    for off in (0,):
        for a in ACCOUNTS:
            s=a['sheet'];r=a['row']+off
            expected=(a['code'],meta['数据版本号'],meta['口径标记'],meta['生效周期'],closed)
            for c,x in zip('PQRST',expected):
                if book.value(s,f'{c}{r}')!=x:raise ExcelError(f'科目编码或元字段不符：{s}!{c}{r}')
            for c in 'UV':
                if not isinstance(book.value(s,f'{c}{r}'),str):raise ExcelError('结构变更标签和受影响科目不能为空，未发生时填“无”')
            for m in range(12):
                x=book.number(s,f'{col(m+3)}{r}')
                if x<0 or x>Decimal('9000000000'):raise ExcelError(f'科目金额超出允许范围：{a["code"]}')
    checks=reconcile(book)
    rows=[];row_meta=[]
    grain=meta['期间粒度'];count=12 if grain=='月度' else 4
    closed_month=int(closed[-2:])
    for a in ACCOUNTS:
        for i in range(count):
            months=[i] if grain=='月度' else [i*3,i*3+1,i*3+2]
            if category=='实时经营' and max(months)+1>closed_month:continue
            period=f'{year}-{i+1:02}' if grain=='月度' else f'{year}-Q{i+1}'
            amount=sum((book.number(a['sheet'],f'{col(m+3)}{a["row"]}') for m in months),Decimal(0))
            note={'主体编码':meta['主体编码'],'情景编码':meta['情景编码'],'科目唯一编码':a['code'],
                  '数据版本号':meta['数据版本号'],'口径标记':meta['口径标记'],'生效周期':meta['生效周期'],
                  '已结账标记':category=='实时经营','结构性变更标签':book.value(a['sheet'],f'U{a["row"]}'),
                  '受影响科目':book.value(a['sheet'],f'V{a["row"]}'),'源工作表':a['sheet'],'源行':a['row'],
                  '数据状态':meta['数据状态']}
            rows.append([category,period,a['name'],f'{amount:.2f}','元','确定性模拟模板' if meta['数据状态']=='占位' else '标准Excel模板',closed+'-01',json.dumps(note,ensure_ascii=False)])
            row_meta.append(note)
    stream=io.StringIO();writer=csv.writer(stream);writer.writerow(BIXU_LIE);writer.writerows(rows)
    records=daoru_csv(stream.getvalue())
    if records.jujue:raise ExcelError('标准字段转换未通过校验，整本拒绝')
    benchmark=[]
    procurement=[]
    for s in SHEETS[3:5]:
        for m in range(12):
            c=col(m+3)
            procurement.append({'主体编码':meta['主体编码'],'情景编码':meta['情景编码'],'期间':f'{year}-{m+1:02}',
                '项目编码':s,'数据状态':meta['数据状态'],'预算采购金额分':cents(book.number(s,f'{c}37')) if category=='预算基础' else None,
                '实际采购金额分':cents(book.number(s,f'{c}37')) if category=='实时经营' and m+1<=closed_month else None,
                '预算单价':str(book.number(s,f'{c}34')),'预算数量':str(book.number(s,f'{c}35')),
                '供应商编码':'占位供应商','来源':'模板收入明细采购参数；不得再次计入成本合计'})
    period=closed if grain=='月度' else f'{year}-Q{closed_month//3}'
    if category=='实时经营' and grain=='季度' and closed_month<3:raise ExcelError('季度模式至少需要一个完整已结账季度')
    record_data=dataclasses.asdict(records);record_data['ruku_shu']=records.ruku_shu
    return {'records':record_data,'subjects':[{k:a[k] for k in ('module','direction')}|{'kemu':a['name'],'accountCode':a['code']} for a in ACCOUNTS],
        'metadata':meta,'category':category,'benchmarks':benchmark,'procurement':procurement,'checks':checks,'text':stream.getvalue(),
        'groupKey':json.dumps([meta['主体编码'],meta['情景编码'],year,grain],ensure_ascii=False),
        'scope':{'cycle':grain,'period':period},'simulation':meta['数据状态']=='占位'}

def import_excel(data,name='标准模板.xlsx'):
    """按唯一固定工作表序列分派三套版式、四种数据类别。"""
    if not isinstance(name,str) or not name.lower().endswith('.xlsx'):raise ExcelError('只接收固定 Excel 模板（.xlsx）')
    names=tuple(Book(data).cells)
    if names==SHEETS:return import_twelve_sheet(data,name)
    from external_templates import industry,changes
    if names==('批次信息','基准指标'):return industry(data)
    if names==('批次信息','事件台账','科目影响'):return changes(data)
    raise ExcelError('工作表结构不符合预算/实际、行业对标或经营变更任一固定模板')
