# -*- coding: utf-8 -*-
"""量价拆分表解析（v3s 十一表；规划/执行差异拆分的唯一数据源）。

表版式（固定，纯数值零公式）：
    第 1 行表头：科目 | 标准单价（元） | 标准用量 | 修订单价（元） | 修订用量 | 实际产量 | 实际总用量 | 实际总成本（元）
    数据行（科目名必须在九表科目集内；顺序不限；同一科目不得重复）：
        标准单价 ≥ 0；标准用量 ≥ 0；修订单价 ≥ 0；修订用量 ≥ 0；
        实际产量 > 0（单位成本要有分母）；实际总用量 ≥ 0；实际总成本 ≥ 0。
    金额两位小数（元），数量非负整数。任一校验不过 → 整本退回（中文报错带格位）。
    允许整行留空（该科目不做拆分）；至少一行有效数据才产出拆分。

    轨道判定（表序列即轨道，本文件一次服务两条）：
        十一表 = v3 十表 + 量价拆分（本表第十一张）-> contract_version='v3s'；
        十二表 = 十一表 + 非财务指标（第十二张）-> contract_version='v3sk'，尾部多一张表。
    契约硬规则（任一不过即整本退回，中文报错带「表名!格位」）：
        1) 表序列：量价拆分必须是第十一张，其余表序列不得变动（多一张少一张都退回）；
        2) 表头：A..H 八列表头必须与 LJ_BIAOTOU 逐字一致（列序不可调、不可加列）；
        3) 数据行：A 列科目必须在九表科目集内且不重复；七个参数列不许留空；
        4) 值域：六列 ≥0，实际产量必须 >0（单位成本要有分母）；
        5) 至少一行有效数据，否则「没有产出拆分」也算失败。
    产出：在 v3 结果上追加 liangjia（每科目一条：kemu + 七个 ChaifenShuru 字段，
          金额已换整数分、数量为整数），v3sk 另追加 kpi_input；checks 记 8×科目数+8。
    失败口径：一律抛 ExcelError；量价表读失败不会产出半份结果。
"""
# Decimal 承担金额与数量的精确解析；InvalidOperation 用于把「非数字文本」判成 None，
# 交给上层按缺参退回，而不是让 Decimal 的原始异常漏到调用方。
from decimal import Decimal, InvalidOperation

# 复用 v3 的十表序列做「本文件再加一张表」的基底：依赖链 v3s -> v3 -> v2 单向，
# V3_TEN 只拿来拼序列与比对，本文件不重复实现部门明细的任何校验。
from excel_ingest_v3 import V3_SHEETS as V3_TEN       # noqa: F402
# v3sk 轨道的非财务指标解析直接复用 v3_kpi，不在此重写：KPI 的六行约定、
# 值域文案、缺数语义都只有一份真源，改一处两条轨道同步。
from excel_ingest_v3_kpi import KPI_BIAO, du_kpi_biao  # noqa: F402

# 第十一张表的精确表名：既是模板 sheet 名，也是本轨道被分派的判据之一。
LJ_BIAO = '量价拆分'
# 十一表序列（v3s 轨道）：量价拆分固定追加在第十一张，顺序即模板顺序。
V3_SHEETS = V3_TEN + (LJ_BIAO,)
# 十二表序列（v3sk 轨道）：在量价拆分之后再来一张非财务指标，
# 即「第十一张量价、第十二张 KPI」——顺序不能互换，分派按整条序列判等。
V3SK_SHEETS = V3_TEN + (LJ_BIAO, KPI_BIAO)   # v3sk 十二表：部门 + 量价 + 非财务

# 表头八列：A 科目、B 标准单价、C 标准用量、D 修订单价、E 修订用量、
# F 实际产量、G 实际总用量、H 实际总成本。字典保留列字母是为了报错时能直接
# 拼出「量价拆分!B5 表头应为…」这种可回查的格位，而不是只报列序号。
#: 表头列定义：列字母 → 表头名
LJ_BIAOTOU = {'A': '科目', 'B': '标准单价（元）', 'C': '标准用量', 'D': '修订单价（元）',
              'E': '修订用量', 'F': '实际产量', 'G': '实际总用量', 'H': '实际总成本（元）'}
