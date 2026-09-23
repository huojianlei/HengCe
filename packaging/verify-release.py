"""Verify freshly built archives against current source, before publication."""
import sys,json,hashlib,zipfile,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
output=root/'dist/三栏安装输出'
rows=[]
for variant in ('Production','Experimental'):
    folder=output/variant
    archive=folder/'衡策-1.0.5-便携包.zip'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert not any('/qa/' in n or 'qa-模板包内验证' in n or n.endswith('.pyc') for n in names)
        assert not any(re.search(r'(^|/)(local-llm|llama|ollama|vllm|Qwen[^/]*|GLM[^/]*)(/|$)|\.(gguf|ggml)$',n,re.I) for n in names)
        expected={f'desktop/templates/{kind}输入模板.xlsx':root/f'desktop/templates/{kind}输入模板.xlsx' for kind in ('预算基础','实时经营','行业对标','经营变更')}
        expected['衡策图标.ico']=root/'packaging/assets/衡策图标.ico'
        for file in ('ai-boundary.mjs','ai_worker.py','server.mjs','engine.mjs','bridge.py','web/app.mjs'):
            expected['desktop/'+file]=root/'desktop'/file
        for name,source in expected.items():assert z.read(name)==source.read_bytes(),name
        html=z.read('desktop/web/index.html').decode('utf-8-sig')
        if variant=='Production':
            assert '/experimental/' not in html
            assert not any(n.startswith('desktop/experimental/') for n in names)
        else:
            assert '/experimental/entry.mjs' in html
            assert z.read('desktop/experimental/entry.mjs')==(root/'desktop/experimental/entry.mjs').read_bytes()
        assert json.loads(z.read('desktop/assets.json'))['/template-budget.xlsx'].endswith('预算基础输入模板.xlsx')
    for path in (folder/'衡策-1.0.5-安装包.exe',archive):
        rows.append({'版本':variant,'文件':str(path),'字节数':path.stat().st_size,'SHA256':hashlib.sha256(path.read_bytes()).hexdigest()})
report={'状态':'通过','模板与源码一致':True,'图标一致':True,'正式演示隔离':True,'无本地生成模型工具':True,'文件':rows}
target=root/'临时/三栏发布包核验.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'状态':'通过','报告':str(target),'发布物':len(rows)},ensure_ascii=False))
