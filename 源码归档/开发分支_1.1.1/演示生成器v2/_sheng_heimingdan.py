# -*- coding: utf-8 -*-
"""黑名单内嵌生成（开发期一次性）：老师件数值哈希 → heimingdan.py。

一旦生成，运行时不读任何外部文件（"零外部读取"纪律）。
哈希口径：sha256(str(Decimal(v).normalize()))，与 1.0.5 契约一致。

用法：python -B _sheng_heimingdan.py
"""
import json
import sys
from pathlib import Path

MU = Path(__file__).resolve().parent
YUAN = Path(r'D:\AppProject\开发分支_1.0.5\desktop\templates\数值黑名单哈希.json')

TOU = '''# -*- coding: utf-8 -*-
"""数值黑名单（内嵌，运行时不读外部文件）。

老师原件里"硬写的"数值的 sha256 集合（多为资负行次一类的结构数）；
演示数值逐个避让，保证与老师原件数值零重复。
哈希口径：sha256(str(Decimal(v).normalize()))。
"""

HASHES = frozenset((
'''


def main():
    if not YUAN.exists():
        print(f'缺黑名单：{YUAN}')
        return 1
    ha = sorted(set(json.loads(YUAN.read_text(encoding='utf-8'))))
    wen = [TOU]
    for h in ha:
        wen.append(f"    '{h}',\n")
    wen.append('))\n')
    (MU / 'heimingdan.py').write_text(''.join(wen), encoding='utf-8')
    print(f'heimingdan.py 已生成（{len(ha)} 条）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
