"""JSON-only bridge to the existing kb2 search and guarded M5 analysis.

No report rendering lives here. Model keys arrive on stdin and are never saved.
"""
import sys, json, base64, io, contextlib, sqlite3, dataclasses
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'kb2'), str(ROOT / 'fenxi'), str(ROOT / 'algo')]

def search(query, count=4):
    from query_kb2 import jiansuo, zhida, ZHIDA_GESHI
    rows = zhida(query) if ZHIDA_GESHI.match(query) else jiansuo(chaxun=query, shuliang=count)
    with sqlite3.connect(f'file:{(ROOT / "kb2/guanli_ku.sqlite").as_posix()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        sources = {r['zhiyin_hao']: dict(r) for r in db.execute('SELECT * FROM zhiyin')}
    result = []
    for row in rows:
        clean = {k:v for k,v in row.items() if not isinstance(v, bytes)}
        clean['dingwei'] = f"{row['zhiyin_hao']}-{row['tiao_hao']}" + (f"-{row['duan_hao']}" if row.get('duan_hao') else '')
        clean['source'] = sources.get(row['zhiyin_hao'], {})
        result.append(clean)
    return result

def main(req, emit=None):
    if req['op'] == 'import_excel':
        from excel_ingest import import_excel
        return import_excel(base64.b64decode(req['data'], validate=True), req['name'])
    if req['op'] == 'generate_excel':
        from excel_generate import generate, demo_input
        from excel_ingest import import_excel
        from external_generate import industry_demo, change_demo
        hashes=json.loads((ROOT / 'desktop/templates/数值黑名单哈希.json').read_text(encoding='utf-8'))
        seed=req['seed'];entity=req.get('entity','主体甲');scenario=req.get('scenario','基础情景');grain=req.get('grain','月度')
        files=[];items=[]
        for kind in ('预算基础','实时经营'):
            template=(ROOT / f'desktop/experimental/演示底稿-{kind}.xlsx').read_bytes()
            raw,imported=generate(template,seed,entity,scenario,grain,hashes)
            files.append({'category':kind,'base64':base64.b64encode(raw).decode()});items.append(imported)
        meta=items[0]['metadata'];arguments=(seed,meta['主体编码'],entity,meta['情景编码'],scenario,int(meta['年度']),grain)
        raw=industry_demo((ROOT/'desktop/templates/行业对标输入模板.xlsx').read_bytes(),*arguments,hashes)
        files.append({'category':'行业对标','base64':base64.b64encode(raw).decode()});items.append(import_excel(raw,'行业对标.xlsx'))
        raw=change_demo((ROOT/'desktop/templates/经营变更输入模板.xlsx').read_bytes(),*arguments,hashes)
        files.append({'category':'经营变更','base64':base64.b64encode(raw).decode()});items.append(import_excel(raw,'经营变更.xlsx'))
        return {'files':files,'imported':items,'input':demo_input(items),'checks':sum(x.get('checks',0) for x in items)}
    op = req['op']
    if op == 'extract':
        import pymupdf
        raw = base64.b64decode(req['data'], validate=True)
        with pymupdf.open(stream=raw, filetype='pdf') as doc:
            parts = [page.get_text(sort=True) for page in doc]
        if not ''.join(parts).strip():
            raise ValueError('扫描 PDF 没有文本层，请导入 OCR 后的 PDF 或在页面粘贴识别文本。当前未安装 OCR 引擎。')
        return {'text':'\n'.join(parts)}
    if op == 'search':
        return {'references':search(req['query'])}
    if op in ('chat', 'enrich', 'intake'):
        from ai_worker import run
        return run(req, emit)
    if op == 'normalize':
        raise ValueError('云端原始数据解析已停用；请使用本机 Excel 模板解析')
    raise ValueError('不支持的操作')

if __name__ == '__main__':
    sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8')
    try:
        request = json.load(sys.stdin)
        # Third-party diagnostics belong on stderr, never in the JSON protocol.
        def emit(event):
            sys.__stdout__.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
            sys.__stdout__.flush()
        with contextlib.redirect_stdout(sys.stderr): result = main(request, emit if request.get('stream') else None)
        print(json.dumps({'ok':True, **result}, ensure_ascii=False, allow_nan=False))
    except Exception as error:
        print(json.dumps({'ok':False,'error':str(error)}, ensure_ascii=False))
