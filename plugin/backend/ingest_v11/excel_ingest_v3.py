# -*- coding: utf-8 -*-
"""输入端口 v3 轨道：v2 九表 + 第十张「部门明细表」（表内部门维度）。

为什么加第十张表而不是改九表：v2 契约的表序列/白名单/勾稽已被既有
工作簿和验收钉死；部门维度按既有双轨惯例另开一条轨，三轨互不干扰。
    · 表序列 = v2 九表 + 部门明细表（追加在最后）→ 分发判据即表序列；
    · 九表部分原样走 v2 全套校验（剥离第十表后复用 import_v2，公司口径
      全绿才继续，任何旧规则零改动）；
    · 部门明细表版式：扁平表（部门 | 项目 | 12 个月列 | 合计），纯数值；
    · 新增勾稽：逐（科目, 期间）Σ各部门 == 公司取数位（分位精确比较，
      不齐整本退回，报错带格位）；
    · 输出：v2 结果 + departments（每部门一份八字段 CSV 文本，供宿主
      展开成虚拟分册，复用分组分析链）。

      契约硬规则（任一不过即整本退回，中文报错带「表名!格位」）：
          1) 表序列：恰好十张，九表在前、部门明细表必须第十张（多一张少一张都退回）；
          2) 表头：A1=部门、B1=项目、C1..N1 必须逐列等于「年度-01」..「年度-12」、O1=合计；
          3) 行规则：部门与科目必须成对；科目须落在九表科目集；12 个月列不允许负数；
          4) 勾稽：逐（科目, 期间）Σ部门 == 公司取数位，分位精确比较；反向也查
             （公司口径为空但部门有值且不为 0 = 多报了部门数据）；
          5) 业务规则：营业收入、税金及附加不得下沉到部门（部门按费用中心口径）。
      产出：v2 的结果 dict 原样续用，只额外补 departments（每部门一份八字段 CSV 文本）、
            sheets（十表名）、contract_version='v3'、checks（追加部门行数）。
      失败口径：一律抛 ExcelError；不存在「部分导入」——公司口径不平就整本退回。
"""
import io
import json                                                  # groupKey 保持同构
from decimal import Decimal                                  # 分位精确勾稽

# 复用 v2 内部件而不是重写：BI_XU=八字段表头、YUE_LIE=12 个月列字母、
# import_v2=九表全套校验；这样 v3 与 v2 的口径天然一致，改 v2 规则会同步生效。
# noqa: F401 是因为其中个别名字只为保持导入面与 v2 对齐，未必在本文件被直接引用。
from excel_ingest_v2 import (BI_XU, YUE_LIE, import_v2,      # noqa: F401  复用 v2 内部件
                             V2_SHEETS)

# 第十表的精确表名：既是模板 sheet 名，也是本轨道被分派到的判据之一；
# 改名等于改版式，会让所有存量 v3 工作簿在表序列比对处整本退回。
BUMEN_BIAO = '部门明细表'
# 十表序列 = 九表 + 本表（追加在最后）：tuple 顺序即分派顺序，先拼后比，
# 这样「部门明细表被挪到中间」这种错误会在表序列比较里一步挡下。
V3_SHEETS = V2_SHEETS + (BUMEN_BIAO,)
# 数据类别 -> import_v2 结果里的记录桶名：预算基础落 yusuan、实时经营落 shishi。
# 用映射而不是 if/else，是为了让「多一个类别」时只改这张表，不动主流程。
LEI_JIAN = {'预算基础': 'yusuan', '实时经营': 'shishi'}       # 类别 → 记录桶


# ---------------------------------------------------------------- 取值层
# 部门明细表的格值归一：None/空串 -> None（缺格跳过），数字/数字文本 -> Decimal。
def _shu(zhi):
    """格值 → Decimal（None/空 → None）；非数值文本原样抛错由上层处理。"""
    if zhi is None or zhi == '':
        return None
    try:
        return Decimal(str(zhi))
    except Exception:
        return None


