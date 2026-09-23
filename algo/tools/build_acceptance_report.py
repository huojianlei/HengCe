"""生成可复现的零残留与勾稽验收报告，不展示原件原始值。"""
import hashlib,json,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from excel_ingest import import_excel
from audit_excel import audit

project=Path(__file__).resolve().parents[3]
dev=project/'开发分支_1.0.5'
source=project/'预算表-利润表0608提交（正常摊销）.xlsx'
files=[dev/'desktop/templates/唯一输入模板.xlsx',dev/'algo/fixtures/唯一模板-月度-主体甲.xlsx',dev/'algo/fixtures/唯一模板-季度-主体乙.xlsx']
items=[]
for path in files:
    result=audit(source,path)
    info=import_excel(path.read_bytes())
    if result['结论']!='通过':raise SystemExit(f'零残留复核失败：{path}')
    items.append({'文件':str(path),'零残留':result,'勾稽断言数':info['checks'],
                  '业务行数':info['records']['ruku_shu'],'主体':info['metadata']['主体名称'],
                  '情景':info['metadata']['情景名称'],'期间粒度':info['metadata']['期间粒度']})
old=json.loads((project/'临时/输入模板105/冻结目录初始哈希.json').read_text(encoding='utf-8'))
frozen={}
for name,baseline in old.items():
    path=project/name
    current={str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest() for p in path.rglob('*') if p.is_file()}
    frozen[name]={'文件数':len(current),'零差异':current==baseline}
if not all(x['零差异'] for x in frozen.values()):raise SystemExit('1.0.4 归档被修改')
release=project/'dist/releases/1.0.5';release_files=[]
for file in release.rglob('*'):
    if file.is_file() and file.suffix in ('.exe','.zip'):
        digest=hashlib.sha256(file.read_bytes()).hexdigest()
        release_files.append({'文件':str(file),'字节数':file.stat().st_size,'SHA256':digest})
if len(release_files)!=4:raise SystemExit('发布物不齐')
for variant in ('Experimental','Production'):
    zip_path=release/variant/'衡策-1.0.5-便携包.zip'
    with zipfile.ZipFile(zip_path) as z:
        packaged=z.read('desktop/templates/唯一输入模板.xlsx')
    if hashlib.sha256(packaged).digest()!=hashlib.sha256(files[0].read_bytes()).digest():raise SystemExit('便携包内模板与脱敏模板不一致')
logs=dev/'临时'
results={'旧插件216项':(logs/'算法插件测试结果.txt').read_text(encoding='utf-8',errors='replace').split('# pass 216')[-1] is not None,
         '旧桌面31项':'# pass 31' in (logs/'桌面原有测试结果.txt').read_text(encoding='utf-8',errors='replace'),
         '模板14项':'Ran 14 tests' in (logs/'新增模板测试结果.txt').read_text(encoding='utf-8',errors='replace') and 'OK' in (logs/'新增模板测试结果.txt').read_text(encoding='utf-8',errors='replace'),
         '接口4项':'# pass 4' in (logs/'模板接口测试结果.txt').read_text(encoding='utf-8',errors='replace'),
         '界面双主体': '"ok":true' in (logs/'界面验收结果.txt').read_text(encoding='utf-8',errors='replace')}
results['旧插件216项']='# pass 216' in (logs/'算法插件测试结果.txt').read_text(encoding='utf-8',errors='replace')
if not all(results.values()):raise SystemExit('测试日志验收失败')
report={'状态':'全部通过','口径说明':'完整数值匹配与结构性位置豁免已获用户确认；原件、两处1.0.4归档保持只读',
        '原件SHA256':hashlib.sha256(source.read_bytes()).hexdigest(),'目标工作簿':items,
        '旧归档核验':frozen,'发布文件':release_files,'测试':results,
        '局限':'实际、采购和行业数值均为占位；三表计算以1.0.5演示会计假设为准，真实账簿待用户提供后另验收'}
output=project/'docs/脱敏与勾稽验收报告-1.0.5.json'
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'报告':str(output),'状态':report['状态'],'工作簿':len(items),'发布文件':len(release_files),'测试':results},ensure_ascii=False))
