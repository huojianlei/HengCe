# -*- coding: utf-8 -*-
"""report_parse 报表模板解析层的测试（14 用例，全部离线、期望值手算写死）。

口径依据：algo/report_parse.py 模块头（用户指令 2026-08-30 新增口径：
预算报告分表输入——报告头 + 分节 + "科目×期间"矩阵 + 登记小表 → 标准 8 列；
识别不了交回 llm_clean 智能分流，绝不硬解）。

用例目录（四大组，对应解析器的四个决策面）：
    TestShibie    ×4  识别边界：完整报告 / 纯叙述 / 缺编制日期 / 表体空
                      ——"宁可不认也不硬解"的四个失败出口逐一锁死
    TestQijian    ×3  期间写法规范：季度混写 / 月度混写与防误咬 / 裸写法
                      ——真实报告里'一季度''2026-Q1''1月'混用是常态
    TestJiegou    ×4  结构细节：合计列与元后缀 / 占位符 / 短行容错 / 坏值透传
                      ——矩阵解析的四个边角，全部用最小夹具隔离变量
    TestXiaobiao  ×3  单页小表：变更登记 / 行业对标(%与天) / 业务量计数
                      ——三种固定列法到 8 列的映射契约

夹具策略：全部为行内拼装的"迷你报告文本"——不依赖 testgen（依赖方向
纪律：主体永不引用 testgen）；期望值全部手工推演写死，禁止现算自证。
断言形态：关键行【逐字】核对（'预算基础,2026-Q1,营收,……'），
其余用包含断言（定位字段在行内即可）——逐字锁死出口契约，
包含断言保持用例对无关字段（如备注措辞）的稳健。
"""

from __future__ import annotations

import unittest

from data_ingest import daoru_csv              # 集成断言用：解析文本直接入库
from report_parse import guifan_qijian, shitu_jiexi

#: 报告头（各夹具共用）——年度供期间兜底、编制日期供台账字段，
#: 二者缺一解析器都会"宁可不认"（见 TestShibie 的反向用例）
BAOGAO_TOU = ('华衡科技有限公司\n2026年度预算报告\n'
              '编制单位：财务部\n编制日期：2026-01-15\n')


class TestShibie(unittest.TestCase):
    """识别边界：像报告就解析成 8 列，不像就 shibie=False 交回智能分流。

    四条用例 = 解析器全部失败出口 + 一条成功主路：
    成功（台账三字段补齐）/ 纯叙述（连分节都没有）/ 缺日期（有分表
    但台账字段造不出来）/ 空表体（分节在但没数据行）——
    每条失败出口的 beizhu 都要写清"为什么交回"，界面层好提示用户。
    """

    def test_wanzheng_baogao(self) -> None:
        """完整迷你报告：矩阵展开 + 台账字段统一（来源=预算报告/时间=编制日期）。

        手算：预算表 2 个期间列（"合计"列被跳过）× 1 科目 = 2 条预算记录；
        合计行整行跳过；实际表 1 条（"完成率"列被跳过）——共 3 条记录，
        加表头 = 4 行输出。台账三字段由解析器统一补齐（来源/时间/空备注）。
        """
        wenben = BAOGAO_TOU + (
            '\n一、编制说明\n本报告按季度列示全年预算，作为滚动调整的基准。\n'
            '\n二、年度分季度预算表（单位：元）\n'
            '科目,2026年第一季度,2026年第二季度,合计\n'
            '营收,100000.00,110000.00,210000.00\n'
            '合计,100000.00,110000.00,210000.00\n'
            '\n三、实际经营数据表（单位：元）\n'
            '科目,2026年第一季度,完成率\n'
            '营收,105000.00,105.00%\n')
        jg = shitu_jiexi(wenben)
        self.assertTrue(jg.shibie)
        hang_lie = jg.wenben_8lie.strip().split('\n')
        self.assertEqual(len(hang_lie), 4)                       # 表头 + 3 条记录
        self.assertEqual(hang_lie[1],                            # 期望值手抄逐字核对
                         '预算基础,2026-Q1,营收,100000.00,元,预算报告,2026-01-15,')
        self.assertEqual(hang_lie[3],
                         '实时经营,2026-Q1,营收,105000.00,元,预算报告,2026-01-15,')

    def test_chun_xushu_jiaohui(self) -> None:
        """纯叙述文本：一个分节都认不出 → shibie=False、文本为空（交回分流）。

        叙述里故意放了"花多了""采购的账"这类与预算相关的字眼——
        只要不含"表"字收尾的短行，就不许误判成分节（闸门纪律）。
        """
        jg = shitu_jiexi('老板说：这个月花多了，下个月注意。\n再看看采购的账。\n')
        self.assertFalse(jg.shibie)
        self.assertEqual(jg.wenben_8lie, '')
        self.assertIn('交回', jg.beizhu)

    def test_que_bianzhi_riqi_jujue(self) -> None:
        """有分表但缺编制日期：记录缺台账字段 → 宁可不认（诚实拒绝）。

        data_ingest 要求来源/时间非空——解析器与其硬造一个日期，
        不如整份不认、交回分流（宁缺毋滥口径）。
        """
        wenben = ('2026年度预算报告\n'
                  '二、预算表（单位：元）\n'
                  '科目,一季度\n营收,1000.00\n')
        jg = shitu_jiexi(wenben)
        self.assertFalse(jg.shibie)
        self.assertIn('编制日期', jg.beizhu)

    def test_kong_biao_jiaohui(self) -> None:
        """分节标题存在但表体空（只有表头行）：解析不出记录 → 交回。"""
        wenben = (BAOGAO_TOU
                  + '\n二、年度分季度预算表（单位：元）\n'
                  + '科目,2026年第一季度\n')
        jg = shitu_jiexi(wenben)
        self.assertFalse(jg.shibie)
        self.assertIn('未解析出任何记录', jg.beizhu)


