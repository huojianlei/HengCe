# -*- coding: utf-8 -*-
"""ingest_v11 自查测试：老底稿照进 / 老格式文件照进 / 骨架与新区激活 / 拒收路径。

覆盖四组事实（对应施工要求①②③ + v1.2 版式重排）：
    ① 老区零改动——experimental 演示底稿在 v1.2 双轨导入器下走老轨道，
       与 1.0.5 行为一致（同样 226 项勾稽全过）；
    ② 扩容生效——骨架底稿（v1.1/v1.2 两轨）导入通过；注入确定性新区数据后
       五区激活、恒等式计数 31 项全过；
    ③ 更严校验——非白名单格拒收、固化公式被改拒收、功能区标签被改拒收、
       分录借贷不平衡/税种分档不符/现金流期末不符逐字报错；
    ④ v1.2 新版式——三表两列制骨架照进（v1.2 轨）、展示公式被改拒收、
       老轨道版本串仍按 1.0.5 原串校验（双轨互不干扰）。
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）｜ v1.2：2026-10-16
"""
import sys  # 引导路径用
import unittest  # 测试框架
from decimal import Decimal  # 合成数值精度
from pathlib import Path  # 文件定位

BEN_MU = Path(__file__).resolve().parents[1]  # 包根
sys.dont_write_bytecode = True                     # 引 1.0.5 只读树，不留编译副产物
sys.path.insert(0, str(BEN_MU))  # 本包优先导入

import xlsx_xieqi_v11 as xw                         # noqa: E402  自带 ALGO 引导
from xlsx_reader import Book, ExcelError            # noqa: E402
from excel_ingest_v11 import import_excel_v11       # noqa: E402

DIGAO_105 = Path(r'D:\AppProject\开发分支_1.0.5\desktop\experimental')  # 老底稿目录（只读）
SHENGCHENG_QI = Path(r'D:\AppProject\开发分支_1.1.1\演示生成器\输出')  # 演示生成器输出目录
MU_LU = BEN_MU / '模板'  # 本包模板目录


def baozheng_muban():  # 契约保障
    """契约/骨架产物缺失时先跑构建器（正常交付态由 jian_qiyue_v11 预生成）。

    v1.2 构建器产出 v1.2 契约与骨架；v1.1 契约与骨架为冻结留档（老轨道依赖），
    缺失时不再重建（构建器已升级 v1.2 口径）。
    """
    if not (MU_LU / '模板结构规范-v1.2-预算基础.json').exists():  # 缺 v1.2 产物才构建
        import jian_qiyue_v11  # 调构建器
        assert jian_qiyue_v11.main() == 0, '契约构建自检失败'  # 构建必须全过


