# -*- coding: utf-8 -*-
"""suyuan（经营变更双维溯源）单元测试 —— 期望值全部手工验算写死。

设计原则：
    1. 回归基准 = 模块 docstring 的变更事件例题（原材料涨价+订单延迟+
       产能提升）——影响率/作用方向/占比逐项锁定；
    2. 作用方向 = 15 项 KPI 偏好表（越高越好 vs 越低越好）逐项锁定；
    3. 占比分母 = Σ|净影响率|（同积木 D2）——合计恒 10000 基点是核心不变量。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from suyuan import SuyuanCuowu, SuyuanHang, jisuan_suyuan  # noqa: E402


def liti_hang() -> list[SuyuanHang]:
    """构造 docstring 例题的三行输入（变更事件：涨价+延迟+产能提升）。"""
    return [
        SuyuanHang('采购成本变动率', 100_000, 108_000, 100_000),
        SuyuanHang('交付周期', 5, 8, 5),
        SuyuanHang('产能利用率', 800, 850, 800),
    ]


class TestLiti(unittest.TestCase):
    """例题回归：影响率/数值方向/作用方向/占比/TOP3 全部对上。"""

    def test_yingxianglv(self) -> None:
        """三行影响率：+8% → 800、+60% → 6000、+6.25% → 625 基点。"""
        # 手算：采购 (108000−100000)/100000 = +8%；交付 (8−5)/5 = +60%；
        # 产能 (850−800)/800 = +6.25%——全部按 yuan_yusuan 作分母
        jg = jisuan_suyuan(liti_hang())
        self.assertListEqual([x.yingxianglv_bps for x in jg.xiang], [800, 6000, 625])
        # 数值方向：三行都是上升
        self.assertListEqual([x.shuzhi_fangxiang for x in jg.xiang],
                             ['上升', '上升', '上升'])

    def test_zuoyong_pianhao(self) -> None:
        """偏好表：采购/交付周期越低越好（上升=负向）；产能越高越好（正向）。"""
        # 偏好表即模块内 KPI_PIANHAO：作用方向 = 数值方向 × 偏好（四象限）
        jg = jisuan_suyuan(liti_hang())
        self.assertListEqual([x.zuoyong for x in jg.xiang],
                             ['负向作用', '负向作用', '正向作用'])

    def test_zhanbi_he_10000(self) -> None:
        """占比分母 = 800+6000+625 = 7425；三行占比合计恒 10000。"""
        jg = jisuan_suyuan(liti_hang())
        self.assertEqual(jg.yingxiang_fenmu_bps, 7425)
        # 手算：800/7425=10.77%→1077；6000/7425=80.81%→8081；
        # 625/7425=8.42%→842（half-up）
        self.assertListEqual([x.zhanbi_bps for x in jg.xiang], [1077, 8081, 842])
        self.assertEqual(sum(x.zhanbi_bps for x in jg.xiang), 10000)

    def test_top3(self) -> None:
        """TOP3：正向 [产能利用率]；负向 [交付周期, 采购成本变动率]（降序）。"""
        # 负向 TOP3 按 |影响率| 降序：交付 6000 > 采购 800
        jg = jisuan_suyuan(liti_hang())
        self.assertEqual(jg.zhengxiang_top3, ['产能利用率'])
        self.assertEqual(jg.fuxiang_top3, ['交付周期', '采购成本变动率'])


    def test_gongshi_ziduan(self) -> None:
        """公式字段（T-29#4）：结果携带影响率计算公式文本。"""
        # 公式与定稿 §8.3 口径一致——报告【计算公式】列的数据源
        jg = jisuan_suyuan([SuyuanHang('交付周期', 5, 8, 5)])
        self.assertIn('原始预算数值', jg.gongshi)
        self.assertIn('变更后数值 − 变更前数值', jg.gongshi)


class TestZuoyong(unittest.TestCase):
    """作用方向：偏好表 × 数值方向四象限全覆盖。"""

    def test_xiajiang_yuedi_shi_zhengxiang(self) -> None:
        """交付周期 8→5（下降、越低越好）→ 正向作用，影响率 −60%。"""
        # 符号纪律：影响率负 = 数值下降；作用方向才是经营语义
        jg = jisuan_suyuan([SuyuanHang('交付周期', 8, 5, 8)])
        self.assertEqual(jg.xiang[0].yingxianglv_bps, -3750)  # (5−8)/8 = −37.5%
        self.assertEqual(jg.xiang[0].zuoyong, '正向作用')

    def test_xiajiang_yuegao_shi_fuxiang(self) -> None:
        """产能 850→800（下降、越高越好）→ 负向作用。"""
        jg = jisuan_suyuan([SuyuanHang('产能利用率', 850, 800, 850)])
        self.assertEqual(jg.xiang[0].zuoyong, '负向作用')

    def test_chiping_wu_zuoyong(self) -> None:
        """持平：数值方向持平、作用无作用、影响率 0。"""
        jg = jisuan_suyuan([SuyuanHang('交付周期', 5, 5, 5)])
        self.assertEqual(jg.xiang[0].shuzhi_fangxiang, '持平')
        self.assertEqual(jg.xiang[0].zuoyong, '无作用')
        self.assertEqual(jg.xiang[0].yingxianglv_bps, 0)


