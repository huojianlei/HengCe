# -*- coding: utf-8 -*-
"""外部两册数值模型：行业对标 / 经营变更（零公式、纯数值、名称走替换接口）。

口径（演示假设）：批次信息 15 键 + 基准指标 5 行 16 列 / 事件台账 2 行 15 列 /
科目影响 2 行 8 列，全部填数（无空格）；数值逐个避让老师原件数值黑名单。
"""
import random
from decimal import Decimal

from shuju import FEN, ming_zhong

#: 行业对标五指标：(编码, 名称, 参考值, 单位)
HANGYE_ZB = (
    ('GROSS_MARGIN', '行业毛利率', '38.62', '%'),
    ('PROCUREMENT_COST_CHANGE', '采购成本变动率', '2.41', '%'),
    ('CAPACITY_UTILIZATION', '产能利用率', '76.35', '%'),
    ('EXPENSE_THRESHOLD', '费用阈值', '24.18', '%'),
    ('RAW_MATERIAL_INDEX', '原材料指数', '101.34', '%'),
)

#: 基准指标数据列 C..R（统计周期/参考值/单位/…/备注）
ZB_LIE = ('C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R')

#: 事件台账两行（A..O 十五字段，全部有值）
SHI_JIAN = (
    ('EVT-2027-001', '采购条件变化', '2027-03-01', '2027-03', '2027-03', '待审批',
     '总经理办公会', '2027-03-01', '模拟授权内容采购单价上调，等待人工审批',
     '王经理', '2027-02-28', '李总监', '2027-03-02', '待审批', '演示依据 Demo-2027-016'),
    ('EVT-2027-002', '房租补充协议', '2027-02-15', '2027-03', '2027-12', '已批准',
     '总经理办公会', '2027-02-20', '模拟新增园区办公场地租金补充协议',
     '王经理', '2027-02-16', '李总监', '2027-02-18', '已批准', '演示协议 Demo-2027-018'),
)

#: 科目影响两行（A..H 八字段）
KE_MU = (
    # 影响期间必须落在事件生效区间内（EVT-001 生效 2027-03..2027-03）
    ('EVT-2027-001', 'EXP1.004', '2027-03', '增加', '9800.00', '元', '否', ''),
    ('EVT-2027-002', 'EXP2.011', '2027-04', '增加', '8000.00', '元', '否', ''),
)


def _bi_mian(v, bu=Decimal('0.37')):
    """小数避让黑名单。"""
    v = Decimal(v).quantize(FEN)
    for _ in range(200):
        if not ming_zhong(v):
            return v
        v = (v + bu).quantize(FEN)
    raise ValueError(f'外部册数值无法避开黑名单：{v}')


def _pi_ci(seed, tihuan, zhong):
    """批次信息 B1..B15（B1 用中性版本串，不含任何真名）。"""
    return {
        'B1': f'标准/{zhong}/1.0.5',
        'B2': tihuan['主体编码'], 'B3': tihuan['主体名'], 'B4': tihuan['情景编码'],
        'B5': tihuan['情景'], 'B6': tihuan['年度'], 'B7': '月度',
        'B8': '演示占位-v1', 'B9': '模拟权责发生制', 'B10': '2027-01',
        'B11': '2027-06', 'B12': '无', 'B13': '无', 'B14': '占位',
        'B15': f'固定种子 {seed}；演示数据，不代表真实情况',
    }


def hangye_biao(seed, tihuan):
    """行业对标册：{表名: {格位: 值}}。"""
    rng = random.Random(f'{seed}|行业对标|v2')
    zhi = {'批次信息': _pi_ci(seed, tihuan, '行业对标'), '基准指标': {}}
    for i, (_, _, can, dan) in enumerate(HANGYE_ZB, 2):
        h = i
        jia = _bi_mian(Decimal(can) + Decimal(rng.randrange(-90, 91)) / 100)   # 参考值浮动
        lie_zhi = (f'{tihuan["年度"]}-06', jia, dan, '构造参考值',
                   '影视投资示意（非统计总体）', '无真实样本',
                   '演示参数；不得用作真实阈值', '本地演示生成器',
                   '本地构造，无外部真实出处', f'{tihuan["年度"]}-06-30', '仅用于流程演示',
                   tihuan['主体编码'], tihuan['情景编码'], '是',
                   f'{tihuan["年度"]}-06-30', f'固定种子 {seed} 模拟')
        for x, v in zip(ZB_LIE, lie_zhi):
            zhi['基准指标'][f'{x}{h}'] = v
    return zhi


def biangeng_biao(seed, tihuan):
    """经营变更册：{表名: {格位: 值}}。"""
    zhi = {'批次信息': _pi_ci(seed, tihuan, '经营变更'), '事件台账': {}, '科目影响': {}}
    for i, hang in enumerate(SHI_JIAN, 2):
        for x, v in zip('ABCDEFGHIJKLMNO', hang):
            zhi['事件台账'][f'{x}{i}'] = v
    for i, hang in enumerate(KE_MU, 2):
        for x, v in zip('ABCDEFGH', hang):
            zhi['科目影响'][f'{x}{i}'] = _bi_mian(v) if x == 'E' else v
        zhi['科目影响'][f'H{i}'] = f'固定种子 {seed} 模拟'
    return zhi
