# -*- coding: utf-8 -*-
"""版式常量生成（开发期一次性）：_版式档案/*.json → banshi.py。

banshi.py 是运行时唯一的版式依据：程序里定死每张表的
网格规模 / 列宽 / 行高 / 合并区 / 冻结 / 静态标签 / 数字位 / 单元格样式。
运行时不读任何文件。

三表取老师件；九表取旧版骨架（v1.2 预算基础）；外部两册取 1.0.5 模板。
名称类文本一律换成占位符（{主体一}/{主体二}/{项目一}/{主体名}…），由 mingcheng 渲染。

用法：python -B _sheng_banshi.py

====================================================================
这个脚本为什么要存在（而不是运行时读 xlsx）
====================================================================
参照档案是 xlsx，解析它要装 openpyxl、要处理合并区/样式继承/主题色，几百毫秒起步，
而且一旦参照文件缺失或版本变了，运行时就崩。所以采取"开发期固化"：
    _版式档案/*.json（人工从参照表抽取的中间层，纯 JSON、无二进制）
        ↓ 本脚本（一次性）
    banshi.py（生成的 Python 常量，体积大但加载零依赖、零 I/O）
    ↓ import
    xiechu.py（按版式摆骨架、填数）
代价是 banshi.py 是"生成物"，**不要手改**——手改会在下次重跑本脚本时丢失。
需要改版式，就改 _版式档案 里的 JSON（或改本脚本的覆写常量），再重跑。

生成物结构（banshi.py 里的三个字典）
    SAN_BIAO  三表版式（利润表/资产负债表/现金流量表），老师件表样，含名称占位符
    JIU_BIAO  九表版式（税金及附加/销售费用/管理费用/费用表月度汇总/摊销明细/分录）
    WAI_BIAO  外部两册（行业对标/经营变更，各自含多张分表）
    SHEETS    十二表表序，导入/验收共用（顺序 = 输出工作簿 sheet 顺序）
每张表版式字典的键（与 xiechu.py 的消费口径一一对应）：
    dims             (行数, 列数) 网格规模
    lie_kuan         {列号: 宽度}（区间压缩成逐列有效宽度）
    hang_gao         {行号: 高度}（只收显式设过的行）
    hang_gao_mo_ren  表级默认行高（行高里出现次数最多的值）
    hebing           合并区 ['A1:B2', ...]
    freeze           冻结窗格格位或 None
    biaoqian         {格位: 文本}（静态标签；含占位符）
    shuzhi_wei       数值格位清单（写出器据此知道哪些格属"业务数值层"）
    ge_ys            {格位: 样式索引}（逐格样式）
    lie_ys           {列: 样式索引, '*': 兜底}（给参照里没有的新格兜底）
    yangshi          样式表 tuple 列表（字段序见生成的文件头）

口径与纪律
    - 本脚本**只在开发期跑**，不进运行时链路；产品包里可以不带它和 _版式档案。
    - 占位符只替换名称类文本（主体/项目），不动科目名、表头、公式骨架——
      这些属"结构白名单"，替换了导入口就不认。
    - 不写任何主观数值：数值格清单只列"哪些格是数值格"，具体数值由 shuju.py 给。
    - 生成结果必须与仓库里的 banshi.py 一致（否则说明有人手改过生成物）；
      重跑后 git diff 应为空。
"""
import json
import pprint
import sys
from pathlib import Path

MU = Path(__file__).resolve().parent
DANG_AN = MU / '_版式档案'          # 参照档案中间层（JSON）；产品包可删，重跑时需还原

#: 三表：取老师件版式（表样须与财会2019-6号一致，用户一眼能认）
SAN = ('利润表', '资产负债表', '现金流量表')
#: 九表：取旧版骨架 v1.2（预算基础）；顺序决定 JIU_BIAO 与输出 sheet 的先后
JIU = ('税金及附加', '销售费用', '管理费用',
       '费用表月度汇总', '摊销明细', '分录')      # 收入两表、蓝恐龙费用 均已下线
