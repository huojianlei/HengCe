# 新版DSH插件裁剪与账号登录调研

> 调研对象：DeepSeek Harness 桌面客户端 0.2.0-rc.2（`D:\deepseek harness Windows`）及其数据目录 `D:\dsh-desktop-data`。
> 方法：两路**只读**调查（插件盘点员＝插件/Bundle/MCP 全景与关闭草稿；登录机制调查员＝登录态、可绕性与替代方案），全程未执行任何安装/卸载/配置写入、未启动被测程序。本报告由报告整理员合并两份调查而成，并抽样复核了关键证据（见文末"复核记录"）。
> 日期：2026-10-12。

---

## 一、结论速览

1. **最小插件集合**：目标是"AI 只剩对话 + 写报告（自研插件）"，最小集合为 **`@deepseek-ai/dsh-base`（对话内核）＋ `@deepseek-ai/dsh-web-app`（窗口 UI/webserver）＋ 装回自研 `@finagent/fin-agent-dsh-plugin`（写报告本体，当前未挂载）**，按需另留 `mcp-office`（仅当报告要直接落 .docx/.xlsx）；其余 2 个实验 bundle、dshmarket（装好 fin-agent 后）与全部 8 条未禁用 MCP 均可关（证据：`D:\dsh-desktop-data\dsh-home\profiles\desktop\package.json:9-15`、`cordis.patch.yml:59-160`）。
2. **登录能关**：产品原生支持纯 API‑key 模式——欢迎窗判定是 `needsWelcome = !loggedIn && !hasApiKey`（`app.asar /lib/main.js:7764-7765`），账号或 API key 任一在即不弹；登录只管**账号模型路由＋账号 UI**，不管更新（generic feed、强制更新策略 anonymous）、不管插件市场（dshmarket 是社区市场）、不管本地 UI 鉴权（回环 cookie 密钥）。
3. **推荐做法**：按顺序**先配 API key（三选一）→ 把默认模型从 `deepseek-account` 切到 `deepseek-official` → 侧栏退出登录**（顺序不能反：当前 `.credentials.yaml` 无 `refs` 节即无任何 key 存量，先登出会每启必弹欢迎窗）；插件裁剪按第二节草稿逐项改、逐项重启验证，改前备份 `cordis.patch.yml`。本轮全部为纸面草稿，未动任何配置。

---

## 二、插件全景表与关闭手段

### 2.1 当前加载全景

配置来源两处：`D:\dsh-desktop-data\dsh-home\profiles\desktop\package.json`（`dsh.profile.bundles` 5 项，:9-15）与同目录 `cordis.patch.yml`（默认模型行 :4-9、MCP 插入行 :59-160）。

