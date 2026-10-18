# -*- coding: utf-8 -*-
"""数值模型：种子 → 十二表全部数值（零公式，全部由程序算出）。

架构：
    seed → 参数层（收入/费用/摊销/往来/现金）→ 各表数值 → {表名: {格位: 数值}}
写出器（xiechu.py）只负责"把数字放进版式指定的格位"，不做任何计算。

口径（演示假设，全部标注演示）：
    - 主体一 = 非主控业务（收入非主控表），主体二 = 主控业务（收入主控表）；
      三表"含《项目一》"块 = 基础块 + 项目一追加分成（六四分）。
    - 三表 = 老师件版式（利润表双情景块 / 资负左右两栏 / 现金流本期=累计）。
    - 恒等式由程序保证（写出即成立）：
        收入 = 单价×数量、成本 = 单位成本×数量、分档税合计 = 税金及附加、
        三费汇总 = 三表之和、摊销矩阵合计 = 本月摊销、现金链（期末=期初+净增加）、
        资负平衡（资产 = 负债 + 权益）、分录借贷平衡且现金流对照 = 现金流量表。
"""
import hashlib
import random
from decimal import Decimal, ROUND_HALF_UP

from heimingdan import HASHES

YUE_LIE = tuple('CDEFGHIJKLMN')                       # 12 个月度列
YUEFEN = tuple(f'2027-{i:02d}' for i in range(1, 13))
FEN = Decimal('0.01')
SI_WEI = Decimal('0.0001')
ZERO = Decimal('0.00')
BEN_FEN = Decimal('0.0001')                           # 万分之一（比率刻度）
FEI_BIAO = ('销售费用', '管理费用')                   # 两张费用表（原"蓝恐龙费用"已并入管理费用）
FEI_XISHU = Decimal('0.70')                           # 演示费用系数（让两主体都有正利润）

#: 费用科目基准月额（元）：行号 → (销售费用, 管理费用)
FEI_BASE = {
    4: (42000, 46000), 5: (3000, 3400), 6: (1200, 1300),
    7: (14000, 15000), 8: (2800, 3000), 9: (1500, 1200),
    10: (1000, 1100), 11: (6000, 6000), 12: (1500, 1500),
    13: (1800, 1800), 14: (2200, 2300), 15: (1200, 1300),
    16: (2500, 2600), 17: (2000, 2400), 18: (900, 1000),
    19: (500, 550), 21: (2600, 1100), 22: (1800, 850),
    23: (900, 550), 24: (700, 420), 25: (1600, 950),
    26: (1100, 700), 27: (1300, 800), 28: (450, 500),
    30: (800, 800), 31: (150, 180), 32: (280, 290), 33: (600, 630),
}

#: 费用科目基准数量（人月/单据/间等口径，仅用于反推单价）
FEI_QTY = {
    4: (12.0, 13.0), 5: (12.0, 13.0), 6: (3.0, 3.0), 7: (12.0, 13.0),
    8: (12.0, 13.0), 9: (3.0, 3.0), 10: (4.0, 4.0), 11: (6.0, 6.0),
    12: (6.0, 6.0), 13: (3.0, 3.0), 14: (11.0, 11.0), 15: (6.0, 6.0),
    16: (5.0, 6.0), 17: (2.0, 3.0), 18: (9.0, 10.0), 19: (5.0, 5.0),
    21: (26.0, 11.0), 22: (18.0, 8.0), 23: (9.0, 5.0), 24: (7.0, 4.0),
    25: (8.0, 4.0), 26: (11.0, 7.0), 27: (4.0, 3.0), 28: (15.0, 16.0),
    30: (1.0, 2.0), 31: (3.0, 3.0), 32: (5.0, 4.0), 33: (6.0, 6.0),
}

#: 摊销台账八项资产：(名称, 费用归属表, 部门, 月摊销, 摊销月数)；月摊销合计 = 2100.00
#: 月数取"黑名单安全值"（老师件行次 1..135 里的整数已被黑名单占用）
ZICHAN = (
    ('摄影设备', '销售费用', '业务部', 420, 47),
    ('剪辑工作站', '管理费用', '制作部', 315, 37),
    ('录音设备', '销售费用', '业务部', 260, 49),
    ('灯光器材', '管理费用', '制作部', 245, 57),
    ('办公装修', '管理费用', '行政部', 230, 23),
    ('运输车辆', '销售费用', '业务部', 230, 30),
    ('软件授权', '管理费用', '技术部', 210, 35),
    ('空调机组', '管理费用', '行政部', 190, 55),
)

#: 行业化摊销台账（月摊销额与归属保持不变 → 费用表行 20 / 摊销矩阵数值不变）
#: 制造企业不该出现摄影设备/剪辑工作站这类影视资产，按行业换成本行业的设备
ZICHAN_BY_HANG = {
    '智能制造': (                                   # 整机代工
        ('贴片机', '销售费用', '生产部', 420, 47),
        ('回流焊炉', '管理费用', '生产部', 315, 37),
        ('波峰焊机', '销售费用', '生产部', 260, 49),
        ('检测治具', '管理费用', '品质部', 245, 57),
        ('总装流水线', '管理费用', '生产部', 230, 23),
        ('配送货车', '销售费用', '仓储部', 230, 30),
        ('注塑机', '管理费用', '生产部', 210, 35),
        ('中央空调', '管理费用', '行政部', 190, 55),
    ),
    '精密制造': (                                   # 贴片代工
        ('高速贴片机', '销售费用', '生产部', 420, 47),
        ('AOI 检测仪', '管理费用', '品质部', 315, 37),
        ('锡膏印刷机', '销售费用', '生产部', 260, 49),
        ('X-Ray 检测仪', '管理费用', '品质部', 245, 57),
        ('洁净车间装修', '管理费用', '行政部', 230, 23),
        ('物料配送车', '销售费用', '仓储部', 230, 30),
        ('二次回流焊', '管理费用', '生产部', 210, 35),
        ('空压机组', '管理费用', '动力部', 190, 55),
    ),
    '商贸实业': (                                   # 贸易中间商
        ('门店装修', '销售费用', '门店部', 420, 47),
        ('陈列货架', '管理费用', '仓储部', 315, 37),
        ('收银系统', '销售费用', '门店部', 260, 49),
        ('仓储货架', '管理费用', '仓储部', 245, 57),
        ('办公装修', '管理费用', '行政部', 230, 23),
        ('配送车辆', '销售费用', '物流部', 230, 30),
        ('打包设备', '管理费用', '仓储部', 210, 35),
        ('中央空调', '管理费用', '行政部', 190, 55),
    ),
    '供应链管理': (                                 # 品牌加盟
        ('加盟门店装修', '销售费用', '加盟部', 420, 47),
        ('品牌展陈道具', '管理费用', '品牌部', 315, 37),
        ('POS 收银系统', '销售费用', '加盟部', 260, 49),
        ('冷链运输车', '管理费用', '物流部', 245, 57),
        ('分拣流水线', '管理费用', '仓储部', 230, 23),
        ('配送车辆', '销售费用', '物流部', 230, 30),
        ('仓储管理系统', '管理费用', '信息部', 210, 35),
        ('中央空调', '管理费用', '行政部', 190, 55),
    ),
    '数字科技': (                                   # 信息服务
        ('服务器集群', '销售费用', '技术部', 420, 47),
        ('开发工作站', '管理费用', '技术部', 315, 37),
        ('网络设备', '销售费用', '运维部', 260, 49),
        ('机房精密空调', '管理费用', '运维部', 245, 57),
        ('办公装修', '管理费用', '行政部', 230, 23),
        ('交付用车', '销售费用', '交付部', 230, 30),
        ('存储阵列', '管理费用', '技术部', 210, 35),
        ('UPS 电源', '管理费用', '运维部', 190, 55),
    ),
    '信息技术': (
        ('机房服务器', '销售费用', '技术部', 420, 47),
        ('开发工作站', '管理费用', '技术部', 315, 37),
        ('网络设备', '销售费用', '运维部', 260, 49),
        ('测试终端', '管理费用', '测试部', 245, 57),
        ('办公装修', '管理费用', '行政部', 230, 23),
        ('运维用车', '销售费用', '运维部', 230, 30),
        ('存储设备', '管理费用', '技术部', 210, 35),
        ('精密空调', '管理费用', '运维部', 190, 55),
    ),
}

