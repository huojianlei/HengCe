# -*- coding: utf-8 -*-
"""计算报告流水线（compute_report_pipeline）——报告接线核心交付。

结构口径（照 1.0.5 fenxi/zhenghe_baogao.py 的"对应位置"参照实现）：
    计算报告-月度.md = 抬头 + 总览 + 九个模块章节（三段式）+ AI 分析解读
    每个模块章节固定三段：**数据表**（algo baogao 组装的数据块原文——忠实
    计算输出零改写）/ **分析内容**（M5 逐模块分析——注入文案函数，默认
    确定性占位并注明由 DSH 宿主 agent 回填）/ **依据条例**（kb2 真检索
    ——query_kb2 只读引用；检索不可用时如实占位）。
    总体 LLM 解读落在文末『AI 分析解读』章节（总体解读 + 逐条整改建议）。

AI 标注口径（统一文案，一字不改）：
    只有内容真的由注入的文案函数生成才贴 AI 标注——wencai_hanshu 命中某个模块
    的『分析内容』时，在该段标题下贴 `> 内容为AI生成，仅供参考`；zongjie_hanshu
    命中『AI 分析解读』时，在章标题下与『### 总体解读』下各贴一行；两者任一注入
    （整篇含 AI 内容）时，在抬头元信息后补 `> 本报告含 AI 生成内容，仅供参考`。
    mo_kuai_zhanwei / zongti_zhanwei 的确定性占位不是 AI 生成：不贴 AI 标注，
    只保留原有的占位说明——不能把占位文案冒充成模型输出。标注行按固定位置插入，
    同一输入重复生成仍逐字节一致（幂等）。

JSON 口径（改造规范第四节）：
    zucheng_json() 与 md 共用同一次汇总（huibian_neirong）的中间结果，
    compute_report_pipeline 在同目录落 计算报告-月度.json。金额一律整数分、
    比率一律整数基点，JSON 内原值照抄，不做单位换算、不转浮点——消费方按
    meta.unit 的口径自行格式化，保证 md 与 JSON 的数字可逐项对账。

幂等纪律（照 pipeline_m5.py 第 102-114 行）：重复运行整链重建、同输入
逐字节一致；对已生成报告的"追加解读"走 zhuijie_jiedu——已含
『AI 分析解读』即跳过，不重复贴。JSON 的 generatedAt 不读当前时钟，按
「显式参数 > 环境变量 > meta 生成时间 > 种子日期」的固定顺序取值。

依赖注入：wencai_hanshu（逐模块）/ zongjie_hanshu（总体）默认占位；
jiansuo_hanshu 默认懒加载 1.0.5/kb2/query_kb2（只读引用，numpy+onnx
运行时齐备即真检索），失败/缺失回退占位文案。
HTML 版：本包内置极简样式（演示生成器无既有报告样式资产——实测其目录
仅 xlsx 工具，无 HTML/CSS），md 子集转换、零第三方依赖；含 AI 内容时
在 </body> 前补统一的页脚标注。
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）
"""
import html as _html  # houtai_hexin 与 algo 路径
import json  # JSON 版报告序列化（ensure_ascii=False 保中文）
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

#: AI 生成标注：只贴在真由注入文案函数产出的段落/章节上（一字不改）
AI_BIAOZHU = '内容为AI生成，仅供参考'
#: 整篇含 AI 内容时的抬头提示与 HTML 页脚（任一文案函数注入即出现）
AI_TAITOU = '本报告含 AI 生成内容，仅供参考'
#: JSON 版报告的 schema 标识；字段/层级变更须同步升版，消费方按它判版
JSON_SCHEMA = 'hengce.report/1'
#: 金额/比率口径措辞：md 抬头与 JSON meta.unit 共用，避免两处口径漂移
DANWEI_KOUJING = '金额=分、比率=基点'
#: 整改建议占位后缀（与 1.0.5 桥接入口 _ai_zhenggai 的回填锚点保持一致）
ZHENGGAI_ZHANWEI = '待 DSH 宿主 agent 回填'
#: 依据条例两种占位：检索运行时未注入 / 真检索但没命中
WEI_JIANSUO_ZHURU = '— 未检索到直接依据（检索运行时未注入）。'
WEI_JIANSUO = '— 未检索到直接依据。'

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
# 表格解析（md 表格 → JSON 结构化 columns/rows/align/raw/rest）
# ======================================================================