| 名称 | 作用 | 配置来源 | 对"对话+写报告" |
|---|---|---|---|
| `@deepseek-ai/dsh-base`（bundle v0.2.0-rc.2） | 共享内核：llm/session/agent/tools/sandbox/审批/存储/会话持久化/遥测等约百行核心插件行 | `package.json:10`；包体与 20732 字符 `cordis.patch.yml` 在 `app.asar` 内 `dsh/node_modules/@deepseek-ai/dsh-base/` | **必留**，禁用即 boot 失败 |
| `@deepseek-ai/dsh-web-app`（bundle v0.2.0-rc.2） | webserver（127.0.0.1:3080 兜底）、前端 dist、聊天 UI 全套、4 个 agent preset（standard/ptc/minimal/cordis）、桌面档遥测 `desktop-product-telemetry`＋`product-analytics`、会话导出/目录选择器/插件清单 RPC | `package.json:11`；`app.asar` 内其 `cordis.patch.yml`（21393 字符）＋presets 4 件 | **必留**，没有它应用无界面 |
| `@deepseek-ai/dsh-experimental-agent-team-profile`（bundle） | 实验性多智能体团队：插入 agent-team（maxMembers 8）/tool-agent-team/ui-agent-team 三行，同时禁用 tool-subagent、tool-subagent-fork、tool-subagent-control、tool-subagent-list-agents 四个直连委派工具 | `package.json:12`；`app.asar` 内其 `cordis.patch.yml`（818 字符） | 无用，**可关** |
| `@deepseek-ai/dsh-experimental-auto-review`（bundle） | 实验性：为 Auto 权限档提供逐工具 LLM 授权复核（仅插一行 auto-review） | `package.json:13`；`app.asar` 内其 `cordis.patch.yml`（88 字符） | 默认 workspace-write+ask 档下**可关**；用 Auto 档则关掉失去复核层 |
| `dshmarket`（v1.66.7） | 可视化插件市场：浏览/搜索/一键安装社区插件、热开关（写 `cordis.patch.yml` 的 disabled 行）、失败恢复、插件诊断页——当前唯一图形化管理入口 | `package.json:5`（dependencies）与 `:14`（bundles 末项）；`node_modules/dshmarket/`；`.dsh-market/state.json`（disabled:[]，region china） | fin-agent 装好后**可关可卸** |
| `mcp-connector-proxy` | connector-proxy（streamable-http 127.0.0.1:12931/mcp） | `cordis.patch.yml:59-66` | **已处于 `disabled: true`，未运行** |
| `mcp-blender` | Blender 3D 桥（venv2 python -m blmcp，连 localhost:9876） | `cordis.patch.yml:67-79` | 无关，可关 |
| `mcp-vision` | 图像理解/文字提取（llm-vision-mcp，glm-4v-flash 走 bigmodel API；env 内含**明文 API key**，本报告不复述其值） | `cordis.patch.yml:80-95`（明文 key 在 :91） | 报告需读截图/图片时才用，可关；关停顺带降低泄露面 |
| `mcp-jianying` | 剪映草稿生成（jianying-mcp venv3 python server.py） | `cordis.patch.yml:96-108` | 无关，可关 |
| `mcp-playwright` | 浏览器自动化（@playwright/mcp --extension，浏览器在 `D:\dsh-desktop-data\mcp-runtimes\browsers`）。注意联网查资料走 dsh-base 内置 web_search/web_fetch，不依赖它 | `cordis.patch.yml:109-120`；dsh-base patch 的 tool-web 行 | 无关，可关 |
| `mcp-context7` | Upstash 库文档检索 | `cordis.patch.yml:121-129` | 无关，可关 |
| `mcp-sequential-thinking` | sequential-thinking 思维链工具 | `cordis.patch.yml:130-138` | 无关，可关 |
| `mcp-office` | Office 文档读写（`D:\dsh-desktop-data\mcp-runtimes\office\.venv` python stdio-safe.py） | `cordis.patch.yml:139-148` | **按需**：报告要直接产出/编辑 .docx/.xlsx 才保留；纯 Markdown 报告可关 |
| `mcp-git` | git 服务器，`--repository` 固定指向 `D:/新建文件夹 (3)/deepseek harness/eighth` 单仓 | `cordis.patch.yml:149-160` | 无关，可关 |
| （未加载）`@finagent/fin-agent-dsh-plugin` | 用户自研插件：18 个预算分析/报告工具＋persona，写报告落点 `src/baogao.ts`。当前**不在** bundles、不在 profile patch、不在 pnpm-lock，asar 全载荷检索亦无 fin-agent | 源码 `D:/AppProject/plugins/fin-agent/`（package.json、README、cordis.yml、fin-agent.patch.yml --patch overlay）；三处为空的排查证据：profile `package.json:7-16`、`cordis.patch.yml` 全文、`pnpm-lock.yaml` importers 仅 dshmarket | **要达成"写报告"必须先装回** |

另：`cordis.patch.yml:39-56` 的 working-activity 与 dsh-tui* 禁用行是 2026-10-02 TUI/活动条清理后的历史防御空行（全 asar 载荷检索 0 命中），删不删都不影响运行。

### 2.2 关闭手段（命令/配置行草稿——本轮均未执行）

**前提**：desktop 档被 Electron 独占——盘点员实测 `dsh --dump-config` 报 `error: profile "desktop" is managed exclusively by the Electron application`。改文件前先退出应用；或直接用市场内热开关（免重启，HMR 约 1 秒）。

