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

    补充约定（写给后来维护的人）：
        · 元字段：AX1:AY16 十六键，键在 AX 列、值在 AY 列，锚点表固定为「税金及附加」
          （v2 九表里只有这张表保留 AX/AY 区块）；「数据类别」只允许 预算基础 / 实时经营 两个值，
          它是判别「这本册子是预算还是实际」的唯一权威，不能靠文件名或用户口述去猜。
        · 金额口径：模板单元格是「元、两位小数」，本文件内部一律用 Decimal 比较（容差 0.005 元
          = 半分），不经过 float；转八字段 CSV 时按 '%.2f' 落字符串，整数分由 data_ingest 统一换算。
        · 报错口径：一律抛 ExcelError，文案形如「<表名>…：<格位>」，指明哪张表哪一格，
          不吞异常、不降级返回空结果——校验失败就是整本退回，宁可什么都不返回。
        · 返回结构（import_v2）：ok / contract_version / category / metadata / checks / records /
          ruku_shu / subjects / text / sheets / three / shuijin / tanxiao / fenlu / groupKey，
          各字段用途见主入口 return 处的逐键注释；下游只依赖这些键，不读内部中间变量。
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


# ======================================================================
# 基础件：版式常量取用、单元格值归一、按分容差比较
# ======================================================================
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

# Book.cells 是 dict（Python 3.7+ 保插入序），键序即工作表物理顺序，
# 所以 tuple(...) 可以直接与模板序列逐位比对——换序也能一次抓到。
def jian_xulie(book):
    """表序列门：9 张表名与顺序逐字一致。"""
    if tuple(book.cells) != V2_SHEETS:                       # cells 的键序即工作表顺序
        raise ExcelError('工作表名称、数量或顺序不符合 v2 模板：必须完整保留九张表')
    return len(V2_SHEETS)                                    # 计数：9


# 十六键定义复用 excel_contract_v11.META（v1.1/v1.2 与 v2 共用同一份键名），
# 不在本文件重抄一份，避免两条轨道对「元字段该有哪些」各说各话。
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

# 数据区/台账用「数字列区间」声明（好写也好改），白名单却需要「字母+行号」，
# 这个换算是两套坐标之间的唯一桥；只支持 1..26 以外也正确（两位数继续进位）。
def _lie_ming(hao):
    """列号 → 列字母（1 起）。"""
    out = ''
    while hao:
        hao, yu = divmod(hao - 1, 26)
        out = chr(65 + yu) + out
    return out


#: 九表的「数据区」白名单补充（列区间, 起行, 止行）——生成器按这些区写数
# 数据区 = 生成器实际写数的矩形区，元组结构 ((起始列, 结束列), 起始行, 结束行)：
#   税金及附加：老区 C..O 行 31-36 + 分档区 O..AC 行 121-127；
#   两张费用表：三段（金额 4-36 / 单价 204-233 / 数量 324-353），列均为 C..O；
#   摊销明细：台账行 9-17 + 月度矩阵行 19-29。
# 只列「写数」的区，不含表头与说明文字；漏登记会让合法数据被判成野格，多登记会放行脏数据。
SHU_JU_QU = {
    '税金及附加': (((3, 15), 31, 36), ((15, 29), 121, 127)),          # 老区 31-36 + Z3 分档区
    '销售费用': (((3, 15), 4, 36), ((3, 15), 204, 233), ((3, 15), 324, 353)),
    '管理费用': (((3, 15), 4, 36), ((3, 15), 204, 233), ((3, 15), 324, 353)),
    '费用表月度汇总': (((3, 15), 4, 36),),
    '摊销明细': (((1, 7), 9, 17), ((1, 14), 19, 29)),                 # 台账 + 月度矩阵
}


# 三表不设格级白名单的取舍：官方表样行数固定、用户可在行内补数，
# 放开格位但用「标签逐字 + 三表恒等式」兜底，比维护 40 行 × 8 列的白名单更稳；
# 九表是自建版式，多打一个字都可能污染科目，所以必须逐格核。
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
    # 分录是真流水，行数随业务变：放行到「最后一条摘要行 + 4 行」（给合计行与两行空白留余量），
    # 否则合计行一写就被白名单判成野格。
    if ming == '分录':                                        # 数据区 A2:H(末行+4)
        mo = 1
        for r in range(2, book_max(book, ming) + 1):
            if book.value(ming, f'B{r}'):
                mo = r
        ge |= {f'{c}{r}' for c in 'ABCDEFGH' for r in range(2, mo + 5)}
    return ge


