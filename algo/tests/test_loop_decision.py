# -*- coding: utf-8 -*-
"""单双环判定模块的测试（方案B 步骤 4，定稿 v2.1 §4 判定表五情形回归）。

用例设计（期望值全部手工推导写死——纯函数纪律，禁止自证循环）：
    1. 五情形各一路（情形 1/2/3/4/5 与定稿 §4.4 表逐行对应）；
    2. 显著性阈值边界（恰好 100 基点算显著、99 基点不显著——整数比较）；
    3. LLM 语义归类三路（升级复核提示 / 执行偏差无影响 / 异常降级）；
    4. 留白边界三条（差异率 None / 拆分缺失退化 / 规划显著无登记）；
    5. 校验组（负差异率、负成本额抛 PanDuanCuowu）+ 确定性（同输入同输出）。

数字例题沿用定稿 §3 Holmes Ltd（原标准成本 $39,200 = 3,920,000 分，
规划总 +$3,360、执行总 −$1,060、整体差异率 587 基点），与模块头
知识点示例同源但独立推导，交叉印证。
"""

from __future__ import annotations

import unittest

# 门限口径注记（2026-09-04 拍板）：MENJIAN_BPS 默认 = 2500 基点（25%）。
# 下方沿用 Holmes 定稿例题（差异率 587 基点 = 5.87%）的用例一律传
# menjian_bps=100, xianzhu_bps=100（原定稿 1% 口径）——数字锚点不动，顺带覆盖自定义注入口。
from loop_decision import (GUILEI_HEFA, MENJIAN_BPS, PanDuanCuowu, XIANZHU_BPS,
                           PanDuanShuru, panduan_huanlu)


class WuQingxingTest(unittest.TestCase):
    """定稿 §4.4 判定表五行逐一回归（编号、判定值、审批标志）。"""

    def test_qingxing_1_zaosheng_buchufa(self) -> None:
        """情形 1：差异率 50 基点（低于默认门限 25%）且无登记 → 不触发。"""
        # 50 基点 < 2500 默认门限 → 噪声；无登记 → 情形 1
        jg = panduan_huanlu(PanDuanShuru(chalv_bps=50))
        self.assertEqual((jg.qingxing, jg.panduan, jg.shenpi), (1, '不触发', False))

    def test_qingxing_2_danhuan(self) -> None:
        """情形 2：过门 + 执行差异显著（2,300,000 分 = 587 基点）+ 无登记 → 单环。"""
        # 执行 2,300,000/3,920,000 = 587 基点 ≥ 100 显著；规划 0 不显著
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=0, zhixing_zong_fen=2_300_000,
            yuandan_cbf_fen=3_920_000, jie_gou_biangeng=False), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual((jg.qingxing, jg.panduan, jg.shenpi), (2, '单环', False))
        # 单环纠错指令必须"不动预算方案"
        self.assertIn('预算方案不动', jg.jiuzheng)

    def test_qingxing_3_shuanghuan(self) -> None:
        """情形 3：规划显著（2,000,000 分）+ 执行不显著（100,000 分）+ 有登记 → 双环。"""
        # 规划显著性：2e6×1e4=2e10 ≥ 100×3.92e7=3.92e9 → 显著；
        # 执行显著性：1e5×1e4=1e9 < 3.92e9 → 不显著 → 情形 3（不是 4）
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=300, guihua_zong_fen=2_000_000, zhixing_zong_fen=100_000,
            yuandan_cbf_fen=39_200_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual((jg.qingxing, jg.panduan, jg.shenpi), (3, '双环', True))
        # 双环纠错指令必须含"人工审批"（护栏 FR-8）
        self.assertIn('人工审批', jg.jiuzheng)

    def test_qingxing_4_shuanggui_holmes(self) -> None:
        """情形 4：Holmes 拆分下规划/执行均显著 + 有登记 → 混合纠错模式（必审）。"""
        # Holmes：规划 3,360/39,200 = 857 基点显著；执行 1,060/39,200 = 270 基点显著
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=3_360_000, zhixing_zong_fen=-1_060_000,
            yuandan_cbf_fen=39_200_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual((jg.qingxing, jg.panduan, jg.shenpi), (4, '混合纠错模式', True))
        # 双轨 = 单环整改 + 双环审批同时输出
        self.assertIn('行为整改', jg.jiuzheng)
        self.assertIn('人工审批', jg.jiuzheng)

    def test_qingxing_5_fuhe_tishi(self) -> None:
        """情形 5：差异率 80 基点（低于默认门限）但有登记 → 复核提示（必审）。"""
        # 80 基点 < 2500 默认门限，但登记了结构变更 → 情形 5（建议口径）
        jg = panduan_huanlu(PanDuanShuru(chalv_bps=80, jie_gou_biangeng=True))
        self.assertEqual((jg.qingxing, jg.panduan, jg.shenpi), (5, '复核提示', True))
        # 情形 5 是建议口径，备注必须声明随 T-05 确认（诚实标注纪律）
        self.assertIn('T-05', jg.beizhu)