def zhuru_xinqu(gujia):  # 新区数据注入器
    """在骨架底稿上注入确定性新区数据（五区全激活、恒等式全成立）。

    数值全部由老底稿既有链条推导（期末现金/税金/摊销月值），零拍脑袋：
        a = 1 月期末现金(月度区 C68) − 期初现金(资负 C200) + 流出 300
          —— 使直接法 1 月期末 == 月度区期末（恒等式③）。
    """
    book = xw.read_book(gujia)  # 读骨架底稿
    c68 = book.number('现金流量表', 'C68')  # 1 月期末现金
    c200 = book.number('资产负债表', 'C200')  # 期初现金
    shui = [book.number('税金及附加', f'{c}33') for c in 'CDEFGHIJKLMN']  # 税金逐月值
    tan = [book.number('摊销明细', f'{c}33') for c in 'CDEFGHIJKLMN']  # 摊销逐月值
    yuanzhi = book.number('摊销明细', 'C31')  # 摊销原值
    yueshu = book.number('摊销明细', 'C32')  # 摊销月数
    a = c68 - c200 + Decimal('300')  # 合成流入（直接法配平）
    assert a > 0, f'合成流入须为正：{a}'  # 正数前提
    gai = {  # 变更表
        # Z1 利润表补充披露：营业外收入/支出各 1 笔 + 股数
        '利润表': {'P123': ('number', Decimal('1000')),  # Z1 营业外收入
                  'P124': ('number', Decimal('400')),  # Z1 营业外支出
                  'P131': ('number', Decimal('1000'))},  # Z1 股数
        # Z2 现金流明细：1 月收款 a（对照主体区第 4 行）/其他经营付现 300（第 11 行）
        '现金流量表': {'P123': ('number', a), 'P130': ('number', Decimal('300'))},  # Z2 收款/付款
        # Z3 税种分档：城建税逐月 = 税金及附加 C33（合计恒等成立）
        '税金及附加': {f'{x}123': ('number', shui[i])  # Z3 城建税逐月
                      for i, x in enumerate(('Q', 'R', 'S', 'T', 'U', 'V',  # 月列 Q..AB
                                             'W', 'X', 'Y', 'Z', 'AA', 'AB'))},
        # Z4 摊销台账：1 号资产承接老区单资产参数；矩阵月值 = 本月摊销
        '摊销明细': {'O123': ('text', '演示资产甲'), 'P123': ('text', '销售费用'),  # Z4 台账字段
                   'Q123': ('text', '演示部门'), 'R123': ('text', '2027-01'),  # 部门/起始月
                   'S123': ('number', yuanzhi), 'T123': ('number', yueshu),  # 原值/月数
                   **{f'{x}133': ('number', tan[i])  # Z4 矩阵月值
                      for i, x in enumerate(('P', 'Q', 'R', 'S', 'T', 'U',  # 月列 P..AA
                                             'V', 'W', 'X', 'Y', 'Z', 'AA'))}},
        # Z5 分录全账：收款/付款两笔（月度与年度借贷平衡，现金流对照齐）
        '分录': {'O124': ('text', '2027-01'), 'P124': ('text', '演示收款'),  # Z5 收款分录
               'Q124': ('text', '银行存款'), 'R124': ('text', '主营业务收入'),  # 借贷科目
               'S124': ('number', a), 'T124': ('number', a),  # 借贷金额
               'U124': ('number', Decimal('4')), 'V124': ('text', 'v11-1'),  # 对照=主体区 4 行
               'O125': ('text', '2027-01'), 'P125': ('text', '演示付款'),  # 付款分录
               'Q125': ('text', '管理费用'), 'R125': ('text', '银行存款'),  # 借贷科目
               'S125': ('number', Decimal('300')), 'T125': ('number', Decimal('300')),  # 借贷金额
               'U125': ('number', Decimal('11')), 'V125': ('text', 'v11-2')},  # 对照=主体区 11 行
    }  # 完整变更表
    return xw.patch(gujia, gai)  # 手术写出


class LaoQuJianrong(unittest.TestCase):  # 兼容测试组
    """① 老区零改动：老底稿与老格式文件照进。"""

    @classmethod  # 组级夹具
    def setUpClass(cls):
        baozheng_muban()  # 契约保障

    def test_lao_di_gao_zhao_jin(self):  # 老底稿照进
        """experimental 老底稿：v1.1 导入 226 项全过、新区不激活。"""
        shuju = (DIGAO_105 / '演示底稿-预算基础.xlsx').read_bytes()  # 读老底稿
        jie = import_excel_v11(shuju, '演示底稿-预算基础.xlsx')  # v1.1 导入
        self.assertEqual(jie['checks'], 226)  # 226 全过
        self.assertEqual(jie['zone_checks'], 0)  # 新区不激活
        self.assertEqual(jie['zones'], {})  # zones 空
        self.assertEqual(jie['contract_version'], 'v1.1')  # 版本标识

    def test_lao_di_gao_yu_1_0_5_tong_xing(self):  # 与 1.0.5 同行
        """同一老底稿：v1.1 与 1.0.5 导入结果逐键一致（行为零漂移）。"""
        sys.path.insert(0, r'D:\AppProject\开发分支_1.0.5\algo')  # 挂 1.0.5 路径
        from excel_ingest import import_excel as dao_ru_105  # 老导入器
        shuju = (DIGAO_105 / '演示底稿-预算基础.xlsx').read_bytes()
        lao = dao_ru_105(shuju, '演示底稿-预算基础.xlsx')  # 1.0.5 结果
        xin = import_excel_v11(shuju, '演示底稿-预算基础.xlsx')  # v1.1 结果
        for jian in ('checks', 'category', 'metadata', 'groupKey', 'text',  # 逐键比对
                     'subjects', 'procurement'):  # 七个关键键
            self.assertEqual(lao[jian], xin[jian], jian)  # 键名报错定位

    def test_shengchengqi_lao_shuchu_zhao_jin(self):  # 老格式件照进
        """老格式 12 表文件照进：experimental 两类老底稿（v1.0.5 契约、零新区格）。

        演示生成器输出已升级 v1.1（五区激活 zone_checks=111/63），其断言移驻
        演示生成器/verify.py；本用例的老格式代表 = experimental 老底稿两本。
        """
        for ming in ('演示底稿-预算基础.xlsx', '演示底稿-实时经营.xlsx'):  # 两类老底稿
            jie = import_excel_v11((DIGAO_105 / ming).read_bytes(), ming)  # v1.1 导入
            self.assertEqual(jie['checks'], 226, ming)  # 226 全过
            self.assertEqual(jie['zone_checks'], 0, ming)  # 新区不激活
            self.assertEqual(jie['zones'], {}, ming)  # zones 空