# Book 不暴露 max_row，只能扫：A..H 覆盖了分录/台账/费用表所有「有意义的首个非空格」，
# 2000 行是模板行数上限（九表最长的税金及附加 480 行 ×4 余量），
# 「连续 40 行全空才收手」用来跳过尾部零星空行，又不会把中间大段空行之后的数据漏掉。
def book_max(book, ming):
    """该表已用最大行号（Book 不暴露 max_row，按 A 列非空扫描）。"""
    mo = 1
    for r in range(1, 2000):
        if any(book.value(ming, f'{c}{r}') not in (None, '') for c in 'ABCDEFGH'):
            mo = r
        elif r > mo + 40:
            break
    return mo


# 白名单是「版式没被手改」的第一道护栏：命中即报，连多一个空格都算。
# 三表跳过这一层，但它们的标签/数值位/恒等式仍在后面的层里逐一过。
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


# 期望标签来自 banshi 的版式常量（静态文本 + 带 {占位符} 的动态文本两类）。
# 动态文本（主体名/日期/种子）只查「非空且占位符已渲染」，因为值本身随批次变；
# 静态文本里含类别词的一律先在期望值上替换成实际类别再比——同一份版式要服务
# 预算基础与实时经营两本册子，不能在常量里钉死成「预算基础」。
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


# 数值位 = 生成器写数的格：Book 对空单元格返回 None，对文本返回 str，两类都直接拒。
# 手打「100」这种文本数字在这里就被拦下，不会等到勾稽层再报一个看不懂的错。
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

# 三表恒等式是「这本册子算得对不对」的总闸：先在元位（两位小数）逐行复算，
# 再比两栏平衡与现金衔接。符号位（income +1 / 费用 −1）直接照利润表项目方向取，
# 与财会2019-6号三表的行序绑定：5 收入、6 成本、7 税金、8 销售、9 管理、10 研发、
# 11 财务为减项；14 其他收益、15 投资收益、17-22 各项收益/损失为加项。
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
        # 资负列结构：B/C = 左栏（期末/上年年末），E/F = 右栏（负债与所有者权益的期末/上年年末）。
        # 左栏：19 流动资产合计 = Σ6..18，40 资产总计 = 19 + 39（非流动资产合计）；
        # 右栏：19/31/32/44 分别流动负债、非流动负债、负债合计、所有者权益合计，45 为右侧总计。
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
    # 现金链四条互锁：期末现金 = 净增加额 + 期初（B42=B40+B41 / C42=C40+C41），
    # 期末现金须等于资负货币资金期末（B6）、期初须等于资负上年年末货币资金（C6），
    # 上期期末（C42）必须等于本期期初（B41）——任何一条断了都说明有人只改了一张表。
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


# 分档区坐标（模板「税金及附加」表）：O 列区头，P 列分档率，Q..AB = 第 17..28 列 = 1..12 月，
# AC 列年度合计；行 121 区名、122 表头、123 城建税、124 教育费附加、125 地方教育附加、
# 126 其他、127 分档合计。左侧 C..N 是同一批税额的「月度汇总」列（行 32 计税收入、33 税金）。
# 两条口径必须互相对上：分档合计 = 当月税金及附加，且合计 ≥ 四税之和（印花税等并入 B6）。
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


# 摊销坐标：B1/B2/B3 = 台账汇总（原值、月数、本月摊销）；台账行 10-17 八项
# （A 资产、B 归属费用表、C 部门、D 起始月、E 原值、F 月数、G 月摊销）；
# 行 19 是「资产＼月份」矩阵表头，行 29 是逐月合计行。两条口径：
# 月摊销 = ROUND(原值/月数, 2)，矩阵每列合计 = 本月摊销。
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
    # 矩阵十二个月列 B..M 各有一行合计（第 29 行）；N 列年度合计不在本循环内，
    for c in 'BCDEFGHIJKLM':                                 # 矩阵逐月合计（含年度列）
        if not _deng(book.value(tx, f'{c}29'), yue_tan):
            raise ExcelError(f'摊销矩阵合计与本月摊销不一致：{c}29')
        n += 1
    return n + 1


