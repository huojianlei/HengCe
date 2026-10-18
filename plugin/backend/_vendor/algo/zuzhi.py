# -*- coding: utf-8 -*-
"""组织单元识别与部门汇总 —— 报告精确到部门的算法底座。

背景（2026-09-24 用户拍板）：输入模板结构已定死，不得改动；部门维度由
【程序识别】取得——批次内每份工作簿是一个主体，主体名称写成「机构/部门」
时按层级归并，未写分隔符时该主体自身即一个组织单元。本模块只做识别与
汇总，不读文件、不写文件、不认识 Excel。

与桌面引擎的关系：`desktop/engine.mjs` 的 `zuzhi_shibie`/`zuzhi_huizong`
是同口径的 JavaScript 实现（供界面实时渲染）；本模块是 Python 侧的算法
实现，两者用同一组手算样例互相印证（见 tests/test_zuzhi.py 与
desktop/tests/zuzhi.test.mjs 的同名断言）。

命名规范（2026-08-23 用户指令）：标识符全拼音、数据值中文、文件英文。
数值纪律：金额一律整数「分」，比率一律「基点」（1% = 100），本模块不做
除法以外的换算，也不引入浮点。

使用示例（知识点速览，doctest 格式，`python -m doctest zuzhi.py` 可验证）：

    知识点 1 · 识别主体名称里的机构与部门
    >>> from zuzhi import shibie_zuzhi
    >>> shibie_zuzhi('衡策中学/教务处')
    ('衡策中学', '教务处')
    >>> shibie_zuzhi('后勤处')            # 不写分隔符：该主体自身就是一个组织单元
    ('后勤处', '后勤处')
    >>> shibie_zuzhi('衡策中学/二级学院/会计学院')   # 多级：取最后一段为部门
    ('衡策中学/二级学院', '会计学院')
    >>> shibie_zuzhi('  衡策中学 ／ 学生处  ')        # 容忍全角斜杠与首尾空白
    ('衡策中学', '学生处')

    知识点 2 · 汇总一个组织单元（差额＝实际 − 基准；绝对偏差不抵消有利/不利）
    >>> from zuzhi import BumenShuru, juhe_bumen
    >>> jiaowu = BumenShuru('衡策中学/教务处', 500000, 460000, ((60000, 'A'), (-100000, 'A')), 0, 4, 1)
    >>> houqin = BumenShuru('衡策中学/后勤处', 300000, 340000, ((60000, 'F'), (-20000, 'A')), 0, 2, 2)
    >>> huizong = juhe_bumen([jiaowu, houqin])
    >>> huizong.jigou
    '衡策中学'
    >>> [(x.bumen, x.cha_e_fen, x.juedui_cha_fen, x.fangxiang) for x in huizong.bumen_lie]
    [('教务处', -40000, 160000, '不利'), ('后勤处', 40000, 80000, '有利')]

    知识点 3 · 机构合计恒等于各部门相加，行数可核对
    >>> (huizong.jizhun_fen, huizong.shiji_fen, huizong.cha_e_fen)
    (800000, 800000, 0)
    >>> (huizong.juedui_cha_fen, huizong.youli_fen, huizong.buli_fen)
    (240000, 60000, 180000)
    >>> sum(x.juedui_cha_fen for x in huizong.bumen_lie) == huizong.juedui_cha_fen
    True

    知识点 4 · 偏差排行（按绝对偏差降序，占比为万分之一基点的整数）
    >>> huizong.paihang
    (('教务处', 160000, 6667), ('后勤处', 80000, 3333))

    知识点 5 · 多机构与空输入的行为约定
    >>> a = BumenShuru('东区', 100, 100, ((0, 'N'),))
    >>> b = BumenShuru('西区', 100, 100, ((0, 'N'),))
    >>> juhe_bumen([a, b]).jigou          # 不同机构不强行归并，回落到统一称呼
    '全部组织单元'
    >>> juhe_bumen([])
    Traceback (most recent call last):
        ...
    ValueError: 组织单元批次不能为空

口径依据：desktop/engine.mjs 的 zuzhi_huizong（同批次逐主体分析结果）；
         docs/唯一Excel输入模板规格书-1.0.5.md「主体/情景/期间」批次字段。
建立：2026-09-24 ｜ Agent：ZCode（deepseek-flash）
"""

from dataclasses import dataclass

