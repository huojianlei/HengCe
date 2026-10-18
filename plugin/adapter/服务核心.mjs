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
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, normalize, sep } from 'node:path';

const BEN_MU = dirname(dirname(fileURLToPath(import.meta.url)));   // plugin 根
const UI_MU = join(BEN_MU, 'ui');

// 轻量 mime 表（UI 全集：html/css/mjs/js/svg/png/json/md）
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
async function du_index() {
  const yuan = await readFile(join(UI_MU, 'index.html'), 'utf-8');
  const zhu = '<script src="./宿主桥.js"></script>\n  ';
  const m = yuan.match(/<script type="module"/);
  if (!m) throw new Error('ui/index.html 里找不到模块脚本注入点');
  return yuan.replace(m[0], zhu + m[0]);
}

/** POST body → JSON（上限 64MB，导入 xlsx 走 base64 后足够）。 */
function du_qingtiu(req) {
  return new Promise((resolve, reject) => {
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
        const wen = Buffer.concat(kuai).toString('utf-8');
        resolve(wen ? JSON.parse(wen) : {});
      } catch (e) {
        reject(new Error(`请求体不是合法 JSON：${e.message}`));
      }
    });
    req.on('error', reject);
  });
}

/** 统一 JSON 出口（no-store，避免工作区状态被缓存）。 */
function xie_json(res, zhuangtai, duixiang) {
  res.writeHead(zhuangtai, { 'content-type': 'application/json; charset=utf-8',
                             'cache-control': 'no-store' });
  res.end(JSON.stringify(duixiang));
}

/** 造一个 HTTP 处理器：prefix 路由（dsh 宿主）与独立服务共用。 */
export function zao_chuliqi(qiao) {
  let huan_index = null;                     // 注入后的 index（进程内缓存）
  return async function hengce_chuli(req, res) {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      let lu = url.pathname;                      // WHATWG URL 保留百分号编码
      try { lu = decodeURIComponent(lu); } catch { /* 非法转义按原样处理 */ }
      if (lu === '/hengce') lu = '/hengce/';
      if (!lu.startsWith('/hengce/')) {
        res.writeHead(404).end();
        return;
      }
      // ① 入口页（注入宿主桥）
      if (lu === '/hengce/' || lu === '/hengce/index.html') {
        if (!huan_index) huan_index = await du_index();
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8',
                             'cache-control': 'no-store' });
        res.end(huan_index);
        return;
      }
      // ② 宿主桥脚本
      if (lu === '/hengce/宿主桥.js') {
        const ma = await readFile(join(BEN_MU, 'adapter', '宿主桥.js'));
        res.writeHead(200, { 'content-type': 'text/javascript; charset=utf-8',
                             'cache-control': 'no-store' });
        res.end(ma);
        return;
      }
      // ③ API：POST {action, payload}
      if (lu === '/hengce/api') {
        if (req.method !== 'POST') {
          xie_json(res, 405, { ok: false, error: '只接受 POST' });
          return;
        }
        const ti = await du_qingtiu(req);
        if (!ti.action) {
          xie_json(res, 400, { ok: false, error: '缺少 action' });
          return;
        }
        try {
          const data = await qiao.qing(ti.action, ti.payload || {});
          xie_json(res, 200, { ok: true, data });
        } catch (e) {
          xie_json(res, 200, { ok: false, error: e.message });
        }
        return;
      }
      // ④ 其余静态文件（仅 ui/ 目录内，防路径穿越）
      const xiangdui = normalize(lu.slice('/hengce/'.length)).replaceAll('\\', '/');
      const mu = join(UI_MU, ...xiangdui.split('/'));
      const guifan = normalize(mu);
      if (!guifan.startsWith(normalize(UI_MU) + sep)) {
        res.writeHead(403).end();
        return;
      }
      if (!existsSync(guifan) || !guifan.includes(sep)) {
        res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
        res.end('文件不存在');
        return;
      }
      const hou = guifan.slice(guifan.lastIndexOf('.')).toLowerCase();
      res.writeHead(200, { 'content-type': MIME[hou] || 'application/octet-stream',
                           'cache-control': 'no-store' });
      res.end(await readFile(guifan));
    } catch (e) {
      // 兜底：任何异常都以中文 JSON 报出（页面侧会转成可读错误）
      try { xie_json(res, 500, { ok: false, error: `衡策服务异常：${e.message}` }); }
      catch { /* 响应已发出则忽略 */ }
    }
  };
}
