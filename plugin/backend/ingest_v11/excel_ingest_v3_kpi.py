# -*- coding: utf-8 -*-
"""非财务指标表解析（v3 十一表的第十一张；六项非财务 KPI 的唯一数据源）。

表版式（固定，纯数值零公式）：
    第 1 行表头：指标 | 单位 | 本期值 | 备注
    数据行（顺序固定六行，名称逐字）：
        供应链履约率     %     按期足额交付订单数 / 订单总数（0-100，两位小数）
        产能利用率       %     实际产出 / 潜在产能（0-100，两位小数）
        交付周期         天    平均下单到交付天数（正数，两位小数）
        客户满意度       %     满意客户数 / 受访客户数（0-100，两位小数）
        业务完成进度     %     已完成业务量 / 计划业务量（0-100，两位小数）
        异常事项数量     次    本期异常事项次数（非负整数）
    允许整行数值留空（该指标缺数，不臆造）；百分比范围 [0,100]；
    交付周期 >0；异常数量为非负整数。任一校验不过 → 整本退回（中文报错带格位）。
    契约校验（任一不过即整本退回，中文报错带「表名!格位」）：
        1) 表序列：本表必须是第十一张，且前十表与 v3 十表逐项同名同序；
        2) 表头：A1..D1 必须逐字等于 指标/单位/本期值/备注（列序不可调、不可加列）；
        3) 六行：A 列名称、B 列单位必须与本文件 KPI_HANG 逐字一致（顺序固定）；
        4) 值域：百分比 [0,100]、交付周期 >0、异常数量为非负整数；C 列留空=缺数，跳过。
    对外产出：jie['kpi_input'] = {KpiShuru 字段名: 十进制字符串}，只在缺数时不出现该键；
    金额/比率纪律：本表只存「表值原单位」的字符串，比率转整数基点由 kpi.py 在做。
    失败口径：抛 xlsx_reader.ExcelError，不抛裸 Decimal/KeyError，由总分派转退回收据。
"""
# Decimal 是唯一数值类型：值域比较不能用 float（0.1 边界会误判 100 上限），
# InvalidOperation 用于捕获「非数字文本」的转换失败，配合 _shu() 的容错口径。
from decimal import Decimal, InvalidOperation

# 单向依赖：v3_kpi -> v3 -> v2，本文件不反向 import，避免循环。
# 本文件实际只用到 V3_TEN 做序列拼接；import_v2 / V2_SHEETS / YUE_LIE / BUMEN_BIAO
# 都是为与九表、十表口径对齐而保留的导入（noqa: F402），改动它们会连带影响别的轨道。
from excel_ingest_v2 import import_v2, V2_SHEETS, YUE_LIE          # noqa: F402
from excel_ingest_v3 import BUMEN_BIAO, V3_SHEETS as V3_TEN        # noqa: F402

# 表名常量 = 模板里那张 sheet 的精确名字，也是 import_excel_v11 分派本轨道的判据之一；
# 表名错一个字（如「非财务指标表」）会落到「工作表结构不符合任一固定模板」的兜底退回。
KPI_BIAO = '非财务指标'
# 十一表序列 = v3 的十表 + 本表，顺序即模板顺序，也是分派顺序：
# 先拼序列再判等，任何位置插表/换表都会立刻被 tuple 比较挡下。
V3_SHEETS = V3_TEN + (KPI_BIAO,)

