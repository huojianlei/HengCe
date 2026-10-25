# -*- coding: utf-8 -*-
"""校验器：对生成产物做数值级验收（读回 xlsx 逐条核对）。

六道门：
    1) 零公式      —— 全簿无一格以 '=' 开头
    2) 全填        —— 三表科目行 × 数据列、九表数字位，全部是数字
    3) 恒等式      —— 收入/成本/税金/三费/摊销/现金链/资负平衡/分录借贷/对照
    4) 尺寸回读    —— 列宽/行高/合并区/冻结窗格与版式常量逐项一致
    5) 名称        —— 占位符已渲染、禁词零残留
    6) 确定性      —— 同种子两次生成逐格一致

用法：python -B jiaoyan.py [--seed 20260923]

这一层为什么必须与生成器分开
    生成器自己算完再自己说"我算对了"没有证明力。本模块只做一件事：把 xlsx 读回来，
    用**独立于生成路径**的算法重算一遍恒等式，再与落盘值比对。所有期望值都从文件里的
    其它格子推出（例如"净利润 = 利润总额 − 所得税"），不引用 shuju 的中间变量——
    这样"写盘写错""行号错位""正负号反了"才能被抓到。

输入与输出
    输入: 由 shengcheng 现场生成的四册（也接受 --out 指向已有产物目录）。
    输出: 控制台逐项 [PASS]/[FAIL] + 末尾摘要「通过 N 项，失败 M 项」+ 每项 FAIL 明细。
    退出码: 0 = 全通过；1 = 存在失败项。上游（全流程报告.py）就是靠这两个数字与退出码
        判断链路是否放行，所以摘要行格式「通过 N 项，失败 M 项」不许改。

判定口径
    · 金额一律元、两位小数；比较走 deng()，容差 RONG_CHA = 0.005（分币容差）。
      容差不是放宽标准：分位四舍五入后，两个"各自正确"的算法可能差 1 分，
      0.005 只吸收这种进位差，超过即判失败。
    · 比率/费率（城建 7%、教育 3%、地方 2%、所得税 25%）按模板公式反算，
      比较时留 0.02~0.05 的绝对放宽——这些是逐月按分位四舍五入的乘积，误差随月数累积。
    · "文化事业建设费 0" 是演示口径的显式假设（模板 B10/126 行恒为 0），不是漏算。

与其它模块的契约
    · 版式期望值全部来自 banshi（SAN_BIAO/JIU_BIAO/WAI_BIAO）——本模块不自己定义版式，
      否则就是"自己校验自己"；版式一旦变，这里第 4 道门会立刻报出行/列号差异。
    · 禁词表来自 mingcheng.JIN_CI，黑名单来自 shuju.ming_zhong（同一份 HASHES）。
    · 外部两册（行业对标/经营变更）走"允许文本、但不得为空"的宽松全填口径，
      因为它们的单元格里有编码、日期这类非金额文本。

副作用
    只读产物文件；TONG/YI 两个模块级列表累积结果（因此一个进程只跑一次 main 才准确）。
    生成过程会写文件——那是为了"确定性"这道门要现场再生成一遍做逐格比对。
"""
import argparse
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from banshi import JIU_BIAO, SAN_BIAO, SHEETS, WAI_BIAO
from mingcheng import JIN_CI
from shuju import YUE_LIE

MU = Path(__file__).resolve().parent
RONG_CHA = Decimal('0.005')          # 分币容差
TONG, YI = [], []                    # 通过项 / 失败项的文字台账（供末尾摘要与 FAIL 明细）


def rd2(v):
    """四舍五入到分（与模型同口径：HALF_UP）。

    参数: v 可转 Decimal 的数值。
    返回: Decimal 量化到 0.01。
    为什么必须与 shuju 同用 HALF_UP: 生成端用 HALF_UP 落盘，校验端若用 Python 内置
        round()（银行家舍入），0.005 这类边界值会稳定差 1 分，产生"假失败"。
    """
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def rd4(v):
    """四舍五入到四位小数（与模型同口径）。"""
    return Decimal(v).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def jian(ming, hao, xi=''):
    """登记一项断言结果。

    参数: ming 断言名称（会原样打印）；hao 布尔结果；xi 失败明细串（可选）。
    返回: 原样返回 hao，便于 `ok &= jian(...)` 链式累积。
    副作用: 往 TONG/YI 追加一条台账并打印一行 [PASS]/[FAIL]。
    为什么台账存字符串而不存对象: 末尾摘要要按原顺序列 FAIL，字符串最省事也最好读。
    """
    (TONG if hao else YI).append(f'{ming}{("：" + xi) if xi else ""}')
    print(f'  [{"PASS" if hao else "FAIL"}] {ming}' + (f'：{xi}' if xi else ''))
    return hao


def deng(a, b):
    """数值比较（容忍分币尾差）。

    参数: a, b 任意值（None 当 0）。
    返回: 两者差 ≤ RONG_CHA 时 True。
    为什么 None 当 0: xlsx 里空单元格读回 None，而"本月无发生额"在语义上就是 0；
        若把 None 判成失败，未生效月（实时经营册 7~12 月）会集体误报。
    """
    return abs(Decimal(str(a or 0)) - Decimal(str(b or 0))) <= RONG_CHA


def shu(v):
    """格值 → Decimal（None → 0）。"""
    return Decimal(str(v)) if isinstance(v, (int, float)) else Decimal(0)


