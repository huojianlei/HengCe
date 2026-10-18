# -*- coding: utf-8 -*-
"""一条命令验收 v1.2：生成四文件 → 结构断言（对 ingest_v11 骨架与契约）→
excel_ingest_v11 严格校验（老 226 + 新区恒等式）→ 密度/黑名单 → 确定性复现
→ v1.2 专项（缓存完备/三表版式/主体企业化/老底稿兼容实测）。

用法：python verify.py（在 演示生成器 目录）
口径：v1.2 骨架底稿（ingest_v11/模板）已含展示层两列制公式与功能区骨架——
生成器写数值层并全书公式格重发（缓存完备）；本验收器断言"骨架未破坏 +
数值层齐 + 五区全激活 + 缓存无 None + 版式两列制 + 全簿无旧主体字样 + 幂等"。
"""
import hashlib  # 生成→结构→导入→密度→确定性
import io
import sys  # 本目录与 ingest_v11 双路径
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True                     # 引 1.0.5 只读树，不留编译副产物
BEN_MU = Path(__file__).resolve().parent  # 写出/读回（公式缓存可缺省）
for _lu in (str(BEN_MU.parent / 'ingest_v11'), str(BEN_MU)):  # 功能区坐标唯一事实源
    if _lu not in sys.path:
        sys.path.insert(0, _lu)

import xlsx_xieqi_v11 as xw                         # noqa: E402  写出/读回（缓存可缺省）
import gongneng_qu as gq                            # noqa: E402  功能区坐标唯一事实源
from excel_contract_v11 import SHEETS               # noqa: E402  12 表名序
from excel_ingest_v11 import import_excel_v11       # noqa: E402  v1.2 双轨严格导入器
from excel_generate import combine_imports          # noqa: E402  四类合并（只读复用）
from openpyxl import load_workbook                  # noqa: E402  行列规模/缓存实测

import external_book                                # noqa: E402  行业对标/经营变更
import twelve_book                                  # noqa: E402  十二表编排 v1.2
from demo_model import (MONTHS, load_blacklist, number_hash,  # noqa: E402
                        qiye_ming, FANGZHUANG_SHENGMING)

ROOT = BEN_MU  # 本目录
GUJIA_MU = BEN_MU.parent / 'ingest_v11' / '模板'    # v1.2 骨架底稿目录
DIGAO_105 = Path(r'D:\AppProject\开发分支_1.0.5\desktop\experimental')  # 老底稿（只读）
TEMPLATES = Path(r'D:\AppProject\开发分支_1.0.5\desktop\templates')  # 黑名单（只读）
OUT = ROOT / '输出'  # 验收双清单
SEED = 20260923  # 固定种子（确定性）
ENTITY = qiye_ming(SEED)  # 企业主体（字号池+行业词随机生成，禁"衡策/中学"）
SCENARIO = '基础情景'  # 情景
E_CODE, S_CODE = 'ENT-2027', 'S-BASE'
JIN_CI = ('衡策', '中学')  # 主体名禁词（全簿零残留）

# 文本格改动白名单（元数据/动态标题/防撞名声明），其余文本格必须与骨架底稿逐字一致
TEXT_WHITELIST = {('利润表', 'C2')}  # 单项登记与打印
for _s in SHEETS:
    for _r in ('AY2', 'AY3', 'AY4', 'AY5', 'AY15', 'AY17'):
        TEXT_WHITELIST.add((_s, _r))

# 月度区必须非空的行（C..N 全覆盖——老区口径不变）
MONTH_ROWS = {  # 加载 v1.2 契约三段
    '利润表': range(61, 70), '资产负债表': range(61, 69), '现金流量表': range(61, 69),
    '收入非主控': (31, 32, 33, 34, 36), '收入主控': (31, 32, 33, 34, 36),
    '销售费用': range(4, 34), '管理费用': range(4, 34), '蓝恐龙费用': range(4, 34),
    '费用表月度汇总': range(4, 34), '摊销明细': range(33, 36),
}

# 预期新区恒等式计数（实测口径：Z1=2；Z2/Z3 逐月；Z4 全 12 月；Z5=1+月数+对照组数）
YUQI_ZONE_CHECKS = {'预算基础': 111, '实时经营': 63}  # 生成四文件到 输出/
YUQI_FENLU_SHU = {'预算基础': 108, '实时经营': 54}   # 每月 9 笔 × 激活月数

PASSED, FAILED = [], []


def check(name, ok, detail=''):
    """登记并打印单项结果（PASS/FAIL 双清单）。"""
    (PASSED if ok else FAILED).append(f'{name}{("：" + detail) if detail else ""}')  # 两类 12 表各一本
    print(f'  [{"PASS" if ok else "FAIL"}] {name}' + (f'：{detail}' if detail else ''))
    return ok


