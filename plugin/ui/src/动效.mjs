// 动效层：只负责「呈现前后状态的差异」，不参与任何业务计算，也不决定分析、焦点或提交的时机。
// 设计前提：所有业务 DOM 更新都是同步完成的，动画只是在重绘前后各抓一次布局做插值，因此任何时刻中断动画都不会破坏数据。
// 降级策略：系统开启「减少动态效果」时全部跳过，功能与状态不受影响（可访问性优先于观感）。
// 所有业务 DOM 更新保持同步。动画只呈现前后状态，不控制分析、焦点或提交时机。
// 标准出场/过渡缓动：起步快、收尾慢，用于布局位移、水波纹、抽屉关闭这类「有明确终点」的动作。
const OUT = 'cubic-bezier(.22,1,.36,1)';
// 弹簧曲线用 CSS linear() 逐点描述：中途会轻微过冲（1.025）再回到 1，比 cubic-bezier 更像真实弹簧。
// 用 linear() 而不是 JS 物理动画的原因：交给合成器执行，主线程忙时也不掉帧。
const SPRING = 'linear(0, .13 7%, .44 17%, .76 29%, .94 42%, 1.025 58%, 1.012 76%, 1)';
// 所有进行中的动画记录：偏好变化、卸载、页面隐藏时要能一次性收尾或取消。
const running = new Set();
// 正在关闭的弹窗：backdrop → Promise。用 WeakMap 是因为 DOM 节点被移除后应自动失去引用，不留内存。
const closing = new WeakMap();
// installMotion 的安装标记兼 disposer：非空表示已安装，重复调用直接返回它。
let installation = null;

// 统一的选择器入口：动效只查固定结构节点（#main / .sidebar / #overlay），不依赖业务数据。
const query = selector => document.querySelector(selector);
// 读取「减少动态效果」偏好；matchMedia 可能不存在（极端环境），用可选链并兜底 false。
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false;
// 浏览器不支持 linear() 时退回一个近似「快出回弹」的三次贝塞尔，保证旧内核也有弹性观感。
const spring = () => window.CSS?.supports('animation-timing-function', SPRING) ? SPRING : 'cubic-bezier(.2,.9,.25,1.04)';
// 统一取布局快照：返回普通对象而不是 DOMRect，避免调用方把它当活对象使用（DOMRect 会随滚动变化）。
const rect = node => {
// 节点不存在时返回 null，调用方用可选链或提前 return 跳过动画。
  if (!node) return null;
// 取视口坐标：动画插值用的都是视口值，与页面滚动量无关。
  const r = node.getBoundingClientRect();
// 只暴露四个布局需要的数值，读起来比 DOMRect 更明确。
  return { left: r.left, top: r.top, width: r.width, height: r.height };
};

