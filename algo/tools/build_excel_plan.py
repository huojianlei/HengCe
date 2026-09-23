"""从只读原件提取结构，构造脱敏公式模型；只随机输入参数。"""
import hashlib,json,random,re,sys,zipfile,posixpath
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from excel_contract import SHEETS,META,VERSION,EXPENSES,ACCOUNTS,col,BENCH_HEADERS

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def source_structure(source):
    """保守白名单：只保留标准报表科目列、费用科目和明确表头。"""
    numbers=set();texts=set();layout={};numeric_count=0;formula_count=0
    allowed=set(('日期','摘要','科目','借方','贷方','金额','数量','单价','小计','合计','行数','行次','项     目','项      目','电视剧','电影','项目名称','项目','投资比例','税率','单位','备注','成本','收入','已摊销','未摊销'))
    allowed.update(x for _,a,b in EXPENSES for x in (a,b));allowed.update(SHEETS[:8]);allowed.update(('增值税附加','三费及税金合计','资产','负债和所有者权益','年初数','期末数','期初数'))
    with zipfile.ZipFile(source) as z:
        strings=[''.join(s.itertext()) for s in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rel={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for s in ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets',NS):
            name=s.attrib['name'];target=rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            part=posixpath.normpath(posixpath.join('xl',target));tree=ET.fromstring(z.read(part))
            values={};original_formulas={}
            for c in tree.findall('.//s:c',NS):
                ref=c.attrib['r'];v=c.find('s:v',NS);f=c.find('s:f',NS);t=c.attrib.get('t')
                if f is not None:
                    formula_count+=1
                    # 原表可用的纯本表合计公式可保留，其他计算在副本明确补齐。
                    if re.fullmatch(r'SUM\([A-Z]+\d+:[A-Z]+\d+\)',f.text or '',re.I):original_formulas[ref]='='+f.text
                if v is None:continue
                if t=='s':
                    text=strings[int(v.text)].strip();texts.add(text)
                    column=re.sub(r'\d','',ref)
                    standard_report=name in SHEETS[:3] and column in (('A','E') if name=='资产负债表' else ('A',)) and int(re.sub(r'\D','',ref)) <= (40 if name!='利润表' else 23)
                    if standard_report or text in allowed:values[ref]=text
                elif t not in ('e','str','b'):
                    try:numbers.add(str(Decimal(v.text).normalize()));numeric_count+=1
                    except Exception:pass
            layout[name]={'labels':values,'merges':[c.attrib['ref'] for c in tree.findall('.//s:mergeCell',NS)],
                'columns':[dict(c.attrib) for c in tree.findall('.//s:col',NS)],'sums':original_formulas}
    # The raw blacklist lives only in memory. Deliverable evidence contains hashes and counts.
    return layout,numbers,texts,{'sourceNumericCells':numeric_count,'uniqueNumericValues':len(numbers),'sourceFormulaCells':formula_count}

def make_plan(source,seed=20260923,entity='主体甲',scenario='基础情景',grain='月度',year=2027,category='预算基础'):
    if category not in ('预算基础','实时经营'):raise ValueError('源十二表只适用于预算基础和实时经营')
    layout,blacklist,texts,evidence=source_structure(source);rng=random.Random(f'{seed}|{entity}|{scenario}|{category}')
    plan={s:{'values':dict(layout[s]['labels']),'formulas':{},'merges':layout[s]['merges'],'columns':layout[s]['columns']} for s in SHEETS}
    def val(s,a,x):plan[s]['values'][a]=x;plan[s]['formulas'].pop(a,None)
    def formula(s,a,x):plan[s]['formulas'][a]='='+x.lstrip('=');plan[s]['values'].pop(a,None)
    def input_num(s,a,low,high,precision=2):
        while True:
            x=Decimal(rng.randrange(int(low*10**precision),int(high*10**precision)))/(10**precision)
            if str(x.normalize()) not in blacklist:break
        val(s,a,float(x));return x
    metadata=[VERSION,'E-'+hashlib.sha256(entity.encode()).hexdigest()[:10],entity,
              'S-'+hashlib.sha256(scenario.encode()).hexdigest()[:10],scenario,str(year),grain,
              '演示占位-v1','模拟权责发生制',f'{year}-01',f'{year}-06','无','无','占位','种子-'+str(seed),category]
    for s in SHEETS:
        for r,(k,v) in enumerate(zip(META,metadata),1):val(s,f'AX{r}',k);val(s,f'AY{r}',v)
        val(s,'AX17','使用说明');val(s,'AY17',f'蓝色为{category}输入参数；示例数值为占位；金额单位：元')
        val(s,'AX18','计算链说明');val(s,'AY18','副本已补齐缺失计算链；原文件未修改')
    # 预算与实际用完全相同的十二表版式，分成两份文件，类别仅在元字段区分。
    for off,kind in ((0,category),):
        for s in SHEETS[6:9]:
            val(s,f'A{1+off}',s if s!='蓝恐龙费用' else '其他主体费用')
            val(s,f'C{2+off}',kind+'（月度，元）')
            for m in range(12):val(s,f'{col(m+3)}{3+off}',f'{year}-{m+1:02}')
            val(s,f'O{3+off}','小计')
            for r,parent,leaf in EXPENSES:
                val(s,f'B{r+off}',leaf)
                for m in range(12):
                    c=col(m+3);driver=200+off+r
                    if r==20:
                        formula(s,f'{c}{r+off}',f"ROUND('摊销明细'!{c}{33+off}/3,2)")
                    elif r==29:
                        # 利息收入使用独立负向财务列，避免费用叶子出现不被旧引擎接受的负数。
                        formula(s,f'{c}{r+off}','0')
                    else:
                        input_num(s,f'{c}{driver}',17.31,67.83)
                        input_num(s,f'{c}{driver+120}',2.17,8.89)
                        formula(s,f'{c}{r+off}',f'ROUND({c}{driver}*{c}{driver+120},2)')
                    val(s,f'B{driver}',leaf+'单价');val(s,f'B{driver+120}',leaf+'数量')
                formula(s,f'O{r+off}',f'SUM(C{r+off}:N{r+off})')
            for m in range(12):formula(s,f'{col(m+3)}{34+off}',f'SUM({col(m+3)}{4+off}:{col(m+3)}{33+off})')
            formula(s,f'O{34+off}',f'SUM(C{34+off}:N{34+off})')
            val(s,f'A{34+off}','合计')
        for s in SHEETS[3:5]:
            for r,label in ((30,kind+'（月度，元）'),(31,'授权单价'),(32,'授权数量'),(33,'营业收入'),(34,'单位采购成本'),(35,'采购数量'),(36,'营业成本'),(37,'采购金额（占位）')):val(s,f'B{r+off}',label)
            for m in range(12):
                c=col(m+3);val(s,f'{c}{30+off}',f'{year}-{m+1:02}')
                input_num(s,f'{c}{31+off}',1501.13,2501.97)
                input_num(s,f'{c}{32+off}',81.13,127.97)
                input_num(s,f'{c}{34+off}',537.11,829.79)
                formula(s,f'{c}{35+off}',f'{c}{32+off}')
                formula(s,f'{c}{33+off}',f'ROUND({c}{31+off}*{c}{32+off},2)')
                formula(s,f'{c}{36+off}',f'ROUND({c}{34+off}*{c}{35+off},2)')
                formula(s,f'{c}{37+off}',f'{c}{36+off}')
            for r in (33,36,37):formula(s,f'O{r+off}',f'SUM(C{r+off}:N{r+off})')
        s='摊销明细'
        for r,label in ((30,kind+'内部底稿'),(31,'摊销资产原值'),(32,'摊销月数'),(33,'本月摊销'),(34,'累计已摊销'),(35,'尚未摊销'),(36,'摊销起始日')):val(s,f'B{r+off}',label)
        input_num(s,f'C{31+off}',71237.11,99837.91);input_num(s,f'C{32+off}',37,59,0)
        val(s,f'C{36+off}',f'{year}-01-01')
        for m in range(12):
            c=col(m+3)
            if m:
                formula(s,f'{c}{31+off}',f'$C${31+off}');formula(s,f'{c}{32+off}',f'$C${32+off}')
            formula(s,f'{c}{33+off}',f'ROUND({c}{31+off}/MAX({c}{32+off},1),2)')
            formula(s,f'{c}{34+off}',f'SUM($C{33+off}:{c}{33+off})')
            formula(s,f'{c}{35+off}',f'{c}{31+off}-{c}{34+off}')
        s='税金及附加'
        for r,label in ((30,kind+'（月度，元）'),(31,'综合附加率（演示假设）'),(32,'计税收入'),(33,'税金及附加')):val(s,f'B{r+off}',label)
        input_num(s,f'C{31+off}',0.0041,0.0097,5)
        for m in range(12):
            c=col(m+3)
            formula(s,f'{c}{32+off}',f"'收入非主控'!{c}{33+off}+'收入主控'!{c}{33+off}")
            formula(s,f'{c}{33+off}',f'ROUND({c}{32+off}*$C${31+off},2)')
        # 三表模型：收付与确认同月，无存货、借款、分红；期初资本构成现金和摊销资产。
        for s in SHEETS[:3]+('费用表月度汇总',):
            val(s,f'B{60+off if s in SHEETS[:3] else 120+off}',kind+'月度勾稽')
        b=60+off
        income={61:'营业收入',62:'营业成本',63:'税金及附加',64:'销售费用',65:'管理费用',66:'其他主体费用',67:'税前利润',68:'所得税费用',69:'净利润'}
        for r,label in income.items():val('利润表',f'B{r+off}',label)
        for r,label in ((61,'货币资金'),(62,'未摊销资产'),(63,'资产总额'),(64,'负债总额'),(65,'实收资本'),(66,'累计未分配利润'),(67,'所有者权益'),(68,'负债及权益合计')):val('资产负债表',f'B{r+off}',label)
        for r,label in ((61,'净利润'),(62,'折旧摊销加回'),(63,'经营现金净流量'),(64,'投资现金净流量'),(65,'筹资现金净流量'),(66,'现金净增加'),(67,'期初现金'),(68,'期末现金')):val('现金流量表',f'B{r+off}',label)
        input_num('资产负债表',f'C{200+off}',110537.13,160739.81)
        val('资产负债表',f'B{200+off}','期初现金（投入资本）')
        input_num('利润表',f'C{200+off}',0.18317,0.23971,5)
        val('利润表',f'B{200+off}','所得税率（演示假设）')
        for m in range(12):
            c=col(m+3);p=col(m+2)
            for s in SHEETS[:3]:val(s,f'{c}{60+off}',f'{year}-{m+1:02}')
            f=lambda s,r,x:formula(s,f'{c}{r+off}',x)
            f('利润表',61,f"'收入非主控'!{c}{33+off}+'收入主控'!{c}{33+off}")
            f('利润表',62,f"'收入非主控'!{c}{36+off}+'收入主控'!{c}{36+off}")
            f('利润表',63,f"'税金及附加'!{c}{33+off}")
            for r,s in zip((64,65,66),SHEETS[6:9]):f('利润表',r,f"'{s}'!{c}{34+off}")
            f('利润表',67,f'{c}{61+off}-SUM({c}{62+off}:{c}{66+off})')
            f('利润表',68,f'ROUND(MAX({c}{67+off},0)*$C${200+off},2)')
            f('利润表',69,f'{c}{67+off}-{c}{68+off}')
            f('现金流量表',61,f"'利润表'!{c}{69+off}")
            f('现金流量表',62,'+'.join(f"'{s}'!{c}{20+off}" for s in SHEETS[6:9]))
            f('现金流量表',63,f'SUM({c}{61+off}:{c}{62+off})')
            f('现金流量表',64,'0');f('现金流量表',65,'0')
            f('现金流量表',66,f'SUM({c}{63+off}:{c}{65+off})')
            f('现金流量表',67,f"'资产负债表'!$C${200+off}" if not m else f'{p}{68+off}')
            f('现金流量表',68,f'SUM({c}{66+off}:{c}{67+off})')
            f('资产负债表',61,f"'现金流量表'!{c}{68+off}")
            # 费用端按分分摊的总和作为实际累计摊销，尾差保持在资产余额。
            f('资产负债表',62,f"'摊销明细'!$C${31+off}-SUM('现金流量表'!$C{62+off}:{c}{62+off})")
            f('资产负债表',63,f'SUM({c}{61+off}:{c}{62+off})')
            f('资产负债表',64,'0')
            f('资产负债表',65,f"$C${200+off}+'摊销明细'!$C${31+off}")
            f('资产负债表',66,f"SUM('利润表'!$C{69+off}:{c}{69+off})")
            f('资产负债表',67,f'SUM({c}{65+off}:{c}{66+off})')
            f('资产负债表',68,f'SUM({c}{64+off},{c}{67+off})')
        # 原报表表头和科目位置保留，原年度展示区域链接新月度计算链。
        outcol='C'
        for r,monthly in ((4,61),(5,62),(6,63),(7,64),(8,65),(14,67),(18,67),(19,68),(20,69)):
            formula('利润表',f'{outcol}{r}',f'SUM(C{monthly+off}:N{monthly+off})')
        formula('利润表',f'{outcol}8',f'SUM(C{65+off}:N{66+off})')
        formula('资产负债表',f'{outcol}4',f'N{61+off}');formula('资产负债表',f'{outcol}34',f'N{62+off}');formula('资产负债表',f'{outcol}40',f'N{63+off}')
        right='G'
        for r,monthly in ((29,64),(32,65),(34,65),(38,66),(39,67),(40,68)):formula('资产负债表',f'{right}{r}',f'N{monthly+off}')
        for r,monthly in ((13,63),(26,64),(36,65),(38,66)):
            formula('现金流量表',f'{outcol}{r}',f'SUM(C{monthly+off}:N{monthly+off})')
        formula('现金流量表',f'{outcol}39',f'C{67+off}');formula('现金流量表',f'{outcol}40',f'N{68+off}')
        for r,parent,leaf in EXPENSES:
            val('费用表月度汇总',f'B{r+off}',leaf)
            for m in range(12):
                c=col(m+3);formula('费用表月度汇总',f'{c}{r+off}','+'.join(f"'{s}'!{c}{r+off}" for s in SHEETS[6:9]))
            formula('费用表月度汇总',f'O{r+off}',f'SUM(C{r+off}:N{r+off})')
        for m in range(12):
            c=col(m+3);formula('费用表月度汇总',f'{c}{34+off}',f'SUM({c}{4+off}:{c}{33+off})')
        for a in ACCOUNTS:
            r=a['row']+off;s=a['sheet'];val(s,f'P{r}',a['code']);val(s,f'Q{r}',metadata[7]);val(s,f'R{r}',metadata[8]);val(s,f'S{r}',metadata[9]);val(s,f'T{r}',metadata[10]);val(s,f'U{r}','无');val(s,f'V{r}','无')
    # 分录仅作底稿；重建演示摘要避免任何原始往来对象残留。
    for c,label in zip('ABCDE',('期间','科目','借方','贷方','说明')):val('分录',f'{c}150',label)
    for m in range(12):
        c=col(m+3);r=151+m*2
        val('分录',f'A{r}',f'{year}-{m+1:02}');val('分录',f'B{r}','银行存款')
        formula('分录',f'C{r}',f"'利润表'!{c}61");formula('分录',f'D{r}','0')
        val('分录',f'B{r+1}','主营业务收入');formula('分录',f'C{r+1}','0');formula('分录',f'D{r+1}',f'C{r}')
        val('分录',f'E{r}','占位收入分录，非完整总账')
    # 行业参考由单独的《行业对标输入模板》提供，十二表只承载本类别。
    # 原件合计公式：在同一位置且数学关系完全一致时保留原文本。
    for s in SHEETS[:3]:
        val(s,'C3',f'全年{category}');val(s,'D3','非本次输入')
    val('资产负债表','G2',f'全年{category}');val('资产负债表','H2','非本次输入')
    val('利润表','C2',entity+' / '+scenario);val('利润表','F2','其他主体费用计入管理费用展示')
    retained=0
    for s in SHEETS:
        for ref,f in layout[s]['sums'].items():
            if plan[s]['formulas'].get(ref,'').upper()==f.upper():plan[s]['formulas'][ref]=f;retained+=1
    evidence['retainedExactSumFormulas']=retained
    evidence['sourceSha256']=hashlib.sha256(Path(source).read_bytes()).hexdigest()
    evidence['seed']=seed
    # No source numeric or identifying text is persisted in this plan.
    return {'sheets':plan,'metadata':dict(zip(META,metadata)),'evidence':evidence}

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    plan=make_plan(sys.argv[1],category=sys.argv[3] if len(sys.argv)>3 else '预算基础');Path(sys.argv[2]).write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(plan['evidence'],ensure_ascii=False))
