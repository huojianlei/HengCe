# -*- coding: utf-8 -*-
"""ai_bianjie（AI 白名单 DTO 构造器）的单元测试 —— 对照 ai-boundary.mjs 逐行断言。

覆盖：权限门两分支（L19/L37）、操作白名单（L20）、前置门禁（L21）、
差异行 11 字段白名单化（L25-31）、模块汇总 F/A/N 映射（L32-33）、
组织汇总白名单与 200 行截断（L10-16）、问题截断 8000（L37）。

纪律：
    断言基于真实分析结果（yinqing.fenxi 产物），仅"过滤器行为"类
    用例用 SimpleNamespace 造最小差异行；期望值手工写死不回读实现。
"""

import unittest
from types import SimpleNamespace

# 被测对象：AI 边界层唯一入口 + 固定拒绝文案常量
from ai_bianjie import AI_JUJUE_WENAN, zhunbei_ai_qingqiu
# 夹具：标准输入 dict（口径见 gongju.py 模块头）
from .gongju import biaozhun_shuru


def _jieguo():
    """标准分析结果（红 2 行 / 变更未确认覆写 / 模块净 0）——见 tests/gongju.py。"""
    # 权限开启分支的断言都吃这一份真实分析结果（不造假数据）
    from yinqing import fenxi
    return fenxi(biaozhun_shuru())


def _jia_xiang(kemu='营业收入', qijian='2025-01', chae=1000, chalv=1000, fa='F'):
    """造一条最小差异行（SimpleNamespace 鸭子形态，等价 algo ChayiXiang 读取面）。"""
    # 仅供"过滤器行为"类用例：字段集与 ChayiXiang 的读取面一致即可
    return SimpleNamespace(kemu=kemu, qijian=qijian, chushi_fen=10000,
                           jizhun_fen=10000, shiji_fen=11000, chae_fen=chae,
                           chalv_bps=chalv, fa=fa, yujing='红')


class QuanxianMenTestCase(unittest.TestCase):
    """权限门（ai-boundary.mjs L19）：门未开连 result 都不解引用。

    验算口径：三分支各一发——拒绝、操作白名单、前置门禁。
    （拒绝分支的文案同时是 server.mjs 两处消费口的返回体，不许改字。）
    """

    def test_guanbi_guding_dajue(self):
        """data_access 非 True → 固定拒绝文案 + 权限关闭状态（result 传 None 也不炸）。"""
        # 门禁分支不触碰 result：None 也能安全返回四件套固定答复
        huida = zhunbei_ai_qingqiu(None, data_access=False)
        # 整个返回体逐字比对（文案与键集都不许漂移）
        self.assertEqual(huida, {'allowed': False,
                                 'response': {'answer': AI_JUJUE_WENAN,
                                              'status': '权限关闭',
                                              'references': [], 'failures': []}})

    def test_caozuo_baimingdan(self):
        """op 只认 chat/enrich（ai-boundary.mjs L20）。"""
        # 白名单外的操作一律拒绝（文案逐字）
        with self.assertRaises(ValueError) as cm:
            zhunbei_ai_qingqiu(_jieguo(), data_access=True, op='summary')
        self.assertEqual(str(cm.exception), '不支持的 AI 操作')

    def test_qianzhi_menjin(self):
        """没有已核验差异结果 → 拒绝构造请求（ai-boundary.mjs L21）。"""
        # 空结果（没有 variance.xiang）不允许进 AI——先本机分析再谈问答
        with self.assertRaises(ValueError) as cm:
            zhunbei_ai_qingqiu({}, data_access=True)
        self.assertEqual(str(cm.exception), '请先完成本次本机分析')