def san_biao_wei(ming):
    """三表"科目行 × 数据列"格位清单（分区标题行不算）。

    财会2019-6号版式：利润表/现金流量表 B=本期金额 C=上期金额；
    资产负债表 左 B=期末余额 C=上年年末余额，右 E=期末余额 F=上年年末余额。

    参数: ming 表名（利润表/资产负债表/现金流量表）。
    返回: 格位字符串列表（如 ['B5','C5','B6','C6',...]）。
    为什么按"标签是否以：结尾"筛行: 三表里有「一、营业收入」「其中：」这类分区标题行，
        标题行没有金额，若一并要求"全填"会把版式结构当成缺数。
    为什么利润表/现金流量表扫到 47/43 行: 这两个上限是版式里最后一个科目行的行号，
        超出范围的格位即便有数也不是科目行（如脚注），不参与全填判定。
    """
    bq = SAN_BIAO[ming]['biaoqian']
    if ming == '利润表':
        hang = [r for r in range(5, 48) if isinstance(bq.get(f'A{r}'), str)
                and not bq[f'A{r}'].strip().endswith('：')]
        return [f'{x}{r}' for r in hang for x in 'BC']
    if ming == '资产负债表':
        ge = []
        for r in range(5, 46):
            # 资产负债表左右两栏：A 列科目配 B/C 列金额，D 列科目配 E/F 列金额
            for zhu, lie in (('A', 'BC'), ('D', 'EF')):
                v = bq.get(f'{zhu}{r}')
                if isinstance(v, str) and not v.strip().endswith('：'):
                    ge += [f'{x}{r}' for x in lie]
        return ge
    hang = [r for r in range(5, 43) if isinstance(bq.get(f'A{r}'), str)
            and not bq[f'A{r}'].strip().endswith('：')]
    return [f'{x}{r}' for r in hang for x in 'BC']


def men_ling_gongshi(ws_all):
    """1) 零公式。

    参数: ws_all {表名: 工作表}。
    返回: jian() 的布尔结果。
    为什么这条是硬门: 交付要求"纯数值·零公式"——带公式的簿子一旦换环境打开，
        公式缓存失效会显示成 0 或 #REF，而且接收端解析时读到的是公式文本而非数值。
    实现: 全簿逐格扫字符串并以 '=' 开头判定；明细只留前 4 个格位，避免刷屏。
    """
    ji = [f'{s}!{c.coordinate}' for s, ws in ws_all.items()
          for row in ws.iter_rows() for c in row
          if isinstance(c.value, str) and c.value.startswith('=')]
    return jian('零公式（全簿无一格公式）', not ji, str(ji[:4]))


def men_quantian(ws_all, biao_ji=None, san_biao=True, yao_shuzi=True):
    """2) 全填：三表科目行（可选）+ 版式里登记的全部数值位。

    yao_shuzi=True（十二表）：数值位必须是数字；
    yao_shuzi=False（外部册）：数值位允许文本（编码/日期等），但不得为空。

    参数: ws_all 表→工作表；biao_ji 版式集合（缺省 JIU_BIAO）；
        san_biao 是否检查三表科目行（外部册没有三表，传 False）；
        yao_shuzi 数值位是否必须是数字。
    返回: jian() 的布尔结果。
    为什么"有值"与"是数字"要分开: 外部两册里有编码、期间这类文本字段，
        要求它们是数字既做不到也没意义；但"空着"必须报——空白单元格到了接收端
        就是缺失字段，属于硬故障。
    """
    def you_xiao(v):
        """单个格值是否算"填了"。"""
        if v is None:
            return False
        if isinstance(v, str):
            return (not yao_shuzi) and bool(v.strip())
        return isinstance(v, (int, float))

    que = []
    biao_ji = biao_ji if biao_ji is not None else JIU_BIAO
    if san_biao:
        for ming in ('利润表', '资产负债表', '现金流量表'):
            ws = ws_all[ming]
            for ref in san_biao_wei(ming):
                if not isinstance(ws[ref].value, (int, float)):
                    que.append(f'{ming}!{ref}')
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for ref in ban['shuzhi_wei']:
            if not you_xiao(ws[ref].value):
                que.append(f'{ming}!{ref}')
    return jian('全填（科目行/数值位全部有数）', not que, f'缺 {len(que)}：{que[:4]}')


