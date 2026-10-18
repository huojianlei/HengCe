// 原生 select 继续保存表单值，自绘控件负责呈现和键盘交互。
const controls = new WeakMap();
let active = null;
let installed = false;
let sequence = 0;
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const available = option => !option.disabled && !option.hidden && !option.closest('optgroup[disabled]');
const canFocus = element => element?.isConnected && !element.disabled && !element.closest('[inert]') && element.getClientRects().length;

function controlLabel(select) {
  const labelledBy = select.getAttribute('aria-labelledby');
  if (labelledBy) return labelledBy.split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
  return select.getAttribute('aria-label') || select.closest('label')?.querySelector(':scope > span')?.textContent?.trim() || select.name || '选择选项';
}

function sync(control) {
  const { select, trigger, value } = control;
  value.textContent = select.selectedOptions[0]?.label || '请选择';
  trigger.disabled = select.disabled;
  trigger.setAttribute('aria-disabled', String(select.disabled));
  trigger.setAttribute('aria-label', `${control.label}：${value.textContent}`);
  if (select.required) trigger.setAttribute('aria-required', 'true');
  else trigger.removeAttribute('aria-required');
}

function setActive(index, scroll = true) {
  if (!active) return;
  const item = active.items.find(entry => entry.index === index && available(entry.option));
  if (!item) return;
  active.index = index;
  for (const entry of active.items) entry.element.classList.toggle('is-focused', entry === item);
  active.control.trigger.setAttribute('aria-activedescendant', item.element.id);
  if (scroll) item.element.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
}

function positionMenu() {
  if (!active) return;
  const { menu, control } = active;
  if (!canFocus(control.trigger)) { closeSelects(); return; }
  const rect = control.trigger.getBoundingClientRect();
  const viewport = window.visualViewport;
  const leftEdge = (viewport?.offsetLeft || 0) + 8;
  const topEdge = (viewport?.offsetTop || 0) + 8;
  const width = viewport?.width || document.documentElement.clientWidth;
  const height = viewport?.height || window.innerHeight;
  const rightEdge = leftEdge + width - 16;
  const bottomEdge = topEdge + height - 16;
  const measuredWidth = Math.min(Math.max(rect.width, control.select.classList.contains('topbar-select') ? 192 : 200), width - 16);
  menu.style.width = `${measuredWidth}px`;
  menu.style.maxHeight = '320px';
  const desiredHeight = Math.min(menu.scrollHeight + 2, 320);
  const below = bottomEdge - rect.bottom - 8;
  const above = rect.top - topEdge - 8;
  const upward = below < desiredHeight && above > below;
  const room = Math.max(48, upward ? above : below);
  const menuHeight = Math.min(desiredHeight, room, height - 16);
  menu.style.maxHeight = `${menuHeight}px`;
  menu.style.left = `${Math.max(leftEdge, Math.min(rect.left, rightEdge - measuredWidth))}px`;
  menu.style.top = `${Math.max(topEdge, Math.min(upward ? rect.top - 8 - menuHeight : rect.bottom + 8, bottomEdge - menuHeight))}px`;
  menu.dataset.direction = upward ? 'up' : 'down';
  menu.style.transformOrigin = upward ? '50% 100%' : '50% 0%';
}

export function closeSelects({ restoreFocus = false } = {}) {
  if (!active) return;
  const previous = active;
  active = null;
  previous.control.trigger.setAttribute('aria-expanded', 'false');
  previous.control.trigger.removeAttribute('aria-activedescendant');
  previous.control.trigger.classList.remove('is-open');
  previous.animation?.cancel();
  try { if (previous.menu.matches(':popover-open')) previous.menu.hidePopover(); } catch {}
  previous.menu.remove();
  if (restoreFocus && canFocus(previous.control.trigger)) previous.control.trigger.focus({ preventScroll: true });
}

function commit(index) {
  if (!active) return;
  const { control } = active;
  const option = control.select.options[index];
  if (!option || !available(option) || control.select.disabled) return;
  const changed = control.select.selectedIndex !== index;
  control.select.selectedIndex = index;
  sync(control);
  closeSelects();
  if (changed) {
    control.select.dispatchEvent(new Event('input', { bubbles: true }));
    control.select.dispatchEvent(new Event('change', { bubbles: true }));
  }
  // change 可同步重建整个页面；把焦点交还重建后的同一控件。
  queueMicrotask(() => {
    const trigger = control.trigger.isConnected ? control.trigger : document.getElementById(control.trigger.id);
    if (canFocus(trigger)) trigger.focus({ preventScroll: true });
  });
}

