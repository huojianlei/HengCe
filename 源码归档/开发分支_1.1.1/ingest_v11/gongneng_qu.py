# -*- coding: utf-8 -*-
"""契约 v1.2 扩容定义（唯一事实源）：展示区公式 + 前沿功能区布局。

v1.2 变化（对齐"三表标准对外版式"用户拍板）：
    A) 展示层（ZHANSHI_*）：三表主体区改两列制——利润表/现金流量表 =
       项目｜本期金额（末月）｜本年累计；资产负债表 = 项目｜期末余额｜年初余额
       （左右两侧各一组）。v1.1 的 D..N 月度镜像层整体退役（572 格），月度
       明细仍完整保留在勾稽区（行 60-69 的 C..N）与前沿功能区（P..AA）。
       展示口径升级为全口径：营业利润含投资收益/公允/减值，利润总额=营业利润
       +营业外收支，未分配利润带披露净影响（勾稽区 226 项零改动——展示区
       不参与任何冻结恒等式，实测 12 项展示恒等式全成立）。
    B) 前沿功能区（QU_*）：行 121-480 × 列 15-41 不变；Z1 每股收益链改
       ROUND(D20/P131,4)（修正 v1.1 对 AB125 其中项的重复扣减，并对接
       新展示净利）；Z4 矩阵行名由名称链公式改为文本输入（消除空文本公式，
       使全书公式格均可数值求值缓存）。
本模块零 I/O、纯定义；构建器（jian_qiyue_v11）与导入器（excel_ingest_v11）
共用，保证"契约怎么生成就怎么校验"。公式只用 Book 引擎支持的
四则/SUM/ROUND/MAX/MIN/ABS（xlsx_reader 实测支持集，无 SUMIFS）。
注意：空输入引用一律写 SUM(X:X) 单格区间——引擎裸引用空格返回 None 不能
写缓存，SUM 区间按 0 计（可求值性关键约束，145 格已实测）。
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）｜ v1.2：2026-10-16
"""

# ==== 通用列常量 ====

#: 老区月度列（勾稽区/费用表用）：C..N 共 12 列（1-12 月）
YUE12 = 'CDEFGHIJKLMN'

#: 功能区月度列：P..AA 共 12 列（列 16-27，在前沿列段 15-41 内）
QUYUE12 = ('P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA')

#: 功能区年合计列（Z3 因 P 列是分档率，年合计放 AC）
NIAN_LIE = 'AB'
NIAN_LIE_C = 'AC'

#: 月序号（1 起）→ 功能区月列
def qu_yue(i):
    """月序号（1-12）→ 功能区月列字母。"""
    return QUYUE12[i - 1]


# ==== A) 展示层 v1.2：三表两列制（C=本期/期末，D=累计/年初）====

# ==== 展示层通用说明 ====
# 1) 两列制：C 列=本期金额（资负为期末余额），D 列=本年累计（资负为年初余额）；
#    资负右侧 G/H 与左侧 C/D 对称（账户式）。
# 2) 期末/本期取勾稽区末月列（预算 N=12月；实时 H=已结账截至月 2027-06）；
#    年初取期初参数（C200 期初现金 / 摊销明细!C31 原值 / C201-C203 周转参数）。
# 3) 空输入引用一律 SUM(X:X) 单格区间：引擎裸引用空格得 None 不可缓存，
#    SUM 区间按 0 计——这是 145 个展示格全可求值缓存的关键。
# 4) 展示口径=全口径（营业利润含投资收益/公允/减值；利润总额含营业外；
#    未分配利润带披露净影响），勾稽区 226 项冻结不动、与展示互不牵连。
# 5) 披露净影响 P=营业外收入-营业外支出+投资收益+公允-减值（其中项不重复计）；
#    P>0 计入其他应收款（C10），P<0 计入其他应付款（G13），权益侧带符号。
#

#: 各类别"本期"列：（勾稽区末月列， 功能区末月列）——预算=12 月 N/AA；
#: 实时=已结账截至月（演示固定 2027-06）H/U。契约按类别固化文本。
ZHANSHI_LIE = {'预算基础': ('N', 'AA'), '实时经营': ('H', 'U')}