class TestQijian(unittest.TestCase):
    """期间写法规范：报告里常见的五花八门写法 → '2026-Q1'/'2026-01'。

    真实报告的期间列头人写的，同一张表里'2026年第一季度'和'一季度'
    混用毫不稀奇——规范化是矩阵展开的前提；认不出的一律 None
    （该列按"非期间列"跳过），绝不猜。
    """

    def test_jidu_hunxie(self) -> None:
        """季度四种写法同指一个期间（同一份报告里混用是常态）。"""
        for xiefa in ('2026年第一季度', '2026年1季度', '一季度', '2026-Q1'):
            self.assertEqual(guifan_qijian(xiefa, '2026'), '2026-Q1', xiefa)

    def test_yuedu_hunxie(self) -> None:
        """月度三种写法同指一个期间；越界月份/非期间词返回 None。

        防误咬回归用例：'2026-13' 不许被咬成 2026-01——月份正则带
        负向断言（匹配到的月份数字后面不许再跟数字），
        对应开发期真实修过的一个 bug。
        """
        for xiefa in ('2026-01', '2026年1月', '1月'):
            self.assertEqual(guifan_qijian(xiefa, '2026'), '2026-01', xiefa)
        self.assertIsNone(guifan_qijian('2026-13', '2026'))
        self.assertIsNone(guifan_qijian('完成率', '2026'))

    def test_luo_Q1_kao_nianfen(self) -> None:
        """裸写法 'Q1'：年从报告年度取——缺年度则返回 None（不瞎猜）。"""
        self.assertEqual(guifan_qijian('Q1', '2026'), '2026-Q1')
        self.assertIsNone(guifan_qijian('Q1', None))
        self.assertIsNone(guifan_qijian('1月', None))


class TestJiegou(unittest.TestCase):
    """结构细节：合计列/占位符/短行/坏值——矩阵解析的四个边角。"""

    def _jie_yusuan(self, biaotou: str, hang: str) -> list[str]:
        """小助手：拼一份只有预算表的报告，返回解析出的数据行（去表头）。

        夹具收敛到最小形态：报告头 + 一个分节 + 表头 + 一行数据——
        每个边角用例只变一处，失败时一眼定位。
        """
        wenben = (BAOGAO_TOU
                  + '\n二、年度分季度预算表（单位：元）\n'
                  + biaotou + '\n' + hang + '\n')
        jg = shitu_jiexi(wenben)
        self.assertTrue(jg.shibie)
        return jg.wenben_8lie.strip().split('\n')[1:]

    def test_heji_lie_tiaoguo(self) -> None:
        """合计列跳过：表头带'合计'列不生成记录；数值带'元'后缀也能剥掉。

        期望手算：'营收,1000.00元,210000.00' → 只有 Q1 一条，
        数值 '1000.00元' 清理为 '1000.00'（合法性仍归 data_ingest）。
        """
        hang_lie = self._jie_yusuan(
            '科目,一季度,合计', '营收,1000.00元,210000.00')
        self.assertEqual(len(hang_lie), 1)
        self.assertEqual(hang_lie[0],
                         '预算基础,2026-Q1,营收,1000.00,元,预算报告,2026-01-15,')

    def test_zhanwei_fu_tiaoguo(self) -> None:
        """占位符格跳过：'—'格不生成记录，其余格照常。"""
        hang_lie = self._jie_yusuan(
            '科目,一季度,二季度', '服务收入,2000.00,—')
        self.assertEqual(len(hang_lie), 1)
        self.assertIn('2026-Q1,服务收入,2000.00', hang_lie[0])

    def test_duan_hang_rongcuo(self) -> None:
        """短行容错：数据行比表头短（缺尾列）不炸，缺的格不生成记录。"""
        hang_lie = self._jie_yusuan(
            '科目,一季度,二季度,三季度', '其他收入,500.00')
        self.assertEqual(len(hang_lie), 1)
        self.assertIn('2026-Q1,其他收入,500.00', hang_lie[0])

    def test_huai_shuzhi_toumian(self) -> None:
        """坏数值原样透传：解析层不判合法性，'abc' 交给 data_ingest 拒绝。

        这是"链路诚实"的契约测试——坏行必须出现在拒绝清单里，
        而不是在解析层悄悄消失；解析成功与数值合法是两回事。
        """
        wenben = (BAOGAO_TOU
                  + '\n二、年度分季度预算表（单位：元）\n'
                  + '科目,一季度\n办公费,abc\n')
        jg = shitu_jiexi(wenben)
        self.assertTrue(jg.shibie)                       # 模板识别与数值合法无关
        ruku = daoru_csv(jg.wenben_8lie)
        self.assertEqual(ruku.ruku_shu, 0)
        self.assertEqual(len(ruku.jujue), 1)
        self.assertIn('数值不是合法数字', ruku.jujue[0].yuanyin)


