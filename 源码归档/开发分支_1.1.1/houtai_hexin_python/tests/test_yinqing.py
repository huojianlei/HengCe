# -*- coding: utf-8 -*-
"""yinqing（引擎编排层）的单元测试 —— 期望值全部对照 engine.mjs 手工验算写死。

覆盖面（对应 engine.mjs 段落）：
    zhengshu / daoru_biaoge / kemu_guilei 基础助手（L17-36）；
    fenxi 主链：滚动+差异+模块汇总+判定+整改+看板+系数（L42-179）；
    修订链式重算（L95-106）与 T-21 人工强制归成本（L57）；
    校验链全部中文报错逐字断言（L44-53、L65-68、L75-76、L82-83、L87、
    L112、L119、L134-137）；
    chongji 计数回算（L252-256）。

纪律（与 algo/tests 同约）：
    期望数字禁止从实现回读——全部按 engine.mjs 口径手工推演；
    报错文案逐字断言，任一侧改文案即红。
"""

import unittest

# 被测对象：编排层全部公开入口（助手 / 主链 / 计数回算）
from yinqing import (YinqingCuowu, chongji, daoru_biaoge, fenxi,
                     kemu_guilei, zhengshu)
# 夹具：标准 8 列表头 + 标准记录 + 标准输入（口径见 gongju.py 模块头）
from .gongju import BIAOTOU, biaozhun_jilu, biaozhun_shuru


class ZhushuTestCase(unittest.TestCase):
    """zhengshu：整数域校验（engine.mjs L17-20）。

    验算口径：
        报错文案的数字渲染对齐 JS 模板字面量——9e11 在两侧都显示 900000000000；
        布尔单独点名（Python 的 True 是 int 子类，JS 的 true 不是 number）。
    """

    def test_hefa_zhengshu(self):
        """合法整数原样放行（含负域与上界）。"""
        # 正常值：默认域与自定义负域各验一发
        self.assertEqual(zhengshu(5, '测试'), 5)
        self.assertEqual(zhengshu(-100, '测试', -10000, 10000), -100)

    def test_feifa_baoocuo(self):
        """浮点/布尔/越界一律拒绝，报错文案逐字对齐。"""
        # 六种脏值各断言一次：浮点 / 布尔 / 字符串 / None / 负越界 / 正越界
        for zhi in (1.5, True, '5', None, -1, 10 ** 12):
            with self.subTest(zhi=zhi), self.assertRaises(YinqingCuowu) as cm:
                zhengshu(zhi, '测试金额')
            # 文案逐字：label + 空格 + "必须为" + 域（JS 数字渲染同形）
            self.assertEqual(str(cm.exception), '测试金额 必须为 0 至 900000000000 的整数')


class DaoruBiaogeTestCase(unittest.TestCase):
    """daoru_biaoge：文本导入回退链（engine.mjs L21-30）。

    验算口径：
        第一级走 algo data_ingest（元两位小数 → 整数分，×100 换算）；
        第二级走 algo report_parse；两级都失败时文案 = 固定前缀 + 交回原因。
        （1.0.7 桌面链路里此口仅调试可达；主入口为 xlsx → excel_ingest。）
    """

    def test_biaozhun_csv_zhijie_daoru(self):
        """标准 8 列 CSV 直接导入成功（BOM 也会被剥掉）。"""
        # 带行首 BOM 的标准 CSV：剥 BOM → 清洗 → 100.00 元换算 10000 分
        jilu = daoru_biaoge('\ufeff' + BIAOTOU +
                            '\n预算基础,2025-01,营业收入,100.00,元,测试,2025-12-31,')
        self.assertEqual(len(jilu.yusuan), 1)
        self.assertEqual(jilu.yusuan[0].shuzhi, 10000)  # 元 → 分（两位小数换算）

    def test_laji_wenben_tuihui(self):
        """非表格文本两级都失败 → 整本退回（文案逐字对齐 engine.mjs L26）。"""
        # 纯说明文字：不是 8 列 CSV 也不像预算报告 → 前缀逐字命中即可（原因随解析器）
        with self.assertRaises(YinqingCuowu) as cm:
            daoru_biaoge('这不是任何表格，只是一段随手的说明文字。')
        self.assertTrue(str(cm.exception).startswith('无法识别表格，请在导入区核对或编辑标准 CSV。'))


