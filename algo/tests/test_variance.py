"""variance（差异计算模块）单元测试 —— 期望值全部手工验算写死。

设计原则：
    1. 回归基准 = 定稿 v2.1 §2.3 的 E&G Co 弹性预算全表（六行 + 合计）；
    2. 每条口径（方向/F-A/三档预警/基准退化/除零/校验）各一组用例；
    3. 差异率基点手工换算（如 5,000/105,000 = 4.7619% → 476 基点）。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from variance import ChayiCuowu, ChayiShuru, jisuan_chayi  # noqa: E402


def eg_liu_hang() -> list[ChayiShuru]:
    """构造 E&G Co 六行输入（预算 3,000 件 / 实际 3,500 件的弹性对比）。

    数据与期望输出来自定稿 v2.1 §2.3 表格，金额元 ×100 转分；
    此函数同时被"全表回归"与 docstring 示例的知识点 3 复用。
    """
    # 六行依次：直接材料 / 直接人工 / 间接人工 / 电力 / 物料 / 固定成本
    return [
        ChayiShuru('2026-01', '直接材料', '成本类', 9_000_000, 10_500_000, 11_000_000),
        ChayiShuru('2026-01', '直接人工', '成本类', 7_500_000, 8_750_000, 8_750_000),
        ChayiShuru('2026-01', '间接人工', '成本类', 6_000_000, 7_000_000, 7_100_000),
        ChayiShuru('2026-01', '电力',     '成本类', 1_500_000, 1_750_000, 1_480_000),
        ChayiShuru('2026-01', '物料',     '成本类', 2_400_000, 2_800_000, 2_640_000),
        ChayiShuru('2026-01', '固定成本', '成本类', 5_500_000, 5_500_000, 5_500_000),
    ]


class TestEHuiGui(unittest.TestCase):
    """E&G Co 全表回归——与定稿例题逐行逐格一致（最重要的用例组）。

    任何改动若使本组失败，即为口径回归（对应定稿 v2.1 §2.3）。
    """

    def test_quanbiao(self) -> None:
        """六行差异（差额/差异率/F-A/预警）与合计全部对上例题。"""
        jg = jisuan_chayi(eg_liu_hang())
        # 期望值手工验算（差额=分；差异率=基点 half-up）；
        # 预警阈值【2026-09-03 三档分割】= 黄 15%（1500 基点）/ 红 30%（3000 基点）：
        #   材料 +500 元 A；476 基点（4.76%）< 15% → 无
        #   人工 0 '—'；无
        #   间接 +100 元 A；143 基点 → 无
        #   电力 −270 元 F；1543 基点（15.43%）≥ 15% → 黄
        #   物料 −160 元 F；571 基点（5.71%）< 15% → 无
        #   固定 0 '—'；无
        qidai = [
            (500_000, 476, 'A', '无'),
            (0, 0, '—', '无'),
            (100_000, 143, 'A', '无'),
            (-270_000, 1543, 'F', '黄'),
            (-160_000, 571, 'F', '无'),
            (0, 0, '—', '无'),
        ]
        self.assertListEqual(
            [(x.chae_fen, x.chalv_bps, x.fa, x.yujing) for x in jg.xiang],
            qidai,
        )
        # 合计：36,470 − 36,300 = +170 元 → A（全表同向成本类）
        self.assertEqual(jg.heji_chae_fen, 170_000)
        self.assertEqual(jg.heji_fa, 'A')
        # 预警计数：红 0、黄 1（电力）、无 5、无法定级 0（阈值 15%/30%）
        self.assertEqual((jg.hong_shu, jg.huang_shu, jg.wu_shu, jg.wufa_shu), (0, 1, 5, 0))


class TestFangxiang(unittest.TestCase):
    """方向规则：成本类与收入类的 F-A 映射相反（§0.5）。"""

    def test_shouru_chaoe_shi_F(self) -> None:
        """收入类正差额 = 超额 = 有利 F（与成本类相反）。"""
        jg = jisuan_chayi([ChayiShuru('2026-Q1', '营收', '收入类',
                                      5_000_000, 5_200_000, 5_350_000)])
        x = jg.xiang[0]
        self.assertEqual(x.chae_fen, 150_000)      # 超收 1,500 元
        self.assertEqual(x.fa, 'F')
        # 1500/52000 = 2.88% → 288 基点 → 无（< 5% 新阈值）
        self.assertEqual(x.chalv_bps, 288)
        self.assertEqual(x.yujing, '无')

    def test_shouru_weida_shi_A(self) -> None:
        """收入类负差额 = 未达标 = 不利 A。"""
        jg = jisuan_chayi([ChayiShuru('2026-Q1', '营收', '收入类',
                                      5_000_000, 5_200_000, 5_000_000)])
        self.assertEqual(jg.xiang[0].fa, 'A')

    def test_hunhe_fangxiang_heji_wu_panding(self) -> None:
        """成本/收入混合输入：合计 F/A 无意义 → '—'（明细仍逐项判定）。"""
        jg = jisuan_chayi([
            ChayiShuru('2026-01', '营收', '收入类', 5_000_000, 5_200_000, 5_350_000),
            ChayiShuru('2026-01', '直接材料', '成本类', 9_000_000, 10_500_000, 11_000_000),
        ])
        self.assertEqual(jg.heji_fa, '—')


class TestJizhun(unittest.TestCase):
    """基准规则：滚动优先、缺省退化、除零保护。

    除零是唯一"无法定级"的场景——预警记 '—' 交人工（口径见模块头）。
    """

    def test_gundong_quexing_tuihua_chushi(self) -> None:
        """未提供滚动预算（None）：基准 = 初始（固定）预算。"""
        jg = jisuan_chayi([ChayiShuru('2026-02', '办公费', '成本类',
                                      3_000_000, None, 3_100_000)])
        x = jg.xiang[0]
        self.assertEqual(x.jizhun_fen, 3_000_000)   # 基准退化到固定预算
        self.assertEqual(x.chae_fen, 100_000)       # 超支 1,000 元
        self.assertEqual(x.fa, 'A')

    def test_jizhun_ling_chalv_None(self) -> None:
        """基准为 0：差异率 None、预警 '—'（交人工，不臆造定级）。"""
        # 场景：新科目尚无任何预算（两列基准都是 0）但已有实际发生
        jg = jisuan_chayi([ChayiShuru('2026-03', '新科目', '成本类',
                                      0, 0, 500_000)])
        x = jg.xiang[0]
        self.assertIsNone(x.chalv_bps)
        self.assertEqual(x.yujing, '—')
        # 差额本身仍可算（500,000 分 = 超支 5,000 元）
        self.assertEqual(x.chae_fen, 500_000)

    def test_yujing_sandang_bianjie(self) -> None:
        """三档边界（2026-09-03 阈值）：恰 1500=黄、2999=黄、3000=红、1499=无。"""
        # 基准统一 10,000,000 分（=10 万元）；偏差=基点×基准÷10000：
        # 1499 基点→1,499,000 分；1500→1,500,000；2999→2,999,000；3000→3,000,000
        jg = jisuan_chayi([
            ChayiShuru('2026-01', '边界1499', '成本类', 10_000_000, 10_000_000, 11_499_000),
            ChayiShuru('2026-02', '边界1500', '成本类', 10_000_000, 10_000_000, 11_500_000),
            ChayiShuru('2026-03', '边界2999', '成本类', 10_000_000, 10_000_000, 12_999_000),
            ChayiShuru('2026-04', '边界3000', '成本类', 10_000_000, 10_000_000, 13_000_000),
        ])
        # 1,499,000/10,000,000 = 14.99% = 1499 基点 → 无
        self.assertEqual(jg.xiang[0].yujing, '无')
        self.assertEqual(jg.xiang[1].yujing, '黄')   # 恰达 15% 阈值
        self.assertEqual(jg.xiang[2].yujing, '黄')
        self.assertEqual(jg.xiang[3].yujing, '红')   # 恰达 30% 阈值


class TestJiaoyan(unittest.TestCase):
    """输入校验：脏数据必须被拒绝。

    校验范围：方向枚举 / 金额形态（负数、浮点、布尔）/ 键唯一 / 非空。
    """

    def test_feifa_fangxiang(self) -> None:
        """未知方向 → 拒绝。"""
        with self.assertRaises(ChayiCuowu):
            jisuan_chayi([ChayiShuru('2026-01', 'x', '随便', 1, 1, 1)])

    def test_feifa_jine(self) -> None:
        """负数 / 浮点 / 布尔金额 → 拒绝（整数分纪律）。"""
        # 三种典型脏形态逐个试（bool 是 int 子类，须单独排除）
        for huai in (-1, 100.5, True):
            with self.assertRaises(ChayiCuowu, msg=f'{huai!r} 应被拒绝'):
                jisuan_chayi([ChayiShuru('2026-01', 'x', '成本类', huai, 1, 1)])

    def test_chongfu_he_kong(self) -> None:
        """（期间, 科目）重复 / 空列表 → 拒绝。"""
        with self.assertRaises(ChayiCuowu):
            jisuan_chayi([
                ChayiShuru('2026-01', 'x', '成本类', 1, 1, 1),
                ChayiShuru('2026-01', 'x', '成本类', 2, 2, 2),  # 同键重复
            ])
        with self.assertRaises(ChayiCuowu):
            jisuan_chayi([])


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_variance.py
    unittest.main()