def men_hengdeng(ws_all):
    """3) 恒等式（数值级）。

    参数: ws_all 十二表的 {表名: 工作表}。
    返回: 所有小节都通过才为 True；`ok &= jian(...)` 保证任一小节失败都不会被后续覆盖。

    九个小节（顺序即报告里的出现顺序，编号沿用 05 文档的约定）:
        3.1 税金及附加四税 + 印花税并入      3.6 现金链与资负货币资金衔接
        3.3 分档税逐月/年合计                3.7 资负两栏小计与平衡
        3.4 三费合计/含税合计/月度汇总        3.8 利润表行间关系与每股收益
        3.5 摊销台账/矩阵/归属行 20           3.9 分录借贷平衡与现金流对照覆盖
    （3.2 在早期版本里是"收入成本倒轧"，当前口径已并入 3.8，编号保留不重排，
      避免与文档、历史 FAIL 记录对不上号。）
    每个小节都先累积 ci（失败格位清单）再一次性 jian()：这样一次能报出同类的所有错，
    不用修一个跑一次。
    """
    ok = True
    fei, xj, zf = ws_all['费用表月度汇总'], ws_all['现金流量表'], ws_all['资产负债表']
    sj, tx, fl, lr = (ws_all['税金及附加'], ws_all['摊销明细'],
                      ws_all['分录'], ws_all['利润表'])
    # 3.1 税金及附加：城建7%/教育3%/地方2%/文化0（按增值税应纳额）+ 印花税并入合计
    # 两套行区并存：Z3/AC127 区（分档明细，月列 Q..AB）与老区 B6..B10（合计/四税），
    # 两套必须互相印证，否则下游取哪一套都会读到不同的数。
    ci = []
    lie_fen31 = ('Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB')
    for i, m in enumerate(YUE_LIE):
        x = lie_fen31[i]                                 # Z3 分档区的月列是 Q..AB
        tong = shu(sj[f'{m}33'].value)                   # 本月税金及附加合计（老区行 33）
        a, b, c, d = (shu(sj[f'{x}{r}'].value) for r in (123, 124, 125, 126))
        # 123=城建 124=教育 125=地方 126=文化（演示恒 0）；年合计区在 AC 列同号行
        if tong < 0:
            ci.append(f'{m}33')                          # 附加税不可能为负
        if not deng(d, 0):
            ci.append(f'{m}126')                         # 文化事业建设费按假设必须为 0
        if a and abs(b - rd2(a * Decimal('3') / Decimal('7'))) > Decimal('0.05'):
            ci.append(f'{m}124')                         # 教育 = 城建 × 3/7（同为增值税的 3%/7%）
        if a and abs(c - rd2(a * Decimal('2') / Decimal('7'))) > Decimal('0.05'):
            ci.append(f'{m}125')                         # 地方 = 城建 × 2/7
        if tong < a + b + c + d:                        # 印花税并入后合计不得小于四税之和
            ci.append(f'{m}印花税为负')
        # 老区行映射（05 文档 §4.1）：B6=合计、B7..B10=四税、B4=0、B3=增值税应纳额
        if not deng(sj[f'{m}6'].value, tong):
            ci.append(f'{m}6≠{m}33')                     # 老区合计必须等于分档区月合计
        for hang, v in ((7, a), (8, b), (9, c), (10, d)):
            if not deng(sj[f'{m}{hang}'].value, v):
                ci.append(f'{m}{hang}')                  # 老区四项税逐项对齐分档区
        if not deng(sj[f'{m}4'].value, 0):
            ci.append(f'{m}4')                           # B4（非主控增值税）按口径恒 0
        zeng = shu(sj[f'{m}3'].value)                    # B3 增值税应纳额
        if zeng < 0 or not deng(a, rd2(zeng * Decimal('0.07'))):
            ci.append(f'{m}3')                           # 城建 = 应纳增值税 × 7%
        if zeng and abs((a + b + c) - rd2(zeng * Decimal('0.12'))) > Decimal('0.02'):
            ci.append(f'{m}附加合计12%')                  # 三项附加合计 = 应纳增值税 × 12%
    nian_shou = sum((shu(sj[f'{m}32'].value) for m in YUE_LIE), Decimal(0))
    nian_shui = sum((shu(sj[f'{m}33'].value) for m in YUE_LIE), Decimal(0))
    if nian_shou and not deng(sj['C31'].value, rd4(nian_shui / nian_shou)):
        ci.append('C31')                                 # C31 综合附加率 = 年税 ÷ 年计税收入
    ok &= jian('税金及附加：城建7%/教育3%/地方2%/文化0 + 印花税并入', not ci, str(ci[:4]))
    # 3.3 分档税：逐月合计 = 税金及附加；年合计 = 12 月之和
    lie_fen = ('Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB')
    ci = []
    for i, x in enumerate(lie_fen):
        # 每一列的 127 行是当月分档合计，必须等于老区同月 33 行（两个入口同一个数）
        if not deng(sj[f'{x}127'].value, sj[f'{YUE_LIE[i]}33'].value):
            ci.append(f'{x}127')
    for j in range(4):
        # 年合计区 AC 列：AC123..AC126 必须是 12 个月逐行相加
        if not deng(sj[f'AC{123 + j}'].value,
                    sum(shu(sj[f'{x}{123 + j}'].value) for x in lie_fen)):
            ci.append(f'AC{123 + j}')
    ok &= jian('分档税合计 = 税金及附加（逐月 + 年合计）', not ci, str(ci[:4]))
    # 3.4 三费：合计行 = 明细之和；三费及税金 = 合计 + 附加；汇总 = 三表之和
    ci = []
    for s in ('销售费用', '管理费用'):
        ws = ws_all[s]
        for m in YUE_LIE:
            # 行 4..33 是 30 个明细科目，行 34 是合计：明细必须逐月加总到合计
            if not deng(ws[f'{m}34'].value,
                        sum(shu(ws[f'{m}{r}'].value) for r in range(4, 34))):
                ci.append(f'{s}!{m}34')
            # 行 36 = 行 34 合计 + 行 35 增值税附加（"三费及税金合计"口径）
            if not deng(ws[f'{m}36'].value, shu(ws[f'{m}34'].value) + shu(ws[f'{m}35'].value)):
                ci.append(f'{s}!{m}36')
        for m in YUE_LIE:
            # 费用表的附加行 35 必须与税金及附加同月 33 行相等（同源同一个数）
            if not deng(ws[f'{m}35'].value, sj[f'{m}33'].value):
                ci.append(f'{s}!{m}35')
    for m in YUE_LIE:
        for r in range(4, 37):
            he = sum(shu(ws_all[s][f'{m}{r}'].value) for s in ('销售费用', '管理费用'))
            if not deng(fei[f'{m}{r}'].value, he):
                ci.append(f'费用表月度汇总!{m}{r}')       # 汇总表每行=销售+管理两表之和
    ok &= jian('费用：合计/含税合计/月度汇总（两表之和）逐月', not ci, str(ci[:6]))
    # 3.5 摊销：本月摊销 = ROUND(原值/月数)；矩阵合计 = 本月摊销；累计 + 尚未 = 原值
    # 年份口径：摊销起始 2027-01-01，12 个月各一列（C..N 为月份列，故 yue_lie 平移到 B..M）
    ci = []
    yue_lie = {m: chr(ord(m) - 1) for m in YUE_LIE}       # 平移后月份列 C..N → B..M
    for m, x in yue_lie.items():
        # 月摊销额由原值/月数逐月算出，不在生成端写死——这里反算一次，防止"手滑改数"
        if not deng(tx[f'{x}3'].value, rd2(shu(tx['B1'].value) / shu(tx['B2'].value))):
            ci.append(f'{x}3')
        # 尚未摊销 = 原值 − 累计已摊销（摊销表最核心的恒等式）
        if not deng(tx[f'{x}5'].value, shu(tx[f'{x}1'].value) - shu(tx[f'{x}4'].value)):
            ci.append(f'{x}5')
    for x in ('B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M'):
        # 行 29 是八项资产的月度合计，每个月都必须等于当月摊销总额（B3 为月摊合计）
        if not deng(tx[f'{x}29'].value, shu(tx['B3'].value)):
            ci.append(f'{x}29')
    for i in range(8):
        # 台账 8 行（行 10..17）：月摊销 = ROUND(原值 E / 月数 F)，月数下限 1 防除零
        if not deng(tx[f'G{10 + i}'].value,
                    rd2(shu(tx[f'E{10 + i}'].value) / max(shu(tx[f'F{10 + i}'].value), 1))):
            ci.append(f'G{10 + i}')
    # 三表行 20（折旧及摊销）= 摊销明细当月矩阵合计，按台账归属到各费用表（17-T2 口径）
    for m, x in yue_lie.items():
        he20 = sum((shu(ws_all[s][f'{m}20'].value) for s in ('销售费用', '管理费用')),
                   Decimal(0))
        if he20 > 0 and not deng(he20, shu(tx[f'{x}3'].value)):
            ci.append(f'{m}行20')
    ok &= jian('摊销：本月摊销/尚未摊销/矩阵合计/台账归属行20', not ci, str(ci[:4]))
    # 3.6 现金链（本期 B / 上期 C）+ 与资负货币资金衔接
    # 现金流量表结构：9=经营小计 15=经营净额 22=投资小计 28=投资净额
    #                 33=筹资小计 38=筹资净额 40=净增加 42=期末余额
    # B 列本期、C 列上期同构，所以循环两列即可覆盖"本期 + 上期"两套一致口径。
    ci = []
    for x in ('B', 'C'):
        # 经营小计 = 销售商品/收到其他/退回税费 三项（行 6/7/8）
        if not deng(xj[f'{x}9'].value, sum(shu(xj[f'{x}{r}'].value) for r in (6, 7, 8))):
            ci.append(f'{x}9')
        # 经营支出小计 = 行 10..13
        if not deng(xj[f'{x}14'].value,
                    sum(shu(xj[f'{x}{r}'].value) for r in (10, 11, 12, 13))):
            ci.append(f'{x}14')
        # 经营净额 = 流入小计 − 流出小计
        if not deng(xj[f'{x}15'].value, shu(xj[f'{x}9'].value) - shu(xj[f'{x}14'].value)):
            ci.append(f'{x}15')
        # 投资小计 = 行 17..21；投资净额 = 小计 − 流出小计（行 27）
        if not deng(xj[f'{x}22'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(17, 22))):
            ci.append(f'{x}22')
        if not deng(xj[f'{x}27'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(23, 27))):
            ci.append(f'{x}27')
        if not deng(xj[f'{x}28'].value, shu(xj[f'{x}22'].value) - shu(xj[f'{x}27'].value)):
            ci.append(f'{x}28')
        # 筹资小计 = 行 30..32；筹资净额 = 小计 − 流出小计（行 37）
        if not deng(xj[f'{x}33'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(30, 33))):
            ci.append(f'{x}33')
        if not deng(xj[f'{x}37'].value, sum(shu(xj[f'{x}{r}'].value) for r in range(34, 37))):
            ci.append(f'{x}37')
        if not deng(xj[f'{x}38'].value, shu(xj[f'{x}33'].value) - shu(xj[f'{x}37'].value)):
            ci.append(f'{x}38')
        # 净增加 = 经营 + 投资 + 筹资净额 + 汇率影响（行 39，演示恒 0）
        if not deng(xj[f'{x}40'].value,
                    sum(shu(xj[f'{x}{r}'].value) for r in (15, 28, 38, 39))):
            ci.append(f'{x}40')
        # 期末余额 = 净增加 + 期初余额（行 41）
        if not deng(xj[f'{x}42'].value, shu(xj[f'{x}40'].value) + shu(xj[f'{x}41'].value)):
            ci.append(f'{x}42')
    # 三处跨表衔接：现金流量表期末/期初 ↔ 资负货币资金期末/上年年末；上期期末 ↔ 本期期初
    if not deng(xj['B42'].value, zf['B6'].value):
        ci.append('本期期末↔资负货币资金期末')
    if not deng(xj['B41'].value, zf['C6'].value):
        ci.append('本期期初↔资负货币资金上年年末')
    if not deng(xj['C42'].value, xj['B41'].value):
        ci.append('上期期末↔本期期初')
    ok &= jian('现金链：小计/净额/净增加/期末，且与资负货币资金衔接', not ci, str(ci[:4]))
    # 3.7 资负：两栏小计合计 + 平衡（左 B/C、右 E/F）
    # 左栏：19=流动资产合计(6..18) 39=非流动(21..38) 40=资产总计
    # 右栏：19=流动负债合计 31=非流动负债合计 32=负债合计 44=所有者权益 45=负债和所有者权益
    ci = []
    for x in ('B', 'C'):
        if not deng(zf[f'{x}19'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(6, 19))):
            ci.append(f'{x}19')
        if not deng(zf[f'{x}39'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(21, 39))):
            ci.append(f'{x}39')
        if not deng(zf[f'{x}40'].value, shu(zf[f'{x}19'].value) + shu(zf[f'{x}39'].value)):
            ci.append(f'{x}40')
    for x in ('E', 'F'):
        if not deng(zf[f'{x}19'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(6, 19))):
            ci.append(f'{x}19')
        if not deng(zf[f'{x}31'].value, sum(shu(zf[f'{x}{r}'].value) for r in range(21, 31))):
            ci.append(f'{x}31')
        if not deng(zf[f'{x}32'].value, shu(zf[f'{x}19'].value) + shu(zf[f'{x}31'].value)):
            ci.append(f'{x}32')
        # 所有者权益合计 = 实收资本+其他权益工具+资本公积+库存股+其他综合收益
        #                +专项储备+盈余公积+未分配利润（行 34/35/38/39/40/41/42/43）
        if not deng(zf[f'{x}44'].value,
                    sum(shu(zf[f'{x}{r}'].value) for r in (34, 35, 38, 39, 40, 41, 42, 43))):
            ci.append(f'{x}44')
        if not deng(zf[f'{x}45'].value, shu(zf[f'{x}32'].value) + shu(zf[f'{x}44'].value)):
            ci.append(f'{x}45')
    # 会计恒等式本体：期末、上年年末两个时点都必须 资产 = 负债 + 所有者权益
    if not deng(zf['B40'].value, zf['E45'].value):
        ci.append('期末不平衡')
    if not deng(zf['C40'].value, zf['F45'].value):
        ci.append('上年年末不平衡')
    ok &= jian('资负：小计/合计/两栏平衡（期末 + 上年年末）', not ci, str(ci[:4]))
    # 3.8 利润表：行间关系（本期 B / 上期 C）
    # 关键行号：23=营业利润 26=利润总额 27=所得税 28=净利润 44=综合收益
    #           46=基本每股收益 47=稀释每股收益；上期 C 列同构
    ci = []
    for x in ('B', 'C'):
        # 营业利润 = 收入 − 成本 − 税金 − 销售 − 管理 − 研发 − 财务 + 其他收益 + 投资收益
        #            + 公允 + 信用 + 资产减值 + 处置（行 5..22 带符号展开）
        if not deng(lr[f'{x}23'].value,
                    sum(shu(lr[f'{x}{r}'].value) * k for r, k in
                        ((5, 1), (6, -1), (7, -1), (8, -1), (9, -1), (10, -1), (11, -1),
                         (14, 1), (15, 1), (17, 1), (18, 1), (19, 1), (20, 1), (21, 1),
                         (22, 1)))):
            ci.append(f'{x}23')
        # 利润总额 = 营业利润 + 营业外收入 − 营业外支出
        if not deng(lr[f'{x}26'].value,
                    shu(lr[f'{x}23'].value) + shu(lr[f'{x}24'].value) - shu(lr[f'{x}25'].value)):
            ci.append(f'{x}26')
        # 净利润 = 利润总额 − 所得税
        if not deng(lr[f'{x}28'].value, shu(lr[f'{x}26'].value) - shu(lr[f'{x}27'].value)):
            ci.append(f'{x}28')
        # 演示口径的所得税：利润总额为正时按 25% 计提（亏损不计税，故先判 >0）
        if shu(lr[f'{x}26'].value) > 0 and not deng(
                lr[f'{x}27'].value, rd2(shu(lr[f'{x}26'].value) * Decimal('0.25'))):
            ci.append(f'{x}27')
        # 其他综合收益合计 = 行 33..36 四项；综合收益总额 = 净利润 + 其他综合收益
        if not deng(lr[f'{x}32'].value,
                    sum(shu(lr[f'{x}{r}'].value) for r in (33, 34, 35, 36))):
            ci.append(f'{x}32')
        if not deng(lr[f'{x}37'].value,
                    sum(shu(lr[f'{x}{r}'].value) for r in range(38, 44))):
            ci.append(f'{x}37')
        if not deng(lr[f'{x}31'].value, shu(lr[f'{x}32'].value) + shu(lr[f'{x}37'].value)):
            ci.append(f'{x}31')
        if not deng(lr[f'{x}44'].value, shu(lr[f'{x}28'].value) + shu(lr[f'{x}31'].value)):
            ci.append(f'{x}44')
        # 行 29 是"其中：归属于母公司所有者的净利润"（演示为全资，故等于净利润）
        if not deng(lr[f'{x}29'].value, shu(lr[f'{x}28'].value)):
            ci.append(f'{x}29')
        # 每股收益：净利润 ÷ 100 万股（模板股本单位为万股，故分母是 1,000,000 倍关系）
        if not deng(lr[f'{x}46'].value, rd4(shu(lr[f'{x}28'].value) / Decimal('1000000'))):
            ci.append(f'{x}46')
        # 稀释每股收益 = 净利润 × 0.98（演示给 2% 的稀释影响，模拟潜在普通股）
        if not deng(lr[f'{x}47'].value,
                    rd4(shu(lr[f'{x}28'].value) * Decimal('0.98') / Decimal('1000000'))):
            ci.append(f'{x}47')
    ok &= jian('利润表：营业利润/利润总额/净利润/综合收益/每股收益', not ci, str(ci[:4]))
    # 3.9 分录：借贷平衡 + 对照合计 = 现金流量表同位
    ci = []
    # 合计行由写出器按数据末尾落位 → 按标签动态定位
    he_hang = {}
    for r in range(2, fl.max_row + 1):
        v = fl[f'A{r}'].value
        if v in ('全部借方合计', '全部贷方合计', '借贷差额（应为0）'):
            he_hang[v] = r
    jie_r = he_hang.get('全部借方合计', 0)
    dai_r = he_hang.get('全部贷方合计', 0)
    cha_r = he_hang.get('借贷差额（应为0）', 0)
    if not (jie_r and dai_r and cha_r):
        ci.append('缺合计行')
    # 借方合计 = 贷方合计：复式记账的底线，任何不相等都是写盘级故障
    if jie_r and dai_r and not deng(fl[f'E{jie_r}'].value, fl[f'F{dai_r}'].value):
        ci.append('借贷不平衡')
    # 差额行必须字面为 0（不是"容差内"），这张表的存在意义就是让差额显形
    if cha_r and not deng(fl[f'G{cha_r}'].value, 0):
        ci.append('差额≠0')
    jie = {}
    for r in range(2, jie_r or 2):
        dui = fl[f'G{r}'].value
        # G 列是现金流量表行号：同一行号上所有分录金额相加，应等于该行的"本期金额"
        if isinstance(dui, (int, float)):
            jie[int(dui)] = jie.get(int(dui), Decimal(0)) + shu(fl[f'E{r}'].value)
    for hang, he in jie.items():
        if not deng(he, xj[f'B{hang}'].value):
            ci.append(f'对照{hang}行')
    # 对照须覆盖现金流量表全部"取数行"（有数就必须有分录兜着）
    qu_shu_hang = (6, 7, 8, 10, 11, 12, 13, 17, 18, 19, 20, 21, 23, 24, 25, 26,
                   30, 31, 32, 34, 35, 36)
    lou = [r for r in qu_shu_hang if shu(xj[f'B{r}'].value) != 0 and r not in jie]
    if lou:
        ci.append(f'未覆盖行{lou}')                       # 有金额却没分录 → 表的数没有账支撑
    ok &= jian('分录：借贷平衡 + 对照覆盖并等于现金流量表', not ci, str(ci[:6]))
    return ok


