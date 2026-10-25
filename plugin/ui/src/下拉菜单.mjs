// 把浏览器原生 <select> 增强成玻璃风格的自绘下拉菜单，同时保留原生控件作为表单值的唯一来源。
// 这样做的好处：表单取值、serialize、required 校验、事件语义全都不变，界面只接管「呈现与键盘交互」。
// 无障碍契约：触发按钮是 role=combobox，弹出列表是 role=listbox，焦点始终留在触发按钮上，用 aria-activedescendant 标记当前项。
// 原生 select 继续保存表单值，自绘控件负责呈现和键盘交互。
// select → control 的映射用 WeakMap：页面重绘时旧 select 被回收，映射随之释放，不会造成内存泄漏。
const controls = new WeakMap();
// 当前打开的菜单（同一时刻只允许一个）；null 表示没有菜单处于展开状态。
let active = null;
// 全局监听只安装一次：多次 enhanceSelects 调用不会重复绑定 document 事件。
let installed = false;
// 自增序号：为没有 id/name 的控件、以及 id 冲突时生成唯一后缀。
let sequence = 0;
// 是否降级动画：读取系统的「减少动态效果」偏好，开启时跳过入场动画。
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
// 可选项判定：（未禁用、未隐藏、且不在被禁用的 optgroup 里）；键盘导航与点击都只认可选项。
const available = option => !option.disabled && !option.hidden && !option.closest('optgroup[disabled]');
// 能否聚焦：仍挂在文档上、未 disabled、不在 inert 容器里、且有实际盒子（getClientRects 非空）。
// isConnected 判断是必要的：整页 innerHTML 重建后，旧 trigger 已是游离节点，再 focus 会丢焦点。
const canFocus = element => element?.isConnected && !element.disabled && !element.closest('[inert]') && element.getClientRects().length;

// 控件可读名：优先 aria-labelledby，其次 aria-label，最后退回 label 文本 / name / 默认「选择选项」。
// 名字会写进触发按钮的 aria-label（「收入达成率：89.74%」），读屏用户能连标签带当前值一起听到。
function controlLabel(select) {
// aria-labelledby 指向一个或多个元素 id，取它们的 textContent 拼接。
  const labelledBy = select.getAttribute('aria-labelledby');
// 多个 id 用空白分隔，逐个查 DOM 并拼成一句；元素不存在时忽略该 id。
  if (labelledBy) return labelledBy.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
// 回退顺序：aria-label → 外层 label 的直接 span（表单里「标签 + 控件」的常见结构）→ name → 默认文案。
  return select.getAttribute('aria-label') || select.closest('label')?.querySelector(':scope > span')?.textContent?.trim() || select.name || '选择选项';
}

// 把原生 select 的当前状态同步到自绘控件：显示文本、title、禁用、必填、可读名。
// 每次 option 变化、表单 reset、外部改值后都要调用它，自绘控件本身不保存任何值。
function sync(control) {
// 解构出三件套：原生 select（值来源）、触发按钮、显示文本节点。
  const { select, trigger, value } = control;
// 显示的是 option 的 label（可能带额外说明），没有选中项时显示「请选择」。
  value.textContent = select.selectedOptions[0]?.label || '请选择';
// title 悬浮提示：长选项被 CSS 省略号截断时，悬停仍能看到完整文字。
  trigger.title = select.selectedOptions[0]?.title || value.textContent;
// 禁用状态跟随原生控件，视觉与行为一起禁用。
  trigger.disabled = select.disabled;
// aria-disabled 让读屏也能知道不可用（button 的 disabled 已能被识别，这里是双保险）。
  trigger.setAttribute('aria-disabled', String(select.disabled));
// 可读名 = 字段名 + 当前值：Tab 到触发按钮时读屏会念出「收入达成率：89.74%」。
  trigger.setAttribute('aria-label', `${control.label}：${value.textContent}`);
// 必填标记随原生 required 走，表单校验语义保持一致。
  if (select.required) trigger.setAttribute('aria-required', 'true');
// 非必填时移除属性而不是写 false：避免读屏念出「不必填」这类多余信息。
  else trigger.removeAttribute('aria-required');
}