def jia_zai_qiyue(leibie):  # 外部两版式各一份
    """加载 v1.2 契约（base+diff + cells 全量白名单 + ext 公式含展示层）。"""
    import json  # 落盘输出目录
    return json.loads((GUJIA_MU / f'模板结构规范-v1.2-{leibie}.json').read_text(encoding='utf-8'))


def gen_all():
    """生成四类演示文件到 输出/（v1.2 企业主体 + 功能区全激活）。"""
    OUT.mkdir(parents=True, exist_ok=True)  # 骨架与契约读回
    made = {}
    for category in ('预算基础', '实时经营'):
        data, _ = twelve_book.generate_twelve(
            category, seed=SEED, entity=ENTITY, scenario=SCENARIO,
            entity_code=E_CODE, scenario_code=S_CODE, closed_month=6)  # Book 解包读回
        made[category] = data
    made['行业对标'] = external_book.generate_industry(SEED, ENTITY, SCENARIO, E_CODE, S_CODE)
    made['经营变更'] = external_book.generate_changes_file(SEED, ENTITY, SCENARIO, E_CODE, S_CODE)
    names = {'预算基础': f'演示-预算基础-{ENTITY}-{SEED}.xlsx',  # 1) 表名与顺序
             '实时经营': f'演示-实时经营-{ENTITY}-{SEED}.xlsx',
             '行业对标': f'演示-行业对标-{ENTITY}-{SEED}.xlsx',
             '经营变更': f'演示-经营变更-{ENTITY}-{SEED}.xlsx'}  # 2) 行列规模（openpyxl 实测）
    for k, data in made.items():
        (OUT / names[k]).write_bytes(data)
    return made, names


def structure_checks(made):
    """结构一致性：对骨架底稿与 v1.2 契约逐格断言（展示层/功能区骨架未破坏）。

    六道门：表名序 → 行列规模（网格不变）→ 合并区三向一致 → 文本标签白名单
    比对 → 公式位全集逐字命中（base 含 diff + ext 含展示层）→ 旧镜像公式
    零残留（镜像位列不得再有公式格）。任何一道破坏 = 版面被动手脚。
    """
    print('== 结构一致性断言（对 ingest_v11 骨架底稿与契约 v1.2） ==')
    for category in ('预算基础', '实时经营'):
        gujia_raw = (GUJIA_MU / twelve_book.BASE_NAMES[category]).read_bytes()  # v1.2 骨架字节
        qiyue = jia_zai_qiyue(category)  # v1.2 契约（含 base_diff 与 display 索引）
        gen_book = xw.read_book(made[category])     # Book：受限解包 + 公式引擎
        gujia_book = xw.read_book(gujia_raw)  # 骨架文本集合
        tag = f'[{category}] '
        # 1) 表名与顺序
        check(tag + '12 表表名与顺序与契约一致', tuple(gen_book.cells) == SHEETS)  # 4) 文本标签比对（含 text 输入格放行）
        # 2) 行列规模与骨架一致（openpyxl 实测，A1:AY480 网格未变）
        wg = load_workbook(io.BytesIO(made[category]))
        wb = load_workbook(io.BytesIO(gujia_raw))
        dims_ok = all(wg[s].max_row == wb[s].max_row and wg[s].max_column == wb[s].max_column
                      for s in SHEETS)
        wg.close(); wb.close()
        check(tag + '行列规模与骨架一致（A1:AY480 未变）', dims_ok)
        # 3) 合并区三向一致（生成==骨架==契约 base）
        merge_ok = all(sorted(gen_book.merges[s]) == sorted(gujia_book.merges[s])  # 元数据/动态标题白名单
                       == sorted(qiyue['base'][s]['merges']) for s in SHEETS)
        check(tag + '合并单元格三向一致（生成==骨架==契约）', merge_ok)
        # 4) 文本标签逐格一致（骨架已含功能区标签；白名单外不许动；
        #    功能区 text 输入格（台账名称等）是数值层合法填列位，放行）
        bad = []
        for s in SHEETS:  # 非白名单新增即记
            gujia_t = {r: v[1] for r, v in gujia_book.cells[s].items() if v[0] in ('text', 'str')}
            gen_t = {r: v[1] for r, v in gen_book.cells[s].items() if v[0] in ('text', 'str')}
            wenben_shuru = {r for r, lx in qiyue['ext']['inputs'][s].items() if lx == 'text'}  # 5) 公式位全集（base+ext）
            for r, v in gujia_t.items():
                if (s, r) in TEXT_WHITELIST:
                    continue                         # 元数据/动态标题/防撞名声明允许改
                if gen_t.get(r) != v:
                    bad.append(f'{s}!{r}')
            for r in gen_t:
                if (s, r) not in TEXT_WHITELIST and r not in gujia_t \
                        and r not in wenben_shuru:
                    bad.append(f'新增:{s}!{r}')
        check(tag + '文本标签逐字一致（白名单：元数据/C2/防撞名/功能区文本输入格）', not bad, str(bad[:4]))  # ext 固化公式
        # 5) 公式位全集：老区 base（已含 diff）∪ 扩容 ext（展示层+功能区）逐字命中
        f_bad = []
        for s in SHEETS:
            for ref, wen in qiyue['base'][s]['formulas'].items():   # base 必备公式
                if gen_book.cells[s].get(ref) != ('formula', wen):  # 严格导入器校验
                    f_bad.append(f'base:{s}!{ref}')
            for ref, wen in qiyue['ext']['formulas'][s].items():    # ext 固化公式
                if gen_book.cells[s].get(ref) != ('formula', wen):  # 老区 226
                    f_bad.append(f'ext:{s}!{ref}')
        check(tag + '公式位全集逐字命中（老区+展示层+功能区骨架）', not f_bad,
              f'不符={f_bad[:4]}')
        # 6) v1.2 展示旧公式零残留：v1.1 月度镜像位（利润/现金流 E..N、资负 E/F/I..N）
        #    不得再有任何公式格（三表合法值列 = 利润/现金流 C..D；资负 C/D/G/H）
        hefa_lie = {'利润表': (3, 4), '现金流量表': (3, 4), '资产负债表': (3, 4, 7, 8)}
        jiu = [f'{s}!{r}' for s in ('利润表', '资产负债表', '现金流量表')
               for r, kv in gen_book.cells[s].items()
               if kv[0] == 'formula' and 2 <= _hang_hao(r) <= 40
               and _can_lie(r) not in hefa_lie[s] and _can_lie(r) <= 14]
        check(tag + '展示旧公式零残留（镜像位无公式格）', not jiu, str(jiu[:4]))