# 对齐分隔行单元格的合法形态：---、---:、:--:（md 表格第二行的语法）
BIAO_FENGE = re.compile(r':?-+:?')


def _biao_dange(hang):
    """md 表格行 → 单元格文字数组。

    口径：去掉首尾竖线与每个单元格两端空白，**单元格文字一律保留原文**——
    千分位（1,234.56）、百分号（9.01%）、破折号（—）都不做任何转换，避免在
    JSON 里引入数值语义歧义；数值如何解释交给消费方按 meta.unit（分/基点）。
    """
    wen = hang.strip()
    if wen.startswith('|'):                          # 首尾竖线是表格语法，不是数据
        wen = wen[1:]
    if wen.endswith('|'):
        wen = wen[:-1]
    return [ge.strip() for ge in wen.split('|')]


def _biao_fenge(hang):
    """判断该行是否表格对齐分隔行；是则返回各列对齐（left/center/right），否则 None。

    对齐来源就是 md 分隔行的冒号：:--- 左、---: 右、:---: 居中、无冒号按左
    （与 zhuan_html 渲染时 sup 的缺省口径一致，机器侧不必再猜）。
    """
    dange = _biao_dange(hang)
    if not dange or not all(BIAO_FENGE.fullmatch(ge) for ge in dange):
        return None
    duiqi = []
    for ge in dange:
        zuo, you = ge.startswith(':'), ge.endswith(':')
        duiqi.append('center' if zuo and you else ('right' if you else 'left'))
    return duiqi


def jiegou_biaoge(shuju_kuai):
    """数据表 markdown 块 → 结构化 dict（JSON 直接可读）；整块无表格时返回 None。

    为什么要这么拆：报告的「数据表」块不一定只装一张表——实际存在
    「首表 + 空行/说明行 + 子标题 + 又一张列数不同的表」的形态（模块四的判断表
    与 5.1 对比表，模块九的整改清单 + 附表 C 预警表）。因此：
      * columns/rows/align/raw 取块内**第一张表**（表头、表体、对齐、原文），
        raw 与该表原文逐行一致，供幂等核对与向下兼容；
      * 块内其余文字与后续表格原样放进 rest，一个字不丢（消费方需要全文时
        用 raw + rest，需要表格时只读 columns/rows）；
      * 列宽以首表表头为准：短行补空串、长行按表头列数截断，保证
        len(columns) == len(rows[i])，机器侧不用再判长短；
      * 整块没有 md 表格（如「（缺料）」这类缺料占位）返回 None，而不是造空数组。
    """
    raw = shuju_kuai if isinstance(shuju_kuai, str) else ''
    hang = raw.split('\n')
    kai = None                                       # 首表表头所在行号
    for i, h in enumerate(hang):
        if not h.lstrip().startswith('|'):
            continue
        if i + 1 < len(hang) and _biao_fenge(hang[i + 1]):
            kai = i                                  # 下一行是对齐分隔行才认表头
            break
    if kai is None:
        return None                                  # 整块不是表格：如实给 null
    jie = kai + 2                                    # 表体起点（表头 + 分隔行之后）
    ti = []
    while (jie < len(hang) and hang[jie].lstrip().startswith('|')
           and not _biao_fenge(hang[jie])):          # 连续竖线行且非分隔行 = 表体
        ti.append(hang[jie])
        jie += 1
    biao_hang = hang[kai:jie]                        # 首表原文（表头+分隔行+表体）
    lie = _biao_dange(hang[kai])                     # 表头单元格
    duiqi = _biao_fenge(hang[kai + 1]) or []         # 分隔行的对齐串
    duiqi = (duiqi + ['left'] * len(lie))[:len(lie)]  # 缺列按左对齐补齐
    hang_lie = []
    for h in ti:
        dange = _biao_dange(h)
        dange = (dange + [''] * len(lie))[:len(lie)]  # 短行补空串、长行按表头截断
        hang_lie.append(dange)
    return {'columns': lie, 'rows': hang_lie, 'align': duiqi,
            'raw': '\n'.join(biao_hang),             # 首表原文（逐行原样）
            # 首表之后的文字/后续表原样保留：raw + '\n' + rest 可逐字还原整块，
            # 块内没有表格之外的内容时 rest 为空串（不丢说明行、子标题、附表）。
            'rest': '\n'.join(hang[jie:])}


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