// A timer is always available alongside WAAPI: background tabs must never block a close callback.
// 播放一段 WAAPI 动画并登记到 running；group 用于按用途取消（layout / navigation / dialog / ripple）。
// cleanup 在「动画结束或被取消」时都会执行（用于还原临时样式、移除节点），finish 只在正常结束时执行（用于关闭回调）。
// 返回 record，调用方若要提前结束可以 record.cancel() / record.finish()。
function play(node, frames, options, { group = 'layout', cleanup, finish } = {}) {
// 三种降级：没有节点、用户要求减少动效、浏览器不支持 WAAPI——都必须立刻走收尾回调，不能把调用方卡住。
  if (!node || reduced() || typeof node.animate !== 'function') {
    cleanup?.();
    finish?.();
    return null;
  }
  let animation;
// fill: both 让动画首帧也生效（避免第一帧闪回原位）；默认 easing 可被 options.easing 覆盖。
  try { animation = node.animate(frames, { fill: 'both', easing: OUT, ...options }); }
// 参数非法时浏览器会抛错：同样走收尾，保证调用方逻辑（例如关闭弹窗）不会因为动画失败而中断。
  catch { cleanup?.(); finish?.(); return null; }
// 幂等哨兵：onfinish、oncancel、兜底定时器可能先后触发，只允许结算一次。
  let settled = false;
// 兜底定时器句柄：结算时要能清除它。
  let timer;
// 统一结算：清定时器、移除登记、解绑回调、取消动画、执行 cleanup，只有正常结束时才执行 finish。
  const settle = invokeFinish => {
// 已结算就直接返回：这是「动画结束」与「兜底超时」竞争时的胜负判定。
    if (settled) return;
// 先置位再清理：清理过程可能触发 focus/resize 等事件再次进来，避免递归。
    settled = true;
// 清掉兜底定时器，防止它在动画已结束后再次触发。
    clearTimeout(timer);
// 从进行中集合移除，卸载与偏好切换时不再处理它。
    running.delete(record);
// 解绑事件回调：避免真正结束事件随后又把已结算的动画走一遍。
    animation.onfinish = null;
// 同上，cancel 事件也解除。
    animation.oncancel = null;
// 显式取消动画：把节点的内联样式交还给 CSS，避免动画结束后残留 fill: both 的最终帧。
    animation.cancel();
    cleanup?.();
// 取消时不调用 finish：关闭弹窗的「真正移除节点」必须等动画正常播完，绝不能因为被打断而提前执行。
    if (invokeFinish) finish?.();
  };
// 对外句柄：cancel = 中断（不触发 finish），finish = 正常结束（触发 finish）。
  const record = { group, node, cancel: () => settle(false), finish: () => settle(true) };
// 登记后才能被 cancelGroup、偏好切换、卸载逻辑找到。
  running.add(record);
// 正常播完：走 finish 分支。
  animation.onfinish = record.finish;
// 被浏览器取消（节点被移除等）：走 cancel 分支，只清理不回调。
  animation.oncancel = record.cancel;
// 兜底：后台标签页里 WAAPI 的 onfinish 可能长时间不触发，用「时长 + 延迟 + 100ms」的定时器强制结算。
  timer = setTimeout(record.finish, Number(options.duration || 0) + Number(options.delay || 0) + 100);
// 返回句柄供调用方控制（例如菜单关闭时 cancel 入场动画）。
  return record;
}

// 按用途取消一组动画：重绘前必须调用，否则上一轮的插值结果会被当成「原始位置」。
function cancelGroup(group) {
// 遍历副本：cancel 会修改 running，直接迭代 Set 会漏掉元素。
  for (const record of [...running]) if (record.group === group) record.cancel();
}

// 临时设置内联样式并返回恢复函数：动画期间锁住尺寸/定位，结束后原样还原。
function temporaryStyles(node, values) {
// 节点为空时返回空函数，调用方可以无条件调用恢复，不需要判空。
  if (!node) return () => {};
// 先记录原内联值（可能是空字符串），恢复时按原值写回，不假设原本没有内联样式。
  const old = Object.fromEntries(Object.keys(values).map(key => [key, node.style[key]]));
// 写入临时值：动画在这一帧的布局基础上做插值。
  Object.assign(node.style, values);
// 恢复函数：把每个属性还原成记录下来的原值。
  return () => Object.assign(node.style, old);
}

// 抓取侧栏导航的当前状态：当前页 + 液体指示器（或当前项）的矩形，供重绘后对比是否换了页面/位置。
function navState() {
  const host = query('.sidebar');
  const active = host?.querySelector('.nav-item.active');
// 只有存在激活项时才返回状态；没有激活项（例如首帧）返回 null，调用方据此跳过动画。
// 侧栏容器（.sidebar）是指示器的定位基准，坐标换算全部相对它完成。
  return active ? {
// 记录页面标识：重绘后如果还是同一页，说明只是局部更新，不做整页切换动画。
    page: active.dataset.page,
// 优先取指示器当前位置：连续快速切换时，指示器可能还在半路，从当前位置继续才连贯。
    rect: rect(host.querySelector('.nav-liquid-indicator') || active)
  } : null;
}