#: 资负左栏明细（行号 → (上年年末, 期末)）；6 货币资金与 13 其他应收款（兜底位）另行处理
ZIFU_ZUO = {
    7: (130000, 150000), 8: (50000, 60000), 9: (80000, 95000), 10: (350000, 380000),
    11: (35000, 40000), 12: (60000, 68000), 14: (140000, 155000), 15: (100000, 120000),
    16: (0, 0), 17: (25000, 25000), 18: (9000, 11000),
    21: (70000, 80000), 22: (40000, 45000), 23: (28000, 30000), 24: (200000, 210000),
    25: (65000, 70000), 26: (50000, 55000), 27: (170000, 180000), 28: (560000, 592000),
    29: (90000, 120000), 30: (0, 0), 31: (0, 0), 32: (85000, 90000), 33: (60000, 55000),
    34: (30000, 35000), 35: (40000, 40000), 36: (30000, 25000), 37: (15000, 18000),
    38: (8000, 9000),
}
#: 资负右栏明细（行号 → (上年年末, 期末)）；15 其他应付款（兜底位）与权益行另行处理
ZIFU_YOU = {
    6: (300000, 340000), 7: (18000, 20000), 8: (7000, 8000), 9: (60000, 55000),
    10: (220000, 240000), 11: (90000, 100000), 12: (140000, 150000), 13: (70000, 75000),
    14: (45000, 50000), 16: (0, 0), 17: (40000, 35000), 18: (7000, 8000),
    21: (250000, 280000), 22: (20000, 20000), 23: (0, 0), 24: (0, 0), 25: (80000, 85000),
    26: (30000, 28000), 27: (5000, 6000), 28: (14000, 15000), 29: (3000, 4000),
    30: (8000, 9000),
    34: (1500000, 1500000), 35: (0, 0), 36: (0, 0), 37: (0, 0), 38: (120000, 120000),
    39: (0, 0), 41: (10000, 12000),
}

#: 现金流量表行号映射（财会2019-6号版式，见官方模板 A 列标签）
XJL_HANG = {
    'shou_xian': 6, 'fan_huan': 7, 'qi_ta_shou': 8, 'jing_liu_ru': 9,
    'gou_mai': 10, 'zhi_gong': 11, 'shui_fei': 12, 'qi_ta_fu': 13,
    'jing_liu_chu': 14, 'jing_jing': 15,
    'shou_hui': 17, 'shou_yi': 18, 'chu_zhi': 19, 'chu_zhi_zi': 20, 'shou_qi_ta': 21,
    'tou_liu_ru': 22, 'gou_jian': 23, 'tou_zi_fu': 24, 'qu_de_zi': 25, 'fu_qi_ta': 26,
    'tou_liu_chu': 27, 'tou_jing': 28,
    'xi_shou': 30, 'jie_kuan': 31, 'chou_qi_ta': 32, 'chou_liu_ru': 33,
    'chang_huan': 34, 'gu_li': 35, 'chou_fu_qi_ta': 36, 'chou_liu_chu': 37,
    'chou_jing': 38, 'hui_lv': 39, 'jing_zeng': 40, 'qi_chu': 41, 'qi_mo': 42,
}

#: 现金流量表的可独立取数项（其余为派生小计/净额）
XIAN_SHU_RU = ('shou_xian', 'fan_huan', 'qi_ta_shou', 'gou_mai', 'zhi_gong', 'shui_fei',
               'qi_ta_fu', 'shou_hui', 'shou_yi', 'chu_zhi', 'chu_zhi_zi', 'shou_qi_ta',
               'gou_jian', 'tou_zi_fu', 'qu_de_zi', 'fu_qi_ta', 'xi_shou', 'jie_kuan',
               'chou_qi_ta', 'chang_huan', 'gu_li', 'chou_fu_qi_ta', 'hui_lv')

#: 每笔分录模板：(摘要, 借方科目, 贷方科目, 金额键, 现金流对照行号或 None)
FENLU_XIAN = (
    ('销售收现（演示）', '银行存款', '主营业务收入', 'shou', 6),
    ('采购付现（演示）', '库存商品', '银行存款', 'gou', 10),
    ('工资社保付现（演示）', '费用（演示合并）', '银行存款', 'gong', 11),
    ('税费付现（演示）', '应交税费', '银行存款', 'shui', 12),
    ('费用付现（演示合并）', '费用（演示合并）', '银行存款', 'qi', 13),
    ('购建资产付现（演示）', '固定资产', '银行存款', 'jian', 23),
    ('投资支付（演示）', '长期股权投资', '银行存款', 'tou', 24),
    ('取得借款（演示）', '银行存款', '短期借款', 'jie', 31),
    ('偿还债务（演示）', '短期借款', '银行存款', 'chang', 34),
    ('分配股利（演示）', '利润分配', '银行存款', 'gu', 35),
    # 增值税三笔（价税分离：销项计入收现、进项计入付现、应纳计入支付税费）
    ('销项税额（演示）', '银行存款', '应交税费—应交增值税（销项税额）', 'xiao_xiang', 6),
    ('进项税额（演示）', '应交税费—应交增值税（进项税额）', '银行存款', 'jin_xiang', 10),
    ('缴纳增值税（演示）', '应交税费—未交增值税', '银行存款', 'zeng_jiao', 12),
    # 以下六类补齐现金流量表其余行（保证"银行存款"净额 = 现金净增加）
    ('收到税费返还（演示）', '银行存款', '其他收益', 'fan_huan', 7),
    ('收到其他经营款（演示）', '银行存款', '其他应付款', 'qi_ta_shou', 8),
    ('收回投资（演示）', '银行存款', '长期股权投资', 'shou_hui', 17),
    ('收到投资收益（演示）', '银行存款', '投资收益', 'shou_yi', 18),
    ('处置固定资产收现（演示）', '银行存款', '固定资产', 'chu_zhi', 19),
    ('处置子公司收现（演示）', '银行存款', '长期股权投资', 'chu_zhi_zi', 20),
    ('收到其他投资款（演示）', '银行存款', '其他应收款', 'shou_qi_ta', 21),
    ('取得子公司付现（演示）', '长期股权投资', '银行存款', 'qu_de_zi', 25),
    ('支付其他投资款（演示）', '其他应收款', '银行存款', 'fu_qi_ta', 26),
    ('吸收投资收现（演示）', '银行存款', '实收资本', 'xi_shou', 30),
    ('收到其他筹资款（演示）', '银行存款', '其他应付款', 'chou_qi_ta', 32),
    ('支付其他筹资款（演示）', '其他应付款', '银行存款', 'chou_fu_qi_ta', 36),
)
#: 第二组非现金分录模板（摘要, 借, 贷, 取数表, 取数行）——给实时经营凑满每月笔数
FENLU_FEI2 = (
    ('计提差旅费（演示）', '管理费用', '其他应付款', '管理费用', 21),
    ('计提住宿费（演示）', '管理费用', '其他应付款', '管理费用', 22),
    ('计提交通费（演示）', '管理费用', '其他应付款', '管理费用', 23),
    ('计提差旅补贴（演示）', '管理费用', '其他应付款', '管理费用', 24),
    ('计提业务招待费（演示）', '管理费用', '其他应付款', '管理费用', 25),
    ('计提市内交通费（演示）', '管理费用', '其他应付款', '管理费用', 26),
    ('计提调研费（演示）', '管理费用', '其他应付款', '管理费用', 27),
    ('计提手续费（演示）', '财务费用', '其他应付款', '管理费用', 28),
    ('计提办公费（演示）', '管理费用', '其他应付款', '管理费用', 14),
    ('计提办公用品（演示）', '管理费用', '其他应付款', '管理费用', 15),
    ('计提水电煤（演示）', '管理费用', '其他应付款', '管理费用', 16),
    ('计提咨询服务费（演示）', '管理费用', '应付账款', '管理费用', 17),
    ('计提电话费（演示）', '管理费用', '其他应付款', '管理费用', 18),
    ('计提快递费（演示）', '销售费用', '其他应付款', '销售费用', 19),
    ('计提福利费（演示）', '费用（演示合并）', '应付职工薪酬', '销售费用', 8),
    ('计提招聘费（演示）', '管理费用', '其他应付款', '销售费用', 9),
    ('计提培训费（演示）', '管理费用', '其他应付款', '销售费用', 10),
    ('计提汽车费用（演示）', '销售费用', '其他应付款', '销售费用', 13),
    ('计提物业管理费（演示）', '管理费用', '其他应付款', '销售费用', 12),
    ('计提差旅（发行）（演示）', '销售费用', '其他应付款', '销售费用', 21),
    ('计提招待（发行）（演示）', '销售费用', '其他应付款', '销售费用', 25),
    ('计提其他费用（演示）', '管理费用', '其他应付款', '销售费用', 33),
    ('计提车船税（演示）', '税金及附加', '应交税费', '销售费用', 31),
    ('计提印花税（演示）', '税金及附加', '应交税费', '销售费用', 32),
    ('计提坏账准备（演示）', '资产减值损失', '坏账准备', '管理费用', 33),
)

