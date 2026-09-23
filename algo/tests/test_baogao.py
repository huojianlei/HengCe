# -*- coding: utf-8 -*-
"""baogao（报告排版）单元测试 —— 期望值全部手工验算写死。

设计原则：
    1. 结构回归：八单元各一节一表（"一个分析项目对应一张数据表"）+ 三个附表；
    2. 显示回归：金额 = 元（两位小数千分位）、比率 = 百分比、周转率 = 次、
       布尔 = 是/否、缺数 = "—"——全部锁定；
    3. 容错回归：上游缺省 → "（缺料）"占位，绝不抛错。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest

# 被测模块与上游构造：discover -t . 运行时 algo 根目录在 sys.path 上
from baogao import BgShuru, shengcheng_baogao_md  # noqa: E402
from bsc import BscShuru, jisuan_bsc  # noqa: E402
from building_blocks import chai_jimu, cong_chayi_xiang  # noqa: E402
from data_ingest import daoru_csv  # noqa: E402
from kanban import KanbanShuru, shengcheng_kanban  # noqa: E402
from kpi import KpiShuru, jisuan_kpi  # noqa: E402
from loop_decision import PanDuanShuru, panduan_huanlu  # noqa: E402
from planning_operational import ChaifenShuru, chai_fen  # noqa: E402
from rolling_budget import GunDongShezhi, QijianJine, gengxin_gundong_yusuan  # noqa: E402
from suyuan import SuyuanHang, jisuan_suyuan  # noqa: E402
from variance import ChayiShuru, YujingDang, jisuan_chayi  # noqa: E402
from zhenggai import ZhenggaiShuru, shengcheng_zhenggai  # noqa: E402


def yanshi_ruku() -> object:
    """演示录入：营收预算/实际两行（数据录入节的数据源）。"""
    # 8 列表头与 data_ingest 规范一致——报告表数据即录入层原样
    wenben = (
        '数据类别,统计周期,数据科目,数值,单位,数据来源,更新时间,备注\n'
        '预算基础,2026-Q1,营收,220000.00,元,预算表V3,2026-01-15,年初定稿\n'
        '实时经营,2026-Q1,营收,210000.00,元,ERP导出,2026-04-02,Q1实际\n'
    )
    return daoru_csv(wenben)


def quanlian_shuru() -> BgShuru:
    """构造八单元全链路上游（数字与端到端演示同源，可交叉核对）。"""
    # 本函数即「八单元串联」的测试化版本——与 examples/quanliucheng.py
    # 共用同一套演示数字，报告值与锚点两处互证
    ruku = yanshi_ruku()
    # 滚动：营收两期（Q1 届满、Q2 口径 A 重算——企业 1% vs 行业 0.5% 差值
    # 恰达 50 基点阈值，边界即启用）
    gundong = gengxin_gundong_yusuan(
        [QijianJine('2026-Q1', 22_000_000), QijianJine('2026-Q2', 22_000_000)],
        [QijianJine('2026-Q1', 21_000_000)],
        GunDongShezhi(zhouqi='季度', zengzhanglv_jidian=100,
                      hangye_xiuzheng='A', hangye_zengzhanglv_jidian=50,
                      hangye_yuzhi_jidian=50),
    )
    # 差异：期间费用红预警一行（2,000,000 → 2,200,000 分，差异率 10%）
    # 自定义档位 红≥10%（默认已改 15%/30%——保持本链"红预警"演示意图）
    chayi = jisuan_chayi([
        ChayiShuru('2026-Q1', '期间费用', '成本类',
                   2_000_000, None, 2_200_000),
    ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
    # 拆分：Holmes 例题
    chaifen = chai_fen(ChaifenShuru(400, 7, 380, 8, 1400, 11000, 4_150_000))
    # 判定：规划+执行双显著+登记 → 混合纠错模式
    panduan = panduan_huanlu(PanDuanShuru(
        chalv_bps=1000, guihua_zong_fen=336_000, zhixing_zong_fen=-106_000,
        yuandan_cbf_fen=3_920_000, jie_gou_biangeng=True, bianma='供应商涨价'),
        menjian_bps=100, xianzhu_bps=100)
    # 积木：费用行 → 费用模块
    jimu = chai_jimu([cong_chayi_xiang(chayi.xiang[0])])
    bsc = jisuan_bsc(BscShuru(7500, 8000, 7000, 6000))
    kpi = jisuan_kpi(KpiShuru(
        shouru_shiji_fen=21_000_000, shouru_yusuan_fen=22_000_000,
        maoli_fen=10_500_000, jingshui_fen=6_300_000, pbit_fen=8_400_000,
        ziben_zhanyong_fen=80_000_000,
        liudong_zichan_qichu_fen=30_000_000, liudong_zichan_qimo_fen=35_000_000,
        liudong_fuzhai_qichu_fen=10_000_000, liudong_fuzhai_qimo_fen=12_000_000,
        feiyong_shiji_fen=2_200_000, feiyong_yusuan_fen=2_000_000,
        caigou_benqi_fen=8_500_000, caigou_shangqi_fen=8_000_000,
        shiji_chanchu=850, qianzai_channeng=1000,
        dingdan_zongshu=200, lvyue_dingdan_shu=190,
        jiaofu_zhouqi_tian_shu=7, manyi_keshu=180, shoufang_keshu=200,
        jihua_yewu_liang=1000, wancheng_yewu_liang=750, yichang_shijian_shu=3,
    ))
    suyuan = jisuan_suyuan([
        SuyuanHang('采购成本变动率', 8_000_000, 8_500_000, 8_000_000),
        SuyuanHang('交付周期', 6, 7, 6),
    ])
    zhenggai = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi, jimu=jimu, panduan=panduan))
    kanban = shengcheng_kanban(KanbanShuru(
        chayi=chayi, gundong=gundong, jimu=jimu, bsc=bsc, kpi=kpi,
        suyuan=suyuan, panduan=panduan, zhenggai=zhenggai))
    return BgShuru(ruku=ruku, gundong=gundong, chayi=chayi, chaifen=chaifen,
                   panduan=panduan, jimu=jimu, bsc=bsc, kpi=kpi,
                   suyuan=suyuan, zhenggai=zhenggai, kanban=kanban)


class TestJiegou(unittest.TestCase):
    """结构回归：八单元 + 三附表各一节，一个分析项目一张表。"""

    # 「一个分析项目对应一张数据表」= 每节恰一个主表（明细小节除外）

    def test_badanyuan_jie_cunzai(self) -> None:
        """八个单元节标题与三个附表标题全部出现。"""
        # 结构契约：节顺序 = 方案 B 步骤顺序（1 录入 … 8 溯源 + 三附表）
        md = shengcheng_baogao_md(quanlian_shuru())
        biaoti = ['总览 · 三重对比汇总',
                  '单元 1 · 数据录入', '单元 2 · 滚动预算', '单元 3 · 差异计算',
                  '单元 4 · 规划/执行拆分', '单元 5 · 单双环判定',
                  '单元 6 · 积木拆解', '单元 7 · 平衡计分卡', '单元 8 · 变更溯源',
                  '附表 A · KPI 指标库', '附表 B · 整改清单', '附表 C · 预警汇总']
        for t in biaoti:
            with self.subTest(t=t):
                self.assertIn(t, md)

    def test_mei_danyuan_you_biao(self) -> None:
        """每节至少一张表（Markdown 分隔行 '---' 计数 ≥ 表数量）。"""
        # 分隔行 '| ---' 即表头下的那行——每张表恰一个；
        # 全链路下含总览/单元1 双表/单元6 双表/C.1 定位 → 计数显著大于 11
        md = shengcheng_baogao_md(quanlian_shuru())
        # 11 节：每节至少 1 张表 → 分隔行 '| ---' 出现 ≥ 11 次
        self.assertGreaterEqual(md.count('| ---'), 11)


class TestXianshi(unittest.TestCase):
    """显示回归：金额/比率/周转率/布尔/缺数格式逐项锁定。"""

    def test_jine_xianshi(self) -> None:
        """金额显示：210,000.00 元 + 千分位；负号前置 -1,060.00。"""
        # 显示层整数实现：分→元 divmod + 千分位格式符，无浮点参与
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('210,000.00', md)          # 实际收入
        self.assertIn('220,000.00', md)          # 预算收入
        self.assertIn('-1,060.00', md)           # 执行总差异（负号前置）

    def test_bilv_xianshi(self) -> None:
        """比率显示：10.00%（差异率）、+6.25%（影响率带符号）、50.00%（占比）。"""
        # 带符号只用于影响率列——数值上升/下降的语义显式化
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('10.00%', md)              # 差异率 1000 基点
        self.assertIn('+6.25%', md)              # 采购影响率 +625 基点
        self.assertIn('100.00%', md)             # 积木费用模块独占占比

    def test_zhouzhuanlv_xianshi(self) -> None:
        """周转率显示：0.2625 次（资产）、0.9767 次（资金）——去尾零。"""
        md = shengcheng_baogao_md(quanlian_shuru())
        # 手算：资产 = 210,000/800,000 = 0.2625 次；资金 = 210,000/215,000 = 0.9767 次
        self.assertIn('| 资产周转率 | 0.2625 次 |', md)
        self.assertIn('| 资金周转率 | 0.9767 次 |', md)

    def test_buer_xianshi(self) -> None:
        """布尔显示：审批标志 = 是；恒等式成立 = 是。"""
        # 布尔统一是/否（None → "—"）——审计报告不允许 True/False 混入
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('| 需人工审批 | 是 |', md)
        self.assertIn('| 恒等式成立（规划 + 执行 = 原标准总） | 是 |', md)

    def test_queshu_xianshi(self) -> None:
        """缺数显示：缺料字段输出 "—"（占位非空串）。"""
        # 缺数纪律的展示出口：宁显 "—" 不填空串/零——审计可查
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('—', md)


class TestDanjiZhi(unittest.TestCase):
    """关键数值回归：各单元核心数字与上游输出一致（不重算、不失真）。"""

    # 排版层唯一承诺：数值原样呈现——本组测试即该承诺的回归锁

    def test_gundong_shuzhi(self) -> None:
        """滚动表：两期合计 433,311.00、滚动差异 -6,689.00。"""
        md = shengcheng_baogao_md(quanlian_shuru())
        # 手算：Q1 届满 210,000 + Q2 220,000×1.01×1.005 = 223,311 → 合计 433,311；
        # 差异 = 433,311 − 440,000 = -6,689（预算下调，负号前置显示）
        self.assertIn('| 年度合计 | — | 440,000.00 | 433,311.00 |', md)
        self.assertIn('-6,689.00', md)

    def test_chayi_shuzhi(self) -> None:
        """差异表：差额 2,000.00、F/A = A、预警 = 红。"""
        # 期间费用 2,000,000 分 → 2,000.00 元；差异率 10% → 红档
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('2,000.00', md)
        self.assertIn('| A | 红 |', md)

    def test_panding_shuzhi(self) -> None:
        """判定表：判定 = 混合纠错模式、情形 = 4、门检基点 = 100。"""
        # 依据明细（yiju 快照）逐条入表——答辩溯源可直接引用本表
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('| 判定 | 混合纠错模式 |', md)
        self.assertIn('| 情形 | 4 |', md)
        self.assertIn('| 门检基点 | 100 |', md)

    def test_bsc_shuzhi(self) -> None:
        """BSC 表（T-29#7 四列含达成率）：总分 74、等级 合格、权重 40%。"""
        md = shengcheng_baogao_md(quanlian_shuru())
        # 达成率列 = 得分溯源（线性折算说明在节尾注记）
        self.assertIn('| 财务 | 75.00% | 75 | 40% |', md)
        self.assertIn('| 总分 | — | 74 | — |', md)
        self.assertIn('| 等级 | — | 合格 | — |', md)
        self.assertIn('维度得分 = KPI 达成率 × 100', md)

    def test_kpi_shuzhi(self) -> None:
        """KPI 表：营收达成率 95.45%、交付周期 7 天、异常事项 3 次。"""
        # 15 项按定稿清单顺序，三类单位分派显示（pct/ci/tian·ci_shu）
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('| 营收达成率 | 95.45% |', md)
        self.assertIn('| 交付周期 | 7 天 |', md)
        self.assertIn('| 异常事项数量 | 3 次 |', md)

    def test_zhenggai_shuzhi(self) -> None:
        """整改表：预算修订案 + 强制整改；合计行出现。"""
        # 混合纠错模式 → 预算修订案（审批=是）；红行 → 强制整改——两条各占一行
        md = shengcheng_baogao_md(quanlian_shuru())
        self.assertIn('预算修订案', md)
        self.assertIn('强制整改', md)
        self.assertIn('合计：', md)


class TestRongcuo(unittest.TestCase):
    """容错回归：上游缺省 → （缺料）占位，绝不抛错。"""

    def test_kong_shuru(self) -> None:
        """全部缺省：报告仍完整（抬头 + 总览/八单元/三附表 + 缺料占位）。"""
        # 12 个组装块（总览 + 8 单元 + 3 附表）各一个占位——结构完整性契约
        md = shengcheng_baogao_md(BgShuru())
        self.assertIn('数据计算测试报告', md)
        self.assertIn('（缺料）', md)
        self.assertEqual(md.count('（缺料）'), 12)   # 12 块全缺

    def test_quedingxing(self) -> None:
        """确定性：同输入两次排版完全一致。"""
        # 排版纯函数：行顺序稳定是报告可比对的前提
        shuru = quanlian_shuru()
        self.assertEqual(shengcheng_baogao_md(shuru), shengcheng_baogao_md(shuru))


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_baogao.py
    unittest.main()