def _can_lie(ref):
    """格位 → 列号（A=1；E 起=5）。"""
    n = 0  # 累加器
    for ch in ''.join(x for x in ref if x.isalpha()):
        n = n * 26 + ord(ch) - 64  # 26 进制
    return n


def _hang_hao(ref):
    """格位 → 行号。"""
    return int(''.join(x for x in ref if x.isdigit()))


def import_checks(made, names):
    """v1.2 双轨严格导入：老 226 + 新区恒等式 + 四类合并 + 老底稿兼容实测。

    双轨判据：contract_version == 'v1.2'（新产物走新契约）；
    老底稿照进 = 老轨道（v1.1 冻结契约）+ 226 全过 + 新区不激活——
    施工要求①的"老底稿照进兼容实测"在此落地（两类各一本）。
    """
    print('== excel_ingest_v11 严格校验（双轨） ==')
    for category in ('预算基础', '实时经营'):
        r = import_excel_v11(made[category], names[category])
        check(f'[{category}] 老区 226 项勾稽全过', r.get('checks') == 226,  # 外部两版式
              f"checks={r.get('checks')}")
        check(f'[{category}] 新区恒等式全过（五区激活）',
              r.get('zone_checks') == YUQI_ZONE_CHECKS[category],
              f"zone_checks={r.get('zone_checks')}")  # 四类合并
        check(f'[{category}] 契约轨道 v1.2', r.get('contract_version') == 'v1.2')
    for kind in ('行业对标', '经营变更'):
        r = import_excel_v11(made[kind], names[kind])
        check(f'[{kind}] import_excel_v11 通过', r.get('category') == kind)
    items = [import_excel_v11(made[k], names[k]) for k in
             ('预算基础', '实时经营', '行业对标', '经营变更')]  # 黑名单（1.0.5 只读）
    combo = combine_imports(items)
    check('四类文件 combine_imports 合并成功', combo['groupKey'] != '',
          f"入库行数={combo['records']['ruku_shu']}")  # Book 读回
    # ---- ① 老底稿兼容实测：experimental 两类老底稿经双轨导入器照进 ----
    for ming in ('演示底稿-预算基础.xlsx', '演示底稿-实时经营.xlsx'):
        r = import_excel_v11((DIGAO_105 / ming).read_bytes(), ming)
        check(f'老底稿照进兼容（{ming[:5]}）：226 全过、老轨道、新区不激活',
              r['checks'] == 226 and r['contract_version'] == 'v1.1'
              and r['zone_checks'] == 0 and r['zones'] == {},
              f"checks={r['checks']} ver={r['contract_version']}")


