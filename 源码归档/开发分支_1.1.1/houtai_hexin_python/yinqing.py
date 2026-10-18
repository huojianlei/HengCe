# -*- coding: utf-8 -*-
"""引擎编排层（yinqing）—— 1.0.7 桌面版后端核心的 Python 移植。

移植来源（TS 权威运行时，逐段对应，行号可点检）：
    D:/AppProject/开发分支_1.0.5/desktop/engine.mjs
        L17-20   integer          → 本模块 zhengshu()          整数域校验
        L21-30   parseText        → 本模块 daoru_biaoge()      文本导入回退链
        L31-36   subjects         → 本模块 kemu_guilei()       科目归类清单
        L37-41   tiers            → 本模块 _dangwei()          预警档位校验
        L42-179  analyze          → 本模块 fenxi()             单主体全链分析
        L180-188 zuzhi_shibie     → 本模块 zuzhi_shibie()      组织单元识别
        L189-193 方向/基点助手     → 本模块 _zuzhi_fangxiang()/_bps()
        L194-251 zuzhi_huizong    → 本模块 zuzhi_huizong()     批次组织汇总
        L252-256 recount          → 本模块 chongji()           整改计数回算

算法权威实现（一律 import 复用，本文件【不重写】任何计算模块）：
    D:/AppProject/开发分支_1.0.5/algo/
        data_ingest.daoru_csv / report_parse.shitu_jiexi（daoru_biaoge 回退链）
        rolling_budget.gengxin_gundong_yusuan / GunDongShezhi（滚动预算）
        rolling_budget._cheng_jidian（修订链式重算的乘基点助手）
        variance.jisuan_chayi / ChayiShuru / YujingDang（差异计算）
        planning_operational.chai_fen / ChaifenShuru（规划/执行拆分）
        loop_decision.panduan_huanlu / PanDuanShuru（单双环判定）
        building_blocks.chai_jimu / cong_chayi_xiang / yingshe_mokuai（积木聚合）
        bsc.jisuan_bsc / BscShuru（平衡计分卡）
        kpi.jisuan_kpi / KpiShuru（KPI 指标库）
        suyuan.jisuan_suyuan / SuyuanHang（双维溯源）
        zhenggai.shengcheng_zhenggai / ZhenggaiShuru（整改底座）
        kanban.shengcheng_kanban / KanbanShuru（看板组装）
        xishu.shengcheng_xishu / XishuShuru（判定系数包）
        zuzhi.shibie_zuzhi（组织单元识别的算法底座，本模块 zuzhi_shibie 委托它）

行为对齐纪律：
    - 中文报错文案与 engine.mjs 逐字一致（含全角引号与顿号）；
    - 金额一律整数「分」、比率一律整数「基点」，Python 整数无上限，
      与 TS 侧 BigInt 半进位助手（int-math.ts）的 half-up 结果一致；
    - 输入口径与桌面 API 载荷同形（dict / JSON）；records 既可传
      data_ingest.DaoruJieguo 实例（导入链产物），也可传同构 dict（页面回传），
      入口处统一转 dict 后再走校验链。

命名规范：标识符全拼音（与 algo 一致）、数据值中文、文件名英文。
建立：2026-10-11 ｜ 移植：ZCode（GLM-5.3）
"""

import re
import sys
import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# ---- sys.path 引导：把 algo 权威实现挂进模块搜索路径（幂等，零副作用）----
# 本文件位于 开发分支_1.1.1/houtai_hexin_python/，algo 在 开发分支_1.0.5/algo。
ALGO_LUJING = Path(__file__).resolve().parents[2] / '开发分支_1.0.5' / 'algo'
if str(ALGO_LUJING) not in sys.path:
    sys.path.insert(0, str(ALGO_LUJING))

# ---- algo 权威模块（只 import，不重写）----
from data_ingest import DaoruJieguo, daoru_csv                      # noqa: E402
from report_parse import shitu_jiexi                                # noqa: E402
from rolling_budget import (                                        # noqa: E402
    GunDongShezhi, QijianJine, gengxin_gundong_yusuan, _cheng_jidian,
)
from variance import ChayiShuru, YujingDang, jisuan_chayi           # noqa: E402
from planning_operational import ChaifenShuru, chai_fen             # noqa: E402
from loop_decision import PanDuanShuru, panduan_huanlu              # noqa: E402
from building_blocks import chai_jimu, cong_chayi_xiang             # noqa: E402
from bsc import BscShuru, jisuan_bsc                                # noqa: E402
from kpi import KpiShuru, jisuan_kpi                                # noqa: E402
from suyuan import SuyuanHang, jisuan_suyuan                        # noqa: E402
from zhenggai import ZhenggaiShuru, shengcheng_zhenggai             # noqa: E402
from kanban import KanbanShuru, shengcheng_kanban                   # noqa: E402
from xishu import XishuShuru, shengcheng_xishu                      # noqa: E402
from zuzhi import shibie_zuzhi                                      # noqa: E402

#: 四模块名集合（engine.mjs L122/L192 的 ZUZHI_MOKUAI 同源常量）
#: ——科目归属白名单与组织模块分解共用的权威顺序：收入、成本、费用、采购
ZUZHI_MOKUAI = ['收入模块', '成本模块', '费用模块', '采购模块']
#: 人工类科目关键词（engine.mjs L57，T-21：人工一律归成本，含费用表内嵌行）
#: ——注意"社保"与"社会保险"都要列：后者不含连续的"社保"子串
RENGONG_ZE = re.compile(r'人工|人力|薪酬|工资|社保|社会保险|公积金')
#: 预警颜色必须为 #RRGGBB 六位色号（engine.mjs L39 的 /#[0-9a-f]{6}$/i）
#: ——展示层据此着色，自定义档名可中文但色号格式不可放
YANSE_ZE = re.compile(r'#[0-9a-fA-F]{6}')


class YinqingCuowu(ValueError):
    """编排层校验失败（与 algo 各模块的 ValueError 系异常同一捕获口径）。"""


# ======================================================================
# 基础校验区（engine.mjs L17-20 integer 的移植）
# ======================================================================


def zhengshu(shuzhi, biaoshi, xiaxian=0, shangxian=9 * 10 ** 11):
    """整数域校验：[xiaxian, shangxian] 内的整数才放行（对应 engine.mjs integer）。

    TS 的 Number.isSafeInteger 在 Python 侧的对应口径：
        非 int / bool / 超出安全域（2^53-1）一律拒绝——报错文案逐字对齐
        engine.mjs L18：`{label} 必须为 {min} 至 {max} 的整数`。
    全链路所有金额/比率/门限字段都过这道闸——它是编排层的第一道防线。
    """
    # bool 是 int 子类，先排除（True/False 混入金额是脏数据）；
    # 2^53-1 是 JS 安全整数上界：桌面载荷不会出现更大的合法整数
    if isinstance(shuzhi, bool) or not isinstance(shuzhi, int) \
            or abs(shuzhi) > 2 ** 53 - 1 or shuzhi < xiaxian or shuzhi > shangxian:
        raise YinqingCuowu(f'{biaoshi} 必须为 {xiaxian} 至 {shangxian} 的整数')
    return shuzhi