class BaohuaDTOTestCase(unittest.TestCase):
    """权限开启后的白名单 DTO（ai-boundary.mjs L24-37）。

    手算基准（tests/gongju.py 夹具）：两行差异、红档、模块净 0、变更未确认。
    """


    @classmethod
    def setUpClass(cls):
        """一次分析、两次断言共用。"""
        # 权限开启 + chat + 中文问题：后续断言都读这一份请求
        cls.qingqiu = zhunbei_ai_qingqiu(_jieguo(), data_access=True,
                                         op='chat', question='为什么超支？')

    def test_dingceng_xingtai(self):
        """顶层：allowed/op/dataAccess/units/period/question 逐项核对。"""
        # 顶层放行 + 请求四件套（op/dataAccess/data/question）
        self.assertTrue(self.qingqiu['allowed'])
        qing = self.qingqiu['request']
        # op 原样放行、dataAccess 恒 True、问题原文透传
        self.assertEqual((qing['op'], qing['dataAccess'], qing['question']),
                         ('chat', True, '为什么超支？'))
        # data 的协议版本/单位/期间：金额分、比率基点、分析期间 2025-02
        self.assertEqual(qing['data']['schemaVersion'], 'ai-results/1')
        self.assertEqual(qing['data']['units'], {'amount': '分', 'rate': '基点'})
        self.assertEqual(qing['data']['period'], '2025-02')

    def test_chayihang_baimingdan(self):
        """差异行 11 字段：金额分/基点原样、判定取覆写后的复核提示（七值白名单内）。"""
        # 两行差异都过境；第一行全字段逐项核对
        hang = self.qingqiu['request']['data']['variance']
        self.assertEqual(len(hang), 2)
        # 1 月行：初始/基准 10000、实际 11000、差 +1000 分、1000 基点、F、复核提示
        self.assertEqual(hang[0], {
            'subject': '营业收入', 'period': '2025-01', 'module': '收入模块',
            'budgetAmount': 10000, 'baselineAmount': 10000, 'actualAmount': 11000,
            'deltaAmount': 1000, 'varianceRate': 1000, 'direction': 'F',
            'decision': '复核提示', 'requiresApproval': False})

    def test_mokuai_fanxiang(self):
        """模块汇总：四模块全量透传（moduleSummary 本就含四模块，白名单放行），
        净 0 → 方向 N（engine.mjs 的 moduleSummary 方向是"持平"）。"""
        # 四行齐全 + 每行都是净 0 / N / 占比 0（夹具只有收入科目且净差为 0）
        # ——与差异行不同，模块块不带科目名，只送四行汇总数字
        mo = self.qingqiu['request']['data']['modules']
        self.assertEqual([x['module'] for x in mo],
                         ['收入模块', '成本模块', '费用模块', '采购模块'])
        self.assertTrue(all(x['deltaAmount'] == 0 and x['direction'] == 'N'
                            and x['shareRate'] == 0 for x in mo))

    def test_zuzhi_keyi_quebao(self):
        """没传组织汇总 → 不加 organization 键（字段集保持最小）。"""
        # 可选项缺省即省键：DTO 不送空壳结构（云端按缺键识别）
        self.assertNotIn('organization', self.qingqiu['request']['data'])

