# -*- coding: utf-8 -*-
"""试算平衡（开发期体检）：分录逐笔汇总到科目 + 三表勾稽。

用法：python -B _shisuan.py [产物路径]

这个脚本解决什么问题:
    演示件的数不是手填的，是"生成 → 写盘"两步出来的。写盘本身不会报错，所以必须有一个
    独立于生成器的体检口子，把 xlsx 读回来、按会计恒等式逐条对账，任何一条 ✗ 就说明
    这一批演示件作废。它是"生成器可复现 + 数据可信"这条纪律的守门人。

输入 / 输出契约:
    输入: 一个 xlsx 路径（命令行第一个参数；缺省读 输出/演示-预算基础-20260923.xlsx）。
    输出: 只有 stdout 文本报告（凭证张数、借贷合计、科目试算表、三表勾稽逐条 ✓/✗），
          **不写任何文件**、不退出非零码——它是人读的体检报告，不是 CI 断言。

口径（金额单位）:
    表里读回来的金额一律是"元、两位小数"的展示值（生成器内部是整数分，写盘时除以 100
    还原成元），所以本脚本用 Decimal 逐格转、不引入浮点误差，比对用精确相等而不是容差。
    勾稽要求是"分毫不差"：差额 0.01 元也判 ✗。

与其他模块的关系:
    不做校验逻辑复用——本脚本刻意独立成一套读法，避免"用生成器的假设去验证生成器的输出"；
    jiaoyan.py 是生成期的强校验（失败即中止），本脚本是生成后的外部复核（事后体检）。

异常边界:
    路径不存在 / sheet 名对不上 → 直接抛异常（这是开发期脚本，不做兜底提示）。
    分录表里找不到"全部借方合计"标记行 → 取不到截断行，遍历会走完整表（结果偏大但不报错）。
"""
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

MU = Path(__file__).resolve().parent          # 本脚本所在目录（默认产物目录的父级）


def shu(v):
    """把单元格值转成 Decimal；非数值（None/空串/文本）一律当 0。

    为什么不用 float(): 金额是两位小数，float 的二进制表示会带来 1e-17 级别的误差，
    而这套体检要求"分毫不差"，所以全程 Decimal。str(v) 再转，避免 float 的尾数污染。
    """
    return Decimal(str(v)) if isinstance(v, (int, float)) else Decimal(0)


def s(v):
    """金额显示格式：千分位 + 两位小数（仅用于打印，不参与比对）。"""
    return f'{v:,.2f}'


