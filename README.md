# 衡策（HengCe）· 财务智能体


##本仓库为临时快照版本，是deepseek harness的插件，不能直接安装生效，需要agent进行辅助安装


> 四类固定 Excel 模板进 → 12 表/9 表契约校验 → 十五步分析 → 计算报告（md/html/PDF，
> 引《管理会计应用指引》）→ 液态玻璃工作台。全部浓缩为一个 DeepSeek Harness（dsh）插件。

本仓库 = 2026-10-18 收官快照：**后端 1.1.1（三条打包自检全绿）+ 玻璃 UI（当日交付验收全过）
+ dsh 插件拼接层（本轮新写，冒烟七件全绿）**。



## 目录

```
├─ plugin\                    ← 最终 dsh 插件（自足、可直接挂载）
│  ├─ index.ts / adapter\ / ui\ / backend\ / 数据\
│  └─ 挂载说明.md             ← 怎么装、怎么验（先读这个）
├─ 源码归档\开发分支_1.1.1\    ← 后端完整开发树（含 tests、老生成器、验收脚本）
├─ 源码归档\衡策UI重建\        ← UI 开发树（含 验收*.py 交互/动效/菜单/玻璃回归）
├─ legacy-fin-agent\          ← 旧 18 工具 TS 插件存档（依赖已归档的 harness，仅留档）
└─ docs\                      ← 打包清单、接入说明、界面契约、历轮验收报告
```

## 快速开始

1. **装到 dsh 桌面端**：见 `plugin\挂载说明.md`（追加一行 overlay 或独立服务两种方式）。
2. **跑一遍全流程**（不装 dsh 也能跑）：
   ```sh
   cd plugin\backend\演示生成器v2 && python -B shengcheng.py   # 生成四册演示件
   cd .. && python -B 跑衡策全流程.py                            # 导入→分析→报告→PDF
   ```
3. **打开界面**：`cd plugin && node adapter/独立服务.mjs` → http://127.0.0.1:4180/hengce/

## 架构（一行一程）

```
衡策界面 ui/（原生 ESM，液态玻璃）
  ↕ window.hengceHost（adapter/宿主桥.js，13 action 协议）
宿主适配层 adapter/（dsh webServer 前缀路由 /hengce + 独立服务 + 4 个 dsh 工具）
  ↕ stdio JSON 行协议（base64 文件字节）
Python 后端 backend/（1.1.1 权威三函数）
  ├─ excel_ingest_v11  导入：三轨道契约校验（v2 9表 / v1.1·v1.2 12表 / 外部两册）
  ├─ yinqing.fenxi     十五步分析（滚动/差异预警/积木/BSC/KPI/整改，19 个结果键）
  └─ baogao_liuxian    报告：9 模块 × 三段式，kb2 真检索《管理会计应用指引》
```

金额=整数分、比率=整数基点、缺数=null 不臆造；演示数据固定种子确定性生成。

## 质量基线（2026-10-18 实测，全部可复现）

| 验收 | 结果 |
|---|---|
| 生成器自检 jiaoyan.py（vendored 树内） | 44/44 |
| ingest_v11 unittest | 21/21 OK |
| 全流程 CLI（dev-env 与 dsh 自带 Python 双实测） | 19 键 / 108 整改 / 9 模块 / 72 条例 / 18 页 PDF；确定性逐字节一致 |
| 桥接 13 action 冒烟（含修订真重算、三格式导出、拒绝路径） | 全过 |
| dsh 工具冒烟（import→analyze→report→open_ui） | 全过 |
| 界面宿主模式 Playwright（桥注入/真实主体/108 行/金额换算/无报错） | 8/8 |
| dsh 挂载冒烟（--dump-config overlay） | hengce 行在册 |

## 红线（沿袭共享工作规则）

- 数据零入库零外发；演示数据固定种子，主体为虚构企业；
- 原始工作簿不出本机；报告 AI 解读为占位标注，由宿主回填，不冒充模型产出；
- Python 计算为唯一权威（44+21 项自检锁死），前端与适配层只做编排与展示。