class ZuzhiDTOTestCase(unittest.TestCase):
    """组织汇总白名单（ai-boundary.mjs L10-16）。

    验算口径：200 行截断 + 七字段部门行 + 非汇总结构不加键。
    """

    def test_200_hang_jieduan(self):
        """部门截断 200 行、六字段白名单、名称限长 120。"""
        # 造 250 个部门的假汇总：部门行是唯一被截断的数组
        zuzhi = {'jigou': '某机构', 'heji': {'bumenShu': 250},
                 'bumen_lie': [{'bumen': f'部门{i}', 'jigou': '某机构',
                                'budgetFen': i, 'actualFen': i, 'deltaFen': 0,
                                'jueduiChaFen': i, 'yujingShu': 0} for i in range(250)]}
        qing = zhunbei_ai_qingqiu(_jieguo(), data_access=True, zuzhi=zuzhi)
        org = qing['request']['data']['organization']
        # 顶层：机构名 + 单元数（250 原样透传——截断只作用在部门行）
        self.assertEqual(org['name'], '某机构')
        self.assertEqual(org['unitCount'], 250)
        # 部门行恰好 200 条
        self.assertEqual(len(org['departments']), 200)
        # 首行七字段逐项核对（i=0 → 金额全 0）
        self.assertEqual(org['departments'][0], {
            'name': '部门0', 'institution': '某机构', 'budgetAmount': 0,
            'actualAmount': 0, 'deltaAmount': 0, 'absoluteDeltaAmount': 0,
            'alertCount': 0})

    def test_fei_huizong_xingtai(self):
        """非汇总结构（缺 bumen_lie）→ 不加键。"""
        # 只有机构名没有部门行 → 不是汇总，整个 organization 键不加
        qing = zhunbei_ai_qingqiu(_jieguo(), data_access=True, zuzhi={'jigou': 'x'})
        # 键缺失而非空壳（云端按缺键识别"本批次未做组织汇总"）
        self.assertNotIn('organization', qing['request']['data'])


class BiaoliangGuolvTestCase(unittest.TestCase):
    """标量过滤器与长科目名拒绝（ai-boundary.mjs L5-8、L26）。

    验算口径：非法值一律"清空/置 None/待确认"，只有科目名超长才报错。
    """

    def test_kemu_chaochang_jujue(self):
        """科目名超 180 字 → 报错文案逐字（ai-boundary.mjs L26）。"""
        # 181 字科目名：白名单化阶段唯一会抛错的输入
        chang = '超' * 181
        # 最小结果骨架：variance 一行 + 其余空（够走到科目名校验即可）
        jia = {'variance': SimpleNamespace(xiang=[_jia_xiang(kemu=chang)]),
               'subjects': [], 'decisions': [], 'moduleSummary': [],
               'meta': {'period': '2025-02'}}
        with self.assertRaises(ValueError) as cm:
            zhunbei_ai_qingqiu(jia, data_access=True)
        self.assertEqual(str(cm.exception), '科目名称不符合模型结果契约')

    def test_biao_liang_qingxi(self):
        """期间非法 → 空串；金额浮点 → None；方向非 F/A/N → 空串；判定未知 → 待确认。"""
        # 一行五处非法各验一发：期间 2025-1 / 模块白名单外 / 方向 X / 金额浮点 / 无判定行
        jia = {'variance': SimpleNamespace(xiang=[SimpleNamespace(
            kemu='营业收入', qijian='2025-1', chushi_fen=10000.5, jizhun_fen=10000,
            shiji_fen=11000, chae_fen=1000, chalv_bps=1000, fa='X', yujing='红')]),
            'subjects': [{'kemu': '营业收入', 'module': '未知模块'}],
            'decisions': [], 'moduleSummary': [], 'meta': {'period': '2025-02'}}
        hang = zhunbei_ai_qingqiu(jia, data_access=True)['request']['data']['variance'][0]
        # 五个字段各自的"清空/置 None/待确认"降级形态
        self.assertEqual((hang['period'], hang['module'], hang['direction'],
                          hang['budgetAmount'], hang['decision']),
                         ('', '', '', None, '待确认'))

    def test_wenti_jieduan(self):
        """问题超 8000 字截断（ai-boundary.mjs L37）；非字符串归空串。"""
        # 9000 字 → 截 8000（长度上限，非拒绝）
        qing = zhunbei_ai_qingqiu(_jieguo(), data_access=True,
                                  question='问' * 9000)
        self.assertEqual(len(qing['request']['question']), 8000)
        # 非字符串（数字等）→ 空串（TS typeof 守卫的同义）
        qing = zhunbei_ai_qingqiu(_jieguo(), data_access=True, question=123)
        self.assertEqual(qing['request']['question'], '')


if __name__ == '__main__':
    unittest.main()