def yiju_dingwei(tishi, jiansuo_hanshu, shuliang=4):
    """一组检索提示词 → {定位串: (条文, 命中它的提示词)}（同定位去重、首见保留）。

    定位串形如 3001-12-P2（指引号-条号[-片号]）：同一条文被多条提示词命中时只留
    第一次的命中（提示词用于在报告里交代检索出处）。检索运行时未注入时返回空
    dict——占位文案由调用方按口径输出，这里不抛错、不伪造条文。
    """
    if jiansuo_hanshu is None:
        return {}
    pian_jian = {}
    for cha in tishi:
        for pian in jiansuo_hanshu(chaxun=cha, shuliang=shuliang):
            dingwei = (f"{pian['zhiyin_hao']}-{pian['tiao_hao']}"
                       + (f"-P{pian['duan_hao']}" if pian.get('duan_hao') else ''))
            pian_jian.setdefault(dingwei, (pian, cha))    # 同定位串去重（首见保留）
    return pian_jian


def _yiju_biaoti(dingwei, zhiyin_ming):
    """定位串 → 出处标题（《管理会计应用指引第N号——标题》第M条[第P片]）。

    指引名册（kb2 zhiyin 表）缺该号时回退用指引号本身，保证标题始终可读；
    条号用公文汉字（第十三条），片号取定位串第三段（P2 → 第2片）。
    """
    kuai = dingwei.split('-')
    ming = zhiyin_ming.get(kuai[0], kuai[0])   # 名册缺名即回号（不出空标题）
    tiao_wen = f'第{_tiaohao_zh(int(kuai[1]))}条' + (f'第{kuai[2][1]}片' if len(kuai) > 2 else '')
    return f'《管理会计应用指引第{kuai[0]}号——{ming}》{tiao_wen}'


def yiju_hang(pian_jian, zhiyin_ming):
    """去重后的条文 → md 出处行（序号/标题/定位/提示词 + 条文原文）。

    多项出处之间由调用方用单换行相接（项内标题与正文之间才是空行）——这是
    1.0.5 报告的既有版式，逐字节不能变。
    """
    hang = []
    for chu_xu, (dingwei, (pian, cha)) in enumerate(pian_jian.items(), start=1):
        biaoti = _yiju_biaoti(dingwei, zhiyin_ming)
        hang.append(f'**出处 {chu_xu}：{biaoti}**（定位 {dingwei} ｜ 检索提示词：{cha}）'
                    f'\n\n{pian["neirong"]}')
    return hang


def yiju_yinwen(pian_jian, zhiyin_ming, leiming):
    """去重后的条文 → JSON 引用项（定位串/标题/提示词/原文摘录，金额比率原文）。

    与 yiju_hang 共用同一批 pian_jian：md 里的「依据条例」与 JSON 的 citations
    因此不可能分叉；kind 记收入类/成本类以对应报告里的两段。
    """
    yin = []
    for xu, (dingwei, (pian, cha)) in enumerate(pian_jian.items(), start=1):
        yin.append({'no': xu, 'kind': leiming, 'locator': dingwei,
                    'title': _yiju_biaoti(dingwei, zhiyin_ming),
                    'query': cha, 'excerpt': str(pian.get('neirong') or '').strip()})
    return yin