#: 外部两册：1.0.5 输入模板版式（不是十二表体系，各自有多张分表）
WAI = ('行业对标', '经营变更')

#: 三表里的主体/项目名 → 占位符（老师件有真实主体名，必须擦除后换成占位符）
SAN_TIHUAN = (('贰零壹陆', '{主体一}'), ('蓝恐龙', '{主体二}'), ('少年派', '{项目一}'))
#: 官方三表的表头/脚注覆写（编制单位、报表日、演示声明）
#: 覆写放在这里而不是改 JSON：这三项属"产品要求"，与参照表样无关，变了要能一眼看到。
SAN_FU_GAI = {
    '利润表': {'A3': '编制单位：{主体名}', 'B3': '{报表日}',
               'A49': '本表为演示数据（程序生成·纯数值·零公式），不代表真实财务数据。'},
    '资产负债表': {'A3': '编制单位：{主体名}', 'B3': '{报表日}',
                   'A47': '本表为演示数据（程序生成·纯数值·零公式），不代表真实财务数据。'},
    '现金流量表': {'A3': '编制单位：{主体名}', 'B3': '{报表日}',
                   'A44': '本表为演示数据（程序生成·纯数值·零公式），不代表真实财务数据。'},
}
#: 批次元字段覆写（AY 列）：主体/情景/年度/种子/类别
#: AY16 = 数据类别，是"预算基础 vs 实时经营"的唯一判据（两册共用同一套 12 表版式）
YUAN_SHU = {'AY2': '{主体编码}', 'AY3': '{主体名}', 'AY4': '{情景编码}', 'AY5': '{情景}',
            'AY6': '{年度}', 'AY15': '种子-{种子}', 'AY16': '{类别}'}
#: 九表补标签（依《05_四企业对照与衡策映射》§4.1：税金及附加老区行映射）
#: 为什么只补税金及附加：旧骨架这一片的行标签是空的，直接输出会出现"有数无项目"的裸行。
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
#: 模板里这些格本来是空的，不显式列出来写出器就不知道要给它们填数。
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
#: 旧骨架把汇总写死在 463/543/551/640 几处，演示件改用"动态末尾合计"，
#: 这些写死的汇总行必须删掉，否则会出现两套合计、数额还对不上。
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
    """JSON 里的 list → tuple（样式签名要可哈希，便于写出器缓存）。

    参数 v: 任意 JSON 值（list/dict/标量）。
    返回: list 递归转成 tuple，其它原样返回。
    为什么必须转: 样式签名在 xiechu._tiao 里当 dict 的键来缓存
        （`if qian not in dian: dian[qian] = ...`），list 不可哈希会直接 TypeError。
    """
    if isinstance(v, list):
        return tuple(yuan(x) for x in v)
    return v


def zuo_you_lie_kuan(ji_lu, zui_da_lie):
    """区间条目 → 每列有效宽度（后者覆盖前者）。

    参数:
        ji_lu       [(起列, 止列, 宽度), ...]（从 xlsx 抽出来的区间式列宽）。
        zui_da_lie  网格最大列号，用于截断越界区间。
    返回: {列号: 宽度}，按键升序。
    为什么区间要展开: Excel 里列宽是按区间存的（A:C = 12），
        但写出器需要"每一列各自多宽"才能逐列设 column_dimensions。
        后出现的区间覆盖前面的，与 Excel 的赋值语义一致。
    """
    kuan = {}
    for lo, hi, w in ji_lu:
        for i in range(lo, min(hi, zui_da_lie) + 1):
            kuan[i] = w
    return dict(sorted(kuan.items()))


