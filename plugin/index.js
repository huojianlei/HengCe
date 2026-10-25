// 衡策（HengCe）· dsh 树外插件入口。
//
// 形态（对齐 docs/接入说明.md 的分工图）：
//   衡策界面（ui/，宿主 webserver 托管于 /hengce/）
//     ↕ window.hengceHost（adapter/宿主桥.js，页面侧协议）
//   宿主适配器（adapter/服务核心.mjs + 本文件的路由与工具）
//     ↕ stdio JSON 行协议（adapter/桥接.mjs ↔ backend/桥接入口.py）
//   衡策插件后端（backend/：import_excel_v11 → fenxi → compute_report_pipeline）
//
// 入口约定：export const name / inject / apply(ctx)（cordis 插件三件套）。
// 本文件零 @deepseek-ai 导入（桌面档 file:// 挂载不依赖 harness node_modules），
// 工具注册沿用 defineTool 的入参形状直接登记；任何单项失败不拖垮 dsh 启动
// （dsh boot 是 all-or-nothing，插件必须自兜底）。
//
// ---------------------------------------------------------------------------
// 【本文件是什么：index.ts 的加载产物】
//   package.json 的 main 指向 ./index.js 且 exports 也指向它 —— Node 真正加载
//   的是本文件；index.ts 只是同目录的可读源文件（含类型标注）。因此本文件
//   与 index.ts 必须保持同一套可执行语句序列：改一个必须同步改另一个，
//   否则改 .ts 不生效、改 .js 又与源码对不上，排障会两头绕。
//   一致性校验：.tmp-本轮-注释与CLI/T7/对照tsjs.mjs（把 .ts 的类型标注用
//   Node 内置 module.stripTypeScriptTypes 抹掉，再与去注释的本文件逐字符比较）。
//
// 【本文件在链路的哪一环】
//   上游：dsh 宿主（cordis 容器）在服务装配好后调用 apply(ctx)。ctx 提供
//         webServer / tools / systemPrompt 三个服务（见下方 inject 声明）。
//   下游：adapter/桥接.mjs 的 Qiao —— 本进程唯一的 Python 子进程；再往下是
//         backend/桥接入口.py 的 DONGZUO 分发表（workspace.load / files.import /
//         analysis.run / reports.generate 等 action，每个 action 一问一答）。
//   本文件自己不碰 Excel、不做财务计算，只做三件事：
//     ① 把 ui/ 挂成宿主 HTTP 前缀路由 /hengce/*；
//     ② 把四个对话工具翻译成 Qiao 请求（payload 形状 = Python 侧入参）；
//     ③ 写 persona，约束宿主模型怎么用这四个工具、怎么说话。
//
// 【失败兜底策略（dsh boot all-or-nothing 的应对）】
//   · webServer 挂不上 → 只 console.error，四个工具照旧可用；界面改走独立
//     服务（node adapter/独立服务.mjs，默认 4180 端口），行为与宿主路由一致。
//   · 单个工具注册失败 → 只报该工具名，其余三个继续注册，不连坐。
//   · systemPrompt 写不进 → 只 console.error，不影响路由与工具。
//   · Python 桥崩溃 / 等待超时 → Qiao 抛中文 Error，工具把中文原文交给宿主
//     模型展示给用户（不吞异常、不编造成功结果）。
//   任何一项都不向外抛异常，否则整个插件会被宿主判为加载失败。
//
// 【口径纪律（贯穿本文件、persona 与所有回包文案）】
//   金额一律整数分（MoneyFen），比率一律整数基点（BasisPoints，10000 bp = 100%）；
//   只有 UI 显示层才做 分→元（÷100）、基点→百分数（÷100）换算，本层传输不换算。
// ---------------------------------------------------------------------------
import { readFile } from 'node:fs/promises';
// fileURLToPath / dirname 当前未被引用：早期版本用它们算 plugin 根目录，后改由
// adapter 各模块自算 BEN_MU；按「只加注释不改逻辑」原则保留 import 不动。
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
// Python 桥进程客户端：拉起/看护 backend/桥接入口.py，串行转发 action 请求。
import { Qiao } from './adapter/桥接.mjs';
// HTTP 处理器工厂：dsh 前缀路由与独立服务共用同一份实现。
import { zao_chuliqi } from './adapter/服务核心.mjs';