**手段①：关单条 MCP** —— 编辑 `D:\dsh-desktop-data\dsh-home\profiles\desktop\cordis.patch.yml`，把对应 `mcp-*` 行的 `disabled: false` 改为 `disabled: true`（`:59-66` 的 mcp-connector-proxy 即现成范例；待关 8 条在 `:67-160`）。

**手段②：关插件行（与市场热开关同一写入机制）** —— 在 `cordis.patch.yml` 末尾追加（草稿）：

```yaml
- id: auto-review
  disabled: true
- id: dsh-market
  disabled: true
```

机制原文：dshmarket `lib/patch.js:6-12`——"a patch row `- id: X` + `disabled: true` stops that loader entry"，配置文件 watcher 约 1 秒内重组、免重启，重启后依然生效（已复核原文）。可用行 id 清单（各 bundle patch 的 insert id）：`auto-review`、`dsh-market`、`agent-team`、`tool-agent-team`、`ui-agent-team`。

**手段③：关/卸 Bundle** —— 改 `package.json` 的 `dsh.profile.bundles` 删行。草稿：仅留 `@deepseek-ai/dsh-base` 与 `@deepseek-ai/dsh-web-app` 两项，删 `dsh-experimental-agent-team-profile`、`dsh-experimental-auto-review`，可选删 `dshmarket`。卸载 dshmarket 包本体：

```
dsh plugin --profile desktop remove dshmarket
```

（`dsh plugin` 即 pnpm 直通，盘点员实测 `--help` 显示 pnpm 11.7.0；本轮未执行。）或应用内 **Settings → Plugins → Plugin configuration → Remove**（`dshmarket/README.md:53`，含可选项"顺带清掉它写过的禁用行"）。

**手段④（可选）：关桌面档遥测** —— 市场内设置页；或补丁行 `- id: desktop-product-telemetry` / `disabled: true` 与 `- id: product-analytics` / `disabled: true`（这两行桌面档默认启用，来源 `app.asar` 内 `dsh-web-app/cordis.patch.yml` insert 段的 `disabled: !!js "ctx.get('profileContext')?.name !== 'desktop'"` 表达式）。

**装回 fin-agent（达成"写报告"的前置）** —— 草稿命令（本轮未执行）：

```
dsh plugin --profile desktop add D:/AppProject/plugins/fin-agent
```

其原设计的 `--patch file:///D:/AppProject/plugins/fin-agent/fin-agent.patch.yml` 依赖已归档的 `D:/AppProject/harness` node 入口，桌面档内建议走 pnpm 安装。

### 2.3 最小集合与逐项关闭风险

**最小集合**＝`dsh-base`＋`dsh-web-app`＋`fin-agent`（＋按需 `mcp-office`）。MCP 全关后 9 条服务器一个进程都不再拉起。

| 可关项 | 关掉的风险 |
|---|---|
| `dsh-experimental-agent-team-profile` | 低。多智能体团队 UI/工具消失；副作用是直连委派工具 subagent/subagent_fork/control/list-agents 重新可用（它们正是被该 bundle 禁用的）——如也想关直连委派，可在 `cordis.patch.yml` 追加对这 4 个 id 的 `disabled: true` 行 |
| `dsh-experimental-auto-review` | 低到中。Auto 权限档失去逐工具 LLM 复核；若切到 Auto/"危险全放行"档，工具将无复核直接执行。默认 workspace-write+ask 档不受影响 |
| `dshmarket` | 中。失去唯一图形化插件管理/热开关/失败恢复页；此后开关插件全靠手工编辑 `cordis.patch.yml`，且启动失败时没有 "Adjust plugins" 自愈界面（`dshmarket/README.md:50`：DSH boot 是 all-or-nothing，一个插件加载失败整个进程退出）。建议 fin-agent 装好并验证后再卸 |
| `mcp-blender` / `mcp-jianying` | 无。创作向工具，零依赖 |
| `mcp-playwright` | 无（对本目标）。AI 不能再操作浏览器；联网检索仍走 dsh-base 内置 web_search/web_fetch |
| `mcp-context7` / `mcp-sequential-thinking` | 无。分别损失库文档检索与显式思维链工具，模型行为略变但功能不依赖 |
| `mcp-vision` | 低。AI 看不懂图片/截图（glm-4v-flash 桥断）；报告需配图理解时才需要。另：其 env 里有明文 API key（`cordis.patch.yml:91`，文件 :58 自带 "never publish" 警告），关停顺带降低泄露面 |
| `mcp-git` | 无。只服务 eighth 单仓 |
| `mcp-office` | 低。AI 不能直接产出/改写 docx·xlsx，报告只能以 Markdown 交付；fin-agent 自带解析不受影响 |
| （**不要动**）`dsh-base`、`dsh-web-app` | 启动失败或白窗。dsh-boot all-or-nothing，核心行（llm/session/agent/webserver 等）缺一即整包起不来；退路是市场失败恢复页（若 dshmarket 还在）或手工回滚 `cordis.patch.yml`/`package.json` |