#: 主体名称里机构与部门的分隔符（半角与全角斜杠都接受）
FEN_GE_ZI = ('/', '／')
#: 缺省机构名：一个批次里出现多个机构、无法归并时使用
QUANBU_JIGOU = '全部组织单元'
#: 未命名时的兜底名称（主体名称为空字符串时）
WEI_MING_MING_JIGOU = '未命名机构'
WEI_MING_MING_BUMEN = '未命名组织单元'


def shibie_zuzhi(zhuti_mingcheng: str) -> tuple[str, str]:
    """从主体名称识别（机构, 部门）：取最后一段为部门，其余为机构。

    约定（用户 2026-09-24 拍板的识别口径）：
        - 含分隔符：'机构/部门' → 机构='机构'，部门='部门'；
          多级 '机构/二级/三级' → 机构='机构/二级'，部门='三级'；
        - 不含分隔符：该主体自身就是一个组织单元，机构与部门同名；
        - 空名称：回落到"未命名机构/未命名组织单元"，不抛异常
          （名称合法性由模板导入层负责，这里只保证不崩）。
    """
    wenben = str(zhuti_mingcheng or '').strip()
    # 先把全角斜杠统一成半角，再按半角切分，避免两套分隔符各写一遍逻辑。
    for zi in FEN_GE_ZI[1:]:
        wenben = wenben.replace(zi, FEN_GE_ZI[0])
    duan = [x.strip() for x in wenben.split(FEN_GE_ZI[0]) if x.strip()]
    if not duan:
        return WEI_MING_MING_JIGOU, WEI_MING_MING_BUMEN
    if len(duan) == 1:
        return duan[0], duan[0]
    return FEN_GE_ZI[0].join(duan[:-1]), duan[-1]


