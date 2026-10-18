// 衡策界面 · 宿主桥（由插件服务下发，独立打开 ui/ 时不存在 → 演示模式）。
//
// 实现 接入说明 §2 的 window.hengceHost：所有业务请求走同源
// /hengce/api（POST JSON），文件字节在本层做 ArrayBuffer ↔ base64，
// 协议失败一律 reject 中文 Error（不回退演示数据）。
(function () {
  'use strict';
  if (window.hengceHost) return;                 // 已注入则不覆盖

  // ArrayBuffer/Uint8Array → base64（分块累加，避免 String.fromCharCode 溢出）
  function zhuan_b64(huanchong) {
    let u8 = huanchong instanceof Uint8Array ? huanchong
      : new Uint8Array(huanchong instanceof ArrayBuffer ? huanchong : huanchong.buffer);
    let er = '';
    for (let i = 0; i < u8.length; i += 0x8000) {
      er += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    }
    return btoa(er);
  }

  // base64 → ArrayBuffer（下载响应：bytesB64 → bytes）
  function jie_b64(wen) {
    const er = atob(wen);
    const u8 = new Uint8Array(er.length);
    for (let i = 0; i < er.length; i++) u8[i] = er.charCodeAt(i);
    return u8.buffer;
  }

  // 上行负载预处理：把文件字节换成 {bytesB64}（接入说明：二进制显式转换）
  function yuchu(zhi) {
    if (!zhi || typeof zhi !== 'object') return zhi;
    if (zhi instanceof ArrayBuffer || zhi instanceof Uint8Array) {
      return { bytesB64: zhuan_b64(zhi) };
    }
    if (Array.isArray(zhi)) return zhi.map(yuchu);
    const out = {};
    for (const k of Object.keys(zhi)) out[k] = yuchu(zhi[k]);
    return out;
  }

  window.hengceHost = {
    version: '1.0',
    async request(action, payload) {
      let ying;
      try {
        ying = await fetch('/hengce/api', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ action, payload: yuchu(payload || {}) }),
        });
      } catch (e) {
        throw new Error('无法连接衡策宿主服务：' + e.message);
      }
      let da;
      try {
        da = await ying.json();
      } catch {
        throw new Error('宿主服务返回了无法解析的响应（HTTP ' + ying.status + '）');
      }
      if (!ying.ok || !da.ok) {
        throw new Error((da && da.error) || ('宿主请求失败（HTTP ' + ying.status + '）'));
      }
      const shu = da.data;
      // 下载响应：{name, mime, bytesB64} → {name, mime, bytes:ArrayBuffer}
      if (shu && typeof shu.bytesB64 === 'string') {
        return { name: shu.name, mime: shu.mime, bytes: jie_b64(shu.bytesB64) };
      }
      return shu;
    },
    // 事件订阅：本版无推送（每次请求返回完整工作区），提供合法空订阅
    subscribe() {
      if (console && console.info) {
        console.info('[hengce] 本版宿主桥无事件推送，工作区随每次请求整体刷新');
      }
      return function quxiao() {};
    },
  };
})();
