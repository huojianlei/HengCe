"""model_api（模型 API 调用器）单元测试 —— 全部离线（注入假发送器，不打真接口）。

设计原则：
    1. 真发送器 _fasong_https 从不被触发——全部经 fasong 参数注入替身；
    2. 密钥安全三断言：不落盘（无文件写）、错误信息不含密钥全文、请求头含 Bearer；
    3. 请求体逐字段核对（模型名/温度=0/提示词完整带入）。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（algo 目录下）：
    ../env/Scripts/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import json
import urllib.error
import unittest
from unittest import mock

# 被测模块：discover -t . 运行时 algo 根目录在 sys.path 上
from model_api import (  # noqa: E402
    HUANJING_MIAOYAO_BIANLIANG,
    MoxingCuowu,
    _zhegai_miyao,
    chuangjian_moxing_hanshu,
)

#: 测试用假密钥（仅内存，永不落盘）
JIAMIYAO = 'sk-ceshiyaoshi000123'


def zhuangzhu_fasong(bo_hui: Exception | None = None, xiangying: bytes | None = None):
    """造一个"录制型"假发送器：捕获请求对象，按剧本返回或抛错。

    返回 (fasong_hanshu, buhuo_liebiao)——捕获的请求供断言请求头/请求体。
    """
    buhuo = []  # 捕获到的 (Request 对象, 超时秒)

    def fasong(qingqiu, chaozhi_miao):
        buhuo.append((qingqiu, chaozhi_miao))
        if bo_hui is not None:
            raise bo_hui  # 剧本：抛错（HTTP/网络错误）
        return xiangying if xiangying is not None else b'{}'

    return fasong, buhuo


class TestChuangjian(unittest.TestCase):
    """工厂函数：正常创建与请求构造核对。

    请求构造用例是最重要的——它是"前端输入口"的契约测试：
    密钥进请求头、模型名/温度/提示词进请求体，一个都不能错。
    """

    def test_chenggong_fanhui_neirong(self) -> None:
        """正常剧本：返回 choices[0].message.content 的文本。"""
        # 假响应按 OpenAI 兼容结构构造（json.dumps 再编码，避开中文字节串限制）
        xiangying = json.dumps({'choices': [{'message': {'content': '翻译结果'}}]}).encode('utf-8')
        fasong, _ = zhuangzhu_fasong(xiangying=xiangying)
        hanshu = chuangjian_moxing_hanshu(JIAMIYAO, fasong=fasong)
        self.assertEqual(hanshu('把乱表格转成标准CSV'), '翻译结果')

    def test_qingqiu_tou_yu_ti_zhengque(self) -> None:
        """请求构造：Bearer 头、URL、模型名、温度=0、提示词完整带入。"""
        xiangying = b'{"choices": [{"message": {"content": "ok"}}]}'
        fasong, buhuo = zhuangzhu_fasong(xiangying=xiangying)
        hanshu = chuangjian_moxing_hanshu(JIAMIYAO, moxing_ming='ceshi-moxing', fasong=fasong)
        hanshu('提示词ABC')
        qingqiu, chaozhi = buhuo[0]  # 捕获的请求与超时
        # ① 鉴权头：Bearer + 密钥全文（进请求头是应该的，进日志才是错）
        self.assertEqual(qingqiu.get_header('Authorization'), f'Bearer {JIAMIYAO}')
        # ② URL：端点拼 /chat/completions
        self.assertTrue(qingqiu.full_url.endswith('/chat/completions'))
        # ③ 请求体：模型名 / 温度 0 / 非流式 / 提示词在内
        ti = json.loads(qingqiu.data.decode('utf-8'))
        self.assertEqual(ti['model'], 'ceshi-moxing')
        self.assertEqual(ti['temperature'], 0)
        self.assertFalse(ti['stream'])
        self.assertEqual(ti['messages'][0]['content'], '提示词ABC')
        # ④ 超时参数透传
        self.assertEqual(chaozhi, 60.0)


class TestMiyaoAnquan(unittest.TestCase):
    """密钥纪律：缺密钥报错、环境变量兜底、错误信息永不露全文。

    对应 docs\\03 §6 安全要点——这是本项目答辩与合规的底线测试组。
    """

    def test_que_miyao_mingque_baocuo(self) -> None:
        """无参数且无环境变量 → 明确的中文指引错误。"""
        # mock 清空环境变量：保证测试不受本机真实环境干扰
        with mock.patch.dict('os.environ', {}, clear=True):  # 清空环境变量
            with self.assertRaises(MoxingCuowu) as cuo:
                chuangjian_moxing_hanshu(None)  # 不传密钥也不给发送器
        self.assertIn('api_miyao', str(cuo.exception))       # 指引里有参数名
        self.assertIn(HUANJING_MIAOYAO_BIANLIANG, str(cuo.exception))  # 和环境变量名

    def test_huanjing_bianliang_houbei(self) -> None:
        """参数缺省时回退读环境变量 FINAGENT_API_KEY。"""
        xiangying = b'{"choices": [{"message": {"content": "ok"}}]}'
        fasong, buhuo = zhuangzhu_fasong(xiangying=xiangying)
        with mock.patch.dict('os.environ', {HUANJING_MIAOYAO_BIANLIANG: 'sk-huanjing999'}):
            hanshu = chuangjian_moxing_hanshu(None, fasong=fasong)  # 参数缺省
        hanshu('x')
        # 环境变量里的密钥进了请求头 → 证明兜底生效
        self.assertEqual(buhuo[0][0].get_header('Authorization'), 'Bearer sk-huanjing999')

    def test_http_cuowu_bu_lu_miyao(self) -> None:
        """HTTP 401：报错含遮盖密钥、不含全文。"""
        bo_hui = urllib.error.HTTPError(
            url='https://api.deepseek.com/chat/completions', code=401,
            msg='Unauthorized', hdrs=None, fp=None,
        )
        fasong, _ = zhuangzhu_fasong(bo_hui=bo_hui)
        hanshu = chuangjian_moxing_hanshu(JIAMIYAO, fasong=fasong)
        with self.assertRaises(MoxingCuowu) as cuo:
            hanshu('x')
        xinxi = str(cuo.exception)
        self.assertIn('401', xinxi)              # 状态码在
        self.assertNotIn(JIAMIYAO, xinxi)        # 密钥全文绝不在
        self.assertIn(_zhegai_miyao(JIAMIYAO), xinxi)  # 只有遮盖形态

    def test_zhegai_guize(self) -> None:
        """遮盖规则：长密钥露前 4 位；过短整体遮盖。"""
        self.assertEqual(_zhegai_miyao('sk-abcdefgh1234'), 'sk-a****')
        self.assertEqual(_zhegai_miyao('abc'), '****')


class TestCuowuFanyi(unittest.TestCase):
    """异常翻译：urllib 原生错误 → MoxingCuowu 中文信息。

    llm_clean.zhineng_fenliu 按异常走降级，中文信息直接呈现给用户排障。
    """

    def test_wangluo_cuowu(self) -> None:
        """URLError（断网/超时）→ 中文网络错误提示。"""
        # OSError 是 URLError 的常见内部原因（超时的真实形态）
        bo_hui = urllib.error.URLError(OSError('timed out'))
        fasong, _ = zhuangzhu_fasong(bo_hui=bo_hui)
        hanshu = chuangjian_moxing_hanshu(JIAMIYAO, fasong=fasong)
        with self.assertRaises(MoxingCuowu) as cuo:
            hanshu('x')
        self.assertIn('网络错误', str(cuo.exception))

    def test_fei_json_xiangying(self) -> None:
        """响应不是 JSON → 响应格式异常。"""
        # 字节串字面量不能含中文（语法限制），用字符串 encode 代替
        fasong, _ = zhuangzhu_fasong(xiangying='<html>网关错误</html>'.encode('utf-8'))
        hanshu = chuangjian_moxing_hanshu(JIAMIYAO, fasong=fasong)
        with self.assertRaises(MoxingCuowu) as cuo:
            hanshu('x')
        self.assertIn('响应格式异常', str(cuo.exception))

    def test_jiegou_que_shi(self) -> None:
        """JSON 合法但缺 choices（非 OpenAI 兼容结构）→ 同样报格式异常。"""
        fasong, _ = zhuangzhu_fasong(xiangying=b'{"error": "x"}')
        hanshu = chuangjian_moxing_hanshu(JIAMIYAO, fasong=fasong)
        with self.assertRaises(MoxingCuowu):
            hanshu('x')


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_model_api.py
    unittest.main()
