# -*- coding: utf-8 -*-
"""zhenggai（整改数据底座）单元测试 —— 期望值全部手工验算写死。

设计原则：
    1. 规则回归：判定指令项（双环/双轨→预算修订案、单环→行为整改、
       复核提示→人工复核）+ 预警项（红=强制/黄=关注）逐条锁定；
    2. 责任模块 = 科目→模块映射（复用 building_blocks 默认映射）+ 积木高亮；
    3. 排序：高 → 中 → 低（稳定排序）；进度初始全"待整改"。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块与上游构造：discover -t . 运行时 algo 根目录在 sys.path 上
from building_blocks import JimuHang, chai_jimu  # noqa: E402
from loop_decision import PanDuanShuru, panduan_huanlu  # noqa: E402
from variance import ChayiShuru, YujingDang, jisuan_chayi  # noqa: E402
from zhenggai import ZhenggaiShuru, shengcheng_zhenggai  # noqa: E402


def hong_chayi() -> object:
    """红预警差异：材料价格 100,000 → 110,000 元（差异率 10% = 1000 基点）。"""
    # 自定义档位 红≥1000（默认已改 15%/30%，此处显式传旧线以覆盖下游规则）
    return jisuan_chayi([
        ChayiShuru('2026-Q1', '材料价格差异', '成本类',
                   10_000_000, 10_000_000, 11_000_000),
    ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))


def huang_chayi() -> object:
    """黄预警差异：办公费 100,000 → 105,000 元（差异率 5% = 500 基点）。"""
    # 自定义档位 红 10%/黄 5%：500 ∈ [500, 1000) → 黄 → 关注整改（中）
    return jisuan_chayi([
        ChayiShuru('2026-Q1', '办公费', '成本类',
                   10_000_000, 10_000_000, 10_500_000),
    ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))


def jimu_caigou() -> object:
    """积木结果：材料价格差异 → 采购模块（高亮 = 采购模块）。"""
    # 高亮规则（积木 D3）：不利模块中 |差额| 最大者 = 采购模块
    # 材料价格差异按默认映射归采购模块（材料价格关键词先于材料）
    return chai_jimu([JimuHang('2026-Q1', '材料价格差异', 1_000_000, 'A', '红', 1000)])


def panduan_shuanghuan() -> object:
    """双环判定：结构变更登记 + 规划差异显著（情形 3）。"""
    # 判定表五情形详见 loop_decision 模块头（定稿 §4.4）
    # 规划差异 900,000/10,000,000 = 9% 显著（≥100 基点）且已登记 → 双环
    return panduan_huanlu(PanDuanShuru(
        chalv_bps=1000, guihua_zong_fen=900_000, zhixing_zong_fen=100_000,
        yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True, bianma='供应商涨价'),
        menjian_bps=100, xianzhu_bps=100)  # 演示锚点保持在原定稿 1% 门限口径下复现（可会计复核）


class TestLiti(unittest.TestCase):
    """例题回归：双环 + 红预警 + 积木高亮 → 两条高优先级整改项。"""

    def test_shuanghuan_hong(self) -> None:
        """清单 = [预算修订案(高,采购), 强制整改(高,采购)]；计数 2/2。"""
        # 责任模块来源：判定项取积木高亮、预警项取科目映射——两路一致
        jg = shengcheng_zhenggai(ZhenggaiShuru(
            chayi=hong_chayi(), jimu=jimu_caigou(), panduan=panduan_shuanghuan()))
        # 高亮=采购模块且强制整改责任模块同为采购 → 不重复追加高亮提示项
        self.assertListEqual(
            [(x.leixing, x.youxianji, x.zeren_mokuai) for x in jg.qingdan],
            [('预算修订案', '高', '采购模块'), ('强制整改', '高', '采购模块')],
        )
        self.assertEqual((jg.gao_shu, jg.zhong_shu, jg.di_shu), (2, 0, 0))
        # 进度三态：初始全"待整改"（计算层只生成底座，进度流转属后续）
        self.assertEqual((jg.daizhenggai_shu, jg.jinxingzhong_shu,
                          jg.wancheng_shu), (2, 0, 0))
        # 预算修订案必人工审批（定稿 §9 步骤 8 审批闭环）；强制整改不用
        self.assertTrue(jg.qingdan[0].shenpi)
        self.assertFalse(jg.qingdan[1].shenpi)


class TestPandingZhiling(unittest.TestCase):
    """判定指令项：双轨/单环/复核提示三条规则逐一锁定。"""

    def test_shuanggui_yusuan_xiuding(self) -> None:
        """双轨 → 预算修订案（高、必审批）。"""
        # 双轨与双环同出口：预算修订案 + 人工审批（定稿 §4.2 职责拆分）
        # 规划+执行双显著且已登记 → 双轨（判定表情形 4）
        pd = panduan_huanlu(PanDuanShuru(
            chalv_bps=1500, guihua_zong_fen=1_000_000, zhixing_zong_fen=500_000,
            yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True, bianma='原材料替换'),
            menjian_bps=100, xianzhu_bps=100)  # 示例差异率低于 25% 新默认门限，传 100 沿用原口径
        jg = shengcheng_zhenggai(ZhenggaiShuru(panduan=pd))
        self.assertEqual(jg.qingdan[0].leixing, '预算修订案')
        self.assertTrue(jg.qingdan[0].shenpi)

    def test_danhuan_xingwei_zhiling(self) -> None:
        """单环 → 行为整改指令（中、不审批、不改预算基准）。"""
        # 单环语义：纠正当下执行动作，年度预算基准方案不动
        # 执行差异显著 + 无登记 → 单环（情形 2）
        pd = panduan_huanlu(PanDuanShuru(
            chalv_bps=800, guihua_zong_fen=None, zhixing_zong_fen=800_000,
            yuandan_cbf_fen=10_000_000, jie_gou_biangeng=False, bianma=''),
            menjian_bps=100, xianzhu_bps=100)  # 800 基点同样低于 25% 新默认，统一走原口径注入
        jg = shengcheng_zhenggai(ZhenggaiShuru(panduan=pd))
        self.assertEqual(jg.qingdan[0].leixing, '行为整改指令')
        self.assertEqual(jg.qingdan[0].youxianji, '中')
        self.assertFalse(jg.qingdan[0].shenpi)

    def test_fuhe_tishi(self) -> None:
        """复核提示 → 人工复核项（中）；LLM 只能提示不能直接双环。"""
        # 复核提示是 LLM 语义归类的唯一出口（升级提示，绝不直接触发双环）
        # 与 loop_decision 知识点 6 同款构造：注入假 LLM 归类"结构变动"
        # + 有变更文本但无登记 → 升级为复核提示（护栏 FR-8）
        pd = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, zhixing_zong_fen=2_300_000,
            yuandan_cbf_fen=39_200_000, jie_gou_biangeng=False,
            bianma='永久更换核心供应商', yuyi_guilei=lambda wenben: '结构变动'),
            menjian_bps=100, xianzhu_bps=100)  # Holmes 数字锚点不动，门限走原定稿口径
        jg = shengcheng_zhenggai(ZhenggaiShuru(panduan=pd))
        self.assertEqual(jg.qingdan[0].leixing, '人工复核')
        self.assertEqual(jg.qingdan[0].youxianji, '中')


class TestYujingXiang(unittest.TestCase):
    """预警项：红=强制（高）、黄=关注（中）；责任模块按科目映射。"""

    def test_huang_guanzhu(self) -> None:
        """只有黄预警 → 关注整改（中），责任模块 = 费用模块（办公费）。"""
        # 办公费 ∈ 费用模块关键词（映射增强后锁定，防回归）
        # 办公费 ∈ 费用模块关键词（2026-08-23 映射增强，与积木模块同表）
        jg = shengcheng_zhenggai(ZhenggaiShuru(chayi=huang_chayi()))
        self.assertListEqual(
            [(x.leixing, x.youxianji, x.zeren_mokuai) for x in jg.qingdan],
            [('关注整改', '中', '费用模块')],
        )

    def test_weiguishu_kemu(self) -> None:
        """科目映射不中 → 责任模块 = 未归属（不静默丢弃）。"""
        # 宁可交人工补映射，也不猜测归属——与积木模块 D1 兜底同纪律
        # 神秘科目不含任何关键词 → 未归属（与积木模块 D1 兜底同纪律）
        chayi = jisuan_chayi([
            ChayiShuru('2026-Q1', '神秘科目', '成本类',
                       10_000_000, 10_000_000, 11_000_000),
        ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
        jg = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi))
        self.assertEqual(jg.qingdan[0].zeren_mokuai, '未归属')

    def test_gaoliang_tishi_xuanji(self) -> None:
        """积木高亮 ≠ 预警行责任模块 → 追加关注整改提示项。"""
        # 高亮提示优先级取中——红/黄预警行才是强制入口
        # 预警行是"办公费"（费用模块），积木高亮是"采购模块"——两者不同
        jimu = chai_jimu([JimuHang('2026-Q1', '材料价格差异', 1_000_000, 'A', '红', 1000)])
        jg = shengcheng_zhenggai(ZhenggaiShuru(chayi=huang_chayi(), jimu=jimu))
        # 两条关注整改：一条来自黄预警、一条来自高亮提示（责任模块采购）
        self.assertEqual([x.leixing for x in jg.qingdan], ['关注整改', '关注整改'])
        self.assertEqual(jg.qingdan[1].zeren_mokuai, '采购模块')

    def test_gaoliang_chongfu_bu_xuanji(self) -> None:
        """积木高亮已存在于强制整改项 → 不重复追加提示项。"""
        # 去重规则：高亮与预警行责任模块一致时不重复列示（清单干净）
        # 红预警责任模块=采购模块 与高亮一致 → 只有 1 条强制整改
        jg = shengcheng_zhenggai(ZhenggaiShuru(chayi=hong_chayi(), jimu=jimu_caigou()))
        self.assertEqual(len(jg.qingdan), 1)


class TestPaixuJishu(unittest.TestCase):
    """排序与计数：高 → 中 → 低（稳定）；空输入 → 全零。"""

    def test_paixu(self) -> None:
        """红(高) + 单环(中) + 黄(中) → 顺序 [强制整改, 行为整改指令, 关注整改]。"""
        # 高在前、中在后；同级按生成顺序（判定项先于预警项）
        pd = panduan_huanlu(PanDuanShuru(
            chalv_bps=800, guihua_zong_fen=None, zhixing_zong_fen=800_000,
            yuandan_cbf_fen=10_000_000, jie_gou_biangeng=False, bianma=''),
            menjian_bps=100, xianzhu_bps=100)  # 800 基点同样低于 25% 新默认，统一走原口径注入
        chayi = jisuan_chayi([
            ChayiShuru('2026-Q1', '材料价格差异', '成本类',
                       10_000_000, 10_000_000, 11_000_000),
            ChayiShuru('2026-Q1', '办公费', '成本类',
                       10_000_000, 10_000_000, 10_500_000),
        ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
        jg = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi, panduan=pd))
        # 排序稳定性：两条"中"保持生成顺序（行为整改指令在前）
        self.assertListEqual([x.leixing for x in jg.qingdan],
                             ['强制整改', '行为整改指令', '关注整改'])
        self.assertEqual((jg.gao_shu, jg.zhong_shu, jg.di_shu, jg.zong_shu),
                         (1, 2, 0, 3))

    def test_kong_shuru(self) -> None:
        """全部上游缺省 → 空清单、全零计数（聚合层容错）。"""
        # 聚合层职责：只组装不重算——上游缺失就空着，由看板层显示「无」
        # 端到端脚本某阶段缺失时不允许崩——空清单即合法输出
        jg = shengcheng_zhenggai(ZhenggaiShuru())
        self.assertEqual(jg.qingdan, [])
        self.assertEqual((jg.gao_shu, jg.zhong_shu, jg.di_shu, jg.zong_shu),
                         (0, 0, 0, 0))

    def test_quedingxing(self) -> None:
        """确定性：同输入两次调用结果完全一致（dataclass 等值）。"""
        # 清单顺序与计数均须稳定——AI 层文案起草依赖顺序稳定
        # 纯函数要求：无 I/O、无全局状态 → 同输入必同输出
        shuru = ZhenggaiShuru(chayi=hong_chayi(), jimu=jimu_caigou(),
                              panduan=panduan_shuanghuan())
        self.assertEqual(shengcheng_zhenggai(shuru), shengcheng_zhenggai(shuru))


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_zhenggai.py
    unittest.main()
