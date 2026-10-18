# -*- coding: utf-8 -*-
"""契约 v1.2 构建器：老契约 + 展示区重排 → v1.2 契约 JSON 与骨架底稿。

产物（全部落本包 模板/ 目录，零 C 盘；1.0.5 与老师原件全程只读）：
    模板结构规范-v1.2-预算基础.json / 模板结构规范-v1.2-实时经营.json
        ——base 段=1.0.5 契约 + 受控 base_diff（三表展示区旧公式移位、参数
          公式改列、表头标签重钉、AY1 版本串换新）；ext 段=v1.2 展示层固化
          公式 + 功能区标签/公式/输入白名单 + display 索引；cells 段=全量
          白名单；version_pin=AY1 新版本串。
    演示底稿-v1.2-预算基础.xlsx / 演示底稿-v1.2-实时经营.xlsx
        ——experimental 老底稿 + 展示层/功能区骨架 + base_diff 物理落格
          （只加标签与固化公式，不写任何演示数值）。
    v1.1 契约与骨架在 模板/ 冻结留档：老格式文件（老底稿/v1.1 演示件）经
    双轨导入器照进（excel_ingest_v11 按 C3 表头探测轨道），互不干扰。

构建后自检（新契约自洽）：
    1) 新格与老契约 labels/formulas 零碰撞（展示格豁免 cells 位碰撞——
       展示位本就是老 cells 位置的重 occupied）；
    2) 功能区全部落在前沿矩形（行 121-480 × 列 15-41）内；展示格全部落在
       展示区（行 2-40 × 列 C..H）；费用表 35/36 固化公式行 ≤59；
    3) 现金流功能区行标签与老契约 A 列行项目逐字对齐（37 行）；
    4) 固化公式引用的每个格子都在白名单（老∪新）内；
    5) 骨架底稿回读：ext 标签/公式逐字命中、老区公式位一个不少、base_diff
       标签全部落格、被移位的展示旧公式零残留；
    6) 契约 JSON 落盘后重载复检（round-trip）；
    7) 汇总尾引号回归门：ext 公式文本不得以单引号收尾（v1.1 语法 bug）。
用法：python jian_qiyue_v11.py   （任何一项自检失败即非零退出）
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）｜ v1.2：2026-10-16
"""
import json  # 契约 JSON 读写
import os  # 环境变量覆盖 algo 路径（自足包）
import re  # 引用/格位正则
import sys  # 引导 algo 只读树
from pathlib import Path  # 路径处理

BEN_MU = Path(__file__).resolve().parent  # 本包根
sys.dont_write_bytecode = True                     # 引 algo 只读树，不留编译副产物
sys.path.insert(0, str(BEN_MU))  # 本包优先导入
# 自足包：1.0.5 的 algo 树与 desktop 契约/底稿已 vendor 进 _vendor（环境变量可覆盖）
ALGO = os.environ.get('HENGCE_ALGO_DIR') or str(BEN_MU.parent / '_vendor' / 'algo')  # 算法树
if ALGO not in sys.path:  # 幂等判断
    sys.path.insert(0, ALGO)  # 插入搜索路径
TEMPLATES_105 = BEN_MU.parent / '_vendor' / 'desktop_模板' / 'templates'  # 契约目录（vendored）
DIGAO_105 = BEN_MU.parent / '_vendor' / 'desktop_模板' / 'experimental'  # 老底稿目录（vendored）

import gongneng_qu as gq                            # noqa: E402  本包扩容定义（唯一事实源）
from excel_contract_v11 import SHEETS, V12_BANBEN, V12_MUBAN_BANBEN  # noqa: E402
import xlsx_xieqi_v11 as xw                         # noqa: E402

#: 引用解析：'利润表'!C61 / C61 / SUM(P123:AA125) 里的格位与区间
YINYONG_ZE = re.compile(r"(?:'([^']+)'!)?\$?([A-Z]{1,2})\$?(\d+)(?::\$?([A-Z]{1,2})\$?(\d+))?")  # 表引用/区间解析

# ==== base_diff 清单（v1.2 对 1.0.5 base 段的受控编辑；其余 9 表零改动）====

