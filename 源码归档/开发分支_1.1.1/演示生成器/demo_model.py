# -*- coding: utf-8 -*-
"""确定性演示业务数值层：固定种子生成收入/成本/费用/摊销输入参数。

设计约束（保证 226 项勾稽恒等成立的输入层条件）：
1. 三张费用表行 20（折旧及摊销）月度合计 == 摊销明细月摊销额（ROUND(原值/月数,2)），
   使资产负债表"未摊销资产及营运资金"与摊销明细"尚未摊销"同口径；
2. 全部科目金额非负且 < 90 亿元（excel_ingest 的取值范围校验）；
3. 生成值逐个避开数值黑名单哈希（老师原件数值零残留）；
4. 同一组（种子,主体,情景,类别）产出完全一致（逐字节复现的前提）。
"""
import hashlib  # sha256 数值哈希
import random  # sha256 十六进制摘要
from decimal import Decimal, ROUND_HALF_UP  # 黑名单比对键

from xlsx_patch import col_index  # noqa: F401  (复用列号工具)


def number_hash(v):  # 月度列 C..N
    return hashlib.sha256(str(Decimal(v).normalize()).encode()).hexdigest()


MONTHS = tuple(col for col in 'CDEFGHIJKLMN')  # 12 个月度列

# ==== v1.2 主体企业化：随机企业名（固定种子确定性；不得含"衡策/中学"字样）====

#: 字号池（双字僻字组合，避开现实知名企业与"衡/策/中/学"用字）
QIYE_ZIHAO = ('恒暻', '睿衍', '晟屿', '岚峙', '岱远', '泓翎', '屿棠',
              '峋瑞', '森屹', '洲衍', '宸屹', '汐衍')

#: 行业词池（一般企业报表适用行业；避开"衡/策/中/学"用字）
QIYE_HANGYE = ('智能制造', '数字科技', '供应链管理', '精密制造', '商贸实业', '信息技术')

#: 防撞名声明（写入各表 AY17 使用说明位；白名单文本输入格）
FANGZHUANG_SHENGMING = ('防撞名声明：主体名称由固定种子从演示字号池与行业词随机组合生成，'
                        '仅用于演示，与任何现实企业或组织无关；如有雷同纯属巧合。')


def qiye_ming(seed):
    """固定种子 → 确定性企业名（字号 + 行业词 + 有限公司）。"""
    rng = random.Random(f'{seed}|企业名|v1.2|防撞名')  # 独立种子流（与数值层解耦）
    ming = rng.choice(QIYE_ZIHAO) + rng.choice(QIYE_HANGYE) + '有限公司'
    for jin_ci in ('衡策', '中学'):  # 双保险：企业名禁词自检
        if jin_ci in ming:
            raise ValueError(f'生成的企业名含禁词 {jin_ci}：{ming}')
    return ming

# 费用科目基础月额（元）与数量基准：行号 -> (销售, 管理, 蓝恐龙) 月额；数量基准另行给出
EXPENSE_BASE = {
    4: (42000, 32000, 14000),    # 工资
    5: (3000, 2400, 1000),       # 十三薪（按月预算平摊）
    6: (1200, 900, 400),         # 离职补偿金
    7: (14000, 10500, 4500),     # 五险一金
    8: (2800, 2100, 900),        # 福利费
    9: (1500, 900, 300),         # 招聘费
    10: (1000, 800, 300),        # 培训费
    11: (6000, 4500, 1500),      # 房租
    12: (1500, 1100, 400),       # 物业管理费
    13: (1800, 1300, 500),       # 汽车费用
    14: (2200, 1600, 700),       # 办公费
    15: (1200, 900, 400),        # 办公用品
    16: (2500, 1800, 800),       # 水电煤
    17: (2000, 1800, 600),       # 咨询服务费
    18: (900, 700, 300),         # 电话费
    19: (500, 400, 150),         # 快递费
    21: (2600, 800, 300),        # 机票火车票
    22: (1800, 600, 250),        # 住宿费
    23: (900, 400, 150),         # 交通费
    24: (700, 300, 120),         # 差旅补贴
    25: (1600, 700, 250),        # 业务招待费
    26: (1100, 500, 200),        # 市内交通费
    27: (1300, 600, 200),        # 调研费用
    28: (450, 350, 150),         # 手续费
    29: (0, 0, 0),               # 利息收入（演示无借款利息冲回）
    30: (0, 0, 0),               # 利息支出（演示无借款）
    31: (150, 120, 60),          # 车船税
    32: (280, 200, 90),          # 印花税
    33: (600, 450, 180),         # 其他
}  # 月摊销常量（精确整除）
# 行 20 折旧及摊销：月摊销 2100.00 -> 销售 840 / 管理 840 / 蓝恐龙 420；
# (数量, 单价) 候选分解按黑名单安全性在运行时挑选，保证 price*qty 精确等于分摊值。
AMORT_MONTHLY = Decimal('2100.00')  # 行 20 月摊销常量
AMORT_CANDIDATES = {  # 候选（数量,单价）分解
    '销售费用': [(15, 56)],  # 摊销月数（黑名单安全）
    '管理费用': [(15, 56)],
    '蓝恐龙费用': [(15, 28), (12, 35)],
}
AMORT_MONTHS = 64                                   # 摊销月数（黑名单安全值）
AMORT_COST = (AMORT_MONTHLY * AMORT_MONTHS).quantize(Decimal('0.01'))  # 原值 134400.00
INCOME_TAX_RATE = Decimal('0.25')                   # 所得税率（演示假设，法定税率口径）
OPENING_CASH = Decimal('1200000.00')                # 期初投入资本（货币资金期初）
SURTAX_RATE = None                                  # 综合附加率由种子生成（0.5%~0.7%）

