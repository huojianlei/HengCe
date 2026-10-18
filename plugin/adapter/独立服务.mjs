// 衡策插件 · 独立服务（不依赖 dsh 宿主的演示/验收兜底）。
//
// 用法：node adapter/独立服务.mjs          → http://127.0.0.1:4180/hengce/
//       HENGCE_PORT=5000 node …           → 自定端口；仅绑本机回环。
// 与 dsh 宿主路由（index.ts）共用同一套处理器，行为完全一致。
import { createServer } from 'node:http';
import { Qiao } from './桥接.mjs';
import { zao_chuliqi } from './服务核心.mjs';

const DUANKOU = Number(process.env.HENGCE_PORT || 4180);
const qiao = new Qiao();
const chuli = zao_chuliqi(qiao);

const fuwu = createServer((req, res) => {
  // 非本插件路径一律 404（独立服务只服务 /hengce/*）
  if (!req.url.startsWith('/hengce')) {
    res.writeHead(404).end();
    return;
  }
  chuli(req, res);
});

fuwu.listen(DUANKOU, '127.0.0.1', () => {
  console.log(`衡策独立服务：http://127.0.0.1:${DUANKOU}/hengce/ （Ctrl+C 退出）`);
  console.log('嵌入布局：加 ?embedded=1 ；工作区状态在 plugin/数据/ 下。');
});

// 退出时带走 Python 子进程（不留孤儿）
for (const xin of ['SIGINT', 'SIGTERM']) {
  process.on(xin, () => {
    qiao.guanbi();
    fuwu.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 1500).unref();
  });
}
