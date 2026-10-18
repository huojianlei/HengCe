# -*- coding: utf-8 -*-
"""algo 权威实现的冒烟测试 —— 证明 sys.path 引导真实命中 algo 原模块。

范围克制（algo 自身的 275 个用例不在这里重复，见 algo/tests/）：
    1. 引导路径必须指向 开发分支_1.0.5/algo（只读权威实现）；
    2. 各关键模块一次最小数值断言（期望值按 algo 源码手算，非读回实现值）：
       rolling_budget 链法① / variance 默认档 / planning_operational 恒等式 /
       loop_decision 五情形之一 / building_blocks 关键词映射 / bsc 教材例题 /
       kpi 结构完整性 / zhenggai 红行落强制整改 / zuzhi 识别；
    3. 引导必须是插入而非复制：algo 模块的 __file__ 落在 algo 目录内。
"""

import unittest

import houtai_hexin  # 先引包：sys.path 引导在包入口完成
from yinqing import fenxi  # noqa: F401  编排层依赖 algo 的连带冒烟


class YinDaoTestCase(unittest.TestCase):
    """sys.path 引导（houtai_hexin.ALGO_LUJING）。

    验算口径：路径指向正确 + import 到的确实是 algo 原件（非任何副本）。
    """

    def test_lujing_zhixiang_algo(self):
        """引导路径必须是 开发分支_1.0.5/algo，且真实存在。"""
        # 目录名与存在性各验一发——引导失效时后续所有冒烟都会先炸在这里
        self.assertEqual(houtai_hexin.ALGO_LUJING.name, 'algo')
        self.assertTrue(houtai_hexin.ALGO_LUJING.exists())

    def test_mokuai_laizi_algo(self):
        """import 到的必须是 algo 原件（按 __file__ 判定，不是任何副本）。"""
        # rolling_budget 的来源文件必须落在 开发分支_1.0.5 内
        import rolling_budget
        self.assertIn('开发分支_1.0.5', str(rolling_budget.__file__).replace('\\', '/'))