QTY_BASE = {  # 数量基准（人月/单据/间等口径），仅用于单价反推
    4: (12.0, 9.0, 4.0), 7: (12.0, 9.0, 4.0), 5: (12.0, 9.0, 4.0), 6: (12.0, 9.0, 4.0), 8: (12.0, 9.0, 4.0),
    9: (3.0, 2.0, 1.0), 10: (4.0, 3.0, 1.0), 11: (6.0, 4.0, 2.0), 12: (6.0, 4.0, 2.0),
    13: (3.0, 2.0, 1.0), 14: (11.0, 8.0, 3.0), 15: (6.0, 4.0, 2.0), 16: (5.0, 4.0, 2.0),
    17: (2.0, 2.0, 1.0), 18: (9.0, 7.0, 3.0), 19: (5.0, 4.0, 1.0),
    21: (26.0, 8.0, 3.0), 22: (18.0, 6.0, 2.0), 23: (9.0, 4.0, 1.0), 24: (7.0, 3.0, 1.0),
    25: (8.0, 3.0, 1.0), 26: (11.0, 5.0, 2.0), 27: (4.0, 2.0, 1.0),
    28: (15.0, 11.0, 5.0), 29: (1.0, 1.0, 1.0), 30: (1.0, 1.0, 1.0),
    31: (3.0, 2.0, 1.0), 32: (5.0, 3.0, 1.0), 33: (6.0, 4.0, 2.0),
}


