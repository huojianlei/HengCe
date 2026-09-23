"""只读模板盘点；输出结构与缺陷计数，不输出原始业务数值。"""
import collections
import json
import posixpath
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def inspect(path):
    with zipfile.ZipFile(path) as z:
        rels = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        strings = [''.join(s.itertext()) for s in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        sheets = ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets', NS)
        result = []
        for sheet in sheets:
            target = rels[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            name = posixpath.normpath(posixpath.join('xl', target)) if not target.startswith('/') else target.lstrip('/')
            tree = ET.fromstring(z.read(name))
            cells = tree.findall('.//s:c', NS)
            labels = []
            for c in cells:
                v = c.find('s:v', NS)
                if c.attrib.get('t') == 's' and v is not None:
                    text = strings[int(v.text)]
                    # Only early-column accounting labels and generic headers are reported.
                    if c.attrib['r'].rstrip('0123456789') in ('A', 'B') and len(text) < 22:
                        if not any(w in text for w in ('公司','项目','少年','恐龙','壹陆','剧场','配楼','钼业')):
                            labels.append([c.attrib['r'], text])
            fs = [f.text or '' for f in tree.findall('.//s:f', NS)]
            result.append({'sheet':sheet.attrib['name'], 'part':name,
                'dimension':tree.find('s:dimension', NS).attrib,
                'formulas':len(fs), 'brokenFormulas':sum('#REF!' in f for f in fs),
                'cachedErrors':sum(c.attrib.get('t')=='e' for c in cells),
                'externalFormulas':sum('[' in f for f in fs),
                'labels':labels})
        return result

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(inspect(sys.argv[1]),ensure_ascii=False,indent=2))
