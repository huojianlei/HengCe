# -*- coding: utf-8 -*-
"""模型 API 调用器 —— DeepSeek（OpenAI 兼容协议）真模型接线。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

设计定位（用户指令 2026-08-23："测试的时候是给真模型的，留个输入口给
前端调用，用来输入 apikey"）：
    本模块是【前端输入口】：界面拿到用户输入的 API Key 后调用
    chuangjian_moxing_hanshu(api_miyao=用户输入)，得到一个
    moxing_hanshu（Callable[[str], str]），直接喂给 llm_clean 的
    zhineng_fenliu 即可完成真模型归一化。接线链路：

        前端密钥输入框 → chuangjian_moxing_hanshu(api_miyao=...)
                       → zhineng_fenliu(乱文本, moxing_hanshu)

密钥纪律（docs\\03 §6 安全要点，强制）：
    1. 密钥只经【参数】进入，本模块不落盘、不写日志、不进任何文件；
    2. 错误信息里永不出现密钥全文（仅遮盖展示，见 _zhegai_miyao）；
    3. 命令行测试建议用环境变量 FINAGENT_API_KEY 传入（避免留在
       Shell 历史里）；--miyao 参数仅为应急，注释中有提醒。

零依赖：网络调用用标准库 urllib（不装 requests）；协议为 OpenAI 兼容
chat/completions，换端点/换模型只改参数（ADR-02：不写死供应商 SDK）。

默认模型 deepseek-v4-flash（用户指定；正式选型待 Q4 拍板，届时只改
MOREN_MOXING_MING 一处）。归一化任务取 temperature=0（结构翻译要
确定性，不要创造性）。

可测试性：真实 HTTPS 发送器（_fasong_https）可经 fasong 参数注入
假实现——单元测试与 doctest 全部离线运行，不打真接口。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests\\test_demos.py 守护；真接口端到端测试见 examples\\ceshi_moxing.py）：

    知识点 1 · 创建模型函数（注入假发送器演示，离线）
    >>> def jia_fasong(qingqiu, chaozhi_miao):
    ...     return '{"choices": [{"message": {"content": "翻译结果"}}]}'.encode('utf-8')
    >>> hanshu = chuangjian_moxing_hanshu('sk-cecshi123', fasong=jia_fasong)
    >>> hanshu('把乱表格转成标准CSV')
    '翻译结果'

    知识点 2 · 密钥遮盖：错误信息里永不露全文
    >>> from model_api import _zhegai_miyao
    >>> _zhegai_miyao('sk-abcdefgh1234')
    'sk-a****'

命名对照表（拼音标识符 → 中文含义）：
    chuangjian_moxing_hanshu   创建模型函数（前端输入口：密钥从这进）
    MoxingCuowu                模型错误（网络/鉴权/响应格式，统一异常）
    cong_huanjing_duqu_miyao   从环境读取密钥（FINAGENT_API_KEY）
    _zhegai_miyao              遮盖密钥（展示用，只露前 4 位）
    _fasong_https              发送 HTTPS（默认真发送器，可注入替换）
    api_miyao                  API 密钥（参数名，前端传这个）
    jiekou_dizhi / moxing_ming 接口地址 / 模型名（均可配置）
    chaozhi_miao / wendu       超时秒数 / 温度（默认 60 / 0）
    fasong                     发送器（Callable 注入口，测试用）

口径依据：docs\\02 架构 ADR-02（OpenAI 兼容、不写死 SDK）、Q4（模型选型
         待定）、TODO T-19（API Key 仍待用户提供）、docs\\03 §6（密钥安全）。
建立：2026-08-23 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

# ======================================================================
# 常量区
# ======================================================================

#: 默认接口地址（DeepSeek 官方 OpenAI 兼容端点；换供应商改这里或传参）
MOREN_JIEKOU_DIZHI = 'https://api.deepseek.com'

#: 默认模型名（用户指定的快模型；正式选型待 Q4，届时只改这一处）
MOREN_MOXING_MING = 'deepseek-v4-flash'

#: 环境变量名：命令行测试时由此传入密钥（避免密钥留在 Shell 历史里）
HUANJING_MIAOYAO_BIANLIANG = 'FINAGENT_API_KEY'

#: 发送器类型别名：接收（请求对象, 超时秒），返回响应字节串
FasongQi = Callable[[urllib.request.Request, float], bytes]


class MoxingCuowu(RuntimeError):
    """模型调用失败（网络 / 鉴权 / 响应格式）——统一异常类型。

    llm_clean.zhineng_fenliu 捕获一切异常走降级路径，本异常的中文
    信息会原样带给用户（人工排障用）。密钥全文永不出现在信息里。
    """

    pass  # 无附加行为，仅作类型标识


# ======================================================================
# 内部工具函数区
# ======================================================================


def _zhegai_miyao(miyao: str) -> str:
    """遮盖密钥：只保留前 4 位 + ****（展示与排障用，绝不露全文）。"""
    if len(miyao) <= 4:
        return '****'  # 过短的密钥整体遮盖
    return miyao[:4] + '****'


def cong_huanjing_duqu_miyao() -> str | None:
    """从环境变量读取密钥（FINAGENT_API_KEY）；未设置返回 None。

    用途：命令行测试的免参入口；前端场景不靠它（前端走参数传入）。
    """
    return os.environ.get(HUANJING_MIAOYAO_BIANLIANG) or None


def _fasong_https(qingqiu: urllib.request.Request, chaozhi_miao: float) -> bytes:
    """默认真发送器：urllib 发 HTTPS 请求并返回响应字节串。

    超时/网络/HTTP 错误会以 urllib 原生异常抛出，由上层包装成
    MoxingCuowu（中文信息）。测试时经 fasong 参数注入假实现替换。
    """
    with urllib.request.urlopen(qingqiu, timeout=chaozhi_miao) as xiangying:
        return xiangying.read()


# ======================================================================
# 对外接口区（本模块唯一的公开工厂）
# ======================================================================


def chuangjian_moxing_hanshu(
    api_miyao: str | None = None,
    jiekou_dizhi: str = MOREN_JIEKOU_DIZHI,
    moxing_ming: str = MOREN_MOXING_MING,
    chaozhi_miao: float = 60.0,
    wendu: float = 0.0,
    fasong: FasongQi | None = None,
) -> Callable[[str], str]:
    """创建真模型调用函数（前端输入口：API Key 从这个参数进系统）。

    参数：
        api_miyao:    API 密钥。前端把用户输入的密钥传这里；
                      缺省时回退读环境变量 FINAGENT_API_KEY（命令行测试用）。
        jiekou_dizhi: OpenAI 兼容端点（默认 DeepSeek 官方）。
        moxing_ming:  模型名（默认 deepseek-v4-flash，选型待 Q4）。
        chaozhi_miao: 请求超时秒数（默认 60）。
        wendu:        采样温度（默认 0——格式归一化要确定性，不要创造性）。
        fasong:       发送器注入（测试用；缺省用真 HTTPS 发送器）。

    返回：
        moxing_hanshu(tishi) -> str：喂给 llm_clean.zhineng_fenliu 的
        Callable；内部完成 请求构造 → 发送 → 响应解析 → 取回复文本。

    失败语义（全部抛 MoxingCuowu，密钥全文永不入信息）：
        无密钥 / HTTP 4xx-5xx（鉴权、额度）/ 网络错误 / 响应格式异常。
    """
    # ---- 密钥解析：参数优先，环境变量兜底，两者皆无则明确报错 ----
    miyao = api_miyao or cong_huanjing_duqu_miyao()
    if not miyao:
        raise MoxingCuowu(
            '未提供 API Key：请前端经 api_miyao 参数传入，'
            f'或设置环境变量 {HUANJING_MIAOYAO_BIANLIANG}'
        )

    fasongqi = fasong if fasong is not None else _fasong_https

    def moxing_hanshu(tishi: str) -> str:
        """单次调用：提示词进、回复文本出（闭包持有密钥与配置）。"""
        # 请求体：OpenAI 兼容 chat/completions（非流式；system 提示随 tishi 由上层拼好）
        qingqiu_ti = {
            'model': moxing_ming,
            'temperature': wendu,
            'stream': False,
            'messages': [{'role': 'user', 'content': tishi}],
        }
        qingqiu = urllib.request.Request(
            jiekou_dizhi.rstrip('/') + '/chat/completions',
            data=json.dumps(qingqiu_ti, ensure_ascii=False).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {miyao}',  # 密钥只进请求头，不进任何日志
            },
            method='POST',
        )
        try:
            yuanshi = fasongqi(qingqiu, chaozhi_miao)
        except urllib.error.HTTPError as cuo:
            # 4xx/5xx：常见为鉴权失败(401)或额度不足(402/429)
            raise MoxingCuowu(
                f'接口返回 HTTP {cuo.code}（密钥 {_zhegai_miyao(miyao)}）：请检查密钥有效性与余额'
            ) from cuo
        except urllib.error.URLError as cuo:
            # 网络层失败：断网/DNS/超时等
            raise MoxingCuowu(f'网络错误：{cuo.reason}；请检查网络或接口地址 {jiekou_dizhi}') from cuo

        # ---- 响应解析：取 choices[0].message.content ----
        try:
            shuju = json.loads(yuanshi.decode('utf-8'))
            return shuju['choices'][0]['message']['content']
        except (ValueError, KeyError, IndexError, TypeError) as cuo:
            # JSON 坏了 / 结构不符（非 OpenAI 兼容响应）
            raise MoxingCuowu('响应格式异常（非预期的 JSON 结构）；请确认端点为 OpenAI 兼容接口') from cuo

    return moxing_hanshu