def yiju_tiaoli(tishi, jiansuo_hanshu, zhiyin_ming, shuliang=4):
    """一组检索提示词 → 条文段列表（去重；出处行含定位与提示词）。"""
    if jiansuo_hanshu is None:
        return [WEI_JIANSUO_ZHURU]                   # 检索运行时未注入：如实占位
    return yiju_hang(yiju_dingwei(tishi, jiansuo_hanshu, shuliang), zhiyin_ming) or [WEI_JIANSUO]


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

def huibian_neirong(jieguo, wencai_hanshu, zongjie_hanshu, jiansuo_hanshu, jiyu_ming):
    """汇总一次报告内容：md 全文 + JSON 所需的同源结构化数据。

    返回 dict：
        'md'         报告全文（口径与 zucheng_md 完全一致，含 AI 标注行）
        'meta'       批次元信息（company/period/scenarioName/seed 等原值）
        'overview'   总览数据块原文（报告『## 总览』的内容）
        'modules'    九模块：[{no, name, table, analysis, aiGenerated, citations}]
        'aiAnalysis' {conclusion, actions:[{no,type,owner,desc,suggestion}], aiGenerated}
        'aiGenerated' 整篇是否含 AI 文案（wencai/zongjie 任一注入）
        'aiWencai'/'aiZongjie' 两条文案注入通道是否启用（标注位置由它决定）
        'tiaoli_shu' 报告里「出处」条数（与 md.count 同口径）

    md 与 JSON 共用本函数的中间结果：检索、占位文案各只跑一次，避免同一输入
    因重复调用而分叉；新增标注行只在 AI 注入时出现，纯计算报告输出保持原样。
    """
    bg = zhuang_bgshuru(jieguo)
    shuju_md = shengcheng_baogao_md(bg)             # 数据表全文（algo 权威组装）
    zong_lan = ti_kuai(shuju_md, ('总览',)) or '（总览缺料）'
    meta = jieguo['meta']
    # 抬头口径：种子优先取调用方注入的 meta['seed']，其次 meta['种子']，都没有就不写
    zhong = str(meta.get('seed') or meta.get('种子') or '').strip()
    zhong_wen = f'（种子 {zhong}）' if zhong else ''
    ai_wencai = wencai_hanshu is not None            # 逐模块文案是否由 AI 回填
    ai_zongjie = zongjie_hanshu is not None          # 总体解读是否由 AI 回填
    hang = [f"# 计算报告-月度（{meta['company']} · {meta['period']}）", '',
            f"> 主体 {meta['company']}｜情景 {meta.get('scenarioName') or '—'}｜"
            f"单位 金额=分、比率=基点｜数据口径 演示件{zhong_wen}｜"
            f"分析链 yinqing.fenxi 十五步", '']
    if ai_wencai or ai_zongjie:                      # 纯计算报告不加抬头标注
        hang += [f'> {AI_TAITOU}', '']
    hang += ['## 总览', '', zong_lan, '']
    # ---- 九个模块章节：三段式（数据表 / 分析内容 / 依据条例）----
    mokuai_lie = []                                  # JSON modules（与 md 同源同序）
    for xu, (qianzhui_lie, zhanshi, (t_shouru, t_chengben)) in enumerate(MO_KUAI, start=1):
        shuju_kuai = ti_kuai(shuju_md, qianzhui_lie)
        wen = (wencai_hanshu(zhanshi, shuju_kuai) if wencai_hanshu
               else mo_kuai_zhanwei(zhanshi, shuju_kuai))
        hang += [f'## 模块{u"一二三四五六七八九"[xu - 1]} · {zhanshi}', '',
                 '**数据表**', '', shuju_kuai, '',
                 '**分析内容**', '']
        if ai_wencai:                                # 仅 AI 文案贴标注；占位不贴
            hang += [f'> {AI_BIAOZHU}', '']
        hang += [wen, '']
        yinwen = []                                  # 本模块 citations（两段引用合并）
        for leiming, cha in (('收入类', t_shouru), ('成本类', t_chengben)):
            hang += [f'**依据条例（{leiming}）**', '']
            if jiansuo_hanshu is None:               # 检索运行时未注入：如实占位
                hang += [WEI_JIANSUO_ZHURU]
            else:
                pian_jian = yiju_dingwei((cha,), jiansuo_hanshu)   # 每类只检索一次
                hang += (yiju_hang(pian_jian, jiyu_ming) or [WEI_JIANSUO])
                yinwen += yiju_yinwen(pian_jian, jiyu_ming, leiming)
            hang.append('')
        mokuai_lie.append({'no': xu, 'name': zhanshi, 'table': shuju_kuai,
                           'analysis': wen, 'aiGenerated': ai_wencai,
                           'citations': yinwen})
    # ---- AI 分析解读章节（总体 LLM 解读；占位标注 DSH 回填）----
    zong_wen = zongjie_hanshu(jieguo) if zongjie_hanshu else zongti_zhanwei(jieguo)
    hang += ['---', '', '## AI 分析解读', '']
    if ai_zongjie:                                   # 章标题下贴一章级标注
        hang += [f'> {AI_BIAOZHU}', '']
    hang += [f"*文案模式：{'注入文案函数' if wencai_hanshu or zongjie_hanshu else '确定性占位（由 DSH 宿主 agent 回填）'}*", '',
             '### 总体解读', '']
    if ai_zongjie:                                   # 总体解读段前同样标注
        hang += [f'> {AI_BIAOZHU}', '']
    hang += [zong_wen, '', '### 逐条整改建议', '']
    dongzuo = []                                     # JSON aiAnalysis.actions
    for xu, tiao in enumerate(jieguo['correction'].qingdan, start=1):
        hang.append(f"**{xu}. [{tiao.leixing}｜{tiao.zeren_mokuai}]（占位）** "
                    f"{tiao.miaoshu}——{ZHENGGAI_ZHANWEI}。")
        hang.append('')
        dongzuo.append({'no': xu, 'type': tiao.leixing, 'owner': tiao.zeren_mokuai,
                        'desc': tiao.miaoshu,
                        'suggestion': '' if ai_zongjie else ZHENGGAI_ZHANWEI})
    md = '\n'.join(hang).rstrip() + '\n'
    return {'md': md, 'meta': meta, 'overview': zong_lan, 'modules': mokuai_lie,
            'aiAnalysis': {'conclusion': zong_wen, 'actions': dongzuo,
                           'aiGenerated': ai_zongjie},
            'aiGenerated': ai_wencai or ai_zongjie,
            'aiWencai': ai_wencai, 'aiZongjie': ai_zongjie,
            'tiaoli_shu': md.count('**出处 ')}


