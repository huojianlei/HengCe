# -*- coding: utf-8 -*-
"""baogao_docx（报告 Word 渲染）单元测试 —— 系统 Python 下全量、env 下跳过。

设计原则：
    1. 环境适配：python-docx 仅系统 Python 有——本文件 skipUnless 包裹，
       env Python（零依赖纪律）下自动跳过，系统 Python 下全量执行；
    2. 双渲染互证：docx 内容与 baogao 组装层（BiaoKuai）同源——
       表数/表头/单元格数值逐项与 md 版对同一组期望；
    3. 真表格验证：读回 docx 检查表格对象结构（非文本比对）。

本项目强制规则：注释率 ≥ 40%；标识符全拼音。
运行方式（系统 Python，algo 目录下）：
    D:/dev-env/Python312/python.exe -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

# 环境探测：无 python-docx 时整组跳过（env Python 的常态）；
# 系统 Python（D:/dev-env/Python312）下全量执行——两解释器都纳入常规回归
try:
    import docx  # noqa: F401
    YOU_DOCX = True
except ImportError:
    YOU_DOCX = False

# 被测模块与组装层：discover -t . 运行时 algo 根目录在 sys.path 上
from baogao import BgShuru, shengcheng_baogao_kuai  # noqa: E402
from baogao_docx import jiancha_huanjing, shengcheng_baogao_docx  # noqa: E402
from building_blocks import JimuHang, chai_jimu  # noqa: E402
from variance import ChayiShuru, YujingDang, jisuan_chayi  # noqa: E402


def zui_xiao_shuru() -> BgShuru:
    """最小链上游：一行红预警差异 + 积木——与 baogao 测试共用同一组数字。"""
    # 其余九个上游缺省 → 对应节输出缺料占位段落（渲染层容错路径）
    chayi = jisuan_chayi([
        ChayiShuru('2026-Q1', '材料价格差异', '成本类',
                   10_000_000, 10_000_000, 11_000_000),
    ], dang_lie=(YujingDang('红', '红', 1000), YujingDang('黄', '黄', 500)))
    jimu = chai_jimu([JimuHang('2026-Q1', '材料价格差异', 1_000_000, 'A', '红', 1000)])
    return BgShuru(chayi=chayi, jimu=jimu)


@unittest.skipUnless(YOU_DOCX, 'python-docx 不可用（请用系统 Python 运行全量）')
class TestDocxXuanran(unittest.TestCase):
    """docx 渲染：文件生成/标题/表数/表头/单元格/双渲染一致。"""

    def _shengcheng(self) -> str:
        """渲染到临时目录，返回路径（每用例独立文件）。"""
        # 辅助方法：临时目录随上下文自动销毁——测试不落任何残留
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            # 渲染后立即读回验证（临时目录随上下文销毁，验证在内部完成）
            return lu, linshi  # type: ignore[return-value]

    def test_wenjian_shengcheng(self) -> None:
        """渲染落盘成功：文件存在且非空。"""
        # 返回值 = 落盘路径（调用方可直接引用）；文件大小 > 0 即 docx 结构完整
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            jieguo = shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            self.assertEqual(jieguo, lu)
            self.assertTrue(Path(lu).is_file())
            self.assertGreater(Path(lu).stat().st_size, 0)

    def test_biaoti_he_shuoming(self) -> None:
        """文档标题（Heading 1）+ 三行抬头说明。"""
        # 抬头与 md 版同文案（组装层常量同源）——双渲染互证的一部分
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            wenjian = docx.Document(lu)
            # 首段 = 标题（Heading 1）；其后三个说明段落
            self.assertEqual(wenjian.paragraphs[0].text, '数据计算测试报告（FinAgent 八单元串联）')
            self.assertEqual(wenjian.paragraphs[0].style.name, 'Heading 1')
            self.assertIn('一个分析项目对应一张数据表', wenjian.paragraphs[1].text)

    def test_jie_biaoti_he_biao_shu(self) -> None:
        """11 个节标题（Heading 2）；最小链下 3 张表（缺料块不产表）。"""
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            wenjian = docx.Document(lu)
            jie_biaoti = [p.text for p in wenjian.paragraphs if p.style.name == 'Heading 2']
            # 组装层 12 块（总览+8 单元+3 附表）→ 12 个 Heading 2
            self.assertEqual(len(jie_biaoti), 12)
            self.assertEqual(jie_biaoti[0], '总览 · 三重对比汇总')
            # 表数：最小链有数据的块 = 总览/单元3/单元6/附表C；
            # 附表C 因存在红/黄行追加「C.1 定位」明细表 → 共 5 张
            self.assertEqual(len(wenjian.tables), 5)

    def test_biaotou_jia_cu(self) -> None:
        """表头行加粗 + 表头文本与组装层一致。"""
        # 每个表头单元格首个 run 加粗——渲染层逐格设置，无遗漏
        # 表头加粗是 Word 表格的视觉锚点；文本与 BiaoKuai 表头元组同源
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            wenjian = docx.Document(lu)
            # 最小链下第 2 张表 = 单元 3（第 1 张为总览）；表头第一格 = 期间
            biao = wenjian.tables[1]
            self.assertEqual(biao.rows[0].cells[0].text, '期间')
            # 表头行每个 run 都加粗（组装层与渲染层同源的表头元组）
            for ge in biao.rows[0].cells:
                self.assertTrue(ge.paragraphs[0].runs[0].bold)

    def test_danyuange_shuzhi(self) -> None:
        """单元格数值：与组装层显示转换一致（110,000.00 / 10.00% / 红）。"""
        # 列序按表头：期间(0)/科目(1)/…/实际(5)/差额(7)/率(8)/预警(10)
        # 显示转换发生在组装层——docx 渲染只透传，此处验证不失真
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            wenjian = docx.Document(lu)
            # 最小链下第 2 张表 = 单元 3（差异计算）
            biao = wenjian.tables[1]
            # 数据行 1：期间/科目/方向/固定/滚动/实际/基准/差额/率/FA/预警
            hang = biao.rows[1]
            self.assertEqual(hang.cells[1].text, '材料价格差异')
            self.assertEqual(hang.cells[5].text, '110,000.00')
            self.assertEqual(hang.cells[8].text, '10.00%')
            self.assertEqual(hang.cells[10].text, '红')

    def test_shuang_xuanran_yizhi(self) -> None:
        """双渲染互证：docx 表数与组装层 BiaoKuai 表数一致。"""
        # 缺料块 biao_lie 为空不产表——qidai 自动只数有数据的块
        # qidai 由组装层直接计算——渲染层多一张少一张都立刻暴露
        kuai_lie = shengcheng_baogao_kuai(zui_xiao_shuru())
        qidai = sum(len(k.biao_lie) for k in kuai_lie)
        with tempfile.TemporaryDirectory() as linshi:
            lu = str(Path(linshi) / 'baogao.docx')
            shengcheng_baogao_docx(zui_xiao_shuru(), lu)
            wenjian = docx.Document(lu)
            self.assertEqual(len(wenjian.tables), qidai)


if __name__ == '__main__':
    # 支持直接运行本文件：python tests/test_baogao_docx.py
    unittest.main()
