# -*- coding: utf-8 -*-
"""AI 边界层（ai_bianjie）—— 白名单结果 DTO 构造器的 Python 移植。

移植来源（TS 权威运行时，逐段对应，行号可点检）：
    D:/AppProject/开发分支_1.0.5/desktop/ai-boundary.mjs
        L2      AI_ACCESS_DENIED       → 本模块 AI_JUJUE_WENAN（权限关闭固定文案）
        L3-4    modules / decisions    → 本模块 MOKUAI_HEFA / PANDUAN_HEFA（白名单集合）
        L5-8    period/amount/...      → 本模块 _qijian/_shuzhi/... 五个标量过滤器
        L10-16  organization()         → 本模块 _zuzhi_dto()（批次组织汇总白名单）
        L17-38  prepareAiRequest()     → 本模块 zhunbei_ai_qingqiu()（唯一对外入口）

边界纪律（ai-boundary.mjs 头注 L1：财务数据只在边界上以"新建的结果 DTO"形态过境）：
    - 权限门未开：不触碰 result，直接返回固定拒绝文案（engine/server 两级同款）；
    - 权限门开启：模型只收本次已核验的科目、期间、金额与判定结果，
      原始工作簿与备注永不进入请求；
    - 本构造器是【第一道闸】；云端还有第二道闸 desktop/ai_worker.py::sanitize_results
      （同为 Python，白名单口径一致），两道闸不得合并删除。

与 yinqing.fenxi() 结果的衔接：result 取 dict 形态（variance 保留 algo
ChayiJieguo 数据类——本模块经属性读取；subjects/decisions/moduleSummary
为 dict 列表）。标量过滤器一律"非法即清空/置 None"，不抛错、不补造。

命名规范：标识符全拼音（与 algo 一致）、数据值中文、文件名英文。
建立：2026-10-11 ｜ 移植：ZCode（GLM-5.3）
"""

import re

#: 权限关闭时的固定答复（ai-boundary.mjs L2 文案逐字保留，含全角引号）
AI_JUJUE_WENAN = ('数据访问权限当前关闭，AI 无法读取或解释本次财务数据。'
                  '工作簿解析、勾稽校验与数值计算均在本机完成；开启“数据访问”后，'
                  '模型仅接收本次已核验的科目、期间、金额与判定结果，原始工作簿始终不上传。')
#: 模块白名单（ai-boundary.mjs L3）：只有四模块名能进入 DTO
MOKUAI_HEFA = {'收入模块', '成本模块', '费用模块', '采购模块'}
#: 判定白名单（ai-boundary.mjs L4）：五情形 + 三个兜底态；不认识的一律"待确认"
PANDUAN_HEFA = {'不触发', '单环', '双环', '混合纠错模式', '复核提示', '待确认', '待补充经营变更'}
#: 期间白名单（ai-boundary.mjs L5）：yyyy-MM 或 yyyy-Qn，其余清空串
_QIJIAN_ZE = re.compile(r'\d{4}-(?:0[1-9]|1[0-2]|Q[1-4])')
#: 安全整数上限（TS Number.isSafeInteger 的对应：|x| ≤ 2^53-1）
_ANQUAN_SHANGXIAN = 2 ** 53 - 1


def _qijian(x):
    """期间过滤器：合法期间原样放行，其余清空串（ai-boundary.mjs L5）。"""
    # fullmatch 等价 TS 的 ^...$ 锚定；非字符串直接清空
    return x if isinstance(x, str) and _QIJIAN_ZE.fullmatch(x) else ''


def _shuzhi(x):
    """金额/比率过滤器：安全整数放行，其余置 None（ai-boundary.mjs L6）。"""
    # bool 是 int 子类，先排除——True 绝不能当 1 分钱过境
    if isinstance(x, bool) or not isinstance(x, int) or abs(x) > _ANQUAN_SHANGXIAN:
        return None
    return x


def _fangxiang(x):
    """方向过滤器：只认 F/A/N 三记号（ai-boundary.mjs L7）。"""
    # '—'（零差额）不进 DTO 方向字段——云端只认三字母记号
    return x if x in ('A', 'F', 'N') else ''


def _mingcheng(x, zuida):
    """名称过滤器：字符串且不超长放行（空串也放行），其余清空（ai-boundary.mjs L8）。"""
    return x if isinstance(x, str) and len(x) <= zuida else ''


def _zuzhi_dto(zuzhi):
    """组织单元汇总 → 最小白名单 DTO（ai-boundary.mjs L10-16）。

    只送机构名、单元数与每部门的六个已核验数字；部门截断 200 行、
    名称限长 120；不是汇总结构（缺 bumen_lie）→ None（不加这个键）。
    """
    if not isinstance(zuzhi, dict) or not isinstance(zuzhi.get('bumen_lie'), list):
        # 不是汇总结构（缺部门行列表）→ 整个键都不加，而非送空壳
        return None
    heji = zuzhi.get('heji') or {}
    # 机构名限长 120；单元数走安全整数（非整数 → None，不补 0）
    return {
        'name': _mingcheng(zuzhi.get('jigou'), 120),
        'unitCount': _shuzhi(heji.get('bumenShu')),
        # 部门行只保留七个白名单字段：两名称 + 五个已核验数字（六金额 + 预警计数）
        'departments': [{
            'name': _mingcheng(hang.get('bumen'), 120),
            'institution': _mingcheng(hang.get('jigou'), 120),
            'budgetAmount': _shuzhi(hang.get('budgetFen')),
            'actualAmount': _shuzhi(hang.get('actualFen')),
            'deltaAmount': _shuzhi(hang.get('deltaFen')),
            'absoluteDeltaAmount': _shuzhi(hang.get('jueduiChaFen')),
            'alertCount': _shuzhi(hang.get('yujingShu')),
        } for hang in zuzhi['bumen_lie'][:200]],  # 上限 200：防大批次撑爆提示词
    }


