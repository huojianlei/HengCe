// 衡策插件 · Python 桥接进程管理（Node 侧）。
//
// 职责：拉起并看护 backend/桥接入口.py（stdio JSON 行协议），
// 把宿主/页面的 action 请求串行转发过去；进程崩溃自动重启，
// 请求超时如实报错。文件字节在本层与 Python 层之间走 base64。
//
// 纪律：零 C 盘写；Python 只读执行 backend 下的程序。
//
// ---------------------------------------------------------------------------
// 【在链路的哪一环】
//   上游（发请求的一方，共两处，共用同一个 Qiao 实例）：
//     · adapter/服务核心.mjs —— HTTP 路由把 UI 的 POST /hengce/api 转成 action；
//     · index.ts / index.js —— 四个对话工具（hengce_import 等）直接调 action。
//   下游（收请求的一方）：backend/桥接入口.py 的 DONGZUO 分发表，16 个 action：
//     workspace.load / files.import / files.clear / files.remove /
//     templates.download / analysis.run / background.save / actions.update /
//     revisions.approve / app.uninstall / reports.generate / reports.export /
//     reports.openFolder / history.open / assistant.ask / hosting.apiKey。
//   再往下才是真正的业务：import_excel_v11 → fenxi → compute_report_pipeline。
//
// 【行协议（一问一答，两端各写各的 JSON 行）】
//   发：{"id":<数字>,"action":"<上表某个>","payload":{…}}\n
//   回：{"id":<同一个>,"ok":true,"data":…}\n
//     或 {"id":<同一个>,"ok":false,"error":"<中文报错原文>"}\n
//   单向 UTF-8、以 \n 分行；本层只做「按 id 配回包」，不做任何字段加工，
//   data 原样上抛给调用方（口径由 Python 侧定，金额分、比率基点）。
//   二进制（xlsx 内容、PDF 字节）在本协议里一律 base64 字符串：
//   JSON 不能承载 ArrayBuffer，且 base64 膨胀仅 4/3，比数组化数字省得多。
//
// 【失败兜底（每一层都要能说清是谁坏了）】
//   · 解释器找不到 → zhao_python 抛中文 Error，调用方把原文交给用户；
//   · 进程未起/已退出 → qdong() 惰性拉起；在途请求由 exit 回调以中文 reject；
//   · 单次请求超时 → qing 的 setTimeout 以「后端处理 X 超时（Ns）」reject，
//     waiter 置空防止迟到回包错配到下一个请求；
//   · 写 stdin 失败（管道已断）→ 以「后端连接已断开：…」reject，不静默吞掉；
//   · Python 业务错误（校验失败等）→ 由 ok:false 的 error 原文成 Error，
//     本层不改写、不翻译、不猜测原因（保底文案由 Python 侧说了算）。
// ---------------------------------------------------------------------------
import { spawn } from 'node:child_process';
// existsSync/readdirSync 只读探测：本文件从不写任何路径（含临时目录），
// 与「零 C 盘写」纪律一致——探测失败只返回 null，绝不 mkdir 兜底。
import { existsSync, readdirSync } from 'node:fs';
// homedir() 只参与「找不找得到 dsh 自带 Python」，不用于放任何产物。
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
// dirname(dirname(import.meta.url)) = 从 adapter/ 上翻一级到 plugin 根，
// 这样无论谁 import 本模块（服务核心 / 独立服务 / index）路径都算得对。
import { dirname, join } from 'node:path';

// plugin 根目录（本文件位于 plugin/adapter/，故上翻两级）
const BEN_MU = dirname(dirname(fileURLToPath(import.meta.url)));   // plugin 根
// 桥接入口脚本的绝对路径：Python 侧一律以 plugin/backend 为工作目录运行，
// 见 qdong() 的 cwd；cwd 不对会找不到 backend 内的相对数据目录。
const RUNNER = join(BEN_MU, 'backend', '桥接入口.py');