// 把液体指示器移动到当前激活项；previous 非空且 animate 为真时，从旧位置做一次形变过渡。
// 这是纯装饰元素（aria-hidden），所以即使动画被跳过也不影响导航可用性。
function placeNavigation(previous, animate = true) {
  const host = query('.sidebar');
  const active = host?.querySelector('.nav-item.active');
// 没有激活项就什么都不做：避免在空侧栏上留下一块高亮。
  if (!active) return;
// 给侧栏加标记类：CSS 据此隐藏原生的 active 背景，避免指示器与它叠加。
  host.classList.add('has-liquid-nav');
// 复用已有指示器：节点一直在，动画才不会因为重建而丢帧。
  let indicator = host.querySelector('.nav-liquid-indicator');
// 首次渲染时创建指示器。
  if (!indicator) {
// 纯装饰节点，不参与语义。
    indicator = document.createElement('div');
// 样式类：毛玻璃底 + 圆角，尺寸由内联样式驱动。
    indicator.className = 'nav-liquid-indicator';
// 对读屏隐藏：导航状态已经由 nav-item 的 aria-current 表达。
    indicator.setAttribute('aria-hidden', 'true');
// 放在侧栏最前：不覆盖导航项的可点击区域（z-index 由 CSS 控制）。
    host.prepend(indicator);
  }
// 目标矩形与容器矩形：指示器用绝对定位，坐标要换算成相对容器的偏移。
  const target = rect(active), parent = rect(host);
// 直接写内联样式而不是用 transform：位置与尺寸都要参与后续的 FLIP 计算，内联值最直观。
  Object.assign(indicator.style, {
// left 需要加上容器滚动量：侧栏可滚动时，内容坐标 = 视口差值 + scrollLeft。
    left: `${target.left - parent.left + host.scrollLeft}px`,
// top 同理。
    top: `${target.top - parent.top + host.scrollTop}px`,
// 尺寸跟随激活项（顶栏紧凑模式下高度可能不同）。
    width: `${target.width}px`, height: `${target.height}px`
  });
// 四种不需要动画的情况：调用方要求直接跳、用户减少动效、没有上一帧、页面没变（只是重绘）。
  if (!animate || reduced() || !previous?.rect || previous.page === active.dataset.page) return;
// 位移差：把指示器「先放回旧位置」，再过渡到新位置（FLIP 的标准做法）。
  const dx = previous.rect.left - target.left, dy = previous.rect.top - target.top;
// 位移不足 1px 时跳过：避免同一位置反复触发的微小动画造成闪烁。
  if (Math.abs(dx) + Math.abs(dy) < 1) return;
// 宽度比例夹在 0.9–1.1：允许轻微拉伸，但不会因为极端尺寸差异变成奇怪的长条。
  const sx = Math.max(.9, Math.min(1.1, previous.rect.width / target.width));
// 高度比例同理。
  const sy = Math.max(.9, Math.min(1.1, previous.rect.height / target.height));
  play(indicator, [
// 起始帧：指示器出现在旧位置，并带着旧尺寸的比例（FLIP 的 First）。
    { transform: `translate(${dx}px,${dy}px) scale(${sx},${sy})`, offset: 0 },
// 中途帧：位移只剩 14%，同时纵向略微拉长——模拟液体被拖动后的惯性形变。
    { transform: `translate(${dx * .14}px,${dy * .14}px) scale(.985,1.075)`, offset: .55 },
// 结束帧：精确落在新位置、恢复原始尺寸。
    { transform: 'translate(0,0) scale(1,1)', offset: 1 }
// 500ms、OUT 缓动：导航切换是低频操作，稍长的动效不会干扰连续操作；归入 navigation 组便于统一取消。
  ], { duration: 500, easing: OUT }, { group: 'navigation' });
}