function openMenu(control, edge) {
  if (control.select.disabled) return;
  closeSelects();
  sync(control);
  const menu = document.createElement('div');
  menu.className = 'glass-select-menu';
  menu.id = `${control.trigger.id}--options`;
  menu.setAttribute('role', 'listbox');
  menu.setAttribute('aria-label', control.label);
  menu.setAttribute('popover', 'manual');
  const items = [];
  let previousGroup = null;
  for (const [index, option] of [...control.select.options].entries()) {
    if (option.hidden) continue;
    const group = option.closest('optgroup');
    if (group && group !== previousGroup) {
      const heading = document.createElement('div');
      heading.className = 'glass-select-group';
      heading.textContent = group.label;
      heading.setAttribute('role', 'presentation');
      menu.append(heading);
    }
    previousGroup = group;
    const element = document.createElement('div');
    element.className = 'glass-select-option';
    element.id = `${menu.id}-${index}`;
    element.dataset.optionIndex = String(index);
    element.setAttribute('role', 'option');
    element.setAttribute('aria-selected', String(option.selected));
    element.setAttribute('aria-disabled', String(!available(option)));
    const label = document.createElement('span');
    label.textContent = option.label;
    const check = document.createElement('span');
    check.className = 'glass-select-check';
    check.setAttribute('aria-hidden', 'true');
    check.innerHTML = '<svg viewBox="0 0 16 16" fill="none"><path d="m3.5 8 3 3 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    element.append(label, check);
    menu.append(element);
    items.push({ index, option, element });
  }
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'glass-select-empty';
    empty.textContent = '暂无可选项';
    menu.append(empty);
  }
  const host = control.trigger.closest('.dialog') || document.body;
  host.append(menu);
  try {
    if (typeof menu.showPopover !== 'function') throw new Error('popover unavailable');
    menu.showPopover();
  } catch {
    menu.removeAttribute('popover');
    document.body.append(menu);
  }
  active = { control, menu, items, index: -1, search: '', lastKey: 0, animation: null };
  control.trigger.setAttribute('aria-expanded', 'true');
  control.trigger.classList.add('is-open');
  positionMenu();
  const enabled = items.filter(item => available(item.option));
  const selected = enabled.find(item => item.option.selected);
  const first = edge === 'last' ? enabled.at(-1) : edge === 'first' ? enabled[0] : selected || enabled[0];
  if (first) setActive(first.index);
  menu.addEventListener('pointerdown', event => { if (event.target.closest('[role=option]')) event.preventDefault(); });
  menu.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch') return;
    const option = event.target.closest('[data-option-index]');
    if (option) setActive(Number(option.dataset.optionIndex), false);
  });
  menu.addEventListener('click', event => {
    const option = event.target.closest('[data-option-index]');
    if (option) commit(Number(option.dataset.optionIndex));
  });
  if (!reducedMotion() && typeof menu.animate === 'function') {
    const shift = menu.dataset.direction === 'up' ? 6 : -6;
    active.animation = menu.animate([
      { opacity: 0, transform: `translateY(${shift}px) scale(.97)` },
      { opacity: 1, transform: 'translateY(0) scale(1)' }
    ], { duration: 220, easing: 'cubic-bezier(.16,1,.3,1)' });
  }
}

