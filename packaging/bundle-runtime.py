"""Copy the installed Python runtime and dependency closure, never a non-portable venv.

Run using kb/env/Scripts/python.exe; all targets must stay inside the given package.
"""
import sys, shutil, sysconfig, importlib.metadata as md
from pathlib import Path
from packaging.requirements import Requirement

target=Path(sys.argv[1]).resolve()
base=Path(sys.base_prefix)
site=Path(sysconfig.get_paths()['purelib']).resolve()
target.mkdir(parents=True,exist_ok=True)
for item in base.iterdir():
    if item.is_file() and (item.suffix in ['.exe','.dll'] or item.name=='LICENSE.txt'):
        shutil.copy2(item,target/item.name)
shutil.copytree(base/'DLLs',target/'DLLs',dirs_exist_ok=True)
shutil.copytree(base/'Lib',target/'Lib',dirs_exist_ok=True,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','tkinter','ensurepip'))
out=target/'Lib/site-packages';out.mkdir(parents=True,exist_ok=True)
pending=['numpy','onnxruntime','tokenizers','pdfminer.six','pymupdf'];seen=set()
while pending:
    name=pending.pop();dist=md.distribution(name);key=dist.metadata['Name'].lower().replace('_','-')
    if key in seen: continue
    seen.add(key)
    for dep in dist.requires or []:
        req=Requirement(dep)
        if req.marker is None or req.marker.evaluate({'extra':''}):pending.append(req.name)
    for entry in dist.files or []:
        src=Path(dist.locate_file(entry)).resolve()
        if not src.is_relative_to(site) or not src.is_file() or '__pycache__' in src.parts:continue
        # KB uses onnxruntime.InferenceSession only. Do not ship optional
        # transformer conversion/benchmark suites (including llama tooling).
        if src.relative_to(site).parts[:2] == ('onnxruntime','transformers'):continue
        dst=out/src.relative_to(site)
        if not dst.resolve().is_relative_to(target):raise ValueError('Runtime target escapes package')
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
print('Bundled Python dependencies: '+', '.join(sorted(seen)))
