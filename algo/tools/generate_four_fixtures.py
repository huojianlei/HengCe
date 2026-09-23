"""固定种子一次生成四类演示工作簿及跨主体季度夹具。"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from excel_generate import generate,combine_imports,demo_input
from excel_ingest import import_excel
from external_generate import industry_demo,change_demo

ROOT=Path(__file__).resolve().parents[2]
TEMPLATE=ROOT/'desktop/templates'
OUT=ROOT/'algo/fixtures'
HASHES=json.loads((TEMPLATE/'数值黑名单哈希.json').read_text(encoding='utf-8'))

def build(seed,entity,scenario,grain,prefix):
    files=[];imports=[]
    for category in ('预算基础','实时经营'):
        raw,item=generate((ROOT/f'desktop/experimental/演示底稿-{category}.xlsx').read_bytes(),seed,entity,scenario,grain,HASHES)
        files.append((category,raw));imports.append(item)
    m=imports[0]['metadata'];args=(seed,m['主体编码'],entity,m['情景编码'],scenario,int(m['年度']),grain,HASHES)
    for category,function in (('行业对标',industry_demo),('经营变更',change_demo)):
        raw=function((TEMPLATE/f'{category}输入模板.xlsx').read_bytes(),*args)
        files.append((category,raw));imports.append(import_excel(raw,category+'.xlsx'))
    for category,raw in files:(OUT/f'{prefix}-{category}.xlsx').write_bytes(raw)
    summary=combine_imports(imports)
    return {'种子':seed,'主体':entity,'情景':scenario,'粒度':grain,'文件':len(files),
            '业务行':summary['records']['ruku_shu'],'勾稽':summary['checks']}

if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    results=[build(20260923,'主体甲','基础情景','月度','月度主体甲'),
             build(20260923,'主体乙','扩展情景','季度','季度主体乙')]
    print(json.dumps(results,ensure_ascii=False))
