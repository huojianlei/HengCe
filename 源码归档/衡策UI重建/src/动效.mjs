// 所有业务 DOM 更新保持同步。动画只呈现前后状态，不控制分析、焦点或提交时机。
const OUT = 'cubic-bezier(.22,1,.36,1)';
const SPRING = 'linear(0, .13 7%, .44 17%, .76 29%, .94 42%, 1.025 58%, 1.012 76%, 1)';
const running = new Set();
const closing = new WeakMap();
let installation = null;

const query = selector => document.querySelector(selector);
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false;
const spring = () => window.CSS?.supports('animation-timing-function', SPRING) ? SPRING : 'cubic-bezier(.2,.9,.25,1.04)';
const rect = node => {
  if (!node) return null;
  const r = node.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
};

// A timer is always available alongside WAAPI: background tabs must never block a close callback.
function play(node, frames, options, { group = 'layout', cleanup, finish } = {}) {
  if (!node || reduced() || typeof node.animate !== 'function') {
    cleanup?.();
    finish?.();
    return null;
  }
  let animation;
  try { animation = node.animate(frames, { fill: 'both', easing: OUT, ...options }); }
  catch { cleanup?.(); finish?.(); return null; }
  let settled = false;
  let timer;
  const settle = invokeFinish => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    running.delete(record);
    animation.onfinish = null;
    animation.oncancel = null;
    animation.cancel();
    cleanup?.();
    if (invokeFinish) finish?.();
  };
  const record = { group, node, cancel: () => settle(false), finish: () => settle(true) };
  running.add(record);
  animation.onfinish = record.finish;
  animation.oncancel = record.cancel;
  timer = setTimeout(record.finish, Number(options.duration || 0) + Number(options.delay || 0) + 100);
  return record;
}

function cancelGroup(group) {
  for (const record of [...running]) if (record.group === group) record.cancel();
}

function temporaryStyles(node, values) {
  if (!node) return () => {};
  const old = Object.fromEntries(Object.keys(values).map(key => [key, node.style[key]]));
  Object.assign(node.style, values);
  return () => Object.assign(node.style, old);
}

function navState() {
  const host = query('.sidebar');
  const active = host?.querySelector('.nav-item.active');
  return active ? {
    page: active.dataset.page,
    rect: rect(host.querySelector('.nav-liquid-indicator') || active)
  } : null;
}

function placeNavigation(previous, animate = true) {
  const host = query('.sidebar');
  const active = host?.querySelector('.nav-item.active');
  if (!active) return;
  host.classList.add('has-liquid-nav');
  let indicator = host.querySelector('.nav-liquid-indicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.className = 'nav-liquid-indicator';
    indicator.setAttribute('aria-hidden', 'true');
    host.prepend(indicator);
  }
  const target = rect(active), parent = rect(host);
  Object.assign(indicator.style, {
    left: `${target.left - parent.left + host.scrollLeft}px`,
    top: `${target.top - parent.top + host.scrollTop}px`,
    width: `${target.width}px`, height: `${target.height}px`
  });
  if (!animate || reduced() || !previous?.rect || previous.page === active.dataset.page) return;
  const dx = previous.rect.left - target.left, dy = previous.rect.top - target.top;
  if (Math.abs(dx) + Math.abs(dy) < 1) return;
  const sx = Math.max(.9, Math.min(1.1, previous.rect.width / target.width));
  const sy = Math.max(.9, Math.min(1.1, previous.rect.height / target.height));
  play(indicator, [
    { transform: `translate(${dx}px,${dy}px) scale(${sx},${sy})`, offset: 0 },
    { transform: `translate(${dx * .14}px,${dy * .14}px) scale(.985,1.075)`, offset: .55 },
    { transform: 'translate(0,0) scale(1,1)', offset: 1 }
  ], { duration: 500, easing: OUT }, { group: 'navigation' });
}

/** Call immediately before replacing #app.innerHTML. No asynchronous DOM work. */
export function captureLayout() {
  const main = query('#main');
  const assistant = query('.content-layout > .assistant');
  const sidebar = query('.sidebar');
  const snapshot = {
    page: main?.dataset.page ?? null,
    main: rect(main),
    assistant: assistant ? { node: assistant, rect: rect(assistant) } : null,
    nav: navState(),
    sidebar: sidebar ? { open: Boolean(sidebar.closest('.nav-open')), transform: getComputedStyle(sidebar).transform } : null,
    scrolls: main ? [...main.querySelectorAll('.table-scroll')].map(node => ({ x: node.scrollLeft, y: node.scrollTop })) : []
  };
  // Capture the interpolated bounds before releasing a previous transition.
  cancelGroup('layout');
  cancelGroup('navigation');
  return snapshot;
}

