"""受限 OOXML 读取及 Decimal 公式计算；不运行宏、不访问外链、不信任缓存值。

为什么自己实现而不引第三方库：
    交付包要求零第三方依赖（openpyxl/pandas 都不随包分发），而且模板校验必须
    逐格可解释——读到的每个单元格都要能说清来自哪个部件、哪种类型。本模块只
    实现十二表模板实际用到的 OOXML 子集：共享字符串、工作表关系、单元格值、
    公式（四则运算 + 少量白名单函数）、合并单元格区间。全程 Decimal 计算，
    不用二进制浮点，避免分位误差（衡策口径：金额整数分、比率整数基点）。

坐标与定位口径：
    单元格坐标沿用 Excel 的 A1 写法（列字母 + 行号，如 P131）；绝对引用符号
    '$' 在取值前统一剥掉（$P$131 与 P131 视为同一格）。工作表按名字索引而不是
    序号，因为十二表的名字与顺序本身是契约（由 excel_contract.SHEETS 校验）。
    列字母 ↔ 列号的换算放在 excel_contract.col，公式区域展开时才延迟导入。

类型处理（与 OOXML 的 t 属性一一对应，值保留原文、不做单位换算）：
    t='s'         共享字符串（数字是 sharedStrings 下标）→ ('text', 文本)
    t='inlineStr' 内联字符串 → ('text', 文本)
    t='str'       公式的字符串结果 → ('str', 原文)
    t='e'         错误值（#REF! 等）→ ('e', 原文)，取值时直接判失败
    t='n'/缺省    数值 → ('number', Decimal(原文本))
    只有 f 节点存在时才记 ('formula', 公式原文)；空单元格不建档，取值按
    ('blank', None) 处理——不能把空格当成 0。
"""
# 仅标准库：ast/io/posixpath/re/zipfile/decimal/xml.etree——交付包不带第三方依赖
import ast
import io
import posixpath
import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET

#: OOXML 主命名空间：ET 的 find 路径里 s: 前缀即指它（读 c/f/v/is 节点用）
# 命名空间字典：把长 URI 缩成 s:，后续 find/findall 路径都带这个前缀
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

class ExcelError(ValueError):
    """模板/工作簿层面的校验失败；文案直接面向用户，接入层原样转告。"""
    pass

