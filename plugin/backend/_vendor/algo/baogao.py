# -*- coding: utf-8 -*-
"""报告组装与 Markdown 排版 —— 计算层【数据计算测试报告】的数据组装层。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

口径依据（权威文件，修改本模块前必读）：
    docs/01-需求说明.md v2.0 §3 FR-14（报告一键导出——计算部分：数据排版）
    TODO.md T-28（计算层/AI 层拆分：本模块只做确定性表格排版，
        **不产出一句分析文案**——文案起草归 AI 层，[043]/[045]/[046]）
    docs/11-算法计算层说明.md §2（八单元串联主图）

模块定位（[046] 拆分后）：
    本模块 = **数据组装层**——把八个计算单元的既有输出组装成 BiaoKuai
    （标题 + 表头 + 数据行），并对所有数值做显示转换（金额→元、比率→
    百分比、周转率→次、布尔→是/否、缺数→"—"）。渲染层两套：
    · Markdown 渲染：shengcheng_baogao_md（本模块，标准库，env Python 可用）；
    · Word 渲染：baogao_docx.py（系统 Python + python-docx，真 Word 表格）。
    显示转换只发生在组装层且全部整数运算实现（计算层数据不动一分一毫）。

八单元 + 附表（表格清单，一个分析项目对应一张数据表）：
    单元 1 数据录入（四类归档明细 + 拒绝清单）
    单元 2 滚动预算（逐期 + 年度合计 + 滚动差异）
    单元 3 差异计算（三重对比：固定/滚动/实际/差额/差异率/F-A/预警）
    单元 4 规划/执行拆分（三总量 + 四细分 + 残差 + 恒等式）
    单元 5 单双环判定（判定要素 + 归因依据 + 纠错动作）
    单元 6 积木拆解（四模块 + 未归属 + 净总差异 + 高亮）
    单元 7 平衡计分卡（四维得分/权重 + 总分/等级）
    单元 8 变更溯源（逐 KPI 影响率/方向/作用/占比 + TOP3）
    附表 A KPI 指标库（15 项——BSC/溯源的取数源）
    附表 B 整改清单（类型/优先级/责任模块/审批/进度）
    附表 C 预警汇总（四档计数）

容错纪律（与看板数据接口同款）：任一上游缺省（None）→ 对应节输出
    "（缺料）"占位，不抛错——端到端任何阶段缺料报告仍完整可读。

排版原则（四条，全部可测试）：
    ① 不重算——所有数值直接取上游输出，排版层只做显示转换；
    ② 不缺列——表头列数 = 数据行列数（渲染层保证）；
    ③ 不藏数——缺数以 "—" 显式占位、未归属明细单列、拒绝清单必列；
    ④ 不作文——零自然语言文案，AI 层在数据表之上追加解读。

使用示例（知识点速览，v0.2 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；例题 = 一行红预警差异 + 积木最小链）：

    知识点 1 · 最小链路：组装层与 md 渲染层的排版与数值显示
    >>> from variance import ChayiShuru, jisuan_chayi
    >>> from building_blocks import JimuHang, chai_jimu
    >>> from baogao import BgShuru, shengcheng_baogao_kuai, shengcheng_baogao_md
    >>> chayi = jisuan_chayi([
    ...     ChayiShuru('2026-Q1', '材料价格差异', '成本类',
    ...                10_000_000, 10_000_000, 11_000_000),
    ... ])
    >>> jimu = chai_jimu([JimuHang('2026-Q1', '材料价格差异', 1_000_000, 'A', '红', 1000)])
    >>> kuai = shengcheng_baogao_kuai(BgShuru(chayi=chayi, jimu=jimu))
    >>> # 组装层共 12 块（总览 + 八单元 + 三附表）；缺料块 biao_lie 为空
    >>> (len(kuai), kuai[3].biaoti)
    (12, '单元 3 · 差异计算（步骤 3a/3b）')
    >>> md = shengcheng_baogao_md(BgShuru(chayi=chayi, jimu=jimu))
    >>> '单元 3 · 差异计算' in md and '单元 6 · 积木拆解' in md
    True
    >>> # 金额显示：11,000,000 分 → 110,000.00 元；差异率 1000 基点 → 10.00%
    >>> '110,000.00' in md and '10.00%' in md
    True

    知识点 2 · 上游缺省 → "（缺料）"占位（容错，不抛错）
    >>> md2 = shengcheng_baogao_md(BgShuru())
    >>> '单元 1 · 数据录入' in md2 and '（缺料）' in md2
    True

命名对照表（拼音标识符 → 中文含义）：
    BgShuru             报告输入（11 个上游结果，鸭子类型，均可 None）
    BiaoKuai            数据块（节标题 + 表列表 + 节尾注记）
    shengcheng_baogao_kuai   组装（主组装函数：输出 11 个 BiaoKuai）
    shengcheng_baogao_md     渲染（Markdown 全文；渲染层之一）
    _yuan / _pct / _dai_fuhao_pct / _ci / _shifou   显示转换助手
        （分→元 / 基点→百分比 / 带符号百分比 / 基点→次 / 布尔→是·否）

与上下游的关系：
    上游：八个计算单元（data_ingest/rolling_budget/variance/
          planning_operational/loop_decision/building_blocks/bsc/
          suyuan）+ kpi/zhenggai（附表）——全部鸭子类型契约；
    下游：baogao_docx（Word 渲染）、examples/quanliucheng.py 落盘
          fixtures/jisuan_baogao.md；AI 层（报告文案追加解读，不重排版）。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ======================================================================
# 常量区
# ======================================================================

#: KPI 15 项显示元数据：（字段名, 中文名, 显示类别）
#: pct = 百分比 / ci = 周转率（次）/ tian = 天 / ci_shu = 次数
#: 顺序 = 定稿 §8 清单（财务 9 + 非财务 6）——与 kpi.py 输出字段一一对应
KPI_XIANSHI = (
    ('yingshou_dachenglv_bps', '营收达成率', 'pct'),
    ('chengben_kongzhilv_bps', '成本控制率', 'pct'),
    ('feiyong_pianchalv_bps', '费用偏差率', 'pct'),
    ('maolilv_bps', '毛利率', 'pct'),
    ('jinglirunlv_bps', '净利润率', 'pct'),
    ('xiaoshou_lirunlv_bps', '销售利润率', 'pct'),
    ('zichan_zhouzhuanlv_bps', '资产周转率', 'ci'),
    ('zijin_zhouzhuanlv_bps', '资金周转率', 'ci'),
    ('caigou_chengben_bian_donglv_bps', '采购成本变动率', 'pct'),
    ('gongyinglian_lvyuelv_bps', '供应链履约率', 'pct'),
    ('channeng_liyonglv_bps', '产能利用率', 'pct'),
    ('jiaofu_zhouqi_tian', '交付周期', 'tian'),
    ('kehu_manyilv_bps', '客户满意度', 'pct'),
    ('yewu_jindu_bps', '业务完成进度', 'pct'),
    ('yichang_shijian_shu', '异常事项数量', 'ci_shu'),
)

#: 报告抬头（版本与说明行——纯文本，无自然语言文案）；元信息行
#: 应 T-29#11 要求：版本/模拟数据集标记/财年/金额单位四项齐备
BAOGAO_TAITOU = (
    '# 数据计算测试报告（FinAgent 八单元串联）\n'
    '\n'
    '> 说明：输入数据依次经过八个计算单元处理；一个分析项目对应一张数据表。\n'
    '> 显示口径：金额 = 元（两位小数、千分位）；比率 = 百分比；周转率 = 次。\n'
    '> 计算口径：内部全程整数分 / 基点；缺数显示 "—"；上游缺料显示 "（缺料）"。\n'
    '> 元信息：版本 V1.1 ｜ 数据集 = 模拟（is_simulation=true）｜ 财年 2026 ｜ 金额单位 = 元。\n'
)

#: 缺料占位行（上游 None 时输出，保证报告结构完整）
#: 占位与数据 "—" 的分工：占位 = 整节缺上游；"—" = 表内单格缺数
QUE_LIAO = '（缺料）'

#: 表行元组类型别名（小节标题或 None, 表头, 数据行）
_BIaoXiang = tuple[str | None, tuple[str, ...], list[tuple[str, ...]]]


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class BgShuru:
    """报告输入：十一个上游结果对象（鸭子类型；None = 该节缺料）。

    字段说明（按八单元顺序）：
        ruku:     data_ingest.DaoruJieguo（四类归档 + 拒绝清单）。
        gundong:  rolling_budget.GunDongJieguo（逐期滚动）。
        chayi:    variance.ChayiJieguo（三重对比）。
        chaifen:  planning_operational.ChaifenJieguo（规划/执行拆分）。
        panduan:  loop_decision.PanDuanJieguo（判定 + 依据 + 纠错）。
        jimu:     building_blocks.JimuJieguo（四模块聚合）。
        bsc:      bsc.BscJieguo（四维评分）。
        suyuan:   suyuan.SuyuanJieguo（变更溯源）。
        kpi:      kpi.KpiJieguo（附表 A）。
        zhenggai: zhenggai.ZhenggaiJieguo（附表 B）。
        kanban:   kanban.KanbanShuju（附表 C 预警汇总；缺省时退回 chayi 计数）。
    """

    ruku: object | None = None
    gundong: object | None = None
    chayi: object | None = None
    chaifen: object | None = None
    panduan: object | None = None
    jimu: object | None = None
    bsc: object | None = None
    suyuan: object | None = None
    kpi: object | None = None
    zhenggai: object | None = None
    kanban: object | None = None
    panduan_shuru: object | None = None   # 判定输入快照源（PanDuanShuru，T-29#3）
    gundong_lie: list | None = None       # 多科目滚动结果 [(科目名, GunDongJieguo)]（T-29#1）
    jimu_guihua_yingshe: dict | None = None   # 模块 →（规划差异分, 执行差异分）（T-29#6）


@dataclass(frozen=True)
class BiaoKuai:
    """数据块：节标题 + 表列表 + 节尾注记（组装层产出，渲染层消费）。

    字段说明：
        biaoti:   节标题（如 '单元 1 · 数据录入（步骤 1）'）。
        biao_lie: 表列表——每项 =（小节标题或 None, 表头元组, 数据行列表）；
                  小节标题非 None 时在表前渲染 "### 小节标题"（md）或三级
                  标题（docx）。上游缺料时为空列表。
        zhu:      节尾注记（缺料占位 QUE_LIAO / 附表 B 合计行等；可为空）。
    """

    biaoti: str
    # 渲染契约：md 与 docx 两套渲染器消费同一结构——新增渲染目标零改组装层；
    # mingxi 行列表顺序 = 输入顺序（溯源/审计要求稳定可引用）
    biao_lie: list[_BIaoXiang] = field(default_factory=list)
    zhu: str = ''


# ======================================================================
# 显示转换助手区（全部整数运算实现——计算层数据不动）
# ======================================================================


def _yuan(fen: int | None) -> str:
    """分 → 元显示：两位小数 + 千分位（负号前置）；None → "—"。"""
    # 整数运算实现（divmod 拆元/分）——排版层不用浮点，计算层数据不动
    if fen is None:
        return '—'
    # 负号只前置一次；千分位由 f-string 的 , 格式符完成（显示层特权）
    fu = fen < 0
    v = -fen if fu else fen
    zheng, xiao = divmod(v, 100)
    s = f'{zheng:,}.{xiao:02d}'
    return f'-{s}' if fu else s


def _pct(bps: int | None, weishu: int = 2) -> str:
    """基点 → 百分比显示（476 基点 → 4.76%）；None → "—"。"""
    # 1% = 100 基点：整数 divmod 拆整百分比与小数两位（half-up 已在计算层做完）
    if bps is None:
        return '—'
    # 负号前置；weishu=0 用于权重这类整数百分比（40% 而非 40.00%）
    fu = bps < 0
    v = -bps if fu else bps
    zheng, xiao = divmod(v, 100)
    s = f'{zheng}.{xiao:02d}' if weishu == 2 else f'{zheng}'
    return f'-{s}%' if fu else f'{s}%'


def _dai_fuhao_pct(bps: int | None) -> str:
    """带符号百分比显示（+8.00% / -37.50% / 0.00%）——溯源影响率用。"""
    # 影响率正负都有业务含义（数值上升/下降），显式带符号避免歧义
    if bps is None:
        return '—'
    # 三条分支：正显 +、负显 -、零显 0.00%——方向语义在符号上
    if bps > 0:
        return f'+{_pct(bps)}'
    if bps < 0:
        return f'-{_pct(-bps)}'
    return '0.00%'


def _ci(bps: int | None) -> str:
    """基点 → 周转率"次"显示（20000 基点 → 2 次；9767 → 0.9767 次）。"""
    # 1 次 = 10000 基点（kpi 模块单位约定）；去尾零（2.0000 次 → 2 次）
    if bps is None:
        return '—'
    # 去尾零：rstrip('0') 再 rstrip('.')——2.0000 次 → 2 次、0.9767 保持
    zheng, xiao = divmod(bps, 10000)
    s = f'{zheng}.{xiao:04d}'.rstrip('0').rstrip('.')
    return f'{s} 次'


def _shifou(boo: bool | None) -> str:
    """布尔 → 是/否显示（None → "—"）。"""
    # 判定表/整改表共用——审批标志、显著标志、登记标志统一是/否
    if boo is None:
        return '—'
    return '是' if boo else '否'


def _zhi_xianshi(shuzhi: int, danwei: str) -> str:
    """录入行数值显示：按单位分派（元→分转元；%→基点转百分比；其余原值）。"""
    # 录入行单位只有三类：元 / % / 计数（个·次·天·单·人）——分派即完备
    if danwei == '元':
        return _yuan(shuzhi)
    if danwei == '%':
        return _pct(shuzhi)
    return f'{shuzhi} {danwei}'


def _biao(toubu: tuple[str, ...], hang_lie: list[tuple[str, ...]]) -> str:
    """Markdown 表格组装：表头 + 分隔行 + 数据行（空数据 → 一行"—"）。

    注意：本函数只是 md 渲染层的表格组装器（docx 渲染层在 baogao_docx）。
    """
    # 全模块唯一的表格组装器——列数由表头决定，数据行缺列即数据层 bug
    lie = '| ' + ' | '.join(toubu) + ' |\n'
    fen_ge = '| ' + ' | '.join('---' for _ in toubu) + ' |\n'
    # 空数据：补一行全 "—"（表格结构保持，一眼看出"有表无数据"）
    if not hang_lie:
        hang_lie = [tuple('—' for _ in toubu)]
    neirong = ''.join('| ' + ' | '.join(h) + ' |\n' for h in hang_lie)
    return lie + fen_ge + neirong


# ======================================================================
# 各单元组装函数区（每个单元一个 BiaoKuai——见模块头表格清单）
# ======================================================================


def _zong_lan(shuru: BgShuru) -> BiaoKuai:
    """总览节：三重对比汇总表（T-29#12 应用——快速查看整体执行情况）。"""
    # 位置：报告第一节——评委/会计先看整体、再下钻各单元；
    # 五行结构 = 固定总额 / 滚动总额 / 实际总额 / 总差额 / 总差异率
    # 汇总口径：对差异表各行求和；滚动总额仅含已生成滚动的科目
    biaoti = '总览 · 三重对比汇总'
    chayi = shuru.chayi
    if chayi is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # 三项总额直接对差异表行求和（不重算上游公式）
    he_chushi = sum(x.chushi_fen for x in chayi.xiang)
    he_jizhun = sum(x.jizhun_fen for x in chayi.xiang)
    he_shiji = sum(x.shiji_fen for x in chayi.xiang)
    zong_chae = chayi.heji_chae_fen   # 上游合计字段透传
    # 总差异率 = 总差额 ÷ Σ基准（half-up，带符号——负 = 整体节约）
    if he_jizhun == 0:
        zong_lv = None
    else:
        v = (abs(zong_chae) * 10000 * 2 + he_jizhun) // (2 * he_jizhun)
        zong_lv = v if zong_chae >= 0 else -v
    # 滚动总额只累计「已生成滚动」的行——未生成滚动的科目在单元 3 以 "—" 展示
    gun_he = sum(x.gundong_fen for x in chayi.xiang if x.gundong_fen is not None)
    hang_lie = [
        ('固定预算总额', _yuan(he_chushi)),
        ('滚动预算总额（仅含已生成滚动的科目）', _yuan(gun_he)),
        ('实际总额', _yuan(he_shiji)),
        ('总差额（实际 − 基准合计）', _yuan(zong_chae)),
        ('总差异率', _dai_fuhao_pct(zong_lv)),
    ]
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('项目', '金额（元）/ 比率'), hang_lie)],
    )


