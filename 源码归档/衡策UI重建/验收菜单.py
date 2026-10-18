"""真实输入验收玻璃下拉与窄屏侧栏；不通过隐藏 select 操作状态。"""
import json
import os
import sys
from pathlib import Path

os.environ['TEMP'] = os.environ['TMP'] = 'D:/dev-env/tmp'
from playwright.sync_api import sync_playwright, expect
from 验收辅助 import choose_option, navigate

OUT = Path(__file__).parent / '验收截图'
OUT.mkdir(exist_ok=True)
URL = 'http://127.0.0.1:4178/'
sidebar_only = '--sidebar-only' in sys.argv
results, errors = [], []


def check(value, message):
    if not value:
        raise AssertionError(message)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.set_default_timeout(6000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)

    def fresh(route='overview', width=1440, height=1000):
        page.set_viewport_size({'width': width, 'height': height})
        page.goto(URL + '#' + route)
        expect(page.locator('#main')).to_be_visible()

    def case(name, fn, sidebar=False):
        if sidebar_only and not sidebar:
            return
        try:
            detail = fn()
            results.append({'name': name, 'passed': True, 'detail': detail})
            print('PASS', name, detail or '', flush=True)
        except Exception as error:
            results.append({'name': name, 'passed': False, 'detail': str(error)})
            print('FAIL', name, error, flush=True)
            page.screenshot(path=str(OUT / f'菜单失败-{len(results):02d}.png'), full_page=True, animations='disabled')

    def department():
        fresh('analysis')
        trigger = page.get_by_role('combobox', name='选择分析部门')
        check(trigger.evaluate('(node) => node.tagName') == 'BUTTON', '部门入口仍是系统 select')
        trigger.click()
        expect(page.get_by_role('listbox')).to_be_visible()
        expect(page.get_by_role('listbox').get_by_role('option')).to_have_count(4)
        expect(page.get_by_role('option', name='全部部门', exact=True)).to_have_attribute('aria-selected', 'true')
        page.screenshot(path=str(OUT / '菜单-部门下拉-1440.png'))
        page.get_by_role('option', name='企业业务部', exact=True).click()
        expect(page.get_by_role('listbox')).to_have_count(0)
        expect(trigger).to_contain_text('企业业务部')
        rows = page.locator('#variance-table tbody tr')
        check(rows.count() > 0, '部门筛选后缺少行')
        for row in rows.all():
            expect(row).to_contain_text('企业业务部')
        choose_option(page, '选择分析部门', '全部部门')
        expect(page.locator('#variance-table tbody tr')).to_have_count(16)
        return '自绘四项部门菜单点击后筛选生效，重绘后菜单仍可再次使用'
    case('顶部部门玻璃菜单', department)

    def warning():
        fresh('analysis')
        choose_option(page, '筛选预警等级', '高风险')
        rows = page.locator('#variance-table tbody tr')
        expect(rows).to_have_count(2)
        for row in rows.all():
            expect(row).to_contain_text('高风险')
        choose_option(page, '筛选预警等级', '全部预警等级')
        expect(rows).to_have_count(16)
        return '预警菜单应用真实筛选，并可恢复全部科目'
    case('预警菜单真实筛选', warning)

    def settings():
        fresh()
        page.locator('.sidebar [data-action="settings"]').click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '分析周期', '季度', scope=dialog)
        dialog.get_by_role('textbox', name='分析期间', exact=True).fill('2027-Q2')
        dialog.get_by_role('button', name='保存设置', exact=True).click()
        expect(dialog).to_have_count(0)
        page.locator('.sidebar [data-action="settings"]').click()
        expect(dialog.get_by_role('combobox', name='分析周期')).to_contain_text('季度')
        expect(dialog.get_by_role('textbox', name='分析期间', exact=True)).to_have_value('2027-Q2')
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        return '周期选择进入 FormData，保存重新打开仍为季度'
    case('分析周期菜单与保存', settings)

    def task_and_revision():
        fresh('risks')
        page.locator('[data-action="task-detail"][data-id="a04"]').click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '处理状态', '进行中', scope=dialog)
        dialog.get_by_role('button', name='保存状态', exact=True).click()
        expect(dialog).to_have_count(0)
        expect(page.locator('.task-column').nth(1)).to_contain_text('确认阶段交付排期')
        page.locator('[data-action="revise"][data-id="r13"]').click()
        choose_option(page, '生效期间', '2027-08', scope=dialog)
        dialog.get_by_role('spinbutton', name='修订后预算（元）').fill('1890000.00')
        dialog.get_by_role('textbox', name='修订原因').fill('菜单验收：未来期间选项提交。')
        dialog.locator('input[name="approved"]').check()
        dialog.get_by_role('button', name='记录演示修订', exact=True).click()
        expect(dialog).to_have_count(0)
        page.get_by_role('button', name='修订记录', exact=True).click()
        expect(dialog).to_contain_text('2027-08')
        expect(dialog).to_contain_text('菜单验收')
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        return '整改处理状态与预算修订期间均通过可见菜单选择并成功提交'
    case('整改与修订菜单提交', task_and_revision)

    def background_and_import():
        fresh('data')
        page.get_by_role('button', name='编辑背景', exact=True).click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '经营变更', '无经营变更', scope=dialog)
        dialog.get_by_role('button', name='保存背景', exact=True).click()
        expect(dialog).to_have_count(0)
        expect(page.locator('.background-box .panel-head')).to_contain_text('无经营变更')
        page.get_by_role('button', name='导入工作簿', exact=True).click()
        choose_option(page, '导入方式', '替换本次全部工作簿', scope=dialog)
        expect(dialog.locator('#import-mode')).to_have_value('replace')
        choose_option(page, '导入方式', '追加到本次工作区', scope=dialog)
        expect(dialog.locator('#import-mode')).to_have_value('append')
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        return '经营背景保存生效；导入方式点击后数据源值正确，不打开文件选择器'
    case('经营背景与导入方式菜单', background_and_import)

    def outside_and_escape():
        fresh()
        page.locator('.sidebar [data-action="settings"]').click()
        dialog = page.get_by_role('dialog')
        trigger = dialog.get_by_role('combobox', name='分析周期')
        trigger.click()
        dialog.locator('.dialog-head h2').click()
        expect(page.get_by_role('listbox')).to_have_count(0)
        expect(dialog).to_be_visible()
        expect(trigger).to_contain_text('月度')
        trigger.click()
        page.keyboard.press('Escape')
        expect(page.get_by_role('listbox')).to_have_count(0)
        expect(dialog).to_be_visible()
        expect(trigger).to_be_focused()
        trigger.click()
        page.mouse.click(10, 10)
        expect(page.get_by_role('listbox')).to_have_count(0)
        expect(dialog).to_be_visible()
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        return '点击菜单外或按 Esc 只关闭下拉；下一次 Esc 才关闭父弹窗'
    case('菜单外部点击与分层 Esc', outside_and_escape)

    def keyboard():
        fresh('analysis')
        trigger = page.get_by_role('combobox', name='选择分析部门')
        trigger.focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('listbox')).to_be_visible()
        for key in ['Home', 'ArrowDown', 'ArrowDown', 'ArrowUp', 'Enter']:
            page.keyboard.press(key)
        expect(page.get_by_role('listbox')).to_have_count(0)
        expect(trigger).to_contain_text('企业业务部')
        expect(trigger).to_be_focused()
        page.keyboard.press('Enter')
        page.keyboard.press('ArrowDown')
        page.keyboard.press('Tab')
        expect(page.get_by_role('listbox')).to_have_count(0)
        expect(trigger).not_to_be_focused()
        expect(trigger).to_contain_text('企业业务部')
        return 'Enter 展开、Home/上下定位、Enter 选择；Tab 正常移焦且不提交未确认项'
    case('下拉完整键盘操作', keyboard)

    def small_menu():
        fresh('overview', 390, 844)
        trigger = page.get_by_role('combobox', name='选择分析部门')
        trigger.click()
        popup = page.get_by_role('listbox')
        box = popup.bounding_box()
        check(box['x'] >= 0 and box['x'] + box['width'] <= 390, f'窄屏菜单横向越界：{box}')
        check(box['y'] >= 0 and box['y'] + box['height'] <= 844, f'窄屏菜单纵向越界：{box}')
        page.screenshot(path=str(OUT / '菜单-部门下拉-390.png'))
        popup.get_by_role('option', name='运营支持部', exact=True).click()
        expect(trigger).to_contain_text('运营支持部')
        expect(page.get_by_role('listbox')).to_have_count(0)
        return '390px 下拉可见选项完整、未溢出视口，触摸尺寸点击有效'
    case('窄屏菜单定位与操作', small_menu)

    def sidebar_outside():
        fresh('overview', 390, 844)
        background_button = page.locator('.topbar [data-action="assistant"]')
        box = background_button.bounding_box()
        page.evaluate("document.addEventListener('click', e => { if(e.target.closest('[data-action=assistant]')) window.__backgroundClicks=(window.__backgroundClicks||0)+1; });")
        page.locator('.mobile-menu').click()
        expect(page.locator('.shell.nav-open')).to_be_visible()
        check(page.locator('.workspace').evaluate('(node) => node.inert'), '侧栏打开时背景未 inert')
        # 点击遮罩下面助手按钮的真实中心，验证关闭不会顺带触发背景动作。
        x = box['x'] + box['width'] / 2
        check(x > 224, '测试目标必须在侧栏外')
        y = box['y'] + box['height'] / 2
        page.mouse.click(x, y)
        expect(page.locator('.mobile-menu')).to_have_attribute('aria-expanded', 'false')
        expect(page.locator('.mobile-menu')).to_be_focused()
        check(not page.locator('.workspace').evaluate('(node) => node.inert'), '侧栏关闭后背景仍 inert')
        check(page.evaluate('window.__backgroundClicks || 0') == 0, '关闭遮罩点击穿透到助手按钮')
        expect(page.get_by_role('complementary', name='衡策助手')).to_have_count(0)
        check(page.locator('[role=progressbar]').count() == 0, '关闭侧栏触发背景分析')
        page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().right <= 0")
        return '点击侧栏外关闭并回焦；无背景点击穿透，关闭后恢复正文操作'
    case('窄屏侧栏点击空白关闭', sidebar_outside, sidebar=True)

    def sidebar_inside():
        fresh('overview', 390, 844)
        page.locator('.mobile-menu').click()
        page.locator('.sidebar .workspace-switch').click()
        expect(page.locator('.mobile-menu')).to_have_attribute('aria-expanded', 'true')
        page.keyboard.press('Escape')
        expect(page.locator('.mobile-menu')).to_have_attribute('aria-expanded', 'false')
        expect(page.locator('.mobile-menu')).to_be_focused()
        page.locator('.mobile-menu').click()
        sidebar = page.locator('.sidebar')
        first = sidebar.locator('a[href],button:not([disabled])').first
        last = sidebar.locator('a[href],button:not([disabled])').last
        last.focus()
        page.keyboard.press('Tab')
        expect(first).to_be_focused()
        page.keyboard.press('Shift+Tab')
        expect(last).to_be_focused()
        page.screenshot(path=str(OUT / '菜单-侧栏展开-390.png'))
        page.keyboard.press('Escape')
        expect(page.locator('.mobile-menu')).to_be_focused()
        return '侧栏内部空白保持展开；Esc 回焦，Tab/Shift+Tab 在菜单内闭环'
    case('侧栏内部与键盘逻辑', sidebar_inside, sidebar=True)

    def sidebar_rapid():
        fresh('overview', 390, 844)
        for _ in range(5):
            page.locator('.mobile-menu').click()
            page.mouse.click(380, 250)
            expect(page.locator('.mobile-menu')).to_have_attribute('aria-expanded', 'false')
        navigate(page, 'risks')
        expect(page.get_by_role('heading', name='风险与整改', exact=True)).to_be_visible()
        expect(page.locator('.mobile-menu')).to_have_attribute('aria-expanded', 'false')
        expect(page.locator('#main')).to_be_focused()
        page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().right <= 0")
        check(page.locator('.nav-scrim:visible').count() == 0, '关闭后仍残留遮罩')
        check(not page.locator('body').evaluate("node => node.classList.contains('navigation-open')"), '关闭后滚动锁未解除')
        check(page.locator('.sidebar').evaluate('(node) => node.inert'), '关闭侧栏仍可聚焦')
        return '五次快速打开/点击外部关闭后状态稳定；导航后关闭侧栏并聚焦正文'
    case('侧栏快速开关与导航收起', sidebar_rapid, sidebar=True)

    case('浏览器错误', lambda: check(not errors, str(errors)) or '无 console error / pageerror', sidebar=True)
    path = OUT / ('侧栏验收结果.json' if sidebar_only else '菜单验收结果.json')
    path.write_text(json.dumps({'results': results, 'browserErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()

raise SystemExit(0 if all(item['passed'] for item in results) else 1)