def zhanshi_biaoqian(leibie):
    """展示区表头标签（v1.2 重钉）：利润表/现金流 C3/D3 + 资负两侧列头。"""
    qi = '12' if leibie == '预算基础' else '6'  # 本期月（已结账末月）
    return {
        '利润表': {'C3': f'本期金额（{qi}月）', 'D3': '本年累计'},
        '资产负债表': {'C2': '期末余额', 'D2': '年初余额',   # 左侧（资产）
                      'G2': '期末余额', 'H2': '年初余额',    # 右侧（负债权益）
                      'C3': f'{qi}月末', 'D3': '年初'},
        '现金流量表': {'C3': f'本期金额（{qi}月）', 'D3': '本年累计'},
    }


def lirun_zhanshi(gj, qu):
    """利润表展示区公式（C=本期金额末月、D=本年累计；全口径小计链）。

    gj=勾稽区本期列（N/H）、qu=功能区本期列（AA/U）。行 10-13/15-17 引
    Z1 披露区输入行，用 SUM(X:X) 防空；行 14/18/20 用 C/D 同列链（读表
    自洽）。D 列年累计 SUM 截至本期列 gj——预算=N（全年）文本与 v1.1 年
    合计口径一致；实时=H（已结账截至月，未结账月的照提摊销不进对外累计，
    保 Δ未分配利润==累计净利恒等）。实测 145 格全可求值、展示恒等式全立。
    """
    return {
        'C4': f'{gj}61', 'D4': f'SUM(C61:{gj}61)',               # 一、营业收入
        'C5': f'{gj}62', 'D5': f'SUM(C62:{gj}62)',               # 减：营业成本
        'C6': f'{gj}63', 'D6': f'SUM(C63:{gj}63)',               # 营业税金及附加
        'C7': f"{gj}64-'销售费用'!{gj}28",
        'D7': f"SUM(C64:{gj}64)-SUM('销售费用'!O28:O30)",         # 销售费用（剔利息重分类）
        'C8': f"{gj}65+{gj}66-'管理费用'!{gj}28-'蓝恐龙费用'!{gj}28",
        'D8': f"SUM(C65:{gj}66)-SUM('管理费用'!O28:O30,'蓝恐龙费用'!O28:O30)",
        'C9': (f"'销售费用'!{gj}28+'销售费用'!{gj}29+'销售费用'!{gj}30"
               f"+'管理费用'!{gj}28+'管理费用'!{gj}29+'管理费用'!{gj}30"
               f"+'蓝恐龙费用'!{gj}28+'蓝恐龙费用'!{gj}29+'蓝恐龙费用'!{gj}30"),
        'D9': "SUM('销售费用'!O28:O30,'管理费用'!O28:O30,'蓝恐龙费用'!O28:O30)",
        'C10': f'SUM({qu}128:{qu}128)', 'D10': 'AB128',            # 资产减值损失
        'C11': f'SUM({qu}129:{qu}129)', 'D11': 'AB129',            # 加：公允价值变动收益
        'C12': f'SUM({qu}126:{qu}126)', 'D12': 'AB126',            # 投资收益
        'C13': f'SUM({qu}127:{qu}127)', 'D13': 'AB127',            # 其中：联营合营
        'C14': 'C4-C5-C6-C7-C8-C9-C10+C11+C12',                    # 二、营业利润（全口径）
        'D14': 'D4-D5-D6-D7-D8-D9-D10+D11+D12',
        'C15': f'SUM({qu}123:{qu}123)', 'D15': 'AB123',            # 加：营业外收入
        'C16': f'SUM({qu}124:{qu}124)', 'D16': 'AB124',            # 减：营业外支出
        'C17': f'SUM({qu}125:{qu}125)', 'D17': 'AB125',            # 其中：处置损失
        'C18': 'C14+C15-C16', 'D18': 'D14+D15-D16',                # 三、利润总额（全口径）
        'C19': f'{gj}68', 'D19': f'SUM(C68:{gj}68)',               # 减：所得税费用
        'C20': 'C18-C19', 'D20': 'D18-D19',                        # 四、净利润（全口径）
        'C22': 'ROUND(C20/P131,4)', 'D22': 'AB132',                # 基本每股收益
        'C23': 'C22', 'D23': 'AB133',                              # 稀释每股收益
    }