#: 展示区旧公式移位：从 base.formulas 删除（位置由 ext 展示公式重新占用）
BASE_YICHI_GONGSHI = {
    '利润表': ['C4', 'C5', 'C6', 'C7', 'C8', 'C9', 'C14', 'C18', 'C19', 'C20'],
    '资产负债表': ['C4', 'C9', 'C13', 'C17', 'C34', 'C36', 'C40',
                  'G6', 'G19', 'G29', 'G32', 'G34', 'G38', 'G39', 'G40'],
    '现金流量表': ['C13', 'C26', 'C36', 'C38', 'C39', 'C40'],
}

#: 资负参数公式改列：利润表 C4/C5（旧年合计列）→ D4/D5（新本年累计列）；
#: 数值口径不变（D4 年累计 == 旧 C4 年合计），实测等值。
BASE_GAIGONG_CANSHU = {
    '资产负债表': {
        'C201': "ROUND('利润表'!$D$4*45/360,2)",
        'C202': "ROUND('利润表'!$D$5*30/360,2)",
        'C203': "ROUND('利润表'!$D$5*20/360,2)",
    },
}


def col_hao(zimu):  # 列字母→列号
    """列字母 → 列号（A=1）。"""
    n = 0  # 累加器
    for ch in zimu:  # 逐字符
        n = n * 26 + ord(ch.upper()) - 64  # 26 进制累加
    return n  # 返回列号


def qu_yue_biaoqian(yue_lie):  # 月列表→表头标签
    """月列表 → {列+'122': 'N月'}（功能区表头月标签，年合计列除外）。"""
    return {f'{x}122': f'{i}月' for i, x in enumerate(yue_lie, start=1)}  # 122 行月标签


def zhuang_ext(leibie):  # ext 总装入口
    """总装 ext 段：formulas（展示+功能区固化）/ labels / inputs / zones。"""
    # ---- 功能区公式与输入（gongneng_qu 总装）----
    qu = gq.qu_zongzhuang()  # 五区元数据
    # ---- 现金流功能区行标签：从老契约 A 列逐字映射（37 行对齐）----
    # 标签不另起炉灶——逐字复用老契约 A 列行项目，保证"区行序 = 主体区行序"
    base_labels = json.loads((TEMPLATES_105 / '模板结构规范-预算基础.json')  # 老契约现金流标签
                             .read_text(encoding='utf-8'))['现金流量表']['labels']  # 取 A 列行项目
    # 区标题/项目列头/年合计列头 + 12 个月标签
    xjl_labels = {'O121': '现金流量表月度明细区（契约v1.2·直接法，行序与主体区一致）',  # 区标题
                  'O122': '项目（对应主体区行）', 'AB122': '年度合计'}  # 项目列头+年合计
    xjl_labels.update(qu_yue_biaoqian(gq.QUYUE12))  # 12 月标签
    # 主体区行 4-40 → 区行 123-159，标签逐字搬移
    for r in range(4, 41):  # 主体区 37 行
        xjl_labels[f'O{r + gq.XJL_WEIYI}'] = base_labels[f'A{r}']  # 逐字搬移到区行
    qu['xianjinliu_mingxi']['labels'] = xjl_labels  # 回填区标签
    # ---- 各区月表头标签补齐 ----
    # Z1 利润披露：月标签在 122 行（P..AA）
    qu['lirun_buchong']['labels'].update(qu_yue_biaoqian(gq.QUYUE12))  # Z1 月标签
    # Z1 区标题升 v1.2 字样（与轨道标识一致）
    qu['lirun_buchong']['labels']['O121'] = '利润表补充披露区（契约v1.2）·营业外与投资收益月度明细'
    # Z3 税种分档：月标签同样在 122 行，但月列是 Q..AB（P 列让位给分档率）
    qu['shuizhong_fendang']['labels'].update(qu_yue_biaoqian(gq.SHUI_YUE12))  # Z3 月标签（Q..AB）
    # Z4 摊销矩阵：月标签在 132 行（台账头 122 行已被台账字段占用）
    qu['tanxiao_taizhang']['labels'].update({f'{x}132': f'{i}月'  # Z4 矩阵月标签（132 行）
                                             for i, x in enumerate(gq.QUYUE12, start=1)})  # 生成器式补齐
    return qu  # 返回总装结果