class KemuGuileiTestCase(unittest.TestCase):
    """kemu_guilei：科目默认归类（engine.mjs L31-36）。

    验算口径：只看"元"单位的预算行；默认映射来自 algo building_blocks 关键词表
    （采购→成本→费用→收入，先命中先得）。
    """

    def test_shouru_kemu(self):
        """单位=元的预算行科目 → 默认关键词映射（营业收入 → 收入模块/收入类）。"""
        # 夹具预算 12 行全为"营业收入/元" → 去重后单科目，收入模块 + 收入类
        qingdan = kemu_guilei(biaozhun_jilu())
        self.assertEqual(qingdan, [{'kemu': '营业收入', 'module': '收入模块',
                                    'direction': '收入类'}])


class FenxiZhuLianTestCase(unittest.TestCase):
    """fenxi 主链（engine.mjs L42-179）——夹具口径见 tests/gongju.py 模块头。

    手算基准（增长率 0、届满 1-2 月、页面档位 黄500/红1000）：
        预算 12×10000 分；实际 1 月 11000 / 2 月 9000 分；
        两行差异率均 1000 基点 → 双双落红档；净差 0 → 模块持平、占比全 0。
    本类九个用例合起来覆盖一次完整分析的十八键结果面。
    """

    def setUp(self):
        """标准输入跑一次，多断言共用（增长 0、届满 1-2 月、红档 1000 基点）。"""
        # 每个用例独立重跑（隔离副作用），夹具构造见 gongju.py
        self.jieguo = fenxi(biaozhun_shuru())

    def test_jieguo_guge(self):
        """结果 DTO 键集与 engine.mjs L177-178 同构，单位声明分/基点。"""
        # 十九个顶层键一个不多一个不少；元数据单位声明固定"分/基点"
        zidian = {'schemaVersion', 'meta', 'config', 'records', 'subjects',
                  'rolling', 'variance', 'moduleSummary', 'splits', 'decisions',
                  'blocks', 'bsc', 'kpi', 'trace', 'correction', 'dashboard',
                  'factors', 'warnings', 'revisions'}
        self.assertEqual(set(self.jieguo), zidian)
        # 协议版本与单位声明（引擎 DTO 的固定头）
        self.assertEqual(self.jieguo['schemaVersion'], '1.0')
        self.assertEqual((self.jieguo['meta']['moneyUnit'],
                          self.jieguo['meta']['rateUnit']), ('分', '基点'))

    def test_meta_zuzhi_shibie(self):
        """meta：主体名称 → 机构/部门识别（engine.mjs L177 委托 zuzhi_shibie）。"""
        # 主体"测试公司/财务部" → 机构=测试公司、部门=财务部
        self.assertEqual(self.jieguo['meta']['organization'],
                         {'jigou': '测试公司', 'bumen': '财务部'})
        # 无 changeStatus 且无事件 → 缺省 unknown（变更未确认态）
        self.assertEqual(self.jieguo['meta']['changeStatus'], 'unknown')

    def test_gundong_lianfa(self):
        """滚动链法①：届满期替换实际，剩余期 0 增长率下保持原预算（手算）。"""
        # 逐期：1 月实际 11000、2 月实际 9000、3 月起重算（0 增长 → 原预算值）
        gundong = self.jieguo['rolling'][0]
        # 1 月实际 11000 分、2 月实际 9000 分、3-12 月各 10000 分 → 合计 120000
        self.assertEqual([t['shuzhi_fen'] for t in gundong['qijian_mingxi'][:3]],
                         [11000, 9000, 10000])
        # 初始与滚动总额都 120000 → 差额 0（0 增长率下的恒等）
        self.assertEqual((gundong['chushi_zonge_fen'], gundong['gundong_zonge_fen'],
                          gundong['chae_fen']), (120000, 120000, 0))
        # 来源标注：届满期"实际"、剩余期"重算"
        self.assertEqual(gundong['qijian_mingxi'][0]['laiyuan'], '实际')
        self.assertEqual(gundong['qijian_mingxi'][2]['laiyuan'], '重算')

    def test_chayi_yujing(self):
        """差异：±1000 分 / 基准 10000 分 = 1000 基点 → 红档（页面档位 1000）。"""
        # 两行差异：1 月正差 F（收入超额有利）、2 月负差 A（未达标不利）
        xiang = self.jieguo['variance'].xiang
        # （期间, 差额, 差率基点, F/A, 档位）五行全对上
        self.assertEqual([(x.qijian, x.chae_fen, x.chalv_bps, x.fa, x.yujing)
                          for x in xiang],
                         [('2025-01', 1000, 1000, 'F', '红'),
                          ('2025-02', -1000, 1000, 'A', '红')])
        # 红档计数 2（页面红阈 1000 基点恰好命中——边界即落入）
        self.assertEqual(self.jieguo['variance'].hong_shu, 2)

    def test_module_summary(self):
        """模块汇总：净差额 0 → 持平；分母 0 → 占比全 0（engine.mjs L122-129）。"""
        # 四模块行恒存在（无数据的模块也占位，净 0 / 占比 0）
        zong = self.jieguo['moduleSummary']
        self.assertEqual(len(zong), 4)
        # 收入模块吃下全部两行：净 0、持平、占比 0、基准=实际=20000、行数 2
        shouru = zong[0]
        self.assertEqual((shouru['module'], shouru['netDeltaFen'],
                          shouru['direction'], shouru['shareBps'],
                          shouru['budgetFen'], shouru['actualFen'], shouru['count']),
                         ('收入模块', 0, '持平', 0, 20000, 20000, 2))

    def test_bian_geng_wei_queren_fuxie(self):
        """变更未确认：判定统一覆写为情形 5 复核提示（engine.mjs L148-152）。"""
        # 每条决策：情形 5、复核提示、不审批、要求先确认变更
        for d in self.jieguo['decisions']:
            self.assertEqual((d['qingxing'], d['panduan'], d['shenpi'],
                              d['requiresChangeConfirmation']), (5, '复核提示', False, True))
            # 覆写后判定输入里的结构登记线索清成 None（如实呈现缺失）
            self.assertIsNone(d['input']['jie_gou_biangeng'])
        # 同步登记一条警告：环路判定暂待复核
        self.assertIn('经营变更尚未确认；缺失文件不代表本期无变更，环路判定暂待复核',
                      self.jieguo['warnings'])

    def test_zhenggai_qingdan(self):
        """整改：2 条红色强制 + 2 条复核提示，统一编号并全量待整改（L164-174）。"""
        # 第一层红行强制 ×2 + 第三层复核提示 ×2 = 4 条
        zhenggai = self.jieguo['correction']
        self.assertEqual(zhenggai.zong_shu, 4)
        # 类型分布：强制 2 条；编号 action-1..4 连续
        self.assertEqual([x.leixing for x in zhenggai.qingdan].count('强制整改'), 2)
        self.assertEqual([x.id for x in zhenggai.qingdan],
                         ['action-1', 'action-2', 'action-3', 'action-4'])
        # 计数：高 2 / 中 2；全部待整改、完成 0
        self.assertEqual((zhenggai.gao_shu, zhenggai.zhong_shu,
                          zhenggai.daizhenggai_shu, zhenggai.wancheng_shu), (2, 2, 4, 0))

    def test_kanban_yu_xishu(self):
        """看板预警计数与系数包：红 2 行、完成率 10000 基点（手算）。"""
        # 看板：预警汇总红 2；整改块总数 4（correction 名字空间直通看板）
        self.assertEqual(self.jieguo['dashboard'].yujing_huizong['hong_shu'], 2)
        self.assertEqual(self.jieguo['dashboard'].zhenggai_block['zong_shu'], 4)
        # 系数包：红 2 行；完成率 = 20000/20000 = 10000 基点（half-up）
        self.assertEqual(self.jieguo['factors'].hong_shu, 2)
        self.assertEqual(self.jieguo['factors'].wanchenglv_bps, 10000)

    def test_quesheng_tishi(self):
        """缺料警告三条：BSC / 溯源 / 拆分（engine.mjs L159-163）。"""
        # 标准夹具不填三组可选输入 → 三条警告逐字在场
        # （加上变更未确认警告共四条，后者另有专测）
        for wen in ('BSC 四维达成率未填写，暂不评分',
                    '未填写变更前后指标，暂不计算双维溯源',
                    '未提供规划/执行拆分参数，判定表将标明缺失线索'):
            self.assertIn(wen, self.jieguo['warnings'])


