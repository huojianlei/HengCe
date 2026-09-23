# -*- coding: utf-8 -*-
"""看板数据接口 —— 方案B 步骤 7 的【纯结构化输出】聚合层（FR-13 计算前置）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文；
    专有缩写可保留（KPI、BSC 等）。

口径依据（权威文件，修改本模块前必读）：
    docs/01-需求说明.md v2.0 §3 FR-13（用户拍板：与 UI 合并最后做；
        计算侧先备"看板数据接口"纯结构化输出，[043]/T-28）
    docs/proposal-full-extract.txt 行 80~88（看板五区清单：预算基准对比区/
        风险预警高亮区/模型分析展示区/溯源分析区/整改闭环区）

模块定位（[043] 分层拆分后的职责边界）：
    本模块是【纯组装层】——把上游各模块的既有输出（variance/滚动/积木/
    BSC/KPI/溯源/判定/整改）打包成看板五区的结构化数据（dict/list），
    供未来 UI 层与 AI 层直接消费。本模块【不重算任何数值】、不含任何
    界面/绘图逻辑——数值口径全部由上游模块负责，这里只做形态转换。

五区输出（对应完整版看板清单）：
    ① 预算基准对比区 → duibi_biao（variance 逐行：固定/滚动/实际/差额/率/FA/预警）；
    ② 风险预警高亮区 → yujing_huizong（四档预警计数）+ 各行 yujing 字段；
    ③ 模型分析展示区 → bingtu（积木四模块+未归属占比）+ zhexian（滚动趋势）
       + bsc_block（四维得分/总分/等级）+ kpi_block（15 项指标）；
    ④ 溯源分析区 → suyuan_block（逐项影响+正负向 TOP3）；
    ⑤ 整改闭环区 → zhenggai_block（整改清单+整改进度）+ panduan_block（判定）。

容错纪律（聚合层）：任一上游缺失（None）→ 对应块为空结构（空列表/空 dict），
    不抛错——端到端脚本任何阶段缺料都能拿到合法输出（看板显示"—"）。

使用示例（知识点速览，v0.1 2026-08-23；doctest 格式——离线可跑，
    由 tests/test_demos.py 守护；例题 = 一行差异 + 积木四模块的最小链路）：

    知识点 1 · 最小链路：对比表 + 饼图 + 预警汇总
    >>> from variance import ChayiShuru, YujingDang, jisuan_chayi
    >>> from building_blocks import JimuHang, chai_jimu, cong_chayi_xiang
    >>> chayi = jisuan_chayi([
    ...     ChayiShuru('2026-Q1', '材料价格差异', '成本类',
    ...                10_000_000, 10_000_000, 11_000_000),
    ... ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
    >>> jimu = chai_jimu([cong_chayi_xiang(chayi.xiang[0])])
    >>> jg = shengcheng_kanban(KanbanShuru(chayi=chayi, jimu=jimu))
    >>> len(jg.duibi_biao)
    1
    >>> jg.duibi_biao[0]['kemu'], jg.duibi_biao[0]['yujing']
    ('材料价格差异', '红')
    >>> (jg.yujing_huizong['hong_shu'], jg.bingtu['mokuai_lie'][3]['mokuai'])
    (1, '采购模块')

    知识点 2 · 上游缺失 → 空结构（容错，不抛错）
    >>> jg2 = shengcheng_kanban(KanbanShuru())
    >>> (jg2.duibi_biao, jg2.bingtu['mokuai_lie'])
    ([], [])

命名对照表（拼音标识符 → 中文含义）：
    KanbanShuru         看板输入（八个上游结果，鸭子类型，均可 None）
    KanbanShuju         看板数据（五区结构化输出）
    shengcheng_kanban   生成看板数据（主函数，纯组装）
    duibi_biao          预算基准对比区（variance 逐行 dict 列表）
    yujing_huizong      风险预警高亮区（四档计数）
    bingtu              积木差异占比饼图数据（四模块+未归属）
    zhexian             滚动预算趋势折线数据（逐期）
    relitu              风险热力图数据（期间×科目 差异率矩阵）
    bsc_block           BSC 四维得分/总分/等级
    kpi_block           KPI 15 项指标
    suyuan_block        溯源分析区（逐项影响+TOP3）
    panduan_block       判定结果区
    zhenggai_block      整改闭环区（清单+进度）

与上下游的关系：
    上游：variance / rolling_budget / building_blocks / bsc / kpi / suyuan /
          loop_decision / zhenggai（全部鸭子类型契约）；
    下游：UI 层（最后与看板界面一起做）、AI 层（报告生成读同一份数据）。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from dataclasses import dataclass

# ======================================================================
# 常量区
# ======================================================================

#: KPI 15 项：KpiJieguo 字段名 → 中文名（kpi_block 展示名；顺序 = 定稿 §8 清单）
KPI_MING = (
    ('yingshou_dachenglv_bps', '营收达成率'),
    ('chengben_kongzhilv_bps', '成本控制率'),
    ('feiyong_pianchalv_bps', '费用偏差率'),
    ('maolilv_bps', '毛利率'),
    ('jinglirunlv_bps', '净利润率'),
    ('xiaoshou_lirunlv_bps', '销售利润率'),
    ('zichan_zhouzhuanlv_bps', '资产周转率'),
    ('zijin_zhouzhuanlv_bps', '资金周转率'),
    ('caigou_chengben_bian_donglv_bps', '采购成本变动率'),
    ('gongyinglian_lvyuelv_bps', '供应链履约率'),
    ('channeng_liyonglv_bps', '产能利用率'),
    ('jiaofu_zhouqi_tian', '交付周期'),
    ('kehu_manyilv_bps', '客户满意度'),
    ('yewu_jindu_bps', '业务完成进度'),
    ('yichang_shijian_shu', '异常事项数量'),
)


# ======================================================================
# 数据结构区
# ======================================================================


@dataclass(frozen=True)
class KanbanShuru:
    """看板输入：八个上游结果对象（鸭子类型；None = 该块缺料）。

    字段说明：
        chayi:   variance.ChayiJieguo（对比表/热力图/预警汇总来源）。
        gundong: rolling_budget.GunDongJieguo（折线来源）。
        jimu:    building_blocks.JimuJieguo（饼图来源）。
        bsc:     bsc.BscJieguo（BSC 块来源）。
        kpi:     kpi.KpiJieguo（KPI 块来源）。
        suyuan:  suyuan.SuyuanJieguo（溯源块来源）。
        panduan: loop_decision.PanDuanJieguo（判定块来源）。
        zhenggai: zhenggai.ZhenggaiJieguo（整改块来源）。
    """

    chayi: object | None = None
    gundong: object | None = None
    jimu: object | None = None
    bsc: object | None = None
    kpi: object | None = None
    suyuan: object | None = None
    panduan: object | None = None
    zhenggai: object | None = None


@dataclass(frozen=True)
class KanbanShuju:
    """看板数据：五区结构化输出（全部 dict/list，零 UI、零重算）。

    字段说明（各区结构见模块头"五区输出"）：
        duibi_biao:     list[dict]——每行 {qijian, kemu, fangxiang, chushi_fen,
                       gundong_fen, shiji_fen, jizhun_fen, chae_fen, chalv_bps,
                       fa, yujing}（variance.ChayiXiang 全字段透传）。
        yujing_huizong: dict——{hong_shu, huang_shu, wu_shu, wufa_shu}。
        bingtu:         dict——{mokuai_lie: [{mokuai, chae_fen, fa, zhanbi_bps,
                       hang_shu}], weiguishu: {zhanbi_bps, hang_shu},
                       jing_heji_fen, hexin_mokuai}。
        zhexian:        list[dict]——{qijian, zhuangtai, shuzhi_fen,
                       chushi_yusuan_fen}（滚动逐期）。
        relitu:         dict——{qijian_lie, kemu_lie, juzhen}（差异率矩阵）。
        bsc_block:      dict——{caijing_defen, kehu_defen, neibu_defen,
                       xuexi_defen, quanzhong, zongfen, dengji}。
        kpi_block:      list[dict]——{mingcheng, zhi}（15 项，缺数 None）。
        suyuan_block:   dict——{xiang, zhengxiang_top3, fuxiang_top3,
                       yingxiang_fenmu_bps}。
        panduan_block:  dict——{panduan, qingxing, shenpi}。
        zhenggai_block: dict——{qingdan, gao_shu, zhong_shu, di_shu, zong_shu,
                       daizhenggai_shu, jinxingzhong_shu, wancheng_shu}。
    """

    duibi_biao: list[dict]
    yujing_huizong: dict
    bingtu: dict
    zhexian: list[dict]
    relitu: dict
    bsc_block: dict
    kpi_block: list[dict]
    suyuan_block: dict
    panduan_block: dict
    zhenggai_block: dict


# ======================================================================
# 各区组装函数区（每区一个函数——只做形态转换，不重算）
# ======================================================================


def _zhuang_duibi(chayi: object | None) -> tuple[list[dict], dict]:
    """① 预算基准对比区 + ② 预警汇总：variance 逐行透传 + 四档计数。"""
    if chayi is None:
        return [], {'hong_shu': 0, 'huang_shu': 0, 'wu_shu': 0, 'wufa_shu': 0}
    duibi = []
    for x in chayi.xiang:
        # 全字段透传（键 = ChayiXiang 字段名）——UI/AI 层直接消费
        duibi.append({
            'qijian': x.qijian, 'kemu': x.kemu, 'fangxiang': x.fangxiang,
            'chushi_fen': x.chushi_fen, 'gundong_fen': x.gundong_fen,
            'shiji_fen': x.shiji_fen, 'jizhun_fen': x.jizhun_fen,
            'chae_fen': x.chae_fen, 'chalv_bps': x.chalv_bps,
            'fa': x.fa, 'yujing': x.yujing,
        })
    huizong = {
        'hong_shu': chayi.hong_shu,
        'huang_shu': chayi.huang_shu,
        'wu_shu': chayi.wu_shu,
        'wufa_shu': chayi.wufa_shu,
    }
    return duibi, huizong


def _zhuang_bingtu(jimu: object | None) -> dict:
    """③ 模型分析区·饼图：积木四模块 + 未归属（占比直接透传）。"""
    if jimu is None:
        return {'mokuai_lie': [], 'weiguishu': {'zhanbi_bps': None, 'hang_shu': 0},
                'jing_heji_fen': 0, 'hexin_mokuai': None}
    return {
        'mokuai_lie': [
            {'mokuai': x.mokuai, 'chae_fen': x.chae_fen, 'fa': x.fa,
             'zhanbi_bps': x.zhanbi_bps, 'hang_shu': x.hang_shu}
            for x in jimu.mokuai_lie
        ],
        'weiguishu': {'zhanbi_bps': jimu.weiguishu_zhanbi_bps,
                      'hang_shu': len(jimu.weiguishu_lie)},
        'jing_heji_fen': jimu.jing_heji_fen,
        'hexin_mokuai': jimu.hexin_mokuai,
    }


def _zhuang_zhexian(gundong: object | None) -> list[dict]:
    """③ 模型分析区·折线：滚动预算逐期透传。"""
    if gundong is None:
        return []
    return [
        {'qijian': t.qijian, 'zhuangtai': t.zhuangtai,
         'shuzhi_fen': t.shuzhi_fen, 'chushi_yusuan_fen': t.chushi_yusuan_fen}
        for t in gundong.qijian_mingxi
    ]


def _zhuang_relitu(chayi: object | None) -> dict:
    """② 风险热力图：期间 × 科目 的差异率矩阵（variance 行 → 二维表）。"""
    if chayi is None or not chayi.xiang:
        return {'qijian_lie': [], 'kemu_lie': [], 'juzhen': []}
    # 期间/科目去重排序（首次出现序保持稳定，不重排语义）
    qijian_lie = sorted({x.qijian for x in chayi.xiang})
    kemu_lie = sorted({x.kemu for x in chayi.xiang})
    zhizhen = {(x.qijian, x.kemu): x.chalv_bps for x in chayi.xiang}
    juzhen = [[zhizhen.get((q, k)) for k in kemu_lie] for q in qijian_lie]
    return {'qijian_lie': qijian_lie, 'kemu_lie': kemu_lie, 'juzhen': juzhen}


def _zhuang_bsc(bsc: object | None) -> dict:
    """③ 模型分析区·BSC：四维得分/权重/总分/等级透传。"""
    if bsc is None:
        return {'caijing_defen': None, 'kehu_defen': None, 'neibu_defen': None,
                'xuexi_defen': None, 'quanzhong': None, 'zongfen': None,
                'dengji': None}
    return {
        'caijing_defen': bsc.caijing_defen, 'kehu_defen': bsc.kehu_defen,
        'neibu_defen': bsc.neibu_defen, 'xuexi_defen': bsc.xuexi_defen,
        'quanzhong': bsc.quanzhong, 'zongfen': bsc.zongfen, 'dengji': bsc.dengji,
    }


def _zhuang_kpi(kpi: object | None) -> list[dict]:
    """③ 模型分析区·KPI：15 项指标（字段名 → 中文名，缺数 None 透传）。"""
    if kpi is None:
        return [{'mingcheng': ming, 'zhi': None} for _, ming in KPI_MING]
    return [{'mingcheng': ming, 'zhi': getattr(kpi, ziming)}
            for ziming, ming in KPI_MING]


def _zhuang_suyuan(suyuan: object | None) -> dict:
    """④ 溯源分析区：逐项影响 + 正负向 TOP3（透传）。"""
    if suyuan is None:
        return {'xiang': [], 'zhengxiang_top3': [], 'fuxiang_top3': [],
                'yingxiang_fenmu_bps': 0}
    return {
        'xiang': [
            {'kpi_mingcheng': x.kpi_mingcheng, 'yingxianglv_bps': x.yingxianglv_bps,
             'shuzhi_fangxiang': x.shuzhi_fangxiang, 'zuoyong': x.zuoyong,
             'zhanbi_bps': x.zhanbi_bps}
            for x in suyuan.xiang
        ],
        'zhengxiang_top3': suyuan.zhengxiang_top3,
        'fuxiang_top3': suyuan.fuxiang_top3,
        'yingxiang_fenmu_bps': suyuan.yingxiang_fenmu_bps,
    }


def _zhuang_panduan(panduan: object | None) -> dict:
    """判定结果区：判定/情形/审批标志（透传）。"""
    if panduan is None:
        return {'panduan': None, 'qingxing': None, 'shenpi': None}
    return {
        'panduan': getattr(panduan, 'panduan', None),
        'qingxing': getattr(panduan, 'qingxing', None),
        'shenpi': getattr(panduan, 'shenpi', None),
    }


def _zhuang_zhenggai(zhenggai: object | None) -> dict:
    """⑤ 整改闭环区：整改清单（逐项透传）+ 优先级与进度计数。"""
    if zhenggai is None:
        return {'qingdan': [], 'gao_shu': 0, 'zhong_shu': 0, 'di_shu': 0,
                'zong_shu': 0, 'daizhenggai_shu': 0, 'jinxingzhong_shu': 0,
                'wancheng_shu': 0}
    return {
        'qingdan': [
            {'leixing': x.leixing, 'youxianji': x.youxianji,
             'zeren_mokuai': x.zeren_mokuai, 'kemu': x.kemu, 'qijian': x.qijian,
             'miaoshu': x.miaoshu, 'shenpi': x.shenpi, 'zhuangtai': x.zhuangtai}
            for x in zhenggai.qingdan
        ],
        'gao_shu': zhenggai.gao_shu, 'zhong_shu': zhenggai.zhong_shu,
        'di_shu': zhenggai.di_shu, 'zong_shu': zhenggai.zong_shu,
        'daizhenggai_shu': zhenggai.daizhenggai_shu,
        'jinxingzhong_shu': zhenggai.jinxingzhong_shu,
        'wancheng_shu': zhenggai.wancheng_shu,
    }


# ======================================================================
# 对外接口区（唯一的组装入口）
# ======================================================================


def shengcheng_kanban(shuru: KanbanShuru) -> KanbanShuju:
    """生成看板数据（方案B 步骤 7 的计算前置；纯组装函数，不重算）。

    参数：shuru —— KanbanShuru（八个上游结果，均可缺省 None）。

    返回：KanbanShuju（五区结构化输出；缺料块为空结构，不抛错）。
    """
    if not isinstance(shuru, KanbanShuru):
        raise TypeError(f'输入必须是 KanbanShuru：{shuru!r}')

    duibi, huizong = _zhuang_duibi(shuru.chayi)
    return KanbanShuju(
        duibi_biao=duibi,
        yujing_huizong=huizong,
        bingtu=_zhuang_bingtu(shuru.jimu),
        zhexian=_zhuang_zhexian(shuru.gundong),
        relitu=_zhuang_relitu(shuru.chayi),
        bsc_block=_zhuang_bsc(shuru.bsc),
        kpi_block=_zhuang_kpi(shuru.kpi),
        suyuan_block=_zhuang_suyuan(shuru.suyuan),
        panduan_block=_zhuang_panduan(shuru.panduan),
        zhenggai_block=_zhuang_zhenggai(shuru.zhenggai),
    )