// 插件标识：宿主日志前缀、热重载按 id 定位、卸载都认这个名字，勿改。
export const name = 'hengce';

// webServer=托管界面；tools=AI 全流程控制四工具；systemPrompt=衡策 persona
// cordis 语义：这是「依赖声明」，三个服务齐备后 apply 才会被调用；缺任一项
// 本插件保持待激活（不是加载失败），所以不会阻塞 dsh 启动。
export const inject = ['webServer', 'tools', 'systemPrompt'];

// 工具与界面共用一个 Python 桥进程（行协议串行，天然互斥）
// 单例的代价：一次只跑一个请求，慢请求（报告出 PDF）会让后面的排队；
// 换来的是状态一致性——backend 的工作区是进程内单例，无需跨进程加锁。
const qiao = new Qiao();

// 插件主入口：宿主装配完成后由 cordis 调用一次。
// · ctx 是宿主注入的 Context（本文件只用 inject/webServer/tools/systemPrompt/on
//   五个成员；.ts 里标 any，避免引入 @deepseek-ai 类型包破坏 file:// 挂载）；
// · 返回 void，不返回卸载函数——卸载走 ④ 的 dispose 钩子；
// · 所有可失败分支已就地捕获，本函数不会向外抛异常。
export function apply(ctx) {
  // ---- ① 界面：宿主 webserver 前缀路由 /hengce/* ----
  // 处理器来自 adapter/服务核心.mjs，与独立服务（4180）共用同一实现，
  // 因此两种形态的路由表、中文报错文案、缓存头完全一致。
  const chuli = zao_chuliqi(qiao);
  // 注销函数登记表：register() / tapIndex() 都返回各自的「注销」函数。
  // 不清旧路由的后果：热重载后同一路径注册两遍，一个请求被处理两次；
  // 这里攒起来交给 ④ dispose 统一调用，保证卸载即净。
  const zhuce = [];
  // 整段 try/catch 的理由：个别宿主档位不带 webserver（如纯 CLI 档），
  // 或 webserver 版本不认 prefix 路由；此时插件仍应可用（工具直连 Python 桥）。
  try {
    // apply 内再次声明依赖：宿主可能延迟装配 webServer，这里能拿到已就绪
    // 实例（服务就绪时回调同步触发），也便于拿到真实端口给工具④用。
    ctx.inject(['webServer'], (host) => {
      // kind:'prefix' 而非精确路径：一次托管整套 UI（/hengce、/hengce/api、
      // /hengce/<静态资源>），不必为每个文件单独登记路由。
      zhuce.push(host.webServer.register({
        kind: 'prefix', path: '/hengce', handler: chuli,
      }));
      // 窗口接管：给客户端首屏 HTML 注入一行跳转（dsh-app scheme 会把
      // 相对路径代理到本 webserver），应用主窗口直达衡策工作台。
      // tapIndex 返回卸载函数，随插件卸载一并清理。
      // 与 client/client.js 的接管互补：浏览器打开宿主首页由这段脚本跳转，
      // 桌面客户端则由 client 插件在 apply 时 replace，避免「打开宿主还要点一次」。
      // ?embedded=1 = 隐藏独立侧栏、改用业务页签布局；只替换第一个 </head>。
      zhuce.push(host.webServer.tapIndex((html) =>
        html.replace('</head>',
          '<script>if(!location.pathname.startsWith("/hengce/"))'
          + 'location.replace("/hengce/?embedded=1")</script></head>')));
    });
  } catch (e) {
    // 只记录不抛出：界面不可用是本插件可接受的降级（工具链仍然完整）。
    console.error('[hengce] webServer 挂载失败（界面不可用，工具仍可用）：', e?.message || e);
  }

  // ---- ② AI 全流程控制：四个工具（对话里即可驱动导入→分析→报告→看界面）----
  // 工具对象直接按 defineTool 的入参形状登记（name/description/parameters/
  // execute），不 import @deepseek-ai —— 树外插件在桌面档是 file:// 挂载，
  // 拿不到 harness 的 node_modules，import 会让插件加载直接失败。
  // 约定：execute 的返回值是给宿主模型看的中文文本，只写事实（计数/编号/路径），
  // 不写推测；失败时让 Qiao 的 Error 原样抛出，宿主会把中文原文展示给用户。
  // description / parameters 是模型选工具的依据，字段名与 units 必须写清口径。
  const gongju = [
    {
      // 工具①：导入一本工作簿。链路 hengce_import → files.import →
      // Python import_excel_v11（三轨道契约校验）。
      // · lu_jing 必须是本机绝对路径——只有插件进程能读文件，模型和页面都不行；
      // · 文件内容转 base64 走 JSON：行协议只传文本，二进制必须显式编码，
      //   直接 JSON.stringify(ArrayBuffer) 会得到 {} 而丢字节；
      // · mode:'append' 追加导入、不覆盖已导入的册；四类类别由解析器判定，
      //   文件名与用户口述只作提示（不信任文件名是契约硬要求）；
      // · 回包里的 category/checks/rows/entity 全部来自后端解析结果，不加工；
      // · dirty=true 表示输入已变、当前分析结果过期，须重新 hengce_analyze。
      name: 'hengce_import',
      description: '导入一本衡策 Excel 工作簿（预算基础/实时经营/行业对标/经营变更，'
        + '四类之一，按工作簿内容自动识别）。传入本机 .xlsx 绝对路径。',
      parameters: {
        type: 'object',
        properties: {
          // Windows 反斜杠或正斜杠均可；取 basename 只作展示名，不参与校验。
          // 类别不在这里传：以工作簿解析结果为准，避免用户选错类别带歪分析。
          lu_jing: { type: 'string', description: 'xlsx 文件绝对路径' },
        },
        required: ['lu_jing'],
      },
      // 返回：一句中文事实摘要（名称/类别/校验项数/入库行数/主体）；
      // 失败：readFile 的 ENOENT 或后端校验中文报错直接向上抛。
      async execute(args) {
        const jie = await qiao.qing('files.import', {
          files: [{
            // name 只用于工作区展示；bytesB64 是原始文件字节（base64）。
            name: args.lu_jing.split(/[\\/]/).pop() || '工作簿.xlsx',
            bytesB64: (await readFile(args.lu_jing)).toString('base64'),
          }],
          mode: 'append',
        });
        // append 模式下最后一本即本批刚导入的；字段与界面 files[] 同形。
        const ce = jie.files[jie.files.length - 1];
        return `已导入并校验通过：${ce.name} ｜ 类别 ${ce.category} ｜ 校验 ${ce.checks} 项 ｜ `
          + `入库 ${ce.rows} 行 ｜ 主体 ${ce.entity}。`
          + (jie.dirty ? '（输入已变更，请重新运行 hengce_analyze）' : '');
      },
    },
    {
      // 工具②：十五步分析。链路 hengce_analyze → 先 workspace.load 取当前
      // 配置 → 再 analysis.run（entityId:'all' = 全部主体/部门一起算）。
      // 两个请求都走同一个 Qiao 串行链，天然先读后算，不会读到旧配置。
      // · 三个可选参数只覆盖「传进来」的键，其余沿用工作区已有配置
      //   （缺省值不重置，避免用户没提参数时把界面上的设置冲掉）；
      // · growth 单位是整数基点：10000 = 100%，2500 = 25%，不是百分数；
      // · 回包 rows 是差异行全集，risk !== 'normal' 的算预警行；
      // · warnings 是后端的非致命提示，原样转述、不加工、不隐藏。
      name: 'hengce_analyze',
      description: '对已导入的「预算基础 + 实时经营」两册运行十五步分析'
        + '（滚动预算/差异预警/积木/KPI/整改清单）。'
        + '可选配置：cycle(月度|季度)、period(如 2027-06)、growth(企业增长率基点)。',
      parameters: {
        type: 'object',
        properties: {
          // 周期决定期间解析口径：月度按 YYYY-MM、季度按 YYYY-Qn，二者不可混用。
          cycle: { type: 'string', description: '月度 或 季度（缺省沿用当前配置）' },
          // 分析末档（工作区期间窗口的右端）；格式须与 cycle 匹配，否则后端报错。
          period: { type: 'string', description: '分析末档，如 2027-06 / 2027-Q2' },
          growth: { type: 'number', description: '企业增长率（基点，0=不增长）' },
        },
      },
      async execute(args) {
        // 先取当前工作区配置：工具参数是「覆盖项」，不是全量配置。
        const dang = await qiao.qing('workspace.load', {});
        const pei = { ...(dang.config || {}) };
        // 只覆盖调用方显式给出的键（undefined/null 都视为「没给」）。
        for (const jian of ['cycle', 'period', 'growth']) {
          if (args[jian] !== undefined && args[jian] !== null) pei[jian] = args[jian];
        }
        const jie = await qiao.qing('analysis.run', { entityId: 'all', config: pei });
        // 预警口径以后端 risk 字段为准，本层不按差额正负自行重判（口径纪律）。
        const yuj = jie.rows.filter((r) => r.risk !== 'normal').length;
        // 回包文本只报计数与运行号：runId 是报告与历史快照的关联键，必须露出。
        return `分析完成：主体 ${jie.meta.company} ｜ 期间 ${jie.meta.period} ｜ `
          + `差异行 ${jie.rows.length}（预警 ${yuj}）｜ 整改 ${jie.actions.length} 条 ｜ `
          + `滚动期数 ${jie.trend.length}。运行号 ${jie.meta.runId}。`
          + (jie.warnings?.length ? ` 提示：${jie.warnings.join('；')}` : '');
      },
    },
    {
      // 工具③：对「最近一次分析运行」生成计算报告。链路 hengce_report →
      // reports.generate（九模块数据表/分析/《管理会计应用指引》依据条例）。
      // · 报告绑定当前 runId：dirty（输入已变但没重算）时后端会拒绝生成，
      //   避免把旧结果包装成新报告；
      // · 产物落 plugin/数据/报告/ 下，md/html/pdf/json 四格式同源同数；
      // · pages 未真实生成时为 null，这里用 '?' 兜底，不编造页数。
      name: 'hengce_report',
      description: '对最近一次分析运行生成计算报告（md/html/pdf/json 四格式，'
        + '含 9 个模块的数据表/分析/《管理会计应用指引》依据条例）并返回报告号。',
      parameters: { type: 'object', properties: {} },
      async execute() {
        const jie = await qiao.qing('reports.generate', {});
        // reports[0] = 最新一份；includeAI 默认关，AI 解读留宿主回填占位。
        const bao = jie.reports[0];
        return `报告已生成：${bao.title} ｜ ${bao.pages ?? '?'} 页 ｜ 报告号 ${bao.id}。`
          + '文件在 plugin/数据/报告/ 下（md/html/pdf/json 四格式）；'
          + '界面内可预览与导出（见 hengce_open_ui 给出的地址）。';
      },
    },
    {
      // 工具④：把工作台地址告诉用户（不返回 HTML，只返回 URL）。
      // · 形态一：宿主 webserver 在跑 → /hengce/ 与 ?embedded=1 两个地址；
      // · 形态二：探测不到端口 → 给独立服务地址与启动命令（4180 兜底端口）。
      // 端口靠二次 inject 同步回调取 host.webServer.config.port；取不到就降级，
      // 不抛错（很多桌面档的 webserver 不暴露 config，属正常情况）。
      name: 'hengce_open_ui',
      description: '给出衡策玻璃工作台的访问地址（宿主 webserver 或独立服务两种形态）。'
        + '打开地址即可操作界面，与工具共用同一后端。',
      parameters: { type: 'object', properties: {} },
      async execute() {
        let duankou = 0;
        try {
          ctx.inject(['webServer'], (host) => {
            duankou = host.webServer?.config?.port || 0;
          });
        } catch { /* 端口探测失败给出独立服务指引 */ }
        if (duankou) {
          // 两个地址都给出：默认布局给浏览器；embedded=1 给宿主内嵌视图。
          return `衡策工作台地址（宿主 webserver）：http://127.0.0.1:${duankou}/hengce/`
            + '\n嵌入布局：http://127.0.0.1:' + duankou + '/hengce/?embedded=1';
        }
        // 兜底文案里必须带「怎么起服务」：只给地址用户点了也是连不上。
        return '未探测到宿主 webserver 端口。兜底：在 plugin 目录运行 '
          + '"node adapter/独立服务.mjs"，然后访问 http://127.0.0.1:4180/hengce/';
      },
    },
  ];
  // 逐个注册、逐个兜底：一个工具的参数结构被宿主拒了，不应该拖掉其余三个。
  // 注册失败只打日志，模型侧会看到「该工具不存在」，但导入/分析/报告仍能跑。
  for (const g of gongju) {
    try {
      ctx.tools.register(g);
    } catch (e) {
      console.error(`[hengce] 工具 ${g.name} 注册失败：`, e?.message || e);
    }
  }

  // ---- ③ persona：让宿主模型知道衡策的口径与边界 ----
  // systemPrompt.section 决定「模型是谁」：name 唯一、order 决定拼接顺序
  // （0 = 靠前，作为角色设定而不是末位附注）、text 是逐行拼进去的中文正文。
  // 这段文字是产品口径的一部分，改字要同步改 docs/接入说明.md 与检验清单。
  try {
    ctx.systemPrompt.section({
      name: 'hengce:persona',
      order: 0,
      text: [
        // 第 1-3 行：工具链的固定顺序——导入 → 分析 → 报告 → 看界面；
        // 顺序写死是为了让模型不要跳过校验直接分析（会拿到空工作区）。
        '你是「衡策」财务智能体的宿主侧助手。衡策通过四个工具完成全流程：',
        'hengce_import（导入四类 Excel 工作簿，契约校验）→ hengce_analyze（十五步分析）',
        '→ hengce_report（计算报告 md/html/PDF）→ hengce_open_ui（玻璃工作台地址）。',
        // 第 4 行：口径纪律（金额整数分、比率整数基点）+ 引用纪律（只引用检索到的
        // 条文，检索不到就说未检索到）+ 数据纪律（演示数据来自固定种子，
        // 不得虚构真实企业）。三条都是验收项，不能删。
        '口径纪律：金额一律整数分、比率一律整数基点；只引用检索到的'
        + '《管理会计应用指引》条文，检索不到就说未检索到；'
        + '演示数据全部来自固定种子，不得虚构真实企业；',
        // 第 5 行：校验失败时原样转述中文报错，禁止模型自行「猜测原因」改写，
        // 否则用户拿不到可定位的失败信息。
        '校验失败时把中文报错原样转告用户，不要臆测原因。',
      ].join('\n'),
    });
  } catch (e) {
    // persona 写不进只影响措辞，不影响功能，降级放行。
    console.error('[hengce] systemPrompt 注册失败：', e?.message || e);
  }

  // ---- ④ 卸载清理：带走 Python 子进程与路由 ----
  // dispose 是 cordis 的卸载钩子（禁用插件、热重载、进程退出都会走到）。
  // 三件事必须做：注销路由、注销首屏注入、杀掉 Python 子进程；漏掉任一项，
  // 热重载后会留下孤儿进程或重复路由（表现为请求被处理两次、状态对不上）。
  ctx.on('dispose', () => {
    // 逐个调用注销函数；重复注销是幂等的，失败也忽略（宿主可能先一步清过）。
    for (const che of zhuce) {
      try { che(); } catch { /* 已卸载则忽略 */ }
    }
    // 关 stdin 再 kill：先让 Python 侧读到 EOF 正常退出，再兜底强杀。
    qiao.guanbi();
  });
}