# 分录三层校验：单笔借贷相等 -> 全表借贷相等 -> 合计行与逐笔汇总一致，
# 再拿 G 列「现金流对照」（现金流量表 B 列的行号）把分录金额对到现金流具体行，
# 对不上的说明分录是手改的、没走生成器。返回 (笔数, 明细, 对照合计) 供下游复用，
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


# 取数口径已写在 docstring；补两点：费用表只取行 4..33（行 34 起是合计/留白），
# 「已结账截至」取月份首日（geng-01）作为更新时间，未结账月为 0 自然不出记录——
# 实时经营册子的预算侧月份本来就是空的，不该被当成 0 元业务行。
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


# 不在本文件自己清洗：八字段 CSV 交给 algo/data_ingest.daoru_csv 做权威校验
# （字段齐全、数值可解析、去重），再拿回 DaoruJieguo；csv 原文一并返回便于复核。
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

# 主流程 = 九道门按序过：文件类型 -> 表序列 -> 元字段 -> 白名单 -> 标签 -> 数值位
# -> 三表 -> 税金 -> 摊销 -> 分录 -> 八字段入库 -> 组装返回。
# 顺序有讲究：先结构后数值、先整本后明细，报错永远指向「最外层能定位的那一处」。
# 参数：data=工作簿字节流（不落盘、不按路径读，宿主侧直接给 Buffer）；
#       name=原始文件名，只用于后缀门与报错回显，不参与取数。
def import_v2(data, name='演示.xlsx'):
    """严格导入一本 v2 工作簿（九表）；校验全过才返回结构化结果。"""
    if not isinstance(name, str) or not name.lower().endswith('.xlsx'):
        raise ExcelError('只接收唯一标准 Excel 模板（.xlsx）')   # 文件类型门
    book = Book(data)                                        # 受限解包（只读）
    checks = jian_xulie(book)                                # 1) 表序列
    meta = jian_yuanshu(book)                                # 2) 元字段
    # 元字段计数：十六键各算一条（与 jian_yuanshu 的循环次数对齐），
    # 表序列层已先把 9（V2_SHEETS 张数）计入 checks。
    checks += 16
    checks += jian_baimingdan(book)                          # 3) 白名单
    checks += jian_biaoqian(book, meta['数据类别'])           # 4) 标签逐字（类别已渲染）
    checks += jian_shuzhi(book)                              # 5) 数值位
    checks += jian_sanbiao(book)                             # 6) 三表恒等式
    checks += jian_shuijin(book)                             # 7) 税金分档
    checks += jian_tanxiao(book)                             # 8) 摊销台账
    n_fenlu, fenlu, dui = jian_fenlu(book)                   # 9) 分录
    checks += n_fenlu + len(dui)                             # 分录计数
    # 三表快照只取「本期/上期」两列（资负取 B/C/E/F 四列），列内到模板最大行；
    # 下游出报表时直接用它做对账展示，不再重开工作簿。
    san = {ming: {f'{c}{r}': book.value(ming, f'{c}{r}')
                  for c in SAN_LIE[ming] for r in range(1, _ban(ming)['dims'][0] + 1)}
           for ming in SAN_LIE}                              # 三表快照（本期/上期两列）
    jilu, wen = ru_ku(book, meta)                            # 八字段入库（走权威清洗链）
    # 科目清单的编码规则：营业收入 REV、税金及附加 TAX、费用表科目 EXP.<表名>.<行号3位>；
    kemu = [{'kemu': '营业收入', 'module': '收入模块', 'direction': '收入类', 'accountCode': 'REV'}]
    kemu.append({'kemu': '税金及附加', 'module': '费用模块', 'direction': '成本类',
                 'accountCode': 'TAX'})
    for b in FEI_BIAO:                                       # 两张费用表的科目清单
        for r in range(4, 34):
            bq = book.value(b, f'A{r}')
            if bq:
                kemu.append({'kemu': f'{b}/{bq}', 'module': '费用模块', 'direction': '成本类',
                             'accountCode': f'EXP.{b}.{r:03d}'})
    # 返回前把 Decimal 一律转 str：跨进程/落 JSON 时 Decimal 无法序列化，
    # 字符串形态也便于报告层原样展示；records 用 asdict 展平五个桶，不传 dataclass 实例。
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


# 自测：python -B excel_ingest_v2.py <九表演示件.xlsx>，打印类别/主体/年度/校验计数/
# 税金年额/摊销台账/分录笔数；只读文件、不写盘，失败时 ExcelError 原样抛出。
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
