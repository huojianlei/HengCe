# -*- coding: utf-8 -*-
"""版式常量生成（开发期一次性）：_版式档案/*.json → banshi.py。

banshi.py 是运行时唯一的版式依据：程序里定死每张表的
网格规模 / 列宽 / 行高 / 合并区 / 冻结 / 静态标签 / 数字位 / 单元格样式。
运行时不读任何文件。

三表取老师件；九表取旧版骨架（v1.2 预算基础）；外部两册取 1.0.5 模板。
名称类文本一律换成占位符（{主体一}/{主体二}/{项目一}/{主体名}…），由 mingcheng 渲染。

用法：python -B _sheng_banshi.py
"""
import json
import pprint
import sys
from pathlib import Path

MU = Path(__file__).resolve().parent
DANG_AN = MU / '_版式档案'

SAN = ('利润表', '资产负债表', '现金流量表')
JIU = ('税金及附加', '销售费用', '管理费用',
       '费用表月度汇总', '摊销明细', '分录')      # 收入两表、蓝恐龙费用 均已下线
WAI = ('行业对标', '经营变更')

SAN_TIHUAN = (('贰零壹陆', '{主体一}'), ('蓝恐龙', '{主体二}'), ('少年派', '{项目一}'))
#: 官方三表的表头/脚注覆写（编制单位、报表日、演示声明）
SAN_FU_GAI = {
    '利润表': {'A3': '编制单位：{主体名}', 'B3': '{报表日}',
               'A49': '本表为演示数据（程序生成·纯数值·零公式），不代表真实财务数据。'},
    '资产负债表': {'A3': '编制单位：{主体名}', 'B3': '{报表日}',
                   'A47': '本表为演示数据（程序生成·纯数值·零公式），不代表真实财务数据。'},
    '现金流量表': {'A3': '编制单位：{主体名}', 'B3': '{报表日}',
                   'A44': '本表为演示数据（程序生成·纯数值·零公式），不代表真实财务数据。'},
}
YUAN_SHU = {'AY2': '{主体编码}', 'AY3': '{主体名}', 'AY4': '{情景编码}', 'AY5': '{情景}',
            'AY6': '{年度}', 'AY15': '种子-{种子}', 'AY16': '{类别}'}
#: 九表补标签（依《05_四企业对照与衡策映射》§4.1：税金及附加老区行映射）
JIU_FU_GAI = {
    '分录': {},
    '税金及附加': dict(
        {'B2': '项目（月度，元）', 'O2': '年合计',
         'B3': '增值税（非主控）', 'B4': '增值税（主控）',
         'B7': '城市维护建设税（7%）', 'B8': '教育费附加（3%）',
         'B9': '地方教育附加（2%）', 'B10': '文化事业建设费（3%）'},
        **{f'{c}2': f'{i + 1}月' for i, c in enumerate('CDEFGHIJKLMN')}),
}
#: 九表补数值位（上面对应各行的 C..N 月列 + O 年合计）
JIU_SHU_ZHI = {
    '税金及附加': [f'{c}{r}' for r in (3, 4, 6, 7, 8, 9, 10)
                   for c in 'CDEFGHIJKLMNO'],
    # 分录合计行由写出器按数据末尾动态落位（行数随月份数变化），版式不再写死
    '分录': [],
}
#: 九表扩容后的网格（分录数据区 124-540）
JIU_DIMS = {'分录': (545, 51)}
#: 平移后的列宽与网格（分录 A..H、摊销 A..N）
PIAN_LIE = {
    '分录': {1: 12, 2: 26, 3: 20, 4: 20, 5: 16, 6: 16, 7: 10, 8: 12},
    '摊销明细': {1: 18, **{c: 12 for c in range(2, 15)}},
}
PIAN_DIMS = {'分录': (665, 51), '摊销明细': (29, 51)}
#: 九表取消冻结（这两张表的数据在 121 行 O 列起，冻结 A4 反而挡住视图）
JIU_FREEZE = {'摊销明细': None, '分录': None}
#: 九表删除的旧格位（分录原汇总行）
JIU_SHAN = {'分录': ('O463', 'O464', 'O465', 'S463', 'T464', 'U465',
                     'O543', 'O544', 'O545', 'S543', 'T544', 'U545',
                     'O551', 'O552', 'O553', 'S551', 'T552', 'U553',
                     'O640', 'O641', 'O642', 'S640', 'T641', 'U642')}