// 设置当前高亮项：只改视觉与 aria-activedescendant，不移动真实焦点（焦点始终在触发按钮上）。
// 第二个参数 scroll 用于鼠标悬停时不触发滚动，避免「鼠标停在某项上整页抖动」。
function setActive(index, scroll = true) {
  if (!active) return;
// 按原生 option 的下标找条目，并再次确认它此刻仍可选项（禁用项不允许高亮）。
  const item = active.items.find(entry => entry.index === index && available(entry.option));
  if (!item) return;
// 记录当前下标：回车确认、上下方向键都以它为基准。
  active.index = index;
// 高亮用 class 切换而不是重新渲染整张列表，菜单打开时的滚动位置保持不变。
  for (const entry of active.items) entry.element.classList.toggle('is-focused', entry === item);
// 把高亮项告诉读屏：焦点虽在按钮上，读屏会念出被引用的 option。
  active.control.trigger.setAttribute('aria-activedescendant', item.element.id);
// 键盘导航时把高亮项滚进视野：nearest 保证不必要不滚动，instant 避免与菜单入场动画叠加。
  if (scroll) item.element.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
}

// 定位菜单：贴住触发按钮，按可视视口边界夹取，空间不足时向上翻转，并把方向写进 dataset 供动画使用。
// 只读 getBoundingClientRect 与 visualViewport，不修改任何业务状态，因此可以安全地在打开后立即调用。
function positionMenu() {
  if (!active) return;
// 从 active 取菜单与控件：本函数只对当前打开的菜单生效。
  const { menu, control } = active;
// 按钮已不可用（被禁用、被移出文档）时直接关闭菜单，避免留下悬空的浮层。
  if (!canFocus(control.trigger)) { closeSelects(); return; }
// 以触发按钮的视口矩形为锚点，所有偏移都相对它计算。
  const rect = control.trigger.getBoundingClientRect();
// 可视视口：移动端软键盘弹出时 innerHeight 不变，只有 visualViewport 会缩小。
  const viewport = window.visualViewport;
// 左右上下各留 8px 安全边距：菜单不贴死屏幕边缘，触屏下也便于点按。
  const leftEdge = (viewport?.offsetLeft || 0) + 8;
// 顶边同样从可视视口的偏移算起，兼容页面被缩放的场景。
  const topEdge = (viewport?.offsetTop || 0) + 8;
// 可视宽度取 visualViewport，不支持时才退回文档宽度。
  const width = viewport?.width || document.documentElement.clientWidth;
// 可视高度同理：优先 visualViewport.height。
  const height = viewport?.height || window.innerHeight;
// 右边界再扣 8px，保证菜单右侧与屏幕边缘之间仍有余量。
  const rightEdge = leftEdge + width - 16;
// 下边界同理。
  const bottomEdge = topEdge + height - 16;
// 菜单宽度：至少与按钮同宽（顶栏紧凑控件 192px、其余 200px），最多不超可视宽度减 16。
  const measuredWidth = Math.min(Math.max(rect.width, control.select.classList.contains('topbar-select') ? 192 : 200), width - 16);
// 宽度直接写死像素：菜单是绝对定位浮层，不参与父容器布局。
  menu.style.width = `${measuredWidth}px`;
// 先用 320px 探测内容高度，下面再按可用空间收紧。
  menu.style.maxHeight = '320px';
// 期望高度 = 内容自然高度（+2px 边框），上限 320px；超过则菜单内部滚动。
  const desiredHeight = Math.min(menu.scrollHeight + 2, 320);
// 按钮下方剩余空间。
  const below = bottomEdge - rect.bottom - 8;
// 按钮上方剩余空间。
  const above = rect.top - topEdge - 8;
// 只有当下方放不下、且上方更宽裕时才向上翻转，否则仍向下展开（符合阅读习惯）。
  const upward = below < desiredHeight && above > below;
// 可用空间至少给 48px：即使空间极小也留一行可见，而不是缩成 0 高。
  const room = Math.max(48, upward ? above : below);
// 最终高度取三者最小值，保证既不溢出锚点方向，也不超出视口。
  const menuHeight = Math.min(desiredHeight, room, height - 16);
// 写入实际高度上限，内容超出时由 CSS 产生内部滚动。
  menu.style.maxHeight = `${menuHeight}px`;
// 水平夹取：默认左对齐按钮，靠右放不下时整体左移，但绝不越出左右边界。
  menu.style.left = `${Math.max(leftEdge, Math.min(rect.left, rightEdge - measuredWidth))}px`;
// 垂直定位：向下时贴按钮下沿 8px，向上时贴按钮上沿 8px，并整体夹在视口内。
  menu.style.top = `${Math.max(topEdge, Math.min(upward ? rect.top - 8 - menuHeight : rect.bottom + 8, bottomEdge - menuHeight))}px`;
// 方向写进 dataset：CSS（圆角与阴影方向）与入场动画都读它，避免两处各算一遍。
  menu.dataset.direction = upward ? 'up' : 'down';
// 缩放原点设在贴住按钮的那一侧，展开动画看起来像「从按钮里长出来」。
  menu.style.transformOrigin = upward ? '50% 100%' : '50% 0%';
}