class XinQuJihuo(unittest.TestCase):  # 激活测试组
    """② 扩容生效：骨架导入通过、注入数据后五区激活且恒等式全过。"""

    @classmethod
    def setUpClass(cls):
        baozheng_muban()  # 骨架字节
        cls.gujia = (MU_LU / '演示底稿-v1.1-预算基础.xlsx').read_bytes()

    def test_gujia_di_gao_dao_ru(self):  # 骨架导入
        """骨架底稿（镜像层+功能区骨架、零数值）：226 照过、新区无数据。"""
        jie = import_excel_v11(self.gujia, '演示底稿-v1.1-预算基础.xlsx')  # v1.1 导入
        self.assertEqual(jie['checks'], 226)  # 226 全过
        self.assertEqual(jie['zone_checks'], 0)  # 无数据
        self.assertEqual(jie['zones'], {})  # zones 空

    def test_wu_qu_jihuo_hengdengshi(self):  # 五区激活
        """注入确定性新区数据：五区激活，恒等式 31 项全过（2+1+12+12+4）。"""
        jihuuo = zhuru_xinqu(self.gujia)  # 注入数据
        jie = import_excel_v11(jihuuo, '演示-激活-v1.1.xlsx')  # 导入激活件
        self.assertEqual(jie['checks'], 226)  # 老区 226
        self.assertEqual(jie['zone_checks'], 31)  # 新区 31 项
        self.assertEqual(set(jie['zones']), {'lirun_buchong', 'xianjinliu_mingxi',  # 五区齐
                                             'shuizhong_fendang', 'tanxiao_taizhang',
                                             'fenlu_quanzhang'})
        # 抽查回读结构：分录两笔、台账一行、分档合计逐月与税金一致
        fl = jie['zones']['fenlu_quanzhang']  # 分录区
        self.assertEqual(len(fl['fentiao']), 2)  # 两笔分录
        self.assertEqual(fl['fentiao'][0]['duizhao'], 4)  # 对照行号
        tz = jie['zones']['tanxiao_taizhang']  # 摊销区
        self.assertEqual(len(tz['taizhang']), 1)  # 一行台账
        self.assertEqual(tz['taizhang'][0]['yue_tanxiao'],  # 月摊销=合计
                         jie['zones']['tanxiao_taizhang']['heji_yue'][0])
        sj = jie['zones']['shuizhong_fendang']  # 税种区
        self.assertEqual(sj['heji_yue'][0],  # 分档合计
                         xw.read_book(self.gujia).number('税金及附加', 'C33'))  # 与老区税金一致