---

## 三、登录机制与替代方案

### 3.1 登录到底管哪些事

- **模型路由（核心）**：登录 token 只喂 `deepseek-account` 这一条路由——`x-dsh-auth-token` 发往 inferenceOrigin（默认 `https://api.deepseek.com`）的 `/v1/messages` 与 `/v1/files`；另一条 `deepseek-official` 路由用 API key（`x-api-key` 头）。**两路互不回退**，`app.asar` 内 `dsh-llm-deepseek/README.md` 原文："deepseek-official resolves only its configured API-key reference. deepseek-account resolves only the stored grant… Neither route falls back to the other. Signing out removes the account grant and preserves API keys."。桌面端出厂同时挂两条：`dsh-base/cordis.patch.yml:521-529`，`llm-deepseek`=api-key 版、`llm-deepseek-account`=账号版（已复核原文 :525-529）。
- **账号 UI 与平台信息**：侧栏头像/UID/打码手机邮箱、余额卡、用量/充值内嵌页（platform.deepseek.com）、红利通知、反馈表单 uid 预填——`dsh-deepseek-account-platform/README.md`（profile/balance API）＋ `dsh-client-ui-settings-account/README.md`。
- **欢迎/登录门（仅此而已）**：`app.asar /lib/main.js:7764-7765`（已复核原文）`function needsWelcome(authentication){ return !authentication.loggedIn && !authentication.hasApiKey; }`——账号或 API key 任一在即不弹；两样都没有才弹欢迎窗，窗上有「添加 API Key」和「稍后配置」（welcomeKeyLater）按钮，跳过＝enterWorkspace（`main.js:12129`），仅本次启动有效，关窗即退出应用（`main.js:12137-12142`）。
- **不管更新**：`D:\deepseek harness Windows\resources\app-update.yml`＝provider: generic（download.deepseek.com/dsh-desk/feeds/win-x64，channel nightly）；`app.asar /package.json` 的 `dshMandatoryUpdatePolicy` 为 `authentication: "anonymous"`；`main.js:12266-12268` 表明强制登录仅 `feishu-test` 内测构建才有，本包不是。
- **不管插件市场**：装的是第三方社区市场 dshmarket（目录来自 awesome-dsh-plugin，安装走 npm/GitHub Release，评论走 giscus/GitHub——`dshmarket/README.zh.md`），全程不涉 DeepSeek 账号。
- **不管本地 UI 鉴权**：`.credentials.yaml` 的 client-connection/browser-session 记录是回环 Web UI 的 cookie 签名密钥（`dsh-client-connection/README.md:41`），device 记录是设备 UUID，都不是账号。
- **过期联动**：账号 token 遇 401/业务码 40003 被本地清除并广播 session-expired（`dsh-deepseek-account-platform/README.md`）；`main.js:11353-11370` 若此刻无 API key 会弹欢迎窗打断使用；账号模型调用失败提示 "Model unavailable. Please sign in and try again."，配额失败弹充值 Modal。
- **伴生本地文件（非鉴权）**：`dsh-home/llm-deepseek/files-v3.json`＝/v1/files 上传缓存索引（expiresAt−createdAt＝604800s 恰为 fileExpiresAfterSeconds）；`.dsh-usage-ledger/-stats`＝本地用量成本台账；`.dsh-usage-reconcile.json`＝与平台余额对账；`pet.json`＝桌宠。