class XianzhuBianjieTest(unittest.TestCase):
    """显著性阈值边界（【建议默认值】口径：|分量|÷成本额 ≥ 100 基点）。"""

    def test_bianjie_100_jidian_suan(self) -> None:
        """恰好 100 基点（39,200 分 ÷ 3,920,000 分）→ 显著 → 落单环。"""
        # 39,200 分恰为 3,920,000 分的 1%：39,200×10,000 = 3.92e8 = 100×3,920,000 → 等号成立算显著
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=0, zhixing_zong_fen=39_200,
            yuandan_cbf_fen=3_920_000, jie_gou_biangeng=False), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '单环')
        self.assertIs(jg.yiju['执行差异显著'], True)

    def test_bianjie_99_jidian_bu_suan(self) -> None:
        """99 基点（39,199 分）→ 不显著；无任何显著分量 → 仍单环但走默认带。"""
        # 39,199×10,000 = 3.9199e8 < 3.92e8 → 差 1 分都不显著（整数比较无舍入）
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=0, zhixing_zong_fen=39_199,
            yuandan_cbf_fen=3_920_000, jie_gou_biangeng=False), menjian_bps=100, xianzhu_bps=100)
        self.assertIs(jg.yiju['执行差异显著'], False)
        # 两个分量都不显著（规划为 0 也不显著）→ 情形 2 兜底（无结构信号即单环带）
        self.assertEqual(jg.panduan, '单环')

    def test_fenmu_ling_tuihua_fei_ling_ji_xianzhu(self) -> None:
        """分母为 0 → 退化口径"非零即显著"：规划 1 分也显著 → 有登记则双环。"""
        # 分母 0 → 退化口径（非零即显著）：规划 1 分也算显著 + 有登记 → 双环
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=1, zhixing_zong_fen=0,
            yuandan_cbf_fen=0, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '双环')


