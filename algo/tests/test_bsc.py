# -*- coding: utf-8 -*-
"""bsc（平衡计分卡四维评分）单元测试 —— 期望值全部手工验算写死。

设计原则：
    1. 回归基准 = 定稿 v2.1 §6 例题（40/30/20/10 权重 × 75/80/70/60 得分
       → 总分 74 → 合格）+ 完整版五档等级九点边界；
    2. 不封顶（T-05 拍板）：达成率 >100% 时得分 >100 原样保留——单独用例锁定；
    3. 权重合计必须 = 100%（人工设定、系统只计算——定稿 §6）。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from bsc import BscCuowu, BscShuru, QUANZHONG_MOREN, jisuan_bsc  # noqa: E402


class TestLiti(unittest.TestCase):
    """定稿 §6 例题回归——总分 74 → 合格（最重要的用例）。"""

    def test_dinggao_liti(self) -> None:
        """四维得分 75/80/70/60 + 默认权重 → 总分 74 → 合格。"""
        jg = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000))
        # 得分 = 达成率 ÷ 100（half-up）：7500 基点 → 75 分，以此类推
        self.assertEqual((jg.caijing_defen, jg.kehu_defen,
                          jg.neibu_defen, jg.xuexi_defen), (75, 80, 70, 60))
        # 总分 = (40×75 + 30×80 + 20×70 + 10×60) ÷ 100 = 7400 ÷ 100 = 74
        self.assertEqual(jg.zongfen, 74)
        self.assertEqual(jg.dengji, '合格')   # 70~79 档
        self.assertEqual(jg.quanzhong, QUANZHONG_MOREN)  # 默认权重回显


class TestBufengding(unittest.TestCase):
    """不封顶（T-05 拍板）：超 100% 达成率得分原样保留、不裁剪。"""

    def test_danwei_chaoguo_100(self) -> None:
        """财务达成率 120% → 得分 120 保留 → 总分 92 → 优秀。"""
        jg = jisuan_bsc(BscShuru(12000, 8000, 7000, 6000))
        self.assertEqual(jg.caijing_defen, 120)   # 不裁剪到 100
        # 总分 = (40×120 + 30×80 + 20×70 + 10×60) ÷ 100 = 9200 ÷ 100 = 92
        self.assertEqual(jg.zongfen, 92)
        self.assertEqual(jg.dengji, '优秀')

    def test_quanwei_chaoguo_100(self) -> None:
        """四维全部超 100%：得分全部保留，总分 129 → 优秀。"""
        jg = jisuan_bsc(BscShuru(15000, 12000, 11000, 10500))
        # 得分 150/120/110/105；总分 = (6000+3600+2200+1050)÷100 = 128.5 → 129
        self.assertEqual((jg.caijing_defen, jg.kehu_defen,
                          jg.neibu_defen, jg.xuexi_defen), (150, 120, 110, 105))
        self.assertEqual(jg.zongfen, 129)
        self.assertEqual(jg.dengji, '优秀')


class TestQuanzhong(unittest.TestCase):
    """权重：默认 40/30/20/10；自定义可微调但合计必须 = 100。"""

    def test_zidingyi_quanzhong(self) -> None:
        """自定义权重（20, 30, 30, 20）→ 总分 72 → 合格。"""
        jg = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000,
                                 quanzhong=(20, 30, 30, 20)))
        # 总分 = (20×75 + 30×80 + 30×70 + 20×60) ÷ 100 = 7200 ÷ 100 = 72
        self.assertEqual(jg.zongfen, 72)
        self.assertEqual(jg.dengji, '合格')
        self.assertEqual(jg.quanzhong, (20, 30, 30, 20))

    def test_heji_fei_100_jujue(self) -> None:
        """权重合计 ≠ 100 → 拒绝（定稿：权重人工设定、合计 100%）。"""
        for huai in ((40, 30, 20, 5), (40, 30, 20, 11), (39, 30, 20, 10)):
            with self.assertRaises(BscCuowu, msg=f'{huai} 应被拒绝'):
                jisuan_bsc(BscShuru(7500, 8000, 7000, 6000, quanzhong=huai))

    def test_quanzhong_xingtai(self) -> None:
        """单维超 100 / 负数 / 布尔 / 非元组 / 长度不足 → 拒绝。"""
        for huai in ((40, 30, 20, 15), (-1, 30, 20, 51), (40, 30, 20, True),
                     [40, 30, 20, 10], (40, 30, 20)):
            with self.assertRaises(BscCuowu, msg=f'{huai!r} 应被拒绝'):
                jisuan_bsc(BscShuru(7500, 8000, 7000, 6000, quanzhong=huai))


class TestDachenglv(unittest.TestCase):
    """达成率校验：非负整数基点 + 合理性上限（上限 ≠ 得分封顶）。"""

    def test_feifa_dachenglv(self) -> None:
        """负数 / 浮点 / 布尔 / 超上限 → 拒绝（整数基点纪律）。"""
        for huai in (-1, 100.5, True, 1_000_001):
            with self.assertRaises(BscCuowu, msg=f'{huai!r} 应被拒绝'):
                jisuan_bsc(BscShuru(huai, 0, 0, 0))

    def test_ling_dachenglv(self) -> None:
        """达成率 0 合法：得分 0、总分 0 → 严重不合格。"""
        jg = jisuan_bsc(BscShuru(0, 0, 0, 0))
        self.assertEqual(jg.zongfen, 0)
        self.assertEqual(jg.dengji, '严重不合格')


class TestDengji(unittest.TestCase):
    """等级五档边界：59/60/69/70/79/80/89/90/100 逐点锁定。"""

    def test_wudang_bianjie(self) -> None:
        """四维同分构造恰好整数总分，逐点对照等级表。"""
        # 权重全 25%（自定义 (25,25,25,25)）时总分 = 四维得分平均——
        # 每档边界得分 x 即总分 x，期望等级手查五档表
        anli = [
            (59, '严重不合格'),
            (60, '预警'),   # 60 起进入预警档
            (69, '预警'),
            (70, '合格'),   # 70 起进入合格档
            (79, '合格'),
            (80, '良好'),   # 80 起进入良好档
            (89, '良好'),
            (90, '优秀'),   # 90 起进入优秀档
            (100, '优秀'),
        ]
        for defen, qidai in anli:
            with self.subTest(defen=defen):
                # 达成率 = 得分 × 100 基点（整数换算，无舍入干扰）
                jg = jisuan_bsc(BscShuru(defen * 100, defen * 100,
                                         defen * 100, defen * 100,
                                         quanzhong=(25, 25, 25, 25)))
                self.assertEqual(jg.zongfen, defen)
                self.assertEqual(jg.dengji, qidai)


class TestSheru(unittest.TestCase):
    """half-up 舍入：维度得分与总分两处整数化逐例验算。"""

    def test_defen_half_up(self) -> None:
        """达成率 75.5% → 76 分；74.5% → 75 分；74.49% → 74 分。"""
        # 7450 基点 = 74.5%：half-up 进位到 75；7449 基点 = 74.49% 不进位
        self.assertEqual(jisuan_bsc(BscShuru(7550, 0, 0, 0)).caijing_defen, 76)
        self.assertEqual(jisuan_bsc(BscShuru(7450, 0, 0, 0)).caijing_defen, 75)
        self.assertEqual(jisuan_bsc(BscShuru(7449, 0, 0, 0)).caijing_defen, 74)

    def test_zongfen_half_up(self) -> None:
        """总分 0.5 → 1（进位）；0.4 → 0（舍去）；0.8 → 1（进位）。"""
        # (1,0,0,1)：Σ权重×得分 = 40+10 = 50 → 0.5 → half-up 1
        self.assertEqual(jisuan_bsc(BscShuru(100, 0, 0, 100)).zongfen, 1)
        # (1,0,0,0)：Σ = 40 → 0.4 → 0（小数不足一半舍去）
        self.assertEqual(jisuan_bsc(BscShuru(100, 0, 0, 0)).zongfen, 0)
        # (2,0,0,0)：Σ = 80 → 0.8 → 1（小数过半进位）
        self.assertEqual(jisuan_bsc(BscShuru(200, 0, 0, 0)).zongfen, 1)


class TestJiaoyan(unittest.TestCase):
    """输入校验与确定性。"""

    def test_feifa_shuru_leixing(self) -> None:
        """非 BscShuru 输入 → 拒绝。"""
        with self.assertRaises(BscCuowu):
            jisuan_bsc('不是输入')  # type: ignore[arg-type]

    def test_quedingxing(self) -> None:
        """确定性：同输入两次调用结果完全一致（dataclass 等值）。"""
        shuru = BscShuru(7500, 8000, 7000, 6000)
        self.assertEqual(jisuan_bsc(shuru), jisuan_bsc(shuru))


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_bsc.py
    unittest.main()
