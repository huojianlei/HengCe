# 报告组装 —— 计算报告流水线（衡策 1.1.1 第二部分重点交付）

> 落点：`D:\AppProject\开发分支_1.1.1\报告组装\` ｜ 建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）
> 铁律：零 C 盘；1.0.5 树只读引用（algo/kb2/houtai 均不写）；AI 文案不接真模型（铁律⑦）。

## 一、compute_report_pipeline

```
输入   jieguo        yinqing.fenxi() 结果（十五步分析全量）
       wencai_hanshu 逐模块文案函数（模块名, 数据块)→str；默认确定性占位
       zongjie_hanshu 总体解读函数（jieguo)→str；默认确定性占位
       jiansuo_hanshu None=自动懒加载 1.0.5/kb2/query_kb2（只读引用，
                      numpy+onnx 齐备即真检索）；False=关闭检索
输出   输出/计算报告-月度.md + 计算报告-月度.html
```

报告结构（照 1.0.5 fenxi/zhenghe_baogao.py 对应位置口径）：

```
# 计算报告-月度（主体 · 期间）        抬头（单位=分/基点、口径声明）
## 总览                               algo baogao 总览块原文
## 模块一..九 · <模块名>              九个模块章节，每章固定三段：
   **数据表**     algo baogao 对应单元/附表块原文（忠实计算输出零改写）
   **分析内容**   M5 逐模块分析——注入文案函数；默认确定性占位
                  （注明"由 DSH 宿主 agent 回填"，数字全部照抄数据表）
   **依据条例（收入类/成本类）**        kb2 真检索各 4 片：出处行
                  《管理会计应用指引第N号——名》第M条（定位 指引-条[-片]）
## AI 分析解读                        总体 LLM 解读（文末唯一章节）：
   ### 总体解读     系数包实算数字（完成率/预警/单双环/BSC/整改计数）
   ### 逐条整改建议 整改清单逐条（占位标注）
```

## 二、幂等纪律（对齐 pipeline_m5.py:102-114）

- `compute_report_pipeline` 同输入整链重建，**逐字节一致**（实测 sha256 相同）；
- `zhuijie_jiedu(md路径, 解读段)` 对已生成报告追加解读：**已含『AI 分析解读』
  即跳过**（返回 False），不重复贴——与 pipeline_m5 第 109 行判定同款。

## 三、注入接口（DSH 宿主回填路径）

```python
# 真实文案由 DSH agent 对话产出后注入重跑（md/html 同步重建）：
compute_report_pipeline(jieguo, wencai_hanshu=宿主函数, zongjie_hanshu=宿主函数)
# 检索运行时缺失时（无 numpy/onnx）：依据条例自动落
# "— 未检索到直接依据（检索运行时未注入）。"——如实占位，不臆造条文。
```

## 四、依赖与样式

- 依赖：仅标准库 + 复用（baogao/rolling_budget/yinqing/excel_generate 只读 import；
  kb2 经 sys.path 只读引用，仅检索时加载 numpy/onnx）；
- HTML：内置极简样式（标题/表格/引用/分隔线）——演示生成器目录实测无既有
  报告样式资产（仅 xlsx 工具），故本包自带零依赖 md→HTML 转换器。

## 五、验收（verify_v11.py 阶段④，2026-10-12 实测）

- md 101,126 字符 / kb2 出处 72 条（真检索）；模块章节 9/9 各含三段；
- AI 分析解读章节在位且唯一；占位文案含"确定性占位/DSH 宿主 agent 回填"标注；
- 幂等复跑逐字节一致；追加解读跳过；HTML 同步（165,377 字符，含表格）。