def zucheng_md(jieguo, wencai_hanshu, zongjie_hanshu, jiansuo_hanshu, jiyu_ming):
    """组装完整报告 md（抬头 + 总览 + 九模块三段 + AI 分析解读）。"""
    return huibian_neirong(jieguo, wencai_hanshu, zongjie_hanshu,
                           jiansuo_hanshu, jiyu_ming)['md']


def _shengcheng_shijian(jieguo, shengcheng_shijian=None):
    """报告生成时刻（固定取值顺序以保幂等——绝不读当前时钟）。

    顺序：显式参数 > 环境变量 HENGCE_REPORT_GENERATED_AT > meta['seed'|'种子']
    的 8 位日期（按东八区零点还原）。批次元信息里的『生成时间』是每次导入都会
    刷新的时刻，刻意不用——否则同一输入两次生成的 JSON 不一致、破坏幂等；
    三个来源都不满足时返回空串，宁可空着也不写一个随机时间戳。
    """
    if shengcheng_shijian:                           # 调用方显式给定（CLI/UI 可传）
        return str(shengcheng_shijian)
    huan = os.environ.get('HENGCE_REPORT_GENERATED_AT')   # 部署侧固定时刻
    if huan:
        return huan
    meta = jieguo.get('meta') or {}
    zhong = str(meta.get('seed') or meta.get('种子') or '').strip()
    if re.fullmatch(r'\d{8}', zhong):                # 演示件种子即 8 位日期
        return f'{zhong[:4]}-{zhong[4:6]}-{zhong[6:]}T00:00:00+08:00'
    # 刻意不读 meta['生成时间']：那是每次导入都会刷新的时刻，用它会让同一输入
    # 两次生成的 JSON 不一致。没有可复现时刻就返回空串，绝不写随机时间戳。
    return ''


