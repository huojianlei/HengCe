// 图标表（唯一数据源）：界面所有线性图标都在这里以 24×24 的路径片段集中声明，由 icon() 统一包一层 <svg>。
// 集中声明的好处：描边宽度、圆角、颜色继承（stroke="currentColor"）只有一处口径，新增图标只需补一条片段。
// 视图盒固定 0 0 24 24，配合 CSS 的 .icon{width:18px} 等比缩放，不必为不同尺寸另存多套资源。
const paths = {
// 经营总览：四宫格仪表盘，用于侧栏导航首项与空状态插图。
  overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="11" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="18" width="7" height="3" rx="1"/>',
// 数据工作区：数据库圆柱体，代表四类 Excel 输入工作簿。
  data:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5M4 12v7c0 4 16 4 16 0v-7"/>',
// 差异分析：折线坐标轴，用于差异分析页与分析图表的标题。
  chart:'<path d="M4 3v17h17M8 15l4-5 4 2 5-7"/>',
// 风险与整改：三角警示号，用于风险导航、高风险标签与提醒条。
  risk:'<path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v5m0 3v.1"/>',
// 组织结构：上下级节点图，用于部门/主体切换与部门明细。
  org:'<rect x="9" y="2" width="6" height="5" rx="1"/><rect x="2" y="17" width="6" height="5" rx="1"/><rect x="16" y="17" width="6" height="5" rx="1"/><path d="M12 7v5M5 17v-5h14v5"/>',
// 报告：带折角的文档，用于报告中心、报告卡片与导出入口。
  report:'<path d="M14 2H5a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V8Z"/><path d="M14 2v6h6M8 12h8m-8 4h8"/>',
// 分析记录：带指针的时钟，表示可回溯的历史分析快照。
  history:'<path d="M3 10a9 9 0 1 1 2 8M3 3v7h7M12 7v5l3 2"/>',
// 设置：带圆点的滑杆，用于分析参数设置弹窗入口。
  settings:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="currentColor" stroke="none"/><circle cx="16" cy="17" r="3" fill="currentColor" stroke="none"/>',
// 帮助：问号圆圈，用于使用说明弹窗。
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 8.5a2.5 2.5 0 1 1 4 2c-1 .8-1.5 1-1.5 3m0 3v.1"/>',
// 方向箭头（右）：面包屑分隔与行内「查看」等轻量跳转。
  chevron:'<path d="m9 5 7 7-7 7"/>',
// 展开/收起（下）：下拉菜单触发按钮与折叠面板。
  down:'<path d="m6 9 6 6 6-6"/>',
// 展开/收起（上）：菜单展开后的方向翻转与升序排序指示。
  up:'<path d="m6 15 6-6 6 6"/>',
// 导入上传：托盘加向上箭头，用于数据工作区导入按钮与拖放区。
  upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
// 导出下载：托盘加向下箭头，用于报告与表格的 PDF、HTML、Markdown、JSON 导出。
  download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v5h16v-5"/>',
// 新增：加号，用于添加阈值档位等增量操作。
  plus:'<path d="M12 5v14M5 12h14"/>',
// 关闭：叉号，用于弹窗右上关闭、提示条与移动端抽屉收起。
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
// 开始：三角播放键，用于运行分析、重新分析。
  play:'<path d="m8 4 12 8-12 8V4Z"/>',
// 完成：对勾，用于步骤完成、必填项已校验。
  check:'<path d="m5 12 4 4L19 6"/>',
// 校验通过：圆圈对勾，用于输入文件完整性检查清单。
  circleCheck:'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
// 时间：时钟，用于生成时间、期间锁止、待办时限。
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
// AI：星芒，用于衡策助手侧栏与「AI 解读」等生成内容标识的视觉锚点。
  spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4"/>',
// 搜索：放大镜，用于差异明细的科目搜索框。
  search:'<circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/>',
// 前往：右向箭头，表示跳页或查看详情。
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
// 上升趋势：向上箭头，用于有利差异与环比改善。
  arrowUp:'<path d="M12 20V4m-6 6 6-6 6 6"/>',
// 趋势：斜向箭头，用于趋势图切换器与指标走势。
  arrowDiag:'<path d="M5 19 19 5M5 5h14v14"/>',
// 文件夹：用于「打开输出文件夹」，指向报告落盘目录。
  folder:'<path d="M3 6V4h7l2 3h9v13H3V6Z"/>',
// 公司/主体：楼宇，用于公司汇总行与主体筛选。
  building:'<path d="M5 21V3h14v18M2 21h20M9 7h1m4 0h1m-6 4h1m4 0h1m-6 4h1m4 0h1M10 21v-3h4v3"/>',
// 预览：眼睛，用于报告预览与文件详情。
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
// 更多操作：三点省略号，预留给列表行内扩展菜单。
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
// 筛选：漏斗，用于模块/风险等级筛选下拉。
  filter:'<path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z"/>',
// 引用来源：链环，用于助手回答下的引用条目与「数据与依据说明」。
  link:'<path d="m9 15 6-6M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m0 12a4 4 0 0 0 6 0l5-5a4 4 0 0 0-6-6l-1 1" transform="translate(1 0) scale(.9)"/>',
// 锁止：挂锁，表示已结账期间不可再修订，用于修订弹窗的禁用说明。
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 14v3"/>',
// 菜单：汉堡按钮，窄屏下开合侧栏导航。
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
// 重置/刷新：循环箭头，用于「载入演示数据」与重新加载工作区。
  refresh:'<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
// 删除：垃圾桶，用于移除已导入文件与清空演示环境（均有二次确认）。
  trash:'<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
// 兜底图标：文件。icon() 查不到名称时用它，避免渲染出空白占位导致布局抖动。
  file:'<path d="M14 2H5v20h14V7Z"/><path d="M14 2v6h5M8 12h8m-8 4h8"/>',
// 关注标记：旗帜，用于整改任务优先级与「持续观察」判定。
  flag:'<path d="M5 22V3m0 1c5-5 9 5 15 0v10c-6 5-10-5-15 0"/>',
// 通知：铃铛，预留给数据变更与任务到期的提醒。
  bell:'<path d="M6 9a6 6 0 0 1 12 0v6l2 3H4l2-3V9Zm3 12h6"/>',
};
// 渲染入口：name 取自 paths 的键，cls 追加在 .icon 之后用于微调尺寸或颜色（如 icon('spark','blue')）。
// 返回值是完整 <svg> 字符串，调用方用模板字符串直接内联进 HTML，不经过任何框架。
// aria-hidden="true" 是刻意的：图标均为纯装饰，可读文本由相邻文字或无障标签承担，避免读屏重复播报。
// stroke-width 固定 1.65，与 CSS 里 .nav-item .icon{stroke-width:1.6} 基本一致，保证导航内外的视觉重量接近。
export function icon(name, cls='') { return `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`; }
