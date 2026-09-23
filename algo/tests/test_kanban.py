# -*- coding: utf-8 -*-
"""kanban（看板数据接口）单元测试 —— 纯组装层：只验透传与形态，不重算。

设计原则：
    1. 组装契约：五区输出与上游模块结果逐字段透传（数值以本源模块为准）；
    2. 容错契约：上游缺省（None）→ 对应块为空结构，绝不抛错；
    3. 派生结构：热力图矩阵（期间×科目）维度与取值逐一锁定。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块与上游构造：discover -t . 运行时 algo 根目录在 sys.path 上
from bsc import BscShuru, jisuan_bsc  # noqa: E402
from building_blocks import JimuHang, chai_jimu, cong_chayi_xiang  # noqa: E402
from kanban import KanbanShuru, shengcheng_kanban  # noqa: E402
from kpi import KpiShuru, jisuan_kpi  # noqa: E402
from loop_decision import PanDuanShuru, panduan_huanlu  # noqa: E402
from rolling_budget import GunDongShezhi, QijianJine, gengxin_gundong_yusuan  # noqa: E402
from suyuan import SuyuanHang, jisuan_suyuan  # noqa: E402
from variance import ChayiShuru, YujingDang, jisuan_chayi  # noqa: E402
from zhenggai import ZhenggaiShuru, shengcheng_zhenggai  # noqa: E402
# 上游九个模块在此全部引入——看板测试即端到端组装的「半程演练」


def chayi_lianghang() -> object:
    """两行差异：材料价格（红）+ 办公费（黄）——覆盖两档预警与两科目。"""
    # 材料价格差异率 10%（红）、办公费 5%（黄）——自定义档位（默认已改 15%/30%）
    return jisuan_chayi([
        ChayiShuru('2026-Q1', '材料价格差异', '成本类',
                   10_000_000, 10_000_000, 11_000_000),
        ChayiShuru('2026-Q2', '办公费', '成本类',
                   10_000_000, 10_000_000, 10_500_000),
    ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))


class TestDuibiYuYujing(unittest.TestCase):
    """① 对比表 + ② 预警汇总：variance 全字段透传。"""

    # 契约：duibi_biao 每行 11 键 = ChayiXiang 全字段（UI 层翻译成中文列名）

    def test_duibi_touzhuan(self) -> None:
        """两行对比表逐字段透传（键 = ChayiXiang 字段名）。"""
        # 组装层不重算：对比表数值以 variance 为准，这里只验透传不失真
        jg = shengcheng_kanban(KanbanShuru(chayi=chayi_lianghang()))
        self.assertEqual(len(jg.duibi_biao), 2)
        # 第一行：材料价格差异 红（差异率 1000 基点）
        self.assertEqual(jg.duibi_biao[0]['kemu'], '材料价格差异')
        self.assertEqual(jg.duibi_biao[0]['chae_fen'], 1_000_000)
        self.assertEqual(jg.duibi_biao[0]['yujing'], '红')
        self.assertEqual(jg.duibi_biao[0]['fa'], 'A')

    def test_yujing_huizong(self) -> None:
        """四档计数：红 1、黄 1、无 0、无法定级 0。"""
        # 计数来自 variance.ChayiJieguo 的四档字段——直接透传
        jg = shengcheng_kanban(KanbanShuru(chayi=chayi_lianghang()))
        self.assertEqual(jg.yujing_huizong,
                         {'hong_shu': 1, 'huang_shu': 1, 'wu_shu': 0, 'wufa_shu': 0})


class TestRelitu(unittest.TestCase):
    """② 热力图：期间 × 科目 差异率矩阵（派生结构）。"""

    # 矩阵取值 = chalv_bps（缺组合 None）——热力着色由 UI 层按预警档完成

    def test_juzhen_weidu(self) -> None:
        """两期间 × 两科目 → 2×2 矩阵，取值与行对应。"""
        # 热力图派生结构：期间/科目排序去重，缺组合填 None（显示「无」）
        jg = shengcheng_kanban(KanbanShuru(chayi=chayi_lianghang()))
        self.assertEqual(jg.relitu['qijian_lie'], ['2026-Q1', '2026-Q2'])
        self.assertEqual(jg.relitu['kemu_lie'], ['办公费', '材料价格差异'])
        # 矩阵：Q1 行 = [None(办公费无此期), 1000]；Q2 行 = [500, None]
        self.assertEqual(jg.relitu['juzhen'], [[None, 1000], [500, None]])


class TestBingtu(unittest.TestCase):
    """③ 饼图：积木四模块 + 未归属透传。"""

    # 饼图数据 = 四模块占比（合计恒 10000 基点的不变量在上游保证）

    def test_bingtu_touzhuan(self) -> None:
        """四模块占比/高亮/净合计逐字段透传。"""
        # 材料价格→采购、办公费→费用；净合计 = 1,000,000+500,000 分
        chayi = chayi_lianghang()
        jimu = chai_jimu([cong_chayi_xiang(x) for x in chayi.xiang])
        jg = shengcheng_kanban(KanbanShuru(chayi=chayi, jimu=jimu))
        # 材料价格→采购、办公费→费用：净合计 1,500,000 分；高亮=采购
        self.assertEqual(len(jg.bingtu['mokuai_lie']), 4)
        self.assertEqual(jg.bingtu['mokuai_lie'][3]['mokuai'], '采购模块')
        self.assertEqual(jg.bingtu['mokuai_lie'][3]['chae_fen'], 1_000_000)
        self.assertEqual(jg.bingtu['hexin_mokuai'], '采购模块')
        self.assertEqual(jg.bingtu['jing_heji_fen'], 1_500_000)


class TestZhexian(unittest.TestCase):
    """③ 折线：滚动预算逐期透传。"""

    # 折线序列 = 滚动预算逐期（届满=实际、剩余=重算），UI 直接连线

    def test_zhexian_touzhuan(self) -> None:
        """两期滚动：届满替换 + 剩余重算的逐期数据透传。"""
        # 增长 100 基点：剩余期 10,000,000×1.01 = 10,100,000 分
        gundong = gengxin_gundong_yusuan(
            [QijianJine('2026-01', 10_000_000), QijianJine('2026-02', 10_000_000)],
            [QijianJine('2026-01', 10_500_000)],
            GunDongShezhi(zhouqi='月度', zengzhanglv_jidian=100, hangye_xiuzheng='B'),
        )
        jg = shengcheng_kanban(KanbanShuru(gundong=gundong))
        self.assertEqual(len(jg.zhexian), 2)
        # 1 月届满 = 实际 10,500,000；2 月剩余 = 10,000,000×1.01 = 10,100,000
        self.assertEqual(jg.zhexian[0]['zhuangtai'], '已届满')
        self.assertEqual(jg.zhexian[0]['shuzhi_fen'], 10_500_000)
        self.assertEqual(jg.zhexian[1]['zhuangtai'], '剩余期')
        self.assertEqual(jg.zhexian[1]['shuzhi_fen'], 10_100_000)


class TestBscKpiSuyuanPanduan(unittest.TestCase):
    """③④块：BSC/KPI/溯源/判定 逐字段透传。"""

    # 各块独立透传：任一上游缺省都不影响其他块（容错契约）

    def test_bsc_touzhuan(self) -> None:
        """BSC 四维得分/总分/等级透传（74 分合格例题）。"""
        # 74 分 = 定稿 §6 例题：40/30/20/10 权重 × 75/80/70/60 得分
        bsc = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000))
        jg = shengcheng_kanban(KanbanShuru(bsc=bsc))
        self.assertEqual(jg.bsc_block['zongfen'], 74)
        self.assertEqual(jg.bsc_block['dengji'], '合格')
        self.assertEqual(jg.bsc_block['quanzhong'], (40, 30, 20, 10))

    def test_kpi_shiwuxiang(self) -> None:
        """KPI 15 项：中文名顺序 = 定稿 §8 清单；缺数 None 透传。"""
        # 15 项顺序即 KPI_MING 常量顺序（财务 9 + 非财务 6）
        kpi = jisuan_kpi(KpiShuru(shouru_shiji_fen=15_000_000,
                                  shouru_yusuan_fen=14_000_000))
        jg = shengcheng_kanban(KanbanShuru(kpi=kpi))
        self.assertEqual(len(jg.kpi_block), 15)
        self.assertEqual(jg.kpi_block[0]['mingcheng'], '营收达成率')
        self.assertEqual(jg.kpi_block[0]['zhi'], 10714)
        self.assertIsNone(jg.kpi_block[3]['zhi'])   # 毛利率缺数 → None

    def test_suyuan_touzhuan(self) -> None:
        """溯源逐项影响/TOP3/分母透传。"""
        # 交付周期 5→8 天、基准 5 天：影响率 +60% = 6000 基点（负向作用）
        suyuan = jisuan_suyuan([SuyuanHang('交付周期', 5, 8, 5)])
        jg = shengcheng_kanban(KanbanShuru(suyuan=suyuan))
        self.assertEqual(jg.suyuan_block['xiang'][0]['yingxianglv_bps'], 6000)
        self.assertEqual(jg.suyuan_block['fuxiang_top3'], ['交付周期'])

    def test_panduan_touzhuan(self) -> None:
        """判定结果透传（混合纠错模式 + 审批标志）。"""
        # 规划 9% 与执行 1% 双显著 + 已登记 → 判定表情形 4 = 混合纠错模式（非双环）
        panduan = panduan_huanlu(PanDuanShuru(
            chalv_bps=1000, guihua_zong_fen=900_000, zhixing_zong_fen=100_000,
            yuandan_cbf_fen=10_000_000, jie_gou_biangeng=True, bianma='供应商涨价'),
            menjian_bps=100, xianzhu_bps=100)
        jg = shengcheng_kanban(KanbanShuru(panduan=panduan))
        self.assertEqual(jg.panduan_block['panduan'], '混合纠错模式')
        self.assertTrue(jg.panduan_block['shenpi'])


class TestZhenggaiKuai(unittest.TestCase):
    """⑤ 整改闭环区：清单与计数透传。"""

    # 整改清单是 AI 层文案起草的输入——透传完整性即验收标准

    def test_zhenggai_touzhuan(self) -> None:
        """整改清单逐项 + 优先级/进度计数透传。"""
        # 红 1 条强制整改 + 黄 1 条关注整改 → 高 1 中 1 共 2
        chayi = chayi_lianghang()
        zhenggai = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi))
        jg = shengcheng_kanban(KanbanShuru(chayi=chayi, zhenggai=zhenggai))
        self.assertEqual(len(jg.zhenggai_block['qingdan']), 2)
        self.assertEqual(jg.zhenggai_block['qingdan'][0]['leixing'], '强制整改')
        self.assertEqual(jg.zhenggai_block['gao_shu'], 1)
        self.assertEqual(jg.zhenggai_block['zong_shu'], 2)


class TestRongcuo(unittest.TestCase):
    """容错契约：上游缺省 → 空结构，绝不抛错。"""

    # 空结构 = 合法输出：UI 显示「无」、AI 层跳过——端到端脚本不中断的前提

    def test_kong_shuru(self) -> None:
        """全部缺省：各区空结构（看板显示「无」的数据基础）。"""
        # 容错契约：端到端任何阶段缺料，看板数据都必须合法可序列化
        jg = shengcheng_kanban(KanbanShuru())
        self.assertEqual(jg.duibi_biao, [])
        self.assertEqual(jg.bingtu['mokuai_lie'], [])
        self.assertEqual(jg.zhexian, [])
        self.assertEqual(jg.relitu, {'qijian_lie': [], 'kemu_lie': [], 'juzhen': []})
        self.assertEqual(len(jg.kpi_block), 15)          # KPI 15 项全 None
        self.assertTrue(all(x['zhi'] is None for x in jg.kpi_block))
        self.assertEqual(jg.zhenggai_block['qingdan'], [])

    def test_quedingxing(self) -> None:
        """确定性：同输入两次调用结果完全一致（dataclass 等值）。"""
        # 组装层也须纯函数：顺序稳定是 UI/AI 消费的前提
        chayi = chayi_lianghang()
        jimu = chai_jimu([cong_chayi_xiang(x) for x in chayi.xiang])
        shuru = KanbanShuru(chayi=chayi, jimu=jimu)
        self.assertEqual(shengcheng_kanban(shuru), shengcheng_kanban(shuru))


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_kanban.py
    unittest.main()