def men_chicun(ws_all, biao_ji=None):
    """4) 尺寸回读：列宽/行高/合并/冻结。

    参数: ws_all 表→工作表；biao_ji 版式集合（缺省 = 十二表各自的版式常量）。
    返回: jian() 的布尔结果。
    为什么连列宽/行高都要校验: 这些属性由 xiechu 从版式常量写盘，任何"写盘时丢了
        某列宽度"的 bug 都不会影响数值，却会让人工打开时版面错乱；只在数值层校验
        是发现不了这类问题的。
    比较容差 0.01: Excel 的列宽/行高是浮点，落盘再读回可能有极小尾差。
    合并区用 sorted 后整体比较：合并区集合无序，但"内容不同"必须报出来；
        逐项比较会产生大量噪声，整体比较一次就能定位到表级。
    冻结窗格按"字符串化后比较"：openpyxl 读回的是 Cell 或 None，与版式里的 'C6'
        这类字符串不同型，必须先归一化。
    """
    ci = []
    biao_ji = biao_ji if biao_ji is not None else {
        m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for i, kuan in ban['lie_kuan'].items():
            zhi = ws.column_dimensions[get_column_letter(int(i))].width
            # 版式里登记过宽度的列，读回必须是同一数值；None 也算失败（说明没写进去）
            if zhi is None or abs(float(zhi) - float(kuan)) > 0.01:
                ci.append(f'{ming}!列{i}')
        for r, gao in ban['hang_gao'].items():
            # 只比较"显式设置过行高"的行；未设置的行由默认行高兜底
            zhi = ws.row_dimensions[int(r)].height
            if zhi is None or abs(float(zhi) - float(gao)) > 0.01:
                ci.append(f'{ming}!行{r}')
        if ban['hang_gao_mo_ren'] and (
                ws.sheet_format.defaultRowHeight is None
                or abs(float(ws.sheet_format.defaultRowHeight)
                       - float(ban['hang_gao_mo_ren'])) > 0.01):
            ci.append(f'{ming}!默认行高')
        if sorted(str(m) for m in ws.merged_cells.ranges) != sorted(ban['hebing']):
            ci.append(f'{ming}!合并区')
        if (str(ws.freeze_panes) if ws.freeze_panes else None) != (ban.get('freeze') or None):
            ci.append(f'{ming}!冻结')
    return jian('尺寸回读：列宽/行高/默认行高/合并区/冻结', not ci, str(ci[:6]))


def men_mingcheng(ws_all):
    """5) 名称：占位符清零 + 禁词零残留。

    参数: ws_all 表→工作表。
    返回: jian() 的布尔结果。
    两道判据:
        · 值里含 '{' —— 占位符（如 {公司}/{年度}）没被 tihuan 渲染掉，属模板缺陷；
        · 值里命中 JIN_CI（mingcheng 禁词表）—— 演示件不得出现真实企业名/敏感词。
    为什么扫全部文本格而不只是"名称格": 主体名会被写进表头、脚注、合并单元格的每一处，
        漏扫一处就可能带出真名；这里是零残留复核的最后一道网。
    """
    liu = [f'{s}!{c.coordinate}' for s, ws in ws_all.items()
           for row in ws.iter_rows() for c in row
           if isinstance(c.value, str) and ('{' in c.value or any(j in c.value for j in JIN_CI))]
    return jian('名称：占位符已渲染、禁词零残留', not liu, str(liu[:4]))


def men_heimingdan(ws_all, biao_ji=None):
    """黑名单：非零数值零命中（豁免：零值 / 三表行次 / 分录对照代码列）。

    参数: ws_all 表→工作表；biao_ji 版式集合（缺省 = 十二表版式）。
    返回: jian() 的布尔结果。
    背景: 演示件不允许出现老师原件里的真实数值。heimingdan.HASHES 里存的是那些数值的
        sha256（只存哈希不存原值），本门把全簿每个非零数值过一遍哈希，命中即失败。
    三处豁免及其理由:
        · 零值 —— 0 是公分母，不可能据以反推原件；
        · 三表行次 —— 版式自带的 6/7/8 这类行号是结构数字，不是业务金额；
        · 分录 G 列 —— 那里放的是"现金流量表第 N 行"的代码，天然会出现 6/15/40 等数字。
    为什么从这里才延迟 import shuju.ming_zhong: shuju 会拉起随机数与整套常量表，
        只有跑到第 5 门时才需要，延迟导入能让前四门更快、也让本模块在缺 shuju 时仍可复用。
    """
    from shuju import ming_zhong
    ci = []
    biao_ji = biao_ji if biao_ji is not None else {
        m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not isinstance(v, (int, float)) or v == 0:
                    continue
                if ming == '分录' and c.column_letter == 'G':       # 对照行号代码（非金额）
                    continue
                bq = ban['biaoqian'].get(c.coordinate)
                if isinstance(bq, (int, float)):                    # 版式自带结构数（三表行次）
                    continue
                if ming_zhong(Decimal(str(v))):
                    ci.append(f'{ming}!{c.coordinate}')
    return jian('黑名单：非零数值零命中（豁免零值/行次/对照列）', not ci, str(ci[:6]))


def men_yangshi(ws_all, biao_ji=None):
    """样式复刻：逐格比对（字体/填充/边框/对齐；数字格式另按规则，不参与比对）。

    参数: ws_all 表→工作表；biao_ji 版式集合（缺省 = 十二表版式）。
    返回: jian() 的布尔结果。
    为什么只比前 16 项: yang_shi_qian 返回的元组里，数字格式（第 17 项起）是按"参照有才覆盖"
        的规则继承来的，天然允许与参照不同；字体/填充/边框/对齐必须逐格一致。
    为什么跳过"空格且非标签"的格: 参照档案里没写值的位置，写出器不会去建样式，
        这类格不存在可比对象；只要它是个有内容的格（或表头标签），就必须比。
    命中 8 个即停: 样式问题通常成片出现，列 8 个足够定位，避免刷满控制台。
    """
    from _tiqu_banshi import yang_shi_qian
    ci = []
    biao_ji = biao_ji if biao_ji is not None else {
        m: (SAN_BIAO.get(m) or JIU_BIAO[m]) for m in SHEETS}
    for ming, ban in biao_ji.items():
        ws = ws_all[ming]
        for ref, idx in ban['ge_ys'].items():
            if ws[ref].value is None and ref not in ban['biaoqian']:
                continue
            if tuple(yang_shi_qian(ws[ref]))[:16] != ban['yangshi'][idx][:16]:
                ci.append(f'{ming}!{ref}')
                if len(ci) >= 8:
                    break
    return jian('样式复刻（字体/填充/边框/对齐逐格一致）', not ci, str(ci[:8]))


def du_qu(lu):
    """读回十二表产物：{表名: 工作表}。

    参数: lu xlsx 路径。
    返回: (workbook, {表名: 工作表})。返回 workbook 是为了调用方负责 close()——
        本函数不关，避免"关早了后面读不到"这类时序问题。
    为什么按 SHEETS 顺序取而不是 wb.sheetnames: 产物表的顺序由 xiechu 保证，
        按 SHEETS 取等于把"十二表都在、且都能按名字找到"这件事一并验证了。
    """
    wb = load_workbook(lu)
    return wb, {s: wb[s] for s in SHEETS}


def du_qu_wai(lu):
    """读回外部册：按实际表名取。

    参数: lu 外部册 xlsx 路径（行业对标/经营变更）。
    返回: (workbook, {表名: 工作表})。
    为什么不像十二表那样用固定 SHEETS: 外部两册的表名与十二表不同，
        且它们的版式由 WAI_BIAO[zhong] 描述，用实际表名更稳（表名本身就是契约的一部分）。
    """
    wb = load_workbook(lu)
    return wb, {s: wb[s] for s in wb.sheetnames}


def _ge_ji(ws_all):
    """全簿格值快照（确定性比对用）。

    参数: ws_all 表→工作表。
    返回: {表名: {格坐标: 值}}。
    为什么快照"全部格"而不只是有值的格: 两次生成若一个多写了一格、一个少写了一格，
        只有把空格也纳入快照，`!=` 比较才会发现差异（缺键 vs 有键）。
    """
    return {s: {c.coordinate: c.value for row in ws.iter_rows() for c in row}
            for s, ws in ws_all.items()}


def main():
    """跑全部门并出摘要。

    返回: 0 = 无失败项；1 = 有失败项。全流程报告.py 按退出码判断放行。
    副作用: 现场生成四册（写 输出/ 或 --out 目录），并对每册再生成一遍做确定性比对；
        因此本脚本产物目录里的文件会被覆盖成同一 seed 的同名文件。
    为什么"确定性"要现场再生成一遍: 可复现是交付纪律，但它只能通过"跑两次比一比"
        证明；比对的是全簿格值快照，任一格不同即列出格位。
    """
    ap = argparse.ArgumentParser(description='演示工作簿校验器（十二表两册 + 外部两册）')
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--out', default=None, help='产物目录（默认 ./输出）')
    ap.add_argument('--hangye', default=None, help='强制行业词（多行业回归用）')
    ap.add_argument('--zhuti', default=None, help='强制主体名（多行业回归用）')
    a = ap.parse_args()
    import shengcheng                                   # 延迟导入：只有要生成时才需要
    chu = Path(a.out) if a.out else (MU / '输出')
    print('== 生成四册 ==')
    si_ce = shengcheng.sheng_si_ce(a.seed, chu, a.hangye, a.zhuti)
    for p in si_ce:
        print(f'  {p.name}（{p.stat().st_size} 字节）')
    # ---- 十二表两册 ----
    for leibie in shengcheng.SHI_ER:
        print(f'== 校验：十二表 / {leibie} ==')
        # 按文件名前缀挑出本类别的册：sheng_si_ce 返回顺序不一定与 SHI_ER 对齐
        lu = next(p for p in si_ce if p.stem.startswith(f'演示-{leibie}-{a.seed}'))
        wb, ws_all = du_qu(lu)
        men_ling_gongshi(ws_all)                        # 1 零公式
        men_quantian(ws_all)                            # 2 全填
        men_hengdeng(ws_all)                            # 3 恒等式（含六类勾稽）
        men_chicun(ws_all)                              # 4 尺寸回读
        men_heimingdan(ws_all)                          # 5 黑名单零命中
        men_yangshi(ws_all)                             # 6 样式复刻
        men_mingcheng(ws_all)                           # 7 名称/禁词
        ge1 = _ge_ji(ws_all)                            # 第一次生成的值快照
        wb.close()
        # 同 seed 再生成一遍：确定性门（纪律要求"可复现"）
        wb2, ws2 = du_qu(shengcheng.sheng(a.seed, leibie, chu, a.hangye, a.zhuti))
        ge2 = _ge_ji(ws2)
        wb2.close()
        bu = [f'{s}!{k}' for s in ge1 for k in ge1[s] if ge1[s][k] != ge2[s].get(k)]
        jian(f'[{leibie}] 确定性：同种子两次生成逐格一致', not bu, str(bu[:4]))
    # ---- 外部两册 ----
    for zhong in shengcheng.WAI:
        print(f'== 校验：外部册 / {zhong} ==')
        lu = next(p for p in si_ce if p.stem.startswith(f'演示-{zhong}-{a.seed}'))
        ban = WAI_BIAO[zhong]
        wb, ws_all = du_qu_wai(lu)
        men_ling_gongshi(ws_all)
        # 外部册没有三表，且允许文本（编码/日期），故全填走宽松口径
        men_quantian(ws_all, ban, san_biao=False, yao_shuzi=False)
        men_chicun(ws_all, ban)
        men_heimingdan(ws_all, ban)
        men_yangshi(ws_all, ban)
        men_mingcheng(ws_all)
        ge1 = _ge_ji(ws_all)
        wb.close()
        wb2, ws2 = du_qu_wai(shengcheng.sheng_wai(a.seed, zhong, chu, a.hangye, a.zhuti))
        ge2 = _ge_ji(ws2)
        wb2.close()
        bu = [f'{s}!{k}' for s in ge1 for k in ge1[s] if ge1[s][k] != ge2[s].get(k)]
        jian(f'[{zhong}] 确定性：同种子两次生成逐格一致', not bu, str(bu[:4]))
    print()
    print('==== 摘要 ====')
    # 摘要行格式被上游按固定模式解析（"通过 N 项，失败 M 项"），改动会静默破坏报告
    print(f'通过 {len(TONG)} 项，失败 {len(YI)} 项')
    for f in YI:
        print('  FAIL:', f)
    return 0 if not YI else 1


if __name__ == '__main__':
    sys.exit(main())
