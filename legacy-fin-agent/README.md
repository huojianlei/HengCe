# FinAgent dsh 插件 —— 智能预算差异分析与风险预警系统（方案B 正式版）

> 把基准 Python 程序（`D:\AppProject\algo\`，206 测试全绿）转写为 dsh（DeepSeek Harness）
> 树外插件的**正式版交付**。只加插件、不改内核（ADR-01）；
> 冲突口径以架构图正式版v1（2026-09-05）与新拍板为准，全部裁决记录见 `docs\转写设计裁决.md`。

## 目录结构（正式版内容，不含测试）

```
fin-agent\
├── index.ts                    # 插件入口：注册 18 个工具 + 岗位守则 persona
├── tools\                      # 工具层（八步主线）
│   ├── step1-ingest.ts         #   步骤1 录入链（5件：提取/报表解析/录入/归一化提示词/幻觉自检）
│   ├── step2-3-compute.ts      #   步骤2/3（3件：滚动预算/多维差异/Holmes拆分）
│   ├── step4-6-analyze.ts      #   步骤4/5/6（5件：语义归类/单双环判定/积木/BSC/溯源）
│   └── step7-8-output.ts       #   步骤7/8（5件：KPI/整改/看板/报告/KB检索提示词）
├── src\                        # 计算核心（17 个纯函数模块，零 dsh 依赖，可独立单测）
│   ├── int-math.ts             #   BigInt 半进位整数运算公共库（金额分×基点中间量防 2^53 溢出）
│   ├── data-ingest.ts          #   ← data_ingest.py      步骤1 清洗归档
│   ├── file-extract.ts         #   ← file_extract.py     word/PDF/csv/txt 文本提取
│   ├── report-parse.ts         #   ← report_parse.py     中式预算报告解析
│   ├── llm-clean.ts            #   ← llm_clean.py        归一化分流/提示词/幻觉校验
│   ├── rolling-budget.ts       #   ← rolling_budget.py   步骤2 滚动预算（链法①+口径A）
│   ├── variance.ts             #   ← variance.py         步骤3 差异计算（黄1500/红3000）
│   ├── planning-split.ts       #   ← planning_operational.py  步骤3c 规划/执行拆分
│   ├── loop-decision.ts        #   ← loop_decision.py    步骤4 单双环五情形（噪声门2500）
│   ├── building-blocks.ts      #   ← building_blocks.py  步骤5a 积木四模块
│   ├── bsc.ts                  #   ← bsc.py              步骤5b 平衡计分卡（40/30/20/10）
│   ├── kpi.ts                  #   ← kpi.py              15 项 KPI 指标库
│   ├── suyuan.ts               #   ← suyuan.py           步骤6 经营变更溯源
│   ├── zhenggai.ts             #   ← zhenggai.py         步骤8 整改数据底座
│   ├── kanban.ts               #   ← kanban.py           步骤7 看板数据接口
│   ├── xishu.ts                #   ← xishu.py            KB 检索提示词包（≤8条去重）
│   └── baogao.ts               #   ← baogao.py           步骤8 12块报告组装+md渲染
├── cordis.yml                  # 自足挂载单（--config 直挂）
├── fin-agent.patch.yml         # --patch overlay（挂任何 profile 之上）
├── fin-agent-smoke.patch.yml   # 冒烟专用（挂插件+关会话压缩，验证 persona/工具进请求）
├── scripts\mkjunction.cjs      # 重建 @deepseek-ai/{dsh-tools,cordis} junction
├── docs\转写设计裁决.md         # 16 项冲突裁决 + 移植范围 + 修正项
└── package.json                # type:module 零依赖
```

**测试不在本目录**：验证区在 `D:\AppProject\fin-agent-verify\`（19 个测试文件，
206 用例全绿；期望值与 Python 测试逐字一致），跑法：`cd D:\AppProject\fin-agent-verify && node --test`。

## 挂载与运行（已实测）

前置：`node scripts\mkjunction.cjs`（重建 node_modules junction，指到 `D:\AppProject\harness`）。

```sh
# 方式一：--patch overlay（推荐，挂任何 profile）
cd D:\AppProject\harness
DSH_HOME=D:\AppProject\dsh-home node --import tsx apps/cli/src/bin.ts \
  --profile headless --patch D:\AppProject\plugins\fin-agent\fin-agent.patch.yml "任务文本"

