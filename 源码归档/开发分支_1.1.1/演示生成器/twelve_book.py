# -*- coding: utf-8 -*-
"""十二表演示工作簿编排 v1.2：以 ingest_v11 骨架底稿为版面，写输入值层。

v1.2 变化（三表标准对外版式 + 缓存完备 + 主体企业化）：
- 版面基准 = ingest_v11/模板/演示底稿-v1.2-*.xlsx（展示层两列制公式与
  五功能区骨架已在骨架底稿内就位；生成器仍只写演示数值）；
- 缓存完备（铁律⑥）：终稿写出前把全书公式格同文本重发进变更表——
  xlsx_xieqi_v11.patch 对每格求值并写 <f>+<v>，openpyxl data_only
  读回任何公式格缓存不再为 None（旧 v1.1 的 366 无缓存格清零）；
- 主体企业化：企业名由固定种子从字号池+行业词生成（禁"衡策/中学"），
  AY3/C2 同步；AY17 写防撞名声明（12 表同值）。
v1.1 存照（功能区数值层口径不变）：
- Z1 营业外收支月度值 + 加权平均股数（demo_model 种子层）；
- Z2 现金流明细（直接法）：收现=Δ期末现金(月度区行68)+各类付现，保证
  直接法期末==间接法期末逐月恒等；
- Z3 税种分档：城建=ROUND(C33×60%,2)、教育费附加=C33−城建（逐月精确
  合计==税金及附加 C33）；
- Z4 摊销台账双资产：月摊销 1500+600=2100（与老区单资产链精确同答），
  v1.2 起矩阵行名由生成器直写（名称链公式已退役）；
- Z5 分录全账：每月 9 笔（收现/采购/职工/税费/费用五笔现金分录带现金流
  对照 + 摊销计提/所得税计提/收入结转/支出结转四笔非现金分录），
  月度与年度借贷平衡、对照合计==Z2 同位值。
黑名单纪律：功能区数值全部避开老师原件数值哈希（种子层 _safe；推导层
遇命中即抛错改种子，不静默放行）。
"""
import sys  # 双路径引导（ingest_v11+本目录）
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True                     # 引 1.0.5 只读树，不留编译副产物
BEN_MU = Path(__file__).resolve().parent  # 写出器（缓存可缺省）
INGEST_V11 = BEN_MU.parent / 'ingest_v11'  # 功能区坐标唯一事实源
for _lu in (str(INGEST_V11), str(BEN_MU)):
    if _lu not in sys.path:
        sys.path.insert(0, _lu)

import xlsx_xieqi_v11 as xw                         # noqa: E402  写出器（缓存可缺省）
import gongneng_qu as gq                            # noqa: E402  功能区坐标唯一事实源
from demo_model import (Demo, MONTHS, load_blacklist, number_hash,  # noqa: E402
                        FANGZHUANG_SHENGMING)

TEMPLATES = Path(r'D:\AppProject\开发分支_1.0.5\desktop\templates')   # 黑名单（只读）
GUJIA_MU = INGEST_V11 / '模板'                      # v1.2 骨架底稿（本仓库 1.1.1）
BASE_NAMES = {'预算基础': '演示底稿-v1.2-预算基础.xlsx', '实时经营': '演示底稿-v1.2-实时经营.xlsx'}  # v1.2 两列制骨架

#: 现金流对照常量（主体区行号 → 分录用途），与 Z2 明细行一一对应
DUIZHAO = {'shouxian': 4, 'caigou': 8, 'zhigong': 9, 'shuifei': 10, 'qita': 11}  # 员工/其他费用行域（剔 20/29/30）

#: 三表现金费用行域（员工 4-8 / 其他 10-19,21-27,28,31-33；排除 20 折旧摊销与 29/30 利息）
YUANGONG_HANG = (4, 5, 6, 7, 8)  # 激活月：预算 12/实时已结账月
QITA_HANG = (10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 28, 31, 32, 33)