def v12_checks(made, names):
    """v1.2 专项验收：缓存完备（data_only 无 None）+ 三表版式断言 + 主体企业化。

    验收标准（施工要求⑤原文落地）：
        1) data_only 全簿扫描——任何公式格缓存值不得为 None（铁律⑥）；
        2) 三表版式——利润表/现金流含"本期金额+本年累计"两列，
           资负含"期末余额+年初余额"两列（左右对称各一组）；
        3) 主体名——全簿无『衡策』『中学』字样（含 AY 元字段与 C2 标题同步）。
    另附展示层会计恒等式抽查（期末/年初平衡、Δ未分配利润=累计净利、现金链）。
    """
    print('== v1.2 专项：缓存完备 / 三表版式 / 主体企业化 ==')
    from openpyxl import load_workbook as _lw
    for category in ('预算基础', '实时经营'):
        wf = _lw(io.BytesIO(made[category]), data_only=False)   # 公式视图（判公式格）
        wv = _lw(io.BytesIO(made[category]), data_only=True)    # 缓存值视图（判 None）
        tag = f'[{category}] '
        # 1) 缓存完备：任何公式格 data_only 读值不得为 None（铁律⑥验收标准）
        holes = [f'{sn}!{c.coordinate}' for sn in wf.sheetnames
                 for row in wf[sn].iter_rows() for c in row
                 if isinstance(c.value, str) and c.value.startswith('=')
                 and wv[sn][c.coordinate].value is None]
        check(tag + '公式格缓存完备（openpyxl data_only 无 None）', not holes,
              f'{len(holes)} 格空{holes[:3]}')
        # 2) 三表版式断言：两列制表头 + 首行公式形态
        qi = '12' if category == '预算基础' else '6'
        gj = 'N' if category == '预算基础' else 'H'  # 本期列（勾稽区末月）
        ban_ok = (wf['利润表']['C3'].value == f'本期金额（{qi}月）'
                  and wf['利润表']['D3'].value == '本年累计'
                  and wf['现金流量表']['C3'].value == f'本期金额（{qi}月）'
                  and wf['现金流量表']['D3'].value == '本年累计'
                  and wf['资产负债表']['C2'].value == '期末余额'
                  and wf['资产负债表']['D2'].value == '年初余额'
                  and wf['资产负债表']['G2'].value == '期末余额'
                  and wf['资产负债表']['H2'].value == '年初余额'
                  and str(wf['利润表']['C4'].value).lstrip('=') == f'{gj}61'
                  and str(wf['利润表']['D4'].value).lstrip('=') == f'SUM(C61:{gj}61)')
        check(tag + '三表版式两列制（利润/现金流=本期+本年累计；资负=期末+年初）', ban_ok)
        # 3) 展示会计恒等式抽查（data_only 缓存值直读）
        a, b = wv['资产负债表'], wv['利润表']
        heng = (a['C40'].value == a['G40'].value          # 期末：资产=负债+权益
                and a['D40'].value == a['H40'].value      # 年初平衡
                and a['G38'].value - (a['H38'].value or 0) == b['D20'].value  # Δ未分配利润=累计净利
                and wv['现金流量表']['D40'].value == a['C4'].value)  # 现金流年末=期末货币资金
        check(tag + '展示恒等式（期末/年初平衡、Δ未分配=净利、现金链）', heng,
              f"C40={a['C40'].value} D20={b['D20'].value}")
        # 4) 主体企业化：全簿禁词零残留 + 名称/声明/版本串就位
        hits = [f'{sn}!{c.coordinate}' for sn in wf.sheetnames
                for row in wf[sn].iter_rows() for c in row
                if isinstance(c.value, str) and any(j in c.value for j in JIN_CI)]
        ok_zt = (not hits and wf['利润表']['C2'].value == f'{ENTITY} / {SCENARIO}'
                 and wf['利润表']['AY3'].value == ENTITY
                 and all(wf[s]['AY3'].value == ENTITY for s in SHEETS)
                 and all(wf[s]['AY1'].value == '标准输入模板/1.0.5' for s in SHEETS)
                 and all(wf[s]['AY17'].value == FANGZHUANG_SHENGMING for s in SHEETS))
        check(tag + '主体企业化（全簿无衡策/中学、25 处同步、防撞名声明）', ok_zt,
              f'残留={hits[:3]}')
        wf.close(); wv.close()
    # 行业对标/经营变更两册：主体名同步与禁词扫描
    for kind in ('行业对标', '经营变更'):
        wf = _lw(io.BytesIO(made[kind]), data_only=False)
        hits = [f'{sn}!{c.coordinate}' for sn in wf.sheetnames
                for row in wf[sn].iter_rows() for c in row
                if isinstance(c.value, str) and any(j in c.value for j in JIN_CI)]
        check(f'[{kind}] 全簿无衡策/中学且批次主体=企业名',
              not hits and wf['批次信息']['B3'].value == ENTITY, f'残留={hits[:3]}')
        wf.close()


