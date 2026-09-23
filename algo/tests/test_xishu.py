# -*- coding: utf-8 -*-
"""xishu 判定系数输出模块的测试（11 用例，全部离线、期望值手算写死）。

口径依据：algo/xishu.py 模块头（TODO T-32：判定系数包 + 系数→提示词
映射表——算法层与分析层 M5 的唯一接缝；提示词=检索查询串，非分析文案）。

用例目录：
    TestHuizong   ×4  汇总：预警计数/红行排序/完成率 half-up/空输入
                      ——覆盖"只汇总不重算"承诺的两个例外（排序+完成率）
    TestTishi     ×4  提示词映射：红A超支/F红方法/判定/核心模块，去重与上限
                      ——映射表是 T-32 建议默认值，用例锁死当前口径
    TestQuanlian  ×3  全链一致性：与 variance/loop_decision/building_blocks
                      真实输出对接（鸭子类型契约）+ 确定性
夹具策略：上游结果一律用真实模块现算（与 zhenggai/kanban 测试同手法），
    期望值全部手工推演写死，禁止现算自证。
"""

from __future__ import annotations

import unittest

from building_blocks import JimuHang, chai_jimu
from loop_decision import PanDuanShuru, panduan_huanlu
from variance import ChayiShuru, jisuan_chayi, YujingDang
from xishu import XishuShuru, shengcheng_xishu


def _zao_chayi():
    """三行差异夹具：红A(3500bps) > 红F(3200bps) > 黄A(1800bps)——排序与映射的考题。

    手算：采购成本 1000万→1150万：+15% → 1500 基点 A 红；
    营收 500万→560万：+12% → 1200 基点 F 红（收入类超额=F 但波动红）；
    办公费 200万→212万：+6% → 600 基点 A 黄。
    【2026-09-03 默认阈值改 15%/30% 后】本夹具改传自定义档位（红 10%/黄 5%）
    ——数据不动，档位显式传入（顺带覆盖自定义接口）。
    """
    return jisuan_chayi([
        ChayiShuru('2026-Q1', '采购成本', '成本类',
                   chushi_fen=10_000_000, gundong_fen=None, shiji_fen=11_500_000),
        ChayiShuru('2026-Q1', '营收', '收入类',
                   chushi_fen=5_000_000, gundong_fen=None, shiji_fen=5_600_000),
        ChayiShuru('2026-Q1', '办公费', '成本类',
                   chushi_fen=2_000_000, gundong_fen=None, shiji_fen=2_120_000),
    ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))


class TestHuizong(unittest.TestCase):
    """汇总面：预警计数、红行排序、完成率、空输入。

    四条用例各守一个汇总契约：计数是透传、排序是本模块唯一重排、
    完成率是本模块唯一计算（half-up 整数基点）、空输入零臆造——
    后两条直接对应全项目"缺数交人工"的纪律。
    """

    def test_yujing_jishu_yu_paixu(self) -> None:
        """红/黄/无计数 + 红行按差异率降序（红F 也要排在红A 前面如果更大）。

        手算：本夹具红行 = 采购成本 1500(A)、营收 1200(F) → 降序即此序；
        黄 1 行（办公费），无 0 行。
        """
        bao = shengcheng_xishu(XishuShuru(chayi=_zao_chayi()))
        self.assertEqual((bao.hong_shu, bao.huang_shu, bao.wu_shu), (2, 1, 0))
        self.assertEqual(bao.hong_hang_lie,
                         (('2026-Q1', '采购成本', 1500, 'A'),
                          ('2026-Q1', '营收', 1200, 'F')))

    def test_wanchenglv_ban_shang(self) -> None:
        """整体完成率 = Σ实际 ÷ Σ基准（基点，half-up）。

        手算：Σ实际 = 1150+560+212 = 1922 万；Σ基准 = 1000+500+200 = 1700 万；
        1922/1700 = 113.06% → half-up 11306 基点（11305.88… 进位）。
        """
        bao = shengcheng_xishu(XishuShuru(chayi=_zao_chayi()))
        self.assertEqual(bao.wanchenglv_bps, 11306)

    def test_kong_shuru_kong_bao(self) -> None:
        """全空输入：计数为 0、完成率 None、结论 None、零提示词——不臆造。"""
        bao = shengcheng_xishu(XishuShuru())
        self.assertEqual((bao.hong_shu, bao.huang_shu, bao.wu_shu), (0, 0, 0))
        self.assertIsNone(bao.wanchenglv_bps)
        self.assertIsNone(bao.panduan_jielun)
        self.assertIsNone(bao.hexin_mokuai)
        self.assertEqual(len(bao.tishi_lie), 0)

    def test_ling_jizhun_jiao_rengong(self) -> None:
        """全部行的基准为 0：完成率无法定义 → None（与 variance 除零纪律一致）。

        零基准不是"完成率 0%"——无法定义和有定义是两回事，
        系数包必须诚实交 None 让分析层明示"缺数"。
        """
        chayi = jisuan_chayi([ChayiShuru('2026-Q1', '营收', '收入类',
                                         chushi_fen=0, gundong_fen=None, shiji_fen=1)])
        bao = shengcheng_xishu(XishuShuru(chayi=chayi))
        self.assertIsNone(bao.wanchenglv_bps)