class FenxiJinJieTestCase(unittest.TestCase):
    """fenxi 进阶：修订链式重算、增长率、T-21、科目级档位与增长率覆盖。

    验算基准全部手写死（engine.mjs 对应段落），禁止从实现回读。

    五个用例的输入差异点：
        修订链——analyze 第二参（金额以分计，只改未来期）；
        增长率——config.growth 全局生效；
        T-21——页面故意配"费用模块"，引擎必须改写为"成本模块"；
        档位/增长率覆盖——subjects[].tiers / subjects[].growth 优先于全局。
    """

    def test_xiuding_lianshi_chongsuan(self):
        """批准修订 4 月为 120.00 元 → 之后各期链式接力（engine.mjs L95-106 手算）。"""
        # 修订案：4 月金额 12000 分（修订金额以"分"为单位走整数闸）
        xiuding = [{'kemu': '营业收入', 'period': '2025-04', 'amount': 12000}]
        # 修订案是 analyze 的第二参（server.mjs /api/revise 的调用形态），不在载荷内
        jieguo = fenxi(biaozhun_shuru(), xiuding)
        mingxi = jieguo['rolling'][0]['qijian_mingxi']
        # 4 月=12000（人工批准），5-12 月按 0 增长率接力仍 12000
        self.assertEqual(mingxi[3]['shuzhi_fen'], 12000)
        self.assertEqual(mingxi[3]['laiyuan'], '人工批准的预算修订')
        # 修订点之后每期都标"已批准修订后链式重算"
        self.assertEqual([t['shuzhi_fen'] for t in mingxi[4:]], [12000] * 8)
        self.assertEqual(mingxi[4]['laiyuan'], '已批准修订后链式重算')
        # 修订点之前的 3 月保持链法原值 10000（种子只在修订点重置）
        self.assertEqual(mingxi[2]['shuzhi_fen'], 10000)
        # 合计 = 11000+9000+10000+12000×9 = 138000，差额 18000
        self.assertEqual((jieguo['rolling'][0]['gundong_zonge_fen'],
                          jieguo['rolling'][0]['chae_fen']), (138000, 18000))
        # 修订案原样回显在结果里（审计溯源用）
        self.assertEqual(jieguo['revisions'], xiuding)

    def test_zengzhanglv_lianfa(self):
        """1% 增长率：3 月 = 10000×1.01 = 10100，4 月 = 10100×1.01 = 10201（手算）。"""
        # 链法①：首个剩余期起于自身年初数，此后逐期接力（half-up 逐期舍入）
        # ——届满期（1-2 月）的实际数不进接力链
        shuru = biaozhun_shuru()
        shuru['config']['growth'] = 100
        mingxi = fenxi(shuru)['rolling'][0]['qijian_mingxi']
        self.assertEqual([t['shuzhi_fen'] for t in mingxi[2:4]], [10100, 10201])

    def test_t21_rengong_gui_chengben(self):
        """工资费用（费用表内嵌人工行）被强制归成本模块（engine.mjs L57）。"""
        # 预算/实际各两个月；页面把它配成费用模块——T-21 强制改写为成本模块
        # （关键词"工资"命中人工正则；改写同时覆盖 module 与 direction 两个字段）
        hang = [BIAOTOU]
        for yue in (1, 2):
            hang.append(f'预算基础,2025-{yue:02d},工资费用,50.00,元,测试,2025-12-31,')
            hang.append(f'实时经营,2025-{yue:02d},工资费用,50.00,元,测试,2025-12-31,')
        jilu = daoru_biaoge('\n'.join(hang))
        shuru = biaozhun_shuru(records=jilu, subjects=[
            {'kemu': '工资费用', 'module': '费用模块', 'direction': '成本类'}])
        # 结果 subjects 里模块已被改写；方向同步变成本类
        jieguo = fenxi(shuru)
        self.assertEqual(jieguo['subjects'][0]['module'], '成本模块')

    def test_kemu_dangwei_fugai(self):
        """科目级档位覆盖：该科目阈值拉到 5000 基点 → 1000 基点不再预警。"""
        # subjects[].tiers 只对该科目生效：全局档位仍是 黄500/红1000
        shuru = biaozhun_shuru(subjects=[
            {'kemu': '营业收入', 'module': '收入模块', 'direction': '收入类',
             'tiers': [{'ming_cheng': '红', 'yan_se': '#FF0000', 'yu_fen': 5000}]}])
        # 1000 基点 < 5000 基点 → 不落红；黄档也被整体覆盖掉 → 全"无"
        self.assertEqual(fenxi(shuru)['variance'].hong_shu, 0)

    def test_kemu_zengzhanglv_fugai(self):
        """科目级增长率覆盖：50% 增长 → 3 月 = 15000 分（10000×1.5）。"""
        # subjects[].growth 优先于 config.growth（engine.mjs L89 的 ?? 链）
        shuru = biaozhun_shuru(subjects=[
            {'kemu': '营业收入', 'module': '收入模块', 'direction': '收入类',
             'growth': 5000}])
        mingxi = fenxi(shuru)['rolling'][0]['qijian_mingxi']
        self.assertEqual(mingxi[2]['shuzhi_fen'], 15000)

    def test_chongji_zhuangtai_tuijin(self):
        """整改状态推进后 chongji 重算计数（engine.mjs L252-256）。"""
        # 模拟复核区推进：一条完成、一条进行中
        jieguo = fenxi(biaozhun_shuru())
        zhenggai = jieguo['correction']
        zhenggai.qingdan[0].zhuangtai = '已完成'
        zhenggai.qingdan[1].zhuangtai = '进行中'
        # 重算后三态计数 2/1/1，总数不变（看板与组织汇总读的就是这组数）
        chongji(zhenggai)
        self.assertEqual((zhenggai.zong_shu, zhenggai.daizhenggai_shu,
                          zhenggai.jinxingzhong_shu, zhenggai.wancheng_shu),
                         (4, 2, 1, 1))