def zichanfuzhai_zhanshi(gj):
    """资产负债表展示区公式（C/D=资产期末/年初，G/H=负债权益期末/年初）。

    期末=勾稽区末月列（N/H）；年初=期初参数。披露净影响（Z1 区 AB 列，跨表
    引用）以 MAX 拆入其他应收款/其他应付款，权益侧带符号进未分配利润——
    两向符号下期末/年初平衡与 Δ未分配利润=净利润均实测成立。
    """
    return {
        'C4': f'{gj}61', 'D4': '$C$200',                           # 货币资金
        'C9': '$C$201', 'D9': '$C$201',                            # 应收账款（参数常量）
        'C10': ("MAX('利润表'!AB123-'利润表'!AB124+'利润表'!AB126"
                "+'利润表'!AB129-'利润表'!AB128,0)"),               # 其他应收款（披露应收净额）
        'C13': '$C$202', 'D13': '$C$202',                          # 存货
        'C17': 'C4+C9+C10+C13', 'D17': 'D4+D9+D13',                # 流动资产合计
        'C34': f'{gj}62-$C$201-$C$202',                            # 长期待摊费用（勾稽区62捆含应收存货需拆）
        'D34': "'摊销明细'!$C$31",                                  # 年初未摊销=原值全额
        'C36': 'C34', 'D36': 'D34',                                # 无形资产及其他资产合计
        'C40': 'C17+C36', 'D40': 'D17+D36',                        # 资产总计
        'G6': '$C$203', 'H6': '$C$203',                            # 应付账款
        'G13': ("MAX('利润表'!AB124-'利润表'!AB123-'利润表'!AB126"
                "-'利润表'!AB129+'利润表'!AB128,0)"),               # 其他应付款（负披露净额）
        'G19': 'G6+G13', 'H19': 'H6',                              # 流动负债合计
        'G29': 'G19', 'H29': 'H19',                                # 负债合计
        'G32': f'{gj}65', 'H32': 'C65',                            # 实收资本（勾稽区65=常量权益）
        'G34': f'{gj}65', 'H34': 'C65',                            # 实收资本净额
        'G38': (f"{gj}66+'利润表'!AB123-'利润表'!AB124+'利润表'!AB126"
                f"+'利润表'!AB129-'利润表'!AB128"),                 # 未分配利润（带符号披露净影响）
        'H38': '0',                                                # 年初未分配利润（勾稽#8 首月基数 0）
        'G39': 'G32+G38', 'H39': 'H32+H38',                        # 权益合计
        'G40': 'G29+G39', 'H40': 'H29+H39',                        # 负债和权益总计
    }


# ==== A) 镜像层：现金流量表主体区行 4-40 ====

#: 主体区行类型表（'d'=明细输入行；'h'=段头行，不镜像；其余为公式行，见 _xjl_gongshi）
#: 行号即"现金流对照列"的合法取值域（明细行集合 = 对照代码白名单）。
XJL_LEIXING = {
    4: 'd', 5: 'd', 6: 'd', 7: 'sum:123:125',                      # 经营流入
    8: 'd', 9: 'd', 10: 'd', 11: 'd', 12: 'sum:127:130',           # 经营流出
    13: 'net:126:131', 14: 'h',                                    # 经营净额/段头
    15: 'd', 16: 'd', 17: 'd', 18: 'd', 19: 'd', 20: 'sum:134:138',
    21: 'd', 22: 'd', 23: 'd', 24: 'd', 25: 'sum:140:143',
    26: 'net:139:144', 27: 'h',                                    # 投资净额/段头
    28: 'd', 29: 'd', 30: 'd', 31: 'sum:147:149',
    32: 'd', 33: 'd', 34: 'd', 35: 'sum:151:153',
    36: 'net:150:154',                                             # 筹资净额
    37: 'd',                          # 汇率变动影响（输入行）
    38: 'zeng', 39: 'qichu', 40: 'qimo',                            # 净增加/期初/期末
}