def yingyong_base_diff(base, leibie):
    """把 base_diff 物理应用到 base 段（返回 (base, 标签改写表, 参数公式表)）。"""
    # 1) 展示区旧公式移位：从 base.formulas 删除（格位白名单保留——由 ext 重占）
    for biao, refs in BASE_YICHI_GONGSHI.items():
        for ref in refs:
            base[biao]['formulas'].pop(ref, None)  # 缺位容错（幂等重建）
    # 2) 资负参数公式改列（文本替换，位置不动）
    for biao, gongshi in BASE_GAIGONG_CANSHU.items():
        base[biao]['formulas'].update(gongshi)
    # 3) 标签重钉：三表展示表头（C3/D3/C2/D2/G2/H2）+ AY1 版本串（12 表）
    biaoqian = {biao: dict(wen) for biao, wen in gq.zhanshi_biaoqian(leibie).items()}
    for biao in SHEETS:
        biaoqian.setdefault(biao, {})['AY1'] = V12_MUBAN_BANBEN  # 版本串换新（主体企业化）
        base[biao]['labels'].update(biaoqian[biao])
    return base, biaoqian, BASE_GAIGONG_CANSHU


def jian_qiyue(leibie):  # 契约构建入口
    """构建一个类别的 v1.2 契约 dict（base 受控改写 + ext 总装）。"""
    # base 段：1.0.5 契约读入 → base_diff 应用（三表展示区 + 参数改列 + 标签重钉）
    base = json.loads((TEMPLATES_105 / f'模板结构规范-{leibie}.json').read_text(encoding='utf-8'))
    base, biaoqian_gai, canshu_gai = yingyong_base_diff(base, leibie)
    qu = zhuang_ext(leibie)  # ext 总装（功能区）
    zhanshi = gq.zhanshi_zongzhuang(leibie)         # 展示层（含费用表 35/36 固化公式）
    qu_gongshi_all = {}                             # 功能区公式（按表归并，供镜像剥离）
    # 四个桶：按表归并的固化公式/标签/输入白名单（+ 功能区索引 + 展示索引）
    ext_formulas = {s: {} for s in SHEETS}  # 固化公式桶
    ext_labels = {s: {} for s in SHEETS}  # 标签桶
    ext_inputs = {s: {} for s in SHEETS}  # 输入桶
    zones = {}  # 区索引桶
    display = {s: {} for s in SHEETS}  # 展示层索引桶（三表新两列制公式）
    for zid, xinxi in qu.items():  # 逐区归并
        biao = xinxi['sheet']  # 区所在表
        # 标签/公式/输入分别并入对应桶（区元数据只存格位清单）
        for ref, wen in xinxi['labels'].items():  # 标签入桶
            ext_labels[biao][ref] = wen  # 登记文本
        for ref, wen in xinxi['formulas'].items():  # 公式入桶
            ext_formulas[biao][ref] = wen  # 登记文本
            qu_gongshi_all[(biao, ref)] = wen  # 区公式索引
        for ref, leixing in xinxi['inputs'].items():  # 输入入桶
            ext_inputs[biao][ref] = leixing  # 登记类型
        zones[zid] = {'sheet': biao, 'biaiti': xinxi['biaoti'],  # 区元数据（格位清单）
                      'labels': sorted(xinxi['labels']),  # 标签清单
                      'formulas': sorted(xinxi['formulas']),  # 公式清单
                      'inputs': sorted(xinxi['inputs'])}  # 输入清单
    # 展示层并入（三表 = 新两列制；费用表/汇总 = 行 35/36 固化公式）
    SAN_BIAO = ('利润表', '资产负债表', '现金流量表')
    for biao, gongshi in zhanshi.items():  # 逐表
        for ref, wen in gongshi.items():  # 逐格
            ext_formulas[biao][ref] = wen  # 展示/固化公式入桶
            if biao in SAN_BIAO:
                display[biao][ref] = wen  # 三表展示格进 display 索引
    # 全量白名单：老 cells ∪ 新标签/公式/输入（导入器的唯一放行清单）
    cells = {}  # 全量白名单桶
    for biao in SHEETS:  # 逐表并集
        quan = set(base[biao]['cells']) | set(ext_labels[biao]) \
            | set(ext_formulas[biao]) | set(ext_inputs[biao])
        cells[biao] = sorted(quan)  # 排序固化（确定性）
    return {'version': V12_BANBEN, 'version_pin': V12_MUBAN_BANBEN,  # AY1 新版本串
            'base': base,  # 契约结构组装（base 已含受控 diff）
            'ext': {'formulas': ext_formulas, 'labels': ext_labels,
                    'inputs': ext_inputs, 'zones': zones,
                    'display': {b: sorted(v) for b, v in display.items() if v}},
            'cells': cells,  # 返回五段契约
            'diff': {'yichi': {b: sorted(r) for b, r in BASE_YICHI_GONGSHI.items()},  # 移位清单留档
                     'canshu': {b: dict(g) for b, g in BASE_GAIGONG_CANSHU.items()},
                     'biaoqian': {b: dict(w) for b, w in biaoqian_gai.items()}}}


