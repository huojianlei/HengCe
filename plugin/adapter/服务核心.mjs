// 衡策插件 · HTTP 服务核心（dsh 宿主路由与独立服务共用）。
//
// 职责：
//   /hengce[/]           → 注入宿主桥脚本的 index.html（UI 唯一改动点）
//   /hengce/宿主桥.js     → 页面侧 hengceHost 实现（fetch 同源 /hengce/api）
//   /hengce/api          → POST {action, payload} → Python 桥 → {ok, data|error}
//   /hengce/<静态路径>    → ui/ 目录文件（路径穿越防护，仅本目录）
//
// 两种宿主形态共用本模块：
//   ① dsh 插件 index.ts：host.webServer.register({kind:'prefix', path:'/hengce'})
//   ② 独立服务.mjs：node:http 自起端口（演示/验收兜底，不依赖 dsh）
//
// ---------------------------------------------------------------------------
// 【在链路的哪一环】
//   上游：浏览器/宿主内嵌视图（页面侧 window.hengceHost，见 宿主桥.js）
//         —— 所有业务请求都打成 POST /hengce/api {action, payload}；
//   本层：只做「HTTP 语义 ↔ 行协议」的翻译与静态资源托管，不碰业务字段；
//   下游：Qiao（adapter/桥接.mjs）→ backend/桥接入口.py 的 DONGZUO 分发表。
//
// 【为什么两种形态共用一份实现】
//   宿主路由（dsh webServer 前缀路由）与独立服务（node:http，默认 4180）如果
//   各写一遍，路由表、中文报错文案、缓存头、路径穿越防护会逐渐分叉，
//   验收时「宿主里能跑、独立服务里不行」的差异最难查。共用一份 = 单一事实来源。
//
// 【响应约定（页面侧据此判成败）】
//   成功：HTTP 200 + {"ok":true,"data":<Python 的 data 原样>}
//   业务失败：HTTP 200 + {"ok":false,"error":"<Python 中文报错原文>"}
//     ——业务失败刻意不用 4xx/5xx：页面侧只认 ok 字段，且不想让浏览器
//       把中文报错替换成自己的错误页；HTTP 层错误（405/400/403/404/500）
//       只用于「请求本身不合法/服务自身坏了」这两种情况。
//   一律 cache-control: no-store：工作区状态、报告列表都是实时数据，
//   一旦被中间缓存复用，用户看到的就是上一次的账。
//
// 【失败兜底】
//   · ui/index.html 缺注入点 → du_index 抛中文 Error，入口页 500 并说明原因；
//   · 请求体超限/非 JSON → 分别回 64MB 上限、非法 JSON 的中文提示；
//   · Python 侧报错 → 原文透传成 error，本层不改写（口径由后端定）；
//   · 处理器内部任何未预期异常 → 最外层 catch 统一转 500 中文 JSON。
// ---------------------------------------------------------------------------
import { readFile } from 'node:fs/promises';
// existsSync 只做静态文件存在性探测：不存在回 404，绝不在服务侧建目录补文件。
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
// normalize + sep 是路径穿越防护的关键：normalize 消掉 ../，sep 保证
// 前缀比较是「目录级」而不是「字符串前缀」（否则 ui-x/ 会冒充 ui/）。
import { dirname, join, normalize, sep } from 'node:path';

// plugin 根（本文件在 plugin/adapter/，上翻两级）
const BEN_MU = dirname(dirname(fileURLToPath(import.meta.url)));   // plugin 根
// UI 根：所有静态资源只从这里出，其它目录一律 403/404。
const UI_MU = join(BEN_MU, 'ui');

// 轻量 mime 表（UI 全集：html/css/mjs/js/svg/png/json/md）
// 不引入 mime 依赖：树外插件按「零依赖」交付（桌面档 file:// 挂载拿不到
// harness 的 node_modules）；表里没有的类型统一 octet-stream 让浏览器下载。
// 文本类型都显式带 charset=utf-8：中文界面乱码几乎都是漏了这个参数。
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
};