def _jie_1(ruku: object | None) -> BiaoKuai:
    """单元 1 数据录入：四类归档明细 + 拒绝清单（两张表）。"""
    # 明细表列：类别/期间/科目/数值/单位/来源/备注——录入层 8 列去掉更新时间
    # （更新时间在报告语境冗余，保留会影响表格宽度）
    biaoti = '单元 1 · 数据录入（步骤 1）'
    # 缺料时 zhu 承载占位——渲染层统一渲染 zhu，缺料与正常路径同构
    if ruku is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # 四类按固定顺序遍历（预算基础→实时经营→行业对标→经营变更）——
    # 表内顺序即录入档案顺序，审计友好
    hang_lie: list[tuple[str, ...]] = []
    for leibie in ('yusuan', 'shishi', 'hangye', 'biangeng'):
        for t in getattr(ruku, leibie, []):
            # T-29#10 应用：经营变更行备注显式补布尔标签——
            # 登记即 true（T-24 字段落地后以真字段为准，此处为展示注记）
            # 注记拼接策略：已有备注则分号续接，否则直接写入——
            # 保证「登记即 true」的语义在报告上可见（T-24 后改读真字段）
            beizhu = t.beizhu
            if t.leibie == '经营变更':
                beizhu = (beizhu + '；' if beizhu else '') + 'is_structural_change=true'
            hang_lie.append((t.leibie, t.qijian, t.kemu,
                             _zhi_xianshi(t.shuzhi, t.danwei), t.danwei,
                             t.laiyuan, beizhu))
    # 拒绝清单（无拒绝行 → 一行"无"）；拒绝行交人工复核——不静默丢弃的展示出口
    jujue = getattr(ruku, 'jujue', [])
    jujue_hang = [(str(x.hanghao), x.yuanyin) for x in jujue] or [('—', '无')]
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[
            ('1.1 归档明细', ('数据类别', '期间', '科目', '数值', '单位', '来源', '备注'), hang_lie),
            ('1.2 拒绝清单（交人工复核）', ('行号', '原因'), jujue_hang),
        ],
    )


