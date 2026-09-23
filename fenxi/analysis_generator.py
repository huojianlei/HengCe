# -*- coding: utf-8 -*-
"""分析生成器 —— M5 分析层第③步：系数包 + 条文片段 → 整改文案与报告解读。

定位（分析层六步计划 2026-08-30 用户拍板"执行"）：
    输入 = 判定系数包（JSON 形态） + 检索适配的条文片段 + 整改清单
    输出 = 逐条整改建议文案 + 报告解读段落（全部经校验闸门后才放行）
    模型调用 = 注入式（moxing_hanshu 参数，与 llm_clean 同手法；
    生产接线注入 model_api 产出的真模型，测试注入假函数，None = 降级）

防幻觉校验闸门（RAG 方案 §4 的代码化——硬要求，不是提示词里的客套话）：
    ① 条号真实：输出里引用的每个条号（'200-3' 式）必须出现在检索片段
       的定位串集合里——编造条号 = 该段打回；
    ② 数字溯源：输出里的每个数字（剥千分位、小数尾零等价后）必须能在
       【事实】系数包、【任务】整改清单或【依据】条文原文中逐字找到——
       凭空数字 = 该段打回；
    ③ 未检到明说：检索片段为空时提示词明令输出"未检索到直接依据"；
    ④ 分层输出：解析【报告解读】与【整改建议】两个区，逐条对应整改项。
    打回的段落不静默丢弃——替换为降级文案并记录拒因（链路诚实）。

降级口径（全项目一致）：
    moxing_hanshu=None（未配 Key/模型不可用）→ 全部文案 = '— 待 AI 分析
    （未配置模型）'，zhuangtai='降级'——数据与结论（系数包/整改清单）
    不受影响，界面照常可读。

命名规范：标识符无声调拼音；文件名英文；数据值中文。
纯函数：无 I/O、无全局状态（模型函数注入）。

使用示例（知识点速览；doctest 格式，tests 守护）：

    知识点 1 · 真引用 + 数字照抄 → 通过
    >>> from analysis_generator import shengcheng_fenxi
    >>> xishu = {'wanchenglv_bps': 10347, 'panduan_jielun': '混合纠错模式',
    ...          'shenpi': True, 'hexin_mokuai': '采购模块',
    ...          'bsc_zongfen': 88, 'bsc_dengji': '良好',
    ...          'hong_hang_lie': [['2026-Q1', '办公费', 2450, 'A']]}
    >>> tiaowen = [{'dingwei': '200-3', 'neirong': '企业应当建立预算执行分析制度，预算完成率 10347。'}]
    >>> zhenggai = [{'leixing': '强制整改', 'zeren_mokuai': '费用模块',
    ...              'kemu': '办公费', 'miaoshu': '办公费 2450 基点红预警'}]
    >>> def hao_moxing(t):
    ...     return ('【报告解读】整体完成率 10347 基点，结论混合纠错模式。\\n'
    ...             '【整改建议】\\n1. 依据 200-3 建立预算执行分析制度，管控办公费。\\n'
    ...             '   本条无额外数字。')
    >>> jieguo = shengcheng_fenxi(xishu, tiaowen, zhenggai, hao_moxing)
    >>> jieguo.zhuangtai
    '成功'
    >>> jieguo.wenan_lie[0].jiaoyan
    '通过'

    知识点 2 · 编造条号 → 该段打回（降级文案顶上，拒因记录）
    >>> def huai_moxing(t):
    ...     return ('【报告解读】整体完成率 10347 基点。\\n'
    ...             '【整改建议】\\n1. 依据 999-9 立即整改。\\n')
    >>> jieguo2 = shengcheng_fenxi(xishu, tiaowen, zhenggai, huai_moxing)
    >>> (jieguo2.wenan_lie[0].jiaoyan, jieguo2.zhuangtai)
    ('拒绝', '部分拒绝')

    知识点 3 · 无模型 → 降级（清单照常，文案占位）
    >>> jieguo3 = shengcheng_fenxi(xishu, tiaowen, zhenggai, None)
    >>> (jieguo3.zhuangtai, jieguo3.wenan_lie[0].wenan)
    ('降级', '— 待 AI 分析（未配置模型）')

    知识点 4 · 只在整改清单里的数字 + 小数尾零写法 → 通过
    （2026-08-31 误杀修复：清单喂给了模型，闸门却只认系数包+条文——
      '774.00'（清单）照抄成 '774'（文案）必须放行）
    >>> qingdan4 = [{'leixing': '关注整改', 'zeren_mokuai': '费用模块',
    ...              'kemu': '差旅费', 'miaoshu': '差旅费超支 774.00 元'}]
    >>> def qingdan_moxing(t):
    ...     return ('【报告解读】整体研判为混合纠错模式。\\n'
    ...             '【整改建议】\\n1. 依据 200-3 管控差旅费，超支 774 元纳入下期预算。\\n')
    >>> jieguo4 = shengcheng_fenxi(xishu, tiaowen, qingdan4, qingdan_moxing)
    >>> jieguo4.wenan_lie[0].jiaoyan
    '通过'

命名对照表（拼音标识符 → 中文含义）：
    shengcheng_fenxi    生成分析（主函数：提示词 → 模型 → 校验 → 结构化结果）
    gouzao_tishi        构造提示词（角色 + 事实 + 依据 + 任务 + 铁律）
    FenxiJieguo         分析结果（状态/解读/逐条文案）
    WenanXiang          文案项（对应一条整改项：文案 + 校验状态 + 拒因）
    _jiexi_shuchu       解析输出（拆【报告解读】/【整改建议】，按序对应整改项）
    _jiaoyan_yiduan     校验一段（条号真实 + 数字溯源，返回状态与违禁清单）
    _yunxu_shuzi        允许数字集（系数包 + 整改清单 + 条文原文 + 定位串）
    _shuzi_guifan       数字归一（去前导零 + 剥小数尾零——'6660.00' ≡ '6660'）
    xishu_miyao         系数包（JSON dict 形态——与落盘的判定系数*.json 同构）
    tiaowen_lie         条文片段列表（检索适配层的产出）
    zhenggai_lie        整改清单（看板 JSON 的 zhenggai_block.qingdan）
    moxing_hanshu       模型函数（Callable 注入；None = 降级）
    weijin_lie          违禁清单（未溯源数字/编造条号——拒因的事实记录）

口径依据：分析层六步计划③（用户拍板 2026-08-30）；kb2/RAG部署与使用方案.md
         §4（校验闸门四条硬要求 + 输出分层）；algo/llm_clean（数字溯源手法）；
         algo/xishu.py（系数包的生产者，字段以落盘 JSON 为准）。
建立：2026-08-30 ｜ Agent：ZCode（GLM-5.3）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: 条号引用形态：'200-3' / '200-3-P2'（与 retrieval_adapter 的定位串同源）
_TIAOHAO_ZE = re.compile(r'\b(\d{2,3}-\d{1,3}(?:-P\d+)?)\b')
#: 数字形态（千分位逗号在提取前先剥离）
_SHUZI_ZE = re.compile(r'\d+(?:\.\d+)?')
#: 逗号夹在两个数字之间才算千分位——剥它，不动中文逗号
_QIANFEN_ZE = re.compile(r'(?<=\d),(?=\d)')

#: 降级占位文案（数据与结论照常，仅文案缺位——全项目可降级口径）
JIANGJI_WENAN = '— 待 AI 分析（未配置模型）'


@dataclass(frozen=True)
class WenanXiang:
    """一条整改建议文案：对应整改清单中的一条（校验不过 = 降级文案顶上）。"""

    xuhao: int            # 对应整改清单的序号（1 起）
    leixing: str          # 整改类型（透传：强制整改/预算修订案/……）
    zeren_mokuai: str     # 责任模块（透传）
    wenan: str            # 文案本体（通过 = 模型产出；拒绝/缺位 = 降级文案）
    jiaoyan: str          # 校验状态（'通过' / '拒绝' / '未输出' / '—'）
    weijin_lie: tuple     # 违禁事实（未溯源数字/编造条号清单；通过则为空）


@dataclass(frozen=True)
class FenxiJieguo:
    """分析结果：解读段 + 逐条文案 + 总状态（'成功'/'部分拒绝'/'降级'）。"""

    zhuangtai: str
    jiedu: str                    # 报告解读段落（模型产出；降级 = 占位文案）
    jiedu_jiaoyan: str            # 解读段校验状态
    wenan_lie: tuple              # WenanXiang 元组（与整改清单等长、同序）
    tishi_yuanwen: str = field(default='', compare=False)   # 送模型的原始提示词（排障用）


def _shuzi_guifan(shu: str) -> str:
    """数字归一：先剥小数尾零，再去前导零——文案与事实两侧同规则才可比。

    >>> _shuzi_guifan('6660.00')      # 小数尾零等价（2026-08-31 误杀修复）
    '6660'
    >>> _shuzi_guifan('7762.50')
    '7762.5'
    >>> _shuzi_guifan('10347')
    '10347'
    >>> _shuzi_guifan('08')           # 前导零等价（原有口径）
    '8'
    >>> _shuzi_guifan('0.50')
    '0.5'
    >>> _shuzi_guifan('0.0')
    '0'
    """
    if '.' in shu:
        shu = shu.rstrip('0').rstrip('.')
    return shu.lstrip('0') or '0'


def _yunxu_shuzi(xishu_miyao: dict, tiaowen_lie: list,
                 zhenggai_lie: list | None = None) -> set[str]:
    """允许数字集：系数包 JSON 全部数字 + 整改清单数字 + 条文原文数字 + 定位串数字。

    提取前统一剥千分位逗号（模型照抄 '10,347' 与事实里的 10347 等价）；
    定位串（'200-3'）拆出的 200/3 也算允许——条号引用本身合法。
    zhenggai_lie（整改清单）2026-08-31 入集：清单金额本来就喂给模型
    （提示词【任务】区），照抄清单数字不该被拒——此前漏集致 10/11 文案误杀。
    """
    laiyuan_lie = [json_dumps(xishu_miyao)]
    if zhenggai_lie:
        laiyuan_lie.append(json_dumps(list(zhenggai_lie)))
    laiyuan_lie += [t['neirong'] for t in tiaowen_lie]
    laiyuan_lie += [t['dingwei'] for t in tiaowen_lie]
    yunxu: set[str] = set()
    for laiyuan in laiyuan_lie:
        for shu in _SHUZI_ZE.findall(_QIANFEN_ZE.sub('', laiyuan)):
            yunxu.add(_shuzi_guifan(shu))
    return yunxu


def _jiaoyan_yiduan(wenben: str, tiaowen_lie: list, yunxu_shuzi: set[str]) -> tuple[str, tuple]:
    """校验一段文案：先条号真实、再数字溯源。返回（状态, 违禁清单）。

    条号真实：文案引用的条号 ⊆ 检索片段定位串集合（编造 = 打回，RAG §4①）；
    数字溯源：文案数字 ⊆ 允许数字集（凭空数字 = 打回，RAG §4②）。
    """
    dingwei_ji = {t['dingwei'] for t in tiaowen_lie}
    weijin: list[str] = []
    for tiaohao in _TIAOHAO_ZE.findall(_QIANFEN_ZE.sub('', wenben)):
        if tiaohao not in dingwei_ji:
            weijin.append(f'编造条号 {tiaohao}')
    for shu in _SHUZI_ZE.findall(_QIANFEN_ZE.sub('', wenben)):
        guifan = _shuzi_guifan(shu)
        if guifan not in yunxu_shuzi:
            weijin.append(f'未溯源数字 {shu}')
    if weijin:
        return '拒绝', tuple(weijin)
    return '通过', ()


def json_dumps(duixiang) -> str:
    """dict → JSON 文本（ensure_ascii=False——中文字面进入提示词与数字集）。"""
    import json
    return json.dumps(duixiang, ensure_ascii=False, indent=2, default=str)


def _jiexi_shuchu(raw: str, zhenggai_lie: list[dict]) -> tuple[str, list[tuple[int | None, str]]]:
    """解析模型输出：解读段 + 编号建议块（块序号 → 整改清单序号）。

    约定输出格式（提示词已明令）：【报告解读】……【整改建议】+ 逐条
    '数字.' 开头的建议。解析宽容：没按格式来的块保持原文归属到第 1 条。
    返回（解读段, [(清单序号 1 起 or None, 建议文本)]）。
    """
    if '【整改建议】' in raw:
        jiedu, _, jianyi_qu = raw.partition('【整改建议】')
    else:
        jiedu, jianyi_qu = raw, ''
    jiedu = jiedu.replace('【报告解读】', '').strip()
    kuai_lie: list[tuple[int | None, str]] = []
    dang_qian_xu: int | None = None
    dang_qian_hang: list[str] = []
    for hang in jianyi_qu.split('\n'):
        tou = re.match(r'^\s*(\d+)\s*[.、）\)]\s*(.*)$', hang)
        if tou:
            if dang_qian_hang:
                kuai_lie.append((dang_qian_xu, '\n'.join(dang_qian_hang).strip()))
            dang_qian_xu = int(tou.group(1))
            dang_qian_hang = [tou.group(2)]
        elif hang.strip() and dang_qian_hang:
            dang_qian_hang.append(hang.strip())
    if dang_qian_hang:
        kuai_lie.append((dang_qian_xu, '\n'.join(dang_qian_hang).strip()))
    # 清单序号越界的块归 None（提示词给了 N 条、模型多写的不硬塞）
    kuai_lie = [(xu if xu is not None and 1 <= xu <= len(zhenggai_lie) else None, wen)
                for xu, wen in kuai_lie]
    return jiedu, kuai_lie


def gouzao_tishi(xishu_miyao: dict, tiaowen_lie: list, zhenggai_lie: list[dict]) -> str:
    """构造提示词：角色 + 【事实】+【依据】+【任务】+ 铁律（§4 输出分层）。"""
    yi_ju_qu = '\n'.join(
        f"[{t['dingwei']}] {t['neirong']}" for t in tiaowen_lie
    ) or '（未检索到直接依据——如无把握，请如实写"未检索到直接依据"）'
    qingdan_qu = '\n'.join(
        f"{i}. [{x.get('leixing', '')}｜{x.get('zeren_mokuai', '')}] "
        f"{x.get('kemu') or ''}{x.get('miaoshu', '')}"
        for i, x in enumerate(zhenggai_lie, start=1))
    return (
        '你是企业预算管理分析师。只依据下方【事实】与【依据】作答，禁止使用任何外部知识。\n\n'
        f'【事实】判定系数包：\n{json_dumps(xishu_miyao)}\n\n'
        f'【依据】检索到的官方条文（只可引用下列条号）：\n{yi_ju_qu}\n\n'
        f'【任务】待整改清单：\n{qingdan_qu}\n\n'
        '请输出：\n'
        '【报告解读】结合完成率、单双环结论、核心问题模块与 BSC 评级写一段整体解读；\n'
        '【整改建议】为上方清单逐条写建议（编号与清单序号一一对应），'
        '每条引用依据时标注条号（如 200-3）。\n\n'
        '铁律：数字必须原样照抄【事实】、【依据】或【任务】清单，禁止换算、四舍五入、编造；'
        '只可引用【依据】中列出的条号；没有依据支撑的判断，请写"未检索到直接依据"。')


def shengcheng_fenxi(xishu_miyao: dict, tiaowen_lie: list, zhenggai_lie: list[dict],
                     moxing_hanshu) -> FenxiJieguo:
    """分析生成主函数：提示词 → 注入的模型 → 校验闸门 → 结构化结果。

    降级链路：moxing_hanshu=None → 全部占位（'— 待 AI 分析'），状态'降级'；
    校验闸门：逐块条号真实 + 数字溯源，拒绝块以降级文案顶上并记录拒因
    （状态'部分拒绝'）；全部通过 = '成功'。输出与整改清单等长同序。
    """
    if moxing_hanshu is None:
        wenan_lie = tuple(
            WenanXiang(xuhao=i + 1, leixing=x.get('leixing', ''),
                       zeren_mokuai=x.get('zeren_mokuai', ''),
                       wenan=JIANGJI_WENAN, jiaoyan='—', weijin_lie=())
            for i, x in enumerate(zhenggai_lie))
        return FenxiJieguo(zhuangtai='降级', jiedu=JIANGJI_WENAN,
                           jiedu_jiaoyan='—', wenan_lie=wenan_lie)
    tishi = gouzao_tishi(xishu_miyao, tiaowen_lie, zhenggai_lie)
    raw = moxing_hanshu(tishi)
    yunxu = _yunxu_shuzi(xishu_miyao, tiaowen_lie, zhenggai_lie)
    jiedu, kuai_lie = _jiexi_shuchu(raw, zhenggai_lie)
    jiedu_zhuangtai, jiedu_weijin = _jiaoyan_yiduan(jiedu, tiaowen_lie, yunxu)
    if jiedu_zhuangtai == '拒绝':
        jiedu = f'— 待 AI 分析（解读未通过校验：{"；".join(jiedu_weijin)}）'
    # 逐条文案：优先取模型按编号写的块；没写的条目占位
    an_xuhao = {xu: wen for xu, wen in kuai_lie if xu is not None}
    wenan_lie: list[WenanXiang] = []
    ju_jue_shu = 0
    for i, x in enumerate(zhenggai_lie, start=1):
        if i in an_xuhao:
            zhuangtai, weijin = _jiaoyan_yiduan(an_xuhao[i], tiaowen_lie, yunxu)
            wenan = an_xuhao[i] if zhuangtai == '通过' else \
                f'— 待人工分析（AI 文案未通过校验：{"；".join(weijin)}）'
            if zhuangtai == '拒绝':
                ju_jue_shu += 1
            wenan_lie.append(WenanXiang(
                xuhao=i, leixing=x.get('leixing', ''),
                zeren_mokuai=x.get('zeren_mokuai', ''), wenan=wenan,
                jiaoyan=zhuangtai, weijin_lie=weijin))
        else:
            wenan_lie.append(WenanXiang(
                xuhao=i, leixing=x.get('leixing', ''),
                zeren_mokuai=x.get('zeren_mokuai', ''),
                wenan='— 待 AI 分析（模型未输出该条）', jiaoyan='未输出', weijin_lie=()))
    zhuangtai = '成功' if ju_jue_shu == 0 and jiedu_zhuangtai == '通过' else '部分拒绝'
    return FenxiJieguo(zhuangtai=zhuangtai, jiedu=jiedu, jiedu_jiaoyan=jiedu_zhuangtai,
                       wenan_lie=tuple(wenan_lie), tishi_yuanwen=tishi)