def zhunbei_ai_qingqiu(result, *, data_access=False, op='chat', question='', zuzhi=None):
    """构造（或拒绝）一次 AI 请求（对应 ai-boundary.mjs prepareAiRequest）。

    参数：
        result      yinqing.fenxi() 的结果 dict（权限关闭时不被触碰）。
        data_access 数据访问开关；非 True 一律拒绝（默认 False）。
        op          'chat' 或 'enrich'（ai-boundary.mjs L20 白名单）。
        question    用户问题（仅 chat 有意义；超 8000 字截断）。
        zuzhi       yinqing.zuzhi_huizong() 的汇总 dict（可缺省）。

    返回（与 ai-boundary.mjs L19/L37 同构）：
        权限关 → {'allowed': False, 'response': {answer/status/references/failures}}；
        权限开 → {'allowed': True, 'request': {op/dataAccess/data/question}}。
    """
    # ---- 权限门在最前：门未开连 result 都不解引用（ai-boundary.mjs L19 注释同义）----
    if data_access is not True:
        # 固定答复四件套：文案/状态/空引用/空失败清单——与 server.mjs 两处消费口同形
        return {'allowed': False,
                'response': {'answer': AI_JUJUE_WENAN, 'status': '权限关闭',
                             'references': [], 'failures': []}}
    if op not in ('chat', 'enrich'):
        raise ValueError('不支持的 AI 操作')
    # result 允许 dict（fenxi 产物）或对象形态；variance 缺失/无差异行一律拒绝
    chayi = (result or {}).get('variance') if isinstance(result, dict) \
        else getattr(result, 'variance', None)
    xiang = getattr(chayi, 'xiang', None)  # algo ChayiJieguo 属性读取
    if not isinstance(xiang, list):
        raise ValueError('请先完成本次本机分析')

    # ---- 两张索引：科目→模块（subjects）、（科目,期间）→判定行（decisions）----
    subjects = (result or {}).get('subjects') if isinstance(result, dict) \
        else getattr(result, 'subjects', None)
    by_subject = {x['kemu']: x.get('module') for x in (subjects or [])}
    decisions = (result or {}).get('decisions') if isinstance(result, dict) \
        else getattr(result, 'decisions', None)
    by_decision = {f"{x['kemu']}\0{x['period']}": x for x in (decisions or [])}

    # ---- 差异行白名单化（ai-boundary.mjs L25-31：11 字段，科目名超长即报错）----
    hang_lie = []
    for row in xiang:
        kemu = row.kemu
        if not isinstance(kemu, str) or len(kemu) > 180:
            raise ValueError('科目名称不符合模型结果契约')
        panduan = by_decision.get(f'{kemu}\0{row.qijian}')
        # 判定结论须落在七值白名单内（缺判定行 = 待确认）；审批标志只认真布尔 True
        jielun = panduan.get('panduan') if panduan else None
        mokuai = getattr(row, 'module', None)
        if mokuai is None:
            mokuai = by_subject.get(kemu)  # 差异行未带模块 → 回落 subjects 索引
        hang_lie.append({
            'subject': kemu, 'period': _qijian(row.qijian),
            'module': mokuai if mokuai in MOKUAI_HEFA else '',
            'budgetAmount': _shuzhi(row.chushi_fen),
            'baselineAmount': _shuzhi(row.jizhun_fen),
            'actualAmount': _shuzhi(row.shiji_fen),
            'deltaAmount': _shuzhi(row.chae_fen),
            'varianceRate': _shuzhi(row.chalv_bps),
            'direction': _fangxiang(row.fa),
            'decision': jielun if jielun in PANDUAN_HEFA else '待确认',
            'requiresApproval': panduan is not None and panduan.get('shenpi') is True,
        })

    # ---- 模块汇总白名单化（ai-boundary.mjs L32-33：有利/不利 → F/A/N）----
    mo_zong = (result or {}).get('moduleSummary') if isinstance(result, dict) \
        else getattr(result, 'moduleSummary', None)
    mo_lie = []
    for x in (mo_zong or []):
        # 白名单外的模块（理论不存在——moduleSummary 恒四模块）直接跳过不送
        if x.get('module') not in MOKUAI_HEFA:
            continue
        # 中文方向 → 三字母记号：有利 F / 不利 A / 其余（含持平）N
        fangxiang = {'有利': 'F', '不利': 'A'}.get(x.get('direction'), 'N')
        mo_lie.append({'module': x['module'],
                       'deltaAmount': _shuzhi(x.get('netDeltaFen')),
                       'direction': fangxiang,
                       'shareRate': _shuzhi(x.get('shareBps'))})

    # ---- 顶层期间：从 meta 取，经期间过滤器后进 DTO（非法 → 空串，不抛错）----
    meta = (result or {}).get('meta') if isinstance(result, dict) \
        else getattr(result, 'meta', None)
    data = {'schemaVersion': 'ai-results/1',
            'period': _qijian((meta or {}).get('period')),
            'units': {'amount': '分', 'rate': '基点'},
            'variance': hang_lie, 'modules': mo_lie}
    # 只有本批次确实做过组织汇总才加这个键——字段集保持最小（ai-boundary.mjs L34-36）
    zuzhi_dto = _zuzhi_dto(zuzhi)
    if zuzhi_dto is not None:
        data['organization'] = zuzhi_dto
    return {'allowed': True,
            'request': {'op': op, 'dataAccess': True, 'data': data,
                        'question': question[:8000] if isinstance(question, str) else ''}}