class JuShouLuJing(unittest.TestCase):  # 拒收测试组
    """③ 更严校验：非白名单/镜像被改/标签被改/勾稽不符逐字报错。"""

    @classmethod
    def setUpClass(cls):
        baozheng_muban()
        cls.gujia = (MU_LU / '演示底稿-v1.1-预算基础.xlsx').read_bytes()  # 骨架字节

    def _duan_yan(self, shuju, wen_an, ming='断言件.xlsx'):  # 断言助手
        """统一断言：ExcelError 且报错文案逐字命中。"""
        with self.assertRaises(ExcelError) as cm:  # 捕获异常
            import_excel_v11(shuju, ming)  # 尝试导入
        self.assertEqual(str(cm.exception), wen_an)  # 文案逐字

    def test_fei_baimingdan_ge(self):  # 非白名单格
        """非白名单格（利润表!C10 主体区年度位）→ 整本拒收。"""
        gai = xw.patch(self.gujia, {'利润表': {'C10': ('number', Decimal('1'))}})  # C10 填值
        self._duan_yan(gai, '利润表出现标准模板以外的单元格')  # 逐字断言

    def test_jingxiang_gongshi_beigai(self):  # 镜像被改
        """镜像格填数值（现金流量表!D4）→ 只接受固化公式。"""
        gai = xw.patch(self.gujia, {'现金流量表': {'D4': ('number', Decimal('5'))}})  # D4 填数值
        self._duan_yan(gai, '镜像公式被修改：现金流量表!D4；月度镜像格只接受固化公式')  # 逐字断言

    def test_qu_biaoqian_beigai(self):  # 区标签被改
        """功能区标签被改（分录!O121）→ 骨架逐字校验拒收。"""
        gai = xw.patch(self.gujia, {'分录': {'O121': ('text', '改过的标题')}})  # O121 改文本
        self._duan_yan(gai, '功能区标签被修改：分录全账区（分录!O121）')  # 逐字断言

    def test_fenlu_jiedai_bu_pingheng(self):  # 借贷不平衡
        """分录贷方多 1 分 → 年度借贷不平衡逐字报错。"""
        jihuo = zhuru_xinqu(self.gujia)  # 激活件
        gai = xw.patch(jihuo, {'分录': {'T124': ('number',  # 贷方+1分
                        xw.read_book(jihuo).number('分录', 'T124') + Decimal('0.01'))}})  # 重读原值再加
        self._duan_yan(gai, '功能区勾稽不通过：分录全年借贷不平衡')  # 逐字断言

    def test_shuizhong_bu_fu(self):  # 税种不符
        """城建税 1 月多 1 元 → 分档合计与税金及附加不符逐字报错。"""
        jihuo = zhuru_xinqu(self.gujia)  # 激活件
        gai = xw.patch(jihuo, {'税金及附加': {'Q123': ('number',  # 城建+1元
                        xw.read_book(jihuo).number('税金及附加', 'Q123') + Decimal('1'))}})  # 重读原值再加
        self._duan_yan(gai, '功能区勾稽不通过：税种分档合计与税金及附加不符：1月')  # 逐字断言

    def test_xianjinliu_qimo_bu_fu(self):  # 期末不符
        """现金流明细 1 月收款多 1 元 → 期末现金与月度区不符逐字报错。"""
        jihuo = zhuru_xinqu(self.gujia)  # 激活件
        gai = xw.patch(jihuo, {'现金流量表': {'P123': ('number',  # 收款+1元
                        xw.read_book(jihuo).number('现金流量表', 'P123') + Decimal('1'))}})  # 重读原值再加
        self._duan_yan(gai, '功能区勾稽不通过：现金流量表期末现金与月度区不符：1月')  # 逐字断言


class V12XinBanshi(unittest.TestCase):  # v1.2 新版式测试组
    """④ v1.2 两列制：骨架照进（v1.2 轨）、展示公式被改拒收、注入激活。"""

    @classmethod
    def setUpClass(cls):  # 组级夹具
        baozheng_muban()
        cls.gujia = (MU_LU / '演示底稿-v1.2-预算基础.xlsx').read_bytes()  # v1.2 骨架

    def test_v12_gujia_dao_ru(self):  # v1.2 骨架照进
        """v1.2 骨架（两列制+功能区，零数值）：226 照过、v1.2 轨、新版本串。"""
        jie = import_excel_v11(self.gujia, '演示底稿-v1.2-预算基础.xlsx')
        self.assertEqual(jie['checks'], 226)  # 226 全过
        self.assertEqual(jie['zone_checks'], 0)  # 无数据
        self.assertEqual(jie['contract_version'], 'v1.2')  # 新轨道
        self.assertEqual(jie['metadata']['模板版本'], '标准输入模板/1.0.5')  # AY1 新版本串

    def test_v12_zhanshi_beigai(self):  # 展示公式被改
        """v1.2 展示格填数值（利润表!D4 本年累计列）→ 只接受固化公式。"""
        gai = xw.patch(self.gujia, {'利润表': {'D4': ('number', Decimal('5'))}})  # D4 填数值
        with self.assertRaises(ExcelError) as cm:  # 捕获异常
            import_excel_v11(gai, '断言件.xlsx')  # 尝试导入
        self.assertEqual(str(cm.exception),
                         '镜像公式被修改：利润表!D4；月度镜像格只接受固化公式')  # 文案逐字

    def test_v12_zhuru_jihuo(self):  # v1.2 注入激活
        """v1.2 骨架注入确定性新区数据：五区激活，恒等式 31 项全过（v1.2 轨）。"""
        jihuo = zhuru_xinqu(self.gujia)  # 注入数据（勾稽区两轨同构）
        jie = import_excel_v11(jihuo, '演示-激活-v1.2.xlsx')  # 导入激活件
        self.assertEqual(jie['checks'], 226)  # 老区 226
        self.assertEqual(jie['zone_checks'], 31)  # 新区 31 项
        self.assertEqual(jie['contract_version'], 'v1.2')  # 新轨道
        self.assertGreater(jie['zones']['lirun_buchong']['eps_jicheng'], 0)  # EPS 链（新口径）为正


if __name__ == '__main__':  # 直跑入口
    unittest.main()  # unittest 主