# ======================================================================
# 导入回退链区（engine.mjs L21-30 parseText 的移植）
# ======================================================================


def daoru_biaoge(wenben):
    """文本 → 标准记录（对应 engine.mjs parseText）。

    链路：先剥 BOM → 直接按标准 8 列 CSV 导入；失败则交给报表模板解析
    （shitu_jiexi 识别"中式预算报告"骨架），模板命中后把还原出的
    8 列文本再走一次 daoru_csv。两级都失败 → 整本退回（engine.mjs L26）。
    1.0.7 桌面链路里本函数只在调试口（FINAGENT_DEBUG_CSV）可达；
    主入口是 xlsx → algo/excel_ingest.import_excel（bridge.py 侧）。
    """
    wenben = re.sub(r'^\ufeff', '', wenben)  # 与 engine 同款：仅剥行首 BOM
    try:
        # 第一级：标准 8 列 CSV 直接清洗入库（algo data_ingest 权威实现）
        return daoru_csv(wenben)
    except ValueError:
        # 第二级：报表模板解析（离线确定、零 LLM）——识别中式预算报告骨架
        jiexi = shitu_jiexi(wenben)
        if not jiexi.shibie:
            # 文案逐字对齐 engine.mjs L26（句号后直接拼交回原因）
            raise YinqingCuowu('无法识别表格，请在导入区核对或编辑标准 CSV。' + jiexi.beizhu)
        # 模板命中：用还原出的标准 8 列文本再导入一次
        return daoru_csv(jiexi.wenben_8lie)


# ======================================================================
# 科目归类区（engine.mjs L31-36 subjects 的移植）
# ======================================================================


def kemu_guilei(jilu):
    """从预算记录提取科目清单并按默认关键词映射模块（对应 engine.mjs subjects）。

    只看「单位=元」的预算基础行；科目去重保序（TS Set 的首现顺序）。
    注意：这里给的是【默认】归属，T-21 人工强制归成本发生在 fenxi() 内。
    """
    from building_blocks import yingshe_mokuai  # 局部导入避免顶部名目拥挤
    # 预算基础行里筛"元"单位（% 与计数单位不进滚动/差异链），科目名去重保首现序
    kemu_lie = list(dict.fromkeys(
        x['kemu'] for x in _hang_lie(jilu, 'yusuan') if x['danwei'] == '元'))
    jieguo = []
    for kemu in kemu_lie:
        # 默认关键词映射（采购→成本→费用→收入，先命中先得）
        mokuai = yingshe_mokuai(kemu)
        # 模块未知 → 空串；收入模块 → 收入类；其余已知模块 → 成本类
        jieguo.append({
            'kemu': kemu,
            'module': mokuai if mokuai is not None else '',
            'direction': '收入类' if mokuai == '收入模块' else ('成本类' if mokuai else ''),
        })
    return jieguo


# ======================================================================
# 预警档位校验区（engine.mjs L37-41 tiers 的移植）
# ======================================================================


def _dangwei(lie):
    """校验一份预警档位配置并转成 variance.YujingDang 序列（对应 engine.mjs tiers）。

    engine 只查两件事：非空 + 每档阈值整数域 + 颜色六位色号；
    档名合法性（空名/保留名/重名）由 variance._jianyan_dang_lie 二道闸把守。
    """
    # 空配置（None / 非列表 / 空列表）一律拒绝——"不想预警"请把阈值设为极高
    if not isinstance(lie, list) or not lie:
        raise YinqingCuowu('至少配置一个预警档位')  # engine.mjs L38
    jieguo = []
    for x in lie:
        # 输入可能是 dict（页面载荷）或已是 YujingDang（程序内组装）——统一读三键
        yuan = x if isinstance(x, dict) else {
            'ming_cheng': x.ming_cheng, 'yan_se': x.yan_se, 'yu_fen': x.yu_fen}
        # 阈值：[0, 1000000] 基点整数（页面档位上限，比 algo 默认口径宽）
        zhengshu(yuan.get('yu_fen'), '预警阈值', 0, 1000000)  # engine.mjs L39
        # 颜色：#RRGGBB 六位十六进制（大小写皆可）——展示层着色的唯一依据
        if not isinstance(yuan.get('yan_se'), str) or not YANSE_ZE.fullmatch(yuan['yan_se']):
            raise YinqingCuowu('预警颜色需为六位色号')  # engine.mjs L39
        # 转成 algo variance 的档位实例：后续 jisuan_chayi 只认 YujingDang
        jieguo.append(YujingDang(
            ming_cheng=yuan.get('ming_cheng', ''),
            yan_se=yuan['yan_se'], yu_fen=yuan['yu_fen']))
    return tuple(jieguo)


# ======================================================================
# 主分析区（engine.mjs L42-179 analyze 的移植）
# ======================================================================