def jihuo_yue(demo):  # 命中即抛错（改种子重跑）
    """激活月字母列表：预算全年；实时=已结账月（未结账月功能区不填列）。"""
    return list(MONTHS) if demo.category == '预算基础' else list(MONTHS[:demo.closed_month])


def _heimingdan_jiancha(demo, zhi, ming):  # 期末现金链预演验证
    """推导值黑名单校验：命中即抛错（改种子重跑，不静默放行）。"""
    if zhi != 0 and number_hash(zhi) in demo.blocked:  # 直接法净增加 = 收现-付现
        raise ValueError(f'{ming} 推导值 {zhi} 命中老师原件数值黑名单，请更换种子')


def _yanyan_duoxian(book, yue, c200, duizhao_zhi):  # 逐月比对期末现金
    """预演验证：直接法期末(区行159)==间接法期末(月度区行68) 逐月恒等。"""
    qian = c200
    for m in yue:  # 预演推导总入口
        i = MONTHS.index(m)
        c = 'CDEFGHIJKLMN'[i]
        z2 = [duizhao_zhi[k][m] for k in duizhao_zhi]
        jing = z2[0] - sum(z2[1:])                   # 直接法净增加 = 收现−付现合计
        qimo = book.number('现金流量表', f'{c}68')  # 对照值桶（五类）
        if qian + jing != qimo:
            raise AssertionError(f'{m} 直接法期末 {qian + jing} != 月度区期末 {qimo}')
        qian = qimo  # 摊销月值（照提口径）


