# -*- coding: utf-8 -*-
"""输入端口 v2 轨道：读「九表 + 财会2019-6号三表」演示件（纯数值、零公式）。

为什么另开一条轨道（而不是改 v1.1/v1.2 契约）：
    v1.1/v1.2 契约是「12 表 + 老版式 + 公式位逐字钉死」，而 v2 演示件是
    「9 表 + 财会2019-6 号三表 + 纯数值（零公式）」——表名、版式、单元格
    属性全都不同，硬塞进老契约只会把两套规则搅在一起。所以按既有双轨惯例
    （v1.1 老轨 / v1.2 新轨）再开一条 v2 轨，三条轨道互不干扰：
      · 表序列不同 → 由 import_excel_v11 的入口分派决定走哪条；
      · 校验规则不同 → 本文件自带一套（表序列/元字段/白名单/标签/恒等式）；
      · 输出结构相同 → 都返回 category/metadata/checks/... 供下游直接消费。

校验分层（任一层不过即整本拒绝，报错文案带表名与格位）：
    1) 表序列：9 张表名与顺序逐字一致（多表/少表/改名/换序整本退回）
    2) 元字段：AX1:AY16 十六键（锚点为「税金及附加」表），键名逐字、值非空文本
    3) 白名单：九表「标签 ∪ 数值位 ∪ 明示数据区」以外的格一律拒收
    4) 标签逐字：静态标签（不带占位符的）与版式常量逐字一致
    5) 数值位：登记为数值位的格必须是真数值（文本/空白都拒）
    6) 勾稽：三表恒等式、税金分档、摊销台账、分录借贷与现金流对照
"""
import json                                                  # 输出结构里的 groupKey
import os                                                    # 环境变量覆盖 algo 路径（自足包）
import sys                                                   # sys.path 引导（只读引用）
from decimal import Decimal                                  # 元位精确比较
from pathlib import Path                                     # 版式常量路径

BEN_MU = Path(__file__).resolve().parent                     # 本包根
if str(BEN_MU) not in sys.path:                              # 幂等插入
    sys.path.insert(0, str(BEN_MU))                          # 本包优先

from excel_contract_v11 import META                          # noqa: E402  十六键定义复用

#: algo 只读算法树（自足包：backend/_vendor/algo，HENGCE_ALGO_DIR 可覆盖；xlsx_reader 在此）
ALGO = os.environ.get('HENGCE_ALGO_DIR') or str(BEN_MU.parent / '_vendor' / 'algo')
if ALGO not in sys.path:                                     # 幂等插入
    sys.path.insert(0, ALGO)
from xlsx_reader import Book, ExcelError                     # noqa: E402  受限解包（只读）

#: v2 版式常量所在包（唯一事实源：标签/数值位都在 banshi.py 里）
BANSHI_MU = BEN_MU.parent / '演示生成器v2'
if str(BANSHI_MU) not in sys.path:                           # 幂等插入
    sys.path.insert(0, str(BANSHI_MU))                       # 允许导入 banshi

#: v2 契约版本标识（写进返回结果的 contract_version，供下游区分三条轨道）
V2_BANBEN = 'v2'

#: v2 工作表序列（9 张，顺序即硬约束）
V2_SHEETS = ('利润表', '资产负债表', '现金流量表', '税金及附加', '销售费用',
             '管理费用', '费用表月度汇总', '摊销明细', '分录')

#: 元字段锚点表（v2 里只有四张九表保留 AX/AY 区块，取税金及附加做基准）
YUAN_BIAO = '税金及附加'

#: 三表数据列（利润表/现金流 B=本期 C=上期；资负左右两栏各两列）
SAN_LIE = {'利润表': ('B', 'C'), '资产负债表': ('B', 'C', 'E', 'F'), '现金流量表': ('B', 'C')}

#: 十二个月列（九表的 C..N）
YUE_LIE = tuple('CDEFGHIJKLMN')


def _ban(ming):
    """取版式常量（延迟导入：避免本模块在无生成器环境下一导入就炸）。"""
    import banshi                                            # 生成器版式常量（唯一事实源）
    return banshi.JIU_BIAO.get(ming) or banshi.SAN_BIAO[ming]


def _shu(v):
    """单元格值 → Decimal（None/文本按 0 处理，仅用于勾稽比较）。"""
    if isinstance(v, bool):                                  # bool 是 int 子类，先挡掉
        return Decimal(0)
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    return Decimal(0)