class FenxiJiaoyanCuowuTestCase(unittest.TestCase):
    """fenxi 校验链的中文报错逐字断言（顺序即 engine.mjs 出现顺序）。

    基准：engine.mjs 的模板字面量原文；改任何一侧文案此组测试即红。

    覆盖十六处报错：记录门禁两条、配置链六条、勾稽查重两条、
    变更状态两条、科目归属两条、三组归属校验两条，及一条正常路径
    （变更已确认后不再覆写判定）作对照。
    """

    def _cuowu(self, **gaixie):
        """便捷断言：跑 fenxi 并返回异常文案。"""
        # 覆盖式改夹具：任何键替换后立即重跑，异常文案交调用方逐字比对
        with self.assertRaises(YinqingCuowu) as cm:
            fenxi(biaozhun_shuru(**gaixie))
        return str(cm.exception)

    def test_wu_yusuan(self):
        """没有预算记录（engine.mjs L44）。"""
        # records 整体缺失：第一道门禁即拦截
        self.assertEqual(self._cuowu(records=None), '请先导入年度预算')

    def test_jujue_hang(self):
        """存在拒绝行必须先修正（engine.mjs L45；预算非空才轮到这道门）。"""
        from data_ingest import BiaozhunJilu, DaoruJieguo, JuJueHang
        # 一条合法预算 + 一条拒绝行：门禁顺序是"先有预算、再看拒绝"
        jia = DaoruJieguo(
            yusuan=[BiaozhunJilu(2, '预算基础', '2025-01', '营业收入', 10000,
                                  '元', '测试', '2025-12-31', '')],
            shishi=[], hangye=[], biangeng=[],
            jujue=[JuJueHang(3, '数值缺失', ('原始行',))])
        self.assertEqual(self._cuowu(records=jia),
                         '有 1 行未通过校验，请先修正后重新导入')

    def test_zhouqi_he_qijian(self):
        """滚动周期与期间格式（engine.mjs L47-49）。"""
        # 周期白名单外 → 第一报错
        shuru = biaozhun_shuru()
        shuru['config']['cycle'] = '周度'
        self.assertEqual(self._cuowu(config=shuru['config']), '请选择滚动周期')
        # 周期合法但期间书写非 ISO → 第二报错
        shuru['config'] = {**shuru['config'], 'cycle': '月度', 'period': '2025/02'}
        self.assertEqual(self._cuowu(config=shuru['config']),
                         '分析期间格式与滚动周期不一致')

    def test_jidu_hangye_liandong(self):
        """季度 + 行业修正 + 行业率为空（engine.mjs L52，全角引号逐字）。"""
        # 三条件联动的配置矛盾：文案含全角引号，逐字节对齐
        shuru = biaozhun_shuru()
        shuru['config'] = {**shuru['config'], 'cycle': '季度', 'period': '2025-Q1',
                           'industryCorrection': True, 'industry': None}
        self.assertEqual(self._cuowu(config=shuru['config']),
                         '已启用季度行业修正：请填写“行业增长率（%）”，'
                         '或取消勾选“启用季度行业增长率差值修正”。')

    def test_dangwei_he_yanse(self):
        """档位为空 / 颜色非色号（engine.mjs L38-39）。"""
        # 空档位列表：至少要有一档（不想预警可把阈值设为极高）
        shuru = biaozhun_shuru()
        shuru['config'] = {**shuru['config'], 'tiers': []}
        self.assertEqual(self._cuowu(config=shuru['config']), '至少配置一个预警档位')
        # 颜色不是 #RRGGBB：英文色名被拒
        shuru['config'] = {**shuru['config'], 'tiers': [
            {'ming_cheng': '红', 'yan_se': 'red', 'yu_fen': 1000}]}
        self.assertEqual(self._cuowu(config=shuru['config']), '预警颜色需为六位色号')

    def test_chayi_nianfen_he_chongfu(self):
        """实际数跨年 / 预算重复行（engine.mjs L65-68）。"""
        from dataclasses import replace
        from data_ingest import BiaozhunJilu
        jilu = biaozhun_jilu(shiji={'2025-01': 110.00, '2025-02': 90.00})
        # 跨年实际：格式合法但年份不符（lex 排序在期间窗口内，被校验链拦下）
        kuania = BiaozhunJilu(99, '实时经营', '2024-12', '营业收入', 8000, '元',
                              '测试', '2025-12-31', '')
        gailiang = replace(jilu, shishi=list(jilu.shishi) + [kuania])
        self.assertEqual(self._cuowu(records=gailiang),
                         '期间不属于当前财年或周期：2024-12')
        # 预算重复行：同一科目同一期间两行预算
        yusuan_chong = list(jilu.yusuan) + [jilu.yusuan[0]]
        self.assertEqual(self._cuowu(records=replace(jilu, yusuan=yusuan_chong)),
                         '重复记录：2025-01 营业收入，请核对后合并')

    def test_juedan_que_shiji(self):
        """届满期缺实际数（engine.mjs L87）。"""
        # 预算 12 个月、实际只有 1 月：2 月已届满但无实际数
        # ——届满完整性是滚动替换的前提，缺一期都不许开工
        jilu = biaozhun_jilu(shiji={'2025-01': 110.00})
        self.assertEqual(self._cuowu(records=jilu),
                         '营业收入 2025-02 已届满但缺实际数，请在数据区补齐')

    def test_wu_shiji(self):
        """分析窗口内没有任何实际数（engine.mjs L72）。"""
        # 实际全空：窗口门禁在届满检查之前先拦
        # （期间窗口 = qijian <= 分析期间，字典序即时间序）
        jilu = biaozhun_jilu(shiji={})
        self.assertEqual(self._cuowu(records=jilu), '当前分析期间内没有实际经营数据')

    def test_bian_geng_zhuangtai(self):
        """变更确认状态非法 / none 与登记互斥（engine.mjs L75-76）。"""
        # 白名单外状态值
        self.assertEqual(self._cuowu(changeStatus='maybe'), '经营变更确认状态无效')
        # 声明"本期无变更"却挂着事件登记 → 互斥报错
        self.assertEqual(self._cuowu(
            changeStatus='none',
            events=[{'kemu': '营业收入', 'period': '2025-01',
                     'structural': False, 'reason': ''}]),
            '已登记经营变更，不能同时声明本期无变更')

    def test_kemu_guilei_he_fangxiang(self):
        """科目未配置归属 / 方向与模块不一致（engine.mjs L82-83）。"""
        # subjects 整组缺失 → 首个预算科目被点名
        self.assertEqual(self._cuowu(subjects=[]), '请填写 营业收入 的科目方向与模块归属')
        # 收入模块配了成本方向 → 方向与模块不一致
        self.assertEqual(self._cuowu(subjects=[
            {'kemu': '营业收入', 'module': '收入模块', 'direction': '成本类'}]),
            '营业收入 的方向与模块不一致')

    def test_shiji_que_yusuan(self):
        """实际数期间不在该科目预算表内：algo 滚动门禁先触发
        （engine.mjs L112 的"缺对应预算"为防御性同义兜底，正常链路走
        rolling_budget 的同文案门禁——两侧行为一致）。"""
        jilu = biaozhun_jilu(shiji={'2025-01': 110.00, '2025-02': 90.00})
        from dataclasses import replace
        from rolling_budget import GunDongCuowu
        # 预算只留 1 月 → 2 月实际数无对应预算，滚动模块在编排层内先行拒绝
        jianlou = replace(jilu, yusuan=[x for x in jilu.yusuan if x.qijian == '2025-01'])
        with self.assertRaises(GunDongCuowu) as cm:
            fenxi(biaozhun_shuru(records=jianlou))
        self.assertEqual(str(cm.exception), '实际数据期间不在预算表中：2025-02')

    def test_shijian_weitianshu_yuanyin(self):
        """结构性变更登记必须填写原因（engine.mjs L137）。"""
        # structural=true 且 reason 只有空白 → 拒绝
        self.assertEqual(self._cuowu(
            changeStatus='provided',
            events=[{'kemu': '营业收入', 'period': '2025-01',
                     'structural': True, 'reason': '  '}]),
            '结构性变更登记需要填写原因')

    def test_sanjie_guishu(self):
        """拆分参数/变更登记/预算基准必须属于已届满科目（engine.mjs L136）。"""
        # 期间 2025-06 未届满（无差异行）→ 拆分参数无处挂靠
        self.assertEqual(self._cuowu(
            splits=[{'kemu': '营业收入', 'period': '2025-06', 'values': {}}]),
            '营业收入 2025-06 不属于本次已届满科目，无法使用其拆分参数')
        # 同一（科目,期间）两条基准 → 重复报错
        self.assertEqual(self._cuowu(
            baselines=[{'kemu': '营业收入', 'period': '2025-01', 'amount': 1},
                       {'kemu': '营业收入', 'period': '2025-01', 'amount': 2}]),
            '营业收入 2025-01 存在重复的预算基准')

    def test_bian_geng_yi_que_ren_zhengchang_panduan(self):
        """变更已确认（provided）：噪声门内差异 → 不触发，不再覆写复核提示。"""
        shuru = biaozhun_shuru(changeStatus='provided')
        # 噪声门 2500 基点 > 实际差异率 1000 基点 → 情形 1 不触发
        jieguo = fenxi(shuru)
        d = jieguo['decisions'][0]
        self.assertEqual((d['qingxing'], d['panduan']), (1, '不触发'))
        # 确认过变更后：不再要求确认、不再登记暂待复核警告
        self.assertFalse(d['requiresChangeConfirmation'])
        self.assertNotIn('经营变更尚未确认；缺失文件不代表本期无变更，环路判定暂待复核',
                         jieguo['warnings'])


if __name__ == '__main__':
    unittest.main()