// 关闭菜单：撤销 aria 状态、取消动画、移除节点；restoreFocus 为真时把焦点还给触发按钮。
// 默认不抢焦点：点击外部关闭时焦点应留在用户刚点的地方，只有 Esc / 再次点击按钮才还焦点。
export function closeSelects({ restoreFocus = false } = {}) {
  if (!active) return;
// 先把 active 存下来再置空：下面的 DOM 操作可能触发 focus/scroll 事件，重入时不会二次关闭。
// 置空（active = null）是关闭动作的「提交点」，之后任何监听都认为已经没有菜单了。
  const previous = active;
  active = null;
// aria-expanded 必须回到 false，否则读屏会一直以为列表是展开的。
  previous.control.trigger.setAttribute('aria-expanded', 'false');
// 去掉活动项引用：菜单已不存在，继续引用会造成无效的 aria 关系。
  previous.control.trigger.removeAttribute('aria-activedescendant');
// 移除 is-open：按钮的箭头与底色由 CSS 依据这个类切换。
  previous.control.trigger.classList.remove('is-open');
// 取消入场动画：立即移除节点时若动画还在跑，会看到一帧残影。
  previous.animation?.cancel();
// popover 可能已被浏览器自动关闭（例如点击外部），matches 判断 + try/catch 双保险，避免抛错中断清理。
  try { if (previous.menu.matches(':popover-open')) previous.menu.hidePopover(); } catch {}
// 从 DOM 移除菜单节点：每次打开都新建，不缓存，保证选项与当前 select 状态一致。
  previous.menu.remove();
// 还焦点：preventScroll 防止聚焦时页面被滚动到按钮位置，破坏用户当前的浏览位置。
  if (restoreFocus && canFocus(previous.control.trigger)) previous.control.trigger.focus({ preventScroll: true });
}

// 确认选择：写回原生 select、同步显示、关闭菜单、派发 input/change，最后把焦点交还触发按钮。
// 写回原生控件是唯一改值方式，所以表单逻辑与后端取值完全不受自绘 UI 影响。
function commit(index) {
  if (!active) return;
// 取当前控件：必须在 closeSelects 之前取，否则 active 已置空。
  const { control } = active;
// 按原生下标取 option。
  const option = control.select.options[index];
// 三重校验：下标有效、该项可选项、控件未禁用，任意一条不满足就不改值。
  if (!option || !available(option) || control.select.disabled) return;
// 记录是否真的变了：没变就不派发事件，避免无意义的重算与请求。
  const changed = control.select.selectedIndex !== index;
// 直接改 selectedIndex：等价于用户在原生下拉里点选，required 校验也随之满足。
// 随后 sync(control) 同步显示文本与 aria-label，再 closeSelects() 收起菜单——change 处理里可能重绘整页，此时菜单必须已经不在了。
  control.select.selectedIndex = index;
  sync(control);
  closeSelects();
// 只有值真的改变才派发事件。
  if (changed) {
// 先 input 后 change：与浏览器原生 select 的事件顺序保持一致。
    control.select.dispatchEvent(new Event('input', { bubbles: true }));
// change 冒泡到 document，界面的表单监听器（bindForms）据此触发筛选/重算。
    control.select.dispatchEvent(new Event('change', { bubbles: true }));
  }
  // change 可同步重建整个页面；把焦点交还重建后的同一控件。
// 把焦点恢复放到微任务：change 可能同步重建整个 #app，等新 DOM 就位后再聚焦。
  queueMicrotask(() => {
// 重建后旧 trigger 已脱离文档，按 id 找新生成的同名触发按钮。
    const trigger = control.trigger.isConnected ? control.trigger : document.getElementById(control.trigger.id);
// 找到且可聚焦才恢复，防止把焦点丢到 body。
    if (canFocus(trigger)) trigger.focus({ preventScroll: true });
  });
}

