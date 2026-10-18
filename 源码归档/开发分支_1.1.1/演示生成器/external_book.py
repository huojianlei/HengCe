# -*- coding: utf-8 -*-
"""行业对标与经营变更演示文件编排：固定模板 + 确定性演示行。

复用 1.0.5 的 external_generate.populate（只读引用）完成 XML 值写入；
批次元数据与演示行内容本模块自定义，全部标注演示口径、可复现种子。
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
ALGO = r'D:\AppProject\开发分支_1.0.5\algo'
if ALGO not in sys.path:
    sys.path.insert(0, ALGO)
from external_generate import populate  # noqa: E402

from demo_model import number_hash, load_blacklist  # noqa: E402

TEMPLATES = Path(r'D:\AppProject\开发分支_1.0.5\desktop\templates')

# 行业对标五指标参考值（% 口径，构造参考值）
INDUSTRY_ROWS = [
    ('GROSS_MARGIN', Decimal('38.62')),
    ('PROCUREMENT_COST_CHANGE', Decimal('2.41')),
    ('CAPACITY_UTILIZATION', Decimal('76.35')),
    ('EXPENSE_THRESHOLD', Decimal('24.18')),
    ('RAW_MATERIAL_INDEX', Decimal('101.34')),
]


def _col(index):
    out = ''
    while index:
        index, n = divmod(index - 1, 26)
        out = chr(65 + n) + out
    return out


def _safe(value, blacklist, quantum=Decimal('0.01')):
    v = Decimal(value).quantize(quantum)
    for _ in range(200):
        if v == 0 or number_hash(v) not in blacklist:
            return v
        v = (v + Decimal('0.37')).quantize(quantum)
    raise ValueError('构造值无法避开数值黑名单')


def _batch_info(entity_code, entity, scenario_code, scenario, year, grain, seed, note, kind):
    """批次信息 14 键值 + B1 中性版本串（主体企业化：不含'衡策'字样）。"""
    return {
        'B1': f'标准/{kind}/1.0.5',  # v1.2：中性模板版本串（fork 导入器双轨放行）
        'B2': entity_code, 'B3': entity, 'B4': scenario_code, 'B5': scenario,
        'B6': str(year), 'B7': grain, 'B8': '演示占位-v1', 'B9': '模拟权责发生制',
        'B10': f'{year}-01', 'B11': f'{year}-06', 'B12': '无', 'B13': '无',
        'B14': '占位', 'B15': note,
    }


def _row(values, skip_cols=()):
    """把一行值元组转成 {列字母: 值}，跳过模板已预置的标签列与空值。"""
    out = {}
    for c, v in enumerate(values, 1):
        if c in skip_cols or v is None or v == '':
            continue
        out[f'{_col(c)}2'] = v
    return out


def generate_industry(seed, entity, scenario, entity_code, scenario_code,
                      year=2027, grain='月度'):
    blacklist = load_blacklist(TEMPLATES / '数值黑名单哈希.json')
    raw = (TEMPLATES / '行业对标输入模板.xlsx').read_bytes()
    period = f'{year}-06' if grain == '月度' else f'{year}-Q2'
    day = f'{year}-06-30'
    rows = {}
    for i, (code, value) in enumerate(INDUSTRY_ROWS, 2):
        safe_v = _safe(value, blacklist)
        values = (code, None, period, safe_v, '%', '构造参考值',
                  '影视投资示意（非统计总体）', '无真实样本', '演示参数；不得用作真实阈值',
                  '本地演示生成器', '本地构造，无外部真实出处', day, '仅用于流程演示',
                  entity_code, scenario_code, '是', day, f'固定种子 {seed} 模拟')
        for c, v in enumerate(values, 1):
            if c in (1, 2) or v is None:
                continue
            rows[f'{_col(c)}{i}'] = v
    changes = {
        '批次信息': _batch_info(entity_code, entity, scenario_code, scenario, year, grain,
                              seed, f'固定种子 {seed}；构造参考值，不代表真实行业数据',
                              '行业对标'),
        '基准指标': rows,
    }
    return populate(raw, changes)


def generate_changes_file(seed, entity, scenario, entity_code, scenario_code,
                          year=2027, grain='月度'):
    blacklist = load_blacklist(TEMPLATES / '数值黑名单哈希.json')
    raw = (TEMPLATES / '经营变更输入模板.xlsx').read_bytes()
    v1 = _safe(Decimal('9800.00'), blacklist)
    v2 = _safe(Decimal('8000.00'), blacklist)
    event1 = ('EVT-2027-001', '采购条件变化', f'{year}-03-01', f'{year}-03', '',
              '待审批', '本地演示生成器', f'{year}-03-01',
              '模拟授权内容采购单价上调，等待人工审批', '', '', '', '', '待审批', '')
    event2 = ('EVT-2027-002', '房租补充协议', f'{year}-02-15', f'{year}-03', '',
              '已批准', '本地演示生成器', f'{year}-02-20',
              '模拟新增园区办公场地租金补充协议', '王经理', f'{year}-02-16',
              '总经理办公会', f'{year}-02-20', '已批准', '演示协议 Demo-2027-018')
    impact1 = ('EVT-2027-001', 'EXP1.004', f'{year}-04', '增加', v1, '元', '否',
               f'固定种子 {seed} 模拟')
    impact2 = ('EVT-2027-002', 'EXP2.011', f'{year}-04', '增加', v2, '元', '否',
               f'固定种子 {seed} 模拟')
    changes = {
        '批次信息': _batch_info(entity_code, entity, scenario_code, scenario, year, grain,
                              seed, f'固定种子 {seed}；演示事件，不代表真实变更',
                              '经营变更'),
        '事件台账': {f'{_col(c)}2': v for c, v in enumerate(event1, 1) if v != ''} |
                   {f'{_col(c)}3': v for c, v in enumerate(event2, 1) if v != ''},
        '科目影响': {f'{_col(c)}2': v for c, v in enumerate(impact1, 1) if v != ''} |
                   {f'{_col(c)}3': v for c, v in enumerate(impact2, 1) if v != ''},
    }
    return populate(raw, changes)