def zucheng_json(jieguo, wencai_hanshu=None, zongjie_hanshu=None,
                 jiansuo_hanshu=None, jiyu_ming=None, shengcheng_shijian=None,
                 _huibian=None):
    """组装 JSON 版报告并返回 dict（结构见改造规范第四节，键名/层级不得改）。

    参数与 compute_report_pipeline 同口径：jiansuo_hanshu=None 自动懒加载 kb2、
    False 关闭检索；jiyu_ming 缺省时按检索状态现取指引名册。shengcheng_shijian
    显式给定生成时刻以保幂等；_huibian 供流水线复用已算好的中间结果（内部参数，
    默认自行汇总）。返回完整 dict，调用方 json.dumps(..., ensure_ascii=False)
    落盘即得 计算报告-月度.json；金额保持整数分、比率保持整数基点原值。
    1.1.5 收口版把 modules[].table 从 markdown 字符串升级成结构化对象
    {columns, rows, align, raw, rest}（见 jiegou_biaoge）：机器侧不用再解析
    `|` 与 `---`；报告 md/html 的组装路径完全不经过这里，字节零变化。
    """
    if _huibian is None:                             # 独立调用：自己补齐检索层
        if jiansuo_hanshu is None:
            jiansuo_hanshu = chuangjian_kb2_jiansuo()
        elif jiansuo_hanshu is False:
            jiansuo_hanshu = None
        if jiyu_ming is None:
            jiyu_ming = du_zhiyin() if jiansuo_hanshu is not None else {}
        _huibian = huibian_neirong(jieguo, wencai_hanshu, zongjie_hanshu,
                                   jiansuo_hanshu, jiyu_ming)
    hb = _huibian
    meta = hb['meta']
    zhong = str(meta.get('seed') or meta.get('种子') or '').strip()
    bao_jing = []                                    # warnings：口径/占位如实登记
    if not hb['aiWencai']:
        bao_jing.append('逐模块分析内容为确定性占位文案，待 DSH 宿主 agent 回填。')
    if not hb['aiZongjie']:
        bao_jing.append('总体解读与逐条整改建议为确定性占位文案，待 DSH 宿主 agent 回填。')
    if jiansuo_hanshu is None:                       # 检索未注入/显式关闭
        bao_jing.append(WEI_JIANSUO_ZHURU)
    elif not hb['tiaoli_shu']:                       # 检索跑了但一条没命中
        bao_jing.append(WEI_JIANSUO)
    # 模块的「数据表」从 md 文本升级成结构化对象（机器可直读）。md 组装只读
    # huibian 的 table 原串、不经过这里，所以报告字节不受影响；三个缺料模块
    # （#3/#6/#8 整块没有 md 表格）如实给 table: null，不造空数组。
    mokuai_json = []
    for m in hb['modules']:
        jie = dict(m)                                # 浅拷贝：键顺序与原结构一致
        jie['table'] = jiegou_biaoge(m.get('table'))
        mokuai_json.append(jie)
    return {
        'schema': JSON_SCHEMA,                       # 消费方按 schema 判版
        'generatedAt': _shengcheng_shijian(jieguo, shengcheng_shijian),
        'aiGenerated': hb['aiGenerated'],            # 整篇是否含 AI 内容
        # 统一标注文案：只在真有 AI 内容时挂（纯计算报告 aiNotice 为空串，
        # 与 aiGenerated=False 一致——不给确定性计算冒充 AI 生成）。
        'aiNotice': AI_BIAOZHU if hb['aiGenerated'] else '',
        'meta': {'company': meta.get('company') or '',
                 'period': meta.get('period') or '',
                 'scenarioName': meta.get('scenarioName') or '',
                 'seed': zhong,                       # 演示件种子原值（不加工）
                 'unit': DANWEI_KOUJING},             # 金额=分、比率=基点
        'overview': hb['overview'],                  # 总览块原文（叙述性文字，仍是字符串）
        'modules': mokuai_json,                      # 九模块（table 已结构化 + citations）
        'aiAnalysis': hb['aiAnalysis'],              # 总体解读 + 逐条整改建议
        'warnings': bao_jing,                        # 占位/检索状态明确交代
    }


