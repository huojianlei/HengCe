// 衡策插件 · 独立服务（不依赖 dsh 宿主的演示/验收兜底）。
//
// 用法：node adapter/独立服务.mjs          → http://127.0.0.1:4180/hengce/
//       HENGCE_PORT=5000 node …           → 自定端口；仅绑本机回环。
// 与 dsh 宿主路由（index.ts）共用同一套处理器，行为完全一致。
//
// ---------------------------------------------------------------------------
// 【在链路的哪一环】
//   上游：浏览器直接访问本机 4180 端口（演示、验收、或 dsh 宿主 webserver
//         不可用时的手动兜底）；页面侧仍是 window.hengceHost（宿主桥.js）。
//   本层：只是「进程与端口」的外壳 —— 用 node:http 起服务，把请求交给
//         adapter/服务核心.mjs 的同一份处理器；路由、报错文案、缓存头
//         全部与宿主形态共用，不存在两套行为。
//   下游：Qiao（本进程唯一一个）→ backend/桥接入口.py。
//
// 【为什么要独立服务】
//   dsh 宿主 webserver 只在装了 dsh 桌面端的机器上存在；评委机/演示机、
//   纯 Node 环境、以及「宿主加载失败但要看界面」的排障场景，都需要一个
//   零依赖的启动方式：一条 node 命令即可，不需要插件框架。
//
// 【失败兜底】
//   · 端口被占用 → node:http 抛 EADDRINUSE 并退出（用 HENGCE_PORT 换端口）；
//   · 只绑 127.0.0.1：这是本机演示工具，不对外提供服务（也不该暴露财务数据）；
//   · 退出信号 → 先关 Python 子进程再退，避免留下孤儿 python.exe。
// ---------------------------------------------------------------------------
import { createServer } from 'node:http';
// 与本模块同目录的两个依赖：桥接（Python 行协议）、服务核心（HTTP 处理器）。
// 用相对路径 import：本文件既可 node 直跑，也可被测试脚本 import 后自起。
import { Qiao } from './桥接.mjs';
import { zao_chuliqi } from './服务核心.mjs';

// 端口：默认 4180，HENGCE_PORT 可覆盖（演示时避开占用，或一次起多个实例）。
// 4180 的取值理由：常见开发端口（3000/8080）在演示机上常被别的工具占用，
// 用一个不常用的高位端口，撞车概率低且一眼能认出是衡策。
const DUANKOU = Number(process.env.HENGCE_PORT || 4180);
// 本进程一个 Qiao：一次只能有一个 Python 桥子进程，串行协议见 桥接.mjs。
// 这不是限制而是设计：后端工作区是进程内单例，多进程会让状态各说各话。
const qiao = new Qiao();
// 处理器只造一次：内部持有注入后的 index.html 缓存（见 服务核心.mjs）。
const chuli = zao_chuliqi(qiao);

const fuwu = createServer((req, res) => {
  // 非本插件路径一律 404（独立服务只服务 /hengce/*）
  // 注意这里是前缀判断而非精确匹配：/hengce、/hengce/、/hengce/api 都要放进来，
  // 具体细分（补斜杠、404/403）由服务核心统一处理，本层不重复判断。
  if (!req.url.startsWith('/hengce')) {
    res.writeHead(404).end();
    return;
  }
  chuli(req, res);
});

// 只绑 127.0.0.1（回环）：不监听 0.0.0.0，局域网/外网无法访问。
// 财务数据 + 无鉴权，暴露到网卡上等于把工作区借给同网段所有人。
fuwu.listen(DUANKOU, '127.0.0.1', () => {
  // 地址与退出方式写进首行：Ctrl+C 是唯一的正常退出办法（见下方信号处理）。
  console.log(`衡策独立服务：http://127.0.0.1:${DUANKOU}/hengce/ （Ctrl+C 退出）`);
  // 两行提示：嵌入布局参数（页面侧行为）与状态落盘位置（用户排障时要找）。
  console.log('嵌入布局：加 ?embedded=1 ；工作区状态在 plugin/数据/ 下。');
});

// 退出时带走 Python 子进程（不留孤儿）
// 为什么要监听两个信号：Windows 控制台 Ctrl+C 是 SIGINT；任务管理器/服务管理器
// 结束进程是 SIGTERM。只处理一个会漏掉另一种退出方式，留下孤儿 python.exe。
for (const xin of ['SIGINT', 'SIGTERM']) {
  process.on(xin, () => {
    // 先关 Python（end stdin → kill，让后端落最后一次状态），再关 HTTP。
    qiao.guanbi();
    fuwu.close(() => process.exit(0));
    // 兜底强退：fuwu.close 要等在途连接全部结束，慢连接（长轮询/未关页面）
    // 会把它卡住；1.5 秒后无条件退出。unref() 让这个定时器不阻止进程自然退出。
    setTimeout(() => process.exit(0), 1500).unref();
  });
}