def lie_yangshi(ban):
    """每列默认样式（给"参照里没有、程序新增"的格用）：取该列出现最多的样式。

    参数 ban: 一张表的原始档案 dict（含 cells: {格位: {'s': 样式索引, ...}}）。
    返回: {列字母: 样式索引, '*': 全表兜底样式索引}。

    为什么要"每列众数": 程序会往表里加参照没有的格（分录数据行、台账新行、
        外部册表体）。这些格没有现成样式，若一律用全表众数，可能把数字列套上标题样式。
        按列取众数，等于"这一列通常长什么样，新格就长什么样"，视觉上最不容易露馅。
        兜底列 '*' 用全表众数，只为保证"有样式"，不追求精确。
    """
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
    """一张表 → 版式常量 dict。shu_zhi: 指定数值位；fu_gai: 标签覆写。

    参数:
        ban      原始档案（cells / dims / col_widths / row_heights / merges /
                 freeze / styles），由 _版式档案 的 JSON 给出。
        tihuan   [(原名, 占位符), ...]，名称类文本替换；非空表示"这是三表"
                 （三表里的数字格是行次等结构数字，按数字保留；九表里的数字格一律算数值层）。
        yuan_shu 指定"这些格是元字段标签"（如 AY2 主体编码），优先于 cells 的类型判定。
        shu_zhi  指定"这些格是数值位"，即使档案里是空的也补进清单。
        fu_gai   标签覆写（表头/脚注/演示声明），覆写后从数值位里剔除。
    返回: 版式字典，键见模块 docstring。

    单格判定顺序（顺序有讲究，不能换）:
        1) 在 shu_zhi 里 → 数值位（显式指定优先）
        2) 类型 'f'（公式位）→ 数值位（演示件零公式，但这些格要填数）
        3) 在 yuan_shu 里 → 标签（元字段）
        4) 类型 'n'（数字）→ 三表当结构数字保留为标签；九表算数值位
        5) 其余 → 标签文本，跑一遍名称替换
    """
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
    # 表级默认行高取"出现次数最多"的行高：参照里个别行（标题/表头）是加高的，
    # 若取平均值会把整表拉高或压低，取众数最接近"这张表平时的行高"。
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
        # 数值位排序：先按格位长度（B5 在 B12 前）、再按字典序，
        # 目的是让生成出来的 banshi.py 稳定（同一输入永远同一字节），便于 diff 回归。
        'shuzhi_wei': sorted(shuzhi_wei, key=lambda r: (len(r), r)),
        'ge_ys': ge_ys,
        'lie_ys': lie_yangshi(ban),
        'yangshi': [yuan(s) for s in ban['styles']],
    }


def main():
    """读三套参照档案 → 拼出 SAN_BIAO/JIU_BIAO/WAI_BIAO/SHEETS → 写 banshi.py。

    返回: 0（命令行成功码）。
    副作用: 覆盖写同目录的 banshi.py；控制台打印每张表的 dims/标签数/数字位数，供人工核对。
    异常边界: 档案 JSON 缺失/损坏直接抛（开发期工具，不做容错——静默降级会生成残缺版式，
        而残缺版式要等到生成演示件时才暴露，反而更难查）。
    四步流程:
        1) 三表：只换名称占位符 + 覆写表头脚注
        2) 九表：换元字段占位符、补标签、补数值位，再删旧汇总行/扩网格/取冻结
        3) 平移表（分录/摊销明细）：格位从 121 行 O 列搬到 A1，并重排列宽网格
        4) 外部两册：逐张分表生成，数值位由 WAI_SHU 指定
    """
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
    # 平移要同时搬五样东西：标签、数值位、逐格样式、合并区、列宽——少搬一样就会错位：
    #   标签搬了算式没搬 → 有标题无数字；
    #   样式没搬 → 新格掉回默认宋体；合并区没搬 → 表头断开；
    #   列宽没搬 → 仍是旧骨架的窄列，数字挤成 ####。
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
            if a and b:                       # 合并区任一端落在旧区外 → 整块丢弃
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
    # 落盘用 text 写、不用 pickle：生成物要是人能看、能 git diff 的文本，
    # 这样"版式有没有意外变化"在代码评审里一眼可见。
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
