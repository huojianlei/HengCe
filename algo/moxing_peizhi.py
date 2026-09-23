# -*- coding: utf-8 -*-
"""模型配置管理器 —— 前端可运行时修改 API Key 与 AI 参数的接口。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

设计定位（用户指令 2026-08-23："留个接口用于修改 apikey 和 ai 配置参数"）：
    前端持有一个 PeizhiGuanliqi（配置管理器）实例，三个方法即全部接口：

        guanliqi = PeizhiGuanliqi()                  # 初始化（自动读环境变量兜底）
        guanliqi.dangqian()                          # 查看当前配置（密钥只露遮盖形态）
        guanliqi.gengxin(api_miyao=新Key, wendu=0.2)  # 改哪个传哪个，即时生效
        hanshu = guanliqi.chuangjian()               # 按当前配置生成模型调用函数

    前端接线图（将来 M6 界面层照此接）：
        设置页输入框提交 → guanliqi.gengxin(api_miyao=用户输入) → 立即 chuangjian()
        即可让后续 zhineng_fenliu 全部走新配置——无需重启、无全局变量。

密钥纪律（延续 model_api，强制）：
    1. 密钥只在管理器实例内存里；本模块【不落盘、不写日志】；
       持久化将来走 dsh credentials 机制（M2 层立项），当前为运行时配置。
    2. dangqian() 返回的展示结构里只有遮盖形态密钥（sk-a****），
       全文仅 chuangjian() 内部使用（进请求头）。
    3. gengxin 校验：密钥非空字符串；温度 [0,2]；超时 >0——脏配置进不来。

状态说明（诚实声明）：管理器是【实例级可变状态】（非模块级全局单例），
    属 algo 层对"运行时配置"的受控例外——状态由调用方显式持有与传递，
    不隐藏在全局变量里；测试仍可完全离线与并行。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests\\test_demos.py 守护）：

    知识点 1 · 建管理器 + 查看配置（密钥自动遮盖）
    >>> from moxing_peizhi import PeizhiGuanliqi
    >>> guanliqi = PeizhiGuanliqi(api_miyao='sk-abc123456')
    >>> xinxi = guanliqi.dangqian()
    >>> (xinxi.api_miyao_zhegai, xinxi.moxing_ming, xinxi.wendu)
    ('sk-a****', 'deepseek-v4-flash', 0.0)

    知识点 2 · 改哪个传哪个（部分更新，即时生效）
    >>> _ = guanliqi.gengxin(wendu=0.3, moxing_ming='deepseek-v4-pro')
    >>> guanliqi.dangqian().moxing_ming, guanliqi.dangqian().wendu
    ('deepseek-v4-pro', 0.3)

    知识点 3 · 按当前配置生成模型函数（注入假发送器离线演示）
    >>> def jia_fasong(qingqiu, chaozhi_miao):
    ...     return '{"choices": [{"message": {"content": "ok"}}]}'.encode('utf-8')
    >>> hanshu = guanliqi.chuangjian(fasong=jia_fasong)
    >>> hanshu('提示词')
    'ok'

    知识点 4 · 脏配置被拒（密钥空 / 温度越界 / 超时非正）
    >>> try:
    ...     guanliqi.gengxin(wendu=9.0)
    ... except Exception as cuo:
    ...     print(type(cuo).__name__)
    PeizhiCuowu

命名对照表（拼音标识符 → 中文含义）：
    PeizhiGuanliqi    配置管理器（前端持有；运行时改配置的唯一入口）
    PeizhiXinxi       配置信息（展示结构：密钥只有遮盖形态）
    PeizhiCuowu       配置错误（校验失败异常）
    gengxin           更新（部分更新：改哪个传哪个）
    dangqian          当前（查看配置，返回遮盖版）
    chuangjian        创建（按当前配置生成模型调用函数）
    api_miyao_zhegai  API密钥遮盖形态（展示用字段名）

口径依据：docs\\02 ADR-02（端点/模型可配置）、docs\\03 §6（密钥安全）、
         TODO T-19/Q4（模型名 deepseek-v4-flash 已真跑验证 2026-08-23）。
建立：2026-08-23 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

# 复用模型调用器：工厂、默认值与密钥遮盖函数（单一事实源，不在本模块重复定义）
from model_api import (
    MOREN_JIEKOU_DIZHI,
    MOREN_MOXING_MING,
    _zhegai_miyao,
    chuangjian_moxing_hanshu,
    cong_huanjing_duqu_miyao,
)


class PeizhiCuowu(ValueError):
    """配置校验失败（密钥空 / 温度越界 / 超时非正 / 字段名不认识）。

    继承 ValueError：前端表单校验可按脏输入统一捕获处理。
    """

    pass  # 无附加行为，仅作类型标识


@dataclass(frozen=True)
class PeizhiXinxi:
    """配置信息（展示结构）——给前端渲染用的"安全视图"。

    与内部配置的区别：api_miyao 字段换成遮盖形态（api_miyao_zhegai），
    从结构上杜绝"查看配置时把密钥全文带出去"的事故。
    """

    api_miyao_zhegai: str   # 遮盖密钥（sk-a****）；全文永不出现在此结构
    jiekou_dizhi: str       # 接口地址
    moxing_ming: str        # 模型名
    chaozhi_miao: float     # 超时秒数
    wendu: float            # 采样温度


@dataclass(frozen=True)
class _NeibuPeizhi:
    """内部配置（持有密钥全文；仅模块内使用，不对外返回）。"""

    api_miyao: str
    jiekou_dizhi: str = MOREN_JIEKOU_DIZHI
    moxing_ming: str = MOREN_MOXING_MING
    chaozhi_miao: float = 60.0
    wendu: float = 0.0


class PeizhiGuanliqi:
    """配置管理器：前端运行时修改 Key 与 AI 参数的唯一入口。

    用法见模块头"知识点速览"；线程安全说明：比赛演示为单线程交互，
    未加锁（多线程前端接入时由调用方自行串行化 gengxin/chuangjian）。
    """

    def __init__(self, api_miyao: str | None = None) -> None:
        """初始化：显式密钥优先，缺省回退读环境变量 FINAGENT_API_KEY。"""
        miyao = api_miyao or cong_huanjing_duqu_miyao()
        if not miyao:
            # 允许先建管理器后补 Key（gengxin 再传），但 dangqian/chuangjian 前必须补上
            miyao = ''
        self._peizhi = _NeibuPeizhi(api_miyao=miyao)

    # ------------------------------------------------------------------
    # 查看（安全视图）
    # ------------------------------------------------------------------

    def dangqian(self) -> PeizhiXinxi:
        """返回当前配置的安全视图（密钥只有遮盖形态）。"""
        return PeizhiXinxi(
            api_miyao_zhegai=_zhegai_miyao(self._peizhi.api_miyao) if self._peizhi.api_miyao else '（未设置）',
            jiekou_dizhi=self._peizhi.jiekou_dizhi,
            moxing_ming=self._peizhi.moxing_ming,
            chaozhi_miao=self._peizhi.chaozhi_miao,
            wendu=self._peizhi.wendu,
        )

    # ------------------------------------------------------------------
    # 修改（部分更新：改哪个传哪个）
    # ------------------------------------------------------------------

    def gengxin(self, **xiang: object) -> PeizhiXinxi:
        """部分更新配置并返回新的安全视图；非法取值抛 PeizhiCuowu。

        可更新字段（与模型调用器参数一一对应）：
            api_miyao（密钥）/ jiekou_dizhi（端点）/ moxing_ming（模型名）
            / chaozhi_miao（超时秒，>0）/ wendu（温度，[0,2]）
        未知字段名直接报错（防前端拼错字段名导致"改了没生效"）。
        """
        if not xiang:
            raise PeizhiCuowu('gengxin 至少传一个字段（空更新无意义）')
        # 先在副本上做全部校验，全过才落盘到实例（原子性：脏配置半途不改状态）
        xin = self._peizhi
        for mingzi, zhi in xiang.items():
            if mingzi not in ('api_miyao', 'jiekou_dizhi', 'moxing_ming', 'chaozhi_miao', 'wendu'):
                raise PeizhiCuowu(f'未知配置字段：{mingzi}')
            if mingzi == 'api_miyao':
                if not isinstance(zhi, str) or not zhi.strip():
                    raise PeizhiCuowu('api_miyao 必须为非空字符串')
                zhi = zhi.strip()
            elif mingzi == 'wendu':
                if not isinstance(zhi, (int, float)) or isinstance(zhi, bool) or not (0 <= zhi <= 2):
                    raise PeizhiCuowu('wendu 必须为 [0, 2] 内的数字（归一化建议 0）')
                zhi = float(zhi)
            elif mingzi == 'chaozhi_miao':
                if not isinstance(zhi, (int, float)) or isinstance(zhi, bool) or zhi <= 0:
                    raise PeizhiCuowu('chaozhi_miao 必须为正数（秒）')
                zhi = float(zhi)
            elif not isinstance(zhi, str) or not zhi.strip():
                raise PeizhiCuowu(f'{mingzi} 必须为非空字符串')
            xin = replace(xin, **{mingzi: zhi})
        self._peizhi = xin  # 全部校验通过才提交（见上方原子性说明）
        return self.dangqian()

    # ------------------------------------------------------------------
    # 生效（按当前配置创建模型调用函数）
    # ------------------------------------------------------------------

    def chuangjian(self, fasong: Callable | None = None) -> Callable[[str], str]:
        """按当前配置生成模型调用函数（喂给 llm_clean.zhineng_fenliu）。

        fasong 参数为测试注入口（与 model_api 工厂一致）；前端不传。
        密钥未设置时抛 PeizhiCuowu（指引先 gengxin 或设环境变量）。
        """
        if not self._peizhi.api_miyao:
            raise PeizhiCuowu('API Key 未设置：请先 gengxin(api_miyao=...) 或设置环境变量')
        return chuangjian_moxing_hanshu(
            api_miyao=self._peizhi.api_miyao,          # 密钥全文只进这里（→请求头）
            jiekou_dizhi=self._peizhi.jiekou_dizhi,
            moxing_ming=self._peizhi.moxing_ming,
            chaozhi_miao=self._peizhi.chaozhi_miao,
            wendu=self._peizhi.wendu,
            fasong=fasong,
        )