class Book:
    """只读工作簿：构造时一次性读入各表单元格，公式按需求值并缓存。"""

    def __init__(self,data):
        # 体积门：按原始字节数限制 28 MB（不信任压缩后尺寸，防解压炸弹）
        if len(data)>28_000_000: raise ExcelError('工作簿超过 28 MB')
        # 四张表：单元格、合并区间、求值缓存、求值栈；一律按表名分桶
        self.cells={}    # {表名: {坐标: (种类, 值)}}——构造期一次性读齐
        self.merges={}   # {表名: [合并区间 'A1:B2', ...]}——合并结构校验用
        self.cache={}    # 公式求值结果缓存 {(表名, 坐标): 值}，同一格只算一次
        self.active=set()# 正在求值的坐标集合——循环引用检测（求值栈）
        try:
            # 按内存 bytes 打开（不落临时文件）：调用方给什么字节就读什么
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=z.namelist()
                # 结构门：重名条目/条目过多/解压后总体积过大（zip 炸弹防护）
                if len(names)!=len(set(names)) or len(names)>3000 or sum(i.file_size for i in z.infolist())>80_000_000:
                    raise ExcelError('工作簿压缩包结构异常或解压后过大')
                # 宏、外链、嵌入物一律拒收：模板必须自足且不含可执行内容
                if any('externallink' in n.lower() or 'vbaproject' in n.lower() or 'embeddings/' in n.lower() for n in names):
                    raise ExcelError('模板禁止外部工作簿链接、宏及嵌入文件')
                # 工作簿关系表：rId → 部件路径（工作表名到 worksheets 部件的映射来源）
                rel={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
                strings=[]  # 共享字符串池；t='s' 单元格里的数字就是这里的下标
                if 'xl/sharedStrings.xml' in names:
                    strings=[''.join(s.itertext()) for s in ET.fromstring(z.read('xl/sharedStrings.xml'))]
                # 工作表清单：名字 + 关系 id；这里的顺序就是报告依赖的十二表顺序
                sheets=ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets',NS)
                for s in sheets:
                    name=s.attrib['name']
                    # 用关系 id 找部件路径：工作表顺序以 workbook.xml 为准，不靠文件名猜
                    target=rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                    # 归一化后强制 xl/worksheets/ 前缀：关系被改成外链或越界路径即拒收
                    part=posixpath.normpath(posixpath.join('xl',target)) if not target.startswith('/') else target.lstrip('/')
                    if not part.startswith('xl/worksheets/'): raise ExcelError('工作表关系非法')
                    tree=ET.fromstring(z.read(part));cells={}
                    # 逐格读：f 公式 / v 缓存值 / t 类型；只有无公式时缓存值才当值用
                    for c in tree.findall('.//s:c',NS):
                        f=c.find('s:f',NS);v=c.find('s:v',NS);typ=c.attrib.get('t','n');raw=v.text if v is not None else None
                        if f is not None:
                            # 公式格：只认已展开的公式文本；共享公式（f 无文本）无法独立复算，整本退回
                            if not f.text: raise ExcelError('请保存为展开公式的标准模板，不支持共享公式')
                            value=('formula',f.text)
                        elif typ=='s': value=('text',strings[int(raw)])
                        elif typ=='inlineStr': value=('text',''.join(c.find('s:is',NS).itertext()))
                        elif typ in ('str','e'): value=(typ,raw)
                        # 数值型：Decimal 直接吃原文，不经 float，分位不丢精度
                        elif raw is not None: value=('number',Decimal(raw))
                        else: continue
                        cells[c.attrib['r']]=value          # 坐标即 r 属性（A1 写法）
                    self.cells[name]=cells
                    self.merges[name]=[x.attrib['ref'] for x in tree.findall('.//s:mergeCell',NS)]
        except ExcelError: raise                             # 业务校验错误原样上抛
        except Exception as e: raise ExcelError('不是有效的标准 XLSX 工作簿') from e

    def value(self,sheet,ref):
        """取一格的原始值（公式格按需求值；结果进缓存，同一格只算一次）。"""
        key=(sheet,ref.replace('$',''))   # 剥掉绝对引用符号，$P$131 与 P131 同一格
        if key in self.cache:return self.cache[key]
        # 求值栈里再次遇到同一格 = 循环引用：给出定位串，不无限递归
        if key in self.active:raise ExcelError(f'循环公式：{sheet}!{ref}')
        if sheet not in self.cells:raise ExcelError('公式引用不存在的工作表')
        kind,val=self.cells[sheet].get(key[1],('blank',None))   # 空格按 blank 处理
        if kind=='formula':
            self.active.add(key)
            try:val=self.formula(sheet,val)
            finally:self.active.remove(key)          # 求值异常也必须出栈
        elif kind=='e':raise ExcelError(f'公式错误：{sheet}!{ref}')   # 错误值不参与计算
        # 只缓存算完的结果：异常路径不进缓存，避免把错误当成结果复用
        self.cache[key]=val
        return val

    def formula(self,sheet,formula):
        """解释并求值一条公式（白名单 AST 解释器：不 eval、不调用 Python）。"""
        # 长度/断链/外部引用/结构化引用一律拒收：模板公式只允许本簿内 A1 引用
        if len(formula)>4000 or '[' in formula or '#' in formula:raise ExcelError('公式含断链、外部引用或不支持的语法')
        # Turn only explicit A1 references into zero-argument nodes, without eval().
        refs=[]  # [(表名, 起点, 终点或'')]——sub 时追加，calc 里按 REF 序号回查
        pattern=r"(?:'([^']+)'!|([\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z_0-9]*)!)?(\$?[A-Z]{1,3}\$?\d+)(?::(\$?[A-Z]{1,3}\$?\d+))?"
        def sub(m):
            """把一处 A1 引用（可带表名、可带区域）换成 REF(序号)，并记下三元组。"""
            refs.append((m[1] or m[2] or sheet,m[3].replace('$',''),(m[4] or '').replace('$','')))
            return f'REF({len(refs)-1})'
        # 引用替换完再解析：语法树里只剩 REF(n) 与白名单运算符/函数名
        code=re.sub(pattern,sub,formula.lstrip('='))
        try: tree=ast.parse(code,mode='eval')
        except SyntaxError as e:raise ExcelError('公式语法不支持') from e
        # 复杂度门：公式节点数上限，挡住超长表达式与深层嵌套（模板远小于此）
        if sum(1 for _ in ast.walk(tree))>700:raise ExcelError('公式过于复杂')   # 节点数上限
        def numeric(v):
            """参与四则运算的值必须是数值：文本引用直接判失败，不做隐式转换。"""
            if v is None:return Decimal(0)
            if not isinstance(v,Decimal):raise ExcelError('数值公式引用文本')
            return v
        def calc(n):
            """按白名单解释 AST 节点：常量、正负号、四则、REF 与五个函数。"""
            if isinstance(n,ast.Constant) and type(n.value) in (int,float):return Decimal(str(n.value))
            if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
                v=numeric(calc(n.operand));return -v if isinstance(n.op,ast.USub) else v
            if isinstance(n,ast.BinOp):
                a,b=numeric(calc(n.left)),numeric(calc(n.right))
                if isinstance(n.op,ast.Add):return a+b
                if isinstance(n.op,ast.Sub):return a-b
                if isinstance(n.op,ast.Mult):return a*b
                if isinstance(n.op,ast.Div):
                    if b==0:raise ExcelError('公式除以零')   # 除零显式报错，不清零不掩盖
                    return a/b
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name):
                fn=n.func.id.upper()  # 函数名大小写不敏感（Excel 习惯大写，也收小写）
                if fn=='REF' and len(n.args)==1 and isinstance(n.args[0],ast.Constant):
                    s,a,b=refs[n.args[0].value]
                    if not b:return self.value(s,a)          # 单格引用：直接取值
                    def rc(x):
                        """A1 坐标 → (行号, 列号)；列字母按 26 进制折算。"""
                        m=re.fullmatch(r'([A-Z]+)(\d+)',x);c=0
                        for ch in m[1]:c=c*26+ord(ch)-64
                        return int(m[2]),c
                    from excel_contract import col    # 延迟导入：列字母换算只在区域引用时用
                    r1,c1=rc(a);r2,c2=rc(b)
                    # 区域上限 1 万格且必须正向（起点<=终点），挡住整列引用式的爆炸展开
                    if (r2-r1+1)*(c2-c1+1)>10000 or r2<r1 or c2<c1:raise ExcelError('公式范围非法')
                    return [self.value(s,f'{col(c)}{r}') for r in range(r1,r2+1) for c in range(c1,c2+1)]
                # 函数实参先各自求值：区域引用得 list，标量得 Decimal
                args=[calc(a) for a in n.args]
                # 区域参数先摊平成一维数值列表（SUM/MAX/MIN/ABS/ROUND 共用）
                flat=[numeric(v) for a in args for v in (a if isinstance(a,list) else [a]) if v is not None]
                # 白名单函数只有这五个；其余函数名落到末尾的统一报错
                if fn=='SUM':return sum(flat,Decimal(0))
                if fn=='MAX':return max(flat)
                if fn=='MIN':return min(flat)
                if fn=='ABS' and len(flat)==1:return abs(flat[0])
                if fn=='ROUND' and len(flat)==2:
                    if abs(flat[1])>10:raise ExcelError('小数位超出范围')   # 小数位上限
                    return flat[0].quantize(Decimal(10)**-int(flat[1]),rounding=ROUND_HALF_UP)
            raise ExcelError('公式只能使用模板支持的四则运算及 SUM/ROUND/MAX/MIN/ABS')
        # 兜底：递归/算术异常统一转成模板口径的失败文案（定位由调用方补）
        try:return calc(tree.body)
        except (ArithmeticError,RecursionError) as e:raise ExcelError('公式计算失败') from e

    def number(self,sheet,ref):
        """取数值格：非 Decimal 或非有限值判失败（金额位不接受空白或文本）。"""
        val=self.value(sheet,ref)
        if not isinstance(val,Decimal) or not val.is_finite():raise ExcelError(f'缺失或非法数值：{sheet}!{ref}')
        return val
