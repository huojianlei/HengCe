# -*- coding: utf-8 -*-
"""external_templates v1.2 fork——自 1.0.5 algo/external_templates.py 逐字复制。

行为差异（两处，均不改变校验口径）：
    1) 批次信息!B1 模板版本钉改双轨——老串 '衡策/{类别}/1.0.5' 照收
       （1.0.5 模板与旧演示件零漂移），新串 '标准/{类别}/1.0.5' 放行
       （v1.2 演示产物全簿不含"衡策"字样）。
    2) 经营变更的 analysis_events 追加 'code'（受影响科目编码），供 9 表轨道
       把 EXP1.021 等编码映射到两级科目名；判定链只消费名称与结构标签。
其余逻辑逐字一致；1.0.5 树全程只读。
建立：2026-10-16 ｜ Agent：ZCode（GLM-5.3）

    v1.11 端口补充说明（只写文档，不改逻辑）：
        这个模块吃两套「外部模板」——行业对标（批次信息 / 基准指标）与
        经营变更（批次信息 / 事件台账 / 科目影响）；两套都是固定版式，
        表名、表数、表序不符整本退回，不做 CSV / Word / PDF / 旧 XLS 适配。
        批次信息是「哪一类外部模板」的唯一身份来源：A 列纵向排 15 个元字段名、
        B 列取值，行号与 META 顺序一一对应，meta() 先查表序列再逐行比对字段名。
        产出统一是 data_ingest 的八字段行（数据类别 / 统计周期 / 数据科目 / 数值 /
        单位 / 数据来源 / 更新时间 / 备注），本模块只做版式与口径校验 + 组装，不做汇总。
        口径纪律：金额进下游一律整数分、比率一律整数基点，本模块交出的数值仍是
        模板原单位（元 / %），换算在分析层完成。
        失败一律抛 xlsx_reader.ExcelError，文案带「表名!单元格」定位，由
        excel_ingest_v11.import_excel_v11 收拢成 jujue 退回收据，不抛裸异常。
"""
# 依赖分工：csv+io 只用来拼八字段 CSV 文本（records()），re 做版式正则，
# dataclasses 把 daoru_csv 的解析结果转成 dict，datetime 处理 Excel 日期序列号。
import csv
import dataclasses
import datetime as dt
import io
import json
import re
from decimal import Decimal

# BIXU_LIE = 八字段固定表头；daoru_csv = 八字段的权威清洗与拒绝判定入口。
# 本模块只负责「按模板把值捞出来写成八字段行」，清洗、金额分位、拒绝码都在 data_ingest。
from data_ingest import BIXU_LIE, daoru_csv
# ACCOUNTS = 1.0.5 algo 的科目注册表（code / name / sheet / row / column 等），
# 经营变更的「受影响科目编码」必须落在它里面，才谈得上映射到九表科目；
# col(n) = 列号转列字母（1 -> A），全文件坐标拼装都走它，别手写列字母。
from excel_contract import ACCOUNTS, col
# Book = 受限 xlsx 读取器：先查后缀、再解包、拒绝宏 / 外链 / 共享公式，
# value()/number() 内建公式受限求值；ExcelError 是本模块唯一对外异常类型。
from xlsx_reader import Book, ExcelError

# 批次信息!A1:B15 的 15 个元字段，元组的顺序就是工作表里的行号（enumerate 从 1 起）。
# 注意它与 12 表版式里的 16 键元字段（excel_contract_v11.META，带生成种子/数据类别）
# 不是同一套：外部两类模板没有生成种子与数据类别，靠「模板版本」字符串里的类别段区分。
# 改这个元组的顺序等于改版式，会导致所有存量外部模板被退回，非必要不动。
META=('模板版本','主体编码','主体名称','情景编码','情景名称','年度','期间粒度','数据版本号',
      '口径标记','生效周期','已结账截至','结构性变更标签','受影响科目','数据状态','备注')
# 基准指标表的 18 列（A..R），顺序即列号：A 指标编码 … D 参考值 … R 备注。
# headers() 会按这个元组逐列比对第 1 行表头，并且发现表头行里出现白名单外的列
# 直接判「存在额外字段」退回——所以这里是白名单而不是「至少要有的列」。
INDUSTRY=('指标编码','指标名称','统计周期','参考值','单位','指标性质','行业范围','样本口径','计算口径',
          '发布机构','来源标题或URL','发布日期','适用限制','适用主体编码','适用情景编码','生效标记','更新时间','备注')