// 打开菜单：新建 listbox + option 列表、处理 optgroup 小标题与空态、挂载（优先 popover 顶层）、定位、设初始高亮、绑定局部事件与入场动画。
// edge 决定初始高亮：'first'/'last' 来自 Home/End，未指定时定位到当前选中项。
function openMenu(control, edge) {
// 禁用控件不打开菜单（点击触发按钮也不会响应）。
// 打开前先 closeSelects() 关闭可能存在的其它菜单，保证同一时刻只有一个浮层。
  if (control.select.disabled) return;
  closeSelects();
  sync(control);
// 每次打开都新建菜单节点：选项数量/文案可能随数据变化，复用节点容易残留旧状态。
  const menu = document.createElement('div');
// 玻璃风格类名：模糊、投影与圆角全部由 CSS 定义。
  menu.className = 'glass-select-menu';
// 固定命名规则：触发按钮的 aria-controls 指向它，便于调试与自动化测试定位。
  menu.id = `${control.trigger.id}--options`;
// listbox 语义：读屏会按「列表，N 项」播报。
  menu.setAttribute('role', 'listbox');
// 列表的可读名与字段名一致，避免读屏只说「列表」。
  menu.setAttribute('aria-label', control.label);
// popover=manual：让菜单进入浏览器顶层图层，不会被父容器的 overflow/stacking 裁剪。
// 手动模式（manual）意味着显隐完全由我们控制，不会被浏览器「轻触外部自动关闭」打乱焦点逻辑。
  menu.setAttribute('popover', 'manual');
// 收集 [{index, option, element}]，后续键盘导航与点击都基于这份数组。
  const items = [];
// 记录上一个 optgroup：只在分组切换时插入一次小标题。
  let previousGroup = null;
// 遍历原生 option 并保留真实下标：提交时要写回 selectedIndex，不能用过滤后的序号。
  for (const [index, option] of [...control.select.options].entries()) {
// 隐藏项不渲染（原生 select 里 hidden option 也不显示）。
    if (option.hidden) continue;
// 取所属分组：用于渲染分组小标题。
    const group = option.closest('optgroup');
// 分组变了才插标题：同一个 optgroup 下的多个选项共享一个小标题。
    if (group && group !== previousGroup) {
// 分组标题节点。
      const heading = document.createElement('div');
// 样式类：小号灰字，不可点击。
      heading.className = 'glass-select-group';
// 标题文字直接取 optgroup 的 label。
      heading.textContent = group.label;
// presentation：告诉读屏这只是视觉分组，不是可选项，避免被当成第 N 项。
      heading.setAttribute('role', 'presentation');
// 插入到当前选项之前。
      menu.append(heading);
    }
// 更新游标，处理「离开分组后进入无分组选项」的情况。
    previousGroup = group;
// 单个选项节点。
    const element = document.createElement('div');
// 选项样式类：padiing、圆角、选中态与高亮态都由它派生。
    element.className = 'glass-select-option';
// 长文本悬浮提示：菜单宽度有限，超长科目名会被省略。
    element.title = option.title || option.label;
// id 用菜单 id + 原生下标：稳定且能反查回 option。
    element.id = `${menu.id}-${index}`;
// 把原生下标写在 data 属性上：点击与悬停时无需再遍历数组。
    element.dataset.optionIndex = String(index);
// option 语义。
    element.setAttribute('role', 'option');
// 选中态用 aria-selected 表达，读屏能念出「已选中」。
    element.setAttribute('aria-selected', String(option.selected));
// 禁用项标 aria-disabled，但仍渲染出来（用户需要看到它存在，只是不可选）。
    element.setAttribute('aria-disabled', String(!available(option)));
// 文字容器：与右侧对勾分开，便于 flex 布局与省略号。
    const label = document.createElement('span');
// 用 textContent 而非 innerHTML：选项文案来自数据，避免注入。
    label.textContent = option.label;
// 选中标记容器。
    const check = document.createElement('span');
// 样式类：只在 aria-selected 为 true 时显示。
    check.className = 'glass-select-check';
// 对勾是纯装饰：语义已由 aria-selected 承担，读屏不必重复。
    check.setAttribute('aria-hidden', 'true');
// 内联 16×16 对勾：不依赖图标模块，菜单节点尽量轻。
    check.innerHTML = '<svg viewBox="0 0 16 16" fill="none"><path d="m3.5 8 3 3 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
// 先文字后标记，保持 flex 两端对齐。
    element.append(label, check);
// 加入菜单。
    menu.append(element);
// 登记条目：键盘导航、悬停高亮与点击提交共用。
    items.push({ index, option, element });
  }
// 所有选项都被隐藏时的空态：不能给用户一个空白浮层。
  if (!items.length) {
// 空态节点。
    const empty = document.createElement('div');
// 样式类：灰字居中、不可点击。
    empty.className = 'glass-select-empty';
// 文案与全局中文风格一致，明确告诉用户是「没有选项」而不是「加载失败」。
    empty.textContent = '暂无可选项';
// 插入空态。
    menu.append(empty);
  }
// 挂载位置：在弹窗里就挂到 dialog 内，保证 tab 顺序与层级都在弹窗内；否则挂 body。
  const host = control.trigger.closest('.dialog') || document.body;
// 先挂载再测量：scrollHeight 需要节点已在文档中才有值。
  host.append(menu);
  try {
// 兼容分支：支持 Popover API 的浏览器走顶层浮层；特性检测用显式抛错进入 catch，而不是两套重复代码。
    if (typeof menu.showPopover !== 'function') throw new Error('popover unavailable');
// 进入顶层图层：菜单不会再被父容器 overflow 裁掉。
    menu.showPopover();
  } catch {
// 不支持 popover 时降级：去掉 popover 属性，改用普通绝对定位。
    menu.removeAttribute('popover');
// 挂到 body：即使原来在 dialog 内，也保证定位基准是视口（position:fixed 的祖先链问题）。
    document.body.append(menu);
  }
// active 是菜单状态的唯一真相：控件、节点、条目、当前下标、首字母搜索缓冲、上次按键时间、动画句柄。
  active = { control, menu, items, index: -1, search: '', lastKey: 0, animation: null };
// 展开状态同步给读屏。
  control.trigger.setAttribute('aria-expanded', 'true');
// 按钮转为展开态（箭头翻转、底色加深）。
  control.trigger.classList.add('is-open');
// 挂载与显隐完成后再定位：此时 scrollHeight 才准确。
  positionMenu();
// 可选项子集：键盘上下移动只在它们之间循环，跳过禁用项。
  const enabled = items.filter(item => available(item.option));
// 当前选中项（可能被禁用，所以用 enabled 里找）。
  const selected = enabled.find(item => item.option.selected);
// 初始高亮规则：Home 打开跳首项、End 打开跳末项，普通打开定位到当前值。
  const first = edge === 'last' ? enabled.at(-1) : edge === 'first' ? enabled[0] : selected || enabled[0];
// 设置初始高亮；没有任何可选项时保持 -1。
  if (first) setActive(first.index);
// 阻止默认的按下行为：否则浏览器会把焦点从触发按钮移走，菜单随之被 focusin 关闭。
  menu.addEventListener('pointerdown', event => { if (event.target.closest('[role=option]')) event.preventDefault(); });
// 鼠标移动时同步高亮（与原生 select 一致），但不动焦点。
  menu.addEventListener('pointermove', event => {
// 触屏跳过悬停高亮：手指移动会连续触发 pointermove，高亮乱跳反而难以点中。
    if (event.pointerType === 'touch') return;
    const option = event.target.closest('[data-option-index]');
// 只在事件目标是选项节点时才高亮；悬停高亮不滚动，用户正在看的区域不应被自动滚动打断。
    if (option) setActive(Number(option.dataset.optionIndex), false);
  });
// 点击选择：与键盘回车走同一个 commit 入口，保证行为一致。
  menu.addEventListener('click', event => {
    const option = event.target.closest('[data-option-index]');
// 提交真实原生下标。
    if (option) commit(Number(option.dataset.optionIndex));
  });
// 入场动画：系统要求减少动效、或浏览器不支持 WAAPI 时直接跳过。
  if (!reducedMotion() && typeof menu.animate === 'function') {
// 位移方向跟着展开方向走：向下展开时从上方 -6px 落下，向上展开时从下方 +6px 升起。
    const shift = menu.dataset.direction === 'up' ? 6 : -6;
// 用 WAAPI 而不是 CSS keyframes：动画句柄可随时 cancel，关闭时不会残留一帧。
    active.animation = menu.animate([
// 起始帧：轻微缩小 + 位移 + 透明，营造「从按钮弹出」的感觉。
      { opacity: 0, transform: `translateY(${shift}px) scale(.97)` },
// 结束帧：回到自然位置与尺寸。
      { opacity: 1, transform: 'translateY(0) scale(1)' }
// 220ms + 快进慢出的缓动：足够被感知，又不至于让键盘操作显得拖沓。
    ], { duration: 220, easing: 'cubic-bezier(.16,1,.3,1)' });
  }
}

