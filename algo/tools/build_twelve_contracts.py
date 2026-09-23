"""从内部脱敏模型固化两类共用12表的允许输入位置和固定公式。"""
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xlsx_reader import Book

root=Path(__file__).resolve().parents[2]
for category in ('预算基础','实时经营'):
    source=root/f'desktop/experimental/演示底稿-{category}.xlsx'
    book=Book(source.read_bytes());result={}
    for sheet,cells in book.cells.items():
        labels={ref:value for ref,(kind,value) in cells.items()
                if kind in ('text','str')
                and not re.fullmatch(r'AY(?:[2-9]|1[0-5]|1[78])',ref)
                and not re.fullmatch(r'[Q-V]\d+',ref)
                and not (sheet=='利润表' and ref=='C2')
                and not (sheet=='摊销明细' and ref=='C36')
                and not re.fullmatch(r'20\d\d-(?:0[1-9]|1[0-2])',str(value))}
        result[sheet]={'cells':sorted(cells),'merges':sorted(book.merges[sheet]),
                       'labels':labels,'formulas':{ref:v for ref,(kind,v) in cells.items() if kind=='formula'}}
    target=root/f'desktop/templates/模板结构规范-{category}.json'
    target.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(category,'工作表',len(result),'允许业务输入数',sum(len(x['cells'])-len(x['formulas'])-len(x['labels']) for x in result.values()))