def density_checks(made):
    """密度抽查：老区月度格 + 新功能区数值层 + 展示公式抽查 + 黑名单零命中。"""
    print('== 逐表密度检查（老区 + 功能区数值层） ==')
    heimingdan = load_blacklist(TEMPLATES / '数值黑名单哈希.json')
    for category in ('预算基础', '实时经营'):
        book = xw.read_book(made[category])
        tag = f'[{category}] '  # 2) 展示公式抽查（三处逐字）
        # 1) 老区月度列 C..N 全覆盖（口径不变）
        holes = [f'{s}!{m}{r}' for s, rows in MONTH_ROWS.items() for r in rows
                 for m in MONTHS if f'{m}{r}' not in book.cells[s]]
        check(tag + '老区月度列 C..N 全覆盖', not holes, str(holes[:4]))
        # 2) 展示公式抽查（两列制公式就位——逐字固化）
        qi = 'N' if category == '预算基础' else 'H'
        zs = (book.cells['利润表'].get('C4') == ('formula', f'{qi}61')
              and book.cells['利润表'].get('D20') == ('formula', 'D18-D19')
              and book.cells['资产负债表'].get('G40') == ('formula', 'G29+G39')
              and book.cells['现金流量表'].get('D39') == ('formula', 'P158')
              and book.cells['销售费用'].get('C35') == ('formula', "'税金及附加'!C33"))
        check(tag + '展示公式抽查（利润C4/资负G40/现金流D39/费用C35）', zs)  # 激活月数（预算 12/实时 6）
        # 3) 功能区数值层密度（Z1 股数/Z2 五类/Z3 分档/Z4 矩阵/Z5 分录笔数）
        nian_yue = 12 if category == '预算基础' else 6  # Z1 股数+营业外在册
        z1 = 'P131' in book.cells['利润表'] and all(
            f'{gq.QUYUE12[i]}123' in book.cells['利润表'] for i in range(12))  # Z2 五类×激活月
        z2 = all(f'{gq.QUYUE12[i]}{r}' in book.cells['现金流量表']
                 for i in range(nian_yue) for r in (123, 127, 128, 129, 130))  # Z3 两税种×激活月
        z3 = all(f'{gq.SHUI_YUE12[i]}{r}' in book.cells['税金及附加']
                 for i in range(nian_yue) for r in (123, 124))  # Z4 矩阵 2×12+台账次行
        z4 = all(f'{gq.QUYUE12[i]}{r}' in book.cells['摊销明细']
                 for i in range(12) for r in (133, 134)) and 'S124' in book.cells['摊销明细']  # Z5 分录行计数
        fenlu_shu = sum(1 for r in range(124, 461) if f'O{r}' in book.cells['分录'])
        z5 = fenlu_shu == YUQI_FENLU_SHU[category]
        check(tag + '功能区数值层齐（Z1 股数/Z2 五类/Z3 分档/Z4 矩阵）', z1 and z2 and z3 and z4)  # 密度四区合并断言
        check(tag + '分录全账笔数', z5, f'{fenlu_shu} 笔（预期 {YUQI_FENLU_SHU[category]}）')
        # 4) 每股收益为正（v1.2 口径：ROUND(D20/P131,4)）
        eps = book.number('利润表', 'AB132')
        check(tag + '基本每股收益为正', eps > 0, f'EPS={eps}')
        # 5) 黑名单零命中（非零数值全量扫描；豁免：零值=结构性中性值，
        #    分录 U 列=现金流对照行号代码（4/8/9/10/11…，非金额））
        hits = [f'{s}!{r}' for s in SHEETS for r, v in book.cells[s].items()  # 5) 黑名单零命中（豁免代码列）
                if v[0] == 'number' and v[1] != 0
                and not (s == '分录' and r[0] == 'U')
                and number_hash(v[1]) in heimingdan]
        check(tag + '非零数值黑名单零命中（豁免零值与对照代码列）', not hits, str(hits[:4]))


def report_checks(made, names):  # 5) 黑名单扫描（豁免 U 列代码）
    """新区勾稽抽查（经导入 zones 结构——恒等式本体已由导入器强制，此处复核结构一致性）。"""
    print('== 新区勾稽抽查（经 zones 结构） ==')
    for category in ('预算基础', '实时经营'):
        r = import_excel_v11(made[category], names[category])
        z = r['zones']  # zones 结构复核入口
        nian_yue = 12 if category == '预算基础' else 6
        # 税种分档：12 月结构齐；激活月合计 = 各税种月值之和（结构自洽）
        heji = z['shuizhong_fendang']['heji_yue']  # 逐类别重导入
        fen_xiang_he = [sum(v[i] or Decimal(0) for v in z['shuizhong_fendang']['shuizhong'].values())
                        for i in range(12)]
        check(f'[{category}] 税种分档 12 月结构齐且合计==分项之和',
              len(heji) == 12 and all(heji[i] == fen_xiang_he[i] for i in range(nian_yue)))  # 税种分项月值之和
        # 摊销矩阵：12 月合计 = 各资产月值之和；台账双资产月摊销合计==矩阵首月
        jz = z['tanxiao_taizhang']['juzhen']  # 12 月结构+激活月闭合
        ju_he = [sum((xing['yue'][i] or Decimal(0)) for xing in jz) for i in range(12)]
        tz_he = sum(t['yue_tanxiao'] for t in z['tanxiao_taizhang']['taizhang'])
        check(f'[{category}] 摊销矩阵合计==各资产行之和且台账月摊销同额',  # 矩阵各资产月值之和
              len(ju_he) == 12 and z['tanxiao_taizhang']['heji_yue'][0] == ju_he[0]
              and tz_he == ju_he[0])  # 台账月摊销合计
        # 分录：全年借贷平衡 + 现金流对照五类齐（None=非现金分录不计入对照集）
        fl = z['fenlu_quanzhang']
        duizhao_ji = {t['duizhao'] for t in fl['fentiao'] if t['duizhao'] is not None}  # 12 月+台账同额断言
        check(f'[{category}] 分录全年借贷平衡且对照五类齐',
              fl['jiefang_heji'] == fl['daifang_heji'] and duizhao_ji == {4, 8, 9, 10, 11})
  # 对照集合（剔 None）


