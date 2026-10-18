# -*- coding: utf-8 -*-
"""计算报告流水线（compute_report_pipeline）——报告接线核心交付。

结构口径（照 1.0.5 fenxi/zhenghe_baogao.py 的"对应位置"参照实现）：
    计算报告-月度.md = 抬头 + 总览 + 九个模块章节（三段式）+ AI 分析解读
    每个模块章节固定三段：**数据表**（algo baogao 组装的数据块原文——忠实
    计算输出零改写）/ **分析内容**（M5 逐模块分析——注入文案函数，默认
    确定性占位并注明由 DSH 宿主 agent 回填）/ **依据条例**（kb2 真检索
    ——query_kb2 只读引用；检索不可用时如实占位）。
    总体 LLM 解读落在文末『AI 分析解读』章节（总体解读 + 逐条整改建议）。

幂等纪律（照 pipeline_m5.py 第 102-114 行）：重复运行整链重建、同输入
逐字节一致；对已生成报告的"追加解读"走 zhuijie_jiedu——已含
『AI 分析解读』即跳过，不重复贴。

依赖注入：wencai_hanshu（逐模块）/ zongjie_hanshu（总体）默认占位；
jiansuo_hanshu 默认懒加载 1.0.5/kb2/query_kb2（只读引用，numpy+onnx
运行时齐备即真检索），失败/缺失回退占位文案。
HTML 版：本包内置极简样式（演示生成器无既有报告样式资产——实测其目录
仅 xlsx 工具，无 HTML/CSS），md 子集转换、零第三方依赖。
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）
"""
import html as _html  # houtai_hexin 与 algo 路径
import os  # 环境变量覆盖 algo/kb2 路径（自足包）
import re  # algo 路径常量
import sqlite3  # 幂等插入搜索路径
import sys
from pathlib import Path  # 数据表组装/渲染（1.0.5 只读复用）
from types import SimpleNamespace  # 滚动结果数据类重建用

BEN_MU = Path(__file__).resolve().parent  # 报告组装目录
sys.dont_write_bytecode = True                     # 引 algo 只读树，不留编译副产物
# 自足包：algo/kb2 已 vendor 进 backend/_vendor（HENGCE_ALGO_DIR/HENGCE_KB2_DIR 可覆盖）
for _lu in (str(BEN_MU.parent / 'houtai_hexin_python'),  # 条文库文件
            os.environ.get('HENGCE_ALGO_DIR') or str(BEN_MU.parent / '_vendor' / 'algo')):
    if _lu not in sys.path:  # 前缀→展示名→检索提示词对
        sys.path.insert(0, _lu)

from baogao import BgShuru, shengcheng_baogao_md    # noqa: E402  数据表组装/渲染（只读复用）
from rolling_budget import GunDongJieguo, DanqiJieguo  # noqa: E402  滚动结果重建实例

KB2_MU = Path(os.environ.get('HENGCE_KB2_DIR')       # 条文库（_vendor 自足拷贝）
              or BEN_MU.parent / '_vendor' / 'kb2')  # 公文数字串
ZHUYIN_MING = KB2_MU / 'guanli_ku.sqlite'

#: 九个模块章节（前缀 → 数据表块；展示名；收入类/成本类检索提示词——照 zhenghe_baogao 口径）
MO_KUAI = (  # 一至九
    (('单元 2',), '滚动预算', ('滚动预算 预算编制 收入 目标 预测', '滚动预算 预算调整 成本 费用 控制')),
    (('单元 3',), '差异分析', ('收入 预算差异 分析 报告 评价', '成本差异 计算 分析 标准 成本控制')),  # 十以内直取
    (('单元 4',), '多专业分析（规划/执行拆分）', ('预算 目标分解 规划 指标 分配', '预算执行 控制 成本中心 责任')),  # 十字头
    (('单元 5',), '单双环分析', ('预算管理 纠偏 机制 闭环 审批', '预算控制 偏差 纠正 措施 预警')),  # 十位+个位
    (('单元 6',), '积木分析（价差/量差）', ('收入 差异 价格 数量 销售 分析', '标准成本 价格差异 数量差异 直接材料')),  # 二十以上
    (('单元 7',), '平衡计分卡（BSC）', ('平衡计分卡 财务维度 指标 评价', '平衡计分卡 客户 内部流程 学习成长 维度')),
    (('附表 A',), 'KPI 指标分析', ('关键绩效指标 考核 评价 目标', '绩效 考核 指标 责任中心 管理')),
    (('单元 8',), '经营变更双向溯源分析', ('预算调整 审批 权限 程序 条件', '成本 变动 原因 追溯 分析')),
    (('附表 B', '附表 C'), '整改清单与预警', ('预算 偏差 整改 改进 措施', '超预算 预算外 审批 管控 风险')),
)