# ==== 自检（新契约自洽）====

def zijian(qiyue, ming):  # 契约自检入口
    """契约自检：碰撞/边界/对齐/引用闭环/尾引号。返回问题清单（空=通过）。"""
    wenti = []  # 问题清单
    base = qiyue['base']
    ext = qiyue['ext']
    quanbai = {s: set(qiyue['cells'][s]) for s in SHEETS}  # 白名单快照
    for biao in SHEETS:  # 逐表
        # 1) 新格与老契约 labels/formulas 零碰撞（展示格豁免 cells 位碰撞——重占位）
        for duan, ming2 in ((ext['labels'], '标签'), (ext['formulas'], '公式'),  # 三桶查重
                            (ext['inputs'], '输入')):
            for ref in duan[biao]:  # 逐格
                zhan_shi = ref in ext['display'].get(biao, ())  # 展示格标记
                if ref in base[biao]['cells'] and not zhan_shi:  # 位碰撞（展示格豁免）
                    wenti.append(f'{ming}:{biao}!{ref} 与老契约格位碰撞（{ming2}）')  # 登记碰撞
                if ref in base[biao]['labels'] or ref in base[biao]['formulas']:  # 钉位碰撞（不豁免）
                    wenti.append(f'{ming}:{biao}!{ref} 与老契约标签/公式碰撞（{ming2}）')  # 登记碰撞
        # 2) 功能区在前沿矩形、展示格在展示区、其余固化公式行 ≤59
        for zid, qu in ext['zones'].items():  # 逐区
            if qu['sheet'] != biao:  # 非本表跳过
                continue  # 下一表
            for ref in qu['labels'] + qu['formulas'] + qu['inputs']:  # 区全部格位
                # 逐格拆行列：区格必须落在行 121-480 × 列 15-41
                hang = int(re.match(r'[A-Z]+(\d+)', ref).group(1))  # 拆行号
                lie = col_hao(re.match(r'([A-Z]+)\d+', ref).group(1))  # 拆列号
                if not (121 <= hang <= 480 and 15 <= lie <= 41):  # 前沿矩形判断
                    wenti.append(f'{ming}:功能区 {zid} {biao}!{ref} 越出前沿矩形')  # 登记越界
        for ref in ext['display'].get(biao, ()):  # 展示格边界：行 2-40 × 列 C..H
            hang = int(re.match(r'[A-Z]+(\d+)', ref).group(1))  # 拆行号
            lie = col_hao(re.match(r'([A-Z]+)\d+', ref).group(1))  # 拆列号
            if not (2 <= hang <= 40 and 3 <= lie <= 8):  # 展示区判断
                wenti.append(f'{ming}:展示格 {biao}!{ref} 越出展示区（行2-40×列C..H）')  # 登记越界
        # 其余固化公式（费用表 35/36 等）必须留在行 ≤59
        for ref in ext['formulas'][biao]:  # 非区非展示固化公式
            if any(ref in ext['zones'][z]['formulas'] and ext['zones'][z]['sheet'] == biao  # 区公式跳过
                   for z in ext['zones']):
                continue                             # 功能区公式已检
            if ref in ext['display'].get(biao, ()):  # 展示格已检
                continue
            hang = int(re.match(r'[A-Z]+(\d+)', ref).group(1))  # 拆行号
            if hang > 59:  # 展示带上限
                wenti.append(f'{ming}:固化公式 {biao}!{ref} 越出展示带（行≤59）')  # 登记越界
    # 3) 现金流功能区行标签与老契约 A 列逐字对齐（37 行）
    for r in range(4, 41):  # 37 行对齐
        ref = f'O{r + gq.XJL_WEIYI}'  # 区行格位
        yu = ext['labels']['现金流量表'].get(ref)  # 区标签
        lao = base['现金流量表']['labels'].get(f'A{r}')  # 老契约标签
        if yu != lao:  # 不一致
            wenti.append(f'{ming}:现金流功能区 {ref} 标签与老契约 A{r} 不对齐')  # 登记不对齐
    # 4) 固化公式引用闭环：每个被引格都在白名单内
    for biao in SHEETS:  # 引用闭环
        for ref, wen in ext['formulas'][biao].items():  # 逐公式
            for m in YINYONG_ZE.finditer(wen):  # 逐引用
                # 解析 '表'!A1[:B2] → 目标表 + 起止行列（区间全展开）
                mbiao = m.group(1) or biao  # 目标表
                c1, r1 = col_hao(m.group(2)), int(m.group(3))  # 起始行列
                c2 = col_hao(m.group(4)) if m.group(4) else c1  # 终止列
                r2 = int(m.group(5)) if m.group(5) else r1  # 终止行
                for rr in range(r1, r2 + 1):  # 区间展开
                    for cc in range(c1, c2 + 1):  # 列展开
                        # 越界（>AY480）直接登记；白名单外同样登记
                        if cc > 51 or rr > 480:  # 网格越界
                            wenti.append(f'{ming}:{biao}!{ref} 引用越界 {mbiao}')  # 登记越界
                            continue  # 跳过后续
                        mu = f'{gq_col(cc)}{rr}'  # 目标格
                        if mu not in quanbai.get(mbiao, set()):  # 白名单外
                            wenti.append(f'{ming}:{biao}!{ref} 引用白名单外 {mbiao}!{mu}')  # 登记引用断链
    # 7) 汇总尾引号回归门：任何固化公式不得以单引号收尾（v1.1 语法 bug 防回归）
    for biao in SHEETS:  # 逐表扫
        for ref, wen in ext['formulas'][biao].items():  # 逐公式
            if wen.rstrip().endswith("'"):  # 尾引号
                wenti.append(f'{ming}:固化公式 {biao}!{ref} 以单引号收尾（语法非法）')  # 登记回归
    return wenti