/** 读一次 index.html 并注入宿主桥（模块脚本之前，确保 hengceHost 先就位）。 */
// 为什么要在服务端注入、而不是在 index.html 里直接写死 <script>：
//   UI 是「宿主可替换」的一层，宿主桥的 URL 由宿主决定（/hengce/宿主桥.js），
//   注入点只此一处，UI 侧零改动；以后换宿主形态只动这里。
// 为什么必须插在 type="module" 之前：
//   模块脚本是延迟执行且按文档顺序，但 hengceHost 是 UI 模块脚本一加载就要
//   用到的全局对象；放前面（普通脚本同步执行）才能保证「先有桥、后有 UI」。
async function du_index() {
  const yuan = await readFile(join(UI_MU, 'index.html'), 'utf-8');
  // 相对路径 ./宿主桥.js：入口可能是 /hengce 或 /hengce/，相对路径两种情况都对。
  const zhu = '<script src="./宿主桥.js"></script>\n  ';
  const m = yuan.match(/<script type="module"/);
  // 找不到注入点说明 UI 的入口脚本被改动过——必须显式报错，
  // 否则页面会「能打开但 hengceHost 不存在」，报错位置飘到浏览器控制台，极难排查。
  if (!m) throw new Error('ui/index.html 里找不到模块脚本注入点');
  return yuan.replace(m[0], zhu + m[0]);
}

/** POST body → JSON（上限 64MB，导入 xlsx 走 base64 后足够）。 */
// 上限为什么是 64MB：单本 xlsx 常见几 MB，base64 后 ×4/3；留一个量级余量
// 既够多册合并导入，又能在误传大文件时及早拒绝（不把内存吃满）。
// 超限时 req.destroy()：立刻断开连接，避免客户端继续往管道里写数据。
function du_qingtiu(req) {
  return new Promise((resolve, reject) => {
    // 分块累积：不能假设一次 data 事件收全（body 可能分多段到达）。
    const kuai = [];
    let n = 0;
    req.on('data', (c) => {
      n += c.length;
      if (n > 64 * 1024 * 1024) {
        reject(new Error('请求体超过 64MB 上限'));
        req.destroy();
        return;
      }
      kuai.push(c);
    });
    req.on('end', () => {
      try {
        // 空 body 视为 {}：部分 action（如 workspace.load）不需要入参，
        // 允许页面直接 POST 空体，少写一行 JSON。
        const wen = Buffer.concat(kuai).toString('utf-8');
        resolve(wen ? JSON.parse(wen) : {});
      } catch (e) {
        // 带上 JSON.parse 的原始 message（含出错位置），便于定位是哪个前端拼坏了包。
        reject(new Error(`请求体不是合法 JSON：${e.message}`));
      }
    });
    // 连接中断（客户端关页面）：让上层 catch 收尾，避免 Promise 永久挂起。
    req.on('error', reject);
  });
}

/** 统一 JSON 出口（no-store，避免工作区状态被缓存）。 */
// 集中在此写头：内容类型与缓存策略只用维护一处，杜绝某个分支漏掉 no-store
// 导致「刷新看到旧账」这类只在个别接口复现的诡异问题。
function xie_json(res, zhuangtai, duixiang) {
  res.writeHead(zhuangtai, { 'content-type': 'application/json; charset=utf-8',
                             'cache-control': 'no-store' });
  res.end(JSON.stringify(duixiang));
}

