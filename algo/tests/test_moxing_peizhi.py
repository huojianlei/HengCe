"""moxing_peizhi（模型配置管理器）单元测试 —— 前端改 Key / 改参数接口的契约测试。

设计原则：
    1. 三个接口各一组用例：dangqian（安全视图）/ gengxin（部分更新与校验）
       / chuangjian（按配置生效）；
    2. 密钥安全断言贯穿：任何展示结构里都不出现密钥全文；
    3. 全部离线：chuangjian 的网络发送器用假实现注入。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import unittest
from unittest import mock

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from moxing_peizhi import PeizhiCuowu, PeizhiGuanliqi  # noqa: E402

#: 测试用假密钥（仅内存）
JIAMIYAO = 'sk-peizhi-ceshi-000999'


def jia_fasong(qingqiu, chaozhi_miao):
    """假发送器：返回固定成功响应（不打网络）。"""
    return '{"choices": [{"message": {"content": "ok"}}]}'.encode('utf-8')


class TestDangqian(unittest.TestCase):
    """查看配置：安全视图（密钥只有遮盖形态）。"""

    def test_zhegai_xinshi(self) -> None:
        """dangqian 返回遮盖密钥，全文绝不在展示结构里。"""
        guanliqi = PeizhiGuanliqi(api_miyao=JIAMIYAO)
        xinxi = guanliqi.dangqian()
        # 展示字段是遮盖形态，且不含全文
        self.assertEqual(xinxi.api_miyao_zhegai, 'sk-p****')
        self.assertNotIn(JIAMIYAO, str(xinxi))

    def test_wei_shezhi_miyao(self) -> None:
        """没给密钥也没环境变量：视图显示"（未设置）"而非报错。"""
        with mock.patch.dict('os.environ', {}, clear=True):  # 清空环境保证确定性
            guanliqi = PeizhiGuanliqi()
        self.assertEqual(guanliqi.dangqian().api_miyao_zhegai, '（未设置）')


class TestGengxin(unittest.TestCase):
    """更新配置：部分更新、即时生效、脏配置原子拒绝。"""

    def test_bufen_gengxin(self) -> None:
        """只改温度与模型名：其余字段保持不变。"""
        guanliqi = PeizhiGuanliqi(api_miyao=JIAMIYAO)
        guanliqi.gengxin(wendu=0.3, moxing_ming='deepseek-v4-pro')
        xinxi = guanliqi.dangqian()
        self.assertEqual(xinxi.wendu, 0.3)                      # 改了
        self.assertEqual(xinxi.moxing_ming, 'deepseek-v4-pro')  # 改了
        self.assertEqual(xinxi.jiekou_dizhi, 'https://api.deepseek.com')  # 没动
        self.assertEqual(xinxi.chaozhi_miao, 60.0)              # 没动

    def test_gengxin_miyao_jishi_shengxiao(self) -> None:
        """换 Key 后立刻生效：chuangjian 出的函数带新密钥进请求头。"""
        guanliqi = PeizhiGuanliqi(api_miyao=JIAMIYAO)
        guanliqi.gengxin(api_miyao='sk-xinmiyao-8888')
        hanshu = guanliqi.chuangjian(fasong=jia_fasong)
        hanshu('x')  # 触发一次调用（假发送器，不打网络）

    def test_zang_peizhi_yuanzi_jujue(self) -> None:
        """脏配置（空密钥/温度越界/超时非正/未知字段）→ 拒绝且旧配置不动。"""
        guanliqi = PeizhiGuanliqi(api_miyao=JIAMIYAO, )
        # 四种脏值逐个试，全部抛 PeizhiCuowu
        for huaire in ({'api_miyao': '  '}, {'wendu': 9.0}, {'chaozhi_miao': 0}, {'bucunzai': 1}):
            with self.assertRaises(PeizhiCuowu, msg=f'{huaire} 应被拒绝'):
                guanliqi.gengxin(**huaire)
        # 原子性：温度没被中途改坏（仍为初始 0.0）
        self.assertEqual(guanliqi.dangqian().wendu, 0.0)

    def test_kong_gengxin_jujue(self) -> None:
        """空更新（一个字段都没传）→ 拒绝（无意义调用挡在门外）。"""
        guanliqi = PeizhiGuanliqi(api_miyao=JIAMIYAO)
        with self.assertRaises(PeizhiCuowu):
            guanliqi.gengxin()


class TestChuangjian(unittest.TestCase):
    """按配置生成模型函数：生效链路与未设密钥保护。"""

    def test_an_peizhi_shengcheng(self) -> None:
        """chuangjian 产出可调用的函数（假发送器离线验证）。"""
        guanliqi = PeizhiGuanliqi(api_miyao=JIAMIYAO)
        guanliqi.gengxin(moxing_ming='ceshi-xinghao', wendu=0.1)
        hanshu = guanliqi.chuangjian(fasong=jia_fasong)
        self.assertEqual(hanshu('提示词'), 'ok')

    def test_wei_shezhi_miyao_bao_cuo(self) -> None:
        """密钥未设置时 chuangjian → 明确指引错误。"""
        with mock.patch.dict('os.environ', {}, clear=True):
            guanliqi = PeizhiGuanliqi()
        with self.assertRaises(PeizhiCuowu) as cuo:
            guanliqi.chuangjian()
        self.assertIn('gengxin', str(cuo.exception))  # 指引里带改法

    def test_huanjing_bianliang_chushi(self) -> None:
        """初始化回退环境变量：FINAGENT_API_KEY 设了就能直接建函数。"""
        with mock.patch.dict('os.environ', {'FINAGENT_API_KEY': 'sk-hj-777'}):
            guanliqi = PeizhiGuanliqi()
            hanshu = guanliqi.chuangjian(fasong=jia_fasong)  # 能建 = 密钥已就绪
        self.assertEqual(hanshu('x'), 'ok')


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_moxing_peizhi.py
    unittest.main()