# 七个参数列的元数据（B..H），三元组含义：
#   字段名：ChaifenShuru 的同名字段，下游按名取数，本文件不做二次映射；
#   是否金额：True 时把表值（元）乘 100 转整数分，False 时直接取整数数量；
#   校验器：闭包收 Decimal 返回 bool，六列 ≥0、实际产量 >0（作单位成本的分母）。
# 用字典而不是列表：表头校验、逐列读取、报错文案三处共用同一份定义，避免错位。
#: 参数列 → (KpiShuru 无关；ChaifenShuru 字段名, 是否金额, 校验器)
LJ_LIE = {
    'B': ('biaozhun_danjia', True, lambda v: v >= 0),
    'C': ('biaozhun_yongliang', False, lambda v: v >= 0),
    'D': ('xiuding_danjia', True, lambda v: v >= 0),
    'E': ('xiuding_yongliang', False, lambda v: v >= 0),
    'F': ('shiji_chanliang', False, lambda v: v > 0),
    'G': ('shiji_yongliang', False, lambda v: v >= 0),
    'H': ('shiji_chengben', True, lambda v: v >= 0),
}


# ---------------------------------------------------------------- 取值层
# 格值归一：None/空串 -> None（缺参），数字/数字文本 -> Decimal；解析失败也归 None，
# 由调用方统一报「不能为空」——这样报错文案只有一种，不会冒出 Decimal 的原始异常。
def _shu(zhi):
    """把单元格值归一成 Decimal。

    参数：zhi=Book.value() 的返回值（Decimal / str / None）。
    返回：Decimal；空值或无法解析时返回 None（= 缺参，由上层报错）。
    """
    if zhi is None or zhi == '':
        return None
    try:
        return Decimal(str(zhi))
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------- 量价拆分表解析
# 参数：book=Book（原始字节流打开）；kemu_ji=九表科目集（来自 v3 结果的 subjects）；
# 返回：list[dict]，每项 {'kemu': 科目名, 七个 ChaifenShuru 字段: int}，顺序即表行序；
# 异常：表头不符/缺科目/科目越界/科目重复/参数缺失/值域不符 -> ExcelError（带格位）。
def du_liangjia_biao(book, kemu_ji):
    """读量价拆分表 → [{kemu, 参数七元组（int，金额×100 转分）}]。"""
    from xlsx_reader import ExcelError
    # 八列表头逐列逐字比对（只比这八列，不扫描额外列）：列序是数据列的坐标基准，
    # 例如 B/C 被互换会把单价当用量读进来，金额与数量的口径就整体错了。
    for lie, ming in LJ_BIAOTOU.items():
        if book.value(LJ_BIAO, f'{lie}1') != ming:
            raise ExcelError(f'{LJ_BIAO}!{lie}1 表头应为「{ming}」')
    # jie 的顺序 = 模板数据行顺序，不做排序：下游按科目名取，顺序只影响展示。
    jie = []
    r = 2
    # 行循环：A 列科目与 B 列标准单价同时为空才算表尾；两列都空之前一律当作有效行处理。
    while True:
        kem = book.value(LJ_BIAO, f'A{r}')
        can = _shu(book.value(LJ_BIAO, f'B{r}'))
        # 终止条件只看「科目空 + 标准单价空」两格：模板里这两格是每行的起点，
        # 它们都空就说明这行没填（允许中间夹空行），继续往下读没有意义。
        if not kem and can is None:
            break
        # 只填了金额没填科目：这一行无法归属到科目，报错点明 A 列格位。
        if not kem:
            raise ExcelError(f'{LJ_BIAO}!A{r} 缺科目名')
        # 科目必须是九表里出现过的科目名（逐字）：量价拆分只是给已有科目加「量、价」维度，
        # 自造科目名会让拆分结果挂不到任何一行预算上，必须退回。
        if kem not in kemu_ji:
            raise ExcelError(f'{LJ_BIAO}!A{r} 科目 {kem} 不在九表科目集内')
        # 同一科目只允许一行：两行意味着「按哪套单价/用量拆」无法判定，直接退回；
        # 用线性查找而不是 set，是因为科目数上限很小（一行一个科目），可读性优先。
        if any(j['kemu'] == kem for j in jie):
            raise ExcelError(f'{LJ_BIAO} 科目 {kem} 重复出现')
        # 先落科目名，再按 LJ_LIE 顺序补齐七个参数；只有全部通过校验才 append，
        # 保证返回列表里不会出现「半行」数据。
        tiao = {'kemu': kem}
        # 七列按 dict 插入顺序（B..H）逐列读，每列三件事：取 Decimal、判缺参、判值域；
        # 三元组里的 jin_e 决定这一列要不要 ×100 转分，jiaoyan 是这一列的值域闭包。
        # 列序与 LJ_BIAOTOU 完全一致，所以报错文案能直接按 lie 取表头名。
        for lie, (ziduan, jin_e, jiaoyan) in LJ_LIE.items():
            zhi = _shu(book.value(LJ_BIAO, f'{lie}{r}'))
            # 参数列缺一格即整行退回：量价拆分缺任一参数就无法做价差/量差分解，
            # 报错带上科目名与列名，指出是哪个科目的哪个参数没填。
            if zhi is None:
                raise ExcelError(f'{LJ_BIAO}!{lie}{r} {kem} 的{LJ_BIAOTOU[lie]}不能为空')
            # 值域报错按列取词：实际产量（F 列）说「大于 0」，其余六列说「非负」；
            # 文案里带当前值，用户不必回查自己填了什么。
            if not jiaoyan(zhi):
                yao = '大于 0' if lie == 'F' else '非负'
                raise ExcelError(f'{LJ_BIAO}!{lie}{r} {LJ_BIAOTOU[lie]}必须{yao}（当前 {zhi}）')
            # 金额列（B/D/H）由元换整数分：Decimal×100 后 int() 精确取整，不经过 float；
            # 数量列（C/E/F/G）直接 int()：模板要求非负整数，校验器只卡 ≥0，
            #           带小数的用量会被静默截断——此处照实记录现状，不改校验口径。
            tiao[ziduan] = int(zhi * 100) if jin_e else int(zhi)
        jie.append(tiao)
        r += 1
    return jie