def qu_shuju_duo(book, demo, yue):  # 收入/成本/税金（勾稽区）
    """预演推导：Z2 明细 / Z5 分录 / Z3 分档（全部读自老区公式链实算值）。"""
    c200 = book.number('资产负债表', 'C200')
    duizhao_zhi = {k: {} for k in DUIZHAO}
    fentiao = []
    tan_yue = [book.number('摊销明细', f'{c}33') for c in MONTHS]
    for m in yue:  # 所得税（利润表行 68）
        i = MONTHS.index(m)
        c = 'CDEFGHIJKLMN'[i]  # 员工付现（三表行 4-8）
        # 老区月度链实算值：收入/成本/税金（利润表勾稽区）、所得税（行 68）
        shouru = book.number('利润表', f'{c}61')
        chengben = book.number('利润表', f'{c}62')  # 其他付现（三表现金费用行）
        shuifei = book.number('利润表', f'{c}63')
        suodeshui = book.number('利润表', f'{c}68')
        yuangong = sum((book.number(s, f'{c}{r}') for s in ('销售费用', '管理费用', '蓝恐龙费用')  # 上月期末（首月=期初现金）
                        for r in YUANGONG_HANG), Decimal(0))
        qita = sum((book.number(s, f'{c}{r}') for s in ('销售费用', '管理费用', '蓝恐龙费用')
                    for r in QITA_HANG), Decimal(0))  # 收现 = Δ期末现金 + 四类付现
        qian_qimo = c200 if i == 0 else book.number('现金流量表', f'{"CDEFGHIJKLMN"[i - 1]}68')
        qimo = book.number('现金流量表', f'{c}68')
        # 收现 = Δ期末现金 + 四类付现（保证直接法期末==间接法期末恒等）
        shouxian = (qimo - qian_qimo) + chengben + yuangong + shuifei + qita  # 收现须非负（否则换种子）
        if shouxian < 0:
            raise AssertionError(f'{m} 推导收现为负 {shouxian}，请更换种子')
        for k, v in (('shouxian', shouxian), ('caigou', chengben), ('zhigong', yuangong),  # 推导值黑名单校验
                     ('shuifei', shuifei), ('qita', qita)):
            _heimingdan_jiancha(demo, v, f'{m}{k}')
            duizhao_zhi[k][m] = v  # 记入对照桶
        # 五笔现金分录（带现金流对照）+ 四笔非现金分录（计提/结转）
        hao = f'V11-{demo.category}-{i + 1:02d}'
        fentiao += [  # 分录号前缀（类别+月）
            ('2027-%02d' % (i + 1), f'{hao}-1 销售收现（演示）', '银行存款', '主营业务收入',
             shouxian, shouxian, DUIZHAO['shouxian']),  # ①销售收现（对照 4）
            ('2027-%02d' % (i + 1), f'{hao}-2 采购付现（演示）', '主营业务成本', '银行存款',
             chengben, chengben, DUIZHAO['caigou']),  # ②采购付现（对照 8）
            ('2027-%02d' % (i + 1), f'{hao}-3 工资社保付现（演示）', '应付职工薪酬', '银行存款',
             yuangong, yuangong, DUIZHAO['zhigong']),  # ③工资社保付现（对照 9）
            ('2027-%02d' % (i + 1), f'{hao}-4 税费付现（演示）', '税金及附加', '银行存款',
             shuifei, shuifei, DUIZHAO['shuifei']),  # ④税费付现（对照 10）
            ('2027-%02d' % (i + 1), f'{hao}-5 费用付现（演示合并）', '费用（演示合并）', '银行存款',
             qita, qita, DUIZHAO['qita']),  # ⑤费用付现（对照 11）
            ('2027-%02d' % (i + 1), f'{hao}-6 计提摊销（非现金）', '折旧及摊销', '长期待摊费用',
             tan_yue[i], tan_yue[i], None),  # ⑥计提摊销（非现金）
            ('2027-%02d' % (i + 1), f'{hao}-7 计提所得税（非现金）', '所得税费用', '应交税费',
             suodeshui, suodeshui, None),  # ⑦计提所得税（非现金）
            ('2027-%02d' % (i + 1), f'{hao}-8 收入结转（非现金）', '主营业务收入', '本年利润',
             shouru, shouru, None),  # ⑧收入结转（非现金）
            ('2027-%02d' % (i + 1), f'{hao}-9 支出结转（非现金）', '本年利润', '成本费用（演示合并）',
             chengben + shuifei + yuangong + qita + tan_yue[i],
             chengben + shuifei + yuangong + qita + tan_yue[i], None),  # ⑨支出结转（非现金，合计额）
        ]
    # 预演恒等：直接法期末 == 月度区期末（逐月）
    _yanyan_duoxian(book, yue, c200, duizhao_zhi)
    # Z3 分档：城建 = ROUND(C33×60%,2)，教育费附加 = C33−城建（精确合计）
    fen_dang = {}  # 期末恒等预演
    for m in yue:
        i = MONTHS.index(m)  # Z3 分档：城建四舍五入、教育找零
        c33 = book.number('税金及附加', f'{MONTHS[i]}33')
        chengjian = (c33 * demo.shuizhong_zhanbi[0]).quantize(Decimal('0.01'))
        jiaoyu = c33 - chengjian
        _heimingdan_jiancha(demo, chengjian, f'{m}城建税')
        _heimingdan_jiancha(demo, jiaoyu, f'{m}教育费附加')
        fen_dang[m] = (chengjian, jiaoyu)  # 城建/教育黑名单校验
    return duizhao_zhi, fentiao, fen_dang