def _jie_2(gundong: object | None, gundong_lie: list | None) -> BiaoKuai:
    """单元 2 滚动预算：多科目 → 科目×期间二维表；单科目 → 逐期表。"""
    # 组装说明：md/docx 渲染层共用同一份行数据
    biaoti = '单元 2 · 滚动预算（步骤 2）'
    if gundong_lie:
        # T-29#1 应用：科目×期间二维表——每科目一行，列为各期间滚动额；
        # 期间列按首次出现序排列；末列 = 该科目滚动总额
        # 期间列并集（首次出现序）——多科目期间天然对齐，缺期显式 "—"
        qi_lie: list[str] = []
        for _, g in gundong_lie:
            for t in g.qijian_mingxi:
                if t.qijian not in qi_lie:
                    qi_lie.append(t.qijian)
        hang_lie = []
        for kemu, g in gundong_lie:
            shuzhi = {t.qijian: t.shuzhi_fen for t in g.qijian_mingxi}
            hang = [kemu] + [_yuan(shuzhi.get(q)) for q in qi_lie]
            hang.append(_yuan(g.gundong_zonge_fen))
            hang_lie.append(tuple(hang))
        toubu = ('科目',) + tuple(qi_lie) + ('合计（元）',)
        # T-29#1 应用：累进基数说明（以年初原始分期预算为基数、非链式）
        # 基数说明即 T-29#1 第二问的答案：非链式、保季节轮廓（答辩口径）
        return BiaoKuai(
            biaoti=biaoti,
            biao_lie=[(None, toubu, hang_lie)],
            zhu='滚动基数说明：以年初原始分期预算为基数、非链式滚动，保留季节波动轮廓（T-23 口径）。',
        )
    if gundong is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # 单科目回退路径：逐期行 + 合计 + 滚动差异（旧形态，兼容保留）
    hang_lie = [(t.qijian, t.zhuangtai, _yuan(t.chushi_yusuan_fen),
                 _yuan(t.shuzhi_fen)) for t in gundong.qijian_mingxi]
    hang_lie.append(('年度合计', '—', _yuan(gundong.chushi_zonge_fen),
                     _yuan(gundong.gundong_zonge_fen)))
    hang_lie.append(('滚动差异（滚动 − 初始）', '—', '—',
                     _yuan(gundong.chae_fen)))
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('期间', '状态', '初始预算（元）', '滚动额（元）'), hang_lie)],
    )


