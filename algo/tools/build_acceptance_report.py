"""生成可复现的零残留与勾稽验收报告，不展示原件原始值。"""
import hashlib,json,sys,zipfile,re,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from excel_ingest import import_excel
from audit_excel import audit
from xlsx_reader import Book,ExcelError

project=Path(__file__).resolve().parents[3]
dev=project/'开发分支_1.0.5'
source=project/'预算表-利润表0608提交（正常摊销）.xlsx'
templates=[dev/f'desktop/templates/{kind}输入模板.xlsx' for kind in ('预算基础','实时经营','行业对标','经营变更')]
fixtures=[dev/f'algo/fixtures/{prefix}-{kind}.xlsx' for prefix in ('月度主体甲','季度主体乙')
          for kind in ('预算基础','实时经营','行业对标','经营变更')]
files=templates+fixtures
items=[]
for path in files:
    result=audit(source,path)
    if result['结论']!='通过':raise SystemExit(f'零残留复核失败：{path}')
    # 行业、变更的下载空模板不应伪装成已填写业务数据。
    if path in templates:
        raw=path.read_bytes();book=Book(raw)
        if any(t=='number' for cells in book.cells.values() for t,v in cells.values()):raise SystemExit('下载模板含预填数值')
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            colors=set(re.findall(r'rgb="([0-9A-Fa-f]{8})"',z.read('xl/styles.xml').decode('utf8')))
            if not colors<={'FF000000','FFFFFFFF'}:raise SystemExit('下载模板不是黑白')
        try:import_excel(raw)
        except ExcelError:pass
        else:raise SystemExit('空模板不能被视为完整业务数据')
        items.append({'文件':str(path),'零残留':result,'工作表':path.name.replace('输入模板.xlsx',''),
                      '状态':'空白待填写，不作为业务记录导入','无预填数值':True,'黑白样式':True})
    else:
        info=import_excel(path.read_bytes())
        items.append({'文件':str(path),'零残留':result,'勾稽断言数':info['checks'],
                      '业务行数':info['records']['ruku_shu'],'类别':info['category'],
                      '主体':info['metadata']['主体名称'],'情景':info['metadata']['情景名称'],
                      '期间粒度':info['metadata']['期间粒度']})
old=json.loads((project/'临时/输入模板105/冻结目录初始哈希.json').read_text(encoding='utf-8'))
frozen={}
for name,baseline in old.items():
    path=project/name
    current={str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
    frozen[name]={'文件数':len(current),'零差异':current==baseline}
if not all(x['零差异'] for x in frozen.values()):raise SystemExit('1.0.4 归档被修改')
logs=dev/'临时'
def log(name):return (logs/name).read_text(encoding='utf-8-sig',errors='replace')
results={'空白模板18项':'Ran 18 tests' in log('空白模板测试结果.txt') and 'OK' in log('空白模板测试结果.txt'),
         '四类接口5项':'# pass 5' in log('空白模板接口测试结果.txt')}
if not all(results.values()):raise SystemExit('测试日志验收失败')
report={'状态':'全部通过','口径说明':'完整数值匹配与结构性位置豁免已获用户确认；原件、两处1.0.4归档保持只读',
        '原件SHA256':hashlib.sha256(source.read_bytes()).hexdigest(),'目标工作簿':items,
        '旧归档核验':frozen,'发布状态':'用户要求暂不合包；本报告仅验收当前开发目录模板，不代表现有安装包已更新','测试':results,
        '局限':'四份下载模板均空白待填写。预算和实际夹具、采购及行业构造参考均为占位；真实账簿及可比行业基准待提供后另验收。'}
output=project/'docs/空白黑白模板验收报告-1.0.5.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'报告':str(output),'状态':report['状态'],'工作簿':len(items),'发布状态':report['发布状态'],'测试':results},ensure_ascii=False))
