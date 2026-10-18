# 导览 · 后端核心 Python 版（houtai_hexin）

> 交付目录：`D:\AppProject\开发分支_1.1.1\houtai_hexin_python`
> 移植对象：衡策 1.0.7 桌面版后端核心（`D:\AppProject\开发分支_1.0.5\desktop` 的编排层与 AI 边界层）
> 算法权威：`D:\AppProject\开发分支_1.0.5\algo`（Python，一律 import 复用，本包零重写）
> 建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）
> 铁律：零 C 盘；algo 与 desktop、plugins/fin-agent 只读；金额=整数分、比率=整数基点；
> 标识符全拼音；注释率 ≥40%（algo 检查器实测全达标，见文末）；零第三方依赖。

---

## 一、这个包是什么、不是什么

**是**：把 1.0.7 桌面版里只有 TypeScript 实现的两块后端核心——
`engine.mjs` 的**编排层**（analyze 输入校验链、逐科目编排、修订链式重算、
组织单元识别/汇总、整改计数回算）与 `ai-boundary.mjs` 的**白名单 DTO 构造器**——
整理成可逐行审阅的 Python，供作者对照审阅。

**不是**：不是重写。全部计算（滚动预算/差异/拆分/判定/积木/BSC/KPI/溯源/
整改/看板/系数/导入清洗/报表解析）都通过 sys.path 引导直接 import `algo/`
的权威模块；`server.mjs` 的 HTTP 壳层（路由/会话/文件落盘/PDF 导出）不在范围。

**验证状态**（2026-10-11 本机实测）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 本包自测 | `python -B -m unittest discover`（包根目录） | **65 用例全绿** |
| 注释率 | algo 的 `tools/check_comments.py` 检本包全部 9 个文件 | **全部 ≥40%** |
| algo 权威基线 | `python -m unittest discover -s tests -t .`（algo 目录，dev-env Python 3.12.2） | **275 用例全绿** |
| 桌面 TS 基线 | `node --test tests/*.test.mjs`（desktop 目录，node v22.22.2） | **50 用例全绿** |
| 转写验证基线 | `node --test tests/*.test.ts`（fin-agent-verify，16 份测试对应 algo 期望值） | **216 用例全绿** |
| 两引擎 A/B 对照 | 同一输入分别喂 `engine.mjs analyze()` 与本包 `fenxi()`（详见第五节） | **关键数值逐项一致** |

---

## 二、阅读顺序（建议 60 分钟通读）

1. **`houtai_hexin.py`（包入口，55 行）**——先看 sys.path 引导与
   `analyze_subjects()` 批次总入口，理解"一份工作簿一个主体 → 逐主体分析 →
   组织汇总"的桌面同序编排（对应 server.mjs `/api/analyze-batch`）。
2. **`yinqing.py`（编排层，约 800 行）**——按函数顺序读，与 engine.mjs 行号
   一一对应（每个 docstring 都标了来源行号）：
   `zhengshu`(L17-20) → `daoru_biaoge`(L21-30) → `kemu_guilei`(L31-36) →
   `_dangwei`(L37-41) → **`fenxi`(L42-179，主链十五步①-⑮)** →
   `zuzhi_shibie`(L180-188) → `zuzhi_huizong`(L189-251) → `chongji`(L252-256)。
   读 `fenxi` 时对照 engine.mjs 同段落最省力——步骤编号、校验次序、报错文案完全同序。
3. **`ai_bianjie.py`（AI 边界层，约 160 行）**——对照 ai-boundary.mjs 全文
   （39 行）读：权限门 → 白名单标量过滤器 → 差异行/模块/组织三段白名单化。
4. **`tests/gongju.py`（夹具）**——标准输入怎么造、手算口径是什么。
5. **`tests/test_yinqing.py` / `test_zuzhi.py` / `test_ai_bianjie.py`**——
   期望值全部按 engine.mjs 手工推演写死；改任何一侧行为/文案即红。
6. **`tests/test_maoyan.py`**——algo 关键模块冒烟（证明引导真实命中 algo 原件）。

---

## 三、TS ↔ Python 全量模块对照表

