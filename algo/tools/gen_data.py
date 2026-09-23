# -*- coding: utf-8 -*-
r"""随机数据生成与性质自检工具 —— 全模块随机测试（零依赖）。

注册模块（--mokuai）：gundong_yusuan / chafen / huanlu / jimu / bsc /
kpi / suyuan——每个模块一组生成器 + 性质断言（或影子互证），新模块
接入点见 zhukong 里的登记提示。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；命令行参数也是拼音
（--mokuai 模块 / --moshi 模式 / --shuliang 数量 / --zhongzi 种子 / --shuchu 输出）；
模式取值改为中文拼音值：'suiji'（随机检验）/ 'yangben'（样本落盘）。

两种模式（--moshi）：
    suiji    随机生成 N 组【合法】输入，跑被测函数，用独立实现的
             「影子算法」逐期复核 + 性质断言（见 jiancha_gundong_yusuan_li）。
    yangben  生成一组随机数据存为 JSON（algo/fixtures/）——
             演示数据集（TODO T-14）与 bug 复现都用它。

为什么需要影子算法：
    用被测函数自己算期望值是自证循环；本工具【独立重演】口径规则
    （全额替换 + 各期自身预算累进 + 口径A一次性乘子），两边逐期比对，
    任何一侧的偏差都会暴露。影子实现刻意不复用被测模块的私有函数。

用法（algo 目录下，PY = D:/AppProject/env/Scripts/python.exe）：
    %PY% tools/gen_data.py --mokuai gundong_yusuan --shuliang 200 --zhongzi 42
    %PY% tools/gen_data.py --moshi yangben --shuchu fixtures/demo.json

退出码：0 = 全部通过；1 = 存在失败（可当脚本门禁）。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# 以脚本方式运行时，把 algo 根目录加进 sys.path 以导入被测模块；
# 以 tools.gen_data 包方式被测试导入时，此插入无副作用。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bsc import BscShuru, jisuan_bsc  # noqa: E402
from building_blocks import JimuHang, chai_jimu  # noqa: E402
from kpi import KpiShuru, jisuan_kpi  # noqa: E402
from suyuan import SuyuanHang, jisuan_suyuan  # noqa: E402
from loop_decision import MENJIAN_BPS, PanDuanShuru, panduan_huanlu  # noqa: E402
from planning_operational import ChaifenShuru, chai_fen  # noqa: E402
from rolling_budget import GunDongShezhi, QijianJine, gengxin_gundong_yusuan  # noqa: E402


# ======================================================================
# 影子算法（独立实现——与被测模块刻意不复用代码）
# ======================================================================


def _yingzi_cheng_jidian(fen: int, jidian: int) -> int:
    """独立实现的「金额 × (10000+基点)/10000，half-up 舍入到分」。

    写法与被测模块不同（先商后判余数），殊途同归——两实现不一致即为缺陷。
    """
    chengji = fen * (10_000 + jidian)
    shang, yushu = divmod(chengji, 10_000)
    return shang + (1 if yushu * 2 >= 10_000 else 0)  # 余数过半进一


def yingzi_gundong_yusuan(li: dict) -> list[int]:
    """按口径规则独立重演一遍，返回逐期金额（分）。

    规则（定稿 #1；剩余期链法① 2026-09-03 队友拍板 T-23 重开，与被测模块同口径、不同代码）：
      届满期 = 实际数（全额替换）；
      首个剩余期 = 自身年初预算 × (1+g)；此后每期 = 上一期滚动值 × (1+g)，
      逐期 half-up 舍入接力；届满期实际数不进接力链。
      季度 + 口径A 且 |企业−行业| ≥ 阈值 时，当期滚动结果再乘一次差值乘子。
    """
    yusuan = li['yusuan']
    shiji_suoyin = {t['qijian']: t['jine_fen'] for t in li['shiji']}
    shezhi = li['shezhi']

    # 口径 A 启用判定（三条件与被测模块一致，代码独立实现）
    hangye_qiyong = (
        shezhi['hangye_xiuzheng'] == 'A'
        and shezhi['zhouqi'] == '季度'
        and abs(shezhi['zengzhanglv_jidian'] - shezhi['hangye_zengzhanglv_jidian']) >= shezhi['hangye_yuzhi_jidian']
    )

    shuzhi_lie: list[int] = []
    sheng_yu_guo = False   # 是否已进入剩余期序列（接力是否已开始）
    qian_yi = None         # 上一期滚动值（接力种子）
    for hang in yusuan:
        if hang['qijian'] in shiji_suoyin:
            shuzhi_lie.append(shiji_suoyin[hang['qijian']])  # 全额替换
            sheng_yu_guo = False
            qian_yi = None
        else:
            zhi = hang['jine_fen'] if not sheng_yu_guo else qian_yi
            zhi = _yingzi_cheng_jidian(zhi, shezhi['zengzhanglv_jidian'])
            if hangye_qiyong:
                zhi = _yingzi_cheng_jidian(zhi, shezhi['zengzhanglv_jidian'] - shezhi['hangye_zengzhanglv_jidian'])
            qian_yi = zhi
            sheng_yu_guo = True
            shuzhi_lie.append(zhi)
    return shuzhi_lie


# ======================================================================
# 随机用例生成
# ======================================================================


def shengcheng_gundong_yusuan_li(suijiqi: random.Random) -> dict:
    """生成一组随机但【合法】的滚动预算输入（纯数据字典）。

    随机维度（每个维度都刻意压测一条实现分支）：
      周期模式   月度/季度二选一——覆盖行业修正的生效/不生效分支；
      期数       月度 2..12 / 季度 2..4——覆盖不同链长；
      各期预算   10 元..500 万元不等额——压测 T-23 累进基准（保轮廓）；
      实际期集合 任意子集（可散布）——压测"届满后期距归零"；
      增长率     ±3%（含负增长）——覆盖上下行两种经营态势；
      口径参数   B 加权 2/3、A 加权 1/3——两种口径都高频出现。
    """
    # ① 周期与期数（季度模式现实上最多 4 期）
    zhouqi = suijiqi.choice(['月度', '季度'])
    shu = suijiqi.randint(2, 12) if zhouqi == '月度' else suijiqi.randint(2, 4)

    # ② 期间命名与模式对应：月度 2026-01..、季度 2026-Q1..
    mingcheng = [f'2026-{i + 1:02d}' if zhouqi == '月度' else f'2026-Q{i + 1}' for i in range(shu)]

    # ③ 各期预算：10 元 ~ 500 万元（分），刻意不等额（季节性轮廓）
    yusuan = [{'qijian': m, 'jine_fen': suijiqi.randint(1_000, 500_000_000)} for m in mingcheng]

    # ④ 实际期：从全部期间里随机抽 k 个（k=0..n），散布的届满期最能压测期距重置
    k = suijiqi.randint(0, shu)
    jieman_xuhao = set(suijiqi.sample(range(shu), k))
    shiji = [
        {'qijian': mingcheng[i], 'jine_fen': suijiqi.randint(1_000, 500_000_000)} for i in sorted(jieman_xuhao)
    ]

    # ⑤ 增长率 ±3% 整数基点；口径 A:B = 2:1 加权（A 为用户拍板默认口径）
    moshi = suijiqi.choice(['A', 'A', 'B'])
    shezhi: dict = {
        'zhouqi': zhouqi,
        'zengzhanglv_jidian': suijiqi.randint(-300, 300),
        'hangye_xiuzheng': moshi,
    }
    if moshi == 'A':
        # ⑥ 口径A 参数：行业增长率 ±3%、启用阈值 0~100 基点（0=恒启用，合法边界）
        shezhi['hangye_zengzhanglv_jidian'] = suijiqi.randint(-300, 300)
        shezhi['hangye_yuzhi_jidian'] = suijiqi.randint(0, 100)
    return {'yusuan': yusuan, 'shiji': shiji, 'shezhi': shezhi}


# ======================================================================
# 性质断言（随机检验核心）
# ======================================================================


def jiancha_gundong_yusuan_li(li: dict) -> list[str]:
    """对单组随机输入跑被测函数并做全套性质断言，返回问题清单。

    性质清单（任何一条不成立都是缺陷）：
      P1 总额一致：gundong_zonge == 逐期 shuzhi 之和；
      P2 差额定义：chae == gundong_zonge − chushi_zonge；
      P3 届满替换：已届满期 shuzhi == 实际数；
      P4 影子一致：逐期 shuzhi == 影子算法结果（独立实现互证）；
      P5 确定性：同输入重跑结果完全一致；
      P6 形态合法：全部 shuzhi 为非负整数。
    """
    yusuan = [QijianJine(t['qijian'], t['jine_fen']) for t in li['yusuan']]
    shiji = [QijianJine(t['qijian'], t['jine_fen']) for t in li['shiji']]
    shezhi = GunDongShezhi(**li['shezhi'])

    jieguo = gengxin_gundong_yusuan(yusuan, shiji, shezhi)
    wenti: list[str] = []

    shuzhi_lie = [t.shuzhi_fen for t in jieguo.qijian_mingxi]
    # P6 形态合法（bool 是 int 子类，须排除）
    if any(isinstance(z, bool) or not isinstance(z, int) or z < 0 for z in shuzhi_lie):
        wenti.append('P6: 存在非法金额值')

    # P1/P2 总额与差额
    if jieguo.gundong_zonge_fen != sum(shuzhi_lie):
        wenti.append(f'P1: zonge={jieguo.gundong_zonge_fen} != he={sum(shuzhi_lie)}')
    if jieguo.chae_fen != jieguo.gundong_zonge_fen - jieguo.chushi_zonge_fen:
        wenti.append('P2: chae 定义不成立')

    # P3 届满替换
    shiji_suoyin = {t['qijian']: t['jine_fen'] for t in li['shiji']}
    for t in jieguo.qijian_mingxi:
        if t.zhuangtai == '已届满' and t.shuzhi_fen != shiji_suoyin.get(t.qijian):
            wenti.append(f'P3: 届满期 {t.qijian} 未等于实际数')

    # P4 影子一致（独立实现逐期互证）
    yingzi = yingzi_gundong_yusuan(li)
    if shuzhi_lie != yingzi:
        wenti.append(f'P4: 与影子算法不一致 {shuzhi_lie} != {yingzi}')

    # P5 确定性：重跑一次，逐字段比对
    zaipao = gengxin_gundong_yusuan(yusuan, shiji, shezhi)
    if (zaipao.gundong_zonge_fen, [t.shuzhi_fen for t in zaipao.qijian_mingxi]) != (
        jieguo.gundong_zonge_fen,
        shuzhi_lie,
    ):
        wenti.append('P5: 同输入重跑结果不一致')
    return wenti


def suiji_yansheng(shuliang: int, zhongzi: int | None = None, xiangqi: bool = True) -> int:
    """随机检验主循环：生成-检验 N 组随机用例，返回失败组数。

    种子约定：None = 真随机（探矿模式）；固定整数 = 可复现（回归模式）。
    """
    suijiqi = random.Random(zhongzi)
    shibai = 0
    for i in range(shuliang):
        li = shengcheng_gundong_yusuan_li(suijiqi)
        wenti = jiancha_gundong_yusuan_li(li)
        if wenti:
            # 失败时打印完整输入 JSON——可直接粘贴为复现用例或样本
            shibai += 1
            if xiangqi:
                print(f'FAIL 例#{i}: {wenti}\n  shuru={json.dumps(li, ensure_ascii=False)}')
    if xiangqi:
        print(f'随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    return shibai


def ling_zengzhang_yansheng(shuliang: int, zhongzi: int | None = None, xiangqi: bool = True) -> int:
    """专项性质：g=0 且口径 B 时，剩余期序列接力冻结于首个剩余期的年初预算。

    链法①（2026-09-03 拍板）下的恒等语义：首个剩余期 = 自身年初数 ×1.0 =
    自身年初数；此后每期 = 上一期滚动值 ×1.0 —— 整段剩余期全部等于
    【首个剩余期】的年初预算（不是各自等于自己的年初数，那是旧非链式语义）。
    """
    suijiqi = random.Random(zhongzi)
    shibai = 0
    for i in range(shuliang):
        li = shengcheng_gundong_yusuan_li(suijiqi)
        li['shezhi']['zengzhanglv_jidian'] = 0  # 强制零增长
        li['shezhi']['hangye_xiuzheng'] = 'B'
        yusuan = [QijianJine(t['qijian'], t['jine_fen']) for t in li['yusuan']]
        shiji = [QijianJine(t['qijian'], t['jine_fen']) for t in li['shiji']]
        jieguo = gengxin_gundong_yusuan(yusuan, shiji, GunDongShezhi(**li['shezhi']))
        sheng_yu_duan: list[list] = []   # 剩余期按届满期切段，每段一个接力起点
        for t in jieguo.qijian_mingxi:
            if t.zhuangtai == '已届满':
                sheng_yu_duan.append([])
            elif sheng_yu_duan:
                sheng_yu_duan[-1].append(t)
            else:
                sheng_yu_duan.append([t])
        huai: list[str] = []
        for duan in sheng_yu_duan:
            if not duan:
                continue
            if duan[0].shuzhi_fen != duan[0].chushi_yusuan_fen:
                huai.append(f'{duan[0].qijian} 段首未等于自身年初数')
            dongjie = duan[0].chushi_yusuan_fen
            huai += [f'{t.qijian} 未冻结于段首 {dongjie}（现 {t.shuzhi_fen}）'
                     for t in duan[1:] if t.shuzhi_fen != dongjie]
        if huai:
            shibai += 1
            if xiangqi:
                print(f'FAIL 零增长例#{i}: {huai}')
    if xiangqi:
        print(f'零增长专项完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    return shibai


# ======================================================================
# 规划/执行拆分：随机生成与性质断言（性质即 oracle，无需影子重复实现）
# ======================================================================
# 设计说明：拆分模块的口径关系（恒等式/残差公式/细分关系）本身就是
# 数学恒等式——比影子实现更强的校验：任何一侧写错，关系式立刻破裂。
# ======================================================================


def shengcheng_chafen_li(suijiqi: random.Random) -> dict:
    """生成一组随机但【合法】的拆分输入（纯数据字典，值即最终值）。

    随机维度：标准/修订单价与用量（各自三成概率"与标准相同"——
    刻意压测退化路径与 Holmes 式混合情形）、实际产量/用量/成本。
    """
    biaozhun_jia = suijiqi.randint(1, 500_000)      # 标准单价（分）
    biaozhun_liang = suijiqi.randint(1, 1000)       # 标准用量（基本单位）
    return {
        'biaozhun_danjia_fen': biaozhun_jia,
        'biaozhun_yongliang': biaozhun_liang,
        # 修订价：30% 取标准值（退化），70% 随机重估
        'xiuding_danjia_fen': biaozhun_jia if suijiqi.random() < 0.3 else suijiqi.randint(1, 500_000),
        # 修订量：同样 30% 退化
        'xiuding_yongliang': biaozhun_liang if suijiqi.random() < 0.3 else suijiqi.randint(1, 1000),
        'shiji_chanliang': suijiqi.randint(1, 10_000),          # 实际产量（必须>0）
        'shiji_yongliang': suijiqi.randint(0, 1_000_000),       # 实际总用量（允许0）
        'shiji_chengben_fen': suijiqi.randint(0, 9 * 10**11),   # 实际总成本（分）
    }


def jiancha_chafen_li(li: dict) -> list[str]:
    """对单组随机拆分输入跑被测函数并做性质断言，返回问题清单。

    性质清单（被测模块已内建自检，此处【独立】复核同一批关系）：
      P1 恒等式：原标准总 = 规划总 + 执行总；
      P2 残差公式：残差 =（修订用量×产量 − 实际用量）×（标准价 − 修订价）；
      P3 细分关系：−四项细分合计 − 残差 = 原标准总；
      P4 形态合法：全部输出金额为整数。
    """
    # 直接用字典值构造输入（生成器已保证值即最终值，无 None 填充）
    shuru = ChaifenShuru(
        biaozhun_danjia_fen=li['biaozhun_danjia_fen'],
        biaozhun_yongliang=li['biaozhun_yongliang'],
        xiuding_danjia_fen=li['xiuding_danjia_fen'],
        xiuding_yongliang=li['xiuding_yongliang'],
        shiji_chanliang=li['shiji_chanliang'],
        shiji_yongliang=li['shiji_yongliang'],
        shiji_chengben_fen=li['shiji_chengben_fen'],
    )
    jieguo = chai_fen(shuru)
    wenti: list[str] = []

    # P1 恒等式独立复核
    if jieguo.yuandan_zong_fen != jieguo.guihua_zong_fen + jieguo.zhixing_zong_fen:
        wenti.append('P1: 恒等式不成立')
    # P2 残差公式独立重算
    qiwang_cancha = (shuru.xiuding_yongliang * shuru.shiji_chanliang - shuru.shiji_yongliang) * (shuru.biaozhun_danjia_fen - shuru.xiuding_danjia_fen)
    if jieguo.cancha_fen != qiwang_cancha:
        wenti.append(f'P2: 残差不符 {jieguo.cancha_fen} != {qiwang_cancha}')
    # P3 细分与总量的解析关系
    he = jieguo.jiage_guihua_fen + jieguo.jiage_zhixing_fen + jieguo.yongliang_guihua_fen + jieguo.yongliang_zhixing_fen
    if -he - jieguo.cancha_fen != jieguo.yuandan_zong_fen:
        wenti.append('P3: 细分关系不成立')
    # P4 形态合法（金额字段全为整数）
    jin_e = (jieguo.yuandan_zong_fen, jieguo.guihua_zong_fen, jieguo.zhixing_zong_fen,
             jieguo.jiage_guihua_fen, jieguo.jiage_zhixing_fen,
             jieguo.yongliang_guihua_fen, jieguo.yongliang_zhixing_fen, jieguo.cancha_fen)
    if any(isinstance(z, bool) or not isinstance(z, int) for z in jin_e):
        wenti.append('P4: 存在非法金额值')
    return wenti


def suiji_yansheng_chafen(shuliang: int, zhongzi: int | None, xiangqi: bool = True) -> int:
    """拆分模块的随机检验主循环（生成-检验 N 组，返回失败组数）。

    与滚动预算版同构：固定种子可复现；失败时打印完整输入 JSON。
    """
    suijiqi = random.Random(zhongzi)  # zhongzi=None → 真随机探矿
    shibai = 0
    for i in range(shuliang):
        li = shengcheng_chafen_li(suijiqi)
        wenti = jiancha_chafen_li(li)
        if wenti:
            # 失败输入可直接粘进测试当回归用例
            shibai += 1
            if xiangqi:
                print(f'FAIL 拆分例#{i}: {wenti}\n  shuru={json.dumps(li, ensure_ascii=False)}')
    if xiangqi:
        print(f'拆分随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    return shibai


# ======================================================================
# 单双环判定：随机生成与性质断言（判定表口径即 oracle，无需影子实现）
# ======================================================================
# 设计说明：判定表是纯逻辑（无算术），性质断言直接检验"判定值域 /
# 门检约束 / 结构信号前置 / 确定性 / 情形映射"五条不变量——任何一条
# 被随机组合打破，都说明判定逻辑偏离定稿 v2.1 §4.4。
# ======================================================================


def shengcheng_huanlu_li(suijiqi: random.Random) -> dict:
    """生成判定模块的随机合法输入（量程刻意横跨默认门限 2500 两侧）。

    生成一组随机但【合法】的判定输入（纯数据字典，值即最终值）。
    门限口径：本生成器不含门限值，量程只保证覆盖；判据以模块常量为准。

    随机维度：差异率（含 None 退化）、规划/执行总差异（含 None 缺失）、
    原标准成本额（含 0 退化）、结构变更登记、变更文本（含空串）、
    LLM 归类函数（None / 正常 / 抛异常三种形态之一）。
    函数无法 JSON 序列化，字典里存的是"形态代号"，构造输入时再物化。
    """
    return {
        # 差异率：70% 随机基点（0~5000 覆盖默认门限 2500 两侧），30% None（无法定级）
        # 量程上限随默认门限水涨船高：门限再拍板调整，2.5 倍余量天然自适应
        # （0~2000 旧量程在新默认 2500 下会永远过不了门，fuzz 就失去触发覆盖）
        'chalv_bps': None if suijiqi.random() < 0.3 else suijiqi.randint(0, 5000),
        # 规划/执行总差异：各 20% 缺失（拆分线索缺失退化），其余随机正负
        'guihua_zong_fen': None if suijiqi.random() < 0.2 else suijiqi.randint(-9 * 10**9, 9 * 10**9),
        'zhixing_zong_fen': None if suijiqi.random() < 0.2 else suijiqi.randint(-9 * 10**9, 9 * 10**9),
        # 原标准成本额：10% 为 0（非零即显著退化），10% 缺失，其余随机
        'yuandan_cbf_fen': None if suijiqi.random() < 0.1 else (0 if suijiqi.random() < 0.1 else suijiqi.randint(1, 10**10)),
        # 结构变更登记：对半开（覆盖有/无登记两大分支）
        'jie_gou_biangeng': suijiqi.random() < 0.5,
        # 变更文本：50% 空串（无线索），50% 随机描述
        'bianma': '' if suijiqi.random() < 0.5 else f'变更事项样本{suijiqi.randint(1, 999)}',
        # LLM 归类函数形态：0=未注入 1=正常返回 2=抛异常 3=返回非法值
        'guilei_xingtai': suijiqi.choice([0, 1, 1, 2, 3]),
        # 正常形态下的归类结论（从合法枚举里随机选）
        'guilei_jieguo': suijiqi.choice(['结构变动', '执行偏差', '无法判断']),
    }


def _wuhua_guilei(xingtai: int, jieguo: str):
    """把"形态代号"物化成真实的 LLM 归类函数（或 None）。

    形态 2/3 刻意制造故障与幻觉——验证 T-22⑨ 降级路径在随机组合下不崩。
    """
    if xingtai == 0:
        return None
    if xingtai == 1:
        return lambda wenben: jieguo
    if xingtai == 2:
        def huai(wenben):
            raise RuntimeError('模拟 LLM 网络故障')
        return huai
    return lambda wenben: '这个文本看起来很棒'   # 形态 3：非法枚举值（幻觉）


def jiancha_huanlu_li(li: dict) -> list[str]:
    """对单组随机判定输入跑被测函数并做性质断言，返回问题清单。

    性质清单（定稿 v2.1 §4.4 判定表的不变量）：
      P1 值域合法：判定 ∈ 五个合法值，情形编号 ∈ 1~5；
      P2 门检约束：差异率 < 门检（或 None）时绝不出单环/双环/双轨；
      P3 结构信号前置：双环/双轨 必然伴随结构变更登记（LLM 不得越权触发）；
      P4 确定性：同输入两次调用结果完全一致；
      P5 情形映射：qingxing 与 panduan 满足判定表行号对应关系。
    """
    shuru = PanDuanShuru(
        chalv_bps=li['chalv_bps'],
        guihua_zong_fen=li['guihua_zong_fen'],
        zhixing_zong_fen=li['zhixing_zong_fen'],
        yuandan_cbf_fen=li['yuandan_cbf_fen'],
        jie_gou_biangeng=li['jie_gou_biangeng'],
        bianma=li['bianma'],
        yuyi_guilei=_wuhua_guilei(li['guilei_xingtai'], li['guilei_jieguo']),
    )
    jieguo = panduan_huanlu(shuru)
    wenti: list[str] = []

    # P1 值域合法
    hefa_pan = {'不触发', '单环', '双环', '混合纠错模式', '复核提示'}
    if jieguo.panduan not in hefa_pan or not (1 <= jieguo.qingxing <= 5):
        wenti.append(f'P1: 非法判定 {jieguo.qingxing}/{jieguo.panduan}')
    # P2 门检约束（None 与低于默认门限 MENJIAN_BPS 都视为没过门）
    # 影子实现直接引用被测模块同源常量——门限怎么调，本约束永不失配
    # 反向断言：门内（未过门）的输入绝不允许出单环/双环/混合三种触发态
    # ——这条与 P1 合计一致同属性质断言：门限改默认值后尤其要盯这条不漂移
    if (li['chalv_bps'] is None or li['chalv_bps'] < MENJIAN_BPS) and jieguo.panduan in {'单环', '双环', '混合纠错模式'}:
        wenti.append(f'P2: 未过门却判定 {jieguo.panduan}')
    # P3 结构信号前置（LLM 只能升级复核提示，不能直接触发双环——护栏 FR-8）
    if jieguo.panduan in {'双环', '混合纠错模式'} and not li['jie_gou_biangeng']:
        wenti.append(f'P3: 无登记却判定 {jieguo.panduan}')
    # P4 确定性（再跑一次，dataclass 相等比较）
    if panduan_huanlu(shuru) != jieguo:
        wenti.append('P4: 同输入两次结果不一致')
    # P5 情形映射（判定表行号 ↔ 判定值，一一对应）
    yingshe = {1: '不触发', 2: '单环', 3: '双环', 4: '混合纠错模式', 5: '复核提示'}
    if yingshe[jieguo.qingxing] != jieguo.panduan:
        wenti.append(f'P5: 情形 {jieguo.qingxing} 与判定 {jieguo.panduan} 不匹配')
    return wenti


def suiji_yansheng_huanlu(shuliang: int, zhongzi: int | None, xiangqi: bool = True) -> int:
    """判定模块的随机检验主循环（生成-检验 N 组，返回失败组数）。"""
    suijiqi = random.Random(zhongzi)
    shibai = 0
    for i in range(shuliang):
        li = shengcheng_huanlu_li(suijiqi)
        wenti = jiancha_huanlu_li(li)
        if wenti:
            shibai += 1
            if xiangqi:
                # 函数形态用代号表示（真实函数无法 JSON 序列化）
                dayin_li = {k: v for k, v in li.items()}
                print(f'FAIL 判定例#{i}: {wenti}\n  shuru={json.dumps(dayin_li, ensure_ascii=False)}')
    if xiangqi:
        print(f'判定随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    return shibai


# ======================================================================
# 积木四模块：随机生成与性质断言（聚合口径即 oracle + 影子聚合互证）
# ======================================================================
# 设计说明：积木模块的不变量（净合计恒等式 / 占比合计恒 10000 基点 /
# 高亮=最大不利模块 / 确定性 / 映射一致）直接性质断言；同时用独立影子
# 聚合（纯字典累加、自写关键词表与 half-up）逐模块互证——影子刻意不复用
# 被测模块的内部函数，任何一侧口径漂移都会在两边比对中暴露。
#
# 口径锚点（与 building_blocks 模块头一致）：D2 分母 = Σ|模块净| + |未归属净|；
# D3 高亮 = 不利模块中 |差额| 最大、并列取顺序靠前。
# ======================================================================

#: 已知科目池：科目 → 期望模块（与 building_blocks 默认映射一致，
#: 随机生成约八成行从此池抽取——归属可用 P4 确定性断言）
#: 池内科目刻意覆盖四模块与关键词顺序陷阱（材料价格→采购先于材料→成本、
#: 销售费用→费用先于销售→收入）——映射若漂移，P4 立即红。
KEMU_CHI = {
    '营收': '收入模块', '销量差异': '收入模块', '毛利率': '收入模块',
    '销售价格差异': '收入模块', '材料价格差异': '采购模块',
    '原材料采购': '采购模块', '供应商议价': '采购模块',
    '采购物流': '采购模块', '直接材料': '成本模块',
    '人工效率差异': '成本模块', '制造费用差异': '成本模块',
    '人力薪酬': '成本模块', '电力': '成本模块',
    '管理费用': '费用模块', '销售费用': '费用模块',
    '财务费用': '费用模块',
}
#: 生僻科目池：默认映射不中的科目（压测未归属路径，约两成行从此抽取）
#: 池内字符串刻意不含任何模块关键词——归属若被误判，P4/P6 立即红
KEMU_SHENGPI = ('其他业务', '或有事项', '未定科目')

#: 预警合法取值（与 building_blocks.HEFA_YUJING 一致，影子不 import）
#: 预警只透传不参与聚合——此处随机给值仅验证透传路径
_YUJING_QU = ('无', '黄', '红', '—')
#: 期间池（与 data_ingest 月度格式一致；按行号取保证（期间,科目）键唯一）
#: 行数上限 12 = 期间池长度——键唯一性由构造保证，不依赖去重逻辑
_QIJIAN_QU = tuple(f'2026-{i + 1:02d}' for i in range(12))


# 影子三件套（独立实现原则）：归属映射 / F-A 方向 / 聚合计算——
# 均刻意不复用被测模块内部函数，双实现互证才能暴露口径漂移
def _yingzi_guishu(kemu: str) -> str | None:
    """影子归属：独立关键词表（与默认映射同口径、不同代码）。"""
    for zi in ('采购', '供应商', '议价', '物流', '材料价格'):
        if zi in kemu:
            return '采购模块'
    # 通用兜底关键词'成本'（可控成本等）——与默认映射同表同步（采购先命中）
    for zi in ('制造费用', '生产成本', '材料', '人工', '人力', '薪酬',
               '工时', '闲置', '电力', '水电', '燃料', '动力', '维修', '折旧',
               '成本'):
        if zi in kemu:
            return '成本模块'
    for zi in ('费用', '期间', '管理费', '销售费', '财务费', '办公费'):
        if zi in kemu:
            return '费用模块'
    for zi in ('收入', '营收', '销量', '销售', '毛利', '利润', '净利', '收益', '价格'):
        if zi in kemu:
            return '收入模块'
    return None


def _yingzi_pan_fa(chae_fen: int, mokuai: str) -> str:
    """影子 F/A：方向规则独立重写（收入正=F；其余正=A；零='—'）。"""
    # 零差额无方向——'—'（与模块内 _pan_mokuai_fa 完全同规则）
    if chae_fen == 0:
        return '—'
    if mokuai == '收入模块':
        return 'F' if chae_fen > 0 else 'A'
    return 'A' if chae_fen > 0 else 'F'


def shengcheng_jimu_li(suijiqi: random.Random) -> dict:
    """生成一组随机但【合法】的积木输入（纯数据字典）。

    随机维度（每维压测一条分支）：
      行数       2..12——压测不同桶数与占比分母规模；
      科目       80% 已知池（P4 可断言归属）/ 20% 生僻池（压未归属清单）；
      差额       ±9e9 分随机，10% 零行（压全零退化与除零纪律）；
      行级 fa    90% 按符号给正确值，10% 故意给错值（验证模块 F/A 只信符号）；
      预警/率    四档随机 + 30% None（验证透传不动摇聚合）。
      键唯一     期间按行号取——避免触发"防双计"校验（非本检验目标）。
      影子互证   每组的期望输出由 yingzi_jimu_jisuan 独立重演后比对。
    """
    # 行数上限 12 与期间池等长——行号即月份，保证（期间, 科目）键唯一，
    # 不触发被测模块的"防双计"校验（那不是本随机检验的目标）
    shu = suijiqi.randint(2, 12)
    hang_lie: list[dict] = []
    for i in range(shu):
        # 科目：已知池 → P4 可断言归属；生僻池 → 压未归属清单与分母口径
        kemu = (suijiqi.choice(list(KEMU_CHI))
                if suijiqi.random() < 0.8 else suijiqi.choice(KEMU_SHENGPI))
        # 差额：零行压占比除零退化；正负随机压四模块两侧 F/A 与高亮选择
        chae = 0 if suijiqi.random() < 0.1 else suijiqi.randint(-9 * 10**9, 9 * 10**9)
        # 行级 fa：先按方向规则算正确值，10% 概率换成任意错误值——
        # 被测模块的模块级 F/A 只信差额符号，不信任行级 fa
        # 正确 F/A 按方向规则推：收入正=F，其余正=A；生僻池按成本类方向推
        mokuai = KEMU_CHI.get(kemu) or _yingzi_guishu(kemu) or '成本模块'
        zhengque_fa = _yingzi_pan_fa(chae, mokuai)
        fa = zhengque_fa if suijiqi.random() >= 0.1 else suijiqi.choice(
            [x for x in ('F', 'A', '—') if x != zhengque_fa])
        # 期间按行号取保证键唯一；预警与差异率只透传不参与聚合——随机压透传
        hang_lie.append({
            'qijian': _QIJIAN_QU[i],
            'kemu': kemu,
            'chae_fen': chae,
            'fa': fa,
            'yujing': suijiqi.choice(_YUJING_QU),
            'chalv_bps': None if suijiqi.random() < 0.3 else suijiqi.randint(0, 2000),
        })
    return {'hang_lie': hang_lie}


# 影子聚合：输入是生成器产出的纯字典（与 JimuHang 物化前的形态一致），
# 输出是可直接与被测结果逐字段比对的同名键字典
def yingzi_jimu_jisuan(li: dict) -> dict:
    """独立影子聚合：字典累加重演 D2 口径（不复用被测模块内部函数）。

    与 building_blocks 同口径、不同写法：纯字典求和 + divmod half-up，
    两边逐字段比对，任何一侧偏差都会暴露。
    """
    # 四个桶按定稿 §5 顺序初始化；未归属单独累计净差额（不并入四桶）
    he_ji = {'收入模块': 0, '成本模块': 0, '费用模块': 0, '采购模块': 0}
    weigui_jing = 0
    # 逐行归属：影子自己的关键词表（见 _yingzi_guishu），不复用被测映射
    for hang in li['hang_lie']:
        mokuai = _yingzi_guishu(hang['kemu'])
        if mokuai is None:
            weigui_jing += hang['chae_fen']          # 未归属：净差额单独累计
        else:
            he_ji[mokuai] += hang['chae_fen']
    # D2 分母：各桶净差额绝对值合计（含未归属桶）——占比合计恒 10000 的基础
    fenmu = sum(abs(v) for v in he_ji.values()) + abs(weigui_jing)  # D2 分母
    zhanbi = {}
    # 逐桶占比：divmod 实现 half-up（与模块内 (2n+d)//(2d) 公式等价）；
    # 分母为 0（全零输入）时占比无法定义 → None（与模块内除零纪律一致）
    for mokuai, chae in he_ji.items():
        if fenmu == 0:
            zhanbi[mokuai] = None
        else:
            # divmod half-up：与 (2×|chae|×10000 + 分母) // (2×分母) 等价
            zhanbi[mokuai], _ = divmod(abs(chae) * 10_000 * 2 + fenmu, 2 * fenmu)
    # 未归属占比同理：净差额按同一分母折算，保证五桶合计恒 10000
    if fenmu == 0:
        zhanbi_weigui = None
    else:
        zhanbi_weigui, _ = divmod(abs(weigui_jing) * 10_000 * 2 + fenmu, 2 * fenmu)
    # 高亮规则重演：A 模块中 |差额| 最大，并列按四模块顺序取先者（D3）
    hexin = None
    for mokuai in ('收入模块', '成本模块', '费用模块', '采购模块'):
        chae = he_ji[mokuai]
        if _yingzi_pan_fa(chae, mokuai) == 'A' and (
            hexin is None or abs(chae) > abs(he_ji[hexin])
        ):
            hexin = mokuai
    return {'he_ji': he_ji, 'weigui_jing': weigui_jing, 'fenmu': fenmu,
            'zhanbi': zhanbi, 'zhanbi_weigui': zhanbi_weigui, 'hexin': hexin}


# 性质断言：P1~P7 全部为口径不变量，任何一条被随机组合打破都说明
# 实现偏离 D1/D2/D3 或映射口径——这就是随机检验的价值（与 [026] 同款）
def jiancha_jimu_li(li: dict) -> list[str]:
    """对单组随机积木输入跑被测函数并做性质断言，返回问题清单。

    性质清单（任何一条不成立都是缺陷）：
      P1 合计恒等：Σ四模块净差额 + 未归属净差额 == 净总差异（Σ全部行）；
      P2 占比恒等：分母>0 时 Σ四模块占比 + 未归属占比 ∈ [9995, 10005]
          （half-up 逐桶舍入 ±0.5 基点 × 5 桶的容差），分母=0 时全 None；
      P3 确定性：同输入两次调用结果完全一致；
      P4 映射一致：已知池科目全部落入期望模块；
      P5 高亮正确：hexin_mokuai == 影子高亮；
      P6 影子一致：四模块差额/占比、分母、未归属占比与影子逐字段相等；
      P7 形态合法：占比为 [0,10000] 整数或 None；模块 F/A 合法。
      容差说明   P2 的 ±5 基点来自 5 个桶各自 half-up 舍入 ±0.5 的极值。
      失败输出   断言失败时打印完整输入 JSON——可粘进单元测试当回归用例。
    """
    # 物化输入：字典 → JimuHang（生成器保证字段名与 dataclass 完全一致）
    hang_lie = [JimuHang(**h) for h in li['hang_lie']]
    # 跑被测函数一次拿结果；影子在下方独立重演（不共享任何代码路径）
    jieguo = chai_jimu(hang_lie)
    wenti: list[str] = []
    yingzi = yingzi_jimu_jisuan(li)

    # P1 合计恒等（未归属净差额来自影子——独立累计）
    mokuai_zong = sum(x.chae_fen for x in jieguo.mokuai_lie)
    if mokuai_zong + yingzi['weigui_jing'] != jieguo.jing_heji_fen:
        wenti.append('P1: 模块合计 + 未归属 != 净总差异')

    # 分母口径（D2）= Σ|模块净| + |未归属净|——与占比合计恒等式同源
    # P2 占比恒等（分母>0 时合计容差 ±5 基点；分母=0 时全部 None）
    fenmu = jieguo.zhanbi_fenmu_fen
    if fenmu == 0:
        if any(x.zhanbi_bps is not None for x in jieguo.mokuai_lie) or jieguo.weiguishu_zhanbi_bps is not None:
            wenti.append('P2: 分母为 0 却仍有占比值')
    else:
        zonghe = sum(x.zhanbi_bps for x in jieguo.mokuai_lie) + jieguo.weiguishu_zhanbi_bps
        if not (9995 <= zonghe <= 10005):
            wenti.append(f'P2: 占比合计 {zonghe} 偏离 10000')

    # 确定性：同输入重跑一次（dataclass 全字段等值比较）
    if chai_jimu(hang_lie) != jieguo:
        wenti.append('P3: 同输入两次结果不一致')

    # 明细反向索引：模块名 → 该模块下科目集合（逐行核对归属）
    mingxi_ditu = {x.mokuai: {t.kemu for t in x.mingxi} for x in jieguo.mokuai_lie}
    for hang in li['hang_lie']:
        qidai_mokuai = KEMU_CHI.get(hang['kemu'])
        if qidai_mokuai is not None and hang['kemu'] not in mingxi_ditu[qidai_mokuai]:
            wenti.append(f"P4: {hang['kemu']} 未落入 {qidai_mokuai}")

    # 高亮比对：四模块内 A 最大者（未归属不参与高亮——D3 口径）
    if jieguo.hexin_mokuai != yingzi['hexin']:
        wenti.append(f"P5: 高亮 {jieguo.hexin_mokuai} != 影子 {yingzi['hexin']}")

    # 影子互证是本节核心：被测模块与影子任何一侧漂移都必然在此暴露
    if [x.chae_fen for x in jieguo.mokuai_lie] != [
        yingzi['he_ji'][m] for m in ('收入模块', '成本模块', '费用模块', '采购模块')
    ]:
        wenti.append('P6: 模块差额与影子不一致')
    if [x.zhanbi_bps for x in jieguo.mokuai_lie] != [
        yingzi['zhanbi'][m] for m in ('收入模块', '成本模块', '费用模块', '采购模块')
    ]:
        wenti.append('P6: 模块占比与影子不一致')
    if jieguo.zhanbi_fenmu_fen != yingzi['fenmu']:
        wenti.append('P6: 占比分母与影子不一致')
    if jieguo.weiguishu_zhanbi_bps != yingzi['zhanbi_weigui']:
        wenti.append('P6: 未归属占比与影子不一致')

    # P7 形态合法（bool 是 int 子类，须排除；F/A 合法集）
    for x in jieguo.mokuai_lie:
        if x.zhanbi_bps is not None and (
            isinstance(x.zhanbi_bps, bool) or not isinstance(x.zhanbi_bps, int)
            or not (0 <= x.zhanbi_bps <= 10000)
        ):
            wenti.append('P7: 占比形态非法')
        if x.fa not in ('F', 'A', '—'):
            wenti.append('P7: 模块 F/A 非法')
    return wenti


# ----------------------------------------------------------------------
# 随机检验主循环：与滚动/判定模块同构（固定种子可复现，失败打印完整输入）
# ----------------------------------------------------------------------
def suiji_yansheng_jimu(shuliang: int, zhongzi: int | None, xiangqi: bool = True) -> int:
    """积木模块的随机检验主循环（生成-检验 N 组，返回失败组数）。"""
    suijiqi = random.Random(zhongzi)  # zhongzi=None → 真随机探矿
    shibai = 0
    # 生成-检验主循环：失败组打印完整输入 JSON（可粘进单元测试当回归用例）
    for i in range(shuliang):
        li = shengcheng_jimu_li(suijiqi)
        wenti = jiancha_jimu_li(li)
        if wenti:
            # 失败输入可直接粘进测试当回归用例
            shibai += 1
            if xiangqi:
                print(f'FAIL 积木例#{i}: {wenti}\n  shuru={json.dumps(li, ensure_ascii=False)}')
    if xiangqi:
        print(f'积木随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    return shibai


# ======================================================================
# 平衡计分卡 BSC：随机生成与性质断言（公式与等级表即 oracle + 影子重算）
# ======================================================================
# 设计说明：BSC 是纯加权公式（得分/总分/等级均为解析关系），性质断言
# 直接复核公式恒等与等级映射；同时用影子重算（独立 half-up 写法）互证。
# 随机维度刻意覆盖：达成率 >100%（不封顶路径 T-05）、全零（退化路径）、
# 随机权重（合计恒 100，压公式两侧与权重回显）。
# 口径锚点：权重默认 40/30/20/10、合计必须 100%；五档等级阈值 90/80/70/60。
# ======================================================================


# 权重生成器独立于被测模块——刻意不 import QUANZHONG_MOREN，影子互证需要
def _suiji_quanzhong(suijiqi: random.Random) -> tuple[int, int, int, int]:
    """随机生成一组合法权重（四段 0~100 整数、合计恒 100）。

    做法：把 100 个"百分点"随机投给四个维度（每投一次某维 +1）——
    天然满足每段 0~100 与合计 100 的校验口径，且能压到 (100,0,0,0)
    这类极端配比。
    """
    fenpei = [0, 0, 0, 0]
    for _ in range(100):
        fenpei[suijiqi.randrange(4)] += 1
    return (fenpei[0], fenpei[1], fenpei[2], fenpei[3])


# 随机用例生成：字典键与 BscShuru 字段同名——jiancha 里直接 **li 解包构造
def shengcheng_bsc_li(suijiqi: random.Random) -> dict:
    """生成一组随机但【合法】的 BSC 输入（纯数据字典，键=dataclass 字段名）。

    随机维度（每维压测一条分支）：
      达成率  三档分布：10% 零（压退化/等级下限）、20% 超 100%（101%~
              150%，压不封顶路径）、70% 正常 0~100%；
      权重    50% 默认（None）、50% 随机四段合计恒 100（压公式两侧与回显）。
    """
    dachenglv = []
    for _ in range(4):
        # 超 100% 档从 101% 起（=10,100 基点）——留足 half-up 余量，
        # 保证得分必然 >100，让 P2 不封顶断言在随机组合下可判定
        if suijiqi.random() < 0.1:
            dachenglv.append(0)
        elif suijiqi.random() < 0.2:
            dachenglv.append(suijiqi.randint(10_100, 15_000))
        else:
            dachenglv.append(suijiqi.randint(0, 10_000))
    # 权重：对半开——None 走默认 40/30/20/10（P5 验证默认回显），
    # 否则随机配比（P5 验证自定义回显）
    quanzhong = None if suijiqi.random() < 0.5 else _suiji_quanzhong(suijiqi)
    return {
        'caijing_bps': dachenglv[0],
        'kehu_bps': dachenglv[1],
        'neibu_bps': dachenglv[2],
        'xuexi_bps': dachenglv[3],
        'quanzhong': quanzhong,
    }


def yingzi_bsc_jisuan(li: dict) -> dict:
    """独立影子重算：同公式、不同 half-up 写法（divmod），逐字段互证。"""
    # 生效权重：None → 默认配比（与 QUANZHONG_MOREN 同值，影子不 import）
    quanzhong = li['quanzhong'] if li['quanzhong'] is not None else (40, 30, 20, 10)
    bps = (li['caijing_bps'], li['kehu_bps'], li['neibu_bps'], li['xuexi_bps'])
    defen = []
    # 维度得分：逐维 ÷100 half-up（影子独立写法，不调被测模块私有函数）
    for v in bps:
        # divmod half-up：与 (2×v+100)//200 等价（÷100 后四舍五入）
        shang, _ = divmod(v * 2 + 100, 200)
        defen.append(shang)
    # 总分：Σ权重×得分 后 ÷100 half-up（divmod 写法与模块内公式等价；
    # 不封顶意味着 Σ 不设上限——得分 >100 的维度直接进加权和）
    jiaquan_he = sum(w * d for w, d in zip(quanzhong, defen))
    zongfen, _ = divmod(jiaquan_he * 2 + 100, 200)
    # 等级：阈值降序查表（独立重写五档映射）
    dengji = '严重不合格'
    for yuzhi, mingcheng in ((90, '优秀'), (80, '良好'), (70, '合格'), (60, '预警')):
        if zongfen >= yuzhi:
            dengji = mingcheng
            break
    return {'defen': tuple(defen), 'quanzhong': quanzhong,
            'zongfen': zongfen, 'dengji': dengji}


def jiancha_bsc_li(li: dict) -> list[str]:
    """对单组随机 BSC 输入跑被测函数并做性质断言，返回问题清单。

    性质清单（任何一条不成立都是缺陷）：
      P1 影子一致：四维得分/总分/等级与影子重算逐字段相等；
      P2 不封顶：任一达成率 >100% → 对应得分 >100（T-05 拍板，无裁剪）；
      P3 确定性：同输入两次调用结果完全一致；
      P4 形态合法：得分为非负整数；等级 ∈ 五档合法集；
      P5 权重回显：输出 quanzhong == 生效权重（默认或自定义）。
      容差说明   无——全公式为解析关系，影子不一致即缺陷，不需要容差。
    """
    shuru = BscShuru(**li)  # 字典键与 dataclass 字段同名，直接解包构造
    # 跑被测函数一次拿结果；影子在下方独立重演（不共享任何代码路径）
    jieguo = jisuan_bsc(shuru)
    wenti: list[str] = []
    yingzi = yingzi_bsc_jisuan(li)

    # P1 影子一致（得分/总分/等级三组字段逐一比对）
    defen = (jieguo.caijing_defen, jieguo.kehu_defen,
             jieguo.neibu_defen, jieguo.xuexi_defen)
    if defen != yingzi['defen']:
        wenti.append(f'P1: 得分与影子不一致 {defen} != {yingzi["defen"]}')
    if jieguo.zongfen != yingzi['zongfen'] or jieguo.dengji != yingzi['dengji']:
        wenti.append('P1: 总分/等级与影子不一致')

    # P2 不封顶（T-05）：达成率 >100% 时得分必须 >100 原样保留
    for bps, d in zip((li['caijing_bps'], li['kehu_bps'],
                       li['neibu_bps'], li['xuexi_bps']), defen):
        if bps > 10_000 and d <= 100:
            wenti.append(f'P2: 达成率 {bps} 超过 100% 但得分被裁剪为 {d}')

    # P3 确定性（dataclass 等值）
    if jisuan_bsc(shuru) != jieguo:
        wenti.append('P3: 同输入两次结果不一致')

    # P4 形态合法（得分非负整数——bool 是 int 子类，须排除）
    if any(isinstance(d, bool) or not isinstance(d, int) or d < 0 for d in defen):
        wenti.append('P4: 得分形态非法')
    if jieguo.dengji not in ('优秀', '良好', '合格', '预警', '严重不合格'):
        wenti.append(f'P4: 等级非法 {jieguo.dengji}')

    # P5 权重回显：报告/看板要展示生效权重，默认与自定义两条路径都验
    if jieguo.quanzhong != yingzi['quanzhong']:
        wenti.append('P5: 权重回显与生效权重不一致')
    return wenti


def suiji_yansheng_bsc(shuliang: int, zhongzi: int | None, xiangqi: bool = True) -> int:
    """BSC 模块的随机检验主循环（生成-检验 N 组，返回失败组数）。"""
    suijiqi = random.Random(zhongzi)  # zhongzi=None → 真随机探矿
    shibai = 0
    # 生成-检验主循环：失败组打印完整输入 JSON（可粘进单元测试当回归用例）
    for i in range(shuliang):
        li = shengcheng_bsc_li(suijiqi)
        wenti = jiancha_bsc_li(li)
        if wenti:
            # 失败输入可直接粘进测试当回归用例
            shibai += 1
            if xiangqi:
                print(f'FAIL BSC例#{i}: {wenti}\n  shuru={json.dumps(li, ensure_ascii=False)}')
    if xiangqi:
        print(f'BSC随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    return shibai


# ======================================================================
# KPI 指标库：随机生成与性质断言（15 项公式即 oracle + 影子重算）
# ======================================================================
# 设计说明：KPI 是纯比率公式，性质断言直接复核影子一致性/确定性/形态；
# 随机维度刻意覆盖：字段 30% 缺数（压缺数纪律 None 路径）、分母 0
# （压除零退化）、极端数值（压 half-up 边界）。
#
# 影子原则：yingzi_kpi_jisuan 独立重写全部 15 项公式（divmod half-up），
# 不复用 kpi 模块任何内部函数——双方不一致即为缺陷。
#
# 缺数语义：None = 缺数（交人工），0 = 有数但为 0（分母 0 → 比率 None）——
# 两种路径在随机组合下都会被压到，防止实现把两者混淆。
# ======================================================================

#: KPI 取数字段清单（KpiShuru 全部字段名——生成器与影子共用）；
#: 26 个字段 = 财务取数 16 + 非财务取数 10（计数/天数类字段同构处理）
_KPI_ZIDUAN = (
    'shouru_shiji_fen', 'shouru_yusuan_fen',
    'kekong_chengben_shiji_fen', 'kekong_chengben_yusuan_fen',
    'feiyong_shiji_fen', 'feiyong_yusuan_fen',
    'maoli_fen', 'jingshui_fen', 'pbit_fen', 'ziben_zhanyong_fen',
    'liudong_zichan_qichu_fen', 'liudong_zichan_qimo_fen',
    'liudong_fuzhai_qichu_fen', 'liudong_fuzhai_qimo_fen',
    'caigou_benqi_fen', 'caigou_shangqi_fen',
    'shiji_chanchu', 'qianzai_channeng',
    'dingdan_zongshu', 'lvyue_dingdan_shu', 'jiaofu_zhouqi_tian_shu',
    'manyi_keshu', 'shoufang_keshu', 'jihua_yewu_liang',
    'wancheng_yewu_liang', 'yichang_shijian_shu',
)


def shengcheng_kpi_li(suijiqi: random.Random) -> dict:
    """生成一组随机但【合法】的 KPI 输入（纯数据字典，键=字段名）。

    随机维度（每维压测一条分支）：
      缺数   30% None（压缺数纪律——缺数项必须输出 None）；
      零值   10% 0（压除零退化——分母 0 的比率必须 None）；
      数值   其余 1..1e9 随机（压 half-up 与形态）。

    说明：字典键与 KpiShuru 字段名完全一致，jiancha 里直接 **li 解包构造；
    影子从同一字典独立重算——输入形态由生成器单一保证。
    """
    li: dict = {}
    # 逐字段三档随机——26 个字段独立决策，形态组合空间足够大
    for ziming in _KPI_ZIDUAN:
        # 三档：30% 缺数、10% 零、60% 随机正整数
        if suijiqi.random() < 0.3:
            li[ziming] = None
        elif suijiqi.random() < 0.1:
            li[ziming] = 0
        else:
            li[ziming] = suijiqi.randint(1, 10**9)
    # 生成器不保证字段间语义关系（如收入>0 才给毛利）——缺数/除零路径
    # 恰是测试目标：公式层必须对任意合法形态给出 None 或数值，不崩；
    # 若实现把「缺数」当 0 算，P1 影子比对会立刻暴露分歧
    return li


def yingzi_kpi_jisuan(li: dict) -> dict:
    """独立影子重算：15 项公式独立实现（divmod half-up），逐字段互证。

    刻意不复用 kpi 模块内部函数——两边不一致即为缺陷；
    带符号项（费用偏差率/采购变动率）符号随差值、half-up 取绝对值后再回填。
    """
    def bili(fenzi, fenmu):
        # 非负比率：分子/分母缺数或分母 ≤ 0 → None；否则 half-up 基点
        # divmod 写法与模块内 (2n+d)//(2d) 等价——殊途同归互证
        if fenzi is None or fenmu is None or fenmu <= 0:
            return None
        shang, _ = divmod(fenzi * 10_000 * 2 + fenmu, 2 * fenmu)
        return shang

    def daifuhao(fenzi, fenmu):
        # 带符号偏差率：(分子−分母)/分母，half-up，符号随差值
        # 先按 |差值| half-up 再回填符号——与模块内 _daifuhao_bps 同规则
        if fenzi is None or fenmu is None or fenmu <= 0:
            return None
        chae = fenzi - fenmu
        shang, _ = divmod(abs(chae) * 10_000 * 2 + fenmu, 2 * fenmu)
        return shang if chae >= 0 else -shang

    # 平均营运资金 =（期初净 + 期末净）÷ 2（half-up；净可为负）；
    # 净营运资金 = 流动资产 − 流动负债（定稿 #9 口径）；
    # 影子独立实现四段取值与负数场景（资金周转率分母 ≤ 0 → None）；
    # 负数 half-up：先取绝对值进位再回填符号（与模块内实现同构不同码）
    qz, qm = li['liudong_zichan_qichu_fen'], li['liudong_zichan_qimo_fen']
    fz, fm = li['liudong_fuzhai_qichu_fen'], li['liudong_fuzhai_qimo_fen']
    pingjun = None
    if qz is not None and qm is not None and fz is not None and fm is not None:
        he = (qz - fz) + (qm - fm)
        pingjun = (he + 1) // 2 if he >= 0 else -((-he + 1) // 2)

    # 15 项逐一重算（顺序 = 定稿 §8 清单；交付周期/异常事项为直接值透传）
    return {
        # 财务 1~2：达成率与控制率（预算分母）
        'yingshou_dachenglv_bps': bili(li['shouru_shiji_fen'], li['shouru_yusuan_fen']),
        'chengben_kongzhilv_bps': bili(li['kekong_chengben_shiji_fen'], li['kekong_chengben_yusuan_fen']),
        # 财务 3：费用偏差率（带符号，负 = 节约）
        'feiyong_pianchalv_bps': daifuhao(li['feiyong_shiji_fen'], li['feiyong_yusuan_fen']),
        # 财务 4~6：三大利润率（分母统一 = 实际收入）
        'maolilv_bps': bili(li['maoli_fen'], li['shouru_shiji_fen']),
        'jinglirunlv_bps': bili(li['jingshui_fen'], li['shouru_shiji_fen']),
        'xiaoshou_lirunlv_bps': bili(li['pbit_fen'], li['shouru_shiji_fen']),
        # 财务 7~8：两大周转率（1 次 = 10000 基点；资金周转率分母可 None）
        'zichan_zhouzhuanlv_bps': bili(li['shouru_shiji_fen'], li['ziben_zhanyong_fen']),
        'zijin_zhouzhuanlv_bps': bili(li['shouru_shiji_fen'], pingjun),
        # 财务 9：采购成本变动率（带符号，负 = 下降）
        'caigou_chengben_bian_donglv_bps': daifuhao(li['caigou_benqi_fen'], li['caigou_shangqi_fen']),
        # 非财务 1~2：履约率与产能利用率（计数分母）
        'gongyinglian_lvyuelv_bps': bili(li['lvyue_dingdan_shu'], li['dingdan_zongshu']),
        'channeng_liyonglv_bps': bili(li['shiji_chanchu'], li['qianzai_channeng']),
        # 非财务 3：交付周期（直接值透传，无公式）
        'jiaofu_zhouqi_tian': li['jiaofu_zhouqi_tian_shu'],
        # 非财务 4~5：满意度与业务进度（计数比率）
        'kehu_manyilv_bps': bili(li['manyi_keshu'], li['shoufang_keshu']),
        'yewu_jindu_bps': bili(li['wancheng_yewu_liang'], li['jihua_yewu_liang']),
        # 非财务 6：异常事项数量（直接值透传）
        'yichang_shijian_shu': li['yichang_shijian_shu'],
    }


#: KPI 输出字段清单（KpiJieguo 全部字段名——性质断言逐字段比对）；
#: 顺序 = KpiJieguo 声明顺序（与定稿 §8 清单一致，含两个带符号项）
_KPI_SHUCHU = ('yingshou_dachenglv_bps', 'chengben_kongzhilv_bps',
               'feiyong_pianchalv_bps', 'maolilv_bps', 'jinglirunlv_bps',
               'xiaoshou_lirunlv_bps', 'zichan_zhouzhuanlv_bps',
               'zijin_zhouzhuanlv_bps', 'caigou_chengben_bian_donglv_bps',
               'gongyinglian_lvyuelv_bps', 'channeng_liyonglv_bps',
               'jiaofu_zhouqi_tian', 'kehu_manyilv_bps', 'yewu_jindu_bps',
               'yichang_shijian_shu')


def jiancha_kpi_li(li: dict) -> list[str]:
    """对单组随机 KPI 输入跑被测函数并做性质断言，返回问题清单。

    性质清单（任何一条不成立都是缺陷）：
      P1 影子一致：15 项输出与影子重算逐字段相等；
      P2 缺数一致：输入缺数 → 对应输出 None（缺数纪律）；
      P3 确定性：同输入两次调用结果完全一致；
      P4 形态合法：输出为 None 或整数（带符号项可为负、其余非负）。

    说明：P1 即全量 oracle——影子实现了同一套 None 规则与 half-up，
    15 项同时一致的概率性失误几乎不可能。
    """
    shuru = KpiShuru(**li)
    # 跑被测函数一次拿结果；影子在下方独立重演（不共享任何代码路径）
    jieguo = jisuan_kpi(shuru)
    wenti: list[str] = []
    # 影子从【同一字典】独立重算——输入形态单一来源，两边起点一致
    yingzi = yingzi_kpi_jisuan(li)

    # P1 影子一致（15 项逐一比对——任何一项漂移都整组失败）
    for ziming in _KPI_SHUCHU:
        if getattr(jieguo, ziming) != yingzi[ziming]:
            wenti.append(f'P1: {ziming} 与影子不一致 '
                         f'{getattr(jieguo, ziming)} != {yingzi[ziming]}')

    # P2 缺数一致（抽样核对：收入分母缺失 → 营收达成率 None；
    # 全量缺数语义已由 P1 影子一致性覆盖——影子实现同样的 None 规则）
    if (li['shouru_shiji_fen'] is None or li['shouru_yusuan_fen'] in (None, 0)) \
            and jieguo.yingshou_dachenglv_bps is not None:
        wenti.append('P2: 收入缺数/分母 0 却算出营收达成率')

    # P3 确定性（dataclass 等值——纯函数要求，同输入必同输出）
    if jisuan_kpi(shuru) != jieguo:
        wenti.append('P3: 同输入两次结果不一致')

    # P4 形态合法（bool 是 int 子类，须排除；带符号项可负）
    # 带符号项 = 费用偏差率/采购成本变动率（负 = 节约/下降）
    dai_fuhao = {'feiyong_pianchalv_bps', 'caigou_chengben_bian_donglv_bps'}
    for ziming in _KPI_SHUCHU:
        zhi = getattr(jieguo, ziming)
        if zhi is None:
            continue
        if isinstance(zhi, bool) or not isinstance(zhi, int):
            wenti.append(f'P4: {ziming} 形态非法 {zhi!r}')
        if zhi < 0 and ziming not in dai_fuhao:
            wenti.append(f'P4: {ziming} 出现负值 {zhi}')
    # 带符号项（费用偏差率/采购变动率）负值合法——节约/下降是有效状态
    return wenti


def suiji_yansheng_kpi(shuliang: int, zhongzi: int | None, xiangqi: bool = True) -> int:
    """KPI 模块的随机检验主循环（生成-检验 N 组，返回失败组数）。"""
    # 与滚动/判定主循环同构：固定种子可复现；失败打印完整输入 JSON
    suijiqi = random.Random(zhongzi)  # zhongzi=None → 真随机探矿
    shibai = 0
    # 生成-检验主循环：失败组打印完整输入 JSON（可粘进单元测试当回归用例）
    for i in range(shuliang):
        li = shengcheng_kpi_li(suijiqi)
        wenti = jiancha_kpi_li(li)
        if wenti:
            # 失败输入可直接粘进单元测试当回归用例
            shibai += 1
            if xiangqi:
                print(f'FAIL KPI例#{i}: {wenti}\n  shuru={json.dumps(li, ensure_ascii=False)}')
    if xiangqi:
        print(f'KPI随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    # 返回失败组数——CLI 以 0/1 退出码作门禁（与滚动模块同约定）
    return shibai


# ======================================================================
# 变更溯源：随机生成与性质断言（影响率/偏好/占比公式即 oracle + 影子）
# ======================================================================
# 设计说明：溯源的不变量（占比合计恒 10000 + 作用方向偏好表 + 影响率
# 带符号公式）直接性质断言；影子独立重写偏好表与 half-up 互证。
#
# 偏好语义：作用方向 = 数值方向 × 偏好（越高越好/越低越好）——
# 影子刻意另写一张偏好集合（_SUYUAN_YUEDI），与 suyuan.KPI_PIANHAO
# 双实现互证，任何一侧表漂移都会被 P1 抓住。
# ======================================================================

#: 15 项 KPI 名清单（生成器抽名用——与 suyuan.KPI_PIANHAO 的键一致）；
#: 抽名保证「名合法」——未知名拒绝路径由单元测试覆盖，这里只压正路
_SUYUAN_KPI_MING = (
    '营收达成率', '成本控制率', '费用偏差率', '毛利率', '净利润率',
    '销售利润率', '资产周转率', '资金周转率', '采购成本变动率',
    '供应链履约率', '产能利用率', '交付周期', '客户满意度',
    '业务完成进度', '异常事项数量',
)
#: 影子偏好表（独立重写，不复用 suyuan 常量——双实现互证）；
#: 越低越好五项 = 成本控制率/费用偏差率/采购成本变动率/交付周期/异常事项
_SUYUAN_YUEDI = {'成本控制率', '费用偏差率', '采购成本变动率',
                 '交付周期', '异常事项数量'}


def shengcheng_suyuan_li(suijiqi: random.Random) -> dict:
    """生成一组随机但【合法】的溯源输入（纯数据字典）。

    随机维度：行数 1..8（KPI 名不重复——不触发防双计校验）；
    变更前/后 0..1e9；原始预算基准 70% 正数 / 20% None / 10% 0
    （压缺数与除零退化——影响率 None 路径高频出现）。
    """
    # 行数 1..8；sample 保证 KPI 名不重复（不触发被测模块的防双计校验）
    shu = suijiqi.randint(1, 8)
    ming_lie = suijiqi.sample(list(_SUYUAN_KPI_MING), shu)
    hang_lie = []
    for ming in ming_lie:
        # 原始预算三档：70% 正、20% 缺数、10% 零——影响率 None 路径高频出现；
        # 三档刻意等概率混合，防止实现只照顾「有数」主线
        if suijiqi.random() < 0.2:
            yuan = None
        elif suijiqi.random() < 0.1:
            yuan = 0
        else:
            yuan = suijiqi.randint(1, 10**9)
        # 变更前/后独立随机——持平（差值 0）也会自然出现，压无作用路径
        hang_lie.append({
            'kpi_mingcheng': ming,
            'bianhua_qian': suijiqi.randint(0, 10**9),
            'bianhua_hou': suijiqi.randint(0, 10**9),
            'yuan_yusuan': yuan,
        })
    return {'hang_lie': hang_lie}


def yingzi_suyuan_jisuan(li: dict) -> dict:
    """独立影子重算：影响率/作用/占比/TOP3 全部独立实现，逐字段互证。

    影响率/占比用 divmod half-up（与模块内公式等价但写法不同）；
    偏好表另写一张集合（_SUYUAN_YUEDI）——双实现互证防表漂移。
    """
    def lv(qian, hou, yuan):
        # 影响率 =（变更后−变更前）÷ 原始预算 × 10000，half-up 带符号；
        # 原始预算缺失/≤0 → None（缺数纪律，与模块内同规则）
        if yuan is None or yuan <= 0:
            return None
        chae = hou - qian
        shang, _ = divmod(abs(chae) * 10_000 * 2 + yuan, 2 * yuan)
        return shang if chae >= 0 else -shang

    def zuoyong(ming, chae):
        # 作用方向 = 数值方向 × 偏好（独立偏好集合判定）
        if chae == 0:
            return '无作用'
        if ming in _SUYUAN_YUEDI:
            return '负向作用' if chae > 0 else '正向作用'
        return '正向作用' if chae > 0 else '负向作用'

    xiang_lie = []
    for hang in li['hang_lie']:
        chae = hang['bianhua_hou'] - hang['bianhua_qian']
        xiang_lie.append({
            'kpi_mingcheng': hang['kpi_mingcheng'],
            'yingxianglv_bps': lv(hang['bianhua_qian'], hang['bianhua_hou'],
                                  hang['yuan_yusuan']),
            'zuoyong': zuoyong(hang['kpi_mingcheng'], chae),
        })
    # 占比分母 = Σ|各 KPI 净影响率|（同积木 D2 口径——合计恒 10000 的基础）
    fenmu = sum(abs(x['yingxianglv_bps']) for x in xiang_lie
                if x['yingxianglv_bps'] is not None)
    # 占比回填：影响率 None 或分母 0 → None（除零纪律）
    for x in xiang_lie:
        if x['yingxianglv_bps'] is None or fenmu == 0:
            x['zhanbi_bps'] = None
        else:
            x['zhanbi_bps'], _ = divmod(abs(x['yingxianglv_bps']) * 10_000 * 2 + fenmu,
                                        2 * fenmu)
    # TOP3：正/负向作用按 |影响率| 降序取前三（影响率 None 不参与排名）；
    # 排序键 = −|影响率|（升序反转），stable 保证并列按输入顺序
    # 注意：排序键用 −|影响率|（升序反转）实现降序——Python 排序稳定，
    # 并列时自动保持输入顺序（与模块内 _top3 约定一致）
    zheng = sorted([x['kpi_mingcheng'] for x in xiang_lie if x['zuoyong'] == '正向作用'
                    and x['yingxianglv_bps'] is not None],
                   key=lambda m: -abs(next(x['yingxianglv_bps'] for x in xiang_lie
                                           if x['kpi_mingcheng'] == m)))
    # 负向 TOP3 同理：影响率取绝对值降序，并列保输入顺序
    fu = sorted([x['kpi_mingcheng'] for x in xiang_lie if x['zuoyong'] == '负向作用'
                 and x['yingxianglv_bps'] is not None],
                key=lambda m: -abs(next(x['yingxianglv_bps'] for x in xiang_lie
                                        if x['kpi_mingcheng'] == m)))
    return {'xiang': xiang_lie, 'fenmu': fenmu,
            'zhengxiang_top3': zheng[:3], 'fuxiang_top3': fu[:3]}


def jiancha_suyuan_li(li: dict) -> list[str]:
    """对单组随机溯源输入跑被测函数并做性质断言，返回问题清单。

    性质清单（任何一条不成立都是缺陷）：
      P1 影子一致：影响率/作用/占比/TOP3 与影子逐字段相等；
      P2 占比恒等：分母>0 时 Σ占比 ∈ [9995, 10005]（half-up 容差）；
      P3 确定性：同输入两次调用结果完全一致；
      P4 形态合法：影响率为 None 或整数（可负）；占比为 [0,10000] 整数或 None。

    说明：P2 容差 ±5 基点来自各桶 half-up 各自 ±0.5 的极值合计。
    """
    hang_lie = [SuyuanHang(**h) for h in li['hang_lie']]
    # 跑被测函数一次拿结果；影子在下方独立重演（不共享任何代码路径）
    jieguo = jisuan_suyuan(hang_lie)
    wenti: list[str] = []
    # 影子从【同一字典】独立重算——输入形态单一来源，两边起点一致
    yingzi = yingzi_suyuan_jisuan(li)

    # P1 影子一致（逐项影响率/作用/占比三字段同时比对；
    # 作用方向比对 = 偏好表双实现互证——任何一侧表漂移都会被抓住）
    for i, x in enumerate(jieguo.xiang):
        y = yingzi['xiang'][i]
        if x.yingxianglv_bps != y['yingxianglv_bps'] or x.zuoyong != y['zuoyong'] \
                or x.zhanbi_bps != y['zhanbi_bps']:
            wenti.append(f'P1: 第 {i} 行与影子不一致')
    # TOP3 比对：正负两路同时验——排名规则漂移会立刻暴露
    if jieguo.zhengxiang_top3 != yingzi['zhengxiang_top3'] \
            or jieguo.fuxiang_top3 != yingzi['fuxiang_top3']:
        wenti.append('P1: TOP3 与影子不一致')

    # P2 占比恒等（分母>0 时合计容差 ±5 基点；分母=0 时全部 None）
    # 分母 = Σ|净影响率|——不可算行既不进分子也不进分母
    # 分母为 0 = 全部行不可算（全 None/全 0 基准）——占比必须全 None
    fenmu = jieguo.yingxiang_fenmu_bps
    if fenmu == 0:
        if any(x.zhanbi_bps is not None for x in jieguo.xiang):
            wenti.append('P2: 分母为 0 却仍有占比值')
    else:
        # 容差 ±5 基点 = 各桶 half-up ±0.5 的极值合计（最多 8 桶）
        zonghe = sum(x.zhanbi_bps for x in jieguo.xiang if x.zhanbi_bps is not None)
        if not (9995 <= zonghe <= 10005):
            wenti.append(f'P2: 占比合计 {zonghe} 偏离 10000')

    # P3 确定性（dataclass 等值——TOP3 顺序也须稳定）
    if jisuan_suyuan(hang_lie) != jieguo:
        wenti.append('P3: 同输入两次结果不一致')

    # P4 形态合法（影响率 None/整数；占比 [0,10000] 或 None；bool 排除）
    # 影响率可负可零（带符号公式）；占比非负且不超 10000（合计恒等约束下）
    for x in jieguo.xiang:
        if x.yingxianglv_bps is not None and (
            isinstance(x.yingxianglv_bps, bool) or not isinstance(x.yingxianglv_bps, int)
        ):
            wenti.append('P4: 影响率形态非法')
        if x.zhanbi_bps is not None and (
            isinstance(x.zhanbi_bps, bool) or not isinstance(x.zhanbi_bps, int)
            or not (0 <= x.zhanbi_bps <= 10000)
        ):
            wenti.append('P4: 占比形态非法')
    return wenti


def suiji_yansheng_suyuan(shuliang: int, zhongzi: int | None, xiangqi: bool = True) -> int:
    """溯源模块的随机检验主循环（生成-检验 N 组，返回失败组数）。"""
    # 与 KPI 主循环同构：固定种子可复现；失败打印完整输入 JSON
    suijiqi = random.Random(zhongzi)
    shibai = 0
    # 生成-检验主循环：失败组打印完整输入 JSON（可粘进单元测试当回归用例）
    for i in range(shuliang):
        li = shengcheng_suyuan_li(suijiqi)
        wenti = jiancha_suyuan_li(li)
        if wenti:
            # 失败输入可直接粘进单元测试当回归用例
            shibai += 1
            if xiangqi:
                print(f'FAIL 溯源例#{i}: {wenti}\n  shuru={json.dumps(li, ensure_ascii=False)}')
    if xiangqi:
        print(f'溯源随机检验完成：{shuliang} 组，失败 {shibai} 组（种子={zhongzi}）')
    # 返回失败组数——CLI 以 0/1 退出码作门禁（与滚动模块同约定）
    return shibai


# ======================================================================
# 样本模式与命令行入口
# ======================================================================


def shengcheng_yangben(zhongzi: int | None, shuchu_lujing: Path) -> dict:
    """生成一组随机数据并以 JSON 落盘（供演示/复现/后续模块复用）。

    样本与随机检验用同一生成器——保证"测试过的数据形态"与
    "落盘的数据形态"完全一致，不会出现两套随机逻辑。
    """
    suijiqi = random.Random(zhongzi)
    li = shengcheng_gundong_yusuan_li(suijiqi)
    shuchu_lujing.parent.mkdir(parents=True, exist_ok=True)  # fixtures/ 不存在则建
    shuchu_lujing.write_text(json.dumps(li, ensure_ascii=False, indent=2), encoding='utf-8')
    # 摘要行：期数/实际期数，方便肉眼确认数据规模
    print(f'样本已写入：{shuchu_lujing}（{len(li["yusuan"])} 期，实际 {len(li["shiji"])} 期）')
    return li


def zhukong(canshu_liebiao: list[str]) -> int:
    """命令行入口：解析参数并调度两种模式。"""
    jiexiqi = argparse.ArgumentParser(description='随机数据生成与随机检验')
    jiexiqi.add_argument('--mokuai', default='gundong_yusuan',
                         help='目标模块（gundong/chafen/huanlu/jimu/bsc/kpi/suyuan）')
    jiexiqi.add_argument('--moshi', default='suiji', choices=['suiji', 'yangben'], help='suiji=随机检验 / yangben=样本落盘')
    jiexiqi.add_argument('--shuliang', type=int, default=200, help='随机检验用例数')
    jiexiqi.add_argument('--zhongzi', type=int, default=42, help='随机种子（可复现）')
    jiexiqi.add_argument('--shuchu', default='fixtures/demo.json', help='样本输出路径')
    canshu = jiexiqi.parse_args(canshu_liebiao)

    if canshu.mokuai not in ('gundong_yusuan', 'chafen', 'huanlu', 'jimu', 'bsc', 'kpi', 'suyuan'):
        # 新模块接入点：在此登记模块名并补 shengcheng_/jiancha_ 两个函数
        print(f'暂不支持模块：{canshu.mokuai}（请在 gen_data.py 登记 shengcheng_/jiancha_ 实现）')
        return 1

    if canshu.moshi == 'yangben':
        # 样本模式按模块走各自的生成器（同一生成器保证形态一致）
        if canshu.mokuai == 'chafen':
            # 拆分样本：一组随机输入直接落盘（复现/演示数据用）
            suijiqi = random.Random(canshu.zhongzi)
            shengcheng_yangben_li = shengcheng_chafen_li(suijiqi)
            shuchu = Path(canshu.shuchu)
            shuchu.parent.mkdir(parents=True, exist_ok=True)
            shuchu.write_text(json.dumps(shengcheng_yangben_li, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'样本已写入：{shuchu}（拆分输入一组）')
            return 0
        if canshu.mokuai == 'bsc':
            # BSC 样本：一组随机输入直接落盘（复现/演示数据用）
            suijiqi = random.Random(canshu.zhongzi)
            bsc_li = shengcheng_bsc_li(suijiqi)
            shuchu = Path(canshu.shuchu)
            shuchu.parent.mkdir(parents=True, exist_ok=True)
            shuchu.write_text(json.dumps(bsc_li, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'样本已写入：{shuchu}（BSC 输入一组）')
            return 0
        if canshu.mokuai == 'jimu':
            # 积木样本：一组随机差异行直接落盘（复现/演示数据用）
            suijiqi = random.Random(canshu.zhongzi)
            jimu_li = shengcheng_jimu_li(suijiqi)
            shuchu = Path(canshu.shuchu)
            shuchu.parent.mkdir(parents=True, exist_ok=True)
            shuchu.write_text(json.dumps(jimu_li, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'样本已写入：{shuchu}（积木输入 {len(jimu_li["hang_lie"])} 行）')
            return 0
        shengcheng_yangben(canshu.zhongzi, Path(canshu.shuchu))
        return 0

    if canshu.mokuai == 'chafen':
        # 拆分模块：性质断言版随机检验（P1~P4，见 jiancha_chafen_li）
        shibai = suiji_yansheng_chafen(canshu.shuliang, zhongzi=canshu.zhongzi)
        return 1 if shibai else 0

    if canshu.mokuai == 'huanlu':
        # 判定模块：性质断言版随机检验（P1~P5，见 jiancha_huanlu_li）
        shibai = suiji_yansheng_huanlu(canshu.shuliang, zhongzi=canshu.zhongzi)
        return 1 if shibai else 0

    if canshu.mokuai == 'jimu':
        # 积木模块：性质断言 + 影子聚合互证（P1~P7，见 jiancha_jimu_li）
        shibai = suiji_yansheng_jimu(canshu.shuliang, zhongzi=canshu.zhongzi)
        return 1 if shibai else 0

    if canshu.mokuai == 'bsc':
        # BSC 模块：性质断言 + 影子重算互证（P1~P5，见 jiancha_bsc_li）
        shibai = suiji_yansheng_bsc(canshu.shuliang, zhongzi=canshu.zhongzi)
        return 1 if shibai else 0

    if canshu.mokuai == 'kpi':
        # KPI 模块：性质断言 + 影子重算互证（P1~P4，见 jiancha_kpi_li；
        # 15 项公式 × 26 字段缺数/除零随机组合——公式层最宽的 fuzz 面）
        shibai = suiji_yansheng_kpi(canshu.shuliang, zhongzi=canshu.zhongzi)
        return 1 if shibai else 0

    if canshu.mokuai == 'suyuan':
        # 溯源模块：性质断言 + 影子重算互证（P1~P4，见 jiancha_suyuan_li；
        # 偏好表双实现互证 + 占比合计恒 10000 不变量）
        shibai = suiji_yansheng_suyuan(canshu.shuliang, zhongzi=canshu.zhongzi)
        return 1 if shibai else 0

    # 滚动预算模块：常规随机 + 零增长专项，两者都须零失败
    shibai = suiji_yansheng(canshu.shuliang, zhongzi=canshu.zhongzi)
    shibai += ling_zengzhang_yansheng(max(canshu.shuliang // 4, 10), zhongzi=canshu.zhongzi + 1)
    return 1 if shibai else 0


if __name__ == '__main__':
    sys.exit(zhukong(sys.argv[1:]))