### 3.2 能不能关——能，产品原生三步法（草稿，未执行）

本机现状：`D:\dsh-desktop-data\dsh-home\.credentials.yaml` 只有 `version`＋`records`（browser-session 密钥、device UUID、deepseek-account-platform/default 账号 grant），**没有 `refs` 节**（合并人已复核：全文件 17 行、无顶层 `refs:`）——即当前仅账号路由可用，**直接登出会退回"每启必弹欢迎窗"状态，所以顺序必须是先配 key 再登出**。

1. **配 API key（三选一）**：
   - 欢迎窗/设置→模型页 DeepSeek 卡片粘贴（`main.js:8190-8207` 经 credentials.set 落盘）；或
   - 手编 `.credentials.yaml` 加两行：`refs:` ＋ `  DEEPSEEK_API_KEY: sk-…`（`dsh-credentials-local/README.md`：文件可直编、watch 自动热载、优先级＝启动环境＞存储文件＞项目.env＞家.env）；或
   - 启动 shell 设 `DEEPSEEK_API_KEY` 环境变量（只读、最优先）。
2. **切默认模型到 API-key 路由**：把 `profiles/desktop/cordis.patch.yml:4-9` 首条 agent-default-model 的 `provider: deepseek-account` 改为 `deepseek-official`（`model` 保留 `deepseek-flash` 或换 `deepseek-v4-pro`，`reasoningEffort` 现为 max），或在设置模型选择器里点选（`dsh-agent-default-model/README.zh.md`：保存即写回 profile patch）。子代理白名单（同文件 :30-38 `allowedModels`）本就只有 deepseek-official 两个模型，无需动（已复核）。
3. **侧栏账号菜单 → 退出登录**：本地先删 grant 再后台 POST `/auth-api/v0/users/logout`（失败也不恢复本地登录），API key 保留。此后 `needsWelcome` 恒 false，演示全程不会再出现任何登录窗。

**可选项**：要演示中连 DeepSeek 官方域名都不出现，可把 DeepSeek 卡「自定义设置」的 baseURL（或 `cordis.patch.yml` 的 `llm-deepseek` 条目加 `config: { baseURL: … }`，或 `$DEEPSEEK_BASE_URL`）指到中转网关——解析链见 `dsh-llm-deepseek/README.md`：显式值→$DEEPSEEK_BASE_URL→官方根 `https://api.deepseek.com/anthropic`，需 Messages 兼容（路径拼接 `/v1/messages`、`/v1/files`）。账号 UI 无独立隐藏开关，但登出后仅呈未登录态，不影响演示。

### 3.3 替代方案与代价

| 方案 | 说明 | 代价 |
|---|---|---|
| **纯 API key 不登录（推荐）** | 按 3.2 三步：存 key→默认模型切 deepseek-official→登出 | 演示机需能访问 api.deepseek.com（或中转）；计费走 key 的钱包；无余额/用量内嵌页 |
| 绕过登录但什么都不配 | 欢迎窗每次启动都弹，点「稍后配置」可进工作区（`main.js:12129` skip→enterWorkspace） | 关窗即退出应用（`main.js:12137-12142`）；模型调用报 MISSING_CREDENTIAL（official 路）或要求登录（account 路），联网搜索也失败（web-search-deepseek 用同一 `DEEPSEEK_API_KEY`，`dsh-base/cordis.patch.yml:478-481`，已复核）——**不适合演示，仅应急** |
| 自定义 base_url＋api_key | ①官方兼容中转：设置→模型→DeepSeek 卡「自定义设置」改 baseURL，或 `cordis.patch.yml` 的 `llm-deepseek` 条目加 `config: { baseURL: https://网关, apiKeyEnv: DEEPSEEK_API_KEY }`（出厂条目 `dsh-base/cordis.patch.yml:525-526` 无 config，覆盖即可；`dsh-llm-deepseek-api-key/README.md` 有完整 yaml 示例）；②任意 OpenAI/Anthropic 兼容端点：设置→模型→「添加模型提供商→自定义模型 API」（llm-pi-ai 路由，`ui-settings-models/README.md`） | 中转网关的稳定性/合规自担；端点必须兼容对应协议路径 |
| dsh headless/CLI 无凭据运行 | `dsh headless "任务"`（`app.asar` `dsh/lib/bin.js:39-49`）与桌面宿主一样**先启动后鉴权**——宿主启动序列 `main.js:11320-11455` 先 backend.start 再 openInitialWindow，账号平台 README 明确 "Startup continues signed out"；缺凭据只在发请求时报错不阻启动 | **源码级结论，未实测**（只读约束，运行会写 sessions/logs） |
| 保持登录的折中 | 既存 API key 又留着登录——`needsWelcome` 恒 false，账号过期/登出都不弹窗打断（判定都先看 hasApiKey），账号 UI 想看就看 | 见第四节第 2、3 条副作用 |

