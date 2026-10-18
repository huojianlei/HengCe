# -*- coding: utf-8 -*-
"""版式摘要（开发期一次性）：把 _版式档案/*.json 转成可读文本，便于抄成程序常量。

产出（落 _版式档案/）：
    摘要-老师三表.txt   —— 三表：有效列宽 / 行高 / 合并 / 标签 / 数字位 / 公式
    摘要-旧版九表.txt   —— 九表：同上

用法：python -B _zhaiyao.py
"""
import json
import sys
from pathlib import Path

MU = Path(__file__).resolve().parent
DANG_AN = MU / '_版式档案'

#: 三表取老师件、九表取旧版骨架（budget 版为准，实时版版式一致）
SAN_BIAO = ('利润表', '资产负债表', '现金流量表')
JIU_BIAO = ('税金及附加', '销售费用', '管理费用',
            '蓝恐龙费用', '费用表月度汇总', '摊销明细', '分录')


def you_xiao_lie_kuan(ji_lu, zui_da_lie):
    """区间条目 → 每列有效宽度（后写的区间覆盖先写的，与 Excel 一致）。"""
    kuan = {}
    for lo, hi, w in ji_lu:
        for i in range(lo, min(hi, zui_da_lie) + 1):
            kuan[i] = w
    return kuan


def lie_ming(i):
    """列号 → 字母。"""
    out = ''
    while i:
        i, n = divmod(i - 1, 26)
        out = chr(65 + n) + out
    return out


def hang_gao_zhai(gao):
    """行高压缩：全同 → '全 X'；否则 默认+例外。"""
    if not gao:
        return '（无显式行高）'
    zhi = {v for v in gao.values()}
    if len(zhi) == 1:
        return f'全 {zhi.pop()}（{len(gao)} 行）'
    chang = max(set(gao.values()), key=list(gao.values()).count)
    li = {r: v for r, v in gao.items() if v != chang}
    return f'默认 {chang}；例外 {li}'


def xie_biao(f, ming, ban, shou_gongshi=True):
    """写一张表的摘要。"""
    dims = ban['dims']
    f.write(f'### {ming}  dims={dims}  合并={len(ban["merges"])}  冻结={ban["freeze"]}\n')
    kuan = you_xiao_lie_kuan(ban['col_widths'], dims[1])
    f.write('列宽: ' + ' '.join(f'{lie_ming(i)}={kuan.get(i, "-")}' for i in range(1, dims[1] + 1)) + '\n')
    f.write(f'行高: {hang_gao_zhai(ban["row_heights"])}\n')
    f.write('合并: ' + ', '.join(ban['merges']) + '\n')
    zi = {}
    for ref, v in ban['cells'].items():
        r = int(''.join(c for c in ref if c.isdigit()))
        zi.setdefault(r, []).append((ref, v))
    for r in sorted(zi):
        ji = []
        for ref, v in sorted(zi[r], key=lambda kv: (len(kv[0]), kv[0])):
            if v['k'] == 't':
                ji.append(f'{ref}={v["v"]!r}')
            elif v['k'] == 'n':
                ji.append(f'{ref}=数[{v["v"]}]')
            else:
                wen = v['v'] if shou_gongshi else (v['v'][:40] + '…')
                ji.append(f'{ref}=式[{wen}]')
        f.write(f'  r{r}: ' + ' | '.join(ji) + '\n')
    f.write('\n')


def main():
    lao = DANG_AN / '老师件.json'
    jiu = DANG_AN / '旧版骨架-v1.2-预算基础.json'
    for p in (lao, jiu):
        if not p.exists():
            print(f'缺 {p}，先跑 _tiqu_banshi.py')
            return 1
    d_lao = json.loads(lao.read_text(encoding='utf-8'))
    d_jiu = json.loads(jiu.read_text(encoding='utf-8'))
    with (DANG_AN / '摘要-老师三表.txt').open('w', encoding='utf-8') as f:
        f.write('三表版式（源：老师件）\n\n')
        for ming in SAN_BIAO:
            xie_biao(f, ming, d_lao[ming])
    with (DANG_AN / '摘要-旧版九表.txt').open('w', encoding='utf-8') as f:
        f.write('九表版式（源：旧版骨架 v1.2 预算基础）\n\n')
        for ming in JIU_BIAO:
            xie_biao(f, ming, d_jiu[ming])
    print('摘要已落盘')
    return 0


if __name__ == '__main__':
    sys.exit(main())