def zhuan_html(md):
    """md 子集 → HTML（标题/表格/粗体/分隔线/段落；内置极简样式零依赖）。

    含 AI 内容（出现抬头或段落标注）时，在 </body> 前补统一页脚标注。
    """
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
    # 含 AI 内容：统一文案同时进 md（引用块）与 html（页脚），两版标注对得上
    if AI_TAITOU in md or AI_BIAOZHU in md:
        chu.append('<footer style="margin-top:36px;padding-top:12px;'
                   'border-top:1px solid #b0b8c1;color:#5d6d7e;font-size:12px">'
                   f'{AI_TAITOU}</footer>')
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
                            jiansuo_hanshu=None, shuchu_mu=None, shengcheng_shijian=None):
    """生成计算报告-月度.md + .html + .json（同输入逐字节一致 = 天然幂等）。

    参数：jieguo = yinqing.fenxi() 结果 dict；wencai_hanshu(模块名, 数据块)→str；
        zongjie_hanshu(jieguo)→str；jiansuo_hanshu=None 表示自动懒加载 kb2 真检索
        （query_kb2 只读引用），传 False 关闭检索（占位）；
        shengcheng_shijian 显式指定 JSON 的生成时刻（默认按固定顺序推导，保幂等）。
    返回：{'md': 路径, 'html': 路径, 'json': 路径, 'mokuai_shu': 9, 'tiaoli_shu': N}
    """
    if jiansuo_hanshu is None:                      # None=自动尝试；False=显式关闭
        jiansuo_hanshu = chuangjian_kb2_jiansuo()
    elif jiansuo_hanshu is False:
        jiansuo_hanshu = None
    jiyu_ming = du_zhiyin() if jiansuo_hanshu is not None else {}
    hb = huibian_neirong(jieguo, wencai_hanshu, zongjie_hanshu, jiansuo_hanshu, jiyu_ming)
    md = hb['md']
    mu = Path(shuchu_mu) if shuchu_mu else BEN_MU / '输出'
    mu.mkdir(parents=True, exist_ok=True)
    md_lu = mu / '计算报告-月度.md'
    md_lu.write_text(md, encoding='utf-8')
    html_lu = mu / '计算报告-月度.html'
    html_lu.write_text(zhuan_html(md), encoding='utf-8')
    # JSON 与 md 同目录同次生成：复用同一次汇总，不重复检索、不重复取数
    json_lu = mu / '计算报告-月度.json'
    json_shu = zucheng_json(jieguo, wencai_hanshu, zongjie_hanshu, jiansuo_hanshu,
                            jiyu_ming, shengcheng_shijian, _huibian=hb)
    json_lu.write_text(json.dumps(json_shu, ensure_ascii=False, indent=2) + '\n',
                       encoding='utf-8')
    return {'md': str(md_lu), 'html': str(html_lu), 'json': str(json_lu),
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