# ---------------------------------------------------------------- 轨道入口
# 流程：表序列判轨道 -> 剥掉量价（与可选 KPI）表 -> import_v3 跑前十表全套校验
#       -> 用原始 data 解析量价 -> 按是否有 KPI 表决定版本标记与 checks。
# 剥表只为复用 import_v3；量价与 KPI 的读值仍用原始 data，绝不复用剥过的字节流。
def import_v3s(data, name='演示.xlsx'):
    """v3s/v3sk 导入：九表(v2 全套校验) + 部门明细表(v3) + 量价拆分表（+ 可选非财务指标表）。

    表序列决定轨道：十一表=V3_SHEETS（v3s）；十二表=V3SK_SHEETS（v3sk，尾部多非财务指标）。"""
    # 局部导入集中在这一屏：io 造内存字节流、openpyxl 剥表、import_v3 复用前十表校验、
    # xlsx_reader 提供受限读取与 ExcelError；放函数内可避免模块级循环导入。
    import io
    from openpyxl import load_workbook
    from excel_ingest_v3 import import_v3
    from xlsx_reader import ExcelError, Book

    # openpyxl 只做结构手术（读表名、删表、内存另存），不参与任何业务取值；
    # 业务值全走 xlsx_reader.Book，安全闸门（宏/外链/共享公式）口径不变。
    wb = load_workbook(io.BytesIO(data))
    # 先记下原始表序：它既是轨道判据（十一表 vs 十二表），也是对外 sheets 字段的来源，
    # 后面剥表会改 wb，所以必须先存成不可变的 tuple。
    mingdan = tuple(wb.sheetnames)
    # 两条轨道一次判定：整条序列必须等于十一表或十二表，不接受「多一张别的表」，
    # 报错文案点明「量价拆分必须是第十一张」，因为用户最常见的错是把它插到中间。
    if mingdan not in (V3_SHEETS, V3SK_SHEETS):
        raise ExcelError(f'{LJ_BIAO} 必须是第十一张表且其余表序列不变：{name}')
    # 依次删第十一张（量价）与可能的第十二张（KPI），把工作簿降维成 v3 认识的十表；
    # 顺序无关紧要（按名删），但必须在 save 之前完成，且只在内存里做。
    del wb[LJ_BIAO]
    if KPI_BIAO in mingdan:
        del wb[KPI_BIAO]
    bf = io.BytesIO()
    wb.save(bf)
    # 前十表全套校验（含部门明细的 Σ部门≡公司 勾稽）走完整 import_v3；
    # 公司口径没全绿就不会继续读量价，避免「部门都不平还报量价错」的噪音。
    jie = import_v3(bf.getvalue(), name)               # 前十表全套校验

    # 合法科目集取自 v2 结果的 subjects（九表科目行）：subjects 为空时兜底空集，
    # 此时任何科目名都会报「不在九表科目集内」——空表本来就是错。
    kemu_ji = {s['kemu'] for s in jie.get('subjects') or []}
    # 用原始 data 再开一次 Book：剥表后的 bf 已无量价拆分表，必须回到原始字节流。
    lj = du_liangjia_biao(Book(data), kemu_ji)
    # 对外字段 liangjia：list[dict]，每项一个科目 + 七个整数参数；
    # 分析层按 kemu 取用，做价差/量差分解时不需再做映射。
    jie['liangjia'] = lj
    if KPI_BIAO in mingdan:
        # 只有 v3sk 才有 kpi_input：字段名沿用 KpiShuru 原名，值转十进制字符串；
        # 与 v3_kpi 轨道返回的形态一致，宿主侧解析逻辑不必分叉。
        jie['kpi_input'] = {z: str(v) for z, v in
                            du_kpi_biao(Book(data)).items()}
        # 版本标记决定分析层走哪条链：v3sk = 十表 + 部门 + 量价 + 非财务指标四件套。
        jie['contract_version'] = 'v3sk'
        jie['checks'] = jie.get('checks', 0) + 18
    else:
        # v3s = 十表 + 部门 + 量价，无 KPI 表；两条链共用本函数，只差尾部一张表。
        jie['contract_version'] = 'v3s'
    # sheets 用原始表序（十一或十二表），让调用方拿到的清单与实际导入一致。
    jie['sheets'] = list(mingdan)
    # 校验计数：每个量价科目记 8 条（1 科目 + 7 参数），再加 8 条表头校验；
    # v3sk 分支已先加 18（KPI 六行×3），两处相加得到总计数。
    jie['checks'] = jie.get('checks', 0) + len(lj) * 8 + len(LJ_BIAOTOU)
    return jie


# 命令行自测：python -B excel_ingest_v3s.py <十一表量价演示件.xlsx>，
# 打印类别、拆分科目数与 checks；不写文件、不改用户工作簿。
if __name__ == '__main__':
    import sys
    from pathlib import Path
    if len(sys.argv) < 2:
        print('用法：python -B excel_ingest_v3s.py <十一表量价演示件.xlsx>')
        sys.exit(2)
    jie = import_v3s(Path(sys.argv[1]).read_bytes(), Path(sys.argv[1]).name)
    print('类别', jie['category'], '｜拆分科目', len(jie['liangjia']),
          '｜checks', jie['checks'])
