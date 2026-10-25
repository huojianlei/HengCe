# -*- coding: utf-8 -*-
"""入口：生成演示工作簿（零公式、纯数值、尺寸与样式定死、运行时不读任何文件）。

用法：
    python shengcheng.py                      # 十二表两册 + 外部两册（共四册）
    python shengcheng.py --leibie 预算基础     # 只出十二表某一类别
    python shengcheng.py --zhong 行业对标      # 只出外部某一册
    python shengcheng.py --seed 20260923 --out 输出
    python shengcheng.py --bumen --seed 20261001 --hangye 供应链管理
    python shengcheng.py --bumen 加盟部 品牌部 物流部 --zhuti 睿衍供应链管理有限公司
产出（默认 ./输出/）：
    演示-预算基础-<种子>.xlsx / 演示-实时经营-<种子>.xlsx
    演示-行业对标-<种子>.xlsx / 演示-经营变更-<种子>.xlsx

====================================================================
这个入口在整条链上的位置
====================================================================
    命令行参数 → mingcheng.tihuan_biao（主体/年度/占位符）
              → shuju.ShuJu（数值层：按种子算全部科目数值）
              → xiechu.xie_shu（写出层：按 banshi 版式落盘）
              → waibu（外部两册的数值层，复用 shuju 的口径工具）
    jiaoyan 校验的是落盘后的 xlsx，是"交付前最后一道闸"，不在本文件的调用链里
    （本文件只负责"生成"，校验由上层流水线单独调；分开是为了让校验能独立重跑）。

四种输出形态（互斥，命令行按优先级判定）
    默认          出四册：十二表 × 两类别（预算基础/实时经营）+ 外部两册（行业对标/经营变更）
    --leibie X    只出十二表的一册（X ∈ 预算基础/实时经营）
    --zhong X     只出外部的一册（X ∈ 行业对标/经营变更）
    --bumen       部门分册模式：同一行业下每个部门单独一册（多主体导入场景）
    --biaonei     表内部门模式（v3 轨）：一册里含公司九表 + 部门明细表，
                  实时经营另附非财务指标（v3k）与量价拆分（v3s）两版

可复现性纪律（本文件最重要的一条）
    同一个 seed 必须产出逐字节相同的四册；因此：
      · 所有随机数都来自 ShuJu / 非财务指标里显式 seed 的 Random，禁止用全局 random；
      · 文件名只由 seed/类别/行业决定，不含时间戳；
      · 输出目录里的临时回读册（v3 轨）固定命名，重跑会被覆盖，不累积垃圾。

金额与比率口径
    金额单位 = 元（数值层已量化到分，详见 shuju 模块 docstring）；
    比率 = 百分数格式的原始小数（0.35 显示 35.00%）；
    非财务指标按各自单位（%/天/次），只保留两位小数，不参与任何勾稽。

退出码
    main() 返回 0；参数非法由 argparse 直接退出（码 2），业务性错误抛 ValueError 向上冒。
"""
import argparse
import hashlib
import sys
from pathlib import Path

import waibu
from banshi import WAI_BIAO
from mingcheng import tihuan_biao
from shuju import ZICHAN, ZICHAN_BY_HANG, ShuJu
from xiechu import xie_shu

MU = Path(__file__).resolve().parent
#: 十二表的两类别（共用同一套版式，靠批次元字段 AY16 数据类别区分）
SHI_ER = ('预算基础', '实时经营')
#: 外部两册（各自独立模板，与十二表体系无关）
WAI = ('行业对标', '经营变更')
BUMEN_BIAO = '部门明细表'                                  # v3 轨第十表表名（与读取器一致）
KPI_BIAO = '非财务指标'                                     # v3k 轨第十一表表名（与读取器一致）
LJ_BIAO = '量价拆分'                                          # v3s 轨第十一表表名（与读取器一致）
#: 量价拆分表头：B/C 规划口径，D/E 修订口径，F/G/H 实际口径
#: 恒等式（由读取端 chai_fen 自检）：实际总成本 = 修订单价 × 实际产量
LJ_BIAOTOU = ['科目', '标准单价（元）', '标准用量', '修订单价（元）',
              '修订用量', '实际产量', '实际总用量', '实际总成本（元）']