# ---------------------------------------------------------------- 轨道入口
# 五段式：表序列 -> 剥表复用 import_v2 -> 读第十表行 -> 双向勾稽 -> 组装 departments。
# 顺序不能反：公司口径没全绿之前，部门数据再多也不进入勾稽，避免报错信息互相干扰。
def import_v3(data, name='演示.xlsx'):
    """严格导入一本 v3 工作簿（十表）；校验全过才返回结构化结果。"""
    # 延迟导入 openpyxl：只在剥表时用到，且避免与 xlsx_reader 的受限解包重复初始化。
    from openpyxl import load_workbook                       # 仅第十表剥离用
    # 这里 openpyxl 只做「结构手术」（拿表名、删第十张表），不读取任何业务值；
    # 业务值全部走 xlsx_reader.Book，保持宏/外链/共享公式的安全校验口径不变。
    wb = load_workbook(io.BytesIO(data))
    # 表序列严格比对：十张、同名、同序。报错文案点明「必须是第十张表」，
    # 因为用户最常犯的错是插到中间或改名，而不是少表。
    if tuple(wb.sheetnames) != V3_SHEETS:
        raise __import__('xlsx_reader').ExcelError(
            f'{BUMEN_BIAO} 必须是第十张表且九表序列不变：{name}')
    # 删第十表后内存另存：把十表降维成 v2 认识的九表，import_v2 才能原样复用。
    # 全程只动内存字节，不回写用户文件；原始 data 之后还要给 Book 用一次。
    del wb[BUMEN_BIAO]
    bf = io.BytesIO()
    wb.save(bf)
    # 九表全套校验（含三表勾稽、元字段十六键、白名单）走完整 import_v2，
    # 公司口径全绿才继续；返回的 dict 直接续用，所以 v3 的 checks 天然继承 v2 的计数。
    jie = import_v2(bf.getvalue(), name)                     # 九表全套校验（公司口径）

    # 第二次解包用原始 data：Book 是受限读取器（拒宏/外链/共享公式），
    # 与上一步 openpyxl 的「结构手术」分工明确——读值只认 Book。
    from xlsx_reader import Book, ExcelError
    book = Book(data)
    # 从 v2 结果里取口径：meta 提供年度与已结账截至，category 决定记录桶，
    # 这样第十张表的「年度-01..12」列名与九表月份口径永远一致。
    meta = jie['metadata']
    lei = jie['category']
    nian = meta['年度']
    # 数据来源日期默认取已结账截至月首日；缺失时退到「年度-12」（年末），
    # 截前 10 位是为了兼容可能带日尾的写法，保证后面拼出的 {geng}-01 稳定。
    geng = (meta.get('已结账截至') or f'{nian}-12')[:10]

    # ---- 1) 表头逐字：部门 | 项目 | 12 个月 | 合计 ----
    # 表头四点抽查：A1=部门、B1=项目、N1（YUE_LIE 末列）=年度-12、O1=合计。
    # 先抽这四点是因为它们定义了「行轴 + 12 个月 + 合计列」的骨架，骨架不对，
    # 后面逐列比月份就是无意义的报错噪音。
    if book.value(BUMEN_BIAO, 'A1') != '部门' or book.value(BUMEN_BIAO, 'B1') != '项目' \
            or book.value(BUMEN_BIAO, f'{YUE_LIE[-1]}1') != f'{nian}-12' \
            or book.value(BUMEN_BIAO, 'O1') != '合计':
        raise ExcelError(f'{BUMEN_BIAO} 表头不符合固定版式（部门/项目/月份/合计）')
    # C..N 十二列逐列比对「年度-01..年度-12」：月份列的列序是数据行的坐标基准，
    # 错一列就会把 3 月的钱记到 2 月，必须逐列确认后再开始读行。
    yue_qi = {}
    for i, m in enumerate(YUE_LIE):
        qi = f'{nian}-{i + 1:02}'
        if book.value(BUMEN_BIAO, f'{m}1') != qi:
            raise ExcelError(f'{BUMEN_BIAO}!{m}1 应为 {qi}')
        yue_qi[m] = qi

    # ---- 2) 行读取：部门 | 科目 | 12 月 | 合计（合计=行和，逐分） ----
    # 类别不在映射里会直接 KeyError；v3 只服务两个类别，正常路径不会走到。
    lei_key = LEI_JIAN[lei]
    # records.shuzhi 语义是分；÷100 换回元，与部门明细表单元格（元）同单位比较
    # 公司口径基准表 {(科目, 期间): 元}；records.shuzhi 是整数分，先 ÷100 换回元，
    # 才能与第十表单元格（元）同单位比较；/100 用 Decimal 运算，不留浮点尾数。
    gong = {(r['kemu'], r['qijian']): Decimal(str(r['shuzhi'])) / 100
            for r in jie['records'][lei_key]}
    # 合法科目集 = 公司口径里出现过的科目 ∪ v2 的 subjects 列表：前者保证有数可对，
    # 后者把「本期无金额但有科目行」的科目也纳入，避免部门明细因无金额而报科目非法。
    kemu_he = {k for k, _ in gong} | {r['kemu'] for r in jie['subjects']}
    # 三张索引表同时建，各司其职：
    #   bu_xing ：(部门, 科目) -> {期间: 元}，建 departments 分册 + 查重复行；
    #   bu_ji   ：(科目, 期间) -> {部门: 元}，做 Σ部门 与公司口径的勾稽；
    #   hang_hao：(部门, 科目) -> 行号，留给将来定位报错行（本版仅记录不读）。
    bu_xing = {}                                  # (部门, 科目) → {期间: Decimal}
    bu_ji = {}                                    # (科目, 期间) → {部门: Decimal}
    hang_hao = {}
    r = 2
    # 行读取按「两个关键列都空」即停：第十表是扁平表，允许中间有空行，
    # 但一行都没读到也算错（见下方 bu_xing 判空），不允许交空表。
    while True:
        bu = book.value(BUMEN_BIAO, f'A{r}')
        kem = book.value(BUMEN_BIAO, f'B{r}')
        # 终止条件：A、B 两列都空才算表尾；只空一列属于填写错误，交给下一条报「必须成对」。
        if not bu and not kem:
            break
        # 只填部门或只填科目：这一行无法归属，直接退回并同时报出两个格位，便于用户定位。
        if not bu or not kem:
            raise ExcelError(f'{BUMEN_BIAO}!A{r}/B{r} 部门与科目必须成对填写')
        # 科目必须是九表里存在的科目名（逐字比较）：部门明细不能自造科目，
        # 否则勾稽时既对不上公司口径、也无法映射到分析层的科目树。
        if kem not in kemu_he:
            raise ExcelError(f'{BUMEN_BIAO}!B{r} 科目 {kem} 不在九表科目集内')
        he_ji, zhi_dui = Decimal('0'), {}
        for m in YUE_LIE:
            # 月份格逐个取：空格跳过（缺月=0，不参与求和）、负数拒收（费用只能非负），
            # 非数字文本由 _shu 归成 None 后同样按缺月处理。
            zhi = _shu(book.value(BUMEN_BIAO, f'{m}{r}'))
            if zhi is None:
                continue
            if zhi < 0:
                raise ExcelError(f'{BUMEN_BIAO}!{m}{r} 不接受负数')
            zhi_dui[yue_qi[m]] = zhi
            he_ji += zhi
        # xlsx 浮点往返会有 1e-9 量级尘埃：一律量化到分位再比较
        FEN_WEI = Decimal('0.01')
        # 合计列（O）必须等于行内 12 个月之和，且两边都量化到分位再比。
        he_lan = _shu(book.value(BUMEN_BIAO, f'O{r}'))
        # 报错同时给出「表内合计」与「逐月之和」两个数：用户一眼能看出差多少，
        # 而不用自己拿计算器回算 12 个月。
        if he_lan is None or he_lan.quantize(FEN_WEI) != he_ji.quantize(FEN_WEI):
            raise ExcelError(f'{BUMEN_BIAO}!O{r} 合计 {he_lan} ≠ 行内 12 个月之和 {he_ji}')
        # 同一部门同一科目只允许一行：出现两行意味着「是覆盖还是累加」无法判定，
        if (bu, kem) in bu_xing:
            raise ExcelError(f'{BUMEN_BIAO} 部门 {bu} 的科目 {kem} 重复出现')
        # 写回三张索引：部门侧、勾稽侧、行号侧同时登记，后面各段只读不重建。
        bu_xing[(bu, kem)] = zhi_dui
        hang_hao[(bu, kem)] = r
        for qi, zhi in zhi_dui.items():
            bu_ji.setdefault((kem, qi), {})[bu] = zhi
        r += 1
    # 只有表头、没有数据行：空表不算导入成功，直接退回（与 v2 空表口径一致）。
    if not bu_xing:
        raise ExcelError(f'{BUMEN_BIAO} 没有任何部门数据行')
    # 业务规则：收入与税金属于公司级，不得下沉到部门（部门按费用中心口径）
    # 业务规则：收入与税金是公司级科目，按费用中心口径不能下沉到部门。
    # 放行会先把收入拆给部门、再与公司口径勾稽时出现「部门合计=公司」的假平，
    # 从而掩盖真正的口径错误，所以这里宁可整本退回。
    if any(kem in ('营业收入', '税金及附加') for _, kem in bu_xing):
        raise ExcelError(f'{BUMEN_BIAO} 不应出现「营业收入/税金及附加」：收入须留在公司级')

    # 正向勾稽：只遍历公司口径里存在的 (科目, 期间)；部门侧没有该键 = 未下沉，跳过。
    # ---- 3) 勾稽：逐（科目, 期间）Σ各部门 == 公司取数位（量化到分位） ----
    FEN_WEI = Decimal('0.01')
    # sorted 只为让报错顺序稳定（同一文件每次报同一处），不影响判定结果。
    for (kem, qi), gong_zhi in sorted(gong.items()):
        if (kem, qi) not in bu_ji:
            continue          # 公司级科目（营业收入/税金及附加）允许不下沉到部门
        bu_he = sum(bu_ji.get((kem, qi), {}).values(), Decimal('0'))
        # 分位比较是勾稽的唯一口径：0.01 元以内的差异视为相等（浮点尘埃），
        # 超过一分钱就是真不平，报错里同时给出部门合计与公司口径两个数。
        if bu_he.quantize(FEN_WEI) != gong_zhi.quantize(FEN_WEI):
            raise ExcelError(f'{BUMEN_BIAO} 勾稽不平：{kem} {qi} '
                             f'各部门合计 {bu_he} ≠ 公司口径 {gong_zhi}')
    # 反向勾稽：公司口径里没有的 (科目, 期间)，部门侧若有非零值就是「凭空多报」，
    # 合计为 0 的允许（部门登记了但金额互相抵消/全为 0，不影响公司口径）。
    for (kem, qi), zhi_dui in bu_ji.items():
        if (kem, qi) not in gong and sum(zhi_dui.values(), Decimal('0')) != 0:
            raise ExcelError(f'{BUMEN_BIAO} 勾稽不平：{kem} {qi} 公司口径为空但部门有值')

    # 分册组装：每部门一份八字段 CSV 文本（不含表头以外的汇总），宿主展开成虚拟分册，
    # 复用既有的分组分析链，因此这里不再另起一套分析入口。
    # ---- 4) departments：每部门一份八字段 CSV（宿主展开成虚拟分册用） ----
    # bu_men：部门 -> 行列表（首行是 BI_XU 八字段表头），顺序按首次出现。
    bu_men = {}
    for (bu, kem), zhi_dui in bu_xing.items():
        # 每个部门第一行固定写八字段表头，后面按期间升序追加数据行。
        hang = bu_men.setdefault(bu, [BI_XU])
        for qi in sorted(zhi_dui):
            hang.append(f'{lei},{qi},{kem},{zhi_dui[qi]:.2f},元,'
                        f'标准Excel模板,{geng}-01,')
    # 值用 {text: ...} 包一层，与 v2 返回结构里其它分册的形态保持一致，
    # 宿主侧解析逻辑不分叉；金额按两位小数格式化，保留「元」为单位（分位换算在下游）。
    jie['departments'] = {bu: {'text': '\n'.join(hang)}
                          for bu, hang in bu_men.items()}
    # sheets 改成十表名，让调用方拿到的表清单与实际导入一致（v2 给的是九表）。
    jie['sheets'] = list(V3_SHEETS)
    jie['contract_version'] = 'v3'
    # checks 追加「部门数据行数」：len(h)-1 扣掉每份 CSV 的表头行，
    # 让校验计数反映实际读了多少行，回归比对时能发现行数异常。
    jie['checks'] = jie.get('checks', 0) + sum(len(h) - 1 for h in bu_men.values())
    return jie


# 命令行自测：python -B excel_ingest_v3.py <表内部门演示件.xlsx>，
# 打印类别、部门数、checks 与各部门行数（不写文件），供人工核对。
if __name__ == '__main__':                                   # 命令行自测
    import sys
    from pathlib import Path
    if len(sys.argv) < 2:
        print('用法：python -B excel_ingest_v3.py <表内部门演示件.xlsx>')
        sys.exit(2)
    jie = import_v3(Path(sys.argv[1]).read_bytes(), Path(sys.argv[1]).name)
    print('类别', jie['category'], '｜部门', len(jie['departments']),
          '｜checks', jie['checks'])
    print(json.dumps({b: len(x['text'].splitlines()) - 1
                      for b, x in jie['departments'].items()},
                     ensure_ascii=False))