#: 现金流对照代码白名单（主体区明细行号；小计/净额/期初/期末行不可作对照）
DUIZHAO_HEFA = frozenset(r for r, t in XJL_LEIXING.items() if t == 'd' and r not in (37,))

#: 主体区行 → 功能区行的固定位移（4→123 … 40→159，37 行一一对应）
XJL_WEIYI = 119


def xianjinliu_qu_gongshi():
    """现金流功能区公式：月列 P..AA 各行公式 + AB 年合计（返回 {ref: 文本}）。"""
    gongshi = {}
    for i in range(12):                                # 逐月列生成公式
        x = QUYUE12[i]
        for r, lei in XJL_LEIXING.items():             # 逐主体区行（37 行）
            h = r + XJL_WEIYI                          # 区行号（+119 对齐）
            if lei.startswith('sum:'):                # 小计 = 明细段 SUM
                _, a, b = lei.split(':')
                gongshi[f'{x}{h}'] = f'SUM({x}{a}:{x}{b})'
            elif lei.startswith('net:'):              # 净额 = 流入小计-流出小计
                _, a, b = lei.split(':')
                gongshi[f'{x}{h}'] = f'{x}{a}-{x}{b}'
            elif lei == 'zeng':                       # 净增加 = 三净额+汇率
                gongshi[f'{x}{h}'] = (f'{x}132+{x}145+{x}155+{x}156')
            elif lei == 'qichu':                      # 期初：1 月=资负 C200，其后=上月期末
                gongshi[f'{x}{h}'] = ("'资产负债表'!C200" if i == 0
                                      else f'{QUYUE12[i - 1]}159')
            elif lei == 'qimo':                       # 期末 = 期初+净增加
                gongshi[f'{x}{h}'] = f'{x}158+{x}157'
    # AB 列：流量行（含明细/小计/净额/汇率）=SUM(P:AA)；存量行（期初/期末）=12 月值
    for r, lei in XJL_LEIXING.items():
        h = r + XJL_WEIYI
        if lei == 'h':                                # 段头行无值列
            continue
        if lei in ('qichu', 'qimo'):                  # 存量行取 12 月末值
            gongshi[f'AB{h}'] = f'AA{h}'
        else:                                         # 流量行取全年合计
            gongshi[f'AB{h}'] = f'SUM(P{h}:AA{h})'
    return gongshi


def xianjinliu_zhanshi(qu):
    """现金流量表展示区公式（C=本期金额末月、D=本年累计；直接法功能区对位）。

    统一规则：D{r}=AB{r+119}（功能区年合计，存量行=末月值）；C{r} 在公式型
    行（小计/净额/汇率合计/净增加/期初/期末）裸引 {qu}{r+119}，输入型明细行
    用 SUM(X:X) 防空。特例 D39=P158（年初现金=1 月期初，不用功能区默认）。
    """
    gongshi = {}
    for r, lei in XJL_LEIXING.items():
        if lei == 'h':                                # 段头行（14/27）无值
            continue
        h = r + XJL_WEIYI                             # 功能区对位行
        if lei == 'd':                                # 输入明细行：SUM 防空
            gongshi[f'C{r}'] = f'SUM({qu}{h}:{qu}{h})'
        else:                                         # 公式行：裸引可求值
            gongshi[f'C{r}'] = f'{qu}{h}'
        gongshi[f'D{r}'] = f'AB{h}'                   # 本年累计=功能区年合计
    gongshi['D39'] = 'P158'                           # 年初现金=1 月期初（覆盖默认）
    return gongshi


def xianjinliu_shuru():
    """现金流功能区输入格：明细行（含汇率行 156）× 月列 P..AA。"""
    return [f'{x}{r + XJL_WEIYI}'
            for r, lei in XJL_LEIXING.items() if lei == 'd'
            for x in QUYUE12]


# ==== A) 镜像层：费用三表 / 费用表月度汇总 行 35/36 ====