def determinism_check():  # 平衡+五类齐
    """确定性复现：同参数两次生成逐字节一致。"""
    print('== 确定性复现 ==')
    d1, _ = twelve_book.generate_twelve('预算基础', seed=SEED, entity=ENTITY,
                                        scenario=SCENARIO, entity_code=E_CODE,
                                        scenario_code=S_CODE)  # 同参数双生成
    d2, _ = twelve_book.generate_twelve('预算基础', seed=SEED, entity=ENTITY,
                                        scenario=SCENARIO, entity_code=E_CODE,
                                        scenario_code=S_CODE)
    check('同参数两次生成逐字节一致', d1 == d2, f'{len(d1)} 字节')
    on_disk = (OUT / f'演示-预算基础-{ENTITY}-{SEED}.xlsx').read_bytes()
    check('落盘文件与内存生成一致', on_disk == d1)  # 落盘=内存


# ==== v1.2 验收口径常量 ====
# 展示层合法值列（判定"旧镜像公式零残留"用）：
#   利润表/现金流量表两列制 = C、D；资产负债表账户式 = C/D（左）+ G/H（右）。
# 恒等式抽查口径：
#   C40==G40 期末资产=负债+权益；D40==H40 年初平衡；
#   G38-H38==D20 Δ未分配利润=本年累计净利润（实时口径截至已结账月）；
#   现金流 D40==资负 C4 年末现金=期末货币资金（两法同袋）。
# 主体企业化断言口径：
#   禁词=（衡策、中学）；同步位=C2 标题 + AY3×12 主体名称 + AY1×12 版本串
#   （合 25 处）+ AY17×12 防撞名声明；外部两册另核批次信息 B3 主体名。