### 3.1 桌面运行时三件套

| TS（desktop/） | Python 落点 | 说明 |
|---|---|---|
| `engine.mjs` L17-20 `integer` | **新写** `yinqing.zhengshu` | 整数域校验；文案逐字 |
| `engine.mjs` L21-30 `parseText` | **新写** `yinqing.daoru_biaoge` | 复用 algo `daoru_csv`+`shitu_jiexi`；1.0.7 桌面仅调试口可达 |
| `engine.mjs` L31-36 `subjects` | **新写** `yinqing.kemu_guilei` | 复用 algo `building_blocks.yingshe_mokuai` |
| `engine.mjs` L37-41 `tiers` | **新写** `yinqing._dangwei` | 校验后转 algo `variance.YujingDang` |
| `engine.mjs` L42-179 `analyze` | **新写** `yinqing.fenxi` | 主链十五步；底层全部 import algo |
| `engine.mjs` L180-188 `zuzhi_shibie` | **新写** `yinqing.zuzhi_shibie` | 算法委托 algo `zuzhi.shibie_zuzhi`；返回 dict 对齐 engine 形态 |
| `engine.mjs` L189-251 `zuzhi_huizong` | **新写** `yinqing.zuzhi_huizong` | engine 功能超集（algo `zuzhi.juhe_bumen` 只是底座，见 drifts①） |
| `engine.mjs` L252-256 `recount` | **新写** `yinqing.chongji` | 整改计数回算 |
| `ai-boundary.mjs` 全文 | **新写** `ai_bianjie.zhunbei_ai_qingqiu` 等 | 白名单 DTO 构造器；云端第二道闸 = desktop `ai_worker.py`（已存在，不改） |
| `server.mjs`（analyze 相关入参组装：`/api/analyze` probe 与 state 快照、`/api/analyze-batch`、`/api/revise` 修订审批流、`/api/action` 状态机、`/api/intake` changeStatus 归一） | 不移植（HTTP 壳层） | 其业务规则随 `yinqing.fenxi`/`analyze_subjects` 交代；`analyze_subjects` 即 `/api/analyze-batch` 的计算主干 |
| `server.mjs` L27-48 `python()` 桥接、`bridge.py`、`ai_worker.py` | 不移植（已在本包范围外的 Python 侧） | bridge 已 sys.path 挂 algo 直接用 `excel_ingest/excel_generate/external_generate`——证明 excel 链路本就在 algo 侧 |

### 3.2 TS 计算模块（plugins/fin-agent/src，17 文件 18 个 fin_* 工具）

> 实测（git diff --no-index）：`plugins/fin-agent/src` 与
> `开发分支_1.0.5/release plugin(1)/release plugin/src` 逐字节一致
> （engine.mjs 实际 import 后者）；下表即桌面引擎真正调用的那套实现。