class TestTishi(unittest.TestCase):
    """提示词映射：A/F 方向、判定结论、核心模块、去重与上限。

    映射是"系数 → 检索查询串"的合同：算法层只产出查询串、不产出分析
    ——查询串的措辞属于 T-32 建议默认值，M5 研究后可调，届时改用例。
    """

    def test_hong_A_chaozhi(self) -> None:
        """红A 行 → '{科目} 预算超支 管控措施'（按来源标签定位——优先序调整不脆）。"""
        bao = shengcheng_xishu(XishuShuru(chayi=_zao_chayi()))
        di_yi = next(t for t in bao.tishi_lie if t.laiyuan == '红预警-采购成本')
        self.assertEqual(di_yi.chaxun_ciyu, '采购成本 预算超支 管控措施')

    def test_hong_F_fangfa(self) -> None:
        """红F 行（超额但波动过大）→ '{科目} 预算差异 分析方法'。"""
        bao = shengcheng_xishu(XishuShuru(chayi=_zao_chayi()))
        ciyu_lie = [t.chaxun_ciyu for t in bao.tishi_lie]
        self.assertIn('营收 预算差异 分析方法', ciyu_lie)

    def test_panduan_yu_mokuai_yingshe(self) -> None:
        """双环/混合 → '预算调整 审批程序'；核心模块 → 模块领域词。

        夹具走真实 loop_decision + building_blocks（同 doctest 的
        混合纠错模式场景）——顺带验证鸭子类型对接无适配层。
        """
        chayi = jisuan_chayi([ChayiShuru('2026-Q1', '采购成本', '成本类',
                                         chushi_fen=10_000_000, gundong_fen=None,
                                         shiji_fen=11_500_000)])
        panduan = panduan_huanlu(PanDuanShuru(
            chalv_bps=1500, guihua_zong_fen=900_000, zhixing_zong_fen=250_000,
            yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
        jimu = chai_jimu([JimuHang('2026-Q1', '采购成本', 1_500_000, 'A', '红', 1500)])
        bao = shengcheng_xishu(XishuShuru(chayi=chayi, panduan=panduan, jimu=jimu))
        ciyu_lie = [t.chaxun_ciyu for t in bao.tishi_lie]
        self.assertIn('预算调整 审批程序', ciyu_lie)
        self.assertIn('采购成本控制 制度', ciyu_lie)
        self.assertEqual(bao.panduan_jielun, '混合纠错模式')
        self.assertTrue(bao.shenpi)

    def test_quchong_yu_shangxian(self) -> None:
        """同查询串去重；条数封顶 TISHI_SHANGXIAN=8。

        构造 6 个红行 + 双环 + 核心模块 = 8 条去重前有重复的空间——
        断言：无重复、总条数 ≤ 8。
        """
        hang_lie = [ChayiShuru(f'2026-Q{i}', f'科目{q}号', '成本类',
                               chushi_fen=1_000_000, gundong_fen=None,
                               shiji_fen=1_000_000 + (q + 1) * 100_000)
                    for i in (1, 2) for q in range(1, 4)]
        chayi = jisuan_chayi(hang_lie)             # 6 行全部红（11%~70%）
        panduan = panduan_huanlu(PanDuanShuru(chalv_bps=1500, jie_gou_biangeng=True),
                                 menjian_bps=100, xianzhu_bps=100)
        bao = shengcheng_xishu(XishuShuru(chayi=chayi, panduan=panduan))
        ciyu_lie = [t.chaxun_ciyu for t in bao.tishi_lie]
        self.assertEqual(len(ciyu_lie), len(set(ciyu_lie)))     # 无重复
        self.assertLessEqual(len(ciyu_lie), 8)                  # 封顶


class TestQuanlian(unittest.TestCase):
    """与上游真实输出的对接契约 + 确定性。

    三条用例证明：系数包对上游是【透传】不加工（整改计数/BSC 评分
    原样带出）、对调用方是【确定】的（同输入同输出）——
    这是"算法层零加工、分析层可信赖"的结构保证。
    """

    def test_zhenggai_jishu_touming(self) -> None:
        """整改计数透传：zhenggai 的高/中计数进系数包（透传，不重算）。"""
        from zhenggai import ZhenggaiShuru, shengcheng_zhenggai
        chayi = _zao_chayi()
        panduan = panduan_huanlu(PanDuanShuru(
            chalv_bps=1500, guihua_zong_fen=900_000, zhixing_zong_fen=250_000,
            yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True), menjian_bps=100, xianzhu_bps=100)
        zhenggai = shengcheng_zhenggai(ZhenggaiShuru(
            chayi=chayi, panduan=panduan,
            jimu=chai_jimu([JimuHang('2026-Q1', '采购成本', 1_500_000, 'A', '红', 1500)])))
        bao = shengcheng_xishu(XishuShuru(chayi=chayi, panduan=panduan, zhenggai=zhenggai))
        self.assertEqual(bao.zhenggai_gao_shu, zhenggai.gao_shu)   # 透传一致
        self.assertEqual(bao.zhenggai_zhong_shu, zhenggai.zhong_shu)

    def test_bsc_touming(self) -> None:
        """BSC 总分/等级透传：上游给什么系数包就带什么。"""
        from bsc import BscShuru, jisuan_bsc
        bsc = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000))
        bao = shengcheng_xishu(XishuShuru(bsc=bsc))
        self.assertEqual((bao.bsc_zongfen, bao.bsc_dengji), (74, '合格'))

    def test_quedingxing(self) -> None:
        """确定性：同输入两次生成，系数包逐字段一致（纯函数纪律）。

        asdict 全字段对比——不只挑几个字段，任何隐藏状态都会现形。
        """
        from dataclasses import asdict
        shuru = XishuShuru(chayi=_zao_chayi())
        self.assertEqual(asdict(shengcheng_xishu(shuru)),
                         asdict(shengcheng_xishu(shuru)))


if __name__ == '__main__':
    unittest.main()