def kan(lu):
    """对一本产物做全量体检：试算平衡 → 科目汇总 → 三表勾稽。

    参数:
        lu: xlsx 路径（str 或 Path）。需要含 '分录'/'资产负债表'/'利润表'/'现金流量表' 四张表。

    副作用:
        只打印，不改文件、不改全局状态；末尾 close() 掉工作簿，避免 Windows 下句柄占用。

    勾稽清单（全部按"精确相等"判定）:
        1. 全部凭证 借方合计 == 贷方合计（复式记账恒等式）
        2. 科目汇总表 各科目净额（借−贷）合计 == 0
        3. 资产总计 == 负债合计 + 所有者权益合计（会计恒等式）
        4. 现金流量表期末现金 == 资产负债表货币资金期末
        5. 现金流量表期初现金 == 资产负债表货币资金上年年末
        6. 现金净增加 == 期末 − 期初
        7. 净利润 == 留存收益增加 + 本期分红（利润去向恒等式）
        8. 营业利润 + 营业外收入 − 营业外支出 == 利润总额
        9. 账面结转净利（贷方'利润分配'）== 报表净利润
        10. 银行存款净额（借−贷）== 现金净增加
        11. 综合收益总额 == 净利润 + 其他综合收益
    """
    wb = load_workbook(lu)
    fl = wb['分录']
    print(f'== 试算平衡：{Path(lu).name} ==')
    # ---- 逐笔取分录 ----
    # 用 defaultdict 累加，避免先判断科目是否存在；Decimal(0) 作为初值保持精度。
    jie = defaultdict(lambda: Decimal(0))      # 科目 → 借方发生额
    dai = defaultdict(lambda: Decimal(0))      # 科目 → 贷方发生额
    zhang, hang_shu, bu_ping = 0, 0, []        # 凭证数 / 分录行数 / 单张不平的行号
    mo = 1
    # 先找"全部借方合计"标记行，那条线以下都是汇总区，不能当明细分录读
    for r in range(2, fl.max_row + 1):
        if fl[f'A{r}'].value == '全部借方合计':
            mo = r
            break
    # 明细区：每行是一笔分录的一侧（借或贷），C/D 是科目名，E/F 是金额（元）
    for r in range(2, mo):
        j_ke, d_ke = fl[f'C{r}'].value, fl[f'D{r}'].value
        j_qian, d_qian = shu(fl[f'E{r}'].value), shu(fl[f'F{r}'].value)
        if not j_ke and not d_ke:              # 科目列为空 = 空行，跳过
            continue
        zhang += 1                             # 一行算一张凭证（演示件按"一借一贷"两行一凭证生成）
        hang_shu += 2                          # 每笔凭证固定两行（借行 + 贷行）
        jie[j_ke] += j_qian
        dai[d_ke] += d_qian
        if j_qian != d_qian:                   # 单张凭证借贷不等 → 记账
            bu_ping.append(r)
    he_jie = sum(jie.values(), Decimal(0))     # 按科目汇总后求总借
    he_dai = sum(dai.values(), Decimal(0))     # 按科目汇总后求总贷
    print(f'凭证 {zhang} 张 / 分录 {hang_shu} 行')
    print(f'借方发生额合计 {s(he_jie)}')
    print(f'贷方发生额合计 {s(he_dai)}')
    print(f'差额           {s(he_jie - he_dai)}   '
          f'{"✓ 平衡" if he_jie == he_dai else "✗ 不平"}')
    if bu_ping:
        print(f'  单张不平的行：{bu_ping[:5]}')   # 只报前 5 行，避免刷屏
    print()
    # ---- 科目试算平衡表 ----
    # 按发生额绝对值从大到小排，让金额大的科目排在前面，便于人眼抓重点
    ke_mu = sorted(set(jie) | set(dai), key=lambda k: -(jie[k] + dai[k]))
    print(f'{"科目":<22}{"借方发生额":>18}{"贷方发生额":>18}{"净额(借-贷)":>18}')
    print('-' * 78)
    jing_he = Decimal(0)                       # 各科目净额之和，理论上应为 0
    for k in ke_mu:
        jing = jie[k] - dai[k]
        jing_he += jing
        print(f'{str(k):<22}{s(jie[k]):>18}{s(dai[k]):>18}{s(jing):>18}')
    print('-' * 78)
    print(f'{"合计":<22}{s(he_jie):>18}{s(he_dai):>18}{s(jing_he):>18}   '
          f'{"✓" if jing_he == 0 else "✗"}')
    print()
    # ---- 三表勾稽 ----
    # 格位是固定版式（banshi.py）里的位置，改版式要同步改这里的硬编码格位
    zf, lr, xj = wb['资产负债表'], wb['利润表'], wb['现金流量表']
    zi, fu, qu = shu(zf['B40'].value), shu(zf['E32'].value), shu(zf['E44'].value)   # 资产总计/负债合计/所有者权益合计
    print('-- 三表勾稽 --')
    # 恒等式：资产 = 负债 + 所有者权益
    print(f'资产总计 {s(zi)} = 负债合计 {s(fu)} + 所有者权益合计 {s(qu)} '
          f'{"✓" if zi == fu + qu else "✗"}')
    # 现金流量表的期末/期初现金必须和资产负债表货币资金对的上一分不差
    print(f'期末现金 {s(shu(xj["B42"].value))} = 货币资金期末 {s(shu(zf["B6"].value))} '
          f'{"✓" if shu(xj["B42"].value) == shu(zf["B6"].value) else "✗"}')
    print(f'期初现金 {s(shu(xj["B41"].value))} = 货币资金上年年末 {s(shu(zf["C6"].value))} '
          f'{"✓" if shu(xj["B41"].value) == shu(zf["C6"].value) else "✗"}')
    # 现金流量表内部：净增加 = 期末 − 期初
    print(f'现金净增加 {s(shu(xj["B40"].value))} = 期末 − 期初 '
          f'{s(shu(xj["B42"].value) - shu(xj["B41"].value))} '
          f'{"✓" if shu(xj["B40"].value) == shu(xj["B42"].value) - shu(xj["B41"].value) else "✗"}')
    jing_li = shu(lr['B28'].value)             # 利润表净利润
    zeng_yu = (shu(zf['E43'].value) - shu(zf['F43'].value)      # 未分配利润：期末 − 上年年末
               + shu(zf['E42'].value) - shu(zf['F42'].value))   # 盈余公积：期末 − 上年年末
    fen_hong = shu(xj['B35'].value)                              # 本期分红（分配股利行）
    # 利润去向：净利润 = 留存增加 + 分红（演示件假设不分红以外无其他分配）
    print(f'净利润 {s(jing_li)} = 留存增加 {s(zeng_yu)} + 分红 {s(fen_hong)} '
          f'{s(zeng_yu + fen_hong)} {"✓" if jing_li == zeng_yu + fen_hong else "✗"}')
    # 利润表内部：营业利润 ± 营业外收支 = 利润总额
    print(f'营业利润 {s(shu(lr["B23"].value))} + 营业外收入 {s(shu(lr["B24"].value))} '
          f'− 营业外支出 {s(shu(lr["B25"].value))} = 利润总额 {s(shu(lr["B26"].value))} '
          f'{"✓" if shu(lr["B23"].value) + shu(lr["B24"].value) - shu(lr["B25"].value) == shu(lr["B26"].value) else "✗"}')
    zhuan = dai.get('利润分配', Decimal(0))                      # 本年利润 → 利润分配 的结转额
    # 账表一致：分录里结转的净利，必须等于利润表净利润（差一分就说明结转分录和报表对不上）
    print(f'账面结转净利 {s(zhuan)} = 报表净利润 {s(jing_li)} '
          f'{"✓" if zhuan == jing_li else "✗"}')
    yin_jing = jie.get('银行存款', Decimal(0)) - dai.get('银行存款', Decimal(0))   # 银行存款净额
    # 账表一致：银行存款的借贷净额要等于现金流量表的现金净增加
    print(f'银行存款净额 {s(yin_jing)} = 现金净增加 {s(shu(xj["B40"].value))} '
          f'{"✓" if yin_jing == shu(xj["B40"].value) else "✗"}')
    # 综合收益总额 = 净利润 + 其他综合收益（演示件里其他综合收益通常为 0）
    print(f'综合收益 {s(shu(lr["B44"].value))} = 净利润 {s(jing_li)} + 其他综合收益 '
          f'{s(shu(lr["B31"].value))} '
          f'{"✓" if shu(lr["B44"].value) == jing_li + shu(lr["B31"].value) else "✗"}')
    wb.close()                                 # 显式关簿，释放文件句柄


if __name__ == '__main__':
    # 默认产物路径指向一次历史演示件；命令行给路径就用给的（建议直接指 输出/ 下最新那份）
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        MU / '输出' / '演示-预算基础-20260923.xlsx')
    kan(p)