| TS 模块（fin_* 工具） | Python 权威实现（algo/） | 状态 |
|---|---|---|
| `data-ingest.ts`（fin_daoru_csv） | `data_ingest.py` | ✅ 复用（`daoru_csv/jiexi_csv/qingxi_bing_guilei`，报错逐字一致） |
| `report-parse.ts`（fin_baobiao_jiexi） | `report_parse.py` | ✅ 复用（`shitu_jiexi/guifan_qijian`） |
| `file-extract.ts`（fin_jiequ_wenben） | `file_extract.py` | ✅ 复用；注意桌面 PDF 实走 pymupdf（drifts③） |
| `llm-clean.ts`（fin_guiyihua_tishi、fin_huanjue_jiaoyan） | `llm_clean.py` | ✅ 复用（编排层不调用，属输入归一化/工具壳层） |
| `rolling-budget.ts`（fin_gundong） | `rolling_budget.py` | ✅ 复用（链法①+口径A逐行核对一致） |
| `variance.ts`（fin_chayi） | `variance.py` | ✅ 复用（常量 1500/3000 两侧一致；Python 注释滞后见 drifts②） |
| `planning-split.ts`（fin_chaifen） | `planning_operational.py` | ✅ 复用（BigInt↔无限整数，恒等式同构） |
| `loop-decision.ts`（fin_yuyi_guilei、fin_panduan） | `loop_decision.py` | ✅ 复用（五情形/Gate-0 逐行一致） |
| `building-blocks.ts`（fin_jimu） | `building_blocks.py` | ✅ 复用（关键词表与 D1-D3 口径逐字一致） |
| `bsc.ts`（fin_bsc） | `bsc.py` | ✅ 复用（权重 40/30/20/10、五档 90/80/70/60） |
| `kpi.ts`（fin_kpi） | `kpi.py` | ✅ 复用（15 项公式） |
| `suyuan.ts`（fin_suyuan） | `suyuan.py` | ✅ 复用（KPI_PIANHAO 15 项表逐字一致） |
| `zhenggai.ts`（fin_zhenggai） | `zhenggai.py` | ✅ 复用（engine 在其上追加自定义档名项，属编排层） |
| `kanban.ts`（fin_kanban） | `kanban.py` | ✅ 复用（KPI_MING 表一致） |
| `xishu.ts`（fin_xishu） | `xishu.py` | ✅ 复用（三张提示映射表一致） |
| `baogao.ts`（fin_baogao） | `baogao.py`（+`baogao_docx.py`） | ✅ 复用（Word 渲染仅 algo 有，TS 无对应） |
| `int-math.ts`（公共库，非工具） | 无单独模块 | ✅ 不新写：五助手逐式对应 algo 散落私有函数——`cheng_jidian`↔`rolling_budget._cheng_jidian`、`fen_zhuan_yuan`↔同文件、`bili_bps`/`pingjun_half_up`↔`kpi._bili_bps/_pingjun_yunying_zijin`、半分母变体↔`variance._jisuan_chalv`；本包直接 import 复用 |
| `tools/step*.ts` + `index.ts`（dsh 工具注册壳/岗位守则） | 无对应 | ➖ 不移植（18 个工具的底层全部落在上表模块） |

### 3.3 algo 侧独有（TS 无对应，本包直接复用）

`model_api.py`、`moxing_peizhi.py`（模型调用/配置）、`excel_contract.py`、
`excel_generate.py`、`excel_ingest.py`、`external_generate.py`、
`external_templates.py`、`xlsx_reader.py`（四类 Excel 输入链路——1.0.7 的
主输入口）、`baogao_docx.py`（Word 渲染）。desktop 的 `bridge.py:11` 已把
algo 挂进 sys.path 直接使用，本包的引导与之同款。

---

## 四、drifts 清单（TS 与 Python 行为有出入处——只登记，不改任何一侧）

1. **zuzhi 功能面**：`engine.mjs:194-251` 的 `zuzhi_huizong` 与
   `algo/zuzhi.py:202-243` 的 `juhe_bumen` 同口径声明但能力不对齐——
   engine 版含四模块分解、红/黄计数、机构小计排序+占比、期间分组
   （qijian_lie/yizhi）；algo 版机构小计按首现顺序不排序、无占比、无模块分解。
   本包按 engine 版实现（属编排层职责），识别与纯聚合底座仍复用 algo。
   并列断链两侧不同：engine 用 `localeCompare(...,'zh')`，Python 用码点序
   （如 '后'(U+540E) < '教'(U+6559)，拼音序则相反）——已在
   `test_zuzhi.py` 用注释锁定此差异。
2. **variance 文档滞后（非行为漂移）**：`algo/variance.py:138-140` 注释与
   `:352-353` docstring、`algo/README.md:105` 仍写"黄 5%/红 10%"，实际常量
   `HUANG_YUZHI_BPS=1500/HONG_YUZHI_BPS=3000`（15%/30%），与
   `variance.ts:99/102` 一致——两侧代码无出入，Python 侧文档滞后，照抄需谨慎。
3. **桌面 PDF 提取选型**：`server.mjs:177`+`bridge.py:49-56` 用 pymupdf（第三方）
   提取 PDF，不用 algo `file_extract.cong_pdf_jiequ` 也不用 TS `file-extract.ts`
   （两者互相逐字对齐且 216 用例绿，但桌面链路解 PDF 不经过它们）。本包遵循
   零依赖原则，文本回退链只用 algo 版。