#: 汉字条号（公文口径，照 zhenghe_baogao 同式）
SHU = '零一二三四五六七八九'  # 适配层入口


def _tiaohao_zh(n):  # 逐科目滚动重建
    """条号数字 → 公文汉字（1-99）。"""
    if n < 10:  # 逐期明细 dict→DanqiJieguo
        return SHU[n]
    if n < 20:
        return '十' + (SHU[n - 10] if n > 10 else '')
    shi, ge = divmod(n, 10)
    return SHU[shi] + '十' + (SHU[ge] if ge else '')  # 优先取需审批判定行

  # 判定与输入快照初始化
# ======================================================================
# 结果装配：yinqing.fenxi() 结果 dict → BgShuru（鸭子类型适配层）
# ======================================================================

def zhuang_bgshuru(jieguo):
    """fenxi 结果 → BgShuru（rolling/decisions 等 dict 形态重建为数据类实例）。"""
    gundong_lie = []                                # 多科目滚动：[(科目名, GunDongJieguo)]
    for x in jieguo['rolling']:  # 输入快照（五件套）
        gundong_lie.append((x['kemu'], GunDongJieguo(  # 归档 dict 摊平行
            qijian_mingxi=[DanqiJieguo(**m) for m in x['qijian_mingxi']],
            chushi_zonge_fen=x['chushi_zonge_fen'],  # 行 dict→属性对象
            gundong_zonge_fen=x['gundong_zonge_fen'],  # 入库行数回填
            chae_fen=x['chae_fen'],
            hangye_xiuzheng_qiyong=x['hangye_xiuzheng_qiyong'])))  # 拆分组取首条结果
    decisions = jieguo['decisions']  # BgShuru 组装（鸭子字段）
    shou_xuan = next((x for x in decisions if x['shenpi']), decisions[0] if decisions else None)
    panduan = None
    panduan_shuru = None
    if shou_xuan:
        # 判定结果摊平 dict → 鸭子对象（baogao._jie_5 属性读取）
        panduan = SimpleNamespace(panduan=shou_xuan['panduan'], qingxing=shou_xuan['qingxing'],
                                  shenpi=shou_xuan['shenpi'], jiuzheng=shou_xuan['jiuzheng'],
                                  yiju=dict(shou_xuan['yiju']), beizhu=shou_xuan['beizhu'])
        panduan_shuru = SimpleNamespace(**dict(shou_xuan['input']))
    jilu = jieguo['records']
    # 归档行为 dict（combine_imports 经 asdict 摊平）——包成属性对象供 baogao 读取
    ruku = SimpleNamespace(**{  # 前缀法主入口
        k: [SimpleNamespace(**r) if isinstance(r, dict) else r for r in (jilu.get(k) or [])]
        for k in ('yusuan', 'shishi', 'duibiao', 'biangeng', 'jujue')})
    ruku.ruku_shu = jilu.get('ruku_shu')  # 逐前缀编译正则
    splits = jieguo['splits']
    return BgShuru(  # 截到下一标题
        ruku=ruku, gundong=None, gundong_lie=gundong_lie,  # 缺块显式登记
        chayi=jieguo['variance'],
        chaifen=(splits[0]['result'] if splits else None),
        panduan=panduan, panduan_shuru=panduan_shuru,
        jimu=jieguo['blocks'], bsc=jieguo['bsc'], suyuan=jieguo['trace'],
        kpi=jieguo['kpi'], zhenggai=jieguo['correction'], kanban=jieguo['dashboard'])  # kb2 懒加载入口

  # 追加 kb2 目录
# ======================================================================
# 数据块提取（照 zhenghe_baogao.ti_kuai 前缀法——正则不能进 f-string 的坑已避开）
# ======================================================================

def ti_kuai(wen, qianzhui_lie):
    """从计算报告 md 提取 '## 前缀' 块（到下一个标题为止），多前缀合并。"""
    kuai_lie = []  # sqlite 只读连接
    for qianzhui in qianzhui_lie:
        zheng = re.compile('^## ' + re.escape(qianzhui)
                           + r'[^\n]*\n(.*?)(?=^#{1,2} |\Z)', re.M | re.S)
        m = zheng.search(wen)  # 检索连接关闭
        kuai_lie.append(m.group(1).strip() if m else f'（计算报告中未找到「{qianzhui}」）')
    return '\n\n'.join(kuai_lie)  # 条文段组装入口