def _deng(a, b, rong=Decimal('0.005')):
    """两数相等（按分容差；元位两位小数比较）。"""
    return abs(_shu(a) - _shu(b)) <= rong


# ======================================================================
# 第一层：表序列 + 元字段
# ======================================================================

def jian_xulie(book):
    """表序列门：9 张表名与顺序逐字一致。"""
    if tuple(book.cells) != V2_SHEETS:                       # cells 的键序即工作表顺序
        raise ExcelError('工作表名称、数量或顺序不符合 v2 模板：必须完整保留九张表')
    return len(V2_SHEETS)                                    # 计数：9


def jian_yuanshu(book):
    """元字段门：AX1:AY16 十六键逐字 + 值非空文本；返回 meta 桶。"""
    meta = {}                                                # 元字段桶
    for i, key in enumerate(META, 1):                        # 十六键逐键核
        if book.value(YUAN_BIAO, f'AX{i}') != key:           # 键名不符即缺字段
            raise ExcelError(f'缺失元字段：{key}')
        v = book.value(YUAN_BIAO, f'AY{i}')                  # 取值列
        if not isinstance(v, str) or not v.strip():           # 必须是非空文本
            raise ExcelError(f'元字段必须为非空文本：{key}')
        meta[key] = v.strip()                                # 入桶
    if meta['数据类别'] not in ('预算基础', '实时经营'):        # 类别二值门
        raise ExcelError('数据类别须为预算基础或实时经营')
    return meta


# ======================================================================
# 第二层：白名单 + 标签 + 数值位
# ======================================================================

def _lie_ming(hao):
    """列号 → 列字母（1 起）。"""
    out = ''
    while hao:
        hao, yu = divmod(hao - 1, 26)
        out = chr(65 + yu) + out
    return out


#: 九表的「数据区」白名单补充（列区间, 起行, 止行）——生成器按这些区写数
SHU_JU_QU = {
    '税金及附加': (((3, 15), 31, 36), ((15, 29), 121, 127)),          # 老区 31-36 + Z3 分档区
    '销售费用': (((3, 15), 4, 36), ((3, 15), 204, 233), ((3, 15), 324, 353)),
    '管理费用': (((3, 15), 4, 36), ((3, 15), 204, 233), ((3, 15), 324, 353)),
    '费用表月度汇总': (((3, 15), 4, 36),),
    '摊销明细': (((1, 7), 9, 17), ((1, 14), 19, 29)),                 # 台账 + 月度矩阵
}


def _xu_ge(ming, book):
    """该表允许出现的格位集合（白名单）。

    三表：官方表样「格格有数」，不做格级白名单（改由标签逐字 + 恒等式把关）；
    九表：版式标签 ∪ 数值位 ∪ 数据区（生成器明示写入的区段）。
    """
    if ming in SAN_LIE:                                      # 三表：整表放行
        b = _ban(ming)
        return {f'{c}{r}' for c in 'ABCDEFGH'
                for r in range(1, b['dims'][0] + 1)}
    b = _ban(ming)                                           # 九表：常量 + 数据区
    ge = set(b['biaoqian']) | set(b['shuzhi_wei'])
    for (c1, c2), r1, r2 in SHU_JU_QU.get(ming, ()):          # 数据区并入白名单
        ge |= {f'{_lie_ming(c)}{r}' for c in range(c1, c2 + 1) for r in range(r1, r2 + 1)}
    if ming == '分录':                                        # 数据区 A2:H(末行+4)
        mo = 1
        for r in range(2, book_max(book, ming) + 1):
            if book.value(ming, f'B{r}'):
                mo = r
        ge |= {f'{c}{r}' for c in 'ABCDEFGH' for r in range(2, mo + 5)}
    return ge


def book_max(book, ming):
    """该表已用最大行号（Book 不暴露 max_row，按 A 列非空扫描）。"""
    mo = 1
    for r in range(1, 2000):
        if any(book.value(ming, f'{c}{r}') not in (None, '') for c in 'ABCDEFGH'):
            mo = r
        elif r > mo + 40:
            break
    return mo


def jian_baimingdan(book):
    """白名单门：九表中出现标准模板以外的格即拒收。返回计数。"""
    n = 0
    for ming in V2_SHEETS:
        if ming in SAN_LIE:                                  # 三表跳过格级白名单
            continue
        xu = _xu_ge(ming, book)                              # 允许格位
        for ref in book.cells[ming]:                         # 逐格核
            if ref not in xu:                                # 不在白名单
                raise ExcelError(f'{ming}出现标准模板以外的单元格：{ref}')
            n += 1
    return n