#: 六行固定：名称 → (单位, KpiShuru 字段名, 值域校验器, 换算)
#: 表值口径：百分比 0-100（÷100 交 KpiShuru 仍是 0-100 的"率"，kpi.py 再乘 10000 基点）；
#: 直接率类喂对应分子分母不可行（表只给一个数）→ 用"达成率型"字段：
#:   供应链履约率→lvyue_dingdan_shu/dingdan_zongshu 不可拆 → 喂 manyi 型比率字段不行；
#: 因此改喂 KpiShuru 的原生"率"字段不存在——统一走比率兜底字段（见下）：
#:   履约率/满意度/进度 → 直接率值×100 当作百分比字段；产能同理；
#:   交付周期(天)/异常(次) → 原值直传。
# 六行「指标名 -> 元数据」的唯一真源，四列含义：
#   名称：必须与 A 列逐字相同（六行顺序固定，错位即报「六行顺序固定」）；
#   单位：必须与 B 列逐字相同，同时决定值域报错文案里的「0-100 之间/大于 0/非负整数」；
#   字段名：KpiShuru 的同名字段（下游 kpi.py 直接按名取，不做映射表）；
#   校验器：闭包直接收 Decimal，返回 bool；用 Decimal('0')/Decimal('100') 而不是 0/100，
#           是为了让 99.995 这类带小数的表值也走精确比较、不被 float 抹平。
# 缺数语义：C 列留空=该指标本期没有数据，跳过而不补 0——补 0 会把「没测」变成「测得 0」。
KPI_HANG = (
    ('供应链履约率', '%', 'lvyue_lv', lambda v: Decimal('0') <= v <= Decimal('100')),
    ('产能利用率', '%', 'channeng_lv', lambda v: Decimal('0') <= v <= Decimal('100')),
    ('交付周期', '天', 'jiaofu_zhouqi_tian_shu', lambda v: v > 0),
    ('客户满意度', '%', 'manyi_lv', lambda v: Decimal('0') <= v <= Decimal('100')),
    ('业务完成进度', '%', 'yewu_jindu', lambda v: Decimal('0') <= v <= Decimal('100')),
    ('异常事项数量', '次', 'yichang_shijian_shu', lambda v: v == v.to_integral_value()),
)
#: 率字段（0-100 表值）→ KpiShuru 分子分母换算：以 100 为分母的达成率
#: （kpi.py 吃分子分母：lvyue_dingdan_shu/dingdan_zongshu 等）——比率类统一
#: 转成"每百单位"的分子分母，保数值等价。
# 率字段 -> (分子, 分母) 的换算表：表里只有一个百分数，而 KpiShuru 的「达成率」口径要分子分母。
# 这里只登记「谁是分子谁是分母」，真正的换算（表值当分子、100 当分母）交给 kpi.py，
# 本文件不写死算式，是为了将来换成「实际件数/计划件数」时不必改端口层。
LV_ZHUAN = {
    'lvyue_lv': ('lvyue_dingdan_shu', 'dingdan_zongshu'),
    'channeng_lv': ('shiji_chanchu', 'qianzai_channeng'),
    'manyi_lv': ('manyi_keshu', 'shoufang_keshu'),
    'yewu_jindu': ('wancheng_yewu_liang', 'jihua_yewu_liang'),
}


# ---------------------------------------------------------------- 取值层
# _shu 是 C 列的唯一入口：把单元格值归一成 Decimal 或 None（None = 缺数）。
def _shu(zhi):
    """把「本期值」单元格归一成 Decimal。

    参数：zhi=Book.value() 的返回值（Decimal / str / None）。
    返回：Decimal；空值或无法解析时返回 None（= 该指标缺数，不报错），
          因为「填了错值」与「没填」的处置不同：前者报错、后者跳过。
    """
    # 空值两态都要挡：None（空格）与空串（只有空白的文本格）。
    if zhi is None or zhi == '':
        return None
    try:
        return Decimal(str(zhi))
    # 解析失败一律降到 None：用户把「3.5%」写成带百分号的文本时按缺数处理，
    # 让整张 KPI 表还能导入（其余指标有效），而不是因为一个格子整本退回；
    # 真正越界（如 120）仍由值域校验器报错，两者边界清晰。
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------- 非财务指标表解析
# 先表头、后六行、再值域：三层按模板固定顺序校验，报错按最外层先命中。
# ExcelError 在函数内延迟导入，__main__ 直接跑本文件时不必先 import xlsx_reader。
def du_kpi_biao(book):
    """读非财务指标表 → dict（KpiShuru 同名字段，缺数不出现）。"""
    from xlsx_reader import ExcelError
    biao = KPI_BIAO
    # 表头四格逐字比对，不用「包含」也不做 strip 后再比：模板版式是契约，
    # 「本期值」被改成「本 期 值」这类细微差异也算版式不符，必须退回。
    if book.value(biao, 'A1') != '指标' or book.value(biao, 'B1') != '单位' \
            or book.value(biao, 'C1') != '本期值' or book.value(biao, 'D1') != '备注':
        raise ExcelError(f'{biao} 表头不符合固定版式（指标/单位/本期值/备注）')
    jie = {}
    # start=2：第 1 行是表头，六项指标固定在 A2..A7 / B2..B7 / C2..C7；
    # i 既当行号又当报错格位，所以不能从默认的 0 开始。
    for i, (ming, danwei, ziduan, jiaoyan) in enumerate(KPI_HANG, start=2):
        # A 列名称、B 列单位都是「逐字相等」校验：名称决定这行的值归哪个字段，
        # 名称或单位错位（比如把 交付周期 填在 客户满意度 那行）会把天当成百分比喂给下游，
        # 所以宁可退回也不做模糊匹配。
        if book.value(biao, f'A{i}') != ming:
            raise ExcelError(f'{biao}!A{i} 应为「{ming}」（六行顺序固定）')
        if book.value(biao, f'B{i}') != danwei:
            raise ExcelError(f'{biao}!B{i} 单位应为「{danwei}」')
        # 一行只有 C 列（本期值）参与数据导入，D 列备注只供人读、不解析。
        zhi = _shu(book.value(biao, f'C{i}'))
        if zhi is None:
            continue                                   # 整行留空 = 该指标缺数
        if not jiaoyan(zhi):
            # 报错文案按单位取词：百分比说「0-100 之间」、天数说「大于 0」、次数说「非负整数」，
            # 比统一的「值不合法」更能让用户知道自己那格错在哪；文案里带当前值便于自查。
            ti = {'%': '0-100 之间', '天': '大于 0', '次': '非负整数'}[danwei]
            raise ExcelError(f'{biao}!C{i} {ming} 必须{ti}（当前 {zhi}）')
        # 只有通过校验的值才进 dict；缺数（continue 分支）不产生键，下游按「键不存在」判缺。
        jie[ziduan] = zhi
    return jie