def build_changes(demo, meta_updates):  # 变更表构造入口
    """构造 {sheet: {ref: (kind, value)}} 全量变更表（骨架已就位，只写数值）。"""
    changes = {}

    def put(sheet, ref, kind, value):
        changes.setdefault(sheet, {})[ref] = (kind, value)  # 单格写入助手

    yue = jihuo_yue(demo)
    # ---- 1) 老区输入参数层（与 v1.0 生成器同款）----
    for sheet, rev in demo.revenue.items():  # 1) 老区输入层（与 v1.0 同款）
        for m in MONTHS:
            put(sheet, f'{m}31', 'number', rev['price'][m])
            put(sheet, f'{m}32', 'number', rev['qty'][m])
            put(sheet, f'{m}34', 'number', rev['unit_cost'][m])
    put('税金及附加', 'C31', 'number', demo.surtax_rate)
    for sheet, table in demo.expenses.items():  # 综合附加率
        for row, per_month in table.items():  # 费用三表单价/数量区
            for m, (price, qty) in per_month.items():
                put(sheet, f'{m}{row + 200}', 'number', price)   # 单价区 204-233
                put(sheet, f'{m}{row + 320}', 'number', qty)     # 数量区 324-353
    put('摊销明细', 'C31', 'number', demo.amort_cost)  # 摊销原值/月数
    put('摊销明细', 'C32', 'number', demo.amort_months)
    put('利润表', 'C200', 'number', demo.income_tax_rate)  # 所得税率（利润表）
    put('资产负债表', 'C200', 'number', demo.opening_cash)  # 期初现金（资负）
    # ---- 2) 预演：注入老区输入 → 读实算值 → 推导功能区数值层 ----
    book = xw.read_book((GUJIA_MU / BASE_NAMES[demo.category]).read_bytes())
    for sheet, cells in changes.items():  # 2) 预演：注入-读实算-推导
        for ref, (kind, value) in cells.items():  # 骨架底稿读回
            book.cells[sheet][ref] = (kind, value)
    duizhao_zhi, fentiao, fen_dang = qu_shuju_duo(book, demo, yue)
    # ---- 3) Z1 利润表补充披露：营业外收支月度 + 股数（月列 P..AA）----
    for m, (shouru, zhichu) in demo.yingye_wai.items():
        x = gq.QUYUE12[MONTHS.index(m)]
        put('利润表', f'{x}123', 'number', shouru)
        put('利润表', f'{x}124', 'number', zhichu)  # 3) Z1 营业外+股数（月列 P..AA）
    put('利润表', 'P131', 'number', demo.gushu)
    # ---- 4) Z2 现金流明细（直接法五类，月列 P..AA）----
    xjl_hang = {'shouxian': 123, 'caigou': 127, 'zhigong': 128, 'shuifei': 129, 'qita': 130}
    for k, hang in xjl_hang.items():  # 加权平均股数
        for m in yue:  # 4) Z2 五类现金流（月列 P..AA）
            put('现金流量表', f'{gq.QUYUE12[MONTHS.index(m)]}{hang}', 'number', duizhao_zhi[k][m])
    # ---- 5) Z3 税种分档（城建/教育费附加；月列 Q..AB 行 123/124）----
    for m, (cj, jy) in fen_dang.items():  # 逐类逐月写入
        i = MONTHS.index(m)
        put('税金及附加', f'{gq.SHUI_YUE12[i]}123', 'number', cj)  # 5) Z3 分档值+分档率
        put('税金及附加', f'{gq.SHUI_YUE12[i]}124', 'number', jy)
    put('税金及附加', 'P123', 'number', demo.shuizhong_zhanbi[0])
    put('税金及附加', 'P124', 'number', demo.shuizhong_zhanbi[1])
    # ---- 6) Z4 摊销台账（双资产，矩阵月列 P..AA；摊销照提全 12 月）----
    for idx, (ming, biao, bumen, qishi, yuanzhi, yueshu, yue_tan) in enumerate(demo.taizhang):
        hang = 123 + idx  # 6) Z4 台账+矩阵
        put('摊销明细', f'O{hang}', 'text', ming)
        put('摊销明细', f'P{hang}', 'text', biao)
        put('摊销明细', f'Q{hang}', 'text', bumen)  # 台账六字段
        put('摊销明细', f'R{hang}', 'text', qishi)
        put('摊销明细', f'S{hang}', 'number', yuanzhi)
        put('摊销明细', f'T{hang}', 'number', yueshu)
        for i in range(12):                         # 矩阵行 133+：全 12 月（照提口径）
            put('摊销明细', f'{gq.QUYUE12[i]}{133 + idx}', 'number', yue_tan)
        put('摊销明细', f'O{133 + idx}', 'text', ming)  # v1.2：矩阵行名直写（名称链公式已退役）
    # ---- 7) Z5 分录全账（行 124 起顺序写入）----
    hang = 124
    for (yuefen, zhaiyao, jie, dai, jie_e, dai_e, duizhao) in fentiao:  # 7) Z5 分录（行 124 起）
        put('分录', f'O{hang}', 'text', yuefen)
        put('分录', f'P{hang}', 'text', zhaiyao)  # 逐笔九字段
        put('分录', f'Q{hang}', 'text', jie)
        put('分录', f'R{hang}', 'text', dai)
        put('分录', f'S{hang}', 'number', jie_e)
        put('分录', f'T{hang}', 'number', dai_e)
        if duizhao is not None:
            put('分录', f'U{hang}', 'number', Decimal(duizhao))
        put('分录', f'V{hang}', 'text', f'V11-{hang}')
        hang += 1
    # ---- 8) 元数据（每表同值）----
    for sheet in ('利润表', '资产负债表', '现金流量表', '收入非主控', '收入主控', '税金及附加',
                  '销售费用', '管理费用', '蓝恐龙费用', '费用表月度汇总', '摊销明细', '分录'):  # 对照列（现金分录才有）
        for ref, value in meta_updates.items():
            put(sheet, ref, 'text', value)  # 分录号
    put('利润表', 'C2', 'text', f'{demo.entity} / {demo.scenario}')
    return changes  # 8) 元数据+动态标题


