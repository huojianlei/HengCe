"""planning_operational（规划/执行差异拆分）单元测试 —— 期望值全部手工验算。

设计原则：
    1. 回归基准 = 定稿 v2.1 §3 的 Holmes Ltd 案例（三总量+四细分+残差）；
    2. 两套符号口径各有专测（总量正=A；细分正=F）；
    3. 退化（修订=标准）与校验组各一组；恒等式与残差关系为内部铁律。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from planning_operational import ChaifenCuowu, ChaifenShuru, chai_fen  # noqa: E402


def holmes() -> ChaifenShuru:
    """Holmes Ltd 输入（定稿 v2.1 §3）。

    标准 7kg×400 分；修订 8kg×380 分；产量 1,400；耗用 11,000kg；
    成本 4,150,000 分（=41,500 元，金额 ×100 转分）。
    """
    return ChaifenShuru(
        biaozhun_danjia_fen=400, biaozhun_yongliang=7,
        xiuding_danjia_fen=380, xiuding_yongliang=8,
        shiji_chanliang=1400, shiji_yongliang=11000,
        shiji_chengben_fen=4_150_000,
    )


class TestHolmesGuiGui(unittest.TestCase):
    """Holmes 案例回归——与定稿例题逐值一致（最重要的用例组）。"""

    def test_sange_zongliang(self) -> None:
        """三总量 + FA + 恒等式：2,300A = 3,360A + (−1,060)F。"""
        jg = chai_fen(holmes())
        # 原标准总 = 4,150,000 − 1,400×7×400 = +230,000 分（2,300 元）→ A
        self.assertEqual((jg.yuandan_zong_fen, jg.yuandan_zong_fa), (230_000, 'A'))
        # 规划总 = 1,400×8×380 − 1,400×7×400 = +336,000 分（3,360 元）→ A
        self.assertEqual((jg.guihua_zong_fen, jg.guihua_zong_fa), (336_000, 'A'))
        # 执行总 = 4,150,000 − 4,256,000 = −106,000 分（−1,060 元）→ F
        self.assertEqual((jg.zhixing_zong_fen, jg.zhixing_zong_fa), (-106_000, 'F'))
        # 恒等式标志必须成立
        self.assertTrue(jg.hengdengshi_chengli)

    def test_sixiang_xibao(self) -> None:
        """四项细分（ACCA 符号：正 = F）+ 残差，全部对上例题。"""
        jg = chai_fen(holmes())
        # 价格规划 = (400−380)×11,000 = +220,000 分（2,200 元 F）
        self.assertEqual((jg.jiage_guihua_fen, jg.jiage_guihua_fa), (220_000, 'F'))
        # 价格执行 = 380×11,000 − 4,150,000 = +30,000 分（300 元 F）
        self.assertEqual((jg.jiage_zhixing_fen, jg.jiage_zhixing_fa), (30_000, 'F'))
        # 用量规划 = (7−8)×1,400×400 = −560,000 分（−5,600 元 A）
        self.assertEqual((jg.yongliang_guihua_fen, jg.yongliang_guihua_fa), (-560_000, 'A'))
        # 用量执行 = (8×1,400−11,000)×380 = +76,000 分（760 元 F）
        self.assertEqual((jg.yongliang_zhixing_fen, jg.yongliang_zhixing_fa), (76_000, 'F'))
        # 残差 = (11,200−11,000)×(400−380) = 4,000 分（40 元）
        self.assertEqual(jg.cancha_fen, 4_000)
        # 细分合计（F 口径）= −234,000：与总量的差恰为残差（P3 关系的显式断言）
        he = jg.jiage_guihua_fen + jg.jiage_zhixing_fen + jg.yongliang_guihua_fen + jg.yongliang_zhixing_fen
        self.assertEqual(-he - jg.cancha_fen, jg.yuandan_zong_fen)


class TestTuihua(unittest.TestCase):
    """退化场景：无结构变更（修订 = 标准）。"""

    def test_guihua_guii_ling(self) -> None:
        """修订=标准：规划总差异 = 0，全部差异归执行；残差 = 0。"""
        jg = chai_fen(ChaifenShuru(400, 7, 400, 7, 1400, 11000, 4_150_000))
        self.assertEqual(jg.guihua_zong_fen, 0)
        self.assertEqual(jg.guihua_zong_fa, '—')
        # 执行总 = 原标准总（规划为零时两者重合）
        self.assertEqual(jg.zhixing_zong_fen, jg.yuandan_zong_fen)
        # 单价相同 → 残差恒为 0（细分为精确分解，无交叉项）
        self.assertEqual(jg.cancha_fen, 0)

    def test_wanmei_zhixing(self) -> None:
        """完美执行（实际恰等于修订标准）：执行总 = 0，全部差异归规划。"""
        # 实际成本 = 修订标准成本 = 1,400×8×380 = 4,256,000 分
        jg = chai_fen(ChaifenShuru(400, 7, 380, 8, 1400, 8 * 1400, 1_400 * 8 * 380))
        self.assertEqual(jg.zhixing_zong_fen, 0)
        self.assertEqual(jg.zhixing_zong_fa, '—')
        self.assertEqual(jg.yuandan_zong_fen, jg.guihua_zong_fen)  # 336,000


class TestJiaoyan(unittest.TestCase):
    """输入校验：脏数据必须被拒绝。"""

    def test_chanliang_ling(self) -> None:
        """产量为 0 → 拒绝（单位成本失去分母，拆分无数学前提）。"""
        with self.assertRaises(ChaifenCuowu):
            chai_fen(ChaifenShuru(400, 7, 380, 8, 0, 11000, 4_150_000))

    def test_feifa_shuzhi(self) -> None:
        """负数 / 浮点 / 布尔 / 非实例 → 拒绝。"""
        for huai in (ChaifenShuru(-1, 7, 380, 8, 1400, 11000, 4_150_000),   # 负单价
                     ChaifenShuru(400, 7, 380, 8, 1400, 11000, 100.5),      # 浮点成本
                     ChaifenShuru(400, True, 380, 8, 1400, 11000, 4_150_000)):  # 布尔用量
            with self.assertRaises(ChaifenCuowu):
                chai_fen(huai)
        with self.assertRaises(ChaifenCuowu):
            chai_fen('不是输入对象')  # type: ignore[arg-type]


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_planning_operational.py
    unittest.main()
