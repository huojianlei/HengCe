"""四类固定 Excel 输入的行为验收，不改原有 247 项用例。"""
import io,json,sys,unittest,zipfile
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from excel_ingest import import_excel
from excel_generate import generate,combine_imports,rewrite
from external_generate import populate
from xlsx_reader import Book,ExcelError
ROOT=Path(__file__).resolve().parents[2]
TEMPLATES=ROOT/'desktop/templates'
FIXTURES=ROOT/'algo/fixtures'
HASHES=json.loads((TEMPLATES/'数值黑名单哈希.json').read_text())
def template(kind):return (TEMPLATES/f'{kind}输入模板.xlsx').read_bytes()
def fixture(kind,prefix='月度主体甲'):return (FIXTURES/f'{prefix}-{kind}.xlsx').read_bytes()
class FourInputs(unittest.TestCase):
 def test_budget_and_actual_share_exact_layout(self):
  a,b=Book(template('预算基础')),Book(template('实时经营'))
  self.assertEqual(tuple(a.cells),tuple(b.cells))
  for sheet in a.cells:
   self.assertEqual(set(a.cells[sheet]),set(b.cells[sheet]))
   self.assertEqual(a.merges[sheet],b.merges[sheet])
   self.assertEqual({r:v for r,(k,v) in a.cells[sheet].items() if k=='formula'},
                    {r:v for r,(k,v) in b.cells[sheet].items() if k=='formula'})
 def test_each_twelve_sheet_book_emits_only_its_own_category(self):
  a=import_excel(template('预算基础'));b=import_excel(template('实时经营'))
  self.assertEqual((len(a['records']['yusuan']),len(a['records']['shishi'])),(1140,0))
  self.assertEqual((len(b['records']['yusuan']),len(b['records']['shishi'])),(0,570))
  self.assertEqual(a['checks'],226);self.assertEqual(b['checks'],226)
 def test_seeded_budget_and_actual_differ_and_reproduce(self):
  a,_=generate(template('预算基础'),73,blacklist_hashes=HASHES)
  b,_=generate(template('实时经营'),73,blacklist_hashes=HASHES)
  self.assertNotEqual(a,b)
  self.assertEqual(a,generate(template('预算基础'),73,blacklist_hashes=HASHES)[0])
  self.assertEqual(b,generate(template('实时经营'),73,blacklist_hashes=HASHES)[0])
 def test_four_files_merge_without_dropping_category(self):
  items=[import_excel(fixture(k)) for k in ('预算基础','实时经营','行业对标','经营变更')]
  result=combine_imports(items)
  self.assertEqual([len(result['records'][g]) for g in ('yusuan','shishi','hangye','biangeng')],[1140,570,5,1])
  self.assertEqual(result['checks'],452)
  self.assertEqual(len(result['categories']),4)
 def test_quarter_sums_exactly_three_months(self):
  m=import_excel(fixture('预算基础'))['records']['yusuan']
  q=import_excel(fixture('预算基础','季度主体乙'))['records']['yusuan']
  # Budget values differ by entity: compare the same subject with quarter aggregation in one book.
  monthly=import_excel(generate(template('预算基础'),73,'主体乙','扩展情景','月度',HASHES)[0])['records']['yusuan']
  quarterly=import_excel(generate(template('预算基础'),73,'主体乙','扩展情景','季度',HASHES)[0])['records']['yusuan']
  self.assertEqual(quarterly[0]['shuzhi'],sum(x['shuzhi'] for x in monthly[:3]))
 def test_three_entities_are_distinct_groups(self):
  keys=set()
  for e in ('主体甲','主体乙','主体丙'):
   _,r=generate(template('预算基础'),47,e,'基础情景',blacklist_hashes=HASHES);keys.add(r['groupKey'])
  self.assertEqual(len(keys),3)
 def test_missing_real_actual_is_not_silently_zero(self):
  with self.assertRaisesRegex(ExcelError,'同时提供'):combine_imports([import_excel(template('预算基础'))])
 def test_cannot_mix_entity_or_basis(self):
  a=import_excel(fixture('预算基础'));b=import_excel(fixture('实时经营','季度主体乙'))
  with self.assertRaises(ExcelError):combine_imports([a,b])
 def test_changed_budget_formula_is_rejected(self):
  b=Book(template('预算基础'));b.cells['资产负债表']['C63']=('formula','0')
  with self.assertRaisesRegex(ExcelError,'公式被修改'):import_excel(rewrite(template('预算基础'),b))
 def test_source_xlsx_with_external_link_is_rejected(self):
  out=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(template('预算基础'))) as src,zipfile.ZipFile(out,'w') as dst:
   for name in src.namelist():dst.writestr(name,src.read(name))
   dst.writestr('xl/externalLinks/externalLink1.xml','<externalLink/>')
  with self.assertRaisesRegex(ExcelError,'外部'):import_excel(out.getvalue())
 def test_csv_and_wrong_sheets_rejected(self):
  with self.assertRaises(ExcelError):import_excel(b'a,b','data.csv')
  with self.assertRaises(ExcelError):import_excel(b'not zip','data.xlsx')
 def test_unfilled_industry_template_rejected(self):
  with self.assertRaises(ExcelError):import_excel(template('行业对标'))
 def test_industry_source_and_unique_active_choice(self):
  base=fixture('行业对标')
  self.assertEqual(len(import_excel(base)['records']['hangye']),5)
  no_url=populate(base,{'基准指标':{'F2':'真实'}})
  with self.assertRaisesRegex(ExcelError,'可核验URL'):import_excel(no_url)
  duplicate=populate(base,{'基准指标':{'A7':'GROSS_MARGIN','B7':'行业毛利率','C7':'2027-06','D7':Decimal('22.13'),
   'E7':'%','F7':'构造参考值','G7':'示意','H7':'无真实样本','I7':'演示口径','J7':'演示生成器',
   'K7':'构造','L7':'2027-06-30','M7':'仅演示','N7':'E-b5ba9f7789','O7':'S-8037e7f5de','P7':'是','Q7':'2027-06-30'}})
  with self.assertRaisesRegex(ExcelError,'重复生效'):import_excel(duplicate)
 def test_pending_change_never_implies_approval(self):
  item=import_excel(fixture('经营变更'))
  self.assertEqual(len(item['records']['biangeng']),1)
  self.assertEqual(item['events'],[])
 def test_approved_change_needs_complete_audit_trail(self):
  raw=fixture('经营变更')
  with self.assertRaisesRegex(ExcelError,'补齐申请'):import_excel(populate(raw,{'事件台账':{'F2':'已批准','N2':'已批准'}}))
  approved=populate(raw,{'事件台账':{'F2':'已批准','J2':'模拟申请人','K2':'2027-03-01',
   'L2':'模拟审批人','M2':'2027-03-02','N2':'已批准','O2':'模拟审批依据'}})
  self.assertEqual(len(import_excel(approved)['events']),1)
 def test_unknown_account_in_change_rejected(self):
  with self.assertRaisesRegex(ExcelError,'未知事件或预算科目'):import_excel(populate(fixture('经营变更'),{'科目影响':{'B2':'UNKNOWN'}}))
if __name__=='__main__':unittest.main()