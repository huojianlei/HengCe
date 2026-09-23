"""fuzz 冒烟测试 —— 把随机数据自检纳入常规测试运行（固定种子，可复现）。

与命令行的区别：
    tools/gen_data.py --moshi suiji 是【手动/门禁】工具（任意种子、可大批量）；
    本文件是【常规回归】的一小批固定种子用例，保证每次跑 unittest
    都顺带做一轮随机性质自检。

性质清单见 tools/gen_data.py 各模块的 jiancha_*_li docstring（滚动 P1~P6 / 积木 P1~P7）。
命名规范（2026-08-23）：标识符全拼音。
"""

from __future__ import annotations

import unittest

# 以 discover -t . 运行时 algo 根目录在 sys.path 上，tools 作为包导入
from tools.gen_data import (  # noqa: E402
    ling_zengzhang_yansheng,
    suiji_yansheng,
    suiji_yansheng_bsc,
    suiji_yansheng_jimu,
    suiji_yansheng_kpi,
    suiji_yansheng_suyuan,
)


class TestSuijiMaoyan(unittest.TestCase):
    """随机数据冒烟：数量小（秒级），种子固定（失败可复现）。"""

    #: 固定种子：与随机性无关地保证本用例的可复现性（失败时可用同种子重放）
    ZHONGZI = 20260822

    def test_suiji_li_quanbu_xingzhi(self) -> None:
        """60 组随机输入：P1~P6 全部性质零失败。"""
        shibai = suiji_yansheng(shuliang=60, zhongzi=self.ZHONGZI, xiangqi=False)
        # 任何一组失败都直接失败——性质测试不容忍部分通过
        self.assertEqual(shibai, 0, '存在性质断言失败的随机用例（用同种子复现）')

    def test_ling_zengzhang_hengdeng(self) -> None:
        """30 组强制 g=0：一切剩余期值必须等于初始预算（恒等性质）。"""
        shibai = ling_zengzhang_yansheng(shuliang=30, zhongzi=self.ZHONGZI, xiangqi=False)
        self.assertEqual(shibai, 0, '零增长率下剩余期未退化为初始预算')


class TestJimuMaoyan(unittest.TestCase):
    """积木模块随机冒烟：数量小（秒级），种子固定（失败可复现）。"""

    #: 固定种子：与 TestSuijiMaoyan 同源约定（失败时可用同种子重放）
    ZHONGZI = 20260823

    def test_jimu_li_quanbu_xingzhi(self) -> None:
        """40 组随机积木输入：P1~P7 全部性质 + 影子互证零失败。"""
        shibai = suiji_yansheng_jimu(shuliang=40, zhongzi=self.ZHONGZI, xiangqi=False)
        self.assertEqual(shibai, 0, '存在性质断言失败的随机积木用例（用同种子复现）')


class TestBscMaoyan(unittest.TestCase):
    """BSC 模块随机冒烟：数量小（秒级），种子固定（失败可复现）。"""

    #: 固定种子：与 TestSuijiMaoyan 同源约定（失败时可用同种子重放）
    ZHONGZI = 20260824

    def test_bsc_li_quanbu_xingzhi(self) -> None:
        """40 组随机 BSC 输入：P1~P5 全部性质 + 影子互证零失败。"""
        shibai = suiji_yansheng_bsc(shuliang=40, zhongzi=self.ZHONGZI, xiangqi=False)
        self.assertEqual(shibai, 0, '存在性质断言失败的随机 BSC 用例（用同种子复现）')


class TestKpiMaoyan(unittest.TestCase):
    """KPI 模块随机冒烟：数量小（秒级），种子固定（失败可复现）。"""

    #: 固定种子：与 TestSuijiMaoyan 同源约定（失败时可用同种子重放）
    ZHONGZI = 20260825

    def test_kpi_li_quanbu_xingzhi(self) -> None:
        """40 组随机 KPI 输入：P1~P4 全部性质 + 影子互证零失败。"""
        shibai = suiji_yansheng_kpi(shuliang=40, zhongzi=self.ZHONGZI, xiangqi=False)
        self.assertEqual(shibai, 0, '存在性质断言失败的随机 KPI 用例（用同种子复现）')


class TestSuyuanMaoyan(unittest.TestCase):
    """溯源模块随机冒烟：数量小（秒级），种子固定（失败可复现）。"""

    #: 固定种子：与 TestSuijiMaoyan 同源约定（失败时可用同种子重放）
    ZHONGZI = 20260826

    def test_suyuan_li_quanbu_xingzhi(self) -> None:
        """40 组随机溯源输入：P1~P4 全部性质 + 影子互证零失败。"""
        shibai = suiji_yansheng_suyuan(shuliang=40, zhongzi=self.ZHONGZI, xiangqi=False)
        self.assertEqual(shibai, 0, '存在性质断言失败的随机溯源用例（用同种子复现）')


if __name__ == '__main__':
    # 支持直接运行：python tests/test_fuzz_smoke.py
    unittest.main()