// 键盘语义：Enter/Space/方向键打开与移动、Home/End 跳首尾、Esc/Alt+↑ 关闭、单字符做首字母搜索。
// 所有分支都不让焦点离开触发按钮，这是 WAI-ARIA combobox 模式的核心约束。
function keydown(control, event) {
// 输入法组合期间忽略按键（中文候选框的回车不应被当成选中），禁用控件也不响应。
  if (event.isComposing || control.select.disabled) return;
// 只有「当前这个控件」的菜单算展开，其它控件的按键按未展开处理。
  const isOpen = active?.control === control;
// Tab 交还浏览器：关闭菜单但不阻止默认行为，焦点正常前进到下一个控件。
  if (event.key === 'Tab') { if (isOpen) closeSelects(); return; }
// Alt+↑ 是原生 select 的收起手势，保持同一套肌肉记忆。
  if (event.altKey && event.key === 'ArrowUp') {
// 展开时才处理，并把焦点还给按钮（防止某些浏览器把焦点丢到 body）。
    if (isOpen) { event.preventDefault(); closeSelects({ restoreFocus: true }); }
    return;
  }
// 一批「打开/移动」键：未展开时用于打开，展开时用于导航。
  if (['Enter', ' ', 'ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault();
// 未展开时打开菜单：Home/End 顺手决定初始高亮落在首项还是末项。
    if (!isOpen) { openMenu(control, event.key === 'Home' ? 'first' : event.key === 'End' ? 'last' : undefined); return; }
// 展开状态下回车/空格 = 确认当前高亮项。
    if (event.key === 'Enter' || event.key === ' ') { commit(active.index); return; }
    const enabled = active.items.filter(item => available(item.option));
    const current = enabled.findIndex(item => item.index === active.index);
// 方向键在可选项里移动并夹取边界（到顶再按向下仍停最后一项，符合原生 select 行为）。
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : Math.max(0, Math.min(enabled.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)));
// 只设置真实存在的高亮项。
    if (enabled[next]) setActive(enabled[next].index);
    return;
  }
// 首字母搜索只接受「单个可打印字符且无修饰键」，Ctrl/Alt/Meta 组合键留给浏览器与系统。
  if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
  event.preventDefault();
// 直接打字也能打开菜单：与原生 select 行为一致。
  if (!isOpen) openMenu(control);
  if (!active) return;
// 用时间戳判断连续输入，而不是定时器。
  const now = Date.now();
// 700ms 内连续按键累积成前缀（如「市场」→ 市场推广费用），超时则重新开始。
  active.search = now - active.lastKey > 700 ? event.key : active.search + event.key;
// 记录本次按键时间，供下一次判断。
  active.lastKey = now;
// 按本地化规则转小写比较，中文不受影响，英文选项做到大小写不敏感。
  let query = active.search.toLocaleLowerCase();
// 连按同一个字母时退化为单字符：在多个同首字母选项之间循环跳转。
  if ([...query].every(character => character === query[0])) query = query[0];
  const enabled = active.items.filter(item => available(item.option));
  const current = enabled.findIndex(item => item.index === active.index);
// 从当前项之后开始找，找到结尾再绕回开头，避免每次都停在第一项。
  const ordered = [...enabled.slice(current + 1), ...enabled.slice(0, current + 1)];
// 前缀匹配的是显示文案（label），与用户看到的文字一致。
  const found = ordered.find(item => item.option.label.trim().toLocaleLowerCase().startsWith(query));
// 命中就移动高亮；没命中保持原样。
  if (found) setActive(found.index);
}