// 在 #app.innerHTML 被替换之前调用：同步抓取所有会被重建的位置与滚动状态，内部不做任何异步 DOM 操作。
// 如果在这里插入 await，重绘时机就会与抓取时机错开，动画会基于错误的旧位置计算。
/** Call immediately before replacing #app.innerHTML. No asynchronous DOM work. */
export function captureLayout() {
  const main = query('#main');
  const assistant = query('.content-layout > .assistant');
  const sidebar = query('.sidebar');
// 快照是一份纯数据 + 两个节点引用，不含任何计算，重绘后可原样交给 animateLayout。
// 助手侧栏的节点引用单独保留：它可能被关闭，旧节点要拿去当退场影像。
  const snapshot = {
// 记录当前页面标识，用于判断重绘后是否发生了整页切换。
    page: main?.dataset.page ?? null,
// 主内容区的旧矩形：宽度变化时用它做宽度插值。
    main: rect(main),
// 同时记录节点与矩形：节点被移除后仍能拿它做「幽灵退场」。
    assistant: assistant ? { node: assistant, rect: rect(assistant) } : null,
// 导航状态：页面与指示器位置。
    nav: navState(),
// 记录开合状态与当前 transform 矩阵：移动端抽屉动画必须从「当前视觉位置」接着走，否则会跳一下。
    sidebar: sidebar ? { open: Boolean(sidebar.closest('.nav-open')), transform: getComputedStyle(sidebar).transform } : null,
// 逐表记录滚动位置：重绘后恢复，避免用户正在看的长表跳回顶部。
    scrolls: main ? [...main.querySelectorAll('.table-scroll')].map(node => ({ x: node.scrollLeft, y: node.scrollTop })) : []
  };
// 先取消 layout 与 navigation 两组动画：这样下面的快照量到的是「插值被停下后的真实边界」。
// 顺序不能反——先量后取消的话，清理本身又会触发一次布局变化，快照就过期了。
  // Capture the interpolated bounds before releasing a previous transition.
  cancelGroup('layout');
  cancelGroup('navigation');
// 返回快照，调用方在 innerHTML 替换后把它交给 animateLayout。
  return snapshot;
}