def feiyong_jingxiang():
    """费用三表行 35/36：C..N 月度固化公式 + O 列年度小计（三表同构）。"""
    gongshi = {}
    for biao in ('销售费用', '管理费用', '蓝恐龙费用'):
        for c in YUE12:                               # 12 个月度列逐月固化
            gongshi[f'{biao}!{c}35'] = f"'税金及附加'!{c}33"   # 增值税附加=当月税金
            gongshi[f'{biao}!{c}36'] = f'{c}34+{c}35'          # 三费及税金合计
        gongshi[f'{biao}!O35'] = 'SUM(C35:N35)'       # 年度小计（O 列家族惯例）
        gongshi[f'{biao}!O36'] = 'SUM(C36:N36)'
    return gongshi


def huizong_jingxiang():
    """费用表月度汇总行 35/36：三表同位相加 + 本表合计行 + O 列年度小计。"""
    gongshi = {}
    for c in YUE12:                                   # 汇总=三表同位之和
        gongshi[f'{c}35'] = ("'销售费用'!{}35+'管理费用'!{}35+'蓝恐龙费用'!{}35"
                              .format(c, c, c))       # v1.2 修复：去除 v1.1 尾部多余单引号（语法 bug）
        gongshi[f'{c}36'] = f'{c}34+{c}35'            # 三费及税金合计=行34+行35
    gongshi['O35'] = 'SUM(C35:N35)'                   # 年度小计
    gongshi['O36'] = 'SUM(C36:N36)'
    return gongshi


# ==== B) 前沿功能区：Z1 利润表补充披露区（行 121-133）====

#: 补充披露区行标签（新文本；现金流功能区行标签由构建器从老契约 A 列映射）
BU_CHONG_BIAOQIAN = {
    'O121': '利润表补充披露区（契约v1.1）·营业外与投资收益月度明细',
    'O122': '项目', 'AB122': '年度合计',
    'O123': '营业外收入', 'O124': '营业外支出',
    'O125': '非流动资产处置损失（其中项）', 'O126': '投资收益',
    'O127': '对联营企业和合营企业的投资收益（其中项）',
    'O128': '资产减值损失', 'O129': '公允价值变动收益',
    'O131': '加权平均股数（股，全年）',
    'O132': '基本每股收益（元/股，披露口径）',
    'O133': '稀释每股收益（元/股，演示口径同基本）',
}


def lirun_buchong_qu():
    """Z1 公式与输入：7 行披露月度输入 + AB 合计 + 每股收益链。"""
    biaoshi, shuru = {}, {}
    for r in range(123, 130):                          # 披露行：AB=SUM(P:AA)
        biaoshi[f'AB{r}'] = f'SUM(P{r}:AA{r})'
        for x in QUYUE12:
            shuru[f'{x}{r}'] = 'number'
    shuru['P131'] = 'number'                           # 加权平均股数（全年一个值）
    # 每股收益（v1.2）：分子改用展示区本年累计净利润 D20（全口径，含披露项）；
    # v1.1 旧式 (C20+AB123-AB124-AB125+…) 对 AB125 其中项重复扣减，已修正
    biaoshi['AB132'] = 'ROUND(D20/P131,4)'
    biaoshi['AB133'] = 'AB132'                         # 演示口径无稀释性潜在股份
    return biaoshi, shuru


# ==== B) 前沿功能区：Z3 税种分档区（行 121-127）====

SHUIZHONG_BIAOQIAN = {
    'O121': '税种分档区（契约v1.1·增值税附加明细，演示口径）',
    'O122': '税种', 'P122': '分档率（占计税收入）',
    'O123': '城市维护建设税', 'O124': '教育费附加',
    'O125': '地方教育附加', 'O126': '文化事业建设费',
    'O127': '分档合计', 'AC122': '年度合计',
}

#: 税种分档月列：Q..AB（P 列让位给分档率）
SHUI_YUE12 = ('Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB')


def shuizhong_qu():
    """Z3 公式与输入：分档率 + 月度税额输入 + 合计行/年度合计固化。"""
    biaoshi, shuru = {}, {}
    for r in range(123, 127):
        biaoshi[f'{NIAN_LIE_C}{r}'] = f'SUM(Q{r}:AB{r})'          # 各税种年合计
        shuru[f'P{r}'] = 'number'                                  # 分档率
        for x in SHUI_YUE12:
            shuru[f'{x}{r}'] = 'number'                            # 月度税额
    for x in SHUI_YUE12:                                           # 分档合计行（月度）
        biaoshi[f'{x}127'] = f'SUM({x}123:{x}126)'
    biaoshi[f'{NIAN_LIE_C}127'] = 'SUM(Q127:AB127)'
    return biaoshi, shuru