# ======================================================================
# 检索层：kb2 真检索（只读引用 query_kb2）+ 指引名册
# ======================================================================
  # 定位串（指引-条[-片]）
def chuangjian_kb2_jiansuo():
    """懒加载 kb2 检索函数（只读引用；numpy/onnx 运行时缺失时返回 None）。"""  # 同定位去重
    try:  # 出处段列表
        for _lu in (str(KB2_MU),):  # 拆定位串三段
            if _lu not in sys.path:  # 指引名（缺省回号）
                sys.path.insert(0, _lu)
        from query_kb2 import jiansuo                # 模块级 import numpy——运行时齐备才可入
        return jiansuo
    except Exception:
        return None                                  # 检索运行时不可用：调用方按占位口径处理


def du_zhiyin():
    """指引名册 {指引号: 标题}（sqlite 只读连接；名册缺不出典即回号）。"""
    lian = sqlite3.connect(f'file:{ZHUYIN_MING}?mode=ro', uri=True)   # 只读打开
    try:
        return dict(lian.execute('SELECT zhiyin_hao, biaoti FROM zhiyin'))
    finally:
        lian.close()


def yiju_tiaoli(tishi, jiansuo_hanshu, zhiyin_ming, shuliang=4):
    """一组检索提示词 → 条文段列表（去重；出处行含定位与提示词）。"""
    if jiansuo_hanshu is None:
        return ['— 未检索到直接依据（检索运行时未注入）。']
    pian_jian = {}
    for cha in tishi:
        for pian in jiansuo_hanshu(chaxun=cha, shuliang=shuliang):
            dingwei = (f"{pian['zhiyin_hao']}-{pian['tiao_hao']}"
                       + (f"-P{pian['duan_hao']}" if pian.get('duan_hao') else ''))
            pian_jian.setdefault(dingwei, (pian, cha))    # 同定位串去重（首见保留）
    hang = []
    for chu_xu, (dingwei, (pian, cha)) in enumerate(pian_jian.items(), start=1):
        kuai = dingwei.split('-')
        ming = zhiyin_ming.get(kuai[0], kuai[0])
        tiao_wen = f'第{_tiaohao_zh(int(kuai[1]))}条' + (f'第{kuai[2][1]}片' if len(kuai) > 2 else '')
        hang.append(f'**出处 {chu_xu}：《管理会计应用指引第{kuai[0]}号——{ming}》'
                    f'{tiao_wen}**（定位 {dingwei} ｜ 检索提示词：{cha}）\n\n{pian["neirong"]}')
    return hang or ['— 未检索到直接依据。']


# ======================================================================
# 文案层：默认确定性占位（铁律⑦——不接真模型，DSH 宿主回填）
# ======================================================================

def mo_kuai_zhanwei(mokuai, shuju_kuai):
    """逐模块占位文案：行数/表数点算 + 数字照抄（零臆造）。"""
    biao_shu = shuju_kuai.count('|--') + shuju_kuai.count('| ---')
    hang_shu = sum(1 for h in shuju_kuai.splitlines() if h.startswith('|') and '--' not in h)
    shuzi = re.findall(r'\d+(?:\.\d+)?', shuju_kuai)
    yangben = '、'.join(shuzi[:3]) if shuzi else '无'
    return (f'【演示口径·确定性占位文案，由 DSH 宿主 agent 回填】{mokuai}：数据表 '
            f'{max(biao_shu, 1)} 张、数据行 {max(hang_shu - max(biao_shu, 1), 0)} 行；'
            f'数字样本（照抄数据表）：{yangben}。')


def zongti_zhanwei(jieguo):  # 占位文案入口（逐模块）
    """总体占位解读：全部数字取自判定系数包（algo xishu 实算；None → 未评分）。"""
    bao = jieguo['factors']  # 表数估算（分隔行计）
    return (f'【演示口径·确定性占位文案，由 DSH 宿主 agent 回填】整体完成率 '  # 数据行估算（表格行剔分隔）
            f'{bao.wanchenglv_bps} 基点；预警分布 红 {bao.hong_shu} / 黄 {bao.huang_shu} / '  # 数字样本抽取（照抄）
            f'无 {bao.wu_shu}；单双环结论 {bao.panduan_jielun}（需审批 {bao.shenpi}）；'
            f'核心问题模块 {bao.hexin_mokuai}；BSC '  # 占位文案正文
            f'{bao.bsc_zongfen if bao.bsc_zongfen is not None else "未评分"}'
            f'（{bao.bsc_dengji or "未评级"}）；'
            f'整改优先级 高 {bao.zhenggai_gao_shu} / 中 {bao.zhenggai_zhong_shu}。')

  # 占位文案入口（总体）