class TestQueshu(unittest.TestCase):
    """缺数纪律：原始预算缺失/≤0 → 该行 None，不参与占比分母。"""

    def test_yuan_yusuan_None(self) -> None:
        """yuan_yusuan None → 影响率/占比 None；TOP3 跳过该行。"""
        jg = jisuan_suyuan([SuyuanHang('交付周期', 5, 8, None)])
        self.assertIsNone(jg.xiang[0].yingxianglv_bps)
        self.assertIsNone(jg.xiang[0].zhanbi_bps)
        self.assertEqual(jg.zhengxiang_top3, [])
        self.assertEqual(jg.fuxiang_top3, [])

    def test_yuan_yusuan_ling_bu_jin_fenmu(self) -> None:
        """yuan_yusuan = 0 → 该行 None；其余行正常且分母只含可算行。"""
        jg = jisuan_suyuan([
            SuyuanHang('交付周期', 5, 8, 0),        # 分母 0 → None
            SuyuanHang('产能利用率', 800, 850, 800),  # 影响率 625
        ])
        self.assertIsNone(jg.xiang[0].yingxianglv_bps)
        self.assertEqual(jg.yingxiang_fenmu_bps, 625)
        # 唯一可算行独占 100%
        self.assertEqual(jg.xiang[1].zhanbi_bps, 10000)

    def test_quanbu_None(self) -> None:
        """全部行不可算 → 分母 0 → 占比全 None、TOP3 空。"""
        # 除零纪律（与 kpi/积木同源）：分母 0 时不臆造占比，交人工
        jg = jisuan_suyuan([SuyuanHang('交付周期', 5, 8, None)])
        self.assertEqual(jg.yingxiang_fenmu_bps, 0)
        self.assertIsNone(jg.xiang[0].zhanbi_bps)


class TestPaiming(unittest.TestCase):
    """TOP3 排名：降序、并列取输入顺序、超过三项截断。"""

    def test_binglie_qu_shuru_shunxu(self) -> None:
        """两个正向作用影响率相同 → 按输入顺序排名。"""
        # 排序稳定性：Python sort 稳定 → 并列自动保输入顺序（模块文档约定）
        jg = jisuan_suyuan([
            SuyuanHang('产能利用率', 100, 200, 100),   # +100% → 10000 正向
            SuyuanHang('业务完成进度', 100, 200, 100),  # 同影响率
        ])
        self.assertEqual(jg.zhengxiang_top3, ['产能利用率', '业务完成进度'])

    def test_chaoguo_san_xiang_jieduan(self) -> None:
        """四个正向作用 → TOP3 只取前三（按 |影响率| 降序）。"""
        jg = jisuan_suyuan([
            SuyuanHang('产能利用率', 100, 110, 100),   # +10% → 1000
            SuyuanHang('业务完成进度', 100, 130, 100),  # +30% → 3000
            SuyuanHang('客户满意度', 100, 120, 100),    # +20% → 2000
            SuyuanHang('供应链履约率', 100, 140, 100),  # +40% → 4000
        ])
        self.assertEqual(jg.zhengxiang_top3,
                         ['供应链履约率', '业务完成进度', '客户满意度'])


class TestJiaoyan(unittest.TestCase):
    """输入校验与确定性。"""

    def test_weizhi_kpi_ming_jujue(self) -> None:
        """KPI 名不在 15 项清单 → 整行拒绝（防脏名混入）。"""
        # 溯源是结构化流程：KPI 名必须来自 KPI 库（15 项清单），不猜语义
        with self.assertRaises(SuyuanCuowu):
            jisuan_suyuan([SuyuanHang('随便指标', 1, 2, 1)])

    def test_chongfu_kpi_jujue(self) -> None:
        """同一 KPI 两行 → 拒绝（防双计）。"""
        # 同一变更事件对同一 KPI 只允许一行——重复即数据问题
        with self.assertRaises(SuyuanCuowu):
            jisuan_suyuan([
                SuyuanHang('交付周期', 5, 8, 5),
                SuyuanHang('交付周期', 6, 9, 5),
            ])

    def test_feifa_zhi_jujue(self) -> None:
        """负数 / 浮点 / 布尔 / 空列表 → 拒绝。"""
        # bool 是 int 子类，须显式排除（与全项目校验纪律一致）
        for huai in (-1, 100.5, True):
            with self.assertRaises(SuyuanCuowu, msg=f'{huai!r} 应被拒绝'):
                jisuan_suyuan([SuyuanHang('交付周期', huai, 8, 5)])
        with self.assertRaises(SuyuanCuowu):
            jisuan_suyuan([])

    def test_quedingxing(self) -> None:
        """确定性：同输入两次调用结果完全一致（dataclass 等值）。"""
        # 纯函数要求：无 I/O、无全局状态 → 同输入必同输出
        hang = liti_hang()
        self.assertEqual(jisuan_suyuan(hang), jisuan_suyuan(hang))


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_suyuan.py
    unittest.main()