# 事件台账的 15 列（A..O）：A 事件ID … F 状态 … I 说明 … J..O 申请/审批六件套。
# 其中 E 结束周期、I 说明、J..O 六列在事件台账里允许为空（文本框为空串），
# 只有「状态=已批准」时才强制补齐申请、审批与依据（见 changes() 的必填链）。
EVENT=('事件ID','事件类型','发生日期','生效周期','结束周期','状态','依据来源','更新时间','说明',
       '申请人','申请日期','审批人','审批日期','审批结论','审批依据')
# 科目影响的 8 列（A..H）：事件ID / 受影响科目编码 / 影响周期 / 方向 / 影响值 /
# 单位 / 是否结构性 / 备注。除备注外全部必填；方向只收 增加|减少，单位只收 元。
# 每行 = 某事件在某科目某期间上的一次变更量，是经营变更唯一被消费的量化载体。
IMPACT=('事件ID','受影响科目编码','影响周期','方向','影响值','单位','是否结构性','备注')
# 行业对标的 5 个受控指标：编码 -> 中文名，双向白名单。
# 校验口径是「编码与名称必须成对且与这张表一致」（industry() 第 119 行），
# 防止用户自造指标名（如把 采购成本变动率 写成 采购降本率）冒充标准口径；
# 指标性质 真实 时还必须有可核验 URL 与完整统计口径，构造参考值仅供演示。
METRICS={'GROSS_MARGIN':'行业毛利率','PROCUREMENT_COST_CHANGE':'采购成本变动率',
         'CAPACITY_UTILIZATION':'产能利用率','EXPENSE_THRESHOLD':'费用阈值','RAW_MATERIAL_INDEX':'原材料指数'}
# 科目编码 -> 两级科目名（如 EXP1.021 -> 管理费用/员工费用/…），
# 用于把变更事件挂到九表科目上：analysis_events 里同时带 kemu（名称）与 code（编码），
# 判定链只消费名称与结构标签，编码供 9 表轨道做精确对齐。
ACCOUNT_NAMES={a['code']:a['name'] for a in ACCOUNTS}

# ---------------------------------------------------------------- 单元格取值层
# text / date 是两个「读格子并当场验口径」的薄封装：模板里的文本字段（编码、
# 名称、周期、状态）与日期字段（发生/申请/审批/发布）都经由它们进入内存，归一化在出口完成。
def text(book,sheet,ref,required=True):
    """读一个文本单元格，返回去首尾空白的 str。

    参数：book=Book 只读工作簿；sheet=表名；ref=坐标（如 批次信息!B3）；
          required=False 表示该格允许为空（空则返回空串，不报错）。
    返回：str。数值型先转成 str 再判文本，避免「年度」「编码」被读成 Decimal；
          整数型 Decimal 会带 .0，所以这里不做数值化，交给 number() 的地方才取数。
    异常：空且必填 ->「请填写 表名!单元格」；非文本 ->「表名!单元格 必须为文本」。
    """
    v=book.value(sheet,ref)
    # 年度、编码这类「看着像数字」的字段常被 Excel 存成数值，先降级成 str 再统一按
    # 文本校验；真正的数值字段不走这里，走 Book.number() 拿 Decimal。
    if isinstance(v,Decimal):v=str(v)
    if v is None or str(v).strip()=='':
        # 空值口径按字段重要性分两档：主体/编码/周期这类定位字段必填（required=True），
        # 备注、结束周期这类附属字段允许留空。报错文案直接写「请填写 表名!单元格」，便于用户按坐标回查。
        if required:raise ExcelError(f'请填写 {sheet}!{ref}')
        return ''
    # 文本校验放在降级之后：Decimal 已转 str，此处非 str 只可能是 bool/date 等异常类型；
    # 一旦出现说明单元格里是公式错值或富文本，无法当作编码使用，直接退回。
    if not isinstance(v,str):raise ExcelError(f'{sheet}!{ref} 必须为文本')
    return v.strip()

