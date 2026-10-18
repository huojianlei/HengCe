# -*- coding: utf-8 -*-
"""组织单元汇总（yinqing.zuzhi_huizong）与批次总入口（houtai_hexin.analyze_subjects）
的单元测试 —— 期望值对照 engine.mjs L194-251 与 server.mjs L208-216 手工验算。

另含一组与 algo/zuzhi.juhe_bumen 的同口径互证：同一批数据两实现各算一遍，
部门行的差额/绝对偏差/有利不利分解/完成率必须一致（zuzhi.py 头注 L9-12 声明的
"同一组手算样例互相印证"在移植包里继续成立）。
"""

import unittest

# 被测对象：组织识别/批量汇总 + 批次总入口（后者从包入口引）
from yinqing import YinqingCuowu, fenxi, zuzhi_huizong, zuzhi_shibie
# 夹具：标准输入 dict（口径见 gongju.py 模块头）
from .gongju import biaozhun_shuru


def _jieguo(zhuti):
    """跑一份标准分析，只换主体名称（同数据不同部门的汇总形态最好核对）。"""
    # 标准夹具 + 指定主体名：主体名是组织识别的唯一输入
    shuru = biaozhun_shuru()
    shuru['metadata'] = {**shuru['metadata'], '主体名称': zhuti}
    return fenxi(shuru)


class ZuzhiShibieTestCase(unittest.TestCase):
    """zuzhi_shibie：主体名称识别（engine.mjs L182-188，算法委托 algo.shibie_zuzhi）。

    验算口径：四种写法各一发——两级、单级、全角斜杠与首尾空白、空名兜底。
    """

    def test_sige_xiezhi(self):
        """「机构/部门」→ 末段为部门；无分隔符自成单元；空名回落未命名。"""
        # 两级：末段为部门、前段为机构
        self.assertEqual(zuzhi_shibie('衡策中学/教务处'),
                         {'jigou': '衡策中学', 'bumen': '教务处'})
        # 单级：主体自身就是一个组织单元（机构与部门同名）
        self.assertEqual(zuzhi_shibie('后勤处'), {'jigou': '后勤处', 'bumen': '后勤处'})
        # 全角斜杠与首尾空白都要容忍（algo 实现已统一处理）
        self.assertEqual(zuzhi_shibie('  衡策中学 ／ 学生处  '),
                         {'jigou': '衡策中学', 'bumen': '学生处'})
        # 空名：回落固定兜底名，不抛错（名称合法性归导入层管）
        self.assertEqual(zuzhi_shibie(''),
                         {'jigou': '未命名机构', 'bumen': '未命名组织单元'})


