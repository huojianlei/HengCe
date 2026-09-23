"""衡策 1.0.5 唯一工作簿契约。叶子数据进入八字段，汇总只作勾稽。"""
SHEETS = ('利润表','资产负债表','现金流量表','收入非主控','收入主控','税金及附加',
          '销售费用','管理费用','蓝恐龙费用','费用表月度汇总','摊销明细','分录')
VERSION = '衡策输入模板/1.0.5'
META = ('模板版本','主体编码','主体名称','情景编码','情景名称','年度','期间粒度','数据版本号',
        '口径标记','生效周期','已结账截至','结构性变更标签','受影响科目','数据状态','生成种子','数据类别')
EXPENSES = ((4,'员工费用','工资'),(5,'员工费用','十三薪'),(6,'员工费用','离职补偿金'),
    (7,'员工费用','五险一金'),(8,'员工费用','福利费'),(9,'员工费用','招聘费'),(10,'员工费用','培训费'),
    (11,'办公费用','房租'),(12,'办公费用','物业管理费'),(13,'办公费用','汽车费用'),
    (14,'办公费用','办公费'),(15,'办公费用','办公用品'),(16,'办公费用','水电煤'),
    (17,'办公费用','咨询服务费'),(18,'办公费用','电话费'),(19,'办公费用','快递费'),
    (20,'办公费用','折旧及摊销'),(21,'差旅费','机票火车票'),(22,'差旅费','住宿费'),
    (23,'差旅费','交通费'),(24,'差旅费','差旅补贴'),(25,'业务费用','业务招待费'),
    (26,'业务费用','市内交通费'),(27,'业务费用','调研费用'),(28,'财务费用','手续费'),
    (29,'财务费用','利息收入'),(30,'财务费用','利息支出'),(31,'税金','车船税'),
    (32,'税金','印花税'),(33,'其他','其他'))
OFFSETS = {'预算基础':0,'实时经营':60}
# 每个指标的科目编码在 P 列；工作簿内唯一且预算/实际共享相同编码。
def accounts():
    result=[]
    for i,sheet in enumerate(SHEETS[6:9],1):
        for row,parent,leaf in EXPENSES:
            code=f'EXP{i}.{row:03}'
            name=f'{"其他主体费用" if i==3 else sheet}/{parent}/{leaf}'
            result.append(dict(sheet=sheet,row=row,column=3,code=code,name=name,module='费用模块',direction='成本类'))
    for i,sheet in enumerate(SHEETS[3:5],1):
        result.extend([dict(sheet=sheet,row=33,column=3,code=f'REV{i}',name=f'营业收入/{sheet}',module='收入模块',direction='收入类'),
                       dict(sheet=sheet,row=36,column=3,code=f'COGS{i}',name=f'营业成本/{sheet}',module='成本模块',direction='成本类')])
    result.append(dict(sheet='税金及附加',row=33,column=3,code='TAX',name='税金及附加',module='费用模块',direction='成本类'))
    return result

ACCOUNTS=accounts()
BENCH_HEADERS=('指标','参考值','单位','数据性质','期间','来源','统计口径','适用限制')

def col(index):
    out=''
    while index:
        index,n=divmod(index-1,26);out=chr(65+n)+out
    return out
