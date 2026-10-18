# -*- coding: utf-8 -*-
"""external_templates v1.2 fork——自 1.0.5 algo/external_templates.py 逐字复制。

唯一行为差异（主体企业化）：批次信息!B1 模板版本钉改双轨——老串
'衡策/{类别}/1.0.5' 照收（1.0.5 模板与旧演示件零漂移），新串
'标准/{类别}/1.0.5' 放行（v1.2 演示产物全簿不含"衡策"字样）。
其余逻辑逐字一致；1.0.5 树全程只读。
建立：2026-10-16 ｜ Agent：ZCode（GLM-5.3）
"""
import csv
import dataclasses
import datetime as dt
import io
import json
import re
from decimal import Decimal

from data_ingest import BIXU_LIE, daoru_csv
from excel_contract import ACCOUNTS, col
from xlsx_reader import Book, ExcelError

META=('模板版本','主体编码','主体名称','情景编码','情景名称','年度','期间粒度','数据版本号',
      '口径标记','生效周期','已结账截至','结构性变更标签','受影响科目','数据状态','备注')
INDUSTRY=('指标编码','指标名称','统计周期','参考值','单位','指标性质','行业范围','样本口径','计算口径',
          '发布机构','来源标题或URL','发布日期','适用限制','适用主体编码','适用情景编码','生效标记','更新时间','备注')
EVENT=('事件ID','事件类型','发生日期','生效周期','结束周期','状态','依据来源','更新时间','说明',
       '申请人','申请日期','审批人','审批日期','审批结论','审批依据')
IMPACT=('事件ID','受影响科目编码','影响周期','方向','影响值','单位','是否结构性','备注')
METRICS={'GROSS_MARGIN':'行业毛利率','PROCUREMENT_COST_CHANGE':'采购成本变动率',
         'CAPACITY_UTILIZATION':'产能利用率','EXPENSE_THRESHOLD':'费用阈值','RAW_MATERIAL_INDEX':'原材料指数'}
ACCOUNT_NAMES={a['code']:a['name'] for a in ACCOUNTS}

def text(book,sheet,ref,required=True):
    v=book.value(sheet,ref)
    if isinstance(v,Decimal):v=str(v)
    if v is None or str(v).strip()=='':
        if required:raise ExcelError(f'请填写 {sheet}!{ref}')
        return ''
    if not isinstance(v,str):raise ExcelError(f'{sheet}!{ref} 必须为文本')
    return v.strip()

def date(book,sheet,ref,required=True):
    v=book.value(sheet,ref)
    if v is None and not required:return ''
    if isinstance(v,Decimal):
        if int(v)!=v or v<1 or v>90000:raise ExcelError(f'{sheet}!{ref} 日期无效')
        v=(dt.datetime(1899,12,30)+dt.timedelta(days=int(v))).strftime('%Y-%m-%d')
    elif isinstance(v,str):v=v.strip()
    else:raise ExcelError(f'{sheet}!{ref} 日期无效')
    if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])-([0-2]\d|3[01])',v):raise ExcelError(f'{sheet}!{ref} 日期格式须为 YYYY-MM-DD')
    try:dt.date.fromisoformat(v)
    except ValueError as e:raise ExcelError(f'{sheet}!{ref} 日期不存在') from e
    return v

def meta(book,kind):
    expected=('批次信息','基准指标') if kind=='行业对标' else ('批次信息','事件台账','科目影响')
    if tuple(book.cells)!=expected:raise ExcelError(f'{kind}工作表名称、数量或顺序错误')
    result={}
    for i,key in enumerate(META,1):
        if book.value('批次信息',f'A{i}')!=key:raise ExcelError(f'批次信息第 {i} 行字段不符')
        result[key]=text(book,'批次信息',f'B{i}')
    if result['模板版本'] not in (f'衡策/{kind}/1.0.5', f'标准/{kind}/1.0.5'):
        raise ExcelError(f'{kind}模板版本不符')  # v1.2 双轨：老串照收、中性串放行
    if result['期间粒度'] not in ('月度','季度') or not re.fullmatch(r'20\d\d',result['年度']):raise ExcelError('年度或粒度不合法')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',result['主体编码']) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',result['情景编码']):raise ExcelError('主体/情景编码不合法')
    year=result['年度']
    for k in ('生效周期','已结账截至'):
        if not re.fullmatch(year+r'-(0[1-9]|1[0-2])',result[k]):raise ExcelError(k+'须为本年月度')
    return result

def headers(book,sheet,expected):
    for i,title in enumerate(expected,1):
        if book.value(sheet,col(i)+'1')!=title:raise ExcelError(f'{sheet}表头第 {i} 列错误')
    if any(re.match(r'[A-Z]+1$',r) and r not in {col(i)+'1' for i in range(1,len(expected)+1)} for r in book.cells[sheet]):
        raise ExcelError(sheet+'表头存在额外字段')