class ZuzhiHuizongTestCase(unittest.TestCase):
    """zuzhi_huizong：批次 → 部门行/机构小计/排行/期间分组（engine.mjs L194-251）。

    手算基准（两部门同数据，见 tests/gongju.py）：
        每部门基准/实际各 20000 分、净差 0、绝对偏差 2000（+1000F/−1000A）；
        预警 2 红黄 0；整改 4 条全待 → 完成率 0 基点。
    """

    def setUp(self):
        """两个部门（同一机构、同期间）的标准分析结果。"""
        # 教务处/后勤处：同机构两部门，是最常见的批次形态
        self.jiaowu = _jieguo('测试公司/教务处')
        self.houqin = _jieguo('测试公司/后勤处')
        # 批次汇总一次，六个用例共用
        self.huizong = zuzhi_huizong([self.jiaowu, self.houqin])

    def test_bumen_xiang(self):
        """部门行：预算/实际 20000 分、净差 0、绝对偏差 2000、F/A 各 1000（手算）。"""
        # 两部门数据相同 → 部门行七项数值 + 预警计数逐项相同
        for hang in self.huizong['bumen_lie']:
            self.assertEqual((hang['budgetFen'], hang['actualFen'],
                              hang['deltaFen'], hang['jueduiChaFen'],
                              hang['youliFen'], hang['buliFen'], hang['direction'],
                              hang['yujingShu'], hang['hongShu'], hang['huangShu']),
                             (20000, 20000, 0, 2000, 1000, 1000, '持平', 2, 2, 0))
            # 完成率 = 0/4 → 0 基点（分母非零，正常整除）
            self.assertEqual(hang['wanchengBps'], 0)  # 0/4 → 0 基点
            # 四模块分解：只有收入模块有数（净 0 → 持平），其余三模块全 0
            shouru = hang['mokuai'][0]
            self.assertEqual((shouru['module'], shouru['budgetFen'],
                              shouru['actualFen'], shouru['deltaFen'],
                              shouru['direction']), ('收入模块', 20000, 20000, 0, '持平'))

    def test_heji_hengdeng(self):
        """合计恒等于各部门相加；机构唯一 → 机构名不回落"全部组织单元"。"""
        # 合计 = 两部门之和（40000/4000）；单机构批次直接用机构名
        heji = self.huizong['heji']
        self.assertEqual(heji['bumenShu'], 2)
        self.assertEqual((heji['budgetFen'], heji['jueduiChaFen']), (40000, 4000))
        self.assertEqual(self.huizong['jigou'], '测试公司')
        self.assertEqual(len(self.huizong['jigou_lie']), 1)

    def test_paihang_yu_qijian(self):
        """排行并列按部门名码点序断链（engine 为 localeCompare 'zh'，已登记 drift）；
        期间一致 → yizhi 为真。"""
        # 两部门绝对偏差并列 → 断链看名字：'后'(U+540E) < '教'(U+6559)
        self.assertEqual([x['bumen'] for x in self.huizong['paihang']],
                         ['后勤处', '教务处'])  # '后'(U+540E) < '教'(U+6559)
        # 各占一半：2000/4000 = 5000 基点
        self.assertEqual([x['zhanbiBps'] for x in self.huizong['paihang']], [5000, 5000])
        # 同周期同期间 → yizhi=True；期间组唯一且金额等于两部门之和
        self.assertTrue(self.huizong['yizhi'])
        self.assertEqual(self.huizong['qijian_lie'],
                         [{'cycle': '月度', 'period': '2025-02',
                           'bumenShu': 2, 'jueduiChaFen': 4000}])

    def test_yu_algo_juhe_bumen_huzheng(self):
        """与 algo/zuzhi.juhe_bumen 同口径互证：部门行五项核心数值一致。"""
        from zuzhi import BumenShuru, juhe_bumen
        # algo 侧输入：预汇总的（基准, 实际, 逐科目(差额,F/A), 预警数, 整改数, 完成数）
        shuru_lie = [BumenShuru('测试公司/教务处', 20000, 20000,
                                ((1000, 'F'), (-1000, 'A')), 2, 4, 0),
                     BumenShuru('测试公司/后勤处', 20000, 20000,
                                ((1000, 'F'), (-1000, 'A')), 2, 4, 0)]
        algo_jieguo = juhe_bumen(shuru_lie)
        # 同一批数据两实现各算一遍：五项核心数值必须一一对上
        by_bumen = {x['bumen']: x for x in self.huizong['bumen_lie']}
        for yuan in algo_jieguo.bumen_lie:
            hang = by_bumen[yuan.bumen]
            self.assertEqual((hang['deltaFen'], hang['jueduiChaFen'],
                              hang['youliFen'], hang['buliFen'], hang['direction'],
                              hang['wanchengBps']),
                             (yuan.cha_e_fen, yuan.juedui_cha_fen, yuan.youli_fen,
                              yuan.buli_fen, yuan.fangxiang, yuan.wancheng_bps))

    def test_kong_pici_jujue(self):
        """空批次拒绝（engine.mjs L195 文案逐字）。"""
        # 一份分析都没有 → 无从汇总
        with self.assertRaises(YinqingCuowu) as cm:
            zuzhi_huizong([])
        self.assertEqual(str(cm.exception),
                         '请先完成至少一个主体的分析，再汇总组织单元')


class AnalyzeSubjectsTestCase(unittest.TestCase):
    """houtai_hexin.analyze_subjects：批次总入口（server.mjs L208-216 同顺序）。

    验算口径：逐主体 fenxi → 批次 zuzhi_huizong；返回键与 server 响应同名。
    """
    def test_pici(self):
        """逐主体分析 + 组织汇总；返回键名与 server.mjs L215 同名同义。"""
        from houtai_hexin import analyze_subjects
        # 两份同构输入（主体名相同也允许——部门同名各自成行）
        pici = analyze_subjects([biaozhun_shuru(), biaozhun_shuru()])
        # 返回两键：逐主体结果列表 + 批次组织汇总
        self.assertEqual(set(pici), {'results', 'zuzhi'})
        self.assertEqual(len(pici['results']), 2)
        # 汇总吃到的就是这两份结果（部门数 2）
        self.assertEqual(pici['zuzhi']['heji']['bumenShu'], 2)

    def test_kong_pici(self):
        """空批次拒绝（server.mjs L209 文案）。"""
        from houtai_hexin import analyze_subjects
        # 批次入口的空列表门禁（server.mjs 同文案逐字）
        with self.assertRaises(YinqingCuowu) as cm:
            analyze_subjects([])
        self.assertEqual(str(cm.exception), '批次不能为空')


if __name__ == '__main__':
    unittest.main()