// 助手侧栏的开合动画：主内容区宽度变化时，用「锁住助手、插值主区宽度」的方式让文字自然重排。
// 不直接缩放整体（scale）的原因：财务报表的数字与表格被拉伸会变得不可读。
function animateAssistantLayout(before, main, assistant) {
// 目标矩形与父容器矩形：宽度动画需要把主区从旧宽度过渡到新宽度。
  const target = rect(main), parent = rect(main.parentElement);
// 宽度变化超过 1px 才算「布局真的变了」，否则只是亚像素差异，不必播动画。
  const changedWidth = before.main && Math.abs(before.main.width - target.width) > 1;
// 默认恢复函数为空：只有确实需要锁定助手位置时才替换它。
  let restoreAssistant = () => {};
// 助手仍然存在：做入场淡入。
  if (assistant) {
    const bounds = rect(assistant);
    // Keep the assistant at its destination while the neighboring content changes width.
// 主区宽度变化时，用 fixed 定位把助手钉在当前视觉位置，防止它在宽度插值过程中被挤着重新排版。
    if (changedWidth) restoreAssistant = temporaryStyles(assistant, {
      position: 'fixed', left: `${bounds.left}px`, top: `${bounds.top}px`,
      width: `${bounds.width}px`, height: `${bounds.height}px`, margin: '0'
    });
    play(assistant, [
// 入场起始帧：从右侧 28px 处淡入，暗示「侧栏从右边展开」。
// 结束帧是 translateX(0)：只把透明度收到 1，最终位置完全由布局决定。
      { opacity: 0, transform: 'translateX(28px)' },
      { opacity: 1, transform: 'translateX(0)' }
// 弹窗/侧栏用弹簧缓动：先快后缓并带轻微回弹，比匀速更像实体。
    ], { duration: 460, easing: spring() });
// 助手已被关闭但之前存在：用旧节点做退场影像。
  } else if (before.assistant?.node) {
    // Reuse the detached old node as a noninteractive exit image; no duplicated IDs remain.
// 幽灵节点就是被替换下来的旧 DOM：直接复用，不用克隆，省一次深拷贝。
    const ghost = before.assistant.node, bounds = before.assistant.rect;
// 标记类：CSS 里去掉阴影与层级干扰，让它只作为视觉残影存在。
    ghost.classList.add('motion-ghost');
// inert 让幽灵节点不可点击、不可聚焦、对读屏不可见，避免用户点到已经「不存在」的侧栏。
    ghost.inert = true;
// 再显式标注一次 aria-hidden，兼容不支持 inert 的浏览器。
    ghost.setAttribute('aria-hidden', 'true');
// 移除根 id：新 DOM 里可能已有同名节点，重复 id 会让 getElementById 取错元素。
    ghost.removeAttribute('id');
// 内部 id 一并清除：表单字段的 id 与 label 的 for 关联不能在幽灵节点上重复存在。
    ghost.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
    Object.assign(ghost.style, {
      position: 'fixed', left: `${bounds.left}px`, top: `${bounds.top}px`,
      width: `${bounds.width}px`, height: `${bounds.height}px`, margin: '0',
      pointerEvents: 'none', zIndex: '38', transform: 'none'
    });
    document.body.append(ghost);
    play(ghost, [
      { opacity: 1, transform: 'translateX(0)' },
// 退场从 translateX(0) 的静止状态开始，向右滑出 32px 并消失，与入场方向相反。
      { opacity: 0, transform: 'translateX(32px)' }
// 退场只需 220ms 且用加速曲线：关闭操作要「立刻有反馈」；cleanup 保证节点一定被移除。
    ], { duration: 220, easing: 'cubic-bezier(.4,0,1,1)' }, { cleanup: () => ghost.remove() });
  }
// 宽度没变就不需要主区动画，到此结束（入场/退场动画已各自登记）。
  if (!changedWidth) return;
// 锁定主区宽度与左右外边距：动画期间由 transform/width 过渡控制，避免被 flex 重新分配。
  const restoreMain = temporaryStyles(main, {
    flex: '0 0 auto', width: `${target.width}px`,
    marginLeft: `${target.left - parent.left}px`, marginRight: '0'
  });
// 临时裁剪横向溢出：宽度动画过程中内容可能短暂超出，不裁剪会出现横向滚动条闪烁。
  const restoreParent = temporaryStyles(main.parentElement, { overflowX: 'clip' });
  // Width interpolation intentionally reflows text instead of scaling financial figures.
  play(main, [
// 起始帧：旧宽度、旧左边距。
    { width: `${before.main.width}px`, marginLeft: `${before.main.left - parent.left}px` },
// 结束帧：新宽度、新左边距。
    { width: `${target.width}px`, marginLeft: `${target.left - parent.left}px` }
// 480ms、OUT 缓动：宽度变化是「有明确终点」的布局过渡，不需要回弹。
  ], { duration: 480, easing: OUT }, {
// cleanup 统一还原三处临时样式：无论动画正常结束还是被取消，都不会留下内联样式污染。
    cleanup: () => { restoreAssistant(); restoreMain(); restoreParent(); }
  });
}

