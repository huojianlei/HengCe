"""受限 OOXML 读取及 Decimal 公式计算；不运行宏、不访问外链、不信任缓存值。"""
import ast
import io
import posixpath
import re
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from xml.etree import ElementTree as ET

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

class ExcelError(ValueError):
    pass

class Book:
    def __init__(self,data):
        if len(data)>28_000_000: raise ExcelError('工作簿超过 28 MB')
        self.cells={};self.merges={};self.cache={};self.active=set()
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=z.namelist()
                if len(names)!=len(set(names)) or len(names)>3000 or sum(i.file_size for i in z.infolist())>80_000_000:
                    raise ExcelError('工作簿压缩包结构异常或解压后过大')
                if any('externallink' in n.lower() or 'vbaproject' in n.lower() or 'embeddings/' in n.lower() for n in names):
                    raise ExcelError('模板禁止外部工作簿链接、宏及嵌入文件')
                rel={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
                strings=[]
                if 'xl/sharedStrings.xml' in names:
                    strings=[''.join(s.itertext()) for s in ET.fromstring(z.read('xl/sharedStrings.xml'))]
                sheets=ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets',NS)
                for s in sheets:
                    name=s.attrib['name']
                    target=rel[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                    part=posixpath.normpath(posixpath.join('xl',target)) if not target.startswith('/') else target.lstrip('/')
                    if not part.startswith('xl/worksheets/'): raise ExcelError('工作表关系非法')
                    tree=ET.fromstring(z.read(part));cells={}
                    for c in tree.findall('.//s:c',NS):
                        f=c.find('s:f',NS);v=c.find('s:v',NS);typ=c.attrib.get('t','n');raw=v.text if v is not None else None
                        if f is not None:
                            if not f.text: raise ExcelError('请保存为展开公式的标准模板，不支持共享公式')
                            value=('formula',f.text)
                        elif typ=='s': value=('text',strings[int(raw)])
                        elif typ=='inlineStr': value=('text',''.join(c.find('s:is',NS).itertext()))
                        elif typ in ('str','e'): value=(typ,raw)
                        elif raw is not None: value=('number',Decimal(raw))
                        else: continue
                        cells[c.attrib['r']]=value
                    self.cells[name]=cells
                    self.merges[name]=[x.attrib['ref'] for x in tree.findall('.//s:mergeCell',NS)]
        except ExcelError: raise
        except Exception as e: raise ExcelError('不是有效的标准 XLSX 工作簿') from e

    def value(self,sheet,ref):
        key=(sheet,ref.replace('$',''))
        if key in self.cache:return self.cache[key]
        if key in self.active:raise ExcelError(f'循环公式：{sheet}!{ref}')
        if sheet not in self.cells:raise ExcelError('公式引用不存在的工作表')
        kind,val=self.cells[sheet].get(key[1],('blank',None))
        if kind=='formula':
            self.active.add(key)
            try:val=self.formula(sheet,val)
            finally:self.active.remove(key)
        elif kind=='e':raise ExcelError(f'公式错误：{sheet}!{ref}')
        self.cache[key]=val
        return val

    def formula(self,sheet,formula):
        if len(formula)>4000 or '[' in formula or '#' in formula:raise ExcelError('公式含断链、外部引用或不支持的语法')
        # Turn only explicit A1 references into zero-argument nodes, without eval().
        refs=[]
        pattern=r"(?:'([^']+)'!|([\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z_0-9]*)!)?(\$?[A-Z]{1,3}\$?\d+)(?::(\$?[A-Z]{1,3}\$?\d+))?"
        def sub(m):
            refs.append((m[1] or m[2] or sheet,m[3].replace('$',''),(m[4] or '').replace('$','')))
            return f'REF({len(refs)-1})'
        code=re.sub(pattern,sub,formula.lstrip('='))
        try: tree=ast.parse(code,mode='eval')
        except SyntaxError as e:raise ExcelError('公式语法不支持') from e
        if sum(1 for _ in ast.walk(tree))>700:raise ExcelError('公式过于复杂')
        def numeric(v):
            if v is None:return Decimal(0)
            if not isinstance(v,Decimal):raise ExcelError('数值公式引用文本')
            return v
        def calc(n):
            if isinstance(n,ast.Constant) and type(n.value) in (int,float):return Decimal(str(n.value))
            if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
                v=numeric(calc(n.operand));return -v if isinstance(n.op,ast.USub) else v
            if isinstance(n,ast.BinOp):
                a,b=numeric(calc(n.left)),numeric(calc(n.right))
                if isinstance(n.op,ast.Add):return a+b
                if isinstance(n.op,ast.Sub):return a-b
                if isinstance(n.op,ast.Mult):return a*b
                if isinstance(n.op,ast.Div):
                    if b==0:raise ExcelError('公式除以零')
                    return a/b
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name):
                fn=n.func.id.upper()
                if fn=='REF' and len(n.args)==1 and isinstance(n.args[0],ast.Constant):
                    s,a,b=refs[n.args[0].value]
                    if not b:return self.value(s,a)
                    def rc(x):
                        m=re.fullmatch(r'([A-Z]+)(\d+)',x);c=0
                        for ch in m[1]:c=c*26+ord(ch)-64
                        return int(m[2]),c
                    from excel_contract import col
                    r1,c1=rc(a);r2,c2=rc(b)
                    if (r2-r1+1)*(c2-c1+1)>10000 or r2<r1 or c2<c1:raise ExcelError('公式范围非法')
                    return [self.value(s,f'{col(c)}{r}') for r in range(r1,r2+1) for c in range(c1,c2+1)]
                args=[calc(a) for a in n.args]
                flat=[numeric(v) for a in args for v in (a if isinstance(a,list) else [a]) if v is not None]
                if fn=='SUM':return sum(flat,Decimal(0))
                if fn=='MAX':return max(flat)
                if fn=='MIN':return min(flat)
                if fn=='ABS' and len(flat)==1:return abs(flat[0])
                if fn=='ROUND' and len(flat)==2:
                    if abs(flat[1])>10:raise ExcelError('小数位超出范围')
                    return flat[0].quantize(Decimal(10)**-int(flat[1]),rounding=ROUND_HALF_UP)
            raise ExcelError('公式只能使用模板支持的四则运算及 SUM/ROUND/MAX/MIN/ABS')
        try:return calc(tree.body)
        except (ArithmeticError,RecursionError) as e:raise ExcelError('公式计算失败') from e

    def number(self,sheet,ref):
        val=self.value(sheet,ref)
        if not isinstance(val,Decimal) or not val.is_finite():raise ExcelError(f'缺失或非法数值：{sheet}!{ref}')
        return val