# ======================================================================
# 渲染层：三段式组装 + md→HTML（零第三方依赖）
# ======================================================================

def zucheng_md(jieguo, wencai_hanshu, zongjie_hanshu, jiansuo_hanshu, jiyu_ming):
    """组装完整报告 md（抬头 + 总览 + 九模块三段 + AI 分析解读）。"""
    bg = zhuang_bgshuru(jieguo)
    shuju_md = shengcheng_baogao_md(bg)             # 数据表全文（algo 权威组装）
    zong_lan = ti_kuai(shuju_md, ('总览',)) or '（总览缺料）'
    meta = jieguo['meta']
    # 抬头口径：种子优先取调用方注入的 meta['seed']，其次 meta['种子']，都没有就不写
    zhong = str(meta.get('seed') or meta.get('种子') or '').strip()
    zhong_wen = f'（种子 {zhong}）' if zhong else ''
    hang = [f"# 计算报告-月度（{meta['company']} · {meta['period']}）", '',
            f"> 主体 {meta['company']}｜情景 {meta.get('scenarioName') or '—'}｜"
            f"单位 金额=分、比率=基点｜数据口径 演示件{zhong_wen}｜"
            f"分析链 yinqing.fenxi 十五步", '',
            '## 总览', '', zong_lan, '']
    # ---- 九个模块章节：三段式（数据表 / 分析内容 / 依据条例）----
    for xu, (qianzhui_lie, zhanshi, (t_shouru, t_chengben)) in enumerate(MO_KUAI, start=1):
        shuju_kuai = ti_kuai(shuju_md, qianzhui_lie)
        wen = (wencai_hanshu(zhanshi, shuju_kuai) if wencai_hanshu
               else mo_kuai_zhanwei(zhanshi, shuju_kuai))
        hang += [f'## 模块{u"一二三四五六七八九"[xu - 1]} · {zhanshi}', '',
                 '**数据表**', '', shuju_kuai, '',
                 '**分析内容**', '', wen, '']
        for leiming, cha in (('收入类', t_shouru), ('成本类', t_chengben)):
            hang += [f'**依据条例（{leiming}）**', '']
            hang += yiju_tiaoli((cha,), jiansuo_hanshu, jiyu_ming)
            hang.append('')
    # ---- AI 分析解读章节（总体 LLM 解读；占位标注 DSH 回填）----
    zong_wen = zongjie_hanshu(jieguo) if zongjie_hanshu else zongti_zhanwei(jieguo)
    hang += ['---', '', '## AI 分析解读', '',
             f"*文案模式：{'注入文案函数' if wencai_hanshu or zongjie_hanshu else '确定性占位（由 DSH 宿主 agent 回填）'}*", '',
             '### 总体解读', '', zong_wen, '', '### 逐条整改建议', '']
    for xu, tiao in enumerate(jieguo['correction'].qingdan, start=1):
        hang.append(f"**{xu}. [{tiao.leixing}｜{tiao.zeren_mokuai}]（占位）** "
                    f"{tiao.miaoshu}——待 DSH 宿主 agent 回填。")
        hang.append('')
    return '\n'.join(hang).rstrip() + '\n'