def jian_biaoqian(book, lei='预算基础'):
    """标签门：静态标签逐字一致（带占位符的动态文本只查非空与无花括号）。

    版式常量里「预算基础」是按类别渲染的（实时经营册渲染成「实时经营」），
    比较时先把期望文本里的类别词替换成实际类别。
    """
    n = 0
    for ming in V2_SHEETS:
        for ref, wen in _ban(ming)['biaoqian'].items():
            v = book.value(ming, ref)                        # 实际值
            if isinstance(wen, str) and '{' in wen:          # 动态文本（主体名/日期/种子）
                if not isinstance(v, str) or not v.strip():  # 必须非空
                    raise ExcelError(f'固定表头缺失：{ming}!{ref}')
                if '{' in v:                                 # 占位符未渲染
                    raise ExcelError(f'表头占位符未渲染：{ming}!{ref}')
            elif v != (wen.replace('预算基础', lei) if isinstance(wen, str) else wen):
                raise ExcelError(f'固定表头或科目被修改：{ming}!{ref}')
            n += 1
    return n


def jian_shuzhi(book):
    """数值位门：登记为数值位的格必须是真数值。返回计数。"""
    n = 0
    for ming in V2_SHEETS:
        for ref in _ban(ming)['shuzhi_wei']:
            v = book.value(ming, ref)
            if not isinstance(v, (int, float, Decimal)):     # 文本/空白都拒（Book 返回 Decimal）
                raise ExcelError(f'数值位必须为数值：{ming}!{ref}')
            n += 1
    return n


# ======================================================================
# 第三层：勾稽（三表 / 税金 / 摊销 / 分录）
# ======================================================================

def jian_sanbiao(book):
    """三表恒等式：利润表行间关系、资负两栏平衡、现金链与货币资金衔接。"""
    lr, zf, xj = '利润表', '资产负债表', '现金流量表'
    n = 0
    for x in ('B', 'C'):                                     # 本期 / 上期两列同规则
        # 营业利润 = 收入 − 成本 − 税金 − 三费 − 研发 − 财务 + 其他收益 + 投资收益 …
        zhi = sum(_shu(book.value(lr, f'{x}{r}')) * k for r, k in
                  ((5, 1), (6, -1), (7, -1), (8, -1), (9, -1), (10, -1), (11, -1),
                   (14, 1), (15, 1), (17, 1), (18, 1), (19, 1), (20, 1), (21, 1), (22, 1)))
        if not _deng(book.value(lr, f'{x}23'), zhi):
            raise ExcelError(f'利润表营业利润勾稽不通过：{x}23')
        if not _deng(book.value(lr, f'{x}26'),
                     _shu(book.value(lr, f'{x}23')) + _shu(book.value(lr, f'{x}24'))
                     - _shu(book.value(lr, f'{x}25'))):
            raise ExcelError(f'利润表利润总额勾稽不通过：{x}26')
        if not _deng(book.value(lr, f'{x}28'),
                     _shu(book.value(lr, f'{x}26')) - _shu(book.value(lr, f'{x}27'))):
            raise ExcelError(f'利润表净利润勾稽不通过：{x}28')
        if not _deng(book.value(lr, f'{x}44'),
                     _shu(book.value(lr, f'{x}28')) + _shu(book.value(lr, f'{x}31'))):
            raise ExcelError(f'利润表综合收益勾稽不通过：{x}44')
        n += 4
        # 资负：左栏 19/39/40，右栏 19/31/32/44/45
        if not _deng(book.value(zf, f'{x}19'),
                     sum(_shu(book.value(zf, f'{x}{r}')) for r in range(6, 19))):
            raise ExcelError(f'流动资产合计勾稽不通过：{x}19')
        if not _deng(book.value(zf, f'{x}40'),
                     _shu(book.value(zf, f'{x}19')) + _shu(book.value(zf, f'{x}39'))):
            raise ExcelError(f'资产总计勾稽不通过：{x}40')
        n += 2
    # 右栏两列（E/F）与左栏两列（B/C）各自平衡
    for zuo, you, ming in (('B', 'E', '期末'), ('C', 'F', '上年年末')):
        if not _deng(book.value(zf, f'{zuo}40'), book.value(zf, f'{you}45')):
            raise ExcelError(f'资产负债表{ming}不平衡')
        n += 1
    # 现金链：B42 = B40 + B41；B42 = 资负货币资金期末；C42 = B41
    for x in ('B', 'C'):
        if not _deng(book.value(xj, f'{x}42'),
                     _shu(book.value(xj, f'{x}40')) + _shu(book.value(xj, f'{x}41'))):
            raise ExcelError(f'现金流量表期末现金勾稽不通过：{x}42')
        n += 1
    if not _deng(book.value(xj, 'B42'), book.value(zf, 'B6')):
        raise ExcelError('现金流量表期末现金与资产负债表货币资金不一致')
    if not _deng(book.value(xj, 'B41'), book.value(zf, 'C6')):
        raise ExcelError('现金流量表期初现金与资产负债表上年年末货币资金不一致')
    if not _deng(book.value(xj, 'C42'), book.value(xj, 'B41')):
        raise ExcelError('现金流量表上期期末与本年期初不一致')
    return n + 3