---

## 四、风险与未知项

1. **只读约束下的验证边界**：两路调查均未启动应用/CLI 实测（运行会写 sessions/logs），全部结论来自源码/配置静态阅读；headless 行为是源码级推断。**未实测不登录启动客户端的完整走查**（如需可另起一轮）。
2. **保留登录的演示副作用**：①首次登录需浏览器 PKCE 跳 platform.deepseek.com，演示机当场登录有网络与等待风险；②账号请求带身份元数据（版本/UI 语言/UTC 偏移、`x-client-platform: desktop-win`）＋模型请求携带稳定匿名 id 与 session id，且默认开启 `dsh_session_log`（增量会话日志字段）与 `dsh_plugin_packages`（插件清单）随请求上行——均在模型输入之外但会离开本机（`dsh-llm-deepseek/README.md` 原文），衡策演示若涉敏感数据建议用 API key/中转并评估此点；③额度耗尽弹充值 Modal、token 失效弹 toast，无 key 时更会弹欢迎窗打断演示。
3. **token 无过期/刷新机制**（account-platform README），但 401/40003 即本地清除——长存 token 可能某天突然失效，勿把"现在能跑"当长期保证。
4. **凭据卫生**：`profiles/desktop/cordis.patch.yml:58` 注释自述 "May contain historical credentials. Keep local; never publish or print."（已复核），且 :91 vision MCP 的 env 里确有一枚**明文第三方 API key**（本报告不复述其值）——演示/打包外发前应清理该文件。
5. **改动风险**：改 `cordis.patch.yml` 需保持 YAML 结构；宿主启动是 all-or-nothing（一个插件配置错整个进程退场，`dshmarket/README.md:50`），改前备份该文件。
6. **当前无任何 API key 存量**（`.credentials.yaml` 无 refs 节）：只登出不配 key 会让欢迎窗在每次启动和每次账号过期时出现。
7. **失效的参考文件**：调查任务指定的 `D:/dsh-desktop-data/import-staging/old-dsh-home/cordis.patch.yml` 已不存在（0930 交接后 staging 已清理，全盘 maxdepth3 检索无其他副本）；其"自定义模型写法"已由包内 README 的等价配置替代；旧 CLI 家目录 `D:\dsh-home` 现是指向新 dsh-home 的符号链接。
8. **插件裁剪的未知项**：agent-team bundle 关闭后直连委派工具重新可用（是否连它们一起关需用户拍板）；auto-review 关闭后 Auto 档无复核；dshmarket 卸载后失去自愈界面；**fin-agent 当前未挂载，"装回"步骤未执行未验证**——最小集合的第三块拼图仍是纸面方案。

---

## 附：证据路径清单

