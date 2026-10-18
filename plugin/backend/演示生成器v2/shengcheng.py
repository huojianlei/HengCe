# -*- coding: utf-8 -*-
"""入口：生成演示工作簿（零公式、纯数值、尺寸与样式定死、运行时不读任何文件）。

用法：
    python shengcheng.py                      # 十二表两册 + 外部两册（共四册）
    python shengcheng.py --leibie 预算基础     # 只出十二表某一类别
    python shengcheng.py --zhong 行业对标      # 只出外部某一册
    python shengcheng.py --seed 20260923 --out 输出
产出（默认 ./输出/）：
    演示-预算基础-<种子>.xlsx / 演示-实时经营-<种子>.xlsx
    演示-行业对标-<种子>.xlsx / 演示-经营变更-<种子>.xlsx
"""
import argparse
import sys
from pathlib import Path

import waibu
from banshi import WAI_BIAO
from mingcheng import tihuan_biao
from shuju import ZICHAN_BY_HANG, ShuJu
from xiechu import xie_shu

MU = Path(__file__).resolve().parent
SHI_ER = ('预算基础', '实时经营')
WAI = ('行业对标', '经营变更')


def _hou(seed, hangye=None):
    """文件名后缀：指定行业时带上，便于同种子多行业并存。"""
    return f'{seed}-{hangye}' if hangye else str(seed)


def sheng(seed=20260923, leibie='预算基础', out=None, hangye=None, zhuti=None):
    """生成十二表一本；返回产物路径。"""
    out = Path(out) if out else (MU / '输出')
    out.mkdir(parents=True, exist_ok=True)
    tihuan = tihuan_biao(seed, leibie, hangye=hangye, zhuti=zhuti)
    # 未指定行业时，按生成出的主体名反推行业 → 摊销台账与行业匹配
    hy = hangye or next((k for k in ZICHAN_BY_HANG if k in tihuan['主体一']), None)
    shuju = ShuJu(seed, leibie, hy)
    lu = out / f'演示-{leibie}-{_hou(seed, hangye)}.xlsx'
    return xie_shu(shuju.biao, tihuan, lu, leibie)      # 被占用时返回另存路径


def sheng_wai(seed=20260923, zhong='行业对标', out=None, hangye=None, zhuti=None):
    """生成外部册一本；返回产物路径。"""
    out = Path(out) if out else (MU / '输出')
    out.mkdir(parents=True, exist_ok=True)
    tihuan = tihuan_biao(seed, zhong, hangye=hangye, zhuti=zhuti)
    zhi = (waibu.hangye_biao(seed, tihuan) if zhong == '行业对标'
           else waibu.biangeng_biao(seed, tihuan))
    lu = out / f'演示-{zhong}-{_hou(seed, hangye)}.xlsx'
    return xie_shu(zhi, tihuan, lu, zhong, WAI_BIAO[zhong])


def sheng_si_ce(seed=20260923, out=None, hangye=None, zhuti=None):
    """生成四册；返回路径列表（顺序：十二表两类别 + 外部两册）。"""
    lu = [sheng(seed, b, out, hangye, zhuti) for b in SHI_ER]
    lu += [sheng_wai(seed, b, out, hangye, zhuti) for b in WAI]
    return lu


def main():
    ap = argparse.ArgumentParser(description='演示工作簿生成器（自包含·零公式·纯数值）')
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--leibie', default=None, choices=SHI_ER)
    ap.add_argument('--zhong', default=None, choices=WAI)
    ap.add_argument('--out', default=None)
    ap.add_argument('--hangye', default=None, help='强制行业词（如 智能制造/商贸实业）')
    ap.add_argument('--zhuti', default=None, help='强制主体名（不含"有限公司"也可）')
    a = ap.parse_args()
    if a.leibie:
        lu = [sheng(a.seed, a.leibie, a.out, a.hangye, a.zhuti)]
    elif a.zhong:
        lu = [sheng_wai(a.seed, a.zhong, a.out, a.hangye, a.zhuti)]
    else:
        lu = sheng_si_ce(a.seed, a.out, a.hangye, a.zhuti)
    for p in lu:
        print(f'生成 {p}（{p.stat().st_size} 字节）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