4. **模块聚合双口径并存**：`engine.mjs:122-129` 的 moduleSummary 占比分母 =
   Σ|四模块净|（本包 `fenxi` 第⑦步同口径）；`building_blocks.py` 的 D2 分母
   还含 |未归属净|。两套在同一次分析里并存不冲突（engine 已强制科目归属
   四模块，故无未归属项），移植时分开保留，勿合并。
5. **输入校验边界（语言性）**：TS 各计算模块用结构键鸭子判定（如
   `rolling-budget.ts:206-208`），Python 用 isinstance 精确 dataclass 判定
   （`rolling_budget.py:259`）——报错文案一致，但被拒绝的输入边界不同
   （TS 收普通对象字面量，Python 要实例）。本包在编排层统一构造
   `QijianJine/ChayiShuru/ChaifenShuru/...` 实例喂给 algo，天然回到严格边界。
6. **（补充发现）engine.mjs L112「的实际数缺对应预算」为防御性兜底**：
   正常链路中该检查先被 `rolling_budget` 的同义门禁
   （`实际数据期间不在预算表中：…`）触发——本包保留两侧检查并按 algo
   门禁实测（见 `test_yinqing.py::test_shiji_que_yusuan` 注释）。

---

## 五、两引擎 A/B 对照（行为对齐的直接证据）

方法：同一份输入（tests/gongju.py 夹具同款 CSV + config + subjects）分别喂
`desktop/engine.mjs` 的 `analyze()`（node v22.22.2，桌面测试同款调用形态）与
本包 `yinqing.fenxi()`，逐项比对关键数值。2026-10-11 实测：

- 滚动逐期明细（12 期 shuzhi_fen 与 laiyuan 标注）、三总额（120000/120000/0）；
- 差异两行（差额 ±1000 分、差率 1000 基点、F/A、红档）；
- moduleSummary 四行（净额/方向/占比/基准/实际/行数）；
- 判定两行（覆写后情形 5 复核提示、依据快照含"结构变更登记: null"）；
- 整改清单（4 条、类型分布、action-1..4 编号、高中低与三态计数）；
- 看板预警计数、系数包红行数与完成率 10000 基点；warnings 四条。

结论：**全部逐项一致**（临时对照脚本在验证后已删除，未留在交付目录）。

---

## 六、复现命令（包根目录 = 本文档所在目录）

```sh
python -B -m unittest discover            # 本包 65 用例（任务指定命令）
D:/dev-env/Python312/python.exe -B -X utf8 -m unittest discover   # 同上（显式解释器）
cd D:/AppProject/开发分支_1.0.5/algo && D:/dev-env/Python312/python.exe -B -X utf8 -m unittest discover -s tests -t .   # algo 275 用例（只读验证）
cd D:/AppProject/开发分支_1.0.5/algo && D:/dev-env/Python312/python.exe tools/check_comments.py <本包文件…>            # 注释率检查
```

环境说明：Python 3.12.2（`D:\dev-env\Python312\python.exe`，PATH 同版本）；
零第三方依赖；Windows 控制台显示中文若乱码，请先执行
`[Console]::OutputEncoding=[System.Text.Encoding]::UTF8`（PowerShell）。

---

## 七、审阅提示（已知的不对称，非缺陷）

- 结果 DTO 里 `variance/blocks/bsc/kpi/trace/dashboard/factors` 保留 algo
  数据类实例（属性访问），`rolling/decisions/moduleSummary/correction` 是
  dict/名字空间——与 engine.mjs 的 JS 对象形态同键名同语义，但序列化前
  需自行摊平（桌面由 JSON.stringify 自动完成）。
- `fenxi` 的 `meta.generatedAt` 每次调用取当前 UTC 时间（engine 同款），
  期望值写死的测试不对其断言。
- `ai_bianjie` 的差异行模块取值：`fenxi` 的 variance 行不带 `module` 属性
  （algo ChayiXiang 无此字段），构造器自动回落 `subjects` 索引——与
  engine L121 标注后的值恒等（两侧模块来源同一张 subjects 表）。