class LlmGuileiTest(unittest.TestCase):
    """LLM 语义归类注入（M5 层接口；离线假函数，不联网）。

    三路覆盖：疑似结构变动（升级复核提示）/ 执行偏差（无影响）/
    故障与幻觉（降级无法判断）——LLM 永远没有直接触发双环的权力。
    """

    def test_llm_canyi_jiegou_shengji_fuhe(self) -> None:
        """LLM 读出结构变动且【无】登记 → 保守升级复核提示（不直接双环）。"""
        jiaren = lambda wenben: '结构变动'   # noqa: E731  测试用假 LLM
        # 无登记但 LLM 读出结构变动 → 只能升级复核提示（不能直接双环）
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, zhixing_zong_fen=2_300_000, yuandan_cbf_fen=39_200_000,
            jie_gou_biangeng=False, bianma='永久更换核心供应商',
            yuyi_guilei=jiaren), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '复核提示')
        self.assertTrue(jg.shenpi)          # 升级后必审（人工确认补录）
        self.assertIn('LLM 疑似结构变动', jg.jiuzheng)

    def test_llm_zhixing_piancha_wu_yingxiang(self) -> None:
        """LLM 归类执行偏差 → 不改变单环判定（语义只加分不减确定性）。"""
        jiaren = lambda wenben: '执行偏差'   # noqa: E731  测试用假 LLM
        # 执行偏差归类与确定性归因方向一致 → 维持单环，不额外动作
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, zhixing_zong_fen=2_300_000, yuandan_cbf_fen=39_200_000,
            jie_gou_biangeng=False, bianma='车间临时赶工超支', yuyi_guilei=jiaren),
            menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '单环')
        self.assertEqual(jg.yiju['语义归类'], '执行偏差')

    def test_llm_yichang_jiangji(self) -> None:
        """LLM 抛异常 / 返回幻觉值 → 降级'无法判断'，判定照常出（T-22⑨）。"""
        huai_1 = lambda wenben: (_ for _ in ()).throw(RuntimeError('网络断'))  # noqa: E731
        huai_2 = lambda wenben: '我觉得应该双环呀'    # noqa: E731  非法枚举值
        # 故障与幻觉都必须被吞掉（T-22⑨ 降级），判定照常出单环
        for jiaren in (huai_1, huai_2):
            jg = panduan_huanlu(PanDuanShuru(
                chalv_bps=587, zhixing_zong_fen=2_300_000,
                yuandan_cbf_fen=39_200_000, bianma='随便一段文本',
                yuyi_guilei=jiaren), menjian_bps=100, xianzhu_bps=100)
            self.assertEqual(jg.yiju['语义归类'], '无法判断')
            self.assertEqual(jg.panduan, '单环')     # 无结构信号 → 单环带


class LiubaiBianjieTest(unittest.TestCase):
    """定稿留白处的建议默认口径（备注必须诚实声明，答辩可溯源）。"""

    def test_chalv_none_buchufa_beizhu(self) -> None:
        """差异率 None（基准 0）→ 不触发 + 备注声明交人工（口径 c）。"""
        # 上游基准为 0 时差异率是 None——本模块不臆造，交人工（口径 c）
        jg = panduan_huanlu(PanDuanShuru(chalv_bps=None))
        self.assertEqual(jg.panduan, '不触发')
        # 备注必须诚实声明"交人工"（与 variance 除零口径一致的口径 c）
        self.assertIn('交人工', jg.beizhu)

    def test_chaifen_quehang_tuihua_danhuan(self) -> None:
        """拆分线索整体缺失（全 None）→ 执行偏差假设单环 + 备注声明（口径 d）。"""
        # 拆分全缺失 → 执行偏差假设（口径 d）：单环 + 备注声明
        jg = panduan_huanlu(PanDuanShuru(chalv_bps=587), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '单环')
        self.assertIn('拆分线索缺失', jg.beizhu)
        self.assertIsNone(jg.yiju['规划差异显著'])
        self.assertIsNone(jg.yiju['执行差异显著'])

    def test_guihua_xianzhu_wu_dengji_beizhu(self) -> None:
        """规划显著但无登记 → 仍单环 + 备注建议补录复判（口径 b）。"""
        # 规划 857 基点显著但没登记 → 单环兜底 + 建议补录（口径 b）
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=3_360_000, zhixing_zong_fen=0,
            yuandan_cbf_fen=3_920_000, jie_gou_biangeng=False), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '单环')
        self.assertIn('补录变更', jg.beizhu)