function animateAssistantLayout(before, main, assistant) {
  const target = rect(main), parent = rect(main.parentElement);
  const changedWidth = before.main && Math.abs(before.main.width - target.width) > 1;
  let restoreAssistant = () => {};
  if (assistant) {
    const bounds = rect(assistant);
    // Keep the assistant at its destination while the neighboring content changes width.
    if (changedWidth) restoreAssistant = temporaryStyles(assistant, {
      position: 'fixed', left: `${bounds.left}px`, top: `${bounds.top}px`,
      width: `${bounds.width}px`, height: `${bounds.height}px`, margin: '0'
    });
    play(assistant, [
      { opacity: 0, transform: 'translateX(28px)' },
      { opacity: 1, transform: 'translateX(0)' }
    ], { duration: 460, easing: spring() });
  } else if (before.assistant?.node) {
    // Reuse the detached old node as a noninteractive exit image; no duplicated IDs remain.
    const ghost = before.assistant.node, bounds = before.assistant.rect;
    ghost.classList.add('motion-ghost');
    ghost.inert = true;
    ghost.setAttribute('aria-hidden', 'true');
    ghost.removeAttribute('id');
    ghost.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
    Object.assign(ghost.style, {
      position: 'fixed', left: `${bounds.left}px`, top: `${bounds.top}px`,
      width: `${bounds.width}px`, height: `${bounds.height}px`, margin: '0',
      pointerEvents: 'none', zIndex: '38', transform: 'none'
    });
    document.body.append(ghost);
    play(ghost, [
      { opacity: 1, transform: 'translateX(0)' },
      { opacity: 0, transform: 'translateX(32px)' }
    ], { duration: 220, easing: 'cubic-bezier(.4,0,1,1)' }, { cleanup: () => ghost.remove() });
  }
  if (!changedWidth) return;
  const restoreMain = temporaryStyles(main, {
    flex: '0 0 auto', width: `${target.width}px`,
    marginLeft: `${target.left - parent.left}px`, marginRight: '0'
  });
  const restoreParent = temporaryStyles(main.parentElement, { overflowX: 'clip' });
  // Width interpolation intentionally reflows text instead of scaling financial figures.
  play(main, [
    { width: `${before.main.width}px`, marginLeft: `${before.main.left - parent.left}px` },
    { width: `${target.width}px`, marginLeft: `${target.left - parent.left}px` }
  ], { duration: 480, easing: OUT }, {
    cleanup: () => { restoreAssistant(); restoreMain(); restoreParent(); }
  });
}

/** Call after shell insertion and form binding, before any caller's synchronous focus(). */
export function animateLayout(before = {}) {
  const main = query('#main');
  if (!main) return;
  const sidebar = query('.sidebar');
  const menuChanged = before.sidebar && sidebar && before.sidebar.open !== Boolean(sidebar.closest('.nav-open'));
  placeNavigation(before.nav, !menuChanged);
  const pageChanged = before.page !== main.dataset.page;
  if (!pageChanged && before.scrolls) {
    main.querySelectorAll('.table-scroll').forEach((node, index) => {
      const saved = before.scrolls[index];
      if (saved) { node.scrollLeft = saved.x; node.scrollTop = saved.y; }
    });
  }
  if (reduced()) return;
  if (menuChanged && window.matchMedia('(max-width: 760px)').matches) {
    const open = Boolean(sidebar.closest('.nav-open'));
    play(sidebar, [
      { transform: before.sidebar.transform },
      { transform: getComputedStyle(sidebar).transform }
    ], { duration: open ? 440 : 220, easing: open ? spring() : OUT });
  }
  const assistant = query('.content-layout > .assistant');
  const toggledAssistant = Boolean(before.assistant) !== Boolean(assistant);
  if (toggledAssistant && before.main) animateAssistantLayout(before, main, assistant);
  if (pageChanged) {
    play(main, [
      { opacity: 0, transform: 'translateY(12px)' },
      { opacity: 1, transform: 'translateY(0)' }
    ], { duration: 480, easing: spring() });
  }
}