#: 外部两册的数值位（批次信息的 B 列是值不是标签；表体整行由程序填）
WAI_SHU = {
    '行业对标': {'批次信息': [f'B{r}' for r in range(1, 16)],
                 '基准指标': [f'{x}{r}' for r in range(2, 7)
                              for x in 'CDEFGHIJKLMNOPQR']},
    '经营变更': {'批次信息': [f'B{r}' for r in range(1, 16)],
                 '事件台账': [f'{x}{r}' for r in (2, 3) for x in 'ABCDEFGHIJKLMNO'],
                 '科目影响': [f'{x}{r}' for r in (2, 3) for x in 'ABCDEFGH']},
}


def yuan(v):
    """JSON 里的 list → tuple（样式签名要可哈希，便于写出器缓存）。"""
    if isinstance(v, list):
        return tuple(yuan(x) for x in v)
    return v


def zuo_you_lie_kuan(ji_lu, zui_da_lie):
    """区间条目 → 每列有效宽度（后者覆盖前者）。"""
    kuan = {}
    for lo, hi, w in ji_lu:
        for i in range(lo, min(hi, zui_da_lie) + 1):
            kuan[i] = w
    return dict(sorted(kuan.items()))


def lie_yangshi(ban):
    """每列默认样式（给"参照里没有、程序新增"的格用）：取该列出现最多的样式。"""
    ji = {}
    for ref, v in ban['cells'].items():
        lie = ''.join(c for c in ref if c.isalpha())
        ji.setdefault(lie, {})
        ji[lie][v['s']] = ji[lie].get(v['s'], 0) + 1
    zui_duo = {}
    quan = {}
    for _, v in ban['cells'].items():
        quan[v['s']] = quan.get(v['s'], 0) + 1
    mo_ren = max(quan, key=quan.get) if quan else 0
    for lie, cishu in ji.items():
        zui_duo[lie] = max(cishu, key=cishu.get)
    zui_duo['*'] = mo_ren
    return zui_duo


def zhuang_biao(ban, tihuan=(), yuan_shu=None, shu_zhi=(), fu_gai=None):
    """一张表 → 版式常量 dict。shu_zhi: 指定数值位；fu_gai: 标签覆写。"""
    dims = tuple(ban['dims'])
    biaoqian, shuzhi_wei, ge_ys = {}, [], {}
    for ref, v in ban['cells'].items():
        ge_ys[ref] = v['s']
        if ref in shu_zhi:
            shuzhi_wei.append(ref)
            continue
        if v['k'] == 'f':
            shuzhi_wei.append(ref)
            continue
        if yuan_shu and ref in yuan_shu:
            biaoqian[ref] = yuan_shu[ref]
            continue
        if v['k'] == 'n':
            if tihuan:                          # 三表：行次等结构性数字按数字保留
                biaoqian[ref] = int(float(v['v'])) if float(v['v']).is_integer() else float(v['v'])
            else:                               # 九表 / 外部册：数字格一律是数值层
                shuzhi_wei.append(ref)
            continue
        wen = v['v']
        for jiu, xin in tihuan:
            wen = wen.replace(jiu, xin)
        biaoqian[ref] = wen
    for ref in shu_zhi:                         # 指定数值位：模板里本是空的也要补进清单
        biaoqian.pop(ref, None)
        if ref not in shuzhi_wei:
            shuzhi_wei.append(ref)
    for ref, wen in (fu_gai or {}).items():     # 表头/脚注覆写
        biaoqian[ref] = wen
        if ref in shuzhi_wei:
            shuzhi_wei.remove(ref)
    gao = {int(r): h for r, h in ban['row_heights'].items()}
    chang = None
    if gao:
        chang = max(set(gao.values()), key=list(gao.values()).count)
    return {
        'dims': dims,
        'lie_kuan': zuo_you_lie_kuan(ban['col_widths'], dims[1]),
        'hang_gao': gao,
        'hang_gao_mo_ren': chang,
        'hebing': list(ban['merges']),
        'freeze': ban.get('freeze'),
        'biaoqian': biaoqian,
        'shuzhi_wei': sorted(shuzhi_wei, key=lambda r: (len(r), r)),
        'ge_ys': ge_ys,
        'lie_ys': lie_yangshi(ban),
        'yangshi': [yuan(s) for s in ban['styles']],
    }


