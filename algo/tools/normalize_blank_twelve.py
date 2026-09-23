"""清理空白下载模板的未使用颜色样式和公式数值缓存。"""
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
TAG='{'+NS+'}'

def set_color(element,color):
    element.attrib.clear()
    element.set('rgb',color)

def normalize(path):
    source=Path(path).read_bytes()
    target=Path(path).with_name(Path(path).stem+'-黑白临时.xlsx')
    with zipfile.ZipFile(Path(path),'r') as zin,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as zout:
        for name in zin.namelist():
            data=zin.read(name)
            if name=='xl/styles.xml':
                tree=ET.fromstring(data)
                for font in tree.findall('.//'+TAG+'fonts/'+TAG+'font'):
                    for color in font.findall(TAG+'color'):set_color(color,'FF000000')
                for fill in tree.findall('.//'+TAG+'fills/'+TAG+'fill'):
                    for color in fill.findall('.//'+TAG+'fgColor')+fill.findall('.//'+TAG+'bgColor'):
                        set_color(color,'FFFFFFFF')
                for border in tree.findall('.//'+TAG+'borders/'+TAG+'border'):
                    for color in border.findall('.//'+TAG+'color'):set_color(color,'FF000000')
                data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            elif name.startswith('xl/worksheets/') and name.endswith('.xml'):
                tree=ET.fromstring(data)
                for cell in tree.findall('.//'+TAG+'c'):
                    if cell.find(TAG+'f') is not None:
                        for cached in cell.findall(TAG+'v'):cell.remove(cached)
                data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            info=zipfile.ZipInfo(name,(2000,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            zout.writestr(info,data)
    target.replace(path)
    from xlsx_reader import Book
    book=Book(Path(path).read_bytes())
    hardcoded=sum(kind=='number' for cells in book.cells.values() for kind,_ in cells.values())
    if hardcoded:raise RuntimeError('空白模板仍有数值型输入')
    with zipfile.ZipFile(path) as z:
        styles=z.read('xl/styles.xml').decode('utf-8')
    if 'FF0000FF' in styles or 'FFE5EAF0' in styles:raise RuntimeError('残留蓝色或灰色样式')
    print(Path(path).name,'硬编码数值',hardcoded,'黑白样式通过')

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    for path in sys.argv[1:]:normalize(path)
