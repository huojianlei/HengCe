# -*- coding: utf-8 -*-
"""数据录入模块 —— 方案B 八步流程【步骤 1：基础数据录入】的确定性核心。

命名规范（2026-08-23 用户指令）：本模块所有标识符（变量/函数/类/常量/
字典键）一律用【无声调拼音】，数据值用中文；文件名保持英文（Windows 规范）。

职责边界（本模块只做三件事，多一件都不做）：
    1. 解析：把 CSV 文本拆成一行行原始数据（表头必须符合统一 8 列规范）；
    2. 清洗：逐行校验 + 数值换算（去重 / 纠错 / 缺失标记；有问题的行
       【不静默丢弃】，而是进入"拒绝清单"交人工复核——对应方案B 4.3
       第二步"标记异常待人工复核"）；
    3. 归类：把合法行按【数据类别】归入四大档案（对应 4.3 第三步）。

数据四大类（方案B 4.1，中文常量）：
    预算基础（年初一次性）、实时经营（按月/季）、行业对标（外部）、
    经营变更（事件式随时）。

统一 8 列表头（方案B 4.2 的 7 个基础字段 + 1 个类别列）：
    数据类别, 统计周期, 数据科目, 数值, 单位, 数据来源, 更新时间, 备注
    （类别列是我们对方案的增强：显式声明比自动猜测可靠；
      让 LLM 智能归类属于 M5 智能体层，不在本确定性模块。）

数值纪律（与全项目一致，杜绝浮点误差）：
    - 金额「元」→ 整数「分」（字符串直接解析，全程不经浮点）；
    - 百分比「%」→ 整数「基点」（1% = 100 基点）；
    - 计数（个/次/天…）→ 整数（本身必须就是整数）。
    【口径分歧·待会计复核】方案B 4.2 写"空值统一填充 0"——我们认为
    缺失 ≠ 0（3 月没录数 ≠ 3 月花销为 0），故空值一律进拒绝清单。

本模块【不含数据库】：输出的是内存中的标准记录，入库（fin-store /
SQLite，见 docs\\10 §四 与 ADR-04）属后续单独模块，届时按 TODO 立项。

使用示例（知识点速览，v0.3 2026-08-23 拼音化；doctest 格式——可直接复制
    到交互环境运行，也可用 `python -m doctest data_ingest.py` 自动验证，
    并由 tests\\test_demos.py 纳入常规测试守护，示例过时测试即红）：

    知识点 1 · 一行搞定导入（daoru_csv：解析+清洗+归类）
    >>> from data_ingest import daoru_csv
    >>> wenben = (
    ...     '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注\\n'
    ...     '预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,年初定稿\\n'
    ...     '实时经营,2026-Q1,营收,210000.50,元,ERP导出,2026-04-02,Q1实际\\n'
    ... )
    >>> jieguo = daoru_csv(wenben)
    >>> jieguo.ruku_shu                         # 合法入库行数
    2

    知识点 2 · 看归档（四类清单；金额已换算为"分"）
    >>> (jieguo.yusuan[0].kemu, jieguo.yusuan[0].shuzhi)   # 22 万元 → 22000000 分
    ('营收', 22000000)
    >>> jieguo.shishi[0].shuzhi                           # 210000.50 元 → 21000050 分
    21000050

    知识点 3 · 看拒绝清单（坏行带行号与中文原因，交人工复核）
    >>> huaiwen = (
    ...     '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注\\n'
    ...     '实时经营,2026-13,营收,100,元,ERP,2026-02-01,月份不存在\\n'
    ...     '实时经营,2026-01,营收,abc,元,ERP,2026-02-01,数值是字母\\n'
    ... )
    >>> jg2 = daoru_csv(huaiwen)
    >>> jg2.ruku_shu
    0
    >>> [(x.hanghao, x.yuanyin.split('：')[0]) for x in jg2.jujue]
    [(2, '期间格式非法'), (3, '数值不是合法数字')]

    知识点 4 · 重复数据（同"类别+期间+科目"只留先到者）
    >>> chongfu = (
    ...     '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注\\n'
    ...     '预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,先到\\n'
    ...     '预算基础,2026-Q1,营收,225000.00,元,预算表V4,2026-02-20,后到\\n'
    ... )
    >>> jg3 = daoru_csv(chongfu)
    >>> (jg3.ruku_shu, len(jg3.jujue))
    (1, 1)

    知识点 5 · 表头错误 = 整个文件的问题（抛 JiexiCuowu）
    >>> from data_ingest import JiexiCuowu
    >>> try:
    ...     daoru_csv('随便什么表头\\n')
    ... except JiexiCuowu:
    ...     print('整文件拒绝，一行都不入库')
    整文件拒绝，一行都不入库

命名对照表（拼音标识符 → 中文含义）：
    daoru_csv / jiexi_csv / qingxi_bing_guilei   导入CSV / 解析CSV / 清洗并归类
    JiexiCuowu            解析错误（表头不符等整文件问题）
    BiaozhunJilu          标准记录（一条清洗后的数据）
    JuJueHang             拒绝行（被拒原始行 + 原因）
    DaoruJieguo           导入结果（四类归档 + 拒绝清单）
    LEIBIE_YUSUAN 等      四个类别常量（预算基础/实时经营/行业对标/经营变更）
    BIXU_LIE              必需的 8 列表头
    hanghao / leibie / qijian / kemu    行号 / 类别 / 期间 / 科目
    shuzhi / danwei / laiyuan / beizhu  数值 / 单位 / 来源 / 备注
    ruku_shu              入库数（合法行合计）

口径依据：docs\\textbook\\finagent-算法核对文档-定稿.md v2.1 §9 步骤 1；
         docs\\proposal-full-extract.txt 行 147~186（完整版第四章投喂体系）。
建立：2026-08-22 23:56；2026-08-23 v0.3 拼音化 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

# ======================================================================
# 常量区（全部中文取值，数据里直接写中文类别与单位）
# ======================================================================

#: 类别一：预算基础（年初定稿的年度预算表等，一次性录入）
LEIBIE_YUSUAN = '预算基础'
#: 类别二：实时经营（月度/季度的实际发生额，周期性录入）
LEIBIE_SHISHI = '实时经营'
#: 类别三：行业对标（外部行业参考值，队友正在找的数据走这类）
LEIBIE_HANGYE = '行业对标'
#: 类别四：经营变更（供应商更换等结构性事件，随时触发录入）
LEIBIE_BIANGENG = '经营变更'

#: 四类的合法取值集合（录入行的「数据类别」列必须是其中之一）
HEFA_LEIBIE = (LEIBIE_YUSUAN, LEIBIE_SHISHI, LEIBIE_HANGYE, LEIBIE_BIANGENG)

#: 统一表头：8 列、顺序固定（第一行必须与此完全一致）
BIXU_LIE = ('数据类别', '统计周期', '数据科目', '数值', '单位', '数据来源', '更新时间', '备注')

#: 金额单位：元（录入两位小数 → 存为整数分）
DANWEI_YUAN = '元'
#: 百分比单位：%（录入两位小数 → 存为整数基点）
DANWEI_BAIFENBI = '%'
#: 计数单位：这些单位下数值必须是纯整数（不允许小数）
JISHU_DANWEI = ('个', '次', '天', '单', '人')

#: 月度期间格式：2026-01 ~ 2026-12（四位年 + 两位月）
_YUEDU_QIJIAN_GESHI = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
#: 季度期间格式：2026-Q1 ~ 2026-Q4（四位年 + Q + 一位季）
_JIDU_QIJIAN_GESHI = re.compile(r'^\d{4}-Q[1-4]$')


class JiexiCuowu(ValueError):
    """解析级错误：表头不符、文件为空等"整个文件的问题"。

    与逐行拒绝（JuJueHang）的区别：
    解析级错误意味着文件本身不合格，一行都处理不了，必须整文件重做；
    逐行拒绝只是个别行有问题，其余行照常入库。
    """

    pass  # 无附加行为，仅作类型标识（继承 ValueError 方便统一捕获）


# ======================================================================
# 数据结构区（frozen = 不可变，纯函数纪律）
# ======================================================================


@dataclass(frozen=True)
class BiaozhunJilu:
    """一条清洗后的标准数据记录（后续入库的基本单位）。

    字段与 8 列一一对应（外加行号）；shuzhi 已换算为整数
    （元→分 / %→基点 / 计数→个），全链路不再出现小数。
    """

    hanghao: int          # 原始行号（数据行从 2 起；台账追溯与复核定位用）
    leibie: str           # 数据类别（四类之一）
    qijian: str           # 统计期间（2026-01 / 2026-Q1）
    kemu: str             # 数据科目（营收、材料成本、毛利率……）
    shuzhi: int           # 数值（整数：分 / 基点 / 个）
    danwei: str           # 单位（元 / % / 计数单位）
    laiyuan: str          # 数据来源（哪个系统/哪份表——答辩可溯源）
    gengxin_shijian: str  # 更新时间（台账追溯）
    beizhu: str           # 备注（唯一允许为空的字段）


@dataclass(frozen=True)
class JuJueHang:
    """一条被拒绝的行：原始内容 + 拒绝原因（人工复核清单的条目）。"""

    hanghao: int            # 行号（定位到具体行）
    yuanyin: str            # 拒绝原因（中文，可能含多项，分号分隔）
    yuanwen: tuple[str, ...]  # 原始行内容（8 列原文，供复核时对照）


@dataclass(frozen=True)
class DaoruJieguo:
    """导入结果：四大类归档清单 + 拒绝清单。

    用法约定：调用方先看 jujue（有则提示人工处理），
    再取四个类别清单做后续运算（滚动预算取"预算基础+实时经营"等）。
    """

    yusuan: list[BiaozhunJilu]     # 预算基础类归档
    shishi: list[BiaozhunJilu]     # 实时经营类归档
    hangye: list[BiaozhunJilu]     # 行业对标类归档
    biangeng: list[BiaozhunJilu]   # 经营变更类归档
    jujue: list[JuJueHang]         # 拒绝清单（交人工复核）

    @property
    def ruku_shu(self) -> int:
        """合法入库总行数（四类之和）——导入摘要与对账用。"""
        return len(self.yusuan) + len(self.shishi) + len(self.hangye) + len(self.biangeng)


# ======================================================================
# 内部工具函数区
# ======================================================================


def _jiexi_fangda_zhengshu(wenben: str, fangda_wei: int) -> int:
    """把十进制数字符串解析为"放大整数"，全程字符串操作、不经浮点。

    规则（以 fangda_wei=2 为例，即元→分、%→基点）：
        '123.45' → 12345   （两位小数，直接拼接）
        '123.4'  → 12340   （一位小数，补零到两位）
        '123'    → 12300   （无小数，补两个零）
    拒绝情形（抛 JiexiCuowu）：
        空值（缺失不填 0，见模块头"口径分歧"）、负数、含字母、
        小数位超过 fangda_wei 位。
    """
    s = wenben.strip()  # 容忍首尾空白（Excel 导出常见）
    if not s:
        raise JiexiCuowu('数值缺失（空值不填 0，标记待人工复核）')
    if s.startswith('-'):
        raise JiexiCuowu('负数不允许（正负方向由指标性质表达，不由录入符号表达）')
    # 按小数点切分（partition 只切第一个点，'1.2.3' 会因后半段非数字被拒）
    zhengshu_bu, _, xiaoshu_bu = s.partition('.')
    if not zhengshu_bu.isdigit() or (xiaoshu_bu and not xiaoshu_bu.isdigit()):
        raise JiexiCuowu(f'数值不是合法数字：{wenben!r}')
    if len(xiaoshu_bu) > fangda_wei:
        raise JiexiCuowu(f'小数位超过 {fangda_wei} 位：{wenben!r}')
    bu_ling = xiaoshu_bu.ljust(fangda_wei, '0')  # 不足位补零
    return int(zhengshu_bu + bu_ling)  # 拼接后必为纯数字串


# ======================================================================
# 对外接口区（三个函数，自上而下组合）
# ======================================================================


def jiexi_csv(wenben: str) -> list[dict]:
    """第一步：解析 CSV 文本 → 原始行字典列表。

    - 自动剥掉 Windows 记事本/Excel 常见的 UTF-8 BOM 头（\\ufeff）；
    - 跳过整行全空的行（表格里常见的装饰性空行）；
    - 第一行必须与 BIXU_LIE 完全一致（8 列、同顺序），
      否则抛 JiexiCuowu（整文件问题，见该异常的说明）；
    - 列数不齐的行【不在此报错】——打上 '__huaihang__' 标记交给清洗阶段
      进拒绝清单（与"逐行标记"的口径一致）；
    - 每行字典附带 '__hanghao__' 行号（数据行从 2 起）。
    """
    ganjing = wenben.lstrip('\ufeff')  # BOM 只可能出现在文件最开头
    duchuqi = csv.reader(io.StringIO(ganjing))
    # 过滤全空行（所有单元格都是空白的不算数据）
    hang_liebiao = [hang for hang in duchuqi if any(dange.strip() for dange in hang)]
    if not hang_liebiao:
        raise JiexiCuowu('CSV 为空（连表头都没有）')

    biaotou = [dange.strip() for dange in hang_liebiao[0]]
    if tuple(biaotou) != BIXU_LIE:
        raise JiexiCuowu(f'表头不符：{biaotou}（应为 {list(BIXU_LIE)}）')

    jiexi_hao: list[dict] = []
    for hanghao, hang in enumerate(hang_liebiao[1:], start=2):  # 行号从 2 起（1 是表头）
        if len(hang) != len(BIXU_LIE):
            # 列数不齐：打标移交清洗阶段（保证解析阶段不因单行失败而中断）
            jiexi_hao.append({'__hanghao__': hanghao, '__huaihang__': tuple(hang)})
            continue
        # 列名 → 去空白后的单元格值
        jilu = dict(zip(BIXU_LIE, (dange.strip() for dange in hang)))
        jilu['__hanghao__'] = hanghao
        jiexi_hao.append(jilu)
    return jiexi_hao


def qingxi_bing_guilei(yuanshi_hang: list[dict]) -> DaoruJieguo:
    """第二步：清洗 + 归类（逐行校验，合法进四档，非法进拒绝清单）。

    校验顺序（先廉价后昂贵，问题全部收集后再决定去留）：
        列数 → 类别 → 期间格式 → 科目非空 → 单位合法 →
        来源/时间非空 → 数值换算 → 跨行去重。
    去重键 =（数据类别, 统计周期, 数据科目）——同一类别同一期间同一科目
    只允许一条，后到的重复行被拒（保留先到者，台账可追溯）。
    """
    yusuan: list[BiaozhunJilu] = []
    shishi: list[BiaozhunJilu] = []
    hangye: list[BiaozhunJilu] = []
    biangeng: list[BiaozhunJilu] = []
    jujue: list[JuJueHang] = []
    chongfu_jian: set[tuple[str, str, str]] = set()  # 去重键集合

    for yuanshi in yuanshi_hang:
        hanghao = yuanshi.get('__hanghao__', 0)
        # —— 列数不齐（解析阶段打的标）——
        if '__huaihang__' in yuanshi:
            jujue.append(JuJueHang(hanghao, f'列数不符（应为 {len(BIXU_LIE)} 列）', yuanshi['__huaihang__']))
            continue

        # —— 逐项校验，问题累积（一行可能有多处问题，一次报全）——
        wenti: list[str] = []
        leibie = yuanshi['数据类别']
        if leibie not in HEFA_LEIBIE:
            wenti.append(f'未知类别：{leibie}')
        qijian = yuanshi['统计周期']
        if not (_YUEDU_QIJIAN_GESHI.match(qijian) or _JIDU_QIJIAN_GESHI.match(qijian)):
            wenti.append(f'期间格式非法：{qijian}（应为 2026-01 或 2026-Q1）')
        kemu = yuanshi['数据科目']
        if not kemu:
            wenti.append('科目为空')
        danwei = yuanshi['单位']
        if danwei != DANWEI_YUAN and danwei != DANWEI_BAIFENBI and danwei not in JISHU_DANWEI:
            wenti.append(f'未知单位：{danwei}')
        for ziduan in ('数据来源', '更新时间'):  # 台账追溯两字段必须非空
            if not yuanshi[ziduan]:
                wenti.append(f'{ziduan}为空')
        if wenti:
            jujue.append(JuJueHang(hanghao, '；'.join(wenti), tuple(yuanshi[c] for c in BIXU_LIE)))
            continue

        # —— 数值换算（格式全对才值得换算；单位决定放大位数）——
        try:
            if danwei in (DANWEI_YUAN, DANWEI_BAIFENBI):
                shuzhi = _jiexi_fangda_zhengshu(yuanshi['数值'], 2)  # 元→分 / %→基点，都是放大 100
            else:
                shuzhi = _jiexi_fangda_zhengshu(yuanshi['数值'], 0)  # 计数：必须纯整数
        except JiexiCuowu as cuo:
            jujue.append(JuJueHang(hanghao, str(cuo), tuple(yuanshi[c] for c in BIXU_LIE)))
            continue

        # —— 跨行去重（同类别+同期间+同科目只留先到者）——
        jian = (leibie, qijian, kemu)
        if jian in chongfu_jian:
            jujue.append(JuJueHang(hanghao, f'重复数据（{leibie}/{qijian}/{kemu} 已存在，保留先到者）', tuple(yuanshi[c] for c in BIXU_LIE)))
            continue
        chongfu_jian.add(jian)

        # —— 构造标准记录并归档到对应类别 ——
        jilu = BiaozhunJilu(
            hanghao=hanghao, leibie=leibie, qijian=qijian, kemu=kemu,
            shuzhi=shuzhi, danwei=danwei, laiyuan=yuanshi['数据来源'],
            gengxin_shijian=yuanshi['更新时间'], beizhu=yuanshi['备注'],
        )
        if leibie == LEIBIE_YUSUAN:
            yusuan.append(jilu)
        elif leibie == LEIBIE_SHISHI:
            shishi.append(jilu)
        elif leibie == LEIBIE_HANGYE:
            hangye.append(jilu)
        else:
            biangeng.append(jilu)

    return DaoruJieguo(yusuan=yusuan, shishi=shishi, hangye=hangye, biangeng=biangeng, jujue=jujue)


def daoru_csv(wenben: str) -> DaoruJieguo:
    """组合便捷入口：解析 + 清洗归类一步到位（大多数调用方只用这个）。"""
    return qingxi_bing_guilei(jiexi_csv(wenben))
