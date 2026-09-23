"""1.0.5 新增边界用例；原有测试文件不修改。"""
import io,json,sys,unittest,zipfile
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from excel_ingest import import_excel
from excel_generate import generate,rewrite
from xlsx_reader import Book,ExcelError

ROOT=Path(__file__).resolve().parents[2]
TEMPLATE=(ROOT/'desktop/templates/唯一输入模板.xlsx').read_bytes()
HASHES=json.loads((ROOT/'desktop/templates/数值黑名单哈希.json').read_text())

def alter(sheet,ref,kind,value):
    book=Book(TEMPLATE);book.cells[sheet][ref]=(kind,value)
    return rewrite(TEMPLATE,book)

class ExcelTemplateTests(unittest.TestCase):
    def test_valid(self):
        result=import_excel(TEMPLATE)
        self.assertEqual(result['checks'],452);self.assertEqual(result['records']['ruku_shu'],1710)
        self.assertEqual(len(result['subjects']),95);self.assertEqual(len(result['procurement']),24)
    def test_reproducible_bytes(self):
        a,_=generate(TEMPLATE,17,blacklist_hashes=HASHES);b,_=generate(TEMPLATE,17,blacklist_hashes=HASHES)
        self.assertEqual(a,b)
        c,_=generate(TEMPLATE,18,blacklist_hashes=HASHES);self.assertNotEqual(a,c)
    def test_quarter_sums_matching_months(self):
        _,monthly=generate(TEMPLATE,31,grain='月度',blacklist_hashes=HASHES)
        _,quarterly=generate(TEMPLATE,31,grain='季度',blacklist_hashes=HASHES)
        m=monthly['records']['yusuan'];q=quarterly['records']['yusuan']
        self.assertEqual(q[0]['shuzhi'],sum(x['shuzhi'] for x in m[:3]));self.assertEqual(len(q)*3,len(m))
    def test_arbitrary_entity_scenario(self):
        keys=set()
        for entity in ('主体甲','主体乙','主体丙'):
            _,r=generate(TEMPLATE,19,entity,'情景丙',blacklist_hashes=HASHES);keys.add(r['groupKey'])
        self.assertEqual(len(keys),3)
    def test_csv_rejected(self):
        with self.assertRaisesRegex(ExcelError,'只接收'):import_excel(b'a,b','file.csv')
    def test_wrong_zip_rejected(self):
        with self.assertRaises(ExcelError):import_excel(b'not zip')
    def test_altered_formula_rejected(self):
        with self.assertRaisesRegex(ExcelError,'计算公式被修改'):import_excel(alter('资产负债表','C63','formula','0'))
    def test_changed_heading_rejected(self):
        with self.assertRaisesRegex(ExcelError,'固定表头'):import_excel(alter('销售费用','B4','text','未知科目'))
    def test_inconsistent_metadata_rejected(self):
        with self.assertRaisesRegex(ExcelError,'不一致'):import_excel(alter('销售费用','AY2','text','E-invalid'))
    def test_negative_input_rejected(self):
        with self.assertRaises(ExcelError):import_excel(alter('收入主控','C31','number',Decimal(-1)))
    def test_input_change_recalculates(self):
        before=import_excel(TEMPLATE);book=Book(TEMPLATE)
        price=book.number('销售费用','C204');book.cells['销售费用']['C204']=('number',price*2);book.cache.clear()
        after=import_excel(rewrite(TEMPLATE,book))
        self.assertGreater(after['records']['yusuan'][0]['shuzhi'],before['records']['yusuan'][0]['shuzhi'])
        self.assertEqual(after['checks'],452)
    def test_reject_external_link(self):
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(TEMPLATE)) as src,zipfile.ZipFile(out,'w') as dest:
            for name in src.namelist():dest.writestr(name,src.read(name))
            dest.writestr('xl/externalLinks/externalLink1.xml','<externalLink/>')
        with self.assertRaisesRegex(ExcelError,'外部'):import_excel(out.getvalue())
    def test_no_python_execution(self):
        b=Book(TEMPLATE)
        with self.assertRaises(ExcelError):b.formula('利润表',"__import__('os').system('anything')")
    def test_seed_bounds(self):
        for seed in (-1,2**32,True,1.5):
            with self.assertRaises(ExcelError):generate(TEMPLATE,seed)

if __name__=='__main__':unittest.main()