# 日期口径：模板允许两种写法——Excel 日期序列号（数值）或 YYYY-MM-DD 文本；
# 出口统一 YYYY-MM-DD 字符串，不做时区/时间运算（本产品全部按自然月口径）。
def date(book,sheet,ref,required=True):
    """读一个日期单元格，统一归一化成 YYYY-MM-DD 字符串。

    参数：book / sheet / ref 同 text()；required=False 时空格返回空串。
    返回：'YYYY-MM-DD'。数值按 Excel 序列号换算，文本按正则+fromisoformat 双验。
    异常：数值越界 ->「日期无效」；格式不符 ->「日期格式须为 YYYY-MM-DD」；
          正则通过但日历上不存在（如 2027-02-30）->「日期不存在」。
    """
    v=book.value(sheet,ref)
    if v is None and not required:return ''
    if isinstance(v,Decimal):
        # 序列号合理性闸门：必须整数（模板里不该出现 45000.5 这种带小数的日期），
        # 下限 1、上限 90000 约合 2146 年，把 0/负数/误填的大数挡在换算之前——
        # 否则 1899-12-30 加天数会得到 1800 年代甚至 9999 年的假日期。
        if int(v)!=v or v<1 or v>90000:raise ExcelError(f'{sheet}!{ref} 日期无效')
        # 1899-12-30 是 Excel 序列号的换算原点（不是 1900-01-01）：Excel 把 1900 年
        # 误当闰年多算了一天，用 12-30 作原点才能对所有当代日期正确对齐。
        v=(dt.datetime(1899,12,30)+dt.timedelta(days=int(v))).strftime('%Y-%m-%d')
    elif isinstance(v,str):v=v.strip()
    else:raise ExcelError(f'{sheet}!{ref} 日期无效')
    # 正则先卡「年份 20xx + 两位月日」的形态，再用 fromisoformat 卡日历合法性；
    # 两道分开是为了让报错能区分「格式错」和「日期不存在」——退回收据要指得准。
    if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])-([0-2]\d|3[01])',v):raise ExcelError(f'{sheet}!{ref} 日期格式须为 YYYY-MM-DD')
    try:dt.date.fromisoformat(v)
    # 保留原异常链（from e）：排查脚本日志里还能看到 datetime 的原始报错，便于区分模板错与读取器错。
    except ValueError as e:raise ExcelError(f'{sheet}!{ref} 日期不存在') from e
    return v

# ---------------------------------------------------------------- 批次元字段层
# meta() 是所有校验的前置：先判「这是哪一类外部模板」，再判元字段取值合规。
# 顺序必须先是表序列、后是元字段——表序列不对，B 列内容根本没意义。
def meta(book,kind):
    """校验并读出批次信息!A1:B15 的 15 个元字段。

    参数：book=Book；kind='行业对标' 或 '经营变更'（决定期望的表序列）。
    返回：dict，键为 META 顺序的 15 个字段名，值均为去空白 str。
    异常（按判定顺序）：表名/数量/顺序错 ->「{kind}工作表名称、数量或顺序错误」；
          字段名错位 ->「批次信息第 i 行字段不符」；版本不符 ->「模板版本不符」；
          年度/粒度非法、编码非法、周期非本年月度 -> 对应中文文案。
    """
    # 表序列即模板指纹：tuple(book.cells) 是解包时的工作表顺序，与期望元组逐项比，
    # 多一张、少一张、换顺序都退回——所以这里不能写成集合或排序后比较。
    expected=('批次信息','基准指标') if kind=='行业对标' else ('批次信息','事件台账','科目影响')
    if tuple(book.cells)!=expected:raise ExcelError(f'{kind}工作表名称、数量或顺序错误')
    result={}
    for i,key in enumerate(META,1):
        # A 列字段名必须与 META 第 i 项逐字相同（行号即顺序），防止用户删行插行把
        # 行序挪位——行序一乱，B 列取值就会被安到错误的字段上，后续校验全成误报。
        if book.value('批次信息',f'A{i}')!=key:raise ExcelError(f'批次信息第 {i} 行字段不符')
        result[key]=text(book,'批次信息',f'B{i}')
    # 版本双轨：1.0.5 旧演示件写「衡策/{类别}/1.0.5」，v1.2 演示产物要求全簿不含
    # 「衡策」字样，改写「标准/{类别}/1.0.5」；两串都收，其余版本一律退回。
    if result['模板版本'] not in (f'衡策/{kind}/1.0.5', f'标准/{kind}/1.0.5'):
        raise ExcelError(f'{kind}模板版本不符')  # v1.2 双轨：老串照收、中性串放行
    # 期间粒度只收 月度/季度 两档，年度必须是四位 20xx；粒度决定后面 period() 的正则
    # 形态（月度 YYYY-MM、季度 YYYY-Qn），两处口径必须一致。
    if result['期间粒度'] not in ('月度','季度') or not re.fullmatch(r'20\d\d',result['年度']):raise ExcelError('年度或粒度不合法')
    # 主体/情景编码只允许字母数字下划线连字符、长度 1..64：它要作为 groupKey 的一部分
    # 和落库目录名，出现斜杠、空格、全角字符会直接破坏下游分组与文件命名。
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',result['主体编码']) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',result['情景编码']):raise ExcelError('主体/情景编码不合法')
    year=result['年度']
    # 生效周期、已结账截至必须是「批次年度-月份」且月为 01..12：这两个字段决定
    # 数据从哪个月起算、以及已结账期间锁止的边界，跨年或写成 2027-13 都会被退回。
    for k in ('生效周期','已结账截至'):
        if not re.fullmatch(year+r'-(0[1-9]|1[0-2])',result[k]):raise ExcelError(k+'须为本年月度')
    return result