def _jie_3(chayi: object | None) -> BiaoKuai:
    """单元 3 差异计算：三重对比表（固定/滚动/实际/基准/差额/率/F-A/预警）。"""
    # 11 列表头——报告中最宽的表；docx 渲染层按同表头生成 Word 表格
    # 列语义：差额 = 实际 − 基准（展示口径）；差异率 = |差额|÷基准（half-up）；
    # 预警三档（无/黄/红）与 F/A 方向规则均来自 variance，本层只排版
    biaoti = '单元 3 · 差异计算（步骤 3a/3b）'
    if chayi is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # 滚动预算列缺省（None）显式 "—"——基准退化固定预算的事实可见；
    # 基准列即方差行 jizhun_fen（滚动优先、缺省退化）
    hang_lie = [
        (x.qijian, x.kemu, x.fangxiang, _yuan(x.chushi_fen),
         _yuan(x.gundong_fen) if x.gundong_fen is not None else '—',
         _yuan(x.shiji_fen), _yuan(x.jizhun_fen), _yuan(x.chae_fen),
         _pct(x.chalv_bps), x.fa, x.yujing)
        for x in chayi.xiang
    ]
    # 合计行：差额求和；F/A 混合方向时上游已判 '—'（口径不在此层重定）
    hang_lie.append(('合计', '—', '—', '—', '—', '—', '—',
                     _yuan(chayi.heji_chae_fen), '—', chayi.heji_fa, '—'))
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('期间', '科目', '方向', '固定预算（元）', '滚动预算（元）',
                          '实际（元）', '对比基准（元）', '差额（元）', '差异率',
                          'F/A', '预警'), hang_lie)],
        # T-29#5 应用：脚注解释 "—" 与阈值（阈值随 variance 常量走，可后台配置）
        zhu='注：① "—"表示该科目本期未生成滚动预算（对比基准退化为固定预算）；'
            '② 预警阈值：|差异率| ≥ 5% 黄色、≥ 10% 红色（可后台配置）。',
    )