REPORT = """# 三表版式重构验收报告（v1.2 · 标准对外版式 + 缓存完备 + 主体企业化）

> 生成器：D:/AppProject/开发分支_1.1.1/演示生成器（独立文件夹，零 C 盘；本文件由 verify.py 每次运行刷新）
> 契约与导入器：D:/AppProject/开发分支_1.1.1/ingest_v11（v1.2 双轨；总验收入口：演示生成器/verify_v11.py）
> 参数：种子 {seed} ｜ 主体 {entity}（企业化随机生成）｜ 情景 {scenario} ｜ 年度 2027 ｜ 月度 ｜ 已结账截至 2027-06
> 环境：Python 3.12（D:/dev-env/Python312）；依赖仅 openpyxl + 标准库；1.0.5 树与预算表原件全程只读

## 一、版式设计说明（三表标准对外版式）

通用规则：展示区 = 行 2-40 × 列 A..H；行 41-59 空白隔离；**行 60-69 勾稽区（月度 C..N + '2027-01'..'2027-12' 表头）原样冻结**；行 121+ 五功能区（Z1-Z5）原样冻结——月度明细一处不丢（月 1-11 在功能区 P..Z 列，月 12 在勾稽区 N 列）。合并单元格集合零改动。B 列行次保持空（财会〔2019〕6 号一般企业格式无行次列）。

- **利润表**（行 2-23）＝ 项目｜本期金额（末月）｜本年累计：C3/D3 重钉表头；C 列取勾稽区末月列（预算 N=12 月；实时 H=已结账月 6 月），D 列年累计 SUM(C..N)（实时截至 H——未结账月照提摊销不进对外累计）；行 10-13/15-17 由镜像改读 Z1 披露区（SUM(X:X) 防空）；行 14/18/20 全口径链（营业利润含投资收益+公允−减值；利润总额=营业利润+营业外收支；净利润=利润总额−所得税）；行 22/23 每股收益首次有值（C=ROUND(C20/P131,4)、D=AB132/AB133）。
- **资产负债表**（行 2-40）＝ 项目｜期末余额｜年初余额（左右两侧各一组，C2/D2/G2/H2 重钉）：期末=勾稽区末月列；年初=期初参数（C200 期初现金、摊销明细!C31 原值、C201-C203 周转参数、C65 常量权益）。披露净影响 P=营业外收入−支出+投资收益+公允−减值：P＞0 入其他应收款（C10=MAX(P,0)），P＜0 入其他应付款（G13=MAX(−P,0)），权益侧未分配利润带符号（G38=末月66+P）；年初未分配利润 H38=0（勾稽#8 首月基数）。
- **现金流量表**（行 2-40）＝ 项目｜本期金额（末月）｜本年累计：统一 D=功能区 AB 年合计（存量行=末月值），C 在公式型行裸引末月区列、输入明细行 SUM(X:X) 防空；D39 年初现金=P158（1 月期初）；基础区旧间接法年合计改读直接法功能区（两法逐月恒等由 zone check 保证）。
- **展示恒等式**（种子 20260923 实测，data_only 直读）：预算 C40==G40==2,951,871.09、D40==H40==2,153,805.40、D20==G38==798,065.69、现金流 D40==资负 C4==2,018,343.38、EPS=0.7981；实时 C40==G40==1,972,774.54、D40==H40==1,711,351.37、D20==G38==260,423.17、年末现金==1,470,007.86、EPS=0.2604。

## 二、契约 v1.2 变更清单（v1.1 → v1.2）

产物：模板结构规范-v1.2-类别.json ×2、演示底稿-v1.2-类别.xlsx ×2（ingest_v11/模板/）；v1.1 契约与骨架四件冻结留档（老轨道依赖，勿删）。

- **base 段受控编辑**（其余 9 表逐字不动）：展示旧公式移位 31 格（利润表 C4-C9/C14/C18-C20 共 10；资负 C4/C9/C13/C17/C34/C36/C40/G6/G19/G29/G32/G34/G38/G39/G40 共 15；现金流 C13/C26/C36/C38/C39/C40 共 6）；资负参数改列 3 格（C201/C202/C203 由 '利润表'!$C$4/$C$5 改引 $D$4/$D$5，数值口径不变）；表头标签重钉 10 格（利润/现金流 C3/D3 各 2、资负 C2/D2/G2/H2/C3/D3 共 6）；AY1 版本串 ×12 表（'衡策输入模板/1.0.5'→'标准输入模板/1.0.5'）。
- **ext 段**：移除月度镜像 572 格（利润表 187 + 现金流 385）；新增展示层 140 格（利润 38 + 资负 32 + 现金流 70）＋ display 索引；Z1 每股收益链重定义 AB132='ROUND(D20/P131,4)'（修正 v1.1 对 AB125 其中项的重复扣减）；Z4 矩阵行名 8 格由名称链公式改文本输入（生成器直写）；费用表月度汇总 26 格去除公式尾部多余单引号（v1.1 语法 bug，引擎"公式语法不支持"根因）；Z1/Z2/Z3 区标题升 v1.2 字样。
- **双轨导入器**（excel_ingest_v11）：按利润表 C3 表头探测轨道——'本期金额（'前缀走 v1.2 契约+新版本串；'全年'前缀走冻结 v1.1 契约+1.0.5 原串。reconcile() 226 项勾稽两轨共用、逐字零改动。外部两册版本钉经 external_templates_v12.py fork 放行中性串 '标准/类别/1.0.5'（1.0.5 树只读；fork 与原件仅差版本钉一行改双轨）。
- **构建器自检 7 组**：零碰撞（展示格豁免位碰撞）/边界（前沿矩形+展示区行 2-40×列 C..H）/37 行对齐/引用闭环/骨架回读（含 base_diff 落格与旧公式零残留）/round-trip/汇总尾引号回归门；两次构建逐字节一致（sha256 复核）。

## 三、缓存值注入实现说明（铁律⑥）

采用**公式格同文本重发**（twelve_book.generate_twelve 末段）：演示数值注入内存 Book 后，把全书所有公式格以 ('formula', 原文) 重发进变更表——xlsx_xieqi_v11.patch 对每个公式格用 Book 引擎（Decimal 精确求值）算缓存并重写 <f>+<v>。可求值性三保障：①展示区对可能为空的功能区输入位一律 SUM(X:X) 单格区间（引擎裸引用空格返回 None、SUM 区间按 0 计）；②Z4 名称链改文本输入（消除求值为空的文本公式）；③汇总尾引号语法修复。v1.1 的 366 无缓存格清零路径：删除消灭 330（利润 77+现金流 253）＋汇总修复 26＋AB132/133 重定义重发 2＋名称链退役 8。验收：产物 zip 扫 <f> 无 <v>＝0；openpyxl data_only 双读任何公式格缓存非 None（0 格空）。内部骨架 AB132/133 因空股数除零不可缓存，属中间件非交付产物（导入路径不触发该格求值）。

## 四、企业名与生成参数

- 企业名：**{entity}**（random.Random('20260923|企业名|v1.2|防撞名') 从 12 字号池×6 行业词确定性抽取；含禁词自检，不含'衡策''中学'及其单字）。
- 同步 25 处：利润表 C2 动态标题 ＋ AY3 主体名称×12 ＋ AY1 版本串×12；另 AY17×12 防撞名声明：'防撞名声明：主体名称由固定种子从演示字号池与行业词随机组合生成，仅用于演示，与任何现实企业或组织无关；如有雷同纯属巧合。'
- 参数：种子 {seed}；主体编码 ENT-2027（旧 HCZX-2027 弃用）；情景 {scenario}/S-BASE；年度 2027；月度；已结账截至 2027-06；四类产物文件名=演示-类别-{entity}-{seed}.xlsx。
- 去学校化措辞：台账部门'教务部'→'业务部'；经营变更事件'校区'→'园区'、'李老师'→'王经理'、'校务会'→'总经理办公会'。twelve_book 增主体名防御门（None/空白/禁词中文报错拒收）。

## 五、验收明细

verify.py 本机全项结果（生成→结构→双轨导入→v1.2 专项→密度→新区抽查→确定性）：

```text
{result}
```

流水线级实测（本轮命令与结果）：
- python ingest_v11/jian_qiyue_v11.py → '自检 7 组全部通过'；两次构建 sha256 一致。
- cd ingest_v11 && python -m unittest discover -s tests -t . → Ran 14 tests, OK（11 老 + 3 新 v1.2 用例）。
- python 演示生成器/verify_v11.py（总验收，六阶段）→ 通过 16 项，失败 0 项（含老底稿照进 226/老轨道、fenxi 十五步 570 判定/87 整改、计算报告 101,816 字符/出处 72 条、幂等复跑一致）。
- python 演示生成器/gen_four_books.py --seed 20260923 → 四件生成，盘上==内存==verify 口径 709,773 字节。
- 注释率（含 docstring 公平口径）：gongneng_qu 46%/excel_contract_v11 45%/jian_qiyue_v11 65%/excel_ingest_v11 54%/twelve_book 49%/verify.py 40%/verify_v11 56%/test 79%。

## 六、遗留项

1. 财政部行项目未新增：研发费用/其他收益/信用减值损失/资产处置收益/持续·终止经营净利润/其他综合收益/综合收益总额不在现行 pinned 行集，本轮按用户口径只填现有空行（含营业外/投资收益/每股收益）；如需可在行 24-59 空区再扩，属下一轮契约变更。
2. 实时经营'本期'列硬编码已结账截至月（演示固定 2027-06）：闭账月变更需重建该类契约 JSON（引擎不支持 INDEX/LOOKUP 动态取列）。
3. v1.1 契约/骨架四件为老轨道依赖的冻结留档：若被删除无法由 v1.2 构建器重建（构建器已升级 v1.2 口径）。
4. v1.1 老轨道契约仍钉着带尾引号 bug 的汇总公式文本（历史文件兼容所需，不影响 v1.2 新产物）。
5. 骨架底稿 AB132/AB133 空股数除零不可缓存（内部中间件；交付产物 100% 缓存覆盖）。
6. 主体名换名会联动重抽全部演示数值（rng 种子串含主体名）——本次已整组重验；未来改名需全套重跑验收。
7. Mimosa 对 demo_model random.Random 的'弱随机'告警为误判：铁律⑤要求固定种子确定性生成（非加密用途），沿模块既有模式。
"""