def _bps(zifen: int, fenmu: int) -> int:
    """整数基点占比（四舍五入到整数）；分母为 0 时返回 0 而不是抛错。"""
    if not fenmu:
        return 0
    return (zifen * 10000 + fenmu // 2) // fenmu


@dataclass(frozen=True)
class BumenShuru:
    """一个组织单元的已核验分析摘要（由逐主体分析结果转换而来）。

    xiang 是逐科目的（差额分, 有利性）二元组：有利性取 'F'（有利）、
    'A'（不利）、'N'（持平），与差异分析模块的 fa 记号一致。
    """

    zhuti_mingcheng: str
    jizhun_fen: int                     # Σ 比较基准（届满前滚动基准，缺省时为原始预算）
    shiji_fen: int                      # Σ 实际发生额
    xiang: tuple[tuple[int, str], ...]  # 逐科目 (差额分, 有利性)
    yujing_shu: int = 0                 # 命中预警档位的科目期间数
    zhenggai_shu: int = 0               # 整改任务数
    wancheng_shu: int = 0               # 已完成整改数


@dataclass(frozen=True)
class BumenYuan:
    """汇总后的一个部门（组织单元）行，字段与桌面端 DTO 同名同义。"""

    bumen: str
    jigou: str
    jizhun_fen: int
    shiji_fen: int
    cha_e_fen: int
    juedui_cha_fen: int
    youli_fen: int
    buli_fen: int
    fangxiang: str
    yujing_shu: int
    zhenggai_shu: int
    wancheng_shu: int
    wancheng_bps: int


@dataclass(frozen=True)
class JigouYuan:
    """按机构归并的小计行（一个机构下的部门相加）。"""

    jigou: str
    bumen_shu: int
    jizhun_fen: int
    shiji_fen: int
    cha_e_fen: int
    juedui_cha_fen: int
    yujing_shu: int


@dataclass(frozen=True)
class BumenHuizong:
    """整批组织单元的汇总结果：部门行 + 机构小计 + 排行 + 合计。"""

    jigou: str
    bumen_lie: tuple[BumenYuan, ...]
    jigou_lie: tuple[JigouYuan, ...]
    paihang: tuple[tuple[str, int, int], ...]  # （部门, 绝对偏差分, 占比基点）按绝对偏差降序
    jizhun_fen: int
    shiji_fen: int
    cha_e_fen: int
    juedui_cha_fen: int
    youli_fen: int
    buli_fen: int
    fangxiang: str
    yujing_shu: int
    zhenggai_shu: int
    wancheng_shu: int
    wancheng_bps: int


def _fangxiang(youli_fen: int, buli_fen: int) -> str:
    """部门方向：混合科目无法用单模块规则判定，改比有利与不利偏差的量。"""
    if youli_fen == buli_fen:
        return '持平'
    return '有利' if youli_fen > buli_fen else '不利'


def _juhe_yuan(shuru: BumenShuru) -> BumenYuan:
    """把一个输入单元算成部门行：差额求和、绝对偏差不抵消、有利不利分解。"""
    cha_e = sum(cha for cha, _ in shuru.xiang)
    juedui = sum(abs(cha) for cha, _ in shuru.xiang)
    youli = sum(abs(cha) for cha, fa in shuru.xiang if fa == 'F')
    buli = sum(abs(cha) for cha, fa in shuru.xiang if fa == 'A')
    jigou, bumen = shibie_zuzhi(shuru.zhuti_mingcheng)
    return BumenYuan(
        bumen=bumen, jigou=jigou,
        jizhun_fen=shuru.jizhun_fen, shiji_fen=shuru.shiji_fen,
        cha_e_fen=cha_e, juedui_cha_fen=juedui, youli_fen=youli, buli_fen=buli,
        fangxiang=_fangxiang(youli, buli),
        yujing_shu=shuru.yujing_shu, zhenggai_shu=shuru.zhenggai_shu, wancheng_shu=shuru.wancheng_shu,
        wancheng_bps=_bps(shuru.wancheng_shu, shuru.zhenggai_shu),
    )


def juhe_bumen(shuru_lie: tuple[BumenShuru, ...] | list[BumenShuru]) -> BumenHuizong:
    """汇总一批组织单元：部门行、机构小计、偏差排行与合计。

    合计恒等于各部门相加（整数分相加，不做任何平摊或四舍五入），
    因此下游可以用"部门合计 = 科目合计"对账；排行占比以全批绝对偏差为分母。
    """
    if not shuru_lie:
        raise ValueError('组织单元批次不能为空')
    bumen_lie = tuple(_juhe_yuan(x) for x in shuru_lie)
    # 机构小计：按机构名分组相加；不同机构不强行合并，机构名回落到统一称呼。
    jigou_ming = []
    for yuan in bumen_lie:
        if yuan.jigou not in jigou_ming:
            jigou_ming.append(yuan.jigou)
    jigou_lie = tuple(
        JigouYuan(jigou=ming,
                  bumen_shu=sum(1 for x in bumen_lie if x.jigou == ming),
                  jizhun_fen=sum(x.jizhun_fen for x in bumen_lie if x.jigou == ming),
                  shiji_fen=sum(x.shiji_fen for x in bumen_lie if x.jigou == ming),
                  cha_e_fen=sum(x.cha_e_fen for x in bumen_lie if x.jigou == ming),
                  juedui_cha_fen=sum(x.juedui_cha_fen for x in bumen_lie if x.jigou == ming),
                  yujing_shu=sum(x.yujing_shu for x in bumen_lie if x.jigou == ming))
        for ming in jigou_ming)
    # 排行：绝对偏差降序，同额按部门名升序，保证结果可复现。
    juedui_heji = sum(x.juedui_cha_fen for x in bumen_lie)
    paixu = sorted(bumen_lie, key=lambda x: (-x.juedui_cha_fen, x.bumen))
    paihang = tuple((x.bumen, x.juedui_cha_fen, _bps(x.juedui_cha_fen, juedui_heji)) for x in paixu)
    youli = sum(x.youli_fen for x in bumen_lie)
    buli = sum(x.buli_fen for x in bumen_lie)
    zhenggai = sum(x.zhenggai_shu for x in bumen_lie)
    wancheng = sum(x.wancheng_shu for x in bumen_lie)
    return BumenHuizong(
        jigou=jigou_lie[0].jigou if len(jigou_lie) == 1 else QUANBU_JIGOU,
        bumen_lie=bumen_lie, jigou_lie=jigou_lie, paihang=paihang,
        jizhun_fen=sum(x.jizhun_fen for x in bumen_lie),
        shiji_fen=sum(x.shiji_fen for x in bumen_lie),
        cha_e_fen=sum(x.cha_e_fen for x in bumen_lie),
        juedui_cha_fen=juedui_heji, youli_fen=youli, buli_fen=buli,
        fangxiang=_fangxiang(youli, buli),
        yujing_shu=sum(x.yujing_shu for x in bumen_lie),
        zhenggai_shu=zhenggai, wancheng_shu=wancheng, wancheng_bps=_bps(wancheng, zhenggai),
    )