/** 造一个 HTTP 处理器：prefix 路由（dsh 宿主）与独立服务共用。 */
// 参数 qiao：adapter/桥接.mjs 的 Qiao 实例（由调用方注入，本模块不 new，
//   以保证「宿主路由」和「独立服务」两条路径共用同一个 Python 子进程/串行链）。
// 返回：(req, res) => Promise<void> 的处理器；永不 throw（全包在 try/catch 内）。
export function zao_chuliqi(qiao) {
  // 注入后的入口页在进程内缓存：index.html 是静态文件，但每次读盘 + 正则
  // 替换在首屏路径上是纯浪费；代价是「改了 index.html 需重启插件才生效」，
  // 与热重载节奏一致，可接受。
  let huan_index = null;                     // 注入后的 index（进程内缓存）
  return async function hengce_chuli(req, res) {
    try {
      // 只取 pathname：查询串（?embedded=1 等）只影响页面侧渲染，服务端不看。
      const url = new URL(req.url, 'http://127.0.0.1');
      let lu = url.pathname;                      // WHATWG URL 保留百分号编码
      // 解码成真实文件名：中文静态资源（宿主桥.js 等）必须解码后才能落到 ui/。
      try { lu = decodeURIComponent(lu); } catch { /* 非法转义按原样处理 */ }
      // 裸前缀补斜杠：/hengce → /hengce/，否则后续 startsWith('/hengce/') 会误判，
      // 也让页面里的相对路径（./宿主桥.js）解析到错误的父目录。
      if (lu === '/hengce') lu = '/hengce/';
      // 严格前缀校验：本处理器只服务 /hengce/ 下的路径；其它路径回 404，
      // 不去抢宿主的其余路由（dsh 其它页面还要用这台 webserver）。
      if (!lu.startsWith('/hengce/')) {
        res.writeHead(404).end();
        return;
      }
      // ① 入口页（注入宿主桥）
      // index.html 与目录路径等价；缓存命中则跳过读盘与正则替换。
      if (lu === '/hengce/' || lu === '/hengce/index.html') {
        if (!huan_index) huan_index = await du_index();
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8',
                             'cache-control': 'no-store' });
        res.end(huan_index);
        return;
      }
      // ② 宿主桥脚本
      // 单独一条路由而不走 ui/ 静态分支：桥的实现属于 adapter 层，
      // 但必须与页面同源（才能直接 fetch /hengce/api 且共享 cookie/来源）。
      if (lu === '/hengce/宿主桥.js') {
        const ma = await readFile(join(BEN_MU, 'adapter', '宿主桥.js'));
        res.writeHead(200, { 'content-type': 'text/javascript; charset=utf-8',
                             'cache-control': 'no-store' });
        res.end(ma);
        return;
      }
      // ③ API：POST {action, payload}
      // 这是唯一的业务通道：action 名必须命中 Python DONGZUO 分发表
      // （拼错不会在这里拦，由后端回 ok:false 的中文报错，本层只透传）。
      if (lu === '/hengce/api') {
        // 只接受 POST：GET 会被浏览器预取/缓存，把业务调用当资源请求是错误设计。
        if (req.method !== 'POST') {
          xie_json(res, 405, { ok: false, error: '只接受 POST' });
          return;
        }
        // 解析体；缺 action 说明前端拼包坏了，直接 400 并说清缺什么。
        const ti = await du_qingtiu(req);
        if (!ti.action) {
          xie_json(res, 400, { ok: false, error: '缺少 action' });
          return;
        }
        // payload 缺省补 {}：workspace.load / reports.generate 这类无参 action
        // 页面可以只发 action，少拼一层。
        try {
          const data = await qiao.qing(ti.action, ti.payload || {});
          xie_json(res, 200, { ok: true, data });
        } catch (e) {
          // 刻意仍用 HTTP 200：页面侧按 ok 字段统一处理（见文件头响应约定），
          // 非 2xx 会让部分浏览器的 fetch 包装层改抛网络错误，反而丢掉中文原文。
          xie_json(res, 200, { ok: false, error: e.message });
        }
        return;
      }
      // ④ 其余静态文件（仅 ui/ 目录内，防路径穿越）
      // 两步消解：normalize 吃掉 ../，再用 sep 做目录级前缀比较。
      const xiangdui = normalize(lu.slice('/hengce/'.length)).replaceAll('\\', '/');
      const mu = join(UI_MU, ...xiangdui.split('/'));
      const guifan = normalize(mu);
      // 403 而非 404：命中这个分支说明客户端在尝试越权读文件（../ 之类），
      // 明确拒绝比假装不存在更有诊断价值（也便于安全审查留痕）。
      if (!guifan.startsWith(normalize(UI_MU) + sep)) {
        res.writeHead(403).end();
        return;
      }
      // 双重判存：文件存在 + 含分隔符（防止 UI_MU 本身被当成文件返回）。
      if (!existsSync(guifan) || !guifan.includes(sep)) {
        res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
        res.end('文件不存在');
        return;
      }
      // 扩展名小写后查表；表外类型给 octet-stream（浏览器下载而不是乱解析）。
      const hou = guifan.slice(guifan.lastIndexOf('.')).toLowerCase();
      res.writeHead(200, { 'content-type': MIME[hou] || 'application/octet-stream',
                           'cache-control': 'no-store' });
      // 返回原始 Buffer：图片/字体等二进制不能转字符串，交给 Node 原样写出。
      res.end(await readFile(guifan));
    } catch (e) {
      // 兜底：任何异常都以中文 JSON 报出（页面侧会转成可读错误）
      // 内层再包 try/catch：响应可能已发出（头已 writeHead），
      // 此时再写会抛 ERR_STREAM_WRITE_AFTER_END，只能忽略——不能让它冒泡成未捕获异常。
      try { xie_json(res, 500, { ok: false, error: `衡策服务异常：${e.message}` }); }
      catch { /* 响应已发出则忽略 */ }
    }
  };
}