def gq_col(n):  # 列号→字母
    """列号 → 列字母（excel_contract_v11.col 同式，本地副本避免环导）。"""
    out = ''  # 输出累积
    while n:
        n, yu = divmod(n - 1, 26)  # 26 进制分解
        out = chr(65 + yu) + out
    return out  # 返回字母


def jian_gujia(leibie, qiyue):  # 骨架底稿构建
    """生成骨架底稿：老底稿 + 展示层/功能区骨架 + base_diff 物理落格（零数值）。"""
    # 老底稿只读读入（experimental 契约齐备版，实测 226 可过）
    raw = (DIGAO_105 / f'演示底稿-{leibie}.xlsx').read_bytes()  # 老底稿只读读入
    ext = qiyue['ext']  # ext 段
    # 变更表 = 全部 ext 标签（text）+ 全部 ext 公式（formula）——不含输入格；
    # 另加 base_diff 的物理落格：标签重钉（C3/D3/AY1 等）与参数公式改列（C201-203）
    changes = {}  # 变更表
    for biao in SHEETS:  # 逐表
        for ref, wen in ext['labels'][biao].items():  # 标签（text）
            changes.setdefault(biao, {})[ref] = ('text', wen)  # 写入变更
        for ref, wen in ext['formulas'][biao].items():  # 公式（formula）
            changes.setdefault(biao, {})[ref] = ('formula', wen)  # 写入变更
        for ref, wen in qiyue['diff']['biaoqian'].get(biao, {}).items():  # base 标签重钉
            changes.setdefault(biao, {})[ref] = ('text', wen)  # 物理落格
        for ref, wen in qiyue['diff']['canshu'].get(biao, {}).items():  # 参数公式改列
            changes.setdefault(biao, {})[ref] = ('formula', wen)  # 物理落格
    return xw.patch(raw, changes)