/** Call after shell insertion and form binding, before any caller's synchronous focus(). */
// 布局动画总入口：在 shell 插入与表单绑定之后调用，默认 before = {} 表示首帧，不播任何过渡。
// 必须在调用方的同步 focus() 之前执行：否则焦点会让浏览器先滚动一次，动画基于错误位置。
export function animateLayout(before = {}) {
  const main = query('#main');
// 没有主内容区（例如启动失败页）就什么都不做。
  if (!main) return;
  const sidebar = query('.sidebar');
// 菜单开合状态是否变化：变化时导航指示器不播形变，避免两套动画叠加。
  const menuChanged = before.sidebar && sidebar && before.sidebar.open !== Boolean(sidebar.closest('.nav-open'));
// 菜单开合时直接跳到位（不播形变），其余情况按上一帧位置过渡。
  placeNavigation(before.nav, !menuChanged);
// 页面标识变化 = 整页切换，需要播淡入。
  const pageChanged = before.page !== main.dataset.page;
// 同一页内的局部更新：恢复表格滚动位置，用户不会因为筛选/排序而跳回顶部。
  if (!pageChanged && before.scrolls) {
// 按索引对应：重绘前后表格数量与顺序一致（同一个页面模板）。
    main.querySelectorAll('.table-scroll').forEach((node, index) => {
// 取对应表格的快照。
      const saved = before.scrolls[index];
// 两轴都恢复：宽表格的横向位置与长表格的纵向位置同样重要。
      if (saved) { node.scrollLeft = saved.x; node.scrollTop = saved.y; }
    });
  }
// 减少动效模式：滚动已恢复，直接结束，不播任何过渡。
  if (reduced()) return;
// 只有移动端（侧栏变成抽屉）才需要滑入滑出动画；桌面端侧栏常驻。
  if (menuChanged && window.matchMedia('(max-width: 760px)').matches) {
// 判断这次是打开还是关闭，决定动画时长与缓动。
    const open = Boolean(sidebar.closest('.nav-open'));
    play(sidebar, [
// 起始帧：从快照里记录的原始 transform 开始，接着上一帧的视觉状态。
      { transform: before.sidebar.transform },
// 结束帧：重绘后 CSS 计算出的目标 transform（打开 = translateX(0)，关闭 = 移出屏幕）。
      { transform: getComputedStyle(sidebar).transform }
// 开抽屉慢一点、带回弹；关抽屉快一点、直接收走——符合「进入从容、退出果断」的交互习惯。
    ], { duration: open ? 440 : 220, easing: open ? spring() : OUT });
  }
  const assistant = query('.content-layout > .assistant');
// 助手侧栏是否存在发生变化 = 开合切换。
  const toggledAssistant = Boolean(before.assistant) !== Boolean(assistant);
// 只有侧栏开关时才做宽度联动动画；普通重绘不碰布局。
  if (toggledAssistant && before.main) animateAssistantLayout(before, main, assistant);
// 整页切换：主区淡入上移，让「页面换了」这件事有明确的空间感。
  if (pageChanged) {
    play(main, [
// 起始帧：略微下移且透明。
      { opacity: 0, transform: 'translateY(12px)' },
// 结束帧：回到原位并完全可见。
      { opacity: 1, transform: 'translateY(0)' }
// 弹簧缓动 + 480ms：页面切换是主要导航动作，值得稍长的过渡。
    ], { duration: 480, easing: spring() });
  }
}

/** Existing modal focus and submit binding can run immediately after this call. */
// 弹窗入场：backdrop 淡入 + dialog 从下方浮起（drawer 从右侧滑入）。
// 调用后弹窗的焦点管理与 submit 绑定可以立即执行，动画不影响它们。
// 入口先 cancelGroup('dialog') 取消上一轮弹窗动画：连续开关时不会有两套动画同时改同一个节点。
export function animateDialog() {
  cancelGroup('dialog');
// backdrop 是遮罩层，dialog 是它内部的面板。
  const backdrop = query('#overlay')?.firstElementChild;
  const dialog = backdrop?.querySelector('.dialog');
// 没有弹窗或用户要求减少动效时直接返回：此时弹窗已经是最终状态。
  if (!dialog || reduced()) return;
// 遮罩淡入 240ms：比面板略快，视觉上「背景先暗、面板后到」。
  play(backdrop, [{ opacity: 0 }, { opacity: 1 }], { duration: 240 }, { group: 'dialog' });
  play(dialog, [
// 起始帧：drawer 从右侧 48px 滑入，普通弹窗从下方 20px 浮起并轻微缩放。
    { opacity: .2, transform: dialog.classList.contains('drawer') ? 'translateX(48px)' : 'translateY(20px) scale(.975)' },
// 结束帧：回到自然位置与尺寸。
    { opacity: 1, transform: dialog.classList.contains('drawer') ? 'translateX(0)' : 'translateY(0) scale(1)' }
// 420ms 弹簧：与侧栏开合观感统一，归入 dialog 组便于关闭时统一取消。
  ], { duration: 420, easing: spring() }, { group: 'dialog' });
}