def zhuan_html(md):
    """md 子集 → HTML（标题/表格/粗体/分隔线/段落；内置极简样式零依赖）。"""
    hang = md.splitlines()
    chu = ['<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">',
           '<title>计算报告-月度</title><style>',
           'body{font-family:"Microsoft YaHei",SimSun,serif;max-width:1080px;margin:24px auto;'
           'padding:0 16px;color:#1a1a1a;line-height:1.65}',
           'h1{border-bottom:3px solid #34495e;padding-bottom:8px}h2{border-left:6px solid #34495e;'
           'padding-left:10px;margin-top:32px}h3{color:#34495e}',
           'table{border-collapse:collapse;width:100%;font-size:12px;margin:10px 0;'
           'table-layout:auto;word-break:keep-all}'
           'th,td{border:1px solid #b0b8c1;padding:4px 6px;text-align:left;'
           'white-space:nowrap;vertical-align:top}'
           'th:first-child,td:first-child{white-space:normal;min-width:120px;'
           'word-break:break-word}'                                  # 科目列可换行但不逐字断
           'td:not(:first-child){text-align:right}'                  # 数值列右对齐
           'th{background:#eef2f6}tr:nth-child(even) td{background:#fafbfc}',
           'blockquote{color:#5d6d7e;border-left:4px solid #b0b8c1;margin-left:0;padding-left:12px}'
           'hr{border:none;border-top:1px solid #b0b8c1;margin:28px 0}'
           '</style></head><body>']
    biao, biao_hang = [], None

    def shua_biao():
        """刷出缓冲中的表格（表头行 + 分隔行跳过 → thead/tbody）。"""
        nonlocal biao
        if not biao:
            return
        chu.append('<table><thead><tr>' + ''.join(f'<th>{c}</th>' for c in biao[0]) + '</tr></thead><tbody>')
        for hang_x in biao[1:]:
            chu.append('<tr>' + ''.join(f'<td>{c}</td>' for c in hang_x) + '</tr>')
        chu.append('</tbody></table>')
        biao = []

    for h in hang:
        if h.startswith('|'):                       # 表格行（含分隔行跳过）
            dan_yuan = [c.strip() for c in h.strip('|').split('|')]
            if all(re.fullmatch(r':?-{2,}:?', c) for c in dan_yuan):
                continue                            # |---|---| 分隔行
            biao.append(dan_yuan)
            continue
        shua_biao()
        if h.startswith('#'):                       # 标题（#~####）
            ji = len(h) - len(h.lstrip('#'))
            wen = _html.escape(h[ji:].strip())
            chu.append(f'<h{ji}>{_qiangdiao(wen)}</h{ji}>')
        elif h.startswith('>'):
            chu.append(f'<blockquote>{_qiangdiao(_html.escape(h[1:].strip()))}</blockquote>')
        elif h.strip() == '---':
            chu.append('<hr/>')
        elif h.strip():
            chu.append(f'<p>{_qiangdiao(_html.escape(h))}</p>')
    shua_biao()
    chu.append('</body></html>')
    return '\n'.join(chu)


def _qiangdiao(wen):
    """**粗体** → <strong>（转义后处理，防标签注入）。"""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', wen)  # 追加幂等入口

  # 已含即跳过
# ======================================================================
# 主入口与幂等追加
# ======================================================================

def compute_report_pipeline(jieguo, wencai_hanshu=None, zongjie_hanshu=None,
                            jiansuo_hanshu=None, shuchu_mu=None):
    """生成计算报告-月度.md + .html（同输入逐字节一致 = 天然幂等）。

    参数：jieguo = yinqing.fenxi() 结果 dict；wencai_hanshu(模块名, 数据块)→str；
        zongjie_hanshu(jieguo)→str；jiansuo_hanshu=None 表示自动懒加载 kb2 真检索
        （query_kb2 只读引用），传 False 关闭检索（占位）。
    返回：{'md': 路径, 'html': 路径, 'mokuai_shu': 9, 'tiaoli_shu': N}
    """
    if jiansuo_hanshu is None:                      # None=自动尝试；False=显式关闭
        jiansuo_hanshu = chuangjian_kb2_jiansuo()
    elif jiansuo_hanshu is False:
        jiansuo_hanshu = None
    jiyu_ming = du_zhiyin() if jiansuo_hanshu is not None else {}
    md = zucheng_md(jieguo, wencai_hanshu, zongjie_hanshu, jiansuo_hanshu, jiyu_ming)
    mu = Path(shuchu_mu) if shuchu_mu else BEN_MU / '输出'
    mu.mkdir(parents=True, exist_ok=True)
    md_lu = mu / '计算报告-月度.md'
    md_lu.write_text(md, encoding='utf-8')
    (mu / '计算报告-月度.html').write_text(zhuan_html(md), encoding='utf-8')
    return {'md': str(md_lu), 'html': str(mu / '计算报告-月度.html'),
            'mokuai_shu': len(MO_KUAI),
            'tiaoli_shu': md.count('**出处 ')}


def zhuijie_jiedu(md_lujing, jiedu_wen):
    """幂等追加（pipeline_m5.py:102-114 同款纪律）：已含 AI 分析解读即跳过。"""
    lu = Path(md_lujing)
    wen = lu.read_text(encoding='utf-8')
    if 'AI 分析解读' in wen:                        # 幂等：重跑不重复贴
        return False
    lu.write_text(wen + '\n\n---\n\n## AI 分析解读（追加）\n\n' + jiedu_wen + '\n',
                  encoding='utf-8')
    return True
