// 衡策 1.1.3 · 客户端接管：应用主窗口直达工作台。
//
// 机制：package.json 声明 dsh.client（immediately:true）后，宿主 web UI
// 启动即经 window.__ModuleLoader__ 执行本文件。工厂必须返回一个带 apply
// 方法的插件对象（dsh 客户端插件契约；返回 undefined 会让 web boot
// 以 invalid plugin 崩溃——实测教训）。apply 在模块激活时调用：此时把
// 窗口导航到衡策工作台（相对路径，dsh-app scheme 代理到插件路由），
// 即老版衡策"打开就是工作台"；dsh 原界面不再出现。
window.__ModuleLoader__.load({
  id: '@hengce/hengce-dsh-plugin',
  factory: () => ({
    name: 'hengce-client',
    apply() {
      if (!location.pathname.startsWith('/hengce/')) {
        location.replace('/hengce/?embedded=1');
      }
    },
  }),
});
