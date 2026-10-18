# -*- coding: utf-8 -*-
"""衡策演示生成器 v2 入口：一次生成四类演示 Excel（v1.2 企业主体）。

用法：
    python gen_four_books.py [--seed 20260923] [--scenario 基础情景]
                             [--year 2027] [--grain 月度] [--closed-month 6]
                             [--entity-code ENT-2027] [--scenario-code S-BASE]
                             [--out 输出]

主体名默认由固定种子从字号池+行业词生成（企业化，禁"衡策/中学"字样）；
也可 --entity 显式指定。产出（输出目录默认 ./输出）：
    演示-预算基础-<主体>-<种子>.xlsx
    演示-实时经营-<主体>-<种子>.xlsx
    演示-行业对标-<主体>-<种子>.xlsx
    演示-经营变更-<主体>-<种子>.xlsx

零 C 盘；底稿与 1.0.5 树只读；同参数逐字节复现。
"""
import argparse
from pathlib import Path

import external_book
import twelve_book
from demo_model import qiye_ming

ROOT = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description='四类演示 Excel 确定性生成器')
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--entity', default=None,
                    help='主体名（缺省=固定种子从字号池+行业词生成企业名）')
    ap.add_argument('--scenario', default='基础情景')
    ap.add_argument('--entity-code', default='ENT-2027')
    ap.add_argument('--scenario-code', default='S-BASE')
    ap.add_argument('--year', type=int, default=2027)
    ap.add_argument('--grain', choices=('月度', '季度'), default='月度')
    ap.add_argument('--closed-month', type=int, default=6)
    ap.add_argument('--out', default=str(ROOT / '输出'))
    args = ap.parse_args()

    entity = args.entity or qiye_ming(args.seed)  # 企业名：种子确定性生成
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    common = dict(seed=args.seed, entity=entity, scenario=args.scenario,
                  entity_code=args.entity_code, scenario_code=args.scenario_code,
                  year=args.year, grain=args.grain)
    tag = f'{entity}-{args.seed}'

    made = []
    for category in ('预算基础', '实时经营'):
        data, _ = twelve_book.generate_twelve(
            category, seed=args.seed, entity=entity, scenario=args.scenario,
            entity_code=args.entity_code, scenario_code=args.scenario_code,
            year=args.year, grain=args.grain, closed_month=args.closed_month)  # entity=换算名（禁 None 入簿）
        path = out / f'演示-{category}-{tag}.xlsx'
        path.write_bytes(data)
        made.append(path)

    data = external_book.generate_industry(**common)
    path = out / f'演示-行业对标-{tag}.xlsx'
    path.write_bytes(data)
    made.append(path)

    data = external_book.generate_changes_file(**common)
    path = out / f'演示-经营变更-{tag}.xlsx'
    path.write_bytes(data)
    made.append(path)

    for p in made:
        print(f'生成 {p} ({p.stat().st_size} 字节)')
    return made


if __name__ == '__main__':
    main()