# ==== B) 前沿功能区：Z4 摊销台账区（行 121-142）====

TANXIAO_BIAOQIAN = {
    'O121': '摊销台账区（契约v1.1·多资产台账与月度矩阵）',
    'O122': '资产名称', 'P122': '费用归属表', 'Q122': '部门',
    'R122': '起始月（YYYY-MM）', 'S122': '原值', 'T122': '摊销月数',
    'U122': '月摊销额',
    'O132': '资产＼月份', 'AB132': '年合计',
    'O142': '合计',
}

#: 台账行数（行 123-130）与矩阵行数（行 133-140），资产一一对应
TAIZHANG_HANG = tuple(range(123, 131))
JUZHEN_HANG = tuple(range(133, 141))


def tanxiao_qu():
    """Z4 公式与输入：台账（U=原值/月数）+ 矩阵（年合计/合计行）+ 名称链。"""
    biaoshi, shuru = {}, {}
    for r in TAIZHANG_HANG:                             # 台账行：O..T 输入，U 固化公式
        biaoshi[f'U{r}'] = f'ROUND(S{r}/MAX(T{r},1),2)'  # 与老区 C33 同款 MAX 防除零
        shuru[f'O{r}'] = 'text'                         # 资产名称
        shuru[f'P{r}'] = 'text'                         # 费用归属表
        shuru[f'Q{r}'] = 'text'                         # 部门
        shuru[f'R{r}'] = 'text'                         # 起始月
        shuru[f'S{r}'] = 'number'                       # 原值
        shuru[f'T{r}'] = 'number'                       # 摊销月数
    for r in JUZHEN_HANG:                               # 矩阵行：名称文本输入 + 月度输入 + 年合计
        biaoshi[f'AB{r}'] = f'SUM(P{r}:AA{r})'
        shuru[f'O{r}'] = 'text'                         # v1.2：行名改文本输入（原名称链公式对空台账行求值为空，无法数值缓存）
        for x in QUYUE12:
            shuru[f'{x}{r}'] = 'number'
    for x in QUYUE12:                                   # 矩阵合计行（月度 + 年度）
        biaoshi[f'{x}142'] = f'SUM({x}133:{x}140)'
    biaoshi['AB142'] = 'SUM(P142:AA142)'
    return biaoshi, shuru


# ==== B) 前沿功能区：Z5 分录全账区（行 121-465）====

FENLU_BIAOQIAN = {
    'O121': '分录全账区（契约v1.1·含现金流科目对照列）',
    'O122': '月份（YYYY-MM）', 'P122': '摘要', 'Q122': '借方科目',
    'R122': '贷方科目', 'S122': '借方金额', 'T122': '贷方金额',
    'U122': '现金流对照（现金流量表主体区行号）', 'V122': '分录号',
    'O463': '全部借方合计', 'O464': '全部贷方合计', 'O465': '借贷差额（应为0）',
}

#: 分录行区间（行 124-460；121-122 表头、463-465 校验行）
FENLU_HANG = (124, 460)


def fenlu_qu():
    """Z5 公式与输入：逐笔分录输入行 + 年度借贷合计/差额固化公式。"""
    biaoshi, shuru = {}, {}
    for r in range(FENLU_HANG[0], FENLU_HANG[1] + 1):
        shuru[f'O{r}'] = 'text'                         # 月份
        shuru[f'P{r}'] = 'text'                         # 摘要
        shuru[f'Q{r}'] = 'text'                         # 借方科目
        shuru[f'R{r}'] = 'text'                         # 贷方科目
        shuru[f'S{r}'] = 'number'                       # 借方金额
        shuru[f'T{r}'] = 'number'                       # 贷方金额
        shuru[f'U{r}'] = 'number'                       # 现金流对照（主体区行号）
        shuru[f'V{r}'] = 'text'                         # 分录号
    a, b = FENLU_HANG
    biaoshi['S463'] = f'SUM(S{a}:S{b})'                 # 全部借方合计
    biaoshi['T464'] = f'SUM(T{a}:T{b})'                 # 全部贷方合计
    biaoshi['U465'] = 'S463-T464'                       # 借贷差额（恒等 0）
    return biaoshi, shuru


