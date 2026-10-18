# -*- coding: utf-8 -*-
"""名称替换接口：版式占位符 → 演示文本（唯一出入口，种子确定性）。

版式常量（banshi.py）里的文本一律带占位符：{主体一}/{主体二}/{项目一}/{主体名}…
运行到这里一次性渲染。要换成外部实现（数据库/接口/人工表），只需替换 tihuan_biao
一个函数，签名不变；其余代码一行不用动。

纪律：种子确定性（同种子同名字）；禁词自检（命中即抛错，绝不静默产出）。
"""
import random

#: 字号池（双字僻字组合，避开现实企业与"衡/策/中/学"用字）
ZIHAO = ('恒暻', '睿衍', '晟屿', '岚峙', '岱远', '泓翎', '屿棠',
         '峋瑞', '森屹', '洲衍', '宸屹', '汐衍')

#: 行业词池（一般企业报表适用行业）
HANGYE = ('智能制造', '数字科技', '供应链管理', '精密制造', '商贸实业', '信息技术')

#: 项目/剧名池（演示项目名，避开任何现实作品）
XIANGMU = ('长夜将明', '云海之上', '山海谣', '星轨之外', '千灯引', '风起西洲', '清川行', '秋野纪')

#: 禁词（不得出现参照里的真名/项目名；"蓝恐龙"是单个企业的项目名，已从全链路剔除）
JIN_CI = ('衡策', '中学', '贰零壹陆', '蓝恐龙', '少年派')


def tihuan_biao(seed, leibie='预算基础', qingjing='基础情景', niandu=2027,
                hangye=None, zhuti=None):
    """占位符 → 演示文本。覆盖版式里出现的全部占位符。

    hangye / zhuti 可强制指定行业词与主体名（做多行业回归用），缺省随机。
    """
    rng = random.Random(f'{seed}|名称替换|v2|防撞名|{hangye or ""}|{zhuti or ""}')
    # 两个主体名：字号池 × 行业词，互不相同
    zhuti_lie = []
    ci = 0
    while len(zhuti_lie) < 2:
        ci += 1
        hy = hangye or rng.choice(HANGYE)
        if ci == 1 and zhuti:
            ming = zhuti if zhuti.endswith('有限公司') else zhuti + '有限公司'
        else:
            ming = rng.choice(ZIHAO) + hy + '有限公司'
        if ming not in zhuti_lie:
            zhuti_lie.append(ming)
    zhuti = zhuti_lie
    xiangmu = rng.choice(XIANGMU)
    # 报表日：预算基础=年末，实时经营=已结账月末
    bao_biao_ri = (f'{niandu}年12月31日' if leibie == '预算基础'
                   else f'{niandu}年6月30日')
    biao = {
        '报表日': bao_biao_ri,
        '主体一': zhuti[0],              # 三表左列（原"贰零壹陆"位）
        '主体二': zhuti[1],              # 三表中列（原"蓝恐龙"位）
        '项目一': xiangmu,               # 三表"含《…》项目"位（原《少年派》）
        '主体名': zhuti[0],              # 九表元字段主体名
        '主体编码': f'ENT-{niandu}',
        '情景编码': 'S-BASE',
        '情景': qingjing,
        '年度': str(niandu),
        '种子': str(seed),
        '类别': leibie,
    }
    for k, v in biao.items():
        for j in JIN_CI:
            if j in v:
                raise ValueError(f'替换文本含禁词 {j}：{k}={v}')
    return biao