#: 非财务六项固定行：(名称, 单位, 值生成函数, 备注)
#: 取值区间是"演示上合理"的区间（履约率 88-99%、产能 70-95% 等），
#: 生成函数接收一个 Random 实例（种子由调用方定），保证同种子同结果。
#: 备注列写给用户看"这个指标怎么算"，不是程序逻辑（读取器不解析它）。
KPI_LIE = (
    ('供应链履约率', '%', lambda r: 88 + r.randrange(0, 1100) / 100, '按期足额交付订单数 ÷ 订单总数'),
    ('产能利用率', '%', lambda r: 70 + r.randrange(0, 2500) / 100, '实际产出 ÷ 潜在产能'),
    ('交付周期', '天', lambda r: 7 + r.randrange(0, 1800) / 100, '平均下单到交付天数'),
    ('客户满意度', '%', lambda r: 80 + r.randrange(0, 1800) / 100, '满意客户数 ÷ 受访客户数'),
    ('业务完成进度', '%', lambda r: 85 + r.randrange(0, 1400) / 100, '已完成业务量 ÷ 计划业务量'),
    ('异常事项数量', '次', lambda r: r.randrange(0, 4), '本期异常事项次数'),
)


def _hou(seed, hangye=None):
    """文件名后缀：指定行业时带上，便于同种子多行业并存。

    参数 seed: 种子；hangye: 行业词（可为 None）。
    返回: 例如 '20261025' 或 '20261025-供应链管理'。
    为什么把行业写进文件名: 同一 seed 换行业是"另一套演示数据"，
        若文件同名会互相覆盖，看不出差异；带上行业后两套可以并排比对。
    """
    return f'{seed}-{hangye}' if hangye else str(seed)


def sheng(seed=20260923, leibie='预算基础', out=None, hangye=None, zhuti=None):
    """生成十二表一本；返回产物路径。

    参数:
        seed    整数种子（同种子必然同结果）。
        leibie  '预算基础' / '实时经营'（决定期间数：预算 12 个月、实时 6 个月已生效）。
        out     输出目录（缺省 ./输出，自动创建）。
        hangye  强制行业词；缺省从生成的主体名反推（见下面的反推逻辑）。
        zhuti   强制主体名；缺省由 mingcheng 按种子取名。
    返回: Path（落盘路径；若目标被 Excel 占用则为"另存"路径）。
    异常: ShuJu 内部对黑名单耗尽的 ValueError、资负不平的 AssertionError 会直接上抛。
    """
    out = Path(out) if out else (MU / '输出')
    out.mkdir(parents=True, exist_ok=True)
    tihuan = tihuan_biao(seed, leibie, hangye=hangye, zhuti=zhuti)
    # 未指定行业时，按生成出的主体名反推行业 → 摊销台账与行业匹配
    hy = hangye or next((k for k in ZICHAN_BY_HANG if k in tihuan['主体一']), None)
    shuju = ShuJu(seed, leibie, hy)
    lu = out / f'演示-{leibie}-{_hou(seed, hangye)}.xlsx'
    return xie_shu(shuju.biao, tihuan, lu, leibie)      # 被占用时返回另存路径


def sheng_wai(seed=20260923, zhong='行业对标', out=None, hangye=None, zhuti=None):
    """生成外部册一本；返回产物路径。

    参数:
        zhong '行业对标'（基准指标表）或 '经营变更'（事件台账 + 科目影响）。
        其余参数同 sheng()。
    返回: Path。
    说明: 外部两册的版式不是十二表体系，走 waibu.WAI_BIAO 单册版式；
        数值层也由 waibu 提供（但它复用 shuju 的 FEN/black名单/ming_zhong 工具，
        保证避让口径与十二表一致）。
    """
    out = Path(out) if out else (MU / '输出')
    out.mkdir(parents=True, exist_ok=True)
    tihuan = tihuan_biao(seed, zhong, hangye=hangye, zhuti=zhuti)
    zhi = (waibu.hangye_biao(seed, tihuan) if zhong == '行业对标'
           else waibu.biangeng_biao(seed, tihuan))
    lu = out / f'演示-{zhong}-{_hou(seed, hangye)}.xlsx'
    return xie_shu(zhi, tihuan, lu, zhong, WAI_BIAO[zhong])


