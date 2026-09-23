# -*- coding: utf-8 -*-
r"""注释率检查器 —— 强制执行项目规则「注释不得少于 40%」。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音
（zhushilv 注释率 / xiaxian 下限 / zijian 自检 / zhukong 主控……）。

规则（用户指令 2026-08-22）：
    所有 algo/ 下的 Python 模块，注释行占比不得低于 40%。

统计口径（本检查器的定义）：
    - 「注释行」= # 开头的行（tokenize COMMENT 命中）+ docstring 覆盖的行；
    - 「总行」  = 非空行（空行不计入分母，也不计入分子）；
    - 占比     = 注释行 / 非空总行。

用法（algo 目录下运行，可一次传多个文件）：
    python tools/check_comments.py rolling_budget.py tests/test_rolling_budget.py

退出码：全部达标 0；任一不达标 1（可供 CI/后续钩子使用）。

自检：ZIJIAN 开启时，检查器会把自己追加进被检清单——
    规则面前人人平等，工具自身不豁免。
"""

from __future__ import annotations

import ast
import sys
import tokenize
from pathlib import Path

#: 项目规则：注释占比下限（0.40 = 40%）
ZHUSHILV_XIAXIAN = 0.40

#: 是否把检查器自身也纳入被检清单（去重后追加）
ZIJIAN = True


def _wendangchuan_hang(shu: ast.Module) -> set[int]:
    """收集文件中所有 docstring（文档串）覆盖的行号集合。

    实现：遍历全部语法树节点，取 模块/类/函数/异步函数 的
    第一个语句若是字符串常量（即文档串），登记其行号范围。
    覆盖异步函数：同样可能有文档串，不可漏计。
    """
    hanghao_jihe: set[int] = set()
    for jiedian in ast.walk(shu):
        if isinstance(jiedian, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            zhengwen = jiedian.body
            if zhengwen and isinstance(zhengwen[0], ast.Expr) and isinstance(zhengwen[0].value, ast.Constant):
                if isinstance(zhengwen[0].value.value, str):  # 仅统计字符串字面量
                    kaishi, jieshu = zhengwen[0].lineno, zhengwen[0].end_lineno
                    hanghao_jihe.update(range(kaishi, jieshu + 1))
    return hanghao_jihe


def zhushilv(lujing: Path) -> tuple[float, int, int]:
    """计算单个文件的注释占比，返回 (占比, 注释行数, 非空总行数)。

    附带效果：语法解析会抛出语法错误——检查器顺带是语法门禁。
    """
    yuanma = lujing.read_text(encoding='utf-8')
    shu = ast.parse(yuanma)

    # ① 文档串行号集合
    zhushi_hanghao: set[int] = _wendangchuan_hang(shu)

    # ② # 注释行号集合（tokenize 精确定位物理行）
    with lujing.open('rb') as wenjian:
        for duan in tokenize.tokenize(wenjian.readline):
            if duan.type == tokenize.COMMENT:
                zhushi_hanghao.add(duan.start[0])

    # ③ 分母：非空物理行（空行两侧都不计）
    wuli_hang = yuanma.splitlines()
    feikong = sum(1 for yuan in wuli_hang if yuan.strip())

    # ④ 分子：注释行中"确有内容"的行（防御性：行号必须在文件范围内，
    #    且该物理行确有字符——防止极端 token 位置越界）
    zhushi_shu = sum(
        1 for hao in zhushi_hanghao if hao <= len(wuli_hang) and wuli_hang[hao - 1].strip()
    )
    zhanbi = zhushi_shu / feikong if feikong else 1.0  # 空文件视为达标
    return zhanbi, zhushi_shu, feikong


def zhukong(canshu: list[str]) -> int:
    """入口：逐文件统计并打印报告；任一低于下限则退出码 1。"""
    if not canshu:
        print('用法：python tools/check_comments.py <文件...>')
        return 1

    # 路径解析去重（防止显式传入 + 自检追加 导致重复统计）
    mubiao: list[Path] = []
    yijian: set[Path] = set()
    for mingzi in canshu:
        jiexi = Path(mingzi).resolve()
        if jiexi not in yijian:
            yijian.add(jiexi)
            mubiao.append(Path(mingzi))

    you_shibai = False  # 任一文件未达标则置位
    for lujing in mubiao:
        # 逐文件统计并即时打印——长清单运行时可见进度，失败文件一眼可见
        zhanbi, zhushi, zong = zhushilv(lujing)
        biaoji = 'PASS' if zhanbi >= ZHUSHILV_XIAXIAN else 'FAIL'
        if zhanbi < ZHUSHILV_XIAXIAN:
            you_shibai = True
        print(f'{biaoji}  {lujing.name:<32} 注释率 {zhanbi:6.1%}  ({zhushi}/{zong} 行)')

    if you_shibai:
        print(f'\n存在未达 {ZHUSHILV_XIAXIAN:.0%} 注释率的文件，请补注释后重试。')
        return 1
    # 全部通过时的收尾提示（含下限复述，便于在日志中留痕）
    print(f'\n全部文件注释率达标（≥ {ZHUSHILV_XIAXIAN:.0%}）。')
    return 0


if __name__ == '__main__':
    # 命令行目标 + 自检追加（zhukong 内部负责去重，避免重复统计同一文件）
    canshu = sys.argv[1:]
    if ZIJIAN and canshu:
        canshu.append(str(Path(__file__).resolve()))
    sys.exit(zhukong(canshu))