def main():
    guan = json.loads((DANG_AN / '官方三表.json').read_text(encoding='utf-8'))
    jiu = json.loads((DANG_AN / '旧版骨架-v1.2-预算基础.json').read_text(encoding='utf-8'))
    san = {m: zhuang_biao(guan[m], SAN_TIHUAN, fu_gai=SAN_FU_GAI[m]) for m in SAN}
    jiu_biao = {m: zhuang_biao(jiu[m], (), YUAN_SHU,
                               JIU_SHU_ZHI.get(m, ()), JIU_FU_GAI.get(m))
                for m in JIU}
    for m, cuo in JIU_SHAN.items():                       # 删除旧格位
        for ref in cuo:
            jiu_biao[m]['biaoqian'].pop(ref, None)
            if ref in jiu_biao[m]['shuzhi_wei']:
                jiu_biao[m]['shuzhi_wei'].remove(ref)
    for m, dims in JIU_DIMS.items():                      # 网格扩容
        jiu_biao[m]['dims'] = dims
    for m, dong in JIU_FREEZE.items():                    # 取消冻结
        jiu_biao[m]['freeze'] = dong
    # 分录/摊销明细：从 121 行 O 列搬到 A1（演示件不需要旧骨架的空白老区）
    from banmian import PIAN_BIAO, xin
    for m in PIAN_BIAO:
        ban = jiu_biao[m]
        ban['biaoqian'] = {r2: v for r, v in ban['biaoqian'].items()
                           for r2 in [xin(m, r)] if r2}
        ban['shuzhi_wei'] = [r2 for r in ban['shuzhi_wei'] for r2 in [xin(m, r)] if r2]
        ban['ge_ys'] = {r2: v for r, v in ban['ge_ys'].items()
                        for r2 in [xin(m, r)] if r2}
        he = []
        for qu in ban['hebing']:
            tou, _, wei = qu.partition(':')
            a, b = xin(m, tou), xin(m, wei)
            if a and b:
                he.append(f'{a}:{b}')
        ban['hebing'] = he
        ban['hang_gao'] = {}                              # 统一默认行高
        ban['lie_kuan'] = dict(PIAN_LIE[m])
        ban['dims'] = PIAN_DIMS[m]
        ban['freeze'] = None
    wai = {}
    for m in WAI:
        d = json.loads((DANG_AN / f'外部-{m}.json').read_text(encoding='utf-8'))
        wai[m] = {b: zhuang_biao(d[b], (), None, WAI_SHU[m].get(b, ()))
                  for b in d}
    cu = pprint.pformat
    wen = ['# -*- coding: utf-8 -*-']
    wen.append('"""版式常量（由 _sheng_banshi.py 从参照档案生成，请勿手改）。')
    wen.append('')
    wen.append('三表版式：老师件 ｜ 九表版式：旧版骨架 v1.2 ｜ 外部两册：1.0.5 输入模板')
    wen.append('runtime 不读任何文件：尺寸/合并/标签/数字位/单元格样式全部在程序里定死。')
    wen.append('样式签名（yangshi / ge_ys / lie_ys 引用）字段序：')
    wen.append('  0 字体名 1 字号 2 粗体 3 斜体 4 下划线 5 字色 ｜ 6 填充型 7 前景 8 背景')
    wen.append('  9-12 左/右/上/下边框(线型,色) ｜ 13 水平 14 垂直 15 自动换行 16 数字格式')
    wen.append('  颜色签名为 ("rgb", "FF000000") / ("theme", n, tint) / ("indexed", n) 或 None')
    wen.append('"""')
    wen.append('')
    wen.append('#: 三表版式（老师件版式，标签含名称占位符）')
    wen.append('SAN_BIAO = ' + cu(san, width=110, sort_dicts=False, compact=True))
    wen.append('')
    wen.append('#: 九表版式（旧版骨架版式）')
    wen.append('JIU_BIAO = ' + cu(jiu_biao, width=110, sort_dicts=False, compact=True))
    wen.append('')
    wen.append('#: 外部两册版式（1.0.5 输入模板版式）')
    wen.append('WAI_BIAO = ' + cu(wai, width=110, sort_dicts=False, compact=True))
    wen.append('')
    wen.append('#: 十二表表序（导入/验收共用）')
    wen.append('SHEETS = ' + repr(tuple(SAN) + tuple(JIU)))
    wen.append('')
    (MU / 'banshi.py').write_text('\n'.join(wen), encoding='utf-8')
    print('banshi.py 已生成')
    for m in SAN:
        print(f'  [三表] {m} dims={san[m]["dims"]} 标签={len(san[m]["biaoqian"])} '
              f'数字位={len(san[m]["shuzhi_wei"])} 样式={len(guan[m]["styles"])}')
    for m in JIU:
        print(f'  [九表] {m} dims={jiu_biao[m]["dims"]} 标签={len(jiu_biao[m]["biaoqian"])} '
              f'数字位={len(jiu_biao[m]["shuzhi_wei"])} 样式={len(jiu[m]["styles"])}')
    for m in WAI:
        for b, v in wai[m].items():
            print(f'  [外部] {m}/{b} dims={v["dims"]} 标签={len(v["biaoqian"])} '
                  f'数值位={len(v["shuzhi_wei"])}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
