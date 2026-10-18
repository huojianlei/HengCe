# -*- coding: utf-8 -*-
"""严格模板导入 v1.1——fork 自 1.0.5 algo/excel_ingest.py，扩容不破老。

与 1.0.5 的关系（三条纪律）：
    1) 老区零改动：12 表表名/元字段/月度表头/科目行校验/94 项年度小计与
       226 项勾稽（reconcile）逐字保留——老 12 表文件（无任何新格）照进，
       行为与 1.0.5 完全一致；
    2) 白名单扩容两块（铁律⑥）：A) 既有展示区行的空白月度格（利润表行
       4-20 与现金流量表行 4-40 的 D..N、费用三表/汇总表行 35/36 的
       C..N 及 O 列年度小计）进白名单并逐字固化公式——出现即必须与固化
       文本完全一致，且同表镜像层"触格即全量"，比 1.0.5 更严；B) 前沿
       功能区（行 121-480 × 列 15-41）五区骨架（标签+公式）完整性硬校验；
    3) 非白名单格仍然拒收（老 cells ∪ 新 cells 全量白名单，逐格子集判断）。

功能区数据按"内部底稿与勾稽依据"口径读入 result['zones']（不进八字段
业务行、不动 226 计数）；新区恒等式计数入 result['zone_checks']。
契约 JSON 与骨架底稿由本包 jian_qiyue_v11.py 生成（模板/ 目录）。
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）
"""
import csv                                            # 八字段 CSV 组装（records 折算）
import dataclasses                                    # DaoruJieguo dataclass 摊平
import io                                             # 内存 CSV 流
import json                                           # 契约加载 + 备注列序列化
import re                                             # 元字段/月份正则
import sys                                            # sys.path 引导 1.0.5 只读树
from decimal import Decimal, ROUND_HALF_UP            # 元→分 half-up 舍入
from pathlib import Path                              # 契约文件定位

BEN_MU = Path(__file__).resolve().parent              # 本包根（契约/模板相对锚点）

sys.path.insert(0, str(BEN_MU))                       # 本包优先（excel_contract_v11/gongneng_qu）
ALGO = r'D:\AppProject\开发分支_1.0.5\algo'            # 1.0.5 算法树（只读引用）
if ALGO not in sys.path:
    sys.path.insert(0, ALGO)                           # 幂等插入（重复导入不重复加）

from excel_contract_v11 import (SHEETS, META, VERSION, ACCOUNTS, EXPENSES,  # noqa: E402
                                OFFSETS, col, BENCH_HEADERS, V11_BANBEN,
                                V12_BANBEN, V12_QIYUE_MING, V12_MUBAN_BANBEN)
import gongneng_qu as gq                            # noqa: E402  功能区布局（唯一事实源）
from xlsx_reader import Book, ExcelError            # noqa: E402
from data_ingest import daoru_csv, BIXU_LIE         # noqa: E402

#: 功能区金额域（与老区科目同界：非负、90 亿以内，元）
QU_SHANGXIAN = Decimal('9000000000')                  # 功能区金额上限（90 亿元，元）

#: 分录月份合法格式（本年 YYYY-MM；年度一致性另查）
YUEFEN_ZE = re.compile(r'(\d{4})-(0[1-9]|1[0-2])')