/** A stale close never clears or refocuses a newer dialog. Returns a settled Promise. */
// 弹窗关闭动画：返回 Promise，在 backdrop 真正退场后 resolve；callback 只在「仍是同一个 backdrop」时执行。
// 关键约束：过期关闭（用户已打开新的弹窗）绝不能清空新弹窗，也绝不能把焦点夺回来。
export function closeDialogMotion(callback) {
// 取当前遮罩与面板；任何一步取不到都按「无需动画」处理。
  const overlay = query('#overlay'), backdrop = overlay?.firstElementChild;
  const dialog = backdrop?.querySelector('.dialog');
// 没有弹窗、或用户要求减少动效：同步回调并立即 resolve，调用方可以当动画不存在。
  if (!backdrop || !dialog || reduced()) {
    callback?.();
// 返回已决议的 Promise，调用方 await 不会挂起。
    return Promise.resolve();
  }
// 同一个 backdrop 重复调用直接复用同一个 Promise：关闭按钮被连点两次也只播一次动画。
  if (closing.has(backdrop)) return closing.get(backdrop);
// 从当前视觉矩阵开始：入场动画还没播完就点关闭，退出也不会跳一下。
  const currentTransform = getComputedStyle(dialog).transform;
// 遮罩同理，记录当前透明度作为退场起点。
  const currentOpacity = getComputedStyle(backdrop).opacity;
  cancelGroup('dialog');
// Promise 的决议函数先声明，稍后在 cleanup 里调用。
  let resolveDone;
// 新建 Promise：cleanup 保证无论动画结束还是被取消都会 resolve，调用方不会永久等待。
  const completion = new Promise(resolve => { resolveDone = resolve; });
// 登记「正在关闭」：重复调用与过期判断都依赖它。
  closing.set(backdrop, completion);
  play(dialog, [
// 起始帧：没有 transform 时显式写 translate(0,0)，保证可插值。
    { transform: currentTransform === 'none' ? 'translate(0,0)' : currentTransform },
// 结束帧：关闭动作更轻微——只偏移一点并略微缩小，避免「弹窗飞出去」的夸张感。
    { transform: dialog.classList.contains('drawer') ? 'translateX(24px)' : 'translateY(8px) scale(.99)' }
// 180ms 加速曲线：关闭必须干脆，等待感会直接影响操作流畅度。
  ], { duration: 180, easing: 'cubic-bezier(.4,0,1,1)' }, { group: 'dialog' });
// 遮罩在同一时长内淡出，与面板同步结束。
  play(backdrop, [{ opacity: currentOpacity }, { opacity: 0 }], { duration: 180 }, {
// 归入 dialog 组，与面板动画一起被 cancelGroup 管理。
    group: 'dialog',
// 清理与决议放在一起：只要结算就一定解除登记并唤醒等待者。
    cleanup: () => { closing.delete(backdrop); resolveDone(); },
// 只有正常结束、且当前遮罩仍是这个 backdrop 时才真正移除弹窗；过期关闭不执行回调。
    finish: () => { if (overlay.firstElementChild === backdrop) callback?.(); }
  });
// 调用方 await 它即可拿到「动画已结束」的时机，再决定是否清理 DOM。
  return completion;
}

