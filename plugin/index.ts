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
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { Qiao } from './adapter/桥接.mjs';
import { zao_chuliqi } from './adapter/服务核心.mjs';

export const name = 'hengce';

// webServer=托管界面；tools=AI 全流程控制四工具；systemPrompt=衡策 persona
export const inject = ['webServer', 'tools', 'systemPrompt'];

// 工具与界面共用一个 Python 桥进程（行协议串行，天然互斥）
const qiao = new Qiao();

export function apply(ctx: any) {
  // ---- ① 界面：宿主 webserver 前缀路由 /hengce/* ----
  const chuli = zao_chuliqi(qiao);
  const zhuce: Array<() => void> = [];
  try {
    ctx.inject(['webServer'], (host: any) => {
      zhuce.push(host.webServer.register({
        kind: 'prefix', path: '/hengce', handler: chuli,
      } as any));
    });
  } catch (e: any) {
    console.error('[hengce] webServer 挂载失败（界面不可用，工具仍可用）：', e?.message || e);
  }

  // ---- ② AI 全流程控制：四个工具（对话里即可驱动导入→分析→报告→看界面）----
  const gongju = [
    {
      name: 'hengce_import',
      description: '导入一本衡策 Excel 工作簿（预算基础/实时经营/行业对标/经营变更，'
        + '四类之一，按工作簿内容自动识别）。传入本机 .xlsx 绝对路径。',
      parameters: {
        type: 'object',
        properties: {
          lu_jing: { type: 'string', description: 'xlsx 文件绝对路径' },
        },
        required: ['lu_jing'],
      },
      async execute(args: { lu_jing: string }) {
        const jie = await qiao.qing('files.import', {
          files: [{
            name: args.lu_jing.split(/[\\/]/).pop() || '工作簿.xlsx',
            bytesB64: (await readFile(args.lu_jing)).toString('base64'),
          }],
          mode: 'append',
        });
        const ce = jie.files[jie.files.length - 1];
        return `已导入并校验通过：${ce.name} ｜ 类别 ${ce.category} ｜ 校验 ${ce.checks} 项 ｜ `
          + `入库 ${ce.rows} 行 ｜ 主体 ${ce.entity}。`
          + (jie.dirty ? '（输入已变更，请重新运行 hengce_analyze）' : '');
      },
    },
    {
      name: 'hengce_analyze',
      description: '对已导入的「预算基础 + 实时经营」两册运行十五步分析'
        + '（滚动预算/差异预警/积木/KPI/整改清单）。'
        + '可选配置：cycle(月度|季度)、period(如 2027-06)、growth(企业增长率基点)。',
      parameters: {
        type: 'object',
        properties: {
          cycle: { type: 'string', description: '月度 或 季度（缺省沿用当前配置）' },
          period: { type: 'string', description: '分析末档，如 2027-06 / 2027-Q2' },
          growth: { type: 'number', description: '企业增长率（基点，0=不增长）' },
        },
      },
      async execute(args: { cycle?: string; period?: string; growth?: number }) {
        const dang = await qiao.qing('workspace.load', {});
        const pei: Record<string, unknown> = { ...(dang.config || {}) };
        for (const jian of ['cycle', 'period', 'growth'] as const) {
          if (args[jian] !== undefined && args[jian] !== null) pei[jian] = args[jian];
        }
        const jie = await qiao.qing('analysis.run', { entityId: 'all', config: pei });
        const yuj = jie.rows.filter((r: any) => r.risk !== 'normal').length;
        return `分析完成：主体 ${jie.meta.company} ｜ 期间 ${jie.meta.period} ｜ `
          + `差异行 ${jie.rows.length}（预警 ${yuj}）｜ 整改 ${jie.actions.length} 条 ｜ `
          + `滚动期数 ${jie.trend.length}。运行号 ${jie.meta.runId}。`
          + (jie.warnings?.length ? ` 提示：${jie.warnings.join('；')}` : '');
      },
    },
    {
      name: 'hengce_report',
      description: '对最近一次分析运行生成计算报告（md + html + PDF，'
        + '含 9 个模块的数据表/分析/《管理会计应用指引》依据条例）并返回报告号。',
      parameters: { type: 'object', properties: {} },
      async execute() {
        const jie = await qiao.qing('reports.generate', {});
        const bao = jie.reports[0];
        return `报告已生成：${bao.title} ｜ ${bao.pages ?? '?'} 页 ｜ 报告号 ${bao.id}。`
          + '文件在 plugin/数据/报告/ 下（md/html/pdf 三格式）；'
          + '界面内可预览与导出（见 hengce_open_ui 给出的地址）。';
      },
    },
    {
      name: 'hengce_open_ui',
      description: '给出衡策玻璃工作台的访问地址（宿主 webserver 或独立服务两种形态）。'
        + '打开地址即可操作界面，与工具共用同一后端。',
      parameters: { type: 'object', properties: {} },
      async execute() {
        let duankou = 0;
        try {
          ctx.inject(['webServer'], (host: any) => {
            duankou = host.webServer?.config?.port || 0;
          });
        } catch { /* 端口探测失败给出独立服务指引 */ }
        if (duankou) {
          return `衡策工作台地址（宿主 webserver）：http://127.0.0.1:${duankou}/hengce/`
            + '\n嵌入布局：http://127.0.0.1:' + duankou + '/hengce/?embedded=1';
        }
        return '未探测到宿主 webserver 端口。兜底：在 plugin 目录运行 '
          + '"node adapter/独立服务.mjs"，然后访问 http://127.0.0.1:4180/hengce/';
      },
    },
  ];
  for (const g of gongju) {
    try {
      ctx.tools.register(g as any);
    } catch (e: any) {
      console.error(`[hengce] 工具 ${g.name} 注册失败：`, e?.message || e);
    }
  }

  // ---- ③ persona：让宿主模型知道衡策的口径与边界 ----
  try {
    ctx.systemPrompt.section({
      name: 'hengce:persona',
      order: 0,
      text: [
        '你是「衡策」财务智能体的宿主侧助手。衡策通过四个工具完成全流程：',
        'hengce_import（导入四类 Excel 工作簿，契约校验）→ hengce_analyze（十五步分析）',
        '→ hengce_report（计算报告 md/html/PDF）→ hengce_open_ui（玻璃工作台地址）。',
        '口径纪律：金额一律整数分、比率一律整数基点；只引用检索到的'
        + '《管理会计应用指引》条文，检索不到就说未检索到；'
        + '演示数据全部来自固定种子，不得虚构真实企业；',
        '校验失败时把中文报错原样转告用户，不要臆测原因。',
      ].join('\n'),
    });
  } catch (e: any) {
    console.error('[hengce] systemPrompt 注册失败：', e?.message || e);
  }

  // ---- ④ 卸载清理：带走 Python 子进程与路由 ----
  ctx.on('dispose', () => {
    for (const che of zhuce) {
      try { che(); } catch { /* 已卸载则忽略 */ }
    }
    qiao.guanbi();
  });
}