# ---------------------------------------------------------------- 表头层
# 表头校验是「列序契约」：模板列序不可调整，用户只能填数据行。
def headers(book,sheet,expected):
    """逐列比对第 1 行表头，并检测表头行里的额外列。

    参数：book；sheet；expected=列名元组（顺序即列号 1..n）。
    返回：无（仅校验）。
    异常：第 i 列不符 ->「{sheet}表头第 i 列错误」；
          表头行出现白名单外的列 ->「{sheet}表头存在额外字段」。
    """
    for i,title in enumerate(expected,1):
        if book.value(sheet,col(i)+'1')!=title:raise ExcelError(f'{sheet}表头第 {i} 列错误')
    # 额外字段检测：找出所有「第 1 行」的列坐标，扣掉白名单长度后的列，非空即判越界。
    # 只扫第 1 行是为了不被数据行里的坐标误伤；目的是禁掉用户自己加列（加了也没人读）。
    if any(re.match(r'[A-Z]+1$',r) and r not in {col(i)+'1' for i in range(1,len(expected)+1)} for r in book.cells[sheet]):
        raise ExcelError(sheet+'表头存在额外字段')

# ---------------------------------------------------------------- 数据行层
# body_rows 是两套外部模板唯一的数据行迭代器：返回 (行号, 行值列表)，
# 空行（整行都没有值）跳过，行号留给报错文案定位。
def body_rows(book,sheet,columns):
    """按行号升序产出 (行号, 该行前 columns 列的值列表)。

    参数：book；sheet；columns=本表契约列数（INDUSTRY 18 / EVENT 15 / IMPACT 8）。
    返回：生成器，逐行 yield (int 行号, list[值])，全空行自动跳过。
    异常：行数超过 3000 或最大行号超过 5000 ->「{sheet}行数超限」。
    """
    seen=set()
    for ref in book.cells[sheet]:
        m=re.fullmatch(r'([A-Z]+)(\d+)',ref)
        if m and int(m[2])>=2:seen.add(int(m[2]))
    # 防呆上限：工作簿单元格数已被 xlsx_reader 限制，这里再卡「行数 3000 / 最大行号 5000」
    # 是为了挡住「用户在 4000 行处误粘一堆空格式」导致迭代和报错行号失控的情况。
    if len(seen)>3000 or max(seen,default=1)>5000:raise ExcelError(sheet+'行数超限')
    for r in sorted(seen):
        row=[book.value(sheet,f'{col(c)}{r}') for c in range(1,columns+1)]
        if not any(x is not None and str(x).strip() for x in row):continue
        # 逐行 yield 而不是一次性 list：合并单元的补充值已经在 Book.value() 里处理过，
        # 这里只要「整行都空就跳过」，避免空行被当成数据行触发必填报错。
        yield r,row

# ---------------------------------------------------------------- 周期层
# 统计周期/影响周期/生效周期三类字段共用一套正则：形态跟着批次粒度走。
def period(value,year,grain):
    """校验统计周期字符串并与批次年度、粒度对齐。

    参数：value=待校验文本；year=批次年度（四位）；grain='月度' 或 '季度'。
    返回：原样返回 value（通过校验后）。
    异常：非文本 ->「统计周期须为文本」；形态不符 ->「统计周期与批次年度或期间粒度不符」。
    """
    if not isinstance(value,str):raise ExcelError('统计周期须为文本')
    pat=year+r'-(0[1-9]|1[0-2])' if grain=='月度' else year+r'-Q[1-4]'
    if not re.fullmatch(pat,value):raise ExcelError('统计周期与批次年度或期间粒度不符')
    return value

