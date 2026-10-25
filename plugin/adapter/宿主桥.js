// 衡策界面 · 宿主桥（由插件服务下发，独立打开 ui/ 时不存在 → 演示模式）。
//
// 实现 接入说明 §2 的 window.hengceHost：所有业务请求走同源
// /hengce/api（POST JSON），文件字节在本层做 ArrayBuffer ↔ base64，
// 协议失败一律 reject 中文 Error（不回退演示数据）。
//
// ---------------------------------------------------------------------------
// 【在链路的哪一环】
//   上游：ui/ 里的页面脚本 —— 只依赖 window.hengceHost 这一个全局对象，
//         不直接 fetch、不感知宿主形态（宿主 webserver 还是独立服务 4180）。
//   本层：页面侧协议适配器。三件事：① 拼 POST /hengce/api {action,payload}；
//         ② 把二进制按协议转 base64（上行 +B64 键名、下行 bytesB64→ArrayBuffer）；
//         ③ 把 HTTP/JSON 层的失败统一收敛成中文 Error。
//   下游：adapter/服务核心.mjs（同源 /hengce/api）→ Qiao → Python 后端。
//
// 【为什么由服务端下发而不是打包进 ui/】
//   桥必须与页面同源才能直接 fetch('/hengce/api')；而「同源地址由谁托管」
//   是宿主决定的。服务端下发（见 服务核心.mjs 的第 ② 条路由）让 ui/ 完全
//   不知道宿主形态；脱离衡策服务直接双击打开 ui/index.html 时这个脚本不存在，
//   页面自然落到演示模式（这是有意的降级，不是 bug）。
//
// 【失败兜底：三条都必须 reject，绝不回退演示数据】
//   ① 网络不通（宿主没起/端口错）→「无法连接衡策宿主服务：…」；
//   ② 响应不是 JSON（被代理/网关改写，或页面被直接当文件打开）→ 带 HTTP 状态；
//   ③ 业务失败（ok:false）→ 优先用后端的中文 error 原文，没有才用状态码兜底。
//   为什么不回退演示数据：财务数字回退会让人把假数当成真账，比报错危险得多。
// ---------------------------------------------------------------------------
(function () {
  'use strict';
  // 幂等保护：宿主可能在别的插件里也注入过同名桥（或页面重复加载脚本），
  // 已存在就保持先来者——覆盖会让「谁在响应请求」变得不可预期。
  if (window.hengceHost) return;                 // 已注入则不覆盖

  // ArrayBuffer/Uint8Array → base64（分块累加，避免 String.fromCharCode 溢出）
  // 为什么要重载成 Uint8Array：三种入参（ArrayBuffer / Uint8Array / 类数组
  // 的 .buffer）在协议层等效，统一成字节视图后再编码，调用方不必自己转。
  function zhuan_b64(huanchong) {
    let u8 = huanchong instanceof Uint8Array ? huanchong
      : new Uint8Array(huanchong instanceof ArrayBuffer ? huanchong : huanchong.buffer);
    let er = '';
    // 0x8000 = 32768 字节/块：String.fromCharCode.apply 的参数个数上限在
    // 各引擎约 65535（栈/参数限制），取一半留足余量；再大的文件只是多循环几次，
    // 而一次 apply 传几十万个参数会直接 RangeError（大 xlsx 必现）。
    for (let i = 0; i < u8.length; i += 0x8000) {
      er += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    }
    return btoa(er);
  }

  // base64 → ArrayBuffer（下载响应：bytesB64 → bytes）
  // 逐字符转字节（charCodeAt 的值范围 0-255 由 atob 保证），不使用 TextEncoder：
  // 那会把 base64 当文本再按 UTF-8 编码，字节立刻错乱。
  function jie_b64(wen) {
    const er = atob(wen);
    const u8 = new Uint8Array(er.length);
    for (let i = 0; i < er.length; i++) u8[i] = er.charCodeAt(i);
    return u8.buffer;
  }

  // 上行负载预处理：文件字节换成同键名 +B64 的字符串字段
  // （接入说明：二进制显式转换——{bytes:ArrayBuffer} → {bytesB64:'...'}）
  // 为什么必须显式转换：JSON.stringify(ArrayBuffer) 得到 {}，字节会静默丢失；
  // 服务端只认 bytesB64（Python 侧再解回字节），两边约定同一个键名。
  // 递归处理数组与嵌套对象：files[] / reports.export 等负载都是多层结构。
  function yuchu(zhi) {
    // 基本类型（含 null/undefined）原样返回，避免无意义拷贝。
    if (!zhi || typeof zhi !== 'object') return zhi;
    // 顶层直接是二进制：整段编成纯 base64 字符串（键名由外层决定）。
    if (zhi instanceof ArrayBuffer || zhi instanceof Uint8Array) {
      return zhuan_b64(zhi);
    }
    // 数组逐项递归（保持顺序，不做展平）。
    if (Array.isArray(zhi)) return zhi.map(yuchu);
    // 对象逐键递归：二进制值改名为 <键>B64，其余键名不变。
    const out = {};
    for (const k of Object.keys(zhi)) {
      const v = zhi[k];
      out[(v instanceof ArrayBuffer || v instanceof Uint8Array) ? k + 'B64' : k] = yuchu(v);
    }
    return out;
  }

  window.hengceHost = {
    // 协议版本：UI 侧可用它做能力判断（后续加事件推送时据此分支）。
    version: '1.0',
    // 唯一请求入口：action = 后端 DONGZUO 分发表里的键；
    // payload = 该 action 的入参（二进制已由 yuchu 转成 *B64）；
    // 返回 Promise<data 原样>，下载类响应已还原成 ArrayBuffer；失败 reject 中文 Error。
    async request(action, payload) {
      let ying;
      try {
        // 相对路径 /hengce/api：与页面同源，宿主路由和独立服务两种形态都成立
        // （服务端把两种形态都挂在同一个前缀下，见 服务核心.mjs）。
        ying = await fetch('/hengce/api', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ action, payload: yuchu(payload || {}) }),
        });
      } catch (e) {
        // fetch 本身 reject 只代表网络层失败（服务没起、被阻断、页面是 file://）。
        throw new Error('无法连接衡策宿主服务：' + e.message);
      }
      let da;
      try {
        da = await ying.json();
      } catch {
        // 拿到了 HTTP 状态但不是 JSON：多半是打到了宿主别的路由或静态 404 页。
        throw new Error('宿主服务返回了无法解析的响应（HTTP ' + ying.status + '）');
      }
      // 双判：HTTP 层不 ok 或业务层 ok:false 都算失败；error 优先用后端中文原文，
      // 没有（如网关直接 502）才回落到状态码文案，保证界面上永远是中文。
      if (!ying.ok || !da.ok) {
        throw new Error((da && da.error) || ('宿主请求失败（HTTP ' + ying.status + '）'));
      }
      const shu = da.data;
      // 下载响应：{name, mime, bytesB64} → {name, mime, bytes:ArrayBuffer}
      // 判定靠 bytesB64 这个字段名——协议里下载只有这一种形状（另一种是
      // {handled:true}，没有 bytesB64，会走下面的 return shu 原样返回）。
      if (shu && typeof shu.bytesB64 === 'string') {
        return { name: shu.name, mime: shu.mime, bytes: jie_b64(shu.bytesB64) };
      }
      return shu;
    },
    // 事件订阅：本版无推送（每次请求返回完整工作区），提供合法空订阅
    // 为什么仍要实现：UI 按接入说明调用 subscribe() 并保存取消函数；
    // 不实现会抛 TypeError，整页初始化失败。空实现 + 一行说明是明确的「能力留白」，
    // 取消函数也必须返回（页面可能在组件卸载时调用它）。
    subscribe() {
      if (console && console.info) {
        console.info('[hengce] 本版宿主桥无事件推送，工作区随每次请求整体刷新');
      }
      return function quxiao() {};
    },
  };
})();
