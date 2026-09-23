# -*- coding: utf-8 -*-
r"""报告 Word 渲染 —— 数据计算测试报告的 .docx 输出（真 Word 表格）。

命名规范（2026-08-23 用户指令）：标识符一律无声调拼音；文件名保持英文。

口径依据（权威文件，修改本模块前必读）：
    docs/01-需求说明.md v2.0 §3 FR-14（报告一键导出——Word 输出，[046] 用户拍板）
    docs/11-算法计算层说明.md §4（端到端手册：docx 为最终交付形态）
    TODO.md T-28（计算层/AI 层拆分——本模块仍是计算层：纯确定性排版，
        零自然语言文案，与 baogao.py 组装层共用同一份 BiaoKuai 数据）

依赖说明（重要）：
    python-docx 仅系统 Python（D:/dev-env/Python312）已装；项目 venv
    （env\，零第三方依赖纪律）没有。本模块在【函数内】懒加载 docx——
    模块级 import 不触雷，env Python 下导入本模块仍安全（调用时才报
    ImportError 并给出提示）。项目零依赖纪律指算法内核；本输出适配器
    沿用教材 docx 管线先例（系统 Python + python-docx，见 HANDOFF §6）。

用法（系统 Python 下运行端到端即产出 Word）：
    D:/dev-env/Python312/python.exe examples/quanliucheng.py
    → fixtures\jisuan_baogao.docx（八单元各一张 Word 表格 + 三附表）

渲染结构（与 md 渲染层逐节一致——双渲染互证）：
    文档标题（Heading 1）+ 抬头说明三行（普通段落）
    + 每单元：节标题（Heading 2）+ 真表格（表头行加粗、Table Grid 边框）
      + 小节标题（Heading 3，如有）
    + 节尾注记（缺料占位 / 附表 B 合计行）为普通段落。

不适用 doctest 守护的原因：渲染需要 python-docx（env Python 下不可用），
故本模块不登记 tests\test_demos.py；功能验证由 tests\test_baogao_docx.py
承担（skipUnless(python-docx 可用)——env 下自动跳过，系统 Python 下全量）。

命名对照表（拼音标识符 → 中文含义）：
    jiancha_huanjing          环境自检（python-docx 是否可用）
    shengcheng_baogao_docx    渲染落盘（主函数：返回 docx 路径）
    shuchu_lujing             输出路径（str；父目录不存在时自动创建）

与上下游的关系：
    上游：baogao.shengcheng_baogao_kuai（组装层——与 md 渲染同源数据）；
    下游：examples/quanliucheng.py [14] 阶段落盘 fixtures/jisuan_baogao.docx。

建立：2026-08-23 ｜ Agent：DeepSeek（DeepSeek Harness 会话模型）
"""

from __future__ import annotations

from pathlib import Path

# 只引入组装层（标准库可导入）；docx 在函数内懒加载——见模块头依赖说明
from baogao import BgShuru, shengcheng_baogao_kuai  # noqa: E402


def jiancha_huanjing() -> bool:
    """环境自检：python-docx 是否可用（False → 用系统 Python 运行）。"""
    try:
        import docx  # noqa: F401  仅探测，不持有
        return True
    except ImportError:
        return False


def shengcheng_baogao_docx(shuru: BgShuru, shuchu_lujing: str) -> str:
    """渲染数据计算测试报告为 .docx 并落盘（真 Word 表格；确定性排版）。

    参数：
        shuru —— BgShuru（十一个上游结果，均可缺省 None）；
        shuchu_lujing —— 输出路径（.docx；父目录不存在时自动创建）。

    返回：落盘路径（str）。

    说明：与 baogao.shengcheng_baogao_md 共用同一份组装数据（BiaoKuai
    列表）——两份产物内容必然一致（双渲染互证）。python-docx 不可用
    时抛 ImportError 并附运行提示。
    """
    # 懒加载：env Python 下只有真正调用到这里才会报错（模块导入安全）
    try:
        import docx
    except ImportError as e:
        raise ImportError(
            '缺少 python-docx——请用系统 Python 运行：'
            'D:/dev-env/Python312/python.exe examples/quanliucheng.py'
        ) from e

    wenjian = docx.Document()
    # ---- 文档标题与抬头说明（普通段落，无自然语言文案）----
    wenjian.add_heading('数据计算测试报告（FinAgent 八单元串联）', level=1)
    for shuoming in (
        '说明：输入数据依次经过八个计算单元处理；一个分析项目对应一张数据表。',
        '显示口径：金额 = 元（两位小数、千分位）；比率 = 百分比；周转率 = 次。',
        '计算口径：内部全程整数分 / 基点；缺数显示 "—"；上游缺料显示 "（缺料）"。',
    ):
        wenjian.add_paragraph(shuoming)

    # ---- 逐块渲染：节标题（Heading 2）+ 真表格（表头加粗 + 边框）----
    kuai_lie = shengcheng_baogao_kuai(shuru)
    for kuai in kuai_lie:
        wenjian.add_heading(kuai.biaoti, level=2)
        if not kuai.biao_lie:
            # 缺料占位：普通段落（与 md 渲染层的"（缺料）"行对应）
            wenjian.add_paragraph(kuai.zhu)
            continue
        for zi_biaoti, toubu, hang_lie in kuai.biao_lie:
            if zi_biaoti is not None:
                wenjian.add_heading(zi_biaoti, level=3)
            # Table Grid 样式带全边框；行数 = 表头 1 + 数据行
            biao = wenjian.add_table(rows=1 + len(hang_lie), cols=len(toubu))
            biao.style = 'Table Grid'
            # 表头行加粗（Word 表格的视觉锚点）
            for lie, mingcheng in enumerate(toubu):
                biao.rows[0].cells[lie].paragraphs[0].add_run(mingcheng).bold = True
            # 数据行逐格填充（组装层已完成显示转换，此处原样写入）
            for hang_xuhao, hang in enumerate(hang_lie, start=1):
                for lie, zhi in enumerate(hang):
                    biao.rows[hang_xuhao].cells[lie].text = zhi
        if kuai.zhu:
            # 节尾注记（附表 B 合计行等；缺料块不经过这里）
            wenjian.add_paragraph(kuai.zhu)

    # ---- 落盘（父目录不存在时自动创建）----
    lu = Path(shuchu_lujing)
    lu.parent.mkdir(parents=True, exist_ok=True)
    wenjian.save(str(lu))
    return str(lu)