def period_end_month(value):
    """把周期折算成「该周期的最后一个月」（1..12）。

    参数：value='2027-05' 或 '2027-Q2'。
    返回：月度取月末两位数字；季度取 Qn*3（Q1->3、Q4->12）。
    用途：判断「生效周期是否晚于发生月份」「影响周期是否落在事件区间内」。
    """
    return int(value[-2:]) if '-Q' not in value else int(value[-1])*3

# ---------------------------------------------------------------- 八字段组装层
# records() 把外部模板行拼成八字段 CSV，再交给 data_ingest.daoru_csv 做权威清洗，
# 这样「外部模板」与「12 表版式」最终走的是同一条入库管道，拒绝码口径统一。
def records(rows):
    """把八字段行转成 daoru_csv 的解析结果 + 原始 CSV 文本。

    参数：rows=每行按 BIXU_LIE 顺序排好的值列表。
    返回：(dict 形式的结果（含 rens/shuju/jujue/ruku_shu 等）, CSV 文本)；
          CSV 文本随结果返回，便于退回收据里原样展示用户填了什么。
    异常：任一八字段转换失败 ->「八字段内部转换失败：<首个拒绝原因>」。
    """
    buf=io.StringIO();w=csv.writer(buf);w.writerow(BIXU_LIE);w.writerows(rows)
    parsed=daoru_csv(buf.getvalue())
    # 只取 jujue[0].yuanyin 拼文案：退回收据面向用户，给首个拒绝原因最有效；
    # 完整拒绝清单留在返回的 jujue 列表里，供调用方逐条展示。
    if parsed.jujue:raise ExcelError('八字段内部转换失败：'+parsed.jujue[0].yuanyin)
    data=dataclasses.asdict(parsed);data['ruku_shu']=parsed.ruku_shu
    return data,buf.getvalue()