def sheng_si_ce(seed=20260923, out=None, hangye=None, zhuti=None):
    """生成四册；返回路径列表（顺序：十二表两类别 + 外部两册）。

    顺序是固定的：预算基础 → 实时经营 → 行业对标 → 经营变更。
    调用方（命令行 / 上层流水线）依赖这个顺序做后续处理，不要改动。
    """
    lu = [sheng(seed, b, out, hangye, zhuti) for b in SHI_ER]
    # 外部两册接在十二表之后出：上层流水线按"前两册=十二表"做分支判断，顺序不能变。
    lu += [sheng_wai(seed, b, out, hangye, zhuti) for b in WAI]
    return lu


def sheng_bumen(seed=20261001, out=None, hangye=None, zhuti=None, bumen=None,
                leibie=None):
    """按行业部门池输出预算/实时两册；缺省输出全部部门，返回路径列表。

    部门名称来自行业台账，固定种子对应固定数值。主体编码由公司、部门、年度
    确定，预算与实时一致；同部门换种子重做演示时仍属于同一个导入分组。

    参数:
        bumen   部门名列表；缺省 = 该行业台账里的全部部门（顺序去重后即台账顺序）。
        leibie  限定只出某一类别；缺省 = 两类别都出。
    返回: Path 列表（每部门 × 每类别的落盘路径）。
    异常:
        ValueError —— leibie 非法 / 主体名里带 '/' / 部门重名 / 部门不在该行业台账。
    为什么主体编码用 sha256(公司/部门)[:12]:
        编码必须"稳定且不可读"——稳定才能让预算册与实时册归到同一导入分组，
        不可读才不会让人从编码里反推业务含义；取前 12 位够用且短。
    为什么部门模式要单独出册而不是塞一张表:
        多主体导入要求"一册一主体"，部门册的主体名写成 `公司/部门`，
        导入端按 '/' 自动识别为部门主体，归到同一公司下。
    """
    if leibie is not None and leibie not in SHI_ER:
        raise ValueError(f'部门模式仅支持：{"、".join(SHI_ER)}')
    if zhuti and '/' in zhuti:
        raise ValueError('请填写公司名称；部门名称通过 bumen 指定')
    out = Path(out) if out else (MU / '输出')
    out.mkdir(parents=True, exist_ok=True)
    base = tihuan_biao(seed, '预算基础', hangye=hangye, zhuti=zhuti)
    hy = hangye or next((k for k in ZICHAN_BY_HANG if k in base['主体一']), None)
    # 行业 → 部门池（行业台账里第 3 列是部门名）；去重保序，避免同一部门出两册
    chi = tuple(dict.fromkeys(z[2] for z in ZICHAN_BY_HANG.get(hy, ZICHAN)))
    bu_lie = tuple(bumen) if bumen else chi
    if len(set(bu_lie)) != len(bu_lie):
        raise ValueError('部门名称不能重复')
    for bu in bu_lie:
        if bu not in chi:
            raise ValueError(f'该行业没有部门 {bu}；可选：{"、".join(chi)}')
    lu = []
    for bu in bu_lie:
        ming = f'{base["主体名"]}/{bu}'
        # 部门编码：公司/部门 → sha256 前 12 位（大写，便于人工抄写）
        ma = hashlib.sha256(ming.encode('utf-8')).hexdigest()[:12].upper()
        for lei in ((leibie,) if leibie else SHI_ER):
            tihuan = tihuan_biao(seed, lei, hangye=hangye, zhuti=zhuti)
            tihuan.update({'主体一': ming, '主体名': ming,
                           '主体编码': f'ENT-{tihuan["年度"]}-D{ma}'})
            # 同一 seed + 同一部门：预算与实时的数值层走同一条随机流（数值层按类别派生），
            # 因此两册的部门口径数值不会互相矛盾。
            shuju = ShuJu(seed, lei, hy, bumen=bu)
            dest = out / f'演示-{lei}-{bu}-种子-{_hou(seed, hangye)}.xlsx'
            lu.append(xie_shu(shuju.biao, tihuan, dest, lei))
    return lu


