"""知识点 doctest 守护测试 —— 保证模块头部的使用示例永远可运行、不出错。

背景（用户指令 2026-08-23）：两个算法模块的 docstring 顶部各有一段
"使用示例（知识点速览）"，格式为 doctest（>>> 开头、可执行）。
示例一旦与代码脱节就会误导读者，故纳入常规测试：
每次跑 unittest 自动执行全部 doctest，失败即红。

新模块接入：在下方 TESTED_MODULES 元组里登记模块对象即可
（同时记得在模块 docstring 顶部写示例——这是 algo 开发铁律第 3 条）。
"""

from __future__ import annotations

import doctest
import unittest

import data_ingest      # noqa: E402  被检模块一：数据录入（方案B 步骤 1）
import file_extract     # noqa: E402  被检模块十五：文件文本提取层（步骤 1 前置，PDF/Word 解包）
import loop_decision    # noqa: E402  被检模块：单双环判定（方案B 步骤 4）
import report_parse     # noqa: E402  被检模块十六：报表模板解析层（步骤 1 前置二段，预算报告 → 8 列）
import xishu            # noqa: E402  被检模块十七：判定系数输出（T-32，算法层 → 分析层 M5 的接缝）
import llm_clean        # noqa: E402  被检模块二：LLM 格式归一化前置层（步骤 1 扩展）
import model_api        # noqa: E402  被检模块三：模型 API 调用器（真模型接线/前端密钥输入口）
import moxing_peizhi    # noqa: E402  被检模块四：模型配置管理器（前端改 Key/改参数接口）
import planning_operational  # noqa: E402  被检模块五：规划/执行差异拆分（方案B 步骤 3c）
import rolling_budget   # noqa: E402  被检模块六：滚动预算（方案B 步骤 2）
import variance         # noqa: E402  被检模块七：差异计算（方案B 步骤 3a/3b）
import baogao           # noqa: E402  被检模块十四：报告排版（八单元 Markdown 表格）
import bsc              # noqa: E402  被检模块九：平衡计分卡四维评分（方案B 步骤 5b）
import kanban           # noqa: E402  被检模块十：看板数据接口（步骤 7 计算前置，纯组装）
import kpi              # noqa: E402  被检模块十一：KPI 指标库（步骤 1b，15 项）
import suyuan           # noqa: E402  被检模块十二：变更溯源（步骤 6）
import zhenggai         # noqa: E402  被检模块十三：整改数据底座（步骤 8 计算部分）
import building_blocks  # noqa: E402  被检模块八：积木四模块聚合（方案B 步骤 5a）

#: 被守护的模块清单——新模块写完示例后在这里登记一行
TESTED_MODULES = (data_ingest, llm_clean, loop_decision, model_api,
                  moxing_peizhi, planning_operational, rolling_budget,
                  variance, building_blocks, bsc, kpi, suyuan,
                  zhenggai, kanban, baogao, file_extract, report_parse, xishu)


class TestDocstringDemos(unittest.TestCase):
    """逐模块执行 docstring 中的知识点示例（doctest）。"""

    def test_all_module_demos(self) -> None:
        """所有登记模块的示例：零失败，且确实识别到了示例（非零条）。"""
        for module in TESTED_MODULES:
            with self.subTest(module=module.__name__):
                result = doctest.testmod(module)
                # failed 必须为 0；attempted 为 0 说明示例没被识别，同样算失败
                self.assertEqual(result.failed, 0, f'{module.__name__} 的知识点示例有失败项')
                self.assertGreater(result.attempted, 0, f'{module.__name__} 未识别到任何示例')


if __name__ == '__main__':
    # 支持直接运行：python tests/test_demos.py
    unittest.main()