// 增强入口：可对整页或某个子树执行；幂等，重复调用只同步状态、不重复插按钮。
// 每次整页重绘后由主界面调用，因此必须便宜且安全：已有的控件只做一次 sync。
export function enhanceSelects(root = document) {
// 确保全局监听已安装（只装一次，重复调用直接返回）。
  installSelects();
// root 自身就是 select 时也要处理：弹窗里经常只增强一小段表单。
  const selects = root.matches?.('select') ? [root] : [...root.querySelectorAll('select')];
// 逐个处理，单个控件失败不影响其余控件。
  for (const select of selects) {
// 多选、列表式（size>1）、或显式声明 data-native-select 的控件保留原生外观，不强行增强。
    if (select.multiple || select.size > 1 || select.dataset.nativeSelect === 'true') continue;
// 已经增强过的控件直接从映射里取出。
    const existing = controls.get(select);
// 重复调用只同步状态（显示值可能已被别处改过），不重复插入触发按钮。
    if (existing) { sync(existing); continue; }
// 自绘触发按钮：真正的可聚焦控件。
    const trigger = document.createElement('button');
// 先算出可读名，后面写进 aria-label。
    const label = controlLabel(select);
// 稳定 key：优先用原生 id，其次 name，最后自增序号，保证同一控件每次生成同一个 id。
    let stableKey = select.id || (select.name ? `field-${select.name}` : `control-${++sequence}`);
// 净化成合法 id 片段：允许各语言字母、数字、下划线与连字符，其余替换为 -。
    stableKey = stableKey.replace(/[^\p{L}\p{N}_-]/gu, '-');
// 按约定命名，便于从触发按钮反查原生控件。
    let triggerId = `${stableKey}--combobox`;
// id 冲突时追加序号：同一表单可能在弹窗与主页面各渲染一份。
    if (document.getElementById(triggerId)) triggerId += `-${++sequence}`;
// 必须是 button：默认的 submit 会在按回车时意外提交表单。
    trigger.type = 'button';
// 写入唯一 id，供 aria-controls / 重建后找回使用。
    trigger.id = triggerId;
// 记录来源标识：调试时能知道这个触发按钮对应哪个原生字段。
    trigger.dataset.selectSource = select.id || select.name || stableKey;
// 按原 select 的视觉角色加修饰类：顶栏用紧凑尺寸，筛选器用筛选样式。
    trigger.className = `glass-select-trigger${select.classList.contains('topbar-select') ? ' glass-select-compact' : ''}${select.classList.contains('filter-select') ? ' glass-select-filter' : ''}`;
// combobox 语义：读屏会按「组合框」播报并支持展开/收起状态。
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-expanded', 'false');
// aria-expanded 初始为收起状态；aria-haspopup=listbox 声明弹层是列表，读屏会提示「按回车展开列表」。
    trigger.setAttribute('aria-haspopup', 'listbox');
// 与菜单 id 的固定命名规则对应，菜单未打开时指向一个不存在的元素是被允许的。
    trigger.setAttribute('aria-controls', `${triggerId}--options`);
// 显示当前值的文本节点。
    const value = document.createElement('span');
// 样式类：单行省略，长科目名不撑破顶栏。
    value.className = 'glass-select-value';
// 右侧箭头容器。
    const arrow = document.createElement('span');
// 样式类：展开时旋转 180 度。
    arrow.className = 'glass-select-arrow';
// 箭头纯装饰，读屏无需播报。
    arrow.setAttribute('aria-hidden', 'true');
// 内联 16×16 下拉箭头，与菜单对勾同一风格。
    arrow.innerHTML = '<svg viewBox="0 0 16 16" fill="none"><path d="m4.5 6 3.5 3.5L11.5 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
// 文字在左、箭头在右。
    trigger.append(value, arrow);
// 紧贴原生控件插入：保持与 <label> 的相邻关系，标签点击仍能关联。
    select.before(trigger);
// 隐藏原生控件但保留在表单里，值照常提交。
    select.hidden = true;
// 退出 Tab 序列：否则键盘会先停在隐藏控件上，出现「幽灵焦点」。
    select.tabIndex = -1;
// 读屏忽略隐藏控件，语义由 combobox 承担。
    select.setAttribute('aria-hidden', 'true');
// 加类便于 CSS 统一处理（部分浏览器对 hidden 的 display 计算有差异）。
    select.classList.add('glass-select-native');
// 一个控件只需这四个字段：原生节点、按钮、显示值、可读名。
    const control = { select, trigger, value, label };
// 登记映射，供重复增强与键盘处理查回。
// 紧接着 sync(control) 初始化显示文本与 aria 状态，让按钮一插入就是正确内容。
    controls.set(select, control);
    sync(control);
// 点击按钮：已展开则收起并还焦点，否则打开。
    trigger.addEventListener('click', () => active?.control === control ? closeSelects({ restoreFocus: true }) : openMenu(control));
// 键盘交互全部交给 keydown()。
    trigger.addEventListener('keydown', event => keydown(control, event));
// 外部（脚本或原生事件）改值时同步显示，并清除上一次的校验错误态。
    select.addEventListener('change', () => { sync(control); trigger.removeAttribute('aria-invalid'); });
// 原生校验失败时：阻止浏览器的默认气泡，改在自绘按钮上标 aria-invalid 并聚焦，错误提示统一由表单渲染。
    select.addEventListener('invalid', event => { event.preventDefault(); trigger.setAttribute('aria-invalid', 'true'); if (canFocus(trigger)) trigger.focus(); });
  }
}