def fenxi(shuru, xiuding_lie=None):
    """单主体全链分析（对应 engine.mjs analyze，行为按段逐行对齐）。

    参数：
        shuru —— 桌面 API 载荷同形的 dict，要点字段：
            records   导入结果（DaoruJieguo 实例或同键 dict；四类归档+拒绝清单）
            config    {cycle,period,growth,industry,industryCorrection,
                       industryThreshold,noise,significance,tiers}
            subjects  [{kemu,module,direction,growth?,tiers?}]（可覆盖默认归属）
            bsc/kpi/traces/splits/events/baselines/metadata/changeStatus/company
        xiuding_lie —— 人工批准的预算修订案列表
            [{kemu,period,amount,...}]（只改未来期预测，届满期与原预算不可动）。

    返回：engine.mjs L177-178 同构的结果 dict（schemaVersion '1.0'，
        金额单位分、比率单位基点；variance/blocks/bsc/kpi/trace/dashboard/
        factors 保留 algo 数据类实例，rolling/decisions/correction 为 dict/名字空间）。
    """
    xiuding_lie = list(xiuding_lie) if xiuding_lie else []

    # ---- ① 记录门禁（engine.mjs L43-45）----
    # 统一转 dict 形态：DaoruJieguo（导入链产物）与页面回传 dict 走同一套校验
    jilu = _zhuan_jilu(shuru.get('records'))
    if not jilu.get('yusuan'):
        # 没有预算基础行就无从分析（% 与计数行也不行——滚动/差异只吃"元"）
        raise YinqingCuowu('请先导入年度预算')  # engine.mjs L44
    if jilu.get('jujue'):
        # 有拒绝行必须先修正再重导——分析建立在已核验数据之上
        raise YinqingCuowu(f"有 {len(jilu['jujue'])} 行未通过校验，请先修正后重新导入")

    # ---- ② 配置校验链（engine.mjs L46-55）----
    config = shuru.get('config') or {}
    # 周期两值：月度 / 季度（定稿 #1 两模式，其余一律退回）
    if config.get('cycle') not in ('月度', '季度'):
        raise YinqingCuowu('请选择滚动周期')
    # 期间格式与周期一致：月度 yyyy-MM / 季度 yyyy-Qn（engine.mjs L48）
    qijian_ze = (r'\d{4}-Q[1-4]' if config.get('cycle') == '季度'
                 else r'\d{4}-(0[1-9]|1[0-2])')
    if not isinstance(config.get('period'), str) or not re.fullmatch(qijian_ze, config['period']):
        raise YinqingCuowu('分析期间格式与滚动周期不一致')
    # 增长率：企业 ±100% 基点封顶；行业率可空（null = 不参与行业口径）
    zhengshu(config.get('growth'), '企业增长率', -10000, 10000)
    # industry 为 null 表示不启用行业参数；给了就必须落在 ±100% 基点内
    if config.get('industry') is not None:
        zhengshu(config['industry'], '行业增长率', -10000, 10000)
    # 季度 + 启用行业修正 + 行业率为空：三条件同时成立才是配置矛盾
    if config.get('cycle') == '季度' and config.get('industryCorrection') \
            and config.get('industry') is None:
        # 全角引号文案逐字对齐 engine.mjs L52
        raise YinqingCuowu('已启用季度行业修正：请填写“行业增长率（%）”，'
                           '或取消勾选“启用季度行业增长率差值修正”。')
    # 门限三件套：行业修正门限 / 噪声门限 / 显著性门限（基点，非负）
    zhengshu(config.get('industryThreshold'), '行业修正门限', 0, 10000)
    zhengshu(config.get('noise'), '噪声门限', 0, 1000000)
    zhengshu(config.get('significance'), '显著性门限', 0, 1000000)
    # 预警档位：非空 + 阈值域 + 色号（档名合法性由 variance 二道闸把守）
    dang_lie = _dangwei(config.get('tiers'))

    # ---- ③ 科目归属：T-21 人工关键词一律强制归成本（engine.mjs L56-59）----
    yuanshi_kemu = shuru.get('subjects') or []
    mapped_subjects = []
    for x in yuanshi_kemu:
        # 关键词命中（人工/人力/薪酬/工资/社保/社会保险/公积金）→ 成本模块；
        # 这是 2026-09 拍板的 T-21 口径：人工属于成本，费用表内嵌行也不例外
        if isinstance(x['kemu'], str) and RENGONG_ZE.search(x['kemu']):
            # 费用表里嵌的人工行也归成本——方向与模块同时改写，其余字段原样保留
            mapped_subjects.append({**x, 'module': '成本模块', 'direction': '成本类'})
        else:
            # 未命中人工关键词：页面填什么用什么（缺省/错配由第⑥步校验拦截）
            mapped_subjects.append({**x})
    # 科目 → 配置行索引（后续模块归属、增长率覆盖都查这张表）
    by_subject = {x['kemu']: x for x in mapped_subjects}
    # 科目级档位覆盖（subjects[].tiers）：有配置才生效，走同一套档位校验
    kemu_dang = {x['kemu']: _dangwei(x['tiers']) for x in yuanshi_kemu if x.get('tiers')}

    # ---- ④ 预算/实际勾稽与查重（engine.mjs L60-72）----
    # 预算侧只吃"元"行；实际侧再按期间窗口截断（ISO 期间键字典序即时间序）
    yusuan_hang = [x for x in jilu['yusuan'] if x['danwei'] == '元']
    shishi_hang = [x for x in (jilu.get('shishi') or [])
                   if x['danwei'] == '元' and x['qijian'] <= config['period']]
    # 两张清单同一套校验：格式 + 财年 + 金额域 + （期间, 科目）唯一
    for lie in (yusuan_hang, shishi_hang):
        chongfu = set()
        for x in lie:
            # 期间必须符合周期格式且属于当前财年（前四位年份一致）
            if not re.fullmatch(qijian_ze, x['qijian']) \
                    or x['qijian'][:4] != config['period'][:4]:
                raise YinqingCuowu(f"期间不属于当前财年或周期：{x['qijian']}")
            # 金额：分（默认 0..9e11 域，超界即脏数据）
            zhengshu(x['shuzhi'], f"{x['kemu']} 金额（分）")
            # （期间, 科目）唯一：同指标同期间两行会双计，必须退回合并
            jian = (x['qijian'], x['kemu'])
            if jian in chongfu:
                raise YinqingCuowu(f"重复记录：{x['qijian']} {x['kemu']}，请核对后合并")
            chongfu.add(jian)
    # 分析窗口内一行实际数都没有 → 无从对比（engine.mjs L72）
    if not shishi_hang:
        raise YinqingCuowu('当前分析期间内没有实际经营数据')

    # ---- ⑤ 经营变更确认状态（engine.mjs L73-78）----
    shijian = shuru.get('events') or []
    # 缺省推断：登记过事件 → provided；否则 unknown（缺失文件 ≠ 本期无变更）
    change_status = shuru.get('changeStatus') or ('provided' if shijian else 'unknown')
    # 四态白名单：unknown / none / provided / pending
    if change_status not in ('unknown', 'none', 'provided', 'pending'):
        raise YinqingCuowu('经营变更确认状态无效')
    # none 与事件登记互斥：声明"本期无变更"就不能再挂事件台账
    if change_status == 'none' and shijian:
        raise YinqingCuowu('已登记经营变更，不能同时声明本期无变更')
    # 未确认 = unknown 或 pending：环路判定暂待复核，不作无结构性变更假设
    bian_geng_wei_queren = change_status in ('unknown', 'pending')
    warnings = []
    if bian_geng_wei_queren:
        # 缺失文件 ≠ 本期无变更：环路判定只能暂待复核，不作无结构性变更假设
        warnings.append('经营变更尚未确认；缺失文件不代表本期无变更，环路判定暂待复核')

    # ---- ⑥ 逐科目：滚动预算 + 修订链式重算 + 三数对比（engine.mjs L79-118）----
    rolling = []
    comparison = []
    # 预算科目按首现序逐个处理（TS Set 同语义）
    for kemu in dict.fromkeys(x['kemu'] for x in yusuan_hang):
        mapping = by_subject.get(kemu)
        # 归属必须四选一且方向合法——未配置/配错都在这里退回
        if not mapping or mapping.get('direction') not in ('成本类', '收入类') \
                or mapping.get('module') not in ZUZHI_MOKUAI:
            raise YinqingCuowu(f'请填写 {kemu} 的科目方向与模块归属')
        # 方向与模块必须同源：只有收入模块能配收入类
        if (mapping['module'] == '收入模块') != (mapping['direction'] == '收入类'):
            raise YinqingCuowu(f'{kemu} 的方向与模块不一致')
        # 原预算按期间升序（ISO 期间键的码点序与 TS localeCompare 同结果）
        original = sorted((x for x in yusuan_hang if x['kemu'] == kemu),
                          key=lambda x: x['qijian'])
        observed = [x for x in shishi_hang if x['kemu'] == kemu]
        # 届满完整性：已到分析期间的每个预算期都必须有对应实际数
        for row in (x for x in original if x['qijian'] <= config['period']):
            if not any(x['qijian'] == row['qijian'] for x in observed):
                raise YinqingCuowu(f"{kemu} {row['qijian']} 已届满但缺实际数，请在数据区补齐")
        # 科目级增长率优先，缺省回落企业增长率；行业口径 A=差值法 B=不修正
        zengzhang = mapping.get('growth')
        if zengzhang is None:
            zengzhang = config['growth']
        shezhi = GunDongShezhi(
            zhouqi=config['cycle'], zengzhanglv_jidian=zengzhang,
            hangye_xiuzheng='A' if config.get('industryCorrection') else 'B',
            hangye_zengzhanglv_jidian=config.get('industry'),
            hangye_yuzhi_jidian=config['industryThreshold'])
        # 滚动重算（algo 权威实现）：届满期全额替换 + 剩余期链式接力
        jieguo = gengxin_gundong_yusuan(
            # algo 侧有 QijianJine isinstance 门禁，必须构造实例而非裸 dict
            [QijianJine(qijian=x['qijian'], jine_fen=x['shuzhi']) for x in original],
            [QijianJine(qijian=x['qijian'], jine_fen=x['shuzhi']) for x in observed],
            shezhi)
        # 逐期明细转 dict（engine 侧就地改写 shuzhi_fen/laiyuan——届满期后重算）
        mingxi = [dataclasses.asdict(t) for t in jieguo.qijian_mingxi]
        # ---- 修订链式重算（engine.mjs L95-106）：批准修订只改未来期 ----
        # 已届满期间锁定：原预算与已发生实际数不可改（server.mjs /api/revise 同口径）
        xiuding_zhongzi = None
        for mubiao in mingxi:
            # findLast 语义：同科目同期间取最后一条修订（Python 反向找第一个）
            xiuding = next((x for x in reversed(xiuding_lie)
                            if x['kemu'] == kemu and x['period'] == mubiao['qijian']), None)
            if mubiao['qijian'] <= config['period']:
                continue  # 已届满期间锁定：原预算与实际数不可改
            if xiuding is not None:
                # 命中批准修订：金额走整数闸，来源标注"人工批准"
                mubiao['shuzhi_fen'] = zhengshu(xiuding['amount'], '修订金额')
                mubiao['laiyuan'] = '人工批准的预算修订'
                xiuding_zhongzi = mubiao['shuzhi_fen']
            elif xiuding_zhongzi is not None:
                # 修订之后的剩余期按增长率接力，行业修正启用时再乘一次差值乘子
                # （乘子口径与 rolling_budget 口径A一致：一次性差值，不累进复利）
                mubiao['shuzhi_fen'] = _cheng_jidian(xiuding_zhongzi, shezhi.zengzhanglv_jidian)
                if jieguo.hangye_xiuzheng_qiyong:
                    mubiao['shuzhi_fen'] = _cheng_jidian(
                        mubiao['shuzhi_fen'], shezhi.zengzhanglv_jidian - config['industry'])
                mubiao['laiyuan'] = '已批准修订后链式重算'
                xiuding_zhongzi = mubiao['shuzhi_fen']
        # 汇总随修订回算（未修订时与 algo 原结果恒等——纯加法无重舍入）
        rolling.append({
            'kemu': kemu, 'qijian_mingxi': mingxi,
            'chushi_zonge_fen': jieguo.chushi_zonge_fen,
            'gundong_zonge_fen': sum(x['shuzhi_fen'] for x in mingxi),
            'chae_fen': sum(x['shuzhi_fen'] for x in mingxi) - jieguo.chushi_zonge_fen,
            'hangye_xiuzheng_qiyong': jieguo.hangye_xiuzheng_qiyong,
        })
        # 三数对比行：基准优先取「届满前预算基准」（baselines），缺省 null → 退化初始预算
        # 已结账期间绝不与被替换后的滚动值比——否则差异全被抹平（engine.mjs L114 注释同义）
        jizhun_biao = shuru.get('baselines') or []
        for row in observed:
            # 实际数必须能对回同期间的原预算行（防御兜底，见导览 drift 说明）
            initial = next((x for x in original if x['qijian'] == row['qijian']), None)
            if initial is None:
                raise YinqingCuowu(f"{kemu} {row['qijian']} 的实际数缺对应预算")
            # 届满前基准：批准修订前该期"本应有的滚动预算"（金额过整数闸）
            jizhun = next((x for x in jizhun_biao
                           if x['kemu'] == kemu and x['period'] == row['qijian']), None)
            comparison.append({
                'qijian': row['qijian'], 'kemu': kemu,
                'fangxiang': mapping['direction'],
                'chushi_fen': initial['shuzhi'],
                'gundong_fen': (zhengshu(jizhun['amount'], '届满前预算基准')
                                if jizhun is not None else None),
                'shiji_fen': row['shuzhi'],
            })
    # 实际数不允许出现预算表没有的科目/期间（engine.mjs L119）
    yusuan_jian = {(x['kemu'], x['qijian']) for x in yusuan_hang}
    if any((x['kemu'], x['qijian']) not in yusuan_jian for x in shishi_hang):
        raise YinqingCuowu('实际数据中存在无对应预算的科目或期间')

    # ---- ⑦ 差异计算 + 模块汇总（engine.mjs L120-129）----
    # 差异计算（algo 权威实现）：基准退化/差额/half-up 差异率/F-A/科目档位全在里面
    chayi = jisuan_chayi(
        [ChayiShuru(qijian=x['qijian'], kemu=x['kemu'], fangxiang=x['fangxiang'],
                    chushi_fen=x['chushi_fen'], gundong_fen=x['gundong_fen'],
                    shiji_fen=x['shiji_fen']) for x in comparison],
        dang_lie, kemu_dang or None)
    # moduleSummary：编排层自有口径——分母只含四模块净差额（科目已被强制归属四模块）
    # （与 building_blocks 的 D2 分母不同：那里还含 |未归属净|，见导览 drifts④）
    module_summary = []
    for mokuai in ZUZHI_MOKUAI:
        # 该模块下的全部差异行：净额求和、基准/实际分别求和
        rows = [x for x in chayi.xiang if by_subject[x.kemu]['module'] == mokuai]
        jing = sum(x.chae_fen for x in rows)
        # 方向：净 0 → 持平；否则收入模块正差=有利、其余模块正差=不利
        module_summary.append({
            'module': mokuai, 'netDeltaFen': jing, 'shareBps': 0,
            'direction': '持平' if jing == 0 else
                         ('有利' if (mokuai == '收入模块') == (jing > 0) else '不利'),
            'budgetFen': sum(x.jizhun_fen for x in rows),
            'actualFen': sum(x.shiji_fen for x in rows), 'count': len(rows)})
    # 占比回填：half-up 整数基点（engine.mjs L129 的 BigInt 同式；分母 0 → 全 0）
    zong_e = sum(abs(x['netDeltaFen']) for x in module_summary)
    for xiang in module_summary:
        xiang['shareBps'] = ((abs(xiang['netDeltaFen']) * 10000 + zong_e // 2) // zong_e
                             if zong_e else 0)

    # ---- ⑧ 拆分/事件/基准三组归属校验（engine.mjs L130-139）----
    # 三组可选输入共享两条纪律：不重复、必须挂在本次已届满的（科目, 期间）上
    zuming = {'splits': '拆分参数', 'events': '变更登记', 'baselines': '预算基准'}
    bijiao_jian = {(x['kemu'], x['qijian']) for x in comparison}
    for zu, ming in zuming.items():
        chongfu = set()
        for item in shuru.get(zu) or []:
            # （科目, 期间）重复 → 退回（防双计）
            jian = (item['kemu'], item['period'])
            if jian in chongfu:
                raise YinqingCuowu(f"{item['kemu']} {item['period']} 存在重复的{ming}")
            chongfu.add(jian)
            # 不属于本次已届满科目 → 无法使用（三组都消费差异行的口径）
            if jian not in bijiao_jian:
                raise YinqingCuowu(f"{item['kemu']} {item['period']} 不属于本次已届满科目，无法使用其{ming}")
            # 事件组专属：结构性变更必须写原因（供语义归类与人工复核）
            if zu == 'events' and item.get('structural') is True \
                    and not str(item.get('reason') or '').strip():
                raise YinqingCuowu('结构性变更登记需要填写原因')

    # ---- ⑨ 规划/执行拆分（engine.mjs L140）----
    # 每组拆分参数即刻算出结果（algo 权威实现：恒等式内建自检，坏数自爆）
    splits = [{'kemu': x['kemu'], 'period': x['period'], 'input': x['values'],
               'result': chai_fen(ChaifenShuru(**{
                   k: v for k, v in x['values'].items()
                   if k in ChaifenShuru.__dataclass_fields__}))}
              for x in (shuru.get('splits') or [])]

    # ---- ⑩ 逐行单双环判定（engine.mjs L141-154）----
    decisions = []
    for row in chayi.xiang:
        # 拆分/事件按（科目, 期间）挂到当前差异行——三数之外的归因线索
        split = next((x for x in splits
                      if x['kemu'] == row.kemu and x['period'] == row.qijian), None)
        shijian_x = next((x for x in shijian
                          if x['kemu'] == row.kemu and x['period'] == row.qijian), None)
        # 判定输入五件套：差异率/结构登记/编码文本/两分量+原标准成本
        params = {
            'chalv_bps': row.chalv_bps,
            'jie_gou_biangeng': shijian_x.get('structural') is True if shijian_x else False,
            'bianma': (shijian_x.get('reason') or '') if shijian_x else '',
            'guihua_zong_fen': split['result'].guihua_zong_fen if split else None,
            'zhixing_zong_fen': split['result'].zhixing_zong_fen if split else None,
            # 原标准成本 = 实际产量 × 标准用量 × 标准单价（与 chai_fen 内部同式）
            'yuandan_cbf_fen': (zhengshu(
                split['input']['shiji_chanliang'] * split['input']['biaozhun_yongliang']
                * split['input']['biaozhun_danjia_fen'], '原标准成本') if split else None),
        }
        # 单双环判定（algo 权威实现）：噪声门/显著阈值用页面配置注入
        jieguo = panduan_huanlu(
            PanDuanShuru(**{k: v for k, v in params.items()
                            if k in PanDuanShuru.__dataclass_fields__}),
            menjian_bps=config['noise'], xianzhu_bps=config['significance'])
        if bian_geng_wei_queren:
            # 经营变更未确认：不作"无结构性变更"假设，统一覆写为复核提示（engine.mjs L148-152）
            # 覆写要点：情形 5、不审批、依据快照里结构登记清成 None（线索缺失如实呈现）
            params['jie_gou_biangeng'] = None
            jieguo = {
                'qingxing': 5, 'panduan': '复核提示',
                'jiuzheng': '先确认本期经营变更；如有，请登记事件台账与科目影响后重新导入',
                'yiju': {**jieguo.yiju, '结构变更登记': None},
                'shenpi': False, 'beizhu': '经营变更未确认，不作无结构性变更假设'}
        else:
            # 正常路径：判定结果摊平成 dict（与覆写分支同形，便于下游统一消费）
            jieguo = {'qingxing': jieguo.qingxing, 'panduan': jieguo.panduan,
                      'jiuzheng': jieguo.jiuzheng, 'yiju': dict(jieguo.yiju),
                      'shenpi': jieguo.shenpi, 'beizhu': jieguo.beizhu}
        # 决策行 = 判定输入快照 + 判定结果 + 变更状态回显（engine.mjs L153）
        decisions.append({'kemu': row.kemu, 'period': row.qijian, 'input': params,
                          **jieguo, 'changeStatus': change_status,
                          'requiresChangeConfirmation': bian_geng_wei_queren})

    # ---- ⑪ 积木聚合（engine.mjs L155-157：自定义档名过白名单后回填原档名）----
    # 底座校验只认 无/—/黄/红 四值：自定义档名先映射成"黄"过闸，
    # 聚合完再把明细行的档名回填为差异表原值（计数/展示用真实档名）
    hefa_yujing = ('无', '—', '黄', '红')
    yuanyang = {(x.kemu, x.qijian): x.yujing for x in chayi.xiang}
    # 差异行 → 积木行适配（algo cong_chayi_xiang：六字段透传零重算）
    jimu_hang = [cong_chayi_xiang(SimpleNamespace(
        qijian=x.qijian, kemu=x.kemu, chae_fen=x.chae_fen, fa=x.fa,
        chalv_bps=x.chalv_bps,
        yujing=x.yujing if x.yujing in hefa_yujing else '黄')) for x in chayi.xiang]
    # 四模块聚合（algo 权威实现）：科目→模块用编排层的已核验归属覆盖默认关键词
    blocks = chai_jimu(jimu_hang, lambda kemu: by_subject.get(kemu, {}).get('module'))
    # 积木明细的预警档名回填为差异表原值（校验用映射档，展示用真实档）
    blocks = dataclasses.replace(blocks, mokuai_lie=[
        dataclasses.replace(kuai, mingxi=[
            dataclasses.replace(hang, yujing=yuanyang[(hang.kemu, hang.qijian)])
            for hang in kuai.mingxi]) for kuai in blocks.mokuai_lie])

    # ---- ⑫ BSC / KPI / 溯源（engine.mjs L158-163）----
    # BSC 四维达成率（可带自定义权重四元组）；空配置 → None + 缺料警告
    bsc = jisuan_bsc(BscShuru(**{
        k: (tuple(v) if k == 'quanzhong' and v is not None else v)
        for k, v in (shuru.get('bsc') or {}).items()
        if k in BscShuru.__dataclass_fields__})) if shuru.get('bsc') else None
    if not bsc:
        warnings.append('BSC 四维达成率未填写，暂不评分')
    # KPI 15 项：缺数字段一律 None 交人工（algo 缺数纪律），空 dict 也可跑
    kpi = jisuan_kpi(KpiShuru(**{
        k: v for k, v in (shuru.get('kpi') or {}).items()
        if k in KpiShuru.__dataclass_fields__}))
    # 双维溯源：变更前后指标对照（KPI 名必须在 15 项清单内——algo 校验）
    traces = shuru.get('traces') or []
    trace = jisuan_suyuan([SuyuanHang(**{
        k: v for k, v in x.items() if k in SuyuanHang.__dataclass_fields__})
        for x in traces]) if traces else None
    if not trace:
        warnings.append('未填写变更前后指标，暂不计算双维溯源')
    # 没有拆分参数：判定表会声明"拆分线索缺失"——如实提示，不臆造归因
    if not splits:
        warnings.append('未提供规划/执行拆分参数，判定表将标明缺失线索')

    # ---- ⑬ 整改清单组装（engine.mjs L164-173）----
    # correction 用名字空间承载：看板/系数包经属性读取，状态推进就地生效
    correction = SimpleNamespace(qingdan=[], zong_shu=0, gao_shu=0, zhong_shu=0,
                                 di_shu=0, daizhenggai_shu=0, jinxingzhong_shu=0,
                                 wancheng_shu=0)
    # 第一层：差异红黄行 + 核心模块高亮（algo 权威实现）
    base = shengcheng_zhenggai(ZhenggaiShuru(chayi=chayi, jimu=blocks, panduan=None))
    correction.qingdan.extend(SimpleNamespace(**dataclasses.asdict(x)) for x in base.qingdan)
    # 第二层：自定义档名（非 无/—/红/黄）也产生整改动作——底座只认红黄，这里补关注项
    # （engine.mjs L165 注释同义：自定义预警名仍要出动作，识别只认红/黄）
    for row in (x for x in chayi.xiang if x.yujing not in hefa_yujing):
        correction.qingdan.append(SimpleNamespace(
            leixing='关注整改', youxianji='中',
            zeren_mokuai=by_subject[row.kemu]['module'], kemu=row.kemu,
            qijian=row.qijian,
            miaoshu=f'{row.kemu} 触发 {row.yujing} 档位，请复核并整改',
            shenpi=False, zhuangtai='待整改', id=None))
    # 第三层：逐条判定的指令项（预算修订案/行为整改/人工复核）
    for decision in decisions:
        # 逐条判定的整改指令：科目/期间/责任模块按判定行回填（engine.mjs L170-171）
        item = shengcheng_zhenggai(ZhenggaiShuru(
            panduan=SimpleNamespace(panduan=decision['panduan'])))
        for x in item.qingdan:
            # algo 的 ZhenggaiXiang 摊平成名字空间，再回填判定行的三字段
            yuan = dataclasses.asdict(x)
            yuan.update(kemu=decision['kemu'], qijian=decision['period'],
                        zeren_mokuai=by_subject[decision['kemu']]['module'], id=None)
            correction.qingdan.append(SimpleNamespace(**yuan))
    # 统一编号 + 状态复位（engine.mjs L173）：重算即新生成一份待整改清单
    for i, xiang in enumerate(correction.qingdan):
        xiang.id = f'action-{i + 1}'
        xiang.zhuangtai = '待整改'
    # 计数回算（优先级三档 + 进度三态）
    chongji(correction)

    # ---- ⑭ 看板与判定系数（engine.mjs L175-176）----
    # 看板：五区纯组装（engine 不传 gundong/panduan——折线与判定块为空结构）
    dashboard = shengcheng_kanban(KanbanShuru(
        chayi=chayi, jimu=blocks, bsc=bsc, kpi=kpi, suyuan=trace,
        zhenggai=correction))
    # 系数包：优先取需审批的判定行，否则首行（检索提示词的生成依据）
    shou_xuan = next((x for x in decisions if x['shenpi']), decisions[0] if decisions else None)
    factors = shengcheng_xishu(XishuShuru(
        chayi=chayi, jimu=blocks, bsc=bsc, zhenggai=correction,
        panduan=SimpleNamespace(panduan=shou_xuan['panduan'], shenpi=shou_xuan['shenpi'])
        if shou_xuan else None))

    # ---- ⑮ 结果 DTO（engine.mjs L177-178：meta 含组织识别，单位声明分/基点）----
    meta_lie = shuru.get('metadata') or {}
    gongsi = shuru.get('company') or '企业预算'
    zhuti = meta_lie.get('主体名称') or gongsi
    dangqian = datetime.now(timezone.utc)  # 单次取时：秒与毫秒必须同源（ISO 形如 ...T08:00:00.123Z）
    return {
        'schemaVersion': '1.0',
        'meta': {
            'company': gongsi,
            'entityName': zhuti,
            'scenarioName': meta_lie.get('情景名称') or '',
            'entityCode': meta_lie.get('主体编码') or '',
            'scenarioCode': meta_lie.get('情景编码') or '',
            'organization': zuzhi_shibie(zhuti),
            'changeStatus': change_status, 'period': config['period'],
            'cycle': config['cycle'], 'simulation': shuru.get('simulation') is True,
            'generatedAt': dangqian.strftime('%Y-%m-%dT%H:%M:%S.')
                           + f'{dangqian.microsecond // 1000:03d}Z',
            'moneyUnit': '分', 'rateUnit': '基点'},
        'config': config, 'records': jilu, 'subjects': mapped_subjects,
        'rolling': rolling, 'variance': chayi, 'moduleSummary': module_summary,
        'splits': splits, 'decisions': decisions, 'blocks': blocks, 'bsc': bsc,
        'kpi': kpi, 'trace': trace, 'correction': correction,
        'dashboard': dashboard, 'factors': factors, 'warnings': warnings,
        'revisions': xiuding_lie,
    }


# ======================================================================
# 组织单元区（engine.mjs L180-251 的移植；识别委托 algo/zuzhi.shibie_zuzhi）
# ======================================================================


def zuzhi_shibie(mingcheng):
    """主体名称 → {机构, 部门}（对应 engine.mjs L182-188）。

    「机构/部门」写法取最后一段为部门、其余为机构；无分隔符时主体自身
    即一个组织单元；空名回落"未命名机构/未命名组织单元"（不抛错）。
    识别算法本体复用 algo/zuzhi.shibie_zuzhi（两侧同口径互证，见其 docstring）；
    返回 dict 而非元组——对齐 engine.mjs 的返回形态（meta.organization 直接可用）。
    """
    # 半角/全角斜杠都认；多级名称取末段为部门（algo 实现已处理容错与兜底）
    jigou, bumen = shibie_zuzhi(mingcheng)
    return {'jigou': jigou, 'bumen': bumen}


def _zuzhi_fangxiang(youli_fen, buli_fen):
    """部门方向：收入模块差额越大越有利，部门混合四模块故比有利/不利偏差量。

    （engine.mjs L190 注释同义：有利/不利偏差量的比较是部门层的判定口径。）
    """
    # 量相等 → 持平；否则量大的那侧定方向（不抵消、不看符号和）
    if youli_fen == buli_fen:
        return '持平'
    return '有利' if youli_fen > buli_fen else '不利'


def _bps(zifen, fenmu):
    """整数基点占比（half-up）；分母为 0 返回 0——engine.mjs L191 的同式。

    （分子非负：排行/完成率场景的入参都是绝对偏差或计数。）
    """
    return (zifen * 10000 + fenmu // 2) // fenmu if fenmu else 0


def zuzhi_huizong(items):
    """同批次各主体的分析结果汇总成组织单元层（对应 engine.mjs L194-251）。

    输入：fenxi() 结果列表（一份工作簿一个主体）。输出：每部门一行
    （含四模块分解、红黄预警计数、整改完成率）+ 机构小计 + 绝对偏差排行
    + 期间分组（批次混月度/季度时必须声明，跨期比较由使用方分期间看）。
    """
    if not isinstance(items, list) or not items:
        # 空批次：连一个主体的分析都没有，无从汇总（engine.mjs L195）
        raise YinqingCuowu('请先完成至少一个主体的分析，再汇总组织单元')
    bumen_lie = []
    # ---- 逐主体 → 部门行（engine.mjs L196-219）----
    for item in items:
        # meta 兼容 dict / 属性两种形态（fenxi 产物为 dict，防御外部对象）
        meta = (item.get('meta') or {}) if isinstance(item, dict) else getattr(item, 'meta', {})
        # 主体名称识别机构与部门（算法底座在 algo/zuzhi.shibie_zuzhi）
        shibie = zuzhi_shibie(meta.get('entityName') or meta.get('company') or '')
        # 差异明细是部门行的唯一数值来源——没有明细的"分析"无法汇总
        xiang = _du(item, 'variance').xiang if _du(item, 'variance') is not None else []
        if not xiang:
            raise YinqingCuowu(f"{shibie['bumen']} 缺少差异明细，无法汇总组织单元")
        # ---- 部门行：差额求和、绝对偏差不抵消、有利/不利按 F/A 分解 ----
        # budgetFen 名为"预算"实为 Σ基准（jizhun_fen）——engine.mjs L204 同口径
        yusuan_e = shiji_e = cha_e = juedui = youli = buli = 0
        yujing_shu = hong_shu = huang_shu = 0
        for row in xiang:
            # 每行金额过整数闸（差额允许负域 ±9e11，其余非负域）
            cha = zhengshu(row.chae_fen, '科目差额', -9 * 10 ** 11, 9 * 10 ** 11)
            yusuan_e += zhengshu(row.jizhun_fen or 0, '科目基准金额')
            shiji_e += zhengshu(row.shiji_fen or 0, '科目实际金额')
            # 净差可抵消、绝对偏差不抵消（有利与不利分开累计）
            cha_e += cha
            juedui += abs(cha)
            # F=有利 / A=不利（'—' 零差不计入任何一侧）
            if row.fa == 'F':
                youli += abs(cha)
            elif row.fa == 'A':
                buli += abs(cha)
            # 预警计数：非 无/— 即命中；红黄分列（自定义档名计入命中数）
            if row.yujing not in ('无', '—'):
                yujing_shu += 1
            if row.yujing == '红':
                hong_shu += 1
            elif row.yujing == '黄':
                huang_shu += 1
        # ---- 四模块分解：优先读分析结果的 moduleSummary，缺行按净额符号推方向 ----
        # （单主体的 moduleSummary 恒有四模块行；这里防御外部裁剪过的结果）
        huizong_biao = {x['module']: x for x in (_du(item, 'moduleSummary') or [])}
        mokuai_lie = []
        for mokuai in ZUZHI_MOKUAI:
            hang = huizong_biao.get(mokuai)
            # 净差额允许负域；基准/实际非负；None 一律按 0 处理
            jing = zhengshu((hang or {}).get('netDeltaFen') or 0, '模块净差额',
                            -9 * 10 ** 11, 9 * 10 ** 11)
            # 方向：有 summary 行直接用；缺行时按"收入正差=有利"同口径补推
            fangxiang = (hang or {}).get('direction') or (
                '持平' if jing == 0 else
                ('有利' if (mokuai == '收入模块') == (jing > 0) else '不利'))
            mokuai_lie.append({
                'module': mokuai,
                'budgetFen': zhengshu((hang or {}).get('budgetFen') or 0, '模块基准金额'),
                'actualFen': zhengshu((hang or {}).get('actualFen') or 0, '模块实际金额'),
                'deltaFen': jing, 'direction': fangxiang})
        # 整改进度：总数与已完成数来自该主体的 correction（名字空间属性读取）
        zhenggai = _du(item, 'correction')
        zhenggai_shu = getattr(zhenggai, 'zong_shu', 0) or 0
        wancheng_shu = getattr(zhenggai, 'wancheng_shu', 0) or 0
        # 部门行落表：主体四码（机构/部门/编码/情景）+ 金额组 + 模块分解 + 预警/整改
        bumen_lie.append({
            'bumen': shibie['bumen'], 'jigou': shibie['jigou'],
            'entityCode': meta.get('entityCode', '') or '',
            'scenarioName': meta.get('scenarioName', '') or '',
            'period': meta.get('period', '') or '',
            'budgetFen': yusuan_e, 'actualFen': shiji_e, 'deltaFen': cha_e,
            'jueduiChaFen': juedui, 'youliFen': youli, 'buliFen': buli,
            'direction': _zuzhi_fangxiang(youli, buli), 'mokuai': mokuai_lie,
            'yujingShu': yujing_shu, 'hongShu': hong_shu, 'huangShu': huang_shu,
            'zhenggaiShu': zhenggai_shu, 'wanchengShu': wancheng_shu,
            'wanchengBps': _bps(wancheng_shu, zhenggai_shu)})
    # ---- 合计恒等于各部门相加（整数分相加，不平摊不舍入）----
    # 下游可用"部门合计 = 科目合计"对账（algo zuzhi 的同一不变量）
    heji = {'bumenShu': len(bumen_lie), 'budgetFen': 0, 'actualFen': 0, 'deltaFen': 0,
            'jueduiChaFen': 0, 'youliFen': 0, 'buliFen': 0, 'yujingShu': 0,
            'zhenggaiShu': 0, 'wanchengShu': 0,
            'mokuai': [{'module': m, 'budgetFen': 0, 'actualFen': 0,
                        'deltaFen': 0, 'direction': '持平'} for m in ZUZHI_MOKUAI]}
    # 模块小计按模块名索引回填（四模块固定，dict 保序）
    by_mokuai = {x['module']: x for x in heji['mokuai']}
    for hang in bumen_lie:
        # 九项标量直接累加
        for jian in ('budgetFen', 'actualFen', 'deltaFen', 'jueduiChaFen', 'youliFen',
                     'buliFen', 'yujingShu', 'zhenggaiShu', 'wanchengShu'):
            heji[jian] += hang[jian]
        # 三项模块金额分别累加
        for bu in hang['mokuai']:
            mubiao = by_mokuai[bu['module']]
            mubiao['budgetFen'] += bu['budgetFen']
            mubiao['actualFen'] += bu['actualFen']
            mubiao['deltaFen'] += bu['deltaFen']
    # 合计方向与完成率（分母 0 → 0 基点，不抛错）
    heji['direction'] = _zuzhi_fangxiang(heji['youliFen'], heji['buliFen'])
    heji['wanchengBps'] = _bps(heji['wanchengShu'], heji['zhenggaiShu'])
    # 模块方向按合计净差重推（收入模块正差=有利，其余相反；0=持平）
    for bu in heji['mokuai']:
        bu['direction'] = ('持平' if bu['deltaFen'] == 0 else
                           ('有利' if (bu['module'] == '收入模块') == (bu['deltaFen'] > 0)
                            else '不利'))
    # ---- 排行：绝对偏差降序；并列断链用码点序（engine 为 localeCompare 'zh'，已登记 drift）----
    # 排行行只带五个汇总字段（部门/机构/两差值/方向/占比/预警数），不含模块分解
    paixu = sorted(bumen_lie, key=lambda x: (-x['jueduiChaFen'], x['bumen']))
    paihang = [{'bumen': x['bumen'], 'jigou': x['jigou'], 'deltaFen': x['deltaFen'],
                'jueduiChaFen': x['jueduiChaFen'], 'direction': x['direction'],
                'zhanbiBps': _bps(x['jueduiChaFen'], heji['jueduiChaFen']),
                'yujingShu': x['yujingShu']} for x in paixu]
    # ---- 机构小计：按机构归并后按绝对偏差降序（engine.mjs L232-240）----
    # dict 保插入序（TS Map 同语义）；归并后才排序，占比分母为全批绝对偏差
    jigou_map = {}
    for hang in bumen_lie:
        cur = jigou_map.setdefault(
            hang['jigou'], {'jigou': hang['jigou'], 'bumenShu': 0, 'budgetFen': 0,
                            'actualFen': 0, 'deltaFen': 0, 'jueduiChaFen': 0, 'yujingShu': 0})
        cur['bumenShu'] += 1
        for jian in ('budgetFen', 'actualFen', 'deltaFen', 'jueduiChaFen', 'yujingShu'):
            cur[jian] += hang[jian]
    # 机构行排序后回填占比（并列断链：机构名码点序）
    jigou_lie = sorted(jigou_map.values(),
                       key=lambda x: (-x['jueduiChaFen'], x['jigou']))
    for hang in jigou_lie:
        hang['zhanbiBps'] = _bps(hang['jueduiChaFen'], heji['jueduiChaFen'])
    # ---- 期间分组：批次可能混月度/季度，必须声明是否同期间 ----
    # 合计按各单元直接相加，但跨期比较由使用方分期间看（engine.mjs L241 注释同义）
    qijian_map = {}
    for index, item in enumerate(items):
        meta = (item.get('meta') or {}) if isinstance(item, dict) else getattr(item, 'meta', {})
        # 键 =（周期, 期间）；空值按空串归组（缺 meta 的结果不至于炸）
        jian = (meta.get('cycle', '') or '', meta.get('period', '') or '')
        cur = qijian_map.setdefault(
            jian, {'cycle': jian[0], 'period': jian[1], 'bumenShu': 0, 'jueduiChaFen': 0})
        cur['bumenShu'] += 1
        # 部门行与 items 同序——index 直取（engine.mjs L247 同写法）
        cur['jueduiChaFen'] += bumen_lie[index]['jueduiChaFen']
    # 期间组按期间升序、周期码点序断链
    qijian_lie = sorted(qijian_map.values(),
                        key=lambda x: (x['period'], x['cycle']))
    # 单机构批次直接用机构名；多机构批次回落统一称呼（不强行归并）
    return {'jigou': jigou_lie[0]['jigou'] if len(jigou_lie) == 1 else '全部组织单元',
            'bumen_lie': bumen_lie, 'paihang': paihang, 'jigou_lie': jigou_lie,
            'qijian_lie': qijian_lie, 'yizhi': len(qijian_lie) == 1, 'heji': heji}


# ======================================================================
# 整改计数回算区（engine.mjs L252-256 recount 的移植）
# ======================================================================


def chongji(c):
    """按清单就地回算整改计数：总数/高中低优先级/进度三态（对应 engine.mjs recount）。

    整改状态被外部推进（待整改→进行中→已完成）后必须重调本函数，
    看板与组织汇总读取的就是这组计数。
    """
    # 总数 = 清单长度（含所有类型与状态）
    c.zong_shu = len(c.qingdan)
    # 优先级三档计数（高/中/低）
    for ziduan, zhi in (('gao_shu', '高'), ('zhong_shu', '中'), ('di_shu', '低')):
        setattr(c, ziduan, sum(1 for x in c.qingdan if x.youxianji == zhi))
    # 进度三态计数（待整改/进行中/已完成）——三态互斥，合计恒等于总数
    for ziduan, zhi in (('daizhenggai_shu', '待整改'), ('jinxingzhong_shu', '进行中'),
                        ('wancheng_shu', '已完成')):
        setattr(c, ziduan, sum(1 for x in c.qingdan if x.zhuangtai == zhi))


# ======================================================================
# 内部工具区（桌面 API 载荷与 algo 数据类的双向适配，仅编排层使用）
# ======================================================================


def _zhuan_jilu(jilu):
    """records 统一转 dict 形态：DaoruJieguo 实例（导入链产物）或同键 dict 原样读。

    engine.mjs 收到的永远是 JS 普通对象；Python 侧导入链产出的是
    DaoruJieguo 数据类——这里一次性摊平成同构 dict，后续校验链只认 dict。
    其余类型（None 之外的非法形态）按"没有预算"退回。
    """
    # None / 缺键：交给"请先导入年度预算"门禁（engine.mjs L44 的可选链同义）
    if jilu is None:
        return {}
    # 导入链产物：五类归档逐行摊平（含拒绝清单——门禁要用它的长度）
    if isinstance(jilu, DaoruJieguo):
        return {ming: [dataclasses.asdict(x) for x in getattr(jilu, ming)]
                for ming in ('yusuan', 'shishi', 'hangye', 'biangeng', 'jujue')}
    # 页面回传的同构 dict：原样通过（行可以是 dict 或数据类，见 _hang_lie）
    if isinstance(jilu, dict):
        return jilu
    raise YinqingCuowu('请先导入年度预算')


def _hang_lie(jilu, ming):
    """安全取某一类归档的行列表（缺键/类型不符一律按空表处理）。

    行形态两种皆可：dict（页面回传）或 BiaozhunJilu 数据类（导入链产物）。
    """
    # 数据类实例：按属性取后逐行摊平成 dict
    if isinstance(jilu, DaoruJieguo):
        hang = getattr(jilu, ming, None)
        return [dataclasses.asdict(x) for x in hang] if hang else []
    # dict：缺键按空表；混合形态逐行归一
    if isinstance(jilu, dict):
        hang = jilu.get(ming) or []
        return [x if isinstance(x, dict) else dataclasses.asdict(x) for x in hang]
    return []


def _du(item, jian, moren=None):
    """duck 读键：dict 用 get、对象用 getattr——兼容 dict 与数据类两种结果形态。"""
    # 组织汇总的输入既可能是 fenxi() 的 dict 产物，也可能是外部对象形态
    if isinstance(item, dict):
        return item.get(jian, moren)
    return getattr(item, jian, moren)