def _jie_4(chaifen: object | None) -> BiaoKuai:
    """单元 4 规划/执行拆分：三总量 + 四细分 + 残差 + 恒等式。"""
    # 行序即审计序：总量（恒等式成员）在前、细分（归因）在后、残差收尾
    # 三总量在前（恒等式成员）、四细分在后（归因参考）、残差注明
    biaoti = '单元 4 · 规划/执行拆分（步骤 3c）'
    if chaifen is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # 恒等式行直接展示布尔——规划 + 执行 = 原标准总 的成立性是审计要点
    hang_lie = [
        ('原标准总差异', _yuan(chaifen.yuandan_zong_fen), chaifen.yuandan_zong_fa),
        ('规划总差异（不可控）', _yuan(chaifen.guihua_zong_fen), chaifen.guihua_zong_fa),
        ('执行总差异（可控）', _yuan(chaifen.zhixing_zong_fen), chaifen.zhixing_zong_fa),
        ('恒等式成立（规划 + 执行 = 原标准总）', _shifou(chaifen.hengdengshi_chengli), '—'),
        ('价格规划（细分）', _yuan(chaifen.jiage_guihua_fen), chaifen.jiage_guihua_fa),
        ('价格执行（细分）', _yuan(chaifen.jiage_zhixing_fen), chaifen.jiage_zhixing_fa),
        ('用量规划（细分）', _yuan(chaifen.yongliang_guihua_fen), chaifen.yongliang_guihua_fa),
        ('用量执行（细分）', _yuan(chaifen.yongliang_zhixing_fen), chaifen.yongliang_zhixing_fa),
        # 残差 = 细分合计与总量的解析差额（v2.1 §3：以总量恒等式为准）
        ('残差（价格×用量交叉项解析差额）', _yuan(chaifen.cancha_fen), '—'),
    ]
    # T-29#2 应用：残差来源与处理规则注记（整数运算无浮点噪声——
    # 残差本质是交叉项，规则为小额不参与业务判定、不下游传导）
    zhu = ('注：残差为价格×用量交叉项的解析差额（非计算误差）；处理规则：'
           f'|残差| ≤ {_yuan(10_000)} 元不参与业务判定、不下游传导'
           f'（本例 {_yuan(chaifen.cancha_fen)} 元）。')
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('项目', '金额（元）', 'F/A'), hang_lie)],
        zhu=zhu,
    )


def _jie_5(panduan: object | None, panduan_shuru: object | None = None) -> BiaoKuai:
    """单元 5 单双环判定：判定要素 + 归因依据 + 纠错动作 + 输入快照。"""
    # 依据行数可变（yiju 键数稳定为 6）——渲染层按行列表自适应
    # 判定值即方案 B 输出变量 Loop_Decision；情形编号对应定稿 §4.4 表
    biaoti = '单元 5 · 单双环判定（步骤 4）'
    if panduan is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # 判定要素四行固定顺序——后续依据行数可变（yiju 键数稳定为 6）
    hang_lie = [
        ('判定', str(panduan.panduan)),
        ('情形', str(panduan.qingxing)),
        ('需人工审批', _shifou(panduan.shenpi)),
        ('纠错动作', str(panduan.jiuzheng)),
    ]
    # 归因依据（yiju 字典快照——答辩可溯源）；布尔显式是/否、None 显式 "—"
    for jian, zhi in panduan.yiju.items():
        hang_lie.append((str(jian), _shifou(zhi) if isinstance(zhi, bool)
                         else ('—' if zhi is None else str(zhi))))
    # 备注只在非空时列出（留白边界/建议默认口径声明——诚实展示）
    # 情形释义随备注/纠错动作自然带入（如情形 4 = 结构变更与执行偏差并存）
    # 备注行承载定稿留白与更名声明——诚实展示原则的最后一环
    # 依据行渲染细则：字符串原样、None 显式 "—"——与快照表同规则；
    # 情形释义随备注/纠错动作自然带入（如情形 4 = 结构变更与执行偏差并存）
    if panduan.beizhu:
        hang_lie.append(('备注', str(panduan.beizhu)))
    biao_lie: list[_BIaoXiang] = [(None, ('项目', '值'), hang_lie)]
    # T-29#3 应用：判定输入变量快照表（数值经显示转换；缺项 "—"）
    if panduan_shuru is not None:
        # 快照六要素与 loop_decision.PanDuanShuru 字段一一对应——
        # 判定可完整复算是「数字零幻觉」承诺在报告侧的体现
        kuai_zhao = [
            ('差异率（基点）', str(getattr(panduan_shuru, 'chalv_bps'))),
            ('规划总差异（元）', _yuan(getattr(panduan_shuru, 'guihua_zong_fen', None))),
            ('执行总差异（元）', _yuan(getattr(panduan_shuru, 'zhixing_zong_fen', None))),
            ('原标准成本额（元）', _yuan(getattr(panduan_shuru, 'yuandan_cbf_fen', None))),
            ('结构变更登记', _shifou(getattr(panduan_shuru, 'jie_gou_biangeng', None))),
            ('变更文本', str(getattr(panduan_shuru, 'bianma', '') or '—')),
        ]
        # 快照作为第二张表挂在单元 5 节内（docx 渲染为三级标题小节）
        biao_lie.append(('5.1 判定输入变量快照',
                         ('输入变量', '值'), kuai_zhao))
    return BiaoKuai(biaoti=biaoti, biao_lie=biao_lie)


