# 演示数据模块（仅演示版/实验变体）

`entry.mjs` 注入「演示数据 · 一键全流程」面板，通过主界面的通用输入/分析接口（`app.mjs` 导出的 `setInput`/`runAnalysis`）操作，不参与正式计算逻辑，无特权调用。`demo.json` 是固定演示输入（含 BSC/KPI/拆分/变更/溯源全部专业参数），`reference.csv` 是同一份记录的八列标准 CSV。

**一键演示**：载入 demo.json → 自动运行分析 → 跳转分析总览。演示效果固定：直接材料红色预警（+36.8%）、营业收入/销售费用黄色预警、直接材料结构性双环判定（需人工审批）、销售费用单环、BSC 90 分优秀、KPI 15 项全出值、双维溯源正向（客户满意度）与负向（交付周期、毛利率）双向展示、整改清单 6 项，全程零报错。

**填入演示 CSV**：把演示 CSV 填入导入区并勾选"保留专业参数"，引导演示者点击"解析并替换当前数据"，展示真实的服务端文件解析校验通道。

数据唯一源头：`desktop/scripts/make-demo.mjs`（无随机性；改动后运行一次重新生成 demo.json + reference.csv）。模拟数据均明确标注（`simulation=true`、来源"演示数据"）。

## 构建隔离

正式版为构建默认值：`packaging/build-all.ps1 -Flavor Production`。演示版（实验变体）需显式指定 `-Flavor Experimental`。

`packaging/prepare-desktop.mjs` 按资产清单（`desktop/assets.json`）复制文件。正式版剔除 experimental/ 目录全部文件、从 HTML 删除演示模块入口，生成仅含正式资源的清单；后端只服务该清单，不存在运行时开关。正式安装器额外移除旧安装中的实验目录和旧 demo.json。

演示版安装标识/目录/数据目录为独立的 FinAgent-Experimental；正式版使用 FinAgent，与旧正式安装的用户数据兼容。

验证：`node --test desktop/tests/*.test.mjs`，`node desktop/scripts/experimental-check.mjs`（源工程），`node desktop/scripts/production-check.mjs`（正式产物，检查隔离与真实 CSV 导入分析）。