// dsh 桌面端自带托管 Python 的候选根（跨机器可发现：环境变量 → 本机数据目录 → 家目录）
// 顺序即优先级：环境变量最准（用户/安装器显式指定），其次是本机约定安装位置，
// 最后是家目录（官方桌面版在 Windows 上把 ~/.dsh 联接指向 D 盘数据目录）。
function dsh_yunxingshi() {
  const gen = [process.env.DSH_HOME,
    'D:\\dsh-desktop-data\\dsh-home',
    join(homedir(), '.dsh')].filter(Boolean);
  for (const gen_mu of gen) {
    // dsh-runtimes/<版本号>/dependencies/python/python.exe：
    // 版本号目录名不固定，所以遍历而不是写死某个版本。
    const yun = join(gen_mu, 'dsh-runtimes');
    if (!existsSync(yun)) continue;
    for (const ming of readdirSync(yun)) {
      const exe = join(yun, ming, 'dependencies', 'python', 'python.exe');
      if (existsSync(exe)) return exe;            // 第一个命中即用（每机一份 primary）
    }
  }
  return null;                                    // 没装 dsh 运行时（罕见）
}

// Python 解释器发现链（跨机器口径，见 挂载说明.md）：
//   ① HENGCE_PYTHON 显式指定
//   ② 本机开发环境（含 onnxruntime，条例检索满血——比赛机优先）
//   ③ dsh 自带托管 Python（任何装了 dsh 桌面端的机器都有 numpy+openpyxl，
//      主链全功能可用；缺 onnx 时条例检索自动降级为占位，不报错）
//   ④ PATH 里的 python
// 每条候选各自的取值理由：
//   ① 给部署方留后门：换解释器/换虚拟环境不用改代码；
//   ② 开发机（D:\dev-env\Python312）装了 onnxruntime，《管理会计应用指引》
//      的向量检索只有它才能真跑；缺它时降级为占位条目（不报错但会标注）；
//   ③ 交付机（只装了 dsh 桌面端的机器）没有 ②，但 dsh 自带 Python 带
//      numpy+openpyxl，足以跑导入/分析/报告主链；
//   ④ 最后兜底系统 PATH，兼容用户自行安装的 Python。
// 四级全落空才抛错，且报错文案直接告诉用户「怎么修」。
function zhao_python() {
  const houxuan = [
    process.env.HENGCE_PYTHON,
    'D:\\dev-env\\Python312\\python.exe',
    dsh_yunxingshi(),
    'python',
  ].filter(Boolean);
  for (const p of houxuan) {
    // 不带路径分隔符的是裸命令名（如 "python"），交给 spawn 走 PATH 解析，
    // 不能用 existsSync 判（那不是文件路径）；带分隔符的必须是真实文件。
    if (!/[\\/]/.test(p) || existsSync(p)) return p;
  }
  // 中文报错的两句：第一句给「怎么修」，括号里给「另一条路」——
  // 用户看不懂 stderr 堆栈，必须让这句话单独就能定位问题。
  throw new Error('找不到 Python 解释器：请设置 HENGCE_PYTHON 指向 python.exe'
    + '（或确认已安装 DeepSeek Harness 桌面端，其自带 Python 运行时）');
}

/** 行协议客户端：串行队列（Python 端单线程逐行处理，天然一问一答）。 */
// 为什么必须串行：Python 桥是单进程单 stdin，且后端工作区是进程内单例状态
// （导入册、分析结果、审批记录），并发写会让「先读配置再算」这类组合请求
// 读到半更新的状态。串行化在这里免费提供了互斥，代价是慢请求排队。
export class Qiao {
  constructor() {
    // proc：子进程句柄；null = 未启动或已崩溃（qdong 惰性拉起）
    // tail：请求串行链（后发的等先发的完成）
    // buf ：stdout 半行缓存（一行 JSON 可能分多段到达）
    // waiter：当前唯一一个「已发出、等回包」的请求（串行保证同时最多一个）
    this.proc = null;
    this.tail = Promise.resolve();      // 请求串行链（后发的等先发的完成）
    this.buf = '';
    this.waiter = null;                 // {resolve, reject, id} 当前等回包的请求
  }