# 方式二：自足挂载单
node --import tsx packages/examples/acp-demo/src/bin.ts --config D:/AppProject/plugins/fin-agent/cordis.yml

# 冒烟（不用真模型）：先起 mock LLM 再跑，验证 persona+18 工具 schema 进请求
node --import tsx packages/test-support/llm-mock-server/src/bin.ts \
  --sequence success --success-text ok --repeat-last --port 8322
#   然后 DEEPSEEK_BASE_URL=http://127.0.0.1:8322/v1 DEEPSEEK_API_KEY=sk-x 按方式一跑
```

真实使用只需设置 `DEEPSEEK_API_KEY`（dsh 凭据链自动解析，密钥不落盘）。

## 18 个工具（AI 点菜 → 柜台真算）

| 步骤 | 工具 | 职责 |
|---|---|---|
| 1 | fin_jiequ_wenben | word/PDF/csv/txt → 文本（docx 表转 CSV 行；扫描件报错引导换文件） |
| 1 | fin_baobiao_jiexi | 中式预算报告 → 标准 8 列 CSV（离线确定零模型） |
| 1 | fin_daoru_csv | 8 列 CSV → 四类归档（元→分、%→基点；拒绝清单交人工） |
| 1 | fin_guiyihua_tishi | 脏表格归一化：直解尝试+归一化提示词（模型活儿由外层智能体干） |
| 1 | fin_huanjue_jiaoyan | 幻觉防线：输出数字必须原文出现过（零容忍整批拒绝） |
| 2 | fin_gundong | 滚动预算：全额替换+链法①逐期舍入；口径A行业修正（≥50bps仅季度） |
| 3 | fin_chayi | 三重对比差异：黄15%/红30%默认，科目自定义档，F/A，防双计 |
| 3c | fin_chaifen | Holmes 拆分：规划/执行总差异+四细分+残差，恒等式自检 |
| 4前 | fin_yuyi_guilei | LLM 语义归类站点（结构变动/执行偏差/无法判断枚举固化） |
| 4 | fin_panduan | 单双环五情形（噪声门25%默认可注入）；双环/混合必须人工审批 |
| 5a | fin_jimu | 积木四模块聚合（人力并入成本）；高亮=A模块最大净差 |
| 5b | fin_bsc | 平衡计分卡：达成率×权重不封顶，五档评级，权重合计=100 |
| 6 | fin_suyuan | 变更溯源：影响率分母=原始预算，偏好×方向，TOP3 |
| 1b | fin_kpi | 15 项 KPI（缺数→null 交人工，绝不臆造） |
| 8 | fin_zhenggai | 整改清单：修订案(高·审批)/行为整改(中)/强制整改(高)/关注(中) |
| 7 | fin_kanban | 看板 JSON 数据源（八路上游纯组装零重算） |
| 8 | fin_baogao | 12 块报告 → Markdown（缺料块占位；PDF/Word 由外层转换） |
| KB | fin_xishu | 4 个 KB 站点统一出口：检索词包 ≤8 条去重（检索执行对接 kb2 为后续） |

## 权威口径（常量可配置）

| 参数 | 值 | 出处 |
|---|---|---|
| 预警黄/红阈 | 1500/3000 bps | 2026-09-03 拍板 |
| 单双环噪声门/显著阈 | 2500/2500 bps（可注入回退） | 2026-09-04 拍板 |
| BSC 权重 | 40/30/20/10（自定义合计=100） | 架构图 + T-05 |
| 积木模块 | 四模块（人力并入成本） | T-21 |
| 滚动预算 | 全额替换+链法①；口径A默认（≥50bps 启用，仅季度） | 2026-09-03 拍板 |
| 报告 | md+JSON | 架构图 PDF+JSON 的零依赖实现 |

> 建立：2026-09-05 ｜ Agent：ZCode（GLM-5.3）｜ Python 权威实现：D:\AppProject\algo（只读）