class AlgoMaoyanTestCase(unittest.TestCase):
    """各关键模块的一次最小数值冒烟（期望值按 algo 源码手算写死）。

    只验"引导命中 + 基本数值正确"；详尽行为归 algo/tests 的 275 个用例。
    """

    def test_rolling_budget_lianfa(self):
        """链法①：3 期预算各 10000 分，1 期实际 11000，增长 100 基点。"""
        from rolling_budget import GunDongShezhi, QijianJine, gengxin_gundong_yusuan
        # 届满替换 + 剩余期接力：2 月起于自身年初数，3 月接上一期滚动值
        jieguo = gengxin_gundong_yusuan(
            [QijianJine(f'2025-{i:02d}', 10000) for i in (1, 2, 3)],
            [QijianJine('2025-01', 11000)],
            GunDongShezhi('月度', 100))
        # 2 月 = 10000×1.01 = 10100；3 月 = 10100×1.01 = 10201（half-up 逐期接力）
        self.assertEqual([t.shuzhi_fen for t in jieguo.qijian_mingxi],
                         [11000, 10100, 10201])
        # 合计 31301 / 差额 1301（11000 替换掉 10000 再叠两次 1% 接力）
        self.assertEqual((jieguo.gundong_zonge_fen, jieguo.chae_fen), (31301, 1301))

    def test_variance_moren_dang(self):
        """默认档位：2000 基点 ≥ 黄阈 1500 且 < 红阈 3000 → 黄。"""
        from variance import ChayiShuru, jisuan_chayi
        # 成本类正差 2000 分 / 基准 10000 分 = 2000 基点：F-A 记号 A（超支）
        jieguo = jisuan_chayi([ChayiShuru(
            qijian='2025-01', kemu='材料', fangxiang='成本类',
            chushi_fen=10000, gundong_fen=None, shiji_fen=12000)])
        xiang = jieguo.xiang[0]
        self.assertEqual((xiang.chae_fen, xiang.chalv_bps, xiang.fa, xiang.yujing),
                         (2000, 2000, 'A', '黄'))

    def test_chaifen_hengdengshi(self):
        """拆分恒等式：原标准 50000 / 修订 49500 / 实际 52000（手算三总量）。"""
        from planning_operational import ChaifenShuru, chai_fen
        # 产量 100 × 标准用量 10 × 标准单价 50 = 原标准 50000 分
        jieguo = chai_fen(ChaifenShuru(
            biaozhun_danjia_fen=50, biaozhun_yongliang=10,
            xiuding_danjia_fen=55, xiuding_yongliang=9,
            shiji_chanliang=100, shiji_yongliang=950, shiji_chengben_fen=52000))
        # 规划总 = 49500−50000 = −500；执行总 = 52000−49500 = +2500；两者和 = 原标准总 2000
        self.assertEqual((jieguo.guihua_zong_fen, jieguo.zhixing_zong_fen,
                          jieguo.yuandan_zong_fen), (-500, 2500, 2000))
        self.assertTrue(jieguo.hengdengshi_chengli)

    def test_loop_decision_qingxing1(self):
        """判定情形 1：差异率低于噪声门且无登记 → 不触发。"""
        from loop_decision import PanDuanShuru, panduan_huanlu
        # 100 基点 < 门限 2500 基点：纯噪声不触发、不需审批
        jieguo = panduan_huanlu(PanDuanShuru(chalv_bps=100), menjian_bps=2500)
        self.assertEqual((jieguo.qingxing, jieguo.panduan, jieguo.shenpi),
                         (1, '不触发', False))

    def test_building_blocks_yingshe(self):
        """默认关键词映射：材料价格 → 采购模块（先于成本的"材料"命中）。"""
        from building_blocks import yingshe_mokuai
        # 匹配顺序采购→成本→费用→收入：'材料价格' 必须被采购先咬走
        self.assertEqual(yingshe_mokuai('材料价格差异'), '采购模块')
        self.assertEqual(yingshe_mokuai('直接材料成本'), '成本模块')
        # 无任何关键词命中 → None（未归属，交人工补映射）
        self.assertIsNone(yingshe_mokuai(' miscellaneous '))

    def test_bsc_jiaocai_li(self):
        """BSC 教材例题：75/80/70/60 × 40/30/20/10 → 总分 74 合格（algo 测试基准）。"""
        from bsc import BscShuru, jisuan_bsc
        # 四维达成率 7500/8000/7000/6000 基点，默认权重 → 总分 (40×75+30×80+20×70+10×60)/100
        jieguo = jisuan_bsc(BscShuru(caijing_bps=7500, kehu_bps=8000,
                                     neibu_bps=7000, xuexi_bps=6000))
        self.assertEqual((jieguo.zongfen, jieguo.dengji), (74, '合格'))

    def test_kpi_jiegou(self):
        """KPI：15 项指标键齐全；缺数纪律 → None（不臆造）。"""
        from kpi import KpiShuru, jisuan_kpi
        # 全缺数输入：结果字段 15 个、比率类全 None（缺数交人工）
        jieguo = jisuan_kpi(KpiShuru())  # 全缺数
        self.assertIsNone(jieguo.yingshou_dachenglv_bps)
        self.assertEqual(len(jieguo.__dataclass_fields__), 15)

    def test_zhenggai_hong_hang(self):
        """整改：红色预警行 → 强制整改、高优先级。"""
        from variance import ChayiShuru, jisuan_chayi
        from zhenggai import ZhenggaiShuru, shengcheng_zhenggai
        # 5000 基点差异（默认红阈 3000）→ 红行 → 一条高优先级强制整改
        chayi = jisuan_chayi([ChayiShuru(
            qijian='2025-01', kemu='材料', fangxiang='成本类',
            chushi_fen=10000, gundong_fen=None, shiji_fen=15000)])  # 5000 基点 → 红
        jieguo = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi))
        self.assertEqual(jieguo.qingdan[0].leixing, '强制整改')
        self.assertEqual((jieguo.gao_shu, jieguo.zong_shu), (1, 1))

    def test_zuzhi_shibie_duoji(self):
        """组织识别：多级名称取末段为部门（algo/zuzhi 的 doctest 基准）。"""
        from zuzhi import shibie_zuzhi
        # 三级名称：末段为部门、其余拼回机构（algo 模块头知识点 1 同例）
        self.assertEqual(shibie_zuzhi('衡策中学/二级学院/会计学院'),
                         ('衡策中学/二级学院', '会计学院'))


if __name__ == '__main__':
    unittest.main()