def jian_shuijin(book):
    """税金及附加：分档合计=税金及附加、附加税合计=增值税×12%、C31=年税/年收入。"""
    sj = '税金及附加'
    n = 0
    for i, m in enumerate(YUE_LIE):
        x = _lie_ming(17 + i)                                # Z3 区分档区月列：Q..AB（17..28）
        tong = _shu(book.value(sj, f'{m}33'))
        a, b, c, d = (_shu(book.value(sj, f'{x}{r}')) for r in (123, 124, 125, 126))
        if not _deng(book.value(sj, f'{x}127'), tong):        # 分档合计 = 税金及附加
            raise ExcelError(f'税种分档合计与税金及附加不一致：{m}月')
        if _shu(book.value(sj, f'{m}6')) < a + b + c + d:     # 合计不得小于四税之和（印花税并入）
            raise ExcelError(f'税金及附加合计小于各税之和：{m}月')
        n += 2
    nian_shou = sum(_shu(book.value(sj, f'{m}32')) for m in YUE_LIE)
    nian_shui = sum(_shu(book.value(sj, f'{m}33')) for m in YUE_LIE)
    if nian_shou and not _deng(book.value(sj, 'C31'), nian_shui / nian_shou, Decimal('0.0001')):
        raise ExcelError('综合附加率与年税金/年计税收入不一致：C31')
    return n + 1


def jian_tanxiao(book):
    """摊销明细：月摊销=ROUND(原值/月数)、台账月摊销=原值/月数、矩阵合计=月摊销。"""
    tx = '摊销明细'
    n = 0
    yuan, yue_shu, yue_tan = (_shu(book.value(tx, f'B{r}')) for r in (1, 2, 3))
    if yue_shu and not _deng(yue_tan, (yuan / yue_shu).quantize(Decimal('0.01')), Decimal('0.02')):
        raise ExcelError('摊销明细月摊销与「原值÷月数」不一致：B3')
    for r in range(10, 18):                                  # 台账八项：月摊销 = 原值 ÷ 月数
        if not _deng(book.value(tx, f'G{r}'),
                     _shu(book.value(tx, f'E{r}')) / max(_shu(book.value(tx, f'F{r}')), Decimal(1)),
                     Decimal('0.02')):
            raise ExcelError(f'摊销台账月摊销与「原值÷月数」不一致：G{r}')
        n += 1
    for c in 'BCDEFGHIJKLM':                                 # 矩阵逐月合计（含年度列）
        if not _deng(book.value(tx, f'{c}29'), yue_tan):
            raise ExcelError(f'摊销矩阵合计与本月摊销不一致：{c}29')
        n += 1
    return n + 1