  /** 确保 Python 进程在位；不在则拉起（重启即清空等待者）。 */
  // 惰性启动的理由：插件加载时（dsh 冷启动）不需要 Python，
  // 等到第一次真用（导入/分析）再付解释器启动的几百毫秒。
  qdong() {
    // 三重判活：句柄在、未被 kill、且尚未退出（exitCode === null）。
    // 少判任何一条都会出现「向已死进程写 stdin」或重复 spawn 两个后端。
    if (this.proc && !this.proc.killed && this.proc.exitCode === null) return;
    const exe = zhao_python();
    // 参数解析：
    //   '-B'        不写 __pycache__（保持 plugin/backend 目录只读干净，
    //               也避免交付包被 .pyc 污染）；
    //   cwd          backend/ —— Python 侧所有相对路径（数据/、报告/）都基于它，
    //               换成 plugin 根会写到别处去；
    //   env          显式 PYTHONIOENCODING=utf-8：Windows 中文系统控制台默认
    //               GBK，不设会把中文回包（含中文报错）编成乱码；
    //   stdio        ['pipe','pipe','pipe']：stdin 发请求、stdout 收回包、
    //               stderr 只作日志线索（见下方 on('data') 注释）。
    this.proc = spawn(exe, ['-B', RUNNER], {
      cwd: join(BEN_MU, 'backend'),
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    // 新进程 = 新流，上一代残留的半行必须丢弃，否则会与本代首行拼接成坏 JSON。
    this.buf = '';
    this.proc.stdout.setEncoding('utf-8');
    this.proc.stdout.on('data', (duan) => this._shou(duan));
    this.proc.stderr.setEncoding('utf-8');
    this.proc.stderr.on('data', (duan) => {
      // Python 端的业务错误走 stdout 回包；stderr 只留日志线索（不刷屏）
      // 截尾 600 字符：traceback 往往很长，但用户要看的是最后那行异常，
      // 完整堆栈交给 console 日志文件，控制台不淹没其它输出。
      const wen = duan.trim();
      if (wen) console.error('[hengce-python]', wen.slice(-600));
    });
    this.proc.on('exit', () => {
      // 在途请求必须被 reject（否则调用方永远等不到回包，界面/spinner 卡死）。
      // 「已自动重启」写进文案：下次请求 qdong() 会重新拉起，用户重试即可，
      // 不必手动重启插件——这句是给用户的操作指引，不是技术细节。
      const w = this.waiter;
      this.waiter = null;
      if (w) w.reject(new Error('衡策后端进程已退出，请重试（已自动重启）'));
      this.proc = null;
    });
  }

  /** stdout 分段 → 按行拆 → 交给当前等待者。 */
  // 为什么要缓冲：stdio 的 'data' 事件按「块」而非按「行」到达，
  // 一行 JSON 可能被拆成多段，也可能一次带好几行；必须以 \n 为界重组。
  _shou(duan) {
    this.buf += duan;
    let i;
    while ((i = this.buf.indexOf('\n')) >= 0) {
      const hang = this.buf.slice(0, i).trim();
      this.buf = this.buf.slice(i + 1);
      // 空行（心跳/续行）或当前无人等待（上一个请求已超时放弃）时丢弃。
      // 只认 id 匹配的行：防止上一请求的超时回包被错配给本请求。
      if (!hang || !this.waiter) continue;
      try {
        const da = JSON.parse(hang);
        if (da.id === this.waiter.id) {
          const w = this.waiter;
          this.waiter = null;
          // ok=false 时把 error 原文包成 Error：调用方/宿主模型看到的
          // 就是 Python 侧写好的中文报错，本层不翻译、不摘录、不补原因。
          if (da.ok) w.resolve(da.data);
          else w.reject(new Error(da.error || '后端返回未知错误'));
        }
      } catch { /* 非 JSON 行忽略（防御，正常不会出现） */ }
    }
  }

  /** 发一个 action 请求（串行 + 超时；崩溃由 exit 回调重启后可重试）。 */
  // 参数：action = DONGZUO 分发表里的键名（拼错会被 Python 回 ok:false）；
  //       payload = 该 action 的入参对象（形状由 Python 侧定，本层透传）；
  //       haoshi  = 单次超时毫秒，默认 300000（5 分钟）：十五步分析 + 报告
  //                 （含 Chrome 无头打印 PDF）在慢机上就是这个量级；
  //                 AI 解读逐模块串行可能更久，调用方可显式传更大值。
  // 返回：Promise，resolve 为 Python 的 data 原样对象；reject 为中文 Error。
  // 副作用：可能拉起子进程、写 stdin、占用串行链（后续请求排队）。
  qing(action, payload = {}, haoshi = 300000) {
    // .catch(() => {}) 是队列自愈：上一个请求 reject 后不能让它污染链条，
    // 否则一次失败会把后续所有请求都带崩（链式 promise 的经典坑）。
    this.tail = this.tail.catch(() => {}).then(() => new Promise((resolve, reject) => {
      this.qdong();
      // id 用「时间戳 + 6 位随机数」而非自增计数：重启进程后自增计数可能
      // 与上一代撞号（Python 侧只看当前行的 id），随机后缀把撞号概率压到极低。
      const id = Date.now() + Math.floor(Math.random() * 1e6);
      this.waiter = { resolve, reject, id };
      // 超时定时器：到点若 waiter 仍是本请求（id 相同）才 reject，
      // 避免「回包刚好到了、定时器也响了」时把已完成的请求二次 reject。
      const shoukong = setTimeout(() => {
        if (this.waiter && this.waiter.id === id) {
          this.waiter = null;
          // 文案带 action 名与秒数：用户/日志能立刻分清是哪个动作超时、
          // 等了多久，便于判断是「后端卡住」还是「超时给太短」。
          reject(new Error(`后端处理 ${action} 超时（${haoshi / 1000}s）`));
        }
      }, haoshi);
      // 统一收尾：无论成功失败先清定时器（否则进程被定时器 keep-alive 拖住）。
      const jie = (f) => { clearTimeout(shoukong); f(); };
      this.waiter.resolve = (v) => jie(() => resolve(v));
      this.waiter.reject = (e) => jie(() => reject(e));
      // 单行 JSON + \n 是协议的唯一分隔符；payload 必须可 JSON 序列化，
      // 二进制已在上游转成 base64（见本文件头「行协议」说明）。
      try {
        this.proc.stdin.write(JSON.stringify({ id, action, payload }) + '\n');
      } catch (e) {
        // 管道已断（Python 刚崩但 exit 事件还没派发到）：立刻失败并清 waiter，
        // 与 exit 回调的清理互斥——谁先到谁负责 reject，另一个看到 waiter 为空就跳过。
        this.waiter = null;
        reject(new Error(`后端连接已断开：${e.message}`));
      }
    }));
    return this.tail;
  }

  /** 关停子进程（插件卸载/服务退出时调用）。 */
  // 顺序有讲究：先 end() 关 stdin，让 Python 侧读到 EOF 走正常退出分支
  // （_huifu 会落盘一次状态），再 kill() 兜底强杀；反过来先 kill 会丢最后一次状态。
  // 两步都 try/catch：进程可能已被系统回收或从未启动（proc 为 null 时直接跳过）。
  guanbi() {
    if (this.proc) {
      try { this.proc.stdin.end(); } catch { /* 已断开 */ }
      this.proc.kill();
      this.proc = null;
    }
  }
}