FENLU_FEI = (
    # —— 月末结转（损益 → 本年利润）——
    ('结转营业收入（演示）', '主营业务收入', '本年利润', 'shouru_yue'),
    ('结转销售成本（演示）', '主营业务成本', '库存商品', 'chengben_yue'),
    ('结转营业成本（演示）', '本年利润', '主营业务成本', 'chengben_yue'),
    ('结转期间费用（演示）', '本年利润', '费用（演示合并）', 'feiyong_yue'),
    # —— 计提（与利润表逐行对应，保证账面利润 = 报表净利润）——
    ('计提折旧摊销（演示）', '折旧及摊销', '累计折旧及摊销（1602/1702/1801）', 'tan'),
    ('计提税金及附加（演示）', '税金及附加', '应交税费', 'shui'),
    ('计提所得税（演示）', '所得税费用', '应交税费', 'suo_ji'),
    ('计提财务费用（演示）', '财务费用', '应付利息', 'caiwu'),
    ('计提研发费用（演示）', '研发费用', '应付职工薪酬', 'yanfa'),
    ('计提信用减值（演示）', '信用减值损失', '坏账准备', 'huai'),
    ('计提资产减值（演示）', '资产减值损失', '存货跌价准备', 'jzhi'),
    ('公允价值变动（演示）', '交易性金融资产', '公允价值变动收益', 'gyjz'),
    ('资产处置收益（演示）', '其他应收款', '资产处置收益', 'czhi'),
    ('营业外收入（演示）', '其他应付款', '营业外收入', 'ywsr'),
    ('营业外支出（演示）', '营业外支出', '其他应付款', 'ywzc'),
    ('结转未交增值税（演示）', '应交税费—应交增值税（转出未交增值税）',
     '应交税费—未交增值税', 'zeng_jiao'),
    ('摊余成本终止确认收益（演示）', '其他应收款', '摊余成本终止确认收益', 'tanyu'),
    ('计提盈余公积（演示）', '利润分配', '盈余公积', 'ying'),
)


def shu_ha(v):
    """数值哈希（与 1.0.5 契约同口径：sha256(Decimal 规范化字符串)）。"""
    return hashlib.sha256(str(Decimal(v).normalize()).encode()).hexdigest()


def ming_zhong(v):
    """是否命中老师原件数值黑名单（零值豁免）。"""
    return Decimal(v) != 0 and shu_ha(v) in HASHES


def rd(v):
    """四舍五入到分。"""
    return Decimal(v).quantize(FEN, rounding=ROUND_HALF_UP)


def rd4(v):
    """四舍五入到四位小数（每股收益）。"""
    return Decimal(v).quantize(SI_WEI, rounding=ROUND_HALF_UP)