def cents(v):
    """元 Decimal → 整数分（half-up；与 1.0.5 逐字同式）。"""
    return int((v * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def reconcile(book):
    """老区 226 项勾稽——与 1.0.5 excel_ingest.reconcile 逐字一致（零改动）。

    计数口径（1.0.5 原样）：12 月 × 11 项月度勾稽 = 132 项，加 94 项科目
    年度小计（O 列 = Σ12 月），合计 226 项；任何一项不相等即整本拒绝。
    """
    checks = 0

    def equal(a, b, where):
        """单勾等式：分币比较（规避 Decimal 元位尾差），不等即抛错。"""
        nonlocal checks
        if cents(a) != cents(b):
            raise ExcelError('勾稽不通过：' + where)
        checks += 1

    for off in (0,):                                # 行位移口径与 1.0.5 一致（仅 0）
        for m in range(12):                         # 逐月（1-12 月）核 11 项恒等式
            c = col(m + 3)                          # 月度列 C..N
            # 恒等式 1-3：三张费用表行 34 月度合计 = 行 4-33 明细之和
            for sheet in SHEETS[6:9]:               # 销售/管理/蓝恐龙三表同式
                equal(book.number(sheet, f'{c}{34+off}'),
                      sum((book.number(sheet, f'{c}{r+off}') for r, _, _ in EXPENSES), Decimal(0)),
                      f'{sheet}月度合计')            # 报错定位到具体表
            # 恒等式 4：费用表月度汇总行 34 = 三表行 34 之和
            equal(book.number('费用表月度汇总', f'{c}{34+off}'),
                  sum((book.number(s, f'{c}{34+off}') for s in SHEETS[6:9]), Decimal(0)),
                  '费用汇总与明细')
            # 恒等式 5：资产总计（行 63）= 负债（行 68，含权益合计口径）
            equal(book.number('资产负债表', f'{c}{63+off}'), book.number('资产负债表', f'{c}{68+off}'),
                  '资产=负债+权益')
            # 恒等式 6：现金流量表期末现金 = 资负货币资金（月度区行 61）
            equal(book.number('现金流量表', f'{c}{68+off}'), book.number('资产负债表', f'{c}{61+off}'),
                  '现金流量期末=资产负债表货币资金')
            # 恒等式 7：间接法净利润（行 61）= 利润表净利润（行 69）
            equal(book.number('现金流量表', f'{c}{61+off}'), book.number('利润表', f'{c}{69+off}'),
                  '现金流量净利润与利润表')
            # 恒等式 8：未分配利润环比变动 = 当月净利润（首月基数为 0）
            prev = Decimal(0) if m == 0 else book.number('资产负债表', f'{col(m+2)}{66+off}')
            equal(book.number('资产负债表', f'{c}{66+off}') - prev,
                  book.number('利润表', f'{c}{69+off}'), '净利润与未分配利润变动')
            # 恒等式 9：摊销明细 已摊销+未摊销 = 原值（行 34/35 对 31）
            equal(book.number('摊销明细', f'{c}{34+off}') + book.number('摊销明细', f'{c}{35+off}'),
                  book.number('摊销明细', f'{c}{31+off}'), '已摊销+未摊销=原值')
            # 恒等式 10：利润表收入（行 61）= 两张收入表行 33 之和
            equal(book.number('利润表', f'{c}{61+off}'),
                  sum((book.number(s, f'{c}{33+off}') for s in SHEETS[3:5]), Decimal(0)),
                  '收入明细与利润表')
            # 恒等式 11：利润表成本（行 62）= 两张收入表行 36 之和
            equal(book.number('利润表', f'{c}{62+off}'),
                  sum((book.number(s, f'{c}{36+off}') for s in SHEETS[3:5]), Decimal(0)),
                  '成本明细与利润表')
        # 年度层：94 个科目的 O 列年度小计 = 12 个月之和（税金表单行科目跳过）
        for a in ACCOUNTS:                           # 注册表逐科目核年度合计
            if a['sheet'] == '税金及附加':            # 税金无 12 月明细行（单率驱动）
                continue
            r = a['row'] + off
            equal(book.number(a['sheet'], f'O{r}'),
                  sum((book.number(a['sheet'], f'{col(m+3)}{r}') for m in range(12)), Decimal(0)),
                  f'{a["code"]}年度小计')             # 报错定位到科目编码
    return checks


# ======================================================================
# 扩展层校验：镜像公式逐字钉死 + 功能区骨架完整性（校验比 1.0.5 更严）
# ======================================================================

def jiaoyan_ext(book, qiyue):
    """镜像层"触格即全量+逐字"；功能区"触区即骨架齐+逐字"。

    两级严格度都高于 1.0.5：1.0.5 对这些格位是"出现即拒"；v1.1 是"出现
    就必须长成契约规定的样子"——既放开了合法填列，又钉死了自由发挥。
    """
    ext = qiyue['ext']
    # 功能区公式位集合（用于从 ext 公式里剥离出"纯镜像层"）
    qu_gongshi_wei = {(q['sheet'], r) for q in ext['zones'].values() for r in q['formulas']}
    # 每区"全部格位"= 标签+公式+输入（触区判据用）
    qu_suoyou = {zid: (set(q['labels']) | set(q['formulas']) | set(q['inputs']))
                 for zid, q in ext['zones'].items()}
    for biao in SHEETS:
        # ---- A) 镜像层：本表出现任一镜像格 → 全表镜像公式必须齐且逐字一致 ----
        jingxiang_wei = [r for r in ext['formulas'][biao] if (biao, r) not in qu_gongshi_wei]
        if any(r in book.cells[biao] for r in jingxiang_wei):
            for r in jingxiang_wei:
                # 缺格：镜像层是成套固化公式，出现一格就要求整套在场
                if r not in book.cells[biao]:
                    raise ExcelError(f'镜像公式缺失：{biao}!{r}；镜像格已出现，本表镜像层必须完整固化')
                # 改格：文本与契约不一致（含填数值/填文本）都拒
                if book.cells[biao][r] != ('formula', ext['formulas'][biao][r]):
                    raise ExcelError(f'镜像公式被修改：{biao}!{r}；月度镜像格只接受固化公式')
        # ---- B) 功能区：任一格在册 → 标签与固化公式骨架必须齐且逐字一致 ----
        for zid, qu in ext['zones'].items():
            if qu['sheet'] != biao:
                continue                                # 只查本表的区
            if not any(r in book.cells[biao] for r in qu_suoyou[zid]):
                continue                                # 整区无格 = v1.0.5 文件，兼容放行
            for r in qu['labels']:
                # 标签逐字校验：区名/表头/行项目一个都不能少、不能改
                if book.value(biao, r) != ext['labels'][biao][r]:
                    if r not in book.cells[biao]:
                        raise ExcelError(f'功能区标签缺失：{qu["biaoti"]}（{biao}!{r}）')
                    raise ExcelError(f'功能区标签被修改：{qu["biaoti"]}（{biao}!{r}）')
            for r in qu['formulas']:
                # 固化公式逐字校验：小计/净额/期末/合计链必须原样在场
                if book.cells[biao].get(r) != ('formula', ext['formulas'][biao][r]):
                    if r not in book.cells[biao]:
                        raise ExcelError(f'功能区公式缺失：{qu["biaoti"]}（{biao}!{r}）')
                    raise ExcelError(f'功能区公式被修改：{qu["biaoti"]}（{biao}!{r}）')


def _jian_shuru(book, biao, ref, qiwang):
    """功能区输入格类型与金额域校验（在册才查；数值格回读 Decimal）。"""
    x = book.cells[biao].get(ref)
    if x is None:
        return None                                     # 未填列 = 合法空（无发生额留空）
    zhong, zhi = x
    # 数值位只认真数值：公式/文本混入数值位即拒（比老区输入格更严）
    if qiwang == 'number' and zhong != 'number':
        raise ExcelError(f'功能区输入类型不符：{biao}!{ref} 应为数值')
    # 文本位只认文本（数字串也不行——防把月份/科目填成数值）
    if qiwang == 'text' and zhong not in ('text', 'str'):
        raise ExcelError(f'功能区输入类型不符：{biao}!{ref} 应为文本')
    if qiwang == 'number':
        # 金额域：非负且 ≤90 亿（与老区科目同界，元口径）
        if zhi < 0 or zhi > QU_SHANGXIAN:
            raise ExcelError(f'功能区金额超出允许范围：{biao}!{ref}')
        return zhi
    return zhi


def _zhi(book, biao, ref):
    """读功能区数值（缺格按 0——求和口径；在册则经 Book 求值）。"""
    if ref not in book.cells[biao]:
        return Decimal(0)
    return book.number(biao, ref)


# ======================================================================
# 功能区数据导入与恒等式（zones 结构 + zone_checks 计数；不进八字段）
# ======================================================================

def qu_lirun_buchong(book, ext):
    """Z1 利润表补充披露区：披露行月度输入 + 股数 + 每股收益链。"""
    biao = '利润表'
    shuru = ext['zones']['lirun_buchong']['inputs']
    # 整区激活判据：任一输入格在册（营业外/投资收益月度值或股数）
    if not any(r in book.cells[biao] for r in shuru):
        return None, 0
    biaoshi = ext['labels'][biao]
    yueye = {}
    # 七个披露行逐行读 12 个月（行名取区标签，输出键即报表行项目名）
    for r in range(123, 130):
        yueye[biaoshi[f'O{r}']] = [_jian_shuru(book, biao, f'{x}{r}', 'number')
                                    for x in gq.QUYUE12]
    # 股数为每股收益链的除数：激活即必须给出正值
    gushu = _jian_shuru(book, biao, 'P131', 'number')
    if gushu is None or gushu <= 0:
        raise ExcelError('功能区校验不通过：每股收益缺少正的加权平均股数（利润表!P131）')
    # 恒等式 2 条：其中项不超母项（年度合计口径，固化公式求值）
    if _zhi(book, biao, 'AB125') > _zhi(book, biao, 'AB124'):
        raise ExcelError('功能区勾稽不通过：非流动资产处置损失超过营业外支出年度合计')
    if _zhi(book, biao, 'AB127') > _zhi(book, biao, 'AB126'):
        raise ExcelError('功能区勾稽不通过：对联营合营投资收益超过投资收益年度合计')
    # 每股收益由固化公式求值回读（披露口径净利润 = C20 + 披露净影响）
    return {'yueye': yueye, 'gushu': gushu,
            'eps_jicheng': book.number(biao, 'AB132'),
            'eps_xishi': book.number(biao, 'AB133')}, 2


def qu_xianjinliu(book, ext):
    """Z2 现金流量表月度明细区：明细月度输入 + 期末现金与月度区逐月恒等。"""
    biao = '现金流量表'
    shuru = ext['zones']['xianjinliu_mingxi']['inputs']
    # 整区激活判据：任一明细输入在册
    if not any(r in book.cells[biao] for r in shuru):
        return None, 0
    mingxi = {}
    # 明细行（含汇率行）逐行读 12 个月；键 = 主体区行号（对照列同域）
    for r, lei in gq.XJL_LEIXING.items():
        if lei != 'd':
            continue
        mingxi[str(r)] = [_jian_shuru(book, biao, f'{x}{r + gq.XJL_WEIYI}', 'number')
                          for x in gq.QUYUE12]
    checks = 0
    for i in range(12):
        lie = gq.QUYUE12[i]
        # 月激活：该列任一明细输入在册才核（未填列月份按"无发生额留空"惯例跳过）
        if not any(f'{lie}{r + gq.XJL_WEIYI}' in book.cells[biao]
                   for r, lei in gq.XJL_LEIXING.items() if lei == 'd'):
            continue
        # 恒等式：直接法期末现金 == 月度间接法区行 68 期末（两条路同一个钱袋）
        if _zhi(book, biao, f'{lie}159') != _zhi(book, biao, f'{gq.YUE12[i]}68'):
            raise ExcelError(f'功能区勾稽不通过：现金流量表期末现金与月度区不符：{i + 1}月')
        checks += 1
    return {'mingxi': mingxi,
            'qimo_yue': [book.number(biao, f'{x}159') for x in gq.QUYUE12]}, checks


def qu_shuizhong(book, ext):
    """Z3 税种分档区：分档月度输入 + 分档合计与税金及附加逐月恒等。"""
    biao = '税金及附加'
    yue_ceng = gq.SHUI_YUE12                             # 分档区月列 Q..AB（P 列是率）
    # 整区激活判据：任一税种月度值在册（只填率不激活——率无金额即无勾稽对象）
    if not any(f'{x}{r}' in book.cells[biao] for r in range(123, 127) for x in yue_ceng):
        return None, 0
    biaoshi = ext['labels'][biao]
    shuizhong, lv = {}, []
    # 四个税种行逐行读月度值与分档率（率只登记不参与恒等式——口径披露用）
    for r in range(123, 127):
        shuizhong[biaoshi[f'O{r}']] = [_jian_shuru(book, biao, f'{x}{r}', 'number')
                                       for x in yue_ceng]
        lv.append(_jian_shuru(book, biao, f'P{r}', 'number'))
    checks = 0
    for i in range(12):
        # 月激活：该月任一税种有值才核（未填列月份跳过）
        if not any(f'{yue_ceng[i]}{r}' in book.cells[biao] for r in range(123, 127)):
            continue
        # 恒等式：分档合计行 == 老区税金及附加 C..N 33（一口率与分档必须同一答案）
        if _zhi(book, biao, f'{yue_ceng[i]}127') != _zhi(book, biao, f'{gq.YUE12[i]}33'):
            raise ExcelError(f'功能区勾稽不通过：税种分档合计与税金及附加不符：{i + 1}月')
        checks += 1
    return {'shuizhong': shuizhong, 'lv': lv,
            'heji_yue': [book.number(biao, f'{x}127') for x in yue_ceng]}, checks


def qu_tanxiao(book, ext):
    """Z4 摊销台账区：台账行完整性 + 矩阵月度合计与本月摊销逐月恒等。"""
    biao = '摊销明细'
    # 两层激活：矩阵月值或台账字段任一在册（只填一层也至少核行完整性）
    juzhen_cunzai = any(f'{x}{r}' in book.cells[biao]
                        for r in gq.JUZHEN_HANG for x in gq.QUYUE12)
    taizhang_cunzai = any(f'{c}{r}' in book.cells[biao]
                          for r in gq.TAIZHANG_HANG for c in 'OPQRST')
    if not (juzhen_cunzai or taizhang_cunzai):
        return None, 0
    taizhang = []
    for r in gq.TAIZHANG_HANG:
        # 触行必齐：台账行出现任一字段 → 名称/归属表/部门/起始月/原值/月数齐备
        if any(f'{c}{r}' in book.cells[biao] for c in 'OPQRST'):
            que = [c for c in 'OPQRST' if f'{c}{r}' not in book.cells[biao]]
            if que:
                raise ExcelError(f'功能区校验不通过：摊销台账行字段不完整（摊销明细!第{r}行 缺{"".join(que)}列）')
            # 月摊销额读固化公式值（ROUND(原值/MAX(月数,1),2) 与老区 C33 同式）
            taizhang.append({
                'mingcheng': _jian_shuru(book, biao, f'O{r}', 'text'),
                'guishu_biao': _jian_shuru(book, biao, f'P{r}', 'text'),
                'bumen': _jian_shuru(book, biao, f'Q{r}', 'text'),
                'qishi_yue': _jian_shuru(book, biao, f'R{r}', 'text'),
                'yuanzhi': _jian_shuru(book, biao, f'S{r}', 'number'),
                'yueshu': _jian_shuru(book, biao, f'T{r}', 'number'),
                'yue_tanxiao': book.number(biao, f'U{r}'),
            })
    juzhen, checks = [], 0
    # 矩阵行名优先对位台账行（O 列固化公式直链），无台账时按序号占名
    for idx, r in enumerate(gq.JUZHEN_HANG):
        ming = taizhang[idx]['mingcheng'] if idx < len(taizhang) else f'资产{idx + 1}'
        juzhen.append({'mingcheng': ming,
                       'yue': [_jian_shuru(book, biao, f'{x}{r}', 'number')
                               for x in gq.QUYUE12]})
    for i in range(12):
        lie = gq.QUYUE12[i]
        # 月激活：该月矩阵任一资产有值才核
        if not any(f'{lie}{r}' in book.cells[biao] for r in gq.JUZHEN_HANG):
            continue
        # 恒等式：矩阵合计行 == 老区本月摊销 C..N 33（多资产合计与单链同答）
        if _zhi(book, biao, f'{lie}142') != _zhi(book, biao, f'{gq.YUE12[i]}33'):
            raise ExcelError(f'功能区勾稽不通过：摊销台账月度合计与本月摊销不符：{i + 1}月')
        checks += 1
    return {'taizhang': taizhang, 'juzhen': juzhen,
            'heji_yue': [book.number(biao, f'{x}142') for x in gq.QUYUE12]}, checks


def qu_fenlu(book, ext, nian_du):
    """Z5 分录全账区：行完整性/月份域/对照白名单 + 借贷平衡 + 与现金流明细互证。"""
    biao = '分录'
    a, b = gq.FENLU_HANG                                  # 分录行区间 124-460
    fentiao = []
    for r in range(a, b + 1):
        lie_wei = [f'{c}{r}' for c in 'OPQRSTUV']
        # 空行直接跳过（全账区允许稀疏填列）
        if not any(w in book.cells[biao] for w in lie_wei):
            continue
        # 触行必齐：月份/摘要/借方科目/贷方科目/借贷金额六要素缺一即拒
        que = [c for c in 'OPQRST' if f'{c}{r}' not in book.cells[biao]]
        if que:
            raise ExcelError(f'功能区校验不通过：分录行字段不完整（分录!第{r}行 缺{"".join(que)}列）')
        # 月份格式：YYYY-MM（四位年-两位月，fullmatch 锚定）
        yuefen = _jian_shuru(book, biao, f'O{r}', 'text')
        pei = YUEFEN_ZE.fullmatch(yuefen)
        if not pei:
            raise ExcelError(f'功能区校验不通过：分录月份格式不符（分录!第{r}行）')
        # 月份年份必须等于批次年度（跨年分录不属本账）
        if pei.group(1) != nian_du:
            raise ExcelError(f'功能区校验不通过：分录月份与年度不符（分录!第{r}行）')
        # 对照列：可空（非现金分录）；填了必须是现金流明细行号（白名单+整数）
        duizhao = _jian_shuru(book, biao, f'U{r}', 'number')
        if duizhao is not None and (duizhao != duizhao.to_integral_value()
                                    or int(duizhao) not in gq.DUIZHAO_HEFA):
            raise ExcelError(f'功能区校验不通过：分录现金流对照行项目无效（分录!第{r}行）')
        # 一条分录 = 七字段（借贷科目/金额 + 对照 + 摘要 + 编号）
        fentiao.append({'yuefen': yuefen,
                        'zhaiyao': _jian_shuru(book, biao, f'P{r}', 'text'),
                        'jiefang_kemu': _jian_shuru(book, biao, f'Q{r}', 'text'),
                        'daifang_kemu': _jian_shuru(book, biao, f'R{r}', 'text'),
                        'jiefang_jine': _jian_shuru(book, biao, f'S{r}', 'number'),
                        'daifang_jine': _jian_shuru(book, biao, f'T{r}', 'number'),
                        'duizhao': None if duizhao is None else int(duizhao),
                        'bianhao': _jian_shuru(book, biao, f'V{r}', 'text')})
    if not fentiao:
        return None, 0
    # 恒等式①：全年借贷平衡（固化公式求值）
    if _zhi(book, biao, 'S463') != _zhi(book, biao, 'T464'):
        raise ExcelError('功能区勾稽不通过：分录全年借贷不平衡')
    checks = 1
    # 恒等式②：逐月借贷平衡（月度分组累加后逐键比较）
    yue_jie, yue_dai = {}, {}
    for t in fentiao:
        yue_jie[t['yuefen']] = yue_jie.get(t['yuefen'], Decimal(0)) + t['jiefang_jine']
        yue_dai[t['yuefen']] = yue_dai.get(t['yuefen'], Decimal(0)) + t['daifang_jine']
    for yuefen, jie in sorted(yue_jie.items()):
        if jie != yue_dai.get(yuefen, Decimal(0)):
            raise ExcelError(f'功能区勾稽不通过：分录月度借贷不平衡：{yuefen}')
        checks += 1
    # 恒等式③：现金流对照逐（行,月）互证——分录合计 == 现金流明细区同位值
    xjl_biao = '现金流量表'
    duizhao_he = {}
    for t in fentiao:
        if t['duizhao'] is None:
            continue                                    # 非现金分录不进互证
        jian = (t['duizhao'], t['yuefen'])
        duizhao_he[jian] = duizhao_he.get(jian, Decimal(0)) + t['jiefang_jine']
    for (dui, yuefen), he in sorted(duizhao_he.items()):
        # 明细区同位格：主体区行号 +119 → 功能区行；月序 → 月列
        i = int(yuefen[-2:]) - 1
        ref = f'{gq.QUYUE12[i]}{dui + gq.XJL_WEIYI}'
        mu_biao = _zhi(book, xjl_biao, ref)
        # 任一侧非零就必须相等（两侧同零视为未发生，不计数不打扰）
        if (he != Decimal(0) or mu_biao != Decimal(0)) and he != mu_biao:
            raise ExcelError(f'功能区勾稽不通过：分录与现金流量表明细不符：主体区第{dui}行 {yuefen}')  # 勾稽报错定位到主体区行+月份
        checks += 1  # 互证恒等式计数
    return {'fentiao': fentiao, 'jiefang_heji': book.number(biao, 'S463'),  # 分录区回读结构（合计经固化公式求值）
            'daifang_heji': book.number(biao, 'T464')}, checks


def qu_daoru(book, qiyue, meta):
    """五个功能区统一入口：未激活区返回 None，激活区出数据并计恒等式数。"""
    zones, checks = {}, 0  # zones=激活区数据；checks=新区恒等式计数
    # 顺序固定：利润披露 → 现金流明细 → 税种 → 摊销 → 分录（分录互证依赖前区在场）
    for zid, hanshu in (('lirun_buchong', qu_lirun_buchong),  # 区导入顺序表（分录互证依赖现金流区在场）
                        ('xianjinliu_mingxi', qu_xianjinliu),
                        ('shuizhong_fendang', qu_shuizhong),
                        ('tanxiao_taizhang', qu_tanxiao),
                        ('fenlu_quanzhang', lambda b, e: qu_fenlu(b, e, meta['年度']))):  # 分录需批次年度（月份一致性校验）
        shuju, n = hanshu(book, qiyue['ext'])  # 逐区导入（未激活返回 None）
        if shuju is not None:  # 激活区才入结果
            zones[zid] = shuju  # 区数据登记
            checks += n  # 恒等式计数累加
    return zones, checks


# ======================================================================
# 主入口：12 表整本导入（老区流程逐字保留 + 扩展层插入）
# ======================================================================

def import_twelve_sheet(data, name='标准模板.xlsx'):
    """严格导入一本 12 表工作簿：老区校验/勾稽逐字保留，扩展层更严校验。"""
    if not isinstance(name, str) or not name.lower().endswith('.xlsx'):  # 文件类型门
        # 只收 xlsx：拒旧 xls/CSV/自由格式（输入口定死四类 Excel 模板）
        raise ExcelError('只接收唯一标准 Excel 模板（.xlsx）')  # 文案与 1.0.5 逐字一致
    book = Book(data)  # Book：受限解包 + Decimal 公式引擎
    if tuple(book.cells) != SHEETS:  # 表序列完整性门
        # 12 表表名+顺序逐一核对（多表/少表/改名/换序都整本退回）
        raise ExcelError('工作表名称、数量或顺序不符合唯一模板：必须完整保留十二张表')  # 12 表名+顺序硬校验
    # 同一版式根据类别选择预算或实际的固定标题契约；两本不能混成一份。
    category = book.value('利润表', 'AY16')  # 类别锚点：AY16（红线坐标）
    if category not in ('预算基础', '实时经营'):  # 类别二值门
        raise ExcelError('十二表数据类别须为预算基础或实时经营')  # 非法类别整本退回
    # ---- 契约轨道探测（v1.2 双轨）：利润表 C3 表头定轨道 ----
    # v1.2 新版式：C3 以"本期金额（"开头（三表两列制）；老版式：C3 以"全年"开头。
    # 新轨道按 v1.2 契约+新版本串校验；老轨道按冻结的 v1.1 契约+1.0.5 版本串
    # 校验——老底稿与 v1.1 演示件照进零漂移（老 226 勾稽两轨共用、逐字不变）。
    biaotou = book.value('利润表', 'C3')  # 轨道探针（展示表头）
    if isinstance(biaotou, str) and biaotou.startswith('本期金额（'):
        guidao = V12_BANBEN  # 新轨道
        qiyue_lu = BEN_MU / '模板' / V12_QIYUE_MING.format(类别=category)  # v1.2 契约路径
        qiwang_banben = V12_MUBAN_BANBEN  # AY1 新版本串
        jianque_tishi = '缺 v1.2 契约文件：请先在 ingest_v11 运行 jian_qiyue_v11.py'  # 缺件提示
    else:
        guidao = V11_BANBEN  # 老轨道（v1.1 契约冻结留档）
        qiyue_lu = BEN_MU / '模板' / f'模板结构规范-v1.1-{category}.json'  # v1.1 契约路径
        qiwang_banben = VERSION  # AY1 旧版本串（1.0.5 原样）
        jianque_tishi = '缺 v1.1 契约文件：请先在 ingest_v11 运行 jian_qiyue_v11.py'  # 缺件提示
    if not qiyue_lu.exists():  # 契约缺失门
        raise ExcelError(jianque_tishi)  # 引导先跑构建器
    qiyue = json.loads(qiyue_lu.read_text(encoding='utf-8'))  # 契约加载（base+ext+cells）
    base = qiyue['base']  # base 段=1.0.5 原契约
    for sheet, schema in base.items():  # 逐表四道门
        # 白名单 = 老 cells ∪ 新 cells（非白名单格仍然拒收）
        if not set(book.cells[sheet]) <= set(qiyue['cells'][sheet]):  # 白名单子集判断（老∪新）
            raise ExcelError(f'{sheet}出现标准模板以外的单元格')  # 非白名单格拒收
        # 合并区逐格比对（新区零合并，故 merges 集合与 1.0.5 完全一致）
        if sorted(book.merges[sheet]) != schema['merges']:  # 合并区双向一致
            raise ExcelError(f'{sheet}合并单元格结构被修改')  # 合并被改整本退回
        # 老区固定表头/科目标签逐字校验（元字段键、科目名、表头）
        for ref, expected in schema['labels'].items():  # 标签逐字校验
            if book.value(sheet, ref) != expected:  # 标签不符定位到格
                raise ExcelError(f'固定表头或科目被修改：{sheet}!{ref}')  # 报错带表名+格位
        # 老区契约公式位逐字校验（缺位/改文本都拒，提示只动蓝色输入参数）
        for ref, expected in schema['formulas'].items():  # 公式逐字校验
            if book.cells[sheet].get(ref) != ('formula', expected):  # 类型+文本双核
                raise ExcelError(f'计算公式被修改：{sheet}!{ref}；请只修改蓝色输入参数')  # 提示语 1.0.5 逐字
    # 扩展层（镜像层 + 功能区）：出现即逐字钉死、触区即骨架齐——比 1.0.5 更严
    jiaoyan_ext(book, qiyue)  # 扩展层两级严校验
    meta = {}  # 元字段桶
    # ---- 元字段链（AX1:AY16 十六键）：键名、非空、跨表一致逐项核 ----
    for i, key in enumerate(META, 1):  # 十六键逐键核
        if book.value('利润表', f'AX{i}') != key:  # 键名不符即缺失
            raise ExcelError(f'缺失元字段：{key}')  # 报错带键名
        value = book.value('利润表', f'AY{i}')  # 读值列 AY
        # 值必须非空文本（数字/空白/None 都拒）
        if not isinstance(value, str) or not value.strip():  # 值非空文本门
            raise ExcelError(f'元字段必须为非空文本：{key}')  # 数字/空白都拒
        meta[key] = value.strip()  # 入桶（strip 后）
    # 模板版本按轨道钉死：v1.2 新版本串 / 老轨道 1.0.5 原串（AY1 十二表一致）
    if meta['模板版本'] != qiwang_banben:  # 版本钉死（轨道内）
        raise ExcelError('模板版本不符，请下载标准模板')  # 版本不符引导
    # 主体/情景编码字符域：字母数字下划线短横线，防注入分隔符
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', meta['主体编码']) \
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', meta['情景编码']):
        raise ExcelError('主体/情景编码只能使用字母、数字、下划线或短横线')  # 文案 1.0.5 逐字
    # 年度 20xx 四位；期间粒度只认月度/季度
    if not re.fullmatch(r'20\d\d', meta['年度']) or meta['期间粒度'] not in ('月度', '季度'):  # 年度/粒度双核
        raise ExcelError('年度或期间粒度非法')  # 非法即拒
    # 数据状态只认占位/真实（演示口径必须显式声明）
    if meta['数据状态'] not in ('占位', '真实'):  # 数据状态二值门
        raise ExcelError('数据状态须为占位或真实')  # 演示口径必须显式
    # 批次内数据类别自洽（AY16 与判定出的类别一致）
    if meta['数据类别'] != category:  # 类别一致性
        raise ExcelError('十二表数据类别不一致')  # 批次内不许混类
    year = meta['年度']  # 年度（后续分录用）
    closed = meta['已结账截至']  # 已结账截至（截断用）
    # 已结账截至/生效周期必须是本年月份（YYYY-MM 与年度前缀双核）
    if not re.fullmatch(year + r'-(0[1-9]|1[0-2])', closed):  # 截至月份格式门
        raise ExcelError('已结账截至须为本年月度 YYYY-MM')  # 须本年 YYYY-MM
    if not re.fullmatch(year + r'-(0[1-9]|1[0-2])', meta['生效周期']):  # 生效周期格式门
        raise ExcelError('生效周期须为本年月度 YYYY-MM')  # 同上口径
    # 其余 11 张表逐一复验十六个元字段（键与值都须与利润表完全一致）
    for s in SHEETS[1:]:  # 其余 11 表元字段复验
        for i, key in enumerate(META, 1):  # 键+值双核
            if book.value(s, f'AX{i}') != key or book.value(s, f'AY{i}') != meta[key]:  # 不一致定位到表
                raise ExcelError(f'{s}元字段与利润表不一致')
    # ---- 月度表头三组：费用三表行 3 / 收入两表行 30 / 前三表行 60 ----
    for s, row in [(x, 3) for x in SHEETS[6:9]] + [(x, 30) for x in SHEETS[3:5]] + [(x, 60) for x in SHEETS[:3]]:  # 三组月度表头位
        for month in range(1, 13):  # 12 月逐月核
            ref = f'{col(month + 2)}{row}'  # 表头格位
            header = book.value(s, ref)  # 读表头
            # 月份表头两种合法写法：'N月' 或 'YYYY-MM'（其余一律视为被改）
            if header not in (f'{month}月', f'{year}-{month:02}'):  # 两种合法写法
                raise ExcelError(f'{s}!{ref} 月份表头被修改')  # 其余视为被改
    # 核验账户注册与每一行的七个元字段，禁止缺失、重码或跨版本混用。
    for off in (0,):  # 科目行核验
        for a in ACCOUNTS:  # 逐科目
            s = a['sheet']  # 科目所在表
            r = a['row'] + off  # 科目行号
            # 科目唯一编码钉死在 P 列（EXP/REV/COGS/TAX 注册表）
            if book.value(s, f'P{r}') != a['code']:  # 编码钉死 P 列
                raise ExcelError(f'科目唯一编码不符：{s}!P{r}')  # 编码不符定位
            # 行级四元字段（QRST）：可空，填了就必须与批次元数据一致
            for c, x in zip('QRST', (meta['数据版本号'], meta['口径标记'], meta['生效周期'], closed)):  # 行级四元字段
                value = book.value(s, f'{c}{r}')  # 读行元字段
                if value is not None and value != x:  # 填了就必须一致
                    raise ExcelError(f'行元字段与批次冲突：{s}!{c}{r}')  # 冲突定位到格
            # U/V 两列结构性标签：只收文本（数字/日期都拒）
            for c in 'UV':  # U/V 标签两列
                if book.value(s, f'{c}{r}') is not None and not isinstance(book.value(s, f'{c}{r}'), str):  # 非文本即拒
                    raise ExcelError('结构变更标签和受影响科目须为文本')  # 文案 1.0.5 逐字
            # 金额域逐格：非负且 ≤90 亿元（元口径，与功能区同界）
            for m in range(12):  # 金额域逐格
                x = book.number(s, f'{col(m + 3)}{r}')  # 读月度格
                if x < 0 or x > Decimal('9000000000'):  # 非负且≤90亿
                    raise ExcelError(f'科目金额超出允许范围：{a["code"]}')  # 超界定位到编码
    # 老区 226 项勾稽（先于功能区：老区不过，新区不核）
    checks = reconcile(book)  # 老区 226 勾稽
    # ---- 功能区导入与恒等式（老区 226 计数不动，新区单独计数）----
    zones, zone_checks = qu_daoru(book, qiyue, meta)  # 功能区导入+恒等式
    rows = []  # 八字段行桶
    row_meta = []  # 备注桶
    grain = meta['期间粒度']  # 粒度
    count = 12 if grain == '月度' else 4        # 展开粒度：月度 12 期 / 季度 4 期
    closed_month = int(closed[-2:])             # 已结账月末（实时经营截断用）
    for a in ACCOUNTS:  # 逐科目展开
        for i in range(count):  # 逐期展开
            # 季度模式下每期覆盖 3 个自然月；月度单月
            months = [i] if grain == '月度' else [i * 3, i * 3 + 1, i * 3 + 2]  # 期覆盖月
            # 实时经营：已结账月之后的期间不产生记录（未结账未录入）
            if category == '实时经营' and max(months) + 1 > closed_month:  # 实际：未结账月跳过
                continue  # 不产记录
            period = f'{year}-{i + 1:02}' if grain == '月度' else f'{year}-Q{i + 1}'  # 期间标签
            # 期间金额 = 覆盖月份月度格之和（Decimal 精确加）
            amount = sum((book.number(a['sheet'], f'{col(m + 3)}{a["row"]}') for m in months), Decimal(0))  # 期间金额=Σ月度
            # 备注列：批次元数据 + 行级标签 + 溯源位（源表/源行可回查）
            note = {'主体编码': meta['主体编码'], '情景编码': meta['情景编码'], '科目唯一编码': a['code'],  # 备注：批次+行级+溯源
                    '数据版本号': meta['数据版本号'], '口径标记': meta['口径标记'], '生效周期': meta['生效周期'],
                    '已结账标记': category == '实时经营', '结构性变更标签': book.value(a['sheet'], f'U{a["row"]}') or '无',  # 结构标签缺省无
                    '受影响科目': book.value(a['sheet'], f'V{a["row"]}') or '无', '源工作表': a['sheet'], '源行': a['row'],  # 源表/源行可回查
                    '数据状态': meta['数据状态']}  # 数据状态透传
            # 八字段行：类别/期间/科目/数值(元两位)/单位/来源/更新时间/备注(JSON)
            rows.append([category, period, a['name'], f'{amount:.2f}', '元',  # 八字段行拼装
                         '确定性模拟模板' if meta['数据状态'] == '占位' else '标准Excel模板',  # 来源标注
                         closed + '-01', json.dumps(note, ensure_ascii=False)])  # 更新时间=截至月-01
            row_meta.append(note)  # 备注桶登记
    # 折算 8 列 CSV → 走与键盘录入同一把清洗校验尺（daoru_csv 权威实现）
    stream = io.StringIO()  # 内存 CSV 流
    writer = csv.writer(stream)  # 写出器
    writer.writerow(BIXU_LIE)  # 表头八字段
    writer.writerows(rows)  # 数据行
    records = daoru_csv(stream.getvalue())  # 走权威清洗校验
    if records.jujue:  # 有拒绝项？
        # 标准字段转换有拒绝项 → 整本拒绝（不留半本入库）
        raise ExcelError('标准字段转换未通过校验，整本拒绝')  # 整本拒绝
    benchmark = []  # 对标旁路（12 表无）
    procurement = []  # 采购旁路桶
    # 采购参数旁路：收入两表行 37（占位口径，不得再计入成本合计）
    for s in SHEETS[3:5]:  # 两张收入表
        for m in range(12):  # 逐月
            c = col(m + 3)  # 月度列
            # 预算：全年 12 月都出预算采购；实际：只出已结账月
            procurement.append({'主体编码': meta['主体编码'], '情景编码': meta['情景编码'],  # 采购参数结构
                                '期间': f'{year}-{m + 1:02}',
                                '项目编码': s, '数据状态': meta['数据状态'],
                                '预算采购金额分': cents(book.number(s, f'{c}37')) if category == '预算基础' else None,  # 预算：全年出预算采购
                                '实际采购金额分': cents(book.number(s, f'{c}37')) if category == '实时经营' and m + 1 <= closed_month else None,  # 实际：只出已结账月
                                '预算单价': str(book.number(s, f'{c}34')), '预算数量': str(book.number(s, f'{c}35')),
                                '供应商编码': '占位供应商', '来源': '模板收入明细采购参数；不得再次计入成本合计'})  # 占位口径声明
    # 批次分析范围：截至期即分析末档（季度按已结账整季取整）
    period = closed if grain == '月度' else f'{year}-Q{closed_month // 3}'  # 分析末档
    if category == '实时经营' and grain == '季度' and closed_month < 3:  # 季度完整性门
        # 季度模式至少要有一个完整已结账季度，否则无分析意义
        raise ExcelError('季度模式至少需要一个完整已结账季度')  # 至少一个完整季度
    record_data = dataclasses.asdict(records)  # 入库结果摊平
    record_data['ruku_shu'] = records.ruku_shu  # 入库行数
    return {'records': record_data,  # 返回结构组装
            # 科目清单：模块/方向 + 科目名 + 编码（下游编排层 subjects 直用）
            'subjects': [{k: a[k] for k in ('module', 'direction')} | {'kemu': a['name'], 'accountCode': a['code']} for a in ACCOUNTS],  # subjects 字段
            # 批次元数据/类别/对标/采购旁路与 1.0.5 完全同构（对账零漂移）
            'metadata': meta, 'category': category, 'benchmarks': benchmark, 'procurement': procurement,  # 1.0.5 同构键
            # 老区 226 勾稽计数不变；八字段 CSV 原文随行（供复核）
            'checks': checks, 'text': stream.getvalue(),  # 226 计数 + CSV 原文
            # 分组键 = 主体+情景+年度+粒度（四类合并 combine_imports 的联接键）
            'groupKey': json.dumps([meta['主体编码'], meta['情景编码'], year, grain], ensure_ascii=False),  # 分组键
            'scope': {'cycle': grain, 'period': period}, 'simulation': meta['数据状态'] == '占位',  # 范围/演示标记
            # ---- v1.1 追加：功能区底稿数据与新区恒等式计数（226 不动）----
            'zones': zones, 'zone_checks': zone_checks, 'contract_version': guidao}  # 轨道标识（v1.2/v1.1）


def import_excel_v11(data, name='标准模板.xlsx'):  # 总入口
    """按唯一固定工作表序列分派三套版式、四种数据类别（v1.1 总入口）。"""
    # 文件后缀门：只收 .xlsx（旧 xls/CSV 一律在外层拦截）
    if not isinstance(name, str) or not name.lower().endswith('.xlsx'):  # 文件类型门
        raise ExcelError('只接收固定 Excel 模板（.xlsx）')  # 只收 xlsx
    # 表名序列三分派：12 表 / 行业对标 / 经营变更（其余结构整本退回）
    names = tuple(Book(data).cells)  # 表序列快照
    if names == SHEETS:  # 12 表走 v1.1 主链
        return import_twelve_sheet(data, name)  # 12 表链
    # v2 轨道：九表 + 财会2019-6号三表（纯数值）——表序列不同即分派到这里
    from excel_ingest_v2 import V2_SHEETS, import_v2  # 延迟导入（老轨不依赖新模块）
    if names == V2_SHEETS:  # 九表走 v2 轨道
        return import_v2(data, name)  # v2 链（自带校验，输出结构与 v1 同构）
    # 外部两套版式走本包 v1.2 fork（B1 版本钉双轨：老串照收、中性串放行）
    from external_templates_v12 import industry, changes  # 外部两版式 fork（1.0.5 只读）
    if names == ('批次信息', '基准指标'):  # 行业对标结构
        return industry(data)  # 行业对标链
    if names == ('批次信息', '事件台账', '科目影响'):  # 经营变更结构
        return changes(data)  # 经营变更链
    raise ExcelError('工作表结构不符合预算/实际、行业对标或经营变更任一固定模板')  # 其余结构整本退回