/** Existing modal focus and submit binding can run immediately after this call. */
export function animateDialog() {
  cancelGroup('dialog');
  const backdrop = query('#overlay')?.firstElementChild;
  const dialog = backdrop?.querySelector('.dialog');
  if (!dialog || reduced()) return;
  play(backdrop, [{ opacity: 0 }, { opacity: 1 }], { duration: 240 }, { group: 'dialog' });
  play(dialog, [
    { opacity: .2, transform: dialog.classList.contains('drawer') ? 'translateX(48px)' : 'translateY(20px) scale(.975)' },
    { opacity: 1, transform: dialog.classList.contains('drawer') ? 'translateX(0)' : 'translateY(0) scale(1)' }
  ], { duration: 420, easing: spring() }, { group: 'dialog' });
}

/** A stale close never clears or refocuses a newer dialog. Returns a settled Promise. */
export function closeDialogMotion(callback) {
  const overlay = query('#overlay'), backdrop = overlay?.firstElementChild;
  const dialog = backdrop?.querySelector('.dialog');
  if (!backdrop || !dialog || reduced()) {
    callback?.();
    return Promise.resolve();
  }
  if (closing.has(backdrop)) return closing.get(backdrop);
  const currentTransform = getComputedStyle(dialog).transform;
  const currentOpacity = getComputedStyle(backdrop).opacity;
  cancelGroup('dialog');
  let resolveDone;
  const completion = new Promise(resolve => { resolveDone = resolve; });
  closing.set(backdrop, completion);
  play(dialog, [
    { transform: currentTransform === 'none' ? 'translate(0,0)' : currentTransform },
    { transform: dialog.classList.contains('drawer') ? 'translateX(24px)' : 'translateY(8px) scale(.99)' }
  ], { duration: 180, easing: 'cubic-bezier(.4,0,1,1)' }, { group: 'dialog' });
  play(backdrop, [{ opacity: currentOpacity }, { opacity: 0 }], { duration: 180 }, {
    group: 'dialog',
    cleanup: () => { closing.delete(backdrop); resolveDone(); },
    finish: () => { if (overlay.firstElementChild === backdrop) callback?.(); }
  });
  return completion;
}

/** Install once. The returned disposer supports plugin unmount; pagehide also cleans up. */
export function installMotion() {
  if (installation) return installation;
  const controller = new AbortController();
  const { signal } = controller;
  const preference = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const onPreference = () => {
    if (reduced()) for (const record of [...running]) record.finish();
    placeNavigation(null, false);
  };
  const dispose = () => {
    controller.abort();
    preference?.removeEventListener?.('change', onPreference);
    for (const record of [...running]) record.cancel();
    document.querySelectorAll('.motion-ghost,.liquid-ripple').forEach(node => node.remove());
    installation = null;
  };
  installation = dispose;
  document.addEventListener('pointerdown', event => {
    if (reduced() || event.button !== 0) return;
    const button = event.target.closest?.('.btn,.icon-btn');
    if (!button || button.disabled || button.closest('[inert]')) return;
    const bounds = button.getBoundingClientRect();
    const size = Math.max(bounds.width, bounds.height) * 2;
    const ripple = document.createElement('span');
    ripple.className = 'liquid-ripple';
    ripple.setAttribute('aria-hidden', 'true');
    Object.assign(ripple.style, {
      width: `${size}px`, height: `${size}px`,
      left: `${event.clientX - bounds.left - size / 2}px`,
      top: `${event.clientY - bounds.top - size / 2}px`
    });
    button.append(ripple);
    play(ripple, [
      { transform: 'scale(.12)', opacity: .3 },
      { transform: 'scale(1)', opacity: 0 }
    ], { duration: 520, easing: OUT }, { group: 'ripple', cleanup: () => ripple.remove() });
  }, { passive: true, signal });
  window.addEventListener('resize', () => {
    cancelGroup('layout');
    cancelGroup('navigation');
    placeNavigation(null, false);
  }, { passive: true, signal });
  window.addEventListener('pagehide', dispose, { once: true, signal });
  preference?.addEventListener?.('change', onPreference);
  placeNavigation(null, false);
  return dispose;
}