def zijian_gujia(shuju, qiyue, ming):
    """骨架底稿回读自检：ext 命中、老区公式位一个不少、diff 落格、旧公式零残留。"""
    from xlsx_reader import Book
    wenti = []
    book = Book(shuju)
    ext = qiyue['ext']
    for biao in SHEETS:
        # ext 标签逐字命中（写进去的就要读得回）
        for ref, wen in ext['labels'][biao].items():
            if book.value(biao, ref) != wen:
                wenti.append(f'{ming}:骨架标签不符 {biao}!{ref}')
        # ext 固化公式逐字命中（含缓存可缺省格）
        for ref, wen in ext['formulas'][biao].items():
            if book.cells[biao].get(ref) != ('formula', wen):
                wenti.append(f'{ming}:骨架公式不符 {biao}!{ref}')
        # 老区公式位一个不少（底稿原状 + 骨架不破坏老区；base 已含受控 diff）
        for ref, wen in qiyue['base'][biao]['formulas'].items():
            if book.cells[biao].get(ref) != ('formula', wen):
                wenti.append(f'{ming}:老区公式丢失 {biao}!{ref}')
        # base 标签逐字命中（含 diff 重钉的 C3/D3/AY1 等）
        for ref, wen in qiyue['base'][biao]['labels'].items():
            if book.value(biao, ref) != wen:
                wenti.append(f'{ming}:base标签不符 {biao}!{ref}')
    # 被移位的展示旧公式零残留：移位格必须已是 ext 新公式（非旧文本）
    jiu_wen = {'利润表': {'C4': 'SUM(C61:N61)', 'C18': 'SUM(C67:N67)', 'C20': 'SUM(C69:N69)'},
               '资产负债表': {'C17': 'C4+C9+C13', 'C40': 'N63', 'G19': 'G6'},
               '现金流量表': {'C13': 'SUM(C63:N63)', 'C40': 'N68'}}
    for biao, gongshi in jiu_wen.items():  # 旧文本零残留
        for ref, wen in gongshi.items():
            if book.cells[biao].get(ref) == ('formula', wen):
                wenti.append(f'{ming}:展示旧公式残留 {biao}!{ref}=={wen}')  # 登记残留
    return wenti


def main():
    """构建两类契约与骨架底稿并跑全部自检；失败非零退出。"""
    mu_lu = BEN_MU / '模板'
    mu_lu.mkdir(exist_ok=True)
    quanbu_wenti = []
    for leibie in ('预算基础', '实时经营'):
        # 一类一建：契约 dict → 自检 → 骨架底稿 → 回读自检 → 落盘 → round-trip
        qiyue = jian_qiyue(leibie)
        wenti = zijian(qiyue, leibie)
        quanbu_wenti += wenti
        gujia = jian_gujia(leibie, qiyue)
        quanbu_wenti += zijian_gujia(gujia, qiyue, leibie)
        lu = mu_lu / f'模板结构规范-v1.2-{leibie}.json'
        # sort_keys + indent=1：同定义产出逐字节一致的 JSON（确定性构建）
        lu.write_text(json.dumps(qiyue, ensure_ascii=False, indent=1, sort_keys=True),
                      encoding='utf-8')
        (mu_lu / f'演示底稿-v1.2-{leibie}.xlsx').write_bytes(gujia)
        # round-trip：落盘 JSON 重载复检（防序列化丢信息）
        chong = json.loads(lu.read_text(encoding='utf-8'))
        quanbu_wenti += zijian(chong, leibie + '-roundtrip')
        zhan_shu = sum(len(v) for v in qiyue['ext']['display'].values())
        print(f'[{leibie}] 契约 {lu.name} + 骨架底稿已生成'
              f'（ext 公式 {sum(len(v) for v in qiyue["ext"]["formulas"].values())} 格，'
              f'其中展示层 {zhan_shu} 格；标签 {sum(len(v) for v in qiyue["ext"]["labels"].values())} 格，'
              f'输入白名单 {sum(len(v) for v in qiyue["ext"]["inputs"].values())} 格，'
              f'base_diff 移位 {sum(len(v) for v in qiyue["diff"]["yichi"].values())} 格）')
    if quanbu_wenti:
        # 有问题即列出并失败退出（不静默放行半自洽契约）
        print(f'自检失败 {len(quanbu_wenti)} 项：')
        for w in quanbu_wenti[:20]:
            print('  -', w)
        return 1
    print('自检 7 组全部通过：零碰撞/边界（前沿+展示）/37 行对齐/引用闭环/骨架回读/round-trip/尾引号回归门')
    return 0


if __name__ == '__main__':
    sys.exit(main())