# ---------------------------------------------------------------- 结果外壳层
# 两套外部模板共用同一套返回外壳（字段名与 12 表/九表轨道保持一致），
# excel_ingest_v11.import_excel_v11 才能不分支地消费。
def common_meta_result(m,kind,records_data,body,**extra):
    """组装两套外部模板共用的返回 dict。

    参数：m=meta() 的元字段；kind=数据类别；records_data=records() 的解析结果；
          body=records() 的 CSV 文本；**extra 由 industry()/changes() 追加
          benchmarks / procurement / events / eventLedger / impacts 等专属字段。
    返回：dict——records / metadata / category / groupKey / scope / simulation /
          subjects / checks / text。subjects 恒为 []（外部模板不产生科目行）。
    """
    year=m['年度'];grain=m['期间粒度'];closed=m['已结账截至']
    # groupKey 固定四元组 [主体编码, 情景编码, 年度, 粒度]：同一主体同一情景同一期间
    # 的多份外部文件落到同一分组，后续按 groupKey 合并分析。
    return {'records':records_data,'metadata':m,'category':kind,'groupKey':json.dumps([m['主体编码'],m['情景编码'],year,grain],ensure_ascii=False),
            # scope.period 的取法：月度 = 已结账截至原样；季度 = 年度 + Q(已结账月份/3 取整)，
            # 例如已结账截至 2027-11 -> 2027-Q3；这是「分析截至期」的对外口径。
            'scope':{'cycle':grain,'period':closed if grain=='月度' else year+'-Q'+str(int(closed[-2:])//3)},
            'simulation':m['数据状态']=='占位','subjects':[],'checks':0,'text':body,**extra}

# ---------------------------------------------------------------- 行业对标模板
# 版式：批次信息 + 基准指标（两表）。基准指标一行 = 某指标某期间的一条行业基准，
# 只有 生效标记=是 的行才进入 benchmarks 与八字段记录；否 是留档（历史来源）。
def industry(data):
    """解析行业对标模板，返回统一外壳 + benchmarks。

    参数：data=xlsx 字节流。
    返回：dict——records / metadata / category='行业对标' / groupKey / scope /
          simulation / benchmarks（18 列原始值 + 参考值字符串）/ procurement=[] / events=[]。
    异常：表序列、表头、指标编码名称、单位、性质、适用主体情景、URL 与口径、
          重复生效来源、空表——均为 ExcelError，文案见各校验点。
    """
    book=Book(data);m=meta(book,'行业对标');headers(book,'基准指标',INDUSTRY)
    items=[];rows=[];active=set();seen=set()
    for r,_ in body_rows(book,'基准指标',len(INDUSTRY)):
        s='基准指标';coord=lambda c:f'{col(c)}{r}'
        # 第 1-2 列先取指标编码与名称：编码必须在 METRICS 白名单里、名称必须与白名单
        # 完全一致，否则这一行既无法进入分析、也无法解释成哪个口径，直接退回。
        code=text(book,s,coord(1));name=text(book,s,coord(2))
        # 编码与名称成对校验（不是只看编码）：用户可能填了合法编码却配了自造名称，
        # 那会把口径解释权交给用户，破坏「指标名称即口径」的纪律。
        if code not in METRICS or name!=METRICS[code]:raise ExcelError(f'基准指标第 {r} 行指标编码/名称错误')
        p=period(text(book,s,coord(3)),m['年度'],m['期间粒度'])
        # 第 4 列参考值走 Book.number() 拿 Decimal（公式会被受限求值），第 5 列单位必须 %。
        value=book.number(s,coord(4));unit=text(book,s,coord(5))
        # 本版行业指标统一用百分数表达，原材料指数也要求以「基期=100%」的百分点填写；
        # 这样下游只需一套「比率整数基点」换算，不必按指标类型分支。
        if unit!='%':raise ExcelError('行业指标本版统一用 %（原材料指数以基期100%表达）')
        nature=text(book,s,coord(6));scope=text(book,s,coord(7));sample=text(book,s,coord(8));definition=text(book,s,coord(9))
        agency=text(book,s,coord(10));source=text(book,s,coord(11));released=date(book,s,coord(12))
        limit=text(book,s,coord(13));entity=text(book,s,coord(14));scenario=text(book,s,coord(15));flag=text(book,s,coord(16));updated=date(book,s,coord(17))
        note=text(book,s,coord(18),False)
        # 指标性质与生效标记的枚举白名单：性质决定要不要 URL 与口径，
        # 标记决定这行是否参与分析；两者都错会导致「真假基准混用」，必须退回。
        if nature not in ('真实','构造参考值') or flag not in ('是','否'):
            raise ExcelError('行业指标性质须真实/构造参考值，生效标记须是/否')
        # 适用主体/情景只能是「全部」或本批次自己的编码：外部模板不能替别的批次立项，
        # 否则同一份文件可能被错误套用到其他主体/情景上。
        if entity not in ('全部',m['主体编码']) or scenario not in ('全部',m['情景编码']):raise ExcelError('适用主体/情景超出批次范围')
        # 真实行业基准的可核验性最低要求：来源必须是 http(s) URL，且样本口径、行业范围、
        # 计算口径三项齐全；构造参考值不受此限，但下游会以 simulation/数据性质标注占位。
        if nature=='真实' and (not source.startswith(('http://','https://')) or not sample or not scope or not definition):raise ExcelError('真实行业基准须提供可核验URL及完整统计口径')
        key=(code,p,m['口径标记'],entity,scenario)
        # 重复生效来源：(指标, 期间, 口径标记, 主体, 情景) 五元组唯一，只对 生效标记=是 的行
        # 生效——同一口径出现两个有效来源会让基准值不可判定，故退回。
        if key in seen and flag=='是':raise ExcelError('同口径指标存在重复生效来源')
        if flag=='是':seen.add(key)
        # benchmarks 保留 18 列原始值（含 Decimal/None），前端展示与复核用；
        # 其中参考值单独用 str 覆盖，便于 JSON 序列化。
        item={k:book.value(s,coord(i)) for i,k in enumerate(INDUSTRY,1)};item['参考值']=str(value);items.append(item)
        if flag=='是':
            # 八字段只有「数值+单位」，没有符号位：负值改写成「绝对值 + 方向=下降」，
            # 正负口径放在 meta_note 的 原值符号 里，避免下游对负百分数做二次解释。
            if value<0:direction='下降'
            else:direction='上升'
            # meta_note 把「这行基准凭什么是这个值」压成备注 JSON：性质、口径、样本、发布机构、
            # 发布日期、数据版本号、口径标记、适用范围——审计追溯全靠它，不完整就别想入选。
            meta_note={'指标编码':code,'数据性质':nature,'原值符号':direction,'统计口径':definition,'样本口径':sample,
                       '行业范围':scope,'适用限制':limit,'适用主体编码':entity,'适用情景编码':scenario,'发布机构':agency,
                       '发布日期':released,'数据版本号':m['数据版本号'],'口径标记':m['口径标记'],'生效周期':m['生效周期'],'备注':note}
            # 八字段顺序：类别 / 周期 / 科目（这里放指标名）/ 数值（取绝对值、两位小数）/ 单位 /
            # 来源 / 更新时间 / 备注 JSON —— 与 BIXU_LIE 逐列对齐。
            rows.append(['行业对标',p,name,f'{abs(value):.2f}','%',source,updated,json.dumps(meta_note,ensure_ascii=False)])
    # 空表兜底：一份只有表头的文件不算「填了行业对标」，避免空数据进入分析层。
    if not items:raise ExcelError('行业对标模板没有填写指标')
    data_rows,text_body=records(rows)
    return common_meta_result(m,'行业对标',data_rows,text_body,benchmarks=items,procurement=[],events=[])

# ---------------------------------------------------------------- 经营变更模板
# 版式：批次信息 + 事件台账 + 科目影响（三表）。事件台账是「发生了什么」，
# 科目影响是「哪个科目哪个期间变多少」；只有状态与结论都为已批准的事件，
# 才会出现在 analysis_events 里被分析层消费。
def changes(data):
    """解析经营变更模板，返回统一外壳 + 事件台账/科目影响明细。

    参数：data=xlsx 字节流。
    返回：dict——records / metadata / category='经营变更' / groupKey / scope /
          simulation / benchmarks=[] / procurement=[] /
          events=analysis_events（仅已批准：kemu/period/reason/structural/eventId/code）/
          eventLedger（15 字段全量事件）/ impacts（8 字段科目影响）。
    异常：表序列、表头、事件ID、状态与结论链、科目编码、方向单位数值、
          期间越界、重复、覆盖不全——均为 ExcelError。
    """
    book=Book(data);m=meta(book,'经营变更');headers(book,'事件台账',EVENT);headers(book,'科目影响',IMPACT)
    # events 以事件ID 为键的 dict：既能判唯一性，又能让科目影响按 ID 回查事件。
    events={}
    for r,_ in body_rows(book,'事件台账',len(EVENT)):
        # required 掩码：第 5 列（结束周期）与第 9-15 列（说明、申请/审批六件套）允许空；
        # 其余列必填——这样草稿/待审批事件可以先只填基本字段，不必编造审批信息。
        s='事件台账';get=lambda c:text(book,s,f'{col(c)}{r}',required=c not in (5,9,10,11,12,13,14,15))
        event_id=get(1)
        # 事件ID 既要做主键又要拼进八字段的「数据科目」（变更/{ID}/{科目名}），
        # 所以限定字母数字下划线连字符、长度 1..64，且在本工作簿内唯一。
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',event_id) or event_id in events:raise ExcelError('事件ID非法或重复')
        start=date(book,s,f'C{r}');effective=period(get(4),m['年度'],m['期间粒度']);end=get(5)
        # 结束周期可空；填了就必须与批次年度/粒度同形态，且逻辑上不早于生效周期。
        if end:period(end,m['年度'],m['期间粒度'])
        status=get(6);source=get(7);updated=date(book,s,f'H{r}');reason=get(9)
        applicant=get(10);applied=date(book,s,f'K{r}',False);approver=get(12);approved=date(book,s,f'M{r}',False);conclusion=get(14);basis=get(15)
        # 事件状态四档、审批结论四档（含空串）：草稿/待审批允许结论为空，
        # 已批准/已驳回要求两者一致，否则审批链无法解释。
        if status not in ('草稿','待审批','已批准','已驳回') or conclusion not in ('','待审批','已批准','已驳回'):raise ExcelError('事件状态或审批结论非法')
        # 已批准事件的完整链路要求：结论必须是已批准，且申请人、申请日期、审批人、
        # 审批日期、审批依据、说明六项齐全——缺一项就退回，不许「先批后补」。
        if status=='已批准':
            if conclusion!='已批准' or not all((applicant,applied,approver,approved,basis,reason)):
                raise ExcelError('已批准事件必须补齐申请、审批与依据字段')
            # 日期先后与生效区间：审批日期不得早于申请日期；生效周期末月不得早于发生月份
            # （即「不能追认到发生月之前就生效」）。这两条是审批链的时间自洽底线。
            if approved<applied or period_end_month(effective)<int(start[5:7]):
                raise ExcelError('审批或生效日期早于申请/发生日期')
        # 已驳回事件必须写明结论也是已驳回；避免出现「已驳回但审批结论写着已批准」
        # 这种会误导分析层的矛盾状态。
        if status=='已驳回' and conclusion!='已驳回':raise ExcelError('已驳回事件的审批结论不一致')
        events[event_id]={'事件ID':event_id,'事件类型':get(2),'发生日期':start,'生效周期':effective,'结束周期':end,
                          '状态':status,'依据来源':source,'更新时间':updated,'说明':reason,'申请人':applicant,
                          '申请日期':applied,'审批人':approver,'审批日期':approved,'审批结论':conclusion,'审批依据':basis}
    # 三表齐全但没有事件行 = 空模板，直接退回，不产出空记录。
    if not events:raise ExcelError('经营变更模板没有事件')
    impacts=[];rows=[];seen=set();covered=set();analysis_events=[]
    for r,_ in body_rows(book,'科目影响',len(IMPACT)):
        # 科目影响只有第 8 列备注可空；其余（事件ID/编码/周期/方向/值/单位/结构标签）必填。
        s='科目影响';get=lambda c:text(book,s,f'{col(c)}{r}',required=c!=8)
        event_id=get(1);code=get(2);p=period(get(3),m['年度'],m['期间粒度']);direction=get(4)
        value=book.number(s,f'E{r}');unit=get(6);structural=get(7);note=get(8)
        # 两条引用完整性：事件ID 必须在本工作簿的事件台账里；科目编码必须是 algo 注册表里的
        # 预算科目（5 大类 × 二三级），否则这条变更挂不上九表任何一行。
        if event_id not in events or code not in ACCOUNT_NAMES:raise ExcelError('科目影响引用未知事件或预算科目编码')
        # 方向只收「增加/减少」，金额必须非负（符号由方向承载），单位固定「元」，
        # 结构标签只收 是/否（是 = 结构性变更，会额外触发科目结构调整的提示）。
        if direction not in ('增加','减少') or unit!='元' or value<0 or structural not in ('是','否'):
            raise ExcelError('科目影响方向、单位、数值或结构标签非法')
        # (事件, 科目, 期间) 三元组唯一：同一事件在同一科目同一期间只能有一条影响，
        # 重复即口径不明（是叠加还是替代？），必须退回。
        key=(event_id,code,p)
        if key in seen:raise ExcelError('同一事件、科目和期间重复')
        seen.add(key);covered.add(event_id)
        event=events[event_id]
        # 期间必须落在事件生效区间内（[生效周期, 结束周期]，结束周期为空视为开区间）；
        # 越界说明科目影响与事件台账互相矛盾。
        if p<event['生效周期'] or event['结束周期'] and p>event['结束周期']:raise ExcelError('科目影响期间超出事件生效区间')
        # impacts 保留 8 字段原样（值用 str 以便序列化），供前端逐条展示。
        item={'事件ID':event_id,'受影响科目编码':code,'影响周期':p,'方向':direction,'影响值':str(value),
              '单位':unit,'是否结构性':structural,'备注':note};impacts.append(item)
        # 八字段的备注 JSON 里再带上事件状态与审批结论：单看一行记录就能判可分析性，
        # 不必回查事件台账。
        encoded={'事件ID':event_id,'方向':direction,'是否结构性':structural,'状态':event['状态'],'审批结论':event['审批结论'],
                 '受影响科目编码':code,'数据版本号':m['数据版本号'],'口径标记':m['口径标记'],'生效周期':m['生效周期'],'备注':note}
        rows.append(['经营变更',p,'变更/'+event_id+'/'+ACCOUNT_NAMES[code],f'{value:.2f}','元',event['依据来源'],event['更新时间'],json.dumps(encoded,ensure_ascii=False)])
        # analysis_events 只收「状态与结论双已批准」的事件：判定链一旦消费未批的变更，
        # 会把成本/收入预测改成未经审批的口径。code 是 v1.2 新增（供 9 表轨道映射名称）。
        if event['状态']=='已批准' and event['审批结论']=='已批准':
            analysis_events.append({'kemu':ACCOUNT_NAMES[code],'period':p,'reason':event['说明'],
                                    'structural':structural=='是','eventId':event_id,'code':code})
    # 覆盖校验：每个事件至少一条科目影响。只有事件没有影响 = 无法量化的变更，
    # 留在分析层只会被静默忽略，所以这里整本退回。
    if covered!=set(events):raise ExcelError('每个事件至少需要一条科目影响')
    data_rows,text_body=records(rows)
    return common_meta_result(m,'经营变更',data_rows,text_body,benchmarks=[],procurement=[],events=analysis_events,eventLedger=list(events.values()),impacts=impacts)