def _jie_6(jimu: object | None, jimu_guihua_yingshe: dict | None = None) -> BiaoKuai:
    """单元 6 积木拆解：四模块表 + 未归属 + 净总差异 + 高亮。"""
    # 四模块顺序固定（收入/成本/费用/采购——T-21 拍板口径）
    biaoti = '单元 6 · 积木拆解（步骤 5a）'
    if jimu is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # T-29#6 应用：规划/执行两列承接单元 4 输出（映射由调用方注入，
    # 无映射的模块显式 "—"——不虚构分摊数据）
    yingshe = jimu_guihua_yingshe or {}
    # T-29#6 应用：新增两列「其中规划差异 / 其中执行差异」——承接单元 4
    # 拆分输出；映射未覆盖的模块显式 "—"（不虚构分摊数据）
    # 演示注入：采购模块 ← Holmes 拆分结果（材料价格属采购环节）
    def liang_lie(mokuai: str) -> tuple[str, str]:
        # 影子式取值：命中映射 → 双元显示；否则双 "—"（宁缺毋滥）
        ying = yingshe.get(mokuai)
        return (_yuan(ying[0]), _yuan(ying[1])) if ying else ('—', '—')

    # 主行循环：四模块逐行展开为七列（含两列规划/执行拆分承接值）
    hang_lie = []
    for x in jimu.mokuai_lie:
        guihua, zhixing = liang_lie(x.mokuai)
        hang_lie.append((x.mokuai, _yuan(x.chae_fen), x.fa, _pct(x.zhanbi_bps),
                         str(x.hang_shu), guihua, zhixing))
    # 未归属净额 = 净总差异 − 四模块合计（行级明细见 6.1）；
    # 减法重算即账实勾稽——不为零差异留隐藏空间
    weigui_jing = jimu.jing_heji_fen - sum(x.chae_fen for x in jimu.mokuai_lie)
    hang_lie.append(('未归属', _yuan(weigui_jing), '—',
                     _pct(jimu.weiguishu_zhanbi_bps),
                     str(len(jimu.weiguishu_lie)), '—', '—'))
    # 汇总行/高亮行的新增两列恒为 "—"——它们不是模块，无规划执行拆分可言
    hang_lie.append(('净总差异（实际合计 − 基准合计）', _yuan(jimu.jing_heji_fen),
                     '—', '—', '—', '—', '—'))
    hang_lie.append(('核心问题模块',
                     jimu.hexin_mokuai if jimu.hexin_mokuai else '无',
                     '—', '—', '—', '—', '—'))
    biao_lie: list[_BIaoXiang] = [
        (None, ('模块', '差异额（元）', 'F/A', '占比', '行数',
                '其中规划差异（元）', '其中执行差异（元）'), hang_lie),
    ]
    # 未归属明细只在存在时列出——不静默丢弃、也不无病呻吟
    # 未归属行的规划/执行两列为 "—"——拆分结果未按科目下钻前无法归属
    if jimu.weiguishu_lie:
        weigui = [(x.qijian, x.kemu, _yuan(x.chae_fen)) for x in jimu.weiguishu_lie]
        biao_lie.append(('6.1 未归属明细（科目映射不中，交人工补映射）',
                         ('期间', '科目', '差额（元）'), weigui))
    return BiaoKuai(biaoti=biaoti, biao_lie=biao_lie)


def _jie_7(bsc: object | None) -> BiaoKuai:
    """单元 7 平衡计分卡：四维得分/权重 + 总分/等级。"""
    # 权重来自 quanzhong 元组——逐维对应四行，None 权重显式 "—"
    # 权重显示整数百分比（40% 风格）；得分列不封顶——>100 原样展示（T-05）
    biaoti = '单元 7 · 平衡计分卡（步骤 5b）'
    if bsc is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # T-29#7 应用：新增达成率列——BSC 得分溯源（得分 = 达成率 × 100 线性折算）
    # 达成率四元组：优先读回显字段（bsc v0.2+）；旧结果对象缺字段时 "—"
    dcl = (getattr(bsc, 'caijing_bps', None), getattr(bsc, 'kehu_bps', None),
           getattr(bsc, 'neibu_bps', None), getattr(bsc, 'xuexi_bps', None))
    qz = bsc.quanzhong if bsc.quanzhong else (None, None, None, None)
    hang_lie = [
        ('财务', _pct(dcl[0]), str(bsc.caijing_defen),
         _pct(qz[0] * 100, 0) if qz[0] is not None else '—'),
        ('客户', _pct(dcl[1]), str(bsc.kehu_defen),
         _pct(qz[1] * 100, 0) if qz[1] is not None else '—'),
        ('内部流程', _pct(dcl[2]), str(bsc.neibu_defen),
         _pct(qz[2] * 100, 0) if qz[2] is not None else '—'),
        ('学习成长', _pct(dcl[3]), str(bsc.xuexi_defen),
         _pct(qz[3] * 100, 0) if qz[3] is not None else '—'),
        # 总分与等级两行收尾——五档等级按总分整数判定（完整版行 69-71）
        ('总分', '—', str(bsc.zongfen), '—'),
        ('等级', '—', str(bsc.dengji), '—'),
    ]
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('维度', 'KPI 达成率', '得分', '权重'), hang_lie)],
        zhu='维度得分 = KPI 达成率 × 100（线性折算 0–100 分，超 100 不封顶——T-05）；'
            '总分 = Σ(权重 × 维度得分)。',
    )