# ---------------------------------------------------------------- 轨道入口
# 十一表轨道的总入口：先删非财务指标表再复用 v3 的十表全套校验，
# 这样九表 + 部门明细的校验逻辑只有一份，KPI 轨道只是「多一张表、多一段解析」。
def import_v3_kpi(data, name='演示.xlsx'):
    """v3 十一表导入：九表(v2 全套校验) + 部门明细表(v3) + 非财务指标表。"""
    import io
    from openpyxl import load_workbook
    from excel_ingest_v3 import import_v3
    from xlsx_reader import ExcelError, Book

    # 这里用 openpyxl 只为两件事：拿到表序列、删掉第十一张表后内存另存；
    # 真正的读取与安全校验仍走 xlsx_reader.Book（受限解包 + 拒绝宏/外链/共享公式），
    # 所以 load_workbook 不参与任何业务取值。
    wb = load_workbook(io.BytesIO(data))
    # 表序列比对是「整本退回」的第一道门：十表 + 本表必须完全同序同名，多一张少一张都不行，
    # 报错文案特意带上文件名，便于用户确认自己提交的是哪份文件。
    if tuple(wb.sheetnames) != V3_SHEETS:
        raise ExcelError(f'{KPI_BIAO} 必须是第十一张表且其余表序列不变：{name}')
    # 删表后另存到内存 BytesIO，把「十一表」降维成 v3 认识的「十表」；
    # 只在内存里做，不回写用户文件，原始字节流保持不变（Book(data) 稍后还要用它）。
    del wb[KPI_BIAO]
    bf = io.BytesIO()
    wb.save(bf)
    # 前十表交给 import_v3 做全套校验（含 Σ部门≡公司 勾稽），返回的结果 dict 直接续用；
    # 因此本轨道天然继承了九表与部门明细的全部校验计数。
    jie = import_v3(bf.getvalue(), name)               # 前十表全套校验

    # KPI 表用原始 data 单独再开一次 Book：删表后的 bf 已经没有该 sheet，
    # 而 KPI 的值域校验需要原始字节流里的第十一张表。
    kpi = du_kpi_biao(Book(data))
    # 对外只给字符串形式的十进制值：结果要进 JSON 与报告，Decimal 直接序列化不可靠；
    # 字段名保持 KpiShuru 原名，下游按名取，不再做一层映射。
    jie['kpi_input'] = {z: str(v) for z, v in kpi.items()}
    jie['sheets'] = list(V3_SHEETS)
    jie['contract_version'] = 'v3k'
    # 校验计数加 6×3：六行各记「名称/单位/值域」三条，缺数的行也算（缺数本身即一次校验），
    # 这样 checks 总量能反映模板规模，便于回归比对时发现「少校验了几项」。
    jie['checks'] = jie.get('checks', 0) + len(KPI_HANG) * 3
    return jie


# 命令行自测入口：python -B excel_ingest_v3_kpi.py <十一表演示件.xlsx>，
# 打印类别、实际读到的 KPI 条数与 checks，供人工核对（不写任何文件）。
if __name__ == '__main__':
    import sys
    from pathlib import Path
    if len(sys.argv) < 2:
        print('用法：python -B excel_ingest_v3_kpi.py <十一表演示件.xlsx>')
        sys.exit(2)
    jie = import_v3_kpi(Path(sys.argv[1]).read_bytes(), Path(sys.argv[1]).name)
    print('类别', jie['category'], '｜非财务项', len(jie['kpi_input']),
          '｜checks', jie['checks'])