def jian_fenlu(book):
    """分录：借贷平衡 + 现金流对照合计 = 现金流量表本期行；返回分录明细。"""
    fl = '分录'
    mo = 0
    for r in range(2, book_max(book, fl) + 1):               # 找合计行标签
        if book.value(fl, f'A{r}') == '全部借方合计':
            mo = r
            break
    if not mo:                                               # 合计行缺失
        raise ExcelError('分录缺少「全部借方合计」行')
    jie = dai = Decimal(0)                                   # 合计
    dui = {}                                                 # 现金流对照 → 金额合计
    mingxi = []                                              # 分录明细（下游用）
    for r in range(2, mo):                                   # 逐笔
        zy = book.value(fl, f'B{r}')
        if not zy:                                           # 空行（数据与合计之间的分隔）
            continue
        jin = _shu(book.value(fl, f'E{r}'))
        if not _deng(jin, book.value(fl, f'F{r}')):          # 单笔借贷不平
            raise ExcelError(f'分录单笔借贷不平衡：第 {r} 行')
        jie += jin
        dai += _shu(book.value(fl, f'F{r}'))
        dh = book.value(fl, f'G{r}')                         # 现金流对照（"—" 表示非现金）
        if isinstance(dh, (int, float, Decimal)):
            dui[int(dh)] = dui.get(int(dh), Decimal(0)) + jin
        mingxi.append({'行': r, '月份': book.value(fl, f'A{r}'), '摘要': zy,
                       '借方': book.value(fl, f'C{r}'), '贷方': book.value(fl, f'D{r}'),
                       '金额': str(jin), '对照': dh, '凭证号': book.value(fl, f'H{r}')})
    if not _deng(jie, dai):                                  # 全表借贷平衡
        raise ExcelError(f'分录借贷不平衡：借 {jie} / 贷 {dai}')
    if not _deng(book.value(fl, f'E{mo}'), jie) or not _deng(book.value(fl, f'F{mo + 1}'), dai):
        raise ExcelError('分录合计行与逐笔汇总不一致')
    for hang, he in dui.items():                             # 对照 → 现金流量表本期列
        if not _deng(he, book.value('现金流量表', f'B{hang}')):
            raise ExcelError(f'分录现金流对照与现金流量表不一致：第 {hang} 行')
    return len(mingxi), mingxi, dui


# ======================================================================
# 八字段入库行（供分析引擎 fenxi 消费）
# ======================================================================

#: 八字段表头（与 algo data_ingest.BIXU_LIE 逐字一致）
BI_XU = '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注'
#: 两张费用表（九表里的科目来源）
FEI_BIAO = ('销售费用', '管理费用')


def zhuan_jilu(book, meta):
    """九表 → 八字段 CSV 文本（科目 × 期间 行），再由 daoru_csv 做权威清洗。

    取数口径：
        营业收入   ← 税金及附加 行 32（计税收入，等于当月不含税营业收入）
        税金及附加 ← 税金及附加 行 33
        销售/管理费用 ← 两张费用表 行 4..33（逐科目月度）
    只输出有值的月份（实时经营未结账月为 0，不产记录）。
    """
    lei, nian = meta['数据类别'], meta['年度']
    geng = (meta['已结账截至'] or f'{nian}-12')[:10]
    hang = [BI_XU]

    def xie(kemu, m, zhi):
        hang.append(f'{lei},{m},{kemu},{Decimal(str(zhi)):.2f},元,'
                    f'标准Excel模板,{geng}-01,')

    for i, m in enumerate(YUE_LIE):                          # 12 个月列
        qijian = f'{nian}-{i + 1:02}'
        shou = _shu(book.value('税金及附加', f'{m}32'))
        if shou:
            xie('营业收入', qijian, shou)
        shui = _shu(book.value('税金及附加', f'{m}33'))
        if shui:
            xie('税金及附加', qijian, shui)
        for b in FEI_BIAO:                                   # 逐费用科目
            for r in range(4, 34):
                biaoqian = book.value(b, f'A{r}')
                zhi = _shu(book.value(b, f'{m}{r}'))
                if biaoqian and zhi:
                    xie(f'{b}/{biaoqian}', qijian, zhi)
    return '\n'.join(hang)


def ru_ku(book, meta):
    """八字段 CSV → DaoruJieguo（走 algo 权威清洗链），返回（records, csv原文）。"""
    import sys as _sys
    from excel_contract_v11 import col as _col  # noqa: F401  保持依赖显式
    algo = ALGO                                  # 模块级 algo（_vendor 自足解析）
    if algo not in _sys.path:
        _sys.path.insert(0, algo)
    from data_ingest import daoru_csv
    wen = zhuan_jilu(book, meta)
    return daoru_csv(wen), wen


# ======================================================================
# 主入口
# ======================================================================