def _jie_8(suyuan: object | None) -> BiaoKuai:
    """单元 8 变更溯源：逐 KPI 影响表 + 正负向 TOP3。"""
    # 影响率列用带符号百分比（方向一目了然）；TOP3 作第二张表
    # 影响率带符号 = 数值方向；作用列 = 偏好表语义——两列不可混读
    biaoti = '单元 8 · 变更溯源（步骤 6）'
    if suyuan is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    # T-29#4 应用：新增【计算公式】列——公式文本来自 suyuan 结果字段
    # 公式文本整列相同（同一口径）——列存在本身即「可手工验算」的声明
    gongshi = getattr(suyuan, 'gongshi', '') or ''
    hang_lie = [
        (x.kpi_mingcheng, gongshi, _dai_fuhao_pct(x.yingxianglv_bps),
         x.shuzhi_fangxiang, x.zuoyong, _pct(x.zhanbi_bps))
        for x in suyuan.xiang
    ]
    # TOP3 两列表：横向并排一表（同结构双列），空列表显式 "—"
    top3 = [(', '.join(suyuan.zhengxiang_top3) or '—',
             ', '.join(suyuan.fuxiang_top3) or '—')]
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[
            (None, ('KPI', '计算公式', '影响率', '数值方向', '作用', '影响占比'), hang_lie),
            ('8.1 作用方向 TOP3', ('正向作用 TOP3', '负向作用 TOP3'), top3),
        ],
    )


def _fubiao_a(kpi: object | None) -> BiaoKuai:
    """附表 A：KPI 指标库 15 项（BSC/溯源取数源）。"""
    # 15 行固定——KPI_XIANSHI 元数据即本表的行生成器（三类单位分派显示）
    # 附表定位：BSC/溯源共同取数源的完整快照——15 项缺数以 "—" 显示；
    # 三类显示分派（pct/ci/tian·ci_shu）在下方逐项完成
    biaoti = '附表 A · KPI 指标库（步骤 1b）'
    if kpi is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    hang_lie = []
    # 三类分派：pct→百分比 / ci→次（去尾零）/ tian·ci_shu→原值+单位后缀
    for ziming, mingcheng, leibie in KPI_XIANSHI:
        zhi = getattr(kpi, ziming)
        # 缺数一律 "—"——附表是「取数源快照」，缺什么一目了然
        if leibie == 'pct':
            xianshi = _pct(zhi)
        elif leibie == 'ci':
            xianshi = _ci(zhi)
        elif leibie == 'tian':
            xianshi = f'{zhi} 天' if zhi is not None else '—'
        else:
            xianshi = f'{zhi} 次' if zhi is not None else '—'
        hang_lie.append((mingcheng, xianshi))
    # 两列表：KPI 名 + 显示值——15 行顺序即定稿清单顺序
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('KPI', '数值'), hang_lie)],
    )


def _fubiao_b(zhenggai: object | None) -> BiaoKuai:
    """附表 B：整改清单（AI 层文案起草的输入）。"""
    # 八列表头与 zhenggai.ZhenggaiXiang 字段一一对应——透传完整性
    # 本表即 AI 层文案起草的输入——表格完整性与优先级排序在此锁定
    biaoti = '附表 B · 整改清单（步骤 8 计算底座）'
    if zhenggai is None:
        return BiaoKuai(biaoti=biaoti, zhu=QUE_LIAO)
    hang_lie = [
        (x.leixing, x.youxianji, x.zeren_mokuai, x.qijian or '—', x.kemu or '—',
         x.miaoshu, _shifou(x.shenpi), x.zhuangtai)
        for x in zhenggai.qingdan
    ]
    # 空清单补一行 "—"（上游无整改项是合法状态——报告照常出）；
    # 期间/科目对判定类条目为空，显式 "—" 对齐八列
    if not hang_lie:
        hang_lie = [tuple('—' for _ in range(8))]
    # 合计行：总数与三档计数——优先级分布一眼可读
    zhu = f'\n合计：{zhenggai.zong_shu} 条（高 {zhenggai.gao_shu} / ' \
          f'中 {zhenggai.zhong_shu} / 低 {zhenggai.di_shu}）\n'
    return BiaoKuai(
        biaoti=biaoti,
        biao_lie=[(None, ('类型', '优先级', '责任模块', '期间', '科目', '描述',
                          '需审批', '状态'), hang_lie)],
        zhu=zhu,
    )