// 安装全局监听：点击外部、Esc、焦点移出、滚动、视口变化、表单重置都会让菜单关闭。
// 只装一次（installed 守卫），因为主界面每次重绘都会调用 enhanceSelects。
export function installSelects() {
  if (installed) return;
  installed = true;
// 捕获阶段监听 pointerdown：在业务点击处理之前判断这次点击是否落在菜单/按钮之外。
  document.addEventListener('pointerdown', event => {
    if (!active) return;
// 用 composedPath 而不是 contains：能穿透 shadow DOM，也覆盖事件源被移除的情况。
    const path = event.composedPath();
// 点在菜单与触发按钮之外才关闭；点菜单内部不关闭（否则选不中）。
    if (!path.includes(active.menu) && !path.includes(active.control.trigger)) closeSelects();
  }, true);
// Esc 关闭菜单，并阻止事件继续冒泡去关闭整个弹窗。
  document.addEventListener('keydown', event => {
// 只处理 Esc 且仅在菜单展开时生效。
    if (event.key !== 'Escape' || !active) return;
    event.preventDefault();
// 关键：stopPropagation 让 Esc 先作用于下拉菜单，用户不会一按 Esc 就连弹窗一起关掉。
// 随后 closeSelects({restoreFocus:true}) 关闭菜单并把焦点还给触发按钮，键盘用户不会丢失位置。
    event.stopPropagation();
    closeSelects({ restoreFocus: true });
  }, true);
// 焦点移出菜单/按钮时关闭：Tab 到别处后不应留下悬空浮层。
  document.addEventListener('focusin', event => {
// 注意排除触发按钮本身：菜单内部元素通常不可聚焦，但防御性判断仍在。
    if (active && event.target !== active.control.trigger && !active.menu.contains(event.target)) closeSelects();
  });
// 任何容器滚动都会让菜单与按钮错位，所以捕获阶段监听并关闭。
  document.addEventListener('scroll', event => {
// 菜单内部滚动（选项超出 320px）不触发关闭。
    if (active && !active.menu.contains(event.target)) closeSelects();
  }, true);
// 窗口尺寸变化：定位失效，直接关闭，避免菜单飘在错误位置。
  window.addEventListener('resize', () => closeSelects(), { passive: true });
// 移动端软键盘弹出/收起只改变 visualViewport，必须单独监听。
  window.visualViewport?.addEventListener('resize', () => closeSelects(), { passive: true });
// 页面缩放与滚动时可视视口偏移变化，同样关闭菜单。
  window.visualViewport?.addEventListener('scroll', () => closeSelects(), { passive: true });
// 表单重置是异步生效的：等微任务里 DOM 值已重置，再同步自绘控件的显示文本。
  document.addEventListener('reset', event => queueMicrotask(() => enhanceSelects(event.target)));
}