class ShuJu:
    """一个种子对应的十二表数值全集。"""

    def __init__(self, seed, leibie='预算基础', hangye=None):
        self.seed = seed
        self.leibie = leibie
        self.hangye = hangye
        #: 摊销台账随行业走（月摊销额与归属不变，只换资产名称/部门）
        self.zichan = ZICHAN_BY_HANG.get(hangye, ZICHAN)
        self.rng = random.Random(f'{seed}|数值层|v2')
        #: 生效月：预算基础 = 全年 12 月；实时经营 = 已结账截至 6 月（其余月按零口径填数）
        self.huo_yue = tuple(YUE_LIE) if leibie == '预算基础' else tuple(YUE_LIE[:6])
        self.biao = {}
        self._shouru()
        self._shuijin()
        self._feiyong()
        self._huizong()
        self._tanxiao()
        self._xianjin()
        self._lirun()
        self._zifu()
        self._fenlu()
        self.xianjin_biao()

    # ---------- 基础工具 ----------
    def _put(self, biao, ref, v):
        self.biao.setdefault(biao, {})[ref] = v

    def _jitter(self, lo, hi):
        """基准浮动（千分刻度）：0.970 ~ 1.030。"""
        return Decimal(self.rng.randrange(lo, hi + 1)) / 1000

    def _safe(self, v, bu=Decimal('0.37'), cishu=200):
        """数值避让：命中黑名单就按 +0.37 步进，直到安全。"""
        v = rd(v)
        for _ in range(cishu):
            if not ming_zhong(v):
                return v
            v = rd(v + bu)
        raise ValueError(f'数值无法避开黑名单：{v}')

    def _safe_jia_liang(self, jia, liang):
        """单价 × 数量（含乘积）同时避让黑名单。"""
        jia, liang = self._safe(jia), self._safe(liang)
        for _ in range(50):
            if not ming_zhong(rd(jia * liang)):
                return jia, liang
            liang = self._safe(liang + Decimal('0.01'))
        raise ValueError('单价×数量无法避开黑名单')

    def _fen_yue(self, nian_e, quan):
        """年度金额按权重分到生效月（末月吸收尾差，合计精确；未生效月记 0）。"""
        zai = self.huo_yue
        zong = sum(quan[i] for i, m in enumerate(YUE_LIE) if m in zai)
        out, he = {}, ZERO
        for i, m in enumerate(YUE_LIE):
            if m not in zai:
                out[m] = ZERO
                continue
            if m == zai[-1]:
                out[m] = nian_e - he
            else:
                v = rd(nian_e * Decimal(quan[i]) / Decimal(zong))
                out[m] = v
                he += v
        return out

    # ---------- 收入/成本（收入两表已下线：只算数，不落表）----------
    def _shouru(self):
        """按"两主体"口径生成月度收入/成本，仅供下游取数（不再输出收入两表）。"""
        self.yue_shouru = {m: ZERO for m in YUE_LIE}
        self.yue_chengben = {m: ZERO for m in YUE_LIE}
        zong = {'收入非主控': ZERO, '收入主控': ZERO}
        zong_cheng = {'收入非主控': ZERO, '收入主控': ZERO}
        for zhu, plo, phi, qlo, qhi, clo, chi in (
                ('收入非主控', 160000, 240000, 8500, 13000, 70000, 95000),
                ('收入主控', 150000, 230000, 8000, 12500, 68000, 93000)):
            for m in YUE_LIE:
                if m not in self.huo_yue:                                    # 未结账月：零口径
                    continue
                jia = rd(Decimal(self.rng.randrange(plo, phi + 1)) / 100)     # 授权单价
                liang = rd(Decimal(self.rng.randrange(qlo, qhi + 1)) / 100)   # 授权数量
                cheng = rd(Decimal(self.rng.randrange(clo, chi + 1)) / 100)   # 单位采购成本
                jia, liang = self._safe_jia_liang(jia, liang)                 # 黑名单避让
                cheng = self._safe(cheng)
                shou = rd(jia * liang)                                       # 营业收入
                cheng_ = rd(cheng * liang)                                   # 营业成本
                self.yue_shouru[m] += shou
                self.yue_chengben[m] += cheng_
                zong[zhu] += shou
                zong_cheng[zhu] += cheng_
        self.nian_shouru = zong
        self.nian_chengben = zong_cheng

    # ---------- 税金及附加（口径依《05_四企业对照与衡策映射》§4）----------
    def _shuijin(self):
        """增值税应纳额 → 城建 7% / 教育 3% / 地方 2% / 文化 0；印花税 0.3‰ 并入合计。

        Z3 行 127 = SUM(123:126) + 印花税_m，且逐月等于税金及附加 C..N33（导入器硬约束）；
        计税收入 = 当月不含税营业收入；综合附加率 = 年税金 ÷ 年计税收入（口径披露）。
        """
        biao = '税金及附加'
        XIAO_LV = Decimal('0.13')            # 销项税率（货物销售/加工修理修配）
        JIN_LV = Decimal('0.13')             # 进项税率（采购/委托加工取得）
        YIN_LV = Decimal('0.0003')           # 印花税 0.3‰（买卖/承揽合同）
        CHENG, JIAO, DI = Decimal('0.07'), Decimal('0.03'), Decimal('0.02')
        lie_fen = ('Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB')
        yue_shui, yue_fen = {}, {r: {} for r in (123, 124, 125, 126, 127)}
        yue_zeng, yue_xiao, yue_jin = {}, {}, {}            # 增值税应纳额/销项/进项
        liudi = ZERO                                        # 期初留抵
        for m in YUE_LIE:
            if m not in self.huo_yue:                       # 未结账月：零口径
                self._put(biao, f'{m}32', ZERO)
                self._put(biao, f'{m}33', ZERO)
                yue_shui[m] = ZERO
                yue_zeng[m] = yue_xiao[m] = yue_jin[m] = ZERO
                for r in (123, 124, 125, 126, 127):
                    yue_fen[r][m] = ZERO
                continue
            shou, cheng_ben = self.yue_shouru[m], self.yue_chengben[m]
            xiao = rd(shou * XIAO_LV)                       # 销项税额
            jin = rd(cheng_ben * JIN_LV)                    # 进项税额
            ying = max(xiao - jin - liudi, ZERO)            # 当月增值税应纳额
            liudi = max(jin + liudi - xiao, ZERO)           # 留抵结转
            yue_zeng[m] = ying
            yue_xiao[m] = xiao
            yue_jin[m] = jin
            a = rd(ying * CHENG)                            # 城建税
            b = rd(ying * JIAO)                             # 教育费附加
            c = rd(ying * DI)                               # 地方教育附加
            d = ZERO                                        # 文化事业建设费（不适用）
            yin = rd((shou + cheng_ben) * YIN_LV)           # 印花税（并入合计）
            tong = a + b + c + d + yin
            self._put(biao, f'{m}32', shou)                 # 计税收入（不含税）
            self._put(biao, f'{m}33', tong)                 # 税金及附加
            yue_shui[m] = tong
            for r, v in ((123, a), (124, b), (125, c), (126, d), (127, tong)):
                yue_fen[r][m] = v
        self.yue_shui = yue_shui
        self.nian_shui = sum(yue_shui.values(), ZERO)
        self.yue_zeng, self.yue_xiaoxiang, self.yue_jinxiang = yue_zeng, yue_xiao, yue_jin
        self.nian_xiaoxiang = sum(yue_xiao.values(), ZERO)
        self.nian_jinxiang = sum(yue_jin.values(), ZERO)
        self.nian_zeng = sum(yue_zeng.values(), ZERO)
        nian_shou = sum((self.yue_shouru[m] for m in self.huo_yue), ZERO)
        self.fujia_lv = rd4(self.nian_shui / nian_shou) if nian_shou else ZERO
        self._put(biao, 'C31', self.fujia_lv)
        for r in (123, 124, 125, 126, 127):                 # 月度矩阵 + 年度合计
            for i, m in enumerate(YUE_LIE):
                self._put(biao, f'{lie_fen[i]}{r}', yue_fen[r][m])
            self._put(biao, f'AC{r}', sum((yue_fen[r][m] for m in YUE_LIE), ZERO))
        for r in (123, 124, 125, 126):                      # 分档率列 = 年各税 ÷ 年计税收入
            nian_e = sum((yue_fen[r][m] for m in YUE_LIE), ZERO)
            self._put(biao, f'P{r}', rd4(nian_e / nian_shou) if nian_shou else ZERO)
        # 老区行映射（05 文档 §4.1）：B3 增值税 / B4 增值税(主控=0) / B6 合计 /
        # B7 城建 / B8 教育 / B9 地方 / B10 文化；C..N 月列，O 年合计
        def xie_hang(hang, qu):
            gong = ZERO
            for m in YUE_LIE:
                v = qu(m)
                self._put(biao, f'{m}{hang}', v)
                gong += v
            self._put(biao, f'O{hang}', gong)

        xie_hang(3, lambda m: yue_zeng[m])                  # 增值税（非主控）
        xie_hang(4, lambda m: ZERO)                         # 增值税（主控）：演示无此拆分
        xie_hang(6, lambda m: yue_shui[m])                  # 税金及附加合计
        xie_hang(7, lambda m: yue_fen[123][m])              # 城建税
        xie_hang(8, lambda m: yue_fen[124][m])              # 教育费附加
        xie_hang(9, lambda m: yue_fen[125][m])              # 地方教育附加
        xie_hang(10, lambda m: yue_fen[126][m])             # 文化事业建设费

    # ---------- 费用三表 ----------
    def _feiyong(self):
        # 折旧摊销按台账归属汇总（09 / 17-T2 口径）：行 20 = 归属该表的资产月摊销合计
        tan_by = {s: ZERO for s in FEI_BIAO}
        for _, gui, _, yue_tan, _ in self.zichan:
            if gui in tan_by:
                tan_by[gui] += Decimal(yue_tan)
        self.fei_yue = {}
        for si, biao in enumerate(FEI_BIAO):
            for row in range(4, 34):
                yue = {}
                for m in YUE_LIE:
                    if m not in self.huo_yue:                       # 未结账月：零口径
                        self._put(biao, f'{m}{row}', ZERO)
                        self._put(biao, f'{m}{row + 200}', ZERO)
                        self._put(biao, f'{m}{row + 320}', ZERO)
                        yue[m] = ZERO
                        continue
                    if row == 20:                                   # 折旧及摊销（按台账归属）
                        liang = self._safe(Decimal('1.13'))          # 数量取安全值（1 在黑名单里）
                        dan = self._safe(rd(tan_by[biao] / liang))
                        he = rd(dan * liang)
                    elif row == 29:                                 # 利息收入（演示无）
                        liang = self._safe(Decimal('1.13'))
                        dan, he = ZERO, ZERO
                    else:
                        base = Decimal(FEI_BASE[row][si]) * FEI_XISHU * self._jitter(970, 1030)
                        liang = rd(Decimal(str(FEI_QTY[row][si])) * self._jitter(960, 1040))
                        if liang <= 0:
                            liang = Decimal('1.00')
                        liang = self._safe(liang)
                        for _ in range(30):                       # 单价×金额一起避让
                            dan = self._safe(rd(base / liang))
                            he = rd(dan * liang)
                            if not ming_zhong(he):
                                break
                            liang = self._safe(liang + Decimal('0.37'))
                        else:
                            raise ValueError(f'{biao} 行 {row} 金额无法避开黑名单')
                    self._put(biao, f'{m}{row}', he)                # 月度金额
                    self._put(biao, f'{m}{row + 200}', dan)         # 单价区 204-233
                    self._put(biao, f'{m}{row + 320}', liang)       # 数量区 324-353
                    yue[m] = he
                self._put(biao, f'O{row}', sum(yue.values(), ZERO))
            for m in YUE_LIE:
                he34 = sum((self.biao[biao][f'{m}{r}'] for r in range(4, 34)), ZERO)
                self._put(biao, f'{m}34', he34)                     # 合计
                self._put(biao, f'{m}35', self.yue_shui[m])         # 增值税附加
                self._put(biao, f'{m}36', he34 + self.yue_shui[m])  # 三费及税金合计
            for o, yuan in (('O34', 34), ('O35', 35), ('O36', 36)):
                self._put(biao, o,
                          sum((self.biao[biao][f'{m}{yuan}'] for m in YUE_LIE), ZERO))
            self.fei_yue[biao] = {
                'he34': self.biao[biao]['O34'],
                'renyuan': sum((self.biao[biao][f'{m}{r}'] for m in YUE_LIE
                                for r in (4, 5, 6, 7, 8)), ZERO),
                'caiwu': sum((self.biao[biao][f'{m}{r}'] for m in YUE_LIE
                              for r in (28, 30)), ZERO),
            }
        self.san_fei_nian = sum((self.fei_yue[s]['he34'] for s in FEI_BIAO), ZERO)
        self.renyuan_nian = sum((self.fei_yue[s]['renyuan'] for s in FEI_BIAO), ZERO)

    # ---------- 费用表月度汇总 ----------
    def _huizong(self):
        biao = '费用表月度汇总'
        for row in range(4, 34):
            for m in YUE_LIE:
                self._put(biao, f'{m}{row}',
                          sum((self.biao[s][f'{m}{row}'] for s in FEI_BIAO), ZERO))
            self._put(biao, f'O{row}',
                      sum((self.biao[biao][f'{m}{row}'] for m in YUE_LIE), ZERO))
        for m in YUE_LIE:
            he34 = sum((self.biao[biao][f'{m}{r}'] for r in range(4, 34)), ZERO)
            self._put(biao, f'{m}34', he34)
            self._put(biao, f'{m}35',
                      sum((self.biao[s][f'{m}35'] for s in FEI_BIAO), ZERO))
            self._put(biao, f'{m}36', he34 + self.biao[biao][f'{m}35'])
        for o, yuan in (('O34', 34), ('O35', 35), ('O36', 36)):
            self._put(biao, o, sum((self.biao[biao][f'{m}{yuan}'] for m in YUE_LIE), ZERO))

    # ---------- 摊销明细（含台账区 / 矩阵区）----------
    def _tanxiao(self):
        biao = '摊销明细'
        yue_shu, yue_tan = 47, Decimal('2100.00')
        yuan_zhi = yue_tan * yue_shu
        self.tan_yue_tan, self.tan_yuan_zhi = yue_tan, yuan_zhi
        for v in (yue_tan, Decimal(yue_shu), yuan_zhi):              # 摊销参数避让自检
            if ming_zhong(v):
                raise ValueError(f'摊销参数命中黑名单：{v}')
        self._put(biao, 'C31', yuan_zhi)
        self._put(biao, 'C32', Decimal(yue_shu))
        lei = ZERO
        for m in YUE_LIE:
            self._put(biao, f'{m}31', yuan_zhi)
            self._put(biao, f'{m}32', Decimal(yue_shu))
            self._put(biao, f'{m}33', rd(yuan_zhi / yue_shu))       # 本月摊销 2100.00
            lei += rd(yuan_zhi / yue_shu)
            self._put(biao, f'{m}34', lei)                          # 累计已摊销
            self._put(biao, f'{m}35', yuan_zhi - lei)               # 尚未摊销
        lie_ju = ('P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA')
        for i, (ming, gui, bu, tan, shu) in enumerate(self.zichan):
            hang = 123 + i
            self._put(biao, f'O{hang}', ming)
            self._put(biao, f'P{hang}', gui)
            self._put(biao, f'Q{hang}', bu)
            self._put(biao, f'R{hang}', '2027-01')
            self._put(biao, f'S{hang}', Decimal(tan) * shu)
            self._put(biao, f'T{hang}', Decimal(shu))
            self._put(biao, f'U{hang}', rd(Decimal(tan) * shu / shu))   # ROUND(原值/月数)
            ju = 133 + i
            self._put(biao, f'O{ju}', ming)
            for x in lie_ju:
                self._put(biao, f'{x}{ju}', Decimal(tan))
            self._put(biao, f'AB{ju}', Decimal(tan) * 12)
        for x in lie_ju:
            self._put(biao, f'{x}142', sum((Decimal(z[3]) for z in self.zichan), ZERO))
        self._put(biao, 'AB142', Decimal(2100) * 12)

    # ---------- 现金流（先算：供资负货币资金与分录使用）----------
    def _xianjin(self):
        tan_nian = self.tan_yue_tan * len(self.huo_yue)   # 随生效月数（实时经营 6 个月）
        x = {
            # 含税口径：销项计入销售收现、进项计入采购付现（增值税已入分录）
            # 收现 = 不含税收入、付现 = 不含税成本（货款当期结清，应收/存货不挂账）
            'shou_xian': (self.nian_shouru['收入非主控'] + self.nian_shouru['收入主控']
                          + self.nian_xiaoxiang),
            'fan_huan': Decimal('20000.00'),
            'qi_ta_shou': Decimal('15000.00'),
            'gou_mai': (self.nian_chengben['收入非主控'] + self.nian_chengben['收入主控']
                        + self.nian_jinxiang),
            'zhi_gong': self.renyuan_nian,
            'shui_fei': self.nian_shui + self.nian_zeng,          # 附加税费+印花 + 增值税
            'qi_ta_fu': max(self.san_fei_nian - self.renyuan_nian - tan_nian,
                            Decimal('1000.00')),
            'shou_hui': Decimal('30000.00'), 'shou_yi': Decimal('18000.00'),
            'chu_zhi': Decimal('12000.00'), 'chu_zhi_zi': Decimal('8000.00'),
            'shou_qi_ta': Decimal('6000.00'),
            'gou_jian': Decimal('180000.00'), 'tou_zi_fu': Decimal('120000.00'),
            'qu_de_zi': Decimal('25000.00'), 'fu_qi_ta': Decimal('12000.00'),
            'xi_shou': Decimal('50000.00'), 'jie_kuan': Decimal('200000.00'),
            'chou_qi_ta': Decimal('10000.00'),
            'chang_huan': Decimal('150000.00'), 'gu_li': Decimal('60000.00'),
            'chou_fu_qi_ta': Decimal('8000.00'),
            'hui_lv': ZERO,
        }
        # 现金流常量按实际覆盖月数折算（预算基础 12 个月＝原值；实时经营 6 个月＝对半）
        qi = Decimal(len(self.huo_yue)) / Decimal('12')
        for k in ('fan_huan', 'qi_ta_shou', 'shou_hui', 'shou_yi', 'chu_zhi', 'chu_zhi_zi',
                  'shou_qi_ta', 'gou_jian', 'tou_zi_fu', 'qu_de_zi', 'fu_qi_ta', 'xi_shou',
                  'jie_kuan', 'chou_qi_ta', 'chang_huan', 'gu_li', 'chou_fu_qi_ta'):
            if x[k]:
                x[k] = self._safe(rd(x[k] * qi))                     # 期间折算 + 黑名单避让
        x['qi_chu'] = self._safe(Decimal('1200000.00'))
        self.xian = self._xian_lie(x)
        if self.xian['qi_mo'] < 0:
            raise ValueError('期末现金为负：请更换种子')
        for k, v in self.xian.items():                               # 派生值避让自检
            if ming_zhong(v):
                raise ValueError(f'现金流量表 {k} 命中黑名单：{v}（请更换种子）')
        # 上期（比较期）：取数项按 0.86 缩放后重算；期末恰好落回本期期初
        shang = {k: (rd(self.xian[k] * Decimal('0.86')) if self.xian[k] else ZERO)
                 for k in XIAN_SHU_RU}
        shang['hui_lv'] = ZERO
        shang['qi_chu'] = ZERO
        shang = self._xian_lie(shang)
        shang['qi_chu'] = self.xian['qi_chu'] - shang['jing_zeng']
        shang = self._xian_lie(shang)
        if shang['qi_chu'] <= 0:
            raise ValueError('上期期初现金为负：请更换种子')
        self.xian_shang = shang

    def _xian_lie(self, x):
        """现金流一列：由取数项算小计/净额/期末。"""
        x = dict(x)
        x['jing_liu_ru'] = x['shou_xian'] + x['fan_huan'] + x['qi_ta_shou']
        x['jing_liu_chu'] = x['gou_mai'] + x['zhi_gong'] + x['shui_fei'] + x['qi_ta_fu']
        x['jing_jing'] = x['jing_liu_ru'] - x['jing_liu_chu']
        x['tou_liu_ru'] = (x['shou_hui'] + x['shou_yi'] + x['chu_zhi'] + x['chu_zhi_zi']
                           + x['shou_qi_ta'])
        x['tou_liu_chu'] = x['gou_jian'] + x['tou_zi_fu'] + x['qu_de_zi'] + x['fu_qi_ta']
        x['tou_jing'] = x['tou_liu_ru'] - x['tou_liu_chu']
        x['chou_liu_ru'] = x['xi_shou'] + x['jie_kuan'] + x['chou_qi_ta']
        x['chou_liu_chu'] = x['chang_huan'] + x['gu_li'] + x['chou_fu_qi_ta']
        x['chou_jing'] = x['chou_liu_ru'] - x['chou_liu_chu']
        x['jing_zeng'] = x['jing_jing'] + x['tou_jing'] + x['chou_jing'] + x['hui_lv']
        x['qi_mo'] = x['qi_chu'] + x['jing_zeng']
        return x

    # ---------- 利润表（财会2019-6号版式：B=本期金额 C=上期金额）----------
    def _lirun(self):
        biao = '利润表'
        gu = Decimal('1000000')
        shouru = self.nian_shouru['收入非主控'] + self.nian_shouru['收入主控']
        chengben = self.nian_chengben['收入非主控'] + self.nian_chengben['收入主控']
        xiaoshou = self.fei_yue['销售费用']['he34']
        guanli = self.fei_yue['管理费用']['he34']
        lixi_fei = sum((self.biao[s][f'{m}30'] for s in FEI_BIAO for m in YUE_LIE), ZERO)
        lixi_shou = sum((self.biao[s][f'{m}29'] for s in FEI_BIAO for m in YUE_LIE), ZERO)
        shouxufei = sum((self.biao[s][f'{m}28'] for s in FEI_BIAO for m in YUE_LIE), ZERO)

        # 余额驱动的口径：用资负明细的期末余额当驱动（演示假设，逐行注明）
        zc = {r: Decimal(v[1]) for r, v in ZIFU_ZUO.items()}
        fz = {r: Decimal(v[1]) for r, v in ZIFU_YOU.items()}
        touzi_shouyi_ji = zc[24] + zc[25]                            # 长期股权投资+其他权益工具投资
        # 期间折算：余额×年率 的口径要按实际覆盖月数折（实时经营=6/12）
        qi = Decimal(len(self.huo_yue)) / Decimal('12')

        def qu_shu(k):
            """输入层（k=1 本期；k<1 比较期按比例缩放）。

            口径（能推的都推，确实没业务的才留 0）：
              研发费用         = 人员费用 × 6%
              其他收益         = 递延收益余额 × 20%（递延收益摊销）
              投资收益         = (长期股权投资+其他权益工具投资) × 4%
              摊余成本终止确认 = 债权投资 × 0.5%
              公允价值变动收益 = 交易性金融资产 × 1.5%
              信用减值损失     = −应收账款 × 1%
              资产减值损失     = −存货 × 2%
              资产处置收益     = 固定资产 × 0.3%
              其他综合收益     = 其他权益工具投资 × 3% + 其他债权投资 × 2%
              利息费用/利息收入 = 三费表「利息支出」「利息收入」行（九表带出）
              净敞口套期收益 / 终止经营净利润 / 其余 OCI 明细 = 0（无此类业务）
            """
            return {
                5: rd(shouru * k),                                   # 营业收入
                6: rd(chengben * k),                                 # 营业成本
                7: rd(self.nian_shui * k),                           # 税金及附加
                8: rd(xiaoshou * k),                                 # 销售费用
                9: rd(guanli * k),                                   # 管理费用
                10: rd(self.renyuan_nian * Decimal('0.06') * k),     # 研发费用
                11: rd((lixi_fei - lixi_shou + shouxufei) * k),      # 财务费用
                12: rd(lixi_fei * k),                                # 其中：利息费用
                13: rd(lixi_shou * k),                               # 利息收入
                14: rd(Decimal('20000.00') * qi * k),                # 其他收益（收到的税费返还，按期间折算）
                15: rd(Decimal('18000.00') * qi * k),                # 投资收益（同口径）
                17: rd(zc[21] * Decimal('0.005') * qi * k),          # 摊余成本终止确认收益
                18: ZERO,                                            # 净敞口套期收益（无套期业务）
                19: rd(zc[7] * Decimal('0.015') * qi * k),           # 公允价值变动收益
                20: -rd(zc[10] * Decimal('0.01') * qi * k),          # 信用减值损失（损失为负）
                21: -rd(zc[14] * Decimal('0.02') * qi * k),          # 资产减值损失（损失为负）
                22: rd(zc[28] * Decimal('0.003') * qi * k),          # 资产处置收益
                24: rd(shouru * Decimal('0.0004') * k),              # 营业外收入
                25: rd(shouru * Decimal('0.0002') * k),              # 营业外支出
                30: ZERO,                                            # 终止经营净利润（无此类业务）
                33: ZERO, 34: ZERO, 36: ZERO,                        # 其余 OCI 明细：无此类业务
                35: rd(zc[25] * Decimal('0.03') * qi * k),           # 其他权益工具投资公允价值变动
                38: ZERO, 40: ZERO, 41: ZERO, 42: ZERO, 43: ZERO,
                39: rd(zc[22] * Decimal('0.02') * qi * k),           # 其他债权投资公允价值变动
            }

        def suan(z):
            """补齐派生行（营业利润/利润总额/所得税/净利润/综合收益/每股收益）。"""
            z = dict(z)
            z[16] = rd(z[15] / 2)                                    # 其中：对联营合营
            z[23] = (z[5] - z[6] - z[7] - z[8] - z[9] - z[10] - z[11]
                     + z[14] + z[15] + z[17] + z[18] + z[19] + z[20] + z[21] + z[22])
            z[26] = z[23] + z[24] - z[25]                            # 利润总额
            z[27] = max(rd(z[26] * Decimal('0.25')), ZERO)           # 所得税费用
            z[28] = z[26] - z[27]                                    # 净利润
            z[29] = z[28]                                            # 持续经营净利润
            z[32] = sum((z[r] for r in (33, 34, 35, 36)), ZERO)
            z[37] = sum((z[r] for r in (38, 39, 40, 41, 42, 43)), ZERO)
            z[31] = z[32] + z[37]                                    # 其他综合收益税后净额
            z[44] = z[28] + z[31]                                    # 综合收益总额
            z[46] = rd4(z[28] / gu)                                  # 基本每股收益
            z[47] = rd4(z[28] * Decimal('0.98') / gu)                # 稀释每股收益
            return z

        ben = suan(qu_shu(Decimal('1')))
        shang = suan(qu_shu(Decimal('0.86')))
        for r in range(5, 48):
            if r == 45:                                              # 分区标题行不填数
                continue
            self._put(biao, f'B{r}', ben[r])
            self._put(biao, f'C{r}', shang[r])
        self.nian_jingli = ben[28]
        self.nian_suodeshui = ben[27]
        self.qita_zonghe_shouyi = ben[31]
        # 利润表各行 → 月度金额（供分录逐行入账，保证账面利润 = 报表净利润）
        def _yue_hua(v):
            return self._fen_yue(v, [1] * 12)

        self.pl_yue = {
            'yanfa': _yue_hua(ben[10]),          # 研发费用
            'huai': _yue_hua(abs(ben[20])),      # 信用减值损失
            'jzhi': _yue_hua(abs(ben[21])),      # 资产减值损失
            'gyjz': _yue_hua(ben[19]),           # 公允价值变动收益
            'czhi': _yue_hua(ben[22]),           # 资产处置收益
            'ywsr': _yue_hua(ben[24]),           # 营业外收入
            'ywzc': _yue_hua(ben[25]),           # 营业外支出
            'caiwu': _yue_hua(ben[11]),          # 财务费用
            'tanyu': _yue_hua(ben[17]),          # 摊余成本终止确认收益
            'suo_ji': _yue_hua(ben[27]),         # 所得税费用
        }
        # 分录「计提坏账」用的月额（与信用减值损失口径一致）
        self.jianzhi_yue = rd(abs(ben[20]) / Decimal(len(self.huo_yue)))

    # ---------- 资产负债表（财会2019-6号版式：左右两栏，期末/上年年末）----------
    def _zifu(self):
        def zuo_ce(ge, xian_jin, tiao=ZERO):
            d = dict(ge)
            d[6] = xian_jin                                    # 货币资金
            d[13] = d.get(13, Decimal('52000')) + tiao         # 其他应收款（兜底）
            d[19] = sum((d[r] for r in range(6, 19)), ZERO)    # 流动资产合计
            d[39] = sum((d[r] for r in range(21, 39)), ZERO)   # 非流动资产合计
            d[40] = d[19] + d[39]                              # 资产总计
            return d

        def you_ce(ge, tiao=ZERO):
            d = dict(ge)
            d[15] = d.get(15, ZERO) + tiao                     # 其他应付款（兜底）
            d[19] = sum((d[r] for r in range(6, 19)), ZERO)    # 流动负债合计
            d[31] = sum((d[r] for r in range(21, 31)), ZERO)   # 非流动负债合计
            d[32] = d[19] + d[31]                              # 负债合计
            d[44] = sum((d[r] for r in (34, 35, 38, 39, 40, 41, 42, 43)), ZERO)
            d[45] = d[32] + d[44]                              # 负债和所有者权益总计
            return d

        chu_zuo = {r: self._safe(v[0]) for r, v in ZIFU_ZUO.items()}
        mo_zuo = {r: self._safe(v[1]) for r, v in ZIFU_ZUO.items()}
        chu_you = {r: self._safe(v[0]) for r, v in ZIFU_YOU.items()}
        mo_you = {r: self._safe(v[1]) for r, v in ZIFU_YOU.items()}
        ti = rd(self.nian_jingli * Decimal('0.10'))            # 提取盈余公积 10%
        # 应交税费：增值税月末已缴清；期末余额 = 计提未缴的所得税（与分录科目余额一致）
        chu_you.update({14: self._safe(Decimal('45000.00'))})
        mo_you.update({14: rd(rd(self.nian_suodeshui / Decimal(len(self.huo_yue)))
                              * len(self.huo_yue))})       # 与分录"计提所得税"逐月数一致
        chu_you.update({40: Decimal('25000'), 42: Decimal('80000'), 43: Decimal('300000')})
        mo_you.update({40: chu_you[40] + self.qita_zonghe_shouyi,   # 其他综合收益随本期 OCI 变动
                       42: chu_you[42] + ti,
                       43: chu_you[43] + self.nian_jingli - ti - self.xian['gu_li']})
        shang_nian = zuo_ce(chu_zuo, self.xian['qi_chu'])
        shang_nian_y = you_ce(chu_you)
        qi_mo = zuo_ce(mo_zuo, self.xian['qi_mo'])
        qi_mo_y = you_ce(mo_you)
        for zuo_a, you_a, ming in ((shang_nian, shang_nian_y, '上年年末'),
                                   (qi_mo, qi_mo_y, '期末')):
            cha = zuo_a[40] - you_a[45]
            if cha > 0:
                you_a[15] = you_a[15] + cha                    # 负债侧兜底（其他应付款）
            elif cha < 0:
                zuo_a[13] = zuo_a[13] - cha                    # 资产侧兜底（其他应收款）
            zuo_b = zuo_ce(zuo_a, zuo_a[6])
            you_b = you_ce(you_a)
            # 兜底行与两侧合计一起避让黑名单：两侧同步 +0.37，平衡不破
            for _ in range(200):
                ht = [zuo_b[r] for r in (13, 19, 39, 40)]
                ht += [you_b[r] for r in (15, 19, 31, 32, 44, 45)]
                if not any(ming_zhong(v) for v in ht if v):
                    break
                zuo_a[13] = zuo_a[13] + Decimal('0.37')
                you_a[15] = you_a[15] + Decimal('0.37')
                zuo_b = zuo_ce(zuo_a, zuo_a[6])
                you_b = you_ce(you_a)
            else:
                raise ValueError(f'资产负债表{ming}无法避开黑名单')
            if zuo_b[40] != you_b[45]:
                raise AssertionError(f'资产负债表{ming}不平：{zuo_b[40]} != {you_b[45]}')
            if ming == '上年年末':
                shang_nian, shang_nian_y = zuo_b, you_b
            else:
                qi_mo, qi_mo_y = zuo_b, you_b
        biao = '资产负债表'
        for r in range(5, 46):
            if r in shang_nian:                                # 左栏：B=期末余额 C=上年年末余额
                self._put(biao, f'B{r}', qi_mo[r])
                self._put(biao, f'C{r}', shang_nian[r])
            if r in shang_nian_y:                              # 右栏：E=期末余额 F=上年年末余额
                self._put(biao, f'E{r}', qi_mo_y[r])
                self._put(biao, f'F{r}', shang_nian_y[r])

    # ---------- 分录全账（124-460 行填满；借贷平衡；现金流对照）----------
    def _fenlu(self):
        biao = '分录'
        x = self.xian
        quan_shou = [self.yue_shouru[m] for m in YUE_LIE]
        quan_fei = [sum((self.biao[s][f'{m}34'] for s in FEI_BIAO), ZERO) for m in YUE_LIE]
        quan_shui = [self.yue_shui[m] for m in YUE_LIE]
        yue = {
            # 不含税口径：增值税由「销项税额/进项税额/缴纳增值税」三笔单独入账
            'shou': self._fen_yue(x['shou_xian'] - self.nian_xiaoxiang, quan_shou),
            'gou': self._fen_yue(x['gou_mai'] - self.nian_jinxiang, quan_fei),
            'gong': self._fen_yue(x['zhi_gong'], quan_fei),
            'shui': self._fen_yue(self.nian_shui, quan_shui),
            'qi': self._fen_yue(x['qi_ta_fu'], quan_fei),
            'jian': self._fen_yue(x['gou_jian'], [1] * 12),
            'tou': self._fen_yue(x['tou_zi_fu'], [1] * 12),
            'jie': self._fen_yue(x['jie_kuan'], [1] * 12),
            'chang': self._fen_yue(x['chang_huan'], [1] * 12),
            'gu': self._fen_yue(x['gu_li'], [1] * 12),
            # 其余现金流行的月度分摊（均摊）
            'fan_huan': self._fen_yue(x['fan_huan'], [1] * 12),
            'qi_ta_shou': self._fen_yue(x['qi_ta_shou'], [1] * 12),
            'shou_hui': self._fen_yue(x['shou_hui'], [1] * 12),
            'shou_yi': self._fen_yue(x['shou_yi'], [1] * 12),
            'chu_zhi': self._fen_yue(x['chu_zhi'], [1] * 12),
            'chu_zhi_zi': self._fen_yue(x['chu_zhi_zi'], [1] * 12),
            'shou_qi_ta': self._fen_yue(x['shou_qi_ta'], [1] * 12),
            'qu_de_zi': self._fen_yue(x['qu_de_zi'], [1] * 12),
            'fu_qi_ta': self._fen_yue(x['fu_qi_ta'], [1] * 12),
            'xi_shou': self._fen_yue(x['xi_shou'], [1] * 12),
            'chou_qi_ta': self._fen_yue(x['chou_qi_ta'], [1] * 12),
            'chou_fu_qi_ta': self._fen_yue(x['chou_fu_qi_ta'], [1] * 12),
        }
        # 分录排布：行 124-540 填满（增值税入账后每月 25 笔现金分录）——
        # 预算基础 12 个月（每月 34 笔，末月 43 笔）；实时经营 6 个月（末月 72 笔）
        # 每月笔数 = 现金 25 + 非现金 18 = 43（不再用占位分录凑数）
        if self.leibie == '实时经营':
            yue_chi, shu_chi = list(YUE_LIE[:6]), [43] * 6
        else:
            yue_chi, shu_chi = list(YUE_LIE), [43] * 12
        hang = 124
        for i, m in enumerate(yue_chi):
            e = {
                'shou': yue['shou'][m], 'gou': yue['gou'][m], 'gong': yue['gong'][m],
                'shui': yue['shui'][m], 'qi': yue['qi'][m], 'jian': yue['jian'][m],
                'tou': yue['tou'][m], 'jie': yue['jie'][m], 'chang': yue['chang'][m],
                'gu': yue['gu'][m],
                'fan_huan': yue['fan_huan'][m], 'qi_ta_shou': yue['qi_ta_shou'][m],
                'shou_hui': yue['shou_hui'][m], 'shou_yi': yue['shou_yi'][m],
                'chu_zhi': yue['chu_zhi'][m], 'chu_zhi_zi': yue['chu_zhi_zi'][m],
                'shou_qi_ta': yue['shou_qi_ta'][m], 'qu_de_zi': yue['qu_de_zi'][m],
                'fu_qi_ta': yue['fu_qi_ta'][m], 'xi_shou': yue['xi_shou'][m],
                'chou_qi_ta': yue['chou_qi_ta'][m], 'chou_fu_qi_ta': yue['chou_fu_qi_ta'][m],
                'tan': self.tan_yue_tan,
                'suo': rd(self.nian_jingli),                      # 年末结转用全年净利
                'suo_ji': rd(self.pl_yue['suo_ji'][m]),
                'fang': rd(self.biao['管理费用'][f'{m}11']),
                'she': rd(yue['gong'][m] / 3),
                'li': rd(self.biao['管理费用'][f'{m}30']),
                'huai': rd(self.pl_yue['huai'][m]),
                'jzhi': rd(self.pl_yue['jzhi'][m]),
                'gyjz': rd(self.pl_yue['gyjz'][m]),
                'czhi': rd(self.pl_yue['czhi'][m]),
                'ywsr': rd(self.pl_yue['ywsr'][m]),
                'ywzc': rd(self.pl_yue['ywzc'][m]),
                'yanfa': rd(self.pl_yue['yanfa'][m]),
                'ying': rd(self.nian_jingli * Decimal('0.1') / 12),
                'yu': Decimal('2000.00'), 'ling': Decimal('8000.00'), 'fu': Decimal('5000.00'),
                'one': Decimal('1.13'),                                  # 往来余量（极小额，仅占位）
                # 月末结转用"利润表口径"的当月数（不是付现口径）
                'shouru_yue': rd(self.yue_shouru[m]),
                'chengben_yue': rd(self.yue_chengben[m]),
                'xiao_xiang': rd(self.yue_xiaoxiang[m]),
                'jin_xiang': rd(self.yue_jinxiang[m]),
                'zeng_jiao': rd(self.yue_zeng[m]),
                # 期间费用付现部分（三费合计 − 折旧，折旧单列）
                'feiyong_yue': rd(quan_fei[YUE_LIE.index(m)] - self.tan_yue_tan),
                'caiwu': rd(self.pl_yue['caiwu'][m]),
                'tanyu': rd(self.pl_yue['tanyu'][m]),
                'ben_nian': rd(self.nian_shouru['收入非主控'] + self.nian_shouru['收入主控']
                               - self.nian_chengben['收入非主控']
                               - self.nian_chengben['收入主控'] - self.san_fei_nian),
            }
            xu = shu_chi[i]
            xu_fei = xu - len(FENLU_XIAN)                            # 本月非现金笔数
            fei_lie = [(z, j, d, k, None) for (z, j, d, k) in FENLU_FEI]
            while len(fei_lie) < xu_fei:                             # 余量补往来（不碰损益）
                fei_lie.append(('往来结算（演示）', '其他应收款', '其他应付款', 'one', None))
            lie = ([(z, j, d, k, u) for (z, j, d, k, u) in FENLU_XIAN]
                   + fei_lie[:xu_fei])
            for (zhaiyao, jie, dai, k, dui) in lie:
                if isinstance(k, tuple):                             # 取某表某行当月值
                    jin = rd(self.biao[k[1]][f'{m}{k[2]}'])
                else:
                    jin = rd(e[k])
                self._put(biao, f'O{hang}', YUEFEN[YUE_LIE.index(m)])
                self._put(biao, f'P{hang}', zhaiyao)
                self._put(biao, f'Q{hang}', jie)
                self._put(biao, f'R{hang}', dai)
                self._put(biao, f'S{hang}', jin)
                self._put(biao, f'T{hang}', jin)
                if dui is not None:
                    self._put(biao, f'U{hang}', Decimal(dui))
                self._put(biao, f'V{hang}', f'JE-{hang - 122:03d}')   # 平移后行号 = 原行号-122
                hang += 1
        # ---- 年末统一结平损益类科目（按分录账面余额结转到本年利润）----
        def yu_e(ke):
            """某科目截至当前行的账面余额（借 − 贷）。"""
            j = sum((self.biao[biao][f'S{r}'] for r in range(124, hang)
                     if self.biao[biao].get(f'Q{r}') == ke), ZERO)
            d = sum((self.biao[biao][f'T{r}'] for r in range(124, hang)
                     if self.biao[biao].get(f'R{r}') == ke), ZERO)
            return j - d

        def xie(zhaiyao, jie, dai, jin):
            nonlocal hang
            self._put(biao, f'O{hang}', YUEFEN[-1])
            self._put(biao, f'P{hang}', zhaiyao)
            self._put(biao, f'Q{hang}', jie)
            self._put(biao, f'R{hang}', dai)
            self._put(biao, f'S{hang}', jin)
            self._put(biao, f'T{hang}', jin)
            self._put(biao, f'V{hang}', f'JE-{hang - 122:03d}')
            hang += 1

        for ke in ('税金及附加', '所得税费用', '折旧及摊销', '研发费用',
                   '信用减值损失', '资产减值损失', '管理费用', '财务费用', '销售费用',
                   '费用（演示合并）', '公允价值变动收益', '资产处置收益',
                   '营业外收入', '营业外支出', '投资收益', '其他收益',
                   '摊余成本终止确认收益'):
            v = yu_e(ke)
            if v > 0:
                xie(f'结转{ke}（演示）', '本年利润', ke, v)
            elif v < 0:
                xie(f'结转{ke}（演示）', ke, '本年利润', -v)
        v = yu_e('本年利润')                                  # 本年利润余额 → 利润分配
        if v < 0:
            xie('结转本年利润（演示）', '本年利润', '利润分配', -v)
        elif v > 0:
            xie('结转本年利润（演示）', '利润分配', '本年利润', v)
        jie_he = sum((self.biao[biao][f'S{r}'] for r in range(124, hang)), ZERO)
        dai_he = sum((self.biao[biao][f'T{r}'] for r in range(124, hang)), ZERO)
        self.fenlu_heji = (jie_he, dai_he)
        self.fenlu_mo = hang - 1                       # 最后一条分录行（模型坐标）
        self.duizhao_he = {}
        for r in range(124, hang):
            dui = self.biao[biao].get(f'U{r}')
            if dui is None:
                continue
            k = int(dui)
            self.duizhao_he[k] = self.duizhao_he.get(k, ZERO) + self.biao[biao][f'S{r}']

    # ---------- 三表现金流 → 现金流量表 ----------
    def xianjin_biao(self):
        """现金流量表数值（财会2019-6号版式：B=本期金额、C=上期金额）。"""
        biao = '现金流量表'
        for lie, shu_ju in (('B', self.xian), ('C', self.xian_shang)):
            for k, hang in XJL_HANG.items():
                self._put(biao, f'{lie}{hang}', shu_ju[k])
