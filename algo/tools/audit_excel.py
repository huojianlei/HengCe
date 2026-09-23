"""原件只读、全数值黑名单、按位置豁免；报告不含原始数值或标识性文本。"""
import hashlib,json,sys,zipfile,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xlsx_reader import Book
from excel_contract import SHEETS
from build_excel_plan import source_structure
from excel_generate import number_hash

def audit(source,target):
    layout,numbers,texts,evidence=source_structure(source)
    allowed={v for s in layout.values() for v in s['labels'].values()}
    allowed.update(('所得税','招待费','累计折旧','主营业务收入','利润','单位：元','现金流','银行存款','摊销起始日','折旧','利息','固定资产','名称','汽车'))
    # Sheet names are exempt only as sheet identifiers and formula references.
    forbidden={t for t in texts if len(t)>=2 and t not in allowed and t not in SHEETS and not re.fullmatch(r'[\d.％%年月日\-]+',t)}
    forbidden.update(('蓝恐龙','贰零壹陆','少年派','小剧场','北配楼'))
    book=Book(Path(target).read_bytes());hits=[];exemptions=[];checked=0
    for sheet,cells in book.cells.items():
        for ref,(kind,value) in cells.items():
            if kind=='number':
                checked+=1
                if str(value.normalize()) in numbers:hits.append({'位置':sheet+'!'+ref,'类型':'完整数值命中','条目哈希':number_hash(value)})
            elif kind=='formula':
                exemptions.append({'位置':sheet+'!'+ref,'类型':'公式及重算缓存','规则':'用户确认白名单：公式结构'})
                text=value
                for s in SHEETS:text=text.replace("'"+s+"'!",'').replace(s+'!','')
                for term in forbidden:
                    if term in text:hits.append({'位置':sheet+'!'+ref,'类型':'公式标识文本命中','条目哈希':hashlib.sha256(term.encode()).hexdigest()})
            elif kind in ('text','str'):
                for term in forbidden:
                    if term in value:hits.append({'位置':sheet+'!'+ref,'类型':'标识文本命中','条目哈希':hashlib.sha256(term.encode()).hexdigest()})
    # Inspect non-cell XML metadata and relationships, not only displayed cells.
    with zipfile.ZipFile(target) as z:
        for name in z.namelist():
            if name.startswith('xl/worksheets/') or not name.endswith(('.xml','.rels')):continue
            text=z.read(name).decode('utf-8')
            if name=='xl/workbook.xml':
                for s in SHEETS:text=text.replace('name="'+s+'"','name="结构白名单"')
            for term in forbidden:
                if term in text:hits.append({'位置':name,'类型':'包内标识文本命中','条目哈希':hashlib.sha256(term.encode()).hexdigest()})
    return {'结论':'通过' if not hits else '失败','原始数字种类':len(numbers),'检查输入数值':checked,
        '标识文本黑名单条数':len(forbidden),'命中':hits,'白名单逐项记录':exemptions,
        '原件SHA256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        '产物SHA256':hashlib.sha256(Path(target).read_bytes()).hexdigest(),
        '口径':'数据单元格完整数值匹配；公式与重算缓存按位置豁免；标识文本逐项子串检查；sheet名称按XML位置豁免'}

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');report=audit(sys.argv[1],sys.argv[2])
    Path(sys.argv[3]).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('白名单逐项记录','命中')},ensure_ascii=False));print('命中数',len(report['命中']))
    sys.exit(0 if report['结论']=='通过' else 1)