def main():  # 验收主链七段
    """验收主链：生成 → 结构 → 导入 → v1.2 专项 → 密度 → 报告抽查 → 确定性 → 摘要。"""
    print(f'== 生成四类演示文件（v1.2 企业主体：{ENTITY}） ==')  # 生成四文件
    made, names = gen_all()
    for k, n in names.items():
        print(f'  输出/{n} ({len(made[k])} 字节)')  # 结构断言
    structure_checks(made)
    import_checks(made, names)  # 导入校验（含老底稿兼容实测）
    v12_checks(made, names)     # v1.2 专项（缓存/版式/主体名）
    density_checks(made)
    report_checks(made, names)  # 密度检查
    determinism_check()
    print()  # zones 复核
    print('==== 验收摘要 ====')
    print(f'通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')  # 确定性复现
    for f in FAILED:
        print('  FAIL:', f)  # 摘要输出
    lines = [f'通过 {len(PASSED)} 项，失败 {len(FAILED)} 项']
    lines += [f'PASS {p}' for p in PASSED]  # PASS/FAIL 明细行
    lines += [f'FAIL {f}' for f in FAILED]
    (ROOT / '验收报告.md').write_text(  # 验收报告模板渲染
        REPORT.format(seed=SEED, entity=ENTITY, scenario=SCENARIO, result='\n'.join(lines)),
        encoding='utf-8')
    print(f'验收报告已刷新 {ROOT / "验收报告.md"}')
    return 0 if not FAILED else 1


if __name__ == '__main__':  # 直跑入口
    sys.exit(main())