def sheng_biaonei(seed=20260923, out=None, hangye=None, zhuti=None, bumen=None, kpi=True, liangjia=True):
    """表内部门版（v3 十表；实时经营另附 v3k 十一表版含非财务指标）：
    公司九表 + 部门明细表（两册各一）+ 非财务指标表（仅实时经营 KPI 版）。

    一册承载全公司 + 各部门的 科目×月 数值：部门明细表为扁平表
    （部门 | 项目 | 12 个月 | 合计）。取数口径与读取器 zhuan_jilu 完全一致
    （临时册回读权威记录，杜绝两套口径漂移）；部门值来自各行业部门池，
    逐（科目,月）与公司口径的尾差吸收进首个部门，保证 Σ部门 ≡ 公司（分位）。
    读取端（excel_ingest_v3）按表序列自动走 v3 轨并把各部门展开成虚拟分册。

    参数:
        bumen  部门名列表；缺省 = 该行业全部部门。
        kpi    True 时实时经营另出 v3k 版（附非财务指标第十一表）。
        liangjia True 时实时经营另出 v3s 版（附量价拆分第十一表 + 可选 KPI）。
    返回: Path 列表（预算基础 1 + 实时经营 1~3 册）。
    副作用: 在 out/临时回读/ 下写"临时回读册"（*.xlsx 中间态），这些文件不删，
        留给排错时对照；重跑同名覆盖，不会累积。
    异常: 同 sheng_bumen；另有"部门出现公司口径没有的键"时抛 ValueError
        （说明部门数值层与公司数值层不一致，属程序缺陷，宁可报错不能悄悄吞掉）。

    设计要点（为什么这样绕）
        1) 数值取"临时册回读"而不是直接在内存里拼：读取器（excel_ingest_v2）才是
           口径权威，回读一遍等于"自证与导入端同口径"，杜绝生成端/读取端两套算法漂移。
           回读值单位是分，故下面 ÷100 换成元，与部门明细表单元格（元）同单位。
        2) 部门口径 = 费用中心：营业收入与税金及附加留在公司级，不下沉到部门
           （部门没有收入确认权，硬拆收入会破坏"Σ部门 = 公司"）。
        3) 尾差吸收：公司值 - Σ部门值 的差额（分位）全部记到第一个部门，
           保证"部门之和 ≡ 公司"严格相等，而不是近似相等。
    """
    import io
    import sys as _sys
    from decimal import Decimal
    gen = Path(__file__).resolve().parents[1]               # plugin/backend
    # 读取器不在本目录：把 ingest_v11 挂到 sys.path 才能 import excel_ingest_v2。
    # 只在函数内 import、且只在需要时改 sys.path —— "生成四册"是常用路径，
    # 不该为 v3 轨的依赖付出加载成本。
    for _lu in (gen / 'ingest_v11',):
        if str(_lu) not in _sys.path:
            _sys.path.insert(0, str(_lu))
    from excel_ingest_v2 import import_v2
    from xiechu import JIU_BIAO, SAN_BIAO, SHEETS
    from openpyxl import load_workbook

    out = Path(out) if out else (MU / '输出')
    out.mkdir(parents=True, exist_ok=True)
    linshi = out / '临时回读'
    base = tihuan_biao(seed, '预算基础', hangye=hangye, zhuti=zhuti)
    hy = hangye or next((k for k in ZICHAN_BY_HANG if k in base['主体一']), None)
    chi = tuple(dict.fromkeys(z[2] for z in ZICHAN_BY_HANG.get(hy, ZICHAN)))
    bu_lie = tuple(bumen) if bumen else chi
    if len(set(bu_lie)) != len(bu_lie):
        raise ValueError('部门名称不能重复')
    for bu in bu_lie:
        if bu not in chi:
            raise ValueError(f'该行业没有部门 {bu}；可选：{"、".join(chi)}')
    jiu_ban = {m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}   # 九表版式
    bumen_ban = {'hang_gao_mo_ren': 16,
                 'lie_kuan': {'1': 14, '2': 26, **{str(i): 11 for i in range(3, 15)},
                              '15': 14},
                 'hang_gao': {}, 'hebing': [], 'biaoqian': {},
                 'ge_ys': {}, 'lie_ys': {}, 'yangshi': [], 'shuzhi_wei': {},
                 'dims': {'freeze': 'C2'}}
    LEI_TONG = {'预算基础': 'yusuan', '实时经营': 'shishi'}

    def hui_du(ji, tihuan, ming, lei):
        """临时写一册九表并按权威链读回记录：{(科目, 期间): Decimal(元)}。

        daoru_csv 的 records.shuzhi 语义是分；回读后 ÷100 回元，与
        部门明细表单元格（元）及公司九表取数位（元）同单位。
        """
        linshi.mkdir(parents=True, exist_ok=True)
        lu = xie_shu(ji, tihuan, linshi / ming, lei)
        jie = import_v2(lu.read_bytes(), lu.name)
        lei_key = LEI_TONG[jie['category']]
        return {(r['kemu'], r['qijian']): Decimal(str(r['shuzhi'])) / 100
                for r in jie['records'][lei_key]}

    lu = []
    yu_gong = {}                       # 预算基础回读值（量价拆分按预算/实际反推）
    #: 实时经营异常注入（演示用，预算基础不动）：差旅费整组 +40%、业务招待费 +69%。
    #: 只放大 2027-06 的用量，金额随 单价×数量 同步，三表勾稽仍由程序保证。
    YC = {('销售费用', 21): {'H': 1.40}, ('销售费用', 22): {'H': 1.40},
          ('销售费用', 23): {'H': 1.40}, ('销售费用', 24): {'H': 1.40},
          ('管理费用', 25): {'H': 1.69}}
    for lei in SHI_ER:
        tihuan = tihuan_biao(seed, lei, hangye=hangye, zhuti=zhuti)
        yc = YC if lei == '实时经营' else None
        gong_biao = ShuJu(seed, lei, hy, yichang=yc).biao
        gong = hui_du(gong_biao, tihuan, f'回读-公司-{lei}.xlsx', lei)
        if lei == '预算基础':
            yu_gong = gong
        bu_zhi, bu_mingdan = {}, []
        for bu in bu_lie:
            ming = f'{base["主体名"]}/{bu}'
            ma = hashlib.sha256(ming.encode('utf-8')).hexdigest()[:12].upper()
            bu_tihuan = dict(tihuan)
            bu_tihuan.update({'主体一': ming, '主体名': ming,
                              '主体编码': f'ENT-{tihuan["年度"]}-D{ma}'})
            bu_biao = ShuJu(seed, lei, hy, bumen=bu, yichang=yc).biao
            bu_zhi[bu] = hui_du(bu_biao, bu_tihuan, f'回读-{bu}-{lei}.xlsx', lei)
            bu_mingdan.append(bu)
        # 尾差吸收：Σ部门 ≡ 公司（分位精确），差额计入首个部门
        shou = bu_mingdan[0]
        for jian, gong_zhi in gong.items():
            cha = gong_zhi - sum((bu_zhi[b].get(jian, Decimal('0'))
                                  for b in bu_mingdan), Decimal('0'))
            if cha:
                bu_zhi[shou][jian] = bu_zhi[shou].get(jian, Decimal('0')) + cha
        for b in bu_mingdan:                                  # 公司没有的键不得残留
            for jian in [j for j in bu_zhi[b] if j not in gong]:
                if bu_zhi[b][jian]:
                    raise ValueError(f'{b} 出现公司口径没有的 {jian}')
                del bu_zhi[b][jian]
        # 拼第十表：表头 + 扁平数据行（部门 | 科目 | 12 月 | 合计）
        # 部门口径＝费用中心：营业收入与税金及附加留在公司级，只有销售/管理费用下沉到部门
        kemu_xu = [k for k in dict.fromkeys(k for k, _ in gong)
                   if not (k == '营业收入' or k == '税金及附加')]
        biao = {'A1': '部门', 'B1': '项目',
                **{f'{chr(67 + i)}1': f'{tihuan["年度"]}-{i + 1:02}' for i in range(12)},
                'O1': '合计'}
        hang = 2
        for bu in bu_mingdan:
            for kem in kemu_xu:
                he = Decimal('0')
                biao[f'A{hang}'] = bu
                biao[f'B{hang}'] = kem
                for i in range(12):
                    qi = f'{tihuan["年度"]}-{i + 1:02}'
                    zhi = bu_zhi[bu].get((kem, qi))
                    if zhi:
                        # 0 值不写：部门明细表的空白 = 该项本月无发生额，
                        # 读取端按"缺省即 0"处理；写满 0 会让表体膨胀、可读性变差。
                        biao[f'{chr(67 + i)}{hang}'] = float(zhi)
                        he += zhi
                if he:
                    biao[f'O{hang}'] = float(he)
                hang += 1
        ji = dict(gong_biao)
        ji[BUMEN_BIAO] = biao
        ban = dict(jiu_ban)
        ban[BUMEN_BIAO] = bumen_ban
        dest = out / f'演示-{lei}-表内部门-种子-{_hou(seed, hangye)}.xlsx'
        lu.append(xie_shu(ji, tihuan, dest, lei, ban))
        if lei == '实时经营' and kpi:
            # v3k：附第十一张「非财务指标」（固定种子 → 固定数值；六行顺序与读取器一致）
            import random as _rd
            # 非财务指标的种子串与数值层不同（'|非财务|v1'）：指标与账表互不干扰，
            # 改动账表种子不会连带改变 KPI 数值，反之亦然——便于分别回归。
            rg = _rd.Random(f'{seed}|非财务|v1')
            kb = {'A1': '指标', 'B1': '单位', 'C1': '本期值', 'D1': '备注'}
            for r_i, (ming, dan, sheng, bei) in enumerate(KPI_LIE, start=2):
                kb[f'A{r_i}'] = ming
                kb[f'B{r_i}'] = dan
                kb[f'C{r_i}'] = round(sheng(rg), 2)
                kb[f'D{r_i}'] = bei
            ji2 = dict(ji)
            ji2[KPI_BIAO] = kb
            ban2 = dict(ban)
            ban2[KPI_BIAO] = {'hang_gao_mo_ren': 16,
                              'lie_kuan': {'1': 16, '2': 10, '3': 12, '4': 40},
                              'hang_gao': {}, 'hebing': [], 'biaoqian': {},
                              'ge_ys': {}, 'lie_ys': {}, 'yangshi': [], 'shuzhi_wei': {},
                              'dims': {}}
            dest2 = out / f'演示-{lei}-表内部门KPI-种子-{_hou(seed, hangye)}.xlsx'
            lu.append(xie_shu(ji2, tihuan, dest2, lei, ban2))
        if lei == '实时经营' and liangjia:
            # v3sk：「量价拆分」按预算/实际反推，三条演示路径各有明确判定：
            #   差旅费     规划差异≈40%、执行≈0   → 有结构变更登记时判双环
            #   业务招待费 规划≈30%、执行≈39%    → 判混合纠错模式
            #   员工费用   规划/执行均小           → 不触发（对照组）
            # 产量/用量固定 100，单价 = 金额 / 10000，恒等式由 chai_fen 自检。
            def _lj_yuan(kem, guihua):
                """guihua：规划差异相对预算的比例；'auto' 表示让修订直接吸收实际。

                参数:
                    kem    量价科目键（'销售费用/差旅费' 这类"表/项目"形式）。
                    guihua 'auto' → 修订单价 = 实际单价（规划差异 0、执行差异全归修订后）；
                            数值 → 修订单价 = 预算单价 ×(1+比例)。
                返回: 一行八列 {A..H}，单价均按分位四舍五入（quantize 0.01）。
                口径: 产量/用量固定 100（演示用约定），故 单价 = 金额 / 10000；
                      这样"单价×产量"恒等于金额，量价拆分的恒等式自检必然通过。
                """
                ji_yu = yu_gong.get((kem, '2027-06')) or Decimal('0')
                ji_shi = gong.get((kem, '2027-06')) or Decimal('0')
                biao_dan = (ji_yu / Decimal('10000')).quantize(Decimal('0.01'))
                if guihua == 'auto':
                    xiu_dan = (ji_shi / Decimal('10000')).quantize(Decimal('0.01'))
                else:
                    xiu_dan = (biao_dan * (Decimal('1') + Decimal(str(guihua)))
                               ).quantize(Decimal('0.01'))
                return {'A': kem, 'B': biao_dan, 'C': 100, 'D': xiu_dan,
                        'E': 100, 'F': 100, 'G': 100, 'H': ji_shi}
            lb = {f'{chr(65+i)}1': tou for i, tou in enumerate(LJ_BIAOTOU)}
            # 三条演示路径：差旅费（结构变更/双环）、业务招待费（混合纠错）、
            # 员工费用（对照组，不触发任何差异判定）——覆盖三种诊断结论。
            for r_i, hang in enumerate((
                    _lj_yuan('销售费用/差旅费', 'auto'),
                    _lj_yuan('管理费用/业务招待费', '0.30'),
                    _lj_yuan('销售费用/员工费用', '0')), start=2):
                for lie, zhi in hang.items():
                    lb[f'{lie}{r_i}'] = zhi
            ji3 = dict(gong_biao)
            ji3[BUMEN_BIAO] = biao
            ji3[LJ_BIAO] = lb
            if kpi:
                # v3sk：尾部再附非财务指标表（与 KPI 册同款六行）
                import random as _rd3
                rg3 = _rd3.Random(f'{seed}|非财务|v1')
                kb2 = {'A1': '指标', 'B1': '单位', 'C1': '本期值', 'D1': '备注'}
                for r_j, (ming2, dan2, sheng2, bei2) in enumerate(KPI_LIE, start=2):
                    kb2[f'A{r_j}'] = ming2
                    kb2[f'B{r_j}'] = dan2
                    kb2[f'C{r_j}'] = round(sheng2(rg3), 2)
                    kb2[f'D{r_j}'] = bei2
                ji3[KPI_BIAO] = kb2
            ban3 = dict(jiu_ban)
            ban3[BUMEN_BIAO] = bumen_ban
            ban3[LJ_BIAO] = {'hang_gao_mo_ren': 16,
                             'lie_kuan': {'1': 24, '2': 14, '3': 12, '4': 14, '5': 12,
                                          '6': 12, '7': 12, '8': 16},
                             'hang_gao': {}, 'hebing': [], 'biaoqian': {},
                             'ge_ys': {}, 'lie_ys': {}, 'yangshi': [], 'shuzhi_wei': {},
                             'dims': {}}
            if kpi:
                # 表序列固定：十表 + 量价拆分 + 非财务指标（v3sk）
                ban3[KPI_BIAO] = {'hang_gao_mo_ren': 16,
                                  'lie_kuan': {'1': 16, '2': 10, '3': 12, '4': 40},
                                  'hang_gao': {}, 'hebing': [], 'biaoqian': {},
                                  'ge_ys': {}, 'lie_ys': {}, 'yangshi': [], 'shuzhi_wei': {},
                                  'dims': {}}
            dest3 = out / f'演示-{lei}-表内部门量价-种子-{_hou(seed, hangye)}.xlsx'
            lu.append(xie_shu(ji3, tihuan, dest3, lei, ban3))
    return lu


