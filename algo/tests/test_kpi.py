# -*- coding: utf-8 -*-
"""kpi（KPI 指标库）单元测试 —— 期望值全部手工验算写死。

设计原则：
    1. 回归基准 = 教材 06 章验算例（毛利率 60% / 费用偏差率 +10% /
       产能利用率 80%）+ 定稿 §8 全部 15 项公式逐项锁定；
    2. 缺数纪律：分子/分母缺数或分母 ≤ 0 → None（交人工，不臆造）；
    3. 单位纪律：比率/周转率 = 整数基点（1 次 = 10000 基点）；
       交付周期 = 天；异常事项 = 次。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from kpi import KpiCuowu, KpiShuru, jisuan_kpi  # noqa: E402


def jiaocai_shuru() -> KpiShuru:
    """构造教材 06 章验算例输入（金额元 ×100 转分；计数为整数件）。"""
    return KpiShuru(
        shouru_shiji_fen=15_000_000, shouru_yusuan_fen=14_000_000,
        maoli_fen=9_000_000, jingshui_fen=3_000_000, pbit_fen=4_500_000,
        ziben_zhanyong_fen=7_500_000,
        liudong_zichan_qichu_fen=5_000_000, liudong_zichan_qimo_fen=6_000_000,
        liudong_fuzhai_qichu_fen=2_000_000, liudong_fuzhai_qimo_fen=2_500_000,
        feiyong_shiji_fen=11_000_000, feiyong_yusuan_fen=10_000_000,
        kekong_chengben_shiji_fen=9_500_000, kekong_chengben_yusuan_fen=10_000_000,
        caigou_benqi_fen=10_800_000, caigou_shangqi_fen=10_000_000,
        shiji_chanchu=800, qianzai_channeng=1000,
        dingdan_zongshu=200, lvyue_dingdan_shu=190,
        jiaofu_zhouqi_tian_shu=6,
        manyi_keshu=180, shoufang_keshu=200,
        jihua_yewu_liang=1000, wancheng_yewu_liang=750,
        yichang_shijian_shu=3,
    )


class TestJiaocaiLiti(unittest.TestCase):
    """教材 06 章验算例全量回归——15 项逐项锁定（最重要的用例）。"""

    def test_quanbiao(self) -> None:
        """15 项指标与手算期望逐项相等。"""
        jg = jisuan_kpi(jiaocai_shuru())
        # 手算（比率=基点；周转率 1 次=10000 基点）：
        #   营收达成率 15,000,000/14,000,000 = 107.142857% → 10714
        #   成本控制率 9,500,000/10,000,000 = 95% → 9500
        #   费用偏差率 (11,000,000−10,000,000)/10,000,000 = +10% → 1000
        #   毛利率 9,000,000/15,000,000 = 60% → 6000
        #   净利率 3,000,000/15,000,000 = 20% → 2000
        #   销售利润率 4,500,000/15,000,000 = 30% → 3000
        #   资产周转率 15,000,000/7,500,000 = 2 次 → 20000
        #   资金周转率 平均营运资金=(3,000,000+3,500,000)/2=3,250,000
        #     → 15,000,000/3,250,000 = 4.6154 次 → 46154
        #   采购变动率 (10,800,000−10,000,000)/10,000,000 = +8% → 800
        self.assertEqual(jg.yingshou_dachenglv_bps, 10714)
        self.assertEqual(jg.chengben_kongzhilv_bps, 9500)
        self.assertEqual(jg.feiyong_pianchalv_bps, 1000)
        self.assertEqual(jg.maolilv_bps, 6000)
        self.assertEqual(jg.jinglirunlv_bps, 2000)
        self.assertEqual(jg.xiaoshou_lirunlv_bps, 3000)
        self.assertEqual(jg.zichan_zhouzhuanlv_bps, 20000)
        self.assertEqual(jg.zijin_zhouzhuanlv_bps, 46154)
        self.assertEqual(jg.caigou_chengben_bian_donglv_bps, 800)
        # 非财务：履约率 190/200 = 95% → 9500；产能 800/1000 = 80% → 8000；
        # 交付周期 6 天；满意度 180/200 = 90% → 9000；
        # 进度 750/1000 = 75% → 7500；异常事项 3 次
        self.assertEqual(jg.gongyinglian_lvyuelv_bps, 9500)
        self.assertEqual(jg.channeng_liyonglv_bps, 8000)
        self.assertEqual(jg.jiaofu_zhouqi_tian, 6)
        self.assertEqual(jg.kehu_manyilv_bps, 9000)
        self.assertEqual(jg.yewu_jindu_bps, 7500)
        self.assertEqual(jg.yichang_shijian_shu, 3)


class TestFangxiang(unittest.TestCase):
    """带符号指标：费用偏差率与采购变动率保留负号（节约为负）。"""

    def test_jieyue_wei_fu(self) -> None:
        """费用 90,000 vs 预算 100,000 → −10%；采购下降 → 负变动率。"""
        # 符号纪律：负 = 节约/下降（有利方向）——与 F/A 判定无关，
        # 展示口径正 = 超支/上涨
        jg = jisuan_kpi(KpiShuru(
            feiyong_shiji_fen=9_000_000, feiyong_yusuan_fen=10_000_000,
            caigou_benqi_fen=9_500_000, caigou_shangqi_fen=10_000_000,
        ))
        self.assertEqual(jg.feiyong_pianchalv_bps, -1000)   # 节约 10%
        self.assertEqual(jg.caigou_chengben_bian_donglv_bps, -500)  # 下降 5%


class TestQueshu(unittest.TestCase):
    """缺数纪律：缺数/分母 ≤ 0 → None（交人工，不臆造）。"""

    def test_queshu_wei_None(self) -> None:
        """只给收入 → 营收达成率可算，其余依赖缺失字段的项全 None。"""
        # 缺数纪律：本模块不替调用方"填 0"——缺失 ≠ 零（与 data_ingest
        # 空值拒收口径同源），交人工补数
        jg = jisuan_kpi(KpiShuru(shouru_shiji_fen=15_000_000,
                                 shouru_yusuan_fen=14_000_000))
        self.assertEqual(jg.yingshou_dachenglv_bps, 10714)
        self.assertIsNone(jg.maolilv_bps)
        self.assertIsNone(jg.feiyong_pianchalv_bps)
        self.assertIsNone(jg.yichang_shijian_shu)

    def test_fenmu_ling(self) -> None:
        """分母为 0：比率无法定义 → None。"""
        # 预算收入 0 → 营收达成率 None；实际收入 0 → 毛利率分母 0 → None
        jg = jisuan_kpi(KpiShuru(shouru_shiji_fen=0, shouru_yusuan_fen=0,
                                 maoli_fen=50))
        self.assertIsNone(jg.yingshou_dachenglv_bps)
        self.assertIsNone(jg.maolilv_bps)   # 收入 0 也是毛利率分母 0

    def test_yingyun_zijin_fei_zheng(self) -> None:
        """平均营运资金 ≤ 0：资金周转率 None（分母非正不定义）。"""
        jg = jisuan_kpi(KpiShuru(
            shouru_shiji_fen=15_000_000,
            liudong_zichan_qichu_fen=1_000_000, liudong_zichan_qimo_fen=1_000_000,
            liudong_fuzhai_qichu_fen=1_500_000, liudong_fuzhai_qimo_fen=1_500_000,
        ))
        self.assertIsNone(jg.zijin_zhouzhuanlv_bps)


class TestSheru(unittest.TestCase):
    """half-up 舍入：1/3 → 3333 基点、2/3 → 6667 基点。"""

    def test_half_up(self) -> None:
        """比率 1/3 与 2/3 的 half-up 边界。"""
        # 1/3 = 3333.33 → 3333（不足一半舍去）；2/3 = 6666.67 → 6667（过半进位）
        jg = jisuan_kpi(KpiShuru(shouru_shiji_fen=1, shouru_yusuan_fen=3))
        self.assertEqual(jg.yingshou_dachenglv_bps, 3333)
        jg2 = jisuan_kpi(KpiShuru(shouru_shiji_fen=2, shouru_yusuan_fen=3))
        self.assertEqual(jg2.yingshou_dachenglv_bps, 6667)

    def test_yingyun_banup(self) -> None:
        """平均营运资金 half-up：(1,000,000 + 2,000,001)/2 恰过半进位。"""
        # 期初净营运资金 1,000,000、期末 2,000,001 → 和 3,000,001 →
        # (3,000,001+1)//2 = 1,500,001（half-up：1,500,000.5 进位）
        jg = jisuan_kpi(KpiShuru(
            shouru_shiji_fen=3_000_000,
            liudong_zichan_qichu_fen=1_000_000, liudong_zichan_qimo_fen=2_000_001,
            liudong_fuzhai_qichu_fen=0, liudong_fuzhai_qimo_fen=0,
        ))
        # 3,000,000/1,500,001 = 2 次 → 20000 基点（half-up 后仍 2 次）
        self.assertEqual(jg.zijin_zhouzhuanlv_bps, 20000)


class TestJiaoyan(unittest.TestCase):
    """输入校验与确定性。"""

    def test_feifa_zhi(self) -> None:
        """负数 / 浮点 / 布尔 / 超上限 → 拒绝（整数纪律）。"""
        for huai in (-1, 100.5, True, 9 * 10**11 + 1):
            with self.assertRaises(KpiCuowu, msg=f'{huai!r} 应被拒绝'):
                jisuan_kpi(KpiShuru(shouru_shiji_fen=huai))

    def test_feifa_leixing(self) -> None:
        """非 KpiShuru 输入 → 拒绝。"""
        with self.assertRaises(KpiCuowu):
            jisuan_kpi('不是输入')  # type: ignore[arg-type]

    def test_quedingxing(self) -> None:
        """确定性：同输入两次调用结果完全一致（dataclass 等值）。"""
        shuru = jiaocai_shuru()
        self.assertEqual(jisuan_kpi(shuru), jisuan_kpi(shuru))


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_kpi.py
    unittest.main()