# ==== 功能区总装（zone_id → 完整元数据）====

def qu_zongzhuang():
    """汇总五个前沿功能区元数据（构建器与导入器共用的总入口）。

    返回 {zone_id: {'sheet','biaoti','labels','formulas','inputs','shuru_leixing'}}：
        labels   —— 区标题/表头/行标签（文本，逐字固化）；
        formulas —— 固化公式（出现即必须逐字一致）；
        inputs   —— 输入格白名单（ref → 'number'/'text'）。
    """
    qu = {}
    lr_biaoshi, lr_shuru = lirun_buchong_qu()
    qu['lirun_buchong'] = {'sheet': '利润表', 'biaoti': '利润表补充披露区',
                           'labels': dict(BU_CHONG_BIAOQIAN),
                           'labels_yue': True,          # 表头月标签行（构建器生成 P..AA）
                           'formulas': lr_biaoshi, 'inputs': lr_shuru}
    qu['xianjinliu_mingxi'] = {'sheet': '现金流量表', 'biaoti': '现金流量表月度明细区',
                               'labels': None,          # 行标签由构建器从老契约 A 列映射
                               'labels_yue': True,
                               'formulas': xianjinliu_qu_gongshi(),
                               'inputs': {r: 'number' for r in xianjinliu_shuru()}}
    sz_biaoshi, sz_shuru = shuizhong_qu()
    qu['shuizhong_fendang'] = {'sheet': '税金及附加', 'biaoti': '税种分档区',
                               'labels': dict(SHUIZHONG_BIAOQIAN),
                               'labels_yue': False,      # 月标签在 Q..AB（构建器特判）
                               'formulas': sz_biaoshi, 'inputs': sz_shuru}
    tx_biaoshi, tx_shuru = tanxiao_qu()
    qu['tanxiao_taizhang'] = {'sheet': '摊销明细', 'biaoti': '摊销台账区',
                              'labels': dict(TANXIAO_BIAOQIAN),
                              'labels_yue': True,
                              'formulas': tx_biaoshi, 'inputs': tx_shuru}
    fl_biaoshi, fl_shuru = fenlu_qu()
    qu['fenlu_quanzhang'] = {'sheet': '分录', 'biaoti': '分录全账区',
                             'labels': dict(FENLU_BIAOQIAN),
                             'labels_yue': False,
                             'formulas': fl_biaoshi, 'inputs': fl_shuru}
    return qu


def zhanshi_zongzhuang(leibie):
    """展示层总装（v1.2）：{'利润表'|'资产负债表'|'现金流量表'|…: {ref: 公式文本}}。

    三表 = 新版式展示公式；费用三表/汇总 = 行 35/36 固化公式（v1.1 沿用，
    汇总尾引号 bug 已修复）。构建器据此生成 ext 段与骨架底稿。
    """
    gj, qu = ZHANSHI_LIE[leibie]                       # 本期两列（勾稽区/功能区）
    huizong = huizong_jingxiang()
    feiyong = feiyong_jingxiang()
    feiyong_fenbiao = {}
    for biao in ('销售费用', '管理费用', '蓝恐龙费用'):
        feiyong_fenbiao[biao] = {k.split('!')[1]: v for k, v in feiyong.items()
                                 if k.startswith(biao + '!')}
    return {
        '利润表': lirun_zhanshi(gj, qu),
        '资产负债表': zichanfuzhai_zhanshi(gj),
        '现金流量表': xianjinliu_zhanshi(qu),
        '销售费用': feiyong_fenbiao['销售费用'],
        '管理费用': feiyong_fenbiao['管理费用'],
        '蓝恐龙费用': feiyong_fenbiao['蓝恐龙费用'],
        '费用表月度汇总': huizong,
    }