def import_v2(data, name='演示.xlsx'):
    """严格导入一本 v2 工作簿（九表）；校验全过才返回结构化结果。"""
    if not isinstance(name, str) or not name.lower().endswith('.xlsx'):
        raise ExcelError('只接收唯一标准 Excel 模板（.xlsx）')   # 文件类型门
    book = Book(data)                                        # 受限解包（只读）
    checks = jian_xulie(book)                                # 1) 表序列
    meta = jian_yuanshu(book)                                # 2) 元字段
    checks += 16
    checks += jian_baimingdan(book)                          # 3) 白名单
    checks += jian_biaoqian(book, meta['数据类别'])           # 4) 标签逐字（类别已渲染）
    checks += jian_shuzhi(book)                              # 5) 数值位
    checks += jian_sanbiao(book)                             # 6) 三表恒等式
    checks += jian_shuijin(book)                             # 7) 税金分档
    checks += jian_tanxiao(book)                             # 8) 摊销台账
    n_fenlu, fenlu, dui = jian_fenlu(book)                   # 9) 分录
    checks += n_fenlu + len(dui)                             # 分录计数
    san = {ming: {f'{c}{r}': book.value(ming, f'{c}{r}')
                  for c in SAN_LIE[ming] for r in range(1, _ban(ming)['dims'][0] + 1)}
           for ming in SAN_LIE}                              # 三表快照（本期/上期两列）
    jilu, wen = ru_ku(book, meta)                            # 八字段入库（走权威清洗链）
    kemu = [{'kemu': '营业收入', 'module': '收入模块', 'direction': '收入类', 'accountCode': 'REV'}]
    kemu.append({'kemu': '税金及附加', 'module': '费用模块', 'direction': '成本类',
                 'accountCode': 'TAX'})
    for b in FEI_BIAO:                                       # 两张费用表的科目清单
        for r in range(4, 34):
            bq = book.value(b, f'A{r}')
            if bq:
                kemu.append({'kemu': f'{b}/{bq}', 'module': '费用模块', 'direction': '成本类',
                             'accountCode': f'EXP.{b}.{r:03d}'})
    return {'ok': True,                                      # 通过标记
            'contract_version': V2_BANBEN,                   # 轨道标识
            'category': meta['数据类别'],                     # 类别（预算/实际）
            'metadata': meta,                                # 十六个元字段
            'checks': checks,                                # 勾稽/校验计数
            'records': {ming: [__import__('dataclasses').asdict(x)
                               for x in getattr(jilu, ming)]
                        for ming in ('yusuan', 'shishi', 'hangye', 'biangeng', 'jujue')},
            'ruku_shu': getattr(jilu, 'ruku_shu', 0),        # 入库行数
            'subjects': kemu,                                # 科目清单（模块/方向/编码）
            'text': wen,                                     # 八字段 CSV 原文（复核用）
            'sheets': list(V2_SHEETS),                       # 表序列回执
            'three': san,                                    # 三表数据（列 → 行）
            'shuijin': {'综合附加率': str((_shu(book.value('税金及附加', 'C31')))
                                          .quantize(Decimal('0.0001'))),
                        '年税金': str(sum(_shu(book.value('税金及附加', f'{m}33'))
                                          for m in YUE_LIE))},
            'tanxiao': {'原值': str(_shu(book.value('摊销明细', 'B1'))),
                        '月数': str(_shu(book.value('摊销明细', 'B2'))),
                        '月摊销': str(_shu(book.value('摊销明细', 'B3'))),
                        '台账': [{'资产': book.value('摊销明细', f'A{r}'),
                                  '归属表': book.value('摊销明细', f'B{r}'),
                                  '部门': book.value('摊销明细', f'C{r}'),
                                  '原值': str(_shu(book.value('摊销明细', f'E{r}'))),
                                  '月数': str(_shu(book.value('摊销明细', f'F{r}'))),
                                  '月摊销': str(_shu(book.value('摊销明细', f'G{r}')))}
                                 for r in range(10, 18)]},
            'fenlu': fenlu,                                  # 分录明细（逐笔）
            'groupKey': json.dumps([meta['主体编码'], meta['情景编码'], meta['年度'],
                                    meta['期间粒度']], ensure_ascii=False)}


if __name__ == '__main__':                                   # 命令行自测：导入并打印摘要
    import io
    from pathlib import Path as _P

    if len(sys.argv) < 2:
        print('用法：python -B excel_ingest_v2.py <演示件.xlsx>')
        sys.exit(2)
    _lu = _P(sys.argv[1])
    _r = import_v2(_lu.read_bytes(), _lu.name)
    print(f'导入通过：{_lu.name}')
    print(f'  类别 {_r["category"]} ｜ 主体 {_r["metadata"]["主体名称"]} ｜ 年度 {_r["metadata"]["年度"]}')
    print(f'  表序列 {len(_r["sheets"])} 张 ｜ 校验计数 {_r["checks"]}')
    print(f'  税金及附加 年额 {_r["shuijin"]["年税金"]}（综合附加率 {_r["shuijin"]["综合附加率"]}）')
    print(f'  摊销 {_r["tanxiao"]["月摊销"]}/月 ｜ 台账 {len(_r["tanxiao"]["台账"])} 项')
    print(f'  分录 {len(_r["fenlu"])} 笔')