function keydown(control, event) {
  if (event.isComposing || control.select.disabled) return;
  const isOpen = active?.control === control;
  if (event.key === 'Tab') { if (isOpen) closeSelects(); return; }
  if (event.altKey && event.key === 'ArrowUp') {
    if (isOpen) { event.preventDefault(); closeSelects({ restoreFocus: true }); }
    return;
  }
  if (['Enter', ' ', 'ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault();
    if (!isOpen) { openMenu(control, event.key === 'Home' ? 'first' : event.key === 'End' ? 'last' : undefined); return; }
    if (event.key === 'Enter' || event.key === ' ') { commit(active.index); return; }
    const enabled = active.items.filter(item => available(item.option));
    const current = enabled.findIndex(item => item.index === active.index);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? enabled.length - 1 : Math.max(0, Math.min(enabled.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)));
    if (enabled[next]) setActive(enabled[next].index);
    return;
  }
  if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
  event.preventDefault();
  if (!isOpen) openMenu(control);
  if (!active) return;
  const now = Date.now();
  active.search = now - active.lastKey > 700 ? event.key : active.search + event.key;
  active.lastKey = now;
  let query = active.search.toLocaleLowerCase();
  if ([...query].every(character => character === query[0])) query = query[0];
  const enabled = active.items.filter(item => available(item.option));
  const current = enabled.findIndex(item => item.index === active.index);
  const ordered = [...enabled.slice(current + 1), ...enabled.slice(0, current + 1)];
  const found = ordered.find(item => item.option.label.trim().toLocaleLowerCase().startsWith(query));
  if (found) setActive(found.index);
}

export function enhanceSelects(root = document) {
  installSelects();
  const selects = root.matches?.('select') ? [root] : [...root.querySelectorAll('select')];
  for (const select of selects) {
    if (select.multiple || select.size > 1 || select.dataset.nativeSelect === 'true') continue;
    const existing = controls.get(select);
    if (existing) { sync(existing); continue; }
    const trigger = document.createElement('button');
    const label = controlLabel(select);
    let stableKey = select.id || (select.name ? `field-${select.name}` : `control-${++sequence}`);
    stableKey = stableKey.replace(/[^\p{L}\p{N}_-]/gu, '-');
    let triggerId = `${stableKey}--combobox`;
    if (document.getElementById(triggerId)) triggerId += `-${++sequence}`;
    trigger.type = 'button';
    trigger.id = triggerId;
    trigger.dataset.selectSource = select.id || select.name || stableKey;
    trigger.className = `glass-select-trigger${select.classList.contains('topbar-select') ? ' glass-select-compact' : ''}${select.classList.contains('filter-select') ? ' glass-select-filter' : ''}`;
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-controls', `${triggerId}--options`);
    const value = document.createElement('span');
    value.className = 'glass-select-value';
    const arrow = document.createElement('span');
    arrow.className = 'glass-select-arrow';
    arrow.setAttribute('aria-hidden', 'true');
    arrow.innerHTML = '<svg viewBox="0 0 16 16" fill="none"><path d="m4.5 6 3.5 3.5L11.5 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    trigger.append(value, arrow);
    select.before(trigger);
    select.hidden = true;
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    select.classList.add('glass-select-native');
    const control = { select, trigger, value, label };
    controls.set(select, control);
    sync(control);
    trigger.addEventListener('click', () => active?.control === control ? closeSelects({ restoreFocus: true }) : openMenu(control));
    trigger.addEventListener('keydown', event => keydown(control, event));
    select.addEventListener('change', () => { sync(control); trigger.removeAttribute('aria-invalid'); });
    select.addEventListener('invalid', event => { event.preventDefault(); trigger.setAttribute('aria-invalid', 'true'); if (canFocus(trigger)) trigger.focus(); });
  }
}

export function installSelects() {
  if (installed) return;
  installed = true;
  document.addEventListener('pointerdown', event => {
    if (!active) return;
    const path = event.composedPath();
    if (!path.includes(active.menu) && !path.includes(active.control.trigger)) closeSelects();
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !active) return;
    event.preventDefault();
    event.stopPropagation();
    closeSelects({ restoreFocus: true });
  }, true);
  document.addEventListener('focusin', event => {
    if (active && event.target !== active.control.trigger && !active.menu.contains(event.target)) closeSelects();
  });
  document.addEventListener('scroll', event => {
    if (active && !active.menu.contains(event.target)) closeSelects();
  }, true);
  window.addEventListener('resize', () => closeSelects(), { passive: true });
  window.visualViewport?.addEventListener('resize', () => closeSelects(), { passive: true });
  window.visualViewport?.addEventListener('scroll', () => closeSelects(), { passive: true });
  document.addEventListener('reset', event => queueMicrotask(() => enhanceSelects(event.target)));
}