def _fubiao_c(shuru: BgShuru) -> BiaoKuai:
    """附表 C：预警汇总（四档计数）+ 预警科目定位明细（T-29#9 应用）。"""
    # 本表同时服务 md/docx 两种渲染——数据与展示彻底分离的证据；
    # kanban 优先（看板同源）；缺省退回 chayi 计数——两条路同一组数；
    # 阈值语义：红 ≥10% / 黄 ≥5%（T-29#5 应用后）/ 无 <5% / 无法定级 = 基准 0
    biaoti = '附表 C · 预警汇总'
    # 计数来源两级回退：kanban 汇总 → chayi 计数 → 全 "—" 占位
    kanban = shuru.kanban
    if kanban is not None and kanban.yujing_huizong:
        hz = kanban.yujing_huizong
        hang_lie = [(str(hz['hong_shu']), str(hz['huang_shu']),
                     str(hz['wu_shu']), str(hz['wufa_shu']))]
    elif shuru.chayi is not None:
        hang_lie = [(str(shuru.chayi.hong_shu), str(shuru.chayi.huang_shu),
                     str(shuru.chayi.wu_shu), str(shuru.chayi.wufa_shu))]
    else:
        # 全缺料 → 一行 "—"（四档计数的空形态）
        hang_lie = [('—', '—', '—', '—')]
    biao_lie: list[_BIaoXiang] = [
        (None, ('红色预警', '黄色预警', '无预警', '无法定级'), hang_lie),
    ]
    # T-29#9 应用：预警科目定位——红/黄行逐行列出
    # （报告位置 = 单元 3 差异表的第几数据行，可直接回查）
    # 定位明细只列红/黄两档——无预警行不占表（与计数口径一致）
    if shuru.chayi is not None:
        dingwei = []
        for xuhao, x in enumerate(shuru.chayi.xiang, start=1):
            if x.yujing in ('红', '黄'):
                dingwei.append((f'{x.yujing}色预警', x.kemu, f'单元 3 第 {xuhao} 行'))
        if dingwei:
            # 报告位置格式「单元 3 第 N 行」——N 即差异表第 N 条数据行
            biao_lie.append(('C.1 预警科目定位', ('档位', '科目', '报告位置'), dingwei))
    return BiaoKuai(biaoti=biaoti, biao_lie=biao_lie)


# ======================================================================
# 组装层入口（数据块列表——渲染层（md/docx）的共同输入）
# ======================================================================


def shengcheng_baogao_kuai(shuru: BgShuru) -> list[BiaoKuai]:
    """组装数据块（总览 + 八单元 + 三附表；纯函数，零自然语言文案）。

    参数：shuru —— BgShuru（十一个上游结果，均可缺省 None）。

    返回：12 个 BiaoKuai（顺序 = 总览 + 方案 B 步骤顺序 + 三附表）；
    任一上游缺省 → 对应块 biao_lie 为空、zhu = "（缺料）"。
    """
    # 类型门禁与全项目一致（ValueError 族留给算法校验，这里是接口契约）
    if not isinstance(shuru, BgShuru):
        raise TypeError(f'输入必须是 BgShuru：{shuru!r}')

    # 十二块按方案 B 步骤顺序组装（总览→录入→滚动→差异→拆分→判定→积木→BSC→溯源）；
    # 返回列表即两种渲染层的共同输入——md 与 docx 内容必然一致
    return [
        _zong_lan(shuru),
        _jie_1(shuru.ruku),
        _jie_2(shuru.gundong, shuru.gundong_lie),
        _jie_3(shuru.chayi),
        _jie_4(shuru.chaifen),
        _jie_5(shuru.panduan, shuru.panduan_shuru),
        _jie_6(shuru.jimu, shuru.jimu_guihua_yingshe),
        _jie_7(shuru.bsc),
        _jie_8(shuru.suyuan),
        _fubiao_a(shuru.kpi),
        _fubiao_b(shuru.zhenggai),
        _fubiao_c(shuru),
    ]


# ======================================================================
# 渲染层一：Markdown（标准库，env Python 可用）
# ======================================================================
# 渲染规则（与 baogao_docx 渲染层保持语义一致）：
#   节标题 → '## '；小节标题 → '### '；数据块 → 管道表格；
#   缺料节 → 标题后跟占位行；节尾注记（zhu）紧随表格之后。
# ======================================================================


def shengcheng_baogao_md(shuru: BgShuru) -> str:
    """生成数据计算测试报告（Markdown 全文；纯函数，零自然语言文案）。

    参数：shuru —— BgShuru（十一个上游结果，均可缺省 None）。

    返回：完整 Markdown 文本——总览 + 八单元各一节一表 + 三个附表；
    任一上游缺省 → 对应节输出"（缺料）"占位，不抛错。
    """
    # 组装与渲染分离：本函数只消费 BiaoKuai，不再触碰任何上游对象——
    # 新增渲染目标（docx/HTML）时组装层零改动
    kuai_lie = shengcheng_baogao_kuai(shuru)
    # md 渲染：同一份 BiaoKuai 列表——与 baogao_docx 双渲染互证
    suipian: list[str] = []
    for kuai in kuai_lie:
        # 每个单元一节一表——「一个分析项目对应一张数据表」即此结构
        suipian.append(f'## {kuai.biaoti}\n\n')
        # 缺料占位：报告结构完整，节内只有占位行——与看板容错同款纪律
        if not kuai.biao_lie:
            suipian.append(QUE_LIAO + '\n\n')
            continue
        # 小节标题（1.1/1.2/6.1/8.1）渲染为三级标题；主表无小节标题
        for i, (zi_biaoti, toubu, hang_lie) in enumerate(kuai.biao_lie):
            if zi_biaoti is not None:
                suipian.append(f'### {zi_biaoti}\n\n')
            suipian.append(_biao(toubu, hang_lie))
            if i < len(kuai.biao_lie) - 1:
                suipian.append('\n')
        if kuai.zhu:
            suipian.append(kuai.zhu)
        suipian.append('\n')
    # 抬头 + 十一节拼接；rstrip 去尾部空行——文件末尾恰好一个换行
    # 抬头（含元信息行）在前、各节依序拼接——文件可直接被 Word/md 渲染器消费
    return BAOGAO_TAITOU + '\n' + ''.join(suipian).rstrip() + '\n'