/** Install once. The returned disposer supports plugin unmount; pagehide also cleans up. */
// 一次性安装全局动效：按钮水波纹、窗口尺寸变化后重排导航、减少动效偏好切换、页面隐藏清理。
// 返回 disposer：插件卸载或需要整体关闭动效时调用，保证不留任何监听与残留节点。
export function installMotion() {
// 已安装就返回同一个 disposer：主界面多次调用 installMotion 不会重复绑定。
  if (installation) return installation;
// 用 AbortController 统一管理监听：卸载时一次 abort 全部移除，不用逐个 removeEventListener。
  const controller = new AbortController();
// 所有 addEventListener 都带上这个 signal。
  const { signal } = controller;
// 监听系统偏好变化：用户中途开启「减少动态效果」时应立即生效。
  const preference = window.matchMedia?.('(prefers-reduced-motion: reduce)');
// 偏好变化回调。
  const onPreference = () => {
// 开启减少动效：把所有进行中的动画按「正常结束」结算，收尾回调必须执行，不能让界面停在半动画状态。
    if (reduced()) for (const record of [...running]) record.finish();
    placeNavigation(null, false);
  };
// disposer：解绑监听、取消动画、移除残留节点、清空安装标记。
  const dispose = () => {
// 一次移除本函数注册的所有监听。
    controller.abort();
// 偏好监听是手动添加的（不受 signal 管理），单独移除。
    preference?.removeEventListener?.('change', onPreference);
// 取消所有动画：卸载场景只需要清理，不需要触发 finish 回调。
    for (const record of [...running]) record.cancel();
// 清掉可能残留的幽灵节点与水波纹：它们不在业务 DOM 里，没人会负责回收。
// 随后 installation = null 清空安装标记，之后再调用 installMotion 可以重新安装。
    document.querySelectorAll('.motion-ghost,.liquid-ripple').forEach(node => node.remove());
    installation = null;
  };
// 登记 disposer，让后续调用直接复用它。
  installation = dispose;
// 用 pointerdown 而不是 click：按下即出水波纹，手感更即时，且与键盘触发的 click 区分开。
  document.addEventListener('pointerdown', event => {
// 减少动效时不画波纹；只响应鼠标左键（或触摸/笔的主按键）。
    if (reduced() || event.button !== 0) return;
// 只给按钮类元素加波纹，普通链接与表格行不加。
    const button = event.target.closest?.('.btn,.icon-btn');
// 禁用按钮、inert 容器内的按钮不响应：视觉反馈不能暗示「可以点」。
    if (!button || button.disabled || button.closest('[inert]')) return;
// 按钮的视口矩形：用来把点击点换算成按钮内坐标。
    const bounds = button.getBoundingClientRect();
// 波纹直径取长边的 2 倍：保证从任意角落点击都能覆盖整个按钮。
    const size = Math.max(bounds.width, bounds.height) * 2;
// 纯装饰节点，播放完即移除，不进业务 DOM 结构。
    const ripple = document.createElement('span');
// 样式类：圆形径向渐变，由 CSS 定义外观。
    ripple.className = 'liquid-ripple';
// 装饰元素对读屏隐藏。
    ripple.setAttribute('aria-hidden', 'true');
// 位置与尺寸必须内联：取决于点击坐标与按钮尺寸，无法预先写进样式表。
    Object.assign(ripple.style, {
// 正方形 + border-radius 50% = 圆形。
      width: `${size}px`, height: `${size}px`,
// 以点击点为圆心：减去半径后得到左上角坐标。
      left: `${event.clientX - bounds.left - size / 2}px`,
// 纵向同理。
      top: `${event.clientY - bounds.top - size / 2}px`
    });
// 挂到按钮内部：溢出由按钮的 overflow:hidden 裁掉。
    button.append(ripple);
    play(ripple, [
// 起始帧：很小、半透明。
      { transform: 'scale(.12)', opacity: .3 },
// 结束帧：放大到满尺寸并完全透明，形成扩散消散的观感。
      { transform: 'scale(1)', opacity: 0 }
// 520ms 扩散；cleanup 确保动画被取消时节点也会被移除，不会在按钮里堆积。
    ], { duration: 520, easing: OUT }, { group: 'ripple', cleanup: () => ripple.remove() });
  }, { passive: true, signal });
// 窗口尺寸变化：布局动画与导航位置都失去意义，全部取消后重排指示器。
  window.addEventListener('resize', () => {
    cancelGroup('layout');
    cancelGroup('navigation');
    placeNavigation(null, false);
  }, { passive: true, signal });
// 页面隐藏/卸载时自动清理：只执行一次，并且随 signal 自动解绑。
  window.addEventListener('pagehide', dispose, { once: true, signal });
// 注册偏好变化监听（可选链兼容不支持 addEventListener 的环境）。
  preference?.addEventListener?.('change', onPreference);
  placeNavigation(null, false);
// 返回值即 disposer：调用方可以显式卸载动效层。
  return dispose;
}