**插件侧**
- `D:\dsh-desktop-data\dsh-home\profiles\desktop\package.json:5,9-15`（dshmarket 依赖与 5 项 bundles；合并人已复核 JSON 原文）
- `D:\dsh-desktop-data\dsh-home\profiles\desktop\cordis.patch.yml:4-9`（默认模型 deepseek-account/deepseek-flash/max）、`:30-38`（子代理 allowedModels 仅 deepseek-official）、`:39-56`（TUI 历史禁用行）、`:58`（历史凭据警告注释）、`:59-160`（MCP inserts；:91 明文 key）、`:60-66`（disabled 范例行）（合并人已复核上述行号原文）
- `D:\dsh-desktop-data\dsh-home\profiles\desktop\node_modules\dshmarket\lib\patch.js:6-12`（patch 行 disabled 机制与 HMR ~1s）、`README.md:48`（热开关）、`:50`（boot all-or-nothing）、`:53`（Settings→Plugins 自管理）（合并人已复核原文）
- `D:\dsh-desktop-data\dsh-home\profiles\desktop\.dsh-market\state.json`（disabled:[]，region china）
- `D:\deepseek harness Windows\resources\app.asar` 内 `dsh/node_modules/@deepseek-ai/dsh-base/cordis.patch.yml:472-481`（web-search 用 DEEPSEEK_API_KEY）、`:521-529`（出厂双 provider 条目）及各 bundle 的 patch/preset 文件（盘点员按 asar 头偏移直读原文；合并人已复核 :472-481、:521-529）
- `D:\deepseek harness Windows\resources\runtime\cli\bin\dsh.cmd`（CLI=Electron 以 node 模式跑 app.asar 内 dsh-desktop-host/lib/cli.js）
- 自研插件源码：`D:\AppProject\plugins\fin-agent\`（package.json `@finagent/fin-agent-dsh-plugin`、src/baogao.ts、fin-agent.patch.yml）

**登录侧**
- `D:\dsh-desktop-data\dsh-home\.credentials.yaml`（version:1＋records 三条，无 refs 节；合并人已复核 17 行结构与顶层键）
- `D:\dsh-desktop-data\dsh-home\llm-deepseek\files-v3.json`、`.dsh-usage-stats.json`、`.dsh-usage-reconcile.json`、`pet.json`（本地伴生文件，非鉴权）
- `D:\dsh-desktop-data\搬迁交接-给codex-20260930.md:13`（junction 重定向：Roaming\@deepseek-ai、~\.dsh→D:\dsh-desktop-data）、`:39-46`（import-staging 痕迹与旧 CLI 凭据未接入说明）
- `D:\deepseek harness Windows\resources\app-update.yml`（generic feed、nightly）、`resources\app.asar` 内 `/package.json`（`dshMandatoryUpdatePolicy.authentication="anonymous"`）、`/lib/main.js:7764-7765`（needsWelcome，合并人已复核原文）、`:7861-7864/8108-8117/8156-8157/8190-8207`（key 保存链路）、`:11320-11455/11353-11370`（启动序列与过期弹窗）、`:12129/12137-12142`（稍后配置/关窗退出）、`:12266-12268`（飞书登录仅内测）
- `app.asar` 内 README：`dsh-llm-deepseek`（双路由互不回退、baseURL 解析链、请求携带匿名 id＋session id、dsh_session_log/dsh_plugin_packages 默认开启）、`dsh-llm-deepseek-api-key`（apiKeyEnv 配置示例）、`dsh-deepseek-account-platform`（PKCE、登出、401/40003、Startup continues signed out）、`dsh-credentials-local`（refs/records 格式与四层优先级）、`dsh-client-connection:41`（browser-session=cookie 签名密钥）、`dsh-client-ui-settings-models`、`dsh-client-ui-settings-account`、`dsh-agent-default-model/README.zh.md`、`dsh/lib/bin.js:39-49`（headless 子命令）

**复核记录（报告整理员在本轮实际执行的抽查）**
- 读 `package.json` 并解析 JSON：bundles 恰为报告所列 5 项，`dshmarket: ^1.66.7`。
- 读 `cordis.patch.yml` 全文 160 行：核对上文引用的全部行区间原文（含 :91 明文 key 存在性，值未复述）。
- 读 `.credentials.yaml`：17 行、顶层仅 version/records、无 `refs:`。
- 按 asar 头偏移提取 `app.asar` 内 `lib/main.js`（12332 行）：`needsWelcome` 位于 :7764-7765，原文与 3.1 引文一致；`dsh-base/cordis.patch.yml`（529 行）：:472-481、:521-529 原文一致。
- 读 `dshmarket/lib/patch.js:1-12` 与 `README.md:46-56`：机制引文一致。
- 两份原始调查全文自工作流运行档案提取存档：`D:\public\First\.zcode\调查存档-插件盘点员.json`、`D:\public\First\.zcode\调查存档-登录机制调查员.json`。