class Demo:
    """一个（类别, 种子, 主体, 情景）组合的完整输入参数集。"""

    def __init__(self, seed, entity, scenario, category, blacklist=(), closed_month=6):  # Demo 参数集类
        self.seed = seed
        self.entity = entity
        self.scenario = scenario
        self.category = category
        self.closed_month = closed_month
        self.blocked = set(blacklist)
        self.rng = random.Random(f'{seed}|{entity}|{scenario}|{category}|演示生成器v2')
        self._build()

    # ---------- 工具 ----------
    def _safe(self, value, quantum=Decimal('0.01')):
        value = Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)
        step = Decimal('1') if quantum >= Decimal('1') else Decimal('0.37')
        for _ in range(200):
            if number_hash(value) not in self.blocked:
                return value
            value = (value + step).quantize(quantum, rounding=ROUND_HALF_UP)
        raise ValueError('生成值无法避开数值黑名单')

    def _jitter(self, lo, hi):
        return Decimal(self.rng.randrange(lo, hi + 1)) / 100000  # 0.85~1.15 之类

    # ---------- 生成 ----------
    def _build(self):
        closed = self.closed_month if self.category == '实时经营' else 12
        # 收入两表：单价（元/集）、数量（集）、单位采购成本（元/集）
        self.revenue = {}
        for sheet, p_lo, p_hi, q_lo, q_hi, c_lo, c_hi in (
                ('收入非主控', 150000, 250000, 8500, 13000, 60000, 83000),
                ('收入主控', 150000, 230000, 8500, 12500, 60000, 82000)):
            price, qty, cost = {}, {}, {}
            for i, m in enumerate(MONTHS):
                if i < closed:
                    price[m] = self._safe(Decimal(self.rng.randrange(p_lo, p_hi + 1)) / 100)
                    qty[m] = self._safe(Decimal(self.rng.randrange(q_lo, q_hi + 1)) / 100)
                    cost[m] = self._safe(Decimal(self.rng.randrange(c_lo, c_hi + 1)) / 100)
                else:
                    price[m] = Decimal('0.00')
                    qty[m] = Decimal('0.00')
                    cost[m] = Decimal('0.00')
            self.revenue[sheet] = {'price': price, 'qty': qty, 'unit_cost': cost}
        # 综合附加率 0.50%~0.70%
        self.surtax_rate = self._safe(Decimal(self.rng.randrange(50, 71)) / 10000)
        # 行 20 安全整数分解（数量、单价都避开黑名单且乘积精确）
        self.amort_split = {}
        for sheet, cands in AMORT_CANDIDATES.items():
            for q, p in cands:
                qd, pd = Decimal(f'{q}.00'), Decimal(f'{p}.00')
                if number_hash(qd) not in self.blocked and number_hash(pd) not in self.blocked:
                    self.amort_split[sheet] = (qd, pd)
                    break
            else:
                raise ValueError(f'{sheet} 行20 无法找到黑名单安全的摊销分解')
        # 费用三表：行 -> {月: (单价, 数量)}
        # 行 20（折旧及摊销）是公式格：ROUND('摊销明细'!X33/3,2)，由摊销参数驱动；
        # 行 29（利息收入）的单价/数量位不在底稿与契约白名单内（底稿缺该输入行），
        # 其月度公式引用空格自动得 0——两行均不属于可写输入层，跳过并登记验收报告。
        self.expenses = {}
        for sheet_idx, sheet in enumerate(('销售费用', '管理费用', '蓝恐龙费用')):
            table = {}
            for row in range(4, 34):
                if row in (20, 29):
                    continue
                per_month = {}
                for i, m in enumerate(MONTHS):
                    if i >= closed:
                        per_month[m] = (Decimal('0.00'), Decimal('0.00'))
                        continue
                    base = Decimal(str(EXPENSE_BASE[row][sheet_idx]))
                    if base == 0:
                        per_month[m] = (Decimal('0.00'), self._safe(Decimal('1.19')))
                        continue
                    band = (9800, 10200) if row in (4, 5, 7) else (8800, 11200)  # 工资类稳、变动类活
                    target = (base * Decimal(self.rng.randrange(*band)) / 10000)
                    qty = Decimal(str(QTY_BASE[row][sheet_idx])) * Decimal(self.rng.randrange(9600, 10401)) / 10000
                    qty = self._safe(qty)
                    price = (target / qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    per_month[m] = (self._safe(price), qty)
                table[row] = per_month
            self.expenses[sheet] = table
        # 固定参数（黑名单避让）
        self.income_tax_rate = self._safe(INCOME_TAX_RATE)
        self.opening_cash = self._safe(OPENING_CASH)
        self.amort_cost = self._safe(AMORT_COST)
        self.amort_months = self._safe(AMORT_MONTHS, Decimal('1'))
        self.amort_monthly = AMORT_MONTHLY  # 2100.00（=原值/月数，精确整除）
        # ---- v1.1 功能区演示参数（契约扩容层；全部固定种子确定性生成）----
        # 已结账月集合：预算=全年 12 月；实时=已结账截至月（未结账月按 0 口径）
        jieshu = set(MONTHS[:self.closed_month]) if self.category == '实时经营' else set(MONTHS)
        # Z1 营业外收支：月度小额演示值（其中项 125/127/129 行不填——恒等式自动满足）
        self.yingye_wai = {}
        for m in MONTHS:
            if m not in jieshu:
                self.yingye_wai[m] = (Decimal('0.00'), Decimal('0.00'))
                continue
            shouru = self._safe(Decimal(self.rng.randrange(90000, 150001)) / 100)
            zhichu = self._safe(Decimal(self.rng.randrange(50000, 90100)) / 100)
            self.yingye_wai[m] = (shouru, zhichu)
        # Z1 加权平均股数（全年一个值；演示口径：公司主体按 100 万股折算）
        self.gushu = self._safe(Decimal('1000000'))
        # Z3 分档率（占综合附加率的演示拆分口径：城建约 60% / 教育费附加约 40%；
        # 经 _safe 黑名单避让，占比值允许微调——分档恒等式按"城建+教育=附加"精确闭合）
        zhan_bi_1 = self._safe(Decimal('0.60'))  # v1.1 功能区参数段起点
        self.shuizhong_zhanbi = (zhan_bi_1, Decimal('1') - zhan_bi_1)
        # Z4 台账资产：双资产精确分摊（月摊销之和必须 == 老区月摊销 2100.00）
        t1 = self._safe(Decimal('1500'))
        t2 = AMORT_MONTHLY - t1
        for _ in range(200):
            if number_hash(t2) not in self.blocked:
                break
            t1 += Decimal('0.01')
            t2 = AMORT_MONTHLY - t1
        else:
            raise ValueError('台账分摊无法避开数值黑名单')
        # 原值 = 月摊销×64（整除精确：ROUND(原值/64,2) == 月摊销）
        self.taizhang = (
            ('演示资产甲', '销售费用', '业务部', '2027-01', t1 * 64, Decimal('64'), t1),
            ('演示资产乙', '管理费用', '行政部', '2027-01', t2 * 64, Decimal('64'), t2),
        )


def load_blacklist(path):
    import json
    with open(path, encoding='utf-8') as f:
        return tuple(json.load(f))
