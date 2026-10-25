// 衡策 1.1.6 · 客户端接管：应用主窗口直达工作台。
//
// 机制：package.json 声明 dsh.client（immediately:true）后，宿主 web UI
// 启动即经 window.__ModuleLoader__ 执行本文件。工厂必须返回一个带 apply
// 方法的插件对象（dsh 客户端插件契约；返回 undefined 会让 web boot
// 以 invalid plugin 崩溃——实测教训）。apply 在模块激活时调用：此时把
// 窗口导航到衡策工作台（相对路径，dsh-app scheme 代理到插件路由），
// 即老版衡策"打开就是工作台"；dsh 原界面不再出现。
// __HENGCE_CLIENT__ 打点（factory/apply）用于诊断模块加载竞速问题。
//
// ---------------------------------------------------------------------------
// 【在链路的哪一环】
//   这是「桌面客户端」的接管路径，与 index.js 里的 tapIndex 注入（浏览器路径）
//   是一对互补：
//     · 桌面客户端：本文件在 web UI 启动时执行，直接 location.replace 跳转；
//     · 浏览器打开宿主首页：由 index.js 的 tapIndex 往首屏 HTML 注入跳转脚本。
//   两条路都指向 /hengce/?embedded=1（embedded=1 = 隐藏独立侧栏、用业务页签
//   布局），所以「打开衡策就是工作台」，不需要用户再点一次导航。
//   本文件不碰后端：跳转过去的页面由 adapter/服务核心.mjs 托管，
//   业务请求经 window.hengceHost（adapter/宿主桥.js）打到 /hengce/api。
//
// 【为什么必须 return 插件对象】
//   dsh 客户端加载器会对 factory 返回值做契约校验，undefined/null 直接判定
//   invalid plugin 并让整个 web boot 失败——这会让宿主界面起不来，
//   影响面远大于「衡策没接管」。所以 factory 永远返回 {name, apply}。
//
// 【失败兜底】
//   · __ModuleLoader__ 不存在（非 dsh 环境直接打开本文件）→ 第一行就 TypeError，
//     这是预期内的：本文件只该由宿主加载器执行，不做兼容降级；
//   · 已在 /hengce/ 下则不重复跳转（防止刷新时抖动/死循环）。
// ---------------------------------------------------------------------------
// __HENGCE_CLIENT__ 的三种值即加载进度：undefined=未加载，
// 'factory'=工厂已执行（模块被认出），'apply'=已激活（跳转已发生）。
// 排查「打开还是宿主首页」时先看它，能立刻分清是没加载还是没跳转。
window.__ModuleLoader__.load({
  // id 与 package.json 的插件名一致：宿主按 id 去重/热重载，写错会出现
  // 同一插件被加载两次的诡异现象（两次跳转、两个 apply）。
  id: '@hengce/hengce-dsh-plugin',
  factory: () => {
    // 打点必须在最前：只要进到 factory 就说明加载器认了这个包。
    window.__HENGCE_CLIENT__ = window.__HENGCE_CLIENT__ || 'factory';
    return {
      // 客户端插件名（与后端插件 name 'hengce' 区分：本名只在 web UI 侧用）。
      name: 'hengce-client',
      apply() {
        // 打点：走到这里说明插件被真正激活（加载器已校验通过）。
        window.__HENGCE_CLIENT__ = 'apply';
        // 幂等：已经在工作台（刷新、或嵌入视图内再启动）就不跳，
        // 否则 replace 会不断重载页面。
        if (!location.pathname.startsWith('/hengce/')) {
          // 相对路径 + embedded=1：dsh-app scheme 会把它代理到本插件的
          // webserver 前缀路由，因此桌面端与浏览器端地址书写一致。
          location.replace('/hengce/?embedded=1');
        }
      },
    };
  },
});