def main():
    """命令行入口：解析参数 → 选模式 → 生成 → 打印产物路径与字节数。

    返回: 0（成功）。参数错误由 argparse 以码 2 退出。
    模式选择优先级（顺序不可换，避免歧义）:
        --biaonei > --bumen > --leibie > --zhong > 默认（四册）
    打印格式固定为 `生成 <路径>（<字节数> 字节）`：
        上层脚本与人工核对都依赖这一行（"字节数"可用来快速判断是否真的重写了文件）。
    """
    ap = argparse.ArgumentParser(description='演示工作簿生成器（自包含·零公式·纯数值）')
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--leibie', default=None, choices=SHI_ER)
    ap.add_argument('--zhong', default=None, choices=WAI)
    ap.add_argument('--out', default=None)
    ap.add_argument('--hangye', default=None, help='强制行业词（如 智能制造/商贸实业）')
    ap.add_argument('--zhuti', default=None, help='强制主体名（不含"有限公司"也可）')
    ap.add_argument('--bumen', nargs='*', default=None, metavar='部门',
                    help='部门拆分：不带名称时生成该行业全部部门，可指定一个或多个部门')
    ap.add_argument('--biaonei', nargs='*', default=None, metavar='部门',
                    help='表内部门版（v3 十表）：一册含公司+各部门，缺省全部部门')
    a = ap.parse_args()
    if a.biaonei is not None:
        # 注意用 `is not None` 而不是真值判断：--biaonei 不带部门名时是 []（空列表），
        # 语义是"全部部门"，而 [] 在布尔判断里为假，改成 if a.biaonei 会误落到别的分支。
        if a.zhong or a.leibie:
            ap.error('表内部门版只生成预算基础和实时经营两册，不能与 --zhong/--leibie 合用')
        lu = sheng_biaonei(a.seed, a.out, a.hangye, a.zhuti, a.biaonei)
    elif a.bumen is not None:
        # 同上：--bumen 空列表 = 全部部门
        if a.zhong:
            ap.error('部门模式只生成预算基础和实时经营，不能与 --zhong 合用')
        lu = sheng_bumen(a.seed, a.out, a.hangye, a.zhuti, a.bumen, a.leibie)
    elif a.leibie:
        lu = [sheng(a.seed, a.leibie, a.out, a.hangye, a.zhuti)]
    elif a.zhong:
        lu = [sheng_wai(a.seed, a.zhong, a.out, a.hangye, a.zhuti)]
    else:
        lu = sheng_si_ce(a.seed, a.out, a.hangye, a.zhuti)
    for p in lu:
        # 字节数写进日志：同一个 seed 重跑若字节数不变，基本可判定"可复现"成立
        print(f'生成 {p}（{p.stat().st_size} 字节）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