class JiaoyanTest(unittest.TestCase):
    """输入校验与确定性（纯函数纪律）。

    校验组防的是调用方绕过上游直接喂非法值；确定性是纯函数的
    底线保证——判定结果可复现，答辩演示才敢现场重跑。
    """

    def test_fuchalv_paocuo(self) -> None:
        """负差异率 → PanDuanCuowu（率不允许负）。"""
        # 差异率在 variance 一侧就保证非负——这里防的是调用方绕过上游直接喂负数
        with self.assertRaises(PanDuanCuowu):
            panduan_huanlu(PanDuanShuru(chalv_bps=-1))

    def test_fuchengbene_paocuo(self) -> None:
        """负原标准成本额 → PanDuanCuowu（0 合法，负数非法）。"""
        with self.assertRaises(PanDuanCuowu):
            panduan_huanlu(PanDuanShuru(chalv_bps=100, yuandan_cbf_fen=-1))

    def test_quedingxing(self) -> None:
        """同输入两次调用 → 结果完全一致（含依据字典）。"""
        # 纯函数复核：含 LLM 注入的完整输入也要确定性（注入函数本身也须纯）
        shuru = PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=3_360_000, zhixing_zong_fen=-1_060_000,
            yuandan_cbf_fen=39_200_000, jie_gou_biangeng=True, bianma='换供应商',
            yuyi_guilei=lambda w: '结构变动')
        self.assertEqual(panduan_huanlu(shuru, menjian_bps=100, xianzhu_bps=100),
                         panduan_huanlu(shuru, menjian_bps=100, xianzhu_bps=100))

    def test_changliang_koujing(self) -> None:
        """口径常量与定稿一致（改常量必须过这里——防口径漂移）。"""
        self.assertEqual(MENJIAN_BPS, 2500)         # 门限默认 25%（2026-09-04 拍板；原 #5=100 留痕）
        self.assertEqual(XIANZHU_BPS, 2500)         # 显著默认 25%（同次拍板；原建议 100 留痕）
        self.assertEqual(GUILEI_HEFA, ('结构变动', '执行偏差', '无法判断'))


class MenXianKouTest(unittest.TestCase):
    """默认门限 25%（2026-09-04 拍板）与自定义注入口（menjian_bps 参数）。

    两口并存的口径：默认值服务"开箱即判"，自定义口服务演示复核与后台
    微调——常量注释留痕原定稿 #5 = 100 基点，防止口径漂移无据可查。
    """

    def test_moren_menxian_guomen_danhuan(self) -> None:
        """默认门限下 3000 基点（30%）过门 → 单环；依据快照记默认 2500。"""
        # 默认路径：不传 menjian_bps 时走常量 MENJIAN_BPS——拍板改默认只动常量不改逻辑
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=3000, guihua_zong_fen=0, zhixing_zong_fen=2_300_000,
            yuandan_cbf_fen=39_200_000, jie_gou_biangeng=False))
        self.assertEqual(jg.panduan, '单环')
        self.assertEqual(jg.yiju['门检基点'], 2500)

    def test_moren_menxian_nei_dengji_fuhe(self) -> None:
        """默认门限内（2000 < 2500）+ 有登记 → 情形 5 复核提示。"""
        # 2000 基点：旧口径（100）下本应过门，新默认（2500）下落回情形 5——
        # 恰好验证门限默认值变更对分诊结果的真实影响
        jg = panduan_huanlu(PanDuanShuru(chalv_bps=2000, jie_gou_biangeng=True))
        self.assertEqual((jg.qingxing, jg.panduan), (5, '复核提示'))

    def test_zidingyi_menxian_zhushe_kou(self) -> None:
        """自定义门限=100（原定稿口径）：587 过门；依据快照记实际用值 100。"""
        # 自定义路径：门限随判定依据落报告——答辩被问"阈值哪来的"可当场溯源
        jg = panduan_huanlu(PanDuanShuru(
            chalv_bps=587, guihua_zong_fen=0, zhixing_zong_fen=2_300_000,
            yuandan_cbf_fen=3_920_000, jie_gou_biangeng=False), menjian_bps=100, xianzhu_bps=100)
        self.assertEqual(jg.panduan, '单环')
        self.assertEqual(jg.yiju['门检基点'], 100)

    def test_zidingyi_menxian_fushu_paocuo(self) -> None:
        """自定义门限为负 → PanDuanCuowu（门限是下限，不允许负）。"""
        with self.assertRaises(PanDuanCuowu):
            panduan_huanlu(PanDuanShuru(chalv_bps=587), menjian_bps=-5)

    def test_zidingyi_xianzhu_fushu_paocuo(self) -> None:
        """自定义显著阈值为负 → PanDuanCuowu（同门限一并校验）。"""
        with self.assertRaises(PanDuanCuowu):
            panduan_huanlu(PanDuanShuru(chalv_bps=587), xianzhu_bps=-5)


if __name__ == '__main__':
    unittest.main()
