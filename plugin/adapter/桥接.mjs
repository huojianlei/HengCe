// 衡策插件 · Python 桥接进程管理（Node 侧）。
//
// 职责：拉起并看护 backend/桥接入口.py（stdio JSON 行协议），
// 把宿主/页面的 action 请求串行转发过去；进程崩溃自动重启，
// 请求超时如实报错。文件字节在本层与 Python 层之间走 base64。
//
// 纪律：零 C 盘写；Python 只读执行 backend 下的程序。
import { spawn } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const BEN_MU = dirname(dirname(fileURLToPath(import.meta.url)));   // plugin 根
const RUNNER = join(BEN_MU, 'backend', '桥接入口.py');

// dsh 桌面端自带托管 Python 的候选根（跨机器可发现：环境变量 → 本机数据目录 → 家目录）
function dsh_yunxingshi() {
  const gen = [process.env.DSH_HOME,
    'D:\\dsh-desktop-data\\dsh-home',
    join(homedir(), '.dsh')].filter(Boolean);
  for (const gen_mu of gen) {
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
function zhao_python() {
  const houxuan = [
    process.env.HENGCE_PYTHON,
    'D:\\dev-env\\Python312\\python.exe',
    dsh_yunxingshi(),
    'python',
  ].filter(Boolean);
  for (const p of houxuan) {
    if (!/[\\/]/.test(p) || existsSync(p)) return p;
  }
  throw new Error('找不到 Python 解释器：请设置 HENGCE_PYTHON 指向 python.exe'
    + '（或确认已安装 DeepSeek Harness 桌面端，其自带 Python 运行时）');
}

/** 行协议客户端：串行队列（Python 端单线程逐行处理，天然一问一答）。 */
export class Qiao {
  constructor() {
    this.proc = null;
    this.tail = Promise.resolve();      // 请求串行链（后发的等先发的完成）
    this.buf = '';
    this.waiter = null;                 // {resolve, reject, id} 当前等回包的请求
  }

  /** 确保 Python 进程在位；不在则拉起（重启即清空等待者）。 */
  qdong() {
    if (this.proc && !this.proc.killed && this.proc.exitCode === null) return;
    const exe = zhao_python();
    this.proc = spawn(exe, ['-B', RUNNER], {
      cwd: join(BEN_MU, 'backend'),
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    this.buf = '';
    this.proc.stdout.setEncoding('utf-8');
    this.proc.stdout.on('data', (duan) => this._shou(duan));
    this.proc.stderr.setEncoding('utf-8');
    this.proc.stderr.on('data', (duan) => {
      // Python 端的业务错误走 stdout 回包；stderr 只留日志线索（不刷屏）
      const wen = duan.trim();
      if (wen) console.error('[hengce-python]', wen.slice(-600));
    });
    this.proc.on('exit', () => {
      const w = this.waiter;
      this.waiter = null;
      if (w) w.reject(new Error('衡策后端进程已退出，请重试（已自动重启）'));
      this.proc = null;
    });
  }

  /** stdout 分段 → 按行拆 → 交给当前等待者。 */
  _shou(duan) {
    this.buf += duan;
    let i;
    while ((i = this.buf.indexOf('\n')) >= 0) {
      const hang = this.buf.slice(0, i).trim();
      this.buf = this.buf.slice(i + 1);
      if (!hang || !this.waiter) continue;
      try {
        const da = JSON.parse(hang);
        if (da.id === this.waiter.id) {
          const w = this.waiter;
          this.waiter = null;
          if (da.ok) w.resolve(da.data);
          else w.reject(new Error(da.error || '后端返回未知错误'));
        }
      } catch { /* 非 JSON 行忽略（防御，正常不会出现） */ }
    }
  }

  /** 发一个 action 请求（串行 + 超时；崩溃由 exit 回调重启后可重试）。 */
  qing(action, payload = {}, haoshi = 300000) {
    this.tail = this.tail.catch(() => {}).then(() => new Promise((resolve, reject) => {
      this.qdong();
      const id = Date.now() + Math.floor(Math.random() * 1e6);
      this.waiter = { resolve, reject, id };
      const shoukong = setTimeout(() => {
        if (this.waiter && this.waiter.id === id) {
          this.waiter = null;
          reject(new Error(`后端处理 ${action} 超时（${haoshi / 1000}s）`));
        }
      }, haoshi);
      const jie = (f) => { clearTimeout(shoukong); f(); };
      this.waiter.resolve = (v) => jie(() => resolve(v));
      this.waiter.reject = (e) => jie(() => reject(e));
      try {
        this.proc.stdin.write(JSON.stringify({ id, action, payload }) + '\n');
      } catch (e) {
        this.waiter = null;
        reject(new Error(`后端连接已断开：${e.message}`));
      }
    }));
    return this.tail;
  }

  /** 关停子进程（插件卸载/服务退出时调用）。 */
  guanbi() {
    if (this.proc) {
      try { this.proc.stdin.end(); } catch { /* 已断开 */ }
      this.proc.kill();
      this.proc = null;
    }
  }
}