def body_rows(book,sheet,columns):
    seen=set()
    for ref in book.cells[sheet]:
        m=re.fullmatch(r'([A-Z]+)(\d+)',ref)
        if m and int(m[2])>=2:seen.add(int(m[2]))
    if len(seen)>3000 or max(seen,default=1)>5000:raise ExcelError(sheet+'行数超限')
    for r in sorted(seen):
        row=[book.value(sheet,f'{col(c)}{r}') for c in range(1,columns+1)]
        if not any(x is not None and str(x).strip() for x in row):continue
        yield r,row

def period(value,year,grain):
    if not isinstance(value,str):raise ExcelError('统计周期须为文本')
    pat=year+r'-(0[1-9]|1[0-2])' if grain=='月度' else year+r'-Q[1-4]'
    if not re.fullmatch(pat,value):raise ExcelError('统计周期与批次年度或期间粒度不符')
    return value

def period_end_month(value):
    return int(value[-2:]) if '-Q' not in value else int(value[-1])*3

def records(rows):
    buf=io.StringIO();w=csv.writer(buf);w.writerow(BIXU_LIE);w.writerows(rows)
    parsed=daoru_csv(buf.getvalue())
    if parsed.jujue:raise ExcelError('八字段内部转换失败：'+parsed.jujue[0].yuanyin)
    data=dataclasses.asdict(parsed);data['ruku_shu']=parsed.ruku_shu
    return data,buf.getvalue()