def generate_twelve(category, seed, entity, scenario, entity_code, scenario_code,
                    year=2027, grain='月度', closed_month=6, version='演示占位-v1'):
    """生成一本十二表演示工作簿（v1.2 功能区全激活 + 缓存完备），返回 xlsx 字节。"""
    if category not in BASE_NAMES:  # 生成入口（v1.2 全激活）
        raise ValueError('类别必须是预算基础或实时经营')
    # 主体名防御门：非空文本 + 禁词拒收（防 None/旧主体字样静默入簿）
    if not isinstance(entity, str) or not entity.strip():
        raise ValueError('主体名必须为非空文本（企业化命名），不得为 None 或空白')
    for jin_ci in ('衡策', '中学'):
        if jin_ci in entity:
            raise ValueError(f'主体名含禁词 {jin_ci}：{entity}')
    raw = (GUJIA_MU / BASE_NAMES[category]).read_bytes()
    blacklist = load_blacklist(TEMPLATES / '数值黑名单哈希.json')
    demo = Demo(seed, entity, scenario, category, blacklist, closed_month)  # 骨架底稿读入
    meta_updates = {
        'AY2': entity_code, 'AY3': entity, 'AY4': scenario_code, 'AY5': scenario,  # 主体/情景元字段
        'AY15': f'种子-{seed}',  # Demo 参数层构造
        'AY17': FANGZHUANG_SHENGMING,  # v1.2：防撞名声明（12 表同值，白名单文本位）
    }
    changes = build_changes(demo, meta_updates)
    # 前置校验：行 20 折旧摊销合计 == 摊销月摊销（与 v1.0 同款预演门）
    book = xw.read_book(raw)
    for sheet, cells in changes.items():
        for ref, (kind, value) in cells.items():  # 全量变更构造
            book.cells[sheet][ref] = (kind, value)
    for m in MONTHS:
        s = sum((book.number(s, f'{m}20') for s in ('销售费用', '管理费用', '蓝恐龙费用')),  # 前置校验：行 20 摊销勾稽
                Decimal(0))
        if s != demo.amort_monthly:  # 骨架+变更注入
            raise AssertionError(f'{m} 折旧摊销勾稽前置失败: {s} != {demo.amort_monthly}')
    # ---- v1.2 缓存完备（铁律⑥）：全书公式格同文本重发进变更表 ----
    # 演示值已注入 book（上文），逐格重发使 patch 重写 <f> 并补 <v> 计算缓存；
    # openpyxl data_only 读回任何公式格缓存不得为 None（验收硬标准）。
    for sheet in book.cells:  # 逐表扫已注入终态
        for ref, (kind, value) in book.cells[sheet].items():
            if kind == 'formula':  # 只重发公式格
                changes.setdefault(sheet, {})[ref] = ('formula', value)
    return xw.patch(raw, changes), demo