class TestXiaobiao(unittest.TestCase):
    """单页小表：变更登记 / 行业对标 / 业务量——三种固定列法到 8 列的映射。

    小表与矩阵表的分野：矩阵是"科目×期间"二维展开（一格一条记录），
    小表是"一行一条记录"——三类小表的列名→8 列字段映射在此逐一锁死，
    含台账字段的来源（登记时间当更新时间 / 编制日期兜底）。
    """

    def test_biangeng_dengji(self) -> None:
        """变更登记表：事项→科目、发生期间→期间、登记时间→台账更新时间。

        数值恒 1 次（事件型数据）；说明进备注——与 data_ingest 8 列对齐；
        期间写法用中文长写法，顺带覆盖"发生期间"列的规范化路径。
        """
        wenben = (BAOGAO_TOU
                  + '\n五、经营变更事项登记表\n'
                  + '变更事项,发生期间,登记时间,说明\n'
                  + '供应商涨价,2026年第一季度,2026-04-05,主要原材料单价上调\n')
        jg = shitu_jiexi(wenben)
        self.assertTrue(jg.shibie)
        self.assertEqual(
            jg.wenben_8lie.strip().split('\n')[1],
            '经营变更,2026-Q1,供应商涨价,1,次,预算报告,2026-04-05,主要原材料单价上调')

    def test_hangye_duibiao(self) -> None:
        """行业对标表：%与计数单位都按行携带；归属期间取自预算表首个期间。

        手算：预算表 1 条 + 行业 2 条 = 3 条记录 + 表头 = 4 行；
        行业行的期间 = 预算表首个期间（2026-Q1），不瞎猜。
        """
        wenben = (BAOGAO_TOU
                  + '\n二、年度分季度预算表（单位：元）\n'
                  + '科目,一季度\n营收,1000.00\n'
                  + '\n六、行业对标数据表（单位：%）\n'
                  + '指标,数值,单位,备注\n'
                  + '行业营收增长率,0.85,%,年度平均\n'
                  + '行业平均交付周期,8,天,行业均值\n')
        jg = shitu_jiexi(wenben)
        self.assertTrue(jg.shibie)
        hang_lie = jg.wenben_8lie.strip().split('\n')
        self.assertEqual(len(hang_lie), 4)               # 表头 + 预算1 + 行业2
        self.assertEqual(hang_lie[2],
                         '行业对标,2026-Q1,行业营收增长率,0.85,%,预算报告,2026-01-15,年度平均')
        self.assertEqual(hang_lie[3],
                         '行业对标,2026-Q1,行业平均交付周期,8,天,预算报告,2026-01-15,行业均值')

    def test_yewuliang_jishu(self) -> None:
        """业务量表：科目/统计期间/数量/单位 → 实时经营计数记录。"""
        wenben = (BAOGAO_TOU
                  + '\n四、业务量统计表\n'
                  + '科目,统计期间,数量,单位\n'
                  + '销量,2026年第一季度,1200,个\n'
                  + '交付周期,2026年第一季度,7,天\n')
        jg = shitu_jiexi(wenben)
        self.assertTrue(jg.shibie)
        hang_lie = jg.wenben_8lie.strip().split('\n')
        self.assertEqual(hang_lie[1],
                         '实时经营,2026-Q1,销量,1200,个,预算报告,2026-01-15,')
        self.assertEqual(hang_lie[2],
                         '实时经营,2026-Q1,交付周期,7,天,预算报告,2026-01-15,')


if __name__ == '__main__':
    unittest.main()