def common_meta_result(m,kind,records_data,body,**extra):
    year=m['年度'];grain=m['期间粒度'];closed=m['已结账截至']
    return {'records':records_data,'metadata':m,'category':kind,'groupKey':json.dumps([m['主体编码'],m['情景编码'],year,grain],ensure_ascii=False),
            'scope':{'cycle':grain,'period':closed if grain=='月度' else year+'-Q'+str(int(closed[-2:])//3)},
            'simulation':m['数据状态']=='占位','subjects':[],'checks':0,'text':body,**extra}

def industry(data):
    book=Book(data);m=meta(book,'行业对标');headers(book,'基准指标',INDUSTRY)
    items=[];rows=[];active=set();seen=set()
    for r,_ in body_rows(book,'基准指标',len(INDUSTRY)):
        s='基准指标';coord=lambda c:f'{col(c)}{r}'
        code=text(book,s,coord(1));name=text(book,s,coord(2))
        if code not in METRICS or name!=METRICS[code]:raise ExcelError(f'基准指标第 {r} 行指标编码/名称错误')
        p=period(text(book,s,coord(3)),m['年度'],m['期间粒度'])
        value=book.number(s,coord(4));unit=text(book,s,coord(5))
        if unit!='%':raise ExcelError('行业指标本版统一用 %（原材料指数以基期100%表达）')
        nature=text(book,s,coord(6));scope=text(book,s,coord(7));sample=text(book,s,coord(8));definition=text(book,s,coord(9))
        agency=text(book,s,coord(10));source=text(book,s,coord(11));released=date(book,s,coord(12))
        limit=text(book,s,coord(13));entity=text(book,s,coord(14));scenario=text(book,s,coord(15));flag=text(book,s,coord(16));updated=date(book,s,coord(17))
        note=text(book,s,coord(18),False)
        if nature not in ('真实','构造参考值') or flag not in ('是','否'):
            raise ExcelError('行业指标性质须真实/构造参考值，生效标记须是/否')
        if entity not in ('全部',m['主体编码']) or scenario not in ('全部',m['情景编码']):raise ExcelError('适用主体/情景超出批次范围')
        if nature=='真实' and (not source.startswith(('http://','https://')) or not sample or not scope or not definition):raise ExcelError('真实行业基准须提供可核验URL及完整统计口径')
        key=(code,p,m['口径标记'],entity,scenario)
        if key in seen and flag=='是':raise ExcelError('同口径指标存在重复生效来源')
        if flag=='是':seen.add(key)
        item={k:book.value(s,coord(i)) for i,k in enumerate(INDUSTRY,1)};item['参考值']=str(value);items.append(item)
        if flag=='是':
            if value<0:direction='下降'
            else:direction='上升'
            meta_note={'指标编码':code,'数据性质':nature,'原值符号':direction,'统计口径':definition,'样本口径':sample,
                       '行业范围':scope,'适用限制':limit,'适用主体编码':entity,'适用情景编码':scenario,'发布机构':agency,
                       '发布日期':released,'数据版本号':m['数据版本号'],'口径标记':m['口径标记'],'生效周期':m['生效周期'],'备注':note}
            rows.append(['行业对标',p,name,f'{abs(value):.2f}','%',source,updated,json.dumps(meta_note,ensure_ascii=False)])
    if not items:raise ExcelError('行业对标模板没有填写指标')
    data_rows,text_body=records(rows)
    return common_meta_result(m,'行业对标',data_rows,text_body,benchmarks=items,procurement=[],events=[])

def changes(data):
    book=Book(data);m=meta(book,'经营变更');headers(book,'事件台账',EVENT);headers(book,'科目影响',IMPACT)
    events={}
    for r,_ in body_rows(book,'事件台账',len(EVENT)):
        s='事件台账';get=lambda c:text(book,s,f'{col(c)}{r}',required=c not in (5,9,10,11,12,13,14,15))
        event_id=get(1)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',event_id) or event_id in events:raise ExcelError('事件ID非法或重复')
        start=date(book,s,f'C{r}');effective=period(get(4),m['年度'],m['期间粒度']);end=get(5)
        if end:period(end,m['年度'],m['期间粒度'])
        status=get(6);source=get(7);updated=date(book,s,f'H{r}');reason=get(9)
        applicant=get(10);applied=date(book,s,f'K{r}',False);approver=get(12);approved=date(book,s,f'M{r}',False);conclusion=get(14);basis=get(15)
        if status not in ('草稿','待审批','已批准','已驳回') or conclusion not in ('','待审批','已批准','已驳回'):raise ExcelError('事件状态或审批结论非法')
        if status=='已批准':
            if conclusion!='已批准' or not all((applicant,applied,approver,approved,basis,reason)):
                raise ExcelError('已批准事件必须补齐申请、审批与依据字段')
            if approved<applied or period_end_month(effective)<int(start[5:7]):
                raise ExcelError('审批或生效日期早于申请/发生日期')
        if status=='已驳回' and conclusion!='已驳回':raise ExcelError('已驳回事件的审批结论不一致')
        events[event_id]={'事件ID':event_id,'事件类型':get(2),'发生日期':start,'生效周期':effective,'结束周期':end,
                          '状态':status,'依据来源':source,'更新时间':updated,'说明':reason,'申请人':applicant,
                          '申请日期':applied,'审批人':approver,'审批日期':approved,'审批结论':conclusion,'审批依据':basis}
    if not events:raise ExcelError('经营变更模板没有事件')
    impacts=[];rows=[];seen=set();covered=set();analysis_events=[]
    for r,_ in body_rows(book,'科目影响',len(IMPACT)):
        s='科目影响';get=lambda c:text(book,s,f'{col(c)}{r}',required=c!=8)
        event_id=get(1);code=get(2);p=period(get(3),m['年度'],m['期间粒度']);direction=get(4)
        value=book.number(s,f'E{r}');unit=get(6);structural=get(7);note=get(8)
        if event_id not in events or code not in ACCOUNT_NAMES:raise ExcelError('科目影响引用未知事件或预算科目编码')
        if direction not in ('增加','减少') or unit!='元' or value<0 or structural not in ('是','否'):
            raise ExcelError('科目影响方向、单位、数值或结构标签非法')
        key=(event_id,code,p)
        if key in seen:raise ExcelError('同一事件、科目和期间重复')
        seen.add(key);covered.add(event_id)
        event=events[event_id]
        if p<event['生效周期'] or event['结束周期'] and p>event['结束周期']:raise ExcelError('科目影响期间超出事件生效区间')
        item={'事件ID':event_id,'受影响科目编码':code,'影响周期':p,'方向':direction,'影响值':str(value),
              '单位':unit,'是否结构性':structural,'备注':note};impacts.append(item)
        encoded={'事件ID':event_id,'方向':direction,'是否结构性':structural,'状态':event['状态'],'审批结论':event['审批结论'],
                 '受影响科目编码':code,'数据版本号':m['数据版本号'],'口径标记':m['口径标记'],'生效周期':m['生效周期'],'备注':note}
        rows.append(['经营变更',p,'变更/'+event_id+'/'+ACCOUNT_NAMES[code],f'{value:.2f}','元',event['依据来源'],event['更新时间'],json.dumps(encoded,ensure_ascii=False)])
        if event['状态']=='已批准' and event['审批结论']=='已批准':
            analysis_events.append({'kemu':ACCOUNT_NAMES[code],'period':p,'reason':event['说明'],
                                    'structural':structural=='是','eventId':event_id})
    if covered!=set(events):raise ExcelError('每个事件至少需要一条科目影响')
    data_rows,text_body=records(rows)
    return common_meta_result(m,'经营变更',data_rows,text_body,benchmarks=[],procurement=[],events=analysis_events,eventLedger=list(events.values()),impacts=impacts)
